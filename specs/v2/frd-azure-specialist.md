# FRD: Azure Specialist Agent

> **Version:** 2.0  
> **Status:** Current  
> **Replaces:** specs/frd-architecture.md (v1, partial)  
> **Component:** `src/python-api/agents/azure_specialist_agent.py`

---

## 1. Overview

The Azure Specialist agent maps architecture components to specific Azure services with SKU recommendations scaled to the project's expected user count. It does not use LLM calls — selection is deterministic based on component type and scale.

---

## 2. Input

| Field | Source | Description |
|-------|--------|-------------|
| `state.architecture.components` | Architect Agent | Array of `{ name, azureService, description }` |
| `state.user_input` | User | Original project description (used for scale extraction) |

---

## 3. Processing

### 3.1 Scale Extraction

The agent parses the concurrent user count from the original user input using regex:

```python
users = 1000  # default
match = re.search(r'(\d[\d,]*)\s*(?:concurrent|simultaneous)?\s*users', requirements, re.I)
if match:
    users = int(match.group(1).replace(',', ''))
```

**Examples:**

| User Input | Extracted Users |
|------------|----------------|
| "platform for 10,000 concurrent users" | 10000 |
| "app with 500 users" | 500 |
| "build a web app" (no mention) | 1000 (default) |

### 3.2 SKU Selection Matrix

The `_select_sku(component_name, requirements)` function selects SKUs based on the Azure service type and user scale:

| Component Type (keyword match) | Users ≤ 1000 | Users 1001–5000 | Users > 5000 |
|-------------------------------|-------------|----------------|-------------|
| SQL / Database | Standard S1 | Standard S3 | Premium P4 |
| Redis / Cache | C0 | C1 | P1 |
| App Service / Web / API / Frontend / Backend | B1 | S1 | P2v3 |
| Search | Standard S1 | Standard S1 | Standard S1 |
| Cosmos | Standard | Standard | Standard |
| *(default / unrecognized)* | Standard | Standard | Standard |

**Keyword matching:** The component's `name` and `azureService` fields are searched (case-insensitive) to determine the service category.

### 3.3 Service Mapping

For each component in `state.architecture.components`:

1. Extract `component.name` and `component.azureService`
2. Call `_select_sku(name, requirements)` to determine the appropriate SKU
3. Build service selection with hardcoded region and standard capabilities

```python
selection = {
    "componentName": component["name"],
    "serviceName": component["azureService"],
    "sku": _select_sku(component["name"], requirements),
    "region": "eastus",
    "capabilities": ["High availability", "Auto-scaling", "Managed service"]
}
```

**Region:** Always `"eastus"` (hardcoded). Future enhancement may allow user-specified regions.

---

## 4. Output

The agent writes to `state.services`:

```python
state.services = {
    "selections": [
        {
            "componentName": "Web Frontend",
            "serviceName": "Azure App Service",
            "sku": "S1",
            "region": "eastus",
            "capabilities": ["High availability", "Auto-scaling", "Managed service"]
        },
        {
            "componentName": "Application Database",
            "serviceName": "Azure SQL Database",
            "sku": "Standard S1",
            "region": "eastus",
            "capabilities": ["High availability", "Auto-scaling", "Managed service"]
        },
        {
            "componentName": "Performance Cache",
            "serviceName": "Azure Cache for Redis",
            "sku": "C0",
            "region": "eastus",
            "capabilities": ["High availability", "Auto-scaling", "Managed service"]
        }
    ]
}
```

### 4.1 Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `selections` | `list[dict]` | Array of service selection objects |
| `selections[].componentName` | `str` | Name from architect's component list |
| `selections[].serviceName` | `str` | Azure service name (e.g., "Azure App Service") |
| `selections[].sku` | `str` | Selected SKU tier (e.g., "S1", "Premium P4") |
| `selections[].region` | `str` | Azure region, always `"eastus"` |
| `selections[].capabilities` | `list[str]` | Standard capabilities list |

---

## 5. Output Formatting (for chat)

```markdown
## ☁️ Azure Service Recommendations

| Component | Azure Service | SKU | Region |
|-----------|--------------|-----|--------|
| Web Frontend | Azure App Service | S1 | eastus |
| Application Database | Azure SQL Database | Standard S1 | eastus |
| Performance Cache | Azure Cache for Redis | C0 | eastus |

**Scale basis:** {users} concurrent users
```

---

## 6. Error Handling

| Failure | Fallback |
|---------|----------|
| No components in `state.architecture` | Return empty selections list |
| Component has no `azureService` field | Skip that component |
| SKU matching fails | Default to `"Standard"` tier |

---

## 7. Dependencies

| Direction | Agent | Relationship |
|-----------|-------|-------------|
| **Depends on** | Architect | Requires `state.architecture.components` |
| **Consumed by** | Cost Specialist | Reads `services.selections` for pricing |
| **Consumed by** | Business Value | Reads `services.selections` for impact analysis |
| **Consumed by** | Presentation | Reads `services.selections` for slide 5 |

---

## 8. Design Notes

- **No LLM calls:** This agent is purely deterministic — faster execution, no API cost, fully predictable output
- **Capabilities field:** Currently static for all services. Future enhancement may provide service-specific capabilities
- **Region hardcoding:** `"eastus"` is hardcoded. Regional selection could be added based on user input parsing (e.g., "deploy in Europe" → `"westeurope"`)

---

## 9. Acceptance Criteria

- [ ] Extracts concurrent user count from user input via regex
- [ ] Defaults to 1000 users when no count is specified
- [ ] Selects appropriate SKU tier based on user scale
- [ ] Maps every component from architect output to a service selection
- [ ] All selections include `componentName`, `serviceName`, `sku`, `region`, `capabilities`
- [ ] Output is deterministic — same input always produces same output
- [ ] Handles missing or empty architecture components gracefully
- [ ] `state.services` is populated after execution
