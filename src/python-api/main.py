"""OneStopAgent Python/FastAPI backend."""

from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from models.schemas import (
    ChatMessage,
    CreateProjectRequest,
    SendMessageRequest,
)
from services.project_store import store
from maf_orchestrator import MAFOrchestrator
from telemetry import setup_telemetry

setup_telemetry()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="OneStopAgent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = MAFOrchestrator()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/workflow")
async def workflow_viz():
    """Interactive MAF workflow visualization."""
    from fastapi.responses import HTMLResponse
    from workflow import create_pipeline_workflow

    wf = create_pipeline_workflow()
    d = wf.to_dict()
    names = {
        "architect_executor": "🏗️ Architect",
        "cost_executor": "💰 Cost & Services",
        "bv_executor": "📊 Business Value",
        "roi_executor": "📈 ROI Calculator",
        "presentation_executor": "📑 Presentation",
    }
    mermaid_lines = ["graph LR"]
    for eg in d["edge_groups"]:
        if eg["type"] == "SingleEdgeGroup":
            for e in eg["edges"]:
                src, tgt = e["source_id"], e["target_id"]
                mermaid_lines.append(f'    {src}["{names.get(src, src)}"] --> {tgt}["{names.get(tgt, tgt)}"]')
    mermaid_code = "\n".join(mermaid_lines)

    html = f"""<!DOCTYPE html>
<html><head><title>OneStopAgent — MAF Workflow</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<style>
  body {{ font-family: Segoe UI, sans-serif; background: #0f0f0f; color: #e0e0e0; margin: 0; padding: 40px; }}
  h1 {{ color: #60a5fa; font-size: 1.5rem; }}
  .info {{ background: #1a1a2e; border-radius: 12px; padding: 24px; margin: 20px 0; }}
  .info h2 {{ color: #818cf8; font-size: 1.1rem; margin-top: 0; }}
  .info ul {{ padding-left: 20px; }}
  .info li {{ margin: 6px 0; }}
  .tag {{ background: #334155; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; }}
  .mermaid {{ background: #1e293b; border-radius: 12px; padding: 30px; text-align: center; }}
</style></head><body>
<h1>Microsoft Agent Framework — Workflow Pipeline</h1>
<div class="mermaid">{mermaid_code}</div>
<div class="info">
  <h2>Pipeline Details</h2>
  <ul>
    <li><b>Framework:</b> <span class="tag">agent-framework 1.0.0rc5</span></li>
    <li><b>Orchestration:</b> MAF Workflow with HITL approval gates</li>
    <li><b>Executors:</b> {len(wf.get_executors_list())} sequential steps</li>
    <li><b>Start:</b> {wf.get_start_executor().id}</li>
    <li><b>HITL:</b> Approval gates after each step + two-phase assumption input (Cost, BV)</li>
  </ul>
</div>
<div class="info">
  <h2>Agents</h2>
  <ul>
    <li>🤖 <b>Project Manager</b> — Brainstorms scenarios, classifies intent, orchestrates flow</li>
    <li>🏗️ <b>System Architect</b> — Layered Azure architecture with Mermaid diagrams (MCP + local patterns)</li>
    <li>💰 <b>Cost & Services</b> — SKU mapping + Azure Retail Prices API (two-phase)</li>
    <li>📊 <b>Business Value</b> — Value drivers with industry benchmarks (two-phase)</li>
    <li>📈 <b>ROI Calculator</b> — Pure-math ROI, payback, cost comparison, 3-year projection</li>
    <li>📑 <b>Presentation</b> — Executive PowerPoint via PptxGenJS</li>
  </ul>
</div>
<script>mermaid.initialize({{theme:'dark',startOnLoad:true}});</script>
</body></html>"""
    return HTMLResponse(content=html)


@app.get("/api/info")
async def info():
    return {"version": "1.0.0", "framework": "python-fastapi-agent-framework"}


