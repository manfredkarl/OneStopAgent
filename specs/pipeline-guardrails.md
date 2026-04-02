# Pipeline Guardrails Spec — State Degradation Fixes

**Status**: Draft
**Priority**: P0 — These bugs produce absurd outputs that destroy credibility
**Date**: 2026-04-02

## Problem Statement

When data flows through the agent pipeline (BV → Architect → Cost → ROI),
information degrades at each handoff. The user provides grounded inputs
($3.5M spend, 2.5M platform users, $42/hr staff), but by the time the
ROI dashboard renders, the baseline has inflated to $439M, ghost value
drivers appear, and caps are bypassed. Five root causes identified.

---

## Issue 1: Baseline Inflation (User → Employee Confusion)

**Severity**: CRITICAL
**File**: `roi_agent.py` lines 108–115, `state.py` lines 27–33

**Root Cause**: `SharedAssumptions.total_users` conflates platform users
(2.5M shoppers) with affected employees. The ROI agent's
`_resolve_current_baseline()` uses `state.sa.total_users` as headcount
for `monthly_labor = users × rate × hours × 4.33`, producing:

```
2,500,000 × $42 × 20hrs × 4.33 = $9.1B/month
```

**Contributing Factor**: The orchestrator prompt asks "How many people
will use or benefit from the solution" — ambiguous between customers
and staff.

### Fix

**A. Add `affected_employees` field to SharedAssumptions** (`state.py`):

```python
affected_employees: float | None = None
```

Add to `_FIELD_MATCHERS`:
```python
("affected_employees", [
    ["employee"],
    ["headcount"],
    ["fte"],
    ["staff", "count"],
    ["team", "size"],
]),
```

Remove `["engineer"]`, `["employee"]`, `["headcount"]` from `total_users`
matchers (those are employee concepts, not user concepts).

**B. Update orchestrator prompt** (`maf_orchestrator.py` line 331):

Change question 1 from:
```
"1. USERS: How many people will use or benefit from the solution"
```
To:
```
"1. AFFECTED STAFF: How many employees/staff are directly affected by this solution (NOT end-user/customer count)"
```

Add question 5:
```
"5. PLATFORM USERS (if different from staff): Total end-users or customers who will use the platform"
```

**C. Update ROI baseline resolver** (`roi_agent.py` line 108):

```python
# Use affected_employees for labor; fall back to total_users only if small (<10K)
sa_employees = state.sa.affected_employees
if sa_employees is None and state.sa.total_users and state.sa.total_users < 10000:
    sa_employees = state.sa.total_users  # likely a staff count, not platform users

if sa_employees and sa_labor_rate:
    users = int(sa_employees)
    ...
```

**D. Add sanity guard** — if computed baseline exceeds `sa_annual_spend × 5`,
cap at `sa_annual_spend` and log a warning:

```python
if sa_annual_spend and monthly_labor * 12 > sa_annual_spend * 5:
    logger.warning("Labor pool ($%s/yr) exceeds 5× stated spend ($%s). Using spend as ceiling.",
                   monthly_labor * 12, sa_annual_spend)
    return (sa_annual_spend / 12,
            [{"label": "Current operations (user-provided)", "amount": round(sa_annual_spend / 12)}],
            False)
```

### Acceptance Criteria
- GIVEN total_users=2.5M AND current_annual_spend=$3.5M WHEN baseline resolves
  THEN monthly baseline ≤ $3.5M/12 = $291K (NOT $9.1B)
- GIVEN affected_employees=30 AND hourly_rate=$100 WHEN baseline resolves
  THEN labor = 30 × $100 × 20 × 4.33 = $259,800/mo (sensible)
- GIVEN total_users=500 (no affected_employees) WHEN baseline resolves
  THEN total_users used as fallback (<10K threshold)

---

## Issue 2: Ghost Risk Driver

**Severity**: HIGH
**File**: `roi_agent.py` lines 370–406

