# PRD: Agent Pipeline Improvements — 20 Enhancements

**Status**: Draft
**Priority**: P0 (5 Critical), P1 (10 Medium-High), P2 (5 Medium)
**Date**: 2026-04-03
**Source**: Deep review of all 7 agents + orchestrator

---

## Executive Summary

After stabilizing the financial math (8 FRDs, 5 guardrails, 19 audit fixes),
this PRD addresses the next tier: **output quality, speed, and seller UX**.
20 improvements organized in 4 categories — Quick Wins (ship in days),
Quality improvements (weeks), Architecture changes (sprints), and
UX enhancements (continuous).

---

## Category 1: Quick Wins (Low effort, immediate value)

### QW-1: Raise Consumption Defaults

**Agent**: Cost Agent
**Impact**: HIGH — current defaults produce 30-50% underestimates
**Effort**: Low (change constants)

**Problem**: Default assumptions are wildly low for enterprise:
- Storage: 100GB (enterprise needs 500GB-5TB)
- Azure OpenAI: 50K requests/mo (real apps: 150K-500K)
- Cosmos DB: 1,000 RU/s (production: 5K-100K)
- App Service: single instance (HA needs ≥2)

**Fix**: Replace fixed defaults with tiered defaults based on user count:
```
< 500 users:  storage 100GB, OpenAI 50K, Cosmos 1K RU/s
500-5000:     storage 500GB, OpenAI 150K, Cosmos 5K RU/s
> 5000:       storage 2TB, OpenAI 500K, Cosmos 20K RU/s
```

**Files**: `cost_agent.py` (5 constants)
**AC**: Azure cost estimate for 10K user scenario increases by ≥30%

---

### QW-2: Security/Compliance Intent Keywords

**Agent**: PM Agent
**Impact**: HIGH — sellers can't refine for security without full re-run
**Effort**: Low (add to ITERATION_MAPPING)

**Problem**: "Add GDPR compliance" or "make it more secure" falls through
to default full pipeline re-run. Should only trigger Architect + Cost.

**Fix**: Add to `ITERATION_MAPPING`:
```python
"secure": ["architect", "cost"],
"security": ["architect", "cost"],
"gdpr": ["architect", "cost"],
"pci": ["architect", "cost"],
"soc2": ["architect", "cost"],
"hipaa": ["architect", "cost"],
"encryption": ["architect", "cost"],
"zero trust": ["architect", "cost"],
```

**Files**: `pm_agent.py` (8 lines)
**AC**: "Add GDPR compliance" re-runs only architect + cost, not BV/ROI

---

### QW-3: Add Missing ESTIMATED_PRICES

**Agent**: Cost Agent / Pricing Service
**Impact**: MEDIUM — 10+ services return "unavailable", producing $0 cost
**Effort**: Low (add dict entries)

**Problem**: These services have no pricing data:
- Azure SQL Database
- Azure Database for MySQL/PostgreSQL
- Key Vault
- Application Insights
- Azure DevOps
- Power Automate / Power Apps
- Azure Spring Cloud
- Synapse Analytics

**Fix**: Add conservative per-hour or per-month estimates with documented
sources for each.

**Files**: `pricing.py` (~50 lines of dict entries)
**AC**: Zero "unavailable" pricing sources for common Azure services

---

### QW-4: Mermaid Diagram Connection Labels

**Agent**: Architect Agent
**Impact**: MEDIUM — diagrams lack data flow context
**Effort**: Low (prompt change)

**Problem**: Mermaid arrows show connections but not what flows through them.
`A --> B` doesn't tell you if it's REST, events, or queue messages.

**Fix**: Update architect prompt to require connection labels:
```
A -->|"REST API"| B
C -->|"Event Stream"| D
E -->|"Queue Messages"| F
```

**Files**: `architect_agent.py` (prompt update)
**AC**: Mermaid diagrams show connection type labels on arrows

---

### QW-5: Improved Slide Flow (12 slides)

**Agent**: Presentation Agent
**Impact**: MEDIUM — better narrative flow for customer meetings
**Effort**: Low (prompt update)

