"""System Architect Agent — generates Azure architecture with Mermaid diagrams.

Retrieves Microsoft reference architectures (via MCP or local fallback) and uses
them to ground architecture designs. Single LLM call produces Mermaid diagram,
components, and narrative together so they stay consistent.
"""

import json
import logging
import re

from agents.llm import llm
from agents.state import AgentState
from services.mcp import mcp_client, MCPUnavailableError
from data.knowledge_base import search_local_patterns

logger = logging.getLogger(__name__)


class ArchitectAgent:
    name = "System Architect"
    emoji = "🏗️"

    def run(self, state: AgentState) -> AgentState:
        """Retrieve reference patterns, then generate architecture grounded in them."""
        self._retrieve_patterns(state)

        try:
            pattern = self._select_pattern(state.retrieved_patterns)
            requirements = state.to_context_string()
            state.architecture = self._generate_architecture(requirements, pattern)
        except Exception:
            logger.exception("ArchitectAgent failed — using LLM-less fallback")
            state.architecture = self._build_fallback(state)

        return state

    # ── pattern retrieval (merged from KnowledgeAgent) ────────────────

    @staticmethod
    def _retrieve_patterns(state: AgentState) -> None:
        """Query MCP for Azure patterns matching the use case, with local fallback."""
        query = f"{state.user_input} {state.clarifications}".strip()

        industry = state.brainstorming.get("industry", "")
        if industry and industry != "Cross-Industry":
            query += f" {industry}"

        try:
            patterns = mcp_client.search(query=query, top_k=5)
            logger.info("MCP returned %d patterns for query: %s", len(patterns), query[:50])
            state.retrieved_patterns = patterns
            return
        except MCPUnavailableError as e:
            logger.warning("MCP unavailable, falling back to local knowledge base: %s", e)

        local_patterns = search_local_patterns(query=query, top_k=5)
        for pattern in local_patterns:
            pattern["_source"] = "local"
            pattern["_ungrounded"] = True

        state.retrieved_patterns = local_patterns
        if local_patterns:
            logger.info("Local KB returned %d patterns (ungrounded)", len(local_patterns))
        else:
            logger.warning("No patterns found in local knowledge base either")

    @staticmethod
    def _select_pattern(patterns: list[dict]) -> dict | None:
        if not patterns:
            return None
        return max(patterns, key=lambda p: p.get("confidence_score", 0.0))

    # ── Single LLM call for mermaid + components + narrative ──────────

    @staticmethod
    def _generate_architecture(requirements: str, pattern: dict | None) -> dict:
        """Generate mermaid, components, and narrative in one LLM call."""
        pattern_context = ""
        if pattern:
            pattern_context = (
                f"\nREFERENCE ARCHITECTURE: {pattern.get('title', '')}\n"
                f"Summary: {pattern.get('summary', '')}\n"
                f"Recommended services: {', '.join(pattern.get('recommended_services', []))}\n"
                f"Components: {json.dumps(pattern.get('components', []))}\n\n"
                "Base your design on this reference architecture. "
                "Adapt it to the user's specific requirements.\n"
            )

        response = llm.invoke([
            {
                "role": "system",
                "content": (
                    "You are an Azure solutions architect. Design a complete Azure architecture.\n"
                    f"{pattern_context}"
                    "Return ONLY valid JSON (no markdown fences) with this structure:\n"
                    "{\n"
                    '  "mermaidCode": "flowchart TD\\n  A[Client] --> B[Web App]\\n  ...",\n'
                    '  "components": [\n'
                    '    {"name": "Component Name", "azureService": "Azure Service Name", "description": "What it does"}\n'
                    "  ],\n"
                    '  "narrative": "2-3 sentence architecture description for a business audience."\n'
                    "}\n\n"
                    "MERMAID RULES:\n"
                    "- Use 'flowchart TD' syntax\n"
                    "- Maximum 15 nodes\n"
                    "- Each node label must be a specific Azure service name\n"
                    "- Show data flow between components with arrows (-->)\n"
                    "- Do NOT use HTML tags like <br> in node labels\n"
                    "- Node labels should be concise: e.g. [Azure SQL Database]\n"
                    "- Use unique single-letter or short IDs for nodes (A, B, C...)\n"
                    "- Every component in the components array MUST appear as a node in the diagram\n\n"
                    "COMPONENT RULES:\n"
                    "- Use real Azure service names (Azure App Service, Azure Cosmos DB, etc.)\n"
                    "- Include ALL services shown in the Mermaid diagram\n"
                    "- 5-15 components depending on complexity\n\n"
                    "NARRATIVE RULES:\n"
                    "- 2-3 sentences for a business audience\n"
                    "- Reference the specific Azure services used\n"
                    "- Mention the reference architecture if one was provided"
                ),
            },
            {"role": "user", "content": f"Design an Azure architecture for:\n{requirements}"},
        ])

        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result = json.loads(text)

        # Validate and clean the mermaid code
        mermaid = result.get("mermaidCode", "")
        mermaid = re.sub(r"^```(?:mermaid)?\s*\n?", "", mermaid)
        mermaid = re.sub(r"\n?```\s*$", "", mermaid)
        if not mermaid.strip().startswith(("flowchart", "graph")):
            mermaid = "flowchart TD\n" + mermaid

        components = result.get("components", [])
        if not isinstance(components, list) or not components:
            raise ValueError("No components returned")

        narrative = result.get("narrative", "")
        if not narrative:
            comp_names = ", ".join(c.get("azureService", c.get("name", "")) for c in components[:5])
            narrative = f"Azure architecture using {comp_names}."

        return {
            "mermaidCode": mermaid,
            "components": components,
            "narrative": narrative,
            "basedOn": pattern["title"] if pattern else "custom design",
        }

    # ── Fallback (LLM failure) ───────────────────────────────────────

    @staticmethod
    def _build_fallback(state: AgentState) -> dict:
        """Build a fallback architecture from brainstorming scenarios if available."""
        scenarios = state.brainstorming.get("scenarios", [])

        # Try to build something useful from the scenarios' azure_services
        services: list[str] = []
        for s in scenarios:
            services.extend(s.get("azure_services", []))

        if not services:
            services = ["Azure App Service", "Azure SQL Database", "Azure Cache for Redis"]

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_services: list[str] = []
        for svc in services:
            if svc not in seen:
                seen.add(svc)
                unique_services.append(svc)

        # Build simple mermaid from services
        lines = ["flowchart TD", "  Client[Client Browser]"]
        components = []
        prev_id = "Client"
        for i, svc in enumerate(unique_services[:12]):
            node_id = chr(65 + i)  # A, B, C, ...
            lines.append(f"  {prev_id} --> {node_id}[{svc}]")
            components.append({
                "name": svc.replace("Azure ", ""),
                "azureService": svc,
                "description": f"Managed {svc.replace('Azure ', '').lower()} service",
            })
            prev_id = node_id

        return {
            "mermaidCode": "\n".join(lines),
            "components": components,
            "narrative": (
                f"Architecture using {', '.join(unique_services[:4])} "
                "to deliver a scalable Azure solution. "
                "⚠️ Generated from fallback — review and refine."
            ),
            "basedOn": "fallback (LLM unavailable)",
        }
