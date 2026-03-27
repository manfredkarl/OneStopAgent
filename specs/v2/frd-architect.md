# FRD: System Architect Agent

> **Version:** 2.0  
> **Status:** Current  
> **Replaces:** specs/frd-architecture.md (v1)  
> **Component:** `src/python-api/agents/architect_agent.py`

---

## 1. Overview

The System Architect agent generates Azure architecture designs including Mermaid diagrams, component lists, and business-audience narratives. It is always required and cannot be disabled. It is the first agent in the default execution pipeline and its output is consumed by all downstream agents.

---

## 2. Input

| Field | Source | Description |
|-------|--------|-------------|
| `state.user_input` | User | Original project description |
| `state.clarifications` | User | Answers to PM clarifying questions |

The agent combines both fields to form the `requirements` string passed to all LLM calls.

---

## 3. Processing

The agent makes **three sequential LLM calls**, each with a focused prompt.

### 3.1 Mermaid Diagram Generation

**LLM Call 1:**

- **System prompt:** `"Generate a Mermaid flowchart TD diagram for an Azure architecture. Use Azure service names as nodes. Maximum 20 nodes. Return ONLY the Mermaid code, no markdown fences, no explanation."`
- **User prompt:** `"Design an Azure architecture for: {requirements}"`

**Post-processing:**

1. Strip markdown fences (`` ``` `` and `` ```mermaid ``) from LLM output
2. Trim whitespace
3. Validate output starts with `flowchart` or `graph`
4. If validation fails → prepend `flowchart TD\n` to the output
5. Enforce max 20 nodes (via LLM instruction)

### 3.2 Component Extraction

**LLM Call 2:**

- **System prompt:** `"Extract Azure architecture components. Return ONLY a JSON array: [{"name": "...", "azureService": "...", "description": "..."}]"`
- **User prompt:** The generated Mermaid diagram + original requirements

**Expected output:**

```json
[
  {
    "name": "Web Frontend",
    "azureService": "Azure App Service",
    "description": "Hosts the customer-facing web application"
  },
  {
    "name": "Application Database",
    "azureService": "Azure SQL Database",
    "description": "Stores user data and transaction records"
  }
]
```

**Error handling:**

- JSON parse failure → fallback to default 3-component architecture:

  ```json
  [
    {"name": "Web App", "azureService": "Azure App Service", "description": "Web application hosting"},
    {"name": "Database", "azureService": "Azure SQL Database", "description": "Data storage"},
    {"name": "Cache", "azureService": "Azure Cache for Redis", "description": "Performance caching"}
  ]
  ```

### 3.3 Narrative Generation

**LLM Call 3:**

- **System prompt:** `"Write a 2-3 sentence description of this Azure architecture for a business audience. Be specific about the services used."`
- **User prompt:** Components array (as JSON) + original requirements

**Output:** A 2-3 sentence paragraph suitable for executive presentations.

---

## 4. Output

The agent writes to `state.architecture`:

```python
state.architecture = {
    "mermaidCode": "flowchart TD\n  A[Azure Front Door] --> B[App Service]\n  B --> C[SQL Database]\n  ...",
    "components": [
        {
            "name": "Web Frontend",
            "azureService": "Azure App Service",
            "description": "Hosts the customer-facing web application"
        },
        {
            "name": "Application Database",
            "azureService": "Azure SQL Database",
            "description": "Stores user data and transaction records"
        }
    ],
    "narrative": "The proposed architecture leverages Azure App Service for scalable web hosting, backed by Azure SQL Database for relational data storage. Azure Cache for Redis provides high-performance caching to minimize database load and improve response times."
}
```

### 4.1 Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `mermaidCode` | `str` | Valid Mermaid flowchart syntax (no markdown fences) |
| `components` | `list[dict]` | Array of `{ name, azureService, description }` objects |
| `narrative` | `str` | 2-3 sentence business-audience description |

---

## 5. Output Formatting (for chat)

When the agent result is streamed to the frontend, it is formatted as markdown:

```markdown
## 🏗️ Architecture Design

{narrative}

### Architecture Diagram

```mermaid
{mermaidCode}
```

### Components

- **{name}** — {azureService}: {description}
- **{name}** — {azureService}: {description}
- ...
```

The frontend's `MessageContent` component:

1. Renders the narrative and component list via `marked` (markdown → HTML)
2. Extracts the `mermaid` fenced block and renders it via the `MermaidDiagram` component as interactive SVG

---

## 6. Error Handling

| Failure | Fallback |
|---------|----------|
| LLM call fails (timeout, API error) | Return default architecture template (App Service + SQL + Redis) |
| Mermaid output invalid | Prepend `flowchart TD\n` to make it parseable |
| Component JSON parse fails | Use 3-component default (App Service, SQL, Redis) |
| Narrative generation fails | Use generic narrative: "The proposed architecture uses Azure services to meet the customer's requirements." |

---

## 7. Dependencies

| Direction | Agent | Relationship |
|-----------|-------|-------------|
| **Consumed by** | Azure Specialist | Reads `architecture.components` for service mapping |
| **Consumed by** | Cost Specialist | Reads via `services.selections` (indirectly) |
| **Consumed by** | Business Value | Reads `architecture.components` for impact analysis |
| **Consumed by** | Presentation | Reads `architecture.narrative` and `architecture.components` for slides 3-4 |

---

## 8. LLM Configuration

- **Model:** Azure OpenAI GPT-4.1 via `AzureChatOpenAI`
- **Temperature:** 0.7 (allows creative but consistent architecture designs)
- **Streaming:** Enabled at LLM level
- **Authentication:** Azure AD token via `AZURE_OPENAI_TOKEN` environment variable

---

## 9. Acceptance Criteria

- [ ] Generates valid Mermaid flowchart syntax starting with `flowchart TD` or `graph TD`
- [ ] Mermaid diagram has ≤ 20 nodes
- [ ] Component extraction returns valid JSON array with `name`, `azureService`, `description` per item
- [ ] Narrative is 2-3 sentences, business-appropriate tone
- [ ] Markdown fences are stripped from raw LLM Mermaid output
- [ ] Falls back to default components on JSON parse failure
- [ ] Falls back to default architecture on complete LLM failure
- [ ] Output renders correctly as Mermaid SVG in the frontend
- [ ] `state.architecture` is populated with all three fields after execution
