"""Tests for the Presentation Agent."""

import os
import json
from unittest.mock import patch, MagicMock

import pytest

from agents.presentation_agent import PresentationAgent
from agents.state import AgentState


# ── Helpers ────────────────────────────────────────────────────────────────

VALID_PPTXGENJS_SCRIPT = (
    'const pptxgen = require("pptxgenjs");\n'
    "const pres = new pptxgen();\n"
    'pres.layout = "LAYOUT_16x9";\n'
    "let slide = pres.addSlide();\n"
    'slide.addText("Test", { x: 1, y: 1, w: 5, h: 1, fontSize: 24 });\n'
    "pres.writeFile({ fileName: OUTPUT_PATH });\n"
)


def _make_llm_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    return resp


# ── _build_slide_data tests ───────────────────────────────────────────────

class TestBuildSlideData:
    """Verify _build_slide_data extracts the right fields from state."""

    def test_minimal_state(self):
        agent = PresentationAgent()
        state = AgentState(user_input="Test problem", customer_name="Contoso")
        data = agent._build_slide_data(state)
        assert data["customer"] == "Contoso"
        assert data["problem"] == "Test problem"
        assert "industry" in data

    def test_full_state(self, agent_state_factory):
        agent = PresentationAgent()
        state = agent_state_factory.state_ready_for_presentation()
        data = agent._build_slide_data(state)

        assert data["customer"] == "Nike"
        assert "architecture" in data
        assert "businessValue" in data
        assert "roi" in data

    def test_missing_optional_sections(self):
        agent = PresentationAgent()
        state = AgentState(
            user_input="problem",
            customer_name="Acme",
            brainstorming={"industry": "Tech"},
        )
        data = agent._build_slide_data(state)
        assert data["customer"] == "Acme"
        assert "architecture" not in data
        assert "costs" not in data
        assert "roi" not in data

    def test_customer_challenges_extracted(self):
        agent = PresentationAgent()
        state = AgentState(
            user_input="problem",
            customer_name="Acme",
            brainstorming={
                "industry": "Retail",
                "pain_points": ["Legacy ERP", "Manual forecasting"],
                "market_drivers": ["AI adoption", "Supply chain disruption"],
                "competitive_landscape": "Competitors investing in ML",
            },
        )
        data = agent._build_slide_data(state)
        assert data["customer_challenges"] == ["Legacy ERP", "Manual forecasting"]
        assert data["market_drivers"] == ["AI adoption", "Supply chain disruption"]
        assert data["competitive_context"] == "Competitors investing in ML"

    def test_customer_challenges_empty_when_missing(self):
        agent = PresentationAgent()
        state = AgentState(
            user_input="problem",
            customer_name="Acme",
            brainstorming={"industry": "Tech"},
        )
        data = agent._build_slide_data(state)
        assert data["customer_challenges"] == []
        assert data["market_drivers"] == []
        assert data["competitive_context"] == ""

    def test_existing_azure_services_extracted(self):
        agent = PresentationAgent()
        state = AgentState(
            user_input="problem",
            customer_name="Acme",
            brainstorming={"industry": "Tech"},
            company_profile={
                "name": "Acme",
                "knownAzureUsage": ["Azure AI", "Azure Data Factory"],
                "cloudProvider": "AWS",
                "erp": "SAP",
            },
        )
        data = agent._build_slide_data(state)
        assert data["existing_azure_services"] == ["Azure AI", "Azure Data Factory"]
        assert data["cloud_provider"] == "AWS"
        assert data["erp"] == "SAP"

    def test_no_azure_fields_when_absent(self):
        agent = PresentationAgent()
        state = AgentState(
            user_input="problem",
            customer_name="Acme",
            brainstorming={"industry": "Tech"},
            company_profile={"name": "Acme"},
        )
        data = agent._build_slide_data(state)
        assert "existing_azure_services" not in data
        assert "cloud_provider" not in data
        assert "erp" not in data

    def test_cost_confidence_high(self):
        agent = PresentationAgent()
        state = AgentState(
            user_input="problem",
            customer_name="Acme",
            brainstorming={"industry": "Tech"},
            costs={
                "estimate": {
                    "totalMonthly": 5000,
                    "totalAnnual": 60000,
                    "pricingSource": "8 live, 2 fallback",
                    "items": [
                        {"serviceName": "Svc A", "sku": "S0", "monthlyCost": 3000},
                    ],
                }
            },
        )
        data = agent._build_slide_data(state)
        assert data["costs"]["confidence"] == "High"

    def test_cost_confidence_moderate(self):
        agent = PresentationAgent()
        state = AgentState(
            user_input="problem",
            customer_name="Acme",
            brainstorming={"industry": "Tech"},
            costs={
                "estimate": {
                    "totalMonthly": 5000,
                    "totalAnnual": 60000,
                    "pricingSource": "2 live, 8 fallback",
                    "items": [],
                }
            },
        )
        data = agent._build_slide_data(state)
        assert data["costs"]["confidence"] == "Moderate"


