# FRD-CHAT: Chat Interface & Project Management

## 1. Overview

This Feature Requirement Document specifies the detailed functional behaviour of the OneStopAgent chat interface and project management capabilities. It covers three user stories and four functional requirements from the PRD:

| Ref | Title | Scope |
|-----|-------|-------|
| **US-1** | Start a New Project | Project creation via free-text description, agent activation, workspace provisioning |
| **US-8** | Agent Selection and Control | Sidebar agent management, activate/deactivate, System Architect lock |
| **US-9** | Guided Questioning | PM Agent structured interview, skip/proceed, assumption flagging |
| **FR-1** | Agent Orchestration API | REST endpoints for projects, chat, and agent control |
| **FR-5** | Frontend Pages | Landing page, project list, chat interface routes |
| **FR-6** | Chat Interface | Chat thread, agent cards, rich content rendering, input controls |
| **FR-8** | Authentication & Authorization | Entra ID SSO, JWT, ownership, rate limiting, audit |

The document provides exact API contracts, validation rules, flow descriptions, security requirements, frontend behaviour, error responses, and edge cases sufficient for implementation and test-case derivation.

---

## 2. API Contracts

All endpoints are prefixed with `/api`. All request and response bodies are `application/json` unless otherwise noted. Timestamps use ISO 8601 format (`YYYY-MM-DDTHH:mm:ss.sssZ`). UUIDs are v4.

### 2.1 POST /api/projects

Create a new project workspace.

**Request**

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `description` | `string` | Yes | 1–5 000 chars, trimmed | Free-text description of the customer opportunity |
| `customerName` | `string` | No | 1–200 chars, trimmed | Optional customer or account name |

```json
{
  "description": "The customer wants to modernise their on-premises .NET monolith to Azure, serving 50k concurrent users across EMEA.",
  "customerName": "Contoso Ltd"
}
```

**Responses**

| Status | Condition | Body |
|--------|-----------|------|
| `201 Created` | Project created successfully | `{ "projectId": "<uuid>" }` |
| `400 Bad Request` | Validation failure | `{ "error": "<message>" }` |
| `401 Unauthorized` | Missing or invalid Bearer token | `{ "error": "Authentication required." }` |
| `429 Too Many Requests` | Rate limit exceeded | `{ "error": "Rate limit exceeded. Try again in <N> seconds." }` |
| `500 Internal Server Error` | Storage or agent initialisation failure | `{ "error": "Project creation failed. Please try again." }` |

**201 Example**

```json
{
  "projectId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Side Effects**
1. A `Project` record is persisted with `status: 'in_progress'`, `userId` set to the authenticated user, `activeAgents` initialised to all agents, and an empty `context`.
2. An initial `ChatMessage` is created with `role: 'agent'`, `agentId: 'pm'`, containing the PM Agent acknowledgement.
3. The PM Agent evaluates the description:
   - If sufficiently detailed → proceeds to guided questioning or agent pipeline.
   - If vague → routes to the Envisioning Agent.

---

### 2.2 GET /api/projects

List all projects for the authenticated user, ordered by `updatedAt` descending.

**Request**

No request body. No query parameters in MVP.

**Responses**

| Status | Condition | Body |
|--------|-----------|------|
| `200 OK` | Success (may be empty array) | `[ { projectId, description, customerName, status, updatedAt } ]` |
| `401 Unauthorized` | Missing or invalid token | `{ "error": "Authentication required." }` |
| `429 Too Many Requests` | Rate limit exceeded | `{ "error": "Rate limit exceeded. Try again in <N> seconds." }` |

**200 Example**

```json
[
  {
    "projectId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "description": "Modernise on-premises .NET monolith to Azure...",
    "customerName": "Contoso Ltd",
    "status": "in_progress",
    "updatedAt": "2025-01-15T14:30:00.000Z"
  },
  {
    "projectId": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "description": "AI-powered customer support chatbot for retail...",
    "customerName": null,
    "status": "completed",
    "updatedAt": "2025-01-14T09:15:00.000Z"
  }
]
```

**Notes**
- The `description` field is truncated to the first 200 characters in the list response. Full description is available via `GET /api/projects/:id`.
- An authenticated user with no projects receives `200` with `[]`.

---

### 2.3 GET /api/projects/:id

Retrieve full project state including all agent outputs.

**Path Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `id` | `string (UUID)` | Project identifier |

**Responses**

| Status | Condition | Body |
|--------|-----------|------|
| `200 OK` | Project found, user is owner | Full `Project` object (see below) |
| `401 Unauthorized` | Missing or invalid token | `{ "error": "Authentication required." }` |
| `403 Forbidden` | User is not the project owner | `{ "error": "You do not have access to this project." }` |
| `404 Not Found` | Project ID does not exist | `{ "error": "Project not found." }` |
| `429 Too Many Requests` | Rate limit exceeded | `{ "error": "Rate limit exceeded. Try again in <N> seconds." }` |

**200 Example**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "userId": "user-oid-from-entra",
  "description": "Modernise on-premises .NET monolith to Azure, serving 50k concurrent users across EMEA.",
  "customerName": "Contoso Ltd",
  "activeAgents": ["pm", "envisioning", "architect", "azure-specialist", "cost", "business-value", "presentation"],
  "context": {
    "requirements": {
      "targetUsers": "50,000 concurrent users",
      "geography": "EMEA"
    },
    "architecture": null,
    "services": null,
    "costEstimate": null,
    "businessValue": null,
    "envisioningSelections": null
  },
  "status": "in_progress",
  "createdAt": "2025-01-15T14:00:00.000Z",
  "updatedAt": "2025-01-15T14:30:00.000Z"
}
```

