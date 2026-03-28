# FRD-04: Financial Agents (Cost + ROI)

> **Source of Truth:** `specs/v2/refactor.md` — §8 (Cost Agent), §10 (ROI Agent)
> **Status:** Draft
> **Last Updated:** 2025-07-28

---

## 1. Overview

Two agents that handle the financial analysis of the Azure solution. **CostAgent** estimates monthly and annual Azure spending by querying the Azure Retail Prices API for each service selection. **ROIAgent** calculates return on investment by comparing annual Azure costs against monetizable business value drivers.

These agents run sequentially in the Mode B execution plan (refactor.md §2.3):

```
... → AzureSpecialistAgent → CostAgent → BusinessValueAgent → ROIAgent → ...
```

CostAgent consumes `state.services.selections` (from AzureSpecialistAgent, §7) and writes to `state.costs`. ROIAgent consumes `state.costs.estimate.totalAnnual` and `state.business_value.drivers` (from BusinessValueAgent, §9) and writes to `state.roi`. Both are **deterministic** — no LLM calls (§3.1). Both communicate exclusively through `AgentState` (§12) — no cross-agent imports (§3.2).

---

## 2. CostAgent

### 2.1 Purpose

Estimate monthly and annual Azure costs for every service in the solution by querying the Azure Retail Prices API. Tag each price with its source reliability (live, fallback, approximate) and document all assumptions for consumption-based services.

*(Refactor.md §8)*

### 2.2 Input (from AgentState)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `state.services.selections` | `list[dict]` | AzureSpecialistAgent output (§7, FRD-03 §3.8) | Service selections with `serviceName`, `sku`, `region` |
| `state.user_input` | `str` | Original user description | Used for consumption scale heuristics |

Each selection provides the fields needed to construct the API query:
- `serviceName` → OData `serviceName` filter
- `sku` → SKU matching against API response
- `region` → OData `armRegionName` filter

### 2.3 Azure Retail Prices API

#### 2.3.1 Endpoint & Query Format

*(Refactor.md §8 — MUST USE)*

```
GET https://prices.azure.com/api/retail/prices
```

- **No authentication required** — public API
- **OData filter** for each service:

```python
PRICING_API_URL = "https://prices.azure.com/api/retail/prices"

def _build_query(self, service_name: str, region: str) -> str:
    """Build OData filter for the Azure Retail Prices API.
    
    Example output:
    $filter=serviceName eq 'Azure App Service' and armRegionName eq 'eastus'
    """
    return (
        f"$filter=serviceName eq '{service_name}' "
        f"and armRegionName eq '{region}'"
    )

def _query_prices(self, service_name: str, region: str) -> list[dict]:
    """Query Azure Retail Prices API.
    
    Returns: list of price items from API response.
    Raises: requests.Timeout after 10 seconds.
    """
    params = {"$filter": f"serviceName eq '{service_name}' and armRegionName eq '{region}'"}
    response = requests.get(PRICING_API_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("Items", [])
```

#### 2.3.2 Response Parsing

Each API response item contains:

```python
{
    "retailPrice": 0.123,          # Price per unit
    "unitOfMeasure": "1 Hour",     # Billing unit
    "skuName": "P2v3",             # SKU identifier
    "serviceName": "Azure App Service",
    "armRegionName": "eastus",
    "productName": "...",
    "meterName": "...",
    # ... other fields
}
```

The agent extracts `retailPrice` and `unitOfMeasure` to calculate monthly costs.

### 2.4 Pricing Source Behavior

*(Directly from refactor.md §8 — Pricing Source Behavior)*

The agent classifies each price lookup into one of five scenarios:

| # | Scenario | Behavior | Source Tag | User Note |
|---|----------|----------|-----------|-----------|
| 1 | API returns matching SKU | Use API price directly | `"live"` | None |
| 2 | API returns results but no SKU match | Use cheapest result for that service | `"live-fallback"` | `"Exact SKU not found, using closest match"` |
| 3 | API returns no results for service | Use `MOCK_PRICES` dict | `"approximate"` | None |
| 4 | API timeout or error | Use `MOCK_PRICES` dict | `"approximate"` | `"API unavailable, using reference pricing"` |
| 5 | Regional mismatch (service unavailable) | Re-query with `eastus` region | `"live"` | `"Service not available in {region}, pricing for eastus"` |

Implementation:

