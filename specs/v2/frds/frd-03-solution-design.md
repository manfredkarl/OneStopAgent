# FRD-03: Solution Design Agents (Architect + Azure Specialist)

> **Source of Truth:** `specs/v2/refactor.md` — §6 (Architect Agent), §7 (Azure Specialist)
> **Status:** Draft
> **Last Updated:** 2025-07-28

---

## 1. Overview

Two sequential agents that design the Azure solution. **ArchitectAgent** generates the high-level architecture (Mermaid diagram, component list, narrative) grounded in Microsoft reference patterns retrieved by the KnowledgeAgent. **AzureSpecialistAgent** then maps every component to a concrete Azure service with scale-appropriate SKUs, regions, and capability tags.

These agents run back-to-back in the Mode B execution plan (refactor.md §2.3):

```
KnowledgeAgent → ArchitectAgent → AzureSpecialistAgent → CostAgent → ...
```

Neither agent operates in isolation — the Architect consumes `state.retrieved_patterns` (from KnowledgeAgent, §4) and the Specialist consumes `state.architecture.components` (from Architect). Both write to `AgentState` (§12) and communicate exclusively through shared state — no agent-to-agent imports (§3.2).

---

## 2. ArchitectAgent

### 2.1 Purpose

Generate a complete Azure solution architecture — Mermaid diagram, structured component list, and executive narrative — adapted from the closest-matching Microsoft reference architecture. The output must be grounded in retrieved patterns so that sellers can trace the design back to a published Microsoft recommendation.

*(Refactor.md §6, §4.4)*

### 2.2 Input (from AgentState)

The ArchitectAgent reads three fields from `AgentState` (§12):

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `state.user_input` | `str` | User's original project description | Free-text describing the workload |
| `state.clarifications` | `str` | PM follow-up answers accumulated during brainstorming | Additional context, constraints, region preferences |
| `state.retrieved_patterns` | `list[dict]` | KnowledgeAgent output (§4.2, §4.3) | Microsoft reference architectures with `confidence_score` |

If `state.retrieved_patterns` is empty, the agent proceeds without grounding and adds the warning:
> "⚠️ No matching reference architecture found — design based on Azure best practices."

### 2.3 Processing

The ArchitectAgent performs four sequential LLM-assisted steps. Each is a separate `llm.invoke()` call (no chains — §15).

#### 2.3.1 Pattern Selection

Select the closest matching reference architecture from `state.retrieved_patterns`:

```python
def _select_pattern(self, patterns: list[dict]) -> dict | None:
    """Select the pattern with the highest confidence_score.
    
    Returns None if patterns is empty.
    Per §4.4: prefer the pattern with the highest confidence_score.
    """
    if not patterns:
        return None
    return max(patterns, key=lambda p: p.get("confidence_score", 0.0))
```

The selected pattern's `title`, `summary`, `recommended_services`, and `components` are injected into the LLM prompt for all subsequent steps.

**Prompt inclusion (§4.4):**
> "Base your solution on the following Microsoft reference architectures. Adapt them to the user's specific requirements: {retrieved_patterns}"

#### 2.3.2 Mermaid Diagram Generation

**LLM call** to generate a Mermaid flowchart diagram.

Constraints enforced (§6):
- **Max 20 nodes** — the prompt instructs the LLM to limit node count
- **`flowchart TD` header** — if missing, prepend automatically
- **Fence cleanup** — strip ` ```mermaid ` / ` ``` ` wrappers from LLM output

```python
def _generate_mermaid(self, user_input: str, clarifications: str, pattern: dict | None) -> str:
    """Generate Mermaid flowchart via LLM.
    
    Post-processing:
    1. Strip markdown fences (```mermaid ... ```)
    2. Ensure starts with 'flowchart TD'
    3. Validate node count ≤ 20
    """
    prompt = f"""Generate a Mermaid flowchart diagram for the following Azure solution.
Maximum 20 nodes. Use 'flowchart TD' format.
Do NOT include markdown fences.

User requirement: {user_input}
Additional context: {clarifications}
Reference architecture: {json.dumps(pattern) if pattern else 'None — use Azure best practices'}

Output ONLY the Mermaid code, nothing else."""

    raw = llm.invoke(prompt).content.strip()
    
    # Fence cleanup
    mermaid = re.sub(r"^```(?:mermaid)?\s*\n?", "", raw)
    mermaid = re.sub(r"\n?```\s*$", "", mermaid)
    
    # Ensure flowchart header
    if not mermaid.strip().startswith("flowchart"):
        mermaid = "flowchart TD\n" + mermaid
    
    # Validate node count (warn if >20, do not reject)
    node_count = len(re.findall(r"^\s*\w+[\[\(\{]", mermaid, re.MULTILINE))
    if node_count > 20:
        logger.warning(f"Mermaid diagram has {node_count} nodes (max 20)")
    
    return mermaid
