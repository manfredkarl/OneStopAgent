# FRD-06: Frontend & UX

> **Source of truth:** `specs/v2/refactor.md` — §14 (UX Requirements), §14.4 (Streaming), §17 (Graceful Degradation)
> **Related sections:** §2.3 (Execution Plan), §2.4 (After Each Step), §14.2 (Execution Plan UI), §14.3 (Agent Toggles), §15 (Technical Rules)

---

## 1. Overview

The OneStopAgent frontend is a **Vite + React + TypeScript SPA** that provides a chat-based interface for interacting with the Project Manager copilot. The UI has three primary areas: an agent sidebar for toggling and monitoring agents, a chat thread displaying PM and agent messages with rich markdown and diagram rendering, and an execution plan visualization that tracks pipeline progress in real time via SSE.

The frontend must be **demo-stable** (§19) — no crashes, no blank screens, graceful handling of all error states. It communicates with the FastAPI backend (§15) via REST API and Server-Sent Events (SSE).

---

## 2. Tech Stack

From §15 (Technical Rules):

| Technology | Purpose | Version Requirement |
|-----------|---------|-------------------|
| **Vite** | Build tool and dev server | Latest stable |
| **React** | UI component library | 18+ |
| **TypeScript** | Type safety | 5+ |
| **Tailwind CSS** | Utility-first styling | 3+ |
| **marked** | Markdown → HTML rendering | Latest stable |
| **mermaid** | Mermaid diagram → SVG rendering | Latest stable |

**Not used** (per §15):
- No server-side rendering (SPA only)
- No state management libraries beyond React state/context (keep it simple for MVP)
- No component libraries (Tailwind provides all styling)

---

## 3. Pages

### 3.1 Landing Page (`/`)

The entry point where users create new projects or resume existing ones.

**Components:**

1. **Project Creation Form**
   - Text input for project name / customer name
   - Textarea for initial project description
   - "Start" button that creates a project via `POST /api/projects` and navigates to `/project/:id`

2. **Example Prompt Cards**
   - 3–4 pre-built scenario cards that demonstrate the system's capabilities
   - Each card shows a title and 1-sentence description
   - **Clicking a card auto-submits** — creates a project with the card's prompt pre-filled, calls `createProject()`, and navigates directly to the chat page
   - Example cards:
     - "E-Commerce Platform" → "We want to build an AI-powered e-commerce platform for our retail business with 10,000 concurrent users"
     - "Healthcare Telehealth" → "Design a HIPAA-compliant telehealth platform for a hospital network serving 500 daily consultations"
     - "IoT Manufacturing" → "We need a real-time IoT monitoring system for our manufacturing floor with 5,000 sensors"
     - "Financial Analytics" → "Build a fraud detection and risk analytics platform processing 1M transactions daily"

3. **Recent Projects List**
   - Lists existing projects fetched via `GET /api/projects`
   - Shows project name, creation date, current status (brainstorming / solutioning)
   - Click navigates to `/project/:id`
   - Empty state: "No projects yet — create one above or try an example."

### 3.2 Chat Page (`/project/:id`)

The main workspace with a **three-area layout**:

```
┌──────────────┬────────────────────────────────┐
│              │                                │
│   Agent      │        Chat Thread             │
│   Sidebar    │                                │
│              │   [PM message]                 │
│   • Agents   │   [User message]               │
│   • Toggles  │   [Agent card]                 │
│   • Status   │   [Execution plan checklist]   │
│              │                                │
│              ├────────────────────────────────┤
│              │   Chat Input                   │
└──────────────┴────────────────────────────────┘
```

**On mount**, the page:
1. Fetches project data via `GET /api/projects/:id`
2. Fetches chat history via `GET /api/projects/:id/chat`
3. Fetches agent list and states via `GET /api/projects/:id/agents`
4. Opens an SSE connection for real-time updates

---

## 4. Agent Sidebar

### 4.1 Agent List

Displays all agents (from §3.1) with visual status indicators:

| Agent | Display Name | Emoji / Avatar | Color |
|-------|-------------|----------------|-------|
| ProjectManager | Project Manager | 🎯 | Blue |
| BrainstormingAgent | Brainstormer | 💡 | Yellow |
| KnowledgeAgent | Knowledge Retrieval | 📚 | Purple |
| ArchitectAgent | System Architect | 🏗️ | Indigo |
| AzureSpecialistAgent | Azure Specialist | ☁️ | Azure/Cyan |
| CostAgent | Cost Analyst | 💰 | Green |
| BusinessValueAgent | Business Value | 📊 | Orange |
| ROIAgent | ROI Calculator | 📈 | Teal |
| PresentationAgent | Presentation | 📑 | Red |

