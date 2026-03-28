# FRD-01: Orchestration & Project Manager

> **Source of truth:** `specs/v2/refactor.md` — sections §1, §2, §12, §13, §14.2, §16, §17
> **Status:** Draft
> **Scope:** Central orchestration engine, execution plan, state model, iteration, persistence, error handling

---

## 1. Overview

The Project Manager (PM) is the **central orchestration engine** of OneStopAgent. It is a **Python class, NOT a LangChain agent** (ref §2.1). It controls:

- Which agent runs and when (deterministic plan, not LLM-driven routing)
- Conversation flow (clarifying questions, approvals, summaries)
- Mode transitions (brainstorming → solutioning)
- Iteration (re-running subsets of agents on user feedback)
- Error handling (graceful degradation for every external dependency)

The PM is the **only** component that calls agents. Agents never call each other — they communicate exclusively through `AgentState` (ref §3.2).

> **Positioning (ref §Final Positioning):** "A Project Manager copilot that helps Azure sellers shape, validate, and present deals — grounded in Microsoft best practices" — NOT "an LLM that generates answers."

---

## 2. System Modes

### 2.1 Mode A — Brainstorming (ref §1.1)

**When it activates:**
- On first user message (default mode)
- When user says "different approach", "start over", "rethink", or "other options" (back-to-brainstorm intent)

**What happens:**
- PM explores ideas with the user via conversational LLM
- `BrainstormingAgent` suggests 2–4 Azure-relevant scenarios based on the user's industry and description
- `KnowledgeAgent` grounds suggestions in real Microsoft patterns via MCP
- PM classifies Azure fit:
  - **Strong** — clear workload that maps to Azure services (e.g., "e-commerce platform", "IoT telemetry")
  - **Weak** — generic IT need without clear Azure advantage (e.g., "improve our processes")
  - **Unclear** — not enough information to assess

**Azure fit gate:**
> ⚠️ MUST NOT proceed to architecture until Azure fit is classified as `"strong"` — either by the PM's assessment or by the user explicitly saying "proceed."

**PM must always explain WHY the system believes Azure is a fit** — e.g.:
> "Azure is a strong fit because your requirements for global availability and PCI-DSS compliance align with Azure Front Door and App Service Environment."

### 2.2 Mode B — Solutioning (ref §1.1)

**When it activates (both conditions checked):**
- PM classifies Azure fit as `"strong"`, **OR**
- User explicitly says "proceed", "let's go", "yes", or similar affirmative

**What happens:**
- PM builds the execution plan (see §4)
- Plan runs **sequentially** with approval gates
- Each step invokes exactly one agent via `agent.run(state)`
- Agent output is written to `AgentState`; PM summarizes and asks for approval

### 2.3 Guided vs Fast-Run (ref §1.2)

Two execution speed modes control where the PM pauses for approval:

| Aspect | Guided Mode (default) | Fast-Run Mode |
|--------|----------------------|---------------|
| **Activation** | Default | User says "run everything", "fast mode", "no stops", or "just build it" |
| **Pause points** | After **every** agent step | Only at **3 major gates** |
| **Gate 1** | — | After brainstorming (before entering Mode B) |
| **Gate 2** | — | After architecture generation (before services + cost) |
| **Gate 3** | — | Before presentation generation (final review) |
| **Intermediate steps** | Each pauses for approval | Services, cost, business value, ROI run without pausing |
| **Best for** | Demos, detailed walkthroughs, first-time users | Returning users, quick iterations |
| **PM announcement** | — | "Running in fast mode — I'll pause at architecture and before the final deck." |

---

## 3. Project Manager Class

### 3.1 Responsibilities (ref §2.1)

The PM must:

1. **Manage the conversation** — ask clarifying questions, acknowledge answers, explain reasoning
2. **Decide which agent to call next** — based on the execution plan, NOT LLM reasoning
3. **Maintain execution plan state** — which steps are done, pending, skipped, or failed
4. **Ask for user approval at gate points** — every step (guided) or major gates (fast-run)
5. **Handle iteration requests** — re-run specific agents when user asks for changes (see §6)
6. **Always explain Azure fit reasoning** — when transitioning from Mode A to Mode B

