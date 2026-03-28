# OneStopAgent – Full Refactor Specification (World-Class Demo Version)

## Objective

Refactor OneStopAgent into a **Project Manager–driven, semi-agentic Azure seller copilot** that:

* Starts as a **brainstorming partner**
* Only proceeds when a **strong Azure use case is identified**
* Uses **Microsoft knowledge (Microsoft Learn MCP Server)**
* Produces:
  * Architecture
  * Azure services
  * Cost (Azure Retail Prices API)
  * Business value
  * ROI
  * Executive-ready presentation (Anthropic PPTX skill)
* Guides the user step-by-step with **visible plan checkboxes and approvals**

---

# 1. CORE SYSTEM BEHAVIOR

## 1.1 Two Modes

### Mode A – Brainstorming

* System explores ideas with the user via conversational LLM
* Suggests Azure-relevant scenarios based on user's industry and description
* Uses knowledge retrieval (MCP) to ground suggestions in real Microsoft patterns
* Determines Azure fit classification:
  * **Strong** — clear workload that maps to Azure services (e.g., "e-commerce platform", "IoT telemetry")
  * **Weak** — generic IT need without clear Azure advantage (e.g., "improve our processes")
  * **Unclear** — not enough information to assess
* **PM must always explain WHY the system believes Azure is a fit** — e.g., "Azure is a strong fit because your requirements for global availability and PCI-DSS compliance align with Azure Front Door and App Service Environment." This builds seller trust and makes brainstorming feel like a real partner.

⚠️ MUST NOT proceed to architecture until Azure fit is classified as "strong" — either by the PM's assessment or by the user explicitly saying "proceed"

---

### Mode B – Solutioning

* Activated ONLY when:
  * PM classifies Azure fit as "strong"
  * OR user explicitly says "proceed", "let's go", "yes", or similar affirmative
* Once activated, the execution plan runs sequentially with approval gates

---

## 1.2 Execution Speed Modes

Two modes for how the plan is executed:

### Guided Mode (default)
* PM pauses after EVERY agent step for approval (proceed / refine / skip)
* Best for: demos, detailed walkthroughs, first-time users

### Fast-Run Mode
* PM pauses only at 3 major gates:
  1. After brainstorming (before entering Mode B)
  2. After architecture generation (before committing to services + cost)
  3. Before presentation generation (final review)
* All intermediate steps (services, cost, business value, ROI) run without pausing
* Activated when user says: "run everything", "fast mode", "no stops", or "just build it"
* PM announces: "Running in fast mode — I'll pause at architecture and before the final deck."

---

# 2. PROJECT MANAGER (CENTRAL CONTROL)

## 2.1 Responsibilities

The Project Manager (PM) is the ONLY orchestrator. It is a Python class, NOT a LangChain agent.

It must:

* Manage the conversation (ask questions, acknowledge answers)
* Decide which agent to call next (based on the execution plan, not LLM reasoning)
* Maintain execution plan state (which steps are done, which are pending)
* Ask for user approval at gate points (every step in guided mode, major gates in fast-run mode)
* Handle iteration requests (re-run specific agents when user asks for changes)
* **Always explain Azure fit reasoning** when transitioning from Mode A to Mode B

---

## 2.2 Intent Interpreter

The PM must classify every user message into one of these intents. This is done via a simple keyword/pattern matcher, NOT an LLM call:

| Intent | Trigger Patterns | PM Action |
|--------|-----------------|-----------|
| **Proceed** | "proceed", "yes", "let's go", "go", "ok", "sure", "do it", "start", "continue" | Advance to next step or start execution |
| **Refine** | "refine", "change", "adjust", "modify", "update", "make it..." | Re-run current agent with feedback |
| **Skip** | "skip", "next", "don't need this" | Mark step as skipped, advance |
| **Fast-run** | "run everything", "fast mode", "no stops", "just build it" | Switch to fast-run mode |
| **Back to brainstorm** | "different approach", "start over", "rethink", "other options" | Return to Mode A |
| **Iteration** | "make it cheaper", "add HA", "change region", contains architectural terms | Re-run affected agents (see §13) |
| **Question** | Contains "?", "what", "why", "how", "can you explain" | PM responds conversationally (LLM call) |
| **New input** | Anything else | Treat as additional context, append to clarifications |

