# FRD-BUSINESS-VALUE: Business Value Assessment

**Feature ID**: US-6
**Status**: Draft
**Priority**: P1
**Last Updated**: 2025-07-15

---

## 1. Overview

The Business Value Assessment agent evaluates a proposed Azure solution against a structured set of value drivers and produces an executive-ready analysis of projected business impact. It synthesizes inputs from upstream agents — requirements, architecture decisions, selected Azure services, and cost estimates — to generate quantified impact projections, industry benchmark comparisons, and a concise executive summary.

This capability addresses a critical gap in the seller workflow: translating technical architecture into business language that resonates with customer executives and budget decision-makers. The agent does not guarantee outcomes; all quantified estimates are clearly labeled as projections based on industry benchmarks and comparable deployments.

**Traceability**: PRD US-6 — "As an Azure seller, I want an ROI and business impact analysis for the proposed solution, so that I can build a business case for the customer."

---

## 2. Value Driver Framework

### 2.1 Standard Drivers

The agent evaluates every solution against five standard value drivers. Each driver has a defined scope, typical metrics, and example quantification patterns.

| # | Driver | Description | Example Metrics |
|---|--------|-------------|-----------------|
| 1 | **Cost Savings** | Reduction in capital expenditure, operational expenditure, or total cost of ownership relative to current state or alternative approaches. | Infrastructure cost reduction %, labor hours saved per month, licensing cost delta, data-center decommission savings. |
| 2 | **Revenue Growth** | New or incremental revenue enabled by the solution — faster product launches, new digital channels, improved customer reach. | Projected incremental revenue %, new market addressable revenue, conversion rate improvement. |
| 3 | **Operational Efficiency** | Gains in throughput, automation, error reduction, or resource utilization that reduce waste or increase capacity without proportional cost increase. | Process cycle time reduction %, manual task elimination count, error rate reduction %, resource utilization improvement. |
| 4 | **Time-to-Market** | Acceleration of feature delivery, deployment frequency, or go-live timelines that provide competitive advantage. | Deployment frequency increase %, lead time reduction (days/weeks), release cycle compression ratio. |
| 5 | **Risk Reduction** | Mitigation of security, compliance, availability, or business-continuity risks through improved controls, redundancy, or governance. | RTO/RPO improvement, compliance gap closure count, security incident reduction %, disaster recovery coverage %. |

### 2.2 Custom Drivers

Beyond the five standard drivers, the agent may identify additional value drivers from the project context:

- **Context scanning**: The agent inspects the `ProjectContext.requirements` for keywords and themes that map to non-standard value categories (e.g., "sustainability", "employee experience", "data sovereignty").
- **Industry alignment**: If the customer's industry is identified, the agent cross-references the Benchmark Knowledge Base (§5) for industry-specific drivers not covered by the standard five.
- **Custom driver output**: Custom drivers use the same `ValueDriver` schema as standard drivers but include `isCustom: true` in the output object.
- **Limit**: A maximum of **3 custom drivers** may be added per assessment to maintain focus and readability.

---

## 3. Agent Input/Output Contract

### 3.1 Input — ProjectContext

The Business Value Agent receives a `ProjectContext` object assembled by the Project Manager Agent from upstream agent outputs.

```typescript
interface ProjectContext {
  /** Customer requirements gathered by Envisioning Agent */
  requirements: {
    industry?: string;
    companySize?: 'startup' | 'smb' | 'enterprise';
    currentState?: string;           // description of existing infrastructure/process
    painPoints?: string[];
    objectives?: string[];
  };

  /** Architecture produced by System Architect Agent */
  architecture: {
    diagramMermaid: string;
    components: string[];
    patterns: string[];              // e.g., ["microservices", "event-driven"]
  };

  /** Azure services selected by Azure Specialist Agent */
  services: {
    name: string;
    sku: string;
    region: string;
    purpose: string;
  }[];

  /** Cost breakdown from Cost Specialist Agent */
  costEstimate?: {
    monthlyCost: number;
    annualCost: number;
    currency: string;
    lineItems: {
      service: string;
      monthlyCost: number;
    }[];
  };
}
```

**Required fields**: `requirements`, `architecture`, `services`.
**Optional fields**: `costEstimate` (may be absent if Cost Specialist has not yet run; see §9 Edge Cases).

