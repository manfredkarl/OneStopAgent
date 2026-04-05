"""Shared fixtures for the OneStopAgent test suite."""

import sys
import os
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import httpx

# ---------------------------------------------------------------------------
# Path setup — ensure the python-api package root is importable
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.state import AgentState  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
# Canned response data
# ═══════════════════════════════════════════════════════════════════════════

CANNED_BUSINESS_VALUE: dict = {
    "phase": "complete",
    "drivers": [
        {
            "name": "Developer Productivity",
            "category": "cost_reduction",
            "metric": "20% faster dev cycles",
            "impact_pct_low": 15,
            "impact_pct_high": 25,
            "annual_value_low": 500000,
            "annual_value_high": 900000,
        },
        {
            "name": "Customer Engagement",
            "category": "revenue_uplift",
            "metric": "15% conversion increase",
            "impact_pct_low": 10,
            "impact_pct_high": 20,
            "annual_value_low": 300000,
            "annual_value_high": 600000,
        },
    ],
    "annual_impact_range": {"low": 800000, "high": 1500000},
    "confidence": {
        "overall_score": 65,
        "driver_scores": [70, 60],
        "methodology": "benchmark",
        "recommendation": "Refine with customer data",
        "label": "moderate",
    },
    "assumptions": ["Based on 500 affected employees", "Labor rate $85/hr"],
    "user_assumptions": [
        {
            "id": "affected_employees",
            "label": "Affected Employees",
            "value": 500,
            "unit": "people",
        },
        {
            "id": "hourly_labor_rate",
            "label": "Hourly Labor Rate",
            "value": 85,
            "unit": "$/hr",
        },
    ],
}

CANNED_ARCHITECTURE: dict = {
    "layers": [
        {
            "name": "AI & Agent Orchestration",
            "purpose": "Central AI processing",
            "components": [
                {
                    "name": "Azure AI Foundry",
                    "azureService": "Azure AI Services",
                    "role": "AI model hosting",
                },
                {
                    "name": "Azure OpenAI",
                    "azureService": "Azure OpenAI Service",
                    "role": "LLM inference",
                },
            ],
        },
        {
            "name": "Data & Integration",
            "purpose": "Data storage and retrieval",
            "components": [
                {
                    "name": "Cosmos DB",
                    "azureService": "Azure Cosmos DB",
                    "role": "NoSQL data store",
                },
            ],
        },
    ],
    "components": [
        {"name": "Azure AI Foundry", "azureService": "Azure AI Services", "tier": "S0"},
        {"name": "Azure OpenAI", "azureService": "Azure OpenAI Service", "tier": "S0"},
        {"name": "Cosmos DB", "azureService": "Azure Cosmos DB", "tier": "Serverless"},
    ],
    "mermaidCode": (
        "flowchart TD\n"
        "  subgraph AI[AI Layer]\n"
        "    A[Azure OpenAI]\n"
        "  end"
    ),
    "narrative": "This architecture is designed for an AI-powered development platform.",
    "adaptedFrom": "AI Chat Baseline",
    "nfr": {
        "security": {"zones": ["dmz", "internal"]},
        "compliance": {"frameworks": ["SOC2"]},
        "ha": {"drStrategy": "active-passive"},
        "monitoring": {"observability": "Azure Monitor"},
    },
}

CANNED_COSTS: dict = {
    "phase": "complete",
    "estimate": {
        "totalMonthly": 8500.0,
        "totalAnnual": 102000.0,
        "services": [
            {"name": "Azure OpenAI Service", "sku": "S0", "monthlyEstimate": 5000.0},
            {"name": "Azure Cosmos DB", "sku": "Serverless", "monthlyEstimate": 1500.0},
            {"name": "Azure AI Services", "sku": "S0", "monthlyEstimate": 2000.0},
        ],
    },
    "user_assumptions": [
        {
            "id": "concurrent_users",
            "label": "Concurrent Users",
            "value": 100,
            "unit": "users",
        },
    ],
}

