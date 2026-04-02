# PRD: Agent Pipeline Hardening — Audit Fix Pass

**Status**: Draft
**Priority**: P0 (12 HIGH), P1 (25 MEDIUM)
**Date**: 2026-04-02
**Source**: Full 7-agent code audit

---

## Problem Statement

A comprehensive audit of all 7 agents + orchestrator revealed 57 issues
(12 HIGH, 25 MEDIUM, 20 LOW). The HIGH issues include crash paths,
dead code, race conditions, and security vulnerabilities that can produce
incorrect outputs or runtime failures under real-world conditions.

---

## Scope

### In Scope
- All 12 HIGH severity fixes
- Top 15 MEDIUM fixes (impact-ranked)
- Test coverage for fixed paths

### Out of Scope
- LOW severity (documentation, naming, style) — separate cleanup pass
- Feature additions (new agents, UI redesign)
- Performance optimization beyond the thread-safety fix

---

## Work Packages

### WP-1: ROI Agent Correctness (3 fixes)

**WP-1A: Fix unreachable confidence adjustment**
- **File**: `roi_agent.py` ~line 485-491
- **Bug**: `_validate_and_reconcile` returns at line 485 before the
  confidence adjustment logic at 487-491. The warning-count-based
  downgrade never executes.
- **Fix**: Remove duplicate return; single return at end of method.
- **Test**: Trigger 2+ warnings → verify confidence downgrades to "low".

**WP-1B: Fix BV clamp rounding overshoot**
- **File**: `roi_agent.py` ~line 604-620
- **Bug**: Overshoot trimming can make a component negative if overshoot
  exceeds the largest component's value.
- **Fix**: `reduction = min(largest_value, overshoot)` — never go below 0.
- **Test**: Edge case with very small components and large overshoot.

**WP-1C: Fix roiRunRateText variable**
- **File**: `roi_agent.py` ~line 995
- **Bug**: `"roiRunRateText": roi_display_text` should be `roi_steady_text`.
- **Fix**: One-line change.
- **Test**: Verify dashboard `roiRunRateText` ≠ `roiDisplayText`.

---

### WP-2: Cost Agent Thread Safety + HA Pattern (2 fixes)

**WP-2A: Add lock to price_cache**
- **File**: `cost_agent.py` ~line 420-450
- **Bug**: `price_cache` dict accessed from 5 concurrent threads without
  synchronization. Can raise `RuntimeError` on dict resize.
- **Fix**: Add `threading.Lock()` around cache reads/writes.
- **Test**: Run with 10+ services; verify no race condition.

**WP-2B: Extract haPattern from architecture/text**
- **File**: `cost_agent.py` ~line 220-235
- **Bug**: `haPattern` is never set by the LLM (not in prompt schema).
  Always defaults to 40% overhead.
- **Fix**: Extract from architecture state or user text:
  `"active-active" in full_text.lower()` → 50%, etc.
- **Test**: Provide "active-passive HA" in use case → verify 30% overhead.

---

### WP-3: PM Agent Crash Prevention (3 fixes)

**WP-3A: Wrap brainstorm LLM call in try-catch**
- **File**: `pm_agent.py` ~line 162
- **Bug**: `llm.invoke()` not wrapped. LLM timeout/error crashes the
  entire brainstorm flow with unhandled exception.
- **Fix**: try-catch with fallback response.
- **Test**: Simulate LLM failure → verify graceful fallback.

**WP-3B: Validate ROI values before display**
- **File**: `pm_agent.py` ~line 362-380, 607-608
- **Bug**: `(roi_pct / 100 + 1)` crashes if `roi_pct` is None.
- **Fix**: Add `if roi_pct is not None` guard.
- **Test**: ROI with missing percent → verify no crash.

**WP-3C: Safe pricing source parsing**
- **File**: `pm_agent.py` ~line 508-516
- **Bug**: `int(p.split()[0])` crashes on malformed pricing source strings.
- **Fix**: Wrap in try-except with `parse_count()` helper.
- **Test**: Malformed source string → verify safe fallback.

---

### WP-4: Presentation Agent Robustness (4 fixes)

**WP-4A: Validate Node.js availability**
- **File**: `services/presentation.py` ~line 50
- **Bug**: `subprocess.run(["node", ...])` raises `FileNotFoundError`
  if Node.js not installed.
- **Fix**: Pre-check with `node --version`; raise descriptive error.
- **Test**: Mock missing node → verify clear error message.

**WP-4B: Validate LLM-generated JavaScript**
- **File**: `presentation_agent.py` ~line 203-206
- **Bug**: Invalid JS passes through silently; only fails at Node runtime.
- **Fix**: Basic structural check — must contain `require("pptxgenjs")`,
  `new PptxGenJS()`, and `writeFile`.
- **Test**: Malformed script → verify early rejection.