@app.post("/api/projects")
async def create_project(req: CreateProjectRequest, x_user_id: str = Header()):
    project = store.create_project(x_user_id, req.description, req.customer_name)
    # Override default active_agents if provided by frontend
    if req.active_agents is not None:
        project.active_agents = req.active_agents
    return {"projectId": project.id}


@app.get("/api/projects")
async def list_projects(x_user_id: str = Header()):
    projects = store.list_projects(x_user_id)
    return [
        {
            "projectId": p.id,
            "description": p.description[:200],
            "customerName": p.customer_name,
            "status": p.status,
            "updatedAt": p.created_at.isoformat(),
        }
        for p in projects
    ]


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, x_user_id: str = Header()):
    project = store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.model_dump()


@app.post("/api/projects/{project_id}/chat")
async def send_message(
    project_id: str,
    req: SendMessageRequest,
    request: Request,
    x_user_id: str = Header(),
):
    project = store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Store user message
    user_msg = ChatMessage(project_id=project_id, role="user", content=req.message)
    store.add_message(project_id, user_msg)

    # SSE streaming
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        async def stream() -> AsyncGenerator[dict, None]:
            async for msg in orchestrator.handle_message(
                project_id, req.message, project.active_agents, project.description
            ):
                # Don't persist individual streaming tokens — only final messages
                if msg.metadata is None or msg.metadata.get("type") != "agent_token":
                    store.add_message(project_id, msg)
                yield {"event": "message", "data": json.dumps(msg.model_dump(), default=str)}
            yield {"event": "done", "data": "[DONE]"}
        return EventSourceResponse(stream())

    # Non-streaming fallback
    messages: list[dict] = []
    try:
        async for msg in orchestrator.handle_message(
            project_id, req.message, project.active_agents, project.description
        ):
            store.add_message(project_id, msg)
            messages.append(msg.model_dump())
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = ChatMessage(
            project_id=project_id, role="agent", agent_id="pm",
            content=f"An error occurred: {str(e)}",
            metadata={"type": "error"},
        )
        store.add_message(project_id, error_msg)
        messages.append(error_msg.model_dump())
    return messages


@app.get("/api/projects/{project_id}/chat")
async def get_chat_history(project_id: str, x_user_id: str = Header()):
    project = store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    messages = store.get_messages(project_id)
    return {
        "messages": [m.model_dump() for m in messages],
        "hasMore": False,
        "nextCursor": None,
    }


@app.get("/api/projects/{project_id}/agents")
async def get_agents(project_id: str, x_user_id: str = Header()):
    project = store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    all_agents = [
        {"agentId": "pm", "displayName": "Project Manager", "status": "idle", "active": True},
        {"agentId": "architect", "displayName": "System Architect", "status": "idle", "active": True},
        {"agentId": "cost", "displayName": "Cost & Services", "status": "idle", "active": "cost" in project.active_agents},
        {"agentId": "business-value", "displayName": "Business Value", "status": "idle", "active": "business-value" in project.active_agents},
        {"agentId": "roi", "displayName": "ROI Calculator", "status": "idle", "active": "roi" in project.active_agents},
        {"agentId": "presentation", "displayName": "Presentation", "status": "idle", "active": "presentation" in project.active_agents},
    ]
    return {"agents": all_agents}


@app.patch("/api/projects/{project_id}/agents/{agent_id}")
async def toggle_agent(
    project_id: str,
    agent_id: str,
    request: Request,
    x_user_id: str = Header(),
):
    project = store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    active = body.get("active", True)

    if agent_id in ("pm", "architect") and not active:
        raise HTTPException(status_code=400, detail=f"Cannot deactivate required agent: {agent_id}")

    if active and agent_id not in project.active_agents:
        project.active_agents.append(agent_id)
    elif not active and agent_id in project.active_agents:
        project.active_agents.remove(agent_id)

    return await get_agents(project_id, x_user_id)


@app.post("/api/test/reset")
async def test_reset():
    """Clear all data (for testing)."""
    store.clear()
    return {"message": "Store cleared"}


