"""Orchestration engine — phase-based state machine with approval gates.

Phases
------
  new         → first message, start brainstorming
  plan_shown  → execution plan displayed, waiting for user confirmation
  executing   → agents running in sequence
  approval    → waiting for user to proceed / refine / skip
  done        → all steps completed

FRD-01 §2 (modes), §3 (PM class), §4 (execution plan), §6 (iteration), §8 (errors).

Implementation is split across four modules for maintainability:
  orchestrator.py  — phase state machine + message routing (this file)
  execution.py     — run_single_step, streaming/non-streaming paths, heartbeat
  approval.py      — approval gate logic, proceed/skip/refine routing
  input_handler.py — two-phase assumption helpers (JSON parsing, defaults)
"""
import asyncio
import json
import uuid
from typing import AsyncGenerator

from agents.state import AgentState
from agents.pm_agent import ProjectManager, AGENT_INFO, Intent
from agents.architect_agent import ArchitectAgent
from agents.cost_agent import CostAgent
from agents.business_value_agent import BusinessValueAgent
from agents.presentation_agent import PresentationAgent
from agents.roi_agent import ROIAgent
from agents.llm import llm
from models.schemas import ChatMessage

from execution import ExecutionMixin
from approval import ApprovalMixin

# ── Agent registry (keyed by plan-step ID) ──────────────────────────────
AGENTS: dict[str, object] = {
    "architect": ArchitectAgent(),
    "cost": CostAgent(),
    "business_value": BusinessValueAgent(),
    "roi": ROIAgent(),
    "presentation": PresentationAgent(),
}

pm = ProjectManager()


# ── Orchestrator ────────────────────────────────────────────────────────