**Problem**: Current 11-slide structure puts "Use Cases" before value
articulation, has no "Why Azure?" slide, no implementation roadmap.

**Fix**: Restructure to 12 slides:
1. Title (dark)
2. Why Now? — urgency, market shift
3. Proposed Solution — architecture visual
4. Business Impact — ROI, value drivers (big numbers)
5. Use Cases — scenario cards
6. 3-Year Total Cost — monthly, annual, confidence
7. Implementation Roadmap — phases, timeline
8. Why Azure? — capabilities, support, roadmap
9. Next Steps (dark)
10. Thank You (dark)
11. Appendix: Architecture Details
12. Appendix: Azure Services & Costs

**Files**: `presentation_agent.py` (prompt update)
**AC**: Generated decks follow the 12-slide structure

---

## Category 2: Quality Improvements (Medium effort)

### QI-1: Verify LLM Arithmetic in BV Drivers

**Agent**: Business Value Agent
**Impact**: HIGH — catches hallucinated dollar values
**Effort**: Medium

**Problem**: The prompt says "COMPUTE, show the math" but there's no
post-validation that the LLM actually did correct arithmetic. A driver
claiming "$500K savings from 100 engineers × $50/hr × 10% savings"
should be verified: 100 × 50 × 2080 × 0.10 = $1,040,000 ≠ $500K.

**Fix**: Add `_verify_arithmetic()` method:
1. Parse the description for numbers and operators
2. Extract claimed `impact_pct_low/high` and `annual_impact_range`
3. Re-compute using shared assumptions (employees, rate, spend)
4. If divergence > 10%, flag the driver and log warning
5. Optionally re-compute and override the LLM's number

**Files**: `business_value_agent.py` (~40 lines)
**AC**: Drivers with >10% arithmetic error are flagged or corrected

---

### QI-2: Architecture-Scoped BV Drivers

**Agent**: Business Value Agent
**Impact**: HIGH — drivers become specific to the actual solution
**Effort**: Medium

**Problem**: BV generates generic drivers ("engineering productivity")
without referencing actual architecture decisions. If architecture
includes serverless, drivers should reference function cost savings.
If it includes managed databases, should mention DBA headcount reduction.

**Fix**: Parse `state.architecture["components"]` and create a
component-to-driver mapping:
```python
COMPONENT_DRIVER_HINTS = {
    "serverless": "Operational efficiency from serverless (no infra management)",
    "managed database": "DBA headcount reduction with managed services",
    "CDN": "Reduced latency → higher conversion rates",
    "AI Search": "Faster information retrieval → productivity gains",
}
```
Inject matching hints into the BV Phase 2 prompt.

**Files**: `business_value_agent.py` (~30 lines + prompt update)
**AC**: At least 1 driver per run references a specific architecture component

---

### QI-3: Per-Service HA Cost Multipliers

**Agent**: Cost Agent
**Impact**: HIGH — HA deployments 30-50% more accurate
**Effort**: Medium

**Problem**: Current flat 30-50% overhead for all multi-region scenarios.
Reality: App Service needs full duplicate (2x), Cosmos DB replication is
cheaper (0.75x), Storage geo-redundancy is +20%, Service Bus Premium
already includes HA.

**Fix**: Replace flat multiplier with per-service dict:
```python
HA_COST_MULTIPLIERS = {
    "Azure App Service": {"active-active": 2.0, "active-passive": 1.5},
    "Azure Cosmos DB": {"active-active": 0.75, "active-passive": 0.50},
    "Azure Blob Storage": {"geo-redundant": 1.20},
    "Azure Service Bus": {"premium": 1.0},  # already HA
    "default": {"active-active": 0.50, "active-passive": 0.30},
}
```
Add data transfer cost estimation for cross-region replication.

**Files**: `cost_agent.py` (~40 lines)
**AC**: Multi-region App Service costs 2x, not 1.4x

---

### QI-4: ROI Tornado Sensitivity

**Agent**: ROI Agent
**Impact**: MEDIUM — sellers can identify which assumption matters most
**Effort**: Low-Medium