---

### 2.4 POST /api/projects/:id/chat

Send a chat message to the orchestrator (PM Agent) or a specific agent.

**Path Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `id` | `string (UUID)` | Project identifier |

**Request Body**

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `message` | `string` | Yes | 1–10 000 chars, trimmed | The user's message |
| `targetAgent` | `string` | No | Must be a valid agent ID | Routes message to a specific agent instead of the PM |

Valid `targetAgent` values: `"pm"`, `"envisioning"`, `"architect"`, `"azure-specialist"`, `"cost"`, `"business-value"`, `"presentation"`.

```json
{
  "message": "The customer needs HIPAA compliance and the solution must be deployed in US East.",
  "targetAgent": null
}
```

**Responses**

| Status | Condition | Body |
|--------|-----------|------|
| `200 OK` | Agent responded successfully | Agent response object (see below) |
| `400 Bad Request` | Validation failure | `{ "error": "<message>" }` |
| `401 Unauthorized` | Missing or invalid token | `{ "error": "Authentication required." }` |
| `403 Forbidden` | User is not the project owner | `{ "error": "You do not have access to this project." }` |
| `404 Not Found` | Project ID does not exist | `{ "error": "Project not found." }` |
| `422 Unprocessable Entity` | Target agent is inactive or invalid | `{ "error": "Agent '<agentId>' is not active in this project." }` |
| `429 Too Many Requests` | Rate limit exceeded | `{ "error": "Rate limit exceeded. Try again in <N> seconds." }` |
| `504 Gateway Timeout` | Agent did not respond within 120s | `{ "error": "Agent response timed out. Please try again." }` |

**200 Example**

```json
{
  "id": "msg-uuid-001",
  "projectId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "role": "agent",
  "agentId": "pm",
  "content": "Thank you! I've noted that HIPAA compliance is required and the deployment region is US East. Let me ask a few more questions to refine the scope.\n\nWhat is the expected data volume (in GB) that the application will process monthly?",
  "metadata": {
    "questionIndex": 3,
    "totalQuestions": 10,
    "category": "scale"
  },
  "timestamp": "2025-01-15T14:32:00.000Z"
}
```

**Side Effects**
1. The user message is persisted as a `ChatMessage` with `role: 'user'`.
2. The agent response is persisted as a `ChatMessage` with `role: 'agent'`.
3. The project `context.requirements` may be updated based on extracted information.
4. The project `updatedAt` is refreshed.

---

### 2.5 GET /api/projects/:id/chat

Retrieve chat history for a project with cursor-based pagination.

**Path Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `id` | `string (UUID)` | Project identifier |

**Query Parameters**

| Param | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `limit` | `integer` | `50` | 1–100 | Maximum number of messages to return |
| `before` | `string` | _(none)_ | Valid message UUID | Return messages older than this cursor |

**Responses**

| Status | Condition | Body |
|--------|-----------|------|
| `200 OK` | Success | `{ "messages": ChatMessage[], "hasMore": boolean, "nextCursor": string \| null }` |
| `400 Bad Request` | Invalid query parameters | `{ "error": "<message>" }` |
| `401 Unauthorized` | Missing or invalid token | `{ "error": "Authentication required." }` |
| `403 Forbidden` | User is not the project owner | `{ "error": "You do not have access to this project." }` |
| `404 Not Found` | Project or cursor not found | `{ "error": "Project not found." }` |
| `429 Too Many Requests` | Rate limit exceeded | `{ "error": "Rate limit exceeded. Try again in <N> seconds." }` |

**200 Example**

```json
{
  "messages": [
    {
      "id": "msg-uuid-002",
      "projectId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "role": "agent",
      "agentId": "pm",
      "content": "Welcome! I'm your Project Manager Agent. I've reviewed your description...",
      "metadata": null,
      "timestamp": "2025-01-15T14:00:05.000Z"
    },
    {
      "id": "msg-uuid-001",
      "projectId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "role": "user",
      "agentId": null,
      "content": "Modernise on-premises .NET monolith to Azure...",
      "metadata": null,
      "timestamp": "2025-01-15T14:00:00.000Z"
    }
  ],
  "hasMore": false,
  "nextCursor": null
}
```

**Notes**
- Messages are returned in reverse chronological order (newest first).
- The `nextCursor` value, when present, should be passed as the `before` parameter in the next request.
- When `hasMore` is `false`, `nextCursor` is `null`.

---

### 2.6 GET /api/projects/:id/agents

List all agents and their current status for a project.

**Path Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `id` | `string (UUID)` | Project identifier |

**Responses**

