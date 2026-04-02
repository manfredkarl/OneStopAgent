# Fix Guide: ROI, Cost & Business Value Agents

> Companion to `AGENT_ISSUES.md` — covers all 23 issues + 5 cross-agent disconnects.
> Fixes are ordered by implementation sequence. Each fix is self-contained.
> Where the original analysis proposed multiple options, this doc picks one.

---

## Phase 1 — Foundation: Canonical Baseline & Typed Schema

These fixes must land first because nearly every other fix depends on agents
sharing the same resolved values.

### Fix A: Typed `SharedAssumptions` Schema (Issues #6, #7, #22; Disconnect #3)

**Files:** `state.py`, `maf_orchestrator.py`

**Root cause:** `shared_assumptions` is `dict[str, Any]` with LLM-generated keys.
Three agents each fuzzy-match against their own key lists.  Same value can
resolve differently in each agent.

**Fix:** Add a `SharedAssumptions` dataclass that centralizes parsing in one place.
All downstream agents use typed fields — no more fuzzy matching.

```python
# state.py — add above AgentState

@dataclass
class SharedAssumptions:
    current_annual_spend: float | None = None
    hourly_labor_rate: float | None = None
    total_users: int | None = None
    concurrent_users: int | None = None
    data_volume_gb: float | None = None
    timeline_months: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SharedAssumptions":
        sa = cls(raw=raw)
        for key, value in raw.items():
            if key.startswith("_"):
                continue
            k = key.lower()
            try:
                v = float(value)
            except (ValueError, TypeError):
                continue
            if ("spend" in k or ("cost" in k and "current" in k)) and v > 1000:
                sa.current_annual_spend = sa.current_annual_spend or v
            elif ("labor" in k or "hourly" in k) and "rate" in k:
                sa.hourly_labor_rate = sa.hourly_labor_rate or v
            elif "concurrent" in k and v > 1:
                sa.concurrent_users = sa.concurrent_users or int(v)
            elif ("user" in k or "engineer" in k) and v > 1:
                sa.total_users = sa.total_users or int(v)
            elif "volume" in k and "gb" in k:
                sa.data_volume_gb = sa.data_volume_gb or v
            elif "timeline" in k and "month" in k:
                sa.timeline_months = sa.timeline_months or int(v)
        return sa
```

In `AgentState`, add a cached property:

```python
@property
def sa(self) -> SharedAssumptions:
    return SharedAssumptions.from_dict(self.shared_assumptions)
```

**Cleanup:** Delete `_CURRENT_SPEND_KEYS`, `_LABOR_RATE_KEYS`, and `_resolve_sa()`
from `roi_agent.py`.  Every consumer becomes e.g. `state.sa.current_annual_spend`.

---

### Fix B: Assumption Question Dedup (Issue #22 boundary; Disconnect #4)

**Files:** new `agents/assumption_catalog.py`, `cost_agent.py`, `business_value_agent.py`

**Problem:** Two agents independently LLM-generate 3–5 questions.  No dedup,
no shared schema, questions can semantically overlap with shared assumptions.

**Fix:** Define a blocklist of IDs that are already covered, including semantic aliases.
Filter every LLM-generated question set before presenting to the user.

```python
# agents/assumption_catalog.py

SHARED_ASSUMPTION_IDS = {
    "total_users", "current_annual_spend", "hourly_labor_rate", "concurrent_users",
}

SEMANTIC_OVERLAPS = {
    "monthly_it_spend", "annual_it_spend", "current_spend",
    "hourly_rate", "headcount", "total_employees",
}

BLOCKED_IDS = SHARED_ASSUMPTION_IDS | SEMANTIC_OVERLAPS

def filter_already_answered(questions: list[dict], state) -> list[dict]:
    sa_ids = set(state.shared_assumptions.keys()) - {"_items"}
    blocked = sa_ids | BLOCKED_IDS
    return [q for q in questions if q["id"] not in blocked]
```

Call in both `CostAgent.generate_usage_assumptions()` and
`BusinessValueAgent.generate_assumptions()`:

```python
from agents.assumption_catalog import filter_already_answered
assumptions = filter_already_answered(assumptions, state)
```

---

## Phase 2 — ROI Formula Corrections

### Fix C + V: Honest ROI Denominator (Issues #1, #2; NEW)

**File:** `roi_agent.py`

**Prerequisite:** Move the Investment computation block (currently ~line 393)
to just after the current-state baseline resolution (~line 370).  `_build_future_cost`
(Fix I) must run before this block so that `future_annual` is available.

