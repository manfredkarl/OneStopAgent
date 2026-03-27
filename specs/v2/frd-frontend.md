# FRD: Frontend (React SPA)

> **Version:** 2.0  
> **Status:** Current  
> **Replaces:** specs/frd-chat.md (v1)  
> **Component:** `src/frontend/`

---

## 1. Overview

The frontend is a Vite + React + TypeScript single-page application with a chat-based interface and agent sidebar. It communicates with the Python backend via REST API and receives real-time agent output via Server-Sent Events (SSE) streaming.

**Tech stack:**

| Technology | Purpose |
|------------|---------|
| Vite | Build tool + dev server |
| React 18 | UI framework |
| TypeScript | Type safety |
| React Router | Client-side routing |
| `marked` | Markdown → HTML rendering |
| `mermaid` | Architecture diagram rendering |
| Tailwind CSS | Utility-first styling |
| CSS custom properties | Light/dark theme support |

---

## 2. Pages

### 2.1 Landing Page (`/`)

**Component:** `src/frontend/src/pages/Landing.tsx`

**Layout:**

- Hero section with title "OneStopAgent" and tagline
- Description textarea (rows=4, placeholder: "Describe your project requirements...")
- Customer name input field (optional)
- "Create Project" button (disabled when textarea empty, shows "Creating..." while loading)
- Example prompt cards (clickable, auto-submit)
- Recent projects grid (up to 6 projects)

**Example prompts (hardcoded):**

```typescript
const EXAMPLES = [
  "Build a scalable e-commerce platform for a retail chain with 10K concurrent users and AI product recommendations",
  "Design a patient portal for a hospital network with HIPAA compliance and Epic EHR integration",
  "Create an IoT telemetry platform for smart manufacturing with 50K devices",
  "Modernize a financial services trading platform with low-latency requirements",
];
```

**State management:**

```typescript
const [description, setDescription] = useState('');
const [customerName, setCustomerName] = useState('');
const [loading, setLoading] = useState(false);
const [projects, setProjects] = useState<Project[]>([]);
```

**Flow:**

1. User types description (and optional customer name)
2. Clicks "Create Project" or clicks an example prompt card
3. Calls `createProject(description, customerName)` API
4. On success: navigates to `/project/{projectId}?msg={encodeURIComponent(text)}`
5. Chat page reads `?msg=` query param and auto-sends the initial message

**Recent projects:**

- Fetched on mount via `listProjects()` API call
- Displayed in grid layout (1 column mobile, 2 columns desktop)
- Each project shown as `ProjectCard` component with description, status badge, customer name, created date
- Only displayed if `projects.length > 0`

### 2.2 Chat Page (`/project/:id`)

**Component:** `src/frontend/src/pages/Chat.tsx`

**Layout:**

```
┌─────────────────────────────────────────────────┐
│ OneStopAgent Header                             │
├──────────────────┬──────────────────────────────┤
│ AgentSidebar     │  Chat Area                   │
│ (w-60, fixed)    │  ├─ Project Header           │
│                  │  ├─ ChatThread (scrollable)  │
│                  │  └─ ChatInput (fixed bottom) │
└──────────────────┴──────────────────────────────┘
```

**State management:**

```typescript
const [project, setProject] = useState<Project | null>(null);
const [messages, setMessages] = useState<ChatMessage[]>([]);
const [agents, setAgents] = useState<AgentStatus[]>([]);
const [sending, setSending] = useState(false);
const initialSent = useRef(false);
```

**Initial data load (on mount):**

1. `getProject(projectId)` → populates project header
2. `getChatHistory(projectId)` → loads previous messages
3. `getAgents(projectId)` → populates agent sidebar

**Auto-send initial message:**

- Reads URL query param `?msg=`
- If present and not already sent, calls `handleSend(initialMsg)` with 300ms delay
- Uses `initialSent` ref to prevent duplicate sends

**Message sending flow:**

1. Create user message: `{ id: user-${Date.now()}, role: 'user', content, projectId, timestamp }`
2. Add to messages state (optimistic UI)
3. Call `sendMessageStreaming(projectId, message, onMessage)`
4. `onMessage` callback: update or append incoming agent messages
5. On error: create error message with `agentId: 'pm'`
6. Finally: refresh agent statuses via `getAgents()`

---

## 3. Components

### 3.1 Agent Sidebar (`AgentSidebar.tsx`)

**Props:**

```typescript
interface Props {
  projectId: string;
  agents: AgentStatus[];
  onAgentsChange: (agents: AgentStatus[]) => void;
}
```

**Features:**

- Fixed width (`w-60`), scrollable agent list
- Each agent row shows: colored avatar with abbreviation, name, toggle switch, status dot
- Toggle switches for all agents except PM and Architect (required, cannot be toggled)
- Status indicator colors: `idle` (gray), `working` (accent, pulsing), `error` (red)

**Agent registry:**

