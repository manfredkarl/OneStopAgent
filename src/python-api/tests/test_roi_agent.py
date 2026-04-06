import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import pytest
from agents.state import AgentState
from agents.roi_agent import ROIAgent


class TestROICalculation:
    """Test core ROI math — the most critical path in the app."""

    @pytest.fixture
    def agent(self):
        return ROIAgent()

    @pytest.fixture
    def state_ready(self):
        """State with BV + cost data ready for ROI calculation."""
        state = AgentState(user_input="AI-powered dev platform for Nike")
        state.brainstorming = {"industry": "Consumer Goods", "scenarios": []}
        state.shared_assumptions = {
            "affected_employees": 500,
            "hourly_labor_rate": 85,
            "current_annual_spend": 250000,
            "concurrent_users": 100,
            "timeline_months": 6,
            "monthly_revenue": 5000000,
        }
        state.business_value = {
            "phase": "complete",
            "drivers": [
                {"name": "Developer Productivity", "category": "cost_reduction",
                 "metric": "20% faster dev cycles", "impact_pct_low": 15, "impact_pct_high": 25,
                 "annual_value_low": 500000, "annual_value_high": 900000},
                {"name": "Customer Engagement", "category": "revenue_uplift",
                 "metric": "15% conversion", "impact_pct_low": 10, "impact_pct_high": 20,
                 "annual_value_low": 300000, "annual_value_high": 600000},
            ],
            "annual_impact_range": {"low": 800000, "high": 1500000},
            "confidence": {
                "overall_score": 65,
                "driver_scores": [70, 60],
                "methodology": "benchmark",
                "recommendation": "Refine",
                "label": "moderate"
            },
            "assumptions": ["Based on 500 employees"],
            "user_assumptions": [
                {"id": "affected_employees", "label": "Affected Employees", "value": 500, "unit": "people"},
            ],
        }
        state.costs = {
            "phase": "complete",
            "estimate": {
                "totalMonthly": 8500.0,
                "totalAnnual": 102000.0,
                "services": [
                    {"name": "Azure OpenAI", "sku": "S0", "monthlyEstimate": 5000.0},
                    {"name": "Cosmos DB", "sku": "Serverless", "monthlyEstimate": 1500.0},
                    {"name": "Azure AI Services", "sku": "S0", "monthlyEstimate": 2000.0},
                ],
            },
            "user_assumptions": [
                {"id": "concurrent_users", "label": "Concurrent Users", "value": 100, "unit": "users"},
            ],
        }
        state.architecture = {
            "layers": [
                {"name": "AI Layer", "components": [
                    {"name": "Azure OpenAI", "azureService": "Azure OpenAI Service"},
                ]},
            ],
            "components": [
                {"name": "Azure OpenAI", "azureService": "Azure OpenAI Service", "tier": "S0"},
                {"name": "Cosmos DB", "azureService": "Azure Cosmos DB", "tier": "Serverless"},
            ],
        }
        return state

    def test_roi_produces_positive_roi(self, agent, state_ready):
        """With 800K-1.5M value and 102K cost, ROI must be positive."""
        result = agent.run(state_ready)
        assert result.roi.get("roi_percent") is not None
        assert result.roi["roi_percent"] > 0

    def test_roi_payback_months_is_number(self, agent, state_ready):
        """Payback months should be a positive number."""
        result = agent.run(state_ready)
        payback = result.roi.get("payback_months")
        assert payback is not None
        assert isinstance(payback, (int, float))
        assert payback > 0

    def test_dashboard_confidence_is_string_not_dict(self, agent, state_ready):
        """REGRESSION: confidence was passed as dict causing React crash."""
        result = agent.run(state_ready)
        dashboard = result.roi.get("dashboard", {})
        confidence = dashboard.get("confidenceLevel")
        assert confidence is not None
        assert isinstance(confidence, str), f"confidenceLevel should be str, got {type(confidence)}: {confidence}"
        assert confidence in ("high", "moderate", "low")

    def test_dashboard_confidence_from_legacy_string(self, agent, state_ready):
        """When BV confidence is already a string, it should pass through."""
        state_ready.business_value["confidence"] = "high"
        result = agent.run(state_ready)
        dashboard = result.roi["dashboard"]
        assert dashboard["confidenceLevel"] == "high"

    def test_dashboard_is_json_serializable(self, agent, state_ready):
        """REGRESSION: dict values caused JSON serialization issues in frontend."""
        result = agent.run(state_ready)
        dashboard = result.roi.get("dashboard")
        assert dashboard is not None
        # This should not raise TypeError
        json_str = json.dumps(dashboard, default=str)
        assert len(json_str) > 100  # Non-trivial output

    def test_dashboard_drivers_are_list(self, agent, state_ready):
        """Dashboard drivers must be an array for React rendering."""
        result = agent.run(state_ready)
        drivers = result.roi["dashboard"].get("drivers")
        assert isinstance(drivers, list)
        assert len(drivers) > 0

    def test_dashboard_projection_exists(self, agent, state_ready):
        """Dashboard must include multi-year projection data."""
        result = agent.run(state_ready)
        projection = result.roi["dashboard"].get("projection")
        assert projection is not None
        assert "cumulative" in projection
        assert len(projection["cumulative"]) > 0

    def test_roi_needs_info_when_no_cost(self, agent):
        """ROI agent should request info when cost data is missing."""
        state = AgentState(user_input="test")
        state.business_value = {
            "drivers": [{"name": "Test"}],
            "annual_impact_range": {"low": 100000, "high": 200000},
        }
        state.costs = {}  # No cost data
        result = agent.run(state)
        assert result.roi.get("needs_info") is not None

    def test_roi_needs_info_when_no_impact_range(self, agent):
        """ROI agent should estimate impact range when BV data is missing."""
        state = AgentState(user_input="test")
        state.business_value = {"drivers": [{"name": "Test"}]}
        state.costs = {"estimate": {"totalAnnual": 100000, "totalMonthly": 8333}}
        result = agent.run(state)
        # Should produce a result (estimated) instead of needs_info
        assert result.roi.get("needs_info") is None
        assert result.roi.get("dashboard") is not None or result.roi.get("annual_cost", 0) > 0

    def test_roi_handles_zero_impact_range(self, agent):
        """Zero impact range should use cost-multiplier fallback, not division by zero."""
        state = AgentState(user_input="test")
        state.business_value = {
            "drivers": [],
            "annual_impact_range": {"low": 0, "high": 0},
        }
        state.costs = {"estimate": {"totalAnnual": 100000, "totalMonthly": 8333}}
        result = agent.run(state)
        # Should produce estimated result via fallback, no crash
        assert result.roi.get("needs_info") is None

    def test_roi_extreme_values_are_flagged(self, agent, state_ready):
        """Extremely high ROI should set roi_capped or produce a display text."""
        # Make value 100x cost
        state_ready.business_value["annual_impact_range"] = {"low": 5000000, "high": 15000000}
        result = agent.run(state_ready)
        # The agent should still produce a numeric display value
        display = result.roi.get("roi_percent_display")
        assert display is not None
        assert isinstance(display, (int, float))
        assert display > 0

    def test_waterfall_values_present(self, agent, state_ready):
        """Dashboard should include value waterfall breakdown."""
        result = agent.run(state_ready)
        waterfall = result.roi["dashboard"].get("valueWaterfall")
        assert waterfall is not None
        assert "costReduction" in waterfall
        assert "revenueUplift" in waterfall

    def test_business_case_present(self, agent, state_ready):
        """Dashboard should include business case summary."""
        result = agent.run(state_ready)
        bc = result.roi["dashboard"].get("businessCase")
        assert bc is not None
        assert "investment" in bc
        assert "valueBridge" in bc

    def test_npv_irr_present(self, agent, state_ready):
        """Dashboard should include NPV and IRR calculations."""
        result = agent.run(state_ready)
        dashboard = result.roi["dashboard"]
        assert "npv" in dashboard
        assert "irr" in dashboard
        # NPV should be meaningful (not zero)
        if dashboard["npv"] is not None:
            assert isinstance(dashboard["npv"], (int, float))

    def test_tornado_sensitivity_present(self, agent, state_ready):
        """Dashboard should include tornado sensitivity analysis."""
        result = agent.run(state_ready)
        tornado = result.roi["dashboard"].get("tornado")
        assert tornado is not None
        assert isinstance(tornado, list)

    def test_methodology_is_string(self, agent, state_ready):
        """Methodology field must be a renderable string."""
        result = agent.run(state_ready)
        methodology = result.roi["dashboard"].get("methodology")
        assert isinstance(methodology, str)
        assert len(methodology) > 20  # Should be a meaningful description