| Status | Condition | Body |
|--------|-----------|------|
| `200 OK` | Success | `{ "agents": AgentStatus[] }` |
| `401 Unauthorized` | Missing or invalid token | `{ "error": "Authentication required." }` |
| `403 Forbidden` | User is not the project owner | `{ "error": "You do not have access to this project." }` |
| `404 Not Found` | Project does not exist | `{ "error": "Project not found." }` |
| `429 Too Many Requests` | Rate limit exceeded | `{ "error": "Rate limit exceeded. Try again in <N> seconds." }` |

**200 Example**

```json
{
  "agents": [
    {
      "agentId": "pm",
      "name": "Project Manager",
      "status": "idle",
      "active": true,
      "canDeactivate": false,
      "deactivateReason": null
    },
    {
      "agentId": "architect",
      "name": "System Architect",
      "status": "working",
      "active": true,
      "canDeactivate": false,
      "deactivateReason": "System Architect is required for all downstream agents to function."
    },
    {
      "agentId": "envisioning",
      "name": "Envisioning",
      "status": "idle",
      "active": true,
      "canDeactivate": true,
      "deactivateReason": null
    },
    {
      "agentId": "azure-specialist",
      "name": "Azure Specialist",
      "status": "idle",
      "active": true,
      "canDeactivate": true,
      "deactivateReason": null
    },
    {
      "agentId": "cost",
      "name": "Cost Specialist",
      "status": "idle",
      "active": false,
      "canDeactivate": true,
      "deactivateReason": null
    },
    {
      "agentId": "business-value",
      "name": "Business Value",
      "status": "idle",
      "active": true,
      "canDeactivate": true,
      "deactivateReason": null
    },
    {
      "agentId": "presentation",
      "name": "Presentation",
      "status": "error",
      "active": true,
      "canDeactivate": true,
      "deactivateReason": null
    }
  ]
}
```

**AgentStatus Schema**

| Field | Type | Description |
|-------|------|-------------|
| `agentId` | `string` | Unique agent identifier |
| `name` | `string` | Human-readable agent name |
| `status` | `"idle" \| "working" \| "error"` | Current execution status |
| `active` | `boolean` | Whether the agent is activated for this project |
| `canDeactivate` | `boolean` | Whether the UI should allow deactivation |
| `deactivateReason` | `string \| null` | Tooltip text explaining why deactivation is blocked |

---

### 2.7 PATCH /api/projects/:id/agents/:agentId

Activate or deactivate an agent.

**Path Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `id` | `string (UUID)` | Project identifier |
| `agentId` | `string` | Agent identifier |

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `active` | `boolean` | Yes | `true` to activate, `false` to deactivate |

```json
{
  "active": false
}
```

**Responses**

| Status | Condition | Body |
|--------|-----------|------|
| `200 OK` | Agent state updated | Updated `AgentStatus` object |
| `400 Bad Request` | Missing or invalid `active` field | `{ "error": "Field 'active' (boolean) is required." }` |
| `401 Unauthorized` | Missing or invalid token | `{ "error": "Authentication required." }` |
| `403 Forbidden` | User is not the project owner | `{ "error": "You do not have access to this project." }` |
| `404 Not Found` | Project or agent does not exist | `{ "error": "Project not found." }` or `{ "error": "Agent '<agentId>' not found." }` |
| `409 Conflict` | Attempting to deactivate a protected agent | `{ "error": "System Architect cannot be deactivated. It is required for all downstream agents." }` |
| `422 Unprocessable Entity` | Deactivating a currently working agent without confirmation | `{ "error": "Agent '<agentId>' is currently working. Set 'confirm: true' to cancel its task and deactivate.", "agentStatus": "working" }` |
| `429 Too Many Requests` | Rate limit exceeded | `{ "error": "Rate limit exceeded. Try again in <N> seconds." }` |

**Extended Request (with confirmation)**

When deactivating a working agent, the client must confirm:

```json
{
  "active": false,
  "confirm": true
}
```

**200 Example**

```json
{
  "agentId": "cost",
  "name": "Cost Specialist",
  "status": "idle",
  "active": false,
  "canDeactivate": true,
  "deactivateReason": null
}
```

**Side Effects**
1. The project `activeAgents` array is updated.
2. If deactivating a working agent with `confirm: true`, the agent's in-progress task is cancelled, a `ChatMessage` is created noting the cancellation, and the agent status becomes `idle`.
3. The PM Agent is notified and adjusts the pipeline accordingly.
4. The project `updatedAt` is refreshed.

---

## 3. Validation Rules

Validations are applied in the order listed. The first failing rule produces the error response; subsequent rules are not evaluated.

### 3.1 Project Description (POST /api/projects)

| # | Rule | Check | Error Message |
|---|------|-------|---------------|
| 1 | Presence | `description` field exists and is a string | `"Field 'description' is required."` |
| 2 | Non-empty | Trimmed length ≥ 1 | `"Project description must not be empty."` |
| 3 | Max length | Trimmed length ≤ 5 000 | `"Project description must not exceed 5,000 characters."` |
| 4 | Customer name length | If `customerName` is provided, trimmed length ≤ 200 | `"Customer name must not exceed 200 characters."` |
| 5 | No prohibited content | Input does not contain executable script tags or known injection patterns | `"Description contains invalid content."` |

### 3.2 Chat Message (POST /api/projects/:id/chat)

