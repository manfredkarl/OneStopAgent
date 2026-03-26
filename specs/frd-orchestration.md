# FRD-ORCHESTRATION: Agent Orchestration

| Field         | Value                                |
|---------------|--------------------------------------|
| Status        | Draft                                |
| Author        | spec2cloud                           |
| Created       | 2025-07-18                           |
| PRD Reference | specs/prd.md — FR-1, FR-2, FR-3, US-1, US-8, US-9 |
| Priority      | P0 — Critical Path                   |

---

## 1. Overview

This FRD specifies the **Project Manager (PM) Agent** and the **agent orchestration pipeline** that forms the execution backbone of OneStopAgent. The PM Agent is the single entry point for all user interactions: it classifies intent, gathers requirements through structured questioning, activates specialist agents in sequence, enforces approval gates between stages, and manages error recovery.

**Scope:** Agent registry, pipeline state machine, PM Agent behavior, inter-agent communication contracts, concurrency controls, timeout policies, and error handling.

**Out of scope:** Individual specialist agent internals (covered by their own FRDs), UI rendering of agent outputs, authentication/authorization (FRD-Auth), data persistence layer (FRD-Data).

### 1.1 Definitions

| Term | Definition |
|------|-----------|
| **Pipeline** | The ordered sequence of agent stages that transforms a user idea into deliverables. |
| **Stage** | A discrete step in the pipeline, bound to one agent. |
| **Gate** | An approval checkpoint between stages where the seller must review output and approve before the pipeline advances. |
| **ProjectContext** | The accumulated state object that grows as each agent appends its output. |
| **Agent Invocation** | The act of the PM Agent calling a specialist agent with a scoped prompt and context slice. |
| **Hard Timeout** | 120 s — the absolute maximum wall-clock time an agent may run before forced termination. |
| **Soft Timeout** | 30 s — the threshold after which the system begins streaming partial results to the UI. |

---

## 2. Agent Registry

### 2.1 Agent Definitions

| agentId | displayName | role | required | defaultActive | pipelineOrder | integrations |
|---------|------------|------|----------|---------------|---------------|-------------|
| `pm` | Project Manager | Orchestrates flow, classifies input, asks structured questions, routes to specialists | Yes (implicit — always active) | true | 0 | All other agents |
| `envisioning` | Envisioning Agent | Suggests use cases, value drivers, reference scenarios for vague inputs | No | false | 1 | Internal knowledge base (simulated) |
| `architect` | System Architect | Generates Mermaid architecture diagrams, maps components to Azure services | **Yes** | true | 2 | Microsoft Learn MCP Server |
| `azure` | Azure Specialist | Selects Azure services, recommends SKUs, regions, trade-offs | No | true | 3 | Microsoft Learn MCP Server |
| `cost` | Cost Specialist | Estimates monthly/annual costs based on architecture and service selections | No | true | 4 | Azure Retail Prices REST API |
| `value` | Business Value | Evaluates ROI, business impact, produces executive summary | No | true | 5 | Internal knowledge base (simulated) |
| `presentation` | Presentation Agent | Compiles all agent outputs into a downloadable PowerPoint deck | No | true | 6 | All agent outputs, PptxGenJS |

**Constraints:**
- `pm` is **never** listed in the sidebar agent panel; it is the system itself.
- `architect` **cannot** be deactivated (PRD US-8 AC-3). Any `PATCH` request to set `architect.active = false` returns `400 Bad Request` with message: `"System Architect is required and cannot be deactivated."`.
- All other agents may be toggled on/off at any time. Deactivating a `Working` agent triggers the **Cancel & Warn** flow (§3.3).

### 2.2 Agent Lifecycle States

Each agent instance (scoped to a project) has exactly one of these states at any time:

```
                  ┌────────────────────────────────────────────────┐
                  │                                                │
                  ▼                                                │
            ┌──────────┐    invoke()    ┌───────────┐              │
  ─────────►│   Idle   │──────────────►│  Working  │──────────────┘
            │  (grey)  │               │ (anim blue)│    cancel()
            └──────────┘               └─────┬──────┘
                  ▲                          │
                  │       ┌──────────────────┼──────────────────┐
                  │       │ success()        │ failure()        │
                  │       ▼                  ▼                  │
                  │  ┌──────────┐      ┌──────────┐            │
                  │  │ Complete │      │  Error   │            │
                  │  │  (green) │      │  (red)   │            │
                  │  └────┬─────┘      └────┬─────┘            │
                  │       │                 │                   │
                  │       │ reset()         │ retry() / skip()  │
                  └───────┴─────────────────┘                  │
                                                               │
                  NOTE: cancel() transitions Working → Idle     │
                        only when agent is deactivated          │
                        mid-execution (§3.3)                    │
```