**Rewritten ROI + payback block:**

```python
# ── Investment (moved up) ────────────────────────────────────
azure_annual = azure_monthly * 12
timeline_months = state.sa.timeline_months or 0
impl_cost = round(azure_monthly * timeline_months) if timeline_months > 0 else round(azure_annual * 0.5)
change_cost = round(impl_cost * 0.10)
year1_investment = round(azure_annual + impl_cost + change_cost)
year2_run_rate = round(azure_annual)

# ── Core ROI math ────────────────────────────────────────────
val_mid = (val_low + val_high) / 2

# ── Future operating cost (from _build_future_cost, Fix I) ───
# future_annual already computed above via _build_future_cost:
#   future_annual = Azure + reduced labor + carried overhead
# This is the TRUE cost of running the solution, not just Azure.

# Year 1 ROI (headline — includes one-time costs on top of future opex)
year1_total_cost = future_annual + impl_cost + change_cost
roi_year1 = ((val_mid - year1_total_cost) / year1_total_cost) * 100 if year1_total_cost > 0 else 0
# Run-rate ROI (steady state, Year 2+ — just future operating cost)
roi_run_rate = ((val_mid - future_annual) / future_annual) * 100 if future_annual > 0 else 0

# Headline = Year 1 (conservative for decision-makers)
roi_mid = roi_year1

# Payback: months until cumulative value covers Year 1 total cost
payback_months = round((year1_total_cost / val_mid) * 12, 1) if val_mid > 0 else None
if payback_months is not None:
    payback_months = max(min(payback_months, self.MAX_PAYBACK_MONTHS), self.MIN_PAYBACK_MONTHS)
```

**State output additions:**

```python
"roi_year1": round(roi_year1, 1),
"roi_run_rate": round(roi_run_rate, 1),
"year1_total_cost": year1_total_cost,
"future_annual_opex": future_annual,
```

**Dashboard addition:**

```python
dashboard["roiRunRate"] = round(roi_run_rate, 1)
dashboard["futureAnnualOpex"] = future_annual
```

Frontend shows both: "Year 1: 2.1× | Steady state: 3.5×".
Tooltip: "Year 1 includes implementation costs. Steady state = value vs. total future operating cost (Azure + labor + overhead).".

**Fix V rationale:** The original guide used `year1_investment` (Azure + impl +
change) as denominator but excluded ongoing labor and overhead that carry
forward post-migration.  True ROI should measure value against the *total*
future operating cost — Azure platform fees + reduced-but-nonzero labor +
carried overhead — which is exactly what `_build_future_cost` (Fix I) returns.
This gives the most honest ROI because:
- Year 1 denominator = `future_annual + impl_cost + change_cost` (everything)
- Run-rate denominator = `future_annual` (Azure + reduced labor + overhead)
- If labor costs carry at 70% of original, that's reflected in both the
  numerator (as a smaller savings) and the denominator (as a real cost)

**Also fix the sensitivity table** in `_build_business_case` to match:

```python
for pct, label in [(0.5, "50%"), (0.75, "75%"), (1.0, "100%")]:
    adj_value = total_annual_value * pct
    adj_roi_y1 = ((adj_value - year1_total_cost) / year1_total_cost * 100) if year1_total_cost > 0 else 0
    adj_roi_rr = ((adj_value - future_annual) / future_annual * 100) if future_annual > 0 else 0
    adj_payback = round(year1_total_cost * 12 / adj_value, 1) if adj_value > 0 else None
    if adj_payback is not None and adj_payback > self.MAX_PAYBACK_MONTHS:
        adj_payback = self.MAX_PAYBACK_MONTHS
    sensitivity.append({
        "adoption": label,
        "annualValue": round(adj_value),
        "roiYear1": round(adj_roi_y1, 1),
        "roiRunRate": round(adj_roi_rr, 1),
        "paybackMonths": adj_payback,
    })
```

---

### Fix D: Estimated Baseline — Variable Multiplier (Issue #4)

**File:** `roi_agent.py`

**Problem:** `ESTIMATED_BASELINE_MULTIPLIER = 1.5` is one constant for all scenarios.

**Fix:** Make it vary by architecture complexity.  When baseline is estimated,
suppress the cost comparison to avoid displaying fabricated savings.

```python
def _estimate_baseline_multiplier(self, state: AgentState) -> float:
    component_count = len(state.architecture.get("components", []))
    if component_count <= 3:
        return 1.2
    elif component_count <= 7:
        return 1.5
    else:
        return 2.0
```

