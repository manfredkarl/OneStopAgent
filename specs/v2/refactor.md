# OneStopAgent – Full Refactor Specification (World-Class Demo Version)

## Objective

Refactor OneStopAgent into a **Project Manager–driven, semi-agentic Azure seller copilot** that:

* Starts as a **brainstorming partner**
* Only proceeds when a **strong Azure use case is identified**
* Uses **Microsoft knowledge (Azure Learn / Architecture Center via MCP)**
* Produces:
  * Architecture
  * Azure services
  * Cost (Azure Retail Prices API)
  * Business value
  * ROI
  * Executive-ready presentation
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

⚠️ MUST NOT proceed to architecture until Azure fit is classified as "strong" — either by the PM's assessment or by the user explicitly saying "proceed"

---

### Mode B – Solutioning

* Activated ONLY when:
  * PM classifies Azure fit as "strong"
  * OR user explicitly says "proceed", "let's go", "yes", or similar affirmative
* Once activated, the execution plan runs sequentially with approval gates

---

# 2. PROJECT MANAGER (CENTRAL CONTROL)

## 2.1 Responsibilities

The Project Manager (PM) is the ONLY orchestrator. It is a Python class, NOT a LangChain agent.

It must:

* Manage the conversation (ask questions, acknowledge answers)
* Decide which agent to call next (based on the execution plan, not LLM reasoning)
* Maintain execution plan state (which steps are done, which are pending)
* Ask for user approval after each step before proceeding
* Handle iteration requests (re-run specific agents when user asks for changes)

---

## 2.2 Execution Plan (CHECKBOX UI)

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

Each step transitions: `pending → running → completed | skipped`

The plan is built once at the start of Mode B and is NOT dynamically changed by LLM reasoning. Steps are removed only if the user explicitly toggles an agent off.

---

## 2.3 After Each Step

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
| 3 | `KnowledgeAgent` | Retrieves Microsoft reference architectures and patterns | No (MCP call) | MCP Server |
| 4 | `ArchitectAgent` | Generates Mermaid diagram + component list grounded in retrieved patterns | Yes | No |
| 5 | `AzureSpecialistAgent` | Maps components to Azure services with scale-appropriate SKUs | No (deterministic) | No |
| 6 | `CostAgent` | Estimates monthly/annual costs per service | No (API call) | Azure Retail Prices API |
| 7 | `BusinessValueAgent` | Generates use-case-specific value drivers with quantified estimates | Yes | No |
| 8 | `ROIAgent` | Calculates ROI percentage and payback period from cost + value data | No (math) | No |
| 9 | `PresentationAgent` | Generates downloadable PowerPoint deck from all outputs | Yes (slide content) | No |

---

## 3.2 RULE: NO DUPLICATE LOGIC

* Business logic (LLM prompts, data transformation, output formatting) MUST live in agent classes
* `tools.py` (if kept) must ONLY contain:
  * External API integration functions (Azure Retail Prices API calls)
  * MCP server query functions
  * File I/O helpers (PPTX saving)
* No agent should import logic from another agent — they communicate only through `AgentState`

---

# 4. KNOWLEDGE LAYER (CRITICAL)

## 4.1 Source

Use MCP (Model Context Protocol) servers to ground agent outputs in real Microsoft documentation:

* **Microsoft Learn MCP Server**: `https://learn.microsoft.com/api/mcp` — Azure docs, tutorials, best practices
* **Azure Architecture Center**: Reference architectures, design patterns, solution ideas

The MCP integration is configured in `.mcp.json` at the repo root.

---

## 4.2 KnowledgeAgent

```python
class KnowledgeAgent:
    """Retrieves relevant Microsoft patterns and reference architectures via MCP."""
    name = "Knowledge Retrieval"
    emoji = "📚"

    def run(self, state: AgentState) -> AgentState:
        """Query MCP servers for Azure patterns matching the user's use case."""
        query = f"{state.user_input} {state.clarifications}"
        results = mcp_client.search(
            query=query,
            sources=["azure architecture center", "microsoft learn"]
        )
        state.retrieved_patterns = results  # list of { title, url, summary, components }
        return state
```

If MCP is unavailable, fall back to the local knowledge base (`data/knowledge_base.py`) and flag outputs as "not grounded in Microsoft Learn".

---

## 4.3 How Retrieved Patterns Are Used

**ArchitectAgent MUST:**

* Include retrieved patterns in its LLM prompt as reference material
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

---

## Output Written to State

