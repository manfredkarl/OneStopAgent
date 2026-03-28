# FRD-02: Discovery Agents (Brainstorming + Knowledge)

> **Source of truth:** `specs/v2/refactor.md` — sections §4 (Knowledge Layer), §5 (Brainstorming Agent)
> **Status:** Draft
> **Scope:** BrainstormingAgent, KnowledgeAgent, MCP integration, local knowledge base fallback
> **Depends on:** FRD-01 (Orchestration & Project Manager) — for `AgentState`, execution plan, and PM behavior

---

## 1. Overview

Two agents work together in **Mode A (Brainstorming)** to explore the customer need and ground it in Microsoft best practices:

| Agent | Purpose | LLM Required | External API |
|-------|---------|-------------|--------------|
| `BrainstormingAgent` | Explores ideas, suggests Azure-relevant scenarios, classifies Azure fit | Yes | No |
| `KnowledgeAgent` | Retrieves Microsoft reference architectures and patterns via MCP | No (MCP call) | Microsoft Learn MCP Server |

These agents are invoked by the Project Manager (ref FRD-01 §3). They communicate only through `AgentState` — they never call each other directly (ref refactor.md §3.2).

**Flow:**
1. User sends initial message (may be vague — e.g., "we want to do something with AI")
2. PM invokes `BrainstormingAgent` → generates scenarios + Azure fit classification
3. PM invokes `KnowledgeAgent` → retrieves matching Microsoft patterns from MCP
4. PM presents results to user, explains Azure fit reasoning
5. If fit is `"strong"` → PM offers to transition to Mode B (Solutioning)
6. If fit is `"weak"` or `"unclear"` → PM stays in Mode A, asks follow-up questions

---

## 2. BrainstormingAgent

### 2.1 Purpose (ref §5)

The BrainstormingAgent takes a potentially vague user description and uses an LLM to:
- Suggest 2–4 Azure-relevant scenarios that could address the user's need
- Detect the user's industry
- Classify Azure fit as `strong`, `weak`, or `unclear`
- Explain **why** Azure is a fit for each scenario — referencing specific Azure capabilities

### 2.2 Input (from AgentState)

```python
# Fields read by BrainstormingAgent
state.user_input       # str — original project description from user
state.clarifications   # str — accumulated user answers to PM questions
```

### 2.3 Processing

#### LLM Prompt

The agent sends a structured prompt to Azure OpenAI (via `AzureChatOpenAI.ainvoke()`):

```python
BRAINSTORMING_PROMPT = """You are an Azure solution consultant helping a seller explore a customer opportunity.

The customer described their need as:
"{user_input}"

Additional context from conversation:
"{clarifications}"

Your task:
1. Suggest 2-4 Azure-relevant scenarios that could address this need.
2. For EACH scenario:
   - Give it a clear title
   - Describe what it is (2-3 sentences)
   - List the primary Azure services involved
   - Explain WHY Azure is a good fit — reference specific Azure capabilities
     (e.g., "Azure Cosmos DB provides global distribution which matches your multi-region requirement")
3. Identify the customer's industry (retail, healthcare, financial services, manufacturing, etc.)
4. Recommend the BEST scenario
5. Classify overall Azure fit as:
   - "strong" — clear workload that maps to Azure services
   - "weak" — generic IT need without clear Azure advantage
   - "unclear" — not enough information to assess
6. Explain your Azure fit classification

Return your response as valid JSON matching this schema:
{{
    "scenarios": [
        {{
            "title": "Scenario title",
            "description": "What this scenario involves",
            "azure_services": ["Azure Service 1", "Azure Service 2"],
            "industry": "Industry name",
            "azure_fit_reason": "Why Azure is a good fit for this scenario"
        }}
    ],
    "recommended": "Title of the best scenario",
    "azure_fit": "strong" | "weak" | "unclear",
    "azure_fit_explanation": "Why Azure is/isn't a fit overall",
    "industry": "Detected industry"
}}
"""
```

#### Processing Rules

- Generate **2–4 scenarios** (never 1, never more than 4)
- Each scenario must reference **specific Azure services** (not generic "cloud services")
- Each `azure_fit_reason` must cite **specific Azure capabilities** — e.g., *"Azure Cosmos DB provides global distribution"*, NOT *"Azure is good for databases"*
- Industry detection should be specific when possible (e.g., "Retail — E-commerce" rather than just "Retail")
- Azure fit classification:
  - **Strong** — clear workload that maps to Azure services (e.g., "e-commerce platform", "IoT telemetry")
  - **Weak** — generic IT need without clear Azure advantage (e.g., "improve our processes")
  - **Unclear** — not enough information to assess

