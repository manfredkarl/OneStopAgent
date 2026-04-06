"""MAF-backed orchestrator — replaces the legacy orchestrator.py.

Keeps the PM brainstorming / plan_shown phases as conversational logic,
but delegates the agent execution pipeline to the MAF Workflow in workflow.py.
Converts MAF WorkflowEvents → ChatMessage SSE format so the React frontend
needs zero changes.
"""

import asyncio
import copy
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from agents.state import AgentState
from agents.pm_agent import ProjectManager, AGENT_INFO, Intent
from agents.llm import llm
from models.schemas import ChatMessage
from workflow import (
    create_pipeline_workflow, PipelineMessage, ApprovalRequest, AssumptionsRequest,
    PIPELINE_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)
pm = ProjectManager()

# Agent name → AgentState field mapping (used for retry/iteration state resets)
_AGENT_STATE_FIELDS = {
    "architect": "architecture",
    "cost": "costs",
    "business_value": "business_value",
    "roi": "roi",
    "presentation": "presentation_path",
}

# @mention regex for targeting specific agents
_AGENT_MENTION_RE = re.compile(
    r'@(architect|cost|business[_\s]?value|bv|roi|presentation|pm)\b',
    re.IGNORECASE,
)

# Regex for detecting numeric assumption corrections in user messages
_NUMERIC_UPDATE_RE = re.compile(
    r'(?:actually|changed?\s+to|now|updated?\s+to|correct(?:ion)?:?|should\s+be)\s+'
    r'(\d[\d,]*(?:\.\d+)?)\s*'
    r'(users?|employees?|spend|budget|gb|tb|months?|revenue)',
    re.IGNORECASE,
)

# Map captured keyword → SharedAssumptions field name
_ASSUMPTION_FIELD_MAP: dict[str, str] = {
    "user": "total_users",
    "employee": "affected_employees",
    "spend": "current_annual_spend",
    "budget": "current_annual_spend",
    "gb": "data_volume_gb",
    "tb": "data_volume_gb",
    "month": "timeline_months",
    "revenue": "monthly_revenue",
}

# Which assumption fields affect which downstream agents
_ASSUMPTION_AGENT_IMPACT: dict[str, list[str]] = {
    "total_users": ["cost", "roi", "presentation"],
    "concurrent_users": ["cost", "roi", "presentation"],
    "current_annual_spend": ["business_value", "roi", "presentation"],
    "monthly_revenue": ["business_value", "roi", "presentation"],
}