If the pattern matcher cannot classify → fall back to an LLM call: "Classify this user message as one of: proceed, refine, skip, fast-run, brainstorm, iteration, question, input."

---

## 2.3 Execution Plan (CHECKBOX UI)

PM must maintain a visible checklist shown in the chat. The frontend renders this as a styled checklist component.

```markdown
## Execution Plan

- [ ] Brainstorm use case
- [ ] Validate Azure fit
- [ ] Retrieve Microsoft patterns (via MCP)
- [ ] Generate architecture (Mermaid diagram)
- [ ] Map Azure services (SKUs + regions)
- [ ] Estimate cost (Azure Retail Prices API)
- [ ] Analyze business value (value drivers)
- [ ] Calculate ROI (cost vs. value)
- [ ] Build presentation (PowerPoint deck)
```

Each step transitions: `pending → running → completed | skipped | failed`

The plan is built once at the start of Mode B and is NOT dynamically changed by LLM reasoning. Steps are removed only if the user explicitly toggles an agent off.

---

## 2.4 After Each Step (Guided Mode)

PM must:

1. Summarize the agent's output in 2-3 sentences (human-readable, not raw JSON)
2. Highlight one key insight (e.g., "Total monthly cost: $1,200" or "Key risk: PCI-DSS compliance requires Premium SKUs")
3. Ask:

> "Does this look right? Say **proceed** to continue, **refine** to adjust, or **skip** to move on."

User options:

* **Proceed** → advance to next step in plan
* **Refine** → re-run the current agent with user's feedback appended to context
* **Skip** → mark step as skipped, advance to next

---

# 3. AGENT ARCHITECTURE

## 3.1 Required Agents

Each agent is a Python class with a `run(state: AgentState) -> AgentState` method. Agents read from and write to shared state.

| # | Agent Class | Purpose | LLM Required | External API |
|---|-------------|---------|-------------|--------------|
| 1 | `ProjectManager` | Orchestrates flow, manages plan, handles approvals | Yes (conversation) | No |
| 2 | `BrainstormingAgent` | Explores ideas, suggests scenarios, classifies Azure fit | Yes | No |
| 3 | `KnowledgeAgent` | Retrieves Microsoft reference architectures and patterns | No (MCP call) | Microsoft Learn MCP Server |
| 4 | `ArchitectAgent` | Generates Mermaid diagram + component list grounded in retrieved patterns | Yes | No |
| 5 | `AzureSpecialistAgent` | Maps components to Azure services with scale-appropriate SKUs | No (deterministic) | No |
| 6 | `CostAgent` | Estimates monthly/annual costs per service | No (API call) | Azure Retail Prices API |
| 7 | `BusinessValueAgent` | Generates use-case-specific value drivers with quantified estimates | Yes | No |
| 8 | `ROIAgent` | Calculates ROI percentage and payback period from cost + value data | No (math) | No |
| 9 | `PresentationAgent` | Generates downloadable PowerPoint deck using Anthropic PPTX skill | Yes (Anthropic) | No |

---

## 3.2 RULE: NO DUPLICATE LOGIC

* Business logic (LLM prompts, data transformation, output formatting) MUST live in agent classes
* `services/` directory contains ONLY:
  * `services/pricing.py` — Azure Retail Prices API calls
  * `services/mcp.py` — MCP server client (NEW)
  * `services/presentation.py` — PPTX file I/O helpers
* No agent should import logic from another agent — they communicate only through `AgentState`

---

# 4. KNOWLEDGE LAYER (CRITICAL)

