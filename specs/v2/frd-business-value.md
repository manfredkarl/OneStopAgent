# FRD: Business Value Agent

> **Version:** 2.0  
> **Status:** Current  
> **Replaces:** specs/frd-business-value.md (v1)  
> **Component:** `src/python-api/agents/business_value_agent.py`

---

## 1. Overview

The Business Value agent analyzes ROI and business impact using a single LLM call with full solution context. It produces industry-specific value drivers with quantified estimates, an executive summary, confidence level, and a standard disclaimer.

---

## 2. Input

| Field | Source | Description |
|-------|--------|-------------|
| `state.user_input` | User | Original project description |
| `state.customer_name` | User | Customer name (optional) |
| `state.architecture` | Architect | Architecture design with components |
| `state.services` | Azure Specialist | Service selections with SKUs |
| `state.costs` | Cost Specialist | Cost estimate with monthly total |

---

## 3. Processing

### 3.1 LLM Call

**Single LLM call** with the complete solution context assembled from all previous agent outputs.

**System prompt:**

```
You are an Azure business value analyst. Return ONLY valid JSON.
```

**User prompt template:**

```
Analyze the business value of this Azure solution:

Customer: {customer_name}
Use Case: {user_input}
Architecture Components: {components_json}
Azure Services: {selections_json}
Monthly Cost: ${monthly_cost}

Provide:
1. 3-5 specific value drivers relevant to THIS use case (not generic)
2. Quantified estimates where possible (e.g., "15-25% increase in conversion rates")
3. A 100-word executive summary mentioning the customer and their specific scenario
4. Confidence level (conservative/moderate/optimistic)

Return ONLY JSON:
{"drivers": [{"name": "...", "impact": "...", "quantifiedEstimate": "..."}], "executiveSummary": "...", "confidenceLevel": "...", "disclaimer": "..."}
```

### 3.2 Response Parsing

The LLM response is parsed as JSON. The expected structure:

```json
{
  "drivers": [
    {
      "name": "Cloud Migration Savings",
      "impact": "Typical 20-40% cost reduction versus on-premises infrastructure",
      "quantifiedEstimate": "Estimated 30% savings on infrastructure spend"
    },
    {
      "name": "Operational Efficiency",
      "impact": "Reduced manual management through managed Azure services",
      "quantifiedEstimate": "40% reduction in operational overhead"
    },
    {
      "name": "Time to Market",
      "impact": "Accelerated development using PaaS services",
      "quantifiedEstimate": "2-3 month reduction in deployment timeline"
    }
  ],
  "executiveSummary": "The proposed Azure solution for {customer} delivers significant value through cloud-native architecture, offering 20-40% infrastructure savings while accelerating time-to-market by 2-3 months. The platform's managed services reduce operational overhead by 40%, allowing the team to focus on core business innovation rather than infrastructure management.",
  "confidenceLevel": "moderate",
  "disclaimer": "These estimates are based on industry benchmarks and typical Azure migration outcomes. Actual results may vary based on implementation specifics, current infrastructure costs, and operational maturity."
}
```

### 3.3 Fallback on LLM Failure

If the LLM call fails or returns unparseable JSON, a generic fallback is used:

```python
{
    "drivers": [
        {
            "name": "Cloud Migration Savings",
            "impact": "Typical 20-40% cost reduction",
            "quantifiedEstimate": "Estimated 30% savings"
        }
    ],
    "executiveSummary": "The proposed Azure solution offers significant value for the customer.",
    "confidenceLevel": "moderate",
    "disclaimer": "These are estimates based on industry benchmarks."
}
```

---

## 4. Output

The agent writes to `state.business_value`:

```python
state.business_value = {
    "drivers": [
        {
            "name": "Cloud Migration Savings",
            "impact": "Typical 20-40% cost reduction",
            "quantifiedEstimate": "Estimated 30% savings"
        },
        {
            "name": "Operational Efficiency",
            "impact": "Reduced manual management",
            "quantifiedEstimate": "40% reduction in ops time"
        }
    ],
    "executiveSummary": "100-200 word narrative summary...",
    "confidenceLevel": "conservative | moderate | optimistic",
    "disclaimer": "Disclaimer text..."
}
```

### 4.1 Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `drivers` | `list[dict]` | 3-5 industry-specific value drivers |
| `drivers[].name` | `str` | Value driver name (e.g., "Cloud Migration Savings") |
| `drivers[].impact` | `str` | Description of business impact |
| `drivers[].quantifiedEstimate` | `str` | Quantified estimate (e.g., "30% savings") |
| `executiveSummary` | `str` | 100-200 word executive summary |
| `confidenceLevel` | `str` | `"conservative"`, `"moderate"`, or `"optimistic"` |
| `disclaimer` | `str` | Standard disclaimer about estimates |

---

## 5. Output Formatting (for chat)

```markdown
## 📊 Business Value Analysis

### Value Drivers

| Driver | Impact | Estimate |
|--------|--------|----------|
| Cloud Migration Savings | Typical 20-40% cost reduction | 30% savings |
| Operational Efficiency | Reduced manual management | 40% reduction in ops time |
| Time to Market | Accelerated development | 2-3 month reduction |

### Executive Summary

{executiveSummary}

**Confidence Level:** {confidenceLevel}

> *{disclaimer}*
```

---

## 6. Error Handling

| Failure | Fallback |
|---------|----------|
| LLM call fails (timeout, API error) | Use generic 1-driver fallback |
| LLM returns invalid JSON | Parse what's possible, fall back to generic |
| Missing cost data in state | Omit monthly cost from prompt, continue analysis |
| Missing architecture/services data | Analyze based on user input alone |

---

## 7. Dependencies

| Direction | Agent | Relationship |
|-----------|-------|-------------|
| **Depends on** | Architect | Reads `architecture.components` |
| **Depends on** | Azure Specialist | Reads `services.selections` |
| **Depends on** | Cost Specialist | Reads `costs.estimate.totalMonthly` |
| **Consumed by** | Presentation | Reads `business_value.drivers` and `executiveSummary` for slide 7 |

---

## 8. Design Notes

- **Single LLM call:** All context is packed into one prompt for efficiency and coherence — the model sees the full picture
- **JSON-only output:** The system prompt enforces JSON-only responses, which simplifies parsing but occasionally requires fallback handling
- **Industry specificity:** The prompt explicitly asks for use-case-specific drivers (not generic "cloud benefits") to maximize value for customer presentations
- **Executive summary length:** 100-200 words targets the right level of detail for a PowerPoint slide or executive briefing

---

## 9. Acceptance Criteria

- [ ] Sends full solution context (architecture, services, costs) to LLM
- [ ] Returns 3-5 value drivers with quantified estimates
- [ ] Executive summary is 100-200 words and mentions the customer scenario
- [ ] Confidence level is one of: `conservative`, `moderate`, `optimistic`
- [ ] Includes a disclaimer
- [ ] Falls back to generic drivers on LLM failure
- [ ] Falls back to generic drivers on JSON parse failure
- [ ] `state.business_value` is populated after execution
- [ ] Value drivers are specific to the customer's industry and use case