```python
class ProjectManager:
    """Central orchestrator. NOT a LangChain agent."""

    name = "Project Manager"
    emoji = "📋"

    def __init__(self, llm, agents: dict[str, BaseAgent]):
        self.llm = llm              # AzureChatOpenAI for conversation
        self.agents = agents        # {"brainstorming": BrainstormingAgent, ...}
        self.intent_interpreter = IntentInterpreter()

    async def handle_message(self, state: AgentState, message: str) -> AgentState:
        """Process a user message: classify intent, execute appropriate action."""
        intent = self.intent_interpreter.classify(message)
        # Route based on intent — see §3.2
        ...

    async def run_step(self, state: AgentState, step_id: str) -> AgentState:
        """Execute a single plan step: run agent, update state, emit SSE events."""
        agent = self.agents[step_id]
        # Emit plan_update(step_id, "running")
        state = await agent.run(state)
        # Emit plan_update(step_id, "completed")
        return state

    def build_plan(self, state: AgentState) -> list[str]:
        """Construct execution plan respecting agent toggles."""
        ...
```

### 3.2 Intent Interpreter (ref §2.2)

The PM classifies every user message into one of 9 intents. Classification is via a **simple keyword/pattern matcher, NOT an LLM call**.

#### Intent Table

| # | Intent | Trigger Patterns | PM Action |
|---|--------|-----------------|-----------|
| 1 | **Proceed** | `"proceed"`, `"yes"`, `"let's go"`, `"go"`, `"ok"`, `"sure"`, `"do it"`, `"start"`, `"continue"` | Advance to next step or start execution |
| 2 | **Refine** | `"refine"`, `"change"`, `"adjust"`, `"modify"`, `"update"`, `"make it..."` | Re-run current agent with feedback |
| 3 | **Skip** | `"skip"`, `"next"`, `"don't need this"` | Mark step as skipped, advance |
| 4 | **Fast-run** | `"run everything"`, `"fast mode"`, `"no stops"`, `"just build it"` | Switch `state.execution_mode` to `"fast-run"` |
| 5 | **Back to brainstorm** | `"different approach"`, `"start over"`, `"rethink"`, `"other options"` | Return to Mode A, reset `state.mode = "brainstorm"` |
| 6 | **Iteration** | `"make it cheaper"`, `"add HA"`, `"change region"`, contains architectural terms | Re-run affected agents per iteration mapping (see §6) |
| 7 | **Question** | Contains `"?"`, `"what"`, `"why"`, `"how"`, `"can you explain"` | PM responds conversationally (LLM call) |
| 8 | **New input** | Anything else | Treat as additional context, append to `state.clarifications` |
| 9 | **During execution** | Any message while an agent is running | Queue the message; do NOT interrupt the running agent |

#### Message-During-Execution Queueing (Intent #9)

When the user sends a message while an agent is actively running:
1. PM immediately responds: *"I'll address that after the current step completes."*
2. Message is queued (appended to an internal `pending_messages` list)
3. After the current agent completes, PM processes the queued message **before** advancing to the next step
4. The queued message is classified through the normal intent interpreter

#### LLM Fallback

If the keyword/pattern matcher **cannot classify** the message into any of the 9 intents:
- Fall back to an LLM call with prompt: *"Classify this user message as one of: proceed, refine, skip, fast-run, brainstorm, iteration, question, input."*
- Use the LLM-returned classification to route the message

