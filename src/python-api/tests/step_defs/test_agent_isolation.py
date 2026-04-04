"""Step definitions for agent_isolation.feature — verifies BV data doesn't bleed into architect.

Bug #2 regression: state.to_context_string() included BV driver info, fed to architect
LLM prompt.  Architect echoed BV summary in its output.  Now the architect builds context
inline (lines 30-41 of architect_agent.py) excluding BV/cost/ROI data.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from copy import deepcopy

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from agents.state import AgentState
from tests.conftest import (
    CANNED_BUSINESS_VALUE,
    CANNED_BRAINSTORMING,
    CANNED_ARCHITECTURE,
    CANNED_SHARED_ASSUMPTIONS,
    CANNED_COMPANY_PROFILE,
    AgentStateFactory,
)

scenarios("../features/agent_isolation.feature")


# ── Shared context ───────────────────────────────────────────────────────


@pytest.fixture
def iso_ctx():
    """Mutable dict shared across Given/When/Then for a single scenario."""
    return {}


def _build_architect_context(state: AgentState) -> str:
    """Replicate the architect's inline context builder (lines 30-41).

    This mirrors ArchitectAgent.run() context construction so we can test
    what data the architect would see without invoking the LLM.
    """
    context_parts = [f"Project: {state.user_input}"]
    if state.brainstorming:
        context_parts.append(
            f"Industry: {state.brainstorming.get('industry', 'Cross-Industry')}"
        )
    if state.shared_assumptions:
        sa_items = [
            f"  {k}: {v}"
            for k, v in state.shared_assumptions.items()
            if not k.startswith("_")
        ]
        if sa_items:
            context_parts.append("Shared assumptions:\n" + "\n".join(sa_items))
    if state.retrieved_patterns:
        titles = [p.get("title", "") for p in state.retrieved_patterns[:5]]
        context_parts.append(f"Reference patterns: {', '.join(titles)}")
    return "\n".join(context_parts)


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Architect context excludes BV data
# ═══════════════════════════════════════════════════════════════════════════


@given("a state with completed business value data")
def state_with_bv(iso_ctx):
    state = AgentStateFactory.state_after_bv()
    iso_ctx["state"] = state


@when("the architect builds its context string")
def architect_builds_context(iso_ctx):
    iso_ctx["context"] = _build_architect_context(iso_ctx["state"])


@then("the context should contain the user input")
def context_has_user_input(iso_ctx):
    state = iso_ctx["state"]
    assert state.user_input in iso_ctx["context"], (
        "Architect context should include the user input"
    )


@then("the context should contain shared assumptions")
def context_has_shared_assumptions(iso_ctx):
    assert "Shared assumptions" in iso_ctx["context"] or "assumptions" in iso_ctx["context"].lower(), (
        "Architect context should include shared assumptions"
    )


@then(parsers.parse('the context should not contain "{forbidden}"'))
def context_excludes(iso_ctx, forbidden):
    assert forbidden not in iso_ctx["context"], (
        f"Architect context must NOT contain '{forbidden}' (BV data leak). "
        f"Context: {iso_ctx['context'][:500]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Architect context includes relevant data only
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse("a state with brainstorming data for {industry} industry"))
def state_with_industry(iso_ctx, industry):
    state = AgentStateFactory.state_after_brainstorm()
    state.brainstorming["industry"] = industry
    state.shared_assumptions = deepcopy(CANNED_SHARED_ASSUMPTIONS)
    iso_ctx["state"] = state


@then(parsers.parse('the context should contain "{expected}"'))
def context_contains(iso_ctx, expected):
    assert expected in iso_ctx["context"], (
        f"Architect context should contain '{expected}'. "
        f"Context: {iso_ctx['context'][:500]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: State to_context_string includes BV for other agents
# ═══════════════════════════════════════════════════════════════════════════


# "Given a state with completed business value data" is reused from above


@when("to_context_string is called on the full state")
def full_context_string(iso_ctx):
    iso_ctx["full_context"] = iso_ctx["state"].to_context_string()


@then(parsers.parse('the result should contain "{expected}"'))
def full_context_contains(iso_ctx, expected):
    assert expected in iso_ctx["full_context"], (
        f"Full state context should contain '{expected}' for downstream agents. "
        f"Context: {iso_ctx['full_context'][:500]}"
    )
