# FRD-005: Future-State Cost Model

**Feature ID**: F-005
**Status**: Draft
**Priority**: P1
**Last Updated**: 2026-04-02

## Description

The ROI agent's `_build_future_cost()` method computes the post-migration
operating cost by applying reduction percentages to the current cost breakdown.
Currently, these reductions are hardcoded constants (10% overhead, 50% error
reduction, 60/40 labor split) with no relationship to the BV agent's driver
analysis. This means the future-state cost model and the value model are
disconnected — BV might claim 30% labor savings while the future-state model
applies a fixed 10%.

Additionally, reduction percentages from multiple drivers are naively summed:
30% labor savings + 20% tooling savings = 50% applied across all line items.
This is incorrect when labor is 60% of costs and tooling is 15% — the
reductions should be applied independently to their respective cost pools.

This FRD replaces hardcoded constants with per-pool reductions derived from
BV driver analysis, with multiplicative accumulation within pools and
independence across pools.

## User Stories

### US-005-001: Driver-Informed Future Costs

**As a** ROI agent computing future operating cost
**I want** reduction percentages sourced from BV driver analysis (not
hardcoded)
**So that** the future-state cost model is consistent with the value model.

**Acceptance Criteria:**
- GIVEN a BV driver "30% labor productivity improvement" WHEN future cost is
  built THEN labor line items are reduced by 30%, NOT by a fixed 10%
- GIVEN no cost-reduction drivers WHEN future cost is built THEN no
  reductions are applied to current breakdown items
- GIVEN a driver with `category != "cost_reduction"` (e.g., revenue uplift)
  WHEN future cost is built THEN it does not affect the cost breakdown

### US-005-002: Per-Pool Reduction Application

**As a** ROI model computing reductions
**I want** driver percentages applied only to their matching cost pool
**So that** 30% labor + 20% tooling doesn't become 50% everywhere.

**Acceptance Criteria:**
- GIVEN a "30% labor savings" driver and a "20% tooling savings" driver AND
  current breakdown = [Labor: $100K, Tooling: $30K, Other: $20K]
  WHEN future cost is built
  THEN Labor = $70K (30% off), Tooling = $24K (20% off), Other = $20K (unchanged)
- GIVEN two labor drivers at 30% each WHEN accumulated THEN labor reduction =
  1 - (0.7 × 0.7) = 51%, NOT 60%
- GIVEN a driver with no pool match (general) WHEN applied THEN it reduces
  all non-Azure items, but only if no specific pool already matched that item

### US-005-003: Per-Item Reduction Cap

**As a** financial model
**I want** no line item reduced by more than 80%
**So that** the model never claims near-zero operating costs.

**Acceptance Criteria:**
- GIVEN three labor drivers at 40% each WHEN accumulated THEN multiplicative
  result = 1 - (0.6³) = 78.4%, which is under the 80% cap
- GIVEN four labor drivers at 40% each WHEN accumulated THEN multiplicative
  result = 87%, capped to 80%

## Functional Requirements

### FR-005-001: Pool Classification

Implement `POOL_KEYWORDS` dict and `_classify_driver_pool(driver)` method:

- Pools: `"labor"` (staff, fte, headcount, personnel, operations),
  `"tooling"` (tool, license, software, saas), `"error"` (error, rework,
  defect, incident, downtime)
- Input: driver dict (reads `name` and `metric` fields)
- Processing: lowercase concatenation of name + metric, check for keyword matches
- Output: pool name (`str`) or `None` for general/blended
- Error handling: if driver has no name or metric, return `None`

### FR-005-002: Pool Matching

Implement `_matches_pool(label, pool)`:

- Input: breakdown item label (str), pool (str | None)
- Processing: if pool is None, matches all items. Otherwise, checks if any
  pool keyword appears in the label.
- Output: boolean
- Error handling: N/A

### FR-005-003: Rewritten _build_future_cost

Replace the existing `_build_future_cost` with:

1. Start with `[{"label": "Azure platform", "amount": azure_monthly}]`
2. For each cost-reduction BV driver: compute `mid_pct = (low + high) / 2 / 100`,
   classify pool, accumulate multiplicatively:
   `pool_reductions[pool] = 1 - (1 - existing) * (1 - mid_pct)`
3. Cap each pool at 80%
4. For each current breakdown item: find best matching pool reduction.
   Specific pool wins over general. Apply reduction. Append to breakdown.
5. Return `(future_total, ai_breakdown)` where `future_total` = sum of all items

- Input: `azure_monthly`, `current_breakdown`, `bv_drivers`, `assumptions_dict`
- Processing: see above
- Output: `(future_total: int, ai_breakdown: list[dict])`
- Error handling: if `bv_drivers` is empty, all items carry forward at 100%
  (no reduction) plus Azure platform

### FR-005-004: Future Total as ROI Input

`_build_future_cost()` returns **monthly** `future_total`. The ROI agent
annualizes it: `future_annual = future_total × 12`. This `future_annual`
feeds into FRD-002's ROI denominator and represents the true total future
operating cost: Azure + reduced labor + carried overhead.

The annualization happens in `roi_agent.py` at the call site, not inside
`_build_future_cost()`, because the method operates in monthly terms
consistent with the existing cost model.

## Non-Functional Requirements

### NFR-005-001: Multiplicative Accumulation

Within a single pool, multiple drivers combine multiplicatively, not
additively. This prevents impossible reductions (e.g., two 60% drivers
= 120% additive vs. 84% multiplicative).

### NFR-005-002: Pool Independence

Cross-pool drivers must not interact. A labor driver and a tooling driver
are applied to their respective pools independently.

## Dependencies

| Dependency | Type | Direction | Description |
|------------|------|-----------|-------------|
| FRD-003 (Fix E) | Feature | Upstream | Structured `impact_pct_low/high` and `category` fields |
| FRD-002 (Fix V) | Feature | Downstream | `future_annual` used as ROI denominator |
| `roi_agent.py` | Internal | Both | Method lives in ROI agent, consumes BV drivers |

---

## Current Implementation (Brownfield Extension)

### Files Involved

| File Path | Role | Lines |
|-----------|------|-------|
| `src/python-api/agents/roi_agent.py` | `_build_future_cost()` | ~260–310 |

### Architecture Pattern

Pure-math method within the ROI agent. Takes current cost breakdown and
returns projected future breakdown. Currently uses hardcoded constants.

### Known Limitations

- 10% reduction for overhead items — no relationship to BV analysis
- 50% reduction for error/rework items — no relationship to BV analysis
- 60/40 split for labor items — arbitrary
- No concept of cost pools or per-driver targeting
- Multiple drivers' percentages have no mechanism to be applied independently
- No cap on per-item reduction

### Test Coverage

| Test Type | Files | Assertions | Coverage |
|-----------|-------|------------|----------|
| Unit | — | — | 0% |
| Integration | — | — | 0% |
| E2E | — | — | 0% |

**Untested paths**: Entire `_build_future_cost()` method.
