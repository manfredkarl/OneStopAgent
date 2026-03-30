# OneStopAgent — Functional Overview

## What It Is

OneStopAgent is an internal Microsoft web application that helps Azure sellers go from a customer idea to a fully scoped Azure solution — complete with architecture diagrams, cost estimates, business value analysis, and a downloadable PowerPoint deck — in a single guided conversation.

## Who It's For

Microsoft field sellers, solution architects, and customer-facing teams who need to quickly scope and present Azure opportunities to customers.

## How It Works

The seller opens the app, describes a customer need in plain language, and a team of AI agents collaborates to produce the solution. There's one central agent — the **Project Manager** — that orchestrates the conversation and calls specialist agents as needed.

### The Conversation Flow

1. **Seller describes the need** — e.g., "Build an e-commerce platform for a retail chain with 10K concurrent users, AI product recommendations, and PCI-DSS payment processing"

2. **Project Manager asks clarifying questions** — 2-3 focused questions about scale, compliance, region, timeline — all in one message, not one at a time

3. **Seller confirms** — says "let's go", "proceed", or answers the questions

4. **Agents execute automatically** — the PM calls specialist agents in sequence, each building on the previous one's output:

   - **🏗️ System Architect** — Designs an Azure architecture with a Mermaid diagram showing all components and their relationships
   - **💰 Cost & Services** — Maps architecture components to Azure services with SKUs, then queries the Azure Retail Prices API for cost estimates. Asks usage questions first (concurrent users, API calls/day, etc.)
   - **📊 Business Value** — Two-phase analysis: asks for business assumptions (employees, hourly rate, etc.), then calculates industry-benchmarked value drivers with web search for real sources
   - **📈 ROI Calculator** — Pure-math ROI with visual dashboard showing cost comparison, value drivers, and 3-year projection
   - **📑 Presentation** — Generates a professional PowerPoint deck using a PptxGenJS template with LLM-polished text content

5. **Seller reviews and iterates** — can ask the PM to modify the architecture, adjust assumptions, or re-run any agent

### Agent Selection

Sellers can toggle agents on or off in the sidebar. If cost estimation isn't needed, turn off the Cost Specialist — the PM skips it. The only required agents are the Project Manager and System Architect.

## Technical Design Decisions

### MAF Workflow Orchestration

The system uses a **deterministic orchestration pattern** powered by the **Microsoft Agent Framework (MAF)**:

```
User → Project Manager (planner) → MAF Workflow → Agents run in sequence → Results stream
```

**Why not ReAct / autonomous agents?**
- Deterministic > autonomous for demos and reliability
- Explicit flow > hidden reasoning for debuggability
- Predictable execution order > LLM-decided order for consistency

**How it works:**

1. **ProjectManager** is a Python class (not a LangChain agent) that:
   - Asks 2-3 clarifying questions via LLM
   - Builds an execution plan (ordered list of agents)
   - Respects agent toggles (removes disabled agents from plan)
   - Architect is always required

2. **Execution Plan** is a simple list:
   ```python
   ["architect", "azure_services", "cost", "business_value", "presentation"]
   ```

3. **MAFOrchestrator** runs agents via MAF workflow:
   ```python
   for step in plan:
       agent = get_agent(step)
       state = agent.run(state)  # each agent reads/writes shared state
   ```

4. **Each agent** is a class with a `run(state) -> state` method:
   ```python
   class ArchitectAgent:
       def run(self, state: AgentState) -> AgentState:
           # call LLM, write to state.architecture
           return state
   ```

5. **Shared state** flows between agents:
   ```python
   state = {
       "user_input": "...",
       "clarifications": "...",
       "architecture": { "mermaidCode": "...", "components": [...] },
       "services": { "selections": [...] },
       "costs": { "estimate": { "totalMonthly": 1200 } },
       "business_value": { "drivers": [...], "executiveSummary": "..." },
       "presentation_path": "output/deck.pptx"
   }
   ```

### LLM Integration

Azure OpenAI is accessed through the **Microsoft Agent Framework (MAF)** — not raw LangChain:

```python
from langchain_openai import AzureChatOpenAI

llm = AzureChatOpenAI(
    azure_endpoint="https://demopresentations.services.ai.azure.com",
    azure_deployment="gpt-4.1",
    azure_ad_token=token,
)

# Inside each agent:
response = llm.invoke([
    {"role": "system", "content": "Generate a Mermaid diagram..."},
    {"role": "user", "content": requirements}
])
```

No LangGraph, no ReAct agents, no chains — just direct LLM calls inside each agent class.

### Streaming via Server-Sent Events (SSE)

Agent responses stream to the frontend in real-time using **Server-Sent Events**:

- The FastAPI `/chat` endpoint supports `Accept: text/event-stream` for SSE streaming
- The **Orchestrator** yields structured progress events as each agent starts and completes:
  ```json
  { "type": "agent_start", "agent": "architect", "content": "🏗️ System Architect is working..." }
  { "type": "agent_result", "agent": "architect", "content": "## Architecture Design\n..." }
  ```
- The frontend uses `fetch()` with `ReadableStream` to process SSE events progressively
- Each agent result appears immediately when that agent finishes — no waiting for the full pipeline
- Agent execution runs in a **thread pool** (`run_in_executor`) to avoid blocking the async event loop

### Azure OpenAI Integration

- Uses **Azure OpenAI GPT-5.4** deployed on Azure AI Foundry
- Authenticated via **Azure CLI credential** (`az account get-access-token`)
- Token passed as `AZURE_OPENAI_TOKEN` environment variable at server startup
- LangChain's `AzureChatOpenAI` handles the API calls
- Each agent makes its own LLM calls for domain-specific tasks (architecture design, component extraction, business analysis)

### Real Azure Pricing

The Cost Specialist agent queries the **Azure Retail Prices REST API** (`https://prices.azure.com/api/retail/prices`):

- No authentication required — the API is publicly accessible
- OData filters match services by name, SKU, and region
- Prices are mapped to monthly costs using service-specific billing models (hourly, monthly, per-GB)
- Falls back to reference prices when the API doesn't return results for a specific SKU
- Pricing source is tracked: `live` (from API), `cached`, or `approximate` (from reference data)

### PowerPoint Generation

The Presentation agent uses a **template-based PptxGenJS approach**:

- A hardcoded, tested PptxGenJS template handles all layout and design (Microsoft color palette, Segoe UI fonts)
- The LLM only generates polished text content (tagline, bullets, narrative) as structured JSON
- The template produces 9 conditional slides: title, executive summary, architecture, services, cost summary with bar chart, business value cards, ROI stats, next steps, and closing
- Falls back to **python-pptx** if Node.js execution fails
- Files saved to `output/` directory, downloadable via API endpoint

## Architecture

### Frontend
- **Vite + React + TypeScript** SPA at `src/frontend/`
- **Markdown rendering** via `marked` for formatted agent responses (headings, tables, lists, bold)
- **Mermaid diagram rendering** — fenced code blocks detected and rendered as interactive SVG via the `mermaid` library
- **SSE streaming** — messages appear progressively as agents produce output
- **Agent sidebar** with toggle switches to activate/deactivate agents
- **CSS variables** for light/dark mode theming

### Backend
- **Python + FastAPI** at `src/python-api/`
- **Controlled orchestration** — ProjectManager is a Python class with MAF workflow execution
- 5 specialist agents as Python classes with `run(state) -> state` methods
- **CORS enabled** for local development
- In-memory project and conversation storage

## The Agents

| Agent | What It Does | How It Works |
|-------|-------------|--------------|
| **Project Manager** | Orchestrates the conversation, decides which agents to call | Python class with LLM-based intent classification (proceed, refine, skip, brainstorm, etc.) |
| **System Architect** | Generates Azure architecture diagrams | Calls LLM to produce Mermaid flowchart + component list with pattern grounding from knowledge base |
| **Cost & Services** | Selects Azure services/SKUs and estimates costs | Two-phase: asks usage questions first, then maps components to SKUs and queries Azure Retail Prices API |
| **Business Value** | Analyzes value drivers with real assumptions | Two-phase: generates assumption questions, user fills inputs, then calculates with web-searched benchmarks |
| **ROI Calculator** | Calculates return on investment | Pure math — no LLM calls. Produces visual dashboard with cost comparison and 3-year projection |
| **Presentation** | Generates executive PowerPoint deck | PptxGenJS template with LLM-generated text content. Falls back to python-pptx |

## Key Features

- **MAF workflow orchestration** — deterministic pipeline with approval gates using Microsoft Agent Framework
- **Two-phase inputs** — Cost and BV agents ask for real assumptions before calculating
- **Streaming responses** — SSE delivers agent output in real-time
- **Real Azure pricing** — cost estimates use the live Azure Retail Prices API
- **ROI visual dashboard** — KPI cards, cost comparison bars, value drivers, 3-year projection
- **Contextual analysis** — business value is specific to the customer's industry and use case
- **Scale-aware** — SKU selection adapts to user-provided usage metrics
- **Agent control** — toggle agents on/off to customize the scoping process
- **Architecture diagrams** — Mermaid flowcharts rendered as interactive SVG
- **Executive deck** — professional PowerPoint generated via PptxGenJS template
- **Guided + fast-run modes** — pause at each step for approval, or run the full pipeline

## Running It

### Prerequisites
- Python 3.11+
- Node.js 18+
- Azure CLI logged in with access to Azure OpenAI

### Start the backend
```bash
# Get Azure OpenAI token
$env:AZURE_OPENAI_TOKEN = az account get-access-token --resource "https://cognitiveservices.azure.com" --query accessToken -o tsv

cd src/python-api
pip install -r requirements.txt
uvicorn main:app --port 8000
```

### Start the frontend
```bash
cd src/frontend
npm install
npm run dev
```

Open `http://localhost:4200` in your browser.

## Project Structure

```
OneStopAgent/
├── src/
│   ├── python-api/              # Python backend (FastAPI + MAF orchestration)
│   │   ├── main.py              # FastAPI routes, SSE streaming, PPTX download
│   │   ├── maf_orchestrator.py  # MAF-based orchestrator (workflow execution)
│   │   ├── workflow.py          # MAF workflow definition, HITL, response handling
│   │   ├── requirements.txt     # fastapi, agent-framework, python-pptx, etc.
│   │   ├── agents/
│   │   │   ├── llm.py                    # Azure OpenAI connection (AzureChatOpenAI)
│   │   │   ├── state.py                  # Shared AgentState dataclass
│   │   │   ├── pm_agent.py               # ProjectManager + IntentInterpreter
│   │   │   ├── architect_agent.py        # System Architect (Mermaid + components)
│   │   │   ├── cost_agent.py             # Two-phase: usage questions → SKU mapping + pricing
│   │   │   ├── business_value_agent.py   # Two-phase: assumptions → value drivers
│   │   │   ├── roi_agent.py              # Pure-math ROI + visual dashboard data
│   │   │   └── presentation_agent.py     # PptxGenJS template + LLM text content
│   │   ├── services/
│   │   │   ├── pricing.py       # Azure Retail Prices API client
│   │   │   ├── presentation.py  # PptxGenJS execution + python-pptx fallback
│   │   │   ├── web_search.py    # DuckDuckGo search for BV benchmarks
│   │   │   └── mcp.py           # Microsoft Learn MCP client
│   │   ├── data/
│   │   │   └── knowledge_base.py # Reference architecture patterns
│   │   └── templates/
│   │       └── slide_master.pptx # Branded PPTX template
│   └── frontend/                # React SPA (Vite + TypeScript)
│       └── src/
│           ├── pages/
│           │   ├── Landing.tsx   # Industry cards + agent toggles
│           │   └── Chat.tsx      # Chat interface with SSE streaming
│           ├── components/
│           │   ├── AgentSidebar.tsx     # Agent toggles + status dots
│           │   ├── ChatThread.tsx       # Messages, approvals, dashboards
│           │   ├── ChatInput.tsx        # Text input with Enter-to-send
│           │   ├── AssumptionsInput.tsx  # Number input fields for BV/cost
│           │   ├── ROIDashboard.tsx      # KPI cards, cost bars, 3-year projection
│           │   ├── MessageContent.tsx    # Markdown (marked) + Mermaid rendering
│           │   ├── MermaidDiagram.tsx    # Async mermaid SVG renderer
│           │   └── ErrorBoundary.tsx     # React error boundary
│           ├── api.ts           # API client with SSE streaming support
│           └── types.ts         # TypeScript interfaces + agent registry
├── specs/                       # v2 specifications and FRDs
├── docs/                        # ADRs and architecture docs
├── FUNCTIONAL_OVERVIEW.md       # This file
└── README.md
```

## Dependencies

### Backend (Python)
| Package | Purpose |
|---------|---------|
| `fastapi` | HTTP API framework |
| `uvicorn` | ASGI server |
| `agent-framework` | Microsoft Agent Framework for orchestration and LLM calls |
| `azure-identity` | Azure credential management |
| `python-pptx` | PowerPoint generation |
| `httpx` | HTTP client for Azure Pricing API |
| `sse-starlette` | Server-Sent Events support |
| `pydantic` | Data validation and schemas |

### Frontend (TypeScript)
| Package | Purpose |
|---------|---------|
| `react` + `react-dom` | UI framework |
| `react-router-dom` | Client-side routing |
| `marked` | Markdown → HTML rendering |
| `mermaid` | Architecture diagram rendering |
| `tailwindcss` | Utility-first CSS |
| `vite` | Build tool + dev server |
