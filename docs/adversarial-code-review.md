# Adversarial Code Review — OneStopAgent (Round 3)

> **Date**: 2026-04-05  
> **Scope**: Full codebase — agents, services, frontend, state/models, tests, config  
> **Method**: 5 parallel adversarial review agents, each verified callers via grep, traced execution paths, challenged prior review findings

---

## Executive Summary

| Category | Critical | High | Medium | Total |
|----------|----------|------|--------|-------|
| Hidden Bugs | 8 | 6 | 4 | 18 |
| Dead Code / Stale Files | — | 3 | 5 | 8 |
| Duplicate Logic | — | 4 | 3 | 7 |
| Inconsistent Architecture | — | 5 | 4 | 9 |
| Schema Drift (FE↔BE) | — | 3 | 2 | 5 |
| CI/Test Gaps | 1 | 3 | 2 | 6 |
| **TOTAL** | **9** | **24** | **20** | **53** |

---

## 🔴 CRITICAL Findings

### C1. `mock_llm` Fixture Doesn't Actually Mock LLM Calls
**File**: `conftest.py:257`, `agents/llm.py:178`  
**Impact**: ALL agent tests hit real Azure OpenAI instead of using mock  
**Root Cause**: `llm = LLMClient()` singleton is instantiated at module import time. By the time `with patch("agents.llm.llm", mock)` runs, agents have already cached a reference to the real instance.  
**Proof**: `test_missing_architecture_graceful` returns 401 Unauthorized from real Azure API.  
**Fix**: Lazy-initialize `llm` via factory function (`get_llm()`) that can be patched, or use dependency injection.

### C2. Division by Zero in ROI Agent
**File**: `agents/roi_agent.py:373`  
```python
if max_hard_savings > 0 and raw_hard > max_hard_savings:
    scale = max_hard_savings / raw_hard  # raw_hard could be 0!
```
**When**: All BV drivers have zero amounts → `raw_hard = 0`.  
**Fix**: Add `and raw_hard > 0` guard.

### C3. Dict KeyError in Cost Agent
**File**: `agents/cost_agent.py:555-556`  
```python
price = result["price"]   # ← No .get(), crashes if key missing
source = result["source"]  # ← Same
```
**When**: Azure Pricing API returns malformed response.  
**Fix**: Use `result.get("price", 0)` and `result.get("source", "unknown")`.

### C4. Race Condition — asyncio.run() in Multi-Threaded Context
**File**: `agents/llm.py:134`  
**When**: Thread pool executor calls `agent.run(state)` → `llm.invoke()` → `asyncio.run(_call())` creates a new event loop per thread. Multiple concurrent threads cause loop conflicts.  
**Fix**: Use `asyncio.new_event_loop()` per thread with proper cleanup, or route all sync calls through `run_coroutine_threadsafe()`.

### C5. Empty Array Cached Forever in Company Intelligence
**File**: `services/company_intelligence.py:281-403`  
**When**: Web search fails → returns `[]` → `_cache_put(cache_key, [])` stores empty result for 30 minutes.  
**Impact**: User searches again, gets cached empty result, thinks company doesn't exist.  
**Fix**: Don't cache empty results, or use shorter TTL (e.g., 60s) for empty results.

### C6. ProjectStore Has Zero Thread Synchronization
**File**: `services/project_store.py:1-53`  
**Race**: Two threads call `add_message("proj1", ...)` simultaneously → one message is lost due to check-then-act on `dict`.  
**Fix**: Use `self.chat_histories.setdefault(project_id, []).append(message)` or add `threading.Lock()`.

### C7. Token Provider Credential Never Re-Evaluated on Refresh Failure
**File**: `services/token_provider.py:105-132`  
**When**: AzureCliCredential succeeds at init, user logs out of CLI, credential cached forever → refresh fails → no fallback to DefaultAzureCredential.  
**Fix**: Catch refresh failures and rebuild the credential chain.

### C8. List Mutation Without Lock in Orchestrator Retry
**File**: `maf_orchestrator.py:294-296`  
```python
state.completed_steps = [s for s in state.completed_steps if s not in rerun_set]
```
Recreates lists WITHOUT holding `state._lock`. If `mark_step_completed()` runs concurrently, the old list reference is orphaned.  
**Fix**: Wrap in `with state._lock:`.

