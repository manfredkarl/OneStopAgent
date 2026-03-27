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
   - **☁️ Azure Specialist** — Maps each architecture component to specific Azure services with SKU recommendations scaled to the user count
   - **💰 Cost Specialist** — Queries the Azure Retail Prices API to estimate monthly and annual costs with a detailed breakdown table
   - **📊 Business Value** — Analyzes ROI and business impact with quantified value drivers specific to the customer's industry and use case
   - **📑 Presentation** — Generates a downloadable PowerPoint deck compiling all the outputs

5. **Seller reviews and iterates** — can ask the PM to modify the architecture, adjust assumptions, or re-run any agent

### Agent Selection

Sellers can toggle agents on or off in the sidebar. If cost estimation isn't needed, turn off the Cost Specialist — the PM skips it. The only required agents are the Project Manager and System Architect.

## Technical Design Decisions

### Controlled Multi-Agent Orchestration

The system uses a **deterministic orchestration pattern** — not autonomous agent reasoning:

```
User → Project Manager (planner) → Execution Plan → Agents run in sequence → Results stream
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

3. **Orchestrator** runs agents in sequence:
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

### LangChain Used ONLY for LLM Calls

LangChain is used for **Azure OpenAI integration only** — not for agent orchestration:

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

- Uses **Azure OpenAI GPT-4.1** deployed on Azure AI Foundry
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

The Presentation agent uses **python-pptx** to generate real `.pptx` files:

- 8-slide deck: Title, Requirements, Architecture, Components, Services, Costs, Business Value, Next Steps
- Architecture components and cost breakdowns rendered as formatted tables
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
- **LangChain / LangGraph** ReAct agent as the PM orchestrator
- 6 specialist agents implemented as LangChain `@tool` functions
- **CORS enabled** for local development
- In-memory project and conversation storage

## The Agents

| Agent | What It Does | How It Works |
|-------|-------------|--------------|
| **Project Manager** | Orchestrates the conversation, decides which agents to call | LangGraph ReAct agent with 6 tools — uses LLM reasoning to decide when and what to call |
| **System Architect** | Generates Azure architecture diagrams | Calls GPT-4.1 to produce Mermaid flowchart + component list based on requirements |
| **Azure Specialist** | Selects specific Azure services and SKUs | Maps architecture components to services with scale-appropriate SKUs (B1 for small, P2v3 for large) |
| **Cost Specialist** | Estimates Azure costs | Queries `https://prices.azure.com/api/retail/prices` for real pricing, falls back to reference prices |
| **Business Value** | Analyzes ROI and business impact | Calls GPT-4.1 with full solution context to generate industry-specific value drivers and executive summary |
| **Presentation** | Generates PowerPoint deck | Uses python-pptx to create an 8-slide deck with architecture, services, costs, and value analysis |
| **Envisioning** | Suggests scenarios for vague requirements | Searches a knowledge base of reference architectures and past scenarios |

## Key Features

- **Natural language input** — describe what you need, the PM figures out the rest
- **LangChain agent orchestration** — ReAct pattern with dynamic tool selection
- **Streaming responses** — SSE delivers agent output in real-time, token by token
- **Real Azure pricing** — cost estimates use the live Azure Retail Prices API
- **Contextual analysis** — business value is specific to the customer's industry and use case
- **Scale-aware** — SKU selection and cost calculation adapt to the specified user count
- **Agent control** — toggle agents on/off to customize the scoping process
- **Markdown output** — formatted responses with headings, tables, bullet lists
- **Architecture diagrams** — Mermaid flowcharts rendered as interactive SVG
- **Downloadable deck** — PowerPoint file ready to present to the customer
- **Conversation memory** — PM remembers context across the entire session

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
│   ├── python-api/              # Python backend (FastAPI + controlled orchestration)
│   │   ├── main.py              # FastAPI routes, SSE streaming, message handling
│   │   ├── orchestrator.py      # Execution engine — runs agents in sequence
│   │   ├── requirements.txt     # fastapi, langchain-openai, python-pptx, etc.
│   │   ├── agents/
│   │   │   ├── llm.py                    # Azure OpenAI connection (AzureChatOpenAI)
│   │   │   ├── state.py                  # Shared AgentState object
│   │   │   ├── pm_agent.py               # ProjectManager class (planner, NOT ReAct)
│   │   │   ├── architect_agent.py        # System Architect (Mermaid + components via LLM)
│   │   │   ├── azure_specialist_agent.py # Azure service + SKU selection
│   │   │   ├── cost_agent.py             # Cost estimation via Azure Pricing API
│   │   │   ├── business_value_agent.py   # ROI analysis via LLM
│   │   │   ├── presentation_agent.py     # PowerPoint generation (python-pptx)
│   │   │   └── envisioning_agent.py      # Reference scenario matching
│   │   ├── services/
│   │   │   ├── pricing.py       # Azure Retail Prices API client + reference prices
│   │   │   ├── presentation.py  # python-pptx deck builder (8 slides)
│   │   │   └── project_store.py # In-memory project + chat storage
│   │   └── data/
│   │       └── knowledge_base.py # 8 reference scenarios for envisioning
│   └── frontend/                # React SPA (Vite + TypeScript)
│       └── src/
│           ├── pages/
│           │   ├── Landing.tsx   # Project creation + example prompt cards
│           │   └── Chat.tsx      # Chat interface with SSE streaming
│           ├── components/
│           │   ├── AgentSidebar.tsx    # Agent list with toggle switches
│           │   ├── ChatThread.tsx      # Message bubbles with avatars
│           │   ├── ChatInput.tsx       # Message input with Enter-to-send
│           │   ├── MessageContent.tsx  # Markdown (marked) + Mermaid rendering
│           │   ├── MermaidDiagram.tsx  # Async mermaid SVG renderer
│           │   └── ErrorBoundary.tsx   # React error boundary
│           ├── api.ts           # API client with SSE streaming support
│           └── types.ts         # TypeScript interfaces
├── specs/                       # PRD, 7 FRDs, 186 Gherkin scenarios, OpenAPI spec
├── docs/                        # ADRs, prototypes, review documents
├── FUNCTIONAL_OVERVIEW.md       # This file
└── README.md
```

## Dependencies

### Backend (Python)
| Package | Purpose |
|---------|---------|
| `fastapi` | HTTP API framework |
| `uvicorn` | ASGI server |
| `langchain-openai` | Azure OpenAI LLM calls (AzureChatOpenAI) |
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
