# FRD-ENVISIONING: Envisioning Agent

**Feature ID**: US-2  
**Status**: Draft  
**Priority**: P1  
**Last Updated**: 2025-07-18  

## 1. Overview

The Envisioning Agent is a specialized AI agent within OneStopAgent that helps Azure sellers shape an opportunity when the customer's need is unclear. It is invoked by the Project Manager Agent when the seller's initial description is too vague to proceed directly to architecture design.

The agent queries a simulated internal knowledge base to surface three categories of suggestions — **scenarios**, **sample estimates**, and **reference architectures** — ranked by relevance to the seller's industry and keywords. The seller reviews the suggestions, selects items via checkboxes, and proceeds to downstream agents with enriched context. If no suggestions match, the agent explains why and prompts for more detail.

**Data source for MVP**: All knowledge base content is mock/simulated data. No real CRM, engagement history, or customer data is used.

---

## 2. Knowledge Base Schema

### 2.1 Scenario Definition

A scenario represents a high-level Azure use case or solution pattern applicable to an industry.

```typescript
interface Scenario {
  id: string;            // Unique identifier, e.g., "SCN-001"
  title: string;         // Display name, e.g., "Digital Commerce Platform"
  industry: string;      // Primary industry, e.g., "Retail"
  description: string;   // 1–2 sentence summary of the scenario
  link: string;          // URL to supporting material (Microsoft Learn, case study)
  tags: string[];        // Keywords for matching, e.g., ["e-commerce", "omnichannel", "digital"]
}
```

### 2.2 Sample Estimate Definition

A sample estimate represents a past engagement (simulated) that can serve as a reference for sizing and scoping.

```typescript
interface SampleEstimate {
  id: string;            // Unique identifier, e.g., "EST-001"
  title: string;         // Engagement title, e.g., "Calgary Connected Commerce"
  customerName: string;  // Anonymized or simulated customer name
  industry: string;      // Industry of the engagement
  description: string;   // 1–2 sentence summary of the engagement scope
  link: string;          // URL to detailed estimate or case study
  estimatedACR?: number; // Estimated Annual Consumed Revenue in USD (optional)
}
```

### 2.3 Reference Architecture Definition

A reference architecture represents a proven Azure architecture pattern with specific service compositions.

```typescript
interface ReferenceArchitecture {
  id: string;              // Unique identifier, e.g., "ARCH-001"
  title: string;           // Display name, e.g., "Microservices-Based E-Commerce Platform"
  description: string;     // 1–2 sentence summary of the architecture
  link: string;            // URL to Azure Architecture Center or Microsoft Learn
  azureServices: string[]; // Key Azure services used, e.g., ["Azure Kubernetes Service", "Cosmos DB", "API Management"]
}
```

### 2.4 Mock Data

The following mock entries populate the knowledge base for MVP. Entries span Retail, Financial Services, Healthcare, Manufacturing, and Media & Entertainment.

#### Scenarios

| ID | Title | Industry | Tags |
|---|---|---|---|
| SCN-001 | Digital Commerce Platform | Retail | e-commerce, omnichannel, digital storefront |
| SCN-002 | Digital Transformation using AI | Cross-Industry | AI, machine learning, modernization |
| SCN-003 | Intelligent Claims Processing | Financial Services | insurance, claims, automation, AI |
| SCN-004 | Remote Patient Monitoring | Healthcare | IoT, telehealth, patient engagement |
| SCN-005 | Predictive Maintenance Platform | Manufacturing | IoT, predictive analytics, OT/IT convergence |
| SCN-006 | Personalized Content Delivery | Media & Entertainment | streaming, recommendation engine, CDN |
| SCN-007 | Fraud Detection & Prevention | Financial Services | real-time analytics, anomaly detection, security |

#### Sample Estimates

| ID | Title | Customer | Industry | Est. ACR |
|---|---|---|---|---|
| EST-001 | Calgary Connected Commerce | Calgary Co-op | Retail | $420,000 |
| EST-002 | Costco Phase 2 Digital Transform | Costco | Retail | $1,200,000 |
| EST-003 | New Balance Project Dawn | New Balance | Retail | $680,000 |
| EST-004 | Contoso Insurance Claims AI | Contoso Insurance | Financial Services | $350,000 |
| EST-005 | Fabrikam Health Monitoring | Fabrikam Health | Healthcare | $290,000 |
| EST-006 | Northwind Traders Analytics | Northwind Traders | Manufacturing | $510,000 |
| EST-007 | Relecloud Streaming Platform | Relecloud | Media & Entertainment | $750,000 |

