"""OneStopAgent Python/FastAPI backend."""

from __future__ import annotations

import json
import logging
import os
import re
import traceback
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from sse_starlette.sse import EventSourceResponse

from models.schemas import (
    ChatMessage,
    CreateProjectRequest,
    SendMessageRequest,
)
from services.company_intelligence import (
    build_fallback_profile,
    FALLBACK_PROFILES,
    search_and_extract_company,
)
from orchestration.maf_orchestrator import MAFOrchestrator
from core.telemetry import setup_telemetry
from orchestration.workflow import create_pipeline_workflow

setup_telemetry()

# ---------------------------------------------------------------------------
# Project store — Cosmos DB when configured, in-memory otherwise
# ---------------------------------------------------------------------------

_cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT")
if _cosmos_endpoint:
    try:
        from services.cosmos_store import CosmosProjectStore
        store = CosmosProjectStore(_cosmos_endpoint)
        logging.getLogger(__name__).info("Using Cosmos DB store: %s", _cosmos_endpoint)
    except Exception as e:
        logging.getLogger(__name__).warning("Cosmos DB init failed (%s) — falling back to in-memory store", e)
        from services.project_store import store  # noqa: F811
else:
    from services.project_store import store  # noqa: F811 — module-level singleton
    logging.getLogger(__name__).info("COSMOS_ENDPOINT not set — using in-memory store")

# ---------------------------------------------------------------------------
# x-user-id header validation
# ---------------------------------------------------------------------------

_USER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _get_user_id(request: Request) -> str:
    """Extract and validate the x-user-id header."""
    user_id = request.headers.get("x-user-id", "")
    if not _USER_ID_RE.match(user_id):
        raise HTTPException(status_code=400, detail="Invalid or missing x-user-id header")
    return user_id


# ---------------------------------------------------------------------------
# Security — allowed output directory for file downloads
# ---------------------------------------------------------------------------

OUTPUT_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "output"))

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="OneStopAgent API", version="1.0.0")

_cors_origins = os.environ.get("CORS_ORIGINS", "")
_allow_origins = _cors_origins.split(",") if _cors_origins else ["http://localhost:4200", "http://localhost:4201", "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "x-user-id", "Accept"],
)

orchestrator = MAFOrchestrator(store=store)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/workflow")
async def workflow_viz():
    """Interactive MAF workflow visualization."""
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


@app.get("/api/company/search")
async def search_company(q: str):
    """Search for a company profile by name. Returns up to 3 ranked matches."""
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    results = await search_and_extract_company(q.strip())
    return results


@app.get("/api/company/fallback/{size}")
async def company_fallback(size: str, name: str = ""):
    """Return a fallback company profile for unknown companies."""
    if size not in FALLBACK_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unknown size tier '{size}'. Use: small, mid-market, enterprise")
    return build_fallback_profile(size, name or size.title())


@app.post("/api/projects")
async def create_project(req: CreateProjectRequest, x_user_id: str = Depends(_get_user_id)):
    project = await store.create_project(
        x_user_id, req.description, req.customer_name,
        company_profile=req.company_profile,
    )
    # Override default active_agents if provided by frontend
    if req.active_agents is not None:
        project.active_agents = [a.replace("-", "_") for a in req.active_agents]
    return {"projectId": project.id}


