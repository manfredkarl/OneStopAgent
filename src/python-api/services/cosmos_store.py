"""Cosmos DB-backed project and chat storage.

Uses async Cosmos client with DefaultAzureCredential (managed identity).
Falls back to in-memory ProjectStore if Cosmos is unavailable.
"""

from __future__ import annotations

import logging
import time
import dataclasses
from datetime import datetime
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
            logger.exception("Failed to get_project %s", project_id)
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

    async def delete_project(self, project_id: str, user_id: str) -> bool:
        """Delete a project, its messages, and state from Cosmos."""
        try:
            # Delete from projects container (partitioned by userId)
            await self._projects.delete_item(project_id, partition_key=user_id)
        except Exception:
            logger.exception("Failed to delete project %s", project_id)
            return False

        # Best-effort cleanup of messages and state (partitioned by projectId)
        try:
            query = "SELECT c.id FROM c WHERE c.projectId = @pid"
            params: list[dict[str, Any]] = [{"name": "@pid", "value": project_id}]
            async for doc in self._messages.query_items(query, parameters=params, partition_key=project_id):
                await self._messages.delete_item(doc["id"], partition_key=project_id)
            async for doc in self._agent_state.query_items(query, parameters=params, partition_key=project_id):
                await self._agent_state.delete_item(doc["id"], partition_key=project_id)
        except Exception:
            logger.warning("Partial cleanup for project %s", project_id, exc_info=True)

        return True

    # ── Agent state persistence ──────────────────────────────────────

    async def save_state(self, project_id: str, state: AgentState) -> None:
        doc = _agent_state_to_doc(project_id, state)
        await self._agent_state.upsert_item(doc)

    async def load_state(self, project_id: str) -> Optional[AgentState]:
        try:
            doc = await self._agent_state.read_item(project_id, partition_key=project_id)
            return _doc_to_agent_state(doc)
        except Exception:
            logger.exception("Failed to load_state %s", project_id)
            return None

    # ── State checkpoints ─────────────────────────────────────────────

    async def save_checkpoint(self, project_id: str, step_name: str, state: AgentState) -> str:
        """Save a state snapshot before an agent runs. Returns checkpoint ID."""
        checkpoint_id = f"{project_id}_{step_name}_{int(time.time())}"
        state_dict = _agent_state_to_doc(project_id, state)
        # Remove Cosmos-level keys that belong to the outer envelope
        state_dict.pop("id", None)
        state_dict.pop("projectId", None)
        item = {
            "id": checkpoint_id,
            "projectId": project_id,
            "stepName": step_name,
            "state": state_dict,
            "timestamp": datetime.utcnow().isoformat(),
            "type": "checkpoint",
        }
        await self._agent_state.upsert_item(item)
        return checkpoint_id

    async def list_checkpoints(self, project_id: str) -> list[dict]:
        """List all checkpoints for a project, newest first."""
        query = (
            "SELECT c.id, c.stepName, c.timestamp FROM c "
            "WHERE c.projectId = @pid AND c.type = 'checkpoint' "
            "ORDER BY c.timestamp DESC"
        )
        items: list[dict] = []
        async for item in self._agent_state.query_items(
            query, parameters=[{"name": "@pid", "value": project_id}],
            partition_key=project_id,
        ):
            items.append(item)
        return items

    async def restore_checkpoint(self, project_id: str, checkpoint_id: str) -> Optional[AgentState]:
        """Restore state from a checkpoint."""
        try:
            item = await self._agent_state.read_item(checkpoint_id, partition_key=project_id)
            return _doc_to_agent_state(item["state"])
        except Exception:
            logger.exception("Failed to restore_checkpoint %s/%s", project_id, checkpoint_id)
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
