"""Business Value Agent — two-phase benchmark-backed value drivers.

Phase 1: Generate assumption questions with defaults for user input.
Phase 2: Calculate value drivers using user-provided assumptions.
"""
import json
import logging
from agents.llm import llm
from agents.state import AgentState
from services.web_search import search_industry_benchmarks

logger = logging.getLogger(__name__)


class BusinessValueAgent:
    name = "Business Value"
    emoji = "📊"

    def generate_assumptions(self, state: AgentState) -> list[dict]:
        """Generate assumption questions based on the use case. Returns list of assumption dicts."""
        industry = state.brainstorming.get("industry", "Cross-Industry")
        description = state.user_input

        try:
            response = llm.invoke([
                {"role": "system", "content": """Generate 3-5 business assumption questions for calculating Azure solution value.
Return ONLY a JSON array. Each item:
{
    "id": "unique_key",
    "label": "Human-readable question",
    "unit": "$" or "hours" or "count" or "%",
    "default": numeric_default_value,
    "hint": "Brief explanation of why this matters"
}

Be specific to the industry and use case. Include things like:
- Number of employees/users affected
- Current cost/spend related to the problem
- Time spent on manual processes
- Revenue or transaction volumes

IMPORTANT: Use REALISTIC default values based on published industry midpoints
for mid-size enterprises. Do not artificially deflate defaults.
Keep it to 3-5 questions max. Be concise."""},
                {"role": "user", "content": f"Industry: {industry}\nUse case: {description}"}
            ])

            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            assumptions = json.loads(text)
            if isinstance(assumptions, list) and len(assumptions) > 0:
                return assumptions[:5]
        except Exception:
            pass

        # Fallback generic assumptions — realistic enterprise defaults
        return [
            {"id": "employees", "label": "Number of employees affected", "unit": "count", "default": 100, "hint": "How many people will use or benefit from this solution"},
            {"id": "monthly_it_spend", "label": "Current monthly IT spend", "unit": "$", "default": 50000, "hint": "Approximate monthly infrastructure/operations cost"},
            {"id": "manual_hours", "label": "Hours spent on manual processes per week", "unit": "hours", "default": 40, "hint": "Time that could be automated or reduced"},
            {"id": "revenue_impact_area", "label": "Monthly revenue from affected area", "unit": "$", "default": 250000, "hint": "Revenue from the business area this solution touches"},
        ]

    def run(self, state: AgentState) -> AgentState:
        """Two-phase value driver generation.

        Phase 1: Return assumption questions for user input.
        Phase 2: Calculate value drivers using user-provided assumptions.
        """
        # Check if we have user-provided assumptions
        user_assumptions = state.business_value.get("user_assumptions")

        if not user_assumptions:
            # Phase 1: Generate assumption questions
            assumptions = self.generate_assumptions(state)
            state.business_value = {
                "phase": "needs_input",
                "assumptions_needed": assumptions,
            }
            return state

        # Phase 2: Calculate with real numbers
        industry = state.brainstorming.get("industry", "Cross-Industry")
        customer = state.customer_name or "the customer"
        description = state.user_input
        clarifications = state.clarifications

        # Build assumption context from user-provided values
        assumption_context = "\n".join([
            f"- {a['label']}: {a['value']} {a.get('unit', '')}"
            for a in user_assumptions
        ])

        # Search for real industry benchmarks
        use_case = description[:120]
        search_results: list[dict[str, str]] = []
        try:
            search_results = search_industry_benchmarks(industry, use_case)
        except Exception as e:
            logger.warning(f"Industry benchmark search failed: {e}")

        # Build search context
        search_context = ""
        if search_results:
            search_context = "INDUSTRY BENCHMARKS (from web search — cite these):\n"
            for r in search_results[:5]:
                search_context += f"- {r.get('title', '')}: {r.get('snippet', '')}\n"
                if r.get("url"):
                    search_context += f"  URL: {r['url']}\n"
        else:
            search_context = "No web search results available — DO NOT make up benchmark sources. Only cite sources if you are CERTAIN they are real published reports with verifiable URLs. Otherwise leave source_url empty and use 'Industry estimate' as source_name.\n"

        # Extra context from prior agents (iteration re-runs)
        extra = []
        scenarios = state.brainstorming.get("scenarios", [])
        if scenarios:
            extra.append("SCENARIOS: " + "; ".join(s.get("title", "") for s in scenarios[:3]))
        if state.architecture.get("narrative"):
            extra.append(f"ARCHITECTURE: {state.architecture['narrative'][:200]}")
        monthly_cost = state.costs.get("estimate", {}).get("totalMonthly", 0)
        if monthly_cost > 0:
            extra.append(f"MONTHLY AZURE COST: ${monthly_cost:,.0f}")
        extra_context = "\n".join(extra)

        # Build source citation instruction based on search availability
        if search_results:
            source_instruction = "Cite real, published sources with URLs for each driver."
        else:
            source_instruction = "Mark source_name as 'Industry estimate' and source_url as '' since no published sources were found."

        prompt = f"""You are a value engineer. Produce EXACTLY 3 benchmark-backed value drivers for this Azure solution.

CUSTOMER: {customer}
INDUSTRY: {industry}
USE CASE: {description}
{f"CLARIFICATIONS: {clarifications}" if clarifications else ""}
{extra_context}

USER-PROVIDED ASSUMPTIONS (use these real numbers, don't make up values):
{assumption_context}

{search_context}

RULES — follow precisely:
1. Return EXACTLY 3 value drivers. No more, no fewer.
2. Each driver must have a SPECIFIC percentage or metric range (e.g. "10–20% time savings").
   Use the midpoint of published industry ranges — do not artificially deflate percentages.
3. {source_instruction}
   Include the source name AND a URL. If you don't have a real URL, use the best matching web search result above.
4. Do NOT write long prose. Each description is 1 sentence max.
5. Provide an aggregated annual_impact_range (low–high dollars) across all 3 drivers.
   USE THE USER-PROVIDED ASSUMPTIONS ABOVE to compute real dollar values.
6. List every assumption behind that number explicitly (headcount, hourly rate, hours saved, etc.).
7. If you cannot compute a dollar range without knowing something, still give the percentage drivers
   but set annual_impact_range to null and list what's missing in assumptions.

CALCULATION APPROACH:
- Calculate each driver INDEPENDENTLY using the user-provided assumptions.
- Use realistic percentage ranges based on published industry data (not artificially deflated).
- For revenue uplift drivers, count the revenue impact at face value — do NOT discount
  revenue uplift to a small fraction (e.g. 5%) of the actual calculated impact.
- Sum the drivers directly. Do NOT apply "overlap adjustments", "double counting reductions",
  or any cross-driver deductions.
- Set confidence to "moderate" by default.

Return ONLY valid JSON (no markdown fences):
{{
  "drivers": [
    {{
      "name": "Short driver name",
      "metric": "10–20% time savings" or similar specific range,
      "description": "One sentence explaining the mechanism",
      "category": "cost_reduction" or "revenue_uplift",
      "source_name": "Gartner 2024" or "McKinsey Digital" or similar,
      "source_url": "https://..."
    }}
  ],
  "annual_impact_range": {{ "low": 500000, "high": 1200000 }} or null,
  "assumptions": [
    "500 engineers at $75/hr average fully loaded cost",
    "15% reduction in search time = 120 hrs/engineer/year"
  ],
  "confidence": "moderate"
}}

CATEGORY RULES:
- "cost_reduction": driver primarily reduces existing spend (labour, infra, errors, rework, licensing)
- "revenue_uplift": driver generates NEW value (new product features, faster time-to-market,
  improved customer retention, higher conversion, new revenue channels)
- Assign each driver to the category that best describes its primary mechanism.
- Aim for at least one driver in each category when the use case supports both."""

        try:
            response = llm.invoke([
                {"role": "system", "content": "You are an Azure value engineer. Return ONLY valid JSON. Be realistic based on published industry data, cite real sources, no fluff."},
                {"role": "user", "content": prompt},
            ])

            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(text)

            # Validate exactly 3 drivers
            drivers = result.get("drivers", [])[:3]
            for d in drivers:
                d.setdefault("name", "")
                d.setdefault("metric", "")
                d.setdefault("description", "")
                d.setdefault("category", "cost_reduction")
                d.setdefault("source_name", "")
                d.setdefault("source_url", "")

            state.business_value = {
                "drivers": drivers,
                "annual_impact_range": result.get("annual_impact_range"),
                "assumptions": result.get("assumptions", []),
                "confidence": result.get("confidence", "moderate"),
                "sources": [
                    {"title": r.get("title", ""), "url": r.get("url", "")}
                    for r in search_results[:5]
                ],
                "user_assumptions": user_assumptions,
            }

        except Exception as e:
            logger.warning("BV LLM call failed: %s", e)
            state.business_value = {
                "drivers": [],
                "annual_impact_range": None,
                "assumptions": ["Value calculation failed — please try again or provide more details about the use case."],
                "confidence": "low",
                "sources": [],
                "user_assumptions": user_assumptions,
                "error": "Could not generate value drivers. Please retry or refine the use case description.",
            }

        return state