**WP-4C: Safe cost confidence parsing**
- **File**: `presentation_agent.py` ~line 87-91
- **Bug**: Same `int(p.split()[0])` crash risk as PM agent.
- **Fix**: Same `parse_count()` helper pattern.
- **Test**: Malformed pricing source → verify safe fallback.

**WP-4D: Fix path traversal via symlinks**
- **File**: `main.py` ~line 307-312
- **Bug**: `os.path.abspath()` doesn't resolve symlinks.
  Attacker could create a symlink to read arbitrary files.
- **Fix**: Use `os.path.realpath()` for both path and OUTPUT_DIR.
- **Test**: Symlink to /etc/passwd → verify 403.

---

### WP-5: Orchestrator Error Handling (2 fixes)

**WP-5A: Use _cleanup_project in error handler**
- **File**: `maf_orchestrator.py` ~line 500-509
- **Bug**: Exception handler does manual pops but misses
  `_pending_assumptions` and `_locks` — incomplete cleanup.
- **Fix**: Replace manual pops with `self._cleanup_project(project_id)`.
- **Test**: Simulate workflow crash → verify all dicts cleaned.

**WP-5B: Presentation executor missing ctx.send_message**
- **File**: `workflow.py` ~line 640-658
- **Bug**: `on_approval()` always emits `pipeline_done` even on skip/refine
  without calling `ctx.send_message(msg)` first.
- **Fix**: Add `await ctx.send_message(msg)` before pipeline_done.
- **Test**: Skip presentation → verify pipeline completes cleanly.

---

### WP-6: Top MEDIUM Fixes (5 fixes)

**WP-6A: ROI affected_employees fallback**
- **File**: `roi_agent.py` ~line 108
- **Bug**: When `affected_employees` is None but `total_users` is 2.5M,
  no fallback logic. Uses single lump baseline (correct but loses
  labor breakdown for future-cost model).
- **Fix**: If `affected_employees` is None AND `total_users < 10000`,
  use `total_users` as employee proxy. Otherwise skip labor breakdown.

**WP-6B: BV spend_ceiling validation**
- **File**: `business_value_agent.py` ~line 192-194
- **Bug**: `spend_ceiling` can be None/0; prompt would contain "$0"
  confusing the LLM about whether cost-reduction should be bounded.
- **Fix**: Validate and skip ceiling block if not available.

**WP-6C: Cost agent missing unit handlers**
- **File**: `cost_agent.py` ~line 501-570
- **Bug**: No handling for "per transaction", "per message", "per event".
  Unknown units silently treated as monthly — underestimates cost.
- **Fix**: Add transaction/message/event unit detection with usage lookup.

**WP-6D: Azure OpenAI price refresh**
- **File**: `pricing.py` ~line 102-113
- **Bug**: `per_request_cost()` called at module import time. Price is
  fixed for app lifetime even if `AI_MODEL_PRICING` is updated.
- **Fix**: Lazy-evaluate in `query_azure_pricing_sync()`.

**WP-6E: Orchestrator error cleanup**
- Already covered by WP-5A.

---

## Implementation Order

```
Parallel Group A (independent):
  WP-1A + WP-1B + WP-1C  (ROI agent — 3 surgical fixes)
  WP-3A + WP-3B + WP-3C  (PM agent — 3 crash guards)
  WP-4C + WP-4D          (Presentation + main.py — parsing + security)

Parallel Group B (after A):
  WP-2A + WP-2B          (Cost agent — thread safety + HA)
  WP-4A + WP-4B          (Presentation — Node.js validation)
  WP-5A + WP-5B          (Orchestrator — error handling)

Parallel Group C (after B):
  WP-6A + WP-6B + WP-6C + WP-6D  (MEDIUM fixes)
```

Groups A and B have no dependencies — all 14 fixes across 6 files.
Group C addresses MEDIUM issues after HIGH fixes stabilize.

---

## Acceptance Criteria

### Per Work Package
Each WP must:
1. Fix the specific bug described
2. Include a test that reproduces the bug BEFORE the fix
3. Pass all existing tests (no regressions)
4. Be committed as an atomic, revertible commit

### Overall
- Zero HIGH severity issues remaining
- All crash paths guarded with try-catch + fallback
- Thread-safe pricing cache
- Path traversal vulnerability closed
- Dead code removed

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| ROI formula changes affect dashboard | All fixes are isolated to specific methods; dashboard contract unchanged |
| Thread lock adds latency | Lock only held during dict read/write (~microseconds); API calls outside lock |
| Node.js validation blocks deployment | Check runs once at startup; fails fast with clear message |
| PM fallback hides real errors | Fallback logs at ERROR level; monitoring can alert |

---

## Metrics

| Metric | Before | Target |
|--------|--------|--------|
| HIGH issues | 12 | 0 |
| Crash paths (unguarded LLM calls) | 3 | 0 |
| Race conditions | 1 | 0 |
| Security vulnerabilities | 1 | 0 |
| Dead code blocks | 1 | 0 |