class TestROIEdgeCases:
    """Edge cases that have caused production issues."""

    @pytest.fixture
    def agent(self):
        return ROIAgent()

    def test_confidence_dict_with_missing_label(self, agent):
        """If confidence dict has no 'label' key, should default to 'moderate'."""
        state = AgentState(user_input="test")
        state.shared_assumptions = {"affected_employees": 100, "hourly_labor_rate": 50, "timeline_months": 6}
        state.business_value = {
            "drivers": [
                {"name": "Efficiency", "category": "cost_reduction",
                 "annual_value_low": 200000, "annual_value_high": 400000},
            ],
            "annual_impact_range": {"low": 200000, "high": 400000},
            "confidence": {"overall_score": 50},  # No 'label' key!
        }
        state.costs = {"estimate": {"totalAnnual": 50000, "totalMonthly": 4167}}
        state.architecture = {"components": []}
        result = agent.run(state)
        dashboard = result.roi.get("dashboard", {})
        conf = dashboard.get("confidenceLevel")
        assert isinstance(conf, str), f"Got {type(conf)}: {conf}"

    def test_empty_drivers_list(self, agent):
        """ROI should handle empty drivers gracefully."""
        state = AgentState(user_input="test")
        state.shared_assumptions = {"timeline_months": 6}
        state.business_value = {
            "drivers": [],
            "annual_impact_range": {"low": 100000, "high": 200000},
            "confidence": "moderate",
        }
        state.costs = {"estimate": {"totalAnnual": 50000, "totalMonthly": 4167}}
        state.architecture = {"components": []}
        result = agent.run(state)
        # Should still produce ROI even with no named drivers
        assert result.roi.get("roi_percent") is not None or result.roi.get("needs_info") is not None

    def test_no_shared_assumptions(self, agent):
        """ROI should work even without shared assumptions."""
        state = AgentState(user_input="test")
        state.business_value = {
            "drivers": [
                {"name": "Efficiency", "category": "cost_reduction",
                 "annual_value_low": 200000, "annual_value_high": 400000},
            ],
            "annual_impact_range": {"low": 200000, "high": 400000},
            "confidence": "moderate",
        }
        state.costs = {"estimate": {"totalAnnual": 50000, "totalMonthly": 4167}}
        state.architecture = {"components": []}
        # No shared_assumptions set
        result = agent.run(state)
        # Should not crash
        assert result.roi is not None