```python
class IntentInterpreter:
    """Keyword-based intent classifier with LLM fallback."""

    INTENT_PATTERNS = {
        "proceed": ["proceed", "yes", "let's go", "go", "ok", "sure", "do it", "start", "continue"],
        "refine": ["refine", "change", "adjust", "modify", "update", "make it"],
        "skip": ["skip", "next", "don't need this"],
        "fast_run": ["run everything", "fast mode", "no stops", "just build it"],
        "brainstorm": ["different approach", "start over", "rethink", "other options"],
        "iteration": ["make it cheaper", "add ha", "change region", "add ai", "compliance"],
        "question": ["?", "what", "why", "how", "can you explain"],
    }

    def classify(self, message: str) -> str:
        """Classify user message by keyword matching. Returns intent string."""
        lower = message.lower().strip()
        for intent, patterns in self.INTENT_PATTERNS.items():
            if any(p in lower for p in patterns):
                return intent
        return "new_input"  # default — treated as additional context

    async def classify_with_fallback(self, message: str, llm) -> str:
        """Try keyword match first; if no match, use LLM."""
        intent = self.classify(message)
        if intent == "new_input":
            # LLM fallback for ambiguous messages
            response = await llm.ainvoke(
                f"Classify this user message as one of: proceed, refine, skip, "
                f"fast-run, brainstorm, iteration, question, input.\n\n"
                f"Message: {message}\n\nClassification:"
            )
            return response.content.strip().lower()
        return intent
```

### 3.3 Approval Flow (ref §2.4)

After each step completes (in guided mode) or at major gates (fast-run mode), the PM must:

1. **Summarize** the agent's output in 2–3 sentences (human-readable, not raw JSON)
2. **Highlight** one key insight — e.g.:
   - *"Total monthly cost: $1,200"*
   - *"Key risk: PCI-DSS compliance requires Premium SKUs"*
3. **Ask:**
   > "Does this look right? Say **proceed** to continue, **refine** to adjust, or **skip** to move on."

**User responses:**

| Response | PM Action |
|----------|-----------|
| **Proceed** | Advance to next step in plan |
| **Refine** | Re-run the current agent with user's feedback appended to `state.clarifications` |
| **Skip** | Mark step as `skipped` in plan, advance to next step |

---

## 4. Execution Plan

### 4.1 Default Plan (ref §2.3)

The default plan contains all 9 steps in fixed order:

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

Mapped to agent IDs:

| Step | Agent ID | Agent Class |
|------|----------|-------------|
| 1 | `brainstorming` | `BrainstormingAgent` |
| 2 | `azure_fit` | (PM internal — part of brainstorming evaluation) |
| 3 | `knowledge` | `KnowledgeAgent` |
| 4 | `architect` | `ArchitectAgent` |
| 5 | `specialist` | `AzureSpecialistAgent` |
| 6 | `cost` | `CostAgent` |
| 7 | `business_value` | `BusinessValueAgent` |
| 8 | `roi` | `ROIAgent` |
| 9 | `presentation` | `PresentationAgent` |

### 4.2 Plan Construction Rules (ref §2.3, §14.3)

1. The plan is built **once** at the start of Mode B
2. The plan is **NOT dynamically changed by LLM reasoning**
3. Steps are removed only if the user explicitly **toggles an agent off** (via sidebar toggle — ref §14.3)
4. When an agent is toggled off, PM must explain the impact:
   - *"Disabling Cost Specialist means no pricing data — ROI calculation will be qualitative only."*
   - *"Disabling Business Value means no value drivers — the presentation will omit the business case slide."*
5. **Architect is always required** — its toggle is disabled in the UI

### 4.3 Step State Machine (ref §2.3)

Each step transitions through these states:

```
pending → running → completed
                  → skipped
                  → failed
```

| State | Description |
|-------|-------------|
| `pending` | Step has not started yet |
| `running` | Agent is currently executing |
| `completed` | Agent finished successfully, output written to state |
| `skipped` | User chose to skip this step |
| `failed` | Agent threw an error (see §8 for fallback behavior) |

State is tracked in `AgentState` via `plan_steps`, `completed_steps`, `skipped_steps`, `failed_steps`, and `current_step`.

### 4.4 Plan UI Events (ref §14.2)

