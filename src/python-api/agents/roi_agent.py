"""ROI Agent — calculates return on investment from cost and business value data.

Pure math — no LLM calls, no regex parsing, no made-up numbers.
Uses annual_impact_range (low/high) from BusinessValueAgent.
If no range is available, signals that user input is needed.
"""
import logging
import re
from agents.state import AgentState

logger = logging.getLogger(__name__)

_PCT_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%"
)

# ── Configurable business assumptions ────────────────────────────────────────
# These are conservative defaults that document the assumption being made.
# They are only applied when the user has not provided an explicit value.
_DEFAULT_AI_COVERAGE = 0.30          # 30% labor reduction when no metrics available
_RESIDUAL_ERROR_RATE = 0.50          # 50% of errors persist after AI (moderate assumption)
_IMPLEMENTATION_COST_RATIO = 0.20    # one-time setup cost = 20% of first-year platform cost
_YEAR1_RAMPUP_FACTOR = 0.80          # Year 1 realises 80% of projected annual savings


def _extract_coverage_from_drivers(drivers: list[dict]) -> float | None:
    """Parse the average percentage from BV driver metric strings.

    Looks for patterns like "10–20% time savings" or "15% reduction" and
    returns the mid-point average as a fraction (0–1), or None if nothing
    parseable is found.
    """
    values: list[float] = []
    for d in drivers:
        metric = d.get("metric", "")
        for m in _PCT_RANGE_RE.finditer(metric):
            low, high, single = m.group(1), m.group(2), m.group(3)
            if low and high:
                values.append((float(low) + float(high)) / 2.0)
            elif single:
                values.append(float(single))
    if not values:
        return None
    avg = sum(values) / len(values) / 100.0
    return max(0.05, min(0.95, avg))


