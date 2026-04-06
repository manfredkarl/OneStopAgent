"""Comprehensive tests for ProjectManager pure-logic methods.

No LLM mocking needed — all methods under test are deterministic.
"""

import sys
import os
from copy import deepcopy

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.pm_agent import (  # noqa: E402
    ProjectManager,
    IntentInterpreter,
    Intent,
    AGENT_INFO,
    SOLUTIONING_PLAN,
    ITERATION_MAPPING,
)
from agents.state import AgentState  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def pm():
    return ProjectManager()


@pytest.fixture
def full_state(canned_bv, canned_architecture, canned_costs):
    """Fully-populated state through the entire pipeline."""
    state = AgentState(user_input="AI-powered dev platform")
    state.brainstorming = {
        "industry": "Technology",
        "scenarios": [{"title": "Dev Assistant"}],
    }
    state.plan_steps = ["business_value", "architect", "cost", "roi", "presentation"]
    state.business_value = canned_bv
    state.architecture = canned_architecture
    state.costs = canned_costs
    state.roi = {
        "roi_percent": 350,
        "roi_percent_display": 350,
        "payback_months": 8.5,
        "annual_cost": 102000,
        "annual_value": 1150000,
        "annual_value_low": 800000,
        "annual_value_high": 1500000,
        "monetized_drivers": [
            {"name": "Dev Productivity", "metric": "$700K/yr"},
        ],
        "assumptions": ["500 affected employees", "$85/hr labor rate"],
        "needs_info": None,
        "dashboard": {
            "businessCase": {
                "investment": {"year1Total": 153000},
                "valueBridge": {
                    "totalAnnualValue": 1150000,
                    "hardSavings": 700000,
                    "revenueUplift": 450000,
                    "riskReduction": 0,
                },
                "sensitivity": [
                    {"adoption": "50%", "annualValue": 575000, "roi": 175},
                ],
            }
        },
    }
    state.presentation_path = "/output/test.pptx"
    return state


# ═══════════════════════════════════════════════════════════════════════════
# TestBuildPlan
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildPlan:
    """Tests for ProjectManager.build_plan()."""

    def test_all_agents_active(self, pm):
        active = ["business_value", "architect", "cost", "roi", "presentation"]
        plan = pm.build_plan(active)
        assert plan == ["business_value", "architect", "cost", "roi", "presentation"]

    def test_subset_agents(self, pm):
        plan = pm.build_plan(["business_value", "cost"])
        assert "business_value" in plan
        assert "cost" in plan
        assert "architect" in plan  # always included

    def test_architect_always_included(self, pm):
        plan = pm.build_plan(["cost", "roi"])
        assert "architect" in plan

    def test_empty_active_agents(self, pm):
        plan = pm.build_plan([])
        assert "architect" in plan
        assert len(plan) >= 1

    def test_order_is_correct(self, pm):
        active = ["presentation", "roi", "cost", "architect", "business_value"]
        plan = pm.build_plan(active)
        expected = ["business_value", "architect", "cost", "roi", "presentation"]
        assert plan == expected

    def test_single_agent_plus_architect(self, pm):
        plan = pm.build_plan(["presentation"])
        assert plan == ["architect", "presentation"]

    def test_duplicate_active_agents(self, pm):
        plan = pm.build_plan(["cost", "cost", "architect"])
        assert plan.count("cost") == 1
        assert plan.count("architect") == 1