### 2.4 Output Schema

Written to `state.brainstorming`:

```python
state.brainstorming = {
    "scenarios": [
        {
            "title": "AI-Powered Product Recommendations",
            "description": "Use machine learning to personalize product suggestions based on browsing and purchase history.",
            "azure_services": [
                "Azure Machine Learning",
                "Azure Cosmos DB",
                "Azure App Service"
            ],
            "industry": "Retail",
            "azure_fit_reason": "Azure ML provides pre-built recommendation models (Smart Store), and Cosmos DB handles the global low-latency reads needed for real-time recommendations at checkout."
        },
        {
            "title": "Omnichannel Commerce Platform",
            "description": "Unified e-commerce backend serving web, mobile, and in-store channels with shared inventory and pricing.",
            "azure_services": [
                "Azure Kubernetes Service",
                "Azure API Management",
                "Azure SQL Database",
                "Azure Cache for Redis"
            ],
            "industry": "Retail",
            "azure_fit_reason": "AKS provides the microservices architecture needed for independent channel scaling, while API Management unifies the frontend gateway for all channels."
        }
        # ... 2-4 scenarios total
    ],
    "recommended": "AI-Powered Product Recommendations",
    "azure_fit": "strong",                    # "strong" | "weak" | "unclear"
    "azure_fit_explanation": "Azure is a strong fit because the customer's e-commerce requirements map directly to Azure's retail solution stack: ML for recommendations, Cosmos DB for global distribution, and App Service for rapid deployment.",
    "industry": "Retail"
}
```

**Additional state fields set by the PM after brainstorming:**

```python
state.azure_fit = state.brainstorming["azure_fit"]                      # "strong" | "weak" | "unclear"
state.azure_fit_explanation = state.brainstorming["azure_fit_explanation"]  # human-readable
```

### 2.5 PM Behavior Based on Azure Fit (ref §5)

| Azure Fit Value | PM Behavior |
|----------------|-------------|
| `"strong"` | PM presents the Azure fit explanation to the user, shows the execution plan (checklist), and asks: *"Azure is a strong fit — shall I proceed with the full solution?"* Transitions to Mode B on user confirmation. |
| `"weak"` | PM stays in Mode A. Explains why the fit is uncertain. Asks follow-up questions to narrow the use case — e.g., *"Can you tell me more about the specific workload? What data volumes and user counts are you expecting?"* |
| `"unclear"` | PM stays in Mode A. Explains that more information is needed. Asks clarifying questions — e.g., *"I need a bit more detail to assess Azure fit. What problem are you trying to solve, and what does your current infrastructure look like?"* |

**Critical:** PM must **always explain WHY** Azure is a fit (ref §1.1, §2.1):
> "Azure is a strong fit because your requirements for global availability and PCI-DSS compliance align with Azure Front Door and App Service Environment."

---

## 3. KnowledgeAgent

### 3.1 Purpose (ref §4)

The KnowledgeAgent retrieves relevant Microsoft reference architectures and patterns from the **Microsoft Learn MCP Server** to ground the solution in real Microsoft best practices. It does **not** use an LLM — it makes a direct MCP call.

> **Important distinction (ref §4.1):** "Azure Architecture Center" is NOT a separate MCP server — it is content within Microsoft Learn. Query the Microsoft Learn MCP Server with architecture-specific terms to retrieve Architecture Center content.

### 3.2 MCP Integration (ref §4.1, §4.2)

**Microsoft Learn MCP Server:**
- **Endpoint:** `https://learn.microsoft.com/api/mcp`
- **Capabilities:** Search and article retrieval across Microsoft Learn and Azure Architecture Center content
- **Documentation:** Publicly documented MCP server with `search` and `get-article` tools
- **Configuration:** MCP integration is configured in `.mcp.json` at the repo root

**KnowledgeAgent implementation:**