```

#### 2.3.3 Component Extraction

**Separate LLM call** to extract a structured component list from the architecture.

```python
def _extract_components(self, mermaid_code: str, pattern: dict | None) -> list[dict]:
    """Extract components as structured JSON from the Mermaid diagram.
    
    Each component must have:
    - name: human-readable component name
    - azureService: mapped Azure service name
    - description: one-line purpose description
    
    Fallback: if JSON parsing fails, return pattern's components
    or a minimal default set.
    """
    prompt = f"""Extract all components from this Mermaid diagram as a JSON array.
Each element must have: "name", "azureService", "description".

Mermaid diagram:
{mermaid_code}

Reference components (for Azure service mapping guidance):
{json.dumps(pattern.get('components', [])) if pattern else '[]'}

Output ONLY valid JSON array, nothing else."""

    raw = llm.invoke(prompt).content.strip()
    
    try:
        components = json.loads(raw)
        if not isinstance(components, list):
            raise ValueError("Expected JSON array")
        return components
    except (json.JSONDecodeError, ValueError):
        # Fallback: use pattern components if available
        if pattern and pattern.get("components"):
            return pattern["components"]
        # Ultimate fallback: minimal default
        return [
            {"name": "Web Frontend", "azureService": "Azure App Service", "description": "Web application hosting"},
            {"name": "Database", "azureService": "Azure SQL Database", "description": "Relational data storage"},
            {"name": "Cache", "azureService": "Azure Cache for Redis", "description": "In-memory caching layer"}
        ]
```

#### 2.3.4 Narrative Generation

**LLM call** to produce a 2–3 sentence architecture narrative for business audiences.

```python
def _generate_narrative(self, user_input: str, components: list[dict], pattern: dict | None) -> str:
    """Generate a 2-3 sentence executive-friendly architecture narrative.
    
    Tone: business audience, not technical jargon.
    Must reference the user's use case and key Azure services.
    """
    prompt = f"""Write a 2-3 sentence architecture overview for a business audience.
Reference the customer's use case and the key Azure services involved.
Do NOT use technical jargon.

Customer requirement: {user_input}
Components: {json.dumps(components)}
Based on: {pattern['title'] if pattern else 'Azure best practices'}

Output ONLY the narrative text, nothing else."""

    return llm.invoke(prompt).content.strip()
