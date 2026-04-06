"""Project Manager — plans and orchestrates the agent pipeline."""
import json
import logging
import re
from enum import Enum
from agents.llm import llm
from agents.state import AgentState
from core.utils import strip_markdown_fences, parse_leading_int

logger = logging.getLogger(__name__)

# M-5: Pre-compiled regex for streaming JSON response field extraction
_RESPONSE_FIELD_RE = re.compile(r'"response"\s*:\s*"((?:[^"\\]|\\.)*)', re.DOTALL)


def _extract_response_field_partial(partial_json: str) -> str:
    """Extract the partial value of the 'response' key from a streaming JSON string.

    Handles both incomplete (streaming) and complete JSON.
    Returns the extracted text, or "" if the key hasn't appeared yet.
    """
    # re.DOTALL so the pattern matches across newlines in the response value
    match = _RESPONSE_FIELD_RE.search(partial_json)
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
    "cost": ["cost", "roi", "presentation"],
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
    # QW-2: Security/compliance intent keywords → architect + cost only
    "secure": ["architect", "cost"],
    "security": ["architect", "cost"],
    "gdpr": ["architect", "cost"],
    "pci": ["architect", "cost"],
    "soc2": ["architect", "cost"],
    "hipaa": ["architect", "cost"],
    "encryption": ["architect", "cost"],
    "zero trust": ["architect", "cost"],
    # AC-5: Semantic iteration mappings
    "budget": ["cost", "roi"],
    "faster": ["architect", "cost", "roi"],
    "performance": ["architect", "cost", "roi"],
    "latency": ["architect", "cost", "roi"],
    "users": ["architect", "cost", "roi"],
    "concurrent": ["architect", "cost", "roi"],
    "simpler": ["architect", "cost", "roi"],
    "reduce": ["architect", "cost", "roi"],
    "fewer": ["architect", "cost", "roi"],
}

# Pre-compiled word-boundary regexes for each keyword (avoids substring false positives)
_ITERATION_RE: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE), agents)
    for kw, agents in ITERATION_MAPPING.items()
]


def _resolve_iteration_agents(message: str) -> list[str]:
    """Collect agents from ALL matching iteration keywords using word-boundary regex.

    Returns a de-duplicated list preserving SOLUTIONING_PLAN order,
    or an empty list if no keywords matched.
    """
    matched: set[str] = set()
    for pattern, agents in _ITERATION_RE:
        if pattern.search(message):
            matched.update(agents)
    if not matched:
        return []
    # Return in canonical plan order (+ any extras at the end)
    ordered = [a for a in SOLUTIONING_PLAN if a in matched]
    ordered.extend(a for a in matched if a not in ordered)
    return ordered