**Problem**: Current sensitivity only varies adoption (50/75/100%).
Doesn't show which driver has the most impact on ROI, or what
happens if costs increase 20%.

**Fix**: Add tornado sensitivity method:
1. For each driver, vary ±20% while holding others constant
2. Compute resulting ROI for each
3. Rank by range (biggest swing = most important lever)
4. Add cost variance scenarios (+10%, +20%)

Output:
```json
"tornado": [
  {"driver": "Labor savings", "lowROI": 150, "highROI": 280, "range": 130},
  {"driver": "Revenue uplift", "lowROI": 180, "highROI": 250, "range": 70},
]
```

**Files**: `roi_agent.py` (~30 lines), `ROIDashboard.tsx` (rendering)
**AC**: Dashboard shows tornado chart ranking drivers by impact

---

### QI-5: Confidence as Scored Object

**Agent**: Business Value Agent
**Impact**: MEDIUM — "moderate" is meaningless; 72/100 is actionable
**Effort**: Medium

**Problem**: Confidence is a string ("high"/"moderate"/"low"). CFOs don't
know if "moderate" means ±20% or ±80%.

**Fix**: Return confidence as scored object:
```json
"confidence": {
  "overall_score": 72,
  "driver_scores": [85, 65, 42],
  "methodology": "2 of 3 drivers computed from user data; 1 estimated",
  "recommendation": "Strong case — validate revenue driver with customer"
}
```

**Files**: `business_value_agent.py` (~30 lines), `ROIDashboard.tsx`
**AC**: Dashboard shows confidence score, not just badge color

---

### QI-6: Architect NFR Layers (Security, Compliance, DR)

**Agent**: Architect Agent
**Impact**: MEDIUM-HIGH — architectures are production-incomplete
**Effort**: Medium

**Problem**: Architectures omit security boundaries, compliance zones,
disaster recovery patterns, and monitoring. These are critical for
regulated industries (healthcare, finance).

**Fix**: Add mandatory NFR section to architecture output:
```json
"nfr": {
  "security": {"zones": [...], "identity": "...", "encryption": "..."},
  "compliance": {"frameworks": [...], "controls": [...]},
  "ha": {"drStrategy": "...", "rpo": "...", "rto": "..."},
  "monitoring": {"observability": "...", "alerting": "..."}
}
```
Update prompt to require these when compliance/security keywords detected.

**Files**: `architect_agent.py` (prompt + post-processing)
**AC**: Architecture includes security zones when compliance is mentioned

---

### QI-7: Multi-Query MCP Search

**Agent**: Architect Agent
**Impact**: MEDIUM-HIGH — better reference pattern matching
**Effort**: Medium

**Problem**: Single MCP query concatenates everything into one search.
"Build AI system Healthcare HIPAA 10K users" is too broad.

**Fix**: Split into targeted queries:
1. Functional pattern: "AI document processing healthcare"
2. Scale pattern: "high-scale real-time 10K concurrent"
3. Compliance pattern: "HIPAA healthcare Azure"

Merge results, deduplicate, rank by relevance.

**Files**: `architect_agent.py` (~20 lines)
**AC**: MCP returns more relevant patterns for complex use cases

---

## Category 3: Architecture Changes (High effort, transformative)

### AC-1: Parallel BV + Architect Execution

**Agent**: Orchestrator / Workflow
**Impact**: CRITICAL — saves 90s per run (30-50% faster)
**Effort**: Medium-High

**Problem**: BV and Architect run sequentially but have NO dependencies.
Both read from `state.brainstorming` and `state.shared_assumptions`
(inputs only). They write to different state fields.

**Fix**: Refactor workflow graph:
```
Current:  BV → Architect → Cost → ROI → Presentation (sequential)
New:      {BV, Architect} → Cost → ROI → Presentation (parallel first two)
```

Use MAF's fork/join or Python `asyncio.gather()`:
```python
await asyncio.gather(
    bv_executor.run(state),
    architect_executor.run(state),
)
# Both write to separate state dicts — no conflict
```

**Files**: `workflow.py` (graph refactor), `maf_orchestrator.py` (event handling)
**AC**: Pipeline time reduced by ≥60s for typical runs

