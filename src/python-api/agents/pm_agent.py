"""Project Manager — plans and orchestrates the agent pipeline."""
import json
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


class IntentInterpreter:
    """Classifies user messages into actionable intents via keyword matching with LLM fallback."""

    PROCEED_PATTERNS = ["proceed", "yes", "let's go", "lets go", "go", "ok", "sure", "do it", "start", "continue", "approved", "approve"]
    REFINE_PATTERNS = ["refine", "change", "adjust", "modify", "update", "tweak", "improve"]
    SKIP_PATTERNS = ["skip", "next", "don't need", "dont need", "pass"]
    FAST_RUN_PATTERNS = ["run everything", "fast mode", "no stops", "just build it", "run all", "do everything"]
    BRAINSTORM_PATTERNS = ["different approach", "start over", "rethink", "other options", "try again", "alternative"]
    ITERATION_KEYWORDS = {
        "cheaper": ["azure_services", "cost", "roi", "presentation"],
        "expensive": ["azure_services", "cost", "roi", "presentation"],
        "high availability": ["architect", "azure_services", "cost", "roi", "presentation"],
        "ha": ["architect", "azure_services", "cost", "roi", "presentation"],
        "region": ["azure_services", "cost", "presentation"],
        "compliance": ["architect", "azure_services"],
        "ai": ["architect", "azure_services", "cost", "business_value", "roi", "presentation"],
        "scale": ["azure_services", "cost", "roi"],
    }

    def classify(self, message: str) -> tuple[Intent, dict]:
        """Classify a message into an intent. Returns (intent, metadata).

        metadata may contain:
        - "agents_to_rerun": list[str] for ITERATION intent
        - "feedback": str for REFINE intent
        """
        msg = message.lower().strip()

        # Check patterns in priority order
        if any(p in msg for p in self.FAST_RUN_PATTERNS):
            return Intent.FAST_RUN, {}

        if any(p == msg or msg.startswith(p) for p in self.PROCEED_PATTERNS):
            return Intent.PROCEED, {}

        if any(p in msg for p in self.SKIP_PATTERNS):
            return Intent.SKIP, {}

        if any(p in msg for p in self.REFINE_PATTERNS):
            return Intent.REFINE, {"feedback": message}

        if any(p in msg for p in self.BRAINSTORM_PATTERNS):
            return Intent.BRAINSTORM, {}

        # Check iteration keywords
        for keyword, agents in self.ITERATION_KEYWORDS.items():
            if keyword in msg:
                return Intent.ITERATION, {"agents_to_rerun": agents, "feedback": message}

        # Check if it's a question
        if "?" in msg or any(msg.startswith(w) for w in ["what", "why", "how", "can you", "could you", "is it", "are there"]):
            return Intent.QUESTION, {}

        # Default: treat as new input
        return Intent.INPUT, {}

    def classify_with_llm_fallback(self, message: str) -> tuple[Intent, dict]:
        """Classify with keyword matching first, LLM fallback for ambiguous cases."""
        intent, meta = self.classify(message)

        # If classified as INPUT (default), try LLM for better classification
        if intent == Intent.INPUT and len(message.split()) > 3:
            try:
                from agents.llm import llm
                response = llm.invoke([
                    {"role": "system", "content": "Classify this user message as one of: proceed, refine, skip, fast_run, brainstorm, iteration, question, input. Return ONLY the classification word."},
                    {"role": "user", "content": message}
                ])
                llm_intent = response.content.strip().lower().replace("-", "_")
                try:
                    return Intent(llm_intent), meta
                except ValueError:
                    pass
            except Exception:
                pass

        return intent, meta


AGENT_INFO = {
    "brainstorm": {"name": "Brainstorming", "emoji": "\U0001f4a1"},
    "knowledge": {"name": "Knowledge Retrieval", "emoji": "\U0001f4da"},
    "architect": {"name": "System Architect", "emoji": "\U0001f3d7\ufe0f"},
    "azure_services": {"name": "Azure Specialist", "emoji": "\u2601\ufe0f"},
    "cost": {"name": "Cost Specialist", "emoji": "\U0001f4b0"},
    "business_value": {"name": "Business Value", "emoji": "\U0001f4ca"},
    "roi": {"name": "ROI Calculator", "emoji": "\U0001f4c8"},
    "presentation": {"name": "Presentation", "emoji": "\U0001f4d1"},
}

DEFAULT_PLAN = [
    "brainstorm",
    "knowledge",
    "architect",
    "azure_services",
    "cost",
    "business_value",
    "roi",
    "presentation",
]

