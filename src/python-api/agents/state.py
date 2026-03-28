"""Shared state object passed between agents."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """Central state object that flows through the agent pipeline.

    Every agent reads from and writes to this object. Fields are grouped
    by concern — see refactor.md §12 for the full specification.
    """

    # ── Core inputs ──────────────────────────────────────────────────
    user_input: str = ""
    customer_name: str = ""
    clarifications: str = ""

    # ── Mode tracking ────────────────────────────────────────────────
    mode: str = "brainstorm"          # "brainstorm" or "solution"
    execution_mode: str = "guided"    # "guided" or "fast-run"
    azure_fit: str = ""               # "strong", "weak", "unclear"
    azure_fit_explanation: str = ""   # WHY Azure is a fit

    # ── Knowledge ────────────────────────────────────────────────────
    retrieved_patterns: list[dict[str, Any]] = field(default_factory=list)

    # ── Agent outputs ────────────────────────────────────────────────
    brainstorming: dict[str, Any] = field(default_factory=dict)
    architecture: dict[str, Any] = field(default_factory=dict)
    services: dict[str, Any] = field(default_factory=dict)
    costs: dict[str, Any] = field(default_factory=dict)
    business_value: dict[str, Any] = field(default_factory=dict)
    roi: dict[str, Any] = field(default_factory=dict)
    presentation_path: str = ""

    # ── Plan tracking ────────────────────────────────────────────────
    plan_steps: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    skipped_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    awaiting_approval: bool = False
    current_step: str = ""

    # ── Helpers ───────────────────────────────────────────────────────

    def to_context_string(self) -> str:
        """Build a context string for LLM prompts with everything known so far."""
        parts = [f"User request: {self.user_input}"]
        if self.clarifications:
            parts.append(f"Clarifications: {self.clarifications}")
        if self.azure_fit:
            parts.append(f"Azure fit: {self.azure_fit} — {self.azure_fit_explanation}")
        if self.retrieved_patterns:
            titles = [p.get("title", "") for p in self.retrieved_patterns[:5]]
            parts.append(f"Reference patterns: {', '.join(titles)}")
        if self.architecture:
            parts.append(f"Architecture: {self.architecture.get('narrative', '')}")
            parts.append(f"Components: {self.architecture.get('components', [])}")
        if self.services:
            sels = self.services.get("selections", [])
            parts.append(f"Services: {len(sels)} mapped")
        if self.costs:
            est = self.costs.get("estimate", {})
            parts.append(f"Cost: ${est.get('totalMonthly', 0):,.2f}/month")
        if self.business_value:
            drivers = self.business_value.get("drivers", [])
            parts.append(f"Value drivers: {len(drivers)} identified")
        if self.roi:
            roi_pct = self.roi.get("roi_percent")
            if roi_pct is not None:
                parts.append(f"ROI: {roi_pct:.0f}%")
        return "\n".join(parts)

    def mark_step_running(self, step: str) -> None:
        self.current_step = step
        self.awaiting_approval = False

    def mark_step_completed(self, step: str) -> None:
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        self.current_step = ""

    def mark_step_skipped(self, step: str) -> None:
        if step not in self.skipped_steps:
            self.skipped_steps.append(step)
        self.current_step = ""

    def mark_step_failed(self, step: str) -> None:
        if step not in self.failed_steps:
            self.failed_steps.append(step)
        self.current_step = ""

    def next_pending_step(self) -> str | None:
        """Return the next step that hasn't been completed, skipped, or failed."""
        done = set(self.completed_steps + self.skipped_steps + self.failed_steps)
        for step in self.plan_steps:
            if step not in done:
                return step
        return None