### 3.2 Output — ValueAssessment

```typescript
interface ValueAssessment {
  /** Evaluated value drivers with impact analysis */
  drivers: ValueDriver[];

  /** Executive-ready summary paragraph(s) */
  executiveSummary: string;

  /** Benchmark references supporting the assessment */
  benchmarks: BenchmarkReference[];

  /** ISO 8601 timestamp of assessment generation */
  generatedAt: string;

  /** Overall confidence level for the assessment */
  overallConfidence: 'low' | 'moderate' | 'high';
}

interface ValueDriver {
  /** Driver name — one of the standard five or a custom driver label */
  name: string;

  /** Qualitative impact description (2-4 sentences) */
  impact: string;

  /**
   * Quantified projection when data supports it.
   * MUST include the word "estimated" or "projected".
   * Example: "Estimated 30% reduction in infrastructure management overhead"
   */
  quantifiedEstimate?: string;

  /** Confidence level for this specific driver */
  confidence: 'conservative' | 'moderate' | 'optimistic';

  /** IDs of benchmarks used to derive this driver's estimate */
  supportingBenchmarkIds: string[];

  /** Whether this is a custom (non-standard) driver */
  isCustom?: boolean;
}

interface BenchmarkReference {
  /** Unique identifier matching Benchmark Knowledge Base entry */
  id: string;

  /** Short label for display */
  label: string;

  /** Source attribution */
  source: string;
}
```

**Example output** (abbreviated):

```json
{
  "drivers": [
    {
      "name": "Cost Savings",
      "impact": "Migrating from on-premises infrastructure to Azure PaaS services eliminates hardware refresh cycles and reduces administrative overhead. The serverless components scale to zero during off-peak hours, avoiding idle-capacity costs.",
      "quantifiedEstimate": "Estimated 30-40% reduction in total infrastructure costs over 3 years",
      "confidence": "moderate",
      "supportingBenchmarkIds": ["BM-001", "BM-003"],
      "isCustom": false
    },
    {
      "name": "Operational Efficiency",
      "impact": "Automated CI/CD pipelines and managed Kubernetes reduce deployment friction. Infrastructure-as-Code eliminates manual provisioning errors and enables repeatable environments.",
      "quantifiedEstimate": "Projected 60% reduction in deployment cycle time",
      "confidence": "optimistic",
      "supportingBenchmarkIds": ["BM-005"],
      "isCustom": false
    }
  ],
  "executiveSummary": "The proposed Azure solution positions [Customer] to realize significant cost savings through PaaS adoption and operational efficiency gains via automation. Conservative estimates project a 30-40% reduction in infrastructure costs and a 60% improvement in deployment velocity. These projections are based on industry benchmarks from comparable cloud migration initiatives and are subject to validation during implementation planning.",
  "benchmarks": [
    { "id": "BM-001", "label": "Cloud migration  TCO reduction (Forrester TEI)", "source": "Forrester Total Economic Impact, 2023" },
    { "id": "BM-003", "label": "Azure PaaS vs IaaS cost comparison", "source": "Microsoft Internal Benchmark Data" },
    { "id": "BM-005", "label": "DevOps automation efficiency gains", "source": "DORA State of DevOps Report, 2023" }
  ],
  "generatedAt": "2025-07-15T14:30:00Z",
  "overallConfidence": "moderate"
}
```

---

## 4. Quantification Methodology

### 4.1 Estimate Sources

The agent generates quantified estimates by combining three input categories:

| Source | Method | Example |
|--------|--------|---------|
| **Industry benchmarks** | Look up matching entries in the Benchmark Knowledge Base (§5) by industry, use case, and metric. Apply the benchmark range to the customer's context. | Benchmark BM-001 states 30-40% TCO reduction for cloud migration; agent applies this to the customer's on-prem-to-Azure scenario. |
| **Cost comparison** | When `costEstimate` is available, compare proposed Azure costs against stated or inferred current-state costs. | Customer states $50K/month current hosting; proposed Azure estimate is $32K/month → 36% cost reduction. |
| **Efficiency modeling** | Map architecture patterns (e.g., serverless, event-driven, managed services) to known efficiency multipliers from the benchmark set. | Serverless adoption correlates with BM-007 (40-60% reduction in ops overhead). |