PLAN_TO_ACTIVE = {
    "brainstorm": "envisioning",
    "knowledge": "knowledge",
    "architect": "architect",
    "azure_services": "azure-specialist",
    "cost": "cost",
    "business_value": "business-value",
    "roi": "roi",
    "presentation": "presentation",
}

ITERATION_MAPPING = {
    "cheaper": ["azure_services", "cost", "roi", "presentation"],
    "expensive": ["azure_services", "cost", "roi", "presentation"],
    "high availability": ["architect", "azure_services", "cost", "roi", "presentation"],
    "region": ["azure_services", "cost", "presentation"],
    "compliance": ["architect", "azure_services"],
    "ai": ["architect", "azure_services", "cost", "business_value", "roi", "presentation"],
    "scale": ["azure_services", "cost", "roi"],
    "different approach": ["brainstorm", "knowledge", "architect", "azure_services", "cost", "business_value", "roi", "presentation"],
}


class ProjectManager:
    def __init__(self):
        self.intent_interpreter = IntentInterpreter()

    def ask_clarifications(self, user_input: str) -> str:
        """Generate 2-3 clarifying questions + execution plan."""
        response = llm.invoke([
            {"role": "system", "content": """You are an Azure solution project manager. The user described a project.
Respond with:
1. A brief acknowledgment (1 sentence)
2. 2-3 clarifying questions as a numbered list
3. An execution plan showing which agents will run

Format your response in markdown. End with: "Ready when you are \u2014 just say **proceed** or answer the questions above."
"""},
            {"role": "user", "content": user_input}
        ])
        return response.content

    def build_plan(self, active_agents: list[str]) -> list[str]:
        """Build execution plan respecting agent toggles. Architect is always included."""
        plan = []
        for agent_id in DEFAULT_PLAN:
            mapped = PLAN_TO_ACTIVE.get(agent_id, agent_id)
            if mapped in active_agents or agent_id == "architect":
                plan.append(agent_id)
        return plan

    def format_plan(self, plan: list[str]) -> str:
        """Format the execution plan as markdown."""
        lines = ["## \U0001f4cb Execution Plan\n"]
        for i, step in enumerate(plan, 1):
            info = AGENT_INFO.get(step, {"name": step, "emoji": "\U0001f527"})
            lines.append(f"{i}. {info['emoji']} **{info['name']}**")
        return "\n".join(lines)

    def approval_summary(self, step: str, state: AgentState) -> str:
        """Generate a summary of agent output + key insight + approval prompt."""
        info = AGENT_INFO.get(step, {"name": step, "emoji": "\U0001f527"})

        summary = ""
        insight = ""

        if step == "brainstorm":
            scenarios = state.brainstorming.get("scenarios", [])
            fit = state.azure_fit
            summary = f"Identified {len(scenarios)} potential Azure scenarios."
            insight = f"Azure fit: **{fit}** \u2014 {state.azure_fit_explanation}"

        elif step == "knowledge":
            patterns = state.retrieved_patterns
            summary = f"Retrieved {len(patterns)} Microsoft reference architectures."
            if patterns:
                insight = f"Best match: **{patterns[0].get('title', 'N/A')}** (confidence: {patterns[0].get('confidence_score', 0):.0%})"

        elif step == "architect":
            comps = state.architecture.get("components", [])
            summary = f"Designed architecture with {len(comps)} Azure components."
            based_on = state.architecture.get("basedOn", "custom design")
            insight = f"Based on: **{based_on}**"

        elif step == "azure_services":
            sels = state.services.get("selections", [])
            summary = f"Mapped {len(sels)} Azure services with SKU recommendations."
            insight = "Review the service selections and SKUs above."

        elif step == "cost":
            est = state.costs.get("estimate", {})
            monthly = est.get("totalMonthly", 0)
            source = est.get("pricingSource", "unknown")
            summary = f"Estimated monthly cost: **${monthly:,.2f}** (source: {source})."
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
            if roi_pct is not None:
                summary = f"ROI calculated: **{roi_pct:.0f}%** with {payback:.1f} month payback."
            else:
                summary = "ROI could not be calculated quantitatively \u2014 see qualitative benefits."
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

    def get_agents_to_rerun(self, user_message: str) -> list[str]:
        """Determine which agents need to re-run based on user's iteration request."""
        msg = user_message.lower()
        for keyword, agents in ITERATION_MAPPING.items():
            if keyword in msg:
                return agents
        # Default: re-run from architect onward
        return ["architect", "azure_services", "cost", "business_value", "roi", "presentation"]