"""Orchestration engine — phase-based state machine with approval gates.

Phases
------
  new         → first message, start brainstorming
  plan_shown  → execution plan displayed, waiting for user confirmation
  executing   → agents running in sequence
  approval    → waiting for user to proceed / refine / skip
  done        → all steps completed

FRD-01 §2 (modes), §3 (PM class), §4 (execution plan), §6 (iteration), §8 (errors).
"""
import asyncio
import json
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

# ── Agent registry (keyed by plan-step ID) ──────────────────────────────
AGENTS: dict[str, object] = {
    "architect": ArchitectAgent(),
    "cost": CostAgent(),
    "business_value": BusinessValueAgent(),
    "roi": ROIAgent(),
    "presentation": PresentationAgent(),
}

pm = ProjectManager()


# ── Output formatting now lives in ProjectManager ───────────────────────
# The orchestrator delegates to pm.format_agent_output(step, state).


def completion_summary(project_id: str, state: AgentState) -> ChatMessage:
    """Build a summary ChatMessage when all plan steps are finished."""
    parts = ["## ✅ Solution Complete\n"]
    if state.architecture:
        parts.append(
            f"- 🏗️ Architecture: "
            f"{len(state.architecture.get('components', []))} components"
        )
    if state.services:
        parts.append(
            f"- ☁️ Services: "
            f"{len(state.services.get('selections', []))} mapped"
        )
    if state.costs:
        est = state.costs.get("estimate", {})
        parts.append(f"- 💰 Cost: ${est.get('totalMonthly', 0):,.2f}/month")
    if state.roi and state.roi.get("roi_percent") is not None:
        parts.append(f"- 📈 ROI: {state.roi['roi_percent']:.0f}%")
    if state.presentation_path:
        parts.append("- 📑 Presentation: ready for download")
    parts.append(
        "\nYou can ask me to adjust anything, or say **different approach** to start over."
    )
    return ChatMessage(
        project_id=project_id,
        role="agent",
        agent_id="pm",
        content="\n".join(parts),
        metadata={"type": "pm_response"},
    )


# ── Orchestrator ────────────────────────────────────────────────────────


