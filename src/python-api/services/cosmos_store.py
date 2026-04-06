"""Cosmos DB-backed project and chat storage.

Uses async Cosmos client with DefaultAzureCredential (managed identity).
Falls back to in-memory ProjectStore if Cosmos is unavailable.
"""

from __future__ import annotations

import logging
import dataclasses
from typing import Any, Optional

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential

from models.schemas import Project, ChatMessage
from agents.state import AgentState

logger = logging.getLogger(__name__)


class CosmosProjectStore:
    """Drop-in replacement for ProjectStore backed by Azure Cosmos DB."""

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._credential = DefaultAzureCredential()
        self._client = CosmosClient(endpoint, credential=self._credential)
        self._db = self._client.get_database_client("onestopagent")
        self._projects = self._db.get_container_client("projects")
        self._messages = self._db.get_container_client("chat_messages")
        self._agent_state = self._db.get_container_client("agent_state")

    # ── Projects ─────────────────────────────────────────────────────

    async def create_project(
        self,
        user_id: str,
        description: str,
        customer_name: Optional[str] = None,
        company_profile: Optional[dict] = None,
    ) -> Project:
        project = Project(
            user_id=user_id,
            description=description,
            customer_name=customer_name,
            company_profile=company_profile,
        )
        doc = project.model_dump(mode="json")
        doc["userId"] = user_id  # partition key
        await self._projects.create_item(doc)
        return project

    async def get_project(self, project_id: str, user_id: str) -> Optional[Project]:
        try:
            doc = await self._projects.read_item(project_id, partition_key=user_id)
            return _doc_to_project(doc)
        except Exception:
            return None

    async def list_projects(self, user_id: str) -> list[Project]:
        query = "SELECT * FROM c WHERE c.userId = @uid ORDER BY c.created_at DESC"
        params: list[dict[str, Any]] = [{"name": "@uid", "value": user_id}]
        items = self._projects.query_items(query, parameters=params, partition_key=user_id)
        return [_doc_to_project(doc) async for doc in items]

    # ── Chat messages ────────────────────────────────────────────────

    async def add_message(self, project_id: str, message: ChatMessage) -> None:
        doc = message.model_dump(mode="json")
        doc["projectId"] = project_id  # partition key
        await self._messages.create_item(doc)

    async def get_messages(self, project_id: str) -> list[ChatMessage]:
        query = "SELECT * FROM c WHERE c.projectId = @pid ORDER BY c.timestamp ASC"
        params: list[dict[str, Any]] = [{"name": "@pid", "value": project_id}]
        items = self._messages.query_items(query, parameters=params, partition_key=project_id)
        return [_doc_to_message(doc) async for doc in items]

    # ── Agent state persistence ──────────────────────────────────────

    async def save_state(self, project_id: str, state: AgentState) -> None:
        doc = _agent_state_to_doc(project_id, state)
        await self._agent_state.upsert_item(doc)

    async def load_state(self, project_id: str) -> Optional[AgentState]:
        try:
            doc = await self._agent_state.read_item(project_id, partition_key=project_id)
            return _doc_to_agent_state(doc)
        except Exception:
            return None

    # ── Testing helper ───────────────────────────────────────────────

    async def clear(self) -> None:
        """Delete all items from all containers (for testing)."""
        for container in (self._projects, self._messages, self._agent_state):
            async for doc in container.read_all_items():
                pk = doc.get("userId") or doc.get("projectId") or doc["id"]
                await container.delete_item(doc["id"], partition_key=pk)


# ── Serialization helpers ────────────────────────────────────────────

def _doc_to_project(doc: dict) -> Project:
    """Convert a Cosmos document back to a Project model."""
    # Remove Cosmos system properties
    for key in ("_rid", "_self", "_etag", "_attachments", "_ts", "userId"):
        doc.pop(key, None)
    return Project.model_validate(doc)


def _doc_to_message(doc: dict) -> ChatMessage:
    for key in ("_rid", "_self", "_etag", "_attachments", "_ts", "projectId"):
        doc.pop(key, None)
    return ChatMessage.model_validate(doc)


def _agent_state_to_doc(project_id: str, state: AgentState) -> dict:
    """Serialize AgentState dataclass to a Cosmos-friendly dict."""
    raw = state.__getstate__()
    doc: dict[str, Any] = {}
    for k, v in raw.items():
        doc[k] = v
    doc["id"] = project_id
    doc["projectId"] = project_id  # partition key
    return doc


def _doc_to_agent_state(doc: dict) -> AgentState:
    """Deserialize a Cosmos document into an AgentState dataclass."""
    for key in ("_rid", "_self", "_etag", "_attachments", "_ts", "id", "projectId"):
        doc.pop(key, None)
    state = AgentState()
    for k, v in doc.items():
        if hasattr(state, k):
            setattr(state, k, v)
    return state