The plan checklist is updated via structured SSE events emitted by the PM:

| SSE Event Payload | Frontend Action |
|-------------------|-----------------|
| `{ "type": "plan_update", "step": "architect", "status": "running" }` | Show spinner on that step |
| `{ "type": "plan_update", "step": "architect", "status": "completed" }` | Show green checkmark ✅ |
| `{ "type": "plan_update", "step": "cost", "status": "skipped" }` | Show grey dash — |
| `{ "type": "plan_update", "step": "cost", "status": "failed" }` | Show red X ❌ |

Additional UI behaviors:
- Prior agent outputs collapse automatically when the next agent starts (accordion behavior)
- User can click any completed step to expand and review its output
- Clicking a completed step shows a **"Re-run"** button for iteration

---

## 5. Shared State Model — `AgentState` (ref §12)

Full class definition with all fields, types, and comments:

```python
from dataclasses import dataclass, field


@dataclass
class AgentState:
    """Shared state object passed between all agents.

    Agents read from and write to this object. Agents never call each other
    directly — AgentState is the only communication channel (ref §3.2).
    """

    # ── Core inputs ──────────────────────────────────────────────
    user_input: str = ""                # Original project description from user
    customer_name: str = ""             # Customer/company name (extracted or asked)
    clarifications: str = ""            # Accumulated user answers to PM questions

    # ── Mode tracking ────────────────────────────────────────────
    mode: str = "brainstorm"            # "brainstorm" (Mode A) or "solution" (Mode B)
    execution_mode: str = "guided"      # "guided" or "fast-run"
    azure_fit: str = ""                 # "strong", "weak", or "unclear"
    azure_fit_explanation: str = ""     # WHY Azure is a fit (human-readable)

    # ── Knowledge ────────────────────────────────────────────────
    retrieved_patterns: list[dict] = field(default_factory=list)
    # From KnowledgeAgent — list of dicts conforming to §4.3 schema:
    # {title, url, summary, workload_type, industry, compliance_tags,
    #  recommended_services, components, confidence_score}

    # ── Agent outputs ────────────────────────────────────────────
    brainstorming: dict = field(default_factory=dict)
    # Schema: {scenarios: [{title, description, azure_services, industry,
    #          azure_fit_reason}], recommended, azure_fit, azure_fit_explanation,
    #          industry}

    architecture: dict = field(default_factory=dict)
    # Schema: {mermaidCode, components: [{name, azureService, description}],
    #          narrative, basedOn}

    services: dict = field(default_factory=dict)
    # Schema: {selections: [{componentName, serviceName, sku, region,
    #          capabilities, skuNote}]}

    costs: dict = field(default_factory=dict)
    # Schema: {estimate: {currency, items: [{serviceName, sku, region,
    #          monthlyCost, pricingNote}], totalMonthly, totalAnnual,
    #          assumptions, pricingSource}}

    business_value: dict = field(default_factory=dict)
    # Schema: {drivers: [{name, description, estimate, monetizable}],
    #          executiveSummary, confidenceLevel}

    roi: dict = field(default_factory=dict)
    # Schema: {annual_cost, annual_value, roi_percent, payback_months,
    #          monetized_drivers: [{name, annual_value, method}],
    #          qualitative_benefits, assumptions}

    presentation_path: str = ""         # Path to generated .pptx file

    # ── Plan tracking ────────────────────────────────────────────
    plan_steps: list[str] = field(default_factory=list)
    # Ordered list of agent IDs in execution order

    completed_steps: list[str] = field(default_factory=list)
    # Agent IDs that have completed successfully

    skipped_steps: list[str] = field(default_factory=list)
    # Agent IDs that were skipped by user

    failed_steps: list[str] = field(default_factory=list)
    # Agent IDs that failed (error caught, pipeline continued)

    awaiting_approval: bool = False
    # True when PM is waiting for user to say proceed/refine/skip

    current_step: str = ""
    # Agent ID currently running or awaiting approval
```

---