```python
MOCK_PRICES = {
    "Azure App Service": {"B1": 54.75, "S1": 73.00, "P2v3": 245.28, "P3v3": 490.56},
    "Azure SQL Database": {"Basic": 4.99, "Standard S1": 30.00, "Premium P4": 930.00, "Business Critical": 5500.00},
    "Azure Cache for Redis": {"C0": 16.00, "C1": 41.00, "P1": 224.00, "P3": 862.00},
    "Azure Cosmos DB": {"Serverless": 25.00, "Autoscale 1000 RU/s": 58.40, "Autoscale 10000 RU/s": 584.00, "Autoscale 50000 RU/s": 2920.00},
    "Azure Functions": {"Consumption": 0.00, "Premium EP1": 145.28, "Premium EP3": 580.90},
    "Azure OpenAI": {"Standard S0": 0.00},  # usage-based
    "Azure AI Search": {"Basic": 75.78, "Standard S1": 250.39},
    "Azure Container Apps": {"Consumption": 0.00, "Dedicated": 220.00},
    "Azure Kubernetes Service": {"Standard_D4s_v3 (3 nodes)": 438.00},
    "Azure Event Hubs": {"Standard": 11.16, "Premium": 870.00},
    "Azure Service Bus": {"Standard": 9.81, "Premium": 677.08},
    "Azure Blob Storage": {"Standard LRS": 21.00, "GRS": 43.00},
    "Azure Key Vault": {"Standard": 0.00, "Premium": 0.00},  # per-operation
    "Azure Monitor": {"Pay-as-you-go": 2.76},
    "Application Insights": {"Pay-as-you-go": 2.76},
    "Azure Front Door": {"Standard": 35.00, "Premium": 330.00},
    "Azure API Management": {"Developer": 49.27, "Standard": 699.55},
    "Microsoft Fabric": {"F2": 262.80},
}

def _resolve_price(self, service_name: str, sku: str, region: str) -> tuple[float, str, str | None]:
    """Resolve price for a service/SKU/region combination.
    
    Returns: (monthly_cost, pricing_source, pricing_note)
    
    Implements the 5-tier pricing source behavior from §8.
    """
    try:
        items = self._query_prices(service_name, region)
    except (requests.Timeout, requests.RequestException):
        # Scenario 4: API timeout or error
        cost = self._mock_price(service_name, sku)
        return (cost, "approximate", "API unavailable, using reference pricing")
    
    if not items:
        # Scenario 5: Try eastus fallback for regional mismatch
        if region != "eastus":
            try:
                items = self._query_prices(service_name, "eastus")
                if items:
                    price, source, note = self._match_sku(items, sku)
                    return (price, source, f"Service not available in {region}, pricing for eastus")
            except (requests.Timeout, requests.RequestException):
                pass
        # Scenario 3: No results at all
        cost = self._mock_price(service_name, sku)
        return (cost, "approximate", None)
    
    return self._match_sku(items, sku)

def _match_sku(self, items: list[dict], target_sku: str) -> tuple[float, str, str | None]:
    """Match SKU in API response items.
    
    Returns: (monthly_cost, pricing_source, pricing_note)
    """
    # Scenario 1: Exact SKU match
    for item in items:
        if target_sku.lower() in item.get("skuName", "").lower():
            return (self._to_monthly(item), "live", None)
    
    # Scenario 2: No SKU match — use cheapest
    cheapest = min(items, key=lambda i: i.get("retailPrice", float("inf")))
    return (
        self._to_monthly(cheapest),
        "live-fallback",
        "Exact SKU not found, using closest match"
    )
```

### 2.5 Consumption-Based Service Assumptions

*(Directly from refactor.md §8 — Consumption-Based Services)*

Some Azure services have usage-based pricing that cannot be inferred from architecture alone. The agent uses these **reasonable demo assumptions**:

| Service | Assumption | Used For Cost Calc |
|---------|-----------|-------------------|
| Azure Functions (Consumption) | 1M executions/month, 400K GB-s | Execution + memory cost |
| Azure Blob Storage | 100 GB stored, 10K read operations/month | Storage + operations cost |
| Azure Cosmos DB | 1,000 RU/s provisioned, 50 GB stored | RU throughput + storage cost |
| Azure Event Hubs | 1M events/month | Event ingestion cost |
| Azure OpenAI | 1M tokens/month | Token usage cost |
| Azure AI Search | 1 search unit | Base unit cost |
| Azure Monitor | 5 GB logs ingested/month | Log ingestion cost |

