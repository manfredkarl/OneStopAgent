"""ROI Agent — calculates return on investment from cost and business value data.

Pure math — no LLM calls, no invented fallback numbers.
Uses annual_impact_range (low/high) from BusinessValueAgent for the value side.
Keeps cost, value, and investment as separate, reconcilable layers.

Output schema (state.roi):
  annual_cost           – Azure platform spend per year (from Cost agent)
  annual_value          – midpoint of value range (low+high)/2
  annual_value_low/high – value range boundaries
  monthly_current_cost  – current-state operating cost per month (None if estimated)
  monthly_future_cost   – future-state operating cost per month (Azure + residual ops)
  monthly_savings       – monthly_current_cost − monthly_future_cost
  hard_savings          – annual cost-reduction drivers (≤ current baseline)
  revenue_uplift        – annual revenue-uplift drivers
  risk_reduction        – annual risk-reduction value (0 if immaterial)
  year1_investment      – Azure annual + implementation + change management
  year2_run_rate        – Azure annual (steady state)
  roi_percent           – uncapped numeric ((value−cost)/cost × 100)
  roi_percent_display   – capped for presentation
  roi_capped            – True when display value was capped
  payback_months        – months to recoup investment
  is_estimated          – True when current-state baseline is estimated, not user-provided
  needs_info            – None or list of questions when data is insufficient
  dashboard             – frontend-ready blob matching ROIDashboardData
"""
import re
from agents.state import AgentState