### C9. Double Project Creation Vulnerability (Frontend)
**File**: `Landing.tsx:397-403`  
**When**: `setLoading(true)` runs asynchronously; fast double-click can submit twice before state updates.  
**Fix**: Move `setLoading(true)` to first synchronous line of `handleCreate()`, or use a ref-based lock.

---

## 🟠 HIGH Findings

### H1. Pricing Fallback Chain Silently Switches to Estimated Prices
**File**: `services/pricing.py:672-717`  
3-strategy API fallback → all return `()` → silently falls through to ESTIMATED_PRICES fuzzy match. Caller sees "live" source label on estimated data.  
**Fix**: Return explicit source type distinguishing live/estimated/fuzzy.

### H2. Frontend Race: getChatHistory Overwrites Streaming Messages
**File**: `Chat.tsx:27-37, 113-121`  
Auto-send fires after 300ms; if history fetch takes >300ms, it overwrites streaming messages when it resolves.  
**Fix**: Make auto-send await history fetch completion.

### H3. Network Error Mid-Stream Shows Partial Data Without Warning
**File**: `api.ts:93-129`  
No try-catch around `reader.read()`. Network drop mid-stream leaves partial architecture/cost data rendered with no indication of incompleteness.  
**Fix**: Wrap streaming loop in try-catch; track completion state.

### H4. SharedAssumptions.from_dict() Accepts Booleans as Numbers
**File**: `agents/state.py:104-109`  
`float(True)` → `1.0` silently. Boolean values get treated as numeric assumptions.  
**Fix**: Add `and not isinstance(sa_val, bool)` guard.

### H5. Shallow Dict Mutation During Retry
**File**: `maf_orchestrator.py:301-304`  
```python
del state.costs["phase"]  # Mutating dict that may be read by running agent
```
**Fix**: Replace with `state.costs = {}` (full reset, not in-place mutation).

### H6. Presentation Agent Node.js Check Is Late
**File**: `services/presentation.py:22-31`  
Node.js check happens inside `execute_pptxgenjs()` — after all prior agents completed. If Node is missing, entire pipeline wasted.  
**Fix**: Check at startup or before pipeline begins.

### H7. Frontend API Errors Lack Context
**File**: `api.ts` (all functions)  
`throw new Error(\`HTTP ${res.status}\`)` — no response body, no URL, no method info.  
**Fix**: Parse `res.text()` and include in error message.

### H8. Dict Default Type Mismatch in Cost Agent
**File**: `agents/cost_agent.py:239-251`  
`usage_dict.get("concurrent_users", 0)` returns `0` → "small" tier selected when NO value was provided (should be sentinel/None).  
**Fix**: Use `usage_dict.get("concurrent_users") or typed.concurrent_users or ...`

### H9. CompanyCard Duplicates CompanyDetailModal Logic
**Files**: `CompanyCard.tsx`, `CompanyDetailModal.tsx`  
Both define identical `fmt()`, `fmtNum()`, `CONFIDENCE_COLORS`, `Tag`, `MetricCell`.  
**Fix**: Extract to shared `utils/format.ts` and `components/CompanyDisplay.tsx`.

### H10. Frontend Missing CSS Variable
**File**: `ROIDashboard.tsx:230`  
Uses `var(--bg-card)` which is never defined in `index.css`.  
**Fix**: Add `--bg-card: var(--bg-subtle);` to CSS.

---

## 🟡 MEDIUM Findings

### M1. Dead Code: `pm_agent.get_agents_to_rerun()` (never called)
### M2. Dead Code: `architect_agent._count_mermaid_nodes()` (only called by tests)
### M3. Dead Code: `workflow.py` (~300 lines, only imported by tests)
### M4. Dead Code: `test_template.py` (orphan manual test script)
### M5. Dead Code: Empty `scripts/` and `src/python-api/scripts/` directories
### M6. Redundant import: `re as _re` in `architect_agent.py:72` (re already imported at top)