# ═══════════════════════════════════════════════════════════════════════════
# TestFormatPlan
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatPlan:
    """Tests for ProjectManager.format_plan()."""

    def _make_state(self, **kwargs) -> AgentState:
        state = AgentState(user_input="test")
        state.plan_steps = kwargs.get(
            "plan_steps",
            ["business_value", "architect", "cost", "roi", "presentation"],
        )
        state.completed_steps = kwargs.get("completed_steps", [])
        state.skipped_steps = kwargs.get("skipped_steps", [])
        state.failed_steps = kwargs.get("failed_steps", [])
        state.current_step = kwargs.get("current_step", "")
        return state

    def test_all_pending(self, pm):
        state = self._make_state()
        output = pm.format_plan(state)
        assert output.count("- [ ]") == 5
        assert "[x]" not in output
        assert "[-]" not in output
        assert "[!]" not in output

    def test_completed_step(self, pm):
        state = self._make_state(completed_steps=["business_value"])
        output = pm.format_plan(state)
        assert "[x]" in output
        assert "Business Value" in output

    def test_skipped_step(self, pm):
        state = self._make_state(skipped_steps=["cost"])
        output = pm.format_plan(state)
        assert "[-]" in output
        assert "~~" in output
        assert "skipped" in output

    def test_failed_step(self, pm):
        state = self._make_state(failed_steps=["roi"])
        output = pm.format_plan(state)
        assert "[!]" in output
        assert "failed" in output

    def test_current_step(self, pm):
        state = self._make_state(current_step="architect")
        output = pm.format_plan(state)
        assert "⏳" in output
        assert "System Architect" in output

    def test_mixed_states(self, pm):
        state = self._make_state(
            completed_steps=["business_value", "architect"],
            current_step="cost",
            skipped_steps=[],
            failed_steps=[],
        )
        output = pm.format_plan(state)
        assert output.count("[x]") == 2
        assert "⏳" in output
        # roi and presentation are still pending
        lines = output.split("\n")
        pending_count = sum(
            1 for line in lines
            if line.startswith("- [ ]") and "⏳" not in line
        )
        assert pending_count == 2

    def test_uses_agent_info_emoji(self, pm):
        state = self._make_state(plan_steps=["architect"])
        output = pm.format_plan(state)
        emoji = AGENT_INFO["architect"]["emoji"]
        assert emoji in output

    def test_heading_present(self, pm):
        state = self._make_state()
        output = pm.format_plan(state)
        assert "## 📋 Execution Plan" in output


# ═══════════════════════════════════════════════════════════════════════════
# TestFormatAgentOutput — architect
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatAgentOutputArchitect:
    """Tests for format_agent_output('architect', state)."""

    def test_architect_output_has_mermaid(self, pm, full_state):
        output = pm.format_agent_output("architect", full_state)
        assert "```mermaid" in output

    def test_architect_output_has_layers(self, pm, full_state):
        output = pm.format_agent_output("architect", full_state)
        assert "AI & Agent Orchestration" in output
        assert "Data & Integration" in output

    def test_architect_output_has_narrative(self, pm, full_state):
        output = pm.format_agent_output("architect", full_state)
        assert "AI-powered development platform" in output

    def test_architect_output_has_components(self, pm, full_state):
        output = pm.format_agent_output("architect", full_state)
        assert "Azure AI Foundry" in output
        assert "Azure OpenAI" in output
        assert "Cosmos DB" in output

    def test_architect_empty_architecture(self, pm):
        state = AgentState(user_input="test")
        state.architecture = {}
        output = pm.format_agent_output("architect", state)
        assert "Architecture" in output
        # Should not crash — graceful output
        assert isinstance(output, str)

    def test_architect_no_layers_falls_back_to_components(self, pm):
        state = AgentState(user_input="test")
        state.architecture = {
            "components": [
                {"name": "App Service", "azureService": "Azure App Service", "description": "Web hosting"},
            ],
            "narrative": "Simple web app.",
        }
        output = pm.format_agent_output("architect", state)
        assert "App Service" in output
        assert "Components" in output

    def test_architect_reference_pattern(self, pm, full_state):
        """basedOn attribution shows when present and not 'custom design'."""
        full_state.architecture["basedOn"] = "AI Hub Gateway"
        full_state.architecture["basedOnUrl"] = "https://example.com/pattern"
        full_state.architecture["adaptationNotes"] = "Adapted for dev tooling"
        output = pm.format_agent_output("architect", full_state)
        assert "Adapted from" in output
        assert "AI Hub Gateway" in output