@app.get("/api/projects")
async def list_projects(x_user_id: str = Depends(_get_user_id)):
    projects = await store.list_projects(x_user_id)
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
async def get_project(project_id: str, x_user_id: str = Depends(_get_user_id)):
    project = await store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.model_dump()


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, x_user_id: str = Depends(_get_user_id)):
    deleted = await store.delete_project(project_id, x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    # Also clean up orchestrator state
    orchestrator.states.pop(project_id, None)
    orchestrator.phases.pop(project_id, None)
    return {"deleted": True}


@app.patch("/api/projects/{project_id}")
async def update_project(project_id: str, request: Request, x_user_id: str = Depends(_get_user_id)):
    project = await store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    body = await request.json()
    if "description" in body:
        project.description = body["description"]
    if hasattr(store, "update_project"):
        await store.update_project(project)
    return project.model_dump()


@app.post("/api/projects/{project_id}/chat")
async def send_message(
    project_id: str,
    req: SendMessageRequest,
    request: Request,
    x_user_id: str = Depends(_get_user_id),
):
    project = await store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Store user message
    user_msg = ChatMessage(project_id=project_id, role="user", content=req.message)
    await store.add_message(project_id, user_msg)

    # SSE streaming
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        async def stream() -> AsyncGenerator[dict, None]:
            try:
                async for msg in orchestrator.handle_message(
                    project_id, req.message, project.active_agents, project.description,
                    company_profile=project.company_profile,
                ):
                    # Don't persist individual streaming tokens — only final messages
                    if msg.metadata is None or msg.metadata.get("type") != "agent_token":
                        await store.add_message(project_id, msg)
                    yield {"event": "message", "data": json.dumps(msg.model_dump(), default=str)}
            except Exception as e:
                logging.getLogger(__name__).exception("SSE stream error")
                error_msg = ChatMessage(
                    project_id=project_id, role="agent", agent_id="pm",
                    content=f"An error occurred: {str(e)}",
                    metadata={"type": "error"},
                )
                yield {"event": "message", "data": json.dumps(error_msg.model_dump(), default=str)}
            yield {"event": "done", "data": "[DONE]"}
        return EventSourceResponse(stream())

    # Non-streaming fallback
    messages: list[dict] = []
    try:
        async for msg in orchestrator.handle_message(
            project_id, req.message, project.active_agents, project.description,
            company_profile=project.company_profile,
        ):
            if not (msg.metadata and msg.metadata.get("type") == "agent_token"):
                await store.add_message(project_id, msg)
            messages.append(msg.model_dump())
    except Exception as e:
        traceback.print_exc()
        error_msg = ChatMessage(
            project_id=project_id, role="agent", agent_id="pm",
            content=f"An error occurred: {str(e)}",
            metadata={"type": "error"},
        )
        await store.add_message(project_id, error_msg)
        messages.append(error_msg.model_dump())
    return messages


@app.get("/api/projects/{project_id}/chat")
async def get_chat_history(project_id: str, x_user_id: str = Depends(_get_user_id)):
    project = await store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    messages = await store.get_messages(project_id)
    return {
        "messages": [m.model_dump() for m in messages],
        "hasMore": False,
        "nextCursor": None,
    }


@app.get("/api/projects/{project_id}/agents")
async def get_agents(project_id: str, x_user_id: str = Depends(_get_user_id)):
    project = await store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Normalize for comparison (frontend sends hyphens, backend uses underscores)
    normalized = {a.replace("-", "_") for a in project.active_agents}
    all_agents = [
        {"agentId": "pm", "displayName": "Project Manager", "status": "idle", "active": True},
        {"agentId": "architect", "displayName": "System Architect", "status": "idle", "active": True},
        {"agentId": "cost", "displayName": "Cost & Services", "status": "idle", "active": "cost" in normalized},
        {"agentId": "business-value", "displayName": "Business Value", "status": "idle", "active": "business_value" in normalized},
        {"agentId": "roi", "displayName": "ROI Calculator", "status": "idle", "active": "roi" in normalized},
        {"agentId": "presentation", "displayName": "Presentation", "status": "idle", "active": "presentation" in normalized},
    ]
    return {"agents": all_agents}


@app.patch("/api/projects/{project_id}/agents/{agent_id}")
async def toggle_agent(
    project_id: str,
    agent_id: str,
    request: Request,
    x_user_id: str = Depends(_get_user_id),
):
    project = await store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    active = body.get("active", True)

    # Normalize: frontend sends hyphens, backend stores underscores
    agent_id = agent_id.replace("-", "_")

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
    await store.clear()
    return {"message": "Store cleared"}


# ---------------------------------------------------------------------------
# Iteration History
# ---------------------------------------------------------------------------

@app.get("/api/projects/{project_id}/iterations")
async def get_iterations(project_id: str, x_user_id: str = Depends(_get_user_id)):
    """Return the iteration history (before/after snapshots) for a project."""
    project = await store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = orchestrator.get_state(project_id)
    return {"iterations": state.iteration_history if state else []}


# ---------------------------------------------------------------------------
# PPTX Download
# ---------------------------------------------------------------------------

@app.get("/api/projects/{project_id}/export/pptx")
async def download_pptx(project_id: str, x_user_id: str = Depends(_get_user_id)):
    """Download the generated PowerPoint deck."""
    project = await store.get_project(project_id, x_user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get presentation path from orchestrator state
    state = orchestrator.get_state(project_id)
    path = state.presentation_path

    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Presentation not generated yet. Run all agents first.")

    # Path validation — prevent directory traversal (realpath resolves symlinks)
    abs_path = os.path.realpath(path)
    if not abs_path.startswith(OUTPUT_DIR):
        raise HTTPException(status_code=403, detail="Access denied")
    if not abs_path.endswith(".pptx"):
        raise HTTPException(status_code=403, detail="Invalid file type")

    filename = os.path.basename(abs_path)
    return FileResponse(
        abs_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

if __name__ == "__main__":
    import uvicorn

    dev_mode = os.environ.get("ENV", "production").lower() == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=dev_mode)
