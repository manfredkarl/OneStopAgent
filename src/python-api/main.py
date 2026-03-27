"""OneStopAgent Python/FastAPI backend."""

from __future__ import annotations

import json
import uuid
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

AGENT_INFO = {
    "generate_architecture": {"name": "System Architect", "emoji": "🏗️"},
    "select_azure_services": {"name": "Azure Specialist", "emoji": "☁️"},
    "estimate_costs": {"name": "Cost Specialist", "emoji": "💰"},
    "assess_business_value": {"name": "Business Value", "emoji": "📊"},
    "generate_presentation": {"name": "Presentation", "emoji": "📑"},
    "suggest_scenarios": {"name": "Envisioning", "emoji": "💡"},
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

    current_text = ""
    current_msg_id = str(uuid.uuid4())

    async for event in agent.astream(
        {"messages": [{"role": "user", "content": user_message}]},
        config=config,
        stream_mode="messages",
    ):
        msg, metadata = event

        # AIMessage content tokens (PM text streaming)
        if msg.type in ("ai", "AIMessageChunk") and msg.content and not getattr(msg, "tool_calls", None):
            current_text += msg.content
            yield ChatMessage(
                id=current_msg_id,
                project_id=project_id,
                role="agent",
                agent_id="pm",
                content=current_text,
                metadata={"type": "pm_response_chunk", "streaming": True},
            )

        # AIMessage with tool calls (PM decided to call a tool)
        elif msg.type in ("ai", "AIMessageChunk") and getattr(msg, "tool_calls", None):
            # Finalize any pending text
            if current_text:
                yield ChatMessage(
                    id=current_msg_id,
                    project_id=project_id,
                    role="agent",
                    agent_id="pm",
                    content=current_text,
                    metadata={"type": "pm_response"},
                )
                current_text = ""
                current_msg_id = str(uuid.uuid4())

            # Announce each tool call
            for tc in msg.tool_calls:
                tool_name = tc["name"]
                agent_info = AGENT_INFO.get(tool_name, {"name": tool_name, "emoji": "🔧"})
                yield ChatMessage(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    role="agent",
                    agent_id="pm",
                    content=f"{agent_info['emoji']} {agent_info['name']} is working...",
                    metadata={"type": "agent_announcement", "tool": tool_name},
                )

        # ToolMessage (tool completed)
        elif msg.type in ("tool", "ToolMessage", "ToolMessageChunk"):
            try:
                tool_result = json.loads(msg.content)
                yield ChatMessage(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    role="agent",
                    agent_id=tool_result.get("agentId", getattr(msg, "name", "tool")),
                    content=_format_tool_output(tool_result),
                    metadata=tool_result,
                )
            except json.JSONDecodeError:
                yield ChatMessage(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    role="agent",
                    agent_id=getattr(msg, "name", "tool"),
                    content=msg.content,
                    metadata={"type": "tool_result"},
                )

    # Finalize any remaining text
    if current_text:
        yield ChatMessage(
            id=current_msg_id,
            project_id=project_id,
            role="agent",
            agent_id="pm",
            content=current_text,
            metadata={"type": "pm_response"},
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

    # Non-streaming: collect all — skip intermediate chunks, only keep final messages
    messages: list[dict] = []
    last_chunk_id: str | None = None
    last_chunk_msg: ChatMessage | None = None
    try:
        async for msg in _run_agent(project_id, session, req.message):
            is_chunk = msg.metadata and msg.metadata.get("streaming")
            if is_chunk:
                # Keep updating the last chunk — only emit the final version
                last_chunk_id = msg.id
                last_chunk_msg = msg
                continue
            else:
                # Emit the finalized chunk if any
                if last_chunk_msg:
                    last_chunk_msg.metadata = {"type": "pm_response"}
                    store.add_message(project_id, last_chunk_msg)
                    messages.append(last_chunk_msg.model_dump())
                    last_chunk_msg = None
                    last_chunk_id = None
                store.add_message(project_id, msg)
                messages.append(msg.model_dump())
        # Emit any trailing chunk
        if last_chunk_msg:
            last_chunk_msg.metadata = {"type": "pm_response"}
            store.add_message(project_id, last_chunk_msg)
            messages.append(last_chunk_msg.model_dump())
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = ChatMessage(
            project_id=project_id, role="agent", agent_id="pm",
            content=f"An error occurred: {str(e)}",
            metadata={"type": "error"}
        )
        store.add_message(project_id, error_msg)
        messages.append(error_msg.model_dump())
    return messages


async def _stream_sse(
    project_id: str, session: dict, user_message: str
) -> AsyncGenerator[dict, None]:
    async for msg in _run_agent(project_id, session, user_message):
        # Only persist final messages, not intermediate streaming chunks
        is_chunk = msg.metadata and msg.metadata.get("streaming")
        if not is_chunk:
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
