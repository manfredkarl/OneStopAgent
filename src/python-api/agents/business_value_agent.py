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

        # Build shared-assumption context so the LLM doesn't re-ask known values
        sa = state.shared_assumptions
        shared_lines: list[str] = []
        if sa:
            if sa.get("current_annual_engineering_toolchain_spend") or sa.get("current_annual_spend"):
                spend = sa.get("current_annual_engineering_toolchain_spend") or sa.get("current_annual_spend")
                shared_lines.append(f"Current annual spend: ${spend:,.0f} (ALREADY PROVIDED)")
            if sa.get("fully_loaded_engineering_labor_rate") or sa.get("hourly_labor_rate"):
                rate = sa.get("fully_loaded_engineering_labor_rate") or sa.get("hourly_labor_rate")
                shared_lines.append(f"Hourly labor rate: ${rate}/hr (ALREADY PROVIDED)")
            if sa.get("active_rd_engineering_users") or sa.get("total_users"):
                users = sa.get("active_rd_engineering_users") or sa.get("total_users")
                shared_lines.append(f"Total users: {users} (ALREADY PROVIDED)")

        shared_context_block = ""
        if shared_lines:
            shared_context_block = (
                "\n\nThe following values are ALREADY PROVIDED from the shared scenario assumptions — "
                "do NOT ask for them again:\n" + "\n".join(shared_lines) + "\n\n"
                "Only ask 3-4 questions about business-value-specific metrics NOT covered above."
            )

        try:
            response = llm.invoke([
                {"role": "system", "content": f"""Generate 3-5 business assumption questions for calculating Azure solution value.
Return ONLY a JSON array. Each item:
{{
    "id": "unique_key",
    "label": "Human-readable question",
    "unit": "$" or "hours" or "count" or "%",
    "default": numeric_default_value,
    "hint": "Brief explanation of why this matters"
}}

Be specific to the industry and use case. Include things like:
- Number of employees/users affected
- Current cost/spend related to the problem
- Time spent on manual processes
- Revenue or transaction volumes

IMPORTANT: Use REALISTIC default values based on published industry midpoints
for mid-size enterprises. Do not artificially deflate defaults.
Keep it to 3-5 questions max. Be concise.{shared_context_block}"""},
                {"role": "user", "content": f"Industry: {industry}\nUse case: {description}"}
            ])

            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            assumptions = json.loads(text)
            if isinstance(assumptions, list) and len(assumptions) > 0:
                return assumptions[:5]
        except Exception as e:
            logger.warning("Phase 1 assumption generation failed: %s", e)

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
            f"- {a.get('label', a.get('id', 'Unknown'))}: {a.get('value', 'N/A')} {a.get('unit', '')}"
            for a in user_assumptions
        ])

        # Prepend shared assumptions as baseline (fuzzy key matching)
        sa = state.shared_assumptions or {}
        shared_lines = []
        for k, v in sa.items():
            if k.startswith("_"):
                continue
            kl = k.lower()
            try:
                fv = float(v)
            except (ValueError, TypeError):
                continue
            if ("spend" in kl or "cost" in kl) and "annual" in kl and fv > 1000:
                shared_lines.append(f"- Current annual spend: ${fv:,.0f}")
            elif ("labor" in kl or "hourly" in kl) and "rate" in kl and 10 < fv < 500:
                shared_lines.append(f"- Hourly labor rate: ${fv}/hr")
            elif ("user" in kl or "engineer" in kl) and fv > 1:
                shared_lines.append(f"- Platform users: {int(fv)}")

        if shared_lines:
            assumption_context = "SHARED BASELINE:\n" + "\n".join(shared_lines) + "\n\nUSER INPUTS:\n" + assumption_context

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
            search_context = (
                "No web search results available.\n"
                "DO NOT fabricate benchmark sources or URLs.\n"
                "Since you are computing value from the user-provided assumptions below, "
                "be HONEST about the source: the numbers come from the user's data combined "
                "with a standard calculation methodology.\n"
                "Use descriptive source_name labels such as:\n"
                "  - 'Calculated from user assumptions' (when the math is based on user inputs)\n"
                "  - 'Labor rate analysis' (for headcount × rate × savings calculations)\n"
                "  - 'Spend optimization model' (for infrastructure cost reduction drivers)\n"
                "  - 'Revenue acceleration estimate' (for revenue uplift drivers)\n"
                "  - 'Azure industry analysis' or 'Microsoft customer evidence' (for Azure-specific claims)\n"
                "NEVER use the vague label 'Industry estimate'.\n"
                "Always set source_url to '' (empty string) when no real URL exists.\n"
            )

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
            source_instruction = (
                "Be honest about sources. Since calculations are derived from user-provided assumptions, "
                "use descriptive labels like 'Calculated from user assumptions', 'Labor rate analysis', "
                "'Spend optimization model', 'Revenue acceleration estimate', 'Azure industry analysis', "
                "or 'Microsoft customer evidence'. NEVER use the vague label 'Industry estimate'. "
                "Set source_url to '' (empty string). "
                "In the description, briefly cite the methodology, e.g. "
                "'Based on 20-30% engineering time savings applied to 1,600 hrs/week × $100/hr labor rate'."
            )

        prompt = f"""You are a value engineer. Produce EXACTLY 3 benchmark-backed value drivers for this Azure solution.

CUSTOMER: {customer}
INDUSTRY: {industry}
USE CASE: {description}
{f"CLARIFICATIONS: {clarifications}" if clarifications else ""}
{extra_context}

USER-PROVIDED ASSUMPTIONS (use these real numbers, don't make up values):
{assumption_context}

Use the SHARED current_annual_spend as the baseline for spend optimization calculations. Use the SHARED hourly_labor_rate for labor savings calculations. Do NOT derive your own labor rate or annual spend — the AUTHORITATIVE SHARED ASSUMPTIONS above are the single source of truth.

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
- For revenue uplift drivers, apply a conservative realization factor: use 25-50% of the gross revenue impact to account for adoption timing, competitive dynamics, and execution risk. Show the full gross impact AND the realized value clearly.
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
      "source_name": "Calculated from user assumptions" or "Labor rate analysis" or "Spend optimization model",
      "source_url": "" or "https://..." (empty string when no real URL exists)
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
                {"role": "system", "content": "You are an Azure value engineer. Return ONLY valid JSON. Be realistic based on published industry data when available; when computing from user-provided assumptions, honestly label sources as calculation-based rather than citing vague 'Industry estimate'. No fluff."},
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
            logger.error("BV LLM call failed: %s", e, exc_info=True)
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
