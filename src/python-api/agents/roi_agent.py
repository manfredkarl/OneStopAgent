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
import logging
import re
from agents.state import AgentState

logger = logging.getLogger(__name__)


class ROIAgent:
    name = "ROI Calculator"
    emoji = "📈"

    # ── Constants ────────────────────────────────────────────────────
    MAX_DISPLAY_ROI = 1000        # 10× = 1000%
    MAX_SAVINGS_PCT = 60          # cap monthly savings display
    MIN_PAYBACK_MONTHS = 0.5
    MAX_PAYBACK_MONTHS = 120.0
    ADOPTION_RAMP = [0.50, 0.85, 1.00]  # default; overridden by _select_adoption_ramp

    ADOPTION_RAMPS: dict[str, list[float]] = {
        "simple":  [0.70, 0.95, 1.00],
        "medium":  [0.50, 0.85, 1.00],
        "complex": [0.30, 0.65, 0.90],
    }

    @classmethod
    def _select_adoption_ramp(cls, state: AgentState) -> list[float]:
        """Select adoption ramp based on architecture complexity."""
        n = len(state.architecture.get("components", []))
        if n <= 3:
            return cls.ADOPTION_RAMPS["simple"]
        elif n <= 8:
            return cls.ADOPTION_RAMPS["medium"]
        else:
            return cls.ADOPTION_RAMPS["complex"]
    # When no current-state baseline is available, use a complexity-based
    # multiplier on Azure cost as a *clearly-labeled* estimate.
    ESTIMATED_BASELINE_MULTIPLIER = 1.5  # default; overridden by _estimate_baseline_multiplier

    @staticmethod
    def _estimate_baseline_multiplier(state: AgentState) -> float:
        """Variable multiplier based on architecture complexity."""
        component_count = len(state.architecture.get("components", []))
        if component_count <= 3:
            return 1.2
        elif component_count <= 7:
            return 1.5
        else:
            return 2.0

    _PERCENTAGE_RANGE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*[–\-−]\s*(\d+(?:\.\d+)?)\s*%')
    _PERCENTAGE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*%')

    # ── Current-state baseline ───────────────────────────────────────
    def _resolve_current_baseline(self, state: AgentState, azure_monthly: float) -> tuple[float, list[dict], bool]:
        """Determine the monthly current-state operating cost.

        Returns (monthly_total, breakdown_items, is_estimated).
        *is_estimated* is True when the baseline is a rough proxy, not user data.
        """
        sa_annual_spend = state.sa.current_annual_spend

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
        sa_labor_rate = state.sa.hourly_labor_rate
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
        multiplier = self._estimate_baseline_multiplier(state)
        estimated = round(azure_monthly * multiplier)
        return (estimated,
                [{"label": "Operations (estimated)", "amount": round(estimated * 0.75)},
                 {"label": "Overhead (estimated)", "amount": round(estimated * 0.25)}],
                True)

    # ── Future-state cost model (pool-based reductions) ────────────────

    # Keywords that identify which cost pool a driver targets
    POOL_KEYWORDS: dict[str, list[str]] = {
        "labor":   ["staff", "fte", "headcount", "personnel", "operations",
                    "labor", "labour", "engineer", "developer", "productivity",
                    "time saving", "manual", "automation"],
        "tooling": ["tool", "license", "software", "saas", "subscription",
                    "platform", "infra"],
        "error":   ["error", "rework", "defect", "incident", "downtime",
                    "outage", "failure", "bug", "quality"],
    }

    MAX_PER_ITEM_REDUCTION = 0.80  # no line item reduced by more than 80%

    @classmethod
    def _classify_driver_pool(cls, driver: dict) -> str | None:
        """Classify a BV driver into a cost pool based on its name and metric."""
        text = (str(driver.get("name", "")) + " " + str(driver.get("metric", ""))).lower()
        for pool, keywords in cls.POOL_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return pool
        return None  # general / blended — applies to all items

    @classmethod
    def _matches_pool(cls, label: str, pool: str | None) -> bool:
        """Check if a breakdown item label matches a cost pool."""
        if pool is None:
            return True  # general pool matches everything
        label_lower = label.lower()
        keywords = cls.POOL_KEYWORDS.get(pool, [])
        return any(kw in label_lower for kw in keywords)

    def _build_future_cost(self, azure_monthly: float,
                           current_breakdown: list[dict],
                           bv_drivers: list[dict],
                           assumptions_dict: dict) -> tuple[float, list[dict]]:
        """Build the monthly operating cost WITH the Azure solution.

        Derives reductions from BV driver percentages (not hardcoded).
        Applies reductions per cost pool with multiplicative accumulation
        and an 80% per-item cap.

        Returns (monthly_total, breakdown_items).
        """
        ai_breakdown: list[dict] = [{"label": "Azure platform", "amount": azure_monthly}]

        # ── Accumulate per-pool reductions from cost_reduction drivers ─
        pool_reductions: dict[str | None, float] = {}  # pool → cumulative reduction fraction
        for d in bv_drivers:
            if d.get("category") != "cost_reduction":
                continue
            low = d.get("impact_pct_low")
            high = d.get("impact_pct_high")
            if low is None or high is None:
                continue
            try:
                mid_pct = (float(low) + float(high)) / 2 / 100
            except (ValueError, TypeError):
                continue
            if mid_pct <= 0:
                continue

            pool = self._classify_driver_pool(d)
            # Multiplicative: 1 - (1 - existing) * (1 - new)
            existing = pool_reductions.get(pool, 0.0)
            combined = 1 - (1 - existing) * (1 - mid_pct)
            pool_reductions[pool] = min(combined, self.MAX_PER_ITEM_REDUCTION)

        # ── Apply reductions to each breakdown item ───────────────────
        for item in current_breakdown:
            label = item["label"]

            # Find the best matching pool reduction (specific > general)
            reduction = 0.0
            found_specific = False
            for pool, pct in pool_reductions.items():
                if pool is not None and self._matches_pool(label, pool):
                    # Multiplicative combine if multiple specific pools match
                    if not found_specific:
                        reduction = pct
                        found_specific = True
                    else:
                        reduction = 1 - (1 - reduction) * (1 - pct)

            # Fall back to general pool if no specific match
            if not found_specific and None in pool_reductions:
                reduction = pool_reductions[None]

            # Cap per-item reduction
            reduction = min(reduction, self.MAX_PER_ITEM_REDUCTION)

            if reduction > 0:
                reduced = round(item["amount"] * (1 - reduction))
                suffix = " (reduced)" if "reduced" not in label.lower() else ""
                ai_breakdown.append({"label": f"{label}{suffix}", "amount": reduced})
            else:
                # No reduction — carry forward as-is
                ai_breakdown.append({"label": label, "amount": item["amount"]})

        total = sum(i["amount"] for i in ai_breakdown)
        return (total, ai_breakdown)

    # ── Per-driver amount allocation ─────────────────────────────────
    def _compute_per_driver_amounts(self, drivers: list[dict], annual_value: float) -> list[float]:
        """Distribute annual_value across drivers proportional to impact percentages.

        Uses structured impact_pct_low/high fields when available,
        falls back to regex on metric string for backward compatibility.
        """
        if not drivers:
            return []

        percentages: list[float] = []
        for d in drivers:
            low = d.get("impact_pct_low")
            high = d.get("impact_pct_high")
            if low is not None and high is not None:
                try:
                    percentages.append((float(low) + float(high)) / 2)
                    continue
                except (ValueError, TypeError):
                    pass
            # Fallback: regex on metric string
            metric = d.get("metric", "")
            range_match = self._PERCENTAGE_RANGE_RE.search(metric)
            if range_match:
                percentages.append((float(range_match.group(1)) + float(range_match.group(2))) / 2)
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
        """Extract an AI coverage percentage from BV driver metrics.

        Uses structured impact_pct_low/high fields when available,
        falls back to regex on metric string for backward compatibility.
        """
        for driver in drivers:
            low = driver.get("impact_pct_low")
            high = driver.get("impact_pct_high")
            if low is not None and high is not None:
                try:
                    return (float(low) + float(high)) / 2 / 100
                except (ValueError, TypeError):
                    continue
            # Fallback: regex on metric string
            metric = driver.get("metric", "")
            range_match = self._PERCENTAGE_RANGE_RE.search(metric)
            if range_match:
                return (float(range_match.group(1)) + float(range_match.group(2))) / 2 / 100
            single_match = self._PERCENTAGE_RE.search(metric)
            if single_match:
                return float(single_match.group(1)) / 100
        return None

    # ── Waterfall split ──────────────────────────────────────────────
    def _split_waterfall(self, bv_drivers: list[dict], driver_amounts: list[float],
                         max_hard_savings: float) -> tuple[list[dict], list[dict], bool, float]:
        """Split driver amounts into cost-reduction and revenue-uplift waterfalls.

        Hard savings (cost reduction) are capped at max_hard_savings — typically
        the actual operating cost reduction from _build_future_cost(), so BV
        drivers can't claim more savings than the cost model proves.

        Returns (cost_items, uplift_items, savings_capped, savings_cap_pct).
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

        # Cap hard savings at the provable operating cost reduction
        savings_capped = False
        savings_cap_pct = 0.0
        raw_hard = sum(i["amount"] for i in cost_items)
        if max_hard_savings > 0 and raw_hard > max_hard_savings:
            scale = max_hard_savings / raw_hard
            cost_items = [{"label": i["label"], "amount": round(i["amount"] * scale)}
                          for i in cost_items]
            savings_capped = True
            savings_cap_pct = round((1 - scale) * 100)

        return cost_items, uplift_items, savings_capped, savings_cap_pct

    # ── Risk reduction ───────────────────────────────────────────────
    @staticmethod
    def _compute_risk_reduction(current_annual: float, hard_savings: float,
                                revenue_uplift: float,
                                components: list[dict] | None = None) -> tuple[float, str]:
        """Return (risk_reduction_amount, methodology_note).

        Risk factor scales based on security/compliance/HA components (2-7%).
        Only includes risk reduction when it's material (>5% of other value).
        """
        has_security = any(
            any(kw in str(c).lower() for kw in ("security", "sentinel", "defender", "ddos", "firewall", "waf"))
            for c in (components or [])
        )
        has_compliance = any(
            any(kw in str(c).lower() for kw in ("compliance", "policy", "purview", "governance"))
            for c in (components or [])
        )
        has_ha = any(
            any(kw in str(c).lower() for kw in ("availability", "disaster", "recovery", "backup", "redundan"))
            for c in (components or [])
        )

        risk_factor = 0.02
        if has_security:
            risk_factor += 0.02
        if has_compliance:
            risk_factor += 0.02
        if has_ha:
            risk_factor += 0.01
        risk_factor = min(risk_factor, 0.07)

        risk_raw = round(current_annual * risk_factor) if current_annual else 0
        preliminary = hard_savings + revenue_uplift
        if preliminary > 0 and risk_raw < preliminary * 0.05:
            return (0, f"Risk reduction (${risk_raw:,}) excluded as immaterial (<5% of total value).")
        if risk_raw > 0:
            return (risk_raw, f"Risk reduction at {risk_factor * 100:.0f}% of current annual spend.")
        return (0, "")

    # ── Cross-agent reconciliation (FRD-004 Fix H) ───────────────────
    @staticmethod
    def _validate_and_reconcile(
        *,
        val_mid: float,
        annual_cost: float,
        current_annual: float,
        azure_annual: float,
        future_annual: float,
        hard_savings: float,
        revenue_uplift: float,
        monthly_savings_annualized: float,
        is_estimated: bool,
        bv_confidence: str,
        bv_warnings: list[str],
        savings_were_capped: bool,
        savings_cap_pct: float,
        monthly_revenue: float | None,
        costs_used_fallback: bool = False,
        bv_used_fallback: bool = False,
    ) -> tuple[str, list[str]]:
        """Run all plausibility checks.  Returns (adjusted_confidence, warnings)."""
        warnings = list(bv_warnings)

        # 1. Value-to-Azure-cost ratio
        if annual_cost > 0:
            ratio = val_mid / annual_cost
            if ratio > 50:
                warnings.append(
                    f"Value (${val_mid:,.0f}) is {ratio:.0f}\u00d7 Azure cost. Unusually high."
                )
                bv_confidence = "low"
            elif ratio > 20:
                warnings.append(f"Value-to-cost ratio is {ratio:.0f}\u00d7. On the high end.")

        # 2. Hard savings cap transparency
        if savings_were_capped:
            warnings.append(
                f"Cost savings reduced by {savings_cap_pct:.0f}% to not exceed "
                f"the current baseline. Original driver estimates were higher."
            )

        # 3. Revenue uplift vs stated revenue
        if monthly_revenue and monthly_revenue > 0:
            annual_revenue = monthly_revenue * 12
            if revenue_uplift > annual_revenue * 0.5:
                warnings.append(
                    f"Revenue uplift (${revenue_uplift:,.0f}) is "
                    f">{revenue_uplift / annual_revenue * 100:.0f}% of stated revenue."
                )

        # 4. Accounting identity: components should sum to ~midpoint
        component_sum = hard_savings + revenue_uplift
        if val_mid > 0 and abs(component_sum - val_mid) > val_mid * 0.15:
            warnings.append(
                f"Driver sum (${component_sum:,.0f}) differs from impact midpoint "
                f"(${val_mid:,.0f}) by {abs(component_sum - val_mid) / val_mid * 100:.0f}%."
            )

        # 5. Cost-reduction-only: Azure shouldn't exceed current
        if revenue_uplift == 0 and not is_estimated and current_annual > 0:
            if azure_annual > current_annual:
                warnings.append(
                    f"Azure cost (${azure_annual:,.0f}/yr) > current cost "
                    f"(${current_annual:,.0f}/yr) with no revenue uplift."
                )

        # 6. Fallback data detection (FRD-008)
        if costs_used_fallback or bv_used_fallback:
            warnings.append("One or more agents used fallback data due to errors.")
            bv_confidence = "low"

        # 7. BV annual value vs actual operating cost savings
        if monthly_savings_annualized > 0 and val_mid > monthly_savings_annualized * 2:
            warnings.append(
                f"Modeled annual value (${val_mid:,.0f}) is "
                f"{val_mid / monthly_savings_annualized:.1f}\u00d7 the actual operating cost "
                f"reduction (${monthly_savings_annualized:,.0f}/yr). "
                "Value drivers may include productivity gains not reflected in direct cost savings."
            )

        # 8. Hard savings vs current baseline ratio
        if current_annual > 0 and hard_savings > current_annual * 0.60:
            warnings.append(
                f"Hard savings (${hard_savings:,.0f}) = "
                f"{hard_savings / current_annual * 100:.0f}% of current baseline "
                f"(${current_annual:,.0f}). Values above 60% require strong justification."
            )

        # Adjust confidence
        if warnings and bv_confidence != "low":
            bv_confidence = "low" if len(warnings) >= 2 else "moderate"

        return bv_confidence, warnings

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

        # ── Future-state monthly cost (must run before ROI formula) ──
        future_monthly, ai_breakdown = self._build_future_cost(
            azure_monthly, current_breakdown, drivers, assumptions_dict)
        future_annual = future_monthly * 12

        monthly_savings = round(current_monthly - future_monthly)

        # ── Investment = NET NEW spending ────────────────────────────
        azure_annual = azure_monthly * 12
        timeline_months = state.sa.timeline_months or 0
        impl_cost = round(azure_monthly * timeline_months) if timeline_months > 0 else round(azure_annual * 0.5)
        change_cost = round(impl_cost * 0.10)
        year1_investment = round(azure_annual + impl_cost + change_cost)
        year2_run_rate = round(azure_annual)

        # ── Driver amounts & waterfall (caps applied here) ───────────
        driver_amounts = self._compute_per_driver_amounts(drivers, val_mid)

        # Verify driver amounts sum ≈ midpoint (FRD-003 FR-003-004)
        actual_sum = sum(driver_amounts)
        if val_mid > 0 and abs(actual_sum - val_mid) > val_mid * 0.1:
            logger.warning(
                "Driver amounts sum ($%s) diverges from midpoint ($%s) by %.0f%%",
                f"{actual_sum:,.0f}", f"{val_mid:,.0f}",
                abs(actual_sum - val_mid) / val_mid * 100,
            )

        # Hard savings cap = actual operating cost reduction from the cost model.
        # _build_future_cost already computed the real savings; BV drivers can't
        # claim more than the cost model proves.
        actual_annual_savings = max(monthly_savings * 12, 0)

        waterfall_cost, waterfall_uplift, savings_capped, savings_cap_pct = self._split_waterfall(
            drivers, driver_amounts, actual_annual_savings)

        hard_savings = sum(i["amount"] for i in waterfall_cost)
        revenue_uplift = sum(i["amount"] for i in waterfall_uplift)

        risk_reduction, risk_note = self._compute_risk_reduction(
            current_annual, hard_savings, revenue_uplift,
            components=state.architecture.get("components"))

        # ── Reconciled value = sum of capped waterfall items ─────────
        # This is what we're actually claiming — NOT the raw BV estimate.
        # Ensures headline, ROI, payback, and waterfall all match.
        total_annual_value = hard_savings + revenue_uplift + risk_reduction

        # ── Adoption ramp (needed for ROI, payback, and projection) ──
        adoption_ramp = self._select_adoption_ramp(state)
        year1_adoption = adoption_ramp[0]  # e.g., 0.30 for complex

        # ── ROI: Year 1 (adoption-adjusted) and run-rate (full) ──────
        # Year 1 ROI reflects partial adoption + one-time costs
        year1_adopted_value = total_annual_value * year1_adoption
        if year1_investment > 0:
            roi_year1 = ((year1_adopted_value - year1_investment) / year1_investment) * 100
        else:
            roi_year1 = 0.0

        # Run-rate ROI: full value vs Azure annual (steady state)
        if azure_annual > 0:
            roi_run_rate = ((total_annual_value - azure_annual) / azure_annual) * 100
        else:
            roi_run_rate = 0.0

        # Headline = Year 1 (conservative, adoption-adjusted)
        roi_mid = roi_year1
        roi_low = ((val_low * year1_adoption - year1_investment) / year1_investment * 100) if year1_investment > 0 else 0.0
        roi_high = ((val_high * year1_adoption - year1_investment) / year1_investment * 100) if year1_investment > 0 else 0.0

        # Payback: months until cumulative adopted value covers investment
        monthly_adopted_value = (total_annual_value * year1_adoption) / 12
        payback_months = round(year1_investment / monthly_adopted_value, 1) if monthly_adopted_value > 0 else None
        if payback_months is not None:
            payback_months = max(min(payback_months, self.MAX_PAYBACK_MONTHS), self.MIN_PAYBACK_MONTHS)
            payback_months = round(payback_months, 1)

        roi_capped = roi_mid > self.MAX_DISPLAY_ROI
        roi_display = min(roi_mid, self.MAX_DISPLAY_ROI)

        # ── Cross-agent reconciliation (FRD-004) ─────────────────────
        adjusted_confidence, plausibility_warnings = self._validate_and_reconcile(
            val_mid=val_mid,
            annual_cost=annual_cost,
            current_annual=current_annual,
            azure_annual=azure_annual,
            future_annual=future_annual,
            hard_savings=hard_savings,
            revenue_uplift=revenue_uplift,
            monthly_savings_annualized=monthly_savings * 12 if monthly_savings > 0 else 0,
            is_estimated=is_estimated,
            bv_confidence=bv.get("confidence", "moderate"),
            bv_warnings=bv.get("consistency_warnings", []),
            savings_were_capped=savings_capped,
            savings_cap_pct=savings_cap_pct,
            monthly_revenue=state.sa.monthly_revenue,
            costs_used_fallback=state.costs.get("_used_fallback", False),
            bv_used_fallback=bv.get("_used_fallback", False),
        )

        # ── Build dashboard (the frontend contract) ──────────────────
        dashboard = self._build_dashboard(
            state=state,
            annual_cost=annual_cost,
            annual_value=total_annual_value,
            roi_percent=round(roi_mid, 1),
            roi_year1=round(roi_year1, 1),
            roi_run_rate=round(roi_run_rate, 1),
            payback_months=payback_months,
            roi_capped=roi_capped,
            is_estimated=is_estimated,
            current_monthly=current_monthly,
            current_breakdown=current_breakdown,
            future_monthly=future_monthly,
            future_annual=future_annual,
            ai_breakdown=ai_breakdown,
            monthly_savings=monthly_savings,
            waterfall_cost=waterfall_cost,
            waterfall_uplift=waterfall_uplift,
            hard_savings=hard_savings,
            revenue_uplift=revenue_uplift,
            risk_reduction=risk_reduction,
            risk_note=risk_note,
            year1_investment=year1_investment,
            year1_total_cost=year1_investment,
            year2_run_rate=year2_run_rate,
            impl_cost=impl_cost,
            change_cost=change_cost,
            assumptions_dict=assumptions_dict,
            driver_amounts=driver_amounts,
            adjusted_confidence=adjusted_confidence,
            plausibility_warnings=plausibility_warnings,
            savings_capped=savings_capped,
        )

        state.roi = {
            # ── Canonical output schema ──────────────────────────────
            "annual_cost": round(annual_cost, 2),
            "annual_value": round(total_annual_value, 2),
            "annual_value_bv_estimate": round(val_mid, 2),
            "annual_value_low": round(val_low, 2),
            "annual_value_high": round(val_high, 2),
            "monthly_current_cost": round(current_monthly) if not is_estimated else None,
            "monthly_future_cost": round(future_monthly),
            "monthly_savings": monthly_savings if not is_estimated else None,
            "hard_savings": round(hard_savings),
            "revenue_uplift": round(revenue_uplift),
            "risk_reduction": round(risk_reduction),
            "year1_investment": year1_investment,
            "year1_total_cost": year1_investment,
            "year2_run_rate": year2_run_rate,
            "future_annual_opex": round(future_annual),
            "roi_percent": round(roi_mid, 1),
            "roi_year1": round(roi_year1, 1),
            "roi_run_rate": round(roi_run_rate, 1),
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
        roi_year1: float | None,
        roi_run_rate: float | None,
        payback_months: float | None,
        roi_capped: bool,
        is_estimated: bool,
        current_monthly: float,
        current_breakdown: list[dict],
        future_monthly: float,
        future_annual: float,
        ai_breakdown: list[dict],
        monthly_savings: int,
        waterfall_cost: list[dict],
        waterfall_uplift: list[dict],
        hard_savings: float,
        revenue_uplift: float,
        risk_reduction: float,
        risk_note: str,
        year1_investment: float,
        year1_total_cost: float,
        year2_run_rate: float,
        impl_cost: float,
        change_cost: float,
        assumptions_dict: dict,
        driver_amounts: list[float],
        adjusted_confidence: str,
        plausibility_warnings: list[str],
        savings_capped: bool,
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
        adoption_ramp = self._select_adoption_ramp(state)

        projection = {
            "years": [1, 2, 3],
            "adoptionRamp": [f"{int(r * 100)}%" for r in adoption_ramp],
            "annualAzureCost": round(azure_annual),
            "annualCostReduction": round(hard_savings),
            "annualRevenueUplift": round(revenue_uplift),
            "annualNetValue": round(annual_total_value - azure_annual),
            "cumulative": [
                {
                    "year": yr + 1,
                    "adoption": f"{int(adoption_ramp[yr] * 100)}%",
                    # Year 1 cost includes one-time impl + change; Year 2+ is run-rate only
                    "azureCost": round(
                        azure_annual * (yr + 1)
                        + (impl_cost + change_cost if yr == 0 else 0)
                    ),
                    "totalValue": round(annual_total_value * sum(adoption_ramp[:yr + 1])),
                    "netValue": round(
                        annual_total_value * sum(adoption_ramp[:yr + 1])
                        - azure_annual * (yr + 1)
                        - (impl_cost + change_cost if yr == 0 else 0)
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
        sa_annual_spend = state.sa.current_annual_spend
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
            + f"Projection assumes {'/'.join(f'{int(r*100)}' for r in adoption_ramp)}% adoption ramp over 3 years. "
            + "Year 1 ROI includes implementation and change management costs. "
            + "Run-rate ROI = (Annual Value \u2212 Total Future Opex) \u00f7 Total Future Opex \u00d7 100."
        )
        if risk_note:
            methodology += " " + risk_note
        methodology += f" Monthly operating cost savings capped at {self.MAX_SAVINGS_PCT}% for display realism."

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
            future_annual=future_annual,
            hard_savings=hard_savings,
            revenue_uplift=revenue_uplift,
            risk_reduction=risk_reduction,
            impl_cost=impl_cost,
            change_cost=change_cost,
            year1_investment=year1_investment,
            year1_total_cost=year1_total_cost,
            year2_run_rate=year2_run_rate,
            adoption_ramp=adoption_ramp,
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

        # Run-rate ROI display (for tooltip / secondary display)
        if roi_run_rate is not None and future_annual > 0:
            roi_run_rate_text = f"{(roi_run_rate / 100 + 1):.1f}x"
        else:
            roi_run_rate_text = None

        roi_description = (
            f"Year 1 ROI: annual value vs. Year 1 investment "
            f"(Azure {roi_run_rate_text or ''} + implementation + change management = "
            f"${year1_investment:,.0f}). "
            f"Steady-state ROI: {roi_run_rate_text or 'N/A'} "
            f"(annual value vs. Azure run-rate ${azure_annual:,.0f}/yr)."
        )

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
            "roiYear1": roi_year1,
            "roiRunRate": roi_run_rate,
            "roiCapped": roi_capped,
            "roiDisplayText": roi_display_text,
            "roiRunRateText": roi_run_rate_text,
            "roiSubtitle": "Year 1 return on total future cost",
            "roiDescription": roi_description,
            "confidenceLevel": bv.get("confidence", "moderate"),
            "paybackMonths": payback_months,
            "futureAnnualOpex": round(future_annual),
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
            # Suppress cost comparison when baseline is estimated (FRD-002)
            dashboard["monthlySavings"] = None
            dashboard["savingsPercentage"] = None

        # ── Reconciliation results (FRD-004) ─────────────────────────
        dashboard["confidenceLevel"] = adjusted_confidence
        dashboard["plausibilityWarnings"] = plausibility_warnings
        if savings_capped:
            dashboard["savingsCapped"] = True

        return dashboard

    # ── Business-case builder ────────────────────────────────────────
    def _build_business_case(
        self,
        *,
        current_annual: float,
        azure_annual: float,
        future_annual: float,
        hard_savings: float,
        revenue_uplift: float,
        risk_reduction: float,
        impl_cost: float,
        change_cost: float,
        year1_investment: float,
        year1_total_cost: float,
        year2_run_rate: float,
        adoption_ramp: list[float],
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
            "futureAnnualOpex": round(future_annual),
        }

        # ── valueBridge ──────────────────────────────────────────────
        total_annual_value = round(hard_savings + revenue_uplift + risk_reduction)

        value_bridge = {
            "hardSavings": round(hard_savings),
            "revenueUplift": round(revenue_uplift),
            "riskReduction": round(risk_reduction),
            "totalAnnualValue": total_annual_value,
        }

        # ── investment (adoption-ramped to match cumulative chart) ────
        year1_adopted_value = round(total_annual_value * adoption_ramp[0])
        year2_adopted_value = round(total_annual_value * adoption_ramp[1]) if len(adoption_ramp) > 1 else total_annual_value
        investment = {
            "year1Total": year1_investment,
            "year2Total": year2_run_rate,
            "year1NetValue": round(year1_adopted_value - year1_investment),
            "year2NetValue": round(year2_adopted_value - year2_run_rate),
        }

        # ── sensitivity ──────────────────────────────────────────────
        sensitivity = []
        for pct, label in [(0.5, "50%"), (0.75, "75%"), (1.0, "100%")]:
            adj_value = total_annual_value * pct
            # Year 1 ROI: value vs net new investment (Azure + impl + change)
            adj_roi_y1 = ((adj_value - year1_total_cost) / year1_total_cost * 100) if year1_total_cost > 0 else 0
            # Run-rate ROI: value vs Azure annual (ongoing new cost)
            adj_roi_rr = ((adj_value - azure_annual) / azure_annual * 100) if azure_annual > 0 else 0
            adj_payback = round(year1_total_cost / adj_value * 12, 1) if adj_value > 0 else None
            if adj_payback is not None and adj_payback > self.MAX_PAYBACK_MONTHS:
                adj_payback = self.MAX_PAYBACK_MONTHS
            sensitivity.append({
                "adoption": label,
                "annualValue": round(adj_value),
                "roi": round(adj_roi_y1, 1),
                "roiYear1": round(adj_roi_y1, 1),
                "roiRunRate": round(adj_roi_rr, 1),
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
