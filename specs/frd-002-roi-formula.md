# FRD-002: ROI Formula Accuracy

| Fix | Status |
|-----|--------|
| FR-002-001: Future operating cost as ROI denominator | ✅ Implemented |
| FR-002-002: Payback against Year 1 total cost | ✅ Implemented |
| FR-002-003: Sensitivity table update | ✅ Implemented |
| FR-002-004: State output additions | ✅ Implemented |
| FR-002-005: Dashboard output additions | ✅ Implemented |
| FR-002-006: Move investment computation | ✅ Implemented |
| FR-002-007: Variable baseline multiplier | ✅ Implemented |
| FR-002-008: Suppress estimated cost comparison | 🚧 Partial |

**Feature ID**: F-002
**Status**: Draft
**Priority**: P0
**Last Updated**: 2026-04-02

## Description

The ROI agent (`roi_agent.py`) computes headline ROI and payback period as
the core decision-making metrics shown in the dashboard. The current formula
has two critical defects:

1. **ROI denominator uses only Azure run-rate** — excludes implementation
   costs, change management costs, and ongoing labor/overhead that carries
   forward post-migration. This inflates ROI by 2–5×.
2. **Payback ignores implementation costs** — reports time to recoup only
   Azure run-rate, not the full Year 1 investment.
3. **Estimated baseline multiplier is a single constant** — `1.5` regardless
   of architecture complexity, producing fabricated savings comparisons.

This FRD introduces an honest ROI denominator that includes total future
operating cost (Azure + reduced labor + carried overhead), a payback
calculation that covers total Year 1 outlay, and a variable baseline
multiplier that suppresses cost comparisons when the baseline is estimated.

## User Stories

### US-002-001: Honest Year 1 ROI

**As a** decision-maker reviewing the business case
**I want** the Year 1 ROI to account for all costs — Azure, implementation,
change management, and carried labor/overhead
**So that** I'm not surprised by a lower actual return than projected.

**Acceptance Criteria:**
- GIVEN Azure annual = $120K, reduced labor/overhead = $80K (so total
  future operating cost = $200K), impl cost = $60K, change cost = $6K,
  and annual value = $500K
  WHEN ROI is calculated
  THEN Year 1 total cost = $200K + $60K + $6K = $266K (future opex + impl + change)
  AND Year 1 ROI = ((500K - 266K) / 266K) × 100 = 87.9%
- GIVEN the same scenario WHEN run-rate ROI is calculated THEN
  run-rate ROI = ((500K - 200K) / 200K) × 100 = 150%
  (denominator = total future operating cost = Azure + reduced labor + overhead, not just Azure)

### US-002-002: Payback Includes Full Year 1 Cost

**As a** finance reviewer
**I want** the payback period to reflect months until cumulative value
recoups the full Year 1 total cost
**So that** I can compare fairly against alternative investments.

**Acceptance Criteria:**
- GIVEN Year 1 total cost = $266K and annual value = $500K
  WHEN payback is calculated
  THEN payback = (266K / 500K) × 12 = 6.4 months
- GIVEN payback exceeds MAX_PAYBACK_MONTHS WHEN calculated THEN it is capped

### US-002-003: Sensitivity Table Consistency

**As a** user viewing the sensitivity analysis
**I want** the 50%/75%/100% adoption scenarios to use the same ROI formula
as the headline
**So that** the sensitivity table is not internally contradictory.

**Acceptance Criteria:**
- GIVEN 50% adoption WHEN sensitivity ROI is calculated THEN it uses
  `year1_total_cost` as Year 1 denominator and `future_annual` as run-rate
  denominator

### US-002-004: Estimated Baseline Suppresses Cost Comparison

**As a** user who did not provide actual current costs
**I want** the dashboard to clearly indicate the baseline is estimated and
suppress the current-vs-future savings comparison
**So that** I don't mistake fabricated savings for real data.

**Acceptance Criteria:**
- GIVEN no user-provided `current_annual_spend` WHEN the baseline is
  estimated THEN `dashboard.costEstimated = true` AND `monthlySavings = null`
  AND a warning message is displayed
- GIVEN architecture has ≤3 components WHEN baseline is estimated THEN
  multiplier = 1.2
- GIVEN architecture has 4–7 components WHEN baseline is estimated THEN
  multiplier = 1.5
- GIVEN architecture has ≥8 components WHEN baseline is estimated THEN
  multiplier = 2.0

## Functional Requirements

### FR-002-001: Future Operating Cost as ROI Denominator

Replace Azure-only denominator with `future_annual` from `_build_future_cost()`
(FRD-005). This value includes Azure platform + reduced labor + carried overhead.

- Input: `future_annual` (from FRD-005), `impl_cost`, `change_cost`, `val_mid`
- Processing:
  - `year1_total_cost = future_annual + impl_cost + change_cost`
  - `roi_year1 = ((val_mid - year1_total_cost) / year1_total_cost) × 100`
  - `roi_run_rate = ((val_mid - future_annual) / future_annual) × 100`
  - `roi_mid = roi_year1` (headline = conservative Year 1)
- Output: `roi_year1`, `roi_run_rate`, `roi_mid`
- Error handling: if `year1_total_cost ≤ 0`, ROI = 0

### FR-002-002: Payback Against Year 1 Total Cost

- Input: `year1_total_cost`, `val_mid`
- Processing: `payback_months = (year1_total_cost / val_mid) × 12`
  Clamped to `[MIN_PAYBACK_MONTHS, MAX_PAYBACK_MONTHS]`
- Output: `payback_months` (float, 1 decimal)
- Error handling: if `val_mid ≤ 0`, `payback_months = None`

### FR-002-003: Sensitivity Table Update