In `_resolve_current_baseline`, use the dynamic multiplier:

```python
# Priority 3: estimated fallback
multiplier = self._estimate_baseline_multiplier(state)
estimated = round(azure_monthly * multiplier)
return (estimated,
        [{"label": "Operations (estimated)", "amount": round(estimated * 0.75)},
         {"label": "Overhead (estimated)", "amount": round(estimated * 0.25)}],
        True)
```

**Suppress fake savings in the dashboard when estimated:**

```python
if is_estimated:
    dashboard["costComparisonAvailable"] = False
    dashboard["monthlySavings"] = None
    dashboard["savingsPercentage"] = None
    dashboard["costEstimated"] = True
    dashboard["warning"] = (
        "Current cost estimated — provide actual figures for accurate comparison"
    )
```

---

## Phase 3 — Value Verification Pipeline

### Fix E: Structured BV Driver Schema (Issue #5)

**File:** `business_value_agent.py` (LLM prompt), `roi_agent.py` (consumer)

**Problem:** `_extract_coverage_from_drivers()` parses free-text metric strings
via regex.  Fragile; silent 25% fallback.

**Fix:** Add `impact_pct_low` and `impact_pct_high` as required numeric fields
in the BV agent's LLM prompt:

```json
{
    "name": "Engineering Productivity",
    "metric": "20–30% time savings",
    "impact_pct_low": 20,
    "impact_pct_high": 30,
    "category": "cost_reduction",
    "source_name": "...",
    "source_url": ""
}
```

Add to the LLM prompt's JSON schema instructions:

```
- "impact_pct_low": numeric low-end of the percentage range
- "impact_pct_high": numeric high-end of the percentage range
These MUST match the numbers in the "metric" field.
```

In `roi_agent.py`, replace the regex-based `_extract_coverage_from_drivers`:

```python
def _extract_coverage_from_drivers(self, drivers: list[dict]) -> float | None:
    for driver in drivers:
        low = driver.get("impact_pct_low")
        high = driver.get("impact_pct_high")
        if low is not None and high is not None:
            try:
                return (float(low) + float(high)) / 2 / 100
            except (ValueError, TypeError):
                continue
    return None  # No fallback — caller handles None
```

---

### Fix F: Validate LLM Value Range + Cross-Check Drivers (Issue #3; Disconnect #2)

**File:** `business_value_agent.py`

**Problem:** `annual_impact_range` from LLM is unverified.  Driver percentages
may not match the dollar range.  Cost-reduction drivers can exceed the baseline.

This fix merges the original value-range validation and driver arithmetic
verification into one function called after LLM parsing.

```python
def _validate_and_verify(
    self,
    result: dict,
    state: AgentState,
) -> tuple[dict | None, list[str]]:
    """Validate impact range AND verify driver arithmetic.

    Returns (corrected_range_or_None, warning_list).
    """
    warnings: list[str] = []
    impact_range = result.get("annual_impact_range")
    drivers = result.get("drivers", [])
    current_spend = state.sa.current_annual_spend
    azure_annual = state.costs.get("estimate", {}).get("totalAnnual", 0)

    # ── Range validation ─────────────────────────────────────
    if not impact_range or not isinstance(impact_range, dict):
        return None, ["No impact range provided by value model."]

    try:
        low, high = float(impact_range.get("low", 0)), float(impact_range.get("high", 0))
    except (ValueError, TypeError):
        return None, ["Impact range contains non-numeric values."]

    if low > high:
        low, high = high, low
    if low < 0:
        low = 0
    if high <= 0:
        return None, ["Impact range is zero or negative."]

    # Extreme hallucination guard: >200× Azure cost
    if azure_annual > 0 and high > azure_annual * 200:
        high = azure_annual * 200
        low = min(low, high)
        warnings.append("Impact range capped (exceeded 200× Azure cost).")

    # Economic plausibility: flag if >3× current baseline
    if current_spend and current_spend > 0 and high > current_spend * 3:
        warnings.append(
            f"Impact high (${high:,.0f}) is >{high/current_spend:.1f}× current spend "
            f"(${current_spend:,.0f}). Verify revenue uplift assumptions."
        )

    # ── Driver arithmetic verification ───────────────────────
    if current_spend and current_spend > 0:
        cost_reduction_implied = 0.0
        for d in drivers:
            if d.get("category") != "cost_reduction":
                continue
            pct_low = d.get("impact_pct_low", 0) or 0
            pct_high = d.get("impact_pct_high", 0) or 0
            mid_pct = (pct_low + pct_high) / 2 / 100
            cost_reduction_implied += current_spend * mid_pct

        if cost_reduction_implied > current_spend:
            warnings.append(
                f"Cost-reduction drivers imply ${cost_reduction_implied:,.0f}/yr "
                f"but current spend is ${current_spend:,.0f}/yr. Over-counting."
            )

    return {"low": round(low, 2), "high": round(high, 2)}, warnings
```