## 4.1 Source

Use the **Microsoft Learn MCP Server** as the primary retrieval surface:

* **Endpoint:** `https://learn.microsoft.com/api/mcp`
* **Capabilities:** Search and article retrieval across Microsoft Learn and Azure Architecture Center content
* **Documentation:** Publicly documented MCP server with search and get-article tools

"Azure Architecture Center" is NOT a separate MCP server — it is content within Microsoft Learn. Query the Microsoft Learn MCP Server with architecture-specific terms to retrieve Architecture Center content.

Optionally, the **Azure MCP Server** can be used for Azure tools and best-practice operations (resource discovery, deployment patterns), but this is secondary to Learn content.

The MCP integration is configured in `.mcp.json` at the repo root.

---

## 4.2 KnowledgeAgent

```python
class KnowledgeAgent:
    """Retrieves relevant Microsoft patterns and reference architectures via MCP."""
    name = "Knowledge Retrieval"
    emoji = "📚"

    def run(self, state: AgentState) -> AgentState:
        """Query Microsoft Learn MCP Server for Azure patterns matching the use case."""
        query = f"{state.user_input} {state.clarifications} azure architecture"
        results = mcp_client.search(query=query)
        state.retrieved_patterns = results
        return state
```

If MCP is unavailable, fall back to the local knowledge base (`data/knowledge_base.py`) and flag outputs as "⚠️ Not grounded in Microsoft Learn — based on local reference data."

---

## 4.3 Retrieved Pattern Schema

Each pattern in `state.retrieved_patterns` must have:

```python
{
    "title": "Scalable e-commerce web app",
    "url": "https://learn.microsoft.com/en-us/azure/architecture/...",
    "summary": "2-3 sentence description",
    "workload_type": "web-app" | "data-platform" | "ai-ml" | "iot" | "microservices" | "migration",
    "industry": "Retail" | "Healthcare" | "Financial Services" | "Manufacturing" | "Cross-Industry",
    "compliance_tags": ["PCI-DSS", "HIPAA", "GDPR", "SOC2"],
    "recommended_services": ["Azure App Service", "Azure SQL", "Azure Cache for Redis"],
    "components": [{"name": "...", "azureService": "...", "description": "..."}],
    "confidence_score": 0.85  # how well this pattern matches the user's query (0-1)
}
```

If the MCP response doesn't include all fields, the KnowledgeAgent fills defaults: `workload_type = "custom"`, `industry = "Cross-Industry"`, `compliance_tags = []`, `confidence_score = 0.5`.

---

## 4.4 How Retrieved Patterns Are Used

**ArchitectAgent MUST:**

* Include retrieved patterns in its LLM prompt as reference material
* Prefer the pattern with the highest `confidence_score`
* Adapt patterns to the user's specific requirements (scale, region, compliance)
* NOT generate architecture from scratch — start from the closest matching pattern

**LLM prompt MUST include:**

> "Base your solution on the following Microsoft reference architectures. Adapt them to the user's specific requirements: {retrieved_patterns}"

If no patterns were retrieved, the architect should note this: "⚠️ No matching reference architecture found — design based on Azure best practices."

---

# 5. BRAINSTORMING AGENT

## Behavior

* Receives the user's initial description (which may be vague)
* Uses LLM to suggest 2–4 Azure-relevant scenarios that could address the need
* For each scenario: explain what it is, why Azure is a good fit, and which Azure services are involved
* Identify the user's industry (retail, healthcare, financial services, manufacturing, etc.)
* Classify Azure fit as: `strong`, `weak`, or `unclear`
* **For each scenario, explain WHY Azure is a fit** — reference specific Azure capabilities (e.g., "Azure Cosmos DB provides global distribution which matches your multi-region requirement")

---

## Output Written to State