---

### AC-2: Template-Based Presentation

**Agent**: Presentation Agent
**Impact**: HIGH — 95% consistency vs 40% with full LLM generation
**Effort**: High

**Problem**: Full LLM generation of PptxGenJS scripts produces inconsistent
layouts, fonts, colors, and text overflow between runs. Hard to debug,
impossible to brand-control.

**Fix**: Hybrid approach — template defines structure, LLM fills content:
1. Python template engine defines slide geometry (x, y, w, h), colors, fonts
2. LLM generates only JSON with text content (taglines, descriptions, labels)
3. Python merges template + JSON → PptxGenJS script

Benefits:
- Geometry is deterministic (no text overflow)
- Colors are brand-guaranteed (Microsoft Fluent palette)
- LLM task is simpler (just text, not code)
- Debug is easy (template bug vs LLM bug)

**Files**: New `presentation_templates.py`, refactored `presentation_agent.py`
**AC**: Two consecutive runs produce visually identical layouts (different text)

---

### AC-3: NPV / IRR / Cumulative Cash Flow

**Agent**: ROI Agent
**Impact**: HIGH — CFOs evaluate using these metrics, not just ROI%
**Effort**: Medium

**Problem**: ROI% tells you return per dollar invested. But CFOs need:
- NPV at corporate discount rate (8-12%): "Is this worth more than alternatives?"
- IRR: "What's the effective interest rate of this investment?"
- Cumulative cash flow: "When does total value exceed total cost?"

**Fix**: Add to ROI agent:
```python
def _compute_npv(cash_flows: list[float], discount_rate: float = 0.10) -> float:
    return sum(cf / (1 + discount_rate) ** yr for yr, cf in enumerate(cash_flows))

def _compute_irr(cash_flows: list[float]) -> float:
    # Newton-Raphson method
    ...

def _compute_cumulative_breakeven(monthly_value, monthly_cost, setup_cost) -> int:
    # Month where cumulative net turns positive
    ...
```

Add to dashboard: NPV, IRR, monthly cumulative chart with breakeven line.

**Files**: `roi_agent.py` (~60 lines), `ROIDashboard.tsx` (new chart)
**AC**: Dashboard shows NPV, IRR, and cumulative breakeven month

---

### AC-4: Granular Agent Retry

**Agent**: Orchestrator
**Impact**: MEDIUM-HIGH — eliminates 5-10 min re-runs for single failures
**Effort**: Medium

**Problem**: If Cost agent fails (LLM timeout, pricing API down), the
entire pipeline must restart. Architect and BV results are lost.

**Fix**: Add retry-specific workflow:
1. Each executor catches exceptions and retries up to 2x with backoff
2. If still fails, marks step failed but continues pipeline (ROI uses fallback)
3. User can say "retry cost" → orchestrator re-runs only cost + downstream

**Files**: `workflow.py` (retry logic), `maf_orchestrator.py` (selective re-run)
**AC**: "retry cost" re-runs cost+ROI in <2min, not full 10min pipeline

---

### AC-5: Semantic Iteration ("make it cheaper")

**Agent**: PM Agent / Orchestrator
**Impact**: MEDIUM — natural language iteration without specifying agents
**Effort**: Medium

**Problem**: Users think in business terms ("make it cheaper", "add HA",
"support 1M users") but iteration requires knowing which agents to re-run.

**Fix**: Map business intents to agent combinations:
```python
SEMANTIC_ITERATIONS = {
    "cheaper|budget|cost": ["cost", "roi"],
    "faster|performance|latency": ["architect", "cost", "roi"],
    "scale|users|concurrent": ["architect", "cost", "roi"],
    "secure|compliance|gdpr|hipaa": ["architect", "cost"],
    "simpler|reduce|fewer": ["architect", "cost", "roi"],
}
```

**Files**: `pm_agent.py` (intent mapping), `maf_orchestrator.py` (selective re-run)
**AC**: "Make it cheaper" re-runs cost+ROI only, preserving architecture

---

## Category 4: UX Enhancements

### UX-1: Decision-Driven Approval Summaries