| # | Rule | Check | Error Message |
|---|------|-------|---------------|
| 1 | Presence | `message` field exists and is a string | `"Field 'message' is required."` |
| 2 | Non-empty | Trimmed length ≥ 1 | `"Message must not be empty."` |
| 3 | Max length | Trimmed length ≤ 10 000 | `"Message must not exceed 10,000 characters."` |
| 4 | Valid target agent | If `targetAgent` is provided, it must be one of the recognised agent IDs | `"Unknown agent '<targetAgent>'."` |
| 5 | Active target agent | If `targetAgent` is provided, the agent must be active in the project | `"Agent '<targetAgent>' is not active in this project."` |
| 6 | No prohibited content | Input passes sanitisation checks | `"Message contains invalid content."` |

### 3.3 Agent Activation (PATCH /api/projects/:id/agents/:agentId)

| # | Rule | Check | Error Message |
|---|------|-------|---------------|
| 1 | Presence | `active` field exists and is a boolean | `"Field 'active' (boolean) is required."` |
| 2 | Agent exists | `agentId` matches a known agent | `"Agent '<agentId>' not found."` |
| 3 | Protected agent | If deactivating, agent is not `architect` | `"System Architect cannot be deactivated. It is required for all downstream agents."` |
| 4 | Working agent | If deactivating a working agent, `confirm: true` must be set | `"Agent '<agentId>' is currently working. Set 'confirm: true' to cancel its task and deactivate."` |

### 3.4 Chat History (GET /api/projects/:id/chat)

| # | Rule | Check | Error Message |
|---|------|-------|---------------|
| 1 | Limit range | `limit` is an integer between 1 and 100 (inclusive) | `"Parameter 'limit' must be an integer between 1 and 100."` |
| 2 | Valid cursor | If `before` is provided, it must be a valid UUID matching an existing message in the project | `"Invalid cursor: message not found."` |

---

## 4. Chat Flow

### 4.1 Project Creation Flow

```
Step 1 — User opens landing page (/)
         UI presents: "Describe your customer scenario" input + "Create Project" button.

Step 2 — User types description, optionally fills customer name, clicks "Create Project".
         Frontend calls POST /api/projects { description, customerName? }.

Step 3 — Server validates input (§3.1).
         On failure → 400 with error message; UI shows inline error; user corrects.

Step 4 — Server creates Project record:
           id:           UUID v4
           userId:       extracted from JWT `oid` claim
           description:  user input (trimmed)
           customerName: user input or null
           activeAgents: ["pm","envisioning","architect","azure-specialist","cost","business-value","presentation"]
           context:      { requirements: {} }
           status:       "in_progress"
           createdAt:    now
           updatedAt:    now

Step 5 — Server returns 201 { projectId }.
         Frontend navigates to /project/:projectId.

Step 6 — PM Agent generates acknowledgement message:
           - Echoes back a summary of the description.
           - Lists the agents that will be activated.
           - States next step (guided questioning or envisioning).

Step 7 — PM Agent evaluates description clarity:
           a) Sufficient detail → proceed to Guided Questioning (§4.2).
           b) Vague / no clear use case → route to Envisioning Agent first.
              Envisioning Agent posts a message with suggested scenarios.

Step 8 — Agent statuses update:
           PM Agent → "working" during evaluation, then "idle".
           Envisioning Agent → "working" if routed to, then "idle".
           Sidebar reflects changes in real time.
```

**Failure Scenario**

```
Step 3a — Storage unavailable (Cosmos DB error):
           Server returns 500 { error: "Project creation failed. Please try again." }.
           UI displays error banner with retry button.
           No project record or chat messages are created (transaction rollback).
```

### 4.2 Guided Questioning Flow

```
Step 1 — PM Agent determines the next unanswered topic from the list:
           1. Target users / audience
           2. Expected scale (concurrent users, data volume)
           3. Geographic requirements (regions, data residency)
           4. Compliance needs (HIPAA, GDPR, SOC 2, etc.)
           5. Integration points (existing systems, APIs, databases)
           6. Timeline (MVP date, GA date)
           7. Value drivers (cost savings, revenue growth, etc.)

Step 2 — PM Agent posts a question as a ChatMessage:
           role: "agent", agentId: "pm"
           metadata: { questionIndex: N, totalQuestions: 10, category: "<topic>" }

Step 3 — User responds in one of three ways:
           a) Answers the question → message is parsed, answer stored in context.requirements[category].
           b) Skips the question → says "skip" or leaves blank.
              PM Agent stores a default and flags it:
              metadata: { assumption: true, defaultValue: "<value>" }
              PM Agent informs user: "I'll assume <default>. You can change this later."
           c) Ends questioning → says "proceed" or clicks "Start Agents" button.
              PM Agent flags all remaining unanswered topics as assumptions.
              Flow advances to agent pipeline.

Step 4 — PM Agent posts the next question (back to Step 1).
         Repeat until:
           - All topics are covered, OR
           - 10 questions have been asked (hard cap), OR
           - User ends questioning early.

Step 5 — PM Agent posts a summary message:
           "Here's what I've gathered:"
           - Lists all requirements (answered and assumed).
           - Assumptions are marked with ⚠️ emoji.
           - "Ready to start the agents? [Start Agents] button"

Step 6 — User confirms → PM Agent activates the agent pipeline.
         Agent statuses update as each agent begins work.
```

