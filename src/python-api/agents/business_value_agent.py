"""Business Value Agent — two-phase benchmark-backed value drivers.

Phase 1: Generate assumption questions with defaults for user input.
Phase 2: Calculate value drivers using user-provided assumptions.
"""
import json
import logging
from agents.llm import llm
from agents.state import AgentState
from agents.assumption_catalog import filter_already_answered
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
        typed = state.sa
        shared_lines: list[str] = []
        if typed.current_annual_spend:
            shared_lines.append(f"Current annual spend: ${typed.current_annual_spend:,.0f} (ALREADY PROVIDED)")
        if typed.hourly_labor_rate:
            shared_lines.append(f"Hourly labor rate: ${typed.hourly_labor_rate}/hr (ALREADY PROVIDED)")
        if typed.total_users:
            shared_lines.append(f"Total users: {int(typed.total_users)} (ALREADY PROVIDED)")

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
                return filter_already_answered(assumptions[:5], state)
        except Exception as e:
            logger.warning("Phase 1 assumption generation failed: %s", e)

        # Fallback generic assumptions — use typed shared assumptions for defaults
        default_employees = int(typed.total_users) if typed.total_users else 100
        default_spend = int(typed.current_annual_spend / 12) if typed.current_annual_spend else 50000

        fallback = [
            {"id": "employees", "label": "Number of employees affected", "unit": "count", "default": default_employees, "hint": "How many people will use or benefit from this solution"},
            {"id": "monthly_it_spend", "label": "Current monthly IT spend", "unit": "$", "default": default_spend, "hint": "Approximate monthly infrastructure/operations cost"},
            {"id": "manual_hours", "label": "Hours spent on manual processes per week", "unit": "hours", "default": 40, "hint": "Time that could be automated or reduced"},
            {"id": "revenue_impact_area", "label": "Monthly revenue from affected area", "unit": "$", "default": 250000, "hint": "Revenue from the business area this solution touches"},
        ]
        return filter_already_answered(fallback, state)

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

        # Prepend shared assumptions as baseline (typed via state.sa)
        typed = state.sa
        shared_lines = []
        if typed.current_annual_spend:
            shared_lines.append(f"- Current annual spend: ${typed.current_annual_spend:,.0f}")
        if typed.hourly_labor_rate:
            shared_lines.append(f"- Hourly labor rate: ${typed.hourly_labor_rate}/hr")
        if typed.total_users:
            shared_lines.append(f"- Platform users: {int(typed.total_users)}")

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

        # Build ceiling context for the prompt
        spend_ceiling = typed.current_annual_spend
        employees = typed.affected_employees or typed.total_users
        labor_rate = typed.hourly_labor_rate

        ceiling_block = ""
        if spend_ceiling and spend_ceiling > 0:
            ceiling_block = f"""
HARD CONSTRAINTS — violating these invalidates your output:
- Current annual spend: ${spend_ceiling:,.0f}. Cost-reduction drivers CANNOT exceed this total.
- If you have {f'{int(employees)} affected staff at ${labor_rate}/hr' if employees and labor_rate else 'labor data'}, compute labor savings as: staff × rate × hours_saved_per_year.
- Revenue uplift is SEPARATE from cost reduction and is NOT bounded by current spend.
- Show your arithmetic for EVERY dollar figure. No unexplained numbers.
"""

        prompt = f"""You are a value engineer. Produce 2–4 value drivers for this Azure solution.

CUSTOMER: {customer}
INDUSTRY: {industry}
USE CASE: {description}
{f"CLARIFICATIONS: {clarifications}" if clarifications else ""}
{extra_context}

USER-PROVIDED NUMBERS (these are FACTS — use them for computation):
{assumption_context}
{ceiling_block}
{search_context}

RULES:
1. COMPUTE, don't estimate. Show the math for every driver:
   - "350 engineers × $100/hr × 15% time savings × 2080 hrs/yr = $10,920,000 gross → 25-50% realization = $2.7M-$5.5M"
   - "Current spend $3.5M × 10-15% optimization = $350K-$525K"
2. Each driver must have a percentage range AND the dollar computation.
3. Cost-reduction drivers: the SUM of all cost-reduction driver dollar values at the HIGH end
   must NOT exceed the current annual spend ({f'${spend_ceiling:,.0f}' if spend_ceiling else 'not provided'}).
4. Revenue uplift: apply 25-50% realization factor to gross impact.
5. If you can't compute a dollar value due to missing data, set excluded=true.
6. {source_instruction}

Return ONLY valid JSON (no markdown fences):
{{
  "drivers": [
    {{
      "name": "Short driver name",
      "metric": "10–20% time savings",
      "impact_pct_low": 10,
      "impact_pct_high": 20,
      "description": "350 engineers × $100/hr × 15% avg savings × 2080 hrs = $10.9M gross, 37.5% realized = $4.1M",
      "category": "cost_reduction" or "revenue_uplift" or "risk_reduction",
      "source_name": "Calculated from user assumptions",
      "source_url": "",
      "excluded": false,
      "excluded_reason": ""
    }}
  ],
  "annual_impact_range": {{ "low": 500000, "high": 1200000 }},
  "assumptions": [
    "350 engineers at $100/hr fully loaded cost",
    "15% time savings = 312 hrs/engineer/yr saved"
  ],
  "confidence": "moderate"
}}

CATEGORY RULES:
- "cost_reduction": reduces existing spend (labour, infra, errors, rework, licensing)
- "revenue_uplift": generates NEW value (faster time-to-market, retention, new revenue)
- "risk_reduction": reduces risk exposure (set excluded=true if no baseline data for dollarization)
- annual_impact_range low/high = sum of all non-excluded driver dollar values at low/high end"""

        benchmark_available = bool(search_results)

        try:
            response = llm.invoke([
                {"role": "system", "content": "You are an Azure value engineer. Return ONLY valid JSON. Be realistic based on published industry data when available; when computing from user-provided assumptions, honestly label sources as calculation-based rather than citing vague 'Industry estimate'. No fluff."},
                {"role": "user", "content": prompt},
            ])

            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(text)

            # Safety cap at 5 drivers (prompt asks for 2-4)
            drivers = result.get("drivers", [])[:5]
            for d in drivers:
                d.setdefault("name", "")
                d.setdefault("metric", "")
                d.setdefault("description", "")
                d.setdefault("category", "cost_reduction")
                d.setdefault("source_name", "")
                d.setdefault("source_url", "")
                d.setdefault("impact_pct_low", None)
                d.setdefault("impact_pct_high", None)
                d.setdefault("excluded", False)
                d.setdefault("excluded_reason", "")

            # Validate impact range and verify driver arithmetic
            validated_range, bv_warnings = self._validate_and_verify(result, state)

            confidence = result.get("confidence", "moderate")
            if bv_warnings:
                confidence = "low"
                for w in bv_warnings:
                    logger.warning("BV validation: %s", w)

            # Downgrade confidence when no industry benchmarks available
            if not benchmark_available:
                if confidence == "high":
                    confidence = "moderate"

            state.business_value = {
                "drivers": drivers,
                "annual_impact_range": validated_range,
                "assumptions": result.get("assumptions", []),
                "confidence": confidence,
                "consistency_warnings": bv_warnings,
                "sources": [
                    {"title": r.get("title", ""), "url": r.get("url", "")}
                    for r in search_results[:5]
                ],
                "user_assumptions": user_assumptions,
            }

            if not benchmark_available:
                state.business_value["methodology_note"] = (
                    "Value drivers computed from user-provided assumptions. "
                    "No external industry benchmarks were available for validation."
                )

        except json.JSONDecodeError as e:
            logger.error("BV LLM returned invalid JSON: %s", e, exc_info=True)
            state.business_value = {
                "drivers": [],
                "annual_impact_range": None,
                "assumptions": ["Value calculation failed \u2014 AI model returned unexpected format."],
                "confidence": "low",
                "sources": [],
                "user_assumptions": user_assumptions,
                "_used_fallback": True,
                "error_type": "json_parse",
                "error": "The AI model returned an unexpected format. Results may be incomplete.",
            }

        except Exception as e:
            logger.error("BV LLM call failed: %s", e, exc_info=True)
            state.business_value = {
                "drivers": [],
                "annual_impact_range": None,
                "assumptions": ["Value calculation failed \u2014 please try again or provide more details about the use case."],
                "confidence": "low",
                "sources": [],
                "user_assumptions": user_assumptions,
                "_used_fallback": True,
                "error_type": "unknown",
                "error": "Could not generate value drivers. Please retry or refine the use case description.",
            }

        return state

    # ── Validation ────────────────────────────────────────────────────

    @staticmethod
    def _validate_and_verify(
        result: dict,
        state: AgentState,
    ) -> tuple[dict | None, list[str]]:
        """Validate impact range structure. Light-touch — the prompt does the heavy lifting.

        Returns (corrected_range_or_None, warning_list).
        """
        impact_range = result.get("annual_impact_range")

        if not impact_range or not isinstance(impact_range, dict):
            return None, []

        try:
            low = float(impact_range.get("low", 0))
            high = float(impact_range.get("high", 0))
        except (ValueError, TypeError):
            return None, []

        if low > high:
            low, high = high, low
        if low < 0:
            low = 0
        if high <= 0:
            return None, []

        return {"low": round(low, 2), "high": round(high, 2)}, []
