# FRD-ARCHITECTURE: Architecture & Azure Services

**Feature ID**: F-003, F-004
**Status**: Draft
**Priority**: P0
**Last Updated**: 2025-07-24
**Traces To**: US-3 (Architecture Generation), US-4 (Azure Service Selection), R-5 (Max 30 Nodes)

---

## 1. Overview

This FRD specifies the functional behavior of two tightly coupled agents in the OneStopAgent pipeline:

1. **System Architect Agent (US-3)** — Accepts project requirements and envisioning selections from prior workflow steps, then produces a Mermaid-based architecture diagram, a structured component list, and a narrative description. The diagram is rendered visually in the chat interface and is exportable as PNG or SVG.

2. **Azure Specialist Agent (US-4)** — Consumes the architecture output and maps each component to concrete Azure services with SKU recommendations, region availability, key capabilities, and alternative-service trade-offs.

Both agents are grounded in Azure documentation retrieved via the Microsoft Learn MCP Server. When the MCP Server is unavailable, each agent falls back to built-in knowledge and flags outputs as **"unverified — MCP source unavailable."**

### Workflow Position

```
Envisioning Agent (US-1/US-2)
        │
        ▼
  ┌─────────────┐      ┌──────────────────┐
  │  System      │─────▶│  Azure Specialist │
  │  Architect   │      │  Agent            │
  │  Agent       │      │  (US-4)           │
  │  (US-3)      │      └──────────────────┘
  └─────────────┘               │
        │                       ▼
        ▼              Cost Estimator (US-5)
  Export Endpoint
  /export/architecture
```

---

## 2. System Architect Agent

### 2.1 Input Contract

The System Architect Agent receives a `ProjectContext` object containing data accumulated from upstream agents.

```typescript
interface ArchitectAgentInput {
  projectId: string;               // UUID — current project identifier
  requirements: Record<string, string>;
  // Key-value pairs from envisioning phase.
  // Example: { "workload": "web app", "scale": "1000 concurrent users",
  //            "data": "relational, <50 GB", "auth": "Entra ID SSO" }

  envisioningSelections?: string[];
  // User-confirmed selections from the Envisioning Agent.
  // Example: ["three-tier architecture", "serverless compute", "managed database"]

  modificationRequest?: string;
  // Optional — present only when the seller requests a change to an
  // existing architecture (see §5 Modification Flow).
  // Example: "add a caching layer between the API and the database"

  previousArchitecture?: ArchitectureOutput;
  // Optional — present only during modification flow.
  // The agent applies a delta update rather than regenerating from scratch.
}
```

**Validation rules:**

| Field | Rule | Error |
|---|---|---|
| `projectId` | Required, valid UUID v4 | `400 INVALID_PROJECT_ID` |
| `requirements` | Required, ≥ 1 key-value pair | `400 EMPTY_REQUIREMENTS` |
| `envisioningSelections` | Optional; if present, must be non-empty array of strings | `400 INVALID_SELECTIONS` |
| `modificationRequest` | Optional; if present, must be non-empty string ≤ 500 chars | `400 INVALID_MODIFICATION` |

### 2.2 Output Contract — ArchitectureOutput

```typescript
interface ArchitectureOutput {
  mermaidCode: string;
  // Valid Mermaid diagram source code.
  // Diagram type: flowchart TD (top-down) by default.
  // Max 30 nodes (R-5). Max 60 edges.
  // Example:
  // ```mermaid
  // flowchart TD
  //   USER[/"End User"\] -->|HTTPS| APIM["Azure API Management"]
  //   APIM --> APP["Azure App Service"]
  //   APP --> SQL[("Azure SQL Database")]
  //   APP --> BLOB[("Azure Blob Storage")]
  //   APP --> REDIS["Azure Cache for Redis"]
  // ```

  components: ArchitectureComponent[];
  // One entry per node in the diagram.
  // Ordered topologically (entry points first, data stores last).

  narrative: string;
  // 2–4 paragraph Markdown description of the architecture.
  // Explains data flow, scaling strategy, and security posture.
  // Written for a non-technical Azure seller audience.

  metadata: {
    generatedAt: string;           // ISO 8601 timestamp
    mcpSourced: boolean;           // true if MCP was used for grounding
    retryCount: number;            // 0–2; number of Mermaid-syntax retries
    diagramType: 'flowchart';      // Currently only flowchart supported
    nodeCount: number;             // Actual node count (≤ 30)
    edgeCount: number;             // Actual edge count (≤ 60)
  };
}

