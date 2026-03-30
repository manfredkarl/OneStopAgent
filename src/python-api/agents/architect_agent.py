"""System Architect Agent — use-case-specific layered Azure architecture.

Retrieves Microsoft reference architectures via:
1. MCP (Model Context Protocol) — Microsoft Learn server
2. Web search — DuckDuckGo for Azure Architecture Center content
3. Local knowledge base — 10 hardcoded reference patterns (last resort)

Then generates a layered architecture framed around the user's specific
scenario — not a generic bag of Azure services.
"""

import asyncio
import json
import logging
import re

from agents.llm import llm
from agents.state import AgentState
from services.mcp import mcp_client, MCPUnavailableError
from services.web_search import search_azure_architectures
from data.knowledge_base import search_local_patterns

logger = logging.getLogger(__name__)


class ArchitectAgent:
    name = "System Architect"
    emoji = "🏗️"

    def run(self, state: AgentState) -> AgentState:
        """Retrieve reference patterns, then generate layered architecture."""
        self._retrieve_patterns(state)

        try:
            pattern = self._select_pattern(state.retrieved_patterns)
            requirements = state.to_context_string()
            industry = state.brainstorming.get("industry", "Cross-Industry")
            scenarios = state.brainstorming.get("scenarios", [])
            state.architecture = self._generate_architecture(
                requirements, pattern, industry, scenarios,
                all_patterns=state.retrieved_patterns,
            )
        except Exception:
            logger.exception("ArchitectAgent failed — using fallback")
            state.architecture = self._build_fallback(state)

        return state

    async def run_streaming(
        self, state: AgentState, on_token
    ) -> AgentState:
        """Async streaming — runs full agent, then streams a narrative summary.

        Approach B per spec: the JSON architecture is generated synchronously,
        then a 2-3 sentence plain-text summary is streamed token-by-token via
        on_token(str) so the user sees text appearing while the diagram loads.
        """
        state = await asyncio.to_thread(self.run, state)

        narrative = state.architecture.get("narrative", "")
        based_on = state.architecture.get("basedOn", "")
        layer_count = len(state.architecture.get("layers", []))

        async for chunk in llm.astream([
            {
                "role": "system",
                "content": (
                    "You are an Azure solutions architect. "
                    "Summarize the following architecture in 2-3 sentences. "
                    "Be concise and specific to the use case. Plain text only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Layers: {layer_count}\n"
                    f"Narrative: {narrative}\n"
                    f"Based on: {based_on}\n\n"
                    "Summarize in 2-3 sentences."
                ),
            },
        ]):
            if chunk.content:
                on_token(chunk.content)

        return state

    # ── pattern retrieval ─────────────────────────────────────────────

    @staticmethod
    def _retrieve_patterns(state: AgentState) -> None:
        """Query MCP → web search → local KB for Azure patterns matching the use case."""
        query = f"{state.user_input} {state.clarifications}".strip()

        industry = state.brainstorming.get("industry", "")
        if industry and industry != "Cross-Industry":
            query += f" {industry}"

        # 1. Try MCP (Microsoft Learn server)
        try:
            patterns = mcp_client.search(query=query, top_k=5)
            logger.info("MCP returned %d patterns for query: %s", len(patterns), query[:50])
            state.retrieved_patterns = patterns
            return
        except MCPUnavailableError as e:
            logger.warning("MCP unavailable: %s — trying web search", e)

        # 2. Try web search for Azure Architecture Center content
        try:
            web_results = search_azure_architectures(query, max_results=5)
            if web_results:
                web_patterns = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "summary": r.get("snippet", ""),
                        "workload_type": "custom",
                        "industry": industry or "Cross-Industry",
                        "recommended_services": [],
                        "components": [],
                        "confidence_score": 0.7,
                        "_source": "web_search",
                    }
                    for r in web_results
                ]
                state.retrieved_patterns = web_patterns
                logger.info("Web search returned %d architecture references", len(web_patterns))
                return
        except Exception as e:
            logger.warning("Web search for architectures failed: %s", e)

        # 3. Last resort: local knowledge base
        local_patterns = search_local_patterns(query=query, top_k=5)
        for pattern in local_patterns:
            pattern["_source"] = "local"
            pattern["_ungrounded"] = True

        state.retrieved_patterns = local_patterns
        if local_patterns:
            logger.info("Local KB returned %d patterns (ungrounded)", len(local_patterns))
        else:
            logger.warning("No patterns found in any source")

    @staticmethod
    def _select_pattern(patterns: list[dict]) -> dict | None:
        if not patterns:
            return None
        # Prefer patterns from MCP or web search over local fallback
        sourced = [p for p in patterns if p.get("_source") != "local"]
        if sourced:
            return max(sourced, key=lambda p: p.get("confidence_score", 0.0))
        return max(patterns, key=lambda p: p.get("confidence_score", 0.0))

    # ── Layered architecture generation ───────────────────────────────

    @staticmethod
    def _generate_architecture(
        requirements: str,
        pattern: dict | None,
        industry: str,
        scenarios: list[dict],
        all_patterns: list[dict] | None = None,
    ) -> dict:
        """Generate a layered, use-case-framed architecture in one LLM call."""
        pattern_context = ""
        pattern_title = ""
        if pattern:
            pattern_title = pattern.get("title", "")
            pattern_context = (
                f"\nPRIMARY REFERENCE ARCHITECTURE: {pattern_title}\n"
                f"Summary: {pattern.get('summary', '')}\n"
                f"Recommended services: {', '.join(pattern.get('recommended_services', []))}\n"
                f"URL: {pattern.get('url', '')}\n\n"
                "ADAPT this reference architecture to the user's specific scenario.\n"
                "Mention by name which Microsoft pattern you adapted and why.\n"
            )

        # Include additional reference architectures from search
        additional_refs = ""
        if all_patterns and len(all_patterns) > 1:
            others = [p for p in all_patterns if p != pattern][:4]
            if others:
                additional_refs = "\nADDITIONAL REFERENCE ARCHITECTURES FOUND:\n"
                for p in others:
                    additional_refs += f"- {p.get('title', '')}: {p.get('summary', '')[:150]}\n"
                    if p.get('url'):
                        additional_refs += f"  URL: {p['url']}\n"
                additional_refs += "\nConsider these for additional patterns or components to incorporate.\n"

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
                    f"{additional_refs}"
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
                    "- 3-5 layers depending on the use case\n"
                    "- TOTAL components across ALL layers: 6-10\n"
                    "- Each layer should have 1-4 components\n"
                    "- Layer names should describe USE CASE FUNCTION, not generic IT tiers\n"
                    "  GOOD: 'AI & Agent Orchestration', 'Engineering Knowledge & PLM Grounding', 'Simulation & HPC'\n"
                    "  BAD:  'Compute Layer', 'Storage Layer', 'Networking Layer'\n"
                    "- Each component's 'role' explains WHY it's here for THIS scenario, not what Azure does generically\n\n"
                    "MERMAID RULES:\n"
                    "- Use 'flowchart TD' with subgraph blocks for each layer\n"
                    "- MUST use subgraphs — each layer is a subgraph block\n"
                    "- Maximum 12 nodes total\n"
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

        result = json.loads(text)

        # Validate mermaid
        mermaid = result.get("mermaidCode", "")
        mermaid = re.sub(r"^```(?:mermaid)?\s*\n?", "", mermaid)
        mermaid = re.sub(r"\n?```\s*$", "", mermaid)
        if not mermaid.strip().startswith(("flowchart", "graph")):
            mermaid = "flowchart TD\n" + mermaid

        layers = result.get("layers", [])
        if not isinstance(layers, list) or not layers:
            raise ValueError("No layers returned")

        # Server-side node cap: rebuild diagram if LLM exceeded the limit
        mermaid = ArchitectAgent._cap_mermaid_nodes(mermaid, layers)

        # Flatten components for downstream consumers (cost agent, etc.)
        all_components = []
        for layer in layers:
            for comp in layer.get("components", []):
                comp["layer"] = layer.get("name", "")
                comp.setdefault("description", comp.get("role", ""))
                all_components.append(comp)

        narrative = result.get("narrative", "")
        if not narrative:
            narrative = f"Layered Azure architecture with {len(layers)} functional layers."

        adapted = result.get("adaptedFrom") or (pattern_title if pattern else None)

        return {
            "mermaidCode": mermaid,
            "layers": layers,
            "components": all_components,
            "narrative": narrative,
            "basedOn": adapted or "custom design",
            "basedOnUrl": result.get("adaptedFromUrl") or (pattern.get("url") if pattern else None),
            "adaptationNotes": result.get("adaptationNotes"),
        }

    # ── Mermaid node cap ──────────────────────────────────────────────────

    @staticmethod
    def _count_mermaid_nodes(mermaid_code: str) -> int:
        """Count unique node IDs defined in a mermaid flowchart.

        Matches identifiers followed by a bracket/paren/brace (node definition
        syntax), excluding directive keywords like ``flowchart``, ``subgraph``,
        ``end``, etc.
        """
        skip = frozenset([
            "flowchart", "graph", "subgraph", "end", "classDef", "classdef",
            "style", "click", "linkStyle", "linkstyle", "direction",
        ])
        node_def_re = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\s*[\[({]")
        node_ids: set[str] = set()
        for line in mermaid_code.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("%%"):
                continue
            first_word = stripped.split()[0].lower().rstrip(":")
            if first_word in skip:
                continue
            for m in node_def_re.finditer(stripped):
                nid = m.group(1)
                if nid.lower() not in skip:
                    node_ids.add(nid)
        return len(node_ids)

    @staticmethod
    def _cap_mermaid_nodes(
        mermaid_code: str,
        layers: list[dict],
        max_nodes: int = 20,
    ) -> str:
        """Return *mermaid_code* unchanged if it has ≤ *max_nodes* nodes.

        If the LLM generated a diagram that exceeds the cap, rebuild a clean
        subgraph diagram from the validated *layers* data, capping at
        *max_nodes* total nodes.  This prevents the Mermaid frontend parser
        from crashing on oversized diagrams.
        """
        if ArchitectAgent._count_mermaid_nodes(mermaid_code) <= max_nodes:
            return mermaid_code

        # Rebuild a bounded diagram from validated layers data
        node_defs: list[str] = []
        layer_entries: list[tuple[str, list[str]]] = []
        total = 0

        for li, layer in enumerate(layers):
            components = layer.get("components", [])
            if not components or total >= max_nodes:
                break
            layer_name = layer.get("name", f"Layer{li + 1}")
            safe_name = re.sub(r'["\[\]{}]', "", layer_name)
            layer_node_ids: list[str] = []
            for comp in components:
                if total >= max_nodes:
                    break
                nid = f"N{total}"
                svc = comp.get("azureService") or comp.get("name") or "Service"
                safe_label = re.sub(r'[<>\[\]{}"\'\\n]', "", svc)[:40]
                node_defs.append(f"  {nid}[{safe_label}]")
                layer_node_ids.append(nid)
                total += 1
            if layer_node_ids:
                layer_entries.append((safe_name, layer_node_ids))

        # Assemble subgraph blocks
        body: list[str] = ["flowchart TD"]
        # Build lookup: node_id -> "  NX[Label]" (consistently indented)
        node_lookup: dict[str, str] = {}
        for defn in node_defs:
            nid = defn.strip().split("[")[0].strip()
            node_lookup[nid] = "    " + defn.strip()  # 4-space indent inside subgraph

        for name, nids in layer_entries:
            body.append(f"  subgraph {name}")
            for nid in nids:
                body.append(node_lookup.get(nid, f"    {nid}[Service]"))
            body.append("  end")

        # Connect adjacent layers with a single inter-layer arrow
        for i in range(len(layer_entries) - 1):
            src = layer_entries[i][1][-1]
            dst = layer_entries[i + 1][1][0]
            body.append(f"  {src} --> {dst}")

        return "\n".join(body)

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
        }