```python
state.brainstorming = {
    "scenarios": [
        {"title": "...", "description": "...", "azure_services": ["..."], "industry": "..."}
    ],
    "recommended": "scenario title",
    "azure_fit": "strong" | "weak" | "unclear",
    "industry": "Retail"
}
```

---

## PM Behavior Based on Azure Fit

* If `azure_fit == "strong"` → PM presents the plan and asks to proceed to Mode B
* If `azure_fit == "weak"` or `"unclear"` → PM stays in brainstorming mode, asks follow-up questions to narrow the use case

---

# 6. ARCHITECT AGENT (UPDATED)

## Input from State

* `state.user_input` — original project description
* `state.clarifications` — user's answers to PM questions
* `state.retrieved_patterns` — Microsoft reference architectures from KnowledgeAgent

## Behavior

* Select the closest matching reference architecture from `retrieved_patterns`
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

| Concurrent Users | App Service | SQL Database | Redis Cache |
|-----------------|------------|--------------|-------------|
| ≤100 | B1 | Basic | C0 |
| ≤1,000 | S1 | Standard S1 | C1 |
| ≤10,000 | P2v3 | Premium P4 | P1 |
| >10,000 | P3v3 | Business Critical | P3 |

* Set region from user preference or default to `eastus`
* This agent does NOT use LLM — it's deterministic mapping logic

## Output Written to State

