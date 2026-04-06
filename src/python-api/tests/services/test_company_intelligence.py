"""Tests for company intelligence service helper functions.

Pure-function tests — no Azure credentials, LLM calls, or web search required.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from services.company_intelligence import (
    estimate_it_spend,
    estimate_labor_rate,
    scope_employees,
    build_fallback_profile,
    IT_SPEND_RATIOS,
    FALLBACK_PROFILES,
)


# ── estimate_it_spend ──────────────────────────────────────────────────────

class TestEstimateItSpend:
    def test_manufacturing_industry(self):
        # 3.5% of 72B EUR revenue
        result = estimate_it_spend(72_000_000_000, "Manufacturing")
        assert result == round(72_000_000_000 * 0.035)

    def test_financial_services_industry(self):
        result = estimate_it_spend(1_000_000_000, "Financial Services")
        assert result == round(1_000_000_000 * 0.075)

    def test_technology_industry(self):
        result = estimate_it_spend(5_000_000_000, "Technology")
        assert result == round(5_000_000_000 * 0.120)

    def test_unknown_industry_uses_default(self):
        result = estimate_it_spend(100_000_000, "Unknown Sector XYZ")
        assert result == round(100_000_000 * IT_SPEND_RATIOS["default"])

    def test_none_revenue_returns_none(self):
        assert estimate_it_spend(None, "Manufacturing") is None

    def test_zero_revenue_returns_none(self):
        assert estimate_it_spend(0, "Healthcare") is None

    def test_partial_match_industry(self):
        # "banking" is a key; "investment banking" should partial-match
        result = estimate_it_spend(500_000_000, "Investment Banking")
        assert result == round(500_000_000 * 0.080)

    def test_healthcare_industry(self):
        result = estimate_it_spend(250_000_000, "Healthcare")
        assert result == round(250_000_000 * 0.045)


# ── estimate_labor_rate ────────────────────────────────────────────────────

class TestEstimateLaborRate:
    def test_us_technology(self):
        rate = estimate_labor_rate("San Francisco, United States", "Technology")
        assert rate == 95.0

    def test_germany_manufacturing(self):
        rate = estimate_labor_rate("Munich, Germany", "Manufacturing")
        assert rate == 70.0

    def test_india_technology(self):
        rate = estimate_labor_rate("Bangalore, India", "Technology")
        assert rate == 35.0

    def test_unknown_region_returns_default(self):
        rate = estimate_labor_rate("Unknown City, Unknown Country", "Healthcare")
        assert rate == 75.0

    def test_empty_hq_returns_default(self):
        rate = estimate_labor_rate("", "Technology")
        assert rate == 75.0

    def test_us_healthcare(self):
        rate = estimate_labor_rate("New York, United States", "Healthcare")
        assert rate == 85.0

    def test_uk_financial_services(self):
        rate = estimate_labor_rate("London, United Kingdom", "Financial Services")
        assert rate == 85.0


# ── scope_employees ────────────────────────────────────────────────────────

class TestScopeEmployees:
    def test_rd_use_case(self):
        # 5% of 320,000 = 16,000
        result = scope_employees(320_000, "Build an R&D platform for engineers")
        assert result == int(320_000 * 0.05)

    def test_all_employees_use_case(self):
        result = scope_employees(10_000, "Deploy company-wide AI assistant for all employees")
        assert result == 10_000

    def test_it_use_case(self):
        result = scope_employees(50_000, "IT operations and monitoring platform")
        assert result == int(50_000 * 0.03)

    def test_manufacturing_use_case(self):
        result = scope_employees(20_000, "Smart manufacturing and factory automation")
        assert result == int(20_000 * 0.15)

    def test_default_ratio_when_no_match(self):
        result = scope_employees(10_000, "General digital transformation initiative")
        assert result == int(10_000 * 0.10)

    def test_none_employees_uses_fallback_1000(self):
        result = scope_employees(None, "R&D platform")
        assert result == int(1_000 * 0.05)

    def test_sales_use_case(self):
        result = scope_employees(5_000, "AI-powered sales enablement platform")
        assert result == int(5_000 * 0.08)


# ── build_fallback_profile ─────────────────────────────────────────────────

class TestBuildFallbackProfile:
    def test_small_profile(self):
        profile = build_fallback_profile("small", "Acme Corp")
        assert profile["name"] == "Acme Corp"
        assert profile["employeeCount"] == FALLBACK_PROFILES["small"]["employeeCount"]
        assert profile["annualRevenue"] == FALLBACK_PROFILES["small"]["annualRevenue"]
        assert profile["itSpendEstimate"] == FALLBACK_PROFILES["small"]["itSpendEstimate"]
        assert profile["hourlyLaborRate"] == FALLBACK_PROFILES["small"]["hourlyLaborRate"]
        assert profile["confidence"] == "low"
        assert profile["sizeTier"] == "small"
        assert "enrichedAt" in profile

    def test_mid_market_profile(self):
        profile = build_fallback_profile("mid-market", "TechCo")
        assert profile["name"] == "TechCo"
        assert profile["employeeCount"] == 2_500
        assert profile["annualRevenue"] == 250_000_000
        assert profile["itSpendEstimate"] == 10_000_000
        assert profile["hourlyLaborRate"] == 80

    def test_enterprise_profile(self):
        profile = build_fallback_profile("enterprise", "MegaCorp")
        assert profile["name"] == "MegaCorp"
        assert profile["employeeCount"] == 25_000
        assert profile["annualRevenue"] == 5_000_000_000
        assert profile["itSpendEstimate"] == 175_000_000
        assert profile["hourlyLaborRate"] == 95

    def test_unknown_size_falls_back_to_mid_market(self):
        # Unknown size key → mid-market default
        profile = build_fallback_profile("xxlarge", "Widget Inc")
        assert profile["employeeCount"] == FALLBACK_PROFILES["mid-market"]["employeeCount"]

    def test_disambiguated_is_false(self):
        profile = build_fallback_profile("small", "Test Co")
        assert profile["disambiguated"] is False

    def test_industry_is_none(self):
        profile = build_fallback_profile("enterprise", "BigBank")
        assert profile["industry"] is None