**State transition table:**

| From | Event | To | Side Effects |
|------|-------|----|-------------|
| Idle | `invoke(agentId, context)` | Working | Agent begins processing; UI shows animated spinner. |
| Working | `success(agentId, output)` | Complete | Output appended to `ProjectContext`; gate presented to seller. |
| Working | `failure(agentId, error)` | Error | PM notifies seller with error details and recovery options. |
| Working | `cancel(agentId)` | Idle | Running task aborted; partial output discarded. |
| Complete | `reset(agentId)` | Idle | Output cleared from `ProjectContext` (used on re-run). |
| Error | `retry(agentId)` | Working | Same invocation re-executed (max 2 retries). |
| Error | `skip(agentId)` | Idle | Agent skipped; pipeline advances to next active stage. |

**Invariants:**
- Only one agent may be in `Working` state per project at any time (sequential pipeline).
- `pm` does not have a visible lifecycle state — it is always implicitly active.
- `Complete` is a visual-only state in the sidebar; logically the agent returns to `Idle` once the pipeline moves past it.

---

## 3. Pipeline State Machine

### 3.1 Pipeline Stages

The pipeline is an ordered list of stages. Each stage maps 1:1 to an agent. The PM Agent walks the pipeline from stage 0 forward, skipping inactive agents.

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 0: PM — Input Classification & Structured Questioning    │
│  (always runs; not gated)                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │ isVague?                     │
              ▼ Yes                          ▼ No
┌──────────────────────────┐    ┌──────────────────────────────┐
│  Stage 1: Envisioning    │    │  (skip to Stage 2)           │
│  (optional — if active)  │    │                              │
└────────────┬─────────────┘    └──────────────┬───────────────┘
             │ Gate: Approve & Continue                │
             └──────────────┬──────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 2: System Architect  (REQUIRED — always runs)             │
│  Produces: ArchitectureOutput (Mermaid + components + narrative)  │
└────────────────────────────┬─────────────────────────────────────┘
                             │ Gate: Approve & Continue
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 3: Azure Specialist  (if active)                          │
│  Produces: ServiceSelection[]                                    │
└────────────────────────────┬─────────────────────────────────────┘
                             │ Gate: Approve & Continue
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 4: Cost Specialist  (if active)                           │
│  Produces: CostEstimate                                          │
└────────────────────────────┬─────────────────────────────────────┘
                             │ Gate: Approve & Continue
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 5: Business Value  (if active)                            │
│  Produces: ValueAssessment                                       │
└────────────────────────────┬─────────────────────────────────────┘
                             │ Gate: Approve & Continue
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 6: Presentation  (if active)                              │
│  Produces: PPTX file (downloadable)                              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
                     Pipeline Complete
                  project.status = 'completed'
```

### 3.2 Stage Transitions

Each gate follows an identical protocol:

1. **Agent completes** → PM receives structured output.
2. **PM posts output to chat** → Rendered as an agent-branded card (Mermaid diagram, table, summary, etc.).
3. **PM posts gate prompt** → A message containing:
   - Summary of what was produced.
   - **"Approve & Continue"** button (primary action).
   - **"Request Changes"** text option — seller can type feedback; PM re-invokes the same agent with the feedback appended to context.
   - **"Skip"** text option — available for non-required agents only.
4. **Seller clicks "Approve & Continue"** → PM:
   a. Sets current agent state to `Idle`.
   b. Persists output into `ProjectContext`.
   c. Resolves the next active stage (skipping deactivated agents).
   d. Invokes the next agent.
5. **Seller types "Request Changes"** → PM re-invokes the current agent with the original context plus seller feedback. The agent produces a revised output. The gate is re-presented. Maximum **3 revision cycles** per stage before PM warns and suggests approving or skipping.

**State representation:**

```typescript
interface PipelineState {
  projectId: string;
  currentStageIndex: number;        // 0–6
  stages: StageState[];
  status: 'questioning' | 'running' | 'gated' | 'completed' | 'error';
}