**Call site** — after `json.loads(text)` in Phase 2:

```python
validated_range, bv_warnings = self._validate_and_verify(result, state)

confidence = result.get("confidence", "moderate")
if bv_warnings:
    confidence = "low"
    for w in bv_warnings:
        logger.warning("BV validation: %s", w)

state.business_value = {
    "drivers": drivers,
    "annual_impact_range": validated_range,
    "assumptions": result.get("assumptions", []),
    "confidence": confidence,
    "consistency_warnings": bv_warnings,
    "user_assumptions": user_assumptions,
    "sources": [...],
}
```

**Additionally — in `roi_agent.py`,** verify that driver amounts sum to the midpoint
after `_compute_per_driver_amounts()`:

```python
driver_amounts = self._compute_per_driver_amounts(drivers, val_mid)
actual_sum = sum(driver_amounts)
if val_mid > 0 and abs(actual_sum - val_mid) > val_mid * 0.1:
    logger.warning(
        "Driver amounts sum ($%s) diverges from midpoint ($%s) by %.0f%%",
        actual_sum, val_mid, abs(actual_sum - val_mid) / val_mid * 100,
    )
```

---

### Fix G: Cost Agent Plausibility Check (Disconnect #1)

**File:** `cost_agent.py`

**Problem:** Cost Agent never reads `current_annual_spend`.  Its Azure
run-rate has zero relationship to the user's existing spend.

**Fix:** After computing `total_annual`, compare against the canonical baseline:

```python
# At the end of CostAgent.run(), after computing total_annual:

current_spend = state.sa.current_annual_spend
if current_spend and current_spend > 0:
    ratio = total_annual / current_spend
    if ratio > 2.0:
        assumptions.append(
            f"⚠️ Azure estimate (${total_annual:,.0f}/yr) exceeds current spend "
            f"(${current_spend:,.0f}/yr) by {ratio:.1f}×. Verify sizing."
        )
    elif ratio < 0.03:
        assumptions.append(
            f"ℹ️ Azure estimate (${total_annual:,.0f}/yr) is {ratio*100:.1f}% of "
            f"current spend (${current_spend:,.0f}/yr). Confirm scope replacement."
        )
```

---

### Fix H: ROI Plausibility Checks + Reconciliation (Disconnect #5; Issue #21)

**File:** `roi_agent.py`

**Problem:** ROI agent blindly divides value by cost.  No cross-check.
Hard-savings cap is invisible to the user.

**Fix:** Single `_validate_and_reconcile` method called before building the dashboard:

```python
def _validate_and_reconcile(
    self,
    *,
    val_mid: float,
    annual_cost: float,
    current_annual: float,
    azure_annual: float,
    hard_savings: float,
    revenue_uplift: float,
    is_estimated: bool,
    bv_confidence: str,
    bv_warnings: list[str],
    savings_were_capped: bool,
    savings_cap_pct: float,
    monthly_revenue: float | None,
) -> tuple[str, list[str]]:
    """Run all plausibility checks.  Returns (adjusted_confidence, warnings)."""
    warnings = list(bv_warnings)

    # Value-to-Azure-cost ratio
    if annual_cost > 0:
        ratio = val_mid / annual_cost
        if ratio > 50:
            warnings.append(
                f"Value (${val_mid:,.0f}) is {ratio:.0f}× Azure cost. Unusually high."
            )
            bv_confidence = "low"
        elif ratio > 20:
            warnings.append(f"Value-to-cost ratio is {ratio:.0f}×. On the high end.")

    # Hard savings cap transparency
    if savings_were_capped:
        warnings.append(
            f"Cost savings reduced by {savings_cap_pct:.0f}% to not exceed "
            f"the current baseline. Original driver estimates were higher."
        )

    # Revenue uplift vs stated revenue
    if monthly_revenue and monthly_revenue > 0:
        annual_revenue = monthly_revenue * 12
        if revenue_uplift > annual_revenue * 0.5:
            warnings.append(
                f"Revenue uplift (${revenue_uplift:,.0f}) is "
                f">{revenue_uplift/annual_revenue*100:.0f}% of stated revenue."
            )

    # Accounting identity: components should sum to ~midpoint
    component_sum = hard_savings + revenue_uplift
    if val_mid > 0 and abs(component_sum - val_mid) > val_mid * 0.15:
        warnings.append(
            f"Driver sum (${component_sum:,.0f}) differs from impact midpoint "
            f"(${val_mid:,.0f}) by {abs(component_sum - val_mid) / val_mid * 100:.0f}%."
        )

    # Cost-reduction-only: Azure shouldn't exceed current
    if revenue_uplift == 0 and not is_estimated and current_annual > 0:
        if azure_annual > current_annual:
            warnings.append(
                f"Azure cost (${azure_annual:,.0f}/yr) > current cost "
                f"(${current_annual:,.0f}/yr) with no revenue uplift."
            )

    # Adjust confidence
    if warnings and bv_confidence != "low":
        bv_confidence = "low" if len(warnings) >= 2 else "moderate"

    return bv_confidence, warnings
```