**Quantification is optional per driver.** If no credible data source supports a numeric estimate, the driver includes only the qualitative `impact` field and `quantifiedEstimate` is omitted.

### 4.2 Confidence Indicators

Every `ValueDriver` carries a `confidence` field that qualifies how the estimate was derived:

| Level | Criteria | Typical Trigger |
|-------|----------|-----------------|
| **Conservative** | Estimate uses the low end of benchmark ranges; multiple corroborating sources exist; customer context closely matches benchmark conditions. | Well-documented migration pattern with industry-specific data. |
| **Moderate** | Estimate uses the midpoint of benchmark ranges; at least one corroborating source; reasonable contextual match. | Standard cloud adoption scenario with general benchmarks. |
| **Optimistic** | Estimate uses the high end of benchmark ranges or extrapolates from loosely related benchmarks; limited corroboration. | Novel architecture pattern or niche industry with few comparable cases. |

The `overallConfidence` on the `ValueAssessment` is determined by the lowest confidence among the top three drivers by impact relevance.

### 4.3 Projection Disclaimers

**All quantified estimates MUST be accompanied by disclaimer language.** The following rules apply:

1. **Per-estimate prefix**: Every `quantifiedEstimate` string MUST begin with "Estimated" or "Projected".
2. **Executive summary disclaimer**: The `executiveSummary` MUST include a closing sentence containing the phrase: *"These projections are based on industry benchmarks and comparable deployments and are subject to validation during implementation planning."*
3. **Frontend display**: The UI MUST render a disclaimer banner above the Value Assessment section (see §7).

**Standard disclaimer text** (rendered in the frontend):

> ⚠️ **Projection Notice**: All quantified estimates in this assessment are projections based on industry benchmarks and comparable customer outcomes. They do not constitute guarantees of specific results. Actual outcomes depend on implementation approach, organizational readiness, and market conditions.

---

## 5. Benchmark Knowledge Base

### 5.1 Schema

The Benchmark Knowledge Base is a static, curated dataset embedded in the agent's configuration. Each entry follows this schema:

```typescript
interface Benchmark {
  /** Unique identifier, format: BM-NNN */
  id: string;

  /** Industry vertical or "cross-industry" */
  industry: string;

  /** Solution pattern or migration type */
  useCase: string;

  /** What is being measured */
  metric: string;

  /** Quantified value or range */
  value: string;

  /** Attribution — report name, publisher, year */
  source: string;
}
```

### 5.2 Mock Data

The following benchmarks are pre-loaded for the simulated knowledge base. In production, this dataset would be maintained and expanded by the product team.

| ID | Industry | Use Case | Metric | Value | Source |
|----|----------|----------|--------|-------|--------|
| BM-001 | Cross-industry | Cloud migration (on-prem to Azure) | TCO reduction | 30–40% over 3 years | Forrester Total Economic Impact, 2023 |
| BM-002 | Financial Services | Core banking modernization | Transaction processing throughput | 3–5× improvement | McKinsey Digital Banking Benchmark, 2023 |
| BM-003 | Cross-industry | PaaS adoption (IaaS → PaaS) | Infrastructure management overhead | 25–35% reduction | Microsoft Internal Benchmark Data, 2024 |
| BM-004 | Retail | E-commerce platform migration | Page load performance | 40–60% improvement | Google Cloud Retail Study, 2023 |
| BM-005 | Cross-industry | DevOps / CI-CD automation | Deployment frequency | 4–10× increase | DORA State of DevOps Report, 2023 |
| BM-006 | Healthcare | EHR system modernization | Compliance audit preparation time | 50–70% reduction | HIMSS Analytics, 2023 |
| BM-007 | Cross-industry | Serverless adoption | Operations overhead | 40–60% reduction | Datadog Serverless Report, 2023 |
| BM-008 | Manufacturing | IoT predictive maintenance | Unplanned downtime | 25–35% reduction | Deloitte Smart Factory Study, 2023 |
| BM-009 | Cross-industry | AI/ML integration (Copilot-style) | Developer productivity | 20–40% improvement | GitHub Copilot Productivity Study, 2023 |
| BM-010 | Cross-industry | Containerization (VMs → AKS) | Resource utilization | 30–50% improvement | Gartner Container Adoption Report, 2023 |
| BM-011 | Public Sector | Legacy application modernization | Citizen service response time | 40–55% improvement | Accenture Government Cloud Study, 2023 |
| BM-012 | Cross-industry | Disaster recovery on Azure | RTO improvement | 60–80% reduction | IDC Cloud Resiliency Report, 2024 |