**Question Format Example**

```
PM Agent: "What geographic regions should this solution be deployed to?
           Common options: US East, US West, West Europe, Southeast Asia.
           You can specify multiple regions or say 'skip' to let me decide."

           metadata: { questionIndex: 3, totalQuestions: 10, category: "geography" }
```

**Assumption Flagging Example**

```
PM Agent: "I'll assume a single-region deployment in US East for now.
           ⚠️ This is an assumption — you can update it at any time by
           telling me your preferred region."

           metadata: { assumption: true, defaultValue: "US East", category: "geography" }
```

### 4.3 Agent Selection Flow

```
Step 1 — User views sidebar showing all agents with status indicators:
           ● Grey dot  = Idle (agent available, not currently working)
           ● Blue dot (animated pulse) = Working (agent processing)
           ● Red dot   = Error (agent encountered a failure)

Step 2 — User clicks on an agent toggle to deactivate it.
         Frontend calls PATCH /api/projects/:id/agents/:agentId { active: false }.

Step 3 — Server validates (§3.3):
           a) Agent is "architect" → 409 Conflict.
              UI shows tooltip: "System Architect is required for all downstream agents."
              Toggle remains in active state.

           b) Agent is currently "working" → 422 Unprocessable Entity.
              UI shows confirmation dialog:
              "⚠️ [Agent Name] is currently working. Deactivating it will cancel
               the in-progress task. Are you sure?"
              [Cancel] [Confirm]
              If confirmed → re-send PATCH with { active: false, confirm: true }.

           c) Agent is idle and deactivatable → 200 OK.
              Sidebar updates: agent toggle moves to inactive, dot turns grey.

Step 4 — PM Agent adjusts pipeline:
           Posts a ChatMessage: "I've removed [Agent Name] from the pipeline.
           The following steps will be skipped: [list affected outputs]."

Step 5 — User re-activates agent.
         Frontend calls PATCH /api/projects/:id/agents/:agentId { active: true }.
         Server returns 200. Agent status → "idle". Sidebar updates.
         PM Agent may offer to run the re-activated agent immediately if the
         pipeline has already passed its stage.

Step 6 — On-demand invocation:
         User sends a chat message with targetAgent set:
         POST /api/projects/:id/chat { message: "Re-run cost estimation for US West region", targetAgent: "cost" }
         The cost agent runs outside the normal pipeline sequence and posts results.
```

---

## 5. Security Requirements

| # | Requirement | Detail |
|---|-------------|--------|
| SEC-1 | Authentication | Microsoft Entra ID SSO. Users authenticate with @microsoft.com accounts via MSAL. The frontend acquires a Bearer JWT and sends it in the `Authorization: Bearer <token>` header on every API request. |
| SEC-2 | Token validation | The backend validates the JWT signature, issuer (`https://login.microsoftonline.com/{tenantId}/v2.0`), audience (application client ID), and expiration. Invalid tokens return `401`. |
| SEC-3 | Ownership enforcement | Every project-scoped endpoint extracts the `oid` (object ID) claim from the JWT and compares it to `project.userId`. Mismatches return `403 Forbidden` with body `{ "error": "You do not have access to this project." }`. |
| SEC-4 | Rate limiting | All API endpoints are rate-limited to **60 requests per minute per user** (keyed on `oid`). Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header (seconds). Body: `{ "error": "Rate limit exceeded. Try again in <N> seconds." }`. |
| SEC-5 | Input sanitisation | All user-provided text (`description`, `customerName`, `message`) is sanitised before persistence and before forwarding to AI agents. Sanitisation strips HTML tags, neutralises prompt-injection patterns (e.g., `ignore previous instructions`), and rejects inputs with embedded script blocks. |
| SEC-6 | Audit logging | Every API request is logged with: `userId`, `action` (HTTP method + path), `projectId` (if applicable), `statusCode`, `timestamp`, `ipAddress`. Logs are written to a tamper-evident store. Retention: 12 months. |
| SEC-7 | Data isolation | Projects are scoped to individual users. There are no shared or collaborative projects in MVP. Database queries always include a `userId` filter. |
| SEC-8 | Transport security | All traffic is served over HTTPS (TLS 1.2+). HSTS headers are set. No HTTP fallback. |
| SEC-9 | CORS policy | The API only accepts requests from the application's own origin. `Access-Control-Allow-Origin` is set to the frontend's deployed URL. |
| SEC-10 | Content Security Policy | The frontend sets CSP headers disallowing inline scripts, restricting `connect-src` to the API origin, and allowing `img-src` for rendered diagrams. |

---

## 6. Frontend Behaviour

### 6.1 Landing Page (`/`)