class IntentInterpreter:
    """Classifies user messages into actionable intents via LLM.

    Uses an LLM call as the primary classifier for natural language understanding.
    The ITERATION_MAPPING dict is used only to resolve *which agents* to re-run
    once the LLM has identified an iteration intent — that routing is deterministic.

    Supports multi-intent classification: a single message like "looks good but
    make it cheaper" can return ``[Intent.PROCEED, Intent.ITERATION]``.
    """

    SYSTEM_PROMPT_BASE = (
        "You are an intent classifier for an Azure solution copilot. "
        "Classify the user's message into ONE OR MORE of these intents:\n\n"
        "- proceed: User wants to move forward (e.g. 'yes', 'ok', 'let's go', 'approved', 'continue')\n"
        "- refine: User wants to adjust the current step's output (e.g. 'change X', 'make it more detailed', 'tweak the architecture')\n"
        "- skip: User wants to skip the current step (e.g. 'skip', 'next', 'don't need this')\n"
        "- fast_run: User wants to run all remaining steps without pausing (e.g. 'run everything', 'fast mode', 'just build it')\n"
        "- brainstorm: User wants to start over or explore different ideas (e.g. 'different approach', 'start over', 'rethink')\n"
        "- iteration: User wants to change something about an already-completed solution "
        "(e.g. 'make it cheaper', 'add high availability', 'change region to Europe', 'add AI capabilities')\n"
        "- question: User is asking a question (e.g. 'why did you pick this?', 'what does this cost?', 'can you explain?')\n"
        "- input: User is providing new information or context that doesn't fit the above categories\n\n"
        "A message may express multiple intents. For example, 'looks good but make it cheaper' "
        "is both 'proceed' and 'iteration'.\n\n"
        "Return a JSON array of intent strings, e.g. [\"proceed\"] or [\"proceed\", \"iteration\"]. "
        "Return ONLY the JSON array, nothing else."
    )

    # Keep backward-compatible single-intent prompt for reference
    SYSTEM_PROMPT = SYSTEM_PROMPT_BASE

    # Default agents to re-run when iteration intent has no keyword match
    DEFAULT_RERUN_AGENTS: list[str] = [
        "architect", "cost", "business_value", "roi", "presentation",
    ]

    def _build_system_prompt(self, phase: str = "", current_step: str = "",
                             recent_messages: list[str] | None = None) -> str:
        """Build a context-aware system prompt including phase and step info."""
        prompt = self.SYSTEM_PROMPT_BASE

        context_parts: list[str] = []
        if phase:
            context_parts.append(f"Current phase: {phase}")
        if current_step:
            context_parts.append(f"Current step: {current_step}")
        if recent_messages:
            recent_text = " | ".join(recent_messages[-3:])
            context_parts.append(f"Recent context: {recent_text}")

        if context_parts:
            context_block = "\n".join(context_parts)
            prompt += (
                f"\n\n{context_block}\n\n"
                "Given the phase context, classify the user's message. In the \"executing\" phase, "
                "users often want to provide feedback to the current agent. In the \"done\" phase, "
                "users often want to iterate on specific parts of the solution."
            )

        return prompt

    def _build_meta(self, intent: Intent, message: str) -> dict:
        """Build the metadata dict for a resolved intent."""
        meta: dict = {}
        if intent == Intent.ITERATION:
            meta["feedback"] = message
            agents = _resolve_iteration_agents(message)
            meta["agents_to_rerun"] = agents if agents else list(self.DEFAULT_RERUN_AGENTS)
        elif intent == Intent.REFINE:
            meta["feedback"] = message
        return meta

    def _build_multi_meta(self, intents: list[Intent], message: str) -> dict:
        """Build combined metadata dict for multiple intents."""
        combined: dict = {}
        for intent in intents:
            single = self._build_meta(intent, message)
            combined.update(single)
        return combined

    def _parse_intents(self, raw_text: str) -> list[Intent]:
        """Parse LLM response into a list of Intent enums.

        Handles both JSON array format and single-word fallback.
        """
        cleaned = raw_text.strip()
        # Strip markdown fences if present
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        # Try JSON array first
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                intents = []
                for item in parsed:
                    normalized = str(item).strip().lower().replace("-", "_").replace(" ", "_")
                    intents.append(Intent(normalized))
                return intents if intents else [Intent.INPUT]
            elif isinstance(parsed, str):
                normalized = parsed.strip().lower().replace("-", "_").replace(" ", "_")
                return [Intent(normalized)]
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            pass

        # Fallback: single word (backward compat with old prompt format)
        try:
            normalized = cleaned.lower().replace("-", "_").replace(" ", "_")
            return [Intent(normalized)]
        except (ValueError, KeyError):
            pass

        return [Intent.INPUT]

    def classify(self, message: str, phase: str = "", current_step: str = "",
                 recent_messages: list[str] | None = None) -> tuple[list[Intent], dict]:
        """Classify a message into one or more intents using an LLM call.

        Returns (intents_list, metadata).
        """
        system_prompt = self._build_system_prompt(phase, current_step, recent_messages)
        try:
            response = llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ])
            intents = self._parse_intents(response.content)
        except Exception:
            logger.warning("Intent classification failed, defaulting to [INPUT]")
            intents = [Intent.INPUT]

        return intents, self._build_multi_meta(intents, message)

    async def aclassify(self, message: str, phase: str = "", current_step: str = "",
                        recent_messages: list[str] | None = None) -> tuple[list[Intent], dict]:
        """Async version of :meth:`classify` — uses ``ainvoke`` to avoid
        blocking the event loop.  Drop-in replacement for async contexts."""
        system_prompt = self._build_system_prompt(phase, current_step, recent_messages)
        try:
            response = await llm.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ])
            intents = self._parse_intents(response.content)
        except Exception:
            logger.warning("Intent classification failed, defaulting to [INPUT]")
            intents = [Intent.INPUT]

        return intents, self._build_multi_meta(intents, message)


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