---

## 6. Executive Summary Generation

### 6.1 Format & Length

- **Length**: 100–200 words (3–5 sentences).
- **Format**: Single prose paragraph. No bullet points, no headers, no markdown formatting within the summary string.
- **Audience**: C-level executives, VP-level decision-makers, and budget owners who may not read the full assessment.

### 6.2 Content Structure

The executive summary follows a fixed narrative arc:

1. **Opening** (1 sentence): State the strategic opportunity — what the proposed solution enables for the customer.
2. **Key value highlights** (1–2 sentences): Reference the top 2–3 value drivers by name with their quantified estimates (if available).
3. **Benchmark grounding** (1 sentence): Note that projections are informed by industry benchmarks and comparable deployments.
4. **Closing qualifier** (1 sentence): Include the required projection disclaimer (see §4.3).

**Example**:

> The proposed Azure solution positions Contoso to accelerate its digital transformation by modernizing legacy infrastructure and enabling scalable, cloud-native operations. Key projected benefits include a 30–40% reduction in total infrastructure costs through PaaS adoption and a 60% improvement in deployment velocity via automated CI/CD pipelines. These estimates are informed by industry benchmarks from Forrester, DORA, and comparable enterprise cloud migrations. All projections are based on industry benchmarks and comparable deployments and are subject to validation during implementation planning.

### 6.3 Tone Guidelines

| Guideline | Do | Don't |
|-----------|-----|-------|
| **Confident but qualified** | "Projected to reduce costs by 30–40%" | "Will definitely save 40%" |
| **Business-focused** | "Enables faster go-to-market" | "Uses Azure Container Apps with Dapr sidecars" |
| **Concise** | One clear sentence per idea | Run-on sentences with multiple clauses |
| **Active voice** | "The solution accelerates deployment" | "Deployment is accelerated by the solution" |
| **Customer-centric** | "Positions [Customer] to capture…" | "Our platform provides…" |

---

## 7. Frontend Behavior

### 7.1 Value Driver Cards

Each value driver is rendered as a card in the assessment results panel.

**Card layout**:
- **Header**: Driver name (e.g., "Cost Savings") with a confidence badge (`conservative` = blue, `moderate` = amber, `optimistic` = green).
- **Body**: The `impact` text (qualitative description).
- **Highlight bar**: If `quantifiedEstimate` is present, render it in a visually distinct callout box with an 📊 icon prefix.
- **Footer**: "Based on: [benchmark labels]" — clickable links that expand to show the full benchmark source.
- **Custom driver indicator**: Drivers with `isCustom: true` display a "Custom" tag next to the driver name.

**Ordering**: Standard drivers appear first in the fixed order defined in §2.1. Custom drivers appear after, sorted alphabetically by name.

**Empty state**: If a standard driver has no meaningful impact for the given solution, it is omitted from the card list (not shown as "N/A").

### 7.2 Executive Summary Display

