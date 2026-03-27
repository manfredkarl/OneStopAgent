# FRD: Cost Specialist Agent

> **Version:** 2.0  
> **Status:** Current  
> **Replaces:** specs/frd-cost.md (v1)  
> **Component:** `src/python-api/agents/cost_agent.py`, `src/python-api/services/pricing.py`

---

## 1. Overview

The Cost Specialist agent estimates Azure costs by querying the Azure Retail Prices API for live pricing data. It falls back to a comprehensive reference price dictionary when the API is unavailable or returns no results. All prices are converted to monthly costs and aggregated into a total estimate.

---

## 2. Input

| Field | Source | Description |
|-------|--------|-------------|
| `state.services.selections` | Azure Specialist | Array of `{ componentName, serviceName, sku, region }` |
| `state.user_input` | User | Original description (for context) |

---

## 3. Processing

### 3.1 Azure Retail Prices API

**Endpoint:** `https://prices.azure.com/api/retail/prices`

**Authentication:** None required — the API is publicly accessible.

**Request:**

```python
client.get(
    "https://prices.azure.com/api/retail/prices",
    params={"$filter": f"serviceName eq '{service_name}' and armRegionName eq '{region}'"},
    timeout=8  # seconds
)
```

**Response parsing:**

```json
{
  "Items": [
    {
      "retailPrice": 0.10,
      "skuName": "Standard S1",
      "armSkuName": "S1",
      "serviceName": "Azure App Service",
      "armRegionName": "eastus"
    }
  ]
}
```

**SKU matching logic:**

```python
for item in response["Items"]:
    sku_name = (item.get("skuName") or "").lower()
    arm_sku = (item.get("armSkuName") or "").lower()
    if sku.lower() in sku_name or sku.lower() in arm_sku:
        price = item.get("retailPrice", 0.0)
        if price > 0:
            return price
```

### 3.2 Fallback Pricing (MOCK_PRICES)

When the API fails, times out, or returns no matching SKU, the agent falls back to a reference price dictionary.

**Fallback cascade:**

1. Try live Azure Pricing API
2. Search `MOCK_PRICES` by exact service name + SKU match
3. Return first available price for that service (any SKU)
4. Return `0.0` as last resort

**Reference price coverage (subset):**

| Service | SKUs Available | Price Range |
|---------|---------------|-------------|
| Azure App Service | Free, B1, B2, S1, S2, P1v3, P2v3, P3v3 | $0–$0.60/hr |
| Azure SQL Database | Basic, Standard S0–S2, Premium P1/P4 | $4.99–$930/mo |
| Azure Cache for Redis | C0/C1 Basic, C1 Standard, P1 Premium | $16–$172/mo |
| Azure Cosmos DB | Serverless, 400 RU/s, 1000 RU/s | $0.25–$58.40/mo |
| Azure Blob Storage | Hot/Cool/Archive LRS | $0.002–$0.018/GB |
| Azure Functions | Consumption, Premium EP1 | $0–$0.173/hr |
| AKS | Standard, B4ms, D4s v3, D8s v3 | $0.10–$0.384/hr |
| API Management | Developer, Standard, Premium | $3.50–$2794/mo |
| IoT Hub | Free, S1, S2, S3 | $0–$2500/mo |
| Azure CDN | Standard, Premium | $0.081–$0.17/query |
| Synapse Analytics | DW100c–DW500c | $1.20–$6.00/hr |
| Power BI | Pro, Premium P1 | $9.99–$4995/mo |
| *(+12 more services)* | *(various SKUs)* | *(various prices)* |

### 3.3 Cost Calculation

**Price convention:**

```python
# If price < $1.0, treat as hourly → multiply by 730 hours/month
# If price ≥ $1.0, treat as already monthly
monthly_cost = price * 730 if price < 1.0 else price
```

**For each service in `state.services.selections`:**

1. Call `query_azure_pricing_sync(service_name, sku, region)` to get unit price
2. Convert to monthly cost using the price convention
3. Build cost item with service details

**Aggregation:**

```python
total_monthly = sum(item["monthlyCost"] for item in items)
total_annual = total_monthly * 12
```

### 3.4 Pricing Source Tracking

Each estimate is tagged with its source:

| Source | Meaning |
|--------|---------|
| `"live"` | Price retrieved from Azure Retail Prices API |
| `"cached"` | Price from a cached API response |
| `"approximate"` | Price from reference data (MOCK_PRICES fallback) |

---

## 4. Output

The agent writes to `state.costs`:

```python
state.costs = {
    "estimate": {
        "currency": "USD",
        "items": [
            {
                "serviceName": "Azure App Service",
                "sku": "S1",
                "region": "eastus",
                "unitPrice": 0.10,
                "monthlyCost": 73.00
            },
            {
                "serviceName": "Azure SQL Database",
                "sku": "Standard S1",
                "region": "eastus",
                "unitPrice": 15.01,
                "monthlyCost": 15.01
            }
        ],
        "totalMonthly": 88.01,
        "totalAnnual": 1056.12,
        "assumptions": [
            "Based on 730 hours/month for hourly-priced services",
            "Pay-as-you-go pricing"
        ],
        "pricingSource": "live"
    }
}
```

### 4.1 Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `estimate.currency` | `str` | Always `"USD"` |
| `estimate.items` | `list[dict]` | Per-service cost breakdown |
| `estimate.items[].serviceName` | `str` | Azure service name |
| `estimate.items[].sku` | `str` | Selected SKU tier |
| `estimate.items[].region` | `str` | Azure region |
| `estimate.items[].unitPrice` | `float` | Raw price from API/reference |
| `estimate.items[].monthlyCost` | `float` | Calculated monthly cost |
| `estimate.totalMonthly` | `float` | Sum of all monthly costs |
| `estimate.totalAnnual` | `float` | `totalMonthly × 12` |
| `estimate.assumptions` | `list[str]` | Assumptions used in calculations |
| `estimate.pricingSource` | `str` | `"live"`, `"cached"`, or `"approximate"` |

---

## 5. Output Formatting (for chat)

```markdown
## 💰 Cost Estimate

| Service | SKU | Monthly Cost |
|---------|-----|-------------|
| Azure App Service | S1 | $73.00 |
| Azure SQL Database | Standard S1 | $15.01 |
| Azure Cache for Redis | C0 | $16.00 |

**Total Monthly:** $104.01  
**Total Annual:** $1,248.12

> *Pricing source: live Azure Retail Prices API*  
> *Assumptions: Based on 730 hours/month for hourly-priced services. Pay-as-you-go pricing.*
```

---

## 6. Error Handling

| Failure | Fallback |
|---------|----------|
| API timeout (>8s) | Fall back to MOCK_PRICES |
| API returns no results for service | Fall back to MOCK_PRICES for that service |
| API returns no matching SKU | Use first available price for that service |
| No price found anywhere | Use $0.00 for that service |
| No services in `state.services` | Return empty estimate with $0 totals |

---

## 7. Dependencies

| Direction | Agent | Relationship |
|-----------|-------|-------------|
| **Depends on** | Azure Specialist | Requires `state.services.selections` |
| **Consumed by** | Business Value | Reads `costs.estimate.totalMonthly` for ROI analysis |
| **Consumed by** | Presentation | Reads `costs.estimate.items` for slide 6 |

---

## 8. Design Notes

- **No authentication:** The Azure Retail Prices API is free and public — no keys or tokens needed
- **Price convention threshold ($1.0):** Simple heuristic — compute services are typically priced hourly (< $1), while managed services are priced monthly (≥ $1). This is a trade-off for simplicity vs. checking `unitOfMeasure`
- **8-second timeout:** Keeps the pipeline responsive; reference prices provide reasonable approximations
- **No instance scaling:** Currently 1 instance per service. Future enhancement could multiply by `ceil(users / usersPerInstance)`

---

## 9. Acceptance Criteria

- [ ] Queries Azure Retail Prices API with correct OData filter syntax
- [ ] Falls back to reference prices when API is unavailable
- [ ] Converts hourly prices to monthly using 730 hours/month
- [ ] Calculates correct monthly and annual totals
- [ ] Tags pricing source as `"live"` or `"approximate"`
- [ ] Handles API timeouts gracefully (≤ 8s)
- [ ] Produces valid cost items for each service selection
- [ ] `state.costs` is populated after execution
- [ ] Empty services list produces empty estimate (not an error)
