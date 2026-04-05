# FRD-003: Business Value Verification

| Fix | Status |
|-----|--------|
| FR-003-001: Structured driver schema (impact_pct fields) | ✅ Implemented |
| FR-003-002: Replace regex-based coverage extraction | ✅ Implemented |
| FR-003-003: Validate and verify BV output | ✅ Implemented |
| FR-003-004: ROI agent driver sum check | ✅ Implemented |
| FR-003-005: Flexible driver count | 🚧 Partial |
| FR-003-006: Confidence downgrade | ✅ Implemented |

**Feature ID**: F-003
**Status**: Draft
**Priority**: P1
**Last Updated**: 2026-04-02

## Description

The Business Value agent produces `annual_impact_range` (low/high dollar
values) and a list of value `drivers` via LLM. These outputs feed directly
into the ROI agent's dashboard. Currently, the LLM output is accepted without
validation: dollar ranges are unbounded, driver impact percentages are embedded
in free-text metric strings parsed by fragile regex, the driver count is
forced to exactly 3, and confidence level stays "moderate" even when web
search for industry benchmarks returns nothing.

This FRD introduces structured driver output with numeric impact fields,
arithmetic verification of driver-to-range consistency, flexible driver count,
and honest confidence downgrading.

## User Stories

### US-003-001: Structured Driver Impact Percentages

**As a** ROI agent consuming BV driver data
**I want** impact percentages as numeric fields (not free text)
**So that** I can compute per-driver values without regex parsing.

**Acceptance Criteria:**
- GIVEN a BV driver with metric "20–30% time savings" WHEN the LLM produces
  output THEN the driver includes `impact_pct_low: 20` and `impact_pct_high: 30`
- GIVEN a driver with numeric fields WHEN the ROI agent reads it THEN it uses
  `(impact_pct_low + impact_pct_high) / 2 / 100` as the fractional impact
- GIVEN a driver where numeric fields are missing WHEN the ROI agent reads it
  THEN `_extract_coverage_from_drivers` returns `None` (no silent 25% fallback)

### US-003-002: Validated Dollar Range

**As a** decision-maker
**I want** the annual impact range to be sanity-checked against the Azure cost
and current baseline
**So that** hallucinated multi-billion-dollar claims are caught before
reaching the dashboard.

**Acceptance Criteria:**
- GIVEN impact high > 200× Azure annual cost WHEN validation runs THEN the
  range is capped to 200× and a warning is emitted
- GIVEN impact high > 3× current annual spend WHEN validation runs THEN a
  warning flags the disparity (but does not cap)
- GIVEN impact range where low > high WHEN validation runs THEN low and high
  are swapped

### US-003-003: Driver Arithmetic Cross-Check

**As a** ROI agent
**I want** cost-reduction drivers to be verified against the current baseline
**So that** drivers don't claim more savings than the total current spend.

**Acceptance Criteria:**
- GIVEN two cost-reduction drivers implying $3M/yr combined savings against
  $2M/yr current spend WHEN verification runs THEN a warning is emitted:
  "Cost-reduction drivers imply $3M but current spend is $2M. Over-counting."
- GIVEN cost-reduction drivers sum ≤ current spend WHEN verification runs
  THEN no warning

### US-003-004: Flexible Driver Count

**As a** BV agent processing a simple use case
**I want** to produce 2 drivers when only 2 are defensible
**So that** I'm not forced to fabricate a third low-quality driver.

**Acceptance Criteria:**
- GIVEN a simple architecture (≤3 components) WHEN the LLM generates drivers
  THEN 2 drivers is acceptable
- GIVEN a complex architecture WHEN the LLM generates drivers THEN up to 4
  drivers are allowed
- GIVEN 6 drivers returned WHEN post-processing runs THEN only the first 5
  are kept (safety cap)

### US-003-005: Honest Confidence Level

**As a** user viewing the confidence indicator
**I want** confidence to degrade when no industry benchmarks were found
**So that** I know the value estimate is based solely on the LLM's judgment.

**Acceptance Criteria:**
- GIVEN web search returned zero results WHEN confidence is set THEN "high"
  is downgraded to "moderate"
- GIVEN web search returned zero results WHEN the BV result is stored THEN a
  `methodology_note` explains: "No external industry benchmarks available."
- GIVEN validation warnings were emitted WHEN confidence is set THEN
  confidence = "low"

## Functional Requirements

