"""MAF-backed orchestrator — replaces the legacy orchestrator.py.

Keeps the PM brainstorming / plan_shown phases as conversational logic,
but delegates the agent execution pipeline to the MAF Workflow in workflow.py.
Converts MAF WorkflowEvents → ChatMessage SSE format so the React frontend
needs zero changes.
"""

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from agents.state import AgentState
from agents.pm_agent import ProjectManager, AGENT_INFO, Intent
from agents.llm import llm
from models.schemas import ChatMessage
from workflow import create_pipeline_workflow, PipelineMessage, ApprovalRequest, AssumptionsRequest

logger = logging.getLogger(__name__)
pm = ProjectManager()


class MAFOrchestrator:
    """Phase-based orchestrator backed by Microsoft Agent Framework Workflow.

    Phases
    ------
    new         – first message, PM brainstorming
    plan_shown  – execution plan displayed, waiting for confirmation
    executing   – MAF workflow running (replaces legacy execution.py + approval.py)
    done        – all steps completed
    """

    FAST_RUN_GATES = {"business_value", "architect", "presentation"}

    def __init__(self):
        self.states: dict[str, AgentState] = {}
        self.phases: dict[str, str] = {}
        self.workflows: dict[str, object] = {}  # MAF Workflow per project
        self.pending_requests: dict[str, dict] = {}  # project_id → {request_id: ...}

    def get_state(self, project_id: str) -> AgentState:
        if project_id not in self.states:
            self.states[project_id] = AgentState()
        return self.states[project_id]

    def _msg(self, project_id: str, content: str, metadata: dict | None = None,
             agent_id: str = "pm") -> ChatMessage:
        return ChatMessage(
            project_id=project_id, role="agent", agent_id=agent_id,
            content=content, metadata=metadata or {"type": "pm_response"},
        )

    async def handle_message(
        self, project_id: str, message: str,
        active_agents: list[str], description: str,
    ) -> AsyncGenerator[ChatMessage, None]:
        state = self.get_state(project_id)
        phase = self.phases.get(project_id, "new")

        intent, meta = await pm.intent_interpreter.aclassify(message)

        # ── Phase: new ──────────────────────────────────────────────
        if phase == "new":
            state.user_input = message
            state.mode = "brainstorm"

            msg_id = str(uuid.uuid4())
            token_queue: asyncio.Queue = asyncio.Queue()
            result_holder: list = [None]

            async def _run_brainstorm():
                def on_token(token: str):
                    token_queue.put_nowait(token)
                result_holder[0] = await pm.brainstorm_greeting_streaming(message, on_token)
                token_queue.put_nowait(None)

            task = asyncio.create_task(_run_brainstorm())
            while True:
                token = await token_queue.get()
                if token is None:
                    break
                yield ChatMessage(
                    project_id=project_id, role="agent", agent_id="pm",
                    content=token,
                    metadata={"type": "agent_token", "agent": "pm", "msg_id": msg_id, "token": token},
                )

            await task
            result = result_holder[0]

            state.brainstorming = {"scenarios": result["scenarios"], "industry": result["industry"]}
            state.azure_fit = result["azure_fit"]
            state.azure_fit_explanation = result["azure_fit_explanation"]
            greeting = result["response"]

            if isinstance(greeting, str) and greeting.strip().startswith("{"):
                try:
                    inner = json.loads(greeting)
                    if isinstance(inner, dict) and "response" in inner:
                        greeting = inner["response"]
                except json.JSONDecodeError:
                    pass

            plan = pm.build_plan(active_agents)
            state.plan_steps = plan

            if state.azure_fit and state.azure_fit != "strong":
                self.phases[project_id] = "plan_shown"
                yield ChatMessage(
                    id=msg_id, project_id=project_id, role="agent", agent_id="pm",
                    content=(
                        f"{greeting}\n\n"
                        f"> ⚠️ **Azure fit: {state.azure_fit}** — {state.azure_fit_explanation}\n\n"
                        "Could you provide more details? Or say **proceed** to continue anyway."
                    ),
                    metadata={"type": "pm_response"},
                )
            else:
                plan_text = pm.format_plan(state)
                self.phases[project_id] = "plan_shown"
                yield ChatMessage(
                    id=msg_id, project_id=project_id, role="agent", agent_id="pm",
                    content=f"{greeting}\n\n{plan_text}",
                    metadata={"type": "pm_response"},
                )

        # ── Phase: plan_shown ───────────────────────────────────────
        elif phase == "plan_shown":
            if intent in (Intent.PROCEED, Intent.FAST_RUN):
                state.clarifications = message if intent == Intent.PROCEED else ""
                state.mode = "solution"
                execution_mode = "fast-run" if intent == Intent.FAST_RUN else "guided"
                state.execution_mode = execution_mode

                if intent == Intent.FAST_RUN:
                    yield self._msg(project_id, "Running in fast mode — I'll pause at architecture and before the final deck.", {"type": "pm_response"})

                self.phases[project_id] = "executing"
                async for msg in self._run_workflow(project_id, state, active_agents):
                    yield msg

            elif intent == Intent.SKIP:
                yield self._msg(project_id, "Got it. What else would you like to adjust, or say **proceed** to start?")

            else:
                if state.clarifications:
                    state.clarifications += f"\n{message}"
                else:
                    state.clarifications = message
                try:
                    ack = await llm.ainvoke([
                        {"role": "system", "content": (
                            "You are a project manager. The user just answered your questions about their Azure project. "
                            "Briefly acknowledge their input in 1-2 sentences. Then ask if there's anything else or if they want to proceed. "
                            "Be concise. Use **proceed** in bold."
                        )},
                        {"role": "user", "content": f"User's original request: {state.user_input}\n\nUser's additional input: {message}"},
                    ])
                    ack_text = ack.content.strip()
                except Exception:
                    ack_text = "Got it. Anything else, or say **proceed** to start?"
                yield self._msg(project_id, ack_text)

        # ── Phase: executing (workflow paused for HITL) ─────────────
        elif phase == "executing":
            pending = self.pending_requests.get(project_id, {})
            if pending:
                # Feed user response to the paused workflow
                async for msg in self._resume_workflow(project_id, state, message, pending):
                    yield msg
            else:
                yield self._msg(project_id, "I'll address that after the current step completes.")

        # ── Phase: done ─────────────────────────────────────────────
        elif phase == "done":
            if intent == Intent.ITERATION:
                agents_to_rerun = meta.get("agents_to_rerun") or pm.get_agents_to_rerun(message)
                state.clarifications += f"\nIteration: {message}"

                rerun_set = set(agents_to_rerun)
                state.completed_steps = [s for s in state.completed_steps if s not in rerun_set]
                state.failed_steps = [s for s in state.failed_steps if s not in rerun_set]
                state.skipped_steps = [s for s in state.skipped_steps if s not in rerun_set]

                names = [AGENT_INFO.get(a, {"name": a})["name"] for a in agents_to_rerun]
                yield self._msg(project_id, f"Re-running {len(agents_to_rerun)} agents ({', '.join(names)}) with your feedback...")

                self.phases[project_id] = "executing"
                async for msg in self._run_workflow(project_id, state, list(rerun_set)):
                    yield msg

            elif intent == Intent.BRAINSTORM:
                self.phases[project_id] = "new"
                state.mode = "brainstorm"
                state.completed_steps.clear()
                state.skipped_steps.clear()
                state.failed_steps.clear()
                yield self._msg(project_id, "Starting fresh! Tell me about your project.")

            else:
                follow_up = await llm.ainvoke([
                    {"role": "system", "content": "You are an Azure solution project manager. The solution has been designed. Help the user with follow-up questions or modifications. Be brief."},
                    {"role": "user", "content": f"Context: {state.to_context_string()}\n\nUser says: {message}"},
                ])
                yield self._msg(project_id, follow_up.content)

    # ── MAF Workflow execution ──────────────────────────────────────

    async def _run_workflow(
        self, project_id: str, state: AgentState, active_agents: list[str],
    ) -> AsyncGenerator[ChatMessage, None]:
        """Start a new MAF workflow and stream events as ChatMessages."""
        wf = create_pipeline_workflow()
        self.workflows[project_id] = wf

        pipeline_msg = PipelineMessage(
            state=state,
            project_id=project_id,
            execution_mode=state.execution_mode,
            active_agents=active_agents,
        )

        yield self._msg(
            project_id,
            f"Starting execution with {len(state.plan_steps)} agents...",
            {"type": "pm_response"},
        )

        stream = wf.run(pipeline_msg, stream=True)
        async for chat_msg in self._process_workflow_events(project_id, stream):
            yield chat_msg

    async def _resume_workflow(
        self, project_id: str, state: AgentState, message: str,
        pending: dict,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Resume a paused MAF workflow with user response."""
        wf = self.workflows.get(project_id)
        if not wf:
            yield self._msg(project_id, "No active workflow to resume.")
            return

        # Map all pending requests to user's response
        responses = {req_id: message for req_id in pending}
        self.pending_requests[project_id] = {}

        stream = wf.run(stream=True, responses=responses)
        async for chat_msg in self._process_workflow_events(project_id, stream):
            yield chat_msg

    async def _process_workflow_events(
        self, project_id: str, stream,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Convert MAF WorkflowEvents → ChatMessage SSE format."""
        async for event in stream:
            logger.info("WF event: type=%s executor=%s data_type=%s",
                        event.type, getattr(event, 'executor_id', '?'),
                        type(event.data).__name__)

            if event.type == "output" and isinstance(event.data, dict):
                data = event.data
                etype = data.get("type", "")
                step = data.get("step", "")

                if etype == "agent_start":
                    msg_id = data.get("msg_id", str(uuid.uuid4()))
                    plan_text = pm.format_plan(self.get_state(project_id))
                    yield ChatMessage(
                        project_id=project_id, role="agent", agent_id="pm",
                        content=plan_text,
                        metadata={"type": "plan_update", "step": step, "status": "running"},
                    )

                elif etype == "agent_result":
                    content = data.get("content", "")
                    metadata: dict = {"type": "agent_result", "step": step}
                    if "dashboard" in data and data["dashboard"]:
                        metadata["type"] = "roi_dashboard"
                        metadata["dashboard"] = data["dashboard"]
                    yield ChatMessage(
                        project_id=project_id, role="agent",
                        agent_id=step, content=content, metadata=metadata,
                    )

                elif etype == "agent_error":
                    yield ChatMessage(
                        project_id=project_id, role="agent", agent_id=step,
                        content=f"⚠️ {step} failed: {data.get('error', 'unknown')}",
                        metadata={"type": "agent_error", "step": step},
                    )

                elif etype == "assumptions_input":
                    assumptions = data.get("assumptions", [])
                    yield ChatMessage(
                        project_id=project_id, role="agent", agent_id=step,
                        content=f"Please provide your assumptions for {step}:",
                        metadata={
                            "type": "assumptions_input",
                            "step": step,
                            "assumptions": assumptions,
                        },
                    )

                elif etype == "pipeline_done":
                    self.phases[project_id] = "done"
                    yield self._msg(
                        project_id,
                        "All steps complete! You can download the deck, ask follow-up questions, or request changes.",
                        {"type": "pm_response"},
                    )

            elif event.type == "request_info":
                # HITL pause — store pending request and emit approval prompt
                if project_id not in self.pending_requests:
                    self.pending_requests[project_id] = {}
                self.pending_requests[project_id][event.request_id] = event.data

                if isinstance(event.data, ApprovalRequest):
                    summary = event.data.summary
                    yield ChatMessage(
                        project_id=project_id, role="agent", agent_id="pm",
                        content=f"{summary}\n\nSay **proceed** to continue, **skip** to skip, or provide feedback to refine.",
                        metadata={"type": "approval", "step": event.data.step},
                    )
                elif isinstance(event.data, AssumptionsRequest):
                    # Already emitted via assumptions_input above
                    pass