These assumptions **MUST** be listed in `estimate.assumptions` (§8).

```python
CONSUMPTION_ASSUMPTIONS = {
    "Azure Functions": "1M executions/month, 400K GB-s",
    "Azure Blob Storage": "100 GB stored, 10K read operations/month",
    "Azure Cosmos DB": "1,000 RU/s provisioned, 50 GB stored",
    "Azure Event Hubs": "1M events/month",
    "Azure OpenAI": "1M tokens/month",
    "Azure AI Search": "1 search unit",
    "Azure Monitor": "5 GB logs ingested/month",
}
```

### 2.6 Cost Calculation

Monthly cost is derived from the API's `retailPrice` and `unitOfMeasure`:

```python
def _to_monthly(self, price_item: dict) -> float:
    """Convert API price item to monthly cost.
    
    Conversion rules:
    - Hourly: retailPrice × 730 hours/month
    - Monthly: retailPrice (direct)
    - Per GB: retailPrice × assumed volume
    - Per 10K operations: retailPrice × assumed operations / 10000
    """
    price = price_item.get("retailPrice", 0.0)
    unit = price_item.get("unitOfMeasure", "").lower()
    
    if "hour" in unit:
        return price * 730  # 730 hours/month standard
    elif "month" in unit:
        return price
    elif "gb" in unit:
        return price * 100  # default 100 GB assumption
    elif "10k" in unit or "10,000" in unit:
        return price * 1    # 10K operations assumption
    else:
        return price * 730  # default to hourly assumption
```

**Annual cost** is simply `monthly × 12`.

**Instance scaling:** If the architecture specifies multiple instances (e.g., AKS with 3 nodes), multiply accordingly:

```python
def _apply_instance_count(self, monthly_cost: float, sku: str) -> float:
    """Multiply cost by instance count if SKU specifies multiple instances.
    
    Example: 'Standard_D4s_v3 (3 nodes)' → multiply by 3
    """
    match = re.search(r"\((\d+)\s*nodes?\)", sku)
    if match:
        return monthly_cost * int(match.group(1))
    return monthly_cost
```

### 2.7 Output Schema

Written to `state.costs` (§8, §12):

```python
state.costs = {
    "estimate": {
        "currency": "USD",
        "items": [
            {
                "serviceName": str,      # e.g., "Azure App Service"
                "sku": str,              # e.g., "P2v3"
                "region": str,           # e.g., "eastus"
                "monthlyCost": float,    # e.g., 245.28
                "pricingNote": str | None  # e.g., "Exact SKU not found, using closest match"
            }
        ],
        "totalMonthly": float,       # Sum of all items' monthlyCost
        "totalAnnual": float,        # totalMonthly × 12
        "assumptions": [str],        # e.g., ["Based on 730 hours/month", "Pay-as-you-go pricing", ...]
        "pricingSource": str         # Overall source: "live" | "live-fallback" | "approximate"
    }
}
```

**`pricingSource` (overall) logic:**
- If ALL items are `"live"` → `"live"`
- If ANY item is `"approximate"` → `"approximate"`
- Otherwise → `"live-fallback"`

**`assumptions` always includes:**
1. `"Based on 730 hours/month"`
2. `"Pay-as-you-go pricing (no reservations or savings plans)"`
3. Any consumption assumptions from §2.5 that apply to services in the solution

### 2.8 Error Handling

*(Refactor.md §8, §17)*

| Failure | Fallback | Source Tag | User Note |
|---------|----------|-----------|-----------|
| API timeout (>10s) | Use `MOCK_PRICES` dict | `"approximate"` | `"API unavailable, using reference pricing"` |
| API HTTP error (4xx/5xx) | Use `MOCK_PRICES` dict | `"approximate"` | `"API unavailable, using reference pricing"` |
| Missing SKU in `MOCK_PRICES` | Use cheapest available price for that service | `"approximate"` | `"SKU not found, using base tier pricing"` |
| Service not in `MOCK_PRICES` | Set cost to `$0.00` | `"approximate"` | `"Pricing unavailable for {serviceName}"` |
| Regional mismatch | Re-query with `eastus` | `"live"` | `"Service not available in {region}, pricing for eastus"` |