```

### 2.4 Output Schema

Written to `state.architecture` (§6, §12):

```python
state.architecture = {
    "mermaidCode": str,       # Mermaid flowchart TD code (max 20 nodes, no fences)
    "components": [           # Structured component list
        {
            "name": str,          # e.g., "Web Frontend"
            "azureService": str,  # e.g., "Azure App Service"
            "description": str    # e.g., "Hosts the customer-facing web application"
        }
    ],
    "narrative": str,         # 2-3 sentence business-audience description
    "basedOn": str            # Reference architecture title or "custom design"
}
```

**`basedOn` field rules:**
- If a pattern was selected → `basedOn = pattern["title"]` (e.g., `"Scalable e-commerce web app"`)
- If no patterns available → `basedOn = "custom design"`

### 2.5 Error Handling

| Failure | Fallback | User-Visible Note |
|---------|----------|--------------------|
| LLM call fails (timeout, API error) | Use a static fallback template with generic 3-tier architecture | "⚠️ AI service unavailable — using default architecture template." |
| Invalid Mermaid syntax from LLM | Prepend `flowchart TD\n` and attempt render; if still invalid, show component table only | Diagram silently hidden (§17) |
| JSON parsing fails for components | Use pattern's `components` if available; otherwise use 3-component fallback set | None (silent fallback) |
| No retrieved patterns | Proceed without grounding | "⚠️ No matching reference architecture found — design based on Azure best practices." |
| LLM returns invalid JSON (§17) | Retry once with stricter prompt; if still fails, use fallback template | None (silent retry) |

**Fallback template** (used when LLM is completely unavailable):

```python
FALLBACK_ARCHITECTURE = {
    "mermaidCode": "flowchart TD\n  A[Client] --> B[Web App]\n  B --> C[API Layer]\n  C --> D[Database]\n  C --> E[Cache]",
    "components": [
        {"name": "Web App", "azureService": "Azure App Service", "description": "Web application frontend"},
        {"name": "API Layer", "azureService": "Azure App Service", "description": "REST API backend"},
        {"name": "Database", "azureService": "Azure SQL Database", "description": "Relational data storage"},
        {"name": "Cache", "azureService": "Azure Cache for Redis", "description": "Performance caching"}
    ],
    "narrative": "A standard three-tier Azure architecture with web frontend, API layer, and managed database.",
    "basedOn": "custom design"
}
```

---

## 3. AzureSpecialistAgent

### 3.1 Purpose

Map every component from the architecture to a concrete Azure service with a scale-appropriate SKU, region, and capability list. This agent is entirely **deterministic** — no LLM calls (§7). It uses lookup tables and regex-based scale extraction to produce service selections.

### 3.2 Input (from AgentState)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `state.architecture.components` | `list[dict]` | ArchitectAgent output (§2.4) | Components with `name`, `azureService`, `description` |
| `state.user_input` | `str` | Original user description | Used for concurrent-user scale extraction |
| `state.clarifications` | `str` | PM follow-up answers | May contain region preferences, HA requirements |

### 3.3 Scale Extraction

The agent parses concurrent user count from `state.user_input` and `state.clarifications` using regex:

```python
def _extract_scale(self, user_input: str, clarifications: str) -> int:
    """Extract concurrent user count from user text.
    
    Patterns matched:
    - "500 users", "10,000 concurrent users", "10k users"
    - "500 employees", "large enterprise" (infer scale)
    
    Returns: int (concurrent users), default 100 if not found.
    """
    text = f"{user_input} {clarifications}".lower()
    
    # Match explicit numbers: "10,000 users", "10k users"
    patterns = [
        r"(\d{1,3}(?:,\d{3})*)\s*(?:concurrent\s+)?users",
        r"(\d+)k\s*(?:concurrent\s+)?users",
        r"(\d{1,3}(?:,\d{3})*)\s*(?:concurrent\s+)?employees",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            num_str = match.group(1).replace(",", "")
            if "k" in pattern:
                return int(num_str) * 1000
            return int(num_str)
    
    # Heuristic fallback
    if "enterprise" in text or "large" in text:
        return 10000
    if "startup" in text or "small" in text:
        return 100
    
    return 100  # default
```

The extracted scale determines the SKU tier for all services via the matrices below.

### 3.4 Core Service SKU Matrix

*(Directly from refactor.md §7)*

| Concurrent Users | App Service | SQL Database | Redis Cache | Cosmos DB | Azure Functions |
|-----------------|------------|--------------|-------------|-----------|----------------|
| ≤100 | B1 | Basic | C0 | Serverless | Consumption |
| ≤1,000 | S1 | Standard S1 | C1 | Autoscale 1000 RU/s | Consumption |
| ≤10,000 | P2v3 | Premium P4 | P1 | Autoscale 10000 RU/s | Premium EP1 |
| >10,000 | P3v3 | Business Critical | P3 | Autoscale 50000 RU/s | Premium EP3 |

Implementation as lookup:

```python
CORE_SKU_MATRIX = {
    "Azure App Service": {100: "B1", 1000: "S1", 10000: "P2v3", float("inf"): "P3v3"},
    "Azure SQL Database": {100: "Basic", 1000: "Standard S1", 10000: "Premium P4", float("inf"): "Business Critical"},
    "Azure Cache for Redis": {100: "C0", 1000: "C1", 10000: "P1", float("inf"): "P3"},
    "Azure Cosmos DB": {100: "Serverless", 1000: "Autoscale 1000 RU/s", 10000: "Autoscale 10000 RU/s", float("inf"): "Autoscale 50000 RU/s"},
    "Azure Functions": {100: "Consumption", 1000: "Consumption", 10000: "Premium EP1", float("inf"): "Premium EP3"},
}

def _get_core_sku(self, service_name: str, concurrent_users: int) -> str | None:
    """Look up SKU from core matrix. Returns None if service not in matrix."""
    tiers = CORE_SKU_MATRIX.get(service_name)
    if not tiers:
        return None
    for threshold in sorted(tiers.keys()):
        if concurrent_users <= threshold:
            return tiers[threshold]
    return None
```

### 3.5 Extended Service Defaults

*(Directly from refactor.md §7)*

For services **not** in the core matrix, use these defaults. Some scale with concurrent users:

| Service | Default SKU | Scale Note |
|---------|------------|------------|
| Azure OpenAI | Standard S0 | Provisioned throughput for >1,000 users |
| Azure AI Search | Standard S1 | Basic for ≤100 users |
| Azure Container Apps | Consumption | Dedicated for >10,000 users |
| Azure Kubernetes Service (AKS) | Standard_D4s_v3 (3 nodes) | Scale node count with users |
| Azure Event Hubs | Standard | Premium for >10,000 events/sec |
| Azure Service Bus | Standard | Premium for mission-critical |
| Azure Blob Storage | Standard LRS | GRS for HA requirements |
| Azure Key Vault | Standard | Premium for HSM-backed keys |
| Azure Monitor / App Insights | Pay-as-you-go | Always included |
| Azure Front Door | Standard | Premium for WAF + private link |
| Azure API Management | Developer | Standard for production |
| Microsoft Fabric | F2 | Scale with data volume |

Implementation:

```python
EXTENDED_DEFAULTS = {
    "Azure OpenAI": {
        "default_sku": "Standard S0",
        "scale_rule": lambda users: "Provisioned Throughput" if users > 1000 else "Standard S0",
    },
    "Azure AI Search": {
        "default_sku": "Standard S1",
        "scale_rule": lambda users: "Basic" if users <= 100 else "Standard S1",
    },
    "Azure Container Apps": {
        "default_sku": "Consumption",
        "scale_rule": lambda users: "Dedicated" if users > 10000 else "Consumption",
    },
    "Azure Kubernetes Service": {
        "default_sku": "Standard_D4s_v3 (3 nodes)",
        "scale_rule": lambda users: f"Standard_D4s_v3 ({max(3, users // 2000)} nodes)",
    },
    "Azure Event Hubs": {"default_sku": "Standard", "scale_rule": None},
    "Azure Service Bus": {"default_sku": "Standard", "scale_rule": None},
    "Azure Blob Storage": {"default_sku": "Standard LRS", "scale_rule": None},
    "Azure Key Vault": {"default_sku": "Standard", "scale_rule": None},
    "Azure Monitor": {"default_sku": "Pay-as-you-go", "scale_rule": None},
    "Application Insights": {"default_sku": "Pay-as-you-go", "scale_rule": None},
    "Azure Front Door": {
        "default_sku": "Standard",
        "scale_rule": lambda users: "Premium" if users > 10000 else "Standard",
    },
    "Azure API Management": {
        "default_sku": "Developer",
        "scale_rule": lambda users: "Standard" if users > 1000 else "Developer",
    },
    "Microsoft Fabric": {"default_sku": "F2", "scale_rule": None},
}

def _get_extended_sku(self, service_name: str, concurrent_users: int) -> str | None:
    """Look up SKU from extended defaults. Returns None if service not listed."""
    entry = EXTENDED_DEFAULTS.get(service_name)
    if not entry:
        return None
    if entry.get("scale_rule"):
        return entry["scale_rule"](concurrent_users)
    return entry["default_sku"]
```

### 3.6 Fallback Rule

*(Refactor.md §7 — Fallback Rule)*

For any component type **not** listed in the core matrix (§3.4) or extended defaults (§3.5):

```python
def _get_fallback_sku(self, service_name: str) -> tuple[str, str]:
    """Return fallback SKU and warning note for unknown services.
    
    Returns: (sku, skuNote)
    """
    return (
        "Standard",
        f"⚠️ SKU needs manual validation for {service_name}."
    )
```

- **SKU:** `"Standard"`
- **Region:** User preference or `"eastus"`
- **`skuNote`:** `"⚠️ SKU needs manual validation for {serviceName}."`

### 3.7 Multi-Region Handling

*(Refactor.md §7 — Multi-Region Handling)*

If the user specifies multiple regions (e.g., "US East and West"):

1. **Primary region:** Use the first mentioned region for all entries in `state.services.selections`
2. **HA/DR note:** Add to each service: `"For high availability, deploy a secondary instance in {second_region}"`
3. **Do NOT duplicate** every service into two entries — that inflates cost estimates unrealistically
4. **Add ONE line item:** `"Multi-region replication overhead"` with an estimated 30–50% uplift on compute + storage costs
5. **Diagram guidance:** The ArchitectAgent should reflect multi-region in the Mermaid diagram (show both regions as deployment targets)

```python
def _handle_multi_region(self, selections: list[dict], regions: list[str]) -> list[dict]:
    """Add multi-region handling if >1 region specified.
    
    - Sets primary region on all selections
    - Adds HA/DR note to each service
    - Appends a single multi-region overhead line item
    """
    if len(regions) <= 1:
        return selections
    
    primary = regions[0]
    secondary = regions[1]
    
    for sel in selections:
        sel["region"] = primary
        sel["skuNote"] = (
            sel.get("skuNote", "") +
            f" For high availability, deploy a secondary instance in {secondary}."
        ).strip()
    
    # Add overhead line item (not a real service — signals cost agent)
    selections.append({
        "componentName": "Multi-region replication overhead",
        "serviceName": "Multi-region overhead",
        "sku": "30-50% uplift",
        "region": f"{primary} + {secondary}",
        "capabilities": ["high-availability", "disaster-recovery"],
        "skuNote": "Estimated 30-50% uplift on compute and storage costs for multi-region deployment."
    })
    
    return selections
```

### 3.8 Output Schema

Written to `state.services` (§7, §12):

```python
state.services = {
    "selections": [
        {
            "componentName": str,     # From architecture component name
            "serviceName": str,       # Azure service name (e.g., "Azure App Service")
            "sku": str,               # Scale-appropriate SKU (e.g., "P2v3")
            "region": str,            # Azure region (e.g., "eastus")
            "capabilities": [str],    # Service capabilities (e.g., ["auto-scale", "SSL"])
            "skuNote": str | None     # Optional warning or note (e.g., fallback warning)
        }
    ]
}
```

### 3.9 No LLM Required

This agent is **entirely deterministic** (§3.1, §7). It uses:
- Regex for scale extraction
- Lookup tables for SKU mapping
- Static rules for multi-region handling

No `llm.invoke()` calls. No external API calls. No MCP calls.

---

## 4. Agent Interaction

### Data Flow

```
┌─────────────────────┐
│   KnowledgeAgent    │
│   (§4, FRD-02)      │
│                     │
│ Output:             │
│ state.retrieved_    │
│ patterns            │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   ArchitectAgent    │
│   (§6, FRD-03 §2)   │
│                     │
│ Reads:              │
│ • user_input        │
│ • clarifications    │
│ • retrieved_patterns│
│                     │
│ Writes:             │
│ • architecture      │
│   ├ mermaidCode     │
│   ├ components      │
│   ├ narrative       │
│   └ basedOn         │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ AzureSpecialistAgent│
│   (§7, FRD-03 §3)   │
│                     │
│ Reads:              │
│ • architecture.     │
│   components        │
│ • user_input        │
│   (scale extraction)│
│                     │
│ Writes:             │
│ • services          │
│   └ selections[]    │
│     ├ componentName │
│     ├ serviceName   │
│     ├ sku           │
│     ├ region        │
│     ├ capabilities  │
│     └ skuNote       │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│     CostAgent       │
│   (§8, FRD-04)      │
└─────────────────────┘
```

**Key contracts:**
- ArchitectAgent **must** produce at least one component in `state.architecture.components` for the Specialist to operate
- If `state.architecture.components` is empty, AzureSpecialistAgent writes an empty `selections` array and logs a warning
- Agents communicate **only** through `AgentState` — no imports between agent modules (§3.2)

---

## 5. Acceptance Criteria

### ArchitectAgent

- [ ] Generates valid Mermaid flowchart in `flowchart TD` format (max 20 nodes)
- [ ] Architecture is grounded in `retrieved_patterns` — `basedOn` field set to pattern title
- [ ] When no patterns retrieved, `basedOn = "custom design"` and warning note emitted
- [ ] Mermaid output has markdown fences stripped (no ` ```mermaid ` wrappers)
- [ ] Mermaid output starts with `flowchart TD` (prepended if missing)
- [ ] Components extracted as structured JSON with `name`, `azureService`, `description`
- [ ] JSON parse failure falls back to pattern components, then to 3-component default
- [ ] Narrative is 2–3 sentences in business-audience tone (no jargon)
- [ ] LLM failure triggers static fallback architecture template (system does not crash — §17)
- [ ] LLM invalid JSON triggers one retry with stricter prompt before fallback (§17)

