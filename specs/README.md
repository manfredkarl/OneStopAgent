# Financial Agent Pipeline — FRD Index

Feature Requirement Documents for hardening the Cost → Business Value → ROI
agent pipeline. Derived from the audit in `AGENT_ISSUES.md` (23 issues +
5 cross-agent disconnects) and the fix guide in `AGENT_FIXES.md`.

## FRDs

| ID | Feature | Fixes | Priority | Dependencies |
|----|---------|-------|----------|--------------|
| [FRD-001](frd-001-shared-assumptions.md) | Typed Shared Assumptions | A, B | P0 | — |
| [FRD-002](frd-002-roi-formula.md) | ROI Formula Accuracy | C+V, D | P0 | FRD-001, FRD-005 |
| [FRD-003](frd-003-bv-verification.md) | Business Value Verification | E, F, R, S | P1 | FRD-001 |
| [FRD-004](frd-004-cross-agent-reconciliation.md) | Cross-Agent Reconciliation | G, H | P1 | FRD-001, FRD-003 |
| [FRD-005](frd-005-future-state-cost-model.md) | Future-State Cost Model | I | P1 | FRD-003 (Fix E) |
| [FRD-006](frd-006-pricing-accuracy.md) | Azure Pricing Accuracy | J, K, L, M, N | P2 | — |
| [FRD-007](frd-007-roi-model-refinements.md) | ROI Model Refinements | O, P, Q | P2 | — |
| [FRD-008](frd-008-error-handling.md) | Error Handling & Transparency | T, U | P2 | — |

## Implementation Order

```
Phase 1:  FRD-001 (foundation — all others depend on typed schema)
Phase 2:  FRD-003 (structured drivers needed by FRD-005 and FRD-002)
Phase 3:  FRD-005 (future-state cost model needed by FRD-002)
Phase 4:  FRD-002 (ROI formula — consumes future_annual from FRD-005)
Phase 5:  FRD-004 (reconciliation — consumes outputs of FRD-002 + FRD-003)
Phase 6:  FRD-006, FRD-007, FRD-008 (independent — parallelizable)
```

> **Priority vs. Implementation Order:** Priority (P0/P1/P2) reflects
> business impact. Implementation order reflects technical dependencies.
> FRD-002 is P0 (highest business impact) but implemented in Phase 4
> because it depends on FRD-005 (P1) and FRD-003 (P1).

## Coverage Matrix

| Issue # | Description | FRD | Fix |
|---------|-------------|-----|-----|
| 1 | ROI excludes implementation costs | 002 | C+V |
| 2 | Payback ignores implementation | 002 | C+V |
| 3 | No LLM value range validation | 003 | F |
| 4 | Arbitrary estimated baseline | 002 | D |
| 5 | Fragile regex for AI coverage | 003 | E |
| 6 | Fuzzy key resolution cascade | 001 | A |
| 7 | Schema-free shared_assumptions | 001 | A |
| 8 | Hardcoded future-state reductions | 005 | I |
| 9 | Sequential pricing API calls | 006 | K |
| 10 | Median SKU fallback | 006 | J |
| 11 | Fixed 3% risk reduction | 007 | O |
| 12 | Forced 3 drivers | 003 | R |
| 13 | Hardcoded AI pricing | 006 | N |
| 14 | Unit detection fallthrough | 006 | L |
| 15 | Fixed 40% multi-region overhead | 006 | M |
| 16 | Silent search failure | 003 | S |
| 17 | Fixed adoption ramp | 007 | P |
| 18 | productivityGains always 0 | 007 | Q |
| 19 | No pricing cache | 006 | K |
| 20 | Silent JSON parse fallbacks | 008 | T |
| 21 | Hidden savings cap | 004 | H |
| 22 | Stringly-typed assumptions | 001 | A |
| 23 | Broad exception swallowing | 008 | U |
| D1 | Cost ignores baseline | 004 | G |
| D2 | BV unverified math | 003 | F |
| D3 | ROI re-derives baseline | 001 | A |
| D4 | Uncoordinated question sets | 001 | B |
| D5 | No value-to-cost validation | 004 | H |
| NEW | ROI denominator excludes carried opex | 002 | V |

## Source Documents

- [AGENT_ISSUES.md](../AGENT_ISSUES.md) — Full audit (23 issues + 5 disconnects)
- [AGENT_FIXES.md](../AGENT_FIXES.md) — Consolidated fix guide (A–V)

## Frontend Impact Summary

All FRDs that modify the `ROIDashboard.tsx` `BusinessCase` TypeScript
interface or add new dashboard fields, consolidated here to coordinate
frontend changes:

| FRD | Change | File | Field(s) |
|-----|--------|------|----------|
| FRD-002 | Add fields | `ROIDashboard.tsx` | `roiRunRate`, `futureAnnualOpex`, `costComparisonAvailable`, `costEstimated`, `warning` |
| FRD-004 | Add fields | `ROIDashboard.tsx` | `plausibilityWarnings: string[]`, `savingsCapped: boolean`, `confidenceLevel` (already exists — now set by reconciliation) |
| FRD-007 | Remove field | `ROIDashboard.tsx` | Remove `productivityGains` from `BusinessCase.valueBridge` |
| FRD-008 | Add field | `ROIDashboard.tsx` | `error_type: "json_parse" \| "timeout" \| "api_error" \| "unknown"` |

**Updated `BusinessCase` interface** (target state after all FRDs):

```typescript
interface BusinessCase {
  currentState: { totalAnnual: number; breakdown: { category: string; description: string; annual: number }[] };
  futureState: { azurePlatformAnnual: number; implementationCost: number; changeCost: number; futureAnnualOpex: number };
  valueBridge: { hardSavings: number; revenueUplift: number; riskReduction: number; totalAnnualValue: number };
  investment: { year1Total: number; year2Total: number; year1NetValue: number; year2NetValue: number };
  sensitivity: { adoption: string; annualValue: number; roiYear1: number; roiRunRate: number; paybackMonths: number | null }[];
  decisionDrivers: string[];
}

interface ROIDashboard {
  // ... existing fields ...
  roiRunRate: number;
  costComparisonAvailable: boolean;
  costEstimated: boolean;
  plausibilityWarnings: string[];
  savingsCapped: boolean;
  confidenceLevel: "high" | "moderate" | "low";
  warning?: string;
  error_type?: "json_parse" | "timeout" | "api_error" | "unknown";
}
```
