"""MAF Workflow — replaces orchestrator.py + execution.py + approval.py + input_handler.py.

Uses Microsoft Agent Framework's Executor/Workflow/HITL patterns to orchestrate
the agent pipeline: PM → Architect → Cost → BV → ROI → Presentation.

Each pipeline step is an Executor subclass wrapping the existing agent class.
Approval gates and two-phase assumption flows use ctx.request_info / @response_handler.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_framework import (
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
    response_handler,
)

from agents.state import AgentState
from agents.pm_agent import ProjectManager, AGENT_INFO
from agents.architect_agent import ArchitectAgent
from agents.cost_agent import CostAgent
from agents.business_value_agent import BusinessValueAgent
from agents.roi_agent import ROIAgent
from agents.presentation_agent import PresentationAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared pipeline message types (flow between executors via ctx.send_message)
# ---------------------------------------------------------------------------

DEFAULT_ACTIVE_AGENTS = ["architect", "cost", "business_value", "roi", "presentation"]


@dataclass
class PipelineMessage:
    """Wraps AgentState + metadata flowing between executors."""
    state: AgentState
    project_id: str
    execution_mode: str = "guided"  # "guided" or "fast-run"
    active_agents: list[str] = field(default_factory=lambda: list(DEFAULT_ACTIVE_AGENTS))


# ---------------------------------------------------------------------------
# HITL request/response types
# ---------------------------------------------------------------------------

@dataclass
class ApprovalRequest:
    """Sent to the user after an agent step completes."""
    step: str
    summary: str
    step_output: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssumptionsRequest:
    """Sent to the user when cost/BV agent needs input."""
    step: str  # "business_value" or "cost"
    assumptions: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAST_RUN_GATES = {"business_value", "architect", "presentation"}
REQUIRED_STEPS = {"architect"}  # Pipeline cannot continue without these


def _should_pause(mode: str, step: str) -> bool:
    """Decide whether to pause for approval after a step."""
    if mode == "fast-run":
        return step in FAST_RUN_GATES
    return True  # guided mode: always pause


# ---------------------------------------------------------------------------
# Base executor with common helpers
# ---------------------------------------------------------------------------

class PipelineExecutor(Executor):
    """Base class for pipeline step executors."""

    def __init__(self, id: str, step_name: str):
        super().__init__(id=id)
        self.step_name = step_name
        self.pm = ProjectManager()


# ---------------------------------------------------------------------------
# Architect Executor
# ---------------------------------------------------------------------------

class ArchitectExecutor(PipelineExecutor):
    def __init__(self):
        super().__init__(id="architect_executor", step_name="architect")
        self.agent = ArchitectAgent()

    @handler
    async def run_architect(
        self, msg: PipelineMessage, ctx: WorkflowContext[PipelineMessage, dict]
    ) -> None:
        state = msg.state
        ctx.set_state("pipeline", msg)

        # AC-1: Skip if already completed by the parallel BV+Architect path,
        # or if architect is not in the active agent set.
        if "architect" not in msg.active_agents or "architect" in state.completed_steps:
            if "architect" not in msg.active_agents:
                state.mark_step_skipped("architect")
            else:
                logger.info("Architect already completed (parallel path) — skipping standalone run")
            await ctx.send_message(msg)
            return

        state.mark_step_running("architect")

        await ctx.yield_output({
            "type": "agent_start", "step": "architect",
            "msg_id": str(uuid.uuid4()),
        })

        # Run agent (sync agent in thread pool)
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.agent.run, state),
                timeout=300,
            )
            state.mark_step_completed(self.step_name)

            summary = self.pm.approval_summary(self.step_name, state)
            output_text = self.pm.format_agent_output(self.step_name, state)

            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": output_text,
            })

            # Approval gate
            if _should_pause(msg.execution_mode, self.step_name):
                await ctx.request_info(
                    request_data=ApprovalRequest(
                        step=self.step_name, summary=summary,
                    ),
                    response_type=str,
                )
            else:
                await ctx.send_message(msg)

        except Exception as e:
            logger.exception("Architect agent failed")
            state.mark_step_failed(self.step_name)
            await ctx.yield_output({
                "type": "agent_error", "step": self.step_name,
                "error": str(e),
            })
            if self.step_name in REQUIRED_STEPS:
                await ctx.yield_output({"type": "pipeline_done", "content": f"Pipeline stopped: {self.step_name} is required but failed."})
                return
            await ctx.send_message(msg)

    @response_handler
    async def on_approval(
        self, request: ApprovalRequest, response: str, ctx: WorkflowContext
    ) -> None:
        msg: PipelineMessage = ctx.get_state("pipeline")
        resp_lower = response.strip().lower()

        if resp_lower in ("skip", "skip this", "next"):
            msg.state.mark_step_skipped(self.step_name)
        elif resp_lower in ("refine", "redo", "again", "retry"):
            msg.state.clarifications += f"\nFeedback on {self.step_name}: {response}"
            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": "Feedback noted. Use 'make it different' or 'iterate' after the pipeline completes to re-run this step with your feedback.",
            })
        # Default: proceed (covers "proceed", "yes", "ok", "continue", etc.)
        await ctx.send_message(msg)


# ---------------------------------------------------------------------------
# Cost Executor (two-phase: assumptions → calculation)
# ---------------------------------------------------------------------------

class CostExecutor(PipelineExecutor):
    def __init__(self):
        super().__init__(id="cost_executor", step_name="cost")
        self.agent = CostAgent()

    @handler
    async def run_cost(
        self, msg: PipelineMessage, ctx: WorkflowContext[PipelineMessage, dict]
    ) -> None:
        state = msg.state
        ctx.set_state("pipeline", msg)

        # Skip if not in active agents
        if "cost" not in msg.active_agents:
            state.mark_step_skipped("cost")
            await ctx.send_message(msg)
            return

        state.mark_step_running("cost")
        await ctx.yield_output({
            "type": "agent_start", "step": "cost",
            "msg_id": str(uuid.uuid4()),
        })

        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.agent.run, state),
                timeout=300,
            )

            # Check for two-phase input needed
            if state.costs.get("phase") == "needs_input":
                assumptions = state.costs.get("assumptions_needed", [])
                await ctx.yield_output({
                    "type": "assumptions_input", "step": "cost",
                    "assumptions": assumptions,
                })
                await ctx.request_info(
                    request_data=AssumptionsRequest(
                        step="cost", assumptions=assumptions,
                    ),
                    response_type=str,
                )
                return

            state.mark_step_completed(self.step_name)
            output_text = self.pm.format_agent_output(self.step_name, state)
            summary = self.pm.approval_summary(self.step_name, state)

            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": output_text,
            })

            if _should_pause(msg.execution_mode, self.step_name):
                await ctx.request_info(
                    request_data=ApprovalRequest(step=self.step_name, summary=summary),
                    response_type=str,
                )
            else:
                await ctx.send_message(msg)

        except Exception as e:
            logger.exception("Cost agent failed")
            state.mark_step_failed(self.step_name)
            await ctx.yield_output({
                "type": "agent_error", "step": self.step_name, "error": str(e),
            })
            if self.step_name in REQUIRED_STEPS:
                await ctx.yield_output({"type": "pipeline_done", "content": f"Pipeline stopped: {self.step_name} is required but failed."})
                return
            await ctx.send_message(msg)

    @response_handler
    async def on_assumptions_or_approval(
        self, request: AssumptionsRequest | ApprovalRequest, response: str,
        ctx: WorkflowContext,
    ) -> None:
        msg: PipelineMessage = ctx.get_state("pipeline")
        state = msg.state

        if isinstance(request, AssumptionsRequest):
            try:
                user_values = json.loads(response)
            except json.JSONDecodeError:
                # Use defaults with full schema (id, label, value, unit)
                user_values = [
                    {
                        "id": a["id"],
                        "label": a.get("label", a["id"]),
                        "value": a.get("default", 0),
                        "unit": a.get("unit", ""),
                    }
                    for a in request.assumptions
                ]
            state.costs["user_assumptions"] = user_values
            state.completed_steps = [
                s for s in state.completed_steps if s != "cost"
            ]

            loop = asyncio.get_running_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, self.agent.run, state),
                    timeout=300,
                )
                state.mark_step_completed(self.step_name)
            except Exception as e:
                logger.exception("Phase 2 re-run failed for %s", self.step_name)
                state.mark_step_failed(self.step_name)
                await ctx.yield_output({"type": "agent_error", "step": self.step_name, "error": str(e)})
                await ctx.send_message(msg)
                return

            output_text = self.pm.format_agent_output(self.step_name, state)
            summary = self.pm.approval_summary(self.step_name, state)
            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": output_text,
            })

            if _should_pause(msg.execution_mode, self.step_name):
                await ctx.request_info(
                    request_data=ApprovalRequest(step=self.step_name, summary=summary),
                    response_type=str,
                )
            else:
                await ctx.send_message(msg)
            return

        # ApprovalRequest path — check for skip or refine intent
        resp_lower = response.strip().lower()
        if resp_lower in ("skip", "skip this", "next"):
            state.mark_step_skipped("cost")
        elif resp_lower in ("refine", "redo", "again", "retry"):
            state.clarifications += f"\nFeedback on {self.step_name}: {response}"
            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": "Feedback noted. Use 'make it different' or 'iterate' after the pipeline completes to re-run this step with your feedback.",
            })
        await ctx.send_message(msg)


# ---------------------------------------------------------------------------
# Business Value Executor (two-phase: assumptions → drivers; AC-1 parallel)
# ---------------------------------------------------------------------------

class BusinessValueExecutor(PipelineExecutor):
    def __init__(self):
        super().__init__(id="bv_executor", step_name="business_value")
        self.agent = BusinessValueAgent()
        self._architect_agent = ArchitectAgent()

    @handler
    async def run_bv(
        self, msg: PipelineMessage, ctx: WorkflowContext[PipelineMessage, dict]
    ) -> None:
        state = msg.state
        ctx.set_state("pipeline", msg)

        if "business_value" not in msg.active_agents:
            state.mark_step_skipped("business_value")
            # AC-1: still run architect in parallel path even when BV skipped
            if "architect" in msg.active_agents:
                await self._run_architect_only(msg, ctx)
            else:
                await ctx.send_message(msg)
            return

        state.mark_step_running("business_value")
        await ctx.yield_output({
            "type": "agent_start", "step": "business_value",
            "msg_id": str(uuid.uuid4()),
        })

        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.agent.run, state),
                timeout=300,
            )

            if state.business_value.get("phase") == "needs_input":
                assumptions = state.business_value.get("assumptions_needed", [])
                await ctx.yield_output({
                    "type": "assumptions_input", "step": "business_value",
                    "assumptions": assumptions,
                })
                await ctx.request_info(
                    request_data=AssumptionsRequest(
                        step="business_value", assumptions=assumptions,
                    ),
                    response_type=str,
                )
                return

            state.mark_step_completed(self.step_name)
            output_text = self.pm.format_agent_output(self.step_name, state)
            summary = self.pm.approval_summary(self.step_name, state)

            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": output_text,
            })

            if _should_pause(msg.execution_mode, self.step_name):
                await ctx.request_info(
                    request_data=ApprovalRequest(
                        step=self.step_name, summary=summary,
                    ),
                    response_type=str,
                )
            else:
                await ctx.send_message(msg)

        except Exception as e:
            logger.exception("Business Value agent failed")
            state.mark_step_failed(self.step_name)
            await ctx.yield_output({
                "type": "agent_error", "step": self.step_name,
                "error": str(e),
            })
            if self.step_name in REQUIRED_STEPS:
                await ctx.yield_output({"type": "pipeline_done", "content": f"Pipeline stopped: {self.step_name} is required but failed."})
                return
            await ctx.send_message(msg)

    async def _run_architect_only(
        self, msg: PipelineMessage, ctx: WorkflowContext
    ) -> None:
        """Run architect standalone (when BV is skipped)."""
        state = msg.state
        state.mark_step_running("architect")
        await ctx.yield_output({"type": "agent_start", "step": "architect", "msg_id": str(uuid.uuid4())})
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(loop.run_in_executor(None, self._architect_agent.run, state), timeout=300)
            state.mark_step_completed("architect")
            output_text = self.pm.format_agent_output("architect", state)
            summary = self.pm.approval_summary("architect", state)
            await ctx.yield_output({"type": "agent_result", "step": "architect", "content": output_text})
            if _should_pause(msg.execution_mode, "architect"):
                await ctx.request_info(
                    request_data=ApprovalRequest(step="architect", summary=summary),
                    response_type=str,
                )
            else:
                await ctx.send_message(msg)
        except Exception as e:
            logger.exception("Architect agent failed (parallel path)")
            state.mark_step_failed("architect")
            await ctx.yield_output({"type": "agent_error", "step": "architect", "error": str(e)})
            if "architect" in REQUIRED_STEPS:
                await ctx.yield_output({"type": "pipeline_done", "content": "Pipeline stopped: architect failed."})
                return
            await ctx.send_message(msg)

    async def _run_bv_and_architect_parallel(
        self, msg: PipelineMessage, ctx: WorkflowContext, state
    ) -> None:
        """AC-1: Run BV Phase 2 and Architect in parallel, emit results."""
        loop = asyncio.get_running_loop()
        bv_error: Exception | None = None
        arch_error: Exception | None = None

        await ctx.yield_output({"type": "agent_start", "step": "business_value", "msg_id": str(uuid.uuid4())})
        await ctx.yield_output({"type": "agent_start", "step": "architect", "msg_id": str(uuid.uuid4())})

        async def _run_bv():
            nonlocal bv_error
            try:
                await asyncio.wait_for(loop.run_in_executor(None, self.agent.run, state), timeout=300)
            except Exception as e:
                bv_error = e

        async def _run_architect():
            nonlocal arch_error
            try:
                await asyncio.wait_for(loop.run_in_executor(None, self._architect_agent.run, state), timeout=300)
            except Exception as e:
                arch_error = e

        await asyncio.gather(_run_bv(), _run_architect())

        # Emit BV result
        if bv_error:
            logger.exception("BV parallel run failed: %s", bv_error)
            state.mark_step_failed("business_value")
            await ctx.yield_output({"type": "agent_error", "step": "business_value", "error": str(bv_error)})
        else:
            state.mark_step_completed("business_value")
            await ctx.yield_output({
                "type": "agent_result", "step": "business_value",
                "content": self.pm.format_agent_output("business_value", state),
            })

        # Emit architect result
        if arch_error:
            logger.exception("Architect parallel run failed: %s", arch_error)
            state.mark_step_failed("architect")
            await ctx.yield_output({"type": "agent_error", "step": "architect", "error": str(arch_error)})
            if "architect" in REQUIRED_STEPS:
                await ctx.yield_output({"type": "pipeline_done", "content": "Pipeline stopped: architect failed."})
                return
        else:
            state.mark_step_completed("architect")
            await ctx.yield_output({
                "type": "agent_result", "step": "architect",
                "content": self.pm.format_agent_output("architect", state),
            })

        # Approval gate for BV (architect approval is deferred — Cost runs after both)
        if not bv_error and state.business_value.get("phase") == "needs_input":
            assumptions = state.business_value.get("assumptions_needed", [])
            await ctx.yield_output({"type": "assumptions_input", "step": "business_value", "assumptions": assumptions})
            await ctx.request_info(
                request_data=AssumptionsRequest(step="business_value", assumptions=assumptions),
                response_type=str,
            )
            return

        if _should_pause(msg.execution_mode, "business_value") and not bv_error:
            summary = self.pm.approval_summary("business_value", state)
            await ctx.request_info(
                request_data=ApprovalRequest(step="business_value", summary=summary),
                response_type=str,
            )
        else:
            await ctx.send_message(msg)

    @response_handler
    async def on_assumptions_or_approval(
        self, request: AssumptionsRequest | ApprovalRequest, response: str,
        ctx: WorkflowContext,
    ) -> None:
        msg: PipelineMessage = ctx.get_state("pipeline")
        state = msg.state

        if isinstance(request, AssumptionsRequest):
            try:
                user_values = json.loads(response)
            except json.JSONDecodeError:
                user_values = [
                    {
                        "id": a["id"],
                        "label": a.get("label", a["id"]),
                        "value": a.get("default", 0),
                        "unit": a.get("unit", ""),
                    }
                    for a in request.assumptions
                ]
            state.business_value["user_assumptions"] = user_values
            state.completed_steps = [
                s for s in state.completed_steps if s != "business_value"
            ]

            # AC-1: If architect hasn't run yet, run both in parallel
            architect_done = "architect" in state.completed_steps
            if not architect_done and "architect" in msg.active_agents:
                await self._run_bv_and_architect_parallel(msg, ctx, state)
                return

            loop = asyncio.get_running_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, self.agent.run, state),
                    timeout=300,
                )
                state.mark_step_completed(self.step_name)
            except Exception as e:
                logger.exception("Phase 2 re-run failed for %s", self.step_name)
                state.mark_step_failed(self.step_name)
                await ctx.yield_output({"type": "agent_error", "step": self.step_name, "error": str(e)})
                await ctx.send_message(msg)
                return

            output_text = self.pm.format_agent_output(self.step_name, state)
            summary = self.pm.approval_summary(self.step_name, state)
            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": output_text,
            })

            if _should_pause(msg.execution_mode, self.step_name):
                await ctx.request_info(
                    request_data=ApprovalRequest(step=self.step_name, summary=summary),
                    response_type=str,
                )
            else:
                await ctx.send_message(msg)
            return

        # ApprovalRequest path — check for skip or refine intent
        resp_lower = response.strip().lower()
        if resp_lower in ("skip", "skip this", "next"):
            state.mark_step_skipped("business_value")
        elif resp_lower in ("refine", "redo", "again", "retry"):
            state.clarifications += f"\nFeedback on {self.step_name}: {response}"
            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": "Feedback noted. Use 'make it different' or 'iterate' after the pipeline completes to re-run this step with your feedback.",
            })
        await ctx.send_message(msg)


# ---------------------------------------------------------------------------
# ROI Executor (pure math, no LLM)
# ---------------------------------------------------------------------------

class ROIExecutor(PipelineExecutor):
    def __init__(self):
        super().__init__(id="roi_executor", step_name="roi")
        self.agent = ROIAgent()

    @handler
    async def run_roi(
        self, msg: PipelineMessage, ctx: WorkflowContext[PipelineMessage, dict]
    ) -> None:
        state = msg.state
        ctx.set_state("pipeline", msg)

        if "roi" not in msg.active_agents:
            state.mark_step_skipped("roi")
            await ctx.send_message(msg)
            return

        state.mark_step_running("roi")
        await ctx.yield_output({
            "type": "agent_start", "step": "roi",
            "msg_id": str(uuid.uuid4()),
        })

        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.agent.run, state),
                timeout=300,
            )
            state.mark_step_completed(self.step_name)

            output_text = self.pm.format_agent_output(self.step_name, state)
            summary = self.pm.approval_summary(self.step_name, state)
            dashboard = state.roi.get("dashboard")

            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": output_text,
                "dashboard": dashboard,
            })

            if _should_pause(msg.execution_mode, self.step_name):
                await ctx.request_info(
                    request_data=ApprovalRequest(step=self.step_name, summary=summary),
                    response_type=str,
                )
            else:
                await ctx.send_message(msg)

        except Exception as e:
            logger.exception("ROI agent failed")
            state.mark_step_failed(self.step_name)
            await ctx.yield_output({
                "type": "agent_error", "step": self.step_name, "error": str(e),
            })
            if self.step_name in REQUIRED_STEPS:
                await ctx.yield_output({"type": "pipeline_done", "content": f"Pipeline stopped: {self.step_name} is required but failed."})
                return
            await ctx.send_message(msg)

    @response_handler
    async def on_approval(
        self, request: ApprovalRequest, response: str, ctx: WorkflowContext
    ) -> None:
        msg: PipelineMessage = ctx.get_state("pipeline")
        resp_lower = response.strip().lower()

        if resp_lower in ("skip", "skip this", "next"):
            msg.state.mark_step_skipped(self.step_name)
        elif resp_lower in ("refine", "redo", "again", "retry"):
            msg.state.clarifications += f"\nFeedback on {self.step_name}: {response}"
            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": "Feedback noted. Use 'make it different' or 'iterate' after the pipeline completes to re-run this step with your feedback.",
            })
        # Default: proceed (covers "proceed", "yes", "ok", "continue", etc.)
        await ctx.send_message(msg)


# ---------------------------------------------------------------------------
# Presentation Executor (terminal step)
# ---------------------------------------------------------------------------

class PresentationExecutor(PipelineExecutor):
    def __init__(self):
        super().__init__(id="presentation_executor", step_name="presentation")
        self.agent = PresentationAgent()

    @handler
    async def run_presentation(
        self, msg: PipelineMessage, ctx: WorkflowContext[PipelineMessage, dict]
    ) -> None:
        state = msg.state
        ctx.set_state("pipeline", msg)

        if "presentation" not in msg.active_agents:
            state.mark_step_skipped("presentation")
            await ctx.yield_output({
                "type": "pipeline_done",
                "content": "Pipeline complete (presentation skipped).",
            })
            return

        state.mark_step_running("presentation")
        await ctx.yield_output({
            "type": "agent_start", "step": "presentation",
            "msg_id": str(uuid.uuid4()),
        })

        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.agent.run, state),
                timeout=300,
            )
            state.mark_step_completed(self.step_name)

            output_text = self.pm.format_agent_output(self.step_name, state)

            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": output_text,
            })

            if _should_pause(msg.execution_mode, self.step_name):
                await ctx.request_info(
                    request_data=ApprovalRequest(
                        step=self.step_name,
                        summary=self.pm.approval_summary(self.step_name, state),
                    ),
                    response_type=str,
                )
            else:
                await ctx.yield_output({
                    "type": "pipeline_done",
                    "content": "Pipeline complete.",
                })

        except Exception as e:
            logger.exception("Presentation agent failed")
            state.mark_step_failed(self.step_name)
            await ctx.yield_output({
                "type": "agent_error", "step": self.step_name,
                "error": str(e),
            })
            await ctx.yield_output({
                "type": "pipeline_done",
                "content": "Pipeline complete (presentation failed).",
            })

    @response_handler
    async def on_approval(
        self, request: ApprovalRequest, response: str,
        ctx: WorkflowContext,
    ) -> None:
        msg: PipelineMessage = ctx.get_state("pipeline")
        resp_lower = response.strip().lower()
        if resp_lower in ("skip", "skip this", "next"):
            msg.state.mark_step_skipped("presentation")
        elif resp_lower in ("refine", "redo", "again", "retry"):
            msg.state.clarifications += f"\nFeedback on {self.step_name}: {response}"
            await ctx.yield_output({
                "type": "agent_result", "step": self.step_name,
                "content": "Feedback noted. Use 'make it different' or 'iterate' after the pipeline completes to re-run this step with your feedback.",
            })
        await ctx.send_message(msg)
        await ctx.yield_output({
            "type": "pipeline_done",
            "content": "Pipeline complete.",
        })


# ---------------------------------------------------------------------------
# Workflow factory
# ---------------------------------------------------------------------------

def create_pipeline_workflow() -> Workflow:
    """Build the agent pipeline workflow.

    Graph: BV → architect → cost → ROI → presentation
    Each step has HITL approval gates and optional two-phase assumption input.
    """
    bv = BusinessValueExecutor()
    architect = ArchitectExecutor()
    cost = CostExecutor()
    roi = ROIExecutor()
    presentation = PresentationExecutor()

    workflow = (
        WorkflowBuilder(
            name="onestop_pipeline",
            description="OneStopAgent pipeline: BV → architect → cost → ROI → presentation",
            start_executor=bv,
        )
        .add_chain([bv, architect, cost, roi, presentation])
        .build()
    )
    return workflow
