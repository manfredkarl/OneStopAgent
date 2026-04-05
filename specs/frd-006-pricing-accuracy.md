# FRD-006: Azure Pricing Accuracy

| Fix | Status |
|-----|--------|
| FR-006-001: Tier-proximity scoring | ✅ Implemented |
| FR-006-002: Parallel pricing | ✅ Implemented |
| FR-006-003: Session cache | 🚧 Partial |
| FR-006-004: Unit detection whitelist | ❌ Not Started |
| FR-006-005: HA-pattern overhead | ✅ Implemented |
| FR-006-006: Configurable AI pricing | ✅ Implemented |

**Feature ID**: F-006
**Status**: Draft
**Priority**: P2
**Last Updated**: 2026-04-02

## Description

The Cost agent queries the Azure Retail Prices API to price each service in
the architecture. Five accuracy and performance problems degrade the cost
estimate:

1. **SKU fallback returns median price** — when the requested SKU isn't found,
   `_find_best_match` returns the median-priced item, which can be 10–50× off
   (e.g., B1 request returns P3v3).
2. **Sequential API calls** — each service is priced in series with a 15s
   timeout; 10 services = 150s wall time.
3. **Unit detection fallback** — unrecognized pricing units default to hourly
   (×730), wildly overcharging per-GB-day or per-transaction items.
4. **Multi-region overhead** — fixed 40% regardless of HA pattern.
5. **AI model pricing** — hardcoded `$0.006/request` for GPT-4o with no
   staleness detection.

## User Stories

### US-006-001: Tier-Proximity SKU Matching

**As a** cost estimator
**I want** SKU fallback to return the nearest tier, not the median price
**So that** a B1 request returns B2 or B1ms pricing, not P3v3.

**Acceptance Criteria:**
- GIVEN requested SKU "B1" and available SKUs [Free, B2, S1, P1, P3v3]
  WHEN fallback runs THEN B2 is returned (nearest tier)
- GIVEN no non-zero-priced items WHEN fallback runs THEN None is returned
- GIVEN "low priority" or "spot" SKUs in the list WHEN fallback filters
  THEN they are excluded

### US-006-002: Parallel Pricing with Cache

**As a** user waiting for cost estimates
**I want** pricing calls to run in parallel with a session cache
**So that** 10 services complete in ~15s instead of ~150s.

**Acceptance Criteria:**
- GIVEN 10 services to price WHEN pricing runs THEN max 5 concurrent requests
  (ThreadPoolExecutor)
- GIVEN two services with identical (serviceName, sku, region) WHEN pricing
  runs THEN only one API call is made (cache hit)
- GIVEN API timeout on one service WHEN pricing runs THEN other services
  complete independently

### US-006-003: Safe Unit Detection

**As a** cost model
**I want** unknown pricing units to default to monthly (not hourly)
**So that** a per-GB-day price isn't multiplied by 730.

**Acceptance Criteria:**
- GIVEN unit "1 hour" WHEN monthly cost is calculated THEN multiply by 730
- GIVEN unit "1/day" WHEN monthly cost is calculated THEN multiply by 30
- GIVEN unit "per 10K transactions" WHEN monthly cost is calculated THEN log
  warning and treat as monthly

### US-006-004: HA-Pattern Multi-Region Overhead

**As a** architect designing active-passive HA
**I want** the multi-region overhead to be 30%, not 50%
**So that** my cost estimate reflects the actual replication pattern.

**Acceptance Criteria:**
- GIVEN `haPattern = "active-active"` WHEN overhead is calculated THEN 50%
- GIVEN `haPattern = "active-passive"` WHEN overhead is calculated THEN 30%
- GIVEN `haPattern` not specified WHEN overhead is calculated THEN 40% default

### US-006-005: Configurable AI Pricing with Staleness Warning

**As a** pricing module
**I want** AI model costs computed from a versioned config (not hardcoded)
**So that** pricing updates don't require code changes.

**Acceptance Criteria:**
- GIVEN `AI_MODEL_PRICING["gpt-4o"]` last updated 100 days ago WHEN
  `per_request_cost()` is called THEN a warning is logged
- GIVEN token pricing `input: $2.50/1M, output: $10.00/1M` and average
  `800 input + 400 output tokens` WHEN computed THEN cost = $0.006/request

## Functional Requirements

### FR-006-001: Tier-Proximity Scoring (Fix J)

Replace median fallback in `_find_best_match()` with tier-proximity scoring.

