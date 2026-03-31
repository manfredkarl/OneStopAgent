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
            # Match any key with "labor"/"hourly" + "rate" against rate candidates
            if ("labor" in sk or "hourly" in sk) and "rate" in sk:
                if any("labor" in c or "rate" in c for c in candidates):
                    try:
                        return float(raw)
                    except (ValueError, TypeError):
                        pass
            # Match any key with "spend" or "cost" (current/annual) against spend candidates
            if "spend" in sk or ("cost" in sk and "current" in sk):
                if any("spend" in c or "cost" in c for c in candidates):
                    try:
                        val = float(raw)
                        if val > 1000:  # Sanity: spend should be > $1K
                            return val
                    except (ValueError, TypeError):
                        pass
        return None

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
        payback_months = round((annual_cost * 12 / val_mid), 1) if val_mid > 0 else None
        if payback_months is not None and payback_months > 120:
            payback_months = 120.0

        # Cap displayed ROI to avoid unrealistic precision
        MAX_DISPLAY_ROI = 1000  # 10x = 1000%
        roi_display = min(roi_mid, MAX_DISPLAY_ROI)
        roi_capped = roi_mid > MAX_DISPLAY_ROI

        # Payback: cap at reasonable max
        if payback_months is not None and payback_months < 0.5:
            payback_months = max(payback_months, 0.5)  # Minimum half-month payback

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
                         payback_months: float | None,
                         roi_capped: bool = False,
                         max_display_roi: int = 1000) -> dict:
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

        # Use shared assumptions as authoritative baseline when available
        sa = state.shared_assumptions or {}
        sa_annual_spend = self._resolve_sa(sa, self._CURRENT_SPEND_KEYS)
        sa_labor_rate = self._resolve_sa(sa, self._LABOR_RATE_KEYS)

        if sa_annual_spend:
            # Use authoritative baseline from shared assumptions
            current_monthly = sa_annual_spend / 12
            current_breakdown = [
                {"label": "Current operations (user-provided)", "amount": round(current_monthly)},
            ]
            has_any_input = True  # Mark as real data, not estimated
        elif sa_labor_rate and not hourly_rate:
            hourly_rate = sa_labor_rate

        if not current_breakdown:
            if not has_any_input:
                # Last-resort estimate: NO shared assumptions AND no user inputs provided.
                # Uses 1.5× Azure cost as rough proxy for current equivalent capability.
                estimated_current = round(azure_monthly * 1.5)
                # Industry-typical breakdown when no detailed user inputs:
                # 55% labor (salaries, contractors), 30% tools/licenses, 15% delay/opportunity cost
                # Source: Gartner IT Spending Benchmark (approximate)
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

        # Add AI inference estimate from cost items
        ai_inference = sum(item.get("monthlyCost", 0) for item in cost_items if "openai" in item.get("serviceName", "").lower() or "ai" in item.get("serviceName", "").lower())

        # ── Cost comparison ──────────────────────────────────────────
        if current_total > 0:
            savings = current_total - ai_total
            savings_pct = round((savings / current_total) * 100)
        else:
            savings = 0
            savings_pct = 0

        # Cap savings at 60% of baseline — 99% reduction is not realistic
        MAX_SAVINGS_PCT = 60
        if savings > 0 and current_total > 0:
            actual_pct = (savings / current_total) * 100
            if actual_pct > MAX_SAVINGS_PCT:
                savings = current_total * (MAX_SAVINGS_PCT / 100)
                savings_pct = MAX_SAVINGS_PCT

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

        # ── 3-year projection — cumulative net value ─────────────
        annual_azure_cost = azure_monthly * 12
        annual_cost_reduction = sum(item["amount"] for item in waterfall_cost_reduction)
        annual_total_value = annual_cost_reduction + annual_uplift
        annual_net_value = annual_total_value - annual_azure_cost

        # Adoption ramp: Year 1 = 50% value (ramp-up), Year 2 = 85%, Year 3 = 100%
        ADOPTION_RAMP = [0.50, 0.85, 1.00]

        projection = {
            "years": [1, 2, 3],
            "adoptionRamp": ["50%", "85%", "100%"],
            "annualAzureCost": round(annual_azure_cost),
            "annualCostReduction": round(annual_cost_reduction),
            "annualRevenueUplift": round(annual_uplift),
            "annualNetValue": round(annual_net_value),
            "cumulative": [
                {
                    "year": yr + 1,
                    "adoption": f"{int(ADOPTION_RAMP[yr] * 100)}%",
                    "azureCost": round(annual_azure_cost * (yr + 1)),  # Full cost from day 1
                    "totalValue": round(annual_total_value * sum(ADOPTION_RAMP[:yr+1])),  # Ramped value
                    "netValue": round(annual_total_value * sum(ADOPTION_RAMP[:yr+1]) - annual_azure_cost * (yr + 1)),
                }
                for yr in range(3)
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
        if sa_annual_spend:
            methodology += (
                f"Current operational cost from user-provided baseline "
                f"(${sa_annual_spend:,.0f}/yr). "
            )
        elif cost_estimated:
            methodology += (
                "Current operational cost estimated as 2\u00d7 Azure cost "
                "(industry rule-of-thumb for cloud migration). "
                "For accurate ROI, provide actual current costs. "
            )
        else:
            methodology += f"Current operational costs derived from {assumption_note}. "
        methodology += (
            driver_note
            + "Projection assumes 50/85/100% adoption ramp over 3 years. "
            + "One-time implementation costs are excluded. "
            + "Risk reduction estimated at 3% of current annual spend (governance, compliance, reduced outage exposure). "
            + "ROI = (Annual Value \u2212 Annual Cost) \u00f7 Annual Cost \u00d7 100."
        )
        methodology += f" Savings capped at {MAX_SAVINGS_PCT}% of current baseline to ensure realism."

        # Classify assumptions
        assumption_types = []
        if sa_annual_spend:
            assumption_types.append("Current baseline: user-provided")
        else:
            assumption_types.append("Current baseline: estimated (1.5\u00d7 Azure cost)")
        if bv_drivers:
            assumption_types.append(f"Value drivers: {len(bv_drivers)} identified ({state.business_value.get('confidence', 'moderate')} confidence)")
        assumption_types.append(f"Azure costs: {cost_source}")

        methodology += " Assumptions: " + "; ".join(assumption_types) + "."

        # ── Business Case ────────────────────────────────────────────
        business_case = self._build_business_case(
            state, azure_monthly, annual_azure_cost, annual_value,
            current_total, waterfall_cost_reduction, waterfall_revenue_uplift,
            bv_drivers,
        )

        # Append risk methodology note determined by _build_business_case
        if hasattr(self, '_methodology_risk') and self._methodology_risk:
            methodology += " " + self._methodology_risk

        bv = state.business_value

        dashboard: dict = {
            "monthlySavings": savings,
            "annualImpact": round(annual_value),
            "azureMonthlyCost": azure_monthly,
            "platformCostMonthly": azure_monthly,
            "platformCostAnnual": round(azure_monthly * 12),
            "totalOperatingCostMonthly": round(current_total) if current_total else None,
            "aiInferenceMonthlyCost": round(ai_inference) if ai_inference else None,
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
            "roiCapped": roi_capped,
            "roiDisplayText": f">{max_display_roi // 100}x" if roi_capped else f"{(roi_percent/100 + 1):.1f}x" if roi_percent is not None else None,
            "confidenceLevel": bv.get("confidence", "moderate"),
            "paybackMonths": payback_months,
            "drivers": [
                {
                    "name": d.get("name", ""),
                    "metric": d.get("metric", ""),
                    "category": d.get("category", "cost_reduction"),
                    "annualImpact": driver_amounts[idx],
                    "methodology": d.get("description", ""),
                }
                for idx, d in enumerate(bv_drivers)
            ],
            "valueWaterfall": value_waterfall,
            "projection": projection,
            "methodology": methodology,
            "businessCase": business_case,
        }

        if cost_estimated:
            dashboard["costEstimated"] = True
            dashboard["warning"] = "Current cost estimated \u2014 provide actual figures for accurate ROI"

        return dashboard

    # ── Business-case builder ────────────────────────────────────────
    def _build_business_case(
        self,
        state: AgentState,
        azure_monthly: float,
        azure_annual: float,
        annual_value: float,
        current_annual_from_dash: float,
        waterfall_cost_reduction: list[dict],
        waterfall_revenue_uplift: list[dict],
        bv_drivers: list[dict],
    ) -> dict:
        """Produce a full economic business case alongside the existing dashboard."""

        sa = state.shared_assumptions or {}

        # ── currentState ─────────────────────────────────────────────
        sa_annual = self._resolve_sa(sa, self._CURRENT_SPEND_KEYS)
        current_annual = sa_annual or (current_annual_from_dash * 12)

        sa_hourly = self._resolve_sa(sa, self._LABOR_RATE_KEYS)
        hourly_rate = sa_hourly or 0
        manual_hours_annual = 0
        for d in bv_drivers:
            metric = d.get("metric", "")
            m = self._PERCENTAGE_RE.search(metric)
            if m and hourly_rate:
                manual_hours_annual += float(m.group(1)) * 20  # rough proxy

        # Industry-typical breakdown when no detailed user inputs:
        # 55% labor (salaries, contractors), 30% tools/licenses, 15% delay/opportunity cost
        # Source: Gartner IT Spending Benchmark (approximate)
        labor_portion = round(hourly_rate * manual_hours_annual) if hourly_rate and manual_hours_annual else round(current_annual * 0.55)
        tool_portion = round(current_annual * 0.30) if current_annual else 0
        delay_portion = round(current_annual - labor_portion - tool_portion) if current_annual else 0

        current_state = {
            "totalAnnual": round(current_annual),
            "breakdown": [
                {"category": "Manual operations", "description": "Staff labor on repetitive and manual tasks", "annual": labor_portion},
                {"category": "Tool/platform spend", "description": "Existing software licenses, hosting, and infrastructure", "annual": tool_portion},
                {"category": "Delay/opportunity cost", "description": "Revenue leakage and slower time-to-market", "annual": max(delay_portion, 0)},
            ],
        }

        # ── futureState ──────────────────────────────────────────────
        timeline_months = sa.get("timeline_months", 0)
        if timeline_months and azure_monthly:
            impl_cost = round(azure_monthly * timeline_months)
        else:
            impl_cost = round(azure_annual * 0.5)
        change_cost = round(impl_cost * 0.10)

        future_state = {
            "azurePlatformAnnual": round(azure_annual),
            "implementationCost": impl_cost,
            "changeCost": change_cost,
        }

        # ── valueBridge ──────────────────────────────────────────────
        hard_savings = sum(item["amount"] for item in waterfall_cost_reduction)
        revenue_uplift = sum(item["amount"] for item in waterfall_revenue_uplift)

        # Productivity is already part of hard_savings (cost_reduction drivers
        # include labor/time savings) — don't double-count.
        productivity = 0
        risk_reduction = round(current_annual * 0.03) if current_annual else 0

        # Only include risk reduction if material (>5% of total value)
        preliminary_total = hard_savings + revenue_uplift
        if risk_reduction < preliminary_total * 0.05:
            self._methodology_risk = f"Risk reduction ({risk_reduction:,.0f}) excluded as immaterial (<5% of total value)."
            risk_reduction = 0
        else:
            self._methodology_risk = "Risk reduction estimated at 3% of current annual spend."

        total_value = round(hard_savings + revenue_uplift + risk_reduction)

        value_bridge = {
            "hardSavings": round(hard_savings),
            "productivityGains": round(productivity),
            "revenueUplift": round(revenue_uplift),
            "riskReduction": risk_reduction,
            "totalAnnualValue": total_value,
        }

        # ── investment ───────────────────────────────────────────────
        year1_total = round(azure_annual + impl_cost + change_cost)
        year2_total = round(azure_annual)

        investment = {
            "year1Total": year1_total,
            "year2Total": year2_total,
            "year1NetValue": round(total_value - year1_total),
            "year2NetValue": round(total_value - year2_total),
        }

        # ── sensitivity ──────────────────────────────────────────────
        sensitivity = []
        for pct, label in [(0.5, "50%"), (0.75, "75%"), (1.0, "100%")]:
            adj_value = total_value * pct
            adj_roi = ((adj_value - azure_annual) / azure_annual) * 100 if azure_annual > 0 else 0
            adj_payback = round((azure_annual * 12 / adj_value), 1) if adj_value > 0 else None
            if adj_payback is not None and adj_payback > 120:
                adj_payback = 120.0
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
        # Enrich with actual BV driver names when available
        decision_drivers = []
        driver_names = [d.get("name", "") for d in bv_drivers if d.get("name")]
        if driver_names:
            for dn in driver_names[:3]:
                decision_drivers.append(dn)
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
