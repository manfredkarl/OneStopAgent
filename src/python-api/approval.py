"""Approval gate logic — should_pause determination and approval-phase routing.

Provides :class:`ApprovalMixin`, which is mixed into
:class:`orchestrator.Orchestrator` to handle the ``approval`` phase of the
conversation state machine.

FRD-01 §2.3 (approval gates), §6 (iteration).
"""

import asyncio
from typing import AsyncGenerator

from agents.pm_agent import AGENT_INFO, Intent
from agents.llm import llm
from agents.state import AgentState
from input_handler import parse_assumption_json, build_default_values
from models.schemas import ChatMessage


class ApprovalMixin:
    """Approval gate and approval-phase message routing.

    Expects to be mixed into a class that provides:
    - ``self.phases: dict[str, str]``
    - ``self.pm`` — ProjectManager instance
    - ``self._msg(project_id, content, metadata) -> ChatMessage``
    - ``self.run_single_step(project_id, state, step)`` async gen
    - ``self.continue_execution(project_id, state)`` async gen
    """

    # ── Approval gate ──────────────────────────────────────────────────────

    def should_pause(self, state: AgentState, step: str) -> bool:
        """Return True if execution should pause for approval after *step*."""
        if state.execution_mode == "fast-run":
            # Fast-run: only pause at major gates (FRD-01 §2.3)
            return step in self.FAST_RUN_GATES
        # Guided mode: pause after every step
        return True

    # ── Approval phase routing ─────────────────────────────────────────────

    async def _route_approval_message(
        self,
        project_id: str,
        message: str,
        state: AgentState,
        intent: Intent,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Handle a user message received while the pipeline is in *approval* phase.

        Yields zero or more :class:`ChatMessage` objects and (as a side-effect)
        transitions ``self.phases[project_id]`` to the appropriate next phase.
        """
        current = state.current_step

        # ── Two-phase: user submitted assumption values (JSON array) ────────
        assumption_values = parse_assumption_json(message)
        if assumption_values is not None:
            # Determine which agent needs re-run
            if current == "business_value" or state.business_value.get("phase") == "needs_input":
                state.business_value["user_assumptions"] = assumption_values
                target_agent = "business_value"
            elif current == "cost" or state.costs.get("phase") == "needs_input":
                state.costs["user_assumptions"] = assumption_values
                target_agent = "cost"
            else:
                # Fallback: the current step name is ambiguous or not set —
                # default to business_value for backward compatibility.
                # This can occur when older state snapshots lack current_step.
                state.business_value["user_assumptions"] = assumption_values
                target_agent = "business_value"

            state.completed_steps = [
                s for s in state.completed_steps if s != target_agent
            ]
            self.phases[project_id] = "executing"
            agent_label = (
                "business value" if target_agent == "business_value" else "cost estimate"
            )
            yield self._msg(
                project_id,
                f"📊 Got your numbers — calculating {agent_label}...",
                {"type": "pm_response"},
            )
            async for msg in self.run_single_step(project_id, state, target_agent):
                yield msg
            return

        # ── Two-phase: user says "proceed" while BV awaits input (use defaults) ──
        if (
            current == "business_value"
            and state.business_value.get("phase") == "needs_input"
            and intent == Intent.PROCEED
        ):
            assumptions = state.business_value.get("assumptions_needed", [])
            state.business_value["user_assumptions"] = build_default_values(assumptions)
            state.completed_steps = [
                s for s in state.completed_steps if s != "business_value"
            ]
            self.phases[project_id] = "executing"
            yield self._msg(
                project_id,
                "📊 Using default values — calculating business value...",
                {"type": "pm_response"},
            )
            async for msg in self.run_single_step(project_id, state, "business_value"):
                yield msg
            return

        # ── Two-phase: user says "proceed" while cost awaits input (use defaults) ──
        if (
            current == "cost"
            and state.costs.get("phase") == "needs_input"
            and intent == Intent.PROCEED
        ):
            assumptions = state.costs.get("assumptions_needed", [])
            state.costs["user_assumptions"] = build_default_values(assumptions)
            state.completed_steps = [
                s for s in state.completed_steps if s != "cost"
            ]
            self.phases[project_id] = "executing"
            yield self._msg(
                project_id,
                "💰 Using default values — calculating costs...",
                {"type": "pm_response"},
            )
            async for msg in self.run_single_step(project_id, state, "cost"):
                yield msg
            return

        # ── Standard approval-gate intents ─────────────────────────────────

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
            agent_output = (
                self.pm.format_agent_output(step_name, state) if step_name else ""
            )
            answer = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: llm.invoke(
                    [
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
                    ]
                ).content,
            )
            yield self._msg(
                project_id,
                f"{answer}\n\nSay **proceed** to continue, "
                "**refine** to adjust, or **skip** to move on.",
                {"type": "pm_response"},
            )

        elif intent == Intent.INPUT:
            # User is providing additional context — re-run the current agent
            state.clarifications += f"\nAdditional input: {message}"
            last_step = current or (
                state.completed_steps[-1] if state.completed_steps else ""
            )
            if last_step:
                state.completed_steps = [
                    s for s in state.completed_steps if s != last_step
                ]
                info = AGENT_INFO.get(last_step, {"name": last_step, "emoji": "🔧"})
                yield self._msg(
                    project_id,
                    f"Got it — re-running **{info['name']}** with your input...",
                    {"type": "pm_response"},
                )
                state.awaiting_approval = False
                self.phases[project_id] = "executing"
                async for msg in self.run_single_step(project_id, state, last_step):
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
            async for msg in self.run_single_step(project_id, state, current):
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