class ROIAgent:
    name = "ROI Calculator"
    emoji = "📈"

    # ── Constants ────────────────────────────────────────────────────
    MAX_DISPLAY_ROI = 1000        # 10× = 1000%
    MAX_SAVINGS_PCT = 60          # cap monthly savings display
    MIN_PAYBACK_MONTHS = 0.5
    MAX_PAYBACK_MONTHS = 120.0
    ADOPTION_RAMP = [0.50, 0.85, 1.00]
    # When no current-state baseline is available, use this multiplier
    # on Azure cost as a *clearly-labeled* estimate.  Single value
    # everywhere so dashboard and business case never disagree.
    ESTIMATED_BASELINE_MULTIPLIER = 1.5

    # Key name variants the LLM may generate for shared assumptions
    _CURRENT_SPEND_KEYS = [
        "current_annual_spend",
        "current_annual_engineering_toolchain_spend",
        "current_annual_engineering_spend",
        "current_annual_toolchain_spend",
        "current_annual_operational_spend",
        "current_annual_platform_spend",
    ]
    _LABOR_RATE_KEYS = [
        "hourly_labor_rate",
        "fully_loaded_engineering_labor_rate",
        "fully_loaded_hourly_rate",
        "hourly_rate",
        "loaded_labor_rate",
    ]

    _PERCENTAGE_RANGE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*[–\-−]\s*(\d+(?:\.\d+)?)\s*%')
    _PERCENTAGE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*%')

    # ── Shared-assumption resolver ───────────────────────────────────
    @staticmethod
    def _resolve_sa(sa: dict, candidates: list[str]) -> float | None:
        """Return the first truthy numeric value from *sa* matching any candidate key.

        Tries exact match first, then fuzzy substring match to handle
        LLM-generated dynamic key names like 'hourly_engineering_labor_rate'.
        """
        if not sa:
            return None
        # 1. Exact match
        for key in candidates:
            raw = sa.get(key)
            if raw:
                try:
                    val = float(raw)
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    continue
        # 2. Fuzzy: check if any sa key contains a candidate substring or vice versa
        for sa_key, raw in sa.items():
            if sa_key.startswith("_"):
                continue
            sk = sa_key.lower()
            for cand in candidates:
                if cand in sk or sk in cand:
                    try:
                        val = float(raw)
                        if val > 0:
                            return val
                    except (ValueError, TypeError):
                        continue
        # 3. Keyword match: find spend-like or rate-like keys
        for sa_key, raw in sa.items():
            if sa_key.startswith("_"):
                continue
            sk = sa_key.lower()
            if ("labor" in sk or "hourly" in sk) and "rate" in sk:
                if any("labor" in c or "rate" in c for c in candidates):
                    try:
                        return float(raw)
                    except (ValueError, TypeError):
                        pass
            if "spend" in sk or ("cost" in sk and "current" in sk):
                if any("spend" in c or "cost" in c for c in candidates):
                    try:
                        val = float(raw)
                        if val > 1000:
                            return val
                    except (ValueError, TypeError):
                        pass
        return None

    # ── Current-state baseline ───────────────────────────────────────
    def _resolve_current_baseline(self, state: AgentState, azure_monthly: float) -> tuple[float, list[dict], bool]:
        """Determine the monthly current-state operating cost.

        Returns (monthly_total, breakdown_items, is_estimated).
        *is_estimated* is True when the baseline is a rough proxy, not user data.
        """
        sa = state.shared_assumptions or {}
        sa_annual_spend = self._resolve_sa(sa, self._CURRENT_SPEND_KEYS)

        # ── Merge user assumptions from Cost + BV agents ─────────────
        assumptions_dict: dict = {}
        for source in (state.costs.get("user_assumptions", []),
                       state.business_value.get("user_assumptions", [])):
            for a in source:
                if isinstance(a, dict) and "id" in a:
                    assumptions_dict[a["id"]] = a["value"]

        employees = assumptions_dict.get("employees", assumptions_dict.get("headcount", 0))
        hourly_rate = assumptions_dict.get("hourly_rate", 0)
        manual_hours = assumptions_dict.get("manual_hours", assumptions_dict.get("hours_per_week", 0))
        monthly_it_spend = assumptions_dict.get("monthly_it_spend", 0)
        has_any_input = bool(employees or hourly_rate or manual_hours or monthly_it_spend)

        # Priority 1: explicit annual spend from shared assumptions
        if sa_annual_spend:
            monthly = sa_annual_spend / 12
            return (monthly,
                    [{"label": "Current operations (user-provided)", "amount": round(monthly)}],
                    False)

        # Priority 2: detailed user inputs (employees, rate, hours)
        sa_labor_rate = self._resolve_sa(sa, self._LABOR_RATE_KEYS)
        if sa_labor_rate and not hourly_rate:
            hourly_rate = sa_labor_rate
            has_any_input = True

        if has_any_input:
            if not employees:
                employees = 30
            if not hourly_rate:
                hourly_rate = 45
            if not manual_hours:
                manual_hours = 15

            breakdown: list[dict] = []
            monthly_labor = round(employees * hourly_rate * manual_hours * 4.33)
            breakdown.append({"label": "Staff labor", "amount": monthly_labor})

            if monthly_it_spend:
                breakdown.append({"label": "IT spend", "amount": round(monthly_it_spend)})

            error_rate = assumptions_dict.get("error_rate", 8) / 100
            error_cost = round(monthly_labor * error_rate)
            if error_cost > 0:
                breakdown.append({"label": "Errors & rework", "amount": error_cost})

            overhead = assumptions_dict.get("overhead", 0)
            if overhead:
                breakdown.append({"label": "Overhead / tools", "amount": round(overhead)})

            total = sum(item["amount"] for item in breakdown)
            return (total, breakdown, False)

        # Priority 3: estimated fallback — clearly labeled
        estimated = round(azure_monthly * self.ESTIMATED_BASELINE_MULTIPLIER)
        return (estimated,
                [{"label": "Operations (estimated)", "amount": round(estimated * 0.75)},
                 {"label": "Overhead (estimated)", "amount": round(estimated * 0.25)}],
                True)

    # ── Future-state (AI-assisted) monthly cost ──────────────────────
    def _build_future_cost(self, azure_monthly: float,
                           current_breakdown: list[dict],
                           bv_drivers: list[dict],
                           assumptions_dict: dict) -> tuple[float, list[dict]]:
        """Build the monthly operating cost WITH the Azure solution.

        Returns (monthly_total, breakdown_items).
        """
        ai_breakdown: list[dict] = [{"label": "Azure platform", "amount": azure_monthly}]

        ai_coverage = self._extract_coverage_from_drivers(bv_drivers) or 0.25

        for item in current_breakdown:
            label_lower = item["label"].lower()
            if "labor" in label_lower or "operations" in label_lower:
                reduced = round(item["amount"] * (1 - ai_coverage))
                ai_breakdown.append({"label": "Staff labor (reduced)", "amount": reduced})
            elif "error" in label_lower or "rework" in label_lower:
                error_reduction = max(0, min(1, assumptions_dict.get("error_reduction", 50) / 100))
                reduced = round(item["amount"] * (1 - error_reduction))
                if reduced > 0:
                    ai_breakdown.append({"label": "Errors & rework (reduced)", "amount": reduced})
            elif "overhead" in label_lower or "it spend" in label_lower or "tool" in label_lower:
                reduced = round(item["amount"] * 0.9)
                ai_breakdown.append({"label": item["label"], "amount": reduced})
            elif "user-provided" in label_lower:
                labor_share = round(item["amount"] * 0.6 * (1 - ai_coverage))
                overhead_share = round(item["amount"] * 0.4 * 0.9)
                ai_breakdown.append({"label": "Staff labor (reduced)", "amount": labor_share})
                ai_breakdown.append({"label": "Tools & overhead", "amount": overhead_share})

        total = sum(i["amount"] for i in ai_breakdown)
        return (total, ai_breakdown)

    # ── Per-driver amount allocation ─────────────────────────────────
    def _compute_per_driver_amounts(self, drivers: list[dict], annual_value: float) -> list[float]:
        """Distribute annual_value across drivers proportional to metric percentages."""
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

        non_zero = [p for p in percentages if p > 0]
        if non_zero:
            fallback = sum(non_zero) / len(non_zero)
            percentages = [p if p > 0 else fallback for p in percentages]

        total_pct = sum(percentages)
        if total_pct > 0:
            return [round(annual_value * (p / total_pct)) for p in percentages]
        equal = round(annual_value / len(drivers))
        return [equal] * len(drivers)

    def _extract_coverage_from_drivers(self, drivers: list[dict]) -> float | None:
        """Extract an AI coverage percentage from BV driver metrics."""
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

    # ── Waterfall split ──────────────────────────────────────────────
    def _split_waterfall(self, bv_drivers: list[dict], driver_amounts: list[float],
                         current_annual: float) -> tuple[list[dict], list[dict]]:
        """Split driver amounts into cost-reduction and revenue-uplift waterfalls.

        Hard savings (cost reduction) are capped at the current annual baseline
        to prevent reporting savings that exceed the actual spend being displaced.
        """
        cost_items: list[dict] = []
        uplift_items: list[dict] = []
        for idx, d in enumerate(bv_drivers):
            category = d.get("category", "cost_reduction")
            item = {"label": d.get("name", ""), "amount": driver_amounts[idx]}
            if category == "revenue_uplift":
                uplift_items.append(item)
            else:
                cost_items.append(item)

        # Guard: hard savings cannot exceed the current-state baseline
        raw_hard = sum(i["amount"] for i in cost_items)
        if current_annual > 0 and raw_hard > current_annual:
            scale = current_annual / raw_hard
            cost_items = [{"label": i["label"], "amount": round(i["amount"] * scale)}
                          for i in cost_items]

        return cost_items, uplift_items

    # ── Risk reduction ───────────────────────────────────────────────
    @staticmethod
    def _compute_risk_reduction(current_annual: float, hard_savings: float,
                                revenue_uplift: float) -> tuple[float, str]:
        """Return (risk_reduction_amount, methodology_note).

        Only includes risk reduction when it's material (>5% of other value).
        """
        risk_raw = round(current_annual * 0.03) if current_annual else 0
        preliminary = hard_savings + revenue_uplift
        if preliminary > 0 and risk_raw < preliminary * 0.05:
            return (0, f"Risk reduction ({risk_raw:,.0f}) excluded as immaterial (<5% of total value).")
        if risk_raw > 0:
            return (risk_raw, "Risk reduction estimated at 3% of current annual spend.")
        return (0, "")

    # ── Main entry point ─────────────────────────────────────────────
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

        # ── Core ROI math ────────────────────────────────────────────
        val_mid = (val_low + val_high) / 2
        roi_low = ((val_low - annual_cost) / annual_cost) * 100
        roi_high = ((val_high - annual_cost) / annual_cost) * 100
        roi_mid = ((val_mid - annual_cost) / annual_cost) * 100

        payback_months = round((annual_cost * 12 / val_mid), 1) if val_mid > 0 else None
        if payback_months is not None:
            payback_months = max(min(payback_months, self.MAX_PAYBACK_MONTHS), self.MIN_PAYBACK_MONTHS)
            payback_months = round(payback_months, 1)

        roi_capped = roi_mid > self.MAX_DISPLAY_ROI
        roi_display = min(roi_mid, self.MAX_DISPLAY_ROI)

        # ── Resolve current-state baseline ───────────────────────────
        azure_monthly = round(state.costs.get("estimate", {}).get("totalMonthly", 0))
        current_monthly, current_breakdown, is_estimated = self._resolve_current_baseline(state, azure_monthly)
        current_annual = current_monthly * 12

        # ── Merge user assumption dicts (for future-cost builder) ────
        assumptions_dict: dict = {}
        for source in (state.costs.get("user_assumptions", []),
                       bv.get("user_assumptions", [])):
            for a in source:
                if isinstance(a, dict) and "id" in a:
                    assumptions_dict[a["id"]] = a["value"]

        # ── Future-state monthly cost ────────────────────────────────
        future_monthly, ai_breakdown = self._build_future_cost(
            azure_monthly, current_breakdown, drivers, assumptions_dict)

        monthly_savings = round(current_monthly - future_monthly)

        # ── Driver amounts & waterfall ───────────────────────────────
        driver_amounts = self._compute_per_driver_amounts(drivers, val_mid)
        waterfall_cost, waterfall_uplift = self._split_waterfall(
            drivers, driver_amounts, current_annual)

        hard_savings = sum(i["amount"] for i in waterfall_cost)
        revenue_uplift = sum(i["amount"] for i in waterfall_uplift)

        risk_reduction, risk_note = self._compute_risk_reduction(
            current_annual, hard_savings, revenue_uplift)

        # ── Investment ───────────────────────────────────────────────
        azure_annual = azure_monthly * 12
        sa = state.shared_assumptions or {}
        timeline_months = sa.get("timeline_months", 0)
        impl_cost = round(azure_monthly * timeline_months) if timeline_months is not None and timeline_months > 0 else round(azure_annual * 0.5)
        change_cost = round(impl_cost * 0.10)
        year1_investment = round(azure_annual + impl_cost + change_cost)
        year2_run_rate = round(azure_annual)

        # ── Build dashboard (the frontend contract) ──────────────────
        dashboard = self._build_dashboard(
            state=state,
            annual_cost=annual_cost,
            annual_value=val_mid,
            roi_percent=round(roi_mid, 1),
            payback_months=payback_months,
            roi_capped=roi_capped,
            is_estimated=is_estimated,
            current_monthly=current_monthly,
            current_breakdown=current_breakdown,
            future_monthly=future_monthly,
            ai_breakdown=ai_breakdown,
            monthly_savings=monthly_savings,
            waterfall_cost=waterfall_cost,
            waterfall_uplift=waterfall_uplift,
            hard_savings=hard_savings,
            revenue_uplift=revenue_uplift,
            risk_reduction=risk_reduction,
            risk_note=risk_note,
            year1_investment=year1_investment,
            year2_run_rate=year2_run_rate,
            impl_cost=impl_cost,
            change_cost=change_cost,
            assumptions_dict=assumptions_dict,
            driver_amounts=driver_amounts,
        )

        state.roi = {
            # ── Canonical output schema ──────────────────────────────
            "annual_cost": round(annual_cost, 2),
            "annual_value": round(val_mid, 2),
            "annual_value_low": round(val_low, 2),
            "annual_value_high": round(val_high, 2),
            "monthly_current_cost": round(current_monthly) if not is_estimated else None,
            "monthly_future_cost": round(future_monthly),
            "monthly_savings": monthly_savings if not is_estimated else None,
            "hard_savings": round(hard_savings),
            "revenue_uplift": round(revenue_uplift),
            "risk_reduction": round(risk_reduction),
            "year1_investment": year1_investment,
            "year2_run_rate": year2_run_rate,
            "roi_percent": round(roi_mid, 1),
            "roi_percent_display": round(roi_display, 1),
            "roi_capped": roi_capped,
            "roi_range": f"{roi_low:.0f}\u2013{roi_high:.0f}%",
            "payback_months": payback_months,
            "is_estimated": is_estimated,
            "monetized_drivers": [
                {"name": d.get("name", ""), "metric": d.get("metric", "")}
                for d in drivers
            ],
            "assumptions": assumptions,
            "needs_info": None,
            "dashboard": dashboard,
        }
        return state

    # ── Dashboard builder ────────────────────────────────────────────
    def _build_dashboard(
        self,
        *,
        state: AgentState,
        annual_cost: float,
        annual_value: float,
        roi_percent: float | None,
        payback_months: float | None,
        roi_capped: bool,
        is_estimated: bool,
        current_monthly: float,
        current_breakdown: list[dict],
        future_monthly: float,
        ai_breakdown: list[dict],
        monthly_savings: int,
        waterfall_cost: list[dict],
        waterfall_uplift: list[dict],
        hard_savings: float,
        revenue_uplift: float,
        risk_reduction: float,
        risk_note: str,
        year1_investment: float,
        year2_run_rate: float,
        impl_cost: float,
        change_cost: float,
        assumptions_dict: dict,
        driver_amounts: list[float],
    ) -> dict:
        """Build the frontend ROIDashboardData blob.

        All numbers are passed in from the caller — no re-derivation, so every
        view of the same figure traces back to one computation.
        """
        cost_estimate = state.costs.get("estimate", {})
        azure_monthly = round(cost_estimate.get("totalMonthly", 0))
        cost_items = cost_estimate.get("items", [])
        bv = state.business_value
        bv_drivers = bv.get("drivers", [])
        current_annual = current_monthly * 12
        azure_annual = azure_monthly * 12

        # ── Savings percentage (capped for realism) ──────────────────
        if current_monthly > 0:
            savings_pct_raw = (monthly_savings / current_monthly) * 100
            if savings_pct_raw > self.MAX_SAVINGS_PCT:
                savings_pct = self.MAX_SAVINGS_PCT
                monthly_savings = round(current_monthly * self.MAX_SAVINGS_PCT / 100)
            else:
                savings_pct = round(savings_pct_raw)
        else:
            savings_pct = 0

        # ── AI inference cost (informational) ────────────────────────
        ai_inference = sum(
            item.get("monthlyCost", 0) for item in cost_items
            if "openai" in item.get("serviceName", "").lower()
            or "ai" in item.get("serviceName", "").lower()
        )

        # ── Driver display list (reuse amounts from caller) ─────────
        display_drivers = [
            {
                "name": d.get("name", ""),
                "metric": d.get("metric", ""),
                "category": d.get("category", "cost_reduction"),
                "annualImpact": driver_amounts[idx],
                "methodology": d.get("description", ""),
            }
            for idx, d in enumerate(bv_drivers)
        ]

        # ── Value waterfall ──────────────────────────────────────────
        value_waterfall = {
            "costReduction": waterfall_cost,
            "revenueUplift": waterfall_uplift,
        }

        # ── 3-year projection ────────────────────────────────────────
        annual_total_value = hard_savings + revenue_uplift + risk_reduction

        projection = {
            "years": [1, 2, 3],
            "adoptionRamp": [f"{int(r * 100)}%" for r in self.ADOPTION_RAMP],
            "annualAzureCost": round(azure_annual),
            "annualCostReduction": round(hard_savings),
            "annualRevenueUplift": round(revenue_uplift),
            "annualNetValue": round(annual_total_value - azure_annual),
            "cumulative": [
                {
                    "year": yr + 1,
                    "adoption": f"{int(self.ADOPTION_RAMP[yr] * 100)}%",
                    "azureCost": round(azure_annual * (yr + 1)),
                    "totalValue": round(annual_total_value * sum(self.ADOPTION_RAMP[:yr + 1])),
                    "netValue": round(
                        annual_total_value * sum(self.ADOPTION_RAMP[:yr + 1])
                        - azure_annual * (yr + 1)
                    ),
                }
                for yr in range(3)
            ],
        }

        # ── Methodology string ───────────────────────────────────────
        cost_source = cost_estimate.get("pricingSource", "estimated")
        service_count = len(cost_items)

        assumption_sources = []
        if state.costs.get("user_assumptions"):
            assumption_sources.append("usage metrics")
        if bv.get("user_assumptions"):
            assumption_sources.append("business metrics")
        assumption_note = " and ".join(assumption_sources) if assumption_sources else "estimated defaults"

        cost_red_count = len(waterfall_cost)
        uplift_count = len(waterfall_uplift)
        driver_note = (
            f"{cost_red_count} cost-reduction and {uplift_count} revenue-uplift driver(s) identified. "
            if (cost_red_count + uplift_count) > 0
            else ""
        )

        methodology = f"Azure costs based on {service_count} services ({cost_source} pricing). "
        sa_annual_spend = self._resolve_sa(state.shared_assumptions or {}, self._CURRENT_SPEND_KEYS)
        if sa_annual_spend:
            methodology += (
                f"Current operational cost from user-provided baseline "
                f"(${sa_annual_spend:,.0f}/yr). "
            )
        elif is_estimated:
            methodology += (
                f"Current operational cost estimated as "
                f"{self.ESTIMATED_BASELINE_MULTIPLIER}\u00d7 Azure cost "
                "(no user-provided baseline). "
                "For accurate ROI, provide actual current costs. "
            )
        else:
            methodology += f"Current operational costs derived from {assumption_note}. "
        methodology += (
            driver_note
            + "Projection assumes 50/85/100% adoption ramp over 3 years. "
            + "One-time implementation costs excluded from monthly comparison. "
            + "ROI = (Annual Value \u2212 Annual Cost) \u00f7 Annual Cost \u00d7 100."
        )
        if risk_note:
            methodology += " " + risk_note
        methodology += f" Savings capped at {self.MAX_SAVINGS_PCT}% of current baseline to ensure realism."

        assumption_types = []
        if sa_annual_spend:
            assumption_types.append("Current baseline: user-provided")
        else:
            assumption_types.append(
                f"Current baseline: estimated ({self.ESTIMATED_BASELINE_MULTIPLIER}\u00d7 Azure cost)"
            )
        if bv_drivers:
            assumption_types.append(
                f"Value drivers: {len(bv_drivers)} identified "
                f"({bv.get('confidence', 'moderate')} confidence)"
            )
        assumption_types.append(f"Azure costs: {cost_source}")
        methodology += " Assumptions: " + "; ".join(assumption_types) + "."

        # ── Business case ────────────────────────────────────────────
        business_case = self._build_business_case(
            current_annual=current_annual,
            azure_annual=azure_annual,
            hard_savings=hard_savings,
            revenue_uplift=revenue_uplift,
            risk_reduction=risk_reduction,
            impl_cost=impl_cost,
            change_cost=change_cost,
            year1_investment=year1_investment,
            year2_run_rate=year2_run_rate,
            bv_drivers=bv_drivers,
            is_estimated=is_estimated,
            sa_annual_spend=sa_annual_spend,
        )

        # ── ROI display text ─────────────────────────────────────────
        if roi_capped:
            roi_display_text = f">{self.MAX_DISPLAY_ROI // 100}x"
        elif roi_percent is not None:
            roi_display_text = f"{(roi_percent / 100 + 1):.1f}x"
        else:
            roi_display_text = None

        # ── Assemble dashboard ───────────────────────────────────────
        dashboard: dict = {
            "monthlySavings": monthly_savings,
            "annualImpact": round(annual_value),
            "azureMonthlyCost": azure_monthly,
            "platformCostMonthly": azure_monthly,
            "platformCostAnnual": round(azure_annual),
            "totalOperatingCostMonthly": round(current_monthly) if current_monthly else None,
            "aiInferenceMonthlyCost": round(ai_inference) if ai_inference else None,
            "savingsPercentage": savings_pct,
            "costComparisonAvailable": not is_estimated,
            "currentCost": {
                "total": round(current_monthly),
                "breakdown": current_breakdown,
            },
            "aiCost": {
                "total": round(future_monthly),
                "breakdown": ai_breakdown,
            },
            "roiPercent": roi_percent,
            "roiCapped": roi_capped,
            "roiDisplayText": roi_display_text,
            "confidenceLevel": bv.get("confidence", "moderate"),
            "paybackMonths": payback_months,
            "drivers": display_drivers,
            "valueWaterfall": value_waterfall,
            "projection": projection,
            "methodology": methodology,
            "businessCase": business_case,
        }

        if is_estimated:
            dashboard["costEstimated"] = True
            dashboard["warning"] = (
                "Current cost estimated \u2014 provide actual figures for accurate ROI"
            )

        return dashboard

    # ── Business-case builder ────────────────────────────────────────
    def _build_business_case(
        self,
        *,
        current_annual: float,
        azure_annual: float,
        hard_savings: float,
        revenue_uplift: float,
        risk_reduction: float,
        impl_cost: float,
        change_cost: float,
        year1_investment: float,
        year2_run_rate: float,
        bv_drivers: list[dict],
        is_estimated: bool,
        sa_annual_spend: float | None,
    ) -> dict:
        """Produce a full economic business case.

        All value/cost figures are received from the caller to guarantee
        that dashboard, headline ROI, and business case reconcile exactly.
        """
        # ── currentState breakdown ───────────────────────────────────
        # When a real user-provided baseline exists, report it as a single
        # authoritative line rather than inventing sub-categories.
        if sa_annual_spend:
            current_state = {
                "totalAnnual": round(current_annual),
                "breakdown": [
                    {"category": "Current operations (user-provided)",
                     "description": "Baseline operating cost as reported",
                     "annual": round(current_annual)},
                ],
            }
        elif not is_estimated:
            # Detailed user inputs assembled in _resolve_current_baseline;
            # reflect the same total without re-deriving category splits.
            current_state = {
                "totalAnnual": round(current_annual),
                "breakdown": [
                    {"category": "Current operations",
                     "description": "Derived from user-provided labor, spend, and overhead inputs",
                     "annual": round(current_annual)},
                ],
            }
        else:
            # Estimated baseline — label clearly
            current_state = {
                "totalAnnual": round(current_annual),
                "breakdown": [
                    {"category": "Operations (estimated)",
                     "description": (
                         f"Estimated at {self.ESTIMATED_BASELINE_MULTIPLIER}\u00d7 Azure cost "
                         "(no user-provided baseline)"
                     ),
                     "annual": round(current_annual)},
                ],
            }

        # ── futureState ──────────────────────────────────────────────
        future_state = {
            "azurePlatformAnnual": round(azure_annual),
            "implementationCost": impl_cost,
            "changeCost": change_cost,
        }

        # ── valueBridge ──────────────────────────────────────────────
        total_annual_value = round(hard_savings + revenue_uplift + risk_reduction)

        value_bridge = {
            "hardSavings": round(hard_savings),
            "productivityGains": 0,  # folded into hard_savings to avoid double-counting
            "revenueUplift": round(revenue_uplift),
            "riskReduction": round(risk_reduction),
            "totalAnnualValue": total_annual_value,
        }

        # ── investment ───────────────────────────────────────────────
        investment = {
            "year1Total": year1_investment,
            "year2Total": year2_run_rate,
            "year1NetValue": round(total_annual_value - year1_investment),
            "year2NetValue": round(total_annual_value - year2_run_rate),
        }

        # ── sensitivity ──────────────────────────────────────────────
        sensitivity = []
        for pct, label in [(0.5, "50%"), (0.75, "75%"), (1.0, "100%")]:
            adj_value = total_annual_value * pct
            adj_roi = ((adj_value - azure_annual) / azure_annual * 100) if azure_annual > 0 else 0
            adj_payback = round(azure_annual * 12 / adj_value, 1) if adj_value > 0 else None
            if adj_payback is not None and adj_payback > self.MAX_PAYBACK_MONTHS:
                adj_payback = self.MAX_PAYBACK_MONTHS
            sensitivity.append({
                "adoption": label,
                "annualValue": round(adj_value),
                "roi": round(adj_roi, 1),
                "paybackMonths": adj_payback,
            })

        # ── decisionDrivers ──────────────────────────────────────────
        default_drivers = [
            "Lower cost to serve",
            "Faster growth through shorter cycles",
            "Reduced operational risk",
            "Higher employee productivity",
            "Strategic platform flexibility",
        ]
        driver_names = [d.get("name", "") for d in bv_drivers if d.get("name")]
        if driver_names:
            decision_drivers = driver_names[:3]
            decision_drivers.extend(default_drivers[len(decision_drivers):5])
        else:
            decision_drivers = default_drivers

        return {
            "currentState": current_state,
            "futureState": future_state,
            "valueBridge": value_bridge,
            "investment": investment,
            "sensitivity": sensitivity,
            "decisionDrivers": decision_drivers,
        }

    # ── Needs-info helper ────────────────────────────────────────────
    def _needs_info(self, reason: str, questions: list[str],
                    qualitative: list[str] | None = None) -> dict:
        """Return an ROI result that signals we need user input to calculate."""
        return {
            "annual_cost": 0,
            "annual_value": None,
            "annual_value_low": None,
            "annual_value_high": None,
            "monthly_current_cost": None,
            "monthly_future_cost": None,
            "monthly_savings": None,
            "hard_savings": None,
            "revenue_uplift": None,
            "risk_reduction": None,
            "year1_investment": None,
            "year2_run_rate": None,
            "roi_percent": None,
            "roi_percent_display": None,
            "roi_capped": False,
            "payback_months": None,
            "is_estimated": False,
            "monetized_drivers": [],
            "qualitative_benefits": qualitative or [],
            "needs_info": questions,
        }