**Root Cause**: `_compute_risk_reduction()` auto-generates risk value
from `current_annual × risk_factor` (2–7% based on architecture
components). It NEVER checks whether the BV agent already analyzed
and explicitly excluded risk drivers.

With the inflated $439M baseline: `$439M × 0.05 = $22M` in phantom
risk reduction.

### Fix

**A. Add `excluded` flag to BV driver schema**:

When the BV agent determines a driver cannot be dollarized, mark it:
```python
d.setdefault("excluded", False)
d.setdefault("excluded_reason", "")
```

In the BV prompt, add instruction:
```
If a driver cannot be dollarized due to missing data, include it but set
"excluded": true and "excluded_reason": "reason".
```

**B. Pass BV drivers to `_compute_risk_reduction()`**:

```python
risk_reduction, risk_note = self._compute_risk_reduction(
    current_annual, hard_savings, revenue_uplift,
    components=state.architecture.get("components"),
    bv_drivers=drivers)
```

**C. Check for BV risk assessment before auto-generating**:

```python
if bv_drivers:
    risk_drivers = [d for d in bv_drivers if d.get("category") == "risk_reduction"]
    if risk_drivers:
        # BV already assessed risk — use their judgment
        excluded = all(d.get("excluded", False) for d in risk_drivers)
        if excluded:
            return (0, "Risk reduction excluded by value analysis (insufficient baseline data).")
        # If BV quantified it, it's already in the waterfall — don't double-count
        return (0, "Risk reduction quantified via business value drivers.")
```

### Acceptance Criteria
- GIVEN BV produces a risk driver with `excluded=true` WHEN ROI runs
  THEN risk_reduction = $0 AND note explains why
- GIVEN BV produces no risk drivers WHEN ROI runs THEN auto-generation
  still works (backward compat)
- GIVEN BV produces a quantified risk driver (excluded=false) WHEN ROI
  runs THEN risk_reduction = $0 (already in waterfall, no double-count)

---

## Issue 3: Value Cap Bypass via Uncapped Components

**Severity**: HIGH
**File**: `roi_agent.py` lines 580–584

**Root Cause**: `total_annual_value = hard_savings + revenue_uplift +
risk_reduction`. Hard savings are capped by the cost model, but revenue
uplift and risk reduction are NOT capped. When risk is $22M (ghost) and
revenue uplift is uncapped, the total blows past the BV's capped range.

### Fix

**A. Cap `total_annual_value` at the BV-capped range**:

After computing total_annual_value, clamp it:
```python
total_annual_value = hard_savings + revenue_uplift + risk_reduction

# total_annual_value must not exceed the BV-validated range
bv_cap = float(impact_range.get("high", 0)) if impact_range else None
if bv_cap and bv_cap > 0 and total_annual_value > bv_cap:
    scale = bv_cap / total_annual_value
    hard_savings = round(hard_savings * scale)
    revenue_uplift = round(revenue_uplift * scale)
    risk_reduction = round(risk_reduction * scale)
    total_annual_value = hard_savings + revenue_uplift + risk_reduction
    logger.warning("Total value capped to BV range high ($%s)", bv_cap)
```

### Acceptance Criteria
- GIVEN BV caps range at $2.2M high WHEN waterfall components sum to $8M
  THEN total_annual_value ≤ $2.2M
- GIVEN BV range is null WHEN waterfall computes THEN no capping applied

---

## Issue 4: Communication Services Undercosting

**Severity**: MEDIUM
**File**: `services/pricing.py` lines 81–86, `cost_agent.py` lines 501–554

**Root Cause**: Communication Services has a flat `$500/month` estimate
with unit `"1/Month"`. The `_calculate_monthly()` function sees "month"
in the unit and returns $500 unchanged. The user's 50,000 hours of
chat/voice usage is completely ignored.

### Fix

**A. Change ESTIMATED_PRICES to per-minute pricing**:

```python
"Azure Communication Services": {
    "price": 0.004,  # blended per-minute (voice $0.05, chat $0.001, weighted)
    "source": "estimated",
    "note": "Blended per-minute rate for mixed voice/chat. Voice ~$0.05/min, chat ~$0.001/msg.",
    "unit": "1/Minute",
},
```