# ═══════════════════════════════════════════════════════════════════════════
# TestFormatAgentOutput — business_value
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatAgentOutputBusinessValue:
    """Tests for format_agent_output('business_value', state)."""

    def test_bv_output_has_drivers(self, pm, full_state):
        output = pm.format_agent_output("business_value", full_state)
        assert "Developer Productivity" in output
        assert "Customer Engagement" in output

    def test_bv_output_has_impact_range(self, pm, full_state):
        output = pm.format_agent_output("business_value", full_state)
        assert "$800,000" in output
        assert "$1,500,000" in output

    def test_bv_empty(self, pm):
        state = AgentState(user_input="test")
        state.business_value = {}
        output = pm.format_agent_output("business_value", state)
        assert isinstance(output, str)
        # No drivers, should mention no dollar range
        assert "need more inputs" in output.lower() or "Value Drivers" in output

    def test_bv_needs_input_phase(self, pm):
        state = AgentState(user_input="test")
        state.business_value = {
            "phase": "needs_input",
            "assumptions_needed": [
                {"label": "Affected Employees", "default": 500, "unit": "people"},
            ],
        }
        output = pm.format_agent_output("business_value", state)
        assert "Input Needed" in output
        assert "Affected Employees" in output

    def test_bv_output_has_assumptions(self, pm, full_state):
        output = pm.format_agent_output("business_value", full_state)
        assert "500 affected employees" in output

    def test_bv_output_has_confidence(self, pm, full_state):
        output = pm.format_agent_output("business_value", full_state)
        # confidence dict has "label": "moderate" — used as confidence text
        assert "moderate" in output.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TestFormatAgentOutput — cost
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatAgentOutputCost:
    """Tests for format_agent_output('cost', state)."""

    def test_cost_output_has_services(self, pm, full_state):
        output = pm.format_agent_output("cost", full_state)
        assert "Azure OpenAI Service" in output or "Cost Estimate" in output

    def test_cost_output_has_totals(self, pm, full_state):
        output = pm.format_agent_output("cost", full_state)
        assert "$8,500" in output
        assert "$102,000" in output

    def test_cost_empty(self, pm):
        state = AgentState(user_input="test")
        state.costs = {}
        state.services = {}
        output = pm.format_agent_output("cost", state)
        assert isinstance(output, str)
        assert "Cost Summary" in output or "Cost Estimate" in output

    def test_cost_has_monthly_and_annual_labels(self, pm, full_state):
        output = pm.format_agent_output("cost", full_state)
        assert "Monthly" in output
        assert "Annual" in output


# ═══════════════════════════════════════════════════════════════════════════
# TestFormatAgentOutput — roi
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatAgentOutputROI:
    """Tests for format_agent_output('roi', state)."""

    def test_roi_output_has_roi_percent(self, pm, full_state):
        output = pm.format_agent_output("roi", full_state)
        # 350% ROI displayed as "+350%"
        assert "+350%" in output

    def test_roi_output_has_payback(self, pm, full_state):
        output = pm.format_agent_output("roi", full_state)
        assert "8.5 months" in output

    def test_roi_output_has_value_range(self, pm, full_state):
        output = pm.format_agent_output("roi", full_state)
        assert "$800,000" in output
        assert "$1,500,000" in output

    def test_roi_output_has_monetized_drivers(self, pm, full_state):
        output = pm.format_agent_output("roi", full_state)
        assert "Dev Productivity" in output
        assert "$700K/yr" in output

    def test_roi_output_has_assumptions(self, pm, full_state):
        output = pm.format_agent_output("roi", full_state)
        assert "500 affected employees" in output

    def test_roi_needs_info(self, pm):
        state = AgentState(user_input="test")
        state.roi = {
            "roi_percent": None,
            "needs_info": [
                "How many employees will use this?",
                "What is the current manual process time?",
            ],
        }
        output = pm.format_agent_output("roi", state)
        assert "How many employees" in output
        assert "manual process time" in output

    def test_roi_output_has_business_case(self, pm, full_state):
        output = pm.format_agent_output("roi", full_state)
        assert "Business Case Summary" in output
        assert "$1,150,000" in output  # totalAnnualValue
        assert "$153,000" in output  # year1Total

    def test_roi_empty(self, pm):
        state = AgentState(user_input="test")
        state.roi = {}
        output = pm.format_agent_output("roi", state)
        assert isinstance(output, str)
        assert "ROI" in output

    def test_roi_sensitivity(self, pm, full_state):
        output = pm.format_agent_output("roi", full_state)
        assert "50%" in output
        assert "Sensitivity" in output.lower() or "adoption" in output.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TestFormatAgentOutput — presentation
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatAgentOutputPresentation:
    """Tests for format_agent_output('presentation', state)."""

    def test_presentation_with_path(self, pm, full_state):
        output = pm.format_agent_output("presentation", full_state)
        assert "Ready for download" in output

    def test_presentation_without_path(self, pm):
        state = AgentState(user_input="test")
        state.presentation_path = ""
        output = pm.format_agent_output("presentation", state)
        assert "failed" in output.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TestFormatAgentOutput — unknown step
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatAgentOutputUnknown:
    def test_unknown_step_returns_completed(self, pm, full_state):
        output = pm.format_agent_output("unknown_step", full_state)
        assert "unknown_step completed" in output


# ═══════════════════════════════════════════════════════════════════════════
# TestApprovalSummary
# ═══════════════════════════════════════════════════════════════════════════