# ---------------------------------------------------------------------------
# PPTX Download
# ---------------------------------------------------------------------------

@app.get("/api/projects/{project_id}/export/pptx")
async def download_pptx(project_id: str, x_user_id: str = Header()):
    """Download the generated PowerPoint deck."""
    import os
    from fastapi.responses import FileResponse

    project = store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get presentation path from orchestrator state
    state = orchestrator.get_state(project_id)
    path = state.presentation_path

    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Presentation not generated yet. Run all agents first.")

    filename = os.path.basename(path)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
# ---------------------------------------------------------------------------
# MAF DevUI — debug chat interface for local development
# ---------------------------------------------------------------------------
# The agent-framework-devui package provides a built-in browser UI that
# discovers MAF agents/workflows from a directory and exposes an
# OpenAI-compatible chat API.  It runs on a separate port (default 8080)
# so it doesn't interfere with the production API on :8000.
#
# Quick-start (from this directory):
#     python main.py              # starts API on :8000
#     python main.py --devui      # starts API on :8000 + DevUI on :8081
#
# Or standalone:
#     python -c "from agent_framework_devui import serve; serve(entities_dir='agents', port=8081, auto_open=True)"
# ---------------------------------------------------------------------------

_DEVUI_PORT = 8081


def _start_devui_background(port: int = _DEVUI_PORT) -> None:
    """Launch MAF DevUI on a background thread with all agents + workflow registered."""
    import threading

    def _run() -> None:
        try:
            from agent_framework_devui import EntityInfo, serve

            from workflow import create_pipeline_workflow

            wf = create_pipeline_workflow()
            wf_dump = wf.to_dict()

            entities = [
                EntityInfo(
                    id="onestop-pipeline",
                    type="workflow",
                    name="OneStopAgent Pipeline",
                    description="Full agent pipeline: Architect → Cost → BV → ROI → Presentation with HITL approval gates",
                    framework="agent-framework",
                    executors=[e.id for e in wf.get_executors_list()],
                    start_executor_id=wf.get_start_executor().id,
                    workflow_dump=wf_dump,
                ),
                EntityInfo(
                    id="pm-agent", type="agent", name="Project Manager",
                    description="Brainstorms Azure scenarios, classifies intent, builds execution plans, and formats agent output",
                    framework="agent-framework",
                ),
                EntityInfo(
                    id="architect-agent", type="agent", name="System Architect",
                    description="Designs layered Azure architectures with Mermaid diagrams using MCP/local patterns",
                    framework="agent-framework",
                ),
                EntityInfo(
                    id="cost-agent", type="agent", name="Cost & Services",
                    description="Maps architecture to Azure SKUs and estimates costs via Azure Retail Prices API (two-phase: assumptions → pricing)",
                    framework="agent-framework",
                ),
                EntityInfo(
                    id="bv-agent", type="agent", name="Business Value",
                    description="Generates value drivers with industry benchmarks and annual impact ranges (two-phase: assumptions → drivers)",
                    framework="agent-framework",
                ),
                EntityInfo(
                    id="roi-agent", type="agent", name="ROI Calculator",
                    description="Pure-math ROI computation: cost comparison, value waterfall, 3-year projection, payback period",
                    framework="agent-framework",
                ),
                EntityInfo(
                    id="presentation-agent", type="agent", name="Presentation",
                    description="Generates executive PowerPoint deck via PptxGenJS with LLM-written slide content",
                    framework="agent-framework",
                ),
            ]

            serve(entities=entities, port=port, host="127.0.0.1", auto_open=True)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("DevUI failed to start: %s", exc)

    t = threading.Thread(target=_run, daemon=True, name="devui")
    t.start()


if __name__ == "__main__":
    import sys

    import uvicorn

    if "--devui" in sys.argv:
        sys.argv.remove("--devui")
        print(f"🤖 Starting MAF DevUI on http://127.0.0.1:{_DEVUI_PORT}")
        _start_devui_background()

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
