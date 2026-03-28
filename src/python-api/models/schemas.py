from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    description: str
    customer_name: Optional[str] = None
    active_agents: list[str] = Field(
        default_factory=lambda: [
            "envisioning",
            "knowledge",
            "architect",
            "azure-specialist",
            "cost",
            "business-value",
            "roi",
            "presentation",
        ]
    )
    status: Literal["in_progress", "completed", "error"] = "in_progress"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    role: Literal["user", "agent"]
    agent_id: Optional[str] = None
    content: str
    metadata: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CreateProjectRequest(BaseModel):
    description: str = Field(min_length=10, max_length=5000)
    customer_name: Optional[str] = Field(default=None, max_length=200)


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class PlanStep(BaseModel):
    tool: str
    agent_name: str
    emoji: str
    reason: str
    status: Literal["pending", "running", "done", "skipped"] = "pending"