class Orchestrator:
    """Phase-based state machine orchestrator with approval gates.

    Phases
    ------
    new         – first message, start brainstorming
    plan_shown  – execution plan displayed, waiting for confirmation
    executing   – agents running in sequence
    approval    – waiting for proceed / refine / skip after a step
    done        – all steps completed
    """

    # In fast-run mode, only pause at these major gates (FRD-01 §2.3)
    # In fast-run mode, pause at these major gates:
    # 1. After brainstorm (Mode A → Mode B transition)
    # 2. After business_value (review value case before architecture)
    # 3. After architect (review design before committing to services + cost)
    # 4. Before presentation (final review)
    FAST_RUN_GATES = {"business_value", "architect", "presentation"}

    def __init__(self):
        self.states: dict[str, AgentState] = {}
        self.phases: dict[str, str] = {}

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

            # Brainstorm + classify Azure fit in one call
            result = await asyncio.get_event_loop().run_in_executor(
                None, pm.brainstorm_greeting, message,
            )

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
                yield self._msg(
                    project_id,
                    f"{greeting}\n\n"
                    f"> ⚠️ **Azure fit: {state.azure_fit}** — "
                    f"{state.azure_fit_explanation}\n\n"
                    "Could you provide more details so I can better assess "
                    "the Azure opportunity? Or say **proceed** to continue anyway.",
                    {"type": "pm_response"},
                )
            else:
                plan = pm.build_plan(active_agents)
                state.plan_steps = plan
                plan_text = pm.format_plan(state)

                self.phases[project_id] = "plan_shown"
                yield self._msg(
                    project_id,
                    f"{greeting}\n\n{plan_text}",
                    {"type": "pm_response"},
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
                # Treat as additional clarification
                if state.clarifications:
                    state.clarifications += f"\n{message}"
                else:
                    state.clarifications = message
                yield self._msg(
                    project_id,
                    "Got it. Anything else, or say **proceed** to start?",
                    {"type": "pm_response"},
                )

        # ── Phase: approval ─────────────────────────────────────────
        elif phase == "approval":
            current = state.current_step

            if intent == Intent.PROCEED:
                state.awaiting_approval = False
                self.phases[project_id] = "executing"
                async for msg in self.continue_execution(project_id, state):
                    yield msg

            elif intent == Intent.SKIP:
                state.mark_step_skipped(current)
                state.awaiting_approval = False
                self.phases[project_id] = "executing"
                async for msg in self.continue_execution(project_id, state):
                    yield msg

            elif intent == Intent.QUESTION:
                # Answer the question about current step output — stay in approval
                step_name = current or (
                    state.completed_steps[-1] if state.completed_steps else ""
                )
                agent_output = pm.format_agent_output(step_name, state) if step_name else ""
                answer = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: llm.invoke([
                        {
                            "role": "system",
                            "content": (
                                f"You are the Project Manager. The user is asking about "
                                f"the {step_name} step output. Answer based on the data "
                                f"below. Be concise."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Output:\n{agent_output[:2000]}\n\n"
                                f"User asks: {message}"
                            ),
                        },
                    ]).content,
                )
                yield self._msg(
                    project_id,
                    f"{answer}\n\nSay **proceed** to continue, "
                    "**refine** to adjust, or **skip** to move on.",
                    {"type": "pm_response"},
                )

            elif intent == Intent.INPUT:
                # User is providing additional context (e.g. answering an
                # ROI question) — re-run the current agent with the new info
                state.clarifications += f"\nAdditional input: {message}"
                last_step = current or (
                    state.completed_steps[-1] if state.completed_steps else ""
                )
                if last_step:
                    state.completed_steps = [
                        s for s in state.completed_steps if s != last_step
                    ]
                    info = AGENT_INFO.get(
                        last_step, {"name": last_step, "emoji": "🔧"}
                    )
                    yield self._msg(
                        project_id,
                        f"Got it — re-running **{info['name']}** with your input...",
                        {"type": "pm_response"},
                    )
                    state.awaiting_approval = False
                    self.phases[project_id] = "executing"
                    async for msg in self.run_single_step(
                        project_id, state, last_step
                    ):
                        yield msg
                else:
                    yield self._msg(
                        project_id,
                        "Thanks for the input. Say **proceed** to continue.",
                        {"type": "pm_response"},
                    )

            elif intent == Intent.REFINE:
                # Explicit refine → re-run step with feedback
                state.clarifications += f"\nFeedback: {message}"
                state.completed_steps = [
                    s for s in state.completed_steps if s != current
                ]
                state.awaiting_approval = False
                self.phases[project_id] = "executing"
                async for msg in self.run_single_step(
                    project_id, state, current
                ):
                    yield msg

            elif intent == Intent.FAST_RUN:
                # Switch to fast-run and continue from here
                state.execution_mode = "fast-run"
                state.awaiting_approval = False
                yield self._msg(
                    project_id,
                    "Switching to fast mode — running remaining agents without pauses.",
                    {"type": "pm_response"},
                )
                self.phases[project_id] = "executing"
                async for msg in self.continue_execution(project_id, state):
                    yield msg

            else:
                # Default: treat as additional context, stay in approval
                state.clarifications += f"\n{message}"
                yield self._msg(
                    project_id,
                    "Got it. Say **proceed** to continue, **refine** to adjust, or just keep chatting.",
                    {"type": "pm_response"},
                )

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

    # ── Execution engine ────────────────────────────────────────────

    async def execute_plan(
        self, project_id: str, state: AgentState,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Execute the full plan from the beginning."""
        yield self._msg(
            project_id,
            f"Starting execution with {len(state.plan_steps)} agents...",
            {"type": "pm_response"},
        )
        async for msg in self.continue_execution(project_id, state):
            yield msg

    async def continue_execution(
        self, project_id: str, state: AgentState,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Continue execution from the next pending step."""
        next_step = state.next_pending_step()
        if not next_step:
            self.phases[project_id] = "done"
            yield completion_summary(project_id, state)
            return

        async for msg in self.run_single_step(project_id, state, next_step):
            yield msg

    async def run_single_step(
        self, project_id: str, state: AgentState, step: str,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Run one agent step, then gate for approval."""
        info = AGENT_INFO.get(step, {"name": step, "emoji": "🔧"})
        agent = AGENTS.get(step)

        # Skip unavailable agents gracefully (FRD-01 §8)
        if not agent:
            state.mark_step_skipped(step)
            yield self._msg(
                project_id,
                f"⏭️ {info['name']} skipped (not available)",
                {"type": "plan_update", "step": step, "status": "skipped"},
            )
            async for msg in self.continue_execution(project_id, state):
                yield msg
            return

        # Emit plan_update: running
        yield ChatMessage(
            project_id=project_id,
            role="agent",
            agent_id="pm",
            content="",
            metadata={"type": "plan_update", "step": step, "status": "running"},
        )

        state.mark_step_running(step)
        yield self._msg(
            project_id,
            f"{info['emoji']} **{info['name']}** is working...",
            {"type": "agent_start", "agent": step},
        )

        # Run agent in thread pool with progress heartbeat
        loop = asyncio.get_event_loop()
        done_event = asyncio.Event()
        result_holder = [None]
        error_holder = [None]

        def _run():
            try:
                result_holder[0] = agent.run(state)
            except Exception as e:
                error_holder[0] = e
            loop.call_soon_threadsafe(done_event.set)

        loop.run_in_executor(None, _run)

        # Heartbeat: emit progress every 5s while agent runs
        _PROGRESS = [
            "⏳ Analyzing requirements...",
            "⏳ Generating insights...",
            "⏳ Synthesizing output...",
        ]
        elapsed = 0
        while not done_event.is_set():
            try:
                await asyncio.wait_for(done_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                elapsed += 5
                idx = min(elapsed // 5 - 1, len(_PROGRESS) - 1)
                yield self._msg(
                    project_id,
                    f"{_PROGRESS[idx]} ({elapsed}s)",
                    {"type": "progress", "agent": step},
                )

        try:
            if error_holder[0]:
                raise error_holder[0]
            state = result_holder[0]
            self.states[project_id] = state  # update reference
            state.mark_step_completed(step)

            # Emit plan_update: completed
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id="pm",
                content="",
                metadata={
                    "type": "plan_update",
                    "step": step,
                    "status": "completed",
                },
            )

            # Emit formatted agent result
            formatted = pm.format_agent_output(step, state)
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id=step,
                content=formatted,
                metadata={"type": "agent_result", "agent": step},
            )

            # Approval gate check (FRD-01 §2.3)
            if self.should_pause(state, step):
                summary = pm.approval_summary(step, state)
                state.awaiting_approval = True
                state.current_step = step  # remember for refine
                self.phases[project_id] = "approval"
                yield self._msg(
                    project_id,
                    summary,
                    {"type": "approval", "step": step},
                )
            else:
                # Fast-run or non-gate step — continue automatically
                async for msg in self.continue_execution(
                    project_id, state
                ):
                    yield msg

        except Exception as e:
            # Graceful degradation (FRD-01 §8)
            state.mark_step_failed(step)
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id="pm",
                content="",
                metadata={
                    "type": "plan_update",
                    "step": step,
                    "status": "failed",
                },
            )
            yield self._msg(
                project_id,
                f"⚠️ {info['name']} failed: {str(e)}",
                {"type": "agent_error", "agent": step},
            )
            # Continue to next step — pipeline never stops (FRD-01 §8)
            async for msg in self.continue_execution(project_id, state):
                yield msg

    # ── Approval gate ───────────────────────────────────────────────

    def should_pause(self, state: AgentState, step: str) -> bool:
        """Determine if we should pause for approval after this step."""
        if state.execution_mode == "fast-run":
            # Fast-run: only 3 major gates (FRD-01 §2.3)
            return step in self.FAST_RUN_GATES
        # Guided mode: pause after every step
        return True

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
