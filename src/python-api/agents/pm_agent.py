"""Project Manager — plans and orchestrates the agent pipeline."""
from enum import Enum
from agents.llm import llm
from agents.state import AgentState


class Intent(Enum):
    PROCEED = "proceed"
    REFINE = "refine"
    SKIP = "skip"
    FAST_RUN = "fast_run"
    BRAINSTORM = "brainstorm"
    ITERATION = "iteration"
    QUESTION = "question"
    INPUT = "input"


# ── Single source of truth for iteration keyword → agent mapping ────────
ITERATION_MAPPING: dict[str, list[str]] = {
    "cheaper": ["cost", "roi", "presentation"],
    "expensive": ["cost", "roi", "presentation"],
    "high availability": ["architect", "cost", "roi", "presentation"],
    "ha": ["architect", "cost", "roi", "presentation"],
    "region": ["cost", "presentation"],
    "compliance": ["architect", "cost"],
    "ai": ["business_value", "architect", "cost", "roi", "presentation"],
    "scale": ["cost", "roi"],
    "different approach": ["business_value", "architect", "cost", "roi", "presentation"],
    "value": ["business_value", "roi", "presentation"],
    "business": ["business_value", "roi", "presentation"],
}


class IntentInterpreter:
    """Classifies user messages into actionable intents via LLM.

    Uses an LLM call as the primary classifier for natural language understanding.
    The ITERATION_MAPPING dict is used only to resolve *which agents* to re-run
    once the LLM has identified an iteration intent — that routing is deterministic.
    """

    SYSTEM_PROMPT = (
        "You are an intent classifier for an Azure solution copilot. "
        "Classify the user's message into exactly ONE of these intents:\n\n"
        "- proceed: User wants to move forward (e.g. 'yes', 'ok', 'let's go', 'approved', 'continue')\n"
        "- refine: User wants to adjust the current step's output (e.g. 'change X', 'make it more detailed', 'tweak the architecture')\n"
        "- skip: User wants to skip the current step (e.g. 'skip', 'next', 'don't need this')\n"
        "- fast_run: User wants to run all remaining steps without pausing (e.g. 'run everything', 'fast mode', 'just build it')\n"
        "- brainstorm: User wants to start over or explore different ideas (e.g. 'different approach', 'start over', 'rethink')\n"
        "- iteration: User wants to change something about an already-completed solution "
        "(e.g. 'make it cheaper', 'add high availability', 'change region to Europe', 'add AI capabilities')\n"
        "- question: User is asking a question (e.g. 'why did you pick this?', 'what does this cost?', 'can you explain?')\n"
        "- input: User is providing new information or context that doesn't fit the above categories\n\n"
        "Return ONLY the intent word, nothing else."
    )

    def classify(self, message: str) -> tuple[Intent, dict]:
        """Classify a message into an intent using an LLM call. Returns (intent, metadata)."""
        try:
            response = llm.invoke([
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ])
            raw = response.content.strip().lower().replace("-", "_").replace(" ", "_")
            intent = Intent(raw)
        except (ValueError, Exception):
            # LLM returned something unparseable or call failed — safe default
            intent = Intent.INPUT

        # Build metadata based on resolved intent
        meta: dict = {}
        if intent == Intent.ITERATION:
            meta["feedback"] = message
            # Resolve which agents to re-run from the keyword mapping
            msg_lower = message.lower()
            for keyword, agents in ITERATION_MAPPING.items():
                if keyword in msg_lower:
                    meta["agents_to_rerun"] = agents
                    return intent, meta
            # LLM said iteration but no keyword match — re-run from architect onward
            meta["agents_to_rerun"] = [
                "architect", "cost",
                "business_value", "roi", "presentation",
            ]
        elif intent == Intent.REFINE:
            meta["feedback"] = message

        return intent, meta


AGENT_INFO = {
    "architect": {"name": "System Architect", "emoji": "\U0001f3d7\ufe0f"},
    "cost": {"name": "Cost & Services", "emoji": "\U0001f4b0"},
    "business_value": {"name": "Business Value", "emoji": "\U0001f4ca"},
    "roi": {"name": "ROI Calculator", "emoji": "\U0001f4c8"},
    "presentation": {"name": "Presentation", "emoji": "\U0001f4d1"},
}

# Solutioning plan (Mode B only — brainstorming is Mode A, handled separately)
SOLUTIONING_PLAN = [
    "business_value",
    "architect",
    "cost",
    "roi",
    "presentation",
]

