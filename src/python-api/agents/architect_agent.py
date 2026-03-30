"""System Architect Agent — use-case-specific layered Azure architecture.

Retrieves Microsoft reference architectures (via MCP or local fallback),
then generates a layered architecture framed around the user's specific
scenario — not a generic bag of Azure services.
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
        """Retrieve reference patterns, then generate layered architecture."""
        self._retrieve_patterns(state)

        try:
            industry = state.brainstorming.get("industry", "Cross-Industry")
            pattern = self._select_pattern(state.retrieved_patterns, industry)
            requirements = state.to_context_string()
            scenarios = state.brainstorming.get("scenarios", [])
            state.architecture = self._generate_architecture(
                requirements, pattern, industry, scenarios,
            )
        except Exception:
            logger.exception("ArchitectAgent failed — using fallback")
            state.architecture = self._build_fallback(state)

        return state

    # ── pattern retrieval ─────────────────────────────────────────────

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

    # Domain keywords used to detect cross-domain mismatches between a
    # reference pattern and the user's stated industry.
    _DOMAIN_KEYWORDS: dict[str, list[str]] = {
        "Healthcare": ["patient", "telehealth", "clinical", "fhir", "hipaa", "health", "medical", "ehr"],
        "Retail": ["e-commerce", "ecommerce", "storefront", "shopping", "cart", "product recommendation"],
        "Financial Services": ["fraud", "transaction", "banking", "payment", "fintech"],
        "Manufacturing": ["iot", "telemetry", "factory", "sensor", "plc", "scada", "plant"],
    }

    @classmethod
    def _select_pattern(cls, patterns: list[dict], industry: str = "") -> dict | None:
        """Pick the best pattern, but only if it's actually relevant."""
        if not patterns:
            return None

        best = max(patterns, key=lambda p: p.get("confidence_score", 0.0))

        # Low-confidence patterns are not trustworthy
        if best.get("confidence_score", 0.0) < 0.3:
            logger.info("Best pattern '%s' below relevance threshold (%.2f)",
                        best.get("title", ""), best.get("confidence_score", 0.0))
            return None

        # Cross-domain mismatch check: if the pattern is from a specific
        # industry that clearly doesn't match the user's industry, reject it.
        pattern_industry = best.get("industry", "Cross-Industry")
        if pattern_industry != "Cross-Industry" and industry:
            industry_lower = industry.lower()
            pattern_title_lower = best.get("title", "").lower()
            # Check if the pattern's domain keywords appear in its title
            # but the user's industry is different
            for domain, keywords in cls._DOMAIN_KEYWORDS.items():
                if domain.lower() == pattern_industry.lower() and domain.lower() != industry_lower:
                    if any(kw in pattern_title_lower for kw in keywords):
                        logger.info("Rejecting pattern '%s' (%s) — mismatches user industry '%s'",
                                    best.get("title", ""), pattern_industry, industry)
                        return None

        return best

    # ── Layered architecture generation ───────────────────────────────

    @staticmethod
    def _generate_architecture(
        requirements: str,
        pattern: dict | None,
        industry: str,
        scenarios: list[dict],
    ) -> dict:
        """Generate a layered, use-case-framed architecture in one LLM call."""
        pattern_context = ""
        pattern_title = ""
        pattern_relevant = False
        if pattern:
            pattern_title = pattern.get("title", "")
            pattern_relevant = True
            pattern_context = (
                f"\nREFERENCE ARCHITECTURE: {pattern_title}\n"
                f"Summary: {pattern.get('summary', '')}\n"
                f"Recommended services: {', '.join(pattern.get('recommended_services', []))}\n"
                f"URL: {pattern.get('url', '')}\n\n"
                "Use this reference architecture as STRUCTURAL INSPIRATION if relevant, "
                "but design the architecture for the actual use case. "
                "If the reference pattern is from a different domain (e.g., healthcare for a "
                "manufacturing use case), ignore the pattern name and design from scratch "
                "based on Azure best practices.\n"
            )
        else:
            pattern_context = (
                "\nNo closely matching reference architecture was found.\n"
                "Design the architecture from scratch using Azure Well-Architected Framework "
                "best practices and services appropriate for the stated industry and use case.\n"
            )

        scenario_context = ""
        if scenarios:
            scenario_context = "BRAINSTORMED SCENARIOS:\n"
            for s in scenarios[:3]:
                scenario_context += f"- {s.get('title', '')}: {s.get('description', '')}\n"

        response = llm.invoke([
            {
                "role": "system",
                "content": (
                    "You are an Azure solutions architect. You design architectures that are SPECIFIC to the customer's use case.\n\n"
                    "KEY PRINCIPLE: Every architecture decision must be explained in the context of the use case.\n"
                    "Do NOT produce a generic list of Azure services. Instead, organize around functional LAYERS\n"
                    "that map to what the customer is actually trying to do.\n\n"
                    f"INDUSTRY: {industry}\n"
                    f"{pattern_context}"
                    f"{scenario_context}\n"
                    "Return ONLY valid JSON (no markdown fences) with this structure:\n"
                    "{\n"
                    '  "layers": [\n'
                    "    {\n"
                    '      "name": "Layer name (e.g. User & Engineering Experience)",\n'
                    '      "purpose": "1 sentence: what this layer does FOR THIS USE CASE",\n'
                    '      "components": [\n'
                    '        {"name": "Component Name", "azureService": "Azure Service Name", "role": "What this component does for the use case (1 sentence)"}\n'
                    "      ]\n"
                    "    }\n"
                    "  ],\n"
                    '  "mermaidCode": "flowchart TD\\n  subgraph Layer1[...]\\n  ...",\n'
                    '  "narrative": "2-3 sentences framing this architecture for the specific use case.",\n'
                    '  "adaptedFrom": "Name of Microsoft reference pattern adapted, or null",\n'
                    '  "adaptedFromUrl": "URL to the reference pattern, or null",\n'
                    '  "adaptationNotes": "1-2 sentences on what was adapted and why, or null"\n'
                    "}\n\n"
                    "LAYER GUIDELINES:\n"
                    "- 3-6 layers depending on the use case\n"
                    "- Each layer should have 1-4 components (keep it lean — not every service needs to show early)\n"
                    "- Layer names should describe USE CASE FUNCTION, not generic IT tiers\n"
                    "  GOOD: 'AI & Agent Orchestration', 'Engineering Knowledge & PLM Grounding', 'Simulation & HPC'\n"
                    "  BAD:  'Compute Layer', 'Storage Layer', 'Networking Layer'\n"
                    "- Each component's 'role' explains WHY it's here for THIS scenario, not what Azure does generically\n\n"
                    "MERMAID RULES:\n"
                    "- Use 'flowchart TD' with subgraph blocks for each layer\n"
                    "- Maximum 15 nodes total\n"
                    "- Subgraph labels = layer names\n"
                    "- Node labels = short Azure service name (e.g. [Azure AI Search])\n"
                    "- Show data flow between layers with arrows (-->)\n"
                    "- Do NOT use HTML tags like <br> in labels\n"
                    "- Use unique short IDs (A, B, C... or descriptive like PLM, HPC)\n\n"
                    "NARRATIVE RULES:\n"
                    "- Open with 'This architecture is designed for [specific use case]...'\n"
                    "- Reference the adapted pattern if one was provided\n"
                    "- Mention the key differentiating layers"
                ),
            },
            {"role": "user", "content": f"Design a layered Azure architecture for:\n{requirements}"},
        ])

        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("LLM returned invalid architecture JSON: %s", text[:200])
            raise ValueError(f"Invalid architecture JSON from LLM") from e

        # Validate mermaid
        mermaid = result.get("mermaidCode", "")
        mermaid = re.sub(r"^```(?:mermaid)?\s*\n?", "", mermaid)
        mermaid = re.sub(r"\n?```\s*$", "", mermaid)
        if not mermaid.strip().startswith(("flowchart", "graph")):
            mermaid = "flowchart TD\n" + mermaid

        layers = result.get("layers", [])
        if not isinstance(layers, list) or not layers:
            raise ValueError("No layers returned")

        # Flatten components for downstream consumers (cost agent, etc.)
        all_components = []
        for layer in layers:
            for comp in layer.get("components", []):
                comp["layer"] = layer.get("name", "")
                comp.setdefault("description", comp.get("role", ""))
                all_components.append(comp)

        # Validate each component has required fields
        validated = []
        for comp in all_components:
            comp.setdefault("name", comp.get("azureService", "Unknown"))
            comp.setdefault("azureService", comp.get("name", "Unknown"))
            comp.setdefault("role", "")
            comp.setdefault("description", comp.get("role", ""))
            validated.append(comp)
        all_components = validated

        narrative = result.get("narrative", "")
        if not narrative:
            narrative = f"Layered Azure architecture with {len(layers)} functional layers."

        adapted = result.get("adaptedFrom") or (pattern_title if pattern_relevant else None)

        # When no relevant pattern was found, attribute to Azure best practices
        if pattern_relevant:
            based_on = adapted or "custom design"
            based_on_url = result.get("adaptedFromUrl") or (pattern.get("url") if pattern else None)
            adaptation_notes = result.get("adaptationNotes")
        else:
            based_on = "Azure Well-Architected Framework"
            based_on_url = "https://learn.microsoft.com/azure/well-architected/"
            adaptation_notes = f"Architecture designed from Azure best practices for {industry}"

        return {
            "mermaidCode": mermaid,
            "layers": layers,
            "components": all_components,
            "narrative": narrative,
            "basedOn": based_on,
            "basedOnUrl": based_on_url,
            "adaptationNotes": adaptation_notes,
        }

    # ── Fallback ──────────────────────────────────────────────────────

    @staticmethod
    def _build_fallback(state: AgentState) -> dict:
        """Build a fallback architecture from brainstorming scenarios."""
        scenarios = state.brainstorming.get("scenarios", [])

        services: list[str] = []
        for s in scenarios:
            services.extend(s.get("azure_services", []))

        if not services:
            services = ["Azure App Service", "Azure SQL Database", "Azure Cache for Redis"]

        seen: set[str] = set()
        unique: list[str] = []
        for svc in services:
            if svc not in seen:
                seen.add(svc)
                unique.append(svc)

        lines = ["flowchart TD", "  Client[Client Browser]"]
        components = []
        prev_id = "Client"
        for i, svc in enumerate(unique[:10]):
            node_id = chr(65 + i)
            lines.append(f"  {prev_id} --> {node_id}[{svc}]")
            components.append({
                "name": svc.replace("Azure ", ""),
                "azureService": svc,
                "description": f"Managed {svc.replace('Azure ', '').lower()} service",
                "role": f"Managed {svc.replace('Azure ', '').lower()} service",
            })
            prev_id = node_id

        return {
            "mermaidCode": "\n".join(lines),
            "layers": [{"name": "Core Services", "purpose": "Primary Azure services", "components": components}],
            "components": components,
            "narrative": (
                f"Architecture using {', '.join(unique[:4])} "
                "to deliver a scalable Azure solution. "
                "⚠️ Generated from fallback — review and refine."
            ),
            "basedOn": "fallback (LLM unavailable)",
            "basedOnUrl": None,
            "adaptationNotes": "Generated from fallback when primary architecture generation was unavailable.",
        }
