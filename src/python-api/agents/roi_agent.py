"""ROI Agent — calculates return on investment from cost and business value data.

Pure math — no LLM calls, no regex parsing, no made-up numbers.
Uses annual_impact_range (low/high) from BusinessValueAgent.
If no range is available, signals that user input is needed.
"""
from agents.state import AgentState


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
        """Build the cost-breakdown data for the frontend ROI dashboard."""
        user_assumptions = state.business_value.get("user_assumptions", [])
        assumptions_dict = (
            {a["id"]: a["value"] for a in user_assumptions}
            if user_assumptions else {}
        )

        cases = assumptions_dict.get("cases_per_month", 500)
        minutes_per_case = assumptions_dict.get("minutes_per_case", 30)
        hourly_rate = assumptions_dict.get("hourly_rate", 45)
        error_rate = assumptions_dict.get("error_rate", 12) / 100
        ai_coverage = assumptions_dict.get("ai_coverage", 70) / 100

        # Current cost breakdown
        labor_hours = (cases * minutes_per_case) / 60
        labor_cost = round(labor_hours * hourly_rate)
        error_cost = round(labor_cost * error_rate)
        current_total = labor_cost + error_cost

        # AI-assisted cost breakdown
        ai_labor_cost = round(labor_cost * (1 - ai_coverage))
        azure_cost = round(state.costs.get("estimate", {}).get("totalMonthly", 0))
        ai_error_cost = round(error_cost * 0.2)  # AI reduces errors by ~80%
        ai_total = ai_labor_cost + azure_cost + ai_error_cost

        savings = current_total - ai_total
        savings_pct = round((savings / current_total) * 100) if current_total > 0 else 0

        return {
            "monthlySavings": savings,
            "annualImpact": round(annual_value),
            "azureMonthlyCost": azure_cost,
            "savingsPercentage": savings_pct,
            "currentCost": {
                "total": current_total,
                "labor": labor_cost,
                "errors": error_cost,
            },
            "aiCost": {
                "total": ai_total,
                "labor": ai_labor_cost,
                "azure": azure_cost,
                "errors": ai_error_cost,
            },
            "roiPercent": roi_percent,
            "paybackMonths": payback_months,
            "benchmarks": [
                {
                    "source": "Forrester TEI",
                    "metric": "327% ROI",
                    "detail": "Microsoft Foundry delivers 327% ROI over 3 years with <6 months payback.",
                },
                {
                    "source": "McKinsey",
                    "metric": "60-70%",
                    "detail": "60-70% of worker activities automatable by AI agents; avg 35% operational cost reduction.",
                },
                {
                    "source": "Gartner",
                    "metric": "15-23%",
                    "detail": "GenAI early adopters report 15% cost savings and 23% productivity improvement.",
                },
            ],
            "methodology": (
                "Current cost = cases × minutes ÷ 60 × hourly rate + rework overhead. "
                "AI-assisted cost = remaining human effort after AI task coverage + Azure platform + reduced rework."
            ),
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