### AzureSpecialistAgent

- [ ] Maps **ALL** components from `state.architecture.components` to service selections
- [ ] SKUs scale correctly with concurrent users (B1 → S1 → P2v3 → P3v3 for App Service)
- [ ] Core matrix covers: App Service, SQL Database, Redis Cache, Cosmos DB, Azure Functions
- [ ] Extended defaults cover 12+ services: OpenAI, AI Search, Container Apps, AKS, Event Hubs, Service Bus, Blob Storage, Key Vault, Monitor/App Insights, Front Door, API Management, Fabric
- [ ] Extended services with scale rules adjust SKUs based on user count (e.g., AI Search: Basic ≤100, Standard S1 otherwise)
- [ ] Unknown/unlisted services get fallback SKU `"Standard"` with warning in `skuNote`
- [ ] Region defaults to `"eastus"` when no user preference specified
- [ ] Multi-region does **not** duplicate service entries — adds single overhead line item
- [ ] Multi-region overhead line item specifies 30–50% uplift
- [ ] HA/DR note added to each service when multi-region detected
- [ ] No LLM calls — agent is fully deterministic
- [ ] Empty `architecture.components` produces empty `selections[]` (no crash)

### Integration

- [ ] ArchitectAgent output feeds directly into AzureSpecialistAgent without transformation
- [ ] Both agents read/write exclusively through `AgentState` (no cross-agent imports — §3.2)
- [ ] PM can re-run either agent independently during iteration (§13)
- [ ] "Add HA" iteration triggers Architect → Specialist → Cost → ROI → Presentation re-run (§13)
- [ ] "Make it cheaper" iteration triggers Specialist → Cost → ROI → Presentation re-run (§13)