**B. Add minute-based handling in `_calculate_monthly()`**:

```python
elif "minute" in unit_lower:
    # Look for voice/chat minutes in usage assumptions
    monthly_minutes = 0
    if usage_dict:
        for key in ("monthly_voice_chat_minutes", "monthly_chat_voice_hours",
                     "voice_chat_minutes", "monthly_minutes"):
            if usage_dict.get(key):
                val = float(usage_dict[key])
                # Convert hours to minutes if key suggests hours
                if "hour" in key:
                    val = val * 60
                monthly_minutes = val
                break
    if monthly_minutes == 0:
        monthly_minutes = 100_000  # default: 100K minutes/mo
    return unit_price * monthly_minutes
```

### Acceptance Criteria
- GIVEN 50,000 hours of voice/chat WHEN cost calculated THEN
  monthly ≈ 50,000 × 60 × $0.004 = $12,000 (not $500)
- GIVEN no usage data WHEN cost calculated THEN uses 100K min default

---

## Issue 5: Baseline Must Be the Ceiling

**Severity**: HIGH
**File**: `roi_agent.py` lines 102–120

**Root Cause**: When both `sa_annual_spend` and labor data exist, the
code computes `monthly_tools + monthly_labor` which can far exceed the
user's stated spend. The user said their total relevant spend is $3.5M,
but the labor calculation can produce $43B.

### Fix

**A. User-provided spend is the authoritative ceiling**:

The baseline should NEVER exceed `current_annual_spend` (the user's
stated number). Labor breakdown adds detail but doesn't override.

```python
if sa_annual_spend:
    monthly_ceiling = sa_annual_spend / 12

    # Try to break down into labor + tools for future-cost modeling
    if sa_employees and sa_labor_rate:
        monthly_labor = round(sa_employees * sa_labor_rate * hours * 4.33)
        monthly_tools = max(0, monthly_ceiling - monthly_labor)
        if monthly_labor > monthly_ceiling:
            # Labor alone exceeds stated spend — trust the spend number
            return (monthly_ceiling,
                    [{"label": "Current operations (user-provided)", "amount": round(monthly_ceiling)}],
                    False)
        return (monthly_ceiling,
                [{"label": "Staff labor", "amount": min(monthly_labor, round(monthly_ceiling * 0.7))},
                 {"label": "Tools & platform spend", "amount": round(monthly_ceiling - min(monthly_labor, round(monthly_ceiling * 0.7)))}],
                False)

    return (monthly_ceiling,
            [{"label": "Current operations (user-provided)", "amount": round(monthly_ceiling)}],
            False)
```

### Acceptance Criteria
- GIVEN current_annual_spend=$3.5M AND total_users=2.5M AND hourly_rate=$42
  WHEN baseline resolves THEN monthly = $291,667 (NOT $9.1B)
- GIVEN current_annual_spend=$3.5M AND affected_employees=50 AND rate=$100
  WHEN baseline resolves THEN monthly = $291,667 with labor/tools breakdown

---

## Implementation Order

```
1. Issue 1 + Issue 5 (baseline fixes — they share the same code path)
2. Issue 2 (risk ghost — independent)
3. Issue 3 (cap bypass — depends on risk fix)
4. Issue 4 (cost undercount — independent)
```

Issues 2 and 4 can be parallelized with Issues 1+5.

## Coverage Matrix

| Finding | Root Cause | Fix Location |
|---------|-----------|--------------|
| $439M baseline | total_users=2.5M as employees | roi_agent.py + state.py + orchestrator |
| $22M ghost risk | Auto-generated, BV exclusion ignored | roi_agent.py _compute_risk_reduction |
| $23.7M cap bypass | Uncapped revenue + risk inflate total | roi_agent.py total_annual_value |
| $500 for 50K hours | Flat monthly estimate, usage ignored | pricing.py + cost_agent.py |
| User/employee conflation | No affected_employees field | state.py SharedAssumptions |
