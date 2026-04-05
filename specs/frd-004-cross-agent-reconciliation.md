# FRD-004: Cross-Agent Reconciliation

| Fix | Status |
|-----|--------|
| FR-004-001: Cost agent baseline comparison | 🚧 Partial |
| FR-004-002: ROI plausibility engine | ✅ Implemented |
| FR-004-003: Savings cap tracking | 🚧 Partial |
| FR-004-004: Dashboard plausibility output | 🚧 Partial |

**Feature ID**: F-004
**Status**: Draft
**Priority**: P1
**Last Updated**: 2026-04-02

## Description

The Cost, Business Value, and ROI agents each produce financial outputs
independently. No agent validates its results against the others'. The Cost
agent never checks whether its Azure estimate is plausible relative to the
user's current spend. The ROI agent blindly divides value by cost without
cross-checking the components. When hard savings are silently capped to not
exceed the baseline, the user has no visibility into the adjustment.

This FRD introduces plausibility checks at two points: after cost estimation
(Cost agent output vs. baseline) and before dashboard rendering (ROI agent
reconciliation of all three outputs).

## User Stories

### US-004-001: Cost Plausibility Flag

**As a** user reviewing cost estimates
**I want** the system to flag when the Azure estimate is implausibly high or
low relative to my current spend
**So that** I can verify whether the sizing is correct.

**Acceptance Criteria:**
- GIVEN Azure annual estimate = $5M and current spend = $2M WHEN cost
  plausibility runs THEN an assumption note says: "Azure estimate ($5M/yr)
  exceeds current spend ($2M/yr) by 2.5×. Verify sizing."
- GIVEN Azure annual estimate = $50K and current spend = $2M WHEN cost
  plausibility runs THEN a note says: "Azure estimate is 2.5% of current
  spend. Confirm scope replacement."
- GIVEN no `current_annual_spend` available WHEN cost plausibility runs THEN
  no check is performed (skip silently)

### US-004-002: ROI Reconciliation Warnings

**As a** decision-maker viewing the ROI dashboard
**I want** to see explicit warnings when the numbers don't add up
**So that** I know where to apply skepticism.

**Acceptance Criteria:**
- GIVEN value-to-cost ratio > 50× WHEN reconciliation runs THEN confidence =
  "low" and a warning is emitted
- GIVEN hard savings were capped by 40% WHEN reconciliation runs THEN a
  warning explains the cap: "Cost savings reduced by 40% to not exceed
  the current baseline."
- GIVEN revenue uplift > 50% of stated annual revenue WHEN reconciliation
  runs THEN a warning flags the disparity
- GIVEN driver sum diverges > 15% from impact midpoint WHEN reconciliation
  runs THEN a warning flags the accounting gap
- GIVEN cost-reduction-only scenario where Azure > current cost WHEN
  reconciliation runs THEN a warning flags the inconsistency

### US-004-003: Savings Cap Transparency

**As a** user viewing the waterfall chart
**I want** to know when savings values were reduced from driver estimates
**So that** I understand why driver savings don't match the headline number.

**Acceptance Criteria:**
- GIVEN `_split_waterfall` capped raw hard savings WHEN the dashboard is
  built THEN `dashboard.savingsCapped = true`
- GIVEN the dashboard has savings capped WHEN the plausibility warnings are
  rendered THEN the warning includes the cap percentage

## Functional Requirements

### FR-004-001: Cost Agent Baseline Comparison (Fix G)

At the end of `CostAgent.run()`, after computing `total_annual`:

- Input: `total_annual`, `state.sa.current_annual_spend`
- Processing: compute ratio. If > 2.0 or < 0.03, append a note to assumptions.
- Output: assumption string appended to `state.costs.assumptions`
- Error handling: skip if `current_annual_spend` is None or ≤ 0

### FR-004-002: ROI Plausibility Engine (Fix H)

Implement `_validate_and_reconcile()` in `roi_agent.py` with keyword-only
arguments. Checks:

1. Value-to-cost ratio (>50× → "low", >20× → warning)
2. Hard savings cap transparency
3. Revenue uplift vs. stated revenue (>50% → warning)
4. Accounting identity (driver sum vs. midpoint, >15% → warning)
5. Cost-reduction-only: Azure > current cost → warning
6. Fallback data detection (from FRD-008)

- Input: `val_mid`, `annual_cost`, `current_annual`, `azure_annual`,
  `hard_savings`, `revenue_uplift`, `is_estimated`, `bv_confidence`,
  `bv_warnings`, `savings_were_capped`, `savings_cap_pct`, `monthly_revenue`
  (sourced from `state.sa.monthly_revenue` — see FRD-001 FR-001-001)
- Processing: run all checks, collect warnings, adjust confidence
- Output: `(adjusted_confidence: str, warnings: list[str])`
- Error handling: each check is independent — one failure doesn't block others

### FR-004-003: Savings Cap Tracking (Fix H)

Modify `_split_waterfall` to return 4-tuple instead of 2-tuple:
`(cost_items, uplift_items, savings_capped: bool, savings_cap_pct: float)`

- Input: raw driver waterfall items, `current_annual`
- Processing: if `raw_hard > current_annual`, scale down and record cap %
- Output: augmented 4-tuple
- Error handling: if `current_annual ≤ 0`, no capping

### FR-004-004: Dashboard Plausibility Output

Write reconciliation results to the dashboard:
- `dashboard["confidenceLevel"]` = adjusted confidence
- `dashboard["plausibilityWarnings"]` = warning list
- `dashboard["savingsCapped"]` = boolean (if applicable)

## Non-Functional Requirements

### NFR-004-001: Warning Independence

Each plausibility check runs independently. A failure in one check must not
prevent other checks from running.

### NFR-004-002: No Silent Overrides

When values are adjusted (confidence downgraded, savings capped), the
adjustment must be visible to the user via warnings — never silent.

## Dependencies

| Dependency | Type | Direction | Description |
|------------|------|-----------|-------------|
| FRD-001 | Feature | Upstream | `state.sa.current_annual_spend` |
| FRD-003 | Feature | Upstream | `consistency_warnings` from BV validation |
| FRD-008 | Feature | Upstream | `_used_fallback` flags on state dicts |
| `ROIDashboard.tsx` | Frontend | Downstream | Displays warnings |

---

## Current Implementation (Brownfield Extension)

### Files Involved

| File Path | Role | Lines |
|-----------|------|-------|
| `src/python-api/agents/cost_agent.py` | `run()` — end of function | ~380–420 |
| `src/python-api/agents/roi_agent.py` | `_split_waterfall()`, `_build_dashboard()` | ~280–310, ~400–500 |
| `src/frontend/src/components/ROIDashboard.tsx` | Dashboard display | full file |

### Architecture Pattern

Pipeline: Cost → BV → ROI. Each agent writes to `state.*` dicts. ROI agent
reads from all three and produces the dashboard. No cross-validation exists.

### Known Limitations

- Cost agent never reads `current_annual_spend` — its Azure estimate is
  disconnected from the user's baseline
- ROI agent divides value by cost without any reasonableness checks
- `_split_waterfall` silently caps hard savings when they exceed the baseline
  but never surfaces this to the user
- No fallback detection — if upstream agents used error fallbacks, ROI agent
  treats the data as normal
- Confidence level is passed through from BV without ROI-level adjustment

### Test Coverage

| Test Type | Files | Assertions | Coverage |
|-----------|-------|------------|----------|
| Unit | — | — | 0% |
| Integration | — | — | 0% |
| E2E | — | — | 0% |

**Untested paths**: No plausibility or reconciliation logic exists to test.