```python
class KnowledgeAgent:
    """Retrieves relevant Microsoft patterns and reference architectures via MCP."""

    name = "Knowledge Retrieval"
    emoji = "📚"

    def __init__(self, mcp_client):
        self.mcp_client = mcp_client

    async def run(self, state: AgentState) -> AgentState:
        """Query Microsoft Learn MCP Server for Azure patterns matching the use case."""
        query = f"{state.user_input} {state.clarifications} azure architecture"

        try:
            results = await self.mcp_client.search(query=query)
            state.retrieved_patterns = self._map_results(results)
        except MCPUnavailableError:
            # Fallback to local knowledge base
            state.retrieved_patterns = self._fallback_local(query)

        return state

    def _map_results(self, raw_results: list[dict]) -> list[dict]:
        """Map MCP response to the required pattern schema (ref §4.3).

        Fills defaults for any missing fields.
        """
        patterns = []
        for result in raw_results:
            patterns.append({
                "title": result.get("title", "Untitled"),
                "url": result.get("url", ""),
                "summary": result.get("summary", result.get("description", "")),
                "workload_type": result.get("workload_type", "custom"),
                "industry": result.get("industry", "Cross-Industry"),
                "compliance_tags": result.get("compliance_tags", []),
                "recommended_services": result.get("recommended_services", []),
                "components": result.get("components", []),
                "confidence_score": result.get("confidence_score", 0.5),
            })
        return patterns

    def _fallback_local(self, query: str) -> list[dict]:
        """Fall back to local knowledge base when MCP is unavailable.

        Returns patterns from data/knowledge_base.py, flagged as ungrounded.
        """
        from data.knowledge_base import search_local_patterns

        local_results = search_local_patterns(query)
        for result in local_results:
            result["_ungrounded"] = True  # flag for downstream warning
        return local_results
```

### 3.3 Retrieved Pattern Schema (ref §4.3)

Each pattern in `state.retrieved_patterns` must conform to this schema:

```python
{
    "title": "Scalable e-commerce web app",
    "url": "https://learn.microsoft.com/en-us/azure/architecture/...",
    "summary": "2-3 sentence description of the reference architecture",
    "workload_type": "web-app",
    # One of: "web-app" | "data-platform" | "ai-ml" | "iot"
    #         | "microservices" | "migration" | "custom"

    "industry": "Retail",
    # One of: "Retail" | "Healthcare" | "Financial Services"
    #         | "Manufacturing" | "Cross-Industry"

    "compliance_tags": ["PCI-DSS", "GDPR"],
    # Subset of: ["PCI-DSS", "HIPAA", "GDPR", "SOC2"]
    # Default: [] (empty list)

    "recommended_services": [
        "Azure App Service",
        "Azure SQL",
        "Azure Cache for Redis"
    ],

    "components": [
        {
            "name": "Web Frontend",
            "azureService": "Azure App Service",
            "description": "Hosts the customer-facing web application"
        }
    ],

    "confidence_score": 0.85
    # Float 0.0–1.0: how well this pattern matches the user's query
    # Default: 0.5 (when MCP response doesn't include a score)
}
```

**Default values for missing fields (ref §4.3):**

| Field | Default | When Applied |
|-------|---------|-------------|
| `workload_type` | `"custom"` | MCP response doesn't classify the workload |
| `industry` | `"Cross-Industry"` | MCP response doesn't specify industry |
| `compliance_tags` | `[]` | No compliance information available |
| `confidence_score` | `0.5` | MCP response doesn't include a relevance score |
| `components` | `[]` | MCP response doesn't break down components |
| `recommended_services` | `[]` | MCP response doesn't list services |

### 3.4 How Patterns Are Used Downstream (ref §4.4)

The `ArchitectAgent` (covered in a separate FRD) **must**:

1. Include `state.retrieved_patterns` in its LLM prompt as reference material
2. Prefer the pattern with the highest `confidence_score`
3. Adapt patterns to the user's specific requirements (scale, region, compliance)
4. **NOT generate architecture from scratch** — start from the closest matching pattern

**Required LLM prompt inclusion:**

> "Base your solution on the following Microsoft reference architectures. Adapt them to the user's specific requirements: {retrieved_patterns}"

**If no patterns were retrieved**, the architect should note:

> "⚠️ No matching reference architecture found — design based on Azure best practices."

### 3.5 Fallback Behavior (ref §4.2)

| Condition | Behavior |
|-----------|----------|
| **MCP available, results found** | Use MCP results. Map to pattern schema. Apply defaults for missing fields. |
| **MCP available, no results** | Return empty `state.retrieved_patterns = []`. Architect proceeds with note: *"No matching reference architecture found."* |
| **MCP unavailable (connection error, timeout)** | Fall back to local knowledge base (`data/knowledge_base.py`). Flag all results with `_ungrounded = True`. |
| **Local KB fallback active** | PM warns user: *"⚠️ Not grounded in Microsoft Learn — based on local reference data."* All downstream outputs carry this warning. |