interface ArchitectureComponent {
  name: string;
  // Display name matching the Mermaid node label.
  // Example: "Azure App Service"

  azureService: string;
  // Canonical Azure service name.
  // Example: "Microsoft.Web/sites"

  description: string;
  // One-sentence role description.
  // Example: "Hosts the customer-facing web application with auto-scaling."

  category: 'compute' | 'data' | 'networking' | 'security' | 'integration' | 'monitoring' | 'storage' | 'ai';
  // Functional category for grouping in the UI component table.
}
```

**Example output:**

```json
{
  "mermaidCode": "flowchart TD\n  USER[/\"End User\"\\] -->|HTTPS| FD[\"Azure Front Door\"]\n  FD --> APP[\"Azure App Service\"]\n  APP --> SQL[(\"Azure SQL Database\")]\n  APP --> BLOB[(\"Azure Blob Storage\")]\n  APP --> REDIS[\"Azure Cache for Redis\"]",
  "components": [
    {
      "name": "Azure Front Door",
      "azureService": "Microsoft.Cdn/profiles",
      "description": "Global load balancer and CDN providing TLS termination and WAF protection.",
      "category": "networking"
    },
    {
      "name": "Azure App Service",
      "azureService": "Microsoft.Web/sites",
      "description": "Hosts the customer-facing web application with auto-scaling.",
      "category": "compute"
    },
    {
      "name": "Azure SQL Database",
      "azureService": "Microsoft.Sql/servers/databases",
      "description": "Relational data store for transactional application data.",
      "category": "data"
    },
    {
      "name": "Azure Blob Storage",
      "azureService": "Microsoft.Storage/storageAccounts",
      "description": "Object storage for user-uploaded files and static assets.",
      "category": "storage"
    },
    {
      "name": "Azure Cache for Redis",
      "azureService": "Microsoft.Cache/redis",
      "description": "In-memory cache for session state and frequently accessed data.",
      "category": "data"
    }
  ],
  "narrative": "The proposed architecture follows a three-tier pattern...",
  "metadata": {
    "generatedAt": "2025-07-24T12:00:00Z",
    "mcpSourced": true,
    "retryCount": 0,
    "diagramType": "flowchart",
    "nodeCount": 5,
    "edgeCount": 4
  }
}
```

### 2.3 Mermaid Diagram Generation

#### 2.3.1 Diagram Type

| Property | Value |
|---|---|
| Diagram type | `flowchart TD` (top-down) |
| Direction | Top-to-bottom; entry points at top, data stores at bottom |
| Syntax version | Mermaid v10+ compatible |

#### 2.3.2 Complexity Limits (R-5)

| Constraint | Limit | Enforcement |
|---|---|---|
| Maximum nodes | 30 | Agent prompt constraint; validated post-generation |
| Maximum edges | 60 | Agent prompt constraint; validated post-generation |
| Maximum subgraphs | 5 | Prevents over-nesting |
| Maximum label length | 40 characters per node label | Truncate with `…` if exceeded |

If the generated diagram exceeds any limit, the agent **consolidates** related nodes into logical groups (e.g., multiple microservices → "Microservices Cluster") and regenerates.

#### 2.3.3 Node Styling

| Category | Shape | Example |
|---|---|---|
| User/External | Trapezoid `[/"…"\]` | `USER[/"End User"\]` |
| Compute | Rectangle `["…"]` | `APP["Azure App Service"]` |
| Data store | Cylinder `[("…")]` | `SQL[("Azure SQL Database")]` |
| Networking | Rounded `("…")` | `FD("Azure Front Door")` |
| Security | Hexagon `{{"…"}}` | `KV{{"Azure Key Vault"}}` |
| AI/ML | Stadium `(["…"])` | `OAI(["Azure OpenAI"])` |

#### 2.3.4 Edge Labels

- Edges carry protocol or data-flow labels where informative: `-->|HTTPS|`, `-->|gRPC|`, `-->|Event Grid|`.
- Omit labels for obvious relationships to reduce clutter.

#### 2.3.5 Validation Pipeline

```
Agent generates Mermaid code
        │
        ▼
┌─────────────────────┐    Invalid     ┌──────────────────┐
│ Syntax validation    │──────────────▶│ Retry (max 2)    │
│ (mermaid.parse())    │               │ Re-prompt agent  │
└─────────┬───────────┘               │ with error detail│
          │ Valid                      └────────┬─────────┘
          ▼                                     │ Still invalid