**In `_split_waterfall`**, track when capping occurs (return 4-tuple):

```python
savings_capped = False
savings_cap_pct = 0.0
if current_annual > 0 and raw_hard > current_annual:
    scale = current_annual / raw_hard
    cost_items = [{"label": i["label"], "amount": round(i["amount"] * scale)}
                  for i in cost_items]
    savings_capped = True
    savings_cap_pct = round((1 - scale) * 100)

return cost_items, uplift_items, savings_capped, savings_cap_pct
```

**Dashboard output:**

```python
adjusted_confidence, plausibility_warnings = self._validate_and_reconcile(...)

dashboard["confidenceLevel"] = adjusted_confidence
dashboard["plausibilityWarnings"] = plausibility_warnings
if savings_capped:
    dashboard["savingsCapped"] = True
```

---

## Phase 4 — Future-State Cost Model

### Fix I: Derive Reductions from BV Drivers (Issue #8)

**File:** `roi_agent.py`

**Depends on:** Fix E (structured `impact_pct_low/high` fields)

**Problem:** `_build_future_cost()` uses hardcoded constants (10% overhead,
50% error reduction, 60/40 split).

**Fix:** Source reductions from BV driver percentages, applied per cost pool
(not naively summed).  A driver that targets "labor" only reduces the labor
line items; a driver that targets "tooling" only reduces tooling line items.
This prevents 30% labor + 20% tooling from being treated as 50% across
everything when labor is only 60% of the total.

**Caveat addressed:** Multiple drivers targeting *different* cost pools are
applied independently to their respective pools.  A driver with no clear pool
match gets a blended application across all non-Azure items, capped at 80% per
item (not 80% total).

```python
# Cost-pool keywords — map driver names/metrics to breakdown line items
POOL_KEYWORDS = {
    "labor":   ["labor", "staff", "fte", "headcount", "personnel", "operations"],
    "tooling": ["tool", "license", "software", "saas"],
    "error":   ["error", "rework", "defect", "incident", "downtime"],
}

def _classify_driver_pool(self, driver: dict) -> str | None:
    """Match a BV driver to a cost pool, or None for 'general'."""
    text = (driver.get("name", "") + " " + driver.get("metric", "")).lower()
    for pool, keywords in self.POOL_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return pool
    return None  # general / blended

def _matches_pool(self, label: str, pool: str | None) -> bool:
    """Check if a breakdown line item belongs to the given pool."""
    if pool is None:
        return True  # general driver applies to all non-Azure items
    return any(kw in label for kw in self.POOL_KEYWORDS.get(pool, []))

def _build_future_cost(self, azure_monthly, current_breakdown, bv_drivers, assumptions_dict):
    ai_breakdown = [{"label": "Azure platform", "amount": azure_monthly}]

    # Build per-pool reduction percentages from drivers
    pool_reductions: dict[str | None, float] = {}  # pool → reduction fraction
    for d in bv_drivers:
        if d.get("category") != "cost_reduction":
            continue
        low = d.get("impact_pct_low", 0) or 0
        high = d.get("impact_pct_high", 0) or 0
        mid_pct = (low + high) / 2 / 100
        pool = self._classify_driver_pool(d)
        # Accumulate multiplicatively: two 30% reductions = 1 - (0.7 × 0.7) = 51%, not 60%
        existing = pool_reductions.get(pool, 0.0)
        pool_reductions[pool] = 1 - (1 - existing) * (1 - mid_pct)

    # Cap each pool at 80%
    for pool in pool_reductions:
        pool_reductions[pool] = min(pool_reductions[pool], 0.80)

    for item in current_breakdown:
        label = item["label"].lower()

        # Find the best matching pool reduction for this line item
        reduction = 0.0
        for pool, pct in pool_reductions.items():
            if self._matches_pool(label, pool):
                # Take the highest applicable reduction (specific pool wins over general)
                if pool is not None:
                    reduction = max(reduction, pct)
                elif reduction == 0.0:
                    # General driver only applies if no specific pool matched
                    reduction = pct

        reduced = round(item["amount"] * (1 - reduction))
        suffix = " (reduced)" if reduction > 0 else ""
        if reduced > 0:
            ai_breakdown.append({"label": item["label"] + suffix, "amount": reduced})

    future_total = sum(i["amount"] for i in ai_breakdown)
    return (future_total, ai_breakdown)
```

