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
from agents.pm_agent import create_pm_agent

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="OneStopAgent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Per-project agent sessions (in-memory)
agent_sessions: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT_TOOL_MAP = {
    "architect": "generate_architecture",
    "azure-specialist": "select_azure_services",
    "cost": "estimate_costs",
    "business-value": "assess_business_value",
    "presentation": "generate_presentation",
    "envisioning": "suggest_scenarios",
}


def _get_active_tool_names(active_agents: list[str]) -> list[str]:
    return [AGENT_TOOL_MAP[a] for a in active_agents if a in AGENT_TOOL_MAP]


def _format_tool_output(result: dict) -> str:
    t = result.get("type", "")
    if t == "architecture":
        return result.get("narrative", "Architecture generated.")
    if t == "serviceSelections":
        count = len(result.get("selections", []))
        return f"Mapped {count} Azure services with SKU recommendations."
    if t == "costEstimate":
        est = result.get("estimate", {})
        return f"Cost estimate: ${est.get('totalMonthly', 0):,.2f}/month (${est.get('totalAnnual', 0):,.2f}/year)"
    if t == "businessValue":
        return result.get("assessment", {}).get("executiveSummary", "Business value assessed.")
    if t == "presentationReady":
        return f"Presentation generated with {result.get('metadata', {}).get('slideCount', 0)} slides."
    if t == "envisioning":
        count = len(result.get("scenarios", []))
        return f"Found {count} matching reference scenarios."
    return str(result)


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

async def _run_agent(
    project_id: str,
    session: dict,
    user_message: str,
) -> AsyncGenerator[ChatMessage, None]:
    """Run the LangGraph agent and yield ChatMessages for each step."""
    agent = session["agent"]
    thread_id = session["thread_id"]
    config = {"configurable": {"thread_id": thread_id}}

    async for event in agent.astream(
        {"messages": [{"role": "user", "content": user_message}]},
        config=config,
        stream_mode="updates",
    ):
        for node_name, node_output in event.items():
            messages = node_output.get("messages", [])
            for msg in messages:
                # LLM text response
                if node_name == "agent":
                    if hasattr(msg, "content") and msg.content:
                        yield ChatMessage(
                            project_id=project_id,
                            role="agent",
                            agent_id="pm",
                            content=msg.content,
                            metadata={"type": "pm_response"},
                        )
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            yield ChatMessage(
                                project_id=project_id,
                                role="agent",
                                agent_id="pm",
                                content=f"\U0001f527 Calling {tc['name']}...",
                                metadata={"type": "agent_announcement", "tool": tc["name"]},
                            )

                # Tool results
                elif node_name == "tools":
                    if hasattr(msg, "content") and msg.content:
                        try:
                            tool_result = json.loads(msg.content)
                            yield ChatMessage(
                                project_id=project_id,
                                role="agent",
                                agent_id=tool_result.get("agentId", getattr(msg, "name", "tool")),
                                content=_format_tool_output(tool_result),
                                metadata=tool_result,
                            )
                        except json.JSONDecodeError:
                            yield ChatMessage(
                                project_id=project_id,
                                role="agent",
                                agent_id="tool",
                                content=msg.content,
                            )


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

    # Get or create agent for this project
    if project_id not in agent_sessions:
        tool_names = _get_active_tool_names(project.active_agents)
        agent = create_pm_agent(tool_names)
        agent_sessions[project_id] = {"agent": agent, "thread_id": project_id}

    session = agent_sessions[project_id]

    # SSE streaming
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        return EventSourceResponse(_stream_sse(project_id, session, req.message))

    # Non-streaming: collect all
    messages: list[dict] = []
    async for msg in _run_agent(project_id, session, req.message):
        store.add_message(project_id, msg)
        messages.append(msg.model_dump())
    return messages


async def _stream_sse(
    project_id: str, session: dict, user_message: str
) -> AsyncGenerator[dict, None]:
    async for msg in _run_agent(project_id, session, user_message):
        store.add_message(project_id, msg)
        yield {
            "event": "message",
            "data": json.dumps(msg.model_dump(), default=str),
        }
    yield {"event": "done", "data": "[DONE]"}


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
        {"agentId": "envisioning", "displayName": "Envisioning", "status": "idle", "active": "envisioning" in project.active_agents},
        {"agentId": "architect", "displayName": "System Architect", "status": "idle", "active": True},
        {"agentId": "azure-specialist", "displayName": "Azure Specialist", "status": "idle", "active": "azure-specialist" in project.active_agents},
        {"agentId": "cost", "displayName": "Cost Specialist", "status": "idle", "active": "cost" in project.active_agents},
        {"agentId": "business-value", "displayName": "Business Value", "status": "idle", "active": "business-value" in project.active_agents},
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

    # Recreate agent with updated tools
    if project_id in agent_sessions:
        tool_names = _get_active_tool_names(project.active_agents)
        agent_sessions[project_id]["agent"] = create_pm_agent(tool_names)

    return await get_agents(project_id, x_user_id)


@app.post("/api/test/reset")
async def test_reset():
    """Clear all data (for testing)."""
    store.clear()
    agent_sessions.clear()
    return {"message": "Store cleared"}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