**Ungrounded flag propagation:**
When patterns are flagged `_ungrounded = True`, the `ArchitectAgent` must include a visible warning in its output:
> "⚠️ This architecture is based on local reference data, not verified against current Microsoft Learn content."

---

## 4. MCP Service (`services/mcp.py`)

### 4.1 Client Implementation

The MCP client is a thin wrapper in `services/mcp.py` (ref §3.2: services/ contains only API clients, no business logic).

```python
"""MCP client for Microsoft Learn content retrieval.

This module contains ONLY the MCP API client. No business logic —
that belongs in KnowledgeAgent (ref refactor.md §3.2).
"""

import httpx
from typing import Optional


class MCPUnavailableError(Exception):
    """Raised when the MCP server cannot be reached."""
    pass


class MCPClient:
    """Client for the Microsoft Learn MCP Server."""

    DEFAULT_ENDPOINT = "https://learn.microsoft.com/api/mcp"

    def __init__(self, endpoint: Optional[str] = None, timeout: float = 10.0):
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.timeout = timeout

    async def search(
        self,
        query: str,
        top: int = 5,
        locale: str = "en-us",
    ) -> list[dict]:
        """Search Microsoft Learn for articles matching the query.

        Args:
            query: Search query string (e.g., "e-commerce azure architecture")
            top: Maximum number of results to return (default: 5)
            locale: Content locale (default: "en-us")

        Returns:
            List of result dicts from the MCP server.

        Raises:
            MCPUnavailableError: If the MCP server cannot be reached.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    json={
                        "tool": "search",
                        "parameters": {
                            "query": query,
                            "top": top,
                            "locale": locale,
                        },
                    },
                )
                response.raise_for_status()
                return response.json().get("results", [])
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            raise MCPUnavailableError(f"MCP server unavailable: {e}") from e
```

### 4.2 Search Function Signature

```python
async def search(
    self,
    query: str,          # Free-text search query
    top: int = 5,        # Max results (default 5)
    locale: str = "en-us"  # Content locale
) -> list[dict]:
    """Returns list of MCP result dicts or raises MCPUnavailableError."""
```

### 4.3 Response Mapping

The `KnowledgeAgent._map_results()` method (see §3.2) transforms raw MCP responses into the pattern schema (§3.3). Mapping rules:

| MCP Response Field | Pattern Schema Field | Transformation |
|-------------------|---------------------|----------------|
| `title` | `title` | Direct copy |
| `url` | `url` | Direct copy |
| `description` or `summary` | `summary` | Use `summary` if available, else `description` |
| *(not provided by MCP)* | `workload_type` | Default: `"custom"` — KnowledgeAgent may infer from title/content |
| *(not provided by MCP)* | `industry` | Default: `"Cross-Industry"` |
| *(not provided by MCP)* | `compliance_tags` | Default: `[]` |
| `services` or similar | `recommended_services` | Map service names to standard Azure service names |
| *(not provided by MCP)* | `components` | Default: `[]` |
| `relevance` or `score` | `confidence_score` | Normalize to 0.0–1.0 range; default `0.5` if absent |

---

## 5. Acceptance Criteria

- [ ] BrainstormingAgent suggests 2–4 Azure-relevant scenarios (never 1, never >4)
- [ ] Each scenario includes specific Azure services (not generic "cloud services")
- [ ] Each scenario includes `azure_fit_reason` explaining **WHY** Azure is a fit, citing specific Azure capabilities
- [ ] Azure fit classified as `"strong"`, `"weak"`, or `"unclear"`
- [ ] PM explains Azure fit reasoning to the user before offering to proceed
- [ ] When fit is `"strong"` → PM offers transition to Mode B
- [ ] When fit is `"weak"` or `"unclear"` → PM stays in Mode A, asks follow-up questions
- [ ] Industry detected and stored in `state.brainstorming["industry"]`
- [ ] KnowledgeAgent returns patterns conforming to full schema (§3.3) with all required fields
- [ ] Missing MCP fields are filled with documented defaults (§3.3 table)
- [ ] Patterns include `confidence_score` (float 0.0–1.0)
- [ ] MCP fallback to local knowledge base (`data/knowledge_base.py`) triggers on MCP unavailability
- [ ] Fallback patterns are flagged with `_ungrounded = True`
- [ ] PM displays warning when using ungrounded patterns: *"⚠️ Not grounded in Microsoft Learn"*
- [ ] ArchitectAgent (downstream) receives patterns in its prompt with instruction to base architecture on them
- [ ] `services/mcp.py` contains only the MCP client — no business logic
