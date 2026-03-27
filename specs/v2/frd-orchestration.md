# FRD: Controlled Multi-Agent Orchestration

> **Version:** 2.0  
> **Status:** Current  
> **Replaces:** specs/frd-orchestration.md (v1)  
> **Component:** `src/python-api/orchestrator.py`, `src/python-api/agents/pm_agent.py`

---

## 1. Overview

The orchestration engine manages the execution of specialist agents in a deterministic, sequential pipeline. There is no autonomous agent reasoning — the flow is explicit and predictable.

**Design philosophy:** Deterministic > autonomous for reliability and debuggability. The system uses a controlled orchestration pattern where the Project Manager builds an explicit execution plan and the Orchestrator runs agents in strict sequence.

```
User → Project Manager (planner) → Execution Plan → Agents run in sequence → Results stream via SSE
```

**Why not ReAct / autonomous agents?**

- Deterministic execution > autonomous reasoning for demos and reliability
- Explicit flow > hidden reasoning for debuggability
- Predictable execution order > LLM-decided order for consistency
- No LangGraph, no ReAct agents, no chains — just direct LLM calls inside each agent class

---

## 2. Phases

### 2.1 Clarification Phase (`clarify` state)

**Trigger:** First user message to a new project.

**Behavior:**

1. Orchestrator stores `state.user_input = message`
2. PM calls `ask_clarifications(message)` using an LLM with this system prompt:

   ```
   You are an Azure solution project manager. The user described a project.
   Respond with:
   1. A brief acknowledgment (1 sentence)
   2. 2-3 clarifying questions as a numbered list
   3. An execution plan showing which agents will run

   Format your response in markdown. End with:
   "Ready when you are — just say **proceed** or answer the questions above."
   ```

3. PM calls `build_plan(active_agents)` to create the execution sequence
4. PM formats the plan with emojis and agent names:

   ```markdown
   ## 📋 Execution Plan

   1. 🏗️ **System Architect**
   2. ☁️ **Azure Specialist**
   3. 💰 **Cost Specialist**
   ...
   ```

5. Response (questions + plan) is yielded as a `pm_response` SSE event
6. State transitions to `ready`

### 2.2 Execution Phase (`ready` → `executing` state)

**Trigger:** User confirms execution (says "proceed", "let's go", answers questions, etc.).

**Behavior:**

1. Orchestrator stores `state.clarifications = message`
2. Acknowledges plan execution start
3. For each agent step in the plan:
   - **Announce:** Yield `agent_start` event — `"{emoji} **{name}** is working..."`
   - **Run:** Execute `agent.run(state)` in a thread pool (`run_in_executor`) to avoid blocking the async event loop
   - **Format:** Call `format_agent_output(agent_id, state)` to produce markdown
   - **Yield:** Stream `agent_result` event with formatted output
4. State transitions to `executing` → `done`

### 2.3 Follow-up Phase (`executing`/`done` state)

**Trigger:** Any subsequent user messages after execution.

**Behavior:**

1. Message routed to PM for conversational response
2. PM uses LLM with full solution context:

   ```python
   llm.invoke([
       {"role": "system", "content": "You are an Azure solution project manager..."},
       {"role": "user", "content": f"Context: {state.to_context_string()}\n\nUser says: {message}"}
   ])
   ```

3. PM can address follow-up questions, suggest modifications, or explain outputs
4. User can request re-runs of specific agents (future capability)

---

## 3. Execution Plan

### 3.1 Default Order

```python
DEFAULT_PLAN = ["architect", "azure_services", "cost", "business_value", "presentation"]
```

When envisioning is active, it is inserted at the start:

```python
["envisioning", "architect", "azure_services", "cost", "business_value", "presentation"]
```

### 3.2 Agent Toggle Rules

**Plan construction logic:**

```python
def build_plan(active_agents: list[str]) -> list[str]:
    plan = []
    for agent_id in DEFAULT_PLAN:
        mapped = agent_id.replace("_", "-")   # internal → API format
        if mapped in active_agents or agent_id == "architect":
            plan.append(agent_id)
    return plan
```

**Rules:**

- Disabled agents are removed from the plan
- `architect` is always included (cannot be disabled)
- `pm` is always active but is not in the execution plan (it orchestrates)
- Plan is built once at confirmation time based on current `active_agents`

**Agent ID mapping** (internal ↔ API format):

| Internal ID | API/Active Agents ID |
|-------------|---------------------|
| `architect` | `architect` |
| `azure_services` | `azure-specialist` |
| `cost` | `cost` |
| `business_value` | `business-value` |
| `presentation` | `presentation` |
| `envisioning` | `envisioning` |

### 3.3 Plan Adjustment

- User can say "skip cost" during clarification → Cost Specialist removed from plan
- User can say "add envisioning" → Envisioning inserted at start of plan
- User can answer questions AND request adjustments in the same message

### 3.4 Agent Info Registry

```python
AGENT_INFO = {
    "envisioning":    {"name": "Envisioning",       "emoji": "💡"},
    "architect":      {"name": "System Architect",   "emoji": "🏗️"},
    "azure_services": {"name": "Azure Specialist",   "emoji": "☁️"},
    "cost":           {"name": "Cost Specialist",     "emoji": "💰"},
    "business_value": {"name": "Business Value",      "emoji": "📊"},
    "presentation":   {"name": "Presentation",        "emoji": "📑"},
}
```

---

## 4. Shared State (AgentState)

The `AgentState` object is a Python class that flows through the entire pipeline. Each agent reads from and writes to this shared state.

### 4.1 State Fields

