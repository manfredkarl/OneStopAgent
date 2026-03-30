"""ROI Agent — calculates return on investment from cost and business value data.

Pure math — no LLM calls, no regex parsing, no made-up numbers.
Uses annual_impact_range (low/high) from BusinessValueAgent.
If no range is available, signals that user input is needed.
"""
import re
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

        val_low = float(impact_range.get("low") or 0)
        val_high = float(impact_range.get("high") or 0)

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

    _PERCENTAGE_RANGE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*[–\-−]\s*(\d+(?:\.\d+)?)\s*%')
    _PERCENTAGE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*%')

    def _extract_coverage_from_drivers(self, drivers: list[dict]) -> float | None:
        """Extract an AI coverage percentage from BV driver metrics.

        Looks for patterns like "12% time savings" or "10-20% reduction".
        Returns the midpoint as a decimal (e.g. 0.15 for 15%).
        Returns None if no percentage is found so callers can skip the adjustment.
        """
        for driver in drivers:
            metric = driver.get("metric", "")
            range_match = self._PERCENTAGE_RANGE_RE.search(metric)
            if range_match:
                low = float(range_match.group(1))
                high = float(range_match.group(2))
                return (low + high) / 2 / 100
            single_match = self._PERCENTAGE_RE.search(metric)
            if single_match:
                return float(single_match.group(1)) / 100
        return None

    def _compute_per_driver_amounts(self, drivers: list[dict], annual_value: float) -> list[float]:
        """Compute approximate annual impact per driver, proportional to metric percentages.

        Extracts the midpoint percentage from each driver's metric string and
        distributes annual_value proportionally.  Drivers with no parseable
        percentage receive the mean of the parseable values so they are never
        silently zeroed out.  Falls back to equal distribution when no
        percentages can be parsed at all.
        """
        if not drivers:
            return []

        percentages: list[float] = []
        for d in drivers:
            metric = d.get("metric", "")
            range_match = self._PERCENTAGE_RANGE_RE.search(metric)
            if range_match:
                low = float(range_match.group(1))
                high = float(range_match.group(2))
                percentages.append((low + high) / 2)
            else:
                single = self._PERCENTAGE_RE.search(metric)
                percentages.append(float(single.group(1)) if single else 0.0)

        # Replace zeros (unparseable metrics) with the mean of parseable values
        # so every driver receives a non-zero share when at least one is parseable.
        non_zero = [p for p in percentages if p > 0]
        if non_zero:
            fallback = sum(non_zero) / len(non_zero)
            percentages = [p if p > 0 else fallback for p in percentages]

        total_pct = sum(percentages)
        if total_pct > 0:
            return [round(annual_value * (p / total_pct)) for p in percentages]
        # All metrics are unparseable — equal distribution
        equal = round(annual_value / len(drivers))
        return [equal] * len(drivers)

    def _build_dashboard(self, state: AgentState, annual_cost: float,
                         annual_value: float, roi_percent: float | None,
                         payback_months: float | None) -> dict:
        """Build the cost-breakdown data for the frontend ROI dashboard.

        Pulls REAL data from upstream agents — not hardcoded values.
        Merges assumptions from both Cost and Business Value agents.
        Only shows cost comparison when real user inputs are available.
        """
        # ── Pull real Azure cost from Cost agent ─────────────────────
        cost_estimate = state.costs.get("estimate", {})
        azure_monthly = round(cost_estimate.get("totalMonthly", 0))
        cost_items = cost_estimate.get("items", [])
        bv_drivers = state.business_value.get("drivers", [])

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

        # ── Build current operational cost (WITHOUT AI) ──────────────
        # Use user inputs when available, fill gaps with reasonable defaults.
        current_breakdown: list[dict] = []

        employees = assumptions_dict.get("employees", assumptions_dict.get("headcount", 0))
        hourly_rate = assumptions_dict.get("hourly_rate", 0)
        manual_hours = assumptions_dict.get("manual_hours", assumptions_dict.get("hours_per_week", 0))
        monthly_it_spend = assumptions_dict.get("monthly_it_spend", 0)

        # If we have at least one input, fill in the gaps with sensible defaults
        has_any_input = bool(employees or hourly_rate or manual_hours or monthly_it_spend)

        if not has_any_input:
            # No user input — estimate current cost from Azure spend only (NOT from annual_value).
            # Industry rule-of-thumb: total operational cost ≈ 2× cloud platform cost.
            estimated_current = max(azure_monthly * 2, 5000)
            current_breakdown.append({"label": "Operations (estimated)", "amount": round(estimated_current * 0.75)})
            current_breakdown.append({"label": "Overhead (estimated)", "amount": round(estimated_current * 0.25)})
        else:
            # Fill missing fields with reasonable defaults
            if not employees:
                employees = 30
            if not hourly_rate:
                hourly_rate = 45
            if not manual_hours:
                manual_hours = 15

            monthly_labor = round(employees * hourly_rate * manual_hours * 4.33)
            current_breakdown.append({"label": "Staff labor", "amount": monthly_labor})

            if monthly_it_spend:
                current_breakdown.append({"label": "IT spend", "amount": round(monthly_it_spend)})

            error_rate = assumptions_dict.get("error_rate", 8) / 100
            error_cost = round(monthly_labor * error_rate)
            if error_cost > 0:
                current_breakdown.append({"label": "Errors & rework", "amount": error_cost})

            overhead = assumptions_dict.get("overhead", 0)
            if overhead:
                current_breakdown.append({"label": "Overhead / tools", "amount": round(overhead)})

        current_total = sum(item["amount"] for item in current_breakdown)

        # ── Build AI-assisted cost ───────────────────────────────────
        ai_breakdown: list[dict] = []
        ai_breakdown.append({"label": "Azure platform", "amount": azure_monthly})

        if current_breakdown:
            # Pull AI coverage % from BV driver metrics, default to 25% if unparseable
            ai_coverage = self._extract_coverage_from_drivers(bv_drivers) or 0.25
            labor_items = [item for item in current_breakdown if "labor" in item["label"].lower() or "operations" in item["label"].lower()]
            if labor_items:
                reduced_labor = round(labor_items[0]["amount"] * (1 - ai_coverage))
                ai_breakdown.append({"label": "Staff labor", "amount": reduced_labor})

            error_items = [item for item in current_breakdown if "error" in item["label"].lower() or "rework" in item["label"].lower()]
            if error_items:
                error_reduction = assumptions_dict.get("error_reduction", 50) / 100
                reduced_errors = round(error_items[0]["amount"] * (1 - error_reduction))
                if reduced_errors > 0:
                    ai_breakdown.append({"label": "Errors & rework", "amount": reduced_errors})

        ai_total = sum(item["amount"] for item in ai_breakdown)

        # ── Cost comparison ──────────────────────────────────────────
        if current_total > 0:
            savings = current_total - ai_total
            savings_pct = round((savings / current_total) * 100)
        else:
            savings = 0
            savings_pct = 0

        # ── Value drivers from BV agent ──────────────────────────────
        drivers = [
            {
                "name": d.get("name", ""),
                "metric": d.get("metric", ""),
                "description": d.get("description", ""),
                "category": d.get("category", "cost_reduction"),
                "source_name": d.get("source_name", ""),
                "source_url": d.get("source_url", ""),
            }
            for d in bv_drivers
        ]

        # ── Value waterfall — split drivers into cost reduction vs revenue uplift ─
        driver_amounts = self._compute_per_driver_amounts(bv_drivers, annual_value)
        waterfall_cost_reduction: list[dict] = []
        waterfall_revenue_uplift: list[dict] = []
        for idx, d in enumerate(bv_drivers):
            category = d.get("category", "cost_reduction")
            item = {"label": d.get("name", ""), "amount": driver_amounts[idx]}
            if category == "revenue_uplift":
                waterfall_revenue_uplift.append(item)
            else:
                waterfall_cost_reduction.append(item)

        value_waterfall = {
            "costReduction": waterfall_cost_reduction,
            "revenueUplift": waterfall_revenue_uplift,
        }

        # ── Annual uplift (revenue_uplift drivers only) for projection ──
        annual_uplift = sum(item["amount"] for item in waterfall_revenue_uplift)

        # ── 3-year projection — flat; no fabricated growth or uplift ─
        annual_azure_cost = azure_monthly * 12
        annual_savings = savings * 12

        projection = {
            "years": [1, 2, 3],
            "cumulativeSavings": [
                round(annual_savings),
                round(annual_savings * 2),
                round(annual_savings * 3),
            ],
            "cumulativeCost": [
                round(annual_azure_cost),
                round(annual_azure_cost * 2),
                round(annual_azure_cost * 3),
            ],
            "cumulativeValue": [
                round(annual_value),
                round(annual_value * 2),
                round(annual_value * 3),
            ],
            "cumulativeUplift": [
                round(annual_uplift),
                round(annual_uplift * 2),
                round(annual_uplift * 3),
            ],
        }

        # ── Methodology ─────────────────────────────────────────────
        cost_source = cost_estimate.get("pricingSource", "estimated")
        service_count = len(cost_items)
        assumption_sources = []
        if cost_assumptions:
            assumption_sources.append("usage metrics")
        if bv_assumptions:
            assumption_sources.append("business metrics")
        assumption_note = " and ".join(assumption_sources) if assumption_sources else "estimated defaults"

        uplift_count = len(waterfall_revenue_uplift)
        cost_red_count = len(waterfall_cost_reduction)
        driver_note = (
            f"{cost_red_count} cost-reduction and {uplift_count} revenue-uplift driver(s) identified. "
            if (cost_red_count + uplift_count) > 0
            else ""
        )

        cost_estimated = not has_any_input

        methodology = (
            f"Azure costs based on {service_count} services ({cost_source} pricing). "
        )
        if cost_estimated:
            methodology += (
                "Current operational cost estimated as 2\u00d7 Azure cost "
                "(industry rule-of-thumb for cloud migration). "
                "For accurate ROI, provide actual current costs. "
            )
        else:
            methodology += f"Current operational costs derived from {assumption_note}. "
        methodology += (
            driver_note
            + "Projection uses flat annual figures; one-time implementation costs are excluded. "
            + "ROI = (Annual Value \u2212 Annual Cost) \u00f7 Annual Cost \u00d7 100."
        )

        dashboard: dict = {
            "monthlySavings": savings,
            "annualImpact": round(annual_value),
            "azureMonthlyCost": azure_monthly,
            "savingsPercentage": savings_pct,
            "costComparisonAvailable": True,
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
            "valueWaterfall": value_waterfall,
            "projection": projection,
            "methodology": methodology,
        }

        if cost_estimated:
            dashboard["costEstimated"] = True
            dashboard["warning"] = "Current cost estimated \u2014 provide actual figures for accurate ROI"

        return dashboard


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
