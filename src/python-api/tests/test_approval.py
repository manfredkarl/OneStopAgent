"""Tests for ApprovalMixin.should_pause — no Azure credentials required.

We use sys.modules stubs to satisfy the LLM import before importing
approval.py, so the tests run without any Azure dependency.
"""

import sys
import os
from unittest.mock import MagicMock

# ── Stub out Azure-dependent modules before importing approval ─────────────
# This must happen before the first 'from approval import ...' call.
sys.modules.setdefault("langchain_openai", MagicMock())
sys.modules.setdefault("agents.llm", MagicMock(llm=MagicMock()))

# Also stub pm_agent / llm imports inside approval's dependency chain
_fake_intent = type("Intent", (), {
    "PROCEED": "proceed", "SKIP": "skip", "REFINE": "refine",
    "QUESTION": "question", "INPUT": "input", "FAST_RUN": "fast_run",
    "ITERATION": "iteration", "BRAINSTORM": "brainstorm",
})
_fake_pm_agent = MagicMock(AGENT_INFO={}, Intent=_fake_intent)
sys.modules.setdefault("agents.pm_agent", _fake_pm_agent)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from approval import ApprovalMixin  # noqa: E402 (must come after stubs)


class _StubState:
    """Minimal AgentState stand-in for should_pause tests."""

    def __init__(self, execution_mode: str = "guided"):
        self.execution_mode = execution_mode


class _StubOrchestrator(ApprovalMixin):
    """Minimal stub that inherits the real ApprovalMixin."""

    FAST_RUN_GATES = {"business_value", "architect", "presentation"}


orch = _StubOrchestrator()


class TestShouldPause:
    # ── Guided mode ────────────────────────────────────────────────────────

    def test_guided_mode_pauses_after_every_step(self):
        state = _StubState(execution_mode="guided")
        for step in ("architect", "cost", "roi", "business_value", "presentation"):
            assert orch.should_pause(state, step) is True

    # ── Fast-run mode ──────────────────────────────────────────────────────

    def test_fast_run_pauses_at_architect(self):
        state = _StubState(execution_mode="fast-run")
        assert orch.should_pause(state, "architect") is True

    def test_fast_run_pauses_at_business_value(self):
        state = _StubState(execution_mode="fast-run")
        assert orch.should_pause(state, "business_value") is True

    def test_fast_run_pauses_at_presentation(self):
        state = _StubState(execution_mode="fast-run")
        assert orch.should_pause(state, "presentation") is True

    def test_fast_run_does_not_pause_at_cost(self):
        state = _StubState(execution_mode="fast-run")
        assert orch.should_pause(state, "cost") is False

    def test_fast_run_does_not_pause_at_roi(self):
        state = _StubState(execution_mode="fast-run")
        assert orch.should_pause(state, "roi") is False