class TestApprovalSummary:
    """Tests for ProjectManager.approval_summary()."""

    def test_architect_approval_has_decision_question(self, pm, full_state):
        output = pm.approval_summary("architect", full_state)
        assert "Decision point" in output or "Architecture looks" in output

    def test_architect_approval_has_component_count(self, pm, full_state):
        output = pm.approval_summary("architect", full_state)
        # 3 components in canned_architecture
        assert "3 Azure components" in output

    def test_cost_approval_mentions_total(self, pm, full_state):
        output = pm.approval_summary("cost", full_state)
        assert "$8,500" in output or "$102,000" in output

    def test_bv_approval_mentions_drivers(self, pm, full_state):
        output = pm.approval_summary("business_value", full_state)
        # 2 drivers in canned_bv
        assert "2" in output
        assert "value driver" in output.lower()

    def test_bv_approval_weakest_driver(self, pm, full_state):
        output = pm.approval_summary("business_value", full_state)
        # driver_scores [70, 60] → weakest is Customer Engagement (60)
        assert "Customer Engagement" in output
        assert "60" in output

    def test_roi_approval_with_good_payback(self, pm, full_state):
        output = pm.approval_summary("roi", full_state)
        # payback 8.5 months < 12 → "Strong ROI case"
        assert "Strong ROI" in output

    def test_roi_approval_long_payback(self, pm):
        state = AgentState(user_input="test")
        state.roi = {
            "roi_percent": 80,
            "roi_percent_display": 80,
            "payback_months": 18,
        }
        output = pm.approval_summary("roi", state)
        assert "Break-even" in output or "Month 18" in output

    def test_roi_approval_needs_info(self, pm):
        state = AgentState(user_input="test")
        state.roi = {
            "roi_percent": None,
            "needs_info": ["How many employees?"],
        }
        output = pm.approval_summary("roi", state)
        assert "more information" in output.lower() or "How many employees" in output

    def test_presentation_approval(self, pm, full_state):
        output = pm.approval_summary("presentation", full_state)
        assert "download" in output.lower()

    def test_approval_always_has_refine_prompt(self, pm, full_state):
        for step in SOLUTIONING_PLAN:
            output = pm.approval_summary(step, full_state)
            assert "refine" in output.lower()

    def test_bv_needs_input_approval(self, pm):
        state = AgentState(user_input="test")
        state.business_value = {"phase": "needs_input"}
        output = pm.approval_summary("business_value", state)
        assert "assumptions" in output.lower() or "proceed" in output.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TestGetAgentsToRerun
# ═══════════════════════════════════════════════════════════════════════════


class TestGetAgentsToRerun:
    """Tests for ProjectManager.get_agents_to_rerun()."""

    def test_cheaper_keyword(self, pm):
        result = pm.get_agents_to_rerun("make it cheaper")
        assert "cost" in result
        assert "roi" in result

    def test_scale_keyword(self, pm):
        result = pm.get_agents_to_rerun("we need to scale")
        assert "cost" in result
        assert "roi" in result

    def test_value_keyword(self, pm):
        result = pm.get_agents_to_rerun("show more value")
        assert "business_value" in result

    def test_unknown_keyword(self, pm):
        result = pm.get_agents_to_rerun("xyzzy foobarbaz")
        # Default: all agents
        assert result == ["business_value", "architect", "cost", "roi", "presentation"]

    def test_multiple_keywords(self, pm):
        result = pm.get_agents_to_rerun("make it cheaper and add security")
        # First match wins (cheaper comes before security in ITERATION_MAPPING)
        assert "cost" in result

    def test_ha_keyword(self, pm):
        result = pm.get_agents_to_rerun("add high availability")
        assert "architect" in result
        assert "cost" in result
        assert "roi" in result

    def test_case_insensitive(self, pm):
        result = pm.get_agents_to_rerun("Make It CHEAPER Please")
        assert "cost" in result
        assert "roi" in result

    def test_security_keyword(self, pm):
        result = pm.get_agents_to_rerun("add security controls")
        assert result == ["architect", "cost"]

    def test_compliance_keywords(self, pm):
        for kw in ("gdpr", "hipaa", "pci", "soc2"):
            result = pm.get_agents_to_rerun(f"add {kw} compliance")
            assert "architect" in result, f"'{kw}' should trigger architect"
            assert "cost" in result, f"'{kw}' should trigger cost"

    def test_budget_keyword(self, pm):
        result = pm.get_agents_to_rerun("tight budget limits")
        assert result == ["cost", "roi"]


