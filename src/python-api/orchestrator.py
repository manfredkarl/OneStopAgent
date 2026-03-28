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
from typing import AsyncGenerator

from agents.state import AgentState
from agents.pm_agent import ProjectManager, AGENT_INFO, Intent
from agents.architect_agent import ArchitectAgent
from agents.azure_specialist_agent import AzureSpecialistAgent
from agents.cost_agent import CostAgent
from agents.business_value_agent import BusinessValueAgent
from agents.presentation_agent import PresentationAgent
from agents.brainstorming_agent import BrainstormingAgent
from agents.knowledge_agent import KnowledgeAgent
from agents.roi_agent import ROIAgent
from agents.llm import llm
from models.schemas import ChatMessage

# ── Agent registry (keyed by plan-step ID) ──────────────────────────────
AGENTS: dict[str, object] = {
    "brainstorm": BrainstormingAgent(),
    "knowledge": KnowledgeAgent(),
    "architect": ArchitectAgent(),
    "azure_services": AzureSpecialistAgent(),
    "cost": CostAgent(),
    "business_value": BusinessValueAgent(),
    "roi": ROIAgent(),
    "presentation": PresentationAgent(),
}

pm = ProjectManager()


# ── Output formatters ───────────────────────────────────────────────────

def format_agent_output(step: str, state: AgentState) -> str:
    """Format an agent's output as markdown for the chat."""
    if step == "brainstorm":
        bs = state.brainstorming
        fit = state.azure_fit
        explanation = state.azure_fit_explanation
        scenarios = bs.get("scenarios", [])
        industry = bs.get("industry", "N/A")

        parts = [f"## 💡 Azure Opportunity Analysis\n"]
        parts.append(f"**Industry:** {industry}")
        parts.append(f"**Azure Fit:** {fit.upper()} — {explanation}\n")

        if scenarios:
            parts.append("### Suggested Scenarios\n")
            for i, s in enumerate(scenarios, 1):
                parts.append(f"**{i}. {s.get('title', '')}**")
                parts.append(f"{s.get('description', '')}")
                services = ", ".join(s.get("azure_services", []))
                if services:
                    parts.append(f"*Azure Services: {services}*")
                reason = s.get("azure_fit_reason", "")
                if reason:
                    parts.append(f"💡 {reason}")
                parts.append("")

        return "\n".join(parts)

    if step == "knowledge":
        patterns = state.retrieved_patterns
        ungrounded = any(p.get("_ungrounded") for p in patterns)

        parts = [f"## 📚 Microsoft Reference Architectures ({len(patterns)} found)\n"]
        if ungrounded:
            parts.append("⚠️ *Based on local reference data (Microsoft Learn not available)*\n")

        for p in patterns[:5]:
            score = p.get("confidence_score", 0)
            parts.append(f"**{p.get('title', 'Untitled')}** (relevance: {score:.0%})")
            parts.append(f"{p.get('summary', '')}")
            url = p.get("url", "")
            if url:
                parts.append(f"[View on Microsoft Learn]({url})")
            services = ", ".join(p.get("recommended_services", []))
            if services:
                parts.append(f"*Services: {services}*")
            parts.append("")

        return "\n".join(parts)

    if step == "architect":
        arch = state.architecture
        parts = [f"## 🏗️ Architecture Design\n\n{arch.get('narrative', '')}\n"]
        mermaid = arch.get("mermaidCode", "")
        if mermaid:
            parts.append(f"```mermaid\n{mermaid}\n```\n")
        comps = arch.get("components", [])
        if comps:
            parts.append("### Components\n")
            for c in comps[:15]:
                parts.append(
                    f"- **{c.get('name', '')}** ({c.get('azureService', '')}) "
                    f"— {c.get('description', '')}"
                )
        return "\n".join(parts)

    if step == "azure_services":
        sels = state.services.get("selections", [])
        parts = [f"## ☁️ Azure Services ({len(sels)} mapped)\n"]
        for s in sels[:15]:
            parts.append(
                f"- **{s.get('componentName', '')}** → "
                f"{s.get('serviceName', '')} ({s.get('sku', '')}) "
                f"in {s.get('region', 'eastus')}"
            )
        return "\n".join(parts)

    if step == "cost":
        est = state.costs.get("estimate", {})
        monthly = est.get("totalMonthly", 0)
        annual = est.get("totalAnnual", 0)
        source = est.get("pricingSource", "unknown")
        parts = [
            f"## 💰 Cost Estimate\n\n"
            f"**Total: ${monthly:,.2f}/month (${annual:,.2f}/year)** — Source: {source}\n",
            "| Service | SKU | Monthly Cost |",
            "|---------|-----|-------------|",
        ]
        for item in est.get("items", [])[:20]:
            parts.append(
                f"| {item.get('serviceName', '')} | {item.get('sku', '')} "
                f"| ${item.get('monthlyCost', 0):,.2f} |"
            )
        if est.get("assumptions"):
            parts.append(f"\n*Assumptions: {', '.join(est['assumptions'][:5])}*")
        return "\n".join(parts)

    if step == "business_value":
        bv = state.business_value
        summary = bv.get("executiveSummary", "")
        drivers = bv.get("drivers", [])
        confidence = bv.get("confidenceLevel", "moderate")
        parts = [
            f"## 📊 Business Value Assessment\n\n{summary}\n\n"
            f"**Confidence:** {confidence}\n"
        ]
        if drivers:
            parts.append("### Value Drivers\n")
            for d in drivers:
                est_text = ""
                q = d.get("quantifiedEstimate") or d.get("estimate")
                if q:
                    est_text = f" — *{q}*"
                parts.append(
                    f"- **{d.get('name', '')}**: "
                    f"{d.get('impact', d.get('description', ''))}{est_text}"
                )
        return "\n".join(parts)

    if step == "roi":
        roi = state.roi
        if roi.get("roi_percent") is not None:
            parts = [f"## 📈 ROI Analysis\n"]
            parts.append(f"**ROI: {roi['roi_percent']:.0f}%** | Payback: **{roi.get('payback_months', 'N/A'):.1f} months**\n")
            parts.append(f"- Annual Azure cost: ${roi['annual_cost']:,.2f}")
            parts.append(f"- Annual value generated: ${roi['annual_value']:,.2f}\n")
            if roi.get("monetized_drivers"):
                parts.append("### Monetized Value Drivers\n")
                for d in roi["monetized_drivers"]:
                    parts.append(f"- **{d['name']}**: ${d['annual_value']:,.2f}/year ({d['method']})")
            if roi.get("qualitative_benefits"):
                parts.append(f"\n### Qualitative Benefits\n")
                for b in roi["qualitative_benefits"]:
                    parts.append(f"- {b}")
        else:
            parts = ["## 📈 ROI Analysis\n", "ROI could not be calculated quantitatively.\n"]
            if roi.get("qualitative_benefits"):
                parts.append("### Qualitative Benefits\n")
                for b in roi["qualitative_benefits"]:
                    parts.append(f"- {b}")
        return "\n".join(parts)

    if step == "presentation":
        path = state.presentation_path
        if path:
            return "## 📑 Presentation Ready\n\nPowerPoint deck generated.\n\n📥 Ready for download."
        return "## 📑 Presentation\n\n⚠️ Deck generation failed."

    return f"{step} completed."


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
    FAST_RUN_GATES = {"brainstorm", "architect", "presentation"}

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
        intent, meta = pm.intent_interpreter.classify_with_llm_fallback(message)

        # ── Phase: new ──────────────────────────────────────────────
        if phase == "new":
            state.user_input = message
            state.mode = "brainstorm"

            clarification = await asyncio.get_event_loop().run_in_executor(
                None, pm.ask_clarifications, message,
            )

            plan = pm.build_plan(active_agents)
            state.plan_steps = plan
            plan_text = pm.format_plan(plan)

            self.phases[project_id] = "plan_shown"
            yield self._msg(
                project_id,
                f"{clarification}\n\n{plan_text}",
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
                # Answer the question but stay in approval
                answer = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: llm.invoke([
                        {
                            "role": "system",
                            "content": (
                                "You are an Azure solution project manager. "
                                "Answer the user's question about the current "
                                "step. Be brief."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Context: {state.to_context_string()}\n\n"
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

            else:
                # Refine / unrecognised input → re-run step with feedback
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

        # Run agent in thread pool (agents use synchronous LLM calls)
        loop = asyncio.get_event_loop()
        try:
            state = await loop.run_in_executor(None, agent.run, state)
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
            formatted = format_agent_output(step, state)
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id=step,
                content=formatted,
                metadata={"type": "agent_result", "agent": step},
            )

            # Azure fit gate (FRD-02 §2.5): weak/unclear pauses for more detail
            if step == "brainstorm" and state.azure_fit and state.azure_fit != "strong":
                yield self._msg(
                    project_id,
                    f"Azure fit is **{state.azure_fit}**. "
                    f"{state.azure_fit_explanation}\n\n"
                    "Could you provide more details about your use case "
                    "so I can better assess the Azure opportunity? "
                    "Or say **proceed** to continue anyway.",
                    {"type": "approval", "step": step},
                )
                state.awaiting_approval = True
                state.current_step = step
                self.phases[project_id] = "approval"
                return

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