| Element | Detail |
|---------|--------|
| **Layout** | Centred card on a branded background. Logo + application name at top. |
| **Description input** | Multi-line text area, placeholder: _"Describe your customer's scenario or need…"_, max 5 000 chars, character counter shown. |
| **Customer name input** | Single-line text field, placeholder: _"Customer name (optional)"_, max 200 chars. |
| **Create button** | Label: **"Create Project"**. Disabled until description has ≥ 1 character. Shows spinner during API call. |
| **Recent projects** | Below the form: list of up to 5 most recent projects (from `GET /api/projects`). Each shows truncated description (200 chars), customer name, status badge, and relative time (e.g., "2 hours ago"). Clicking navigates to `/project/:id`. |
| **Empty state** | If no recent projects: _"No projects yet. Start by describing a customer scenario above."_ |
| **Error state** | If `POST /api/projects` fails: red banner above the form with the error message and a "Try Again" button that re-enables the form. |
| **Auth redirect** | If the user is not authenticated, redirect to Entra ID login before rendering. On return, restore any draft text from `sessionStorage`. |

### 6.2 Project List (`/projects`)

| Element | Detail |
|---------|--------|
| **Layout** | Full-width table/card list with header: **"Your Projects"**. |
| **Columns/fields** | Customer name (or "—"), description (truncated to 200 chars), status badge (`in_progress` → blue, `completed` → green, `error` → red), last updated (relative time). |
| **Sorting** | Default: most recently updated first. No user-controlled sorting in MVP. |
| **Click action** | Clicking a row/card navigates to `/project/:id`. |
| **Empty state** | _"You haven't created any projects yet."_ with a **"Create New Project"** link to `/`. |
| **Loading state** | Skeleton rows while `GET /api/projects` is in flight. |
| **Error state** | If the API call fails: _"Unable to load projects. Please try again."_ with a retry button. |

### 6.3 Chat Interface (`/project/:id`)

| Element | Detail |
|---------|--------|
| **Layout** | Three-column layout: agent sidebar (left, 240 px), chat thread (centre, fluid), context panel (right, collapsible, future use). |
| **Chat thread** | Scrollable container. Messages are displayed chronologically (oldest at top). Auto-scrolls to bottom on new messages. |
| **User messages** | Right-aligned bubble, neutral background colour, user avatar (from Entra profile), timestamp below. |
| **Agent messages** | Left-aligned card with agent avatar, agent name, coloured accent bar (unique per agent), timestamp. |
| **Typing indicator** | When an agent's status is `"working"`, a typing indicator (animated dots) appears in the chat thread below the last message, labelled with the agent name: _"[Agent Name] is thinking…"_. |
| **Input area** | Fixed at the bottom. Multi-line text input (auto-growing, max 5 rows visible). Placeholder: _"Type your message…"_. Send button (arrow icon) on the right, disabled when input is empty. `Enter` sends; `Shift+Enter` for newline. |
| **Start Agents button** | Appears as an inline action within the PM Agent's summary message at the end of guided questioning. Label: **"Start Agents"**. Sends a synthetic `{ message: "__START_AGENTS__" }` to trigger pipeline. |
| **Proceed button** | Appears within Envisioning Agent messages after selectable items. Label: **"Proceed with Selected Items"**. Disabled if no items are checked. |
| **Message loading** | On initial load, fetches `GET /api/projects/:id/chat?limit=50`. Shows spinner during load. Implements infinite scroll upward: when user scrolls to top, fetches older messages using `before` cursor. |
| **Scroll behaviour** | Auto-scroll to newest message when a new message arrives, **unless** the user has manually scrolled up (≥ 200 px from bottom). In that case, show a "↓ New messages" pill that scrolls to bottom on click. |

### 6.4 Agent Sidebar

| Element | Detail |
|---------|--------|
| **Header** | **"Agents"** label. |
| **Agent row** | Each row: circular avatar (32 × 32 px), agent name, status dot (right-aligned), toggle switch (far right). |
| **Status dots** | Grey filled circle = Idle. Blue filled circle with CSS pulse animation = Working. Red filled circle = Error. |
| **Toggle switch** | Allows activate/deactivate. Calls `PATCH /api/projects/:id/agents/:agentId`. |
| **System Architect** | Toggle is visually disabled (greyed out). On hover/focus: tooltip _"System Architect is required for all downstream agents and cannot be deactivated."_ |
| **PM Agent** | Always active; toggle is hidden (PM is implicit). |
| **Working agent deactivation** | On toggle off while agent is working: confirmation modal appears (see §4.3 Step 3b). |
| **Error state** | Agent row with red dot. Clicking the row expands an inline error summary. A "Retry" link re-invokes the agent. |
| **Ordering** | Agents are listed in pipeline order: PM, Envisioning, System Architect, Azure Specialist, Cost Specialist, Business Value, Presentation. |

### 6.5 Rich Content Rendering

| Content Type | Rendering Detail |
|--------------|-----------------|
| **Plain text** | Rendered with Markdown support (bold, italic, lists, links, code blocks). |
| **Mermaid diagrams** | Rendered inline using Mermaid.js. If rendering fails, show raw Mermaid code in a scrollable code block with a warning: _"Diagram could not be rendered. Showing source code."_ |
| **Tables** | Rendered as HTML `<table>` elements with alternating row colours, sticky header, horizontal scroll on overflow. |
| **Checkboxes / selectable lists** | Rendered as a list of items with checkboxes. State is managed client-side until submission. Associated action button (e.g., "Proceed with Selected Items") is below the list. |
| **Cost breakdowns** | Rendered as a styled table with service name, SKU, region, monthly cost, and a bold total row. Footnote: _"All prices in USD. EA/CSP discounts are not included."_ |
| **Action buttons** | Styled as primary buttons within agent message cards. Clicking triggers a `POST /api/projects/:id/chat` with the appropriate payload. Button shows spinner and disables during the API call. |
| **Error banners** | Red background, white text, icon. Displayed inline within the chat for agent-level errors. Include retry action where applicable. |

