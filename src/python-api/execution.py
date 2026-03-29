"""Agent execution engine — run_single_step, streaming/non-streaming paths, heartbeat.

Provides :class:`ExecutionMixin`, which is mixed into
:class:`orchestrator.Orchestrator` to run agent pipeline steps.

FRD-01 §3 (PM class), §4 (execution plan), §8 (errors).
"""

import asyncio
import uuid
from typing import AsyncGenerator

from agents.pm_agent import AGENT_INFO
from agents.state import AgentState
from models.schemas import ChatMessage


class ExecutionMixin:
    """Agent execution engine mixed into Orchestrator.

    Expects to be mixed into a class that provides:
    - ``self.agents: dict[str, object]`` — agent registry keyed by step name
    - ``self.pm`` — ProjectManager instance
    - ``self.phases: dict[str, str]``
    - ``self.states: dict[str, AgentState]``
    - ``self._msg(project_id, content, metadata) -> ChatMessage``
    - ``self.should_pause(state, step) -> bool``
    """

    # ── Completion summary ─────────────────────────────────────────────────

    def _completion_summary(
        self, project_id: str, state: AgentState
    ) -> ChatMessage:
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

    # ── Plan execution ─────────────────────────────────────────────────────

    async def execute_plan(
        self,
        project_id: str,
        state: AgentState,
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
        self,
        project_id: str,
        state: AgentState,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Continue execution from the next pending step."""
        next_step = state.next_pending_step()
        if not next_step:
            self.phases[project_id] = "done"
            yield self._completion_summary(project_id, state)
            return

        async for msg in self.run_single_step(project_id, state, next_step):
            yield msg

    # ── Single step ────────────────────────────────────────────────────────

    async def run_single_step(
        self,
        project_id: str,
        state: AgentState,
        step: str,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Run one agent step, then gate for approval."""
        info = AGENT_INFO.get(step, {"name": step, "emoji": "🔧"})
        agent = self.agents.get(step)

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

        if hasattr(agent, "run_streaming"):
            # ── Async streaming path ─────────────────────────────────────
            async for msg in self._run_step_streaming(project_id, state, step, agent, info):
                yield msg
        else:
            # ── Non-streaming path (thread pool + heartbeat) ─────────────
            async for msg in self._run_step_sync(project_id, state, step, agent, info):
                yield msg

    # ── Streaming execution ────────────────────────────────────────────────

    async def _run_step_streaming(
        self,
        project_id: str,
        state: AgentState,
        step: str,
        agent: object,
        info: dict,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Run a streaming agent and yield token + result messages."""
        msg_id = str(uuid.uuid4())
        token_queue: asyncio.Queue = asyncio.Queue()
        stream_state_holder: list = [None]
        stream_error_holder: list = [None]

        async def _run_streaming():
            try:
                def on_token(token: str):
                    token_queue.put_nowait(token)

                stream_state_holder[0] = await agent.run_streaming(state, on_token)
            except Exception as e:
                stream_error_holder[0] = e
            finally:
                token_queue.put_nowait(None)  # sentinel

        task = asyncio.create_task(_run_streaming())

        while True:
            token = await token_queue.get()
            if token is None:
                break
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id=step,
                content=token,
                metadata={
                    "type": "agent_token",
                    "agent": step,
                    "msg_id": msg_id,
                    "token": token,
                },
            )

        await task

        try:
            if stream_error_holder[0]:
                raise stream_error_holder[0]
            state = stream_state_holder[0]
            self.states[project_id] = state

            # Check two-phase needs_input gate
            needs_input_msg = self._check_needs_input(
                project_id, state, step, msg_id=msg_id
            )
            if needs_input_msg is not None:
                yield needs_input_msg
                return

            state.mark_step_completed(step)

            # Emit plan_update: completed
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id="pm",
                content="",
                metadata={"type": "plan_update", "step": step, "status": "completed"},
            )

            # Emit full agent result (reuses msg_id so frontend replaces streaming message)
            formatted = self.pm.format_agent_output(step, state)
            meta: dict = {"type": "agent_result", "agent": step}
            if step == "roi" and state.roi.get("dashboard"):
                meta["type"] = "roi_dashboard"
                meta["dashboard"] = state.roi["dashboard"]
            yield ChatMessage(
                id=msg_id,
                project_id=project_id,
                role="agent",
                agent_id=step,
                content=formatted,
                metadata=meta,
            )

            # Approval gate (FRD-01 §2.3)
            async for msg in self._apply_approval_gate(project_id, state, step):
                yield msg

        except Exception as e:
            async for msg in self._emit_step_failure(project_id, state, step, info, e):
                yield msg

    # ── Non-streaming execution ────────────────────────────────────────────

    async def _run_step_sync(
        self,
        project_id: str,
        state: AgentState,
        step: str,
        agent: object,
        info: dict,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Run a non-streaming agent via thread pool with a progress heartbeat."""
        loop = asyncio.get_event_loop()
        done_event = asyncio.Event()
        result_holder: list = [None]
        error_holder: list = [None]

        def _run():
            try:
                result_holder[0] = agent.run(state)
            except Exception as e:
                error_holder[0] = e
            loop.call_soon_threadsafe(done_event.set)

        loop.run_in_executor(None, _run)

        # Heartbeat: emit progress every 5 s while agent runs
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
            self.states[project_id] = state

            # Check two-phase needs_input gate
            needs_input_msg = self._check_needs_input(project_id, state, step)
            if needs_input_msg is not None:
                yield needs_input_msg
                return

            state.mark_step_completed(step)

            # Emit plan_update: completed
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id="pm",
                content="",
                metadata={"type": "plan_update", "step": step, "status": "completed"},
            )

            # Emit formatted agent result
            formatted = self.pm.format_agent_output(step, state)
            meta: dict = {"type": "agent_result", "agent": step}
            if step == "roi" and state.roi.get("dashboard"):
                meta["type"] = "roi_dashboard"
                meta["dashboard"] = state.roi["dashboard"]
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id=step,
                content=formatted,
                metadata=meta,
            )

            # Approval gate (FRD-01 §2.3)
            async for msg in self._apply_approval_gate(project_id, state, step):
                yield msg

        except Exception as e:
            async for msg in self._emit_step_failure(project_id, state, step, info, e):
                yield msg

    # ── Shared helpers ─────────────────────────────────────────────────────

    def _check_needs_input(
        self,
        project_id: str,
        state: AgentState,
        step: str,
        *,
        msg_id: str | None = None,
    ) -> ChatMessage | None:
        """If the agent returned a *needs_input* phase, emit the assumptions form
        and transition to the ``approval`` phase.

        Returns the :class:`ChatMessage` to yield (and the caller should ``return``
        immediately after yielding it), or *None* if the step completed normally.
        """
        # Business Value — Phase 1
        if step == "business_value" and state.business_value.get("phase") == "needs_input":
            assumptions = state.business_value["assumptions_needed"]
            formatted = self.pm.format_agent_output(step, state)
            state.awaiting_approval = True
            state.current_step = "business_value"
            self.phases[project_id] = "approval"
            kwargs: dict = {
                "project_id": project_id,
                "role": "agent",
                "agent_id": step,
                "content": formatted,
                "metadata": {
                    "type": "assumptions_input",
                    "assumptions": assumptions,
                },
            }
            if msg_id is not None:
                kwargs["id"] = msg_id
            return ChatMessage(**kwargs)

        # Cost — Phase 1
        if step == "cost" and state.costs.get("phase") == "needs_input":
            assumptions = state.costs["assumptions_needed"]
            state.awaiting_approval = True
            state.current_step = "cost"
            self.phases[project_id] = "approval"
            kwargs = {
                "project_id": project_id,
                "role": "agent",
                "agent_id": step,
                "content": (
                    "To estimate costs accurately, I need a few details "
                    "about your expected usage:"
                ),
                "metadata": {
                    "type": "assumptions_input",
                    "assumptions": assumptions,
                },
            }
            if msg_id is not None:
                kwargs["id"] = msg_id
            return ChatMessage(**kwargs)

        return None

    async def _apply_approval_gate(
        self,
        project_id: str,
        state: AgentState,
        step: str,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Emit an approval prompt or continue execution automatically."""
        if self.should_pause(state, step):
            summary = self.pm.approval_summary(step, state)
            state.awaiting_approval = True
            state.current_step = step
            self.phases[project_id] = "approval"
            yield self._msg(
                project_id,
                summary,
                {"type": "approval", "step": step},
            )
        else:
            async for msg in self.continue_execution(project_id, state):
                yield msg

    async def _emit_step_failure(
        self,
        project_id: str,
        state: AgentState,
        step: str,
        info: dict,
        error: Exception,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Emit failure events and continue the pipeline (FRD-01 §8)."""
        state.mark_step_failed(step)
        yield ChatMessage(
            project_id=project_id,
            role="agent",
            agent_id="pm",
            content="",
            metadata={"type": "plan_update", "step": step, "status": "failed"},
        )
        yield self._msg(
            project_id,
            f"⚠️ {info['name']} failed: {str(error)}",
            {"type": "agent_error", "agent": step},
        )
        # Pipeline never stops (FRD-01 §8)
        async for msg in self.continue_execution(project_id, state):
            yield msg