┌─────────────────────┐               ┌─────────▼─────────┐
│ Constraint check     │               │ Return raw code + │
│ (nodes ≤ 30,        │               │ error explanation  │
│  edges ≤ 60)        │               └───────────────────┘
└─────────┬───────────┘
          │ Pass
          ▼
   Store in ProjectContext
```

- **Retry prompt** includes the Mermaid parse error message so the agent can correct specific syntax issues.
- After 2 failed retries, the response includes `mermaidCode` (raw), an `error` field with the parse error, and `metadata.retryCount = 2`.

### 2.4 Component List

Each node in the Mermaid diagram has a corresponding entry in the `components` array.

**Required fields per component:**

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Display name matching the Mermaid node label exactly |
| `azureService` | `string` | Canonical Azure resource provider type (e.g., `Microsoft.Web/sites`) |
| `description` | `string` | One-sentence role description (≤ 120 chars) |
| `category` | `enum` | One of: `compute`, `data`, `networking`, `security`, `integration`, `monitoring`, `storage`, `ai` |

**Ordering:** Components are ordered topologically — entry points and networking first, compute middle, data and storage last.

**Invariant:** `components.length === metadata.nodeCount` — every diagram node has a component entry and vice versa.

### 2.5 Narrative

The `narrative` field is a Markdown-formatted text block describing the architecture.

| Property | Requirement |
|---|---|
| Length | 2–4 paragraphs, 150–400 words |
| Audience | Non-technical Azure seller |
| Tone | Professional, customer-presentable |
| Content | Data flow overview, scaling strategy, security posture, high-availability approach |
| Format | Markdown with bold for Azure service names |
| Prohibited | No code snippets, no pricing, no SKU details (those belong in US-4) |

**Example:**

> The proposed architecture uses **Azure Front Door** as the global entry point, providing TLS termination, Web Application Firewall (WAF) protection, and geographic load balancing. Incoming requests are routed to **Azure App Service**, which hosts the application logic with built-in auto-scaling to handle traffic spikes.
>
> Application data is persisted in **Azure SQL Database**, chosen for its relational model and built-in high availability. Static assets and user uploads are stored in **Azure Blob Storage** with geo-redundant replication. **Azure Cache for Redis** sits between the application tier and the database to reduce read latency for frequently accessed data.

---

## 3. Azure Specialist Agent

### 3.1 Input Contract

The Azure Specialist Agent receives the complete `ArchitectureOutput` from the System Architect Agent.

```typescript
interface AzureSpecialistInput {
  projectId: string;
  architecture: ArchitectureOutput;
  // The full output from the System Architect Agent.

  scaleRequirements?: {
    concurrentUsers?: number;       // e.g., 1000
    requestsPerSecond?: number;     // e.g., 500
    dataVolumeGB?: number;          // e.g., 50
    availabilitySLA?: string;       // e.g., "99.95%"
  };
  // Extracted from ProjectContext.requirements during envisioning.
  // Used to drive SKU selection logic (§3.3).

  regionPreference?: string;
  // Preferred Azure region. Example: "eastus2"
  // If omitted, defaults to "eastus" for US customers.
}
```

### 3.2 Output Contract — ServiceSelection[]

```typescript
interface ServiceSelection {
  componentName: string;
  // Matches ArchitectureComponent.name exactly.
  // Example: "Azure App Service"

  serviceName: string;
  // Canonical Azure service name.
  // Example: "Azure App Service"

  sku: string;
  // Recommended SKU / pricing tier.
  // Example: "P1v3"

  region: string;
  // Recommended Azure region.
  // Example: "eastus2"

  capabilities: string[];
  // Key capabilities relevant to the project's requirements.
  // Example: ["Auto-scaling up to 30 instances", "Deployment slots",
  //           "Custom domains with managed TLS", "VNet integration"]

  alternatives?: ServiceAlternative[];
  // Present when viable alternatives exist.
  // Omitted (or empty) when the recommended service is the clear best fit.

  mcpSourced: boolean;
  // true if this recommendation was grounded via MCP.
  // false triggers "unverified" flag in UI.

  learnUrl?: string;
  // Microsoft Learn documentation URL for the recommended service.
  // Example: "https://learn.microsoft.com/en-us/azure/app-service/overview"
}

interface ServiceAlternative {
  serviceName: string;
  // Alternative Azure service name.
  // Example: "Azure Container Apps"

  tradeOff: string;
  // Concise comparison statement (≤ 200 chars).
  // Example: "More flexible containerized hosting but requires Docker expertise;
  //           better for microservices, less suited for monolithic web apps."