## 6. Iteration Logic (ref §13)

When the user requests changes after the pipeline has run, the PM must:

1. **Identify** which agents are affected by the request
2. **Re-run ONLY those agents** in order, with user feedback appended to `state.clarifications`
3. **NOT re-run the full pipeline** — preserve unaffected agent outputs
4. **Show a diff summary** — e.g., *"Monthly cost reduced from $1,200 to $800 by switching from P2v3 to S1"*

### Iteration Mapping Table

| User Request | Agents to Re-run (in order) |
|-------------|----------------------------|
| "Make it cheaper" | `AzureSpecialistAgent` → `CostAgent` → `ROIAgent` → `PresentationAgent` |
| "Add high availability" | `ArchitectAgent` → `AzureSpecialistAgent` → `CostAgent` → `ROIAgent` → `PresentationAgent` |
| "Change region to Europe" | `AzureSpecialistAgent` → `CostAgent` → `PresentationAgent` |
| "Show me a different approach" | `BrainstormingAgent` (returns to Mode A) |
| "Add AI capabilities" | `ArchitectAgent` → `AzureSpecialistAgent` → `CostAgent` → `BusinessValueAgent` → `ROIAgent` → `PresentationAgent` |
| "What about compliance?" | `ArchitectAgent` → `AzureSpecialistAgent` (add compliance components) |

### Iteration Detection

The PM's intent interpreter classifies iteration requests via the **Iteration** intent (#6 in §3.2). When detected:

1. PM parses the request to determine the appropriate re-run set from the mapping table
2. PM announces: *"I'll update the architecture and re-calculate costs to reflect that change."*
3. PM re-runs only the affected agents in sequence
4. At each re-run step, PM follows the same approval flow (guided mode) or runs through without pausing (fast-run mode, unless it hits a major gate)

---

## 7. State Persistence (ref §16)

### 7.1 MVP (Ephemeral)

| Aspect | Behavior |
|--------|----------|
| **Storage** | In-memory Python dicts / `AgentState` objects |
| **Scope** | Per-server-process — server restart clears everything |
| **Sessions** | Ephemeral — each project exists only while the server is running |
| **Acceptability** | Sufficient for demos and development |
| **User warning** | PM should inform users: *"Note: your project data is stored in memory and will be lost if the server restarts."* |

### 7.2 Future (Persistent)

| Aspect | Behavior |
|--------|----------|
| **Storage** | Azure Cosmos DB or Azure Blob Storage (JSON serialization of `AgentState`) |
| **Sessions** | Resumable across server restarts |
| **Concurrency** | Multiple users can have concurrent sessions |
| **History** | Project history viewable and re-openable |

---

## 8. Error Handling & Graceful Degradation (ref §17)

> **Principle:** The system should NEVER crash or show a blank screen. Every failure is caught, reported to the user, and the pipeline continues where possible.

### Full Failure/Fallback Table

| # | Failure | Impact | Fallback Behavior |
|---|---------|--------|-------------------|
| 1 | **Azure OpenAI unavailable** | All LLM-dependent agents fail | PM announces: *"AI service is temporarily unavailable."* Offer to retry. |
| 2 | **MCP server unavailable** | KnowledgeAgent returns no patterns | Use local knowledge base (`data/knowledge_base.py`). Flag: *"⚠️ Not grounded in Microsoft Learn."* |
| 3 | **Azure Retail Prices API timeout** | Cost estimate uses mock prices | Tag pricing source as `"approximate"`. Show: *"Using reference pricing — verify with Azure Pricing Calculator."* |
| 4 | **Azure Retail Prices API returns no results** | Missing services in cost breakdown | Show $0 for those services with note: *"Pricing unavailable for {service}."* |
| 5 | **Malformed Mermaid from LLM** | Architecture diagram won't render | Show component table instead. Hide diagram silently (no crash). |
| 6 | **PPTX generation fails** | No downloadable deck | Show error: *"Presentation generation failed."* Offer slide content as markdown in chat. |
| 7 | **Agent throws unhandled exception** | Single agent step fails | Mark step as `failed` in plan. PM announces error. Skip to next agent. Pipeline continues. |
| 8 | **LLM returns invalid JSON** | Agent can't parse structured output | Retry once with stricter prompt. If still fails, use fallback template. |