#### Reference Architectures

| ID | Title | Azure Services |
|---|---|---|
| ARCH-001 | Microservices-Based E-Commerce Platform | AKS, Cosmos DB, API Management, Azure Front Door |
| ARCH-002 | Scalable E-Commerce Web App | App Service, Azure SQL, Azure Cache for Redis, CDN |
| ARCH-003 | AI-Enriched Document Processing | Azure AI Document Intelligence, Cognitive Services, Blob Storage, Logic Apps |
| ARCH-004 | IoT Remote Monitoring Solution | IoT Hub, Stream Analytics, Azure Digital Twins, Time Series Insights |
| ARCH-005 | Real-Time Fraud Detection | Event Hubs, Azure Databricks, Azure Synapse, Power BI |
| ARCH-006 | Media Streaming & Delivery | Azure Media Services, CDN, Blob Storage, Azure Front Door |
| ARCH-007 | Hybrid Cloud Manufacturing | Azure Arc, IoT Edge, Azure Monitor, Azure Data Explorer |

---

## 3. Agent Input/Output Contract

### 3.1 Input (from PM Agent)

The Envisioning Agent receives a `ProjectContext` object from the Project Manager Agent containing the seller's description and any inferred metadata.

```typescript
interface EnvisioningInput {
  projectId: string;
  userDescription: string;     // The seller's free-text description of the customer opportunity
  industryHints?: string[];    // Industries inferred by PM Agent from the description, e.g., ["Retail"]
  keywords?: string[];         // Key terms extracted by PM Agent, e.g., ["e-commerce", "digital", "AI"]
  customerName?: string;       // Optional customer name from project creation
}
```

- `userDescription` is required; all other fields are optional.
- If `industryHints` and `keywords` are not provided, the Envisioning Agent infers them from `userDescription` (see §4.1).

### 3.2 Output Schema

The agent returns a structured response containing ranked suggestions across all three categories.

```typescript
interface EnvisioningOutput {
  scenarios: SelectableItem[];
  estimates: SelectableItem[];
  architectures: SelectableItem[];
  matchConfidence: 'high' | 'medium' | 'low' | 'none';
  matchExplanation?: string;   // Required when matchConfidence is 'none'
}

interface SelectableItem {
  id: string;           // Knowledge base item ID (e.g., "SCN-001")
  title: string;        // Display title
  description: string;  // Brief description
  link: string;         // URL to supporting material
  relevanceScore: number; // 0.0–1.0, used for ranking; not displayed to seller
  selected: boolean;    // Default: false; toggled by seller interaction
  category: 'scenario' | 'estimate' | 'architecture';
}
```

- Items within each category are ordered by `relevanceScore` descending.
- Each category returns a maximum of **5** items (top-ranked).
- A minimum of **1** item per category is returned when `matchConfidence` is not `'none'`.

### 3.3 Selection Response

When the seller clicks **"Proceed with Selected Items"**, the agent returns a summary that is persisted to `ProjectContext.envisioningSelections` and forwarded to the next agent in the pipeline.

```typescript
interface EnvisioningSelectionResponse {
  selectedItems: SelectedItem[];
  sellerDirection?: string;     // Free-text if seller rejected all and described own direction
  enrichedContext: {
    inferredIndustry: string;
    inferredKeywords: string[];
    selectedScenarioTitles: string[];
    selectedEstimateTitles: string[];
    selectedArchitectureTitles: string[];
  };
}

interface SelectedItem {
  id: string;
  title: string;
  category: 'scenario' | 'estimate' | 'architecture';
}
```

- If the seller rejected all suggestions and provided own direction, `selectedItems` is an empty array and `sellerDirection` contains the seller's free-text input.
- `enrichedContext` is always populated to give downstream agents maximum context.

---

## 4. Matching Logic

### 4.1 Industry Detection

The agent infers the customer's industry from the seller's description using the following approach:

1. **Explicit hint**: If `industryHints` is provided by the PM Agent, use it as the primary filter.
2. **Keyword extraction**: The agent scans `userDescription` for industry-specific terms mapped to a predefined industry taxonomy:
   - **Retail**: store, commerce, e-commerce, retail, shopping, omnichannel, POS, inventory
   - **Financial Services**: bank, insurance, fintech, trading, payments, claims, fraud, compliance
   - **Healthcare**: hospital, patient, clinical, EHR, telehealth, pharma, medical, HIPAA
   - **Manufacturing**: factory, supply chain, OT, IoT, predictive maintenance, production, assembly
   - **Media & Entertainment**: streaming, content, media, broadcast, gaming, video, CDN
3. **Multi-industry**: If terms from multiple industries are detected, the agent returns results from all matched industries, ranked by term frequency.
4. **No industry detected**: If no industry can be inferred, the agent applies `"Cross-Industry"` as the default filter and includes a broader set of results.

### 4.2 Keyword Matching

Items are ranked using a weighted keyword match:

1. **Tag match** (weight: 1.0): Each tag on a knowledge base item that matches a keyword from `keywords` or `userDescription` contributes a full point.
2. **Title match** (weight: 0.8): Partial or full matches against the item title.
3. **Description match** (weight: 0.5): Partial matches against the item description.
4. **Industry match** (weight: 1.5): Items whose `industry` matches the inferred industry receive a bonus.
5. **Normalization**: Scores are normalized to a 0.0–1.0 range within each category to produce the `relevanceScore`.

Items with a `relevanceScore` below **0.1** are excluded from results.

### 4.3 No-Match Fallback

When no items exceed the relevance threshold across **all three categories**:

1. The agent sets `matchConfidence` to `'none'`.
2. The agent returns an empty array for `scenarios`, `estimates`, and `architectures`.
3. The agent populates `matchExplanation` with a message such as:
   > "I couldn't find matching scenarios, estimates, or reference architectures for your description. This may be because the industry or use case is outside our current knowledge base. Could you provide more details about the customer's industry, the business problem they're trying to solve, or specific Azure services they're interested in?"
4. The frontend renders this message and presents a free-text input for the seller to provide additional context.
5. On resubmission, the PM Agent re-invokes the Envisioning Agent with the combined original + additional context.

---

## 5. Frontend Behavior

### 5.1 Selectable List Rendering

The Envisioning Agent's output is rendered as a structured message card in the chat interface with the following layout:

```
┌──────────────────────────────────────────────┐
│  🔍 Envisioning Agent                        │
│                                              │
│  Based on your description, here are         │
│  relevant suggestions:                       │
│                                              │
│  **Scenarios:**                              │
│  ☐ 1. Digital Commerce Platform (Link)       │
│  ☐ 2. Digital Transformation using AI (Link) │
│                                              │
│  **Sample Estimates:**                       │
│  ☑ 1. Calgary Connected Commerce (Link)      │
│  ☐ 2. Costco Phase 2 Digital Transform (Link)│
│  ☐ 3. New Balance Project Dawn (Link)        │
│                                              │
│  **Reference Architectures:**                │
│  ☐ 1. Microservices-Based E-Commerce (Link)  │
│  ☐ 2. Scalable E-Commerce Web App (Link)     │
│                                              │
│  [Proceed with Selected Items (1)]           │
│                                              │
│  ── or ──                                    │
│  [Describe your own direction]               │
└──────────────────────────────────────────────┘
```

**Rendering rules:**

- Each category is rendered as a group with a bold header (**Scenarios:**, **Sample Estimates:**, **Reference Architectures:**).
- Items within each group are numbered sequentially starting from 1.
- Each item displays a checkbox (`☐` / `☑`), the title, and a hyperlinked "(Link)" that opens the `link` URL in a new tab.
- Hovering over an item title shows the `description` in a tooltip.
- Categories with zero items are hidden entirely (no empty headers).
- Items are listed in `relevanceScore` descending order (highest first).

### 5.2 "Proceed with Selected Items" Button

- The button label dynamically shows the count of selected items: **"Proceed with Selected Items (N)"**.
- The button is **disabled** (greyed out, non-clickable) when **N = 0**.
- The button is **enabled** when **N ≥ 1**.
- On click, the frontend sends a `POST /api/projects/:id/chat` with the selection payload (see §3.3).
- While processing, the button shows a loading spinner and is disabled to prevent double-submission.

### 5.3 Rejection Flow

If the seller finds none of the suggestions relevant:

1. The seller clicks **"Describe your own direction"** (displayed below the Proceed button, separated by a divider).
2. A free-text input area expands inline within the message card.
3. The seller types their own description and clicks **"Submit"**.
4. The agent receives this as `sellerDirection` and passes it to the PM Agent for downstream routing.
5. The PM Agent may re-invoke Envisioning with the new context or proceed directly to the System Architect Agent, depending on the specificity of the seller's input.

---

## 6. Error Responses

| Error Condition | Agent Behavior | User-Facing Message |
|---|---|---|
| Knowledge base unavailable | Agent returns `matchConfidence: 'none'` | "The knowledge base is temporarily unavailable. Please describe your scenario directly, and we'll proceed without pre-built suggestions." |
| PM Agent sends empty `userDescription` | Agent returns validation error | "I need a description of the customer opportunity to find relevant suggestions. Please provide some details about what the customer is looking for." |
| `userDescription` exceeds 5,000 characters | Agent truncates to 5,000 characters and proceeds | No user-facing warning; processing continues on truncated input. |
| Agent timeout (>30s per NFR-1) | PM Agent handles per FR-3 error handling | "The Envisioning Agent is taking longer than expected. You can retry or describe your scenario directly." |
| Malformed selection payload | API returns 400 | "Something went wrong with your selection. Please try again." |

---

## 7. Edge Cases

| Edge Case | Expected Behavior |
|---|---|
| **No matches across all categories** | Agent returns `matchConfidence: 'none'` with explanation (see §4.3). UI shows explanation + free-text input. |
| **All items selected** | Proceed button shows total count. All items are forwarded to downstream agents. No limit on selection count. |
| **Seller selects items from only one category** | Valid. Selection response includes only items from the selected category; other categories are empty arrays. |
| **Conflicting industry signals** | Agent returns results from all detected industries, ranked by relevance. `matchExplanation` notes: "Your description suggests multiple industries. We've included suggestions across all of them." |
| **Very long description (>2,000 chars)** | Agent processes the full description (up to 5,000-char limit). Keyword extraction focuses on the first 2,000 characters for performance but uses the full text for industry detection. |
| **Very short description (<10 chars)** | Agent attempts matching with available terms. If insufficient, returns `matchConfidence: 'low'` with broader results and prompts for more detail. |
| **Re-invocation after rejection** | Agent merges the original `userDescription` with the seller's `sellerDirection` to produce a combined context for a second pass. Previous selections are cleared. |
| **Seller navigates away and returns** | Selections are persisted in the chat message state. The seller can resume where they left off without re-triggering the agent. |
| **Duplicate items across categories** | Not applicable by design — scenarios, estimates, and architectures are distinct entity types with separate ID namespaces. |
| **Special characters in description** | Input is sanitized per FR-8 (prompt injection mitigation). Unicode and standard punctuation are preserved. |

---

## Traceability

| FRD Section | PRD Reference | Notes |
|---|---|---|
| §1 Overview | US-2: Guided Envisioning | Core user story |
| §2 Knowledge Base Schema | FR-2: Agent Definitions (Envisioning row) | "Internal knowledge base (simulated)" |
| §2.4 Mock Data | US-2 AC: "simulated knowledge base" | MVP uses mock data, not real CRM |
| §3.1 Input | FR-3: Agent Pipeline, FR-4: Data Model (ProjectContext) | Input from PM Agent |
| §3.2 Output | US-2 AC: "presents relevant scenarios…reference architectures as selectable options" | Structured multi-category response |
| §3.3 Selection | US-2 AC: "select one or more items…click Proceed with Selected Items" | Selection forwarded to pipeline |
| §4.1 Industry Detection | US-2 AC: "based on industry and keywords" | Inference from description |
| §4.3 No-Match | US-2 AC: "agent explains why and prompts the seller to provide more context" | Fallback flow |
| §5.1 List Rendering | FR-6: Chat Interface — "selectable option lists with checkboxes" | Checkbox groups with links |
| §5.2 Proceed Button | US-2 AC: "Proceed with Selected Items" | Count badge, disabled at 0 |
| §5.3 Rejection Flow | US-2 AC: "reject all suggestions and describe their own direction" | Free-text alternative |
| §6 Error Responses | FR-3: Error handling, NFR-1: Response time | Graceful degradation |
| §7 Edge Cases | US-2 AC (all), FR-8: Input sanitization | Comprehensive coverage |