Update the sensitivity loop in `_build_business_case` to use `year1_total_cost`
as Year 1 denominator and `future_annual` as run-rate denominator.

- Input: `total_annual_value`, adoption percentages, `year1_total_cost`, `future_annual`
- Processing: for each adoption level, compute `adj_roi_y1`, `adj_roi_rr`, `adj_payback`
- Output: sensitivity table entries with `roiYear1`, `roiRunRate`, `paybackMonths`
- Error handling: division-by-zero guarded

### FR-002-004: State Output Additions

Add to state output: `roi_year1`, `roi_run_rate`, `year1_total_cost`,
`future_annual_opex`.

### FR-002-005: Dashboard Output Additions

Add `roiRunRate` and `futureAnnualOpex` to the dashboard payload.
Frontend tooltip: "Year 1 includes implementation costs. Steady state =
value vs. total future operating cost (Azure + labor + overhead)."

### FR-002-006: Move Investment Computation

Move the Investment block (currently ~line 393) to after baseline resolution
(~line 370). `_build_future_cost` (FRD-005) must run before this block.

### FR-002-007: Variable Baseline Multiplier

Replace constant `ESTIMATED_BASELINE_MULTIPLIER = 1.5` with
`_estimate_baseline_multiplier(state)` that returns 1.2 / 1.5 / 2.0 based
on component count (≤3 / ≤7 / ≥8).

- Input: `state.architecture["components"]`
- Processing: count components, select multiplier bracket
- Output: float multiplier
- Error handling: if no components, default to 1.5

### FR-002-008: Suppress Estimated Cost Comparison

When `_resolve_current_baseline` falls back to the estimated path, set
`dashboard.costComparisonAvailable = false`, null out savings fields, and
add a warning message.

## Non-Functional Requirements

### NFR-002-001: Computation Ordering

`_build_future_cost()` (FRD-005) must execute before the ROI formula block
so that `future_annual` is available. The implementation must enforce this
ordering.

## Dependencies

| Dependency | Type | Direction | Description |
|------------|------|-----------|-------------|
| FRD-001 | Feature | Upstream | `state.sa.timeline_months` for impl cost |
| FRD-005 | Feature | Upstream | `future_annual` from `_build_future_cost()` |
| FRD-003 (Fix E) | Feature | Upstream | Structured driver fields feed FRD-005 |
| `ROIDashboard.tsx` | Frontend | Downstream | Displays `roiRunRate`, `futureAnnualOpex` |

---

## Current Implementation (Brownfield Extension)

### Files Involved

| File Path | Role | Lines |
|-----------|------|-------|
| `src/python-api/agents/roi_agent.py` | ROI formula, payback, sensitivity, baseline | ~340–420 |
| `src/frontend/src/components/ROIDashboard.tsx` | Dashboard display | full file |

### Architecture Pattern

Pure-math agent (no LLM). Reads `state.costs` and `state.business_value` set
by upstream agents. Computes ROI, payback, waterfall, and writes to
`state.roi_dashboard`.

### Known Limitations

- ROI formula at ~line 348: `roi_mid = ((val_mid - annual_cost) / annual_cost) * 100`
  where `annual_cost` = Azure run-rate only
- Payback at ~line 350: `payback = (annual_cost / val_mid) * 12` — ignores
  implementation costs
- `ESTIMATED_BASELINE_MULTIPLIER = 1.5` is a single constant
- Investment block at ~line 393 runs after ROI calculation (ordering bug)
- Sensitivity table uses inconsistent denominators

### Test Coverage

| Test Type | Files | Assertions | Coverage |
|-----------|-------|------------|----------|
| Unit | — | — | 0% |
| Integration | — | — | 0% |
| E2E | — | — | 0% |

**Untested paths**: Entire ROI formula, payback calculation, sensitivity table.

## Test Plan

### TP-002-001: ROI Formula Unit Tests

| # | Inputs | Expected |
|---|--------|----------|
| 1 | `future_annual=200K, impl=60K, change=6K, val_mid=500K` | `year1_total=266K, roi_year1=87.9%, roi_run_rate=150%` |
| 2 | `future_annual=100K, impl=0, change=0, val_mid=100K` | `roi_year1=0%, roi_run_rate=0%` |
| 3 | `year1_total_cost=0` | `roi_year1=0` (division-by-zero guard) |
| 4 | `val_mid=0` | `payback_months=None` |
| 5 | Large ROI (>1000%) | Capped at display level (>10×) |

### TP-002-002: Payback Calculation

| # | Inputs | Expected |
|---|--------|----------|
| 1 | `year1_total=266K, val_mid=500K` | `payback = 6.4 months` |
| 2 | `year1_total=500K, val_mid=50K` | Capped at `MAX_PAYBACK_MONTHS` |
| 3 | `val_mid=0` | `payback_months = None` |

### TP-002-003: Variable Baseline Multiplier

| # | Components | Expected Multiplier |
|---|------------|---------------------|
| 1 | 0 components | 1.5 (default) |
| 2 | 2 components | 1.2 |
| 3 | 5 components | 1.5 |
| 4 | 10 components | 2.0 |

### TP-002-004: Estimated Baseline Suppression

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Baseline is estimated | `costComparisonAvailable=false, monthlySavings=null, warning present` |
| 2 | Baseline is user-provided | `costComparisonAvailable=true, monthlySavings=number` |

### TP-002-005: Sensitivity Table

| # | Scenario | Expected |
|---|----------|----------|
| 1 | 50% adoption | Uses `year1_total_cost` as Y1 denominator, `future_annual` as run-rate |
| 2 | All adoption levels | ROI decreases monotonically as adoption decreases |
