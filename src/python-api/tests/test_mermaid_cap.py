"""Tests for ArchitectAgent mermaid node-cap utilities.

These are pure-function tests — no Azure credentials or LLM calls required.
"""

import sys
import os
from unittest.mock import MagicMock

# ── Stub out Azure-dependent modules before importing architect_agent ────────
sys.modules.setdefault("langchain_openai", MagicMock())
sys.modules.setdefault("agents.llm", MagicMock(llm=MagicMock()))
sys.modules.setdefault("services.mcp", MagicMock())
sys.modules.setdefault("services.web_search", MagicMock())
sys.modules.setdefault("data.knowledge_base", MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.architect_agent import ArchitectAgent  # noqa: E402


# ── _count_mermaid_nodes ────────────────────────────────────────────────

class TestCountMermaidNodes:
    def test_simple_flowchart(self):
        code = "flowchart TD\n  A[Service A]\n  B[Service B]\n  A --> B"
        assert ArchitectAgent._count_mermaid_nodes(code) == 2

    def test_node_defined_on_edge_line(self):
        # B is defined inline on the edge line
        code = "flowchart TD\n  A[Svc] --> B[Other]"
        # Both A and B have bracket definitions
        assert ArchitectAgent._count_mermaid_nodes(code) == 2

    def test_subgraph_headers_not_counted(self):
        code = (
            "flowchart TD\n"
            "  subgraph Layer1[Display]\n"
            "    A[Azure App Service]\n"
            "  end\n"
        )
        assert ArchitectAgent._count_mermaid_nodes(code) == 1

    def test_empty_diagram(self):
        assert ArchitectAgent._count_mermaid_nodes("flowchart TD") == 0

    def test_comments_ignored(self):
        code = "flowchart TD\n  %% This is a comment\n  A[Node]"
        assert ArchitectAgent._count_mermaid_nodes(code) == 1

    def test_large_diagram(self):
        # Build a diagram with 25 explicitly-defined nodes
        lines = ["flowchart TD"]
        for i in range(25):
            lines.append(f"  N{i}[Service {i}]")
        code = "\n".join(lines)
        assert ArchitectAgent._count_mermaid_nodes(code) == 25

    def test_duplicate_node_ids_counted_once(self):
        # Same ID referenced on two lines — should be counted once
        code = "flowchart TD\n  A[Svc]\n  A --> B[Other]"
        assert ArchitectAgent._count_mermaid_nodes(code) == 2


# ── _cap_mermaid_nodes ──────────────────────────────────────────────────

_SAMPLE_LAYERS = [
    {
        "name": "Frontend",
        "components": [
            {"name": "Web App", "azureService": "Azure App Service"},
            {"name": "CDN", "azureService": "Azure CDN"},
        ],
    },
    {
        "name": "API",
        "components": [
            {"name": "Gateway", "azureService": "Azure API Management"},
            {"name": "Functions", "azureService": "Azure Functions"},
        ],
    },
    {
        "name": "Data",
        "components": [
            {"name": "Database", "azureService": "Azure SQL Database"},
        ],
    },
]


class TestCapMermaidNodes:
    def test_under_cap_returns_original(self):
        code = "flowchart TD\n  A[App]\n  B[DB]\n  A --> B"
        result = ArchitectAgent._cap_mermaid_nodes(code, _SAMPLE_LAYERS, max_nodes=20)
        assert result == code

    def test_over_cap_returns_rebuilt_diagram(self):
        # Build a diagram with 25 nodes
        lines = ["flowchart TD"]
        for i in range(25):
            lines.append(f"  N{i}[Service {i}]")
        code = "\n".join(lines)

        result = ArchitectAgent._cap_mermaid_nodes(code, _SAMPLE_LAYERS, max_nodes=20)
        # Should be a new diagram rebuilt from layers
        assert result != code
        assert result.startswith("flowchart TD")

    def test_rebuilt_diagram_respects_cap(self):
        # 25-node diagram; layers have only 5 components total
        lines = ["flowchart TD"] + [f"  N{i}[S{i}]" for i in range(25)]
        code = "\n".join(lines)

        result = ArchitectAgent._cap_mermaid_nodes(code, _SAMPLE_LAYERS, max_nodes=20)
        node_count = ArchitectAgent._count_mermaid_nodes(result)
        assert node_count <= 20

    def test_rebuilt_diagram_contains_layer_services(self):
        lines = ["flowchart TD"] + [f"  N{i}[S{i}]" for i in range(25)]
        code = "\n".join(lines)

        result = ArchitectAgent._cap_mermaid_nodes(code, _SAMPLE_LAYERS, max_nodes=20)
        assert "Azure App Service" in result
        assert "Azure CDN" in result

    def test_rebuilt_diagram_has_subgraphs(self):
        lines = ["flowchart TD"] + [f"  N{i}[S{i}]" for i in range(25)]
        code = "\n".join(lines)

        result = ArchitectAgent._cap_mermaid_nodes(code, _SAMPLE_LAYERS, max_nodes=20)
        assert "subgraph" in result

    def test_exactly_at_cap_not_rebuilt(self):
        # 20-node diagram should not be rebuilt
        lines = ["flowchart TD"] + [f"  N{i}[S{i}]" for i in range(20)]
        code = "\n".join(lines)

        result = ArchitectAgent._cap_mermaid_nodes(code, _SAMPLE_LAYERS, max_nodes=20)
        assert result == code

    def test_small_cap_truncates_to_cap(self):
        # Force a tiny cap of 2 nodes; layers have 5 total
        lines = ["flowchart TD"] + [f"  N{i}[S{i}]" for i in range(10)]
        code = "\n".join(lines)

        result = ArchitectAgent._cap_mermaid_nodes(code, _SAMPLE_LAYERS, max_nodes=2)
        node_count = ArchitectAgent._count_mermaid_nodes(result)
        assert node_count <= 2

    def test_empty_layers_produces_minimal_diagram(self):
        lines = ["flowchart TD"] + [f"  N{i}[S{i}]" for i in range(25)]
        code = "\n".join(lines)

        # No layers to rebuild from — should still return a valid flowchart string
        result = ArchitectAgent._cap_mermaid_nodes(code, [], max_nodes=20)
        assert result.startswith("flowchart TD")
