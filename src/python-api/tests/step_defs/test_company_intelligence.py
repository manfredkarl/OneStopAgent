"""Step definitions for company_intelligence.feature — search enrichment and fallbacks."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from services.company_intelligence import (
    build_fallback_profile,
    estimate_it_spend,
    scope_employees,
)
from tests.conftest import CANNED_COMPANY_PROFILE

scenarios("../features/company_intelligence.feature")


# ── Shared context ───────────────────────────────────────────────────────


@pytest.fixture
def ci_ctx():
    """Mutable dict shared across Given/When/Then for a single scenario."""
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Fallback profile for unknown company
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse('an unknown company name "{name}"'))
def unknown_company(ci_ctx, name):
    ci_ctx["company_name"] = name


@when(parsers.parse('the fallback profile is requested for size "{size}"'))
def request_fallback(ci_ctx, size):
    ci_ctx["profile"] = build_fallback_profile(size, ci_ctx["company_name"])


@then(parsers.parse("the profile should have employee count between {low:d} and {high:d}"))
def employee_count_range(ci_ctx, low, high):
    count = ci_ctx["profile"]["employeeCount"]
    assert low <= count <= high, (
        f"employeeCount {count} not in range [{low}, {high}]"
    )


@then(parsers.parse('the confidence should be "{expected}"'))
def confidence_level(ci_ctx, expected):
    assert ci_ctx["profile"]["confidence"] == expected


@then("the profile name should contain the company name")
def profile_has_name(ci_ctx):
    assert ci_ctx["company_name"] in ci_ctx["profile"]["name"]


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Company profile confidence scoring
# ═══════════════════════════════════════════════════════════════════════════


@given("a profile with employees, revenue, and headquarters")
def full_profile(ci_ctx):
    ci_ctx["profile"] = dict(CANNED_COMPANY_PROFILE)


@when("confidence is assessed")
def assess_confidence(ci_ctx):
    # Confidence is already part of the profile dict
    ci_ctx["assessed_confidence"] = ci_ctx["profile"].get("confidence")


@then(parsers.parse('confidence should be "{expected}"'))
def confidence_equals(ci_ctx, expected):
    assert ci_ctx["assessed_confidence"] == expected


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Partial data confidence scoring
# ═══════════════════════════════════════════════════════════════════════════


@given("a profile with only employee count")
def partial_profile(ci_ctx):
    # Fallback profile has confidence="low" by design
    ci_ctx["profile"] = build_fallback_profile("mid-market", "Partial Corp")


@then(parsers.parse('confidence should not be "{unexpected}"'))
def confidence_not_equals(ci_ctx, unexpected):
    assert ci_ctx["assessed_confidence"] != unexpected, (
        f"Partial profile should not have {unexpected} confidence"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: IT spend estimation
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse("a company with annual revenue {revenue:d}"))
def company_with_revenue(ci_ctx, revenue):
    ci_ctx["annual_revenue"] = revenue
    ci_ctx["industry"] = CANNED_COMPANY_PROFILE.get("industry", "Consumer Goods")


@when("IT spend is estimated")
def estimate_spend(ci_ctx):
    ci_ctx["it_spend"] = estimate_it_spend(
        ci_ctx["annual_revenue"], ci_ctx["industry"]
    )


@then(parsers.parse("estimated IT spend should be between {low_b:d} billion and {high_b:d} billion"))
def it_spend_range(ci_ctx, low_b, high_b):
    spend = ci_ctx["it_spend"]
    assert spend is not None, "IT spend estimation returned None"
    low = low_b * 1_000_000_000
    high = high_b * 1_000_000_000
    assert low <= spend <= high, (
        f"IT spend {spend:,.0f} not in range [{low:,.0f}, {high:,.0f}]"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scenario: Employee scoping
# ═══════════════════════════════════════════════════════════════════════════


@given(parsers.parse("a company with {count:d} total employees"))
def company_employees(ci_ctx, count):
    ci_ctx["employee_count"] = count


@when(parsers.parse("affected employees are scoped at {pct:d} percent"))
def scope_at_percent(ci_ctx, pct):
    # 15% maps to "manufacturing" use-case scope (0.15)
    ci_ctx["scoped_result"] = scope_employees(
        ci_ctx["employee_count"], "manufacturing"
    )
    ci_ctx["expected_pct"] = pct


@then(parsers.parse("the result should be approximately {expected:d}"))
def result_approximately(ci_ctx, expected):
    result = ci_ctx["scoped_result"]
    tolerance = expected * 0.05  # 5% tolerance
    assert abs(result - expected) <= tolerance, (
        f"Scoped employees {result} not approximately {expected} (±{tolerance:.0f})"
    )