- Input: requested SKU, list of pricing items
- Processing: define `TIER_ORDER`, compute `_tier_distance()`, sort by distance,
  return closest
- Output: best-match pricing item
- Error handling: if no non-zero items, return None

> **Note:** `TIER_ORDER` targets PaaS tiers (Free, Shared, Basic, Standard,
> Premium, Isolated). VM-family SKUs (D, E, F, L, M, N series) use numeric
> size naming (e.g., "D4s_v3") and are not represented in the tier hierarchy.
> For VM SKUs, `_tier_distance` falls back to default index 5 (Standard
> equivalent), which provides reasonable proximity ordering by price for
> most workloads. A future enhancement could add VM-family-aware matching.

### FR-006-002: Parallel Pricing (Fix K)

Replace sequential loop in `_price_selections()` with `ThreadPoolExecutor(max_workers=5)`.

- Input: selections list
- Processing: submit all to pool, collect via `as_completed`, use `price_cache` dict
- Output: priced items list
- Error handling: per-future exception handling; failed items logged, not fatal

### FR-006-003: Session Cache (Fix K)

Cache key = `(serviceName, sku, region)`. Dict-based, per-invocation lifetime.

### FR-006-004: Unit Detection Whitelist (Fix L)

Define `HOURLY_UNITS`, `MONTHLY_UNITS`, `DAILY_UNITS` sets. Unknown units
log a warning and are treated as monthly.

- Input: `unitOfMeasure` from API response
- Processing: match against whitelists; log warning for unknowns
- Output: monthly cost multiplier
- Error handling: unknown → monthly (×1)

### FR-006-005: HA-Pattern Overhead (Fix M)

Add `MULTI_REGION_OVERHEAD` dict. LLM service mapping includes `haPattern`
field. Select overhead multiplier from dict.

- Input: `haPattern` from selections, `items` cost list
- Processing: look up overhead %, apply to sum of item costs
- Output: overhead amount
- Error handling: missing `haPattern` → 40% default

### FR-006-006: Configurable AI Pricing (Fix N)

Create `AI_MODEL_PRICING` dict in `pricing.py` with per-model token pricing,
average token counts, and `last_updated` date. Implement `per_request_cost()`.

- Input: model name (default "gpt-4o")
- Processing: compute cost from token pricing, check staleness (>90 days → warn)
- Output: per-request cost float
- Error handling: unknown model → KeyError (caller must handle)

## Non-Functional Requirements

### NFR-006-001: API Concurrency Limit

Max 5 concurrent requests to Azure Retail Prices API to avoid rate limiting.

### NFR-006-002: Cache Scope

Price cache is per-invocation (not persistent). Each `run()` call starts fresh.

## Dependencies

| Dependency | Type | Direction | Description |
|------------|------|-----------|-------------|
| Azure Retail Prices API | External | Upstream | pricing data source |
| `cost_agent.py` | Internal | Self | All fixes modify cost agent or pricing module |
| FRD-004 | Feature | Downstream | Cost plausibility check consumes cost output |

---

## Current Implementation (Brownfield Extension)

### Files Involved

| File Path | Role | Lines |
|-----------|------|-------|
| `src/python-api/services/pricing.py` | `query_azure_pricing_sync()`, `_find_best_match()`, `ESTIMATED_PRICES` | full file (~220 lines) |
| `src/python-api/agents/cost_agent.py` | `_price_selections()`, `_calculate_monthly()` | ~200–420 |

### Architecture Pattern

Synchronous HTTP calls to Azure Retail Prices API via `httpx`. Results
processed through `_find_best_match()` with a 3-step fallback: exact SKU →
partial name → median price. Cost agent calls pricing module sequentially
for each service.

### Known Limitations

- `_find_best_match()` step 3 returns median item — can be wildly inaccurate
- Sequential pricing: `for sel in selections: query_azure_pricing_sync(...)` —
  O(n) wall time, 15s timeout each
- No caching: identical (service, SKU, region) queried multiple times
- Unknown `unitOfMeasure` defaults to hourly (×730) — can overcharge 730×
- Multi-region overhead hardcoded at 40% for all patterns
- `ESTIMATED_PRICES` has `"Azure OpenAI Service": 0.006` — hardcoded, no
  staleness warning, based on old token pricing

### Test Coverage

| Test Type | Files | Assertions | Coverage |
|-----------|-------|------------|----------|
| Unit | — | — | 0% |
| Integration | — | — | 0% |
| E2E | — | — | 0% |

**Untested paths**: All pricing logic, SKU matching, unit conversion.
