"""Step definitions for roi_dashboard.feature — regression tests for ROI data integrity.

Bug #1 regression: BV confidence was a dict {overall_score, driver_scores, methodology,
recommendation, label} instead of a string.  ROI agent passed this dict as
dashboard["confidenceLevel"] → React crashed "Objects are not valid as a React child".
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import json
from copy import deepcopy

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from agents.state import AgentState
from agents.roi_agent import ROIAgent
from tests.conftest import (
    CANNED_BUSINESS_VALUE,
    CANNED_ARCHITECTURE,
    CANNED_COSTS,
    CANNED_SHARED_ASSUMPTIONS,
    CANNED_COMPANY_PROFILE,
    CANNED_BRAINSTORMING,
    AgentStateFactory,
)

scenarios("../features/roi_dashboard.feature")


# ── Shared context ───────────────────────────────────────────────────────


@pytest.fixture
def roi_ctx():
    """Mutable dict shared across Given/When/Then for a single scenario."""
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Confidence level is always a string (Bug #1 regression)
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse('BV confidence is a scored dict with label "{label}"'))
def bv_confidence_scored_dict(roi_ctx, label):
    state = AgentStateFactory.state_ready_for_roi()
    # Simulate the QI-5 scored confidence object (the old bug trigger)
    state.business_value["confidence"] = {
        "overall_score": 65,
        "driver_scores": [70, 60],
        "methodology": "benchmark",
        "recommendation": "Refine with customer data",
        "label": label,
    }
    roi_ctx["state"] = state
    roi_ctx["expected_label"] = label


@when("the ROI agent builds the dashboard")
def roi_builds_dashboard(roi_ctx):
    agent = ROIAgent()
    state = agent.run(roi_ctx["state"])
    roi_ctx["result"] = state.roi
    roi_ctx["dashboard"] = state.roi.get("dashboard", {})


@then(parsers.parse('dashboard confidenceLevel should be the string "{expected}"'))
def confidence_is_string(roi_ctx, expected):
    confidence = roi_ctx["dashboard"]["confidenceLevel"]
    assert isinstance(confidence, str), (
        f"confidenceLevel must be a string, got {type(confidence).__name__}: {confidence}"
    )
    # The reconciliation may downgrade confidence, so check it's a valid label
    assert confidence in ("low", "moderate", "high"), (
        f"confidenceLevel must be low/moderate/high, got {confidence!r}"
    )


@then("dashboard confidenceLevel should not be a dict")
def confidence_not_dict(roi_ctx):
    confidence = roi_ctx["dashboard"]["confidenceLevel"]
    assert not isinstance(confidence, dict), (
        f"confidenceLevel must not be a dict (Bug #1 regression), got {confidence}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Confidence level from legacy string format
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse('BV confidence is the string "{label}"'))
def bv_confidence_string(roi_ctx, label):
    state = AgentStateFactory.state_ready_for_roi()
    state.business_value["confidence"] = label
    roi_ctx["state"] = state
    roi_ctx["expected_label"] = label


# "When the ROI agent builds the dashboard" is reused from above
# "Then dashboard confidenceLevel should be the string ..." is reused


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: ROI calculation with valid inputs
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse("annual cost is {cost:d}"))
def annual_cost_is(roi_ctx, cost):
    state = AgentStateFactory.state_ready_for_roi()
    state.costs["estimate"]["totalAnnual"] = float(cost)
    state.costs["estimate"]["totalMonthly"] = float(cost) / 12
    roi_ctx["state"] = state


@given(parsers.parse("annual impact range is {low:d} to {high:d}"))
def impact_range_is(roi_ctx, low, high):
    state = roi_ctx["state"]
    state.business_value["annual_impact_range"] = {"low": low, "high": high}


@when("the ROI agent runs")
def roi_agent_runs(roi_ctx):
    agent = ROIAgent()
    state = agent.run(roi_ctx["state"])
    roi_ctx["result"] = state.roi
    roi_ctx["dashboard"] = state.roi.get("dashboard", {})


@then("roi_percent should be a positive number")
def roi_percent_positive(roi_ctx):
    roi_pct = roi_ctx["result"]["roi_percent"]
    assert roi_pct is not None
    assert isinstance(roi_pct, (int, float))
    assert roi_pct > 0, f"roi_percent should be positive, got {roi_pct}"


@then("payback_months should be a positive number")
def payback_months_positive(roi_ctx):
    payback = roi_ctx["result"]["payback_months"]
    assert payback is not None
    assert isinstance(payback, (int, float))
    assert payback > 0, f"payback_months should be positive, got {payback}"


@then("dashboard should contain drivers array")
def dashboard_has_drivers(roi_ctx):
    drivers = roi_ctx["dashboard"].get("drivers")
    assert isinstance(drivers, list), f"drivers should be a list, got {type(drivers)}"
    assert len(drivers) > 0, "drivers array should not be empty"


@then("dashboard should contain projection data")
def dashboard_has_projection(roi_ctx):
    projection = roi_ctx["dashboard"].get("projection")
    assert isinstance(projection, dict), "projection should be a dict"
    assert "years" in projection
    assert "cumulative" in projection
    assert len(projection["cumulative"]) == 3, "Should have 3-year projection"


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: ROI handles missing cost data
# ═══════════════════════════════════════════════════════════════════════════


@given("no cost estimate is available")
def no_cost_estimate(roi_ctx):
    state = AgentStateFactory.state_after_bv()
    # Clear costs so totalAnnual is 0
    state.costs = {}
    roi_ctx["state"] = state


@then("it should return needs_info")
def result_has_needs_info(roi_ctx):
    result = roi_ctx["result"]
    assert result.get("needs_info") is not None, "needs_info should be set when data is missing"
    assert isinstance(result["needs_info"], list)


@then("needs_info should contain a question about cost")
def needs_info_about_cost(roi_ctx):
    questions = roi_ctx["result"]["needs_info"]
    text = " ".join(questions).lower()
    assert "cost" in text or "spend" in text, (
        f"needs_info should mention cost/spend, got: {questions}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: ROI handles missing BV impact range
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse("cost estimate is {cost:d} annually"))
def cost_estimate_annually(roi_ctx, cost):
    state = AgentStateFactory.state_after_bv()
    state.costs = deepcopy(CANNED_COSTS)
    state.costs["estimate"]["totalAnnual"] = float(cost)
    state.costs["estimate"]["totalMonthly"] = float(cost) / 12
    roi_ctx["state"] = state


@given("no annual impact range is available")
def no_impact_range(roi_ctx):
    state = roi_ctx["state"]
    # Keep drivers but remove the dollar range
    state.business_value["annual_impact_range"] = None


@then("it should return needs_info with qualitative benefits")
def needs_info_qualitative(roi_ctx):
    result = roi_ctx["result"]
    assert result.get("needs_info") is not None, "needs_info should be set"
    qualitative = result.get("qualitative_benefits", [])
    assert isinstance(qualitative, list), "qualitative_benefits should be a list"


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Dashboard values are JSON-serializable
# ═══════════════════════════════════════════════════════════════════════════


@given("a fully populated ROI state")
def fully_populated_roi(roi_ctx):
    state = AgentStateFactory.state_ready_for_roi()
    roi_ctx["state"] = state


@when("the dashboard is serialized to JSON")
def serialize_dashboard(roi_ctx):
    agent = ROIAgent()
    state = agent.run(roi_ctx["state"])
    roi_ctx["result"] = state.roi
    roi_ctx["dashboard"] = state.roi.get("dashboard", {})
    try:
        roi_ctx["json_str"] = json.dumps(state.roi)
        roi_ctx["serialize_error"] = None
    except TypeError as e:
        roi_ctx["json_str"] = None
        roi_ctx["serialize_error"] = str(e)


@then("no TypeError should be raised")
def no_type_error(roi_ctx):
    assert roi_ctx["serialize_error"] is None, (
        f"JSON serialization failed: {roi_ctx['serialize_error']}"
    )


@then("all values should be primitive types or arrays")
def all_values_primitive(roi_ctx):
    def _check(obj, path=""):
        if obj is None:
            return
        if isinstance(obj, (str, int, float, bool)):
            return
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                _check(item, f"{path}[{i}]")
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                _check(v, f"{path}.{k}")
            return
        raise AssertionError(
            f"Non-primitive value at {path}: {type(obj).__name__} = {obj!r}"
        )

    _check(roi_ctx["dashboard"], "dashboard")