**Agent**: PM Agent
**Impact**: MEDIUM — helps sellers make informed approve/refine decisions
**Effort**: Medium

**Problem**: Approval summaries show metrics but not decision context.
Sellers don't know "Why this service over alternatives?" or "What are
the scaling limits?"

**Fix**: Per-step decision guidance:
- Architect: "Risk summary: 2 single-region services. Consider HA?"
- Cost: "Top driver: AI Search ($981/mo, 40% of total). Alternatives?"
- BV: "Weakest driver: revenue uplift (42 confidence). Get customer data?"
- ROI: "Break-even in Month 14. What would accelerate adoption?"

**Files**: `pm_agent.py` (~40 lines in `approval_summary`)
**AC**: Each approval step includes 1-2 decision questions

---

### UX-2: Cost Optimization Insights

**Agent**: Cost Agent
**Impact**: MEDIUM — sellers can discuss savings strategies
**Effort**: Medium

**Problem**: Cost summary shows totals but no optimization guidance.
Sellers can't say "Here's how to save 30%."

**Fix**: Add insights to cost output:
```json
"insights": {
  "top_3_drivers": [...],
  "reservation_savings": "$2,400/yr with 1-yr reserved",
  "cost_per_user": "$2.50/user/mo",
  "optimization_tips": ["Consider serverless for batch workloads"]
}
```

**Files**: `cost_agent.py` (~50 lines)
**AC**: Cost output includes top 3 drivers and reservation savings estimate

---

### UX-3: ROI Conversation Starters

**Agent**: ROI Agent
**Impact**: MEDIUM — helps sellers use the dashboard in meetings
**Effort**: Low

**Problem**: Dashboard has numbers but sellers don't know what to discuss.

**Fix**: Add contextual conversation starters:
```json
"conversationStarters": [
  "Your biggest driver is error reduction (40% of value). Where do errors cost most?",
  "Year 1 adoption is 50%. What training would get you to 70%?",
  "Implementation cost is $X — how accurate is that?"
]
```

**Files**: `roi_agent.py` (~20 lines)
**AC**: Dashboard includes 2-3 conversation starters

---

### UX-4: BV Presentation Narrative

**Agent**: Business Value Agent
**Impact**: MEDIUM — transforms raw data into customer story
**Effort**: Medium

**Problem**: BV output is technical (driver objects). Sellers need a
narrative: "Here's what we assume → here's how Azure fixes it → here's
the financial proof."

**Fix**: Add `narrative_summary` field (~500 chars) tying assumptions
to drivers to impact. Add `presentation_order` sorting drivers by
relevance and confidence.

**Files**: `business_value_agent.py` (~40 lines)
**AC**: BV output includes a customer-ready narrative paragraph

---

## Implementation Order

```
Week 1 — Quick Wins (ship immediately):
  QW-1: Raise consumption defaults
  QW-2: Security intent keywords
  QW-3: Missing ESTIMATED_PRICES
  QW-4: Mermaid connection labels
  QW-5: 12-slide flow

Week 2-3 — Quality (parallel):
  QI-1: Verify LLM arithmetic
  QI-2: Architecture-scoped drivers
  QI-3: Per-service HA multipliers
  QI-4: Tornado sensitivity

Week 3-4 — Quality continued:
  QI-5: Confidence scoring
  QI-6: NFR layers
  QI-7: Multi-query MCP

Week 4-6 — Architecture:
  AC-1: Parallel BV + Architect
  AC-2: Template-based presentation
  AC-3: NPV/IRR/cash flow
  AC-4: Granular agent retry
  AC-5: Semantic iteration

Ongoing — UX:
  UX-1: Decision summaries
  UX-2: Cost insights
  UX-3: Conversation starters
  UX-4: BV narrative
```

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Pipeline time | ~8 min | ~5 min (parallel agents) |
| Cost estimate accuracy | ±30-50% | ±15-20% |
| Presentation consistency | ~40% | ~90% (templates) |
| BV arithmetic accuracy | unchecked | >90% verified |
| Seller iteration time | 10 min (full re-run) | 2 min (targeted) |
| Services with pricing | ~80% | ~95% |