  sku?: string;
  // Suggested SKU for the alternative, if applicable.

  learnUrl?: string;
  // Microsoft Learn documentation URL for the alternative.
}
```

**Example output:**

```json
[
  {
    "componentName": "Azure App Service",
    "serviceName": "Azure App Service",
    "sku": "P1v3",
    "region": "eastus2",
    "capabilities": [
      "Auto-scaling up to 30 instances",
      "Deployment slots for zero-downtime deployments",
      "Built-in authentication with Entra ID",
      "VNet integration for private backends"
    ],
    "alternatives": [
      {
        "serviceName": "Azure Container Apps",
        "tradeOff": "Better for microservices with per-container scaling; requires containerization; lower cost at small scale via scale-to-zero.",
        "sku": "Consumption",
        "learnUrl": "https://learn.microsoft.com/en-us/azure/container-apps/overview"
      },
      {
        "serviceName": "Azure Kubernetes Service",
        "tradeOff": "Full Kubernetes orchestration for complex multi-container workloads; higher operational overhead; overkill for simple web apps.",
        "sku": "Standard",
        "learnUrl": "https://learn.microsoft.com/en-us/azure/aks/intro-kubernetes"
      }
    ],
    "mcpSourced": true,
    "learnUrl": "https://learn.microsoft.com/en-us/azure/app-service/overview"
  },
  {
    "componentName": "Azure SQL Database",
    "serviceName": "Azure SQL Database",
    "sku": "S2 (50 DTU)",
    "region": "eastus2",
    "capabilities": [
      "Built-in high availability (99.99% SLA)",
      "Automated backups with point-in-time restore",
      "Advanced threat protection",
      "Elastic pools for multi-tenant scenarios"
    ],
    "alternatives": [
      {
        "serviceName": "Azure Cosmos DB",
        "tradeOff": "Global distribution and multi-model support; higher cost for relational patterns; best for document/NoSQL workloads.",
        "sku": "Serverless",
        "learnUrl": "https://learn.microsoft.com/en-us/azure/cosmos-db/introduction"
      }
    ],
    "mcpSourced": true,
    "learnUrl": "https://learn.microsoft.com/en-us/azure/azure-sql/database/sql-database-paas-overview"
  }
]
```

### 3.3 SKU Recommendation Logic

The Azure Specialist Agent selects SKUs based on the `scaleRequirements` from the input. The following heuristics apply:

#### 3.3.1 Compute Tier Selection

| Scale Signal | Low | Medium | High |
|---|---|---|---|
| Concurrent users | < 100 | 100–5,000 | > 5,000 |
| Requests/sec | < 50 | 50–1,000 | > 1,000 |
| **App Service SKU** | B1 (Basic) | S1–P1v3 (Standard/Premium) | P2v3–P3v3 (Premium) |
| **Container Apps** | Consumption | Consumption (scaled) | Dedicated |
| **AKS** | — | Standard (3 nodes) | Standard (5+ nodes) |

#### 3.3.2 Data Tier Selection

| Scale Signal | Low | Medium | High |
|---|---|---|---|
| Data volume | < 5 GB | 5–100 GB | > 100 GB |
| **Azure SQL SKU** | S0 (10 DTU) | S2–S4 (50–200 DTU) | P1–P4 (Premium) or vCore |
| **Cosmos DB** | Serverless | Autoscale (400–4000 RU/s) | Provisioned (manual RU/s) |

#### 3.3.3 Region Selection

1. Use `regionPreference` if provided and all required services are available in that region.
2. Otherwise, default to `eastus` (broadest service availability).
3. If a specific service is unavailable in the selected region, the agent selects the nearest region with availability and notes the deviation.

### 3.4 Trade-off Presentation

Trade-offs are presented in a structured comparison format:

| Aspect | Format |
|---|---|
| Recommended service | Shown as the primary selection with full details |
| Alternatives | Listed below with `serviceName` and `tradeOff` fields |
| Trade-off text | Single sentence comparing the alternative against the recommendation |
| Maximum alternatives | 3 per component (to avoid decision paralysis) |
| When to omit | No alternatives shown when the recommended service is the only viable option |

**Trade-off text pattern:**
> "{Alternative} offers {advantage} but {disadvantage} compared to {recommended}."

**Example:**
> "Azure Container Apps offers scale-to-zero cost savings and per-container scaling but requires containerization expertise compared to Azure App Service."

---

## 4. Microsoft Learn MCP Integration

Both agents use the [Microsoft Learn MCP Server](https://learn.microsoft.com/en-us/azure/ai-services/agents/how-to/tools/connected-agents) to ground their outputs in official Azure documentation.

### 4.1 MCP Query Format

Queries to the MCP Server follow this pattern:

```typescript
interface MCPQuery {
  tool: 'microsoft-learn';
  query: string;
  // Natural-language query scoped to Azure documentation.
  // Examples:
  //   "Azure App Service scaling limits and SKU comparison"
  //   "Azure SQL Database vs Cosmos DB for relational workloads"
  //   "Azure Front Door vs Application Gateway differences"