interface StageState {
  agentId: string;
  active: boolean;                  // can be toggled by seller
  status: 'pending' | 'running' | 'complete' | 'skipped' | 'error';
  output?: AgentOutput;             // populated on completion
  revisionCount: number;            // 0–3
  startedAt?: Date;
  completedAt?: Date;
  errorDetail?: string;
}
```

### 3.3 Skip Logic

An agent may be skipped in two ways:

**A. Agent deactivated before its stage is reached:**
- PM simply advances past that stage. No invocation, no gate.
- Stage status set to `skipped`.

**B. Agent deactivated while in `Working` state (mid-execution):**
1. PM calls `cancel(agentId)` — forcibly terminates the running agent task.
2. Any partial output is **discarded** (not persisted).
3. A warning message is posted to chat:
   > ⚠️ **{displayName}** was deactivated while working. Any in-progress output has been discarded. The pipeline will continue to the next active agent.
4. Stage status set to `skipped`.
5. PM resolves and invokes the next active stage.

**C. Agent skipped via error recovery (§3.4):**
- Seller selects "Skip" from error recovery options.
- Stage status set to `skipped`.
- PM advances.

**Downstream impact of skips:**

| Skipped Agent | Impact on Downstream |
|---------------|---------------------|
| Envisioning | None — PM proceeds with whatever context was gathered from structured questions. |
| System Architect | **Pipeline halts.** System Architect is required. Cannot be skipped. |
| Azure Specialist | Cost Specialist receives architecture components but no SKU selections. Cost agent uses default/general-purpose SKUs and flags estimates as `approximate`. |
| Cost Specialist | Business Value agent proceeds without cost data. Value assessment omits ROI calculations and notes the gap. |
| Business Value | Presentation agent omits the business value slide(s). |
| Presentation | Pipeline completes without a downloadable deck. Seller can still view all outputs in chat. |

### 3.4 Error Recovery

When an agent enters `Error` state, the PM Agent presents the seller with a structured error notification:

```
┌──────────────────────────────────────────────────────────┐
│  ❌  {displayName} encountered an error                  │
│                                                          │
│  Error: {user-friendly error message}                    │
│                                                          │
│  What would you like to do?                              │
│                                                          │
│  [🔄 Retry]     [⏭️ Skip & Continue]     [🛑 Stop]       │
└──────────────────────────────────────────────────────────┘
```

**Recovery flows:**

| Option | Behavior |
|--------|----------|
| **Retry** | PM re-invokes the agent with the same context. Retry count incremented. After **2 failed retries** (3 total attempts), auto-escalate: disable the Retry button, show only Skip & Stop. |
| **Skip & Continue** | Agent state → `Idle`, stage status → `skipped`. PM advances to next active stage. Available for all agents **except** `architect`. |
| **Stop Pipeline** | All agent states → `Idle`. `PipelineState.status` → `error`. `project.status` → `error`. Seller can later resume or start a new project. |

**Automatic escalation for required agents:**

If `architect` fails after 3 attempts:
- "Skip & Continue" is **not offered** (agent is required).
- PM posts: `"The System Architect is required to proceed. You can retry or stop the pipeline. If the problem persists, please contact support."`
- `project.status` set to `error` only at this point (unrecoverable).

**project.status transition rules:**

| Condition | project.status |
|-----------|---------------|
| Pipeline running normally | `in_progress` |
| Pipeline completed all stages | `completed` |
| Non-required agent fails & seller skips | `in_progress` (continues) |
| Non-required agent fails & seller stops | `error` |
| Required agent (`architect`) exhausts retries & seller stops | `error` |
| Required agent (`architect`) exhausts retries (auto) | `error` |

---

## 4. Project Manager Agent Behavior

### 4.1 Input Classification

When a seller sends the **first message** of a new project, the PM Agent classifies the input into one of two categories:

**Classification prompt (system prompt excerpt):**
```
You are the Project Manager for OneStopAgent. Analyze the seller's input and classify it:

CLEAR: The input describes a specific technical workload with enough detail to begin 
       architecture design (e.g., mentions specific services, workload patterns, 
       scale requirements, or a concrete business problem with technical implications).

VAGUE: The input is high-level, aspirational, or lacks technical specificity 
       (e.g., "AI for healthcare", "modernize our apps", "something with IoT").

Respond with exactly one word: CLEAR or VAGUE
```

**Routing logic:**

```
IF classification == VAGUE AND envisioning.active == true:
    → Route to Envisioning Agent (Stage 1)
ELIF classification == VAGUE AND envisioning.active == false:
    → PM conducts extended structured questioning (§4.2) to gather specifics
    → Then proceed to Stage 2 (System Architect)
ELIF classification == CLEAR:
    → PM conducts brief structured questioning (§4.2) to fill gaps
    → Then proceed to Stage 2 (System Architect)
```

**Edge case — reclassification:** If the Envisioning Agent's output still lacks technical specificity, the PM does **not** loop back to Envisioning. Instead, it proceeds to structured questioning to fill remaining gaps, then advances to the System Architect with the best available context.

### 4.2 Structured Questioning

The PM Agent asks focused questions to build the `ProjectContext.requirements` map. Questions are:
- **Incremental** — each question builds on prior answers.
- **Skippable** — seller can type "skip" or press a "Skip Question" button to accept the default.
- **Capped at 10** — the PM asks at most 10 questions before proceeding, regardless of completeness.
- **Adaptive** — questions already answered by the initial input or Envisioning output are skipped.

**Question catalog (ordered by priority):**

| # | questionId | Question | Default (if skipped) | Required Context |
|---|-----------|----------|---------------------|-----------------|
| 1 | `workload_type` | What type of workload are you building? (e.g., web app, data pipeline, IoT, AI/ML, migration) | Inferred from input | — |
| 2 | `customer_industry` | What industry is the customer in? | "General / Not specified" | — |
| 3 | `user_scale` | How many users or transactions do you expect? (e.g., 100 users, 10K requests/day) | "Medium scale (~1,000 users)" | — |
| 4 | `region` | What Azure region(s) should be prioritized? | "East US" | — |
| 5 | `compliance` | Are there specific compliance requirements? (e.g., HIPAA, FedRAMP, GDPR) | "No specific compliance requirements" | — |
| 6 | `existing_infra` | Does the customer have existing Azure infrastructure? | "Greenfield deployment" | — |
| 7 | `budget_range` | Is there an approximate monthly budget range? | "No budget constraint specified" | — |
| 8 | `timeline` | What is the expected deployment timeline? | "Standard timeline (3–6 months)" | — |
| 9 | `integration_points` | Are there external systems to integrate with? (e.g., SAP, Salesforce, on-prem databases) | "No external integrations" | — |
| 10 | `special_requirements` | Any other requirements or constraints? | "None" | — |

**Questioning algorithm:**

```pseudocode
function conductQuestioning(initialInput, envisioningOutput?):
    answeredKeys = extractAnsweredKeys(initialInput, envisioningOutput)
    questionsToAsk = QUESTION_CATALOG.filter(q => q.questionId NOT IN answeredKeys)
    questionsAsked = 0

    for question in questionsToAsk:
        if questionsAsked >= 10:
            break
        
        post question to chat
        response = await sellerResponse()
        
        if response.isSkip():
            context.requirements[question.questionId] = question.default
        else:
            context.requirements[question.questionId] = response.text
        
        questionsAsked++
        
        // Early exit: if enough context for architecture
        if hasMinimumContext(context):
            post "I have enough information to proceed. Shall I begin?" 
            if sellerConfirms():
                break
    
    return context
```

**`hasMinimumContext` criteria:** At minimum, `workload_type` and `user_scale` must be answered (explicitly or via defaults) before the PM proceeds to the System Architect.

### 4.3 Context Assembly

The PM Agent maintains the `ProjectContext` object and assembles it incrementally:

```typescript
interface ProjectContext {
  // Populated during structured questioning (§4.2)
  requirements: Record<string, string>;

  // Populated by Envisioning Agent (Stage 1) — optional
  envisioningSelections?: string[];

  // Populated by System Architect (Stage 2)
  architecture?: ArchitectureOutput;

  // Populated by Azure Specialist (Stage 3)
  services?: ServiceSelection[];

  // Populated by Cost Specialist (Stage 4)
  costEstimate?: CostEstimate;

  // Populated by Business Value (Stage 5)
  businessValue?: ValueAssessment;