CANNED_SHARED_ASSUMPTIONS: dict = {
    "affected_employees": 500,
    "hourly_labor_rate": 85,
    "current_annual_spend": 250000,
    "concurrent_users": 100,
    "total_users": 2000,
    "data_volume_gb": 50,
    "timeline_months": 6,
    "monthly_revenue": 5000000,
}

CANNED_COMPANY_PROFILE: dict = {
    "name": "Nike",
    "industry": "Consumer Goods",
    "employeeCount": 79400,
    "annualRevenue": 51200000000,
    "revenueCurrency": "USD",
    "headquarters": "Beaverton, Oregon, USA",
    "estimatedItSpend": 1536000000,
    "knownAzureUsage": ["Azure AI", "Azure Data Factory"],
    "confidence": "high",
}

CANNED_BRAINSTORMING: dict = {
    "phase": "complete",
    "industry": "Consumer Goods",
    "scenarios": [
        {
            "title": "AI-Powered Product Recommendations",
            "description": "Use Azure OpenAI to deliver personalized product suggestions.",
            "azure_services": ["Azure OpenAI", "Azure Cosmos DB"],
        },
        {
            "title": "Supply Chain Optimization",
            "description": "Predict demand spikes using ML models on Azure.",
            "azure_services": ["Azure Machine Learning", "Azure Data Factory"],
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Mock LLM fixture
# ═══════════════════════════════════════════════════════════════════════════

def _make_llm_response(content: str) -> MagicMock:
    """Build a mock LLM response object with a .content attribute."""
    resp = MagicMock()
    resp.content = content
    return resp


@pytest.fixture
def mock_llm():
    """Patch ``agents.llm.llm`` with a mock that returns canned JSON strings.

    The mock inspects the *system prompt* (first message content) and returns
    a plausible response for the detected agent.  Tests can override
    ``mock.invoke.return_value`` or ``mock.invoke.side_effect`` for
    custom scenarios.
    """
    import json

    default_responses: dict[str, str] = {
        "brainstorm": json.dumps(CANNED_BRAINSTORMING),
        "business_value": json.dumps(CANNED_BUSINESS_VALUE),
        "business value": json.dumps(CANNED_BUSINESS_VALUE),
        "architect": json.dumps(CANNED_ARCHITECTURE),
        "cost": json.dumps(CANNED_COSTS),
        "roi": json.dumps({
            "phase": "complete",
            "roiPercent": 1370,
            "paybackMonths": 5,
            "npv": 1200000,
        }),
        "pptxgenjs": (
            'const pptxgen = require("pptxgenjs");\n'
            "const pres = new pptxgen();\n"
            'pres.layout = "LAYOUT_16x9";\n'
            "let slide = pres.addSlide();\n"
            'slide.addText("Test Deck", { x: 1, y: 1, w: 8, h: 1, fontSize: 24 });\n'
            "pres.writeFile({ fileName: OUTPUT_PATH });\n"
        ),
    }

    def _side_effect(messages):
        """Route based on keywords in the system prompt."""
        system_text = ""
        if messages and hasattr(messages[0], "content"):
            system_text = messages[0].content.lower()
        elif messages and isinstance(messages[0], dict):
            system_text = messages[0].get("content", "").lower()
        elif messages and isinstance(messages[0], (list, tuple)):
            system_text = str(messages[0]).lower()

        for keyword, response_json in default_responses.items():
            if keyword in system_text:
                return _make_llm_response(response_json)

        # Fallback — generic acknowledgement
        return _make_llm_response('{"status": "ok"}')

    mock = MagicMock()
    mock.invoke = MagicMock(side_effect=_side_effect)
    mock.ainvoke = AsyncMock(side_effect=_side_effect)

    async def _astream(messages):
        resp = _side_effect(messages)
        for chunk in resp.content:
            mock_chunk = MagicMock()
            mock_chunk.content = chunk
            yield mock_chunk

    mock.astream = _astream

    # Patch both the module-level proxy name AND the internal singleton so
    # that agents which resolved the ``llm`` reference at import time also
    # receive the mock.  This handles the lazy-init path (C1 fix).
    import agents.llm as _llm_mod
    with patch("agents.llm.llm", mock), \
         patch.object(_llm_mod, "_llm_instance", mock):
        yield mock


# ═══════════════════════════════════════════════════════════════════════════
# AgentState factory fixture
# ═══════════════════════════════════════════════════════════════════════════

class AgentStateFactory:
    """Builds ``AgentState`` instances at various pipeline stages."""

    _base_input = "Help Nike build an AI-powered customer engagement platform on Azure"

    @staticmethod
    def empty_state() -> AgentState:
        return AgentState(
            user_input=AgentStateFactory._base_input,
            customer_name="Nike",
            company_profile=deepcopy(CANNED_COMPANY_PROFILE),
        )

    @staticmethod
    def state_after_brainstorm() -> AgentState:
        state = AgentStateFactory.empty_state()
        state.brainstorming = deepcopy(CANNED_BRAINSTORMING)
        state.mode = "brainstorm"
        state.azure_fit = "strong"
        state.azure_fit_explanation = "Nike already uses Azure AI and Azure Data Factory."
        return state

    @staticmethod
    def state_after_bv() -> AgentState:
        state = AgentStateFactory.state_after_brainstorm()
        state.mode = "solution"
        state.business_value = deepcopy(CANNED_BUSINESS_VALUE)
        state.shared_assumptions = deepcopy(CANNED_SHARED_ASSUMPTIONS)
        return state

    @staticmethod
    def state_after_architect() -> AgentState:
        state = AgentStateFactory.state_after_bv()
        state.architecture = deepcopy(CANNED_ARCHITECTURE)
        return state

    @staticmethod
    def state_after_cost() -> AgentState:
        state = AgentStateFactory.state_after_architect()
        state.costs = deepcopy(CANNED_COSTS)
        return state

    @staticmethod
    def state_ready_for_roi() -> AgentState:
        """State with both BV and cost data — the ROI agent's prerequisites."""
        state = AgentStateFactory.state_after_cost()
        # Ensure both business_value and costs are populated
        assert state.business_value.get("annual_impact_range"), "BV data missing"
        assert state.costs.get("estimate", {}).get("totalAnnual"), "Cost data missing"
        return state

    @staticmethod
    def state_ready_for_presentation() -> AgentState:
        """State with all upstream data — the Presentation agent's prerequisites."""
        state = AgentStateFactory.state_after_cost()
        state.roi = {
            "roi_percent": 150,
            "payback_months": 8,
            "annual_cost": 102000,
            "annual_value": 255000,
            "monetized_drivers": [
                {"name": "Developer Productivity", "annual_value": 200000},
            ],
            "qualitative_benefits": ["Improved developer experience"],
            "dashboard": {},
        }
        return state


@pytest.fixture
def agent_state_factory() -> AgentStateFactory:
    """Provides an ``AgentStateFactory`` for building states at various stages."""
    return AgentStateFactory()


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI TestClient fixture
# ═══════════════════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def async_client():
    """Yield an ``httpx.AsyncClient`` wired to the FastAPI app.

    Includes a default ``x-user-id`` header so endpoints that require
    user identification work out of the box.
    """
    from main import app  # local import to avoid import-time side effects

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"x-user-id": "test-user-001"},
    ) as client:
        yield client


# ═══════════════════════════════════════════════════════════════════════════
# Convenience fixtures for canned data (deep-copied to prevent bleed)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def canned_bv() -> dict:
    return deepcopy(CANNED_BUSINESS_VALUE)


@pytest.fixture
def canned_architecture() -> dict:
    return deepcopy(CANNED_ARCHITECTURE)


@pytest.fixture
def canned_costs() -> dict:
    return deepcopy(CANNED_COSTS)


@pytest.fixture
def canned_shared_assumptions() -> dict:
    return deepcopy(CANNED_SHARED_ASSUMPTIONS)


@pytest.fixture
def canned_company_profile() -> dict:
    return deepcopy(CANNED_COMPANY_PROFILE)