**Key properties:**
- Drivers are multiplicative within a pool: two 30% labor drivers → 51% labor reduction, not 60%
- Cross-pool drivers don't interact: 30% labor + 20% tooling stays independent
- Per-item cap of 80% prevents any line item from going negative
- `_build_future_cost` now returns the total future operating cost (Azure + reduced labor + carried overhead) — this feeds Fix V

---

## Phase 5 — Cost Agent Accuracy

### Fix J: SKU Tier-Proximity Scoring (Issue #10)

**File:** `services/pricing.py`

**Problem:** `_find_best_match()` returns median-priced item when no SKU matches.
"B1" lookup can return "P3v3" pricing (10-50× off).

**Fix:** Replace median fallback with tier-proximity scoring:

```python
TIER_ORDER = ["free", "shared", "basic", "b", "standard", "s", "premium", "p", "isolated", "i"]

def _tier_distance(requested: str, candidate: str) -> int:
    req_lower = requested.lower()
    cand_lower = candidate.lower()
    req_idx = next((i for i, t in enumerate(TIER_ORDER) if t in req_lower), 5)
    cand_idx = next((i for i, t in enumerate(TIER_ORDER) if t in cand_lower), 5)
    return abs(req_idx - cand_idx)
```

In `_find_best_match`, replace step 3:

```python
# 3. Nearest-tier match (replaces median fallback)
non_zero = [
    i for i in items
    if i.get("retailPrice", 0) > 0
    and "low priority" not in (i.get("skuName") or "").lower()
    and "spot" not in (i.get("skuName") or "").lower()
]
if non_zero:
    non_zero.sort(key=lambda i: _tier_distance(sku, i.get("skuName", "")))
    return non_zero[0]
```

---

### Fix K: Parallel Pricing + Session Cache (Issues #9, #19)

**File:** `cost_agent.py`

**Problem:** Sequential pricing calls (up to 150s). No caching.

**Fix:**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _price_selections(self, selections, users, usage_dict=None):
    items = []
    assumptions = [
        "Based on 730 hours/month for hourly-priced services",
        "Pay-as-you-go pricing (no reservations or savings plans)",
    ]
    source_counts = {}
    price_cache: dict[tuple, dict] = {}

    def _price_one(sel):
        service_name = sel.get("serviceName", "")
        sku = sel.get("sku", "")
        region = sel.get("region", "eastus")
        if service_name == "Multi-region overhead":
            return None
        cache_key = (service_name, sku, region)
        if cache_key in price_cache:
            return (sel, price_cache[cache_key])
        result = query_azure_pricing_sync(service_name, sku, region)
        price_cache[cache_key] = result
        return (sel, result)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(_price_one, sel) for sel in selections]
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                continue
            sel, pricing = result
            # ... existing per-item processing unchanged ...
```

---

### Fix L: Better Unit Detection (Issue #14)

**File:** `cost_agent.py`

**Problem:** Unrecognized units default to hourly (×730). Per-GB-day → wildly overcharged.

**Fix:** Explicit whitelist; unknown units treated as monthly (safer):

```python
HOURLY_UNITS = {"1 hour", "1/hour", "hour", "hours"}
MONTHLY_UNITS = {"1 month", "1/month", "month"}
DAILY_UNITS = {"1 day", "1/day", "day"}

# In _calculate_monthly, replace the final else:
    else:
        logger.warning("Unknown pricing unit '%s' for %s — treating as monthly", unit, service_name)
        return unit_price  # monthly is the safest default
```

---

### Fix M: Configurable Multi-Region Overhead (Issue #15)

**File:** `cost_agent.py`

**Problem:** Fixed 40% overhead for all multi-region scenarios.

**Fix:** Have the LLM include an `haPattern` field in its service mapping output.
Use it to select the overhead multiplier:

```python
MULTI_REGION_OVERHEAD = {
    "active-active": 0.50,
    "active-passive": 0.30,
    "default": 0.40,
}