# ═══════════════════════════════════════════════════════════════════════════
# TestAgentInfo
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentInfo:
    """Tests for AGENT_INFO and SOLUTIONING_PLAN constants."""

    def test_all_plan_steps_in_agent_info(self):
        for step in SOLUTIONING_PLAN:
            assert step in AGENT_INFO, f"'{step}' missing from AGENT_INFO"

    def test_agent_info_has_name_and_emoji(self):
        for agent_id, info in AGENT_INFO.items():
            assert "name" in info, f"'{agent_id}' missing 'name'"
            assert "emoji" in info, f"'{agent_id}' missing 'emoji'"
            assert len(info["name"]) > 0
            assert len(info["emoji"]) > 0

    def test_solutioning_plan_order(self):
        assert SOLUTIONING_PLAN == [
            "business_value",
            "architect",
            "cost",
            "roi",
            "presentation",
        ]

    def test_iteration_mapping_values_are_valid_agents(self):
        valid = set(SOLUTIONING_PLAN)
        for keyword, agents in ITERATION_MAPPING.items():
            for agent in agents:
                assert agent in valid, (
                    f"ITERATION_MAPPING['{keyword}'] contains invalid agent '{agent}'"
                )


# ═══════════════════════════════════════════════════════════════════════════
# TestIntentInterpreterMultiIntent
# ═══════════════════════════════════════════════════════════════════════════


class TestIntentInterpreterMultiIntent:
    """Tests for multi-intent classification and phase-aware prompts."""

    @pytest.fixture
    def interpreter(self):
        return IntentInterpreter()

    # ── _parse_intents unit tests ──────────────────────────────────

    def test_parse_single_intent_json_array(self, interpreter):
        """Single intent in JSON array format."""
        result = interpreter._parse_intents('["proceed"]')
        assert result == [Intent.PROCEED]

    def test_parse_multi_intent_json_array(self, interpreter):
        """Multiple intents in JSON array → [PROCEED, ITERATION]."""
        result = interpreter._parse_intents('["proceed", "iteration"]')
        assert result == [Intent.PROCEED, Intent.ITERATION]

    def test_parse_single_word_fallback(self, interpreter):
        """Old-style single word response still works."""
        result = interpreter._parse_intents("proceed")
        assert result == [Intent.PROCEED]

    def test_parse_invalid_returns_input(self, interpreter):
        """Unparseable response falls back to [INPUT]."""
        result = interpreter._parse_intents("totally_unknown_garbage_xyz")
        assert result == [Intent.INPUT]

    def test_parse_empty_array_returns_input(self, interpreter):
        """Empty JSON array falls back to [INPUT]."""
        result = interpreter._parse_intents("[]")
        assert result == [Intent.INPUT]

    def test_parse_markdown_fenced_json(self, interpreter):
        """JSON wrapped in markdown code fences."""
        result = interpreter._parse_intents('```json\n["question", "iteration"]\n```')
        assert result == [Intent.QUESTION, Intent.ITERATION]

    def test_parse_json_string_not_array(self, interpreter):
        """JSON string (not array) is handled."""
        result = interpreter._parse_intents('"skip"')
        assert result == [Intent.SKIP]

    # ── classify method (sync) with mocked LLM ────────────────────

    def test_classify_returns_list(self, interpreter, mock_llm):
        """classify() now returns (list[Intent], dict)."""
        mock_llm.invoke.side_effect = None
        mock_llm.invoke.return_value = type("R", (), {"content": '["input"]'})()
        intents, meta = interpreter.classify("hello world")
        assert isinstance(intents, list)
        assert all(isinstance(i, Intent) for i in intents)

    def test_classify_multi_intent_proceed_iteration(self, interpreter, mock_llm):
        """'looks good but cheaper' → [PROCEED, ITERATION]."""
        mock_llm.invoke.side_effect = None
        mock_llm.invoke.return_value = type("R", (), {"content": '["proceed", "iteration"]'})()
        intents, meta = interpreter.classify("looks good but make it cheaper")
        assert Intent.PROCEED in intents
        assert Intent.ITERATION in intents
        assert "agents_to_rerun" in meta
        assert "cost" in meta["agents_to_rerun"]

    def test_classify_single_intent_backward_compat(self, interpreter, mock_llm):
        """Single intent still wrapped in list."""
        mock_llm.invoke.side_effect = None
        mock_llm.invoke.return_value = type("R", (), {"content": '["proceed"]'})()
        intents, meta = interpreter.classify("yes let's go")
        assert intents == [Intent.PROCEED]

    def test_classify_fallback_on_error(self, interpreter, mock_llm):
        """LLM failure falls back to [INPUT]."""
        mock_llm.invoke.side_effect = RuntimeError("API down")
        intents, meta = interpreter.classify("anything")
        assert intents == [Intent.INPUT]

    # ── Phase-aware prompt building ───────────────────────────────

    def test_build_system_prompt_no_phase(self, interpreter):
        """Without phase info, prompt is the base prompt."""
        prompt = interpreter._build_system_prompt()
        assert "JSON array" in prompt
        assert "Current phase" not in prompt

    def test_build_system_prompt_with_phase(self, interpreter):
        """With phase info, prompt includes phase context."""
        prompt = interpreter._build_system_prompt(phase="executing", current_step="cost")
        assert "Current phase: executing" in prompt
        assert "Current step: cost" in prompt
        assert "executing" in prompt

    def test_build_system_prompt_with_recent_messages(self, interpreter):
        """Recent messages appear in the prompt."""
        prompt = interpreter._build_system_prompt(
            phase="done",
            recent_messages=["msg1", "msg2", "msg3"],
        )
        assert "msg1" in prompt
        assert "msg3" in prompt

    def test_phase_done_hint_in_prompt(self, interpreter):
        """Done phase prompt includes iteration hint."""
        prompt = interpreter._build_system_prompt(phase="done")
        assert "done" in prompt
        assert "iterate" in prompt

    def test_classify_with_phase_passes_to_llm(self, interpreter, mock_llm):
        """Phase and step are passed through to the LLM call."""
        mock_llm.invoke.side_effect = None
        mock_llm.invoke.return_value = type("R", (), {"content": '["iteration"]'})()
        intents, meta = interpreter.classify(
            "make it cheaper",
            phase="done",
            current_step="presentation",
            recent_messages=["show me the deck"],
        )
        # Verify the system prompt sent to LLM includes phase info
        call_args = mock_llm.invoke.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "Current phase: done" in system_msg
        assert "Current step: presentation" in system_msg

    # ── Multi-meta building ───────────────────────────────────────

    def test_build_multi_meta_iteration_plus_proceed(self, interpreter):
        """Combined metadata from multiple intents."""
        meta = interpreter._build_multi_meta(
            [Intent.PROCEED, Intent.ITERATION], "looks good but cheaper"
        )
        assert "agents_to_rerun" in meta
        assert "feedback" in meta

    def test_build_multi_meta_single_intent(self, interpreter):
        """Single intent metadata works as before."""
        meta = interpreter._build_multi_meta([Intent.PROCEED], "yes")
        assert meta == {}

    def test_build_multi_meta_question(self, interpreter):
        """Question intent has no special metadata."""
        meta = interpreter._build_multi_meta([Intent.QUESTION], "what does this cost?")
        assert meta == {}