```python
state.services = {
    "selections": [
        {"componentName": "...", "serviceName": "...", "sku": "...", "region": "...", "capabilities": ["..."]}
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

## Fallback

If API returns no results or times out → use `MOCK_PRICES` dict in `services/pricing.py` and tag `pricingSource` as `"approximate"`

## Output Written to State

```python
state.costs = {
    "estimate": {
        "currency": "USD",
        "items": [{"serviceName": "...", "sku": "...", "region": "...", "monthlyCost": 0.0}],
        "totalMonthly": 0.0,
        "totalAnnual": 0.0,
        "assumptions": ["Based on 730 hours/month", "Pay-as-you-go pricing"],
        "pricingSource": "live" | "approximate"
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
    "drivers": [{"name": "...", "description": "...", "estimate": "..."}],
    "executiveSummary": "...",
    "confidenceLevel": "conservative" | "moderate" | "optimistic"
}
```

---

# 10. ROI AGENT (NEW)

## Behavior

Calculate ROI from cost and business value data. This is deterministic math, NOT an LLM call.

```
annual_cost = state.costs.estimate.totalAnnual
annual_value = sum of quantified value driver estimates (converted to dollar amounts)
roi_percent = ((annual_value - annual_cost) / annual_cost) * 100
payback_months = (annual_cost / (annual_value / 12))
```

Where value driver estimates cannot be converted to dollar amounts (e.g., "30% reduction in downtime"), use industry-standard conversion factors or exclude from ROI calculation and list as qualitative benefits.

## Output Written to State

```python
state.roi = {
    "annual_cost": 14400.0,
    "annual_value": 50000.0,
    "roi_percent": 247.0,
    "payback_months": 3.5,
    "assumptions": ["Value estimates based on industry benchmarks", "..."],
    "qualitative_benefits": ["Improved compliance posture", "..."]
}
```

---

# 11. PRESENTATION AGENT

## Requirement

Generate a professional, executive-ready PowerPoint deck that compiles all agent outputs.

---

## Step 1 – Generate Slide Content via LLM

Use LLM to generate concise, presentation-ready text for each slide. The LLM prompt should specify: "Write slide content for an executive audience. Use bullet points, keep text concise, highlight key numbers."

Slide order:

| # | Slide | Content Source |
|---|-------|---------------|
| 1 | Title | Customer name + "Azure Solution Proposal" |
| 2 | Problem / Opportunity | `state.user_input` + `state.brainstorming.recommended` |
| 3 | Solution Overview | `state.architecture.narrative` |
| 4 | Architecture Diagram | `state.architecture.mermaidCode` rendered as image |
| 5 | Azure Services | `state.services.selections` as table |
| 6 | Cost Estimate | `state.costs.estimate` as table + totals |
| 7 | Business Value | `state.business_value.drivers` as bullet list |
| 8 | ROI | `state.roi` — ROI %, payback period, key numbers |
| 9 | Next Steps | Static recommendations (PoC, Azure subscription, etc.) |

---

## Step 2 – Render to PPTX

* Use `python-pptx` to create the physical `.pptx` file
* For the architecture diagram slide: attempt Mermaid → PNG conversion; if that fails, include the component list as a table instead
* Save to `output/` directory with UUID filename

---

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
    mode: str = "brainstorm"  # "brainstorm" or "solution"
    azure_fit: str = ""  # "strong", "weak", "unclear"

    # Knowledge
    retrieved_patterns: list[dict] = []  # from KnowledgeAgent

    # Agent outputs
    brainstorming: dict = {}
    architecture: dict = {}
    services: dict = {}
    costs: dict = {}
    business_value: dict = {}
    roi: dict = {}
    presentation_path: str = ""

    # Plan tracking
    plan_steps: list[str] = []  # ordered list of agent IDs
    completed_steps: list[str] = []  # agent IDs that have completed
    awaiting_approval: bool = False  # True when PM is waiting for user approval
    current_step: str = ""  # agent ID currently running or awaiting approval
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

## Other Iteration Examples

| User Says | Agents to Re-run |
|-----------|-----------------|
| "Make it cheaper" | AzureSpecialist, Cost, ROI, Presentation |
| "Add high availability" | Architect, AzureSpecialist, Cost, ROI, Presentation |
| "Change region to Europe" | AzureSpecialist, Cost, Presentation |
| "Show me a different approach" | BrainstormingAgent (back to Mode A) |

---

# 14. UX REQUIREMENTS

## 14.1 Chat + Workspace Layout

**Left panel:**
* Chat thread (PM + agent messages)
* User input at bottom

**Right panel (future):**
* Execution plan checklist with step statuses
* Latest agent output (architecture diagram, cost table, etc.)

For MVP: right panel is optional. The execution plan and outputs can render inline in the chat.

---

## 14.2 Agent Toggles

* Sidebar shows all agents with toggle switches
* Toggling an agent OFF removes it from the execution plan
* PM must explain the impact of disabling an agent (e.g., "Disabling Cost Specialist means no pricing data will be available for ROI calculation")
* Architect is always required — toggle is disabled

---

## 14.3 Streaming

SSE events must show:

* Agent start: "🏗️ System Architect is working..."
* Agent result: formatted markdown output
* Progress: which step of the plan is active
* Errors: "⚠️ Cost Agent failed: API timeout. Using approximate pricing."

---

# 15. TECHNICAL RULES

* **Backend:** Python + FastAPI
* **LLM:** Azure OpenAI (GPT-4.1 or latest) via `langchain-openai` (`AzureChatOpenAI`)
* **Knowledge:** MCP servers (Microsoft Learn, Azure Architecture Center)
* **Pricing:** Azure Retail Prices REST API (no auth required)
* **Presentation:** python-pptx for PPTX generation
* **Frontend:** Vite + React + TypeScript
* **Streaming:** SSE via sse-starlette
* **NO** FAISS, vector databases, or embedding stores
* **NO** LangGraph, ReAct agents, or autonomous tool calling
* **NO** chains or complex LangChain abstractions — direct `llm.invoke()` calls only

---

# 16. CLEANUP TASKS

## REMOVE / REFACTOR

* Delete `agents/tools.py` — all logic must live in agent classes
* Move external API calls to `services/`:
  * `services/pricing.py` — Azure Retail Prices API (already exists)
  * `services/mcp.py` — MCP server client (NEW)
  * `services/presentation.py` — PPTX generation (already exists)
* Remove any remaining LangGraph/ReAct imports (`create_react_agent`, `MemorySaver`, etc.)
* Remove `langgraph` from `requirements.txt`

---

# 17. DEFINITION OF DONE

System must:

* Start with a vague idea ("we want to do something with AI")
* Act as a brainstorming partner (suggest scenarios, explore options)
* Detect Azure fit and only proceed when fit is strong
* Retrieve Microsoft reference patterns via MCP and use them to ground the architecture
* Generate:
  * Architecture (Mermaid diagram + component list)
  * Azure services (with scale-appropriate SKUs)
  * Cost estimate (from Azure Retail Prices API, with fallback)
  * Business value (use-case-specific, quantified)
  * ROI (calculated from cost + value)
  * Presentation (downloadable PPTX)
* Ask for user approval after each step
* Allow iteration without re-running the full pipeline
* Be demo-stable (deterministic flow, no LLM-driven routing surprises)

---

# FINAL POSITIONING

This system must behave as:

> "A Project Manager copilot that helps Azure sellers shape, validate, and present deals — grounded in Microsoft best practices"

NOT:

> "An LLM that generates answers"