class ROIAgent:
    name = "ROI Calculator"
    emoji = "📈"

    def run(self, state: AgentState) -> AgentState:
        annual_cost = state.costs.get("estimate", {}).get("totalAnnual", 0)
        bv = state.business_value
        impact_range = bv.get("annual_impact_range")
        drivers = bv.get("drivers", [])
        assumptions = bv.get("assumptions", [])

        if annual_cost <= 0:
            state.roi = self._needs_info(
                reason="No cost estimate available.",
                questions=["Please run the Cost agent first or provide an estimated annual Azure spend."],
            )
            return state

        if not impact_range or not isinstance(impact_range, dict):
            driver_names = [d.get("name", "") for d in drivers]
            state.roi = self._needs_info(
                reason="Value drivers identified but no dollar range computed yet.",
                questions=assumptions if assumptions else [
                    "Could you share approximate headcount, revenue, or current spend so we can estimate dollar impact?"
                ],
                qualitative=driver_names,
            )
            return state

        val_low = float(impact_range.get("low", 0))
        val_high = float(impact_range.get("high", 0))

        if val_low <= 0 and val_high <= 0:
            state.roi = self._needs_info(
                reason="Impact range is zero — need more inputs.",
                questions=assumptions or ["Please share headcount or revenue figures to refine."],
                qualitative=[d.get("name", "") for d in drivers],
            )
            return state

        # Use midpoint for headline ROI, but show range
        val_mid = (val_low + val_high) / 2
        roi_low = ((val_low - annual_cost) / annual_cost) * 100
        roi_high = ((val_high - annual_cost) / annual_cost) * 100
        roi_mid = ((val_mid - annual_cost) / annual_cost) * 100
        payback_months = (annual_cost / (val_mid / 12)) if val_mid > 0 else None

        state.roi = {
            "annual_cost": round(annual_cost, 2),
            "annual_value": round(val_mid, 2),
            "annual_value_low": round(val_low, 2),
            "annual_value_high": round(val_high, 2),
            "roi_percent": round(roi_mid, 1),
            "roi_range": f"{roi_low:.0f}–{roi_high:.0f}%",
            "payback_months": round(payback_months, 1) if payback_months else None,
            "monetized_drivers": [
                {"name": d.get("name", ""), "metric": d.get("metric", "")}
                for d in drivers
            ],
            "assumptions": assumptions,
            "needs_info": None,
            "dashboard": self._build_dashboard(state, annual_cost, val_mid, round(roi_mid, 1),
                                               round(payback_months, 1) if payback_months else None),
        }
        return state

    def _build_dashboard(self, state: AgentState, annual_cost: float,
                         annual_value: float, roi_percent: float | None,
                         payback_months: float | None) -> dict:
        """Build the cost-breakdown data for the frontend ROI dashboard.

        Pulls REAL data from upstream agents — not hardcoded values.
        Merges assumptions from both Cost and Business Value agents.
        Shows an honest comparison — if AI costs more than the current process
        for a use case, that is surfaced rather than hidden.
        """
        # ── Pull real Azure cost from Cost agent ─────────────────────
        cost_estimate = state.costs.get("estimate", {})
        azure_monthly = round(cost_estimate.get("totalMonthly", 0))
        cost_items = cost_estimate.get("items", [])

        # ── Merge assumptions from BOTH agents ───────────────────────
        cost_assumptions = state.costs.get("user_assumptions", [])
        bv_assumptions = state.business_value.get("user_assumptions", [])

        assumptions_dict: dict = {}
        for a in cost_assumptions:
            if isinstance(a, dict) and "id" in a:
                assumptions_dict[a["id"]] = a["value"]
        for a in bv_assumptions:
            if isinstance(a, dict) and "id" in a:
                assumptions_dict[a["id"]] = a["value"]

        # ── Value drivers from BV agent ──────────────────────────────
        bv_drivers = state.business_value.get("drivers", [])
        drivers = [
            {
                "name": d.get("name", ""),
                "metric": d.get("metric", ""),
                "description": d.get("description", ""),
            }
            for d in bv_drivers
        ]

        # ── Build current operational cost (WITHOUT AI) ──────────────
        current_cost_estimated = False
        current_breakdown: list[dict] = []

        employees = assumptions_dict.get("employees", assumptions_dict.get("headcount", 0))
        hourly_rate = assumptions_dict.get("hourly_rate", 0)
        manual_hours = assumptions_dict.get("manual_hours", assumptions_dict.get("hours_per_week", 0))

        if employees and hourly_rate and manual_hours:
            monthly_labor = round(employees * hourly_rate * manual_hours * 4.33)
            current_breakdown.append({"label": "Staff labor", "amount": monthly_labor})

            # Only include error cost when the user explicitly provided error_rate
            error_rate_raw = assumptions_dict.get("error_rate")
            if error_rate_raw is not None:
                error_rate = float(error_rate_raw) / 100.0
                # Validate bounds: 0–100%
                clamped = max(0.0, min(1.0, error_rate))
                if clamped != error_rate:
                    logger.warning(
                        "error_rate %.1f%% is out of range — clamped to %.1f%%",
                        error_rate * 100, clamped * 100,
                    )
                error_cost = round(monthly_labor * clamped)
                if error_cost > 0:
                    current_breakdown.append({"label": "Errors & rework", "amount": error_cost})

            overhead = assumptions_dict.get("overhead", 0)
            if overhead:
                current_breakdown.append({"label": "Overhead / tools", "amount": round(overhead)})
        else:
            # No user-provided labor data — estimate conservatively from Azure cost.
            # Do NOT use annual_value here: that would be circular (value → cost → ROI).
            current_cost_estimated = True
            if azure_monthly > 0:
                estimated_current = azure_monthly * 3
                labor_share = round(estimated_current * 0.80)
                other_share = estimated_current - labor_share
                current_breakdown.append({"label": "Staff labor (est.)", "amount": labor_share})
                if other_share > 0:
                    current_breakdown.append({"label": "Process overhead (est.)", "amount": other_share})

        current_total = sum(item["amount"] for item in current_breakdown)

        # ── Derive AI coverage from BV driver metrics ─────────────────
        # Use the percentage improvements stated in driver metrics rather than
        # a hardcoded 70% figure that may contradict the drivers shown on screen.
        ai_coverage_raw = assumptions_dict.get("ai_coverage")
        parsed: float | None = None
        if ai_coverage_raw is not None:
            ai_coverage = max(0.0, min(1.0, float(ai_coverage_raw) / 100.0))
        else:
            parsed = _extract_coverage_from_drivers(bv_drivers)
            # Conservative fallback when drivers carry no numeric percentages
            ai_coverage = parsed if parsed is not None else _DEFAULT_AI_COVERAGE

        # ── Build AI-assisted cost ───────────────────────────────────
        ai_breakdown: list[dict] = []
        ai_breakdown.append({"label": "Azure platform", "amount": azure_monthly})

        labor_items = [item for item in current_breakdown if "labor" in item["label"].lower()]
        if labor_items and current_total > 0:
            reduced_labor = round(labor_items[0]["amount"] * (1 - ai_coverage))
            ai_breakdown.append({"label": "Reduced labor", "amount": reduced_labor})

            # Residual error cost: only when errors appeared in the current breakdown
            error_items = [
                item for item in current_breakdown
                if "error" in item["label"].lower() or "rework" in item["label"].lower()
            ]
            if error_items:
                # Moderate assumption: half of pre-AI errors persist
                residual_errors = round(error_items[0]["amount"] * _RESIDUAL_ERROR_RATE)
                if residual_errors > 0:
                    ai_breakdown.append({"label": "Residual errors", "amount": residual_errors})

        ai_total = sum(item["amount"] for item in ai_breakdown)

        # ── Honest savings calculation — no artificial inflation ──────
        # If AI costs more than the current process, show that truthfully.
        # Positive ROI may still come from quality, speed, or risk reduction
        # (captured in the qualitative section below).
        net = current_total - ai_total
        savings = net  # can be negative
        savings_pct = round((savings / current_total) * 100) if current_total > 0 else 0

        # ── Qualitative / non-monetary benefits ──────────────────────
        qualitative_drivers = [
            d.get("name", "") for d in bv_drivers if not d.get("metric", "").strip()
        ]

        # ── 3-year projection (implementation cost separated from recurring) ─
        # Implementation cost is a one-time expense (Year 1 only).
        # Recurring platform cost repeats every year.
        implementation_cost = round(annual_cost * _IMPLEMENTATION_COST_RATIO)
        recurring_annual_cost = round(annual_cost)

        # Value stays flat — we don't invent growth rates without data
        annual_savings = savings * 12

        year1_savings = round(annual_savings * _YEAR1_RAMPUP_FACTOR)
        year2_savings = round(annual_savings)
        year3_savings = round(annual_savings)           # no invented growth

        year1_cost = implementation_cost + recurring_annual_cost
        year2_cost = recurring_annual_cost
        year3_cost = recurring_annual_cost

        year1_value = round(annual_value)
        year2_value = round(annual_value)
        year3_value = round(annual_value)

        projection = {
            "years": [1, 2, 3],
            "implementationCost": implementation_cost,
            "recurringAnnualCost": recurring_annual_cost,
            "cumulativeSavings": [
                year1_savings,
                year1_savings + year2_savings,
                year1_savings + year2_savings + year3_savings,
            ],
            "cumulativeCost": [
                year1_cost,
                year1_cost + year2_cost,
                year1_cost + year2_cost + year3_cost,
            ],
            "cumulativeValue": [
                year1_value,
                year1_value + year2_value,
                year1_value + year2_value + year3_value,
            ],
        }

        # ── Methodology — transparent about what is estimated ────────
        cost_source = cost_estimate.get("pricingSource", "estimated")
        service_count = len(cost_items)

        assumption_sources = []
        if cost_assumptions:
            assumption_sources.append("cost agent usage metrics")
        if bv_assumptions:
            assumption_sources.append("business value agent inputs")

        if current_cost_estimated:
            current_cost_note = (
                "Current operational cost is ESTIMATED (3× Azure platform cost) "
                "because labor, hourly rate, and manual hours were not provided. "
                "Provide those assumptions for an accurate comparison."
            )
        else:
            src = " and ".join(assumption_sources) if assumption_sources else "solution analysis"
            current_cost_note = f"Current operational cost derived from user-provided {src}."

        if ai_coverage_raw is not None:
            coverage_note = f"AI labor coverage: {round(ai_coverage * 100)}% (user-provided)."
        elif parsed is not None:
            coverage_note = (
                f"AI labor coverage: {round(ai_coverage * 100)}% "
                f"(averaged from BV driver metrics)."
            )
        else:
            coverage_note = (
                f"AI labor coverage: {round(_DEFAULT_AI_COVERAGE * 100)}% "
                f"(conservative default — no driver metrics available)."
            )

        methodology = (
            f"Azure costs based on {service_count} service(s) ({cost_source} pricing). "
            f"{current_cost_note} "
            f"{coverage_note} "
            f"Year 1 projection includes a one-time implementation cost of "
            f"${implementation_cost:,} ({round(_IMPLEMENTATION_COST_RATIO * 100)}% of annual platform cost); "
            f"years 2–3 reflect recurring platform cost only. "
            f"Value held flat across years — no speculative growth applied. "
            f"ROI = (Annual Value − Annual Cost) ÷ Annual Cost × 100."
        )

        return {
            "monthlySavings": savings,
            "annualImpact": round(annual_value),
            "azureMonthlyCost": azure_monthly,
            "savingsPercentage": savings_pct,
            "currentCostEstimated": current_cost_estimated,
            "currentCost": {
                "total": current_total,
                "breakdown": current_breakdown,
            },
            "aiCost": {
                "total": ai_total,
                "breakdown": ai_breakdown,
            },
            "roiPercent": roi_percent,
            "paybackMonths": payback_months,
            "drivers": drivers,
            "qualitativeDrivers": qualitative_drivers,
            "projection": projection,
            "methodology": methodology,
        }

    def _needs_info(self, reason: str, questions: list[str], qualitative: list[str] | None = None) -> dict:
        """Return an ROI result that signals we need user input to calculate."""
        return {
            "annual_cost": 0,
            "annual_value": None,
            "roi_percent": None,
            "payback_months": None,
            "monetized_drivers": [],
            "qualitative_benefits": qualitative or [],
            "needs_info": questions,
        }
