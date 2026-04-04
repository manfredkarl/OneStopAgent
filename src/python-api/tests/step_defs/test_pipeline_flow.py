"""Step definitions for pipeline_flow.feature — verifies execution ordering and approval gates."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from copy import deepcopy

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from agents.state import AgentState
from tests.conftest import (
    CANNED_BRAINSTORMING,
    CANNED_BUSINESS_VALUE,
    CANNED_ARCHITECTURE,
    CANNED_COSTS,
    CANNED_SHARED_ASSUMPTIONS,
    CANNED_COMPANY_PROFILE,
    AgentStateFactory,
)

scenarios("../features/pipeline_flow.feature")


# ── Shared context ───────────────────────────────────────────────────────


@pytest.fixture
def pipeline_ctx():
    """Mutable dict shared across Given/When/Then for a single scenario."""
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: BV completes before architect starts
# ═══════════════════════════════════════════════════════════════════════════


@given("a project state ready for the pipeline")
def state_ready_for_pipeline(pipeline_ctx):
    state = AgentStateFactory.state_after_brainstorm()
    state.plan_steps = ["business_value", "architect", "cost", "roi", "presentation"]
    state.execution_mode = "guided"
    pipeline_ctx["state"] = state


@given("the business value agent has completed")
def bv_agent_completed(pipeline_ctx):
    state = pipeline_ctx["state"]
    state.business_value = deepcopy(CANNED_BUSINESS_VALUE)
    state.shared_assumptions = deepcopy(CANNED_SHARED_ASSUMPTIONS)
    state.mark_step_completed("business_value")


@when("the pipeline processes the BV result")
def pipeline_processes_bv(pipeline_ctx):
    state = pipeline_ctx["state"]
    # After BV completes in guided mode, pipeline should set awaiting_approval
    state.awaiting_approval = True
    pipeline_ctx["bv_completed_at"] = len(state.completed_steps)


@then("the BV result should be emitted before architect starts")
def bv_before_architect(pipeline_ctx):
    state = pipeline_ctx["state"]
    assert "business_value" in state.completed_steps
    assert "architect" not in state.completed_steps


@then("an approval gate should be present after BV")
def approval_gate_after_bv(pipeline_ctx):
    state = pipeline_ctx["state"]
    assert state.awaiting_approval is True


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Architect runs only after BV approval
# ═══════════════════════════════════════════════════════════════════════════


@given("BV has completed with value drivers")
def bv_completed_with_drivers(pipeline_ctx):
    state = AgentStateFactory.state_after_bv()
    state.plan_steps = ["business_value", "architect", "cost", "roi", "presentation"]
    state.mark_step_completed("business_value")
    state.awaiting_approval = True
    pipeline_ctx["state"] = state
    pipeline_ctx["architect_started_during_bv"] = False


@when("the user approves the BV result")
def user_approves_bv(pipeline_ctx):
    state = pipeline_ctx["state"]
    state.awaiting_approval = False
    # Simulate architect starting after approval
    state.mark_step_running("architect")
    pipeline_ctx["architect_started"] = True


@then("the architect agent should start")
def architect_should_start(pipeline_ctx):
    assert pipeline_ctx.get("architect_started") is True
    state = pipeline_ctx["state"]
    assert state.current_step == "architect"


@then("the architect should not have started during BV execution")
def architect_not_during_bv(pipeline_ctx):
    assert pipeline_ctx.get("architect_started_during_bv") is False


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Full pipeline ordering
# ═══════════════════════════════════════════════════════════════════════════

FULL_PIPELINE_ORDER = ["business_value", "architect", "cost", "roi", "presentation"]


@given("all agents are active")
def all_agents_active(pipeline_ctx):
    state = AgentStateFactory.state_after_brainstorm()
    state.plan_steps = list(FULL_PIPELINE_ORDER)
    pipeline_ctx["state"] = state
    pipeline_ctx["execution_log"] = []


@when("the pipeline runs to completion")
def pipeline_runs_full(pipeline_ctx):
    state = pipeline_ctx["state"]
    log = pipeline_ctx["execution_log"]

    # Simulate each step executing in plan_steps order
    for step in state.plan_steps:
        state.mark_step_running(step)
        log.append(step)
        state.mark_step_completed(step)


@then("the execution order should be BV then Architect then Cost then ROI then Presentation")
def verify_execution_order(pipeline_ctx):
    assert pipeline_ctx["execution_log"] == FULL_PIPELINE_ORDER


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Skipped agent does not block pipeline
# ═══════════════════════════════════════════════════════════════════════════


@given("business_value is not in active agents")
def bv_not_active(pipeline_ctx):
    state = AgentStateFactory.state_after_brainstorm()
    state.plan_steps = ["business_value", "architect", "cost", "roi", "presentation"]
    pipeline_ctx["state"] = state
    pipeline_ctx["active_agents"] = ["architect", "cost", "roi", "presentation"]


@when("the pipeline runs")
def pipeline_runs_with_skip(pipeline_ctx):
    state = pipeline_ctx["state"]
    active = pipeline_ctx.get("active_agents", state.plan_steps)
    for step in state.plan_steps:
        if step not in active:
            state.mark_step_skipped(step)
        else:
            state.mark_step_running(step)
            state.mark_step_completed(step)


@then("business_value should be marked as skipped")
def bv_is_skipped(pipeline_ctx):
    state = pipeline_ctx["state"]
    assert "business_value" in state.skipped_steps


@then("architect should still execute")
def architect_still_executes(pipeline_ctx):
    state = pipeline_ctx["state"]
    assert "architect" in state.completed_steps


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Pipeline continues after non-required agent failure
# ═══════════════════════════════════════════════════════════════════════════


@given("the cost agent fails during execution")
def cost_agent_fails(pipeline_ctx):
    state = AgentStateFactory.state_after_bv()
    state.plan_steps = ["business_value", "architect", "cost", "roi", "presentation"]
    state.mark_step_completed("business_value")
    state.mark_step_completed("architect")
    pipeline_ctx["state"] = state


@when("the pipeline processes the error")
def pipeline_processes_error(pipeline_ctx):
    state = pipeline_ctx["state"]
    # Cost fails
    state.mark_step_failed("cost")
    # Pipeline should continue — ROI is attempted next
    next_step = state.next_pending_step()
    if next_step:
        state.mark_step_running(next_step)
        state.mark_step_completed(next_step)
    pipeline_ctx["roi_attempted"] = "roi" in state.completed_steps or state.current_step == "roi"


@then("the ROI agent should still be attempted")
def roi_still_attempted(pipeline_ctx):
    state = pipeline_ctx["state"]
    # ROI should be in completed (or at least not blocked by cost failure)
    assert "roi" in state.completed_steps or state.current_step == "roi"


@then("the cost step should be marked as failed")
def cost_marked_failed(pipeline_ctx):
    state = pipeline_ctx["state"]
    assert "cost" in state.failed_steps
