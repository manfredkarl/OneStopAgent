"""Project Manager — plans and orchestrates the agent pipeline."""
import json
import re
from enum import Enum
from agents.llm import llm
from agents.state import AgentState


def _extract_response_field_partial(partial_json: str) -> str:
    """Extract the partial value of the 'response' key from a streaming JSON string.

    Handles both incomplete (streaming) and complete JSON.
    Returns the extracted text, or "" if the key hasn't appeared yet.
    """
    match = re.search(r'"response"\s*:\s*"((?:[^"\\]|\\.)*)', partial_json)
    return match.group(1) if match else ""


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

    # Default agents to re-run when iteration intent has no keyword match
    DEFAULT_RERUN_AGENTS: list[str] = [
        "architect", "cost", "business_value", "roi", "presentation",
    ]

    def _build_meta(self, intent: Intent, message: str) -> dict:
        """Build the metadata dict for a resolved intent."""
        meta: dict = {}
        if intent == Intent.ITERATION:
            meta["feedback"] = message
            msg_lower = message.lower()
            for keyword, agents in ITERATION_MAPPING.items():
                if keyword in msg_lower:
                    meta["agents_to_rerun"] = agents
                    return meta
            meta["agents_to_rerun"] = list(self.DEFAULT_RERUN_AGENTS)
        elif intent == Intent.REFINE:
            meta["feedback"] = message
        return meta

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

        return intent, self._build_meta(intent, message)

    async def aclassify(self, message: str) -> tuple[Intent, dict]:
        """Async version of :meth:`classify` — uses ``ainvoke`` to avoid
        blocking the event loop.  Drop-in replacement for async contexts."""
        try:
            response = await llm.ainvoke([
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ])
            raw = response.content.strip().lower().replace("-", "_").replace(" ", "_")
            intent = Intent(raw)
        except (ValueError, Exception):
            intent = Intent.INPUT

        return intent, self._build_meta(intent, message)


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
            {"role": "system", "content": """You are an Azure solution project manager. Be CONCISE.
The user described a project idea. Respond with ONLY a JSON object (no markdown fences):

{
    "response": "Brief markdown response: 1 sentence acknowledgment, 2-3 short Azure scenario bullets (service names + why), 2-3 clarifying questions. Keep under 300 words. End with: Say **proceed** to start.",
    "azure_fit": "strong" or "weak" or "unclear",
    "azure_fit_explanation": "1 sentence WHY Azure fits or doesn't",
    "industry": "Retail, Healthcare, Financial Services, Manufacturing, or Cross-Industry",
    "scenarios": [
        {
            "title": "Short name",
            "description": "1 sentence",
            "azure_services": ["Service1", "Service2"]
        }
    ]
}

RULES:
- Keep the response field SHORT — no walls of text
- 2-3 scenarios max, 1 sentence each
- 2-3 questions max
- Be specific about Azure services"""},
            {"role": "user", "content": user_input}
        ])

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(text)

            # Safety: the LLM may put the entire JSON blob as the response
            # field value — extract the conversational text if so
            resp = result.get("response", text)
            if isinstance(resp, str) and resp.strip().startswith("{"):
                try:
                    inner = json.loads(resp)
                    if isinstance(inner, dict) and "response" in inner:
                        result["response"] = inner["response"]
                except json.JSONDecodeError:
                    pass

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

    async def brainstorm_greeting_streaming(
        self, user_input: str, on_token
    ) -> dict:
        """Async streaming version of brainstorm_greeting.

        Calls on_token(str) for each token belonging to the 'response' field
        as the LLM generates it. Accumulates the full JSON and parses at end.
        Returns the same structure as brainstorm_greeting().
        """
        messages = [
            {"role": "system", "content": """You are an Azure solution project manager. Be CONCISE.
The user described a project idea. Respond with ONLY a JSON object (no markdown fences):

{
    "response": "Brief markdown response: 1 sentence acknowledgment, 2-3 short Azure scenario bullets (service names + why), 2-3 clarifying questions. Keep under 300 words. End with: Say **proceed** to start.",
    "azure_fit": "strong" or "weak" or "unclear",
    "azure_fit_explanation": "1 sentence WHY Azure fits or doesn't",
    "industry": "Retail, Healthcare, Financial Services, Manufacturing, or Cross-Industry",
    "scenarios": [
        {
            "title": "Short name",
            "description": "1 sentence",
            "azure_services": ["Service1", "Service2"]
        }
    ]
}

RULES:
- Keep the response field SHORT — no walls of text
- 2-3 scenarios max, 1 sentence each
- 2-3 questions max
- Be specific about Azure services"""},
            {"role": "user", "content": user_input},
        ]

        full_text = ""
        extracted_len = 0  # chars of the response field already sent

        async for chunk in llm.astream(messages):
            if chunk.content:
                full_text += chunk.content
                response_so_far = _extract_response_field_partial(full_text)
                if len(response_so_far) > extracted_len:
                    new_text = response_so_far[extracted_len:]
                    on_token(new_text)
                    extracted_len = len(response_so_far)

        # Parse accumulated full JSON (same logic as brainstorm_greeting)
        try:
            text = full_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(text)

            resp = result.get("response", text)
            if isinstance(resp, str) and resp.strip().startswith("{"):
                try:
                    inner = json.loads(resp)
                    if isinstance(inner, dict) and "response" in inner:
                        result["response"] = inner["response"]
                except json.JSONDecodeError:
                    pass

            return {
                "response": result.get("response", text),
                "azure_fit": result.get("azure_fit", "unclear"),
                "azure_fit_explanation": result.get("azure_fit_explanation", ""),
                "industry": result.get("industry", "Cross-Industry"),
                "scenarios": result.get("scenarios", []),
            }
        except (json.JSONDecodeError, Exception):
            return {
                "response": full_text,
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
            summary = f"Mapped {len(sels)} Azure services and estimated monthly cost: **${monthly:,.0f}** (source: {source})."
            insight = f"Annual projection: **${est.get('totalAnnual', 0):,.0f}**"

        elif step == "business_value":
            bv = state.business_value
            if bv.get("phase") == "needs_input":
                summary = "I need a few assumptions before calculating business value."
                insight = "Fill in the values above and click **Calculate**, or say **proceed** to use defaults."
            else:
                drivers = bv.get("drivers", [])
                impact = bv.get("annual_impact_range")
                summary = f"Identified {len(drivers)} benchmark-backed value drivers."
                if impact:
                    summary += f" Estimated annual impact: **${impact['low']:,.0f}–${impact['high']:,.0f}**."
                insight = ""

        elif step == "roi":
            roi_pct = state.roi.get("roi_percent")
            payback = state.roi.get("payback_months")
            roi_range = state.roi.get("roi_range")
            needs_info = state.roi.get("needs_info")
            if roi_pct is not None:
                range_text = roi_range or f"{roi_pct:.0f}%"
                summary = f"ROI calculated: **{range_text}** with {payback:.1f} month payback."
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
        parts.append("*To refine, just type your feedback below.*")

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
            parts = [f"## \U0001f3d7\ufe0f Architecture\n\n{arch.get('narrative', '')}\n"]

            # Reference pattern attribution
            based_on = arch.get("basedOn")
            url = arch.get("basedOnUrl")
            notes = arch.get("adaptationNotes")
            if based_on and based_on not in ("custom design", "fallback (LLM unavailable)"):
                ref_text = f"[{based_on}]({url})" if url else f"**{based_on}**"
                parts.append(f"\U0001f4da Adapted from: {ref_text}")
                if notes:
                    parts.append(f"  *{notes}*")
                parts.append("")

            # Mermaid diagram
            mermaid = arch.get("mermaidCode", "")
            if mermaid:
                parts.append(f"```mermaid\n{mermaid}\n```\n")

            # Layers with components
            layers = arch.get("layers", [])
            if layers:
                for layer in layers:
                    parts.append(f"### {layer.get('name', '')}")
                    purpose = layer.get("purpose", "")
                    if purpose:
                        parts.append(f"*{purpose}*\n")
                    for c in layer.get("components", []):
                        role = c.get("role", c.get("description", ""))
                        parts.append(
                            f"- **{c.get('name', '')}** ({c.get('azureService', '')}) — {role}"
                        )
                    parts.append("")
            else:
                # Fallback: flat component list
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
            est = state.costs.get("estimate", {})
            monthly = est.get("totalMonthly", 0)
            annual = est.get("totalAnnual", 0)
            source = est.get("pricingSource", "unknown")
            items = est.get("items", [])
            assumptions = est.get("assumptions", [])

            # ── Section 1: Mapped Azure Services ──
            parts = [f"## \u2601\ufe0f Azure Services ({len(sels)} mapped)\n"]
            for s in sels[:15]:
                reason = s.get("reason", "")
                reason_text = f" — {reason}" if reason else ""
                parts.append(
                    f"- **{s.get('componentName', '')}** \u2192 "
                    f"{s.get('serviceName', '')} ({s.get('sku', '')}){reason_text}"
                )

            # ── Section 2: Cost Summary ──
            parts.append(f"\n## \U0001f4b0 Cost Summary\n")
            parts.append(f"| | |")
            parts.append(f"|---|---|")
            parts.append(f"| **Monthly** | **${monthly:,.0f}** |")
            parts.append(f"| **Annual** | **${annual:,.0f}** |")
            parts.append(f"| **Pricing source** | {source} |")

            # Confidence based on pricing source
            confidence = "high" if source == "live" else "medium" if source == "live-fallback" else "low"
            parts.append(f"| **Confidence** | {confidence} |\n")

            # Top 5 cost drivers
            sorted_items = sorted(items, key=lambda x: x.get("monthlyCost", 0), reverse=True)
            top5 = sorted_items[:5]
            if top5:
                parts.append("### Top Cost Drivers\n")
                parts.append("| Service | SKU | Monthly |")
                parts.append("|---------|-----|--------:|")
                for item in top5:
                    cost = item.get("monthlyCost", 0)
                    note = item.get("pricingNote") or ""
                    if cost == 0 and note:
                        cost_text = f"$0 *({note[:50]})*"
                    elif cost == 0:
                        cost_text = "$0 *(usage-dependent)*"
                    else:
                        cost_text = f"${cost:,.0f}"
                    parts.append(
                        f"| {item.get('serviceName', '')} | {item.get('sku', '')} | {cost_text} |"
                    )

            # Flag any $0 items not in top 5
            zero_items = [i for i in items if i.get("monthlyCost", 0) == 0 and i not in top5]
            if zero_items:
                names = ", ".join(i.get("serviceName", "") for i in zero_items[:5])
                parts.append(f"\n*Also usage-dependent (placeholder $0): {names}*")

            # Assumptions
            if assumptions:
                parts.append("\n### Assumptions\n")
                for a in assumptions:
                    parts.append(f"- {a}")

            return "\n".join(parts)

        if step == "business_value":
            bv = state.business_value

            # Phase 1: needs_input — format assumption questions
            if bv.get("phase") == "needs_input":
                assumptions = bv.get("assumptions_needed", [])
                parts = ["## 📊 Business Value — Input Needed\n"]
                parts.append("Please provide these assumptions to calculate value drivers:\n")
                for a in assumptions:
                    unit = a.get("unit", "")
                    unit_prefix = "$" if unit == "$" else ""
                    unit_suffix = f" {unit}" if unit not in ("$", "") else ""
                    parts.append(f"- **{a['label']}**: {unit_prefix}{a['default']}{unit_suffix} *(default)*")
                    if a.get("hint"):
                        parts.append(f"  *{a['hint']}*")
                parts.append("\n*Adjust the values and click Calculate, or say **proceed** to use defaults.*")
                return "\n".join(parts)

            # Phase 2: completed BV with drivers
            drivers = bv.get("drivers", [])
            impact = bv.get("annual_impact_range")
            assumptions = bv.get("assumptions", [])
            confidence = bv.get("confidence", "moderate")

            parts = ["## \U0001f4ca Value Drivers\n"]
            for i, d in enumerate(drivers, 1):
                source = d.get("source_name", "")
                url = d.get("source_url", "")
                source_text = f"[{source}]({url})" if url else source
                parts.append(
                    f"{i}. **{d.get('name', '')}**: {d.get('metric', '')}\n"
                    f"   {d.get('description', '')}\n"
                    f"   *Source: {source_text}*\n"
                )

            if impact:
                parts.append(f"### Estimated Annual Impact\n\n"
                             f"**${impact['low']:,.0f} – ${impact['high']:,.0f}** ({confidence} estimate)\n")
            else:
                parts.append(f"*Dollar range not computed — need more inputs (see assumptions).*\n")

            if assumptions:
                parts.append("### Assumptions\n")
                for a in assumptions:
                    parts.append(f"- {a}")

            return "\n".join(parts)

        if step == "roi":
            roi = state.roi
            needs_info = roi.get("needs_info")
            if roi.get("roi_percent") is not None:
                parts = ["## \U0001f4c8 ROI Analysis\n"]
                roi_range = roi.get("roi_range", f"{roi['roi_percent']:.0f}%")
                parts.append(f"**ROI: {roi_range}** (midpoint {roi['roi_percent']:.0f}%) | Payback: **{roi.get('payback_months', 'N/A'):.1f} months**\n")
                parts.append(f"- Annual Azure cost: ${roi['annual_cost']:,.0f}")
                val_low = roi.get("annual_value_low")
                val_high = roi.get("annual_value_high")
                if val_low and val_high:
                    parts.append(f"- Annual value range: ${val_low:,.0f} – ${val_high:,.0f}\n")
                else:
                    parts.append(f"- Annual value generated: ${roi['annual_value']:,.0f}\n")
                if roi.get("monetized_drivers"):
                    parts.append("### Value Drivers Contributing\n")
                    for d in roi["monetized_drivers"]:
                        metric = d.get("metric", "")
                        parts.append(f"- **{d['name']}**: {metric}" if metric else f"- **{d['name']}**")
                if roi.get("assumptions"):
                    parts.append("\n### Assumptions\n")
                    for a in roi["assumptions"]:
                        parts.append(f"- {a}")
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
            return "\n".join(parts)

        if step == "presentation":
            path = state.presentation_path
            if path:
                return "## \U0001f4d1 Presentation Ready\n\nPowerPoint deck generated.\n\n\U0001f4e5 Ready for download."
            return "## \U0001f4d1 Presentation\n\n\u26a0\ufe0f Deck generation failed."

        return f"{step} completed."