class Orchestrator(ExecutionMixin, ApprovalMixin):
    """Phase-based state machine orchestrator with approval gates.

    Phases
    ------
    new         – first message, start brainstorming
    plan_shown  – execution plan displayed, waiting for confirmation
    executing   – agents running in sequence
    approval    – waiting for proceed / refine / skip after a step
    done        – all steps completed

    Execution and approval logic are provided by :class:`execution.ExecutionMixin`
    and :class:`approval.ApprovalMixin` respectively.  Two-phase assumption
    helpers live in :mod:`input_handler`.  This class is the slim coordinator
    that wires the phase state machine together and owns ``phases`` / ``states``.
    """

    # In fast-run mode, only pause at these major gates (FRD-01 §2.3)
    # 1. After brainstorm (Mode A → Mode B transition)
    # 2. After business_value (review value case before architecture)
    # 3. After architect (review design before committing to services + cost)
    # 4. Before presentation (final review)
    FAST_RUN_GATES = {"business_value", "architect", "presentation"}

    def __init__(self):
        self.states: dict[str, AgentState] = {}
        self.phases: dict[str, str] = {}
        # Injected into ExecutionMixin methods via self
        self.agents = AGENTS
        self.pm = pm

    # ── Helpers ─────────────────────────────────────────────────────

    def get_state(self, project_id: str) -> AgentState:
        if project_id not in self.states:
            self.states[project_id] = AgentState()
        return self.states[project_id]

    def _msg(
        self,
        project_id: str,
        content: str,
        metadata: dict | None = None,
        agent_id: str = "pm",
    ) -> ChatMessage:
        """Convenience builder for a ChatMessage."""
        return ChatMessage(
            project_id=project_id,
            role="agent",
            agent_id=agent_id,
            content=content,
            metadata=metadata or {"type": "pm_response"},
        )

    # ── Main entry point ────────────────────────────────────────────

    async def handle_message(
        self,
        project_id: str,
        message: str,
        active_agents: list[str],
        description: str,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Handle a user message and yield response ChatMessages."""
        state = self.get_state(project_id)
        phase = self.phases.get(project_id, "new")

        # Classify intent (keyword match → LLM fallback)
        intent, meta = pm.intent_interpreter.classify(message)

        # ── Phase: new ──────────────────────────────────────────────
        if phase == "new":
            state.user_input = message
            state.mode = "brainstorm"

            # Stream PM brainstorm response token-by-token
            msg_id = str(uuid.uuid4())
            token_queue: asyncio.Queue = asyncio.Queue()
            result_holder: list = [None]

            async def _run_brainstorm():
                def on_token(token: str):
                    token_queue.put_nowait(token)
                result_holder[0] = await pm.brainstorm_greeting_streaming(
                    message, on_token
                )
                token_queue.put_nowait(None)  # sentinel

            task = asyncio.create_task(_run_brainstorm())

            while True:
                token = await token_queue.get()
                if token is None:
                    break
                yield ChatMessage(
                    project_id=project_id,
                    role="agent",
                    agent_id="pm",
                    content=token,
                    metadata={
                        "type": "agent_token",
                        "agent": "pm",
                        "msg_id": msg_id,
                        "token": token,
                    },
                )

            await task
            result = result_holder[0]

            # Populate state from structured response
            state.brainstorming = {
                "scenarios": result["scenarios"],
                "industry": result["industry"],
            }
            state.azure_fit = result["azure_fit"]
            state.azure_fit_explanation = result["azure_fit_explanation"]

            greeting = result["response"]

            # Safety: if the greeting itself is JSON (LLM failed to extract
            # the response field properly), parse it and extract the text
            if isinstance(greeting, str) and greeting.strip().startswith("{"):
                try:
                    inner = json.loads(greeting)
                    if isinstance(inner, dict) and "response" in inner:
                        greeting = inner["response"]
                except json.JSONDecodeError:
                    pass

            # Azure fit gate: weak/unclear → ask for more detail before showing plan
            if state.azure_fit and state.azure_fit != "strong":
                self.phases[project_id] = "plan_shown"  # stay conversational
                plan = pm.build_plan(active_agents)
                state.plan_steps = plan
                yield ChatMessage(
                    id=msg_id,
                    project_id=project_id,
                    role="agent",
                    agent_id="pm",
                    content=(
                        f"{greeting}\n\n"
                        f"> ⚠️ **Azure fit: {state.azure_fit}** — "
                        f"{state.azure_fit_explanation}\n\n"
                        "Could you provide more details so I can better assess "
                        "the Azure opportunity? Or say **proceed** to continue anyway."
                    ),
                    metadata={"type": "pm_response"},
                )
            else:
                plan = pm.build_plan(active_agents)
                state.plan_steps = plan
                plan_text = pm.format_plan(state)

                self.phases[project_id] = "plan_shown"
                yield ChatMessage(
                    id=msg_id,
                    project_id=project_id,
                    role="agent",
                    agent_id="pm",
                    content=f"{greeting}\n\n{plan_text}",
                    metadata={"type": "pm_response"},
                )

        # ── Phase: plan_shown ───────────────────────────────────────
        elif phase == "plan_shown":
            if intent in (Intent.PROCEED, Intent.FAST_RUN):
                # Store clarifications only for normal proceed
                state.clarifications = message if intent == Intent.PROCEED else ""
                state.mode = "solution"

                if intent == Intent.FAST_RUN:
                    state.execution_mode = "fast-run"
                    yield self._msg(
                        project_id,
                        "Running in fast mode — I'll pause at architecture "
                        "and before the final deck.",
                        {"type": "pm_response"},
                    )

                self.phases[project_id] = "executing"
                async for msg in self.execute_plan(project_id, state):
                    yield msg

            elif intent == Intent.SKIP:
                yield self._msg(
                    project_id,
                    "Got it. What else would you like to adjust, "
                    "or say **proceed** to start?",
                    {"type": "pm_response"},
                )

            else:
                # Treat as additional clarification — store and acknowledge
                if state.clarifications:
                    state.clarifications += f"\n{message}"
                else:
                    state.clarifications = message

                # Use LLM to briefly acknowledge the input
                try:
                    ack = llm.invoke([
                        {"role": "system", "content": (
                            "You are a project manager. The user just answered your questions about their Azure project. "
                            "Briefly acknowledge their input in 1-2 sentences — reference specifics they mentioned "
                            "(e.g. users, region, industry, scale). Then ask if there's anything else or if they want to proceed. "
                            "Be concise. Use **proceed** in bold."
                        )},
                        {"role": "user", "content": f"User's original request: {state.user_input}\n\nUser's additional input: {message}"},
                    ])
                    ack_text = ack.content.strip()
                except Exception:
                    ack_text = "Got it. Anything else, or say **proceed** to start?"

                yield self._msg(
                    project_id,
                    ack_text,
                    {"type": "pm_response"},
                )

        # ── Phase: approval ─────────────────────────────────────────
        elif phase == "approval":
            async for msg in self._route_approval_message(
                project_id, message, state, intent
            ):
                yield msg

        # ── Phase: executing ────────────────────────────────────────
        elif phase == "executing":
            # FRD-01 §3.2 intent #9 — message during execution
            yield self._msg(
                project_id,
                "I'll address that after the current step completes.",
                {"type": "pm_response"},
            )

        # ── Phase: done ─────────────────────────────────────────────
        elif phase == "done":
            if intent == Intent.ITERATION:
                agents_to_rerun = (
                    meta.get("agents_to_rerun")
                    or pm.get_agents_to_rerun(message)
                )
                state.clarifications += f"\nIteration: {message}"
                async for msg in self.iterate(
                    project_id, state, agents_to_rerun
                ):
                    yield msg

            elif intent == Intent.BRAINSTORM:
                # Reset to brainstorm mode
                self.phases[project_id] = "new"
                state.mode = "brainstorm"
                state.completed_steps.clear()
                state.skipped_steps.clear()
                state.failed_steps.clear()
                yield self._msg(
                    project_id,
                    "Starting fresh! Tell me about your project.",
                    {"type": "pm_response"},
                )

            else:
                # Conversational follow-up (question, input, etc.)
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: llm.invoke([
                        {
                            "role": "system",
                            "content": (
                                "You are an Azure solution project manager. "
                                "The solution has been designed. Help the user "
                                "with follow-up questions or modifications. "
                                "Be brief."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Context: {state.to_context_string()}\n\n"
                                f"User says: {message}"
                            ),
                        },
                    ]).content,
                )
                yield self._msg(
                    project_id, response, {"type": "pm_response"}
                )

    # ── Iteration (FRD-01 §6) ──────────────────────────────────────

    async def iterate(
        self,
        project_id: str,
        state: AgentState,
        agents_to_rerun: list[str],
    ) -> AsyncGenerator[ChatMessage, None]:
        """Re-run specific agents for iteration."""
        self.phases[project_id] = "executing"

        # Clear prior status for agents being re-run
        rerun_set = set(agents_to_rerun)
        state.completed_steps = [
            s for s in state.completed_steps if s not in rerun_set
        ]
        state.failed_steps = [
            s for s in state.failed_steps if s not in rerun_set
        ]
        state.skipped_steps = [
            s for s in state.skipped_steps if s not in rerun_set
        ]

        # Temporarily scope plan to just the re-run agents (preserve order)
        original_plan = list(state.plan_steps)
        state.plan_steps = [s for s in original_plan if s in rerun_set]

        names = [
            AGENT_INFO.get(a, {"name": a})["name"] for a in agents_to_rerun
        ]
        yield self._msg(
            project_id,
            f"Re-running {len(agents_to_rerun)} agents "
            f"({', '.join(names)}) with your feedback...",
            {"type": "pm_response"},
        )

        async for msg in self.execute_plan(project_id, state):
            yield msg

        # Restore full plan
        state.plan_steps = original_plan