### Error Flow in PM

```
Agent.run(state) raises exception
  → PM catches exception
  → PM marks step as "failed" in plan
  → PM emits SSE: { "type": "plan_update", "step": "<id>", "status": "failed" }
  → PM announces error to user (human-readable)
  → PM advances to next step in plan
  → Pipeline continues
```

---

## 9. API Contract

### 9.1 POST `/api/projects/{id}/chat` (ref §2, §14)

The primary endpoint for all user ↔ PM interaction.

**Request:**

```json
{
  "message": "string — user's chat message",
  "project_id": "string — UUID of the project/session"
}
```

**Response (SSE stream):**

The endpoint returns a Server-Sent Events stream (`text/event-stream`). Events include:

| Event Type | Payload | Description |
|------------|---------|-------------|
| `message` | `{ "type": "message", "role": "pm", "content": "..." }` | PM's conversational response |
| `plan_update` | `{ "type": "plan_update", "step": "architect", "status": "running" }` | Step state change |
| `agent_start` | `{ "type": "agent_start", "agent": "architect", "emoji": "🏗️", "label": "System Architect is working..." }` | Agent begins execution |
| `agent_result` | `{ "type": "agent_result", "agent": "architect", "content": "..." }` | Agent output (formatted markdown) |
| `error` | `{ "type": "error", "agent": "cost", "message": "API timeout..." }` | Agent failure notification |
| `approval` | `{ "type": "approval", "step": "architect", "summary": "...", "highlight": "..." }` | PM asking for proceed/refine/skip |

**Non-SSE behavior:** If the client does not accept `text/event-stream`, the endpoint should return a single JSON response with the PM's final message after all processing completes.

### 9.2 PATCH `/api/projects/{id}/agents/{agentId}` (ref §14.3)

Toggle an agent on or off, affecting the execution plan.

**Request:**

```json
{
  "enabled": false
}
```

**Response:**

```json
{
  "agentId": "cost",
  "enabled": false,
  "impact": "Disabling Cost Specialist means no pricing data — ROI calculation will be qualitative only.",
  "updated_plan": ["brainstorming", "knowledge", "architect", "specialist", "business_value", "roi", "presentation"]
}
```

**PM behavior on toggle:**
- PM rebuilds the execution plan excluding the disabled agent
- PM explains the downstream impact to the user (see §4.2)
- Architect agent cannot be disabled — PATCH returns `400` with error: `"Architect is required and cannot be disabled."`

---

## 10. Acceptance Criteria

- [ ] PM asks clarifying questions on first user message (Mode A brainstorming)
- [ ] PM presents execution plan before proceeding (shown as checklist)
- [ ] PM pauses at correct gates — every step in guided mode, 3 major gates in fast-run mode
- [ ] Intent interpreter classifies all 9 patterns correctly (proceed, refine, skip, fast-run, brainstorm, iteration, question, new input, during-execution)
- [ ] LLM fallback triggers when keyword matcher cannot classify
- [ ] Messages sent during agent execution are queued and processed after step completes
- [ ] PM explains Azure fit reasoning when transitioning from Mode A to Mode B
- [ ] Iteration re-runs only affected agents (per iteration mapping table)
- [ ] Iteration shows diff summary (before vs. after)
- [ ] Agent toggle disables step in plan and PM explains impact
- [ ] Architect cannot be toggled off
- [ ] SSE events emitted for all plan state changes (running, completed, skipped, failed)
- [ ] Errors don't crash the pipeline — graceful fallback for each dependency per §8 table
- [ ] State is ephemeral (in-memory) for MVP with user warning
- [ ] `AgentState` contains all fields defined in §5
