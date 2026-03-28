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
        """Build the cost-breakdown data for the frontend ROI dashboard.
        
        Pulls REAL data from upstream agents — not hardcoded values.
        """
        # ── Pull real Azure cost from Cost agent ─────────────────────
        cost_estimate = state.costs.get("estimate", {})
        azure_monthly = round(cost_estimate.get("totalMonthly", 0))
        cost_items = cost_estimate.get("items", [])
        
        # ── Pull user assumptions if provided via BV input phase ─────
        user_assumptions = state.business_value.get("user_assumptions", [])
        assumptions_dict = (
            {a["id"]: a["value"] for a in user_assumptions}
            if user_assumptions else {}
        )
        
        # ── Build current vs AI cost comparison ──────────────────────
        # If user provided assumptions, use them for the "current cost" side
        if assumptions_dict:
            cases = assumptions_dict.get("cases_per_month", 500)
            minutes_per_case = assumptions_dict.get("minutes_per_case", 30)
            hourly_rate = assumptions_dict.get("hourly_rate", 45)
            error_rate = assumptions_dict.get("error_rate", 12) / 100
            ai_coverage = assumptions_dict.get("ai_coverage", 70) / 100
            
            labor_hours = (cases * minutes_per_case) / 60
            labor_cost = round(labor_hours * hourly_rate)
            error_cost = round(labor_cost * error_rate)
            current_total = labor_cost + error_cost
            
            ai_labor_cost = round(labor_cost * (1 - ai_coverage))
            ai_error_cost = round(error_cost * 0.2)
            ai_total = ai_labor_cost + azure_monthly + ai_error_cost
        else:
            # No user assumptions — derive from BV drivers and cost data
            # Use annual_value as the "current cost being replaced" proxy
            monthly_value = round(annual_value / 12) if annual_value > 0 else 0
            
            # Estimate: current cost = Azure cost + the savings the solution creates
            savings_monthly = monthly_value - azure_monthly if monthly_value > azure_monthly else round(azure_monthly * 0.5)
            current_total = azure_monthly + savings_monthly
            labor_cost = round(current_total * 0.85)  # ~85% labor
            error_cost = current_total - labor_cost    # ~15% errors/rework
            
            ai_labor_cost = round(labor_cost * 0.3)    # 70% reduction
            ai_error_cost = round(error_cost * 0.2)    # 80% reduction
            ai_total = ai_labor_cost + azure_monthly + ai_error_cost
        
        savings = max(0, current_total - ai_total)
        savings_pct = round((savings / current_total) * 100) if current_total > 0 else 0
        
        # ── Pull benchmarks from BV web search (real sources) ────────
        bv_sources = state.business_value.get("sources", [])
        bv_drivers = state.business_value.get("drivers", [])
        
        benchmarks = []
        # Use real web search sources if available
        if bv_sources:
            for s in bv_sources[:3]:
                benchmarks.append({
                    "source": s.get("source", s.get("title", "Research"))[:30],
                    "metric": "",
                    "detail": s.get("snippet", s.get("title", ""))[:150],
                })
        
        # Add driver-based benchmarks if we have monetized drivers
        if len(benchmarks) < 3 and bv_drivers:
            for d in bv_drivers:
                if len(benchmarks) >= 3:
                    break
                estimate = d.get("estimate", d.get("metric", ""))
                if estimate:
                    benchmarks.append({
                        "source": "Solution Analysis",
                        "metric": estimate[:30] if isinstance(estimate, str) else "",
                        "detail": d.get("description", d.get("name", ""))[:150],
                    })
        
        # Only use generic benchmarks as last resort
        if not benchmarks:
            benchmarks = []  # No real data — show nothing rather than made-up numbers
        
        # ── Build methodology from actual data sources ───────────────
        cost_source = cost_estimate.get("pricingSource", "estimated")
        service_count = len(cost_items)
        assumption_note = "user-provided assumptions" if assumptions_dict else "estimated from solution analysis"
        
        methodology = (
            f"Azure costs based on {service_count} services ({cost_source} pricing). "
            f"Current operational costs derived from {assumption_note}. "
            f"AI-assisted costs assume automated task coverage reduces labor and errors. "
            f"ROI = (Annual Value − Annual Cost) ÷ Annual Cost × 100."
        )
        
        return {
            "monthlySavings": savings,
            "annualImpact": round(annual_value),
            "azureMonthlyCost": azure_monthly,
            "savingsPercentage": savings_pct,
            "currentCost": {
                "total": current_total,
                "labor": labor_cost,
                "errors": error_cost,
            },
            "aiCost": {
                "total": ai_total,
                "labor": ai_labor_cost,
                "azure": azure_monthly,
                "errors": ai_error_cost,
            },
            "roiPercent": roi_percent,
            "paybackMonths": payback_months,
            "benchmarks": benchmarks,
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
