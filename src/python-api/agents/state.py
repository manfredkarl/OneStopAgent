"""Shared state object passed between agents."""
from typing import Any


class AgentState:
    def __init__(self):
        self.user_input: str = ""
        self.customer_name: str = ""
        self.clarifications: str = ""
        self.plan: list[str] = []
        self.architecture: dict[str, Any] = {}
        self.services: dict[str, Any] = {}
        self.costs: dict[str, Any] = {}
        self.business_value: dict[str, Any] = {}
        self.presentation_path: str = ""
        self.envisioning: dict[str, Any] = {}

    def to_context_string(self) -> str:
        """Build a context string for LLM prompts with everything known so far."""
        parts = [f"User request: {self.user_input}"]
        if self.clarifications:
            parts.append(f"Clarifications: {self.clarifications}")
        if self.architecture:
            parts.append(f"Architecture: {self.architecture.get('narrative', '')}")
            parts.append(f"Components: {self.architecture.get('components', [])}")
        if self.services:
            parts.append(f"Services: {self.services.get('selections', [])}")
        if self.costs:
            est = self.costs.get("estimate", {})
            parts.append(f"Cost: ${est.get('totalMonthly', 0)}/month")
        return "\n".join(parts)