# Maps internal plan step IDs to frontend agent toggle IDs
PLAN_TO_ACTIVE = {
    "architect": "architect",
    "cost": "cost",
    "business_value": "business-value",
    "roi": "roi",
    "presentation": "presentation",
}


class ProjectManager:
    def __init__(self):
        self.intent_interpreter = IntentInterpreter()

    def brainstorm_greeting(self, user_input: str) -> dict:
        """Brainstorm + classify Azure fit in one LLM call.

        Returns a dict with:
          - response: str  (conversational markdown for the user)
          - azure_fit: str  ("strong", "weak", or "unclear")
          - azure_fit_explanation: str
          - industry: str
          - scenarios: list[dict]  (structured scenario data)
        """
        response = llm.invoke([
            {"role": "system", "content": """You are an Azure solution project manager acting as a brainstorming partner.
The user described a project idea. Respond with ONLY a JSON object (no markdown fences):

{
    "response": "Your conversational markdown response here (acknowledge the idea, suggest 2-3 Azure scenarios with WHY Azure fits, ask 2-3 clarifying questions, end with: When you're ready, say **proceed** to start building the solution, or keep chatting to refine the idea.)",
    "azure_fit": "strong" or "weak" or "unclear",
    "azure_fit_explanation": "1-2 sentences on WHY Azure is or isn't a good fit",
    "industry": "Retail, Healthcare, Financial Services, Manufacturing, or Cross-Industry",
    "scenarios": [
        {
            "title": "Scenario name",
            "description": "2-3 sentences",
            "azure_services": ["Azure App Service", "..."]
        }
    ]
}

RULES:
- "strong" = clear workload mapping to Azure services
- "weak" = generic IT need without clear Azure advantage
- "unclear" = not enough information
- The response field should be enthusiastic, conversational markdown
- Do NOT mention agent names or execution plans in the response
- Be specific about Azure services, not generic cloud"""},
            {"role": "user", "content": user_input}
        ])

        import json
        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(text)
            return {
                "response": result.get("response", text),
                "azure_fit": result.get("azure_fit", "unclear"),
                "azure_fit_explanation": result.get("azure_fit_explanation", ""),
                "industry": result.get("industry", "Cross-Industry"),
                "scenarios": result.get("scenarios", []),
            }
        except (json.JSONDecodeError, Exception):
            # LLM returned plain text instead of JSON — still usable
            return {
                "response": response.content,
                "azure_fit": "unclear",
                "azure_fit_explanation": "Could not assess Azure fit from the response.",
                "industry": "Cross-Industry",
                "scenarios": [],
            }

    def build_plan(self, active_agents: list[str]) -> list[str]:
        """Build solutioning execution plan respecting agent toggles. Architect is always included."""
        plan = []
        for agent_id in SOLUTIONING_PLAN:
            mapped = PLAN_TO_ACTIVE.get(agent_id, agent_id)
            if mapped in active_agents or agent_id == "architect":
                plan.append(agent_id)
        return plan

    def format_plan(self, state: AgentState) -> str:
        """Format the execution plan as a checkbox list reflecting current step states."""
        lines = ["## \U0001f4cb Execution Plan\n"]
        for step in state.plan_steps:
            info = AGENT_INFO.get(step, {"name": step, "emoji": "\U0001f527"})
            if step in state.completed_steps:
                lines.append(f"- [x] {info['emoji']} **{info['name']}**")
            elif step in state.skipped_steps:
                lines.append(f"- [-] {info['emoji']} ~~{info['name']}~~ *(skipped)*")
            elif step in state.failed_steps:
                lines.append(f"- [!] {info['emoji']} **{info['name']}** *(failed)*")
            elif step == state.current_step:
                lines.append(f"- [ ] {info['emoji']} **{info['name']}** ⏳")
            else:
                lines.append(f"- [ ] {info['emoji']} {info['name']}")
        return "\n".join(lines)

    def approval_summary(self, step: str, state: AgentState) -> str:
        """Generate a summary of agent output + key insight + approval prompt."""
        info = AGENT_INFO.get(step, {"name": step, "emoji": "\U0001f527"})

        summary = ""
        insight = ""

        if step == "architect":
            comps = state.architecture.get("components", [])
            summary = f"Designed architecture with {len(comps)} Azure components."
            based_on = state.architecture.get("basedOn", "custom design")
            insight = f"Based on: **{based_on}**"

        elif step == "cost":
            est = state.costs.get("estimate", {})
            monthly = est.get("totalMonthly", 0)
            source = est.get("pricingSource", "unknown")
            sels = state.services.get("selections", [])
            summary = f"Mapped {len(sels)} Azure services and estimated monthly cost: **${monthly:,.2f}** (source: {source})."
            insight = f"Annual projection: **${est.get('totalAnnual', 0):,.2f}**"

        elif step == "business_value":
            drivers = state.business_value.get("drivers", [])
            confidence = state.business_value.get("confidenceLevel", "moderate")
            summary = f"Identified {len(drivers)} value drivers ({confidence} confidence)."
            if drivers:
                insight = f"Top driver: **{drivers[0].get('name', '')}**"

        elif step == "roi":
            roi_pct = state.roi.get("roi_percent")
            payback = state.roi.get("payback_months")
            needs_info = state.roi.get("needs_info")
            if roi_pct is not None:
                summary = f"ROI calculated: **{roi_pct:.0f}%** with {payback:.1f} month payback."
                if needs_info:
                    summary += "\n\nSome drivers couldn't be monetized yet. To refine the ROI, I'd need:"
                    for q in needs_info:
                        summary += f"\n- {q}"
            elif needs_info:
                summary = "I need a bit more information to calculate ROI:\n"
                for q in needs_info:
                    summary += f"\n- {q}"
                summary += "\n\nShare what you can and I'll re-run the numbers."
            else:
                summary = "ROI could not be calculated quantitatively — see qualitative benefits."
            insight = ""

        elif step == "presentation":
            summary = "PowerPoint deck generated and ready for download."
            insight = ""

        parts = [
            f"{info['emoji']} **{info['name']}** completed.",
            "",
            summary,
        ]
        if insight:
            parts.append(f"\U0001f4a1 {insight}")
        parts.append("")
        parts.append("Say **proceed** to continue, **refine** to adjust, or **skip** to move on.")

        return "\n".join(parts)

    def extract_customer_name(self, state: AgentState) -> str:
        """Extract customer name from state. Falls back to LLM extraction from conversation."""
        if state.customer_name:
            return state.customer_name
        # Try to extract from user input + clarifications
        context = f"{state.user_input}\n{state.clarifications}".strip()
        if not context:
            return ""
        try:
            response = llm.invoke([
                {"role": "system", "content": (
                    "Extract the customer or company name from this conversation. "
                    "Return ONLY the name, nothing else. If no name is mentioned, return 'N/A'."
                )},
                {"role": "user", "content": context}
            ])
            name = response.content.strip()
            if name and name != "N/A":
                state.customer_name = name
                return name
        except Exception:
            pass
        return ""

    def get_agents_to_rerun(self, user_message: str) -> list[str]:
        """Determine which agents need to re-run based on user's iteration request."""
        msg = user_message.lower()
        for keyword, agents in ITERATION_MAPPING.items():
            if keyword in msg:
                return agents
        # Default: re-run from business_value onward
        return ["business_value", "architect", "cost", "roi", "presentation"]

    def format_agent_output(self, step: str, state: AgentState) -> str:
        """Format an agent's output as markdown for the chat."""
        if step == "architect":
            arch = state.architecture
            parts = [f"## \U0001f3d7\ufe0f Architecture Design\n\n{arch.get('narrative', '')}\n"]
            mermaid = arch.get("mermaidCode", "")
            if mermaid:
                parts.append(f"```mermaid\n{mermaid}\n```\n")
            comps = arch.get("components", [])
            if comps:
                parts.append("### Components\n")
                for c in comps[:15]:
                    parts.append(
                        f"- **{c.get('name', '')}** ({c.get('azureService', '')}) "
                        f"\u2014 {c.get('description', '')}"
                    )
            return "\n".join(parts)

        if step == "cost":
            sels = state.services.get("selections", [])
            sels = state.services.get("selections", [])
            est = state.costs.get("estimate", {})
            monthly = est.get("totalMonthly", 0)
            annual = est.get("totalAnnual", 0)
            source = est.get("pricingSource", "unknown")
            parts = [
                f"## \U0001f4b0 Azure Services & Cost Estimate\n",
                f"### \u2601\ufe0f Services ({len(sels)} mapped)\n",
            ]
            for s in sels[:15]:
                parts.append(
                    f"- **{s.get('componentName', '')}** \u2192 "
                    f"{s.get('serviceName', '')} ({s.get('sku', '')}) "
                    f"in {s.get('region', 'eastus')}"
                )
            parts.append(
                f"\n### \U0001f4b0 Cost Estimate\n\n"
                f"**Total: ${monthly:,.2f}/month (${annual:,.2f}/year)** \u2014 Source: {source}\n"
            )
            parts.append("| Service | SKU | Monthly Cost |")
            parts.append("|---------|-----|-------------|")
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
                f"## \U0001f4ca Business Value Assessment\n\n{summary}\n\n"
                f"**Confidence:** {confidence}\n"
            ]
            if drivers:
                parts.append("### Value Drivers\n")
                for d in drivers:
                    est_text = ""
                    q = d.get("estimate")
                    if q:
                        est_text = f" \u2014 *{q}*"
                    annual_val = d.get("annual_value_estimate")
                    icon = "\U0001f4b0" if annual_val else "\U0001f4cb"
                    line = f"- {icon} **{d.get('name', '')}**: {d.get('description', '')}{est_text}"
                    if annual_val:
                        line += f" (~${annual_val:,.0f}/yr)"
                    info = d.get("info_needed")
                    if info:
                        line += f"\n  *To refine: {info}*"
                    parts.append(line)
            # Add source references from retrieved patterns
            patterns = state.retrieved_patterns
            if patterns:
                parts.append("\n### \U0001f4da Sources & References\n")
                for p in patterns[:3]:
                    url = p.get("url", "")
                    title = p.get("title", "Microsoft Learn")
                    if url:
                        parts.append(f"- [{title}]({url})")
                    else:
                        parts.append(f"- {title}")
                parts.append("\n*Value estimates based on Microsoft case studies and industry benchmarks.*")
            else:
                parts.append("\n*\u26a0\ufe0f Value estimates based on LLM knowledge \u2014 not grounded in live sources.*")
            return "\n".join(parts)

        if step == "roi":
            roi = state.roi
            needs_info = roi.get("needs_info")
            if roi.get("roi_percent") is not None:
                parts = ["## \U0001f4c8 ROI Analysis\n"]
                parts.append(f"**ROI: {roi['roi_percent']:.0f}%** | Payback: **{roi.get('payback_months', 'N/A'):.1f} months**\n")
                parts.append(f"- Annual Azure cost: ${roi['annual_cost']:,.2f}")
                parts.append(f"- Annual value generated: ${roi['annual_value']:,.2f}\n")
                if roi.get("monetized_drivers"):
                    parts.append("### Monetized Value Drivers\n")
                    for d in roi["monetized_drivers"]:
                        parts.append(f"- **{d['name']}**: ${d['annual_value']:,.2f}/year")
                if roi.get("qualitative_benefits"):
                    parts.append("\n### Qualitative Benefits\n")
                    for b in roi["qualitative_benefits"]:
                        parts.append(f"- {b}")
                if needs_info:
                    parts.append("\n### \u2139\ufe0f To refine this estimate\n")
                    for q in needs_info:
                        parts.append(f"- {q}")
            elif needs_info:
                parts = ["## \U0001f4c8 ROI Analysis\n"]
                parts.append("I need more information to calculate ROI:\n")
                for q in needs_info:
                    parts.append(f"- {q}")
                parts.append("\nShare what you can and say **refine** to re-run.")
                if roi.get("qualitative_benefits"):
                    parts.append("\n### Qualitative Benefits (in the meantime)\n")
                    for b in roi["qualitative_benefits"]:
                        parts.append(f"- {b}")
            else:
                parts = ["## \U0001f4c8 ROI Analysis\n", "ROI could not be calculated quantitatively.\n"]
                if roi.get("qualitative_benefits"):
                    parts.append("### Qualitative Benefits\n")
                    for b in roi["qualitative_benefits"]:
                        parts.append(f"- {b}")
            return "\n".join(parts)

        if step == "presentation":
            path = state.presentation_path
            if path:
                return "## \U0001f4d1 Presentation Ready\n\nPowerPoint deck generated.\n\n\U0001f4e5 Ready for download."
            return "## \U0001f4d1 Presentation\n\n\u26a0\ufe0f Deck generation failed."

        return f"{step} completed."