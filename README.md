# OneStopAgent

**From customer idea to Azure solution proposal — architecture, costs, business value, and PowerPoint — in one guided conversation.**

OneStopAgent is an internal Microsoft web application for Azure sellers. Describe a customer need in plain language, and a team of AI agents collaborates to produce a fully scoped Azure solution with architecture diagrams, real cost estimates, ROI analysis, and a downloadable executive deck.

## How It Works

```
Seller describes need → PM asks clarifying questions → Agents execute in sequence → Solution delivered
```

1. **Describe the opportunity** — e.g. "Predictive maintenance for a manufacturing company with 500 production lines"
2. **Answer 2-3 clarifying questions** — scale, region, compliance, timeline
3. **Agents build the solution** — each one reads the previous agent's output:
   - 📊 **Business Value** — Industry-benchmarked value drivers with user-provided assumptions
   - 🏗️ **Architect** — Mermaid diagram + component breakdown using Azure patterns
   - 💰 **Cost & Services** — Azure SKU mapping + real pricing from the Azure Retail Prices API
   - 📈 **ROI Calculator** — Pure-math ROI with visual dashboard (cost comparison, 3-year projection)
   - 📑 **Presentation** — Professional PowerPoint deck via PptxGenJS template
4. **Review and iterate** — modify architecture, adjust assumptions, re-run any agent
5. **Download the deck** — ready to present to the customer

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Azure CLI (`az login`) with access to Azure OpenAI

### Backend
```bash
# Get Azure OpenAI token
export AZURE_OPENAI_TOKEN=$(az account get-access-token --resource "https://cognitiveservices.azure.com" --query accessToken -o tsv)

cd src/python-api
pip install -r requirements.txt
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
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Backend | Python + FastAPI + SSE streaming |
| LLM | Azure OpenAI (`gpt-5.4` deployment name) via Microsoft Agent Framework |
| Pricing | Azure Retail Prices REST API (public, no auth) |
| Slides | PptxGenJS (Node.js template engine) |
| Diagrams | Mermaid (rendered client-side as SVG) |

### Key Design Decisions

- **MAF Workflow orchestration** — deterministic pipeline using Microsoft Agent Framework (MAF) with HITL approval gates, two-phase assumption input, and OpenTelemetry tracing.
- **Shared state** — a single `AgentState` dataclass flows between agents. Each reads what it needs and writes its output.
- **Two-phase inputs** — both Cost and Business Value agents ask usage/assumption questions first, then calculate with real numbers.
- **Template-based slides** — a PptxGenJS script template handles all layout; the LLM only generates text content as JSON.

## Project Structure

```
src/
├── python-api/                     # FastAPI backend
│   ├── main.py                     # Routes, SSE streaming, PPTX download
│   ├── maf_orchestrator.py         # MAF-based orchestrator (workflow execution)
│   ├── workflow.py                 # MAF workflow definition, HITL, response handling
│   ├── agents/
│   │   ├── llm.py                  # Azure OpenAI connection
│   │   ├── state.py                # Shared AgentState dataclass
│   │   ├── pm_agent.py             # Project Manager + intent classifier
│   │   ├── architect_agent.py      # Mermaid diagrams + components
│   │   ├── cost_agent.py           # SKU mapping + Azure Pricing API
│   │   ├── business_value_agent.py # Two-phase value driver analysis
│   │   ├── roi_agent.py            # Pure-math ROI + visual dashboard
│   │   └── presentation_agent.py   # PptxGenJS template + LLM text
│   ├── services/
│   │   ├── pricing.py              # Azure Retail Prices API client
│   │   ├── presentation.py         # PptxGenJS execution
│   │   ├── web_search.py           # DuckDuckGo for BV benchmarks
│   │   └── mcp.py                  # Microsoft Learn MCP client
│   ├── data/
│   │   └── knowledge_base.py       # Reference architecture patterns
│   └── templates/
│       └── slide_master.pptx       # Branded PPTX template
└── frontend/                       # React SPA
    └── src/
        ├── pages/
        │   ├── Landing.tsx          # Industry cards, agent toggles
        │   └── Chat.tsx             # Chat interface with SSE
        └── components/
            ├── AgentSidebar.tsx     # Agent toggles + status
            ├── ChatThread.tsx       # Messages, approvals, dashboards
            ├── AssumptionsInput.tsx  # Number input fields
            ├── ROIDashboard.tsx     # KPI cards, cost bars, projection
            ├── MessageContent.tsx   # Markdown + Mermaid rendering
            └── MermaidDiagram.tsx   # SVG diagram renderer
```

## Features

- **Natural language input** — describe the opportunity, the PM handles the rest
- **Agent toggles** — turn agents on/off to customize the scoping flow
- **Real Azure pricing** — Cost agent queries the live Azure Retail Prices API
- **Assumption-driven** — both cost and business value ask for real numbers before calculating
- **ROI dashboard** — visual cost comparison, value drivers, 3-year projection
- **Architecture diagrams** — Mermaid flowcharts rendered as interactive SVG
- **Executive deck** — professional PowerPoint generated via PptxGenJS template
- **SSE streaming** — agent output streams to the UI in real-time
- **Guided + fast-run modes** — pause at each step for approval, or run the full pipeline

> **Note:** Three additional agents (Envisioning, Solution Engineer, Platform Engineer) are registered in the UI but not yet implemented.

## License

[ISC](LICENSE)