```python
def _mock_price(self, service_name: str, sku: str) -> float:
    """Get mock price from fallback dictionary.
    
    Priority:
    1. Exact service + SKU match
    2. Cheapest SKU for that service
    3. $0.00 if service not in MOCK_PRICES
    """
    service_prices = MOCK_PRICES.get(service_name, {})
    if sku in service_prices:
        return service_prices[sku]
    if service_prices:
        return min(service_prices.values())  # cheapest match
    return 0.0
```

**Principle (§17):** The system should NEVER crash. Every API failure is caught, a fallback price is used, the source is tagged, and the pipeline continues.

---

## 3. ROIAgent

### 3.1 Purpose

Calculate return on investment (ROI) by comparing annual Azure costs against monetizable business value drivers. Produce ROI percentage, payback period, and a clear separation of quantitative vs. qualitative benefits. This is **deterministic math** — no LLM calls (§10, §3.1).

### 3.2 Input (from AgentState)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `state.costs.estimate.totalAnnual` | `float` | CostAgent output (§2.7) | Annual Azure cost |
| `state.business_value.drivers` | `list[dict]` | BusinessValueAgent output (§9) | Value drivers with `monetizable` flag |

Each driver has the schema (§9):

```python
{
    "name": str,            # e.g., "Reduced infrastructure downtime"
    "description": str,     # Detailed explanation
    "estimate": str,        # e.g., "30% reduction in downtime costs"
    "monetizable": bool     # True if estimate can be converted to dollars
}
```

### 3.3 Monetizable Value Driver Conversion

*(Directly from refactor.md §10 — Monetizable Value Drivers)*

Only drivers with `monetizable: True` are included in the quantitative ROI. The ROIAgent converts each driver's `estimate` string to an annual dollar amount using these rules:

| # | Estimate Format | Example | Conversion Method | Default Values |
|---|----------------|---------|-------------------|----------------|
| 1 | `"X% reduction in {cost_category}"` | `"30% reduction in downtime costs"` | `annual_cost × X/100` (if cost category can be inferred from architecture) | Infer from `state.costs.estimate.totalAnnual` |
| 2 | `"X% increase in {revenue_metric}"` | `"15% increase in conversion rate"` | Requires user input or uses industry benchmark | Uses industry benchmark if available |
| 3 | `"$X saved per month/year"` | `"$5,000 saved per month"` | Direct use (convert monthly to annual if needed) | N/A |
| 4 | `"X hours saved per week"` | `"20 hours saved per week"` | `X × 52 × hourly_rate` | Default `$75/hr` for IT staff |
| 5 | Cannot be converted | `"Improved brand perception"` | Exclude from ROI calculation | Listed as qualitative benefit |

```python
DEFAULT_HOURLY_RATE = 75  # USD, for IT staff (§10)

def _monetize_driver(self, driver: dict, annual_cost: float) -> dict | None:
    """Convert a monetizable driver's estimate to an annual dollar value.
    
    Returns: {"name": str, "annual_value": float, "method": str}
             or None if conversion fails.
    """
    estimate = driver.get("estimate", "").lower()
    
    # Pattern 1: "X% reduction in ..."
    match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*reduction", estimate)
    if match:
        pct = float(match.group(1))
        value = annual_cost * pct / 100
        return {"name": driver["name"], "annual_value": value, "method": f"{pct}% of annual cost"}
    
    # Pattern 2: "X% increase in ..."
    match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*increase", estimate)
    if match:
        pct = float(match.group(1))
        value = annual_cost * pct / 100  # benchmark approximation
        return {"name": driver["name"], "annual_value": value, "method": f"{pct}% revenue increase (benchmark)"}
    
    # Pattern 3: "$X saved per month" or "$X saved per year"
    match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:saved\s+)?per\s+(month|year)", estimate)
    if match:
        amount = float(match.group(1).replace(",", ""))
        period = match.group(2)
        annual = amount * 12 if period == "month" else amount
        return {"name": driver["name"], "annual_value": annual, "method": f"Direct: ${amount}/{period}"}
    
    # Pattern 4: "X hours saved per week"
    match = re.search(r"(\d+(?:\.\d+)?)\s*hours?\s*saved\s*per\s*week", estimate)
    if match:
        hours = float(match.group(1))
        value = hours * 52 * DEFAULT_HOURLY_RATE
        return {"name": driver["name"], "annual_value": value, "method": f"{hours}h/week × 52 × ${DEFAULT_HOURLY_RATE}/hr"}
    
    # Cannot convert
    return None
```

### 3.4 ROI Calculation

