"""System Architect Agent — generates Azure architecture with Mermaid diagrams.

Reads retrieved_patterns from KnowledgeAgent (FRD-03 §2) to ground designs
in published Microsoft reference architectures.
"""

import json
import logging
import re

from agents.llm import llm
from agents.state import AgentState

logger = logging.getLogger(__name__)

# §2.5 — used when LLM is completely unavailable
FALLBACK_ARCHITECTURE = {
    "mermaidCode": (
        "flowchart TD\n"
        "  A[Client] --> B[Web App]\n"
        "  B --> C[API Layer]\n"
        "  C --> D[Database]\n"
        "  C --> E[Cache]"
    ),
    "components": [
        {"name": "Web App", "azureService": "Azure App Service", "description": "Web application frontend"},
        {"name": "API Layer", "azureService": "Azure App Service", "description": "REST API backend"},
        {"name": "Database", "azureService": "Azure SQL Database", "description": "Relational data storage"},
        {"name": "Cache", "azureService": "Azure Cache for Redis", "description": "Performance caching"},
    ],
    "narrative": "A standard three-tier Azure architecture with web frontend, API layer, and managed database.",
    "basedOn": "custom design",
}


class ArchitectAgent:
    name = "System Architect"
    emoji = "🏗️"

    # ── public entry point ───────────────────────────────────────────

    def run(self, state: AgentState) -> AgentState:
        """Generate architecture grounded in retrieved patterns (§2)."""
        try:
            pattern = self._select_pattern(state.retrieved_patterns)
            requirements = state.to_context_string()

            mermaid_code = self._generate_mermaid(requirements, pattern)
            components = self._extract_components(requirements, pattern)
            narrative = self._generate_narrative(requirements, components, pattern)

            state.architecture = {
                "mermaidCode": mermaid_code,
                "components": components,
                "narrative": narrative,
                "basedOn": pattern["title"] if pattern else "custom design",
            }
        except Exception:
            logger.exception("ArchitectAgent failed — using fallback template")
            state.architecture = dict(FALLBACK_ARCHITECTURE)

        return state

    # ── §2.3.1 pattern selection ─────────────────────────────────────

    @staticmethod
    def _select_pattern(patterns: list[dict]) -> dict | None:
        """Select the pattern with the highest confidence_score."""
        if not patterns:
            return None
        return max(patterns, key=lambda p: p.get("confidence_score", 0.0))

    # ── §2.3.2 Mermaid generation ────────────────────────────────────

    @staticmethod
    def _generate_mermaid(requirements: str, pattern: dict | None) -> str:
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
                    "Generate a Mermaid flowchart TD diagram for an Azure architecture.\n"
                    f"{pattern_context}"
                    "RULES:\n"
                    "- Use 'flowchart TD' syntax\n"
                    "- Maximum 20 nodes\n"
                    "- Include specific Azure service names as nodes\n"
                    "- Show data flow between components\n"
                    "- Return ONLY the Mermaid code, no markdown fences, no explanation"
                ),
            },
            {"role": "user", "content": f"Design an Azure architecture for: {requirements}"},
        ])

        code = response.content.strip()

        # Fence cleanup (§2.3.2)
        code = re.sub(r"^```(?:mermaid)?\s*\n?", "", code)
        code = re.sub(r"\n?```\s*$", "", code)

        if not code.strip().startswith(("flowchart", "graph")):
            code = "flowchart TD\n" + code

        node_count = len(re.findall(r"^\s*\w+[\[\(\{]", code, re.MULTILINE))
        if node_count > 20:
            logger.warning("Mermaid diagram has %d nodes (max 20)", node_count)

        return code

    # ── §2.3.3 component extraction ──────────────────────────────────

    @staticmethod
    def _extract_components(requirements: str, pattern: dict | None) -> list[dict]:
        try:
            response = llm.invoke([
                {
                    "role": "system",
                    "content": (
                        "Extract Azure architecture components. Return ONLY a JSON array: "
                        '[{"name": "...", "azureService": "...", "description": "..."}]'
                    ),
                },
                {"role": "user", "content": requirements},
            ])
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            components = json.loads(text)
            if not isinstance(components, list):
                raise ValueError("Expected JSON array")
            return components
        except (json.JSONDecodeError, ValueError, Exception):
            if pattern and pattern.get("components"):
                return pattern["components"]
            return [
                {"name": "Web Frontend", "azureService": "Azure App Service", "description": "Web hosting"},
                {"name": "API Backend", "azureService": "Azure App Service", "description": "API layer"},
                {"name": "Database", "azureService": "Azure SQL Database", "description": "Data storage"},
            ]

    # ── §2.3.4 narrative generation ──────────────────────────────────

    @staticmethod
    def _generate_narrative(
        requirements: str, components: list[dict], pattern: dict | None
    ) -> str:
        pattern_note = ""
        if pattern:
            pattern_note = (
                f"This design is based on the '{pattern['title']}' "
                "reference architecture from Microsoft. "
            )
        try:
            response = llm.invoke([
                {
                    "role": "system",
                    "content": (
                        "Write a 2-3 sentence architecture description for a business audience. "
                        f"{pattern_note}"
                        "Be specific about Azure services used."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Components: {json.dumps(components)}\nFor: {requirements}",
                },
            ])
            return response.content.strip()
        except Exception:
            comp_names = ", ".join(
                c.get("azureService", c.get("name", "")) for c in components[:5]
            )
            base = f"Based on '{pattern['title']}'" if pattern else "Custom Azure architecture"
            return f"{base} using {comp_names} to deliver a scalable, secure solution."