---

## Appendix A: Agent Class Signatures

```python
class ArchitectAgent:
    """Generates Azure solution architecture grounded in Microsoft reference patterns.
    
    LLM Required: Yes (3 calls — Mermaid, components, narrative)
    External API: None
    Ref: refactor.md §6
    """
    name = "Architecture Design"
    emoji = "🏗️"
    
    def run(self, state: AgentState) -> AgentState:
        pattern = self._select_pattern(state.retrieved_patterns)
        mermaid = self._generate_mermaid(state.user_input, state.clarifications, pattern)
        components = self._extract_components(mermaid, pattern)
        narrative = self._generate_narrative(state.user_input, components, pattern)
        
        state.architecture = {
            "mermaidCode": mermaid,
            "components": components,
            "narrative": narrative,
            "basedOn": pattern["title"] if pattern else "custom design"
        }
        return state


class AzureSpecialistAgent:
    """Maps architecture components to Azure services with scale-appropriate SKUs.
    
    LLM Required: No (deterministic mapping)
    External API: None
    Ref: refactor.md §7
    """
    name = "Azure Services"
    emoji = "☁️"
    
    def run(self, state: AgentState) -> AgentState:
        components = state.architecture.get("components", [])
        concurrent_users = self._extract_scale(state.user_input, state.clarifications)
        region = self._extract_region(state.clarifications) or "eastus"
        regions = self._extract_all_regions(state.clarifications)
        
        selections = []
        for comp in components:
            service_name = comp["azureService"]
            sku = (
                self._get_core_sku(service_name, concurrent_users)
                or self._get_extended_sku(service_name, concurrent_users)
            )
            sku_note = None
            if sku is None:
                sku, sku_note = self._get_fallback_sku(service_name)
            
            selections.append({
                "componentName": comp["name"],
                "serviceName": service_name,
                "sku": sku,
                "region": region,
                "capabilities": self._get_capabilities(service_name),
                "skuNote": sku_note,
            })
        
        selections = self._handle_multi_region(selections, regions)
        state.services = {"selections": selections}
        return state
```

---

## Appendix B: Cross-Reference to refactor.md

| FRD Section | refactor.md Section |
|-------------|-------------------|
| §2 ArchitectAgent | §6 Architect Agent (Updated) |
| §2.2 Input | §6 Input from State, §12 State Model |
| §2.3.1 Pattern Selection | §4.4 How Retrieved Patterns Are Used |
| §2.3.2 Mermaid Generation | §6 Behavior (max 20 nodes) |
| §2.4 Output Schema | §6 Output Written to State |
| §2.5 Error Handling | §17 Graceful Degradation |
| §3 AzureSpecialistAgent | §7 Azure Specialist |
| §3.4 Core SKU Matrix | §7 Core Service SKU Matrix |
| §3.5 Extended Defaults | §7 Extended Service Defaults |
| §3.6 Fallback Rule | §7 Fallback Rule |
| §3.7 Multi-Region | §7 Multi-Region Handling |
| §3.8 Output Schema | §7 Output Written to State |
| §5 Acceptance Criteria | §19 Definition of Done |