  // Metadata
  customerName?: string;
  projectDescription: string;     // original user input
  classificationResult: 'CLEAR' | 'VAGUE';
}
```

**Context persistence rules:**
- `ProjectContext` is persisted to the data store after **every** successful agent completion (gate approval).
- On pipeline resume (after browser refresh or session reconnect), the PM reads `ProjectContext` and the `PipelineState` to determine where to continue.
- If a seller requests changes at a gate and the agent re-runs, the **previous output is overwritten** — only the latest approved output is retained.

### 4.4 Agent Invocation Protocol

The PM Agent invokes each specialist via a standardized protocol:

**Invocation request:**

```typescript
interface AgentInvocationRequest {
  agentId: string;
  projectId: string;
  context: ContextSlice;           // subset of ProjectContext relevant to this agent
  systemPrompt: string;            // agent-specific system prompt (see §5.2)
  tools?: ToolDefinition[];        // MCP tools available to this agent
  timeout: {
    softMs: 30_000;
    hardMs: 120_000;
  };
  metadata: {
    invocationId: string;          // UUID for tracing
    attemptNumber: number;         // 1 = first try, 2 = first retry, 3 = second retry
    sellerFeedback?: string;       // if this is a revision request
  };
}
```

**Context slices per agent:**

| Agent | Context Slice (input) |
|-------|----------------------|
| `envisioning` | `{ requirements (partial), projectDescription }` |
| `architect` | `{ requirements, envisioningSelections?, projectDescription }` |
| `azure` | `{ requirements, architecture }` |
| `cost` | `{ requirements, architecture, services }` — if `services` is missing (Azure Specialist skipped), uses `architecture.components` with default SKUs |
| `value` | `{ requirements, architecture, services?, costEstimate? }` |
| `presentation` | `{ requirements, architecture, services?, costEstimate?, businessValue?, customerName }` — full context |

**Invocation response:**

```typescript
interface AgentInvocationResponse {
  agentId: string;
  invocationId: string;
  status: 'success' | 'error';
  output?: AgentOutput;            // structured output (§5.2)
  chatMessages: ChatMessage[];     // messages to post to the chat UI
  error?: {
    code: string;                  // machine-readable (see §7)
    message: string;               // user-friendly
    retryable: boolean;
  };
  metrics: {
    durationMs: number;
    tokensUsed: number;
    toolCallCount: number;
  };
}
```

---

## 5. Inter-Agent Communication

### 5.1 Context Passing

Agents do **not** communicate directly. All communication flows through the PM Agent via `ProjectContext`:

```
Seller ──► PM Agent ──► Specialist Agent
                  ▲            │
                  │            ▼
              ProjectContext (read/write)
```

**Data flow per pipeline transition:**

```
Stage 0 (PM)        →  requirements: Record<string, string>
                        projectDescription: string
                        classificationResult: 'CLEAR' | 'VAGUE'
                        
Stage 1 (Envisioning) → envisioningSelections: string[]
                         (appended to context)

Stage 2 (Architect)   → architecture: ArchitectureOutput
                         (appended to context)

Stage 3 (Azure)       → services: ServiceSelection[]
                         (appended to context)

Stage 4 (Cost)        → costEstimate: CostEstimate
                         (appended to context)

Stage 5 (Value)       → businessValue: ValueAssessment
                         (appended to context)

Stage 6 (Presentation)→ pptxUrl: string  (download link)
                         (appended to context, file stored separately)
```

**Immutability rule:** Once an agent's output is approved at a gate, downstream agents receive it as **read-only** context. If a seller goes back to revise a previous stage's output (future feature — out of MVP scope), the pipeline must re-run all downstream stages.

### 5.2 Output Schema per Agent

Each agent must return output conforming to its schema. The PM Agent validates the output before presenting it at the gate.

#### 5.2.1 Envisioning Agent Output

```typescript
interface EnvisioningOutput {
  agentId: 'envisioning';
  useCases: {
    id: string;
    title: string;
    description: string;
    valueDrivers: string[];
    referenceScenario?: string;
  }[];
  recommendedUseCase: string;       // id of the top recommendation
  sellerSelections: string[];       // ids selected by seller (populated after interaction)
}
```

**Chat rendering:** Numbered list of use cases with radio-button selection. Seller picks one or more, then confirms.

#### 5.2.2 System Architect Output

```typescript
interface ArchitectureOutput {
  agentId: 'architect';
  mermaidCode: string;              // valid Mermaid graph/flowchart syntax
  components: {
    name: string;
    azureService: string;           // recommended Azure service name
    description: string;
    tier: 'compute' | 'storage' | 'networking' | 'ai' | 'data' | 'security' | 'integration';
  }[];
  narrative: string;                // prose explanation of the architecture
  designDecisions: {
    decision: string;
    rationale: string;
    alternatives: string[];
  }[];
}
```

**Validation rules:**
- `mermaidCode` must parse without errors (server-side validation via mermaid.js).
- Max 30 nodes in the diagram (PRD R-5).
- `components` array must be non-empty.
- Each `azureService` must be a recognized Azure service name.

#### 5.2.3 Azure Specialist Output

```typescript
interface AzureSpecialistOutput {
  agentId: 'azure';
  services: ServiceSelection[];
}