```python
state.brainstorming = {
    "scenarios": [
        {
            "title": "...",
            "description": "...",
            "azure_services": ["..."],
            "industry": "...",
            "azure_fit_reason": "Why Azure is a good fit for this scenario"
        }
    ],
    "recommended": "scenario title",
    "azure_fit": "strong" | "weak" | "unclear",
    "azure_fit_explanation": "Azure is a strong fit because...",
    "industry": "Retail"
}
```

---

## PM Behavior Based on Azure Fit

* If `azure_fit == "strong"` → PM presents the Azure fit explanation, shows the plan, and asks to proceed to Mode B
* If `azure_fit == "weak"` or `"unclear"` → PM stays in brainstorming mode, explains why the fit is uncertain, asks follow-up questions to narrow the use case

---

# 6. ARCHITECT AGENT (UPDATED)

## Input from State

* `state.user_input` — original project description
* `state.clarifications` — user's answers to PM questions
* `state.retrieved_patterns` — Microsoft reference architectures from KnowledgeAgent

## Behavior

* Select the closest matching reference architecture from `retrieved_patterns` (highest `confidence_score`)
* Use LLM to adapt it to the user's specific requirements:
  * Scale (concurrent users → appropriate service tiers)
  * Region (user's preferred Azure region)
  * Compliance (PCI-DSS, HIPAA, GDPR → add required components)
* Generate Mermaid flowchart diagram (max 20 nodes)
* Extract component list with Azure service mapping

## Output Written to State

```python
state.architecture = {
    "mermaidCode": "flowchart TD\n  ...",
    "components": [{"name": "...", "azureService": "...", "description": "..."}],
    "narrative": "2-3 sentence description of the architecture",
    "basedOn": "reference architecture title or 'custom design'"
}
```

---

# 7. AZURE SPECIALIST

## Behavior

* Map each component from `state.architecture.components` to a specific Azure service
* Select SKU based on scale (extracted from `state.user_input`):

### Core Service SKU Matrix

| Concurrent Users | App Service | SQL Database | Redis Cache | Cosmos DB | Azure Functions |
|-----------------|------------|--------------|-------------|-----------|----------------|
| ≤100 | B1 | Basic | C0 | Serverless | Consumption |
| ≤1,000 | S1 | Standard S1 | C1 | Autoscale 1000 RU/s | Consumption |
| ≤10,000 | P2v3 | Premium P4 | P1 | Autoscale 10000 RU/s | Premium EP1 |
| >10,000 | P3v3 | Business Critical | P3 | Autoscale 50000 RU/s | Premium EP3 |

### Extended Service Defaults

For services NOT in the core matrix, use these defaults:

| Service | Default SKU | Notes |
|---------|------------|-------|
| Azure OpenAI | Standard S0 | Provisioned throughput for >1000 users |
| Azure AI Search | Standard S1 | Basic for ≤100 users |
| Azure Container Apps | Consumption | Dedicated for >10,000 users |
| Azure Kubernetes Service (AKS) | Standard_D4s_v3 (3 nodes) | Scale node count with users |
| Azure Event Hubs | Standard | Premium for >10,000 events/sec |
| Azure Service Bus | Standard | Premium for mission-critical |
| Azure Blob Storage | Standard LRS | GRS for HA requirements |
| Azure Key Vault | Standard | Premium for HSM-backed keys |
| Azure Monitor / App Insights | Pay-as-you-go | Always included |
| Azure Front Door | Standard | Premium for WAF + private link |
| Azure API Management | Developer | Standard for production |
| Microsoft Fabric | F2 | Scale with data volume |

### Fallback Rule

For any component type NOT listed above: set `sku = "Standard"`, `region = user preference or "eastus"`, and add a note: "⚠️ SKU needs manual validation for {serviceName}."

* Set region from user preference or default to `eastus`
* This agent does NOT use LLM — it's deterministic mapping logic

## Output Written to State

```python
state.services = {
    "selections": [
        {"componentName": "...", "serviceName": "...", "sku": "...", "region": "...", "capabilities": ["..."], "skuNote": "optional warning"}
    ]
}
```

---

# 8. COST AGENT

## MUST USE:

Azure Retail Prices API: `https://prices.azure.com/api/retail/prices`

* No authentication required
* OData filter: `$filter=serviceName eq '{name}' and armRegionName eq '{region}'`
* Parse `retailPrice` and `unitOfMeasure` from response items

## Pricing Source Behavior

| Scenario | Behavior | Source Tag |
|----------|----------|-----------|
| API returns matching SKU | Use API price | `"live"` |
| API returns results but no SKU match | Use cheapest result for that service | `"live-fallback"` — add note: "Exact SKU not found, using closest match" |
| API returns no results for service | Use `MOCK_PRICES` dict | `"approximate"` |
| API timeout or error | Use `MOCK_PRICES` dict | `"approximate"` — add note: "API unavailable, using reference pricing" |
| Regional mismatch (service unavailable in region) | Query with `eastus` instead | `"live"` — add note: "Service not available in {region}, pricing for eastus" |

## Consumption-Based Services

Some Azure services have usage-based pricing that cannot be inferred from architecture alone. For these, use reasonable demo assumptions:

| Service | Assumption |
|---------|-----------|
| Azure Functions (Consumption) | 1M executions/month, 400K GB-s |
| Azure Blob Storage | 100 GB stored, 10K read operations/month |
| Azure Cosmos DB | 1000 RU/s provisioned, 50 GB stored |
| Azure Event Hubs | 1M events/month |
| Azure OpenAI | 1M tokens/month |
| Azure AI Search | 1 search unit |
| Azure Monitor | 5 GB logs ingested/month |

These assumptions MUST be listed in `estimate.assumptions`.

## Output Written to State

```python
state.costs = {
    "estimate": {
        "currency": "USD",
        "items": [{"serviceName": "...", "sku": "...", "region": "...", "monthlyCost": 0.0, "pricingNote": "optional"}],
        "totalMonthly": 0.0,
        "totalAnnual": 0.0,
        "assumptions": ["Based on 730 hours/month", "Pay-as-you-go pricing", "..."],
        "pricingSource": "live" | "live-fallback" | "approximate"
    }
}
```

---

# 9. BUSINESS VALUE AGENT

## Behavior

* Use LLM with full context (user description, architecture, services, monthly cost, industry)
* Generate 3-5 value drivers that are **specific to the user's use case**, not generic
  * Example for e-commerce: "AI recommendations increase average order value by 15-25%"
  * Example for healthcare: "Telehealth reduces no-show rate by 30%"
* Each driver has: name, description, quantified estimate (where possible)
* Generate 100-200 word executive summary referencing the specific customer and solution

## MUST NOT:

* Return generic value drivers like "cloud migration saves costs" without specifics
* Omit the customer's industry and use case from the analysis

## Output Written to State

```python
state.business_value = {
    "drivers": [{"name": "...", "description": "...", "estimate": "...", "monetizable": True | False}],
    "executiveSummary": "...",
    "confidenceLevel": "conservative" | "moderate" | "optimistic"
}
```

The `monetizable` flag indicates whether the driver's estimate can be converted to a dollar amount for ROI calculation.

---

# 10. ROI AGENT (NEW)

## Behavior

Calculate ROI from cost and business value data. This is deterministic math, NOT an LLM call.

### Monetizable Value Drivers

Only drivers with `monetizable: True` are included in the quantitative ROI. The ROI Agent converts estimates to annual dollar amounts using these rules:

| Estimate Format | Conversion |
|----------------|------------|
| "X% reduction in {cost_category}" | `annual_cost * X/100` (if cost category can be inferred from architecture) |
| "X% increase in {revenue_metric}" | Requires user input or uses industry benchmark |
| "$X saved per month/year" | Direct use |
| "X hours saved per week" | `X * 52 * hourly_rate` (default $75/hr for IT staff) |
| Cannot be converted | Exclude from ROI, list as qualitative benefit |

### Calculation

```
annual_cost = state.costs.estimate.totalAnnual
annual_value = sum of monetized driver values
roi_percent = ((annual_value - annual_cost) / annual_cost) * 100
payback_months = annual_cost / (annual_value / 12)
```

If `annual_value` cannot be reliably calculated (no monetizable drivers): set `roi_percent = None` and report: "ROI cannot be calculated quantitatively — see qualitative benefits below."

## Output Written to State

```python
state.roi = {
    "annual_cost": 14400.0,
    "annual_value": 50000.0,        # None if not calculable
    "roi_percent": 247.0,            # None if not calculable
    "payback_months": 3.5,           # None if not calculable
    "monetized_drivers": [{"name": "...", "annual_value": 0.0, "method": "..."}],
    "qualitative_benefits": ["Improved compliance posture", "..."],
    "assumptions": ["IT staff hourly rate: $75", "..."]
}
```

---

# 11. PRESENTATION AGENT

## Requirement

Use the **Anthropic PPTX generation skill** (https://github.com/anthropics/skills/tree/main/skills/pptx) as the primary presentation generation method. Claude can create PowerPoint files directly as part of its file creation capabilities.

If the Anthropic PPTX skill is unavailable or not integrated, fall back to `python-pptx` for local PPTX generation.

---

## Slide Content (generated via LLM)

The LLM prompt should specify: "Write slide content for an executive audience. Use bullet points, keep text concise, highlight key numbers."

| # | Slide | Content Source |
|---|-------|---------------|
| 1 | Title | Customer name + "Azure Solution Proposal" |
| 2 | Problem / Opportunity | `state.user_input` + `state.brainstorming.recommended` |
| 3 | Solution Overview | `state.architecture.narrative` |
| 4 | Architecture Diagram | `state.architecture.mermaidCode` rendered as image (or component table as fallback) |
| 5 | Azure Services | `state.services.selections` as table |
| 6 | Cost Estimate | `state.costs.estimate` as table + totals |
| 7 | Business Value | `state.business_value.drivers` as bullet list |
| 8 | ROI | `state.roi` — ROI %, payback period, key numbers (or qualitative summary if ROI not calculable) |
| 9 | Next Steps | Static recommendations (PoC, Azure subscription, etc.) |

---

## Fallback Rendering (python-pptx)

If Anthropic PPTX skill is not available:
* Use `python-pptx` to create the physical `.pptx` file
* For the architecture diagram slide: attempt Mermaid → PNG conversion; if that fails, include the component list as a table instead
* Save to `output/` directory with UUID filename

## Output Written to State

```python
state.presentation_path = "output/{uuid}.pptx"
```

---

# 12. STATE MODEL (UPDATED)

Full `AgentState` class with all fields:

```python
class AgentState:
    # Core inputs
    user_input: str = ""
    customer_name: str = ""
    clarifications: str = ""

    # Mode tracking
    mode: str = "brainstorm"        # "brainstorm" or "solution"
    execution_mode: str = "guided"  # "guided" or "fast-run"
    azure_fit: str = ""             # "strong", "weak", "unclear"
    azure_fit_explanation: str = "" # WHY Azure is a fit

    # Knowledge
    retrieved_patterns: list[dict] = []  # from KnowledgeAgent (see §4.3 for schema)

    # Agent outputs
    brainstorming: dict = {}
    architecture: dict = {}
    services: dict = {}
    costs: dict = {}
    business_value: dict = {}
    roi: dict = {}
    presentation_path: str = ""

    # Plan tracking
    plan_steps: list[str] = []          # ordered list of agent IDs
    completed_steps: list[str] = []     # agent IDs that have completed
    skipped_steps: list[str] = []       # agent IDs that were skipped
    failed_steps: list[str] = []        # agent IDs that failed
    awaiting_approval: bool = False     # True when PM is waiting for user approval
    current_step: str = ""              # agent ID currently running or awaiting approval
```

---

# 13. ITERATION LOGIC

## Example

User says: "Make it cheaper"

PM must:

1. Identify which agents are affected (AzureSpecialist → CostAgent → ROIAgent → PresentationAgent)
2. Re-run ONLY those agents in order, with the user's feedback appended to `state.clarifications`
3. NOT re-run the full pipeline — preserve ArchitectAgent and BrainstormingAgent outputs
4. Show updated results with a diff summary: "Monthly cost reduced from $1,200 to $800 by switching from P2v3 to S1"

## Iteration Mapping

| User Says | Agents to Re-run |
|-----------|-----------------|
| "Make it cheaper" | AzureSpecialist, Cost, ROI, Presentation |
| "Add high availability" | Architect, AzureSpecialist, Cost, ROI, Presentation |
| "Change region to Europe" | AzureSpecialist, Cost, Presentation |
| "Show me a different approach" | BrainstormingAgent (back to Mode A) |
| "Add AI capabilities" | Architect, AzureSpecialist, Cost, BusinessValue, ROI, Presentation |
| "What about compliance?" | Architect, AzureSpecialist (add compliance components) |

---

# 14. UX REQUIREMENTS

## 14.1 Chat + Workspace Layout

**Left panel:**
* Chat thread (PM + agent messages)
* User input at bottom

**Right panel (future):**
* Execution plan checklist with step statuses
* Latest agent output (architecture diagram, cost table, etc.)

For MVP: right panel is optional. The execution plan and outputs render inline in the chat.

---

## 14.2 Execution Plan UI Behavior

The plan checklist is updated via structured SSE events:

| SSE Event | Frontend Action |
|-----------|----------------|
| `{ "type": "plan_update", "step": "architect", "status": "running" }` | Show spinner on that step |
| `{ "type": "plan_update", "step": "architect", "status": "completed" }` | Show green checkmark |
| `{ "type": "plan_update", "step": "cost", "status": "skipped" }` | Show grey dash |
| `{ "type": "plan_update", "step": "cost", "status": "failed" }` | Show red X |

Prior agent outputs collapse automatically when the next agent starts (accordion behavior). The user can click any completed step to expand and review its output. Clicking a completed step also shows a "Re-run" button for iteration.

---

## 14.3 Agent Toggles

* Sidebar shows all agents with toggle switches
* Toggling an agent OFF removes it from the execution plan
* PM must explain the impact of disabling an agent:
  * "Disabling Cost Specialist means no pricing data — ROI calculation will be qualitative only."
  * "Disabling Business Value means no value drivers — the presentation will omit the business case slide."
* Architect is always required — toggle is disabled

---

## 14.4 Streaming

SSE events must show:

* Agent start: "🏗️ System Architect is working..."
* Agent result: formatted markdown output
* Plan updates: structured events for checklist UI
* Errors: "⚠️ Cost Agent failed: API timeout. Using approximate pricing."

---

# 15. TECHNICAL RULES

* **Backend:** Python + FastAPI
* **LLM:** Azure OpenAI (GPT-4.1 or latest) via `langchain-openai` (`AzureChatOpenAI`)
* **Knowledge:** Microsoft Learn MCP Server (`https://learn.microsoft.com/api/mcp`)
* **Pricing:** Azure Retail Prices REST API (no auth required)
* **Presentation:** Anthropic PPTX skill (primary), python-pptx (fallback)
* **Frontend:** Vite + React + TypeScript
* **Streaming:** SSE via sse-starlette
* **NO** FAISS, vector databases, or embedding stores
* **NO** LangGraph, ReAct agents, or autonomous tool calling
* **NO** chains or complex LangChain abstractions — direct `llm.invoke()` calls only

---

# 16. STATE PERSISTENCE AND SESSION SCOPE

## MVP (Current)

* All state is **in-memory** (Python dicts / `AgentState` objects)
* State is **per-server-process** — server restart clears everything
* Sessions are **ephemeral** — each project exists only while the server is running
* This is acceptable for demos and development

## Future

* Persist `AgentState` to Azure Cosmos DB or Azure Blob Storage (JSON serialization)
* Sessions resumable across server restarts
* Multiple users can have concurrent sessions
* Project history viewable and re-openable

## Current Limitation (document explicitly)

The PM should warn users: "Note: your project data is stored in memory and will be lost if the server restarts."

---

# 17. GRACEFUL DEGRADATION (ERROR HANDLING)

Every external dependency can fail. The system must handle each gracefully:

| Failure | Impact | Fallback Behavior |
|---------|--------|-------------------|
| **Azure OpenAI unavailable** | All LLM-dependent agents fail | PM announces: "AI service is temporarily unavailable." Offer to retry. |
| **MCP server unavailable** | KnowledgeAgent returns no patterns | Use local knowledge base. Flag: "⚠️ Not grounded in Microsoft Learn." |
| **Azure Retail Prices API timeout** | Cost estimate uses mock prices | Tag as `"approximate"`. Show: "Using reference pricing — verify with Azure Pricing Calculator." |
| **Azure Retail Prices API returns no results** | Missing services in cost breakdown | Show $0 for those services with note: "Pricing unavailable for {service}." |
| **Malformed Mermaid from LLM** | Architecture diagram won't render | Show component table instead. Hide diagram silently (no crash). |
| **PPTX generation fails** | No downloadable deck | Show error: "Presentation generation failed." Offer slide content as markdown in chat. |
| **Agent throws unhandled exception** | Single agent step fails | Mark step as `failed` in plan. PM announces error. Skip to next agent. Pipeline continues. |
| **LLM returns invalid JSON** | Agent can't parse structured output | Retry once with stricter prompt. If still fails, use fallback template. |

**Principle:** The system should NEVER crash or show a blank screen. Every failure is caught, reported to the user, and the pipeline continues where possible.

---

# 18. CLEANUP TASKS

## REMOVE / REFACTOR

* Delete `agents/tools.py` — all logic must live in agent classes
* Move external API calls to `services/`:
  * `services/pricing.py` — Azure Retail Prices API (already exists)
  * `services/mcp.py` — MCP server client (NEW)
  * `services/presentation.py` — PPTX generation (already exists)
* Remove any remaining LangGraph/ReAct imports (`create_react_agent`, `MemorySaver`, etc.)
* Remove `langgraph` from `requirements.txt`

---

# 19. DEFINITION OF DONE

System must:

* Start with a vague idea ("we want to do something with AI")
* Act as a brainstorming partner (suggest scenarios, explore options)
* **Explain WHY Azure is a fit** — not just classify, but reason
* Detect Azure fit and only proceed when fit is strong
* Retrieve Microsoft reference patterns via MCP and use them to ground the architecture
* Generate:
  * Architecture (Mermaid diagram + component list, grounded in Microsoft patterns)
  * Azure services (with scale-appropriate SKUs for 20+ service types)
  * Cost estimate (from Azure Retail Prices API, with explicit fallback handling)
  * Business value (use-case-specific, quantified, with monetizable flags)
  * ROI (calculated from cost + monetizable value, with qualitative benefits listed separately)
  * Presentation (downloadable PPTX via Anthropic skill or python-pptx fallback)
* Support both **guided mode** (pause after every step) and **fast-run mode** (pause at major gates only)
* Ask for user approval at gate points
* Allow iteration without re-running the full pipeline
* Handle all errors gracefully — no crashes, no blank screens
* Be demo-stable (deterministic flow, no LLM-driven routing surprises)

---

# FINAL POSITIONING

This system must behave as:

> "A Project Manager copilot that helps Azure sellers shape, validate, and present deals — grounded in Microsoft best practices"

NOT:

> "An LLM that generates answers"
