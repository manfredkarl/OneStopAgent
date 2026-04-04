"""Tests for the CostAgent's pure-logic helper methods."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agents.cost_agent import CostAgent
from agents.state import AgentState


@pytest.fixture
def agent():
    return CostAgent()


# ═══════════════════════════════════════════════════════════════════════════
# _calculate_monthly
# ═══════════════════════════════════════════════════════════════════════════


class TestCalculateMonthly:
    def test_per_hour_pricing(self, agent):
        result = agent._calculate_monthly(1.0, "1 Hour", "Azure App Service", 1000, {})
        assert result == 730.0

    def test_per_gb_pricing(self, agent):
        result = agent._calculate_monthly(0.02, "1 GB", "Azure Blob Storage", 1000, {})
        # 1000 users → medium tier → 500 GB default
        assert result == pytest.approx(0.02 * 500, rel=0.01)

    def test_per_gb_pricing_with_usage_dict(self, agent):
        result = agent._calculate_monthly(
            0.02, "1 GB", "Azure Blob Storage", 1000,
            {"data_storage_gb": 200},
        )
        assert result == pytest.approx(0.02 * 200)

    def test_per_request_pricing(self, agent):
        usage = {"monthly_ai_requests": 100_000}
        result = agent._calculate_monthly(0.01, "1K requests", "Azure OpenAI", 1000, usage)
        assert result == pytest.approx(0.01 * 100_000)

    def test_flat_monthly(self, agent):
        result = agent._calculate_monthly(50.0, "1 Month", "Some Service", 100, {})
        assert result == 50.0

    def test_zero_price(self, agent):
        result = agent._calculate_monthly(0.0, "1 Hour", "Azure App Service", 1000, {})
        assert result == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# _apply_instance_count
# ═══════════════════════════════════════════════════════════════════════════


class TestApplyInstanceCount:
    def test_single_instance(self, agent):
        """SKU without node multiplier → 1× cost."""
        result = agent._apply_instance_count(100.0, "S0")
        assert result == 100.0

    def test_double_instance(self, agent):
        """SKU with (2 nodes) → 2× cost."""
        result = agent._apply_instance_count(100.0, "P1v3 (2 nodes)")
        assert result == 200.0

    def test_triple_instance(self, agent):
        """SKU with (3 nodes) → 3× cost."""
        result = agent._apply_instance_count(100.0, "S0 (3 nodes)")
        assert result == 300.0

    def test_no_multiplier(self, agent):
        """Plain SKU name without node spec → 1× cost."""
        result = agent._apply_instance_count(100.0, "Standard")
        assert result == 100.0


# ═══════════════════════════════════════════════════════════════════════════
# _build_cost_insights
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildCostInsights:
    @pytest.fixture
    def five_items(self):
        return [
            {"serviceName": "Azure OpenAI", "sku": "S0", "monthlyCost": 5000.0},
            {"serviceName": "Azure Cosmos DB", "sku": "Serverless", "monthlyCost": 1500.0},
            {"serviceName": "Azure App Service", "sku": "P1v3", "monthlyCost": 730.0},
            {"serviceName": "Azure AI Search", "sku": "S1", "monthlyCost": 250.0},
            {"serviceName": "Azure Blob Storage", "sku": "Hot", "monthlyCost": 20.0},
        ]

    def test_identifies_top_drivers(self, agent, five_items):
        total_monthly = sum(i["monthlyCost"] for i in five_items)
        insights = agent._build_cost_insights(five_items, total_monthly, total_monthly * 12, 1000)
        assert len(insights["top3Drivers"]) == 3

    def test_top_drivers_sorted_by_cost(self, agent, five_items):
        total_monthly = sum(i["monthlyCost"] for i in five_items)
        insights = agent._build_cost_insights(five_items, total_monthly, total_monthly * 12, 1000)
        top = insights["top3Drivers"]
        assert top[0]["monthly"] >= top[1]["monthly"] >= top[2]["monthly"]
        assert top[0]["service"] == "Azure OpenAI"

    def test_handles_empty_items(self, agent):
        insights = agent._build_cost_insights([], 0, 0, 1000)
        assert insights == {}


# ═══════════════════════════════════════════════════════════════════════════
# CostAgent state validation (run() with mocked LLM)
# ═══════════════════════════════════════════════════════════════════════════


class TestCostAgentStateValidation:
    def test_missing_architecture_graceful(self, agent, mock_llm):
        """No state.architecture → agent should not crash (phase 1: needs_input)."""
        state = AgentState(user_input="Build a chatbot for Contoso")
        result = agent.run(state)
        # Without user_assumptions the agent enters phase 1
        assert result.costs.get("phase") == "needs_input"

    def test_empty_components(self, agent, mock_llm):
        """Architecture with empty components list → handles gracefully."""
        state = AgentState(user_input="Build a chatbot for Contoso")
        state.architecture = {"components": [], "narrative": "empty arch"}
        result = agent.run(state)
        assert result.costs.get("phase") == "needs_input"