interface ServiceSelection {
  componentName: string;            // must match an ArchitectureOutput.component.name
  serviceName: string;              // Azure service name
  sku: string;                      // specific SKU (e.g., "S1", "P1v3")
  region: string;                   // Azure region (e.g., "eastus")
  capabilities: string[];           // key capabilities of this selection
  justification: string;            // why this SKU was chosen
  alternatives?: {
    serviceName: string;
    sku: string;
    tradeOff: string;               // e.g., "Lower cost but reduced throughput"
  }[];
}
```

**Validation rules:**
- Every `componentName` must reference a component from `ArchitectureOutput.components`.
- `sku` and `region` must be valid Azure identifiers.

#### 5.2.4 Cost Specialist Output

```typescript
interface CostEstimateOutput {
  agentId: 'cost';
  currency: 'USD';
  items: {
    serviceName: string;
    sku: string;
    region: string;
    monthlyCost: number;            // in USD
    assumptions: string;            // e.g., "730 hours/month, 50% utilization"
    pricingSource: 'live' | 'cached' | 'approximate';
  }[];
  totalMonthly: number;
  totalAnnual: number;
  assumptions: string[];            // global assumptions
  generatedAt: Date;
  cacheAge?: number;                // seconds since last live fetch, if cached
}
```

**Validation rules:**
- `totalMonthly` must equal sum of `items[].monthlyCost` (within ±$0.01 for rounding).
- `totalAnnual` must equal `totalMonthly * 12`.
- At least one item must be present.

#### 5.2.5 Business Value Output

```typescript
interface ValueAssessmentOutput {
  agentId: 'value';
  drivers: {
    name: string;
    impact: 'High' | 'Medium' | 'Low';
    quantifiedEstimate?: string;    // e.g., "Save 40 hours/month in manual processing"
    category: 'cost_savings' | 'revenue_growth' | 'risk_reduction' | 'operational_efficiency';
  }[];
  executiveSummary: string;         // 2–4 paragraphs, suitable for CxO audience
  benchmarks: string[];             // industry comparisons
  roiEstimate?: {
    investmentCost: number;         // from CostEstimate.totalAnnual
    projectedBenefit: number;       // estimated annual benefit
    paybackMonths: number;
    roiPercentage: number;          // ((benefit - cost) / cost) * 100
  };
}
```

**Validation rules:**
- `executiveSummary` must be between 200 and 2000 characters.
- If `CostEstimate` is available, `roiEstimate` should be populated.

#### 5.2.6 Presentation Agent Output

```typescript
interface PresentationOutput {
  agentId: 'presentation';
  pptxUrl: string;                  // signed download URL (expires in 1 hour)
  slideCount: number;               // max 20
  slideTitles: string[];            // ordered list of slide titles
  generatedAt: Date;
}
```

**Validation rules:**
- `slideCount` must be ≤ 20 (PRD R-7).
- `pptxUrl` must be a valid, accessible URL.
- `slideTitles.length` must equal `slideCount`.

---

## 6. Concurrency & Timeout

### 6.1 Timeout Policy

| Threshold | Duration | Behavior |
|-----------|----------|----------|
| **Soft timeout** | 30 seconds | System begins streaming partial progress messages to the chat. PM posts: `"⏳ {displayName} is still working… Here's what we have so far:"` followed by any partial output available. |
| **Hard timeout** | 120 seconds | Agent forcibly terminated. State → `Error`. PM presents error recovery options (§3.4). Error code: `AGENT_TIMEOUT`. |

**Progress streaming implementation:**
- At the soft timeout boundary, the PM queries the agent's in-progress output buffer.
- If the agent supports streaming (via Azure AI Foundry streaming responses), tokens are forwarded to the chat in real time from the start, and the soft timeout simply continues streaming.
- If the agent does not support streaming, the PM posts a "still working" indicator and waits until hard timeout or completion.

**Per-agent timeout overrides:**

| Agent | Soft (s) | Hard (s) | Rationale |
|-------|----------|----------|-----------|
| `envisioning` | 30 | 120 | Standard |
| `architect` | 30 | 120 | May produce complex diagrams |
| `azure` | 30 | 120 | MCP tool calls may add latency |
| `cost` | 15 | 60 | Azure Retail Prices API calls should be fast; API has its own 10s timeout (PRD NFR-2) |
| `value` | 30 | 120 | Standard |
| `presentation` | 45 | 180 | PPTX generation is I/O-intensive; extended hard timeout |

### 6.2 Concurrency Limits

| Scope | Limit | Enforcement |
|-------|-------|-------------|
| **Agents per project** | 1 concurrent | Sequential pipeline — only one agent runs at a time per project. |
| **Projects per user** | 3 concurrent `in_progress` projects | Creating a 4th project returns `429 Too Many Requests` with message: `"You have reached the maximum of 3 active projects. Please complete or delete an existing project."` |
| **Global agent pool** | 50 concurrent agent invocations | When the pool is exhausted, new invocations are queued (FIFO). Queue depth: max 100. If queue is full, return `503 Service Unavailable`. |
| **Per-user concurrency** | 2 concurrent agent invocations (across all their projects) | Prevents a single user from monopolizing the agent pool. |
| **API rate limit** | 60 requests/min per user (PRD FR-8) | Applies to all `/api/*` endpoints. Returns `429` with `Retry-After` header. |

**Queuing behavior:**
1. Invocation request arrives → check per-user limit (≤2 active) → check global pool (≤50 active).
2. If both pass → invoke immediately.
3. If per-user exceeded → queue with position, notify via chat: `"Your request is queued (position #{n}). Estimated wait: ~{seconds}s."`
4. If global pool exceeded → queue globally. Same notification.
5. Queue timeout: 60 seconds. If invocation not started within 60s, return `QUEUE_TIMEOUT` error.

---

## 7. Error Catalog

| Error Code | Agent(s) | User Message | Retryable | Recovery Options |
|------------|----------|-------------|-----------|-----------------|
| `AGENT_TIMEOUT` | Any | "{Agent} took too long to respond and was stopped." | Yes (2 retries) | Retry, Skip*, Stop |
| `AGENT_INTERNAL_ERROR` | Any | "{Agent} encountered an unexpected error." | Yes (2 retries) | Retry, Skip*, Stop |
| `MCP_UNAVAILABLE` | architect, azure | "Microsoft Learn documentation service is temporarily unavailable. Results may be less detailed." | Yes (2 retries) | Retry, Skip*, Stop |
| `PRICING_API_ERROR` | cost | "Unable to fetch live Azure pricing. Estimates will use cached data." | Yes (1 retry, then fallback to cache) | Auto-fallback, Retry, Skip, Stop |
| `PRICING_API_STALE` | cost | "Live pricing unavailable. Using cached prices from {date}. Estimates are approximate." | No (informational) | Continue (auto) |
| `MERMAID_INVALID` | architect | "The generated architecture diagram has syntax errors and is being regenerated." | Yes (auto-retry, 2 max) | Auto-retry, then manual Retry, Stop |
| `MERMAID_TOO_COMPLEX` | architect | "The architecture diagram exceeds the 30-component limit. Simplifying…" | Yes (auto-retry with constraint) | Auto-retry, then manual Retry, Stop |
| `PPTX_GENERATION_FAILED` | presentation | "PowerPoint generation failed. You can still view all outputs in the chat." | Yes (2 retries) | Retry, Skip, Stop |
| `PPTX_TOO_LARGE` | presentation | "The presentation exceeds the 20-slide limit. Content has been consolidated." | Yes (auto-retry with truncation) | Auto-retry, then Retry, Stop |
| `CONTEXT_INSUFFICIENT` | architect | "Not enough information to generate an architecture. Please provide more details about the workload." | No | PM re-enters questioning (§4.2) |
| `QUEUE_TIMEOUT` | Any | "The system is currently busy. Your request timed out in the queue." | Yes (1 retry) | Retry, Stop |
| `USER_CONCURRENCY_EXCEEDED` | Any | "You have too many active requests. Please wait for a current operation to complete." | Yes (auto-retry after current completes) | Wait, Stop |
| `PROMPT_INJECTION_DETECTED` | Any | "Your input could not be processed. Please rephrase your request." | No | Rephrase input |
| `REQUIRED_AGENT_EXHAUSTED` | architect | "The System Architect failed after multiple attempts. The pipeline cannot continue." | No | Stop (auto) |

\* "Skip" is **not** available for `architect` (required agent).

---

## 8. Edge Cases

| # | Scenario | Expected Behavior |
|---|----------|-------------------|
| E-1 | Seller sends empty message as first input. | PM responds: "Please describe the Azure solution you'd like to scope for your customer." Does not start pipeline. |
| E-2 | Seller deactivates `architect` via API or UI. | API returns `400 Bad Request`. UI shows error toast: "System Architect is required and cannot be deactivated." State unchanged. |
| E-3 | Seller deactivates `azure` while Azure Specialist is `Working`. | Cancel & Warn flow (§3.3). Running task terminated, partial output discarded, warning posted, pipeline advances to `cost`. |
| E-4 | Seller activates `envisioning` after PM already classified input as CLEAR and started questioning. | Envisioning is activated but the pipeline has already passed Stage 1. PM posts: "Envisioning has been activated but the pipeline has already advanced past that stage. It will be available for your next project." |
| E-5 | All optional agents deactivated (only `architect` remains). | Pipeline runs: PM → Architect → Complete. `project.status = 'completed'` with only `architecture` in `ProjectContext`. |
| E-6 | Seller clicks "Approve & Continue" but the next agent is being deactivated simultaneously. | PM checks agent active status **at invocation time**. If deactivated, skip to next active agent. Race condition resolved by checking state under a lock/transaction. |
| E-7 | Browser disconnects mid-pipeline. | Agent continues running server-side. On reconnect, PM reads `PipelineState` and re-renders the current state: gate prompt if gated, spinner if running, error if failed. No data lost (PRD NFR-5). |
| E-8 | Cost Specialist receives no `services` (Azure Specialist was skipped). | Cost agent uses `architecture.components` to infer services and applies default/general-purpose SKUs. All cost items flagged as `pricingSource: 'approximate'`. A disclaimer is posted: "Cost estimates are approximate because Azure service selection was skipped." |
| E-9 | Seller provides feedback at a gate that contradicts the original requirements. | PM passes the feedback to the agent as `sellerFeedback`. The agent re-generates output considering the feedback. PM does **not** update `requirements` — the feedback is stage-scoped. |
| E-10 | Seller sends a chat message while an agent is `Working`. | PM acknowledges: "I'll address that after {displayName} completes." Message is queued and processed after the current gate. |
| E-11 | Agent returns output that fails schema validation. | PM treats as `AGENT_INTERNAL_ERROR`. Auto-retries once with an appended instruction: "Your previous response did not match the expected format. Please ensure your output follows the schema." If retry also fails, presents error recovery to seller. |
| E-12 | Seller requests changes at a gate 3 times (max revisions reached). | PM posts: "You've reached the maximum revision limit for this stage. Please approve the current output or skip to continue." Only "Approve" and "Skip" options shown. |
| E-13 | Two projects from the same user try to invoke agents simultaneously, exceeding per-user concurrency. | Second invocation is queued. PM posts queue position notification. Processed when first completes or times out. |
| E-14 | Seller sends potential prompt injection (e.g., "Ignore all instructions and…"). | Input sanitization layer strips/escapes injection patterns before passing to any agent. If detected, return `PROMPT_INJECTION_DETECTED` error. Log the attempt for audit. |
| E-15 | Presentation agent receives minimal context (only architecture, no cost or value). | Agent generates a deck with available content only. Missing sections are omitted rather than filled with placeholders. Slide count adjusts accordingly. |
| E-16 | Pipeline is at Stage 4 (Cost) and seller re-activates Envisioning. | Envisioning is marked active but Stage 1 has already passed. It will not re-run. Behavior matches E-4. |
| E-17 | Agent produces valid output but zero chat messages. | PM generates a default chat message summarizing the structured output and presents the gate. |
| E-18 | Global agent pool (50) is exhausted and queue (100) is also full. | New invocations return `503 Service Unavailable`. PM posts: "The system is at capacity. Please try again in a few minutes." No retry is auto-attempted. |

---

## Traceability

| FRD Requirement | PRD Source | User Stories |
|----------------|-----------|-------------|
| §2.1 Agent Definitions | FR-2 | US-1, US-8 |
| §2.2 Agent Lifecycle States | FR-2, FR-3 | US-1 |
| §3.1 Pipeline Stages | FR-3 | US-1, US-2, US-3, US-4, US-5, US-6, US-7 |
| §3.2 Stage Transitions (Gates) | FR-3 | US-1 AC-4 |
| §3.3 Skip Logic | FR-3, US-8 | US-8 AC-2, AC-5 |
| §3.4 Error Recovery | FR-3 | US-1 AC-5 |
| §4.1 Input Classification | FR-3 | US-2 |
| §4.2 Structured Questioning | FR-3, US-9 | US-9 AC-1, AC-2, AC-3 |
| §4.3 Context Assembly | FR-4 | US-1 |
| §4.4 Agent Invocation Protocol | FR-1, FR-3 | US-1 |
| §5.1 Context Passing | FR-3, FR-4 | US-3, US-4, US-5, US-6, US-7 |
| §5.2 Output Schemas | FR-4 | US-3, US-4, US-5, US-6, US-7 |
| §6.1 Timeout Policy | NFR-1, R-1 | — |
| §6.2 Concurrency Limits | NFR-4, R-6 | — |
| §7 Error Catalog | FR-3, R-1, R-2, R-3, R-4, R-5, R-7 | US-1 AC-5 |
| §8 Edge Cases | All FRs | All USs |