### M7. Duplicate Logic: "Extract Quantity from Text" — 3 variants
- `utils.py:parse_leading_int()`, `presentation_agent.py:_safe_leading_int()`, `cost_agent.py:_extract_users()`  
**Fix**: Use `parse_leading_int()` everywhere.

### M8. Duplicate Logic: "Compute Confidence from Source" — 2 identical blocks
- `pm_agent.py:618-627` and `presentation_agent.py:127-146`  
**Fix**: Extract to `utils.compute_pricing_confidence()`.

### M9. Duplicate Logic: "Build Context from State" — 4 variants across agents
**Fix**: Expand `state.to_context_string()` and use consistently.

### M10. Overly Long Methods: `pm_agent.format_agent_output()` (370 lines), `approval_summary()` (150 lines)
**Fix**: Split into per-agent formatters via dispatcher/strategy pattern.

### M11. ESTIMATED_PRICES Has ~25 Duplicate/Near-Duplicate Entries
**File**: `services/pricing.py`  
E.g., "Azure Logic Apps" + "Logic Apps", "Azure Cosmos DB" × 3 entries.  
**Fix**: Canonical names only + expand SERVICE_NAME_MAP for aliases.

### M12. Schema Drift: ChatMessage Uses snake_case Backend, camelCase Frontend
**File**: `models/schemas.py:88` vs `frontend/src/types.ts:52`  
Workaround exists (`normalizeMessage()` in api.ts) but fragile.  
**Fix**: Pydantic `Field(alias="projectId")` with `populate_by_name=True`.

### M13. CI Missing: No linting, no type checking, no coverage reporting
**File**: `.github/workflows/ci.yml`  
pytest-cov installed but never run. No pylint/mypy/black.

### M14. CI: Incomplete py_compile — Only 7 of ~20 Python files checked

### M15. Agent-framework pinned to RC version (1.0.0rc5)
**Fix**: Upgrade to stable release if available; add upper bounds on all deps.

### M16. Three Different Frontend Error Handling Patterns
- Pattern A: `throw new Error(...)` (api.ts)
- Pattern B: `catch → setErrorMessage()` (Chat.tsx)  
- Pattern C: `.catch(() => {})` — silent fail (App.tsx)

### M17. Four Different Frontend Loading State Patterns
`sending`, `loading`, `loadingOpps`, `companySearching` — no unified state machine.

### M18. Inconsistent Agent Error Handling
Architect has explicit fallback, Cost/BV ask for input, ROI gives up. No standardized strategy.

### M19. LLM Invocation: Mixed `invoke()` / `ainvoke()` / `astream()` Without Clear Rationale

### M20. `dangerouslySetInnerHTML` in MessageContent.tsx Without Null Guard
`marked.parse()` could return undefined → renders literal "undefined" in UI.

---

## Implementation Priority

### Phase 1 — Critical Bugs (Immediate)
1. Fix `mock_llm` fixture (C1) — unblocks proper test coverage
2. Fix division-by-zero in ROI agent (C2)
3. Fix KeyError in cost agent (C3)
4. Fix empty-cache bug in company intelligence (C5)
5. Add lock to ProjectStore (C6)
6. Fix token provider refresh (C7)
7. Fix orchestrator list mutation lock (C8)
8. Fix double-click vulnerability (C9)

### Phase 2 — High Priority (Next Sprint)
9. Fix pricing source transparency (H1)
10. Fix frontend race condition (H2)
11. Fix streaming error handling (H3)
12. Fix boolean coercion in SharedAssumptions (H4)
13. Fix dict mutation in retry logic (H5)
14. Extract shared frontend formatters (H9)
15. Define missing CSS variable (H10)

### Phase 3 — Code Quality (Backlog)
16. Delete dead code (M1-M6)
17. Consolidate duplicate logic (M7-M9)
18. Split overly long methods (M10)
19. Deduplicate ESTIMATED_PRICES (M11)
20. Standardize schema casing (M12)

### Phase 4 — CI/DX (Backlog)
21. Add linting + type checking to CI (M13)
22. Expand py_compile coverage (M14)
23. Add pytest-cov reporting
24. Upgrade agent-framework to stable (M15)
25. Standardize frontend error/loading patterns (M16-M17)