# ═══════════════════════════════════════════════════════════════════════════
# TestIntentInterpreterAsync
# ═══════════════════════════════════════════════════════════════════════════


class TestIntentInterpreterAsync:
    """Async variant tests for multi-intent classification."""

    @pytest.fixture
    def interpreter(self):
        return IntentInterpreter()

    @pytest.mark.asyncio
    async def test_aclassify_returns_list(self, interpreter, mock_llm):
        """aclassify() returns (list[Intent], dict)."""
        mock_llm.ainvoke.side_effect = None
        mock_llm.ainvoke.return_value = type("R", (), {"content": '["input"]'})()
        intents, meta = await interpreter.aclassify("hello")
        assert isinstance(intents, list)
        assert intents == [Intent.INPUT]

    @pytest.mark.asyncio
    async def test_aclassify_multi_intent(self, interpreter, mock_llm):
        """aclassify() supports multi-intent."""
        mock_llm.ainvoke.side_effect = None
        mock_llm.ainvoke.return_value = type("R", (), {"content": '["proceed", "iteration"]'})()
        intents, meta = await interpreter.aclassify(
            "looks good but add HA",
            phase="done",
            current_step="",
        )
        assert Intent.PROCEED in intents
        assert Intent.ITERATION in intents

    @pytest.mark.asyncio
    async def test_aclassify_fallback_on_error(self, interpreter, mock_llm):
        """aclassify() falls back to [INPUT] on error."""
        mock_llm.ainvoke.side_effect = RuntimeError("boom")
        intents, meta = await interpreter.aclassify("anything")
        assert intents == [Intent.INPUT]