**Status dots** next to each agent name:

| Status | Visual | Meaning |
|--------|--------|---------|
| `idle` | ⚪ Grey dot | Agent hasn't run yet |
| `running` | 🟡 Yellow dot (pulsing) | Agent is currently executing |
| `completed` | 🟢 Green dot | Agent finished successfully |
| `skipped` | ⚪ Grey dash | Agent was skipped by user |
| `failed` | 🔴 Red dot | Agent encountered an error |
| `disabled` | ⚫ Dark dot | Agent is toggled off |

### 4.2 Toggle Switches

Each agent (except required ones) has a toggle switch in the sidebar:

- **Toggle ON → OFF:** Calls `PATCH /api/projects/:id/agents/:agentId` with `{ "enabled": false }`
- **Toggle OFF → ON:** Calls `PATCH /api/projects/:id/agents/:agentId` with `{ "enabled": true }`
- **Required agents** have their toggle **disabled** (greyed out, non-interactive):
  - ProjectManager — always required (orchestrator)
  - ArchitectAgent — always required (§14.3: "Architect is always required — toggle is disabled")

The toggle state is persisted on the backend. Toggling an agent OFF removes it from the execution plan (§14.3). The frontend updates the agent list immediately on successful API response.

### 4.3 Impact Warnings

From §14.3: When a user toggles an agent OFF, the PM must explain the downstream impact. The frontend displays these as inline warnings below the toggled agent:

| Agent Disabled | Warning Message |
|---------------|-----------------|
| KnowledgeAgent | "Architecture won't be grounded in Microsoft reference patterns." |
| CostAgent | "No pricing data — ROI calculation will be qualitative only." |
| BusinessValueAgent | "No value drivers — the presentation will omit the business case slide." |
| ROIAgent | "No ROI calculation — presentation will show qualitative benefits only." |
| PresentationAgent | "No PowerPoint deck will be generated. Results available in chat only." |
| BrainstormingAgent | "Skipping brainstorming — you'll need to provide a clear use case directly." |

Warnings are styled as amber/yellow alert boxes with a ⚠️ icon. They appear immediately when the toggle is switched OFF and disappear when toggled back ON.

---

## 5. Chat Thread

### 5.1 Message Types

The chat thread renders two types of messages:

**User messages:**
- Right-aligned bubbles
- Light background color (e.g., blue-100)
- Show user text as plain text (no markdown processing)
- Timestamp shown on hover

**Agent / PM messages:**
- Left-aligned cards with more visual structure
- Each card shows:
  - Agent emoji/avatar (from §4.1 table) in a colored circle
  - Agent display name in bold
  - Message content (rendered as markdown — see §5.2)
  - Timestamp

**System messages** (errors, status updates):
- Center-aligned, muted text
- Used for: "🏗️ System Architect is working..." (agent start indicators from §14.4)

### 5.2 Markdown Rendering

All agent/PM messages are rendered as HTML via the `marked` library with a `prose-content` CSS class for styling:

**Supported elements:**

| Markdown Element | Rendering | CSS Notes |
|-----------------|-----------|-----------|
| `# Heading` through `### Heading` | `<h1>` – `<h3>` | Scaled for chat context (smaller than page headings) |
| `**bold**` | `<strong>` | Standard |
| `*italic*` | `<em>` | Standard |
| `- list item` | `<ul><li>` | Indented, with bullet markers |
| `1. list item` | `<ol><li>` | Numbered |
| `| table |` | `<table>` | Styled with borders, alternating row colors, responsive horizontal scroll |
| `` `code` `` | `<code>` | Inline monospace with background |
| ```` ```code block``` ```` | `<pre><code>` | Syntax-highlighted block |
| `> blockquote` | `<blockquote>` | Left border accent, muted background |

**`prose-content` CSS class** applies Tailwind typography-like styling: readable line heights, proper spacing between elements, max-width for readability within the chat column.

### 5.3 Mermaid Diagram Rendering