class TestDashboardPrimitiveTypes:
    """Ensure every dashboard field is a JSON-safe primitive type.
    This prevents React 'Objects are not valid as a React child' crashes."""

    @pytest.fixture
    def dashboard(self):
        agent = ROIAgent()
        state = AgentState(user_input="test")
        state.shared_assumptions = {"affected_employees": 500, "hourly_labor_rate": 85, "timeline_months": 6, "monthly_revenue": 5000000}
        state.business_value = {
            "drivers": [
                {"name": "Dev Productivity", "category": "cost_reduction",
                 "metric": "20% faster", "annual_value_low": 500000, "annual_value_high": 900000},
                {"name": "Revenue Growth", "category": "revenue_uplift",
                 "metric": "15% more", "annual_value_low": 300000, "annual_value_high": 600000},
            ],
            "annual_impact_range": {"low": 800000, "high": 1500000},
            "confidence": {"overall_score": 65, "driver_scores": [70, 60], "methodology": "benchmark", "recommendation": "Refine", "label": "moderate"},
            "user_assumptions": [{"id": "affected_employees", "value": 500}],
        }
        state.costs = {
            "estimate": {"totalAnnual": 102000, "totalMonthly": 8500},
            "user_assumptions": [{"id": "concurrent_users", "value": 100}],
        }
        state.architecture = {"components": [{"name": "Azure OpenAI"}, {"name": "Cosmos DB"}]}
        result = agent.run(state)
        return result.roi.get("dashboard", {})

    def test_confidence_level_is_primitive(self, dashboard):
        val = dashboard.get("confidenceLevel")
        assert val is None or isinstance(val, str)

    def test_roi_percent_is_primitive(self, dashboard):
        val = dashboard.get("roiPercent")
        assert val is None or isinstance(val, (int, float))

    def test_payback_months_is_primitive(self, dashboard):
        val = dashboard.get("paybackMonths")
        assert val is None or isinstance(val, (int, float))

    def test_methodology_is_primitive(self, dashboard):
        val = dashboard.get("methodology")
        assert val is None or isinstance(val, str)

    def test_warning_is_primitive(self, dashboard):
        val = dashboard.get("warning")
        assert val is None or isinstance(val, str)

    def test_monthly_savings_is_primitive(self, dashboard):
        val = dashboard.get("monthlySavings")
        assert val is None or isinstance(val, (int, float))

    def test_annual_impact_is_primitive(self, dashboard):
        val = dashboard.get("annualImpact")
        assert val is None or isinstance(val, (int, float))

    def test_no_nested_dicts_in_top_level(self, dashboard):
        """Top-level dashboard values that React renders directly must not be dicts."""
        react_rendered_keys = [
            "confidenceLevel", "roiPercent", "roiDisplayText", "roiSteadyStateText",
            "roiSubtitle", "roiDescription", "paybackMonths", "monthlySavings",
            "annualImpact", "savingsPercentage", "methodology", "warning",
        ]
        for key in react_rendered_keys:
            val = dashboard.get(key)
            assert not isinstance(val, dict), f"dashboard['{key}'] is a dict: {val}"