*(Directly from refactor.md §10 — Calculation)*

```python
def _calculate_roi(self, annual_cost: float, annual_value: float) -> float | None:
    """Calculate ROI percentage.
    
    Formula: ((annual_value - annual_cost) / annual_cost) × 100
    
    Returns None if annual_cost is 0 (avoid division by zero)
    or if annual_value is None/0.
    """
    if not annual_cost or not annual_value:
        return None
    return ((annual_value - annual_cost) / annual_cost) * 100
```

### 3.5 Payback Period

*(Directly from refactor.md §10 — Calculation)*

```python
def _calculate_payback(self, annual_cost: float, annual_value: float) -> float | None:
    """Calculate payback period in months.
    
    Formula: annual_cost / (annual_value / 12)
    
    Returns None if annual_value is 0 or None.
    """
    if not annual_value:
        return None
    monthly_value = annual_value / 12
    if monthly_value == 0:
        return None
    return annual_cost / monthly_value
```

### 3.6 Non-Calculable Case

*(Refactor.md §10)*

When `annual_value` cannot be reliably calculated (no monetizable drivers, or all conversion attempts fail):

- `roi_percent = None`
- `payback_months = None`
- `annual_value = None`
- Report: `"ROI cannot be calculated quantitatively — see qualitative benefits below."`
- All non-monetizable drivers are listed in `qualitative_benefits`

```python
def _handle_non_calculable(self, drivers: list[dict]) -> dict:
    """Handle case where no drivers can be monetized.
    
    Returns partial state.roi with None values and qualitative benefits.
    """
    return {
        "annual_cost": None,  # will be filled by caller
        "annual_value": None,
        "roi_percent": None,
        "payback_months": None,
        "monetized_drivers": [],
        "qualitative_benefits": [
            f"{d['name']}: {d['description']}" for d in drivers
        ],
        "assumptions": [
            "ROI cannot be calculated quantitatively — see qualitative benefits below."
        ]
    }
```

### 3.7 Output Schema

Written to `state.roi` (§10, §12):

```python
state.roi = {
    "annual_cost": float,               # e.g., 14400.0 (from state.costs.estimate.totalAnnual)
    "annual_value": float | None,       # e.g., 50000.0 (sum of monetized drivers) or None
    "roi_percent": float | None,        # e.g., 247.0 or None if not calculable
    "payback_months": float | None,     # e.g., 3.5 or None if not calculable
    "monetized_drivers": [              # Drivers that were successfully monetized
        {
            "name": str,                # e.g., "Reduced infrastructure downtime"
            "annual_value": float,      # e.g., 25000.0
            "method": str               # e.g., "30% of annual cost"
        }
    ],
    "qualitative_benefits": [str],      # Non-monetizable driver descriptions
    "assumptions": [str]                # e.g., ["IT staff hourly rate: $75", ...]
}
```

### 3.8 No LLM Required

This agent is **entirely deterministic** (§3.1, §10). It uses:
- Regex for estimate parsing
- Arithmetic for ROI and payback calculations
- Static rules for driver classification

No `llm.invoke()` calls. No external API calls. No MCP calls.

---

## 4. Agent Interaction

### Data Flow

```
┌─────────────────────┐
│ AzureSpecialistAgent│
│   (§7, FRD-03)      │
│                     │
│ Output:             │
│ state.services.     │
│ selections          │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│     CostAgent       │
│   (§8, FRD-04 §2)   │
│                     │
│ Reads:              │
│ • services.         │
│   selections[]      │
│   ├ serviceName     │
│   ├ sku             │
│   └ region          │
│                     │
│ Writes:             │
│ • costs             │
│   └ estimate        │
│     ├ items[]       │
│     ├ totalMonthly  │
│     ├ totalAnnual   │
│     ├ assumptions   │
│     └ pricingSource │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ BusinessValueAgent  │
│   (§9, separate FRD)│
│                     │
│ Output:             │
│ state.business_     │
│ value.drivers       │
│ (with monetizable   │
│  flags)             │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│     ROIAgent        │
│   (§10, FRD-04 §3)  │
│                     │
│ Reads:              │
│ • costs.estimate.   │
│   totalAnnual       │
│ • business_value.   │
│   drivers[]         │
│   ├ estimate        │
│   └ monetizable     │
│                     │
│ Writes:             │
│ • roi               │
│   ├ annual_cost     │
│   ├ annual_value    │
│   ├ roi_percent     │
│   ├ payback_months  │
│   ├ monetized_      │
│   │ drivers         │
│   ├ qualitative_    │
│   │ benefits        │
│   └ assumptions     │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ PresentationAgent   │
│   (§11, separate    │
│    FRD)             │
└─────────────────────┘
```