# ── _generate_pptxgenjs_script tests ──────────────────────────────────────

class TestGenerateScript:
    """Verify script generation calls LLM and validates output."""

    def test_valid_script_accepted(self):
        agent = PresentationAgent()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(VALID_PPTXGENJS_SCRIPT)

        script = agent._generate_pptxgenjs_script({"customer": "Test"}, mock_llm)
        assert "pptxgenjs" in script.lower()
        assert "writefile" in script.lower()

    def test_markdown_fences_stripped(self):
        agent = PresentationAgent()
        fenced = f"```javascript\n{VALID_PPTXGENJS_SCRIPT}```"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(fenced)

        script = agent._generate_pptxgenjs_script({"customer": "Test"}, mock_llm)
        assert not script.startswith("```")
        assert "pptxgenjs" in script.lower()

    def test_invalid_script_raises(self):
        agent = PresentationAgent()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("console.log('hello');")

        with pytest.raises(ValueError, match="missing required PptxGenJS structure"):
            agent._generate_pptxgenjs_script({"customer": "Test"}, mock_llm)


# ── Full run() tests ─────────────────────────────────────────────────────

class TestPresentationRun:
    """Test the full run() method with mocked LLM and Node.js."""

    def test_run_success(self, agent_state_factory):
        agent = PresentationAgent()
        state = agent_state_factory.state_ready_for_presentation()

        mock_llm_obj = MagicMock()
        mock_llm_obj.invoke.return_value = _make_llm_response(VALID_PPTXGENJS_SCRIPT)

        with patch("agents.llm.llm", mock_llm_obj), \
             patch("services.presentation.execute_pptxgenjs", return_value="/output/deck.pptx"):
            result = agent.run(state)

        assert result.presentation_path == "/output/deck.pptx"

    def test_run_autofix_on_first_failure(self, agent_state_factory):
        agent = PresentationAgent()
        state = agent_state_factory.state_ready_for_presentation()

        mock_llm_obj = MagicMock()
        # First call: generate script; second call: fix script
        mock_llm_obj.invoke.return_value = _make_llm_response(VALID_PPTXGENJS_SCRIPT)

        call_count = 0

        def mock_execute(script, customer):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Node.js syntax error")
            return "/output/fixed_deck.pptx"

        with patch("agents.llm.llm", mock_llm_obj), \
             patch("services.presentation.execute_pptxgenjs", side_effect=mock_execute):
            result = agent.run(state)

        assert result.presentation_path == "/output/fixed_deck.pptx"
        assert call_count == 2

    def test_run_raises_after_both_failures(self, agent_state_factory):
        agent = PresentationAgent()
        state = agent_state_factory.state_ready_for_presentation()

        mock_llm_obj = MagicMock()
        mock_llm_obj.invoke.return_value = _make_llm_response(VALID_PPTXGENJS_SCRIPT)

        with patch("agents.llm.llm", mock_llm_obj), \
             patch("services.presentation.execute_pptxgenjs", side_effect=RuntimeError("fail")):
            with pytest.raises(RuntimeError, match="Presentation generation failed after auto-fix"):
                agent.run(state)


# ── Mock LLM integration (conftest mock_llm) ─────────────────────────────

class TestMockLLMIntegration:
    """Verify the conftest mock_llm returns valid data for presentation."""

    def test_mock_returns_valid_pptxgenjs(self, mock_llm):
        """The mock LLM should return a valid PptxGenJS script for presentation prompts."""
        response = mock_llm.invoke([
            {"role": "system", "content": "You are a PptxGenJS expert."},
            {"role": "user", "content": "Generate a script."},
        ])
        script = response.content.strip()
        assert "pptxgenjs" in script.lower(), (
            f"Mock response should contain 'pptxgenjs' but got: {script[:100]}"
        )
        assert "writefile" in script.lower(), (
            f"Mock response should contain 'writeFile' but got: {script[:100]}"
        )
