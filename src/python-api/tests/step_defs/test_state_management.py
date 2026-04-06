"""Step definitions for state_management.feature — AgentState tracking and workflow gates."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from agents.state import AgentState, SharedAssumptions
from orchestration.workflow import _should_pause

scenarios("../features/state_management.feature")


# ── Shared context ───────────────────────────────────────────────────────


@pytest.fixture
def ctx():
    """Mutable dict shared across Given/When/Then for a single scenario."""
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Step lifecycle tracking
# ═══════════════════════════════════════════════════════════════════════════


@given("a fresh agent state with plan steps")
def fresh_state(ctx):
    ctx["state"] = AgentState(
        user_input="test",
        plan_steps=["business_value", "architect", "cost", "roi", "presentation"],
    )


@when("business_value is marked as running")
def mark_bv_running(ctx):
    ctx["state"].mark_step_running("business_value")


@then('current_step should be "business_value"')
def current_step_is_bv(ctx):
    assert ctx["state"].current_step == "business_value"


@when("business_value is marked as completed")
def mark_bv_completed(ctx):
    ctx["state"].mark_step_completed("business_value")


@then('"business_value" should be in completed_steps')
def bv_in_completed(ctx):
    assert "business_value" in ctx["state"].completed_steps


@then("current_step should be empty")
def current_step_empty(ctx):
    assert ctx["state"].current_step == ""


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Shared assumptions parsing
# ═══════════════════════════════════════════════════════════════════════════


@given(
    parsers.parse(
        "shared assumptions with affected_employees {employees:d} and hourly_labor_rate {rate:d}"
    )
)
def shared_assumptions_raw(ctx, employees, rate):
    ctx["raw"] = {"affected_employees": employees, "hourly_labor_rate": rate}


@when("the typed accessor is used")
def typed_accessor(ctx):
    ctx["sa"] = SharedAssumptions.from_dict(ctx["raw"])


@then(parsers.parse("affected_employees should be {expected:d}"))
def check_employees(ctx, expected):
    assert ctx["sa"].affected_employees == float(expected)


@then(parsers.parse("hourly_labor_rate should be {expected:d}"))
def check_rate(ctx, expected):
    assert ctx["sa"].hourly_labor_rate == float(expected)


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Context string includes completed agent data
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse("a state with completed BV showing {n:d} value drivers"))
def state_with_drivers(ctx, n):
    state = AgentState(user_input="test")
    state.business_value = {"drivers": [{"name": f"d{i}"} for i in range(n)]}
    ctx["state"] = state


@when("to_context_string is called")
def call_context_string(ctx):
    ctx["context_result"] = ctx["state"].to_context_string()


@then(parsers.parse('the result should contain "{text}"'))
def result_contains(ctx, text):
    assert text in ctx["context_result"]


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Workflow pauses in guided mode / Fast-run mode
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse('the execution mode is "{mode}"'))
def set_execution_mode(ctx, mode):
    ctx["mode"] = mode


@when(parsers.parse("checking if {step} should pause"))
def check_should_pause(ctx, step):
    ctx["pause_result"] = _should_pause(ctx["mode"], step)


@then("the result should be true")
def result_is_true(ctx):
    assert ctx["pause_result"] is True


@then("the result should be false")
def result_is_false(ctx):
    assert ctx["pause_result"] is False