**Key contracts:**
- CostAgent **requires** at least one entry in `state.services.selections` — if empty, writes a zero-cost estimate with a note
- ROIAgent **requires** `state.costs.estimate.totalAnnual` — if `state.costs` is empty (CostAgent was skipped §14.3), ROI cannot be calculated
- ROIAgent **requires** `state.business_value.drivers` — if BusinessValueAgent was skipped, all benefits are qualitative
- If CostAgent step was skipped (user toggled it off), PM warns: "Disabling Cost Specialist means no pricing data — ROI calculation will be qualitative only." (§14.3)

---

## 5. Acceptance Criteria

### CostAgent

- [ ] Queries Azure Retail Prices API at `https://prices.azure.com/api/retail/prices` with correct OData filters
- [ ] OData filter uses `serviceName eq '{name}' and armRegionName eq '{region}'` format
- [ ] API requires no authentication
- [ ] Exact SKU match tagged as `"live"` pricing source
- [ ] No SKU match but results exist → uses cheapest, tagged as `"live-fallback"` with note
- [ ] No API results → falls back to `MOCK_PRICES`, tagged as `"approximate"`
- [ ] API timeout/error → falls back to `MOCK_PRICES`, tagged as `"approximate"` with note
- [ ] Regional mismatch → re-queries with `eastus`, adds note about region substitution
- [ ] Consumption assumptions listed for usage-based services (Functions, Blob, Cosmos DB, Event Hubs, OpenAI, AI Search, Monitor)
- [ ] All consumption assumptions appear in `estimate.assumptions`
- [ ] Hourly prices converted via `× 730` hours/month
- [ ] Multi-instance SKUs (e.g., AKS 3 nodes) multiply cost by instance count
- [ ] Output includes `totalMonthly` (sum of items) and `totalAnnual` (× 12)
- [ ] Overall `pricingSource` correctly reflects worst-case across all items
- [ ] Missing service in `MOCK_PRICES` → `$0.00` with `"Pricing unavailable"` note (§17)
- [ ] Agent never crashes on API failure — all exceptions caught and handled (§17)
- [ ] No LLM calls — agent is fully deterministic

### ROIAgent

- [ ] ROI calculated only from monetizable drivers (`monetizable: True`)
- [ ] Non-monetizable drivers listed as qualitative benefits (not included in ROI math)
- [ ] `"X% reduction"` estimates converted using `annual_cost × X/100`
- [ ] `"X% increase"` estimates converted using benchmark approximation
- [ ] `"$X saved per month/year"` estimates used directly (monthly × 12 if needed)
- [ ] `"X hours saved per week"` estimates converted using `X × 52 × $75/hr`
- [ ] Default IT staff hourly rate is `$75` (documented in assumptions)
- [ ] ROI formula: `((annual_value - annual_cost) / annual_cost) × 100`
- [ ] Payback formula: `annual_cost / (annual_value / 12)` in months
- [ ] `roi_percent = None` when no drivers can be monetized
- [ ] `payback_months = None` when no drivers can be monetized
- [ ] Non-calculable case reports qualitative benefits message
- [ ] All assumptions documented in `state.roi.assumptions`
- [ ] No LLM calls — agent is fully deterministic
- [ ] Division by zero handled (annual_cost = 0 or annual_value = 0)

### Integration

- [ ] CostAgent output (`totalAnnual`) feeds directly into ROIAgent without transformation
- [ ] Both agents read/write exclusively through `AgentState` (no cross-agent imports — §3.2)
- [ ] PM can re-run either agent independently during iteration (§13)
- [ ] "Make it cheaper" iteration triggers AzureSpecialist → Cost → ROI → Presentation re-run (§13)
- [ ] Skipping CostAgent results in qualitative-only ROI (PM warns user per §14.3)
- [ ] Skipping BusinessValueAgent results in ROI with `roi_percent = None`

---

## Appendix A: Agent Class Signatures

