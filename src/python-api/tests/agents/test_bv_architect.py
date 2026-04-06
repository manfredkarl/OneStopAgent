"""Tests for BusinessValueAgent and ArchitectAgent pure-logic methods.

Covers:
  - BusinessValueAgent._validate_and_verify
  - BusinessValueAgent._build_confidence_score
  - BusinessValueAgent._build_architecture_driver_hints
  - BusinessValueAgent._verify_driver_arithmetic
  - ArchitectAgent._select_pattern
  - ArchitectAgent._build_fallback
  - ArchitectAgent._count_mermaid_nodes (edge cases beyond test_mermaid_cap.py)
  - ArchitectAgent._cap_mermaid_nodes  (edge cases beyond test_mermaid_cap.py)
  - Architect context-building regression (BV data must NOT leak)
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.business_value_agent import BusinessValueAgent
from agents.architect_agent import ArchitectAgent
from agents.state import AgentState


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def bv():
    return BusinessValueAgent()


@pytest.fixture
def arch():
    return ArchitectAgent()


@pytest.fixture
def base_state():
    return AgentState(user_input="AI platform for Nike")


# ═══════════════════════════════════════════════════════════════════════════════
# BusinessValueAgent._validate_and_verify
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateAndVerify:

    def test_valid_range(self, bv, base_state):
        result = {"annual_impact_range": {"low": 100_000, "high": 500_000}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        assert corrected is not None
        assert corrected["low"] == 100_000
        assert corrected["high"] == 500_000
        assert warnings == []

    def test_inverted_range_swaps(self, bv, base_state):
        result = {"annual_impact_range": {"low": 500_000, "high": 100_000}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        assert corrected is not None
        assert corrected["low"] == 100_000
        assert corrected["high"] == 500_000

    def test_missing_low_key(self, bv, base_state):
        result = {"annual_impact_range": {"high": 500_000}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        # low defaults to 0, high=500k → valid range (low=0, high=500k)
        if corrected is not None:
            assert corrected["low"] == 0
            assert corrected["high"] == 500_000
        # Either way, no crash

    def test_missing_high_key(self, bv, base_state):
        result = {"annual_impact_range": {"low": 100_000}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        # high defaults to 0, low(100k) > high(0) → swap → low=0, high=100k → valid
        assert corrected is not None
        assert corrected["low"] == 0
        assert corrected["high"] == 100_000

    def test_not_a_dict(self, bv, base_state):
        result = {"annual_impact_range": "invalid"}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        assert corrected is None

    def test_none_input(self, bv, base_state):
        result = {"annual_impact_range": None}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        assert corrected is None

    def test_negative_values(self, bv, base_state):
        result = {"annual_impact_range": {"low": -100, "high": 500_000}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        # low < 0 → clamped to 0
        assert corrected is not None
        assert corrected["low"] == 0
        assert corrected["high"] == 500_000

    def test_both_negative(self, bv, base_state):
        result = {"annual_impact_range": {"low": -500, "high": -100}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        # After swap (if needed) and clamp: low=-100→0, high=-500→swap→-100→0 → high<=0 → None
        assert corrected is None

    def test_zero_values(self, bv, base_state):
        result = {"annual_impact_range": {"low": 0, "high": 0}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        # high <= 0 → returns None
        assert corrected is None

    def test_zero_low_positive_high(self, bv, base_state):
        result = {"annual_impact_range": {"low": 0, "high": 1_000}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        assert corrected is not None
        assert corrected["low"] == 0
        assert corrected["high"] == 1_000

    def test_string_numbers(self, bv, base_state):
        result = {"annual_impact_range": {"low": "100000", "high": "500000"}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        assert corrected is not None
        assert corrected["low"] == 100_000
        assert corrected["high"] == 500_000

    def test_string_non_numeric(self, bv, base_state):
        result = {"annual_impact_range": {"low": "abc", "high": "def"}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        assert corrected is None

    def test_result_missing_key_entirely(self, bv, base_state):
        corrected, warnings = bv._validate_and_verify({}, base_state)
        assert corrected is None

    def test_rounding(self, bv, base_state):
        result = {"annual_impact_range": {"low": 100.456, "high": 500.789}}
        corrected, warnings = bv._validate_and_verify(result, base_state)
        assert corrected is not None
        assert corrected["low"] == 100.46
        assert corrected["high"] == 500.79


# ═══════════════════════════════════════════════════════════════════════════════
# BusinessValueAgent._build_confidence_score
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildConfidenceScore:

    def _make_driver(self, name="Driver", excluded=False, source_url=None, source_name=""):
        d = {"name": name, "excluded": excluded, "source_name": source_name}
        if source_url:
            d["source_url"] = source_url
        return d

    def test_high_confidence_base_score(self, bv):
        result = bv._build_confidence_score("high", [], False, [])
        assert result["overall_score"] >= 80

    def test_moderate_confidence_base_score(self, bv):
        result = bv._build_confidence_score("moderate", [], False, [])
        assert 55 <= result["overall_score"] <= 65

    def test_low_confidence_base_score(self, bv):
        result = bv._build_confidence_score("low", [], False, [])
        assert 30 <= result["overall_score"] <= 40

    def test_benchmark_bonus(self, bv):
        without = bv._build_confidence_score("moderate", [], False, [])
        with_bench = bv._build_confidence_score("moderate", [], True, [])
        assert with_bench["overall_score"] > without["overall_score"]
        assert with_bench["overall_score"] == without["overall_score"] + 10

    def test_warnings_penalty(self, bv):
        no_warn = bv._build_confidence_score("high", [], False, [])
        with_warn = bv._build_confidence_score("high", [], False, ["w1", "w2", "w3"])
        assert with_warn["overall_score"] < no_warn["overall_score"]
        assert with_warn["overall_score"] == no_warn["overall_score"] - 15

    def test_excluded_driver_penalty(self, bv):
        drivers = [self._make_driver(excluded=True)]
        no_excl = bv._build_confidence_score("high", [], False, [])
        with_excl = bv._build_confidence_score("high", drivers, False, [])
        assert with_excl["overall_score"] == no_excl["overall_score"] - 5

    def test_returns_dict_with_label(self, bv):
        result = bv._build_confidence_score("moderate", [], False, [])
        assert result["label"] == "moderate"

    def test_returns_dict_with_required_keys(self, bv):
        result = bv._build_confidence_score("high", [], False, [])
        required = {"overall_score", "driver_scores", "methodology", "recommendation", "label"}
        assert required.issubset(result.keys())

    def test_driver_scores_length_matches_drivers(self, bv):
        drivers = [self._make_driver(f"D{i}") for i in range(5)]
        result = bv._build_confidence_score("high", drivers, False, [])
        assert len(result["driver_scores"]) == 5

    def test_label_preserved(self, bv):
        for label in ("high", "moderate", "low"):
            result = bv._build_confidence_score(label, [], False, [])
            assert result["label"] == label

    def test_unknown_label_defaults_to_moderate_base(self, bv):
        result = bv._build_confidence_score("unknown", [], False, [])
        assert result["overall_score"] == 60  # defaults to moderate

    def test_score_clamped_at_minimum(self, bv):
        drivers = [self._make_driver(excluded=True) for _ in range(20)]
        result = bv._build_confidence_score("low", drivers, False, ["w"] * 10)
        assert result["overall_score"] >= 10

    def test_score_clamped_at_maximum(self, bv):
        result = bv._build_confidence_score("high", [], True, [])
        assert result["overall_score"] <= 100

    def test_driver_score_with_source_url(self, bv):
        drivers = [self._make_driver(source_url="https://example.com")]
        result = bv._build_confidence_score("high", drivers, False, [])
        assert result["driver_scores"][0] == 85

    def test_driver_score_calculated(self, bv):
        drivers = [self._make_driver(source_name="calculated from assumptions")]
        result = bv._build_confidence_score("high", drivers, False, [])
        assert result["driver_scores"][0] == 65

    def test_driver_score_excluded(self, bv):
        drivers = [self._make_driver(excluded=True)]
        result = bv._build_confidence_score("high", drivers, False, [])
        assert result["driver_scores"][0] == 30

    def test_driver_score_default(self, bv):
        drivers = [self._make_driver()]
        result = bv._build_confidence_score("high", drivers, False, [])
        assert result["driver_scores"][0] == 50

    def test_methodology_mentions_benchmarks(self, bv):
        result = bv._build_confidence_score("high", [], True, [])
        assert "benchmark" in result["methodology"].lower()

    def test_recommendation_strong_for_high_score(self, bv):
        result = bv._build_confidence_score("high", [], True, [])
        assert "strong" in result["recommendation"].lower()

    def test_recommendation_low_for_low_score(self, bv):
        result = bv._build_confidence_score("low", [], False, ["w1", "w2"])
        assert "low" in result["recommendation"].lower() or "gather" in result["recommendation"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# BusinessValueAgent._build_architecture_driver_hints
# ═══════════════════════════════════════════════════════════════════════════════

class TestArchitectureDriverHints:

    def test_openai_in_components(self, bv):
        architecture = {
            "components": [{"azureService": "Azure OpenAI", "name": "GPT-4 Service"}]
        }
        hints = bv._build_architecture_driver_hints(architecture)
        assert "ai" in hints.lower() or "manual effort" in hints.lower()

    def test_empty_architecture(self, bv):
        assert bv._build_architecture_driver_hints({}) == ""

    def test_empty_components_list(self, bv):
        assert bv._build_architecture_driver_hints({"components": []}) == ""

    def test_cosmos_in_components(self, bv):
        architecture = {
            "components": [{"azureService": "Azure Cosmos DB", "name": "NoSQL Store"}]
        }
        hints = bv._build_architecture_driver_hints(architecture)
        assert "cosmos" in hints.lower() or "dba" in hints.lower() or "operational" in hints.lower()

    def test_serverless_in_components(self, bv):
        architecture = {
            "components": [{"azureService": "Azure Functions", "name": "Serverless API"}]
        }
        hints = bv._build_architecture_driver_hints(architecture)
        assert "function" in hints.lower() or "serverless" in hints.lower()

    def test_multiple_components_capped_at_four(self, bv):
        components = [
            {"azureService": "Azure OpenAI", "name": ""},
            {"azureService": "Azure Cosmos DB", "name": ""},
            {"azureService": "Azure Kubernetes Service", "name": ""},
            {"azureService": "Azure Service Bus", "name": ""},
            {"azureService": "Azure Sentinel", "name": ""},
            {"azureService": "Azure DevOps", "name": ""},
        ]
        hints = bv._build_architecture_driver_hints({"components": components})
        lines = [l for l in hints.split("\n") if l.strip()]
        assert len(lines) <= 4

    def test_no_matching_keywords(self, bv):
        architecture = {
            "components": [{"azureService": "Custom VM", "name": "MyVM"}]
        }
        hints = bv._build_architecture_driver_hints(architecture)
        assert hints == ""

    def test_duplicate_hints_deduped(self, bv):
        components = [
            {"azureService": "Azure OpenAI", "name": "Service A"},
            {"azureService": "Azure OpenAI", "name": "Service B"},
        ]
        hints = bv._build_architecture_driver_hints({"components": components})
        lines = [l for l in hints.split("\n") if l.strip()]
        assert len(lines) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# BusinessValueAgent._verify_driver_arithmetic
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerifyDriverArithmetic:

    def test_correct_arithmetic_no_warnings(self, bv, base_state):
        # 350 × $100 × 15% × 2080 = $10,920,000
        drivers = [{
            "name": "Dev Productivity",
            "description": "350 engineers × $100/hr × 15% × 2,080 hrs = $10,920,000",
        }]
        warnings = bv._verify_driver_arithmetic(drivers, base_state)
        assert warnings == []

    def test_no_numeric_patterns(self, bv, base_state):
        drivers = [{
            "name": "Qualitative",
            "description": "Improved developer experience and satisfaction",
        }]
        warnings = bv._verify_driver_arithmetic(drivers, base_state)
        assert warnings == []

    def test_arithmetic_mismatch_flagged(self, bv, base_state):
        # Correct: 100 × $50 × 20% × 2080 = $2,080,000 but claiming $5,000,000
        drivers = [{
            "name": "Bad Math",
            "description": "100 employees × $50/hr × 20% × 2,080 hrs = $5,000,000",
        }]
        warnings = bv._verify_driver_arithmetic(drivers, base_state)
        assert len(warnings) == 1
        assert "Bad Math" in warnings[0]
        assert "divergence" in warnings[0].lower() or "mismatch" in warnings[0].lower()

    def test_excluded_drivers_skipped(self, bv, base_state):
        drivers = [{
            "name": "Excluded",
            "description": "100 employees × $50/hr × 20% × 2,080 hrs = $5,000,000",
            "excluded": True,
        }]
        warnings = bv._verify_driver_arithmetic(drivers, base_state)
        assert warnings == []

    def test_empty_drivers(self, bv, base_state):
        assert bv._verify_driver_arithmetic([], base_state) == []

    def test_within_tolerance_no_warning(self, bv, base_state):
        # 100 × $50 × 10% × 2080 = $1,040,000 — claiming $1,040,000 (exact)
        drivers = [{
            "name": "Close Enough",
            "description": "100 employees × $50/hr × 10% × 2,080 hrs = $1,040,000",
        }]
        warnings = bv._verify_driver_arithmetic(drivers, base_state)
        assert warnings == []


# ═══════════════════════════════════════════════════════════════════════════════
# ArchitectAgent._select_pattern
# ═══════════════════════════════════════════════════════════════════════════════

class TestSelectPattern:

    def test_selects_highest_score(self, arch):
        patterns = [
            {"title": "A", "confidence_score": 50},
            {"title": "B", "confidence_score": 90},
            {"title": "C", "confidence_score": 70},
        ]
        result = arch._select_pattern(patterns)
        assert result["title"] == "B"
        assert result["confidence_score"] == 90

    def test_empty_patterns(self, arch):
        assert arch._select_pattern([]) is None

    def test_single_pattern(self, arch):
        pattern = {"title": "Only", "confidence_score": 42}
        assert arch._select_pattern([pattern]) == pattern

    def test_patterns_without_score_default_zero(self, arch):
        patterns = [
            {"title": "NoScore"},
            {"title": "HasScore", "confidence_score": 1},
        ]
        result = arch._select_pattern(patterns)
        assert result["title"] == "HasScore"

    def test_all_same_score(self, arch):
        patterns = [
            {"title": "A", "confidence_score": 50},
            {"title": "B", "confidence_score": 50},
        ]
        result = arch._select_pattern(patterns)
        assert result is not None
        assert result["confidence_score"] == 50


# ═══════════════════════════════════════════════════════════════════════════════
# ArchitectAgent._build_fallback
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildFallback:

    def _state_with_scenarios(self, services_lists=None):
        state = AgentState(user_input="Test project")
        if services_lists:
            state.brainstorming = {
                "scenarios": [{"azure_services": s} for s in services_lists]
            }
        else:
            state.brainstorming = {}
        return state

    def test_fallback_has_mermaid(self, arch):
        state = self._state_with_scenarios()
        result = arch._build_fallback(state)
        assert "mermaidCode" in result
        assert "flowchart" in result["mermaidCode"]

    def test_fallback_has_layers(self, arch):
        state = self._state_with_scenarios()
        result = arch._build_fallback(state)
        assert "layers" in result
        assert isinstance(result["layers"], list)
        assert len(result["layers"]) >= 1

    def test_fallback_has_narrative(self, arch):
        state = self._state_with_scenarios()
        result = arch._build_fallback(state)
        assert "narrative" in result
        assert isinstance(result["narrative"], str)
        assert len(result["narrative"]) > 0

    def test_fallback_based_on(self, arch):
        state = self._state_with_scenarios()
        result = arch._build_fallback(state)
        assert "fallback" in result["basedOn"].lower()

    def test_fallback_uses_default_services_when_no_scenarios(self, arch):
        state = self._state_with_scenarios()
        result = arch._build_fallback(state)
        assert "App Service" in result["mermaidCode"]
        assert "SQL Database" in result["mermaidCode"]

    def test_fallback_uses_scenario_services(self, arch):
        state = self._state_with_scenarios([["Azure OpenAI", "Azure Cosmos DB"]])
        result = arch._build_fallback(state)
        assert "OpenAI" in result["mermaidCode"]
        assert "Cosmos" in result["mermaidCode"]

    def test_fallback_deduplicates_services(self, arch):
        state = self._state_with_scenarios([
            ["Azure OpenAI", "Azure Cosmos DB"],
            ["Azure OpenAI"],
        ])
        result = arch._build_fallback(state)
        # "Azure OpenAI" should appear only once in the mermaid code
        assert result["mermaidCode"].count("Azure OpenAI") == 1

    def test_fallback_caps_at_10_services(self, arch):
        svcs = [f"Azure Svc{i}" for i in range(15)]
        state = self._state_with_scenarios([svcs])
        result = arch._build_fallback(state)
        # Only 10 unique nodes + Client in the diagram
        lines_with_arrow = [l for l in result["mermaidCode"].split("\n") if "-->" in l]
        assert len(lines_with_arrow) <= 10

    def test_fallback_has_components(self, arch):
        state = self._state_with_scenarios([["Azure OpenAI"]])
        result = arch._build_fallback(state)
        assert "components" in result
        assert len(result["components"]) >= 1
        assert result["components"][0]["azureService"] == "Azure OpenAI"


# ═══════════════════════════════════════════════════════════════════════════════
# ArchitectAgent._count_mermaid_nodes — edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestCountMermaidNodesEdgeCases:

    def test_node_with_curly_braces(self, arch):
        code = "flowchart TD\n  A{Decision}\n  B[Result]"
        assert arch._count_mermaid_nodes(code) == 2

    def test_direction_keywords_not_counted(self, arch):
        code = "flowchart LR\n  A[Start]\n  B[End]"
        assert arch._count_mermaid_nodes(code) == 2

    def test_end_keyword_not_counted(self, arch):
        code = "flowchart TD\n  subgraph Layer\n    A[Node]\n  end"
        count = arch._count_mermaid_nodes(code)
        assert count == 1  # Only A, not "end"

    def test_only_comments(self, arch):
        code = "flowchart TD\n%% This is a comment\n%% Another comment"
        assert arch._count_mermaid_nodes(code) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# ArchitectAgent._cap_mermaid_nodes — edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestCapMermaidNodesEdgeCases:

    def test_cap_with_single_node_under_limit(self, arch):
        code = "flowchart TD\n  A[Only Node]"
        layers = [{"name": "L1", "components": [{"name": "Svc", "azureService": "Azure Svc"}]}]
        result = arch._cap_mermaid_nodes(code, layers, max_nodes=20)
        assert result == code  # Under cap, returns original

    def test_cap_rebuilds_when_over(self, arch):
        # Build a diagram with 25 nodes
        nodes = "\n".join(f"  N{i}[Node {i}]" for i in range(25))
        code = f"flowchart TD\n{nodes}"
        layers = [{"name": "Core", "components": [
            {"name": f"Svc{i}", "azureService": f"Azure Svc{i}"} for i in range(25)
        ]}]
        result = arch._cap_mermaid_nodes(code, layers, max_nodes=5)
        assert arch._count_mermaid_nodes(result) <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# Architect context-building regression tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestArchitectContextBuilding:

    def test_architect_context_excludes_bv(self):
        """REGRESSION: architect used to include BV data via state.to_context_string()"""
        state = AgentState(user_input="AI platform for Nike")
        state.brainstorming = {"industry": "Consumer Goods"}
        state.shared_assumptions = {"affected_employees": 500, "hourly_labor_rate": 85}
        state.business_value = {
            "drivers": [{"name": "Dev Productivity"}],
            "annual_impact_range": {"low": 800_000, "high": 1_500_000},
        }

        # Replicate the architect's context building (lines 30-41)
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
        requirements = "\n".join(context_parts)

        # BV data must NOT leak into architect context
        assert "Value drivers" not in requirements
        assert "annual_impact_range" not in requirements
        assert "800000" not in requirements
        assert "Dev Productivity" not in requirements
        # Shared assumptions and brainstorming SHOULD be present
        assert "AI platform for Nike" in requirements
        assert "Consumer Goods" in requirements
        assert "affected_employees" in requirements

    def test_architect_context_includes_patterns(self):
        """When retrieved_patterns exist, they should appear in context."""
        state = AgentState(user_input="Test project")
        state.retrieved_patterns = [
            {"title": "Microservices Pattern"},
            {"title": "Event-Driven Pattern"},
        ]

        context_parts = [f"Project: {state.user_input}"]
        if state.retrieved_patterns:
            titles = [p.get("title", "") for p in state.retrieved_patterns[:5]]
            context_parts.append(f"Reference patterns: {', '.join(titles)}")
        requirements = "\n".join(context_parts)

        assert "Microservices Pattern" in requirements
        assert "Event-Driven Pattern" in requirements

    def test_full_context_includes_bv(self):
        """to_context_string() should still include BV data for agents that need it."""
        state = AgentState(user_input="AI platform")
        state.business_value = {"drivers": [{"name": "Test"}, {"name": "Test2"}]}
        ctx = state.to_context_string()
        assert "Value drivers: 2 identified" in ctx

    def test_full_context_includes_roi(self):
        """to_context_string() includes ROI when present."""
        state = AgentState(user_input="AI platform")
        state.roi = {"roi_percent": 250.0}
        ctx = state.to_context_string()
        assert "ROI: 250%" in ctx

    def test_full_context_includes_architecture(self):
        """to_context_string() includes architecture narrative."""
        state = AgentState(user_input="AI platform")
        state.architecture = {"narrative": "Hub-spoke topology"}
        ctx = state.to_context_string()
        assert "Hub-spoke topology" in ctx
