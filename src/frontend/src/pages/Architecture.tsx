import MermaidDiagram from '../components/MermaidDiagram';

const ARCHITECTURE_DIAGRAM = `graph TD
    subgraph Frontend["React SPA (Vite + TypeScript)"]
        LP[Landing Page<br/>Industry Templates]
        CH[Chat Interface<br/>SSE Streaming]
        AS[Agent Sidebar<br/>Toggle Controls]
        RD[ROI Dashboard<br/>Visual Analytics]
        MD[Mermaid Renderer<br/>Architecture SVG]
    end

    subgraph Backend["FastAPI Backend (Python)"]
        API[HTTP Routes<br/>SSE + REST]
        ORC[MAF Orchestrator<br/>Phase Machine]
        WF[MAF Workflow<br/>Executor Pipeline]
    end

    subgraph Agents["Specialist Agents"]
        PM[Project Manager<br/>Intent Classification]
        BV[Business Value<br/>Two-Phase Drivers]
        AR[System Architect<br/>Mermaid + Components]
        CO[Cost & Services<br/>Two-Phase Pricing]
        ROI[ROI Calculator<br/>Pure Math]
        PR[Presentation<br/>PptxGenJS]
    end

    subgraph External["External Services"]
        AOAI[Azure OpenAI<br/>GPT-5.4]
        PRICE[Azure Retail<br/>Prices API]
        MCP[Microsoft Learn<br/>MCP Server]
        DDG[DuckDuckGo<br/>Benchmark Search]
        NODE[Node.js<br/>PptxGenJS Runtime]
    end

    LP --> API
    CH --> API
    AS --> API
    API --> ORC
    ORC --> PM
    ORC --> WF
    WF --> BV --> AR --> CO --> ROI --> PR

    PM --> AOAI
    BV --> AOAI
    BV --> DDG
    AR --> AOAI
    AR --> MCP
    CO --> AOAI
    CO --> PRICE
    PR --> AOAI
    PR --> NODE

    API --> CH
    API --> RD
    API --> MD`;

const SEQUENCE_DIAGRAM = `sequenceDiagram
    participant U as Seller
    participant FE as React Frontend
    participant API as FastAPI
    participant ORC as Orchestrator
    participant PM as Project Manager
    participant AG as Agent Pipeline

    U->>FE: Describe customer need
    FE->>API: POST /api/projects (create)
    FE->>API: POST /chat (SSE stream)
    API->>ORC: handle_message()
    ORC->>PM: brainstorm_greeting()
    PM-->>FE: Clarifying questions (SSE)
    U->>FE: Answer questions
    FE->>API: POST /chat
    ORC->>PM: classify_intent() → PROCEED
    ORC->>U: Shared assumption questions
    U->>FE: Fill assumptions
    ORC->>AG: Start MAF Workflow
    loop For each agent
        AG-->>FE: agent_start (SSE)
        AG->>AG: Run agent (thread pool)
        AG-->>FE: agent_token stream (SSE)
        AG-->>FE: Approval gate or assumptions_input
        U->>FE: Approve / fill inputs
    end
    AG-->>FE: pipeline_done + PPTX path
    U->>FE: Download deck
    FE->>API: GET /export/pptx`;

export default function Architecture() {
  return (
    <main className="flex-1 overflow-y-auto bg-[var(--bg-main)] px-8 py-10">
      <div className="max-w-5xl mx-auto space-y-10">

        <div className="space-y-2">
          <h1 className="text-3xl font-bold text-[var(--text-primary)] tracking-tight">How OneStopAgent Works</h1>
          <p className="text-[var(--text-secondary)]">
            A multi-agent pipeline that takes a customer idea and produces a fully scoped Azure solution
            with architecture, cost estimate, ROI analysis, and executive presentation.
          </p>
        </div>

        {/* System Architecture */}
        <section className="space-y-4">
          <h2 className="text-xl font-bold text-[var(--text-primary)]">System Architecture</h2>
          <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6 overflow-x-auto">
            <MermaidDiagram mermaidCode={ARCHITECTURE_DIAGRAM} />
          </div>
        </section>

        {/* Agent Pipeline */}
        <section className="space-y-4">
          <h2 className="text-xl font-bold text-[var(--text-primary)]">Agent Pipeline</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { emoji: '🎯', name: 'Project Manager', desc: 'Orchestrates the conversation, classifies intent, asks clarifying questions, and coordinates the pipeline.' },
              { emoji: '📊', name: 'Business Value', desc: 'Two-phase: collects assumptions, then computes value drivers with arithmetic from user inputs. Cost-reduction capped at baseline.' },
              { emoji: '🏗️', name: 'System Architect', desc: 'Designs layered Azure architecture with Mermaid diagrams, using Microsoft Learn MCP for reference patterns.' },
              { emoji: '💰', name: 'Cost & Services', desc: 'Maps components to Azure SKUs, queries the Retail Prices API in parallel, estimates monthly/annual costs.' },
              { emoji: '📈', name: 'ROI Calculator', desc: 'Pure math — no LLM. Computes Year 1 ROI (adoption-adjusted), payback, waterfall, sensitivity, 3-year projection.' },
              { emoji: '📑', name: 'Presentation', desc: 'LLM generates a complete PptxGenJS script that produces an executive-ready PowerPoint deck.' },
            ].map((a, i) => (
              <div key={i} className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">{a.emoji}</span>
                  <h3 className="text-sm font-bold text-[var(--text-primary)]">{a.name}</h3>
                </div>
                <p className="text-xs text-[var(--text-muted)] leading-relaxed">{a.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Orchestration Flow */}
        <section className="space-y-4">
          <h2 className="text-xl font-bold text-[var(--text-primary)]">Orchestration Flow</h2>
          <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6 overflow-x-auto">
            <MermaidDiagram mermaidCode={SEQUENCE_DIAGRAM} />
          </div>
        </section>

        {/* Tech Stack */}
        <section className="space-y-4">
          <h2 className="text-xl font-bold text-[var(--text-primary)]">Tech Stack</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: 'Frontend', value: 'React + Vite + Tailwind' },
              { label: 'Backend', value: 'Python FastAPI' },
              { label: 'Orchestration', value: 'Microsoft Agent Framework' },
              { label: 'LLM', value: 'Azure OpenAI GPT-5.4' },
              { label: 'Deployment', value: 'Azure Container Apps' },
              { label: 'Pricing', value: 'Azure Retail Prices API' },
              { label: 'Presentation', value: 'PptxGenJS via Node.js' },
              { label: 'Observability', value: 'OpenTelemetry' },
            ].map((t, i) => (
              <div key={i} className="bg-[var(--bg-subtle)] border border-[var(--border-light)] rounded-lg p-3">
                <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">{t.label}</p>
                <p className="text-xs font-medium text-[var(--text-primary)] mt-0.5">{t.value}</p>
              </div>
            ))}
          </div>
        </section>

      </div>
    </main>
  );
}