  filters?: {
    product?: string[];
    // Scope to specific Azure products.
    // Example: ["azure-app-service", "azure-sql-database"]
  };
}
```

**Query construction rules:**

| Agent | Query Pattern |
|---|---|
| System Architect | "Azure reference architecture for {workload type} with {key requirements}" |
| Azure Specialist | "Azure {service name} SKU comparison and capabilities for {scale requirements}" |

### 4.2 Response Processing

MCP responses are processed as follows:

1. **Extract relevant facts** — Service capabilities, SKU details, limits, best practices.
2. **Cross-reference** — Validate agent's built-in knowledge against MCP data.
3. **Cite sources** — Attach `learnUrl` to each service recommendation.
4. **Flag confidence** — Set `mcpSourced: true` on outputs grounded by MCP data.

### 4.3 Fallback Behavior

When the MCP Server is unavailable (timeout, error, network failure):

| Condition | Behavior |
|---|---|
| MCP request times out (> 10 s) | Agent proceeds with built-in knowledge |
| MCP returns error (4xx/5xx) | Agent proceeds with built-in knowledge |
| MCP returns empty results | Agent proceeds with built-in knowledge; logs warning |

**In all fallback cases:**

1. `metadata.mcpSourced` is set to `false` on the `ArchitectureOutput`.
2. Each `ServiceSelection` has `mcpSourced: false`.
3. The chat response includes a visible banner:

   > ⚠️ **Unverified — MCP source unavailable.** These recommendations are based on built-in knowledge and may not reflect the latest Azure documentation. Please verify against [Microsoft Learn](https://learn.microsoft.com/en-us/azure/).

4. `learnUrl` fields are still populated with best-effort URLs but marked as unverified.

### 4.4 Source Attribution

Every recommendation that uses MCP data includes:

| Attribution Field | Location | Example |
|---|---|---|
| `learnUrl` | `ServiceSelection` and `ServiceAlternative` | `https://learn.microsoft.com/en-us/azure/app-service/overview` |
| `mcpSourced` | `ServiceSelection` and `ArchitectureOutput.metadata` | `true` |
| Inline citation | Narrative text (§2.5) | "…as recommended in [Azure App Service documentation](https://learn.microsoft.com/…)." |

---

## 5. Modification Flow

The seller can request modifications to the generated architecture at any point after initial generation.

### 5.1 User Requests Change

**Input:** A natural-language modification request sent via the chat interface.

**Examples:**
- "Add a caching layer between the API and the database"
- "Replace Cosmos DB with Azure SQL"
- "Add Azure API Management in front of the App Service"
- "Remove the CDN, we don't need it"

**Constraints:**

| Constraint | Value |
|---|---|
| Max modification request length | 500 characters |
| Modifications per session | Unlimited |
| Concurrent modifications | Not supported — sequential only |

### 5.2 Delta Architecture Update

The System Architect Agent processes modifications as **delta updates**, not full regenerations:

1. **Parse intent** — Identify the type of modification:
   - `ADD` — New component or connection
   - `REMOVE` — Remove component or connection
   - `REPLACE` — Swap one service for another
   - `MODIFY` — Change properties of an existing component

2. **Apply delta** — Update the existing `ArchitectureOutput`:
   - Add/remove nodes and edges in `mermaidCode`
   - Add/remove entries in `components`
   - Update `narrative` to reflect changes

3. **Preserve unchanged elements** — Nodes, edges, and components not affected by the modification remain identical.

4. **Cascade to Azure Specialist** — After architecture modification, the Azure Specialist Agent re-evaluates service selections for affected components only.

### 5.3 Re-validation

After each modification:

1. **Mermaid validation** — Re-parse the updated diagram (same pipeline as §2.3.5).
2. **Constraint check** — Verify node count ≤ 30 after additions.
3. **Consistency check** — Ensure every `component` has a corresponding diagram node and vice versa.
4. **Service re-evaluation** — Azure Specialist re-runs on added/replaced components; existing selections for unchanged components are preserved.