```python
class CostAgent:
    """Estimates monthly and annual Azure costs via Retail Prices API.
    
    LLM Required: No (API calls + math)
    External API: Azure Retail Prices API (https://prices.azure.com/api/retail/prices)
    Ref: refactor.md §8
    """
    name = "Cost Estimation"
    emoji = "💰"
    
    def run(self, state: AgentState) -> AgentState:
        selections = state.services.get("selections", [])
        items = []
        assumptions = [
            "Based on 730 hours/month",
            "Pay-as-you-go pricing (no reservations or savings plans)",
        ]
        worst_source = "live"
        
        for sel in selections:
            monthly, source, note = self._resolve_price(
                sel["serviceName"], sel["sku"], sel["region"]
            )
            monthly = self._apply_instance_count(monthly, sel["sku"])
            
            items.append({
                "serviceName": sel["serviceName"],
                "sku": sel["sku"],
                "region": sel["region"],
                "monthlyCost": round(monthly, 2),
                "pricingNote": note,
            })
            
            # Track worst pricing source
            if source == "approximate":
                worst_source = "approximate"
            elif source == "live-fallback" and worst_source == "live":
                worst_source = "live-fallback"
            
            # Add consumption assumption if applicable
            assumption = CONSUMPTION_ASSUMPTIONS.get(sel["serviceName"])
            if assumption and assumption not in assumptions:
                assumptions.append(f"{sel['serviceName']}: {assumption}")
        
        total_monthly = sum(i["monthlyCost"] for i in items)
        
        state.costs = {
            "estimate": {
                "currency": "USD",
                "items": items,
                "totalMonthly": round(total_monthly, 2),
                "totalAnnual": round(total_monthly * 12, 2),
                "assumptions": assumptions,
                "pricingSource": worst_source,
            }
        }
        return state


class ROIAgent:
    """Calculates ROI from cost and business value data.
    
    LLM Required: No (deterministic math)
    External API: None
    Ref: refactor.md §10
    """
    name = "ROI Calculation"
    emoji = "📊"
    
    def run(self, state: AgentState) -> AgentState:
        annual_cost = state.costs.get("estimate", {}).get("totalAnnual", 0.0)
        drivers = state.business_value.get("drivers", [])
        
        monetizable = [d for d in drivers if d.get("monetizable")]
        non_monetizable = [d for d in drivers if not d.get("monetizable")]
        
        # Attempt to monetize each driver
        monetized = []
        for driver in monetizable:
            result = self._monetize_driver(driver, annual_cost)
            if result:
                monetized.append(result)
            else:
                # Could not convert — treat as qualitative
                non_monetizable.append(driver)
        
        annual_value = sum(m["annual_value"] for m in monetized) if monetized else None
        roi_percent = self._calculate_roi(annual_cost, annual_value)
        payback_months = self._calculate_payback(annual_cost, annual_value)
        
        assumptions = [f"IT staff hourly rate: ${DEFAULT_HOURLY_RATE}"]
        if not monetized:
            assumptions.append(
                "ROI cannot be calculated quantitatively — see qualitative benefits below."
            )
        
        state.roi = {
            "annual_cost": annual_cost,
            "annual_value": annual_value,
            "roi_percent": round(roi_percent, 1) if roi_percent is not None else None,
            "payback_months": round(payback_months, 1) if payback_months is not None else None,
            "monetized_drivers": monetized,
            "qualitative_benefits": [
                f"{d['name']}: {d.get('description', d.get('estimate', ''))}"
                for d in non_monetizable
            ],
            "assumptions": assumptions,
        }
        return state
```

---

## Appendix B: Cross-Reference to refactor.md

| FRD Section | refactor.md Section |
|-------------|-------------------|
| §2 CostAgent | §8 Cost Agent |
| §2.3 Azure Retail Prices API | §8 MUST USE |
| §2.4 Pricing Source Behavior | §8 Pricing Source Behavior (5-tier table) |
| §2.5 Consumption Assumptions | §8 Consumption-Based Services |
| §2.7 Output Schema | §8 Output Written to State |
| §2.8 Error Handling | §8 + §17 Graceful Degradation |
| §3 ROIAgent | §10 ROI Agent (New) |
| §3.3 Driver Conversion | §10 Monetizable Value Drivers (conversion table) |
| §3.4 ROI Calculation | §10 Calculation (formula) |
| §3.5 Payback Period | §10 Calculation (formula) |
| §3.6 Non-Calculable Case | §10 "If annual_value cannot be reliably calculated" |
| §3.7 Output Schema | §10 Output Written to State |
| §5 Acceptance Criteria | §19 Definition of Done |