| Agent ID | Display Name | Abbreviation | Required | Default Active | Color |
|----------|-------------|--------------|----------|---------------|-------|
| `pm` | Project Manager | PM | ✅ | true | `#0F6CBD` |
| `envisioning` | Envisioning | EN | ❌ | false | `#8764B8` |
| `architect` | System Architect | SA | ✅ | true | `#008272` |
| `azure-specialist` | Azure Specialist | AE | ❌ | true | `#005A9E` |
| `cost` | Cost Specialist | CS | ❌ | true | `#D83B01` |
| `business-value` | Business Value | BV | ❌ | true | `#107C10` |
| `presentation` | Presentation | PR | ❌ | true | `#B4009E` |

**Toggle behavior:**

```typescript
const handleToggle = async (agentId: string, currentActive: boolean) => {
  const reg = AGENT_REGISTRY.find(a => a.agentId === agentId);
  if (reg?.required) return; // Cannot toggle required agents
  const updated = await toggleAgent(projectId, agentId, !currentActive);
  onAgentsChange(updated);
};
```

Calls `PATCH /api/projects/{id}/agents/{agentId}` with `{ active: boolean }`.

### 3.2 Chat Thread (`ChatThread.tsx`)

**Props:** `{ messages: ChatMessage[] }`

**Features:**

- Scrollable container with auto-scroll to bottom on new messages
- Empty state: "Send a message to get started"

**User messages:**

- Right-aligned blue pill bubbles
- Max-width 70%, rounded corners (bottom-right flat)

**Agent messages:**

- Left-aligned with colored avatar (8px circle, agent abbreviation)
- Agent name header above message bubble
- Max-width 85%, card-styled with border
- Content rendered via `<MessageContent>` component

**Execution plan rendering:**

- If `msg.metadata?.type === 'execution_plan'` and `msg.metadata?.steps` exists
- Renders `<ExecutionPlan steps={steps} />` component instead of `MessageContent`
- Each step shows: emoji, agent name, reason, status indicator (⏳/🔄/✅/⏭️)

### 3.3 Message Content (`MessageContent.tsx`)

**Props:** `{ content: string }`

**Processing pipeline:**

1. **Mermaid extraction:** Regex matches `` ```mermaid\n...\n``` `` fenced blocks
2. **Unfenced mermaid detection:** Checks for `flowchart|graph TD|TB|BT|RL|LR` patterns with `-->` arrows
3. **Content splitting:** Produces `Array<{ type: 'text' | 'mermaid'; value: string }>`
4. **Rendering:**
   - Text parts → `marked.parse()` → HTML via `dangerouslySetInnerHTML`
   - Mermaid parts → `<MermaidDiagram>` component

**Marked configuration:**

```typescript
marked.setOptions({ breaks: true, gfm: true });
```

### 3.4 Mermaid Diagram (`MermaidDiagram.tsx`)

**Props:** `{ mermaidCode: string }`

**Rendering flow:**

1. Validate code (trimmed, ≥ 10 chars)
2. Dynamic import: `const mermaid = (await import('mermaid')).default`
3. Initialize mermaid: `{ startOnLoad: false, theme: 'default', securityLevel: 'loose', suppressErrorRendering: true, logLevel: 'fatal' }`
4. Parse: `await mermaid.parse(trimmed)`
5. Render: `await mermaid.render(id, trimmed)` → SVG string
6. Clean up error DOM elements

**Display states:**

- Loading: gray placeholder with "Rendering diagram..." + pulse animation
- Success: SVG in white container with border, scrollable overflow
- Error: returns `null` (silently hidden — no crash, no error message)

**Cleanup:** Cancellation flag prevents state updates after unmount. Error elements removed from DOM.

### 3.5 Error Boundary (`ErrorBoundary.tsx`)

**Type:** React class component (required for error boundary pattern)

**Behavior:**

- Wraps entire app routes in `App.tsx`
- `getDerivedStateFromError(error)` → sets `hasError: true`
- `componentDidCatch(error, info)` → logs to console
- Error UI: centered message with "Something went wrong", error text, and "Try Again" button
- "Try Again" resets error state

### 3.6 Chat Input (`ChatInput.tsx`)

**Props:** `{ onSend: (message: string) => void, disabled?: boolean }`

**Features:**

- Auto-resizing textarea (min 1 row, max 160px)
- Enter key to send (without shift), click button to send
- Trims whitespace before sending
- Disabled state during message sending

### 3.7 Project Card (`ProjectCard.tsx`)

**Props:** `{ project: Project }`

**Features:**

- Description text (clamped to 2 lines)
- Status badge: `in_progress` (blue), `completed` (green), `error` (red)
- Customer name and created date
- Clickable — navigates to `/project/{id}`

### 3.8 Execution Plan (`ExecutionPlan.tsx`)

**Props:** `{ steps: PlanStep[] }`

**Features:**

- Card layout with step list
- Each step: emoji/icon, agent name, reason, status indicator
- Status icons: `pending` (⏳), `running` (🔄), `done` (✅), `skipped` (⏭️)
- Running steps highlighted with accent background

---

## 4. SSE Streaming

### 4.1 Implementation