---

## 7. Error Responses

All error responses use a consistent JSON shape:

```json
{
  "error": "Human-readable error message."
}
```

### 7.1 Complete Error Catalogue

| HTTP Status | Error Code | Error Message | Trigger |
|-------------|------------|---------------|---------|
| `400` | `VALIDATION_DESCRIPTION_REQUIRED` | `"Field 'description' is required."` | POST /api/projects with missing `description` |
| `400` | `VALIDATION_DESCRIPTION_EMPTY` | `"Project description must not be empty."` | POST /api/projects with blank `description` |
| `400` | `VALIDATION_DESCRIPTION_TOO_LONG` | `"Project description must not exceed 5,000 characters."` | POST /api/projects with `description` > 5 000 chars |
| `400` | `VALIDATION_CUSTOMER_NAME_TOO_LONG` | `"Customer name must not exceed 200 characters."` | POST /api/projects with `customerName` > 200 chars |
| `400` | `VALIDATION_DESCRIPTION_INVALID` | `"Description contains invalid content."` | POST /api/projects with prohibited content |
| `400` | `VALIDATION_MESSAGE_REQUIRED` | `"Field 'message' is required."` | POST /api/projects/:id/chat with missing `message` |
| `400` | `VALIDATION_MESSAGE_EMPTY` | `"Message must not be empty."` | POST /api/projects/:id/chat with blank `message` |
| `400` | `VALIDATION_MESSAGE_TOO_LONG` | `"Message must not exceed 10,000 characters."` | POST /api/projects/:id/chat with `message` > 10 000 chars |
| `400` | `VALIDATION_MESSAGE_INVALID` | `"Message contains invalid content."` | POST /api/projects/:id/chat with prohibited content |
| `400` | `VALIDATION_ACTIVE_REQUIRED` | `"Field 'active' (boolean) is required."` | PATCH agents with missing/non-boolean `active` |
| `400` | `VALIDATION_LIMIT_INVALID` | `"Parameter 'limit' must be an integer between 1 and 100."` | GET chat with invalid `limit` |
| `400` | `VALIDATION_CURSOR_INVALID` | `"Invalid cursor: message not found."` | GET chat with non-existent `before` cursor |
| `401` | `AUTH_REQUIRED` | `"Authentication required."` | Any endpoint without valid Bearer token |
| `401` | `AUTH_TOKEN_EXPIRED` | `"Authentication token has expired. Please sign in again."` | Any endpoint with expired JWT |
| `403` | `AUTH_FORBIDDEN` | `"You do not have access to this project."` | Project-scoped endpoint where user ≠ owner |
| `404` | `PROJECT_NOT_FOUND` | `"Project not found."` | Any project-scoped endpoint with unknown `:id` |
| `404` | `AGENT_NOT_FOUND` | `"Agent '<agentId>' not found."` | PATCH agents with unknown `:agentId` |
| `409` | `AGENT_PROTECTED` | `"System Architect cannot be deactivated. It is required for all downstream agents."` | PATCH architect agent with `active: false` |
| `422` | `AGENT_INACTIVE` | `"Agent '<agentId>' is not active in this project."` | POST chat targeting an inactive agent |
| `422` | `AGENT_WORKING` | `"Agent '<agentId>' is currently working. Set 'confirm: true' to cancel its task and deactivate."` | PATCH deactivating a working agent without confirmation |
| `422` | `UNKNOWN_AGENT` | `"Unknown agent '<targetAgent>'."` | POST chat with unrecognised `targetAgent` |
| `429` | `RATE_LIMITED` | `"Rate limit exceeded. Try again in <N> seconds."` | Any endpoint when user exceeds 60 req/min |
| `500` | `INTERNAL_ERROR` | `"Project creation failed. Please try again."` | POST /api/projects when storage is unavailable |
| `500` | `INTERNAL_ERROR` | `"An unexpected error occurred. Please try again."` | Any unhandled server error |
| `504` | `AGENT_TIMEOUT` | `"Agent response timed out. Please try again."` | POST /api/projects/:id/chat when agent exceeds 120s |

### 7.2 Error Response Headers

| Header | Value | Condition |
|--------|-------|-----------|
| `Retry-After` | Seconds until rate limit resets | On `429` responses |
| `WWW-Authenticate` | `Bearer realm="OneStopAgent"` | On `401` responses |

---

## 8. Edge Cases

