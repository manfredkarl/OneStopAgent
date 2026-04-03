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
        self._pending_assumptions: dict[str, list] = {}  # project_id → generated assumptions
        self._locks: dict[str, asyncio.Lock] = {}  # per-project concurrency guard (for future use)

    def _cleanup_project(self, project_id: str) -> None:
        """Remove workflow and pending requests for completed project."""
        self.workflows.pop(project_id, None)
        self.pending_requests.pop(project_id, None)
        self._pending_assumptions.pop(project_id, None)
        self._locks.pop(project_id, None)

    def _get_lock(self, project_id: str) -> asyncio.Lock:
        if project_id not in self._locks:
            self._locks[project_id] = asyncio.Lock()
        return self._locks[project_id]

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

        try:
            intent, meta = await asyncio.wait_for(
                pm.intent_interpreter.aclassify(message), timeout=30
            )
        except asyncio.TimeoutError:
            logger.warning("Intent classification timed out, defaulting to INPUT")
            intent, meta = Intent.INPUT, {}

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

            state.brainstorming = {
                "scenarios": result.get("scenarios", []),
                "industry": result.get("industry", "Cross-Industry"),
            }
            state.azure_fit = result.get("azure_fit", "unclear")
            state.azure_fit_explanation = result.get("azure_fit_explanation", "")
            greeting = result["response"]

            if isinstance(greeting, str) and greeting.strip().startswith("{"):
                try:
                    inner = json.loads(greeting)
                    if isinstance(inner, dict) and "response" in inner:
                        greeting = inner["response"]
                except json.JSONDecodeError:
                    pass

            normalized_agents = [a.replace("-", "_") for a in active_agents]
            plan = pm.build_plan(normalized_agents)
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

                # Generate shared assumptions before starting the pipeline
                assumptions = await self._generate_shared_assumptions(state)
                self._pending_assumptions[project_id] = assumptions
                self.phases[project_id] = "collecting_assumptions"

                yield ChatMessage(
                    project_id=project_id, role="agent", agent_id="pm",
                    content="Before we start, please confirm the scenario assumptions that all agents will use:",
                    metadata={"type": "assumptions_input", "step": "shared", "assumptions": assumptions},
                )

            elif intent == Intent.SKIP:
                yield self._msg(project_id, "Got it. What else would you like to adjust, or say **proceed** to start?")

            else:
                if state.clarifications:
                    state.clarifications += f"\n{message}"
                else:
                    state.clarifications = message
                try:
                    ack = await asyncio.wait_for(llm.ainvoke([
                        {"role": "system", "content": (
                            "You are a project manager. The user just answered your questions about their Azure project. "
                            "Briefly acknowledge their input in 1-2 sentences. Then ask if there's anything else or if they want to proceed. "
                            "Be concise. Use **proceed** in bold."
                        )},
                        {"role": "user", "content": f"User's original request: {state.user_input}\n\nUser's additional input: {message}"},
                    ]), timeout=30)
                    ack_text = ack.content.strip()
                except (asyncio.TimeoutError, Exception):
                    ack_text = "Got it. Anything else, or say **proceed** to start?"
                yield self._msg(project_id, ack_text)

        # ── Phase: collecting_assumptions ──────────────────────────────
        elif phase == "collecting_assumptions":
            # Parse user's response (JSON from the assumptions form, or free-text fallback)
            try:
                user_values = json.loads(message)
            except json.JSONDecodeError:
                # User said "proceed" with defaults
                assumptions = self._pending_assumptions.get(project_id, [])
                user_values = [
                    {"id": a["id"], "label": a.get("label", a["id"]), "value": a.get("default", 0), "unit": a.get("unit", "")}
                    for a in assumptions
                ]

            # Store as shared assumptions dict
            state.shared_assumptions = {
                item.get("id", ""): item.get("value", 0)
                for item in user_values if item.get("id")
            }
            # Also store the full items for display
            state.shared_assumptions["_items"] = user_values

            self._pending_assumptions.pop(project_id, None)

            yield self._msg(project_id, "✅ Scenario assumptions locked. Starting agent pipeline...", {"type": "pm_response"})

            self.phases[project_id] = "executing"
            normalized_agents = [a.replace("-", "_") for a in active_agents]
            plan = pm.build_plan(normalized_agents)
            state.plan_steps = plan

            async for msg in self._run_workflow(project_id, state, active_agents):
                yield msg

        # ── Phase: executing (workflow paused for HITL) ─────────────
        elif phase == "executing":
            pending = self.pending_requests.get(project_id, {})
            if pending:
                # Feed user response to the paused workflow
                async for msg in self._resume_workflow(project_id, state, message, pending):
                    yield msg
            elif intent == Intent.QUESTION:
                try:
                    follow_up = await asyncio.wait_for(llm.ainvoke([
                        {"role": "system", "content": "You are a project manager. The solution is being built. Answer briefly."},
                        {"role": "user", "content": f"Context: {state.to_context_string()}\n\nUser asks: {message}"},
                    ]), timeout=30)
                    follow_up_text = follow_up.content
                except asyncio.TimeoutError:
                    follow_up_text = "I'm still working on it. Please hold on."
                yield self._msg(project_id, follow_up_text)
            else:
                yield self._msg(project_id, "I'll address that after the current step completes.")

        # ── Phase: done ─────────────────────────────────────────────
        elif phase == "done":
            # AC-4: Detect granular retry commands ("retry cost", "retry roi", etc.)
            retry_target = self._parse_retry_command(message)
            if retry_target:
                # Determine which agents to re-run (target + downstream)
                agents_to_rerun = self._retry_agents_for(retry_target)
                state.clarifications += f"\nRetry: {message}"

                rerun_set = set(agents_to_rerun)
                state.completed_steps = [s for s in state.completed_steps if s not in rerun_set]
                state.failed_steps = [s for s in state.failed_steps if s not in rerun_set]
                state.skipped_steps = [s for s in state.skipped_steps if s not in rerun_set]

                AGENT_STATE_FIELDS = {
                    "cost": "costs", "business_value": "business_value",
                    "roi": "roi", "presentation": "presentation_path",
                }
                for agent_name in agents_to_rerun:
                    # Clear stale phase markers
                    if agent_name == "cost" and "phase" in state.costs:
                        del state.costs["phase"]
                    if agent_name == "business_value" and "phase" in state.business_value:
                        del state.business_value["phase"]
                    # Reset output state
                    field = AGENT_STATE_FIELDS.get(agent_name)
                    if field:
                        if field == "presentation_path":
                            state.presentation_path = ""
                        else:
                            setattr(state, field, {})

                names = [AGENT_INFO.get(a, {"name": a})["name"] for a in agents_to_rerun]
                yield self._msg(
                    project_id,
                    f"Retrying {names[0]} and downstream agents ({', '.join(names)})...",
                    {"type": "pm_response"},
                )
                self.phases[project_id] = "executing"
                async for msg in self._run_workflow(project_id, state, list(rerun_set)):
                    yield msg

            elif intent == Intent.ITERATION:
                agents_to_rerun = meta.get("agents_to_rerun") or pm.get_agents_to_rerun(message)
                state.clarifications += f"\nIteration: {message}"

                rerun_set = set(agents_to_rerun)
                state.completed_steps = [s for s in state.completed_steps if s not in rerun_set]
                state.failed_steps = [s for s in state.failed_steps if s not in rerun_set]
                state.skipped_steps = [s for s in state.skipped_steps if s not in rerun_set]

                # H4: Clear agent-specific phase markers to avoid stale "needs_input"
                for agent_name in agents_to_rerun:
                    if agent_name == "cost" and "phase" in state.costs:
                        del state.costs["phase"]
                    if agent_name == "business_value" and "phase" in state.business_value:
                        del state.business_value["phase"]

                # H5: Reset agent output dicts so old results don't mix with new
                AGENT_STATE_FIELDS = {
                    "architect": "architecture",
                    "cost": "costs",
                    "business_value": "business_value",
                    "roi": "roi",
                    "presentation": "presentation_path",
                }
                for agent_name in agents_to_rerun:
                    field = AGENT_STATE_FIELDS.get(agent_name)
                    if field:
                        if field == "presentation_path":
                            state.presentation_path = ""
                        else:
                            setattr(state, field, {})

                names = [AGENT_INFO.get(a, {"name": a})["name"] for a in agents_to_rerun]
                yield self._msg(project_id, f"Re-running {len(agents_to_rerun)} agents ({', '.join(names)}) with your feedback...")

                self.phases[project_id] = "executing"
                async for msg in self._run_workflow(project_id, state, list(rerun_set)):
                    yield msg

            elif intent == Intent.BRAINSTORM:
                self._cleanup_project(project_id)
                self.phases[project_id] = "new"
                state.mode = "brainstorm"
                state.completed_steps.clear()
                state.skipped_steps.clear()
                state.failed_steps.clear()
                yield self._msg(project_id, "Starting fresh! Tell me about your project.")

            else:
                try:
                    follow_up = await asyncio.wait_for(llm.ainvoke([
                        {"role": "system", "content": "You are an Azure solution project manager. The solution has been designed. Help the user with follow-up questions or modifications. Be brief."},
                        {"role": "user", "content": f"Context: {state.to_context_string()}\n\nUser says: {message}"},
                    ]), timeout=30)
                    follow_up_text = follow_up.content
                except asyncio.TimeoutError:
                    follow_up_text = "I'm having trouble processing that right now. Could you try again?"
                yield self._msg(project_id, follow_up_text)

    # ── Shared assumption generation ───────────────────────────────

    async def _generate_shared_assumptions(self, state: AgentState) -> list[dict]:
        """Generate overarching scenario assumptions that all agents share.
        
        Keeps it lean — only the essentials that ALL agents need for consistency.
        Technical details (data volume, timeline, requests/day) belong in agent-specific questions.
        """
        industry = state.brainstorming.get("industry", "Cross-Industry")
        description = state.user_input

        try:
            response = await asyncio.wait_for(llm.ainvoke([
                {"role": "system", "content": (
                    "Generate EXACTLY 4 scenario assumption questions that define the business context "
                    "for an Azure solution. These will be shared across all agents.\n\n"
                    "Return ONLY a JSON array with 4 items:\n"
                    '{"id": "snake_case", "label": "Question", "unit": "count" or "$", "default": number, "hint": "Why it matters"}\n\n'
                    "The 4 questions MUST cover:\n"
                    "1. AFFECTED STAFF: How many employees or staff members are directly affected by or will work with this solution (do NOT count end-users or customers)\n"
                    "2. CURRENT SPEND: Current annual spend on equivalent tools/processes ($)\n"
                    "3. LABOR RATE: Fully loaded hourly cost for affected staff ($/hr)\n"
                    "4. PLATFORM SCALE: Peak concurrent users or transactions on the platform\n\n"
                    "Use realistic enterprise defaults. Be specific to the industry. "
                    "Unit for labor rate must be '$/hr' not 'hours'."
                )},
                {"role": "user", "content": f"Industry: {industry}\nUse case: {description}"},
            ]), timeout=30)
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            assumptions = json.loads(text)
            if isinstance(assumptions, list) and len(assumptions) >= 3:
                return assumptions[:5]
        except Exception as e:
            logger.warning("Failed to generate shared assumptions: %s", e)

        # Fallback defaults — lean and essential
        return [
            {"id": "affected_employees", "label": "Employees directly affected by the solution", "unit": "count", "default": 50, "hint": "Drives labor savings and change-management scope"},
            {"id": "current_annual_spend", "label": "Current annual spend on equivalent tools/processes", "unit": "$", "default": 500000, "hint": "Baseline for ROI and value calculation"},
            {"id": "hourly_labor_rate", "label": "Fully loaded hourly rate for affected staff", "unit": "$/hr", "default": 85, "hint": "Used to monetize time savings"},
            {"id": "concurrent_users", "label": "Peak concurrent users on the platform", "unit": "count", "default": 100, "hint": "Determines compute tier and scaling"},
        ]

    # ── MAF Workflow execution ──────────────────────────────────────

    # AC-4: Granular retry — "retry cost" re-runs cost + downstream only
    _RETRY_PATTERNS: dict[str, str] = {
        "retry cost": "cost",
        "retry roi": "roi",
        "retry business value": "business_value",
        "retry bv": "business_value",
        "retry architect": "architect",
        "retry presentation": "presentation",
        "redo cost": "cost",
        "redo roi": "roi",
        "rerun cost": "cost",
        "rerun roi": "roi",
    }

    # Pipeline order for AC-4 downstream dependency
    _PIPELINE_ORDER = ["business_value", "architect", "cost", "roi", "presentation"]

    @classmethod
    def _parse_retry_command(cls, message: str) -> str | None:
        """AC-4: Detect 'retry <agent>' commands. Returns agent name or None."""
        msg_lower = message.strip().lower()
        for pattern, agent in cls._RETRY_PATTERNS.items():
            if msg_lower.startswith(pattern):
                return agent
        return None

    @classmethod
    def _retry_agents_for(cls, agent: str) -> list[str]:
        """AC-4: Return agent + all downstream agents to re-run."""
        try:
            start_idx = cls._PIPELINE_ORDER.index(agent)
        except ValueError:
            return [agent]
        return cls._PIPELINE_ORDER[start_idx:]

    async def _run_workflow(
        self, project_id: str, state: AgentState, active_agents: list[str],
    ) -> AsyncGenerator[ChatMessage, None]:
        """Start a new MAF workflow and stream events as ChatMessages."""
        wf = create_pipeline_workflow()
        self.workflows[project_id] = wf

        # Normalize agent IDs: frontend uses hyphens, backend uses underscores
        normalized = [a.replace("-", "_") for a in active_agents]

        pipeline_msg = PipelineMessage(
            state=state,
            project_id=project_id,
            execution_mode=state.execution_mode,
            active_agents=normalized,
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

        # Respond to first pending request only
        if not pending:
            yield self._msg(project_id, "No pending request to respond to.")
            return
        first_req_id = next(iter(pending))
        responses = {first_req_id: message}

        # Keep remaining requests pending
        remaining = {k: v for k, v in pending.items() if k != first_req_id}
        self.pending_requests[project_id] = remaining

        stream = wf.run(stream=True, responses=responses)
        async for chat_msg in self._process_workflow_events(project_id, stream):
            yield chat_msg

    async def _process_workflow_events(
        self, project_id: str, stream,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Convert MAF WorkflowEvents → ChatMessage SSE format."""
        try:
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
                        # Normalize step name for frontend (underscores → hyphens)
                        agent_id = step.replace("_", "-")
                        plan_text = pm.format_plan(self.get_state(project_id))
                        yield ChatMessage(
                            project_id=project_id, role="agent", agent_id="pm",
                            content=plan_text,
                            metadata={"type": "plan_update", "step": step, "status": "running"},
                        )
                        # Signal sidebar to highlight this agent
                        yield ChatMessage(
                            project_id=project_id, role="agent", agent_id=agent_id,
                            content="",
                            metadata={"type": "agent_start", "agent": agent_id, "step": step},
                        )

                    elif etype == "agent_result":
                        agent_id = step.replace("_", "-")
                        content = data.get("content", "")
                        metadata: dict = {"type": "agent_result", "agent": agent_id, "step": step}
                        if "dashboard" in data and data["dashboard"]:
                            metadata["type"] = "roi_dashboard"
                            metadata["dashboard"] = data["dashboard"]
                        yield ChatMessage(
                            project_id=project_id, role="agent",
                            agent_id=agent_id, content=content, metadata=metadata,
                        )

                    elif etype == "agent_error":
                        agent_id_err = step.replace("_", "-")
                        yield ChatMessage(
                            project_id=project_id, role="agent", agent_id=agent_id_err,
                            content=f"\u26a0\ufe0f {step} failed: {data.get('error', 'unknown')}",
                            metadata={"type": "agent_error", "agent": agent_id_err, "step": step},
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
                        self._cleanup_project(project_id)
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
        except Exception as e:
            logger.exception("Workflow execution failed for project %s", project_id)
            self.phases[project_id] = "done"
            self._cleanup_project(project_id)
            yield ChatMessage(
                project_id=project_id, role="agent", agent_id="pm",
                content=f"⚠️ An error occurred during execution: {str(e)}\n\nYou can try again or start fresh.",
                metadata={"type": "error"},
            )