# In _handle_multi_region:
ha_pattern = selections[0].get("haPattern", "default") if selections else "default"
overhead_pct = MULTI_REGION_OVERHEAD.get(ha_pattern, 0.40)
overhead = sum(item.get("monthlyCost", 0) for item in items) * overhead_pct
```

---

### Fix N: Configurable AI Pricing (Issue #13)

**File:** `services/pricing.py`

**Problem:** `$0.006/request` is hardcoded for GPT-4o. Token counts and pricing change.

**Fix:** Extract to a config dict with staleness warning:

```python
import datetime

AI_MODEL_PRICING = {
    "gpt-4o": {
        "input_per_1m": 2.50,
        "output_per_1m": 10.00,
        "avg_input_tokens": 800,
        "avg_output_tokens": 400,
        "last_updated": "2026-01-15",
    },
}

def per_request_cost(model: str = "gpt-4o") -> float:
    m = AI_MODEL_PRICING[model]
    age = (datetime.date.today() - datetime.date.fromisoformat(m["last_updated"])).days
    if age > 90:
        logger.warning("AI pricing for %s is %d days old — verify current rates", model, age)
    return (m["avg_input_tokens"] / 1_000_000 * m["input_per_1m"]
          + m["avg_output_tokens"] / 1_000_000 * m["output_per_1m"])
```

Update `ESTIMATED_PRICES` entries to call `per_request_cost()` instead of
hardcoding `0.006`.

---

## Phase 6 — ROI Model Refinements

### Fix O: Context-Aware Risk Reduction (Issue #11)

**File:** `roi_agent.py`

**Problem:** Risk is always 3% of current spend.

**Fix:**

```python
@staticmethod
def _compute_risk_reduction(current_annual, hard_savings, revenue_uplift,
                            components: list[dict] = None) -> tuple[float, str]:
    has_security = any("security" in str(c).lower() for c in (components or []))
    has_compliance = any("compliance" in str(c).lower() for c in (components or []))
    has_ha = any("availability" in str(c).lower() or "disaster" in str(c).lower()
                 for c in (components or []))

    risk_factor = 0.02
    if has_security: risk_factor += 0.02
    if has_compliance: risk_factor += 0.02
    if has_ha: risk_factor += 0.01
    risk_factor = min(risk_factor, 0.07)

    risk_raw = round(current_annual * risk_factor)
    preliminary = hard_savings + revenue_uplift
    if preliminary > 0 and risk_raw < preliminary * 0.05:
        return (0, f"Risk reduction (${risk_raw:,}) excluded as immaterial.")
    return (risk_raw, f"Risk reduction at {risk_factor*100:.0f}% of current annual spend.")
```

---

### Fix P: Complexity-Based Adoption Ramp (Issue #17)

**File:** `roi_agent.py`

**Problem:** Same 50/85/100% ramp for all scenarios.

**Fix:**

```python
ADOPTION_RAMPS = {
    "simple":  [0.70, 0.95, 1.00],
    "medium":  [0.50, 0.85, 1.00],
    "complex": [0.30, 0.65, 0.90],
}

def _select_adoption_ramp(self, state: AgentState) -> list[float]:
    n = len(state.architecture.get("components", []))
    if n <= 3:   return self.ADOPTION_RAMPS["simple"]
    elif n <= 8: return self.ADOPTION_RAMPS["medium"]
    else:        return self.ADOPTION_RAMPS["complex"]
```

Call `self._select_adoption_ramp(state)` instead of `self.ADOPTION_RAMP`.

---

### Fix Q: Remove `productivityGains` (Issue #18)

**File:** `roi_agent.py` (`_build_business_case`)

**Problem:** `productivityGains: 0` is permanently zero but exists in the schema.

**Fix:** Remove it from `valueBridge`:

```python
value_bridge = {
    "hardSavings": round(hard_savings),
    "revenueUplift": round(revenue_uplift),
    "riskReduction": round(risk_reduction),
    "totalAnnualValue": total_annual_value,
}
```

Remove the corresponding field from the frontend `BusinessCase` interface.

---

## Phase 7 — BV Agent Quality

### Fix R: Flexible Driver Count (Issue #12)

**File:** `business_value_agent.py`

**Problem:** Forced exactly 3 drivers — too many for simple cases, too few for complex.

**Fix:** Change the prompt from:
```
"Produce EXACTLY 3 benchmark-backed value drivers"
```
To:
```
"Produce 2–4 benchmark-backed value drivers (fewer for simple use cases)"
```

Remove the `[:3]` slice on the drivers list.  Keep `[:5]` as a safety cap.

---

### Fix S: Downgrade Confidence Without Benchmarks (Issue #16)

**File:** `business_value_agent.py`

**Problem:** Confidence stays "moderate" even when web search returns nothing.

**Fix:** After the `search_industry_benchmarks` call:

```python
benchmark_available = bool(search_results)
```

After setting `state.business_value`:

```python
if not benchmark_available:
    if state.business_value.get("confidence") == "high":
        state.business_value["confidence"] = "moderate"
    state.business_value["methodology_note"] = (
        "Value drivers computed from user-provided assumptions. "
        "No external industry benchmarks were available for validation."
    )
