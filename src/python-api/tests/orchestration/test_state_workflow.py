"""Tests for AgentState (agents/state.py) and workflow logic (workflow.py)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from agents.state import AgentState, SharedAssumptions
from orchestration.workflow import _should_pause, REQUIRED_STEPS, FAST_RUN_GATES


# ═══════════════════════════════════════════════════════════════════════════
# AgentState — step tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentStateStepTracking:
    """Verify mark_step_* helpers and next_pending_step."""

    @pytest.fixture(autouse=True)
    def _state(self):
        self.state = AgentState(
            user_input="test input",
            plan_steps=["business_value", "architect", "cost", "roi", "presentation"],
        )

    def test_mark_step_running(self):
        self.state.awaiting_approval = True
        self.state.mark_step_running("business_value")
        assert self.state.current_step == "business_value"
        assert self.state.awaiting_approval is False

    def test_mark_step_completed(self):
        self.state.mark_step_running("architect")
        self.state.mark_step_completed("architect")
        assert "architect" in self.state.completed_steps
        assert self.state.current_step == ""

    def test_mark_step_completed_idempotent(self):
        self.state.mark_step_completed("architect")
        self.state.mark_step_completed("architect")
        assert self.state.completed_steps.count("architect") == 1

    def test_mark_step_skipped(self):
        self.state.mark_step_skipped("cost")
        assert "cost" in self.state.skipped_steps

    def test_mark_step_failed(self):
        self.state.mark_step_failed("roi")
        assert "roi" in self.state.failed_steps

    def test_next_pending_step(self):
        self.state.mark_step_completed("business_value")
        assert self.state.next_pending_step() == "architect"

    def test_next_pending_step_all_done(self):
        for step in self.state.plan_steps:
            self.state.mark_step_completed(step)
        assert self.state.next_pending_step() is None


# ═══════════════════════════════════════════════════════════════════════════
# SharedAssumptions.from_dict
# ═══════════════════════════════════════════════════════════════════════════


class TestSharedAssumptions:
    """Verify fuzzy-key parsing of SharedAssumptions.from_dict()."""

    def test_from_dict_full(self):
        # total_users must precede concurrent_users so the fuzzy matcher
        # doesn't consume "concurrent_users" under the ["user"] keyword
        # belonging to total_users.
        raw = {
            "affected_employees": 500,
            "hourly_labor_rate": 85,
            "current_annual_spend": 250000,
            "total_users": 2000,
            "concurrent_users": 100,
            "data_volume_gb": 50,
            "timeline_months": 6,
            "monthly_revenue": 5000000,
        }
        sa = SharedAssumptions.from_dict(raw)
        assert sa.affected_employees == 500.0
        assert sa.hourly_labor_rate == 85.0
        assert sa.current_annual_spend == 250000.0
        assert sa.concurrent_users == 100.0
        assert sa.total_users == 2000.0
        assert sa.data_volume_gb == 50.0
        assert sa.timeline_months == 6.0
        assert sa.monthly_revenue == 5000000.0

    def test_from_dict_empty(self):
        sa = SharedAssumptions.from_dict({})
        assert sa.affected_employees is None
        assert sa.hourly_labor_rate is None

    def test_from_dict_none(self):
        sa = SharedAssumptions.from_dict(None)
        assert sa.affected_employees is None

    def test_from_dict_partial(self):
        sa = SharedAssumptions.from_dict({"affected_employees": 300})
        assert sa.affected_employees == 300.0
        assert sa.hourly_labor_rate is None

    def test_from_dict_string_values(self):
        sa = SharedAssumptions.from_dict({"affected_employees": "500"})
        assert sa.affected_employees == 500.0

    def test_from_dict_zero_ignored(self):
        sa = SharedAssumptions.from_dict({"affected_employees": 0})
        assert sa.affected_employees is None

    def test_from_dict_negative_ignored(self):
        sa = SharedAssumptions.from_dict({"hourly_labor_rate": -10})
        assert sa.hourly_labor_rate is None

    def test_keyword_matching(self):
        # "total users" should match total_users
        sa = SharedAssumptions.from_dict({"total users": 1500})
        assert sa.total_users == 1500.0

        # "Total Users" (case-insensitive)
        sa2 = SharedAssumptions.from_dict({"Total Users": 1500})
        assert sa2.total_users == 1500.0

        # "users_total" — not a match because the keyword pattern is ["total", "user"]
        # and "users_total" contains both "total" and "user" (substring of "users")
        sa3 = SharedAssumptions.from_dict({"users_total": 1500})
        assert sa3.total_users == 1500.0

    def test_timeline_months(self):
        sa = SharedAssumptions.from_dict({"timeline_months": 6})
        assert sa.timeline_months == 6.0

    def test_monthly_revenue(self):
        sa = SharedAssumptions.from_dict({"monthly_revenue": 5000000})
        assert sa.monthly_revenue == 5000000.0


# ═══════════════════════════════════════════════════════════════════════════
# AgentState.to_context_string
# ═══════════════════════════════════════════════════════════════════════════


class TestToContextString:
    """Verify the LLM context string builder."""

    def test_includes_user_input(self):
        state = AgentState(user_input="Build an AI app")
        ctx = state.to_context_string()
        assert "Build an AI app" in ctx

    def test_includes_architecture(self):
        state = AgentState(user_input="x")
        state.architecture = {"narrative": "A scalable microservices design"}
        ctx = state.to_context_string()
        assert "A scalable microservices design" in ctx

    def test_includes_bv_drivers(self):
        state = AgentState(user_input="x")
        state.business_value = {"drivers": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}
        ctx = state.to_context_string()
        assert "Value drivers: 3 identified" in ctx

    def test_includes_costs(self):
        state = AgentState(user_input="x")
        state.costs = {"estimate": {"totalMonthly": 8500.0}}
        ctx = state.to_context_string()
        assert "Cost: $8,500.00/month" in ctx

    def test_includes_roi(self):
        state = AgentState(user_input="x")
        state.roi = {"roi_percent": 250}
        ctx = state.to_context_string()
        assert "ROI: 250%" in ctx

    def test_empty_state(self):
        state = AgentState(user_input="Just a question")
        ctx = state.to_context_string()
        assert ctx == "User request: Just a question"

    def test_includes_shared_assumptions(self):
        state = AgentState(user_input="x")
        state.shared_assumptions = {"affected_employees": 500, "hourly_labor_rate": 85}
        ctx = state.to_context_string()
        assert "affected_employees: 500" in ctx
        assert "hourly_labor_rate: 85" in ctx


# ═══════════════════════════════════════════════════════════════════════════
# AgentState.sa property
# ═══════════════════════════════════════════════════════════════════════════


class TestSaProperty:
    """Verify the typed .sa accessor and its cache."""

    def test_sa_property_returns_typed(self):
        state = AgentState(user_input="x")
        state.shared_assumptions = {"affected_employees": 500}
        assert isinstance(state.sa, SharedAssumptions)

    def test_sa_property_cached(self):
        state = AgentState(user_input="x")
        state.shared_assumptions = {"affected_employees": 500}
        first = state.sa
        second = state.sa
        assert first is second

    def test_sa_fields_accessible(self):
        state = AgentState(user_input="x")
        state.shared_assumptions = {"affected_employees": 750}
        assert state.sa.affected_employees == 750.0


# ═══════════════════════════════════════════════════════════════════════════
# Workflow — _should_pause
# ═══════════════════════════════════════════════════════════════════════════


class TestShouldPause:
    """Verify approval-gate logic for guided and fast-run modes."""

    def test_guided_mode_always_pauses(self):
        assert _should_pause("guided", "business_value") is True

    def test_guided_mode_pauses_for_cost(self):
        assert _should_pause("guided", "cost") is True

    def test_fast_run_pauses_at_gates(self):
        assert _should_pause("fast-run", "business_value") is True

    def test_fast_run_skips_cost(self):
        assert _should_pause("fast-run", "cost") is False

    def test_fast_run_pauses_architect(self):
        assert _should_pause("fast-run", "architect") is True

    def test_fast_run_pauses_presentation(self):
        assert _should_pause("fast-run", "presentation") is True


# ═══════════════════════════════════════════════════════════════════════════
# Workflow — REQUIRED_STEPS
# ═══════════════════════════════════════════════════════════════════════════


class TestRequiredSteps:
    def test_architect_is_required(self):
        assert "architect" in REQUIRED_STEPS

    def test_cost_is_not_required(self):
        assert "cost" not in REQUIRED_STEPS

    def test_roi_is_not_required(self):
        assert "roi" not in REQUIRED_STEPS


# ═══════════════════════════════════════════════════════════════════════════
# Workflow — FAST_RUN_GATES
# ═══════════════════════════════════════════════════════════════════════════


class TestFastRunGates:
    def test_bv_is_gate(self):
        assert "business_value" in FAST_RUN_GATES

    def test_architect_is_gate(self):
        assert "architect" in FAST_RUN_GATES

    def test_presentation_is_gate(self):
        assert "presentation" in FAST_RUN_GATES

    def test_cost_is_not_gate(self):
        assert "cost" not in FAST_RUN_GATES

    def test_roi_is_not_gate(self):
        assert "roi" not in FAST_RUN_GATES
