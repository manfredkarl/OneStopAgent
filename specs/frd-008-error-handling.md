# FRD-008: Error Handling & Transparency

| Fix | Status |
|-----|--------|
| FR-008-001: Flag fallback in Cost agent | ✅ Implemented |
| FR-008-002: Flag fallback in BV agent | ✅ Implemented |
| FR-008-003: ROI fallback detection | ✅ Implemented |
| FR-008-004: Typed exception handling | 🚧 Partial |

**Feature ID**: F-008
**Status**: Draft
**Priority**: P2
**Last Updated**: 2026-04-02

## Description

The Cost and Business Value agents use broad `except Exception` blocks that
catch all errors identically. When LLM output fails JSON parsing, the agents
silently fall back to placeholder data ("Standard" SKU selections, empty
driver lists) with "moderate" confidence. The ROI agent then consumes this
placeholder data as if it were real, producing a seemingly confident but
meaningless dashboard.

This FRD introduces fallback flagging so downstream agents know when
upstream data is degraded, and typed exception handling so different failure
modes get appropriate responses.

## User Stories

### US-008-001: Visible Fallback Usage

**As a** ROI agent building the dashboard
**I want** to know when upstream agents used fallback data
**So that** I can downgrade confidence and warn the user.

**Acceptance Criteria:**
- GIVEN Cost agent hit a JSON parse error and used fallback selections WHEN
  the ROI agent checks `state.costs` THEN `_used_fallback = True`
- GIVEN BV agent hit a JSON parse error and used fallback drivers WHEN the
  ROI agent checks `state.business_value` THEN `_used_fallback = True` and
  `confidence = "low"`
- GIVEN either agent used fallback WHEN the ROI plausibility engine runs
  (FRD-004) THEN a warning says: "One or more agents used fallback data
  due to errors." AND confidence = "low"

### US-008-002: Context-Specific Error Messaging

**As a** frontend displaying error context
**I want** the error type to distinguish JSON parse failures from unexpected
errors
**So that** I can show relevant guidance (e.g., "Retry" vs. "Contact support").

**Acceptance Criteria:**
- GIVEN LLM returned invalid JSON WHEN error is caught THEN
  `error_type = "json_parse"`
- GIVEN an unexpected runtime error WHEN error is caught THEN
  `error_type = "unknown"`
- GIVEN `error_type = "json_parse"` WHEN frontend renders THEN it shows
  "The AI model returned an unexpected format. Results may be incomplete."

## Functional Requirements

### FR-008-001: Flag Fallback in Cost Agent (Fix T)

In `CostAgent.run()` except blocks, set `state.costs["_used_fallback"] = True`.

- Input: exception caught
- Processing: set flag on state dict
- Output: flag visible to downstream agents
- Error handling: flag-setting itself must not throw

### FR-008-002: Flag Fallback in BV Agent (Fix T)

In `BusinessValueAgent.run()` except blocks, set
`state.business_value["_used_fallback"] = True` and
`state.business_value["confidence"] = "low"`.

### FR-008-003: ROI Fallback Detection (Fix T)

In `_validate_and_reconcile()` (FRD-004), check both `_used_fallback` flags:

- Input: `state.costs`, `state.business_value`
- Processing: if either has `_used_fallback = True`, add warning and force
  confidence = "low"
- Output: warning appended, confidence downgraded

### FR-008-004: Typed Exception Handling (Fix U)

Replace broad `except Exception` in both agents with:

1. `except json.JSONDecodeError` → log "invalid JSON", set `error_type = "json_parse"`
2. `except httpx.TimeoutException` → log "API timeout", set `error_type = "timeout"`
3. `except httpx.HTTPStatusError` → log "API error", set `error_type = "api_error"`
4. `except Exception` → log "unexpected error", set `error_type = "unknown"`

- Input: exception
- Processing: log with `exc_info=True`, set `error_type` on state dict
- Output: `error_type` field on `state.costs` or `state.business_value`
- Error handling: the except block itself must not raise

> **Note:** `timeout` errors are retry-worthy (suggest "Try again").
> `api_error` indicates upstream API issues (suggest "Check Azure status").
> `json_parse` indicates LLM output issues (suggest "Retry — AI model
> returned unexpected format"). `unknown` is a catch-all.

## Non-Functional Requirements

### NFR-008-001: Error Logging

All caught exceptions must be logged with `exc_info=True` (full traceback)
at ERROR level via the structured logger.

### NFR-008-002: Fallback Data Quality

Fallback data must still produce a structurally valid state dict so the
pipeline doesn't crash. The flag + low confidence indicates quality, not
the dict shape.

## Dependencies

| Dependency | Type | Direction | Description |
|------------|------|-----------|-------------|
| FRD-004 | Feature | Downstream | `_validate_and_reconcile` checks `_used_fallback` |
| `ROIDashboard.tsx` | Frontend | Downstream | Renders `error_type` messaging |

---

## Current Implementation (Brownfield Extension)

### Files Involved

| File Path | Role | Lines |
|-----------|------|-------|
| `src/python-api/agents/cost_agent.py` | `run()` except blocks | ~380–420 |
| `src/python-api/agents/business_value_agent.py` | `run()` except blocks | ~300–380 |
| `src/python-api/agents/roi_agent.py` | Dashboard build (consumer) | ~400–500 |

### Architecture Pattern

Both agents use a single `try/except Exception` wrapping the LLM call and
JSON parse. The except block logs the error and populates the state dict with
placeholder data. No distinction between JSON parse failures and other errors.

### Known Limitations

- `except Exception` catches everything: network errors, JSON errors, LLM
  refusals, timeout errors — all handled identically
- Fallback data (e.g., "Standard" SKU for all services) is indistinguishable
  from real data
- Confidence stays "moderate" even after a BV fallback
- ROI agent has no mechanism to detect upstream failures
- No `error_type` field — frontend can't distinguish failure modes

### Test Coverage

| Test Type | Files | Assertions | Coverage |
|-----------|-------|------------|----------|
| Unit | — | — | 0% |
| Integration | — | — | 0% |
| E2E | — | — | 0% |

**Untested paths**: All error paths, fallback logic, exception handling.