**If the modification would exceed 30 nodes:**

> ⚠️ "This modification would result in {N} nodes, exceeding the 30-node limit. Consider consolidating related components or removing unused services first."

The modification is **rejected** and the previous architecture is preserved.

---

## 6. Diagram Export

### 6.1 Export Endpoint

```
GET /api/projects/:id/export/architecture
```

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `format` | `string` | `png` | Export format: `png` or `svg` |
| `width` | `number` | `1200` | Image width in pixels (PNG only; 400–4000) |
| `theme` | `string` | `default` | Mermaid theme: `default`, `dark`, `forest`, `neutral` |

**Headers:**

| Header | Value |
|---|---|
| `Authorization` | `Bearer {token}` |
| `Accept` | `image/png` or `image/svg+xml` |

**Responses:**

| Status | Content-Type | Body |
|---|---|---|
| `200` | `image/png` or `image/svg+xml` | Binary image data |
| `400` | `application/json` | `{ "error": "INVALID_FORMAT", "details": "Supported formats: png, svg" }` |
| `404` | `application/json` | `{ "error": "PROJECT_NOT_FOUND" }` |
| `404` | `application/json` | `{ "error": "NO_ARCHITECTURE", "details": "No architecture has been generated for this project" }` |
| `422` | `application/json` | `{ "error": "INVALID_MERMAID", "details": "Stored Mermaid code cannot be rendered" }` |
| `500` | `application/json` | `{ "error": "RENDER_FAILED", "details": "..." }` |

**Response headers (on success):**

| Header | Value |
|---|---|
| `Content-Disposition` | `attachment; filename="architecture-{projectId}.{format}"` |
| `Cache-Control` | `no-cache` |

### 6.2 Supported Formats

| Format | MIME Type | Use Case |
|---|---|---|
| PNG | `image/png` | Embedding in PowerPoint, email, documents |
| SVG | `image/svg+xml` | Scalable display on web, high-resolution print |

### 6.3 Rendering Pipeline

```
GET /api/projects/:id/export/architecture?format=png
        │
        ▼
┌─────────────────────┐
│ Retrieve project     │
│ from data store      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Extract mermaidCode  │
│ from architecture    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Validate Mermaid     │
│ syntax               │
└─────────┬───────────┘
          │ Valid
          ▼
┌─────────────────────┐     ┌─────────────────────┐
│ format === 'svg'?    │─Yes─▶│ Render via Mermaid   │
│                      │     │ mermaid.render()     │
│                      │     │ → Return SVG string  │
└─────────┬───────────┘     └─────────────────────┘
          │ No (PNG)
          ▼
┌─────────────────────┐
│ Render Mermaid → SVG │
│ Convert SVG → PNG    │
│ (via Playwright or   │
│  sharp/resvg)        │
└─────────┬───────────┘
          │
          ▼
   Return binary PNG
```

**Implementation notes:**

- SVG rendering uses the `@mermaid-js/mermaid-cli` or server-side `mermaid` library.
- PNG conversion uses headless Playwright (preferred for accuracy) or `sharp` with `resvg` (for lighter deployments).
- Rendering timeout: 15 seconds maximum. If exceeded, return `500 RENDER_FAILED`.

---

## 7. Frontend Behavior

### 7.1 Mermaid Rendering

The chat interface renders Mermaid diagrams inline within agent messages.