```

---

## Phase 8 — Error Handling & Transparency

### Fix T: Flag Fallback Results (Issue #20)

**Files:** `cost_agent.py`, `business_value_agent.py`

**Problem:** JSON parse failures silently produce "Standard" SKU placeholders
or empty driver lists with "moderate" confidence.

**Fix:** In both agents' `except` blocks:

```python
# CostAgent:
state.costs["_used_fallback"] = True

# BusinessValueAgent:
state.business_value["_used_fallback"] = True
state.business_value["confidence"] = "low"
```

In `roi_agent.py`'s plausibility check (Fix H), add:

```python
if state.costs.get("_used_fallback") or state.business_value.get("_used_fallback"):
    warnings.append("One or more agents used fallback data due to errors.")
    bv_confidence = "low"
```

---

### Fix U: Typed Exception Handling (Issue #23)

**Files:** `cost_agent.py`, `business_value_agent.py`

**Problem:** Broad `except Exception` catches everything identically.

**Fix:**

```python
except json.JSONDecodeError as e:
    logger.error("LLM returned invalid JSON: %s", e, exc_info=True)
    state.business_value = { ..., "confidence": "low", "error_type": "json_parse" }
except Exception as e:
    logger.error("Unexpected error: %s", e, exc_info=True)
    state.business_value = { ..., "confidence": "low", "error_type": "unknown" }
```

The `error_type` lets the frontend show context-specific messaging.

---

## Coverage Matrix

| Issue # | Description | Fix |
|---------|-------------|-----|
| 1 | ROI excludes implementation costs | C |
| 2 | Payback ignores implementation | C |
| 3 | No LLM value range validation | F |
| 4 | Arbitrary estimated baseline | D |
| 5 | Fragile regex for AI coverage | E |
| 6 | Fuzzy key resolution cascade | A |
| 7 | Schema-free shared_assumptions | A |
| 8 | Hardcoded future-state reductions | I |
| 9 | Sequential pricing API calls | K |
| 10 | Median SKU fallback | J |
| 11 | Fixed 3% risk reduction | O |
| 12 | Forced 3 drivers | R |
| 13 | Hardcoded AI pricing | N |
| 14 | Unit detection fallthrough | L |
| 15 | Fixed 40% multi-region overhead | M |
| 16 | Silent search failure | S |
| 17 | Fixed adoption ramp | P |
| 18 | productivityGains always 0 | Q |
| 19 | No pricing cache | K |
| 20 | Silent JSON parse fallbacks | T |
| 21 | Hidden savings cap | H |
| 22 | Stringly-typed assumptions | A |
| 23 | Broad exception swallowing | U |
| D1 | Cost ignores baseline | G |
| D2 | BV unverified math | F |
| D3 | ROI re-derives baseline | A |
| D4 | Uncoordinated question sets | B |
| D5 | No value-to-cost validation | H |
| NEW | ROI denominator excludes carried opex | V |

---

## Implementation Order

```
Phase 1 (foundation):     A → B
Phase 2 (ROI formula):    C+V → D
Phase 3 (value verify):   E → F → G → H
Phase 4 (future-state):   I
Phase 5 (cost accuracy):  J → K → L → M → N
Phase 6 (ROI model):      O → P → Q
Phase 7 (BV quality):     R → S
Phase 8 (error handling):  T → U
```

**Dependencies:**
- V depends on I (`_build_future_cost` returns `future_annual`)
- C+V are implemented together (same code block)
- I depends on E (structured percentage fields)
- F depends on A (typed schema for `state.sa.current_annual_spend`)
- G depends on A (same reason)
- H depends on F (consumes `consistency_warnings`)

Each fix is independently testable.  Run existing tests after each change.