| Field | Type | Written By | Read By | Description |
|-------|------|------------|---------|-------------|
| `user_input` | `str` | Orchestrator | All agents | Original user project description |
| `customer_name` | `str` | Orchestrator | Presentation | Optional customer name |
| `clarifications` | `str` | Orchestrator | All agents | User's responses to PM questions |
| `plan` | `list[str]` | PM | Orchestrator | Ordered list of agent IDs to execute |
| `envisioning` | `dict[str, Any]` | Envisioning | Architect | Reference scenarios and recommendations |
| `architecture` | `dict[str, Any]` | Architect | Azure Specialist, Cost, BV, Presentation |
| `services` | `dict[str, Any]` | Azure Specialist | Cost, BV, Presentation |
| `costs` | `dict[str, Any]` | Cost | BV, Presentation |
| `business_value` | `dict[str, Any]` | Business Value | Presentation |
| `presentation_path` | `str` | Presentation | API (download endpoint) |

### 4.2 Context String Generation

`state.to_context_string()` builds a summary for LLM context in follow-up conversations:

```
User request: {user_input}
Clarifications: {clarifications}
Architecture: {narrative}
Components: {components}
Services: {selections}
Cost: ${totalMonthly}/month
```

---

## 5. SSE Streaming Events

### 5.1 Protocol

- Client sends `Accept: text/event-stream` header with POST request
- Server responds with `Content-Type: text/event-stream`
- Each event formatted as: `event: message\ndata: {json}\n\n`
- Stream terminated with: `event: done\ndata: [DONE]\n\n`

### 5.2 Event Types

| Event Type (metadata.type) | When | Content | Agent ID |
|---------------------------|------|---------|----------|
| `pm_response` | PM speaks (clarification, follow-up) | Markdown text with questions/plan | `pm` |
| `agent_start` | Agent begins execution | `"{emoji} **{name}** is working..."` | agent ID |
| `agent_result` | Agent completes successfully | Formatted markdown output | agent ID |
| `agent_error` | Agent fails | Error message: `"⚠️ {name} failed: {error}"` | agent ID |
| `error` | System-level error | Error description | `pm` |

### 5.3 SSE Message Schema

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "role": "agent",
  "agent_id": "architect",
  "content": "## 🏗️ Architecture Design\n...",
  "metadata": {
    "type": "agent_result",
    "agent": "architect"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 5.4 Non-Streaming Fallback

When client does not send `Accept: text/event-stream`, the endpoint returns a JSON array of `ChatMessage` objects after all agents complete.

---

## 6. Error Handling

### 6.1 Agent-Level Errors

Each agent execution is wrapped in try/except:

```python
try:
    state = await loop.run_in_executor(None, agent.run, state)
except Exception as e:
    yield ChatMessage(
        agent_id=step,
        content=f"⚠️ {name} failed: {str(e)}",
        metadata={"type": "agent_error", "agent": step}
    )
    continue  # Pipeline continues to next agent
```

**Behavior:**

- On failure: error message streamed to frontend, pipeline continues to next agent
- Each agent independently handles internal errors with fallback behaviors
- Stack traces printed to server logs via `traceback.print_exc()`

### 6.2 Fatal Errors

- If the Architect agent fails and produces no output, downstream agents (Azure Specialist, Cost) will have no components to process — they will produce empty/minimal output but won't crash
- System-level errors (e.g., state corruption) yield an `error` event and stop the pipeline

### 6.3 Thread Pool Execution

All agent `run()` methods execute in the default thread pool via `run_in_executor` to prevent blocking the FastAPI async event loop. This ensures SSE streaming remains responsive.

---

## 7. API Endpoints

### 7.1 Chat Endpoint

```
POST /api/projects/{project_id}/chat
```

**Request:**

```json
{
  "message": "string (1-10000 chars)"
}
```

**Headers:**

| Header | Value | Purpose |
|--------|-------|---------|
| `Content-Type` | `application/json` | Required |
| `Accept` | `text/event-stream` | Enables SSE streaming |
| `x-user-id` | `string` | User identification |

**Response (streaming):** SSE event stream as described in §5.

**Response (non-streaming):** JSON array of `ChatMessage` objects.

### 7.2 Related Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/health` | Health check |
| `GET` | `/api/info` | API version and framework info |
| `POST` | `/api/projects` | Create new project |
| `GET` | `/api/projects` | List user's projects |
| `GET` | `/api/projects/{id}` | Get project details |
| `GET` | `/api/projects/{id}/chat` | Get chat history |
| `GET` | `/api/projects/{id}/agents` | Get available agents |
| `PATCH` | `/api/projects/{id}/agents/{agentId}` | Toggle agent on/off |

---

## 8. State Machine

```
┌──────────┐   first msg    ┌──────────┐   user confirms   ┌───────────┐   all done   ┌──────┐
│ clarify  │ ──────────────→│  ready   │ ─────────────────→│ executing │ ────────────→│ done │
└──────────┘                └──────────┘                   └───────────┘              └──────┘
                                                                                         │
                                                                follow-up messages       │
                                                                ←────────────────────────┘
```

---

## 9. Acceptance Criteria

- [ ] First user message triggers clarification with 2-3 questions and execution plan
- [ ] User confirmation triggers sequential agent execution
- [ ] Disabled agents are excluded from the execution plan
- [ ] Architect agent cannot be disabled
- [ ] Each agent's output streams immediately via SSE when that agent completes
- [ ] Agent failures are caught and reported without stopping the pipeline
- [ ] Follow-up messages are handled conversationally by the PM with full context
- [ ] Non-streaming fallback returns complete JSON array of messages
- [ ] Agent execution runs in thread pool (non-blocking)
- [ ] State transitions follow: `clarify` → `ready` → `executing` → `done`
