"""In-memory project and chat storage (async interface)."""

import threading
from models.schemas import Project, ChatMessage
from typing import Optional


class ProjectStore:
    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}
        self.chat_histories: dict[str, list[ChatMessage]] = {}
        self._lock = threading.Lock()

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
        with self._lock:
            self.projects[project.id] = project
            self.chat_histories[project.id] = []
        return project

    async def get_project(self, project_id: str, user_id: str) -> Optional[Project]:
        with self._lock:
            project = self.projects.get(project_id)
        if project and project.user_id == user_id:
            return project
        return None

    async def update_project(self, project: Project) -> None:
        with self._lock:
            self.projects[project.id] = project

    async def list_projects(self, user_id: str) -> list[Project]:
        with self._lock:
            return [p for p in self.projects.values() if p.user_id == user_id]

    async def add_message(self, project_id: str, message: ChatMessage) -> None:
        with self._lock:
            self.chat_histories.setdefault(project_id, []).append(message)

    async def get_messages(self, project_id: str) -> list[ChatMessage]:
        with self._lock:
            return self.chat_histories.get(project_id, [])

    async def delete_project(self, project_id: str, user_id: str) -> bool:
        """Delete a project and its chat history. Returns True if deleted."""
        with self._lock:
            project = self.projects.get(project_id)
            if not project or project.user_id != user_id:
                return False
            del self.projects[project_id]
            self.chat_histories.pop(project_id, None)
            return True

    async def save_state(self, project_id: str, state, phase: str = "done") -> None:
        """No-op for in-memory store — state is already in memory."""
        pass

    async def load_state(self, project_id: str):
        """In-memory store doesn't persist state separately."""
        return None

    async def save_checkpoint(self, project_id: str, step_name: str, state) -> str:
        """No-op for in-memory store — returns a synthetic checkpoint ID."""
        return f"{project_id}_{step_name}_inmemory"

    async def list_checkpoints(self, project_id: str) -> list:
        """In-memory store has no persisted checkpoints."""
        return []

    async def restore_checkpoint(self, project_id: str, checkpoint_id: str):
        """In-memory store cannot restore checkpoints."""
        return None

    async def clear(self) -> None:
        """Reset all data (for testing)."""
        with self._lock:
            self.projects.clear()
            self.chat_histories.clear()


store = ProjectStore()