| Property | Implementation |
|---|---|
| Library | `mermaid` (client-side, loaded in `ChatMessage` component) |
| Trigger | Detect ` ```mermaid ` code fence in agent message content |
| Initialization | `mermaid.initialize({ theme: 'default', securityLevel: 'strict' })` |
| Container | `<div class="mermaid-container">` with max-width 100%, horizontal scroll on overflow |
| Interaction | Pan and zoom via mouse/touch; click node to highlight component in table |
| Fallback | If client-side rendering fails, show raw Mermaid code in a `<pre>` block with a "Copy" button |

**Accessibility:**

- Diagram has `role="img"` and `aria-label` set to the narrative summary (§2.5, first sentence).
- Component table (§7.2) serves as the accessible alternative to the visual diagram.

### 7.2 Component Table

Displayed below the rendered diagram in the chat message.

| Column | Source | Width |
|---|---|---|
| Component | `component.name` | 25% |
| Azure Service | `component.azureService` | 25% |
| Description | `component.description` | 40% |
| Category | `component.category` (as badge) | 10% |

**Behavior:**

- Sortable by Component name or Category.
- Clicking a row highlights the corresponding node in the Mermaid diagram (if supported by the rendering library).
- Category badges use Azure-branded colors per category.

### 7.3 Service Selection Display

The Azure Specialist Agent's output is rendered as an expandable card list.

**Collapsed state (default):**

```
┌─────────────────────────────────────────────┐
│ 🟦 Azure App Service          SKU: P1v3     │
│    Region: eastus2  ·  2 alternatives       │
│    ▸ Expand for details                     │
└─────────────────────────────────────────────┘
```

**Expanded state:**

```
┌─────────────────────────────────────────────┐
│ 🟦 Azure App Service          SKU: P1v3     │
│    Region: eastus2                           │
│                                              │
│    Capabilities:                             │
│    • Auto-scaling up to 30 instances         │
│    • Deployment slots for zero-downtime      │
│    • Built-in auth with Entra ID             │
│    • VNet integration                        │
│                                              │
│    Alternatives:                             │
│    ┌─ Azure Container Apps (Consumption)     │
│    │  Better for microservices with          │
│    │  scale-to-zero; requires containers.    │
│    ├─ Azure Kubernetes Service (Standard)    │
│    │  Full K8s orchestration; higher ops     │
│    │  overhead; overkill for simple apps.    │
│    └────────────────────────────────────     │
│                                              │
│    📄 Learn more ↗                           │
│    ▾ Collapse                                │
└─────────────────────────────────────────────┘
```

**Unverified banner:** If `mcpSourced: false`, an amber banner appears above the service cards:

> ⚠️ These recommendations are based on built-in knowledge. Verify against [Microsoft Learn](https://learn.microsoft.com/en-us/azure/).

### 7.4 Modification Input

The seller modifies the architecture using the existing chat input.

| Behavior | Detail |
|---|---|
| Trigger | Any message sent while architecture is displayed |
| Agent routing | Orchestrator detects modification intent and routes to System Architect Agent |
| Loading state | "Updating architecture…" with a shimmer overlay on the diagram |
| Success | Old diagram replaced with updated diagram; diff changes highlighted briefly (2 s fade) |
| Failure | Error toast; previous architecture remains unchanged |
| Suggested modifications | Quick-action chips below the diagram: "Add caching", "Add monitoring", "Add API gateway" |

---

## 8. Error Responses

| Error Code | HTTP | Trigger | User-Facing Message |
|---|---|---|---|
| `INVALID_PROJECT_ID` | 400 | Malformed or missing project ID | "Invalid project. Please start a new session." |
| `EMPTY_REQUIREMENTS` | 400 | No requirements in ProjectContext | "No requirements found. Please complete the envisioning step first." |
| `INVALID_MODIFICATION` | 400 | Modification request exceeds 500 chars or is empty | "Please provide a shorter modification request (max 500 characters)." |
| `MERMAID_SYNTAX_ERROR` | 422 | Mermaid code invalid after 2 retries | "The architecture diagram could not be rendered. Here is the raw diagram code:" (followed by code block) |
| `NODE_LIMIT_EXCEEDED` | 422 | Diagram exceeds 30 nodes after modification | "This architecture exceeds the 30-component limit. Please simplify or consolidate components." |
| `MCP_UNAVAILABLE` | 200 | MCP Server unreachable (degraded, not error) | ⚠️ banner (§4.3); response still returned |
| `PROJECT_NOT_FOUND` | 404 | Export for non-existent project | "Project not found." |
| `NO_ARCHITECTURE` | 404 | Export before architecture generated | "No architecture has been generated for this project yet." |
| `INVALID_FORMAT` | 400 | Export format not `png` or `svg` | "Unsupported format. Use 'png' or 'svg'." |
| `RENDER_FAILED` | 500 | Server-side Mermaid rendering fails | "Architecture export failed. Please try again or use the in-chat diagram." |
| `AGENT_TIMEOUT` | 504 | Agent does not respond within 60 s | "The architect agent is taking too long. Please try again." |

---

## 9. Edge Cases

### 9.1 Invalid Mermaid Syntax

- **Trigger:** Agent generates syntactically invalid Mermaid code.
- **Behavior:** Retry generation up to 2 times, providing the parse error in the re-prompt. After 2 failures, return raw Mermaid code with error explanation.
- **UI:** Display raw code in a `<pre>` block with a "Copy" button and an error message explaining the issue.
- **Logging:** Log all retry attempts with error details for agent prompt improvement.

### 9.2 MCP Server Timeout

- **Trigger:** MCP Server does not respond within 10 seconds.
- **Behavior:** Agent proceeds with built-in knowledge. All outputs flagged as `mcpSourced: false`.
- **UI:** Amber "unverified" banner shown.
- **Retry:** No automatic retry of MCP queries; user can manually request "re-check with docs" via chat.

### 9.3 Empty Architecture

- **Trigger:** Requirements are too vague for the agent to generate a meaningful architecture.
- **Behavior:** Agent responds with a clarification request listing what additional information is needed rather than generating a minimal/incorrect architecture.
- **UI:** Chat message with clarifying questions, no diagram rendered.

### 9.4 Exceeding 30-Node Limit (R-5)

- **Trigger:** Requirements imply a complex architecture exceeding 30 components.
- **Behavior:** Agent consolidates related services into logical groups (e.g., "Monitoring Stack" for Log Analytics + App Insights + Alerts). If still > 30, agent proposes splitting into multiple diagrams covering subsystems.
- **UI:** If split, diagrams are shown sequentially with a tab selector.

### 9.5 Unsupported Azure Services

- **Trigger:** User requests a service that does not exist or is in private preview.
- **Behavior:** Agent flags the service as unavailable and suggests the closest GA alternative with an explanation.
- **UI:** Warning inline with the suggestion: "⚠️ {Service} is not currently available. Consider {alternative} instead."

### 9.6 Conflicting Requirements

- **Trigger:** User requirements conflict (e.g., "serverless" + "dedicated VMs", "lowest cost" + "premium SLA").
- **Behavior:** Agent identifies the conflict, explains the trade-off, and asks the seller to choose a direction before generating the architecture.
- **UI:** Chat message listing the conflicts as a numbered list with recommended resolution options.

### 9.7 Modification Causes Inconsistency

- **Trigger:** User modification creates an invalid architecture (e.g., removing a database that other components depend on).
- **Behavior:** Agent detects the dependency and warns: "Removing {component} will break connections from {dependent components}. Would you like to also remove/replace those components?"
- **UI:** Confirmation prompt with affected components listed.

### 9.8 Region Unavailability

- **Trigger:** Recommended Azure service is not available in the preferred region.
- **Behavior:** Azure Specialist selects the nearest available region and notes the deviation in the `ServiceSelection`.
- **UI:** Info badge on the affected service card: "ℹ️ Deployed to {fallback region} — not available in {preferred region}."

### 9.9 Concurrent Architecture and Service Selection

- **Trigger:** User sends a modification while the Azure Specialist is still processing.
- **Behavior:** The current Azure Specialist run is cancelled. The modification is applied to the architecture, and a new Azure Specialist run is triggered on the updated architecture.

---

## Traceability

| FRD Requirement | PRD Reference | Data Model | API Endpoint |
|---|---|---|---|
| §2 System Architect Agent | US-3 (Architecture Generation) | `ArchitectureOutput` | `POST /api/projects/:id/chat` |
| §2.3 Mermaid Generation | US-3 AC: "Mermaid diagram" | `ArchitectureOutput.mermaidCode` | — |
| §2.3.5 Validation & Retry | US-3 AC: "retries up to 2 times" | `metadata.retryCount` | — |
| §2.3.2 Node Limit | R-5 (Max 30 Nodes) | `metadata.nodeCount` | — |
| §2.4 Component List | US-3 AC: "Key components listed" | `ArchitectureComponent[]` | — |
| §3 Azure Specialist Agent | US-4 (Azure Service Selection) | `ServiceSelection[]` | `POST /api/projects/:id/chat` |
| §3.3 SKU Recommendation | US-4 AC: "SKU recommendation" | `ServiceSelection.sku` | — |
| §3.4 Trade-offs | US-4 AC: "alternatives with trade-offs" | `ServiceAlternative[]` | — |
| §4 MCP Integration | US-3/US-4 AC: "Microsoft Learn MCP" | `mcpSourced` flag | MCP Server |
| §4.3 Fallback | US-3/US-4 AC: "falls back to built-in" | `mcpSourced: false` | — |
| §5 Modification Flow | US-3 AC: "request modifications" | `modificationRequest` | `POST /api/projects/:id/chat` |
| §6 Diagram Export | US-3 AC: "exportable as PNG/SVG" | `ArchitectureOutput.mermaidCode` | `GET /api/projects/:id/export/architecture` |
| §4.4 Source Attribution | US-4 AC: "backed by Microsoft Learn" | `learnUrl`, `mcpSourced` | — |
