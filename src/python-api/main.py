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
from orchestrator import Orchestrator

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

orchestrator = Orchestrator()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/info")
async def info():
    return {"version": "1.0.0", "framework": "python-fastapi-langchain"}


@app.post("/api/projects")
async def create_project(req: CreateProjectRequest, x_user_id: str = Header()):
    project = store.create_project(x_user_id, req.description, req.customer_name)
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

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