### FR-003-001: Structured Driver Schema (Fix E)

Add `impact_pct_low` and `impact_pct_high` as required numeric fields in the
BV agent's LLM prompt schema. Add `category` field: `"cost_reduction"`,
`"revenue_uplift"`, or `"risk_reduction"`.

- Input: LLM prompt instructions
- Processing: update JSON schema in prompt to require numeric fields
- Output: driver dicts with `impact_pct_low`, `impact_pct_high`, `category`
- Error handling: if LLM omits fields, they default to `None`; downstream
  treats `None` as "unknown impact"

### FR-003-002: Replace Regex-Based Coverage Extraction (Fix E)

Replace `_extract_coverage_from_drivers()` in `roi_agent.py` with direct
numeric field reads.

- Input: list of driver dicts
- Processing: for first driver with both numeric fields, return
  `(low + high) / 2 / 100`
- Output: `float | None`
- Error handling: if no driver has both fields, return `None`

### FR-003-003: Validate and Verify (Fix F)

Implement `_validate_and_verify(result, state)` in `business_value_agent.py`:

- **Range validation**: swap low/high if inverted, reject ≤0, cap at 200×
  Azure annual, flag >3× current spend
- **Driver arithmetic**: sum cost-reduction driver midpoints × current spend;
  flag if sum > current spend
- **Output**: `(corrected_range | None, warnings_list)`
- Error handling: non-numeric values → return `(None, [error message])`

### FR-003-004: ROI Agent Driver Sum Check (Fix F extension)

After `_compute_per_driver_amounts()` in ROI agent, verify sum ≈ midpoint.
Log warning if divergence > 10%.

### FR-003-005: Flexible Driver Count (Fix R)

Change LLM prompt from "EXACTLY 3" to "2–4". Remove `[:3]` slice. Keep
`[:5]` as safety cap to handle LLM overshoot (prompt requests 2–4, but
code tolerates up to 5 before truncating).

### FR-003-006: Confidence Downgrade (Fix S)

After `search_industry_benchmarks()`:
- Store `benchmark_available = bool(search_results)`
- If not available and confidence = "high", downgrade to "moderate"
- Add `methodology_note` when no benchmarks found
- If validation warnings exist, force confidence = "low"

## Non-Functional Requirements

### NFR-003-001: LLM Prompt Backward Compatibility

The new schema fields are additive. If an older LLM response lacks
`impact_pct_low`/`impact_pct_high`, the system must degrade gracefully
(return `None` for coverage, not crash).

## Dependencies

| Dependency | Type | Direction | Description |
|------------|------|-----------|-------------|
| FRD-001 | Feature | Upstream | `state.sa.current_annual_spend` for verification |
| FRD-005 | Feature | Downstream | Consumes structured `impact_pct_*` fields |
| FRD-004 | Feature | Downstream | Consumes `consistency_warnings` |
| `roi_agent.py` | Internal | Downstream | Reads drivers and impact range |

---

## Current Implementation (Brownfield Extension)

### Files Involved

| File Path | Role | Lines |
|-----------|------|-------|
| `src/python-api/agents/business_value_agent.py` | BV agent — LLM prompt, questions, parsing | full file (~400 lines) |
| `src/python-api/agents/roi_agent.py` | `_extract_coverage_from_drivers()`, `_compute_per_driver_amounts()` | ~200–260 |
| `src/python-api/services/web_search.py` | `search_industry_benchmarks()` | full file |

### Architecture Pattern

Two-phase agent: Phase 1 generates assumption questions via LLM, Phase 2
sends user answers + architecture + benchmark search results to LLM for
driver generation. Output stored in `state.business_value` as a dict.

### Known Limitations

- `annual_impact_range` accepted as-is from LLM — no bounds checking
- `_extract_coverage_from_drivers()` uses fragile regex on free-text `metric`
  field; silent 25% fallback when pattern doesn't match
- Exactly 3 drivers forced (`[:3]` slice) regardless of complexity
- Confidence stays "moderate" even when `search_industry_benchmarks` returns
  empty results (network errors, no matches)
- No verification that driver percentages arithmetically produce the claimed
  dollar range

### Test Coverage

| Test Type | Files | Assertions | Coverage |
|-----------|-------|------------|----------|
| Unit | — | — | 0% |
| Integration | — | — | 0% |
| E2E | — | — | 0% |

**Untested paths**: LLM response validation, driver consistency, confidence logic.
