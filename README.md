# OneStopAgent

**From customer idea to Azure solution proposal — architecture, costs, business value, and PowerPoint — in one guided conversation.**

OneStopAgent is an internal Microsoft web application for Azure sellers. Describe a customer need in plain language, and a team of AI agents collaborates to produce a fully scoped Azure solution with architecture diagrams, real cost estimates, ROI analysis, and a downloadable executive deck.

## Who It's For

Microsoft field sellers, solution architects, and customer-facing teams who need to quickly scope and present Azure opportunities.

## How It Works

```
Seller describes need → PM asks clarifying questions → Agents execute in sequence → Solution delivered
```

1. **Describe the opportunity** — e.g. "Predictive maintenance for a manufacturing company with 500 production lines"
2. **Answer 2-3 clarifying questions** — the Project Manager asks about scale, region, compliance, and timeline in a single message
3. **Agents build the solution** — each one reads the previous agent's output and writes to shared state:
   - 📊 **Business Value** — Two-phase: generates assumption questions, user fills inputs, then calculates industry-benchmarked value drivers with web-searched sources
   - 🏗️ **System Architect** — Retrieves Microsoft reference architectures (via MCP + local pattern knowledge base), then generates a layered Mermaid diagram with component breakdown
   - 💰 **Cost & Services** — Two-phase: asks usage questions (concurrent users, API calls/day, etc.), then maps components to Azure SKUs and queries the Azure Retail Prices API for cost estimates
   - 📈 **ROI Calculator** — Pure-math ROI from cost and business value data. No LLM calls. Produces a visual dashboard with KPI cards, cost comparison bars, and 3-year projection with adoption ramps
   - 📑 **Presentation** — LLM generates a complete PptxGenJS script per run, guided by the PPTX skill reference. Executes via Node.js; auto-fixes on first failure; raises on second
4. **Review and iterate** — modify architecture, adjust assumptions, `@mention` a specific agent, or re-run any step
5. **Download the deck** — ready to present to the customer

### Agent Selection

Sellers can toggle agents on or off in the sidebar. If cost estimation isn't needed, turn off the Cost Specialist and the PM skips it. The only required agents are the Project Manager and System Architect.

### Interaction Patterns

- **@mentions** — `@architect make it more resilient` routes directly to a specific agent
- **Assumption corrections** — "actually 500 users" is detected and triggers downstream re-runs (cost → ROI → presentation)
- **Conversational mode** — `chat with architect` enters a multi-turn dialog with a single agent; `done` exits
- **Iteration keywords** — "make it cheaper", "high availability", etc. trigger targeted agent re-runs with before/after snapshots
- **Guided vs fast-run** — guided mode pauses for approval after each agent; fast-run only pauses at key gates (BV, architect, presentation)

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Azure CLI (`az login`) with access to Azure OpenAI

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | No | Model deployment name (default: `gpt-5.4`) |
| `AZURE_OPENAI_TOKEN` | No | Bootstrap token; auto-refreshes via `azure-identity` after expiry |
| `COSMOS_ENDPOINT` | No | Cosmos DB endpoint; omit for in-memory storage |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | No | Enables OTLP telemetry export to Application Insights |
| `CORS_ORIGINS` | No | Comma-separated allowed origins (default: localhost dev ports) |
| `MCP_ENDPOINT` | No | Microsoft Learn MCP endpoint (default: `https://learn.microsoft.com/api/mcp`) |

### Backend

```bash
cd src/python-api
pip install -r requirements.txt
npm install   # for PptxGenJS slide generation
uvicorn main:app --port 8000
```

### Frontend

```bash
cd src/frontend
npm install
npm run dev
```

Open **http://localhost:4200** in your browser.

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | React 19 + TypeScript + Vite + Tailwind CSS 4 |
| Backend | Python + FastAPI + SSE streaming |
| Orchestration | Microsoft Agent Framework (MAF) `agent-framework 1.0.0rc5` |
| LLM | Azure OpenAI via MAF's `AzureOpenAIChatClient` |
| Auth | `AutoRefreshCredential` — bootstraps from env var, auto-refreshes via `azure-identity` |
| Storage | Azure Cosmos DB (when `COSMOS_ENDPOINT` is set) or in-memory |
| Pricing | Azure Retail Prices REST API (public, no auth) |
| Slides | PptxGenJS via Node.js subprocess |
| Web Search | DuckDuckGo HTML scraping for BV industry benchmarks |
| Reference Patterns | Microsoft Learn MCP client + local knowledge base |
| Telemetry | OpenTelemetry with OTLP export to Application Insights |
| Diagrams | Mermaid (rendered client-side as SVG) |

## Technical Design

### MAF Workflow Orchestration

The system uses a **deterministic orchestration pattern** powered by the Microsoft Agent Framework:

```
User → Project Manager (planner) → MAF Workflow → Agents run in sequence → Results stream via SSE
```

**Why deterministic over autonomous?**
- Explicit flow for debuggability — no hidden LLM-decided routing
- Predictable agent execution order for consistent results
- Approval gates at every step (guided mode) or at key gates (fast-run mode)

**How it works:**

1. **ProjectManager** is a Python class that classifies user intent (proceed, refine, skip, fast_run, brainstorm, iteration, question, input) and builds an execution plan.

2. **Execution plan** is a simple ordered list of agent names:
   ```python
   ["business_value", "architect", "cost", "roi", "presentation"]
   ```
   Disabled agents are removed. Architect is always required.

3. **MAF Workflow** (`workflow.py`) defines an `Executor` subclass per agent. Each executor wraps the agent class, runs it via `run_in_executor` to avoid blocking the async event loop, and uses MAF's HITL pattern (`ctx.request_info` / `@response_handler`) for approval gates and two-phase assumption input.

4. **Each agent** is a class with a `run(state) -> state` method:
   ```python
   class ArchitectAgent:
       def run(self, state: AgentState) -> AgentState:
           # retrieve patterns, call LLM, write to state.architecture
           return state
   ```

5. **AgentState** is a typed dataclass that flows through the pipeline:
   ```python
   @dataclass
   class AgentState:
       user_input: str = ""
       customer_name: str = ""
       company_profile: dict | None = None
       shared_assumptions: dict = field(default_factory=dict)
       architecture: dict = field(default_factory=dict)
       services: dict = field(default_factory=dict)
       costs: dict = field(default_factory=dict)
       business_value: dict = field(default_factory=dict)
       roi: dict = field(default_factory=dict)
       presentation_path: str = ""
       # ... plus plan tracking, iteration history, conversation mode
   ```
   A `SharedAssumptions` frozen dataclass provides typed, cached access to assumption values with fuzzy key matching.

### LLM Integration

Azure OpenAI is accessed through **MAF's `AzureOpenAIChatClient`** — no LangChain:

```python
from agent_framework import Message as MAFMessage
from agent_framework.azure import AzureOpenAIChatClient

client = AzureOpenAIChatClient(
    endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    deployment_name="gpt-5.4",
    credential=AutoRefreshCredential(),
)
```

A custom `LLMClient` wrapper in `agents/llm.py` exposes `invoke` / `ainvoke` / `astream` methods that all agents use. It handles thread-safe sync calls from `run_in_executor` by scheduling on the main event loop, and creates fresh client instances per thread when no main loop is available.

### Streaming via Server-Sent Events (SSE)

Agent responses stream to the frontend in real-time:

- The FastAPI `/chat` endpoint supports `Accept: text/event-stream` for SSE streaming
- The orchestrator yields structured progress events as each agent starts and completes:
  ```json
  { "type": "agent_start", "agent": "architect", "content": "🏗️ System Architect is working..." }
  { "type": "agent_result", "agent": "architect", "content": "## Architecture Design\n..." }
  ```
- The frontend uses `fetch()` with `ReadableStream` to process SSE events progressively
- Each agent result appears immediately when that agent finishes — no waiting for the full pipeline
- Agent execution runs in a **thread pool** (`run_in_executor`) to avoid blocking the async event loop

### Azure Pricing

The Cost agent queries the **Azure Retail Prices REST API** (`https://prices.azure.com/api/retail/prices`):

- No authentication required — the API is publicly accessible
- OData filters match services by name, SKU, and region
- A `SERVICE_NAME_MAP` resolves naming differences between LLM output and the API (e.g. "Azure AI Search" → "Azure Cognitive Search")
- Prices are mapped to monthly costs using service-specific billing models (hourly, monthly, per-GB)
- Tiered consumption defaults by user count (small/medium/large) when exact usage is unknown
- Reservation pricing lookups for 1-year/3-year savings
- Connection pooling via a module-level `httpx.Client`

### Company Intelligence

When a customer name is provided, the system auto-enriches with a company profile:

- **Web search + LLM extraction** — searches for the company, then extracts structured data (employee count, revenue, industry, region)
- **IT spend estimation** — uses Gartner-benchmarked industry ratios to estimate the customer's IT budget
- **Labor rate lookup** — region × industry matrix for fully loaded hourly rates
- **Fallback profiles** — small / mid-market / enterprise size tiers with pre-set defaults for unknown companies
- Enrichment data feeds into BV assumption defaults and ROI calculations

### PowerPoint Generation

The Presentation agent uses **PptxGenJS via Node.js subprocess**:

- The LLM generates a complete PptxGenJS script each run, guided by the installed PPTX skill reference (`~/.agents/skills/pptx/pptxgenjs.md`)
- Structured slide data (architecture, costs, BV drivers, ROI stats) is extracted from pipeline state and passed as LLM context
- The script is written to a temp file and executed with `node`; `NODE_PATH` points to the backend's `node_modules`
- On first execution failure, the LLM auto-fixes the specific error and retries once
- On second failure, the error is raised — no silent fallback
- Files are saved to `output/` and downloadable via the `/api/projects/{id}/export/pptx` endpoint with directory traversal protection

### Storage

- **Cosmos DB** (`services/cosmos_store.py`) — used when `COSMOS_ENDPOINT` is set. Three containers: `projects`, `chat_messages`, `agent_state`. Authenticated via `DefaultAzureCredential` (managed identity). State checkpoints saved before each agent run.
- **In-memory** (`services/project_store.py`) — automatic fallback when Cosmos is not configured. Suitable for local development.

### Telemetry

OpenTelemetry tracing is configured at startup (`telemetry.py`):

- `ConsoleSpanExporter` always active for local dev visibility
- `OTLPSpanExporter` enabled when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set
- Custom spans in pricing and presentation services
- The MAF agent-framework also instruments its own calls

## The Agents

| Agent | What It Does | How It Works |
|-------|-------------|--------------|
| **Project Manager** | Orchestrates the conversation, classifies intent, builds execution plans | Python class with LLM-based intent classification (proceed, refine, skip, fast_run, brainstorm, iteration, question, input). Handles @mentions, assumption corrections, and conversational mode routing |
| **System Architect** | Generates use-case-specific layered Azure architectures | Multi-query MCP search for Microsoft reference architectures + local pattern knowledge base. LLM produces Mermaid flowchart + component list grounded in retrieved patterns |
| **Cost & Services** | Selects Azure services/SKUs and estimates costs | Two-phase: generates usage questions with defaults, user provides real numbers, then LLM maps components to SKUs. Queries Azure Retail Prices API to validate SKUs and estimate monthly costs. Tiered consumption defaults by user count |
| **Business Value** | Analyzes value drivers with real assumptions | Two-phase: generates 3-5 assumption questions with industry-specific defaults, uses web-searched benchmarks (DuckDuckGo → authoritative domains), calculates annual impact range (low/high) per value driver |
| **ROI Calculator** | Calculates return on investment | Pure math — no LLM calls. Separates cost, value, and investment into reconcilable layers. Adoption ramp curves (simple/medium/complex), payback months, 3-year projection. Caps display ROI at 1000% |
| **Presentation** | Generates executive PowerPoint deck | LLM generates complete PptxGenJS script guided by PPTX skill. Conditional slides: title, executive summary, architecture, services, cost summary with bar chart, BV cards, ROI stats, next steps, closing |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/info` | Version and framework info |
| `GET` | `/api/workflow` | Interactive MAF workflow visualization (HTML + Mermaid) |
| `GET` | `/api/company/search?q=` | Search for a company profile by name |
| `GET` | `/api/company/fallback/{size}` | Fallback company profile (small/mid-market/enterprise) |
| `POST` | `/api/projects` | Create a new project |
| `GET` | `/api/projects` | List user's projects |
| `GET` | `/api/projects/{id}` | Get project details |
| `POST` | `/api/projects/{id}/chat` | Send a message (SSE streaming or JSON response) |
| `GET` | `/api/projects/{id}/chat` | Get chat history |
| `GET` | `/api/projects/{id}/agents` | Get agent statuses |
| `PATCH` | `/api/projects/{id}/agents/{agentId}` | Toggle agent active/inactive |
| `GET` | `/api/projects/{id}/iterations` | Get iteration history (before/after snapshots) |
| `GET` | `/api/projects/{id}/export/pptx` | Download generated PowerPoint deck |

All endpoints require an `x-user-id` header (alphanumeric, 1-64 chars).

## Project Structure

```
OneStopAgent/
├── src/
│   ├── python-api/                        # Python backend (FastAPI + MAF)
│   │   ├── main.py                        # Routes, SSE streaming, PPTX download
│   │   ├── maf_orchestrator.py            # Phase-based orchestrator (MAF workflow runner)
│   │   ├── workflow.py                    # MAF Workflow definition, HITL, executors
│   │   ├── telemetry.py                   # OpenTelemetry setup (console + OTLP)
│   │   ├── utils.py                       # JSON parsing, markdown fence stripping
│   │   ├── agents/
│   │   │   ├── llm.py                     # LLMClient wrapping MAF AzureOpenAIChatClient
│   │   │   ├── state.py                   # AgentState dataclass + SharedAssumptions
│   │   │   ├── pm_agent.py                # ProjectManager + IntentInterpreter
│   │   │   ├── architect_agent.py         # MCP + local patterns → Mermaid + components
│   │   │   ├── cost_agent.py              # Two-phase: usage questions → SKU mapping + pricing
│   │   │   ├── business_value_agent.py    # Two-phase: assumptions → value drivers
│   │   │   ├── roi_agent.py               # Pure-math ROI + visual dashboard data
│   │   │   ├── presentation_agent.py      # LLM-generated PptxGenJS script + auto-fix
│   │   │   └── assumption_catalog.py      # Shared assumption dedup across agents
│   │   ├── services/
│   │   │   ├── pricing.py                 # Azure Retail Prices API client (httpx + pooling)
│   │   │   ├── presentation.py            # Node.js subprocess execution of PptxGenJS
│   │   │   ├── web_search.py              # DuckDuckGo HTML scraping for BV benchmarks
│   │   │   ├── company_intelligence.py    # Company profile enrichment (web search + LLM)
│   │   │   ├── cosmos_store.py            # Cosmos DB storage (projects, messages, state)
│   │   │   ├── project_store.py           # In-memory fallback storage
│   │   │   ├── token_provider.py          # AutoRefreshCredential (Azure AD token management)
│   │   │   └── mcp.py                     # Microsoft Learn MCP client
│   │   ├── models/
│   │   │   └── schemas.py                 # Pydantic models (Project, ChatMessage, requests)
│   │   ├── data/
│   │   │   └── knowledge_base.py          # Local reference architecture patterns
│   │   └── templates/
│   │       └── slide_master.pptx          # Branded PPTX template
│   └── frontend/                          # React SPA (Vite + TypeScript)
│       └── src/
│           ├── api.ts                     # API client with SSE streaming support
│           ├── types.ts                   # TypeScript interfaces + agent registry
│           ├── pages/
│           │   ├── Landing.tsx            # Industry cards, company search, agent toggles
│           │   ├── Chat.tsx               # Chat interface with SSE streaming
│           │   └── Architecture.tsx       # Architecture visualization page
│           └── components/
│               ├── AgentSidebar.tsx        # Agent toggles + status dots
│               ├── AgentMentionDropdown.tsx # @mention autocomplete
│               ├── ChatThread.tsx          # Messages, approvals, dashboards
│               ├── ChatInput.tsx           # Text input with @mention support
│               ├── AssumptionsInput.tsx     # Number input fields for BV/cost
│               ├── CompanyCard.tsx          # Company profile display
│               ├── CompanyDetailModal.tsx   # Expanded company info
│               ├── ExecutionPlan.tsx        # Visual execution plan display
│               ├── ROIDashboard.tsx         # KPI cards, cost bars, 3-year projection
│               ├── MessageContent.tsx       # Markdown (marked) + Mermaid rendering
│               ├── MermaidDiagram.tsx       # Async mermaid SVG renderer
│               ├── ActionButtons.tsx        # Approve/skip/iterate action buttons
│               └── ErrorBoundary.tsx        # React error boundary
├── infra/                                 # Azure infrastructure (Bicep)
│   ├── main.bicep                         # Main deployment template
│   ├── core/database/cosmos.bicep         # Cosmos DB provisioning
│   └── core/monitor/                      # App Insights + Log Analytics
├── specs/                                 # Specifications and FRDs
├── docs/                                  # Architecture docs, audits, reviews
└── README.md                              # This file
```

## Dependencies

### Backend (Python)

| Package | Purpose |
|---------|---------|
| `fastapi` | HTTP API framework |
| `uvicorn` | ASGI server |
| `agent-framework` 1.0.0rc5 | Microsoft Agent Framework — workflow orchestration, LLM client, HITL |
| `azure-identity` | Azure credential management (DefaultAzureCredential, AzureCliCredential) |
| `azure-cosmos` | Cosmos DB async client |
| `httpx` | HTTP client for Azure Pricing API and web search |
| `sse-starlette` | Server-Sent Events support |
| `pydantic` | Data validation and request/response schemas |
| `opentelemetry-api` + `opentelemetry-sdk` | Distributed tracing |
| `opentelemetry-exporter-otlp-proto-http` | OTLP export to Application Insights |

### Backend (Node.js — slide generation only)

| Package | Purpose |
|---------|---------|
| `pptxgenjs` | PowerPoint file generation |

### Frontend (TypeScript)

| Package | Purpose |
|---------|---------|
| `react` 19 + `react-dom` | UI framework |
| `react-router-dom` 7 | Client-side routing |
| `marked` | Markdown → HTML rendering |
| `mermaid` 11 | Architecture diagram rendering (SVG) |
| `tailwindcss` 4 | Utility-first CSS |
| `vite` | Build tool + dev server |

## Features

- **Natural language input** — describe the opportunity, the PM handles the rest
- **Company intelligence** — auto-enriches customer profiles via web search with IT spend and labor rate estimation
- **Agent toggles** — turn agents on/off to customize the scoping flow
- **@mention routing** — direct messages to specific agents with `@architect`, `@cost`, etc.
- **Assumption corrections** — natural language corrections ("actually 500 users") trigger cascading re-runs
- **Conversational mode** — multi-turn dialog with a single agent via `chat with architect`
- **Two-phase inputs** — Cost and BV agents ask for real numbers before calculating
- **Real Azure pricing** — live queries against the Azure Retail Prices API with SKU validation
- **Reference architecture grounding** — Architect retrieves Microsoft Learn patterns via MCP + local knowledge base
- **ROI dashboard** — KPI cards, cost comparison bars, value drivers, 3-year projection with adoption ramps
- **Iteration tracking** — before/after snapshots when assumptions or architecture change
- **Architecture diagrams** — Mermaid flowcharts rendered as interactive SVG
- **Executive deck** — PowerPoint generated via LLM-authored PptxGenJS scripts with auto-fix on failure
- **SSE streaming** — agent output streams to the UI in real-time
- **Guided + fast-run modes** — pause at each step for approval, or run the full pipeline with key gates only
- **Persistent storage** — Cosmos DB for projects, chat history, and state checkpoints (falls back to in-memory)
- **Telemetry** — OpenTelemetry tracing with OTLP export to Application Insights

> **Note:** Three additional agents (Envisioning, Solution Engineer, Platform Engineer) are registered in the UI but not yet implemented.

## License

[ISC](LICENSE)