- Rendered as a styled blockquote at the top of the Business Value section.
- Background: Light blue (#EFF6FF) with a left border accent in brand blue.
- A "Copy to clipboard" button allows sellers to paste the summary directly into emails or documents.
- The projection disclaimer (§4.3) is rendered as a collapsible banner immediately below the summary. It defaults to **expanded** on first view and remembers the user's collapse/expand preference in `localStorage`.

### 7.3 Benchmark References

- Benchmarks are listed in a collapsible "Supporting Benchmarks" section below the driver cards.
- Each benchmark row shows: ID, metric, value, and source.
- Benchmarks that are not referenced by any driver in the current assessment are not displayed.
- Tooltip on hover shows the full `industry` and `useCase` fields.

---

## 8. Error Responses

| Scenario | HTTP Status | Error Code | User-Facing Message |
|----------|-------------|------------|---------------------|
| `ProjectContext` is missing required fields (`requirements`, `architecture`, or `services`) | 400 | `INVALID_INPUT` | "Unable to generate business value assessment. Required project context is incomplete." |
| No value drivers could be evaluated (all drivers return empty impact) | 200 (partial) | `NO_DRIVERS_IDENTIFIED` | "The assessment could not identify meaningful value drivers for this solution. Consider refining the project requirements." |
| Benchmark Knowledge Base is unreachable or empty | 200 (degraded) | `BENCHMARKS_UNAVAILABLE` | "Assessment generated without benchmark references. Quantified estimates may be less precise." |
| Agent timeout (>30 seconds) | 504 | `AGENT_TIMEOUT` | "The business value assessment is taking longer than expected. Please try again." |
| Upstream cost estimate failed | 200 (degraded) | `COST_ESTIMATE_MISSING` | Assessment proceeds without cost-comparison quantification; a note is appended to the executive summary (see §9). |

All error responses follow the shared `ApiError` schema:

```typescript
interface ApiError {
  error: string;
  details?: string;
}
```

---

## 9. Edge Cases

### 9.1 No Cost Estimate Available

When `costEstimate` is absent from `ProjectContext`:
- The agent omits cost-comparison quantification from the Cost Savings driver.
- The Cost Savings driver may still include qualitative impact based on architecture patterns (e.g., "serverless eliminates idle-capacity costs").
- The executive summary appends: *"Cost savings projections could not be quantified as cost estimate data was unavailable."*

### 9.2 Conflicting Value Drivers

When two drivers produce contradictory implications (e.g., higher upfront costs for long-term savings):
- Both drivers are included with their respective impacts stated transparently.
- The executive summary acknowledges the trade-off: *"While the solution requires increased initial investment in [area], this is offset by projected long-term savings in [area]."*

### 9.3 Very Niche Industry

When `requirements.industry` does not match any entry in the Benchmark Knowledge Base:
- The agent falls back to `cross-industry` benchmarks only.
- The `overallConfidence` is capped at `'low'`.
- A note is appended to the executive summary: *"Limited industry-specific benchmark data is available for [industry]. Projections are based on cross-industry benchmarks."*

### 9.4 No Benchmarks Match

When no benchmarks in the knowledge base match the solution's use case or architecture patterns:
- All `supportingBenchmarkIds` arrays are empty.
- `quantifiedEstimate` is omitted from all drivers.
- The assessment is purely qualitative.
- `overallConfidence` is set to `'low'`.
- The executive summary notes: *"Quantified projections are not available for this assessment due to limited benchmark coverage."*

### 9.5 Minimal Requirements Input

When `requirements` contains only the `industry` field (no pain points, no objectives):
- The agent generates a generic assessment based on architecture patterns and selected Azure services.
- `overallConfidence` is capped at `'low'`.
- The executive summary includes: *"This assessment is based on limited input. A more detailed requirements gathering session would enable more precise projections."*

### 9.6 Single-Service Architecture

When `services` contains only one Azure service:
- The agent evaluates all five standard drivers but limits quantification to drivers directly supported by that service's capabilities.
- Custom drivers are not generated for single-service architectures.

---

## Traceability

| Artifact | Reference |
|----------|-----------|
| **PRD User Story** | US-6: Business Value Assessment |
| **PRD Functional Requirement** | FR-2: Agent Definitions — Business Value Agent |
| **PRD Functional Requirement** | FR-3: Agent Pipeline — Step 5 (Business Value Agent) |
| **PRD Acceptance Criteria** | US-6 AC-1: Evaluate against value drivers |
| **PRD Acceptance Criteria** | US-6 AC-2: Quantified estimates where possible |
| **PRD Acceptance Criteria** | US-6 AC-3: Industry benchmarks referenced |
| **PRD Acceptance Criteria** | US-6 AC-4: Executive-audience summary |
| **PRD Acceptance Criteria** | US-6 AC-5: Projections not guarantees |
| **Agent** | Business Value Agent |
| **Upstream Dependencies** | Envisioning Agent, System Architect Agent, Azure Specialist Agent, Cost Specialist Agent |
| **Downstream Consumers** | Presentation Agent (PowerPoint generation) |
| **Data Model** | `ValueAssessment`, `ValueDriver`, `BenchmarkReference` (§3.2) |
| **Benchmark Data** | Benchmark Knowledge Base (§5) |