class ProjectManager:
    def __init__(self):
        self.intent_interpreter = IntentInterpreter()

    @staticmethod
    def _parse_brainstorm_json(raw_text: str) -> dict:
        """Parse brainstorm LLM output into a structured dict.

        Handles markdown fences, double-wrapped JSON, and plain-text fallback.
        """
        try:
            text = strip_markdown_fences(raw_text)
            result = json.loads(text)

            resp = result.get("response", text)
            # LLMs sometimes double-wrap: {"response": "{\"response\": \"...\"}"}
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
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return {
                "response": raw_text,
                "azure_fit": "unclear",
                "azure_fit_explanation": "Could not assess Azure fit from the response.",
                "industry": "Cross-Industry",
                "scenarios": [],
            }

    def brainstorm_greeting(self, user_input: str) -> dict:
        """Brainstorm + classify Azure fit in one LLM call.

        Returns a dict with:
          - response: str  (conversational markdown for the user)
          - azure_fit: str  ("strong", "weak", or "unclear")
          - azure_fit_explanation: str
          - industry: str
          - scenarios: list[dict]  (structured scenario data)
        """
        try:
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
        except Exception as e:
            logger.warning("Brainstorm LLM call failed: %s", e, exc_info=True)
            return {
                "response": "I'd be happy to help design your Azure solution. Could you tell me more about your requirements?",
                "azure_fit": "unclear",
                "azure_fit_explanation": "",
                "industry": "Cross-Industry",
                "scenarios": [],
            }

        return self._parse_brainstorm_json(response.content)

    async def brainstorm_greeting_streaming(
        self, user_input: str, on_token, company_profile: dict | None = None,
    ) -> dict:
        """Async streaming version of brainstorm_greeting.

        Calls on_token(str) for each token belonging to the 'response' field
        as the LLM generates it. Accumulates the full JSON and parses at end.
        Returns the same structure as brainstorm_greeting().
        """
        # Build optional company context block
        company_context = ""
        if company_profile:
            p = company_profile
            lines = [f"\nCUSTOMER PROFILE (verified from public sources):"]
            lines.append(f"- Company: {p.get('name', '')} ({p.get('industry', '')})")
            if p.get("employeeCount"):
                lines.append(f"- {p['employeeCount']:,} employees | HQ: {p.get('headquarters', 'Unknown')}")
            if p.get("annualRevenue"):
                rev = p["annualRevenue"]
                currency = p.get("revenueCurrency", "USD")
                lines.append(f"- Annual revenue: {currency} {rev:,.0f}")
            if p.get("itSpendEstimate"):
                lines.append(f"- Est. IT spend: ${p['itSpendEstimate']:,.0f}/yr")
            if p.get("cloudProvider"):
                lines.append(f"- Cloud: {p['cloudProvider']}")
            if p.get("knownAzureUsage"):
                lines.append(f"- Known Azure: {', '.join(p['knownAzureUsage'][:4])}")
            if p.get("erp"):
                lines.append(f"- ERP: {p['erp']}")
            lines.append(
                "\nUse this context to tailor your questions and scenarios specifically "
                f"to {p.get('name', 'this company')}'s industry, scale, and technology landscape."
            )
            company_context = "\n".join(lines)

        messages = [
            {"role": "system", "content": f"""You are an Azure solution project manager. Be CONCISE.
The user described a project idea. Respond with ONLY a JSON object (no markdown fences):

{{
    "response": "Brief markdown response: 1 sentence acknowledgment, 2-3 short Azure scenario bullets (service names + why), 2-3 clarifying questions. Keep under 300 words. End with: Say **proceed** to start.",
    "azure_fit": "strong" or "weak" or "unclear",
    "azure_fit_explanation": "1 sentence WHY Azure fits or doesn't",
    "industry": "Retail, Healthcare, Financial Services, Manufacturing, or Cross-Industry",
    "scenarios": [
        {{
            "title": "Short name",
            "description": "1 sentence",
            "azure_services": ["Service1", "Service2"]
        }}
    ]
}}

RULES:
- Keep the response field SHORT — no walls of text
- 2-3 scenarios max, 1 sentence each
- 2-3 questions max
- Be specific about Azure services{company_context}"""},
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

        # Parse accumulated full JSON (shared logic with brainstorm_greeting)
        return self._parse_brainstorm_json(full_text)

    def build_plan(self, active_agents: list[str]) -> list[str]:
        """Build solutioning execution plan respecting agent toggles. Architect is always included."""
        plan = []
        for agent_id in SOLUTIONING_PLAN:
            if agent_id in active_agents or agent_id == "architect":
                plan.append(agent_id)
        return plan

    def format_plan(self, state: AgentState) -> str:
        """Format the execution plan as a checkbox list reflecting current step states."""
        lines = ["## \U0001f4cb Execution Plan\n"]
        for step in state.plan_steps:
            info = AGENT_INFO.get(step, {"name": step, "emoji": "\U0001f527"})
            if step in state.completed_steps:
                lines.append(f"- [x] {info.get('emoji', '🔧')} **{info.get('name', step)}**")
            elif step in state.skipped_steps:
                lines.append(f"- [-] {info.get('emoji', '🔧')} ~~{info.get('name', step)}~~ *(skipped)*")
            elif step in state.failed_steps:
                lines.append(f"- [!] {info.get('emoji', '🔧')} **{info.get('name', step)}** *(failed)*")
            elif step == state.current_step:
                lines.append(f"- [ ] {info.get('emoji', '🔧')} **{info.get('name', step)}** ⏳")
            else:
                lines.append(f"- [ ] {info.get('emoji', '🔧')} {info.get('name', step)}")
        return "\n".join(lines)

    def approval_summary(self, step: str, state: AgentState) -> str:
        """Generate a summary of agent output + key insight + approval prompt.

        UX-1: Each step includes 1-2 decision questions to guide the seller.
        """
        info = AGENT_INFO.get(step, {"name": step, "emoji": "\U0001f527"})

        summary = ""
        insight = ""
        decision_question = ""

        if step == "architect":
            comps = state.architecture.get("components", [])
            summary = f"Designed architecture with {len(comps)} Azure components."
            based_on = state.architecture.get("basedOn", "custom design")
            insight = f"Based on: **{based_on}**"
            # UX-1: risk summary and decision question
            single_region_service_count = len([
                c for c in comps
                if any(kw in str(c).lower() for kw in ("app service", "sql", "cosmos", "function"))
            ])
            if single_region_service_count > 2:
                decision_question = (
                    f"\U0001f6a8 **Decision point**: {single_region_service_count} services are single-region. "
                    "Add **'high availability'** to the next message to model HA costs, "
                    "or proceed to cost estimation."
                )
            else:
                decision_question = (
                    "\U0001f4a1 Architecture looks HA-ready. "
                    "Say **'add compliance'** if this is a regulated industry (HIPAA, GDPR, PCI), "
                    "or proceed to cost estimation."
                )

        elif step == "cost":
            est = state.costs.get("estimate", {})
            monthly = est.get("totalMonthly", 0)
            source = est.get("pricingSource", "unknown")
            sels = state.services.get("selections", [])
            summary = f"Mapped {len(sels)} Azure services and estimated monthly cost: **${monthly:,.0f}** (source: {source})."
            insight = f"Annual projection: **${est.get('totalAnnual', 0):,.0f}**"
            # UX-1: highlight top cost driver
            insights_data = est.get("insights", {})
            top3 = insights_data.get("top3Drivers", [])
            if top3:
                top = top3[0]
                decision_question = (
                    f"\U0001f4a1 **Top driver**: {top['service']} (${top['monthly']:,}/mo, {top['pct']}% of total). "
                    "Say **'make it cheaper'** to explore alternatives, or proceed to business value."
                )
                if insights_data.get("reservationNote"):
                    decision_question += f"\n\n\U0001f4b0 {insights_data['reservationNote']}"

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
                    summary += f" Estimated annual impact: **${impact.get('low', 0):,.0f}–${impact.get('high', 0):,.0f}**."
                # UX-1: highlight weakest driver for conversation
                confidence_obj = bv.get("confidence")
                if isinstance(confidence_obj, dict):
                    driver_scores = confidence_obj.get("driver_scores", [])
                    if driver_scores:
                        min_score = min(driver_scores)
                        min_idx = driver_scores.index(min_score)
                        if min_idx < len(drivers):
                            weak_driver = drivers[min_idx].get("name", "")
                            decision_question = (
                                f"\U0001f4a1 **Weakest driver**: {weak_driver} (confidence {min_score}/100). "
                                "Get customer data to strengthen this driver, or proceed to ROI."
                            )
                elif drivers:
                    decision_question = (
                        "\U0001f4a1 Review the value drivers above. "
                        "Say **'refine value'** to adjust assumptions, or proceed to ROI calculation."
                    )

        elif step == "roi":
            roi_pct = state.roi.get("roi_percent_display") or state.roi.get("roi_percent")
            payback = state.roi.get("payback_months")
            needs_info = state.roi.get("needs_info")
            if roi_pct is not None:
                range_text = f"{(roi_pct / 100 + 1):.1f}x"
                payback_str = f"{payback:.1f} months" if isinstance(payback, (int, float)) else "N/A"
                summary = f"ROI calculated: **{range_text}** with {payback_str} payback."
                if needs_info:
                    summary += "\n\nSome drivers couldn't be monetized yet. To refine the ROI, I'd need:"
                    for q in needs_info:
                        summary += f"\n- {q}"
                # UX-1: breakeven decision question
                if isinstance(payback, (int, float)) and payback > 12:
                    decision_question = (
                        f"\U0001f4a1 **Decision point**: Break-even is Month {payback:.0f}. "
                        "What would accelerate adoption? Say **'increase adoption'** to model faster ramp, "
                        "or proceed to presentation."
                    )
                else:
                    decision_question = (
                        "\U0001f4a1 Strong ROI case. "
                        "Say **'add NPV'** for CFO-ready metrics, or proceed to presentation."
                    )
            elif needs_info:
                summary = "I need a bit more information to calculate ROI:\n"
                for q in needs_info:
                    summary += f"\n- {q}"
                summary += "\n\nShare what you can and I'll re-run the numbers."
            else:
                summary = "ROI could not be calculated quantitatively — see qualitative benefits."

        elif step == "presentation":
            summary = "PowerPoint deck generated and ready for download."
            decision_question = (
                "\U0001f4a1 Review the deck. Say **'refine presentation'** to adjust any slide, "
                "or download and share with the customer."
            )

        parts = [
            f"{info.get('emoji', '🔧')} **{info.get('name', step)}** completed.",
            "",
            summary,
        ]
        if insight:
            parts.append(f"\U0001f4a1 {insight}")
        if decision_question:
            parts.append("")
            parts.append(decision_question)
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
        agents = _resolve_iteration_agents(user_message)
        return agents if agents else ["business_value", "architect", "cost", "roi", "presentation"]

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

            # ── Section 1: Cost Summary (FIRST — most important) ──
            parts = [f"## \U0001f4b0 Cost Estimate\n"]
            parts.append(f"| | |")
            parts.append(f"|---|---|")
            parts.append(f"| **Monthly** | **${monthly:,.0f}** |")
            parts.append(f"| **Annual** | **${annual:,.0f}** |")
            parts.append(f"| **Pricing source** | {source} |")

            # Confidence based on proportion of services with live/high-confidence pricing
            # Uses per-item confidence field when available, falls back to source string parsing
            _confidence_field = est.get("confidenceSummary")
            if isinstance(_confidence_field, str) and _confidence_field in ("high", "moderate", "low"):
                confidence = _confidence_field
            else:
                _live_count = sum(
                    parse_leading_int(p)
                    for p in source.split(", ")
                    if any(p.endswith(s) for s in ("live", "live-fallback"))
                ) if isinstance(source, str) else 0
                _total_count = sum(
                    parse_leading_int(p) for p in source.split(", ")
                ) if isinstance(source, str) else 1
                _live_pct = _live_count / max(_total_count, 1)
                confidence = "high" if _live_pct > 0.8 else "moderate" if _live_pct > 0.5 else "low"
            parts.append(f"| **Confidence** | {confidence} |\n")

            # ── Section 2: Top Cost Drivers (per-service breakdown) ──
            sorted_items = sorted(items, key=lambda x: x.get("monthlyCost", 0), reverse=True)
            top5 = sorted_items[:5]
            if top5:
                parts.append("### Per-Service Cost Breakdown\n")
                parts.append("| Service | SKU | Monthly |")
                parts.append("|---------|-----|--------:|")
                for item in sorted_items:
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

            # Assumptions
            if assumptions:
                parts.append("\n### Assumptions\n")
                for a in assumptions:
                    parts.append(f"- {a}")

            # ── Section 3: Azure Service Details ──
            parts.append(f"\n## \u2601\ufe0f Azure Services ({len(sels)} mapped)\n")
            for s in sels[:15]:
                reason = s.get("reason", "")
                reason_text = f" — {reason}" if reason else ""
                parts.append(
                    f"- **{s.get('componentName', '')}** \u2192 "
                    f"{s.get('serviceName', '')} ({s.get('sku', '')}){reason_text}"
                )

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
                    parts.append(f"- **{a.get('label', 'Unknown')}**: {unit_prefix}{a.get('default', '')}{unit_suffix} *(default)*")
                    if a.get("hint"):
                        parts.append(f"  *{a.get('hint')}*")
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
                             f"**${impact.get('low', 0):,.0f} – ${impact.get('high', 0):,.0f}** ({confidence} estimate)\n")
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
                roi_display = roi.get("roi_percent_display") or roi.get("roi_percent", 0) or 0
                roi_text = f"{roi_display:+.0f}%"
                payback = roi.get('payback_months')
                payback_str = f"{payback:.1f} months" if isinstance(payback, (int, float)) else "N/A"
                parts.append(f"**ROI: {roi_text}** | Payback: **{payback_str}**\n")
                parts.append(f"- Annual Azure cost: ${roi.get('annual_cost', 0) or 0:,.0f}")
                val_low = roi.get("annual_value_low")
                val_high = roi.get("annual_value_high")
                if val_low and val_high:
                    parts.append(f"- Annual value range: ${val_low:,.0f} – ${val_high:,.0f}\n")
                else:
                    parts.append(f"- Annual value generated: ${roi.get('annual_value', 0) or 0:,.0f}\n")
                if roi.get("monetized_drivers"):
                    parts.append("### Value Drivers Contributing\n")
                    for d in roi.get("monetized_drivers", []):
                        metric = d.get("metric", "")
                        parts.append(f"- **{d.get('name', 'Unknown')}**: {metric}" if metric else f"- **{d.get('name', 'Unknown')}**")
                if roi.get("assumptions"):
                    parts.append("\n### Assumptions\n")
                    for a in roi.get("assumptions", []):
                        parts.append(f"- {a}")
            elif needs_info:
                parts = ["## \U0001f4c8 ROI Analysis\n"]
                parts.append("I need more information to calculate ROI:\n")
                for q in needs_info:
                    parts.append(f"- {q}")
                parts.append("\nShare what you can and say **refine** to re-run.")
                if roi.get("qualitative_benefits"):
                    parts.append("\n### Qualitative Benefits (in the meantime)\n")
                    for b in roi.get("qualitative_benefits", []):
                        parts.append(f"- {b}")
            else:
                parts = ["## \U0001f4c8 ROI Analysis\n", "ROI could not be calculated quantitatively.\n"]

            # ── Business Case Summary ────────────────────────────────
            bc = roi.get("dashboard", {}).get("businessCase")
            if bc:
                parts.append("\n### 💼 Business Case Summary\n")
                vs = bc.get("valueBridge", {})
                inv = bc.get("investment", {})
                if vs.get("totalAnnualValue"):
                    parts.append(f"**Annual value**: ${vs['totalAnnualValue']:,.0f}")
                if inv.get("year1Total"):
                    parts.append(f"**Year 1 investment**: ${inv['year1Total']:,.0f}")
                if inv.get("year1NetValue"):
                    parts.append(f"**Year 1 net value**: ${inv['year1NetValue']:,.0f}")
                sens = bc.get("sensitivity", [])
                if sens:
                    parts.append("\n**Sensitivity to adoption:**")
                    for s in sens:
                        parts.append(f"- {s['adoption']} adoption → ${s['annualValue']:,.0f}/yr value, {s.get('roi', 0):.0f}% ROI")

            return "\n".join(parts)

        if step == "presentation":
            path = state.presentation_path
            if path:
                return "## \U0001f4d1 Presentation Ready\n\nPowerPoint deck generated.\n\n\U0001f4e5 Ready for download."
            return "## \U0001f4d1 Presentation\n\n\u26a0\ufe0f Deck generation failed."

        return f"{step} completed."
