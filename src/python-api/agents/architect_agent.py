"""System Architect Agent — use-case-specific layered Azure architecture.

Retrieves Microsoft reference architectures (via MCP or local fallback),
then generates a layered architecture framed around the user's specific
scenario — not a generic bag of Azure services.
"""

import json
import logging
import re

from agents.llm import llm, parse_llm_json
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
            pattern = self._select_pattern(state.retrieved_patterns)
            # Build clean context for architect — exclude BV/cost/ROI data
            context_parts = [f"Project: {state.user_input}"]
            if state.brainstorming:
                context_parts.append(f"Industry: {state.brainstorming.get('industry', 'Cross-Industry')}")
            if state.shared_assumptions:
                sa_items = [f"  {k}: {v}" for k, v in state.shared_assumptions.items() if not k.startswith("_")]
                if sa_items:
                    context_parts.append("Shared assumptions:\n" + "\n".join(sa_items))
            if state.retrieved_patterns:
                titles = [p.get("title", "") for p in state.retrieved_patterns[:5]]
                context_parts.append(f"Reference patterns: {', '.join(titles)}")
            requirements = "\n".join(context_parts)
            industry = state.brainstorming.get("industry", "Cross-Industry")
            scenarios = state.brainstorming.get("scenarios", [])
            state.architecture = self._generate_architecture(
                requirements, pattern, industry, scenarios,
                shared_assumptions=state.shared_assumptions,
                company_profile=state.company_profile,
            )
        except (json.JSONDecodeError, ValueError, KeyError, TypeError, OSError, ConnectionError, TimeoutError):
            logger.exception("ArchitectAgent failed — using fallback")
            state.architecture = self._build_fallback(state)

        return state

    # ── pattern retrieval ─────────────────────────────────────────────

    @staticmethod
    def _retrieve_patterns(state: AgentState) -> None:
        """QI-7: Multi-query MCP search — separate functional, scale, and compliance queries.

        Merges results, deduplicates by URL, and ranks by confidence_score.
        Falls back to local knowledge base when MCP is unavailable.
        """
        base_query = f"{state.user_input} {state.clarifications}".strip()
        industry = state.brainstorming.get("industry", "")
        if industry and industry != "Cross-Industry":
            base_query += f" {industry}"

        # Extract scale hints
        scale_hint = ""
        full_text = base_query.lower()
        import re as _re
        m = _re.search(r'(\d[\d,]*)\s*(?:concurrent|simultaneous)?\s*users', full_text)
        if m:
            scale_hint = f"high-scale {m.group(1)} concurrent users"

        # Extract compliance hints
        compliance_keywords = ["hipaa", "gdpr", "pci", "soc2", "iso27001", "fedramp", "compliance"]
        compliance_terms = [kw for kw in compliance_keywords if kw in full_text]
        compliance_hint = " ".join(compliance_terms) + " Azure" if compliance_terms else ""

        # Build targeted queries
        queries: list[str] = [base_query]
        if scale_hint:
            queries.append(f"{state.user_input[:80]} {scale_hint} Azure architecture")
        if compliance_hint:
            queries.append(f"{state.user_input[:80]} {compliance_hint}")

        try:
            seen_urls: set[str] = set()
            all_patterns: list[dict] = []

            for q in queries:
                try:
                    results = mcp_client.search(query=q, top_k=3)
                    for p in results:
                        url = p.get("url", "")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            all_patterns.append(p)
                except MCPUnavailableError:
                    raise  # re-raise to trigger local fallback

            # Sort by confidence and cap at top 5
            all_patterns.sort(key=lambda p: p.get("confidence_score", 0.0), reverse=True)
            logger.info(
                "MCP multi-query returned %d unique patterns from %d queries",
                len(all_patterns), len(queries),
            )
            state.retrieved_patterns = all_patterns[:5]
            return

        except MCPUnavailableError as e:
            logger.warning("MCP unavailable, falling back to local knowledge base: %s", e)

        local_patterns = search_local_patterns(query=base_query, top_k=5)
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

    # ── Layered architecture generation ───────────────────────────────

    @staticmethod
    def _generate_architecture(
        requirements: str,
        pattern: dict | None,
        industry: str,
        scenarios: list[dict],
        shared_assumptions: dict | None = None,
        company_profile: dict | None = None,
    ) -> dict:
        """Generate a layered, use-case-framed architecture in one LLM call."""
        pattern_context = ""
        pattern_title = ""
        if pattern:
            pattern_title = pattern.get("title", "")
            pattern_context = (
                f"\nREFERENCE ARCHITECTURE: {pattern_title}\n"
                f"Summary: {pattern.get('summary', '')}\n"
                f"Recommended services: {', '.join(pattern.get('recommended_services', []))}\n"
                f"URL: {pattern.get('url', '')}\n\n"
                "ADAPT this reference architecture to the user's specific scenario.\n"
                "Mention by name which Microsoft pattern you adapted and why.\n"
            )

        # Add scale context from shared assumptions
        scale_context = ""
        sa = shared_assumptions or {}
        if sa:
            scale_parts = []
            for k, v in sa.items():
                if k.startswith("_"):
                    continue
                kl = k.lower()
                try:
                    fv = float(v)
                except (ValueError, TypeError):
                    continue
                if ("user" in kl or "engineer" in kl) and fv > 1:
                    scale_parts.append(f"- Total users: {int(fv)}")
                elif "concurrent" in kl and fv > 1:
                    scale_parts.append(f"- Peak concurrent users: {int(fv)}")
                elif ("volume" in kl or "storage" in kl or "data" in kl) and "gb" in kl and fv > 0:
                    scale_parts.append(f"- Data volume: {int(fv)} GB")
            if scale_parts:
                scale_context = "SCALE REQUIREMENTS (from shared assumptions):\n" + "\n".join(scale_parts) + "\nDesign the architecture to handle this scale appropriately.\n\n"

        # Add company profile scale context — architecture-only (no financial data)
        if company_profile:
            p = company_profile
            company_lines = [f"CUSTOMER SCALE ({p.get('name', 'Company')}):"]
            if p.get("employeeCount"):
                company_lines.append(f"- {p['employeeCount']:,} total employees")
            if p.get("headquarters"):
                company_lines.append(f"- HQ: {p['headquarters']} — consider data residency/compliance")
            if p.get("knownAzureUsage"):
                company_lines.append(f"- Known Azure services: {', '.join(p['knownAzureUsage'][:4])}")
            if p.get("erp"):
                company_lines.append(f"- ERP: {p['erp']} — consider integration requirements")
            if p.get("techStackNotes"):
                company_lines.append(f"- Tech notes: {p['techStackNotes']}")
            scale_context += "\n".join(company_lines) + "\n\n"

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
                    f"{scale_context}"
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
                    '  "adaptationNotes": "1-2 sentences on what was adapted and why, or null",\n'
                    '  "nfr": {\n'
                    '    "security": {"zones": ["zone1"], "identity": "e.g. Microsoft Entra ID + RBAC", "encryption": "e.g. TLS 1.3 in transit, AES-256 at rest"},\n'
                    '    "compliance": {"frameworks": ["e.g. GDPR", "HIPAA"], "controls": ["e.g. Purview for data governance"]},\n'
                    '    "ha": {"drStrategy": "e.g. Active-passive with Azure Site Recovery", "rpo": "e.g. 15 min", "rto": "e.g. 1 hr"},\n'
                    '    "monitoring": {"observability": "e.g. Azure Monitor + Application Insights", "alerting": "e.g. Action Groups"}\n'
                    "  }\n"
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
                    "- ALWAYS add connection type labels on arrows — use the pipe syntax:\n"
                    "    A -->|REST API| B\n"
                    "    C -->|Event Stream| D\n"
                    "    E -->|Queue Messages| F\n"
                    "    G -->|gRPC| H\n"
                    "    I -->|SQL Query| J\n"
                    "    K -->|Vector Search| L\n"
                    "  Choose the label that best describes what flows between the nodes\n"
                    "- Do NOT use HTML tags like <br> in labels\n"
                    "- Use unique short IDs (A, B, C... or descriptive like PLM, HPC)\n\n"
                    "NARRATIVE RULES:\n"
                    "- Open with 'This architecture is designed for [specific use case]...'\n"
                    "- Reference the adapted pattern if one was provided\n"
                    "- Mention the key differentiating layers\n"
                    "- Do NOT include business value metrics, dollar amounts, ROI, savings estimates,\n"
                    "  or value driver language. Focus purely on technical architecture.\n"
                    "- Do NOT reference staff counts, headcount reduction, or cost reduction outcomes"
                ),
            },
            {"role": "user", "content": f"Design a layered Azure architecture for:\n{requirements}"},
        ])

        result = parse_llm_json(response.content, label="ArchitectAgent")
        if result is None:
            logger.error("LLM returned invalid architecture JSON: %s", response.content[:200])
            raise ValueError("Invalid architecture JSON from LLM")

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

        adapted = result.get("adaptedFrom") or (pattern_title if pattern else None)

        # QI-6: capture NFR section
        nfr = result.get("nfr", {})

        return {
            "mermaidCode": mermaid,
            "layers": layers,
            "components": all_components,
            "narrative": narrative,
            "basedOn": adapted or "custom design",
            "basedOnUrl": result.get("adaptedFromUrl") or (pattern.get("url") if pattern else None),
            "adaptationNotes": result.get("adaptationNotes"),
            "nfr": nfr,
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

    # ── Mermaid node utilities (tested via test_mermaid_cap.py) ──────

    _NODE_PATTERN = re.compile(
        r'(?:^|\s)(\w+)\s*'                    # node ID
        r'(?:\[|{|>|\()'                         # opening bracket
        r'[^\[\]{}()\n]*'                        # label contents
        r'(?:\]|}|\))',                           # closing bracket
        re.MULTILINE,
    )
    _SUBGRAPH_PATTERN = re.compile(r'^\s*subgraph\s', re.MULTILINE)
    _COMMENT_PATTERN = re.compile(r'%%[^\n]*')

    @classmethod
    def _count_mermaid_nodes(cls, code: str) -> int:
        """Count the number of unique labelled nodes in a Mermaid diagram.

        Subgraph header lines (subgraph Name[Label]) and comment lines (%%) are excluded.
        Each unique node ID that has a label definition is counted once.
        """
        # Strip comments
        clean = cls._COMMENT_PATTERN.sub("", code)

        # Remove subgraph declaration lines so their IDs aren't counted
        clean = cls._SUBGRAPH_PATTERN.sub("~~SUBGRAPH~~", clean)

        seen: set[str] = set()
        for m in cls._NODE_PATTERN.finditer(clean):
            node_id = m.group(1)
            if node_id not in ("~~SUBGRAPH~~", "end", "TD", "LR", "TB", "RL", "BT"):
                seen.add(node_id)
        return len(seen)

    @classmethod
    def _cap_mermaid_nodes(
        cls, code: str, layers: list[dict], max_nodes: int = 20
    ) -> str:
        """If the diagram has more than max_nodes, rebuild it from layers.

        Rebuilds a deterministic flowchart using subgraph blocks per layer,
        capped at max_nodes total. Returns the original code when under cap.
        """
        if cls._count_mermaid_nodes(code) <= max_nodes:
            return code

        # Flatten all components from layers
        all_components: list[tuple[str, str]] = []  # (name, azureService)
        for layer in layers:
            for comp in layer.get("components", []):
                svc = comp.get("azureService", comp.get("name", "Unknown"))
                all_components.append((comp.get("name", svc), svc))
            if len(all_components) >= max_nodes:
                break

        all_components = all_components[:max_nodes]

        if not all_components:
            return "flowchart TD\n  A[Azure Solution]"

        lines = ["flowchart TD"]
        comp_idx = 0
        prev_subgraph_last_id: str | None = None

        for layer in layers:
            layer_components = layer.get("components", [])
            if not layer_components:
                continue
            layer_name = layer.get("name", "Layer")
            # Sanitise for mermaid subgraph label
            safe_name = layer_name.replace("[", "(").replace("]", ")")
            lines.append(f"  subgraph {safe_name.replace(' ', '_')}[\"{safe_name}\"]")
            first_id_in_layer: str | None = None
            last_id_in_layer: str | None = None
            for comp in layer_components:
                if comp_idx >= max_nodes:
                    break
                node_id = f"N{comp_idx}"
                svc = comp.get("azureService", comp.get("name", "Unknown"))
                safe_svc = svc.replace("[", "(").replace("]", ")")
                lines.append(f"    {node_id}[\"{safe_svc}\"]")
                if first_id_in_layer is None:
                    first_id_in_layer = node_id
                last_id_in_layer = node_id
                comp_idx += 1
            lines.append("  end")
            # Connect previous layer to this layer
            if prev_subgraph_last_id and first_id_in_layer:
                lines.append(f"  {prev_subgraph_last_id} --> {first_id_in_layer}")
            prev_subgraph_last_id = last_id_in_layer

            if comp_idx >= max_nodes:
                break

        return "\n".join(lines)