When agent messages contain Mermaid code blocks (` ```mermaid `), the frontend extracts and renders them:

**Rendering flow:**
1. After `marked` processes the markdown, scan the rendered HTML for `<code class="language-mermaid">` blocks
2. For each block, call `mermaid.render()` to convert the Mermaid code to SVG
3. Replace the `<pre><code>` block with the rendered SVG element
4. SVG is displayed inline in the chat message with pan/zoom capability

**Error handling** (from §17: "Malformed Mermaid from LLM → Show component table instead. Hide diagram silently."):
- If `mermaid.render()` throws an error → **silently return null**
- Do NOT show an error message to the user
- Do NOT let the error pollute the DOM or crash the React component
- The malformed code block is simply hidden (display: none or removed)
- No console.error spam — catch and suppress cleanly

**Implementation pattern:**
```typescript
try {
  const { svg } = await mermaid.render(`mermaid-${id}`, code);
  return svg;
} catch {
  // Silent failure — per §17, invalid mermaid is hidden, not shown
  return null;
}
```

### 5.4 Execution Plan Checklist

From §2.3 and §14.2: The execution plan renders as an **inline checklist** within the chat thread.

**Visual structure:**

```
## Execution Plan
☐  Brainstorm use case
☐  Validate Azure fit
☐  Retrieve Microsoft patterns (via MCP)
🔄 Generate architecture (Mermaid diagram)     ← spinner
☐  Map Azure services (SKUs + regions)
☐  Estimate cost (Azure Retail Prices API)
☐  Analyze business value (value drivers)
☐  Calculate ROI (cost vs. value)
☐  Build presentation (PowerPoint deck)
```

**Step status rendering** (updated via SSE `plan_update` events — see §7):

| Status | Icon | Visual |
|--------|------|--------|
| `pending` | ☐ | Grey checkbox, normal text |
| `running` | 🔄 | Animated spinner, bold text, highlighted background |
| `completed` | ✅ | Green checkmark, text becomes muted |
| `skipped` | ➖ | Grey dash, strikethrough text |
| `failed` | ❌ | Red X, error-colored text |

**Accordion behavior** (from §14.2):
- When an agent completes and its output is shown, the output section is expanded
- When the **next** agent starts, the previous agent's output **collapses automatically**
- User can **click any completed step** to expand and review its output
- Clicking a completed step also reveals a **"Re-run" button** for iteration (§13)
- Clicking an already-expanded step collapses it

**Re-run button:**
- Appears next to completed steps when expanded
- Clicking it sends a message to the PM: "Re-run {step_name}"
- PM handles it as an iteration request (§13)

---

## 6. Chat Input

**Component:** A textarea at the bottom of the chat area.

**Behavior:**

| Feature | Implementation |
|---------|---------------|
| Auto-grow | Textarea height expands as user types multi-line content (min 1 row, max 6 rows) |
| Send | `Enter` key sends the message |
| Newline | `Shift+Enter` inserts a newline (does not send) |
| Disabled state | Input is disabled and shows a loading indicator while a message is being sent / SSE is active |
| Empty guard | Send button is disabled when textarea is empty (whitespace-only counts as empty) |
| Focus | Input auto-focuses on page load and after each message send |

**Send flow:**
1. User presses Enter (or clicks Send button)
2. Message text is captured, textarea is cleared and disabled
3. User message bubble appears immediately in the chat thread (optimistic UI)
4. `POST /api/projects/:id/chat` is called (or SSE stream is initiated)
5. Response messages appear progressively via SSE
6. When SSE stream closes, textarea is re-enabled and focused

---

## 7. Streaming (SSE)

### 7.1 Event Types

From §14.4, the backend sends Server-Sent Events with these types:

| Event Type | Payload | Frontend Action |
|-----------|---------|----------------|
| `agent_start` | `{ "agent": "architect", "display_name": "System Architect", "emoji": "🏗️" }` | Show "{emoji} {display_name} is working..." system message; update agent sidebar status to `running` |
| `agent_result` | `{ "agent": "architect", "content": "markdown string", "metadata": {} }` | Append agent message card to chat thread; update sidebar status to `completed` |
| `plan_update` | `{ "step": "architect", "status": "completed" }` | Update execution plan checklist item (see §5.4 for status rendering) |
| `pm_response` | `{ "content": "markdown string", "awaiting_input": true }` | Append PM message card to chat thread; if `awaiting_input`, re-enable chat input |
| `agent_error` | `{ "agent": "cost", "error": "API timeout", "fallback": "Using approximate pricing" }` | Show error message in chat (inline, not alert); update sidebar status to `failed`; show fallback info |

### 7.2 Frontend Processing

**SSE connection management:**

```typescript
const eventSource = new EventSource(`/api/projects/${projectId}/chat/stream`);
// OR for POST-based SSE:
const response = await fetch(`/api/projects/${projectId}/chat`, {
  method: 'POST',
  body: JSON.stringify({ message }),
  headers: { 'Content-Type': 'application/json' }
});
const reader = response.body!.getReader();
const decoder = new TextDecoder();
```

**ReadableStream parsing:**
- For `fetch`-based SSE (POST requests), use `ReadableStream` with a `TextDecoder`
- Parse the stream line-by-line, looking for `data: ` prefixed lines
- Each `data:` line contains a JSON object with a `type` field matching the event types above
- Handle `data: [DONE]` as stream termination signal

**Message handling per event type:**

1. **`agent_start`**: Create a new system message element (not a full card) showing the agent working indicator. If a previous agent's "working..." message exists, remove it.

2. **`agent_result`**: Remove any "working..." indicator for this agent. Create a full agent message card with markdown rendering. If content arrives in chunks (multiple `agent_result` events for the same agent), append content to the existing card rather than creating a new one.

3. **`plan_update`**: Find the execution plan checklist in the DOM/state and update the specific step's status icon and styling. Trigger accordion collapse/expand behavior.

4. **`pm_response`**: Create a PM message card. If `awaiting_input: true`, re-enable the chat input textarea and auto-focus it.

5. **`agent_error`**: Create an error message in the chat thread (styled as a warning card, not a modal or browser alert). Include the error description and any fallback information.

**Auto-scroll:** The chat thread auto-scrolls to the bottom when new messages arrive, unless the user has manually scrolled up (scroll-lock detection).

---

## 8. API Client

### 8.1 Functions

The frontend API client module provides these functions:

| Function | Method | Endpoint | Purpose |
|----------|--------|----------|---------|
| `createProject(name, description)` | `POST` | `/api/projects` | Create a new project, returns `{ id, name }` |
| `listProjects()` | `GET` | `/api/projects` | List all projects, returns `[{ id, name, status, created_at }]` |
| `getProject(id)` | `GET` | `/api/projects/:id` | Get project details including current state |
| `sendMessageStreaming(id, message)` | `POST` | `/api/projects/:id/chat` | Send message and open SSE stream for response |
| `sendMessage(id, message)` | `POST` | `/api/projects/:id/chat` | Send message, receive complete response (non-streaming fallback) |
| `getChatHistory(id)` | `GET` | `/api/projects/:id/chat` | Get all previous messages for a project |
| `getAgents(id)` | `GET` | `/api/projects/:id/agents` | Get agent list with enabled/disabled status |
| `toggleAgent(id, agentId, enabled)` | `PATCH` | `/api/projects/:id/agents/:agentId` | Enable or disable an agent |

All API functions:
- Return typed responses (TypeScript interfaces)
- Throw on non-2xx responses with parsed error messages
- Include `Content-Type: application/json` headers
- Handle 404 (project not found) → navigate to landing page

### 8.2 Snake_case Normalization

The Python backend (FastAPI) sends responses with `snake_case` field names per Python convention. The frontend normalizes these to `camelCase` for JavaScript/TypeScript convention:

**Normalization rules:**
- `created_at` → `createdAt`
- `customer_name` → `customerName`
- `azure_fit` → `azureFit`
- `monthly_cost` → `monthlyCost`
- `presentation_path` → `presentationPath`
- `agent_id` → `agentId`
- `display_name` → `displayName`

**Implementation:** A utility function `snakeToCamel()` recursively converts all object keys. Applied once at the API client layer so all components receive camelCase data.

```typescript
function snakeToCamel(obj: any): any {
  if (Array.isArray(obj)) return obj.map(snakeToCamel);
  if (obj && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj).map(([key, val]) => [
        key.replace(/_([a-z])/g, (_, c) => c.toUpperCase()),
        snakeToCamel(val)
      ])
    );
  }
  return obj;
}
```

---

## 9. Error Handling

From §17 (Graceful Degradation): "The system should NEVER crash or show a blank screen."

### 9.1 ErrorBoundary Component

A React error boundary wraps each page-level component:

```tsx
class ErrorBoundary extends React.Component<Props, State> {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-fallback">
          <h2>Something went wrong</h2>
          <p>{this.state.error?.message}</p>
          <button onClick={() => this.setState({ hasError: false })}>
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

**Usage:**
- Wraps the chat page and landing page independently
- "Try Again" button resets the error state and re-renders the child tree
- Error details are shown in development mode; generic message in production

### 9.2 Mermaid Crash Prevention

From §17: "Malformed Mermaid from LLM → Show component table instead. Hide diagram silently (no crash)."

**Frontend-specific rules:**
- Mermaid rendering is wrapped in a try/catch — errors produce `null` (no DOM element)
- Invalid Mermaid code does NOT:
  - Show an error message to the user
  - Log noisy console errors (catch and suppress)
  - Leave orphaned SVG elements or error divs in the DOM
  - Crash the React component tree (which would trigger ErrorBoundary)
- The Mermaid library's `suppressErrors` configuration is enabled
- Each Mermaid render uses a unique container ID to prevent DOM pollution across renders

### 9.3 API Error Display

API errors are shown **inline in the chat thread**, not as browser alerts or modal dialogs:

| Error Type | Display |
|-----------|---------|
| Agent failure | Warning card in chat: "⚠️ {Agent Name} encountered an error: {message}. {fallback_info}" |
| API 4xx error | Inline error message: "Could not process your request: {error_detail}" |
| API 5xx error | Inline error message: "Server error — please try again in a moment." |
| Validation error | Inline hint below input: "Please provide a project description." |

**Styling:** Error messages use a red/amber left-border accent with a warning icon, consistent with the agent message card layout but visually distinct.

### 9.4 Network Failure

When the browser loses network connectivity or the backend becomes unreachable:

**Offline indicator:**
- A banner appears at the top of the page: "You're offline — reconnect to continue."
- Banner is styled with a yellow/amber background
- Banner disappears automatically when connectivity is restored (`navigator.onLine` events + periodic health check)

**SSE reconnection:**
- If an SSE connection drops mid-stream, attempt automatic reconnection (3 retries with exponential backoff: 1s, 3s, 9s)
- After retries exhausted, show: "Connection lost. [Retry] button to reconnect."

**Retry prompt:**
- Failed API calls show a "Retry" button inline
- Clicking Retry re-sends the last failed request
- Multiple consecutive failures show: "The server appears to be down. Please check that the backend is running."

---

## 10. Acceptance Criteria

### Landing Page
- [ ] Landing page renders with project creation form
- [ ] Example prompt cards are displayed (3–4 cards)
- [ ] Clicking an example card auto-creates a project and navigates to chat page
- [ ] Recent projects list loads from API
- [ ] Empty state is shown when no projects exist

### Chat Page — Layout & Navigation
- [ ] Chat page loads project data, chat history, and agent list on mount
- [ ] Three-area layout renders correctly (sidebar, chat thread, input)
- [ ] Navigation between landing page and chat page works via router

### Chat Thread — Rendering
- [ ] User messages render right-aligned in bubbles
- [ ] Agent/PM messages render left-aligned with emoji avatar and display name
- [ ] Messages render with full markdown formatting (headings, tables, bold, italic, lists, code blocks)
- [ ] Mermaid diagrams render as inline SVG
- [ ] Invalid Mermaid code is silently hidden — no error shown, no crash
- [ ] Chat auto-scrolls to bottom on new messages (unless user has scrolled up)

### Execution Plan
- [ ] Execution plan checklist renders inline in chat
- [ ] Checklist updates via `plan_update` SSE events
- [ ] Step statuses display correct icons (pending, running, completed, skipped, failed)
- [ ] Completed steps collapse automatically when next agent starts (accordion)
- [ ] Completed steps are clickable to re-open and review output
- [ ] Re-run button appears on expanded completed steps

### Agent Sidebar
- [ ] All agents listed with colored avatars and display names
- [ ] Toggle switches call PATCH API and update local state
- [ ] Required agents (PM, Architect) have disabled toggles
- [ ] Impact warnings appear when agents are toggled OFF
- [ ] Agent status dots update in real time via SSE events

### Chat Input
- [ ] Textarea auto-grows with content (1–6 rows)
- [ ] Enter sends message; Shift+Enter inserts newline
- [ ] Input is disabled while message is being processed
- [ ] Input re-enables and auto-focuses when PM awaits input
- [ ] Empty/whitespace-only messages cannot be sent

### Streaming (SSE)
- [ ] SSE stream connects on message send
- [ ] `agent_start` events show "working..." indicators
- [ ] `agent_result` events render agent message cards with markdown
- [ ] `plan_update` events update checklist in real time
- [ ] `pm_response` events render PM messages and re-enable input when `awaiting_input: true`
- [ ] `agent_error` events show inline error cards (not browser alerts)
- [ ] Stream termination (`[DONE]`) properly cleans up connection

### Error Handling
- [ ] ErrorBoundary catches component crashes with "Try Again" recovery button
- [ ] Mermaid errors never crash the page or pollute the DOM
- [ ] API errors display inline in chat thread
- [ ] Offline indicator appears when network is lost
- [ ] SSE reconnection attempts (3 retries with backoff)
- [ ] Failed API calls show inline Retry button

### Cross-Browser
- [ ] Works on latest Chrome, Edge, and Firefox