```typescript
export async function sendMessageStreaming(
  projectId: string,
  message: string,
  onMessage: (msg: ChatMessage) => void,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'x-user-id': 'demo-user',
    },
    body: JSON.stringify({ message }),
  });

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const dataLine = line.startsWith('data: ') ? line.slice(6).trim()
        : line.startsWith('data:') ? line.slice(5).trim() : null;
      if (!dataLine || dataLine === '[DONE]') continue;
      try {
        onMessage(normalizeMessage(JSON.parse(dataLine)));
      } catch { /* skip unparseable lines */ }
    }
  }
}
```

### 4.2 Message Normalization

Handles both snake_case and camelCase from backend:

```typescript
function normalizeMessage(msg: any): ChatMessage {
  return {
    id: msg.id,
    projectId: msg.project_id || msg.projectId,
    role: msg.role,
    agentId: msg.agent_id || msg.agentId,
    content: msg.content,
    metadata: msg.metadata,
    timestamp: msg.timestamp,
  };
}
```

---

## 5. API Client (`api.ts`)

**Base URL:** `import.meta.env.VITE_API_URL || 'http://localhost:8000'`

**Common headers:** `{ 'x-user-id': 'demo-user' }`

### 5.1 Endpoints

| Function | Method | Endpoint | Request Body | Response |
|----------|--------|----------|-------------|----------|
| `createProject(desc, name?)` | POST | `/api/projects` | `{ description, customer_name? }` | `{ projectId }` |
| `listProjects()` | GET | `/api/projects` | — | `Project[]` |
| `getProject(id)` | GET | `/api/projects/{id}` | — | `Project` |
| `getChatHistory(id)` | GET | `/api/projects/{id}/chat` | — | `{ messages: ChatMessage[] }` |
| `sendMessage(id, msg)` | POST | `/api/projects/{id}/chat` | `{ message }` | `ChatMessage[]` |
| `sendMessageStreaming(id, msg, cb)` | POST | `/api/projects/{id}/chat` | `{ message }` | SSE stream |
| `getAgents(id)` | GET | `/api/projects/{id}/agents` | — | `{ agents: AgentStatus[] }` |
| `toggleAgent(id, agentId, active)` | PATCH | `/api/projects/{id}/agents/{agentId}` | `{ active }` | `{ agents: AgentStatus[] }` |

---

## 6. TypeScript Types (`types.ts`)

```typescript
export interface Project {
  id: string;
  user_id?: string;
  description: string;
  customer_name?: string;
  status: 'in_progress' | 'completed' | 'error';
  created_at: string;
}

export interface ChatMessage {
  id: string;
  projectId: string;
  role: 'user' | 'agent';
  agentId?: string;
  content: string;
  metadata?: Record<string, any>;
  timestamp: string;
}

export interface AgentStatus {
  agentId: string;
  displayName: string;
  status: 'idle' | 'working' | 'error';
  active: boolean;
}

export interface PlanStep {
  tool: string;
  agentName: string;
  emoji: string;
  reason: string;
  status: 'pending' | 'running' | 'done' | 'skipped';
}
```

---

## 7. Routing

```typescript
// App.tsx
<ErrorBoundary>
  <Routes>
    <Route path="/" element={<Landing />} />
    <Route path="/project/:id" element={<Chat />} />
  </Routes>
</ErrorBoundary>
```

**Navigation flow:**

1. Landing → Create project → `/project/{id}?msg={text}`
2. Chat page → auto-sends initial message from query param
3. Logo click → back to landing (`/`)

---

## 8. Styling

**Theme system:** CSS custom properties for light/dark mode:

```css
--text-primary       /* Main text */
--text-secondary     /* Headings, labels */
--text-muted         /* Disabled, placeholder */
--bg-primary         /* Main background */
--bg-secondary       /* Secondary background */
--bg-card            /* Card backgrounds */
--border             /* Border color */
--accent             /* Primary action color */
--accent-hover       /* Hover state */
--accent-light       /* Light accent for highlights */
--error              /* Error state */
--shadow-card        /* Card shadow */
```

**Responsive:** Tailwind CSS utility classes; grid adjusts from 1 to 2 columns on wider screens.

---

## 9. Acceptance Criteria

- [ ] Landing page renders with description input, customer name input, and example prompts
- [ ] Clicking example prompt creates project and navigates to chat
- [ ] Recent projects load and display as clickable cards
- [ ] Chat page loads project details, chat history, and agent list on mount
- [ ] Initial message from URL query param auto-sends on chat page load
- [ ] SSE streaming displays messages progressively as agents complete
- [ ] Agent sidebar shows all agents with correct toggle behavior
- [ ] PM and Architect toggles are disabled (required agents)
- [ ] Agent toggling calls PATCH endpoint and updates UI optimistically
- [ ] Markdown content renders correctly (headings, tables, lists, code)
- [ ] Mermaid diagrams render as interactive SVG
- [ ] Invalid Mermaid code fails silently (no crash or error message)
- [ ] Error boundary catches rendering errors and shows "Try Again"
- [ ] User messages appear right-aligned, agent messages left-aligned with avatar
- [ ] Execution plan renders with status indicators per step
- [ ] Chat auto-scrolls to bottom on new messages
