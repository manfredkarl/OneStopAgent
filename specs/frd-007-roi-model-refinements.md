# FRD-007: ROI Model Refinements

**Feature ID**: F-007
**Status**: Draft
**Priority**: P2
**Last Updated**: 2026-04-02

## Description

Three secondary aspects of the ROI model use static values where
context-aware logic would improve accuracy:

1. **Risk reduction** — always 3% of current spend, regardless of whether the
   architecture includes security, compliance, or HA components.
2. **Adoption ramp** — fixed 50%/85%/100% Year 1/2/3 schedule for all
   scenarios, ignoring architecture complexity.
3. **productivityGains** — a permanently-zero field in the `valueBridge`
   schema that adds noise without value.

## User Stories

### US-007-001: Context-Aware Risk Reduction

**As a** ROI model
**I want** risk reduction to scale based on architecture components
(security, compliance, HA)
**So that** an architecture with Azure DDoS Protection + Sentinel gets a
higher risk factor than a static website.

**Acceptance Criteria:**
- GIVEN architecture includes "Azure Sentinel" (security) WHEN risk is
  computed THEN risk_factor = 4% (base 2% + 2%)
- GIVEN architecture includes security + compliance components WHEN risk is
  computed THEN risk_factor = 6% (2% + 2% + 2%)
- GIVEN risk_factor = 7% (max) and risk_raw < 5% of preliminary value WHEN
  risk is evaluated THEN risk_reduction = 0 (excluded as immaterial), with
  explanation
- GIVEN no security/compliance/HA components WHEN risk is computed THEN
  risk_factor = 2% (base only)

### US-007-002: Complexity-Based Adoption Ramp

**As a** 3-year projection model
**I want** the adoption ramp to vary by architecture complexity
**So that** a simple 3-component architecture gets a faster ramp than a
15-component enterprise system.

**Acceptance Criteria:**
- GIVEN ≤3 components WHEN adoption ramp is selected THEN [70%, 95%, 100%]
- GIVEN 4–8 components WHEN adoption ramp is selected THEN [50%, 85%, 100%]
- GIVEN ≥9 components WHEN adoption ramp is selected THEN [30%, 65%, 90%]

### US-007-003: Clean Value Bridge Schema

**As a** frontend consuming the business case
**I want** the `valueBridge` to not include permanently-zero fields
**So that** the schema is honest about what data is actually computed.

**Acceptance Criteria:**
- GIVEN the value bridge is built WHEN `productivityGains` would be 0 THEN
  the field is not included in the output
- GIVEN the frontend `BusinessCase` interface WHEN updated THEN the
  `productivityGains` property is removed

## Functional Requirements

### FR-007-001: Context-Aware Risk Reduction (Fix O)

Rewrite `_compute_risk_reduction()` as a static method:

- Input: `current_annual`, `hard_savings`, `revenue_uplift`, `components` list
- Processing:
  - Base risk_factor = 2%
  - +2% if any component mentions "security"
  - +2% if any component mentions "compliance"
  - +1% if any component mentions "availability" or "disaster"
  - Cap at 7%
  - `risk_raw = current_annual × risk_factor`
  - If `risk_raw < 5% of (hard_savings + revenue_uplift)`, exclude as immaterial
- Output: `(risk_amount: float, explanation: str)`
- Error handling: if `components` is None/empty, use base 2% only

### FR-007-002: Complexity-Based Adoption Ramp (Fix P)

Define `ADOPTION_RAMPS` dict and `_select_adoption_ramp(state)` method:

- Input: `state.architecture["components"]`
- Processing: count components, select bracket
- Output: 3-element list of adoption fractions
- Error handling: if no architecture data, use "medium" ramp

### FR-007-003: Remove productivityGains (Fix Q)

Delete `productivityGains` from `valueBridge` dict in `_build_business_case()`.
Remove corresponding field from the frontend `BusinessCase` TypeScript
interface in `src/frontend/src/components/ROIDashboard.tsx` (line 44).

- Input: N/A (code deletion)
- Processing: remove key from dict literal, remove property from interface
- Output: `valueBridge` without `productivityGains`
- Error handling: N/A

## Non-Functional Requirements

### NFR-007-001: Component Keyword Matching

Component matching uses case-insensitive substring matching on the component
string representation. This is a heuristic — false positives (e.g., a
component named "security-group" that's a network construct) are acceptable
as they only slightly inflate risk reduction.

## Dependencies

| Dependency | Type | Direction | Description |
|------------|------|-----------|-------------|
| `state.architecture` | Internal | Upstream | Component list from Architect agent |
| `ROIDashboard.tsx` | Frontend | Downstream | `BusinessCase` interface change |

---

## Current Implementation (Brownfield Extension)

### Files Involved

| File Path | Role | Lines |
|-----------|------|-------|
| `src/python-api/agents/roi_agent.py` | `_compute_risk_reduction()`, `ADOPTION_RAMP`, `_build_business_case()` | ~310–340, ~30, ~500–600 |
| `src/frontend/src/components/ROIDashboard.tsx` | `BusinessCase` interface | ~10–40 |

### Architecture Pattern

Constants and static methods within the ROI agent. Risk reduction is computed
from a fixed percentage. Adoption ramp is a module-level constant list.

### Known Limitations

- `_compute_risk_reduction`: always `0.03 × current_annual` — no context
- `ADOPTION_RAMP = [0.50, 0.85, 1.00]` — same for all architectures
- `productivityGains: 0` in every output — dead field
- No materiality test for risk reduction — even $500 risk on a $5M project
  appears in the waterfall

### Test Coverage

| Test Type | Files | Assertions | Coverage |
|-----------|-------|------------|----------|
| Unit | — | — | 0% |
| Integration | — | — | 0% |
| E2E | — | — | 0% |

**Untested paths**: Risk calculation, adoption ramp selection, business case building.