# Conversational mode entry regex
_CHAT_WITH_RE = re.compile(
    r'(?:chat|talk|discuss|speak)\s+(?:with|to)\s+(architect|cost|business[_\s]?value|bv|roi|presentation)',
    re.IGNORECASE,
)


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

    def __init__(self, store=None):
        self.states: dict[str, AgentState] = {}
        self.phases: dict[str, str] = {}
        self.workflows: dict[str, object] = {}  # MAF Workflow per project
        self.pending_requests: dict[str, dict] = {}  # project_id → {request_id: ...}
        self._pending_assumptions: dict[str, list] = {}  # project_id → generated assumptions
        self._locks: dict[str, asyncio.Lock] = {}  # per-project concurrency guard (for future use)
        self._chat_histories: dict[str, list[str]] = {}  # project_id → user messages
        self._deferred_rerun: dict[str, set[str]] = {}  # agents flagged by _drain_queue for re-run
        self._store = store  # optional persistence store (CosmosProjectStore)

    def _cleanup_project(self, project_id: str) -> None:
        """Remove workflow and pending requests for completed project.

        Clears all per-project dicts except states/phases (user may query
        state after pipeline is done) and _chat_histories (post-completion
        context).
        """
        self.workflows.pop(project_id, None)
        self.pending_requests.pop(project_id, None)
        self._pending_assumptions.pop(project_id, None)
        self._chat_histories.pop(project_id, None)
        self._locks.pop(project_id, None)
        self._deferred_rerun.pop(project_id, None)

    def _recent_messages(self, project_id: str, count: int = 3) -> list[str]:
        """Return the last ``count`` user messages for a project."""
        history = self._chat_histories.get(project_id, [])
        return history[-count:]

    def _get_lock(self, project_id: str) -> asyncio.Lock:
        if project_id not in self._locks:
            self._locks[project_id] = asyncio.Lock()
        return self._locks[project_id]

    def get_state(self, project_id: str) -> AgentState:
        if project_id not in self.states:
            self.states[project_id] = AgentState()
        return self.states[project_id]

    async def _persist_state(self, project_id: str) -> None:
        """Save agent state to Cosmos DB if a store is configured."""
        if self._store and hasattr(self._store, "save_state"):
            try:
                await self._store.save_state(project_id, self.get_state(project_id))
            except Exception:
                logger.warning("Failed to persist state for %s", project_id, exc_info=True)

    async def _save_checkpoint(self, project_id: str, step_name: str) -> None:
        """Save a state checkpoint before an agent runs."""
        if self._store and hasattr(self._store, "save_checkpoint"):
            try:
                await self._store.save_checkpoint(
                    project_id, step_name, self.get_state(project_id),
                )
            except Exception:
                logger.warning("Failed to save checkpoint for %s/%s", project_id, step_name)

    async def _inject_chat_history(self, project_id: str, state: AgentState) -> None:
        """Load recent chat messages from the store into state.recent_chat."""
        if self._store and hasattr(self._store, "get_messages"):
            try:
                msgs = await self._store.get_messages(project_id)
                state.recent_chat = [
                    {"role": m.role, "content": m.content} for m in msgs[-6:]
                ]
            except Exception:
                logger.debug("Could not load chat history for %s", project_id)

    def _msg(self, project_id: str, content: str, metadata: dict | None = None,
             agent_id: str = "pm") -> ChatMessage:
        return ChatMessage(
            project_id=project_id, role="agent", agent_id=agent_id,
            content=content, metadata=metadata or {"type": "pm_response"},
        )

    async def handle_message(
        self, project_id: str, message: str,
        active_agents: list[str], description: str,
        company_profile: dict | None = None,
    ) -> AsyncGenerator[ChatMessage, None]:
      try:
        state = self.get_state(project_id)
        phase = self.phases.get(project_id, "new")

        # Track user messages for context-aware classification
        self._chat_histories.setdefault(project_id, []).append(message)

        # ── Conversational mode: exit check ─────────────────────────
        if state.conversation_agent:
            if message.strip().lower() in ("done", "exit", "proceed", "stop", "back"):
                agent = state.conversation_agent
                state.conversation_agent = ""
                state.conversation_turns = 0
                yield self._msg(project_id, f"Left conversation with {agent}. What would you like to do next?")
                return

            async for msg in self._handle_conversation(project_id, state, message):
                yield msg
            return

        # ── Conversational mode: entry check ────────────────────────
        chat_match = _CHAT_WITH_RE.search(message)
        if chat_match:
            agent = chat_match.group(1).lower().replace(" ", "_")
            if agent == "bv":
                agent = "business_value"
            state.conversation_agent = agent
            state.conversation_turns = 0
            yield self._msg(project_id, f"💬 You're now chatting with the **{agent}** agent. Say **done** or click the button when finished.")
            return

        # Attach company profile to state on first message (phase == "new")
        if phase == "new" and company_profile and not state.company_profile:
            state.company_profile = company_profile

        try:
            intents, meta = await asyncio.wait_for(
                pm.intent_interpreter.aclassify(
                    message,
                    phase=phase,
                    current_step=state.current_step,
                    recent_messages=self._recent_messages(project_id),
                ),
                timeout=30,
            )
        except asyncio.TimeoutError:
            logger.warning("Intent classification timed out, defaulting to [INPUT]")
            intents, meta = [Intent.INPUT], {}

        # Primary intent is the first in the array
        intent = intents[0]

        # ── @agent mention routing ──────────────────────────────────
        target_agent, cleaned_message = self._parse_agent_mention(message)
        if target_agent and phase == "done":
            agents_to_rerun = self._retry_agents_for(target_agent)
            state.clarifications += f"\nDirect request for {target_agent}: {cleaned_message}"

            # Capture before snapshot for iteration tracking
            self._record_iteration_before(state, agents_to_rerun, cleaned_message)

            rerun_set = set(agents_to_rerun)
            with state._lock:
                state.completed_steps = [s for s in state.completed_steps if s not in rerun_set]
                state.failed_steps = [s for s in state.failed_steps if s not in rerun_set]
                state.skipped_steps = [s for s in state.skipped_steps if s not in rerun_set]

                for agent_name in agents_to_rerun:
                    if agent_name == "cost" and "phase" in state.costs:
                        del state.costs["phase"]
                    if agent_name == "business_value" and "phase" in state.business_value:
                        del state.business_value["phase"]
                    field = _AGENT_STATE_FIELDS.get(agent_name)
                    if field:
                        if field == "presentation_path":
                            state.presentation_path = ""
                        elif field == "architecture" and "architect" not in rerun_set:
                            pass
                        else:
                            setattr(state, field, {})

            names = [AGENT_INFO.get(a, {"name": a})["name"] for a in agents_to_rerun]
            yield self._msg(project_id, f"Targeting {names[0]} ({', '.join(names)}) with your feedback...")
            self.phases[project_id] = "executing"
            async for msg in self._run_workflow(project_id, state, list(rerun_set)):
                yield msg

            # Capture after snapshot and emit diff summary
            self._record_iteration_after(state)
            if state.iteration_history:
                diff_summary = self._format_iteration_diff(state.iteration_history[-1])
                yield self._msg(project_id, diff_summary, {"type": "iteration_diff"})
            return
        elif target_agent and phase == "executing":
            state.queued_messages.append({
                "message": cleaned_message,
                "intents": ["iteration"],
                "meta": {"agents_to_rerun": self._retry_agents_for(target_agent)},
            })
            yield self._msg(project_id, f"📝 Noted for {target_agent} — will apply after current step.")
            return

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
                try:
                    result_holder[0] = await pm.brainstorm_greeting_streaming(
                        message, on_token, company_profile=state.company_profile
                    )
                except Exception as e:
                    logger.error("PM brainstorm failed: %s", e)
                    result_holder[0] = e
                finally:
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

            # If brainstorm failed (e.g. expired token), send error to user
            if isinstance(result, Exception):
                yield ChatMessage(
                    project_id=project_id, role="agent", agent_id="pm",
                    content=f"⚠️ Project Manager failed to start: {result}\n\nPlease check your Azure OpenAI credentials and try again.",
                    metadata={"type": "error", "agent": "pm"},
                )
                return

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
                # Check for numeric assumption updates in clarifications
                self._detect_assumption_updates(message, state)

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
                except (asyncio.TimeoutError, json.JSONDecodeError, ValueError, TypeError, RuntimeError):
                    ack_text = "Got it. Anything else, or say **proceed** to start?"
                yield self._msg(project_id, ack_text)

            # After processing primary intent, check for secondary iteration intent
            if len(intents) > 1 and Intent.ITERATION in intents[1:]:
                state.clarifications += f"\nPending iteration: {message}"

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
            # Detect and apply numeric assumption corrections mid-pipeline
            updated_fields = self._detect_assumption_updates(message, state)
            if updated_fields:
                yield self._msg(project_id, f"📊 Updated assumptions: {', '.join(updated_fields)}. "
                                f"Affected agents will be refreshed.")

            pending = self.pending_requests.get(project_id, {})
            if pending:
                # Feed user response to the paused workflow
                async for msg in self._resume_workflow(project_id, state, message, pending):
                    yield msg
            elif Intent.QUESTION in intents:
                # Answer the question first
                try:
                    follow_up = await asyncio.wait_for(llm.ainvoke([
                        {"role": "system", "content": "You are a project manager. The solution is being built. Answer briefly."},
                        {"role": "user", "content": f"Context: {state.to_context_string()}\n\nUser asks: {message}"},
                    ]), timeout=30)
                    follow_up_text = follow_up.content
                except asyncio.TimeoutError:
                    follow_up_text = "I'm still working on it. Please hold on."
                yield self._msg(project_id, follow_up_text)
                # Process secondary intents (e.g., iteration alongside question)
                secondary = [i for i in intents if i != Intent.QUESTION]
                if secondary:
                    target_agent, cleaned = self._parse_agent_mention(message)
                    state.queued_messages.append({
                        "message": cleaned if target_agent else message,
                        "intents": [i.value for i in secondary],
                        "meta": {"agents_to_rerun": self._retry_agents_for(target_agent)} if target_agent else meta,
                    })
                    yield self._msg(project_id, "📝 Noted — I'll also apply your feedback after the current step finishes.")
            else:
                # Queue the message for processing after current step
                target_agent, cleaned = self._parse_agent_mention(message)
                state.queued_messages.append({
                    "message": cleaned if target_agent else message,
                    "intents": [intent.value],
                    "meta": {"agents_to_rerun": self._retry_agents_for(target_agent)} if target_agent else meta,
                })
                if target_agent:
                    yield self._msg(project_id, f"📝 Noted for {target_agent} — will apply after current step.")
                else:
                    yield self._msg(project_id, "📝 Noted — I'll apply that after the current step finishes.")

        # ── Phase: done ─────────────────────────────────────────────
        elif phase == "done":
            # Detect and apply numeric assumption corrections post-pipeline
            updated_fields = self._detect_assumption_updates(message, state)
            if updated_fields:
                # Determine affected agents and trigger re-run
                agents_affected: set[str] = set()
                for field in updated_fields:
                    agents_affected.update(
                        _ASSUMPTION_AGENT_IMPACT.get(field, ["cost", "business_value", "roi", "presentation"])
                    )

                rerun_set = agents_affected & set(self._PIPELINE_ORDER)
                with state._lock:
                    state.completed_steps = [s for s in state.completed_steps if s not in rerun_set]
                    state.failed_steps = [s for s in state.failed_steps if s not in rerun_set]
                    state.skipped_steps = [s for s in state.skipped_steps if s not in rerun_set]
                    for agent_name in rerun_set:
                        if agent_name == "cost" and "phase" in state.costs:
                            del state.costs["phase"]
                        if agent_name == "business_value" and "phase" in state.business_value:
                            del state.business_value["phase"]
                        field_key = _AGENT_STATE_FIELDS.get(agent_name)
                        if field_key:
                            if field_key == "presentation_path":
                                state.presentation_path = ""
                            else:
                                setattr(state, field_key, {})

                ordered = [a for a in self._PIPELINE_ORDER if a in rerun_set]
                names = [AGENT_INFO.get(a, {"name": a})["name"] for a in ordered]
                yield self._msg(project_id, f"📊 Updated assumptions: {', '.join(updated_fields)}. "
                                f"Re-running {', '.join(names)}...")
                state.clarifications += f"\nAssumption update: {message}"
                self.phases[project_id] = "executing"
                async for msg in self._run_workflow(project_id, state, ordered):
                    yield msg
                return

            # Undo / revert to previous checkpoint
            if message.strip().lower() in ("undo", "revert", "go back"):
                if self._store and hasattr(self._store, "list_checkpoints"):
                    try:
                        checkpoints = await self._store.list_checkpoints(project_id)
                    except Exception:
                        checkpoints = []
                    if len(checkpoints) >= 2:
                        prev = checkpoints[1]  # [0] is current, [1] is previous
                        try:
                            restored = await self._store.restore_checkpoint(project_id, prev["id"])
                        except Exception:
                            restored = None
                        if restored:
                            self.states[project_id] = restored
                            yield self._msg(project_id, f"⏪ Reverted to before **{prev['stepName']}** step.")
                            return
                yield self._msg(project_id, "No checkpoints available to revert to.")
                return

            # AC-4: Detect granular retry commands ("retry cost", "retry roi", etc.)
            retry_target = self._parse_retry_command(message)
            if retry_target:
                # Determine which agents to re-run (target + downstream)
                agents_to_rerun = self._retry_agents_for(retry_target)
                state.clarifications += f"\nRetry: {message}"

                # Capture before snapshot for iteration tracking
                self._record_iteration_before(state, agents_to_rerun, message)

                rerun_set = set(agents_to_rerun)
                with state._lock:
                    state.completed_steps = [s for s in state.completed_steps if s not in rerun_set]
                    state.failed_steps = [s for s in state.failed_steps if s not in rerun_set]
                    state.skipped_steps = [s for s in state.skipped_steps if s not in rerun_set]

                    AGENT_STATE_FIELDS = _AGENT_STATE_FIELDS
                    for agent_name in agents_to_rerun:
                        # Clear stale phase markers
                        if agent_name == "cost" and "phase" in state.costs:
                            del state.costs["phase"]
                        if agent_name == "business_value" and "phase" in state.business_value:
                            del state.business_value["phase"]
                        # Reset output state — but preserve architecture when cost re-runs without architect
                        field = AGENT_STATE_FIELDS.get(agent_name)
                        if field:
                            if field == "presentation_path":
                                state.presentation_path = ""
                            elif field == "architecture" and "architect" not in rerun_set:
                                # Cost agent needs the existing architecture components — don't clear it
                                pass
                            else:
                                setattr(state, field, {})

                names = [AGENT_INFO.get(a, {"name": a})["name"] for a in agents_to_rerun]
                if not names:
                    yield self._msg(project_id, "No agents to retry.", {"type": "pm_response"})
                    return
                first_name = names[0]
                yield self._msg(
                    project_id,
                    f"Retrying {first_name} and downstream agents ({', '.join(names)})...",
                    {"type": "pm_response"},
                )
                self.phases[project_id] = "executing"
                async for msg in self._run_workflow(project_id, state, list(rerun_set)):
                    yield msg

                # Capture after snapshot and emit diff summary
                self._record_iteration_after(state)
                if state.iteration_history:
                    diff_summary = self._format_iteration_diff(state.iteration_history[-1])
                    yield self._msg(project_id, diff_summary, {"type": "iteration_diff"})

            elif Intent.ITERATION in intents:
                # Multi-intent: if PROCEED is also present, acknowledge approval first
                if Intent.PROCEED in intents:
                    yield self._msg(project_id, "✅ Current step approved. Now applying your iteration feedback...")
                agents_to_rerun = meta.get("agents_to_rerun") or pm.get_agents_to_rerun(message)
                state.clarifications += f"\nIteration: {message}"

                # Capture before snapshot for iteration tracking
                self._record_iteration_before(state, agents_to_rerun, message)

                rerun_set = set(agents_to_rerun)
                with state._lock:
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
                    AGENT_STATE_FIELDS = _AGENT_STATE_FIELDS
                    for agent_name in agents_to_rerun:
                        field = AGENT_STATE_FIELDS.get(agent_name)
                        if field:
                            if field == "presentation_path":
                                state.presentation_path = ""
                            elif field == "architecture" and "architect" not in rerun_set:
                                # Cost agent needs the existing architecture components — don't clear it
                                pass
                            else:
                                setattr(state, field, {})

                names = [AGENT_INFO.get(a, {"name": a})["name"] for a in agents_to_rerun]
                yield self._msg(project_id, f"Re-running {len(agents_to_rerun)} agents ({', '.join(names)}) with your feedback...")

                self.phases[project_id] = "executing"
                async for msg in self._run_workflow(project_id, state, list(rerun_set)):
                    yield msg

                # Capture after snapshot and emit diff summary
                self._record_iteration_after(state)
                if state.iteration_history:
                    diff_summary = self._format_iteration_diff(state.iteration_history[-1])
                    yield self._msg(project_id, diff_summary, {"type": "iteration_diff"})

            elif intent == Intent.BRAINSTORM:
                self._cleanup_project(project_id)
                self.phases[project_id] = "new"
                state.mode = "brainstorm"
                with state._lock:
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

      except Exception:
        logger.exception("Unhandled error in handle_message for project %s", project_id)
        yield self._msg(project_id, "⚠️ An unexpected error occurred. Please try again.")

    # ── Shared assumption generation ───────────────────────────────

    async def _generate_shared_assumptions(self, state: AgentState) -> list[dict]:
        """Generate overarching scenario assumptions that all agents share.

        When a company profile is available, pre-fills defaults from it.
        Keeps it lean — only the essentials that ALL agents need for consistency.
        Technical details (data volume, timeline, requests/day) belong in agent-specific questions.
        """
        industry = state.brainstorming.get("industry", "Cross-Industry")
        description = state.user_input

        # Pre-compute profile-derived defaults if company profile is available
        profile_defaults: dict = {}
        profile_hints: dict = {}
        if state.company_profile:
            from services.company_intelligence import (
                estimate_labor_rate, scope_employees,
            )
            p = state.company_profile
            company_name = p.get("name", "the company")
            total_employees = p.get("employeeCount")
            annual_revenue = p.get("annualRevenue")
            it_spend = p.get("itSpendEstimate")
            hq = p.get("headquarters", "")
            profile_industry = p.get("industry", industry)

            # Affected employees: scoped by use case
            if total_employees:
                scoped = scope_employees(total_employees, description)
                profile_defaults["affected_employees"] = scoped
                ratio = round(scoped / total_employees * 100) if total_employees else 0
                profile_hints["affected_employees"] = (
                    f"Scoped from {total_employees:,} total employees ({ratio}%)"
                )

            # Current annual spend: use IT spend estimate
            if it_spend:
                profile_defaults["current_annual_spend"] = it_spend
                profile_hints["current_annual_spend"] = "From estimated IT spend"

            # Hourly labor rate: derived from HQ + industry
            labor_rate = estimate_labor_rate(hq, profile_industry)
            if labor_rate:
                profile_defaults["hourly_labor_rate"] = labor_rate
                profile_hints["hourly_labor_rate"] = (
                    f"Estimated for {hq}, {profile_industry}" if hq
                    else f"Estimated for {profile_industry}"
                )

            # Total users: same as employee count (platform scale)
            if total_employees:
                profile_defaults["concurrent_users"] = max(100, int(total_employees * 0.05))
                profile_hints["concurrent_users"] = f"5% of {total_employees:,} employees"

            # Monthly revenue: derived from annual revenue
            if annual_revenue:
                profile_defaults["monthly_revenue"] = round(annual_revenue / 12, 2)
                profile_hints["monthly_revenue"] = f"From ${annual_revenue:,.0f}/yr annual revenue"

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
                assumptions = assumptions[:5]
            else:
                raise ValueError(f"Too few assumptions returned: expected at least 3, got {len(assumptions) if isinstance(assumptions, list) else 0}")
        except Exception as e:
            logger.warning("Failed to generate shared assumptions: %s", e)
            # Fallback defaults — lean and essential
            assumptions = [
                {"id": "affected_employees", "label": "Employees directly affected by the solution", "unit": "count", "default": 50, "hint": "Drives labor savings and change-management scope"},
                {"id": "current_annual_spend", "label": "Current annual spend on equivalent tools/processes", "unit": "$", "default": 500000, "hint": "Baseline for ROI and value calculation"},
                {"id": "hourly_labor_rate", "label": "Fully loaded hourly rate for affected staff", "unit": "$/hr", "default": 85, "hint": "Used to monetize time savings"},
                {"id": "concurrent_users", "label": "Peak concurrent users on the platform", "unit": "count", "default": 100, "hint": "Determines compute tier and scaling"},
            ]

        # Overlay profile-derived defaults and per-field source hints
        if profile_defaults:
            # Add monthly_revenue assumption if profile provides it
            if "monthly_revenue" in profile_defaults:
                has_revenue = any(a.get("id") == "monthly_revenue" for a in assumptions)
                if not has_revenue:
                    assumptions.append({
                        "id": "monthly_revenue",
                        "label": "Estimated monthly revenue",
                        "unit": "$",
                        "default": profile_defaults["monthly_revenue"],
                        "hint": "Used for revenue-impact and ROI calculations",
                        "source": profile_hints.get("monthly_revenue", ""),
                    })

            id_map = {
                "affected_employees": profile_defaults.get("affected_employees"),
                "current_annual_spend": profile_defaults.get("current_annual_spend"),
                "hourly_labor_rate": profile_defaults.get("hourly_labor_rate"),
                "concurrent_users": profile_defaults.get("concurrent_users"),
            }
            for assumption in assumptions:
                aid = assumption.get("id", "")
                if aid in id_map and id_map[aid] is not None:
                    assumption["default"] = id_map[aid]
                    if aid in profile_hints:
                        assumption["source"] = profile_hints[aid]

        return assumptions

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

    def _parse_agent_mention(self, message: str) -> tuple[str | None, str]:
        """Extract @agent mention and return (agent_name, cleaned_message)."""
        match = _AGENT_MENTION_RE.search(message)
        if not match:
            return None, message
        agent = match.group(1).lower().replace(" ", "_")
        if agent == "bv":
            agent = "business_value"
        cleaned = message[:match.start()] + message[match.end():]
        return agent, cleaned.strip()

    async def _handle_conversation(
        self, project_id: str, state: AgentState, message: str,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Handle a message in conversational mode — route to the specified agent."""
        agent_name = state.conversation_agent

        context = state.to_context_string()
        agent_context = {
            "architect": "You are an Azure solution architect. Help the user refine the architecture.",
            "cost": "You are an Azure cost specialist. Help the user understand and optimize costs.",
            "business_value": "You are a business value consultant. Help the user understand value drivers.",
            "roi": "You are an ROI analyst. Help the user understand the return on investment.",
            "presentation": "You are a presentation specialist. Help the user refine the slide deck.",
        }

        system_prompt = agent_context.get(agent_name, f"You are the {agent_name} specialist.")

        try:
            response = await asyncio.wait_for(llm.ainvoke([
                {"role": "system", "content": f"{system_prompt}\n\nProject context:\n{context}"},
                {"role": "user", "content": message},
            ]), timeout=60)
            reply = response.content
        except asyncio.TimeoutError:
            reply = "I'm having trouble processing that right now. Could you try again?"

        state.conversation_turns += 1

        yield self._msg(project_id, reply, metadata={
            "type": "agent_conversation",
            "agent": agent_name,
            "turn": state.conversation_turns,
            "actions": [
                {"id": "done", "label": "✅ Done chatting", "variant": "primary"},
            ],
        }, agent_id=agent_name.replace("_", "-"))

    @staticmethod
    def _detect_assumption_updates(message: str, state: AgentState) -> list[str]:
        """Parse numeric corrections from user message and update shared_assumptions.

        Scans *message* for patterns like "actually 5000 users" or "changed to
        2TB" and patches ``state.shared_assumptions`` in-place.  Returns a list
        of updated field names (empty if nothing matched).
        """
        updated: list[str] = []
        for match in _NUMERIC_UPDATE_RE.finditer(message):
            value_str = match.group(1).replace(",", "")
            value = float(value_str)
            keyword = match.group(2).lower().rstrip("s")  # normalize plural

            sa_field = _ASSUMPTION_FIELD_MAP.get(keyword)
            if sa_field:
                if keyword == "tb":
                    value *= 1024  # TB → GB
                state.shared_assumptions[sa_field] = value
                updated.append(sa_field)
                logger.info("Updated assumption %s = %s from user message", sa_field, value)

        if updated:
            state.invalidate_sa_cache()
        return updated

    # ── Iteration tracking helpers ─────────────────────────────────

    def _capture_snapshot(self, state: AgentState, agents: list[str]) -> dict[str, Any]:
        """Capture a deep copy of agent output fields for the given agents."""
        snapshot: dict[str, Any] = {}
        for agent_name in agents:
            field_name = _AGENT_STATE_FIELDS.get(agent_name)
            if field_name and field_name != "presentation_path":
                val = getattr(state, field_name, {})
                if val:
                    snapshot[agent_name] = copy.deepcopy(val)
        return snapshot

    def _record_iteration_before(
        self, state: AgentState, agents: list[str], trigger: str,
    ) -> None:
        """Record a 'before' snapshot in iteration_history."""
        before_snapshot = self._capture_snapshot(state, agents)
        entry = {
            "iteration": len(state.iteration_history) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trigger": trigger,
            "agents_rerun": list(agents),
            "before": before_snapshot,
            "after": {},
        }
        state.iteration_history.append(entry)

    def _record_iteration_after(self, state: AgentState) -> None:
        """Fill in the 'after' snapshot for the most recent iteration entry."""
        if not state.iteration_history:
            return
        current = state.iteration_history[-1]
        if current.get("after"):
            return  # already filled
        current["after"] = self._capture_snapshot(state, current["agents_rerun"])

    def _format_iteration_diff(self, entry: dict) -> str:
        """Format a brief summary of what changed in this iteration."""
        parts = [f"**Iteration #{entry['iteration']}** — _{entry['trigger']}_\n"]

        for agent in entry["agents_rerun"]:
            before = entry["before"].get(agent, {})
            after = entry["after"].get(agent, {})

            if agent == "cost":
                before_total = before.get("estimate", {}).get("totalMonthlyCost", 0)
                after_total = after.get("estimate", {}).get("totalMonthlyCost", 0)
                if before_total and after_total:
                    diff = after_total - before_total
                    pct = (diff / before_total * 100) if before_total else 0
                    arrow = "📉" if diff < 0 else "📈"
                    parts.append(
                        f"- {arrow} **Cost**: ${before_total:,.0f} → ${after_total:,.0f}/mo ({pct:+.1f}%)"
                    )

            elif agent == "roi":
                before_roi = before.get("threeYearROI", 0)
                after_roi = after.get("threeYearROI", 0)
                if before_roi or after_roi:
                    parts.append(f"- **ROI**: {before_roi:.0f}% → {after_roi:.0f}%")

        if len(parts) == 1:
            parts.append("- Agents re-run: " + ", ".join(entry["agents_rerun"]))

        return "\n".join(parts)

    async def _drain_queue(self, project_id: str, state: AgentState) -> list[str]:
        """Process queued messages. Returns list of agents needing re-run."""
        if not state.queued_messages:
            return []

        queued = state.queued_messages.copy()
        state.queued_messages.clear()
        agents_to_rerun: set[str] = set()

        for item in queued:
            message = item["message"]
            state.clarifications += f"\nQueued feedback: {message}"
            if "iteration" in item.get("intents", []):
                agents = item.get("meta", {}).get("agents_to_rerun", [])
                for agent in agents:
                    if agent in state.completed_steps:
                        state.completed_steps.remove(agent)
                        agents_to_rerun.add(agent)

        return list(agents_to_rerun)

    async def _run_workflow(
        self, project_id: str, state: AgentState, active_agents: list[str],
    ) -> AsyncGenerator[ChatMessage, None]:
        """Start a new MAF workflow and stream events as ChatMessages."""
        # Inject recent chat history into state for agent context
        await self._inject_chat_history(project_id, state)

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

        # After the workflow finishes, re-run any agents flagged by
        # _drain_queue during execution (avoids recursive _run_workflow).
        drained = self._deferred_rerun.pop(project_id, None)
        if drained:
            rerun_list = list(drained)
            logger.info("Re-running deferred agents after workflow: %s", rerun_list)
            self.phases[project_id] = "executing"
            async for msg in self._run_workflow(project_id, state, rerun_list):
                yield msg

    _APPROVAL_KEYWORDS = frozenset({
        "proceed", "skip", "refine", "yes", "ok", "continue",
        "skip this", "next", "redo", "again", "retry",
    })

    @classmethod
    def _is_approval_keyword(cls, message: str) -> bool:
        """Check if message is a known approval action keyword."""
        return message.strip().lower() in cls._APPROVAL_KEYWORDS

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
        first_request_data = pending[first_req_id]

        # Suggestion routing: if user responds with free-text (not an approval
        # keyword) while an approval gate is active, treat it as refinement
        # feedback for the current agent and re-run it.
        if (
            isinstance(first_request_data, ApprovalRequest)
            and not self._is_approval_keyword(message)
        ):
            agent_step = first_request_data.step
            state.clarifications += f"\nRefinement for {agent_step}: {message}"
            # Translate free-text feedback into a "refine" action so the
            # workflow's response_handler records the feedback and re-sends
            # the pipeline message to re-run the same step.
            message = "refine"
            yield self._msg(
                project_id,
                f"Got it — refining **{AGENT_INFO.get(agent_step, {'name': agent_step})['name']}** with your feedback...",
                {"type": "pm_response"},
            )

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
            async with asyncio.timeout(PIPELINE_TIMEOUT_SECONDS):
                async for event in stream:
                    logger.info("WF event: type=%s executor=%s data_type=%s",
                                event.type, getattr(event, 'executor_id', '?'),
                                type(event.data).__name__)

                    if event.type == "output" and isinstance(event.data, dict):
                        data = event.data
                        etype = data.get("type", "")
                        step = data.get("step", "")

                        if etype == "agent_start":
                            # Save checkpoint before agent runs
                            await self._save_checkpoint(project_id, step)
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
                            agent_info = AGENT_INFO.get(step, {"name": step, "emoji": "🔧"})
                            label = f"{agent_info.get('emoji', '🔧')} {agent_info.get('name', step)} is working..."
                            yield ChatMessage(
                                project_id=project_id, role="agent", agent_id=agent_id,
                                content=label,
                                metadata={"type": "agent_start", "agent": agent_id, "step": step},
                            )

                        elif etype == "agent_result":
                            agent_id = step.replace("_", "-")
                            content = data.get("content", "")
                            metadata: dict = {"type": "agent_result", "agent": agent_id, "step": step}
                            if "dashboard" in data and data["dashboard"]:
                                metadata["type"] = "roi_dashboard"
                                metadata["dashboard"] = data["dashboard"]
                            if "presentation_path" in data and data["presentation_path"]:
                                metadata["type"] = "presentation_ready"
                                metadata["presentation_path"] = data["presentation_path"]
                            yield ChatMessage(
                                project_id=project_id, role="agent",
                                agent_id=agent_id, content=content, metadata=metadata,
                            )
                            # Drain queued messages after each agent completes.
                            # Store flagged agents — they are re-run AFTER the
                            # current workflow event loop finishes to avoid
                            # recursive _run_workflow() calls.
                            drained_agents = await self._drain_queue(project_id, self.get_state(project_id))
                            if drained_agents:
                                logger.info("Drain queue flagged agents for re-run: %s", drained_agents)
                                self._deferred_rerun.setdefault(project_id, set()).update(drained_agents)
                            # Persist state after each agent completes
                            await self._persist_state(project_id)

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
                            await self._persist_state(project_id)
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
                            step = event.data.step
                            yield ChatMessage(
                                project_id=project_id, role="agent", agent_id="pm",
                                content=f"{summary}\n\nSay **proceed** to continue, **skip** to skip, or provide feedback to refine. You can also say **chat with {step}** to discuss further.",
                                metadata={
                                    "type": "approval",
                                    "step": step,
                                    "actions": [
                                        {"id": "proceed", "label": "✅ Proceed", "variant": "primary"},
                                        {"id": "refine", "label": "✏️ Refine", "variant": "secondary"},
                                        {"id": "skip", "label": "⏭️ Skip", "variant": "ghost"},
                                    ],
                                },
                            )
                        elif isinstance(event.data, AssumptionsRequest):
                            # Already emitted via assumptions_input above
                            pass
        except asyncio.TimeoutError:
            logger.error(
                "Pipeline timeout exceeded (%d seconds) for project %s",
                PIPELINE_TIMEOUT_SECONDS, project_id,
            )
            self.phases[project_id] = "done"
            self._cleanup_project(project_id)
            yield ChatMessage(
                project_id=project_id, role="agent", agent_id="pm",
                content=f"⚠️ Pipeline timed out after {PIPELINE_TIMEOUT_SECONDS}s. Please try again or start fresh.",
                metadata={"type": "error"},
            )
        except Exception as e:
            logger.exception("Workflow execution failed for project %s", project_id)
            self.phases[project_id] = "done"
            self._cleanup_project(project_id)
            yield ChatMessage(
                project_id=project_id, role="agent", agent_id="pm",
                content=f"⚠️ An error occurred during execution: {str(e)}\n\nYou can try again or start fresh.",
                metadata={"type": "error"},
            )