| # | Scenario | Expected Behaviour |
|---|----------|--------------------|
| EC-1 | **Empty project list** | `GET /api/projects` returns `200` with `[]`. UI shows empty state message. |
| EC-2 | **Description is only whitespace** | Trimmed to empty string → `400 "Project description must not be empty."` |
| EC-3 | **Description at exact max length (5 000 chars)** | Accepted. No error. |
| EC-4 | **Description at 5 001 chars** | `400 "Project description must not exceed 5,000 characters."` |
| EC-5 | **Message at exact max length (10 000 chars)** | Accepted. No error. |
| EC-6 | **Special characters in description** | Unicode, emoji, CJK characters, and accented Latin characters are allowed and stored as-is. HTML entities are escaped on render. |
| EC-7 | **HTML/script tags in input** | Stripped during sanitisation. If the entire input becomes empty after stripping → `400 "Description contains invalid content."` |
| EC-8 | **Concurrent modification — two tabs deactivate same agent** | First request succeeds (200). Second request sees agent already inactive → 200 (idempotent, returns current state). |
| EC-9 | **Concurrent modification — deactivate while agent just started working** | Race condition: if the agent transitioned to `working` between the UI check and the PATCH, server returns `422` with working-agent warning. UI shows confirmation dialog. |
| EC-10 | **Network disconnection during chat send** | Frontend detects network error. Message is not removed from the input field. Error toast: _"Message could not be sent. Check your connection and try again."_ Retry button available. Message is **not** persisted server-side (no partial state). |
| EC-11 | **Network disconnection during agent response** | If the POST /chat request was received server-side, the agent response is persisted. On reconnection, the frontend fetches the latest chat history and displays the response. No duplicate messages. |
| EC-12 | **Browser refresh during guided questioning** | On reload, `GET /api/projects/:id/chat` restores full history. The PM Agent's question context (`questionIndex`) is available in message metadata. The PM Agent resumes from the last unanswered question on the next user message. |
| EC-13 | **User sends message while agent is working** | The message is queued. Server responds with `200` but the PM Agent processes it after the current agent completes. The user message is immediately visible in the chat thread with a subtle "queued" indicator. |
| EC-14 | **User clicks "Start Agents" multiple times** | Button disables after first click. Server is idempotent: if the pipeline is already started, the duplicate request is a no-op and the current pipeline state is returned. |
| EC-15 | **Project in `error` state — user sends message** | Allowed. The PM Agent receives the message and can offer recovery options (retry, skip, restart). Project status remains `error` until a successful agent run. |
| EC-16 | **Project in `completed` state — user sends message** | Allowed. The user can re-invoke agents on demand (e.g., "re-run cost estimation"). The project status reverts to `in_progress` if any agent is re-activated. |
| EC-17 | **Invalid UUID in URL path** | `GET /api/projects/not-a-uuid` → `404 "Project not found."` Frontend shows 404 page. |
| EC-18 | **JWT `oid` claim missing** | Server treats as invalid token → `401 "Authentication required."` |
| EC-19 | **Rate limit hit during agent response** | The in-flight agent request completes (rate limit applies to new requests, not in-progress ones). Subsequent requests return `429`. |
| EC-20 | **Very long agent response (> 50 KB text)** | Response is accepted and stored. Frontend renders with virtual scrolling within the message card. Content is not truncated. |
| EC-21 | **All optional agents deactivated** | Only PM and System Architect remain active. PM Agent warns: _"Only the System Architect is active. The pipeline will produce an architecture diagram only. Other outputs will be skipped."_ |
| EC-22 | **User types "proceed" mid-sentence** | The PM Agent uses intent detection, not keyword matching. "I want to proceed with the architecture" triggers pipeline advance. "How should we proceed?" does not. |
| EC-23 | **Cursor pagination with deleted messages** | Messages are never deleted in MVP (soft-delete is out of scope). If a `before` cursor references a non-existent message ID → `400 "Invalid cursor: message not found."` |
| EC-24 | **Multiple rapid messages from user** | Each message generates a separate `POST /api/projects/:id/chat` call. Messages are processed in order (server-side queue per project). Responses may arrive out of visual order; the frontend sorts by `timestamp`. |
| EC-25 | **Agent produces empty response** | PM Agent wraps the error: _"[Agent Name] did not produce output. This may be due to insufficient context. Would you like to retry or provide more details?"_ Agent status → `error`. |

---

## Traceability

| User Story / FR | PRD Reference | FRD Sections |
|-----------------|---------------|--------------|
| **US-1** Start a New Project | PRD §3 US-1 | §2.1 (POST /api/projects), §2.2 (GET /api/projects), §2.3 (GET /api/projects/:id), §3.1 (validation), §4.1 (creation flow), §6.1 (landing page) |
| **US-8** Agent Selection and Control | PRD §3 US-8 | §2.6 (GET agents), §2.7 (PATCH agents), §3.3 (validation), §4.3 (selection flow), §6.4 (agent sidebar) |
| **US-9** Guided Questioning | PRD §3 US-9 | §2.4 (POST chat), §2.5 (GET chat), §3.2 (validation), §4.2 (questioning flow), §6.3 (chat interface) |
| **FR-1** Agent Orchestration API | PRD §4 FR-1 | §2 (all API contracts), §3 (all validation rules), §7 (error catalogue) |
| **FR-5** Frontend Pages | PRD §4 FR-5 | §6.1 (landing), §6.2 (project list), §6.3 (chat interface) |
| **FR-6** Chat Interface | PRD §4 FR-6 | §6.3 (chat interface), §6.4 (agent sidebar), §6.5 (rich content) |
| **FR-8** Authentication & Authorization | PRD §4 FR-8 | §5 (security requirements), §7.1 (auth error codes) |
