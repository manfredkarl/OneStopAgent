# OneStopAgent — Deep Code Audit

**Date:** 2026-04-05  
**Scope:** Line-by-line analysis of every file — dead code, duplication, parallelization, output quality, retrieval improvements  

---

## Executive Summary

A deep audit across 6 areas (agents, services, frontend, tests, config, models/state) identified **100+ findings**. The most impactful are:

- **Data flow gaps** — state data gets lost between agent phases, especially on iteration/re-run
- **Prompt contradictions** — conflicting instructions in BV and Architect prompts degrade LLM output quality
- **Missing validation** — negative employee counts, revenues, and assumptions silently corrupt calculations
- **Parallelization** — BV Phase 2 + Architect could run concurrently (saves ~37% pipeline time)
- **Dead code** — ~15 unused functions/fields/constants across the codebase
- **Duplicate logic** — `strip_markdown_fences()` + JSON parse pattern repeated 8× across 5 agents

---

## Table of Contents

1. [Agent Pipeline](#1-agent-pipeline)
2. [Data Flow & State](#2-data-flow--state)
3. [Services Layer](#3-services-layer)
4. [Frontend](#4-frontend)
5. [Tests](#5-tests)
6. [Config & Infrastructure](#6-config--infrastructure)
7. [Priority Matrix](#7-priority-matrix)
8. [Implementation Plan](#8-implementation-plan)

---

## 1. Agent Pipeline

### 1.1 Prompt Contradictions — BV Agent 🔴 HIGH
**File:** `agents/business_value_agent.py:150-195`  
**Issue:** Lines 151-154 say "DO NOT fabricate benchmark sources" but lines 184-195 instruct using vague labels like "Azure industry analysis." Line 161 says "NEVER use vague label 'Industry estimate'" then provides vague alternatives.  
**Impact:** Inconsistent source labeling across runs. LLM follows the later instruction.  
**Fix:** Unify into one source-labeling rule. When no search results: use only `"Calculated from user assumptions: [formula]"`, `"Labor rate analysis"`, `"Spend optimization model"`, `"Revenue acceleration estimate"`. Always set `source_url` to empty string.

### 1.2 Prompt Contradictions — Architect Agent 🔴 HIGH
**File:** `agents/architect_agent.py:214-277`  
**Issue:** Prompt says "Do NOT include business value metrics, dollar amounts, ROI" but the context block includes company profile with `employeeCount`, `annualRevenue`, `itSpendEstimate`. LLM is confused — ignore financial data or use it for scale guidance?  
**Fix:** Split context into architecture-only block (employee count + HQ for scale) and business block (revenue, IT spend — pass only to cost/BV agents).

### 1.3 Dead Code — `_last_mapping_fallback` 🟡 MEDIUM
**File:** `agents/cost_agent.py:275, 380-381, 474-475, 488-489`  
**Issue:** Instance variable set and checked but the resulting flag `state.costs["_used_fallback"]` is never read by any downstream agent or frontend.  
**Fix:** Either surface the fallback indicator to the user (add to `roi.warnings`) or remove the variable entirely.

### 1.4 Dead Code — Unused Constants and Functions
| File | Line | What | Action |
|------|------|------|--------|
| `pm_agent.py:154-179` | `PLAN_TO_ACTIVE` dict | Never referenced | DELETE |
| `cost_agent.py:20` | `HOURS_PER_MONTH` in comment only | Not a constant | Extract to named constant |
| `agents/llm.py` | `_StaticTokenCredential` class (if remains) | Replaced by token_provider | DELETE |

### 1.5 Duplicate Pattern — `strip_markdown_fences()` + JSON Parse 🟡 MEDIUM
**Files:** 8 locations across `architect_agent.py:282`, `business_value_agent.py:68,294`, `cost_agent.py:216,467`, `pm_agent.py:227,335`, `presentation_agent.py:289,302`  
**Issue:** All follow identical pattern: `strip_markdown_fences(response.content)` → `json.loads()` → `except JSONDecodeError` → fallback.  
**Fix:** Create shared `parse_llm_json(response, fallback)` utility in `agents/llm.py`.

### 1.6 Overly Broad Exception Handling 🔴 HIGH
**Files:** `pm_agent.py:125,216-250`, `architect_agent.py:49`, `cost_agent.py:476`, `business_value_agent.py:74`, `presentation_agent.py:56,62`  
**Issue:** Bare `except Exception` catches everything including `SystemExit`, `KeyboardInterrupt`. Auth failures (401) get swallowed as "fallback response" instead of surfacing to user.  
**Fix:** Catch specific exceptions: `(json.JSONDecodeError, KeyError, ValueError, TypeError)` for parse errors, let `ConnectionError`/`TimeoutError` propagate.

### 1.7 Parallelization — BV Phase 2 + Architect 🟡 MEDIUM
**File:** `workflow.py:356-416, 460-544`  
**Issue:** BV Phase 2 (calculate drivers) and Architect run sequentially. Both are independent after assumptions are provided. Serial = ~8 min, parallel = ~5 min.  
**Fix:** After BV assumptions input, spawn Architect as concurrent task via `asyncio.create_task()`.

### 1.8 Duplicate String Literals 🟢 LOW
**File:** `cost_agent.py:26-89`  
**Issue:** HA patterns ("active-active", "active-passive"), region mappings, and service tier lists are inline strings rather than named constants.  
**Fix:** Extract to module-level constants: `HA_PATTERNS`, `REGION_MAP`, `TIER_ORDER`.

---

## 2. Data Flow & State

### 2.1 No Validation on Critical Fields 🔴 CRITICAL
| Field | File | Issue |
|-------|------|-------|
| `CompanyProfile.employeeCount` | `schemas.py:20` | Can be negative — no Pydantic validator |
| `CompanyProfile.annualRevenue` | `schemas.py:24` | Can be negative — no validator |
| `CompanyProfile.itSpendRatio` | `schemas.py:29` | No range check (0.0-1.0) — API returning 104 = 10,400% |
| `SharedAssumptions` negative values | `state.py:111` | Silently skipped with `if numeric <= 0: continue` — NO warning, NO error |

**Fix:** Add Pydantic `field_validator` for positive numbers. For `SharedAssumptions`, log warning and raise `ValueError` instead of silent skip.

### 2.2 Data Lost on Iteration 🔴 CRITICAL
**File:** `maf_orchestrator.py`, `workflow.py`  
**Issue:** When user says "make it cheaper" (iteration), `state.architecture["components"]` gets cleared. Cost agent re-runs but old components unavailable → falls back to generic 1.5× HA multiplier instead of architecture-specific values.  
**Fix:** Preserve `state.architecture` when re-running cost. Add `state.iteration_context: dict` with `{"previous_step": "cost", "feedback": "...", "rerun_agents": [...]}`.

### 2.3 Scenarios Not Passed to Cost Agent 🔴 HIGH
**File:** `maf_orchestrator.py:147-150`  
**Issue:** `state.brainstorming["scenarios"]` is written by PM Agent and read by Architect + BV + Presentation, but **Cost Agent never reads it**. Cost estimates miss scenario nuances.  
**Fix:** Pass scenarios context to cost agent in orchestrator.

### 2.4 Unused State Fields 🟡 MEDIUM
| Field | File | Status |
|-------|------|--------|
| `state.awaiting_approval` | `state.py:185` | Set in `mark_step_running()`, never read |
| `state.current_step` | `state.py:186` | Only read in tests, never in production |
| `CompanyProfile.revenueSource` | `schemas.py:27` | Extracted but never read by any agent |
| `CompanyProfile.employeeCountSource` | `schemas.py:21` | Extracted but never read |
| `CompanyProfile.techStackNotes` | `schemas.py:35` | Never read — lost opportunity for architect |
| `PlanStep.status` | `schemas.py:93` | Defined as Literal type but never used in workflow |

**Fix:** Delete unused fields, or wire `techStackNotes` into architect prompt for better component selection.

### 2.5 No Field for "Is This a Re-Run?" 🟡 MEDIUM
**Issue:** When user requests iteration, agents don't know they're re-running. PM doesn't reuse prior assumptions, cost doesn't preserve architecture, presentation doesn't highlight changes.  
**Fix:** Add `state.iteration_context` field.

### 2.6 No Tracking of Changed Assumptions 🟡 MEDIUM
**Issue:** When user adjusts `hourly_labor_rate` in iteration, no record of old vs new value. ROI can't highlight "ROI dropped 15% due to $5/hr rate change."  
**Fix:** Add `state.assumption_deltas: dict[str, tuple[float, float]]`.

### 2.7 LLM Company Profile Not Validated Against Schema 🔴 HIGH
**File:** `services/company_intelligence.py:334`  
**Issue:** LLM-generated company JSON is parsed with `json.loads()` but never validated against `CompanyProfile` Pydantic model. Hallucinated fields flow through unchecked.  
**Fix:** Wrap in `CompanyProfile(**data)` with `try/except pydantic.ValidationError`.

---

## 3. Services Layer

### 3.1 Pricing API — Sequential Fallbacks 🟡 MEDIUM
**File:** `services/pricing.py:619-629`  
**Issue:** 4 sequential API calls with fallback. Worst case: 4 × 15s timeout = 60s.  
**Fix:** Fire fallback queries in parallel with `asyncio.gather()`, take first success.

### 3.2 Pricing — Missing Common Azure Services 🟡 MEDIUM
**File:** `services/pricing.py` ESTIMATED_PRICES  
**Missing:** Azure AI Search, Azure Machine Learning Compute, Azure Databricks, Azure Synapse, Azure Data Explorer, Azure Monitor, Application Insights, Azure Logic Apps.  
**Fix:** Add estimated prices for these commonly-architected services.

### 3.3 Duplicate IT Spend Ratio Lookup 🟢 LOW
**Files:** `company_intelligence.py:127-141` AND `347-359`  
**Issue:** Identical industry→ratio matching logic in two places.  
**Fix:** Extract to `_get_industry_ratio(industry: str) -> float`.

### 3.4 Company Search Queries Could Be Better 🟡 MEDIUM
**File:** `company_intelligence.py:287-291`  
**Issue:** Third query (`cloud provider technology stack Azure AWS ERP`) yields low-quality results for most companies. Tech stack info is rarely on DuckDuckGo.  
**Fix:** Replace with `"{company} annual report 2024 investor relations"` for better financial data, or `"{company} case study Azure migration"` for Azure usage hints.

### 3.5 Presentation subprocess Blocking 🟡 MEDIUM
**File:** `services/presentation.py:54`  
**Issue:** `subprocess.run()` blocks event loop 5-10s during Node.js PptxGenJS execution.  
**Fix:** Use `asyncio.create_subprocess_exec()`.

### 3.6 Project Store — No Cleanup 🟡 MEDIUM
**File:** `services/project_store.py`  
**Issue:** In-memory store grows unbounded. No TTL, no eviction.  
**Fix:** Add 24h TTL cleanup via FastAPI lifespan background task.

---

## 4. Frontend

### 4.1 Dead Code 🟡 MEDIUM
| Item | File | Action |
|------|------|--------|
| `sendMessage()` function | `api.ts:133-142` | Never called — DELETE |
| `--bg-sidebar` CSS variable | `index.css:7,38` | Never used — DELETE |
| `_onProjectCreated` param | `Chat.tsx:16` | Aliased but never used — REMOVE |
| `react-markdown` dependency | `package.json` | Never imported — `npm uninstall` |

### 4.2 Zero Client-Side Caching 🔴 HIGH
**Files:** All page components  
**Issue:** Every navigation triggers fresh API calls. No caching of chat history, project list, or agent status.  
**Fix:** Implement `APICache` class with 5-10 min TTL.

### 4.3 No AbortController 🟡 MEDIUM
**File:** `api.ts:93-129`  
**Issue:** Navigating away during streaming leaves fetch requests running.  
**Fix:** Add `AbortController` to `sendMessageStreaming()`, cancel on component unmount.

### 4.4 No Code Splitting 🟡 MEDIUM
**File:** `App.tsx`  
**Issue:** All pages imported statically. No `React.lazy()`.  
**Fix:** Lazy-load `Landing`, `Chat`, `Architecture` pages.

### 4.5 Type Safety — 12 `any` Casts 🟡 MEDIUM
**Files:** `api.ts:11`, `App.tsx:78`, `AgentSidebar.tsx:29,52,63,64`, `ROIDashboard.tsx:240,250,252,510,517,520`  
**Fix:** Define proper interfaces. Extend `AgentRegistry` with `comingSoon?`. Extend `ROIDashboardData` with `roiSubtitle?`, `roiSteadyStateText?`.

### 4.6 Duplicate Components 🟢 LOW
| Duplication | Files | Fix |
|------------|-------|-----|
| `Tag` component defined twice | `CompanyCard.tsx:102`, `CompanyDetailModal.tsx:40` | Extract to `components/Tag.tsx` |
| `EMOJIS` dict defined twice | `ChatThread.tsx:17`, `AgentSidebar.tsx:12` | Export from `types.ts` |

### 4.7 Missing Accessibility 🟡 MEDIUM
- `AgentSidebar.tsx:74`: `role="button"` without `tabIndex={0}` or keyboard handler
- No focus indicators on custom interactive elements
- `MermaidDiagram.tsx:59`: `dangerouslySetInnerHTML` SVG without alt text

### 4.8 No Frontend Tests 🟡 MEDIUM
No vitest/jest configured. No component tests exist.

---

## 5. Tests

### 5.1 BDD Framework Stubbed 🟡 MEDIUM
**Files:** All 5 `tests/step_defs/test_*.py` files  
**Issue:** All marked `# TODO: BDD step definitions are stubbed`. Steps ARE implemented but unclear if CI runs them. Duplicates logic from unit tests.  
**Fix:** Either remove pytest-bdd entirely (consolidate to unit tests) or fully integrate and remove duplicate unit tests.

### 5.2 Missing `canned_brainstorming` Fixture 🟢 LOW
**File:** `conftest.py:165-180`  
**Issue:** `CANNED_BRAINSTORMING` constant exists but no `@pytest.fixture` wrapper (unlike `canned_bv`, `canned_costs`, etc.).  
**Fix:** Add fixture.

### 5.3 Unused `async_client` Fixture 🟢 LOW
**File:** `conftest.py:344-358`  
**Issue:** Defined but never referenced in any test.  
**Fix:** Delete.

### 5.4 Missing Error Path Tests 🔴 HIGH
**Issue:** No tests for LLM failures, malformed JSON, timeout handling in BV, Architect, or Cost agents. Tests verify "doesn't crash" rather than correct fallback behavior.  
**Fix:** Add error scenario tests for each agent's `run()` method.

### 5.5 No E2E Pipeline Test 🔴 HIGH
**Issue:** No integration test for full BV → Architect → Cost → ROI → Presentation flow. State-passing regressions between agents go undetected.  
**Fix:** Add `@pytest.mark.integration` test with mock LLM that exercises full pipeline.

### 5.6 Weak Assertions 🟡 MEDIUM
**Files:** `test_pm_agent.py:231-237`, `test_company_intelligence.py:280-285`  
**Issue:** Tests check `isinstance(output, str)` but not meaningful content.  
**Fix:** Add content assertions (length > N, contains expected keywords).

---

## 6. Config & Infrastructure

### 6.1 CORS — Overly Permissive 🔴 HIGH
**File:** `main.py:61-70`  
**Issue:** `allow_methods=["*"]`, `allow_headers=["*"]` with `credentials=True`. Should be explicit.  
**Fix:** `allow_methods=["GET", "POST", "PATCH"]`, `allow_headers=["Content-Type", "x-user-id"]`.

### 6.2 RC Dependency 🟡 MEDIUM
**File:** `requirements.txt:4`  
**Issue:** `agent-framework==1.0.0rc5` is a pre-release. Can be yanked from PyPI.  
**Fix:** Upgrade to stable GA when available. Document why RC is needed.

### 6.3 Exception Chain Lost 🟡 MEDIUM
**File:** `presentation_agent.py:62`  
**Issue:** `raise RuntimeError(f"...{e2}")` without `from e2` — loses stack trace.  
**Fix:** Add `from e2`.

### 6.4 No Auto-Scaling Rules 🟡 MEDIUM
**File:** `infra/main.bicep`  
**Issue:** Container Apps have no scaling rules. Single instance handles all traffic.  
**Fix:** Add HTTP-based scaling rule (e.g., 10 concurrent requests per instance).

### 6.5 No Health Check Probes in Bicep 🟡 MEDIUM
**Issue:** Container Apps don't define liveness/readiness probes.  
**Fix:** Add `/health` endpoint probe.

### 6.6 README Accuracy 🟢 LOW
**Issue:** README may not reflect current architecture (agents added, MCP integration, presentation gen).  
**Fix:** Update with current agent list, architecture diagram, setup instructions.

---

## 7. Priority Matrix

### Tier 1 — Fix Now (Critical Impact)

| # | Finding | Section | Impact | Effort |
|---|---------|---------|--------|--------|
| 1 | Add Pydantic validators (negative values) | 2.1 | Data corruption | 1 hr |
| 2 | Fix BV prompt contradictions | 1.1 | Inconsistent output | 30 min |
| 3 | Fix Architect prompt contradictions | 1.2 | Confused LLM output | 30 min |
| 4 | Preserve architecture on iteration | 2.2 | Wrong costs on re-run | 1 hr |
| 5 | Pass scenarios to Cost Agent | 2.3 | Missing context | 30 min |
| 6 | Validate company profile against schema | 2.7 | Hallucinated data | 30 min |
| 7 | Narrow exception handling | 1.6 | Hidden auth failures | 2 hr |

### Tier 2 — Next Sprint (High Impact)

| # | Finding | Section | Impact | Effort |
|---|---------|---------|--------|--------|
| 8 | Extract shared `parse_llm_json()` | 1.5 | Code duplication | 1 hr |
| 9 | Parallel BV Phase 2 + Architect | 1.7 | 37% faster pipeline | 2 hr |
| 10 | Frontend client caching | 4.2 | Redundant API calls | 1 hr |
| 11 | Add error path tests | 5.4 | Undetected failures | 3 hr |
| 12 | Add E2E pipeline test | 5.5 | State regression risk | 2 hr |
| 13 | Frontend AbortController | 4.3 | Resource waste | 45 min |
| 14 | Fix CORS to explicit methods | 6.1 | Security | 15 min |
| 15 | Async PPTX subprocess | 3.5 | Event loop blocked | 30 min |
| 16 | Add missing estimated prices | 3.2 | Better cost accuracy | 1 hr |

### Tier 3 — Backlog (Medium/Low)

| # | Finding | Section | Impact | Effort |
|---|---------|---------|--------|--------|
| 17 | Delete dead code (5 items) | 1.3, 1.4, 4.1 | Cleanliness | 30 min |
| 18 | Delete unused state fields (6 items) | 2.4 | Cleanliness | 30 min |
| 19 | Wire `techStackNotes` to architect | 2.4 | Better arch output | 30 min |
| 20 | Improve company search queries | 3.4 | Better enrichment | 30 min |
| 21 | Add iteration context tracking | 2.5, 2.6 | Transparency | 2 hr |
| 22 | Frontend code splitting | 4.4 | Faster initial load | 30 min |
| 23 | Fix TypeScript `any` casts | 4.5 | Type safety | 45 min |
| 24 | Extract duplicate components | 4.6 | DRY | 30 min |
| 25 | Resolve BDD vs unit test overlap | 5.1 | Maintenance | 2 hr |
| 26 | Session store cleanup TTL | 3.6 | Memory leak | 1 hr |
| 27 | Duplicate IT spend ratio logic | 3.3 | DRY | 15 min |
| 28 | Extract string constants | 1.8 | Readability | 30 min |
| 29 | Add accessibility fixes | 4.7 | A11y compliance | 1 hr |
| 30 | Add frontend tests | 4.8 | Coverage | 4 hr |
| 31 | Add auto-scaling rules | 6.4 | Production readiness | 1 hr |
| 32 | Update README | 6.6 | Documentation | 1 hr |

---

## 8. Implementation Plan

### Phase 1: Data Integrity & Prompt Quality (Week 1)
Focus: Prevent bad data from flowing through the pipeline

- [ ] Add Pydantic validators for `employeeCount`, `annualRevenue`, `itSpendRatio`
- [ ] Fix `SharedAssumptions` silent rejection → log warning + raise error
- [ ] Validate LLM company profiles against Pydantic schema
- [ ] Unify BV agent source labeling instructions
- [ ] Remove financial data from Architect prompt context
- [ ] Narrow `except Exception` to specific types across all agents
- [ ] Pass brainstorming scenarios to Cost Agent
- [ ] Preserve `state.architecture` on iteration re-runs

### Phase 2: Performance & Code Quality (Week 2)
Focus: Speed up pipeline, reduce duplication

- [ ] Extract `parse_llm_json()` utility (replaces 8 duplicate patterns)
- [ ] Parallelize BV Phase 2 + Architect after assumptions
- [ ] Parallelize pricing API fallback queries
- [ ] Convert PPTX generation to async subprocess
- [ ] Delete all dead code (functions, fields, constants, CSS vars)
- [ ] Extract duplicate frontend components (Tag, EMOJIS)
- [ ] Add `APICache` to frontend
- [ ] Add `AbortController` to streaming fetch

### Phase 3: Testing & Robustness (Week 3)
Focus: Catch regressions, fill coverage gaps

- [ ] Add error path tests for BV, Architect, Cost agents
- [ ] Add E2E pipeline integration test
- [ ] Resolve BDD vs unit test duplication
- [ ] Add `canned_brainstorming` fixture
- [ ] Remove unused `async_client` fixture
- [ ] Strengthen weak test assertions
- [ ] Add missing estimated prices for 8 Azure services

### Phase 4: Production Hardening (Week 4)
Focus: Security, monitoring, scalability

- [ ] Fix CORS to explicit methods/headers
- [ ] Add auto-scaling rules to Container Apps
- [ ] Add health check probes in Bicep
- [ ] Add session store TTL cleanup
- [ ] Add iteration context + assumption delta tracking
- [ ] Wire `techStackNotes` to architect
- [ ] Improve company search queries
- [ ] Frontend code splitting + accessibility fixes
- [ ] Update README

---

## Metrics

| Metric | Current | After Phase 1 | After All Phases |
|--------|---------|---------------|-----------------|
| Dead code items | ~15 | ~15 | 0 |
| Duplicate patterns | 8+ | 8+ | 0 |
| Prompt contradictions | 2 | 0 | 0 |
| Unvalidated inputs | 4 critical | 0 | 0 |
| Pipeline latency | ~45-60s | ~45-60s | ~25-40s |
| Test coverage (error paths) | ~40% | ~40% | ~85% |
| Frontend `any` casts | 12 | 12 | 0 |
