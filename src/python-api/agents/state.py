"""Shared state object passed between agents."""
from __future__ import annotations
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Keyword maps for classifying LLM-generated assumption keys ────────
# Each tuple: (typed_field_name, keywords_that_must_appear)
# A raw key matches a field when ALL keywords in the tuple appear in
# the lowercased key.  Checked in order — first match wins per field.
_FIELD_MATCHERS: list[tuple[str, list[list[str]]]] = [
    ("current_annual_spend", [
        ["spend"],
        ["cost", "annual"],
        ["cost", "current"],
        ["budget"],
    ]),
    ("hourly_labor_rate", [
        ["labor", "rate"],
        ["hourly", "rate"],
        ["loaded", "rate"],
    ]),
    ("total_users", [
        ["total", "user"],
        ["user"],
        ["engineer"],
        ["employee"],
        ["headcount"],
    ]),
    ("concurrent_users", [
        ["concurrent"],
        ["peak", "user"],
        ["simultaneous"],
    ]),
    ("data_volume_gb", [
        ["data", "volume"],
        ["data", "storage"],
        ["data", "gb"],
    ]),
    ("timeline_months", [
        ["timeline"],
        ["implementation", "month"],
        ["duration"],
    ]),
    ("monthly_revenue", [
        ["revenue"],
        ["monthly", "income"],
    ]),
]


@dataclass(frozen=True)
class SharedAssumptions:
    """Typed, read-only view over the raw shared_assumptions dict.

    Centralizes all fuzzy key resolution in one place so every agent
    gets identical values.  Python 3.7+ guarantees dict insertion order,
    so ``from_dict()`` is deterministic for a given input.
    """

    current_annual_spend: float | None = None
    hourly_labor_rate: float | None = None
    total_users: float | None = None
    concurrent_users: float | None = None
    data_volume_gb: float | None = None
    timeline_months: float | None = None
    monthly_revenue: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SharedAssumptions:
        """Parse a raw shared_assumptions dict into typed fields.

        Resolution strategy per field:
        1. Iterate raw keys in insertion order.
        2. Skip metadata keys (starting with ``_``).
        3. For each key, check if it matches any unresolved field's
           keyword patterns.  First match wins — the field is locked.
        4. Values are cast to ``float``; non-numeric values are skipped.
        """
        if not raw:
            return cls()

        resolved: dict[str, float] = {}
        resolved_fields: set[str] = set()

        for sa_key, sa_val in raw.items():
            if sa_key.startswith("_"):
                continue

            # Try to parse the value as a number
            try:
                numeric = float(sa_val)
            except (ValueError, TypeError):
                logger.debug("SharedAssumptions: skipping non-numeric key %r", sa_key)
                continue

            if numeric <= 0:
                continue

            sk = sa_key.lower()

            for field_name, keyword_groups in _FIELD_MATCHERS:
                if field_name in resolved_fields:
                    continue
                for keywords in keyword_groups:
                    if all(kw in sk for kw in keywords):
                        resolved[field_name] = numeric
                        resolved_fields.add(field_name)
                        logger.debug(
                            "SharedAssumptions: %s = %s (from key %r, matched %s)",
                            field_name, numeric, sa_key, keywords,
                        )
                        break
                if field_name in resolved_fields:
                    break

        return cls(
            current_annual_spend=resolved.get("current_annual_spend"),
            hourly_labor_rate=resolved.get("hourly_labor_rate"),
            total_users=resolved.get("total_users"),
            concurrent_users=resolved.get("concurrent_users"),
            data_volume_gb=resolved.get("data_volume_gb"),
            timeline_months=resolved.get("timeline_months"),
            monthly_revenue=resolved.get("monthly_revenue"),
            raw=dict(raw),
        )


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

    # ── Shared assumptions (locked before pipeline runs) ────────
    shared_assumptions: dict[str, Any] = field(default_factory=dict)

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

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._sa_cache: SharedAssumptions | None = None

    @property
    def sa(self) -> SharedAssumptions:
        """Typed view of shared_assumptions — cached per state instance.

        The cache is invalidated when ``shared_assumptions`` is reassigned
        (which happens once, in the orchestrator).  After that point the
        dict is effectively immutable for the lifetime of a pipeline run.
        """
        if self._sa_cache is None:
            self._sa_cache = SharedAssumptions.from_dict(self.shared_assumptions)
        return self._sa_cache

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        # Invalidate cached SharedAssumptions when raw dict is replaced
        if name == "shared_assumptions":
            try:
                super().__setattr__("_sa_cache", None)
            except AttributeError:
                pass  # during __init__, _sa_cache doesn't exist yet

    def __getstate__(self) -> dict:
        """Exclude non-picklable lock and transient cache from serialization."""
        state = self.__dict__.copy()
        state.pop("_lock", None)
        state.pop("_sa_cache", None)
        return state

    def __setstate__(self, state: dict) -> None:
        """Restore lock and clear cache after deserialization."""
        self.__dict__.update(state)
        self._lock = threading.Lock()
        self._sa_cache = None

    def to_context_string(self) -> str:
        """Build a context string for LLM prompts with everything known so far."""
        parts = [f"User request: {self.user_input}"]
        if self.clarifications:
            parts.append(f"Clarifications: {self.clarifications}")
        if self.shared_assumptions:
            parts.append("Shared scenario assumptions:")
            for key, val in self.shared_assumptions.items():
                parts.append(f"  {key}: {val}")
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
        with self._lock:
            self.current_step = step
            self.awaiting_approval = False

    def mark_step_completed(self, step: str) -> None:
        with self._lock:
            if step not in self.completed_steps:
                self.completed_steps.append(step)
            self.current_step = ""

    def mark_step_skipped(self, step: str) -> None:
        with self._lock:
            if step not in self.skipped_steps:
                self.skipped_steps.append(step)
            self.current_step = ""

    def mark_step_failed(self, step: str) -> None:
        with self._lock:
            if step not in self.failed_steps:
                self.failed_steps.append(step)
            self.current_step = ""

    def next_pending_step(self) -> str | None:
        """Return the next step that hasn't been completed, skipped, or failed."""
        with self._lock:
            done = set(self.completed_steps + self.skipped_steps + self.failed_steps)
            for step in self.plan_steps:
                if step not in done:
                    return step
            return None
