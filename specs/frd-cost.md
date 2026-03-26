# FRD-COST: Cost Estimation

**Feature ID:** US-5
**Status:** Draft
**Priority:** P0
**PRD Reference:** `specs/prd.md` — US-5, FR-2, FR-4, NFR-2, R-2
**Last Updated:** 2025-07-17

---

## 1. Overview

The Cost Specialist Agent produces a detailed cost estimate for the Azure architecture proposed by the upstream agents (System Architect → Azure Specialist). It queries the **Azure Retail Prices REST API** to retrieve current, public pricing for each selected Azure service, then aggregates those prices into monthly and annual projections.

Sellers interact with the estimate through adjustable parameters — number of users, data volume, region, and usage hours — and can trigger an instant recalculation to compare scenarios. When the pricing API is unavailable, the agent falls back to cached data (24-hour TTL) and clearly marks results as **"approximate"**.

The MVP scope explicitly excludes Enterprise Agreement (EA) and CSP discount pricing. This limitation is stated on every output to set correct expectations with customers.

---

## 2. Azure Retail Prices API Integration

### 2.1 API Endpoint & Authentication

| Property | Value |
|----------|-------|
| Base URL | `https://prices.azure.com/api/retail/prices` |
| Authentication | **None** — the Retail Prices API is a public, unauthenticated endpoint |
| Protocol | HTTPS GET with OData query parameters |
| Rate Limits | Undocumented; implement defensive retry (§ 6.2) |
| Response Format | JSON (`{ Items: [], NextPageLink?: string }`) |
| Pagination | Follow `NextPageLink` until `null`; each page returns up to 100 items |

**Reference:** [Azure Retail Prices REST API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)

### 2.2 Query Construction

Given an array of `ServiceSelection[]` from the Azure Specialist Agent, the Cost Agent builds an OData `$filter` for each service:

**Filter pattern:**

```
$filter=serviceName eq '{serviceName}' and armSkuName eq '{sku}' and armRegionName eq '{region}' and priceType eq 'Consumption'
```

**Mapping rules:**

| ServiceSelection field | API filter field | Notes |
|------------------------|------------------|-------|
| `serviceName` | `serviceName` | Exact match (e.g., `"Azure App Service"`) |
| `sku` | `armSkuName` | Exact match (e.g., `"B1"`) |
| `region` | `armRegionName` | Lowercase hyphenated (e.g., `"eastus"`, `"westeurope"`) |
| — | `priceType` | Always `"Consumption"` for pay-as-you-go |
| — | `currencyCode` | Always `"USD"` |

**Compound queries:** When multiple services are selected, issue one API call per service to keep filters simple and cacheable. Do **not** combine unrelated services into a single `$filter` with `or` — this complicates cache key construction.

**Query string construction (pseudo-code):**

```typescript
function buildApiUrl(service: ServiceSelection): string {
  const filter = [
    `serviceName eq '${service.serviceName}'`,
    `armSkuName eq '${service.sku}'`,
    `armRegionName eq '${service.region}'`,
    `priceType eq 'Consumption'`,
    `currencyCode eq 'USD'`
  ].join(' and ');
  return `https://prices.azure.com/api/retail/prices?$filter=${encodeURIComponent(filter)}`;
}
```

### 2.3 Response Parsing

The API returns an `Items[]` array. Each item is mapped to a `CostEstimate.items` entry:

| API response field | Maps to | Notes |
|--------------------|---------|-------|
| `serviceName` | `items[].serviceName` | Pass through |
| `armSkuName` | `items[].sku` | Pass through |
| `armRegionName` | `items[].region` | Pass through |
| `retailPrice` | *(input to calculation)* | Per-unit price in USD |
| `unitOfMeasure` | *(input to calculation)* | e.g., `"1 Hour"`, `"1 GB/Month"`, `"10,000 Transactions"` |
| `meterName` | *(for disambiguation)* | Used when multiple meters exist for same SKU |
| `productName` | *(display/logging)* | Human-readable product name |

**Disambiguation:** When the API returns multiple price items for the same `serviceName + sku + region` (e.g., compute vs. storage meters for a single VM SKU), select items using the following priority:

1. Prefer items where `type eq 'Consumption'` over `'Reservation'`
2. Prefer the **primary compute meter** (e.g., `meterName` containing `"Compute Hours"` or `"vCPU"`) over secondary meters
3. Include storage/bandwidth meters as separate line items if their `unitOfMeasure` differs

### 2.4 Example API Request/Response

**Request — Azure App Service B1 in East US:**

```
GET https://prices.azure.com/api/retail/prices?$filter=serviceName eq 'Azure App Service' and armSkuName eq 'B1' and armRegionName eq 'eastus' and priceType eq 'Consumption' and currencyCode eq 'USD'
```

**Response (simplified):**

```json
{
  "Items": [
    {
      "currencyCode": "USD",
      "tierMinimumUnits": 0.0,
      "retailPrice": 0.075,
      "unitPrice": 0.075,
      "armRegionName": "eastus",
      "location": "US East",
      "effectiveStartDate": "2024-01-01T00:00:00Z",
      "meterId": "abc-123",
      "meterName": "B1",
      "productId": "DZH318Z0C0WF",
      "skuId": "DZH318Z0C0WF/003J",
      "productName": "Azure App Service Basic Plan - Linux",
      "skuName": "B1",
      "serviceName": "Azure App Service",
      "serviceId": "DZH313Z7MMC8",
      "serviceFamily": "Compute",
      "unitOfMeasure": "1 Hour",
      "type": "Consumption",
      "isPrimaryMeterRegion": true,
      "armSkuName": "B1"
    }
  ],
  "NextPageLink": null,
  "Count": 1
}
```

**Resulting CostEstimate item:**

```json
{
  "serviceName": "Azure App Service",
  "sku": "B1",
  "region": "eastus",
  "monthlyCost": 54.75
}
```

*Calculation: $0.075/hour × 730 hours/month = $54.75/month*

---

## 3. Agent Input/Output Contract

### 3.1 Input (from PM Agent)

The Cost Specialist Agent receives a `ProjectContext` object from the orchestrator pipeline. The relevant input fields are:

```typescript
interface CostAgentInput {
  /** Services selected by the Azure Specialist Agent */
  services: ServiceSelection[];

  /** Free-text requirements that may contain scale hints */
  requirements: Record<string, string>;

  /** Optional: seller-provided overrides */
  scaleParameters?: ScaleParameters;
}

interface ServiceSelection {
  serviceName: string;   // e.g., "Azure App Service"
  sku: string;           // e.g., "B1"
  region: string;        // e.g., "eastus"
  justification: string; // Why this service was chosen
}

interface ScaleParameters {
  concurrentUsers?: number;     // Default: 1000
  dataVolumeGB?: number;        // Default: 100
  region?: string;              // Default: from ServiceSelection
  hoursPerMonth?: number;       // Default: 730 (24×365÷12)
  dataTransferOutGB?: number;   // Default: 50
}
```

**Requirements parsing:** The agent scans `requirements` for scale-related keywords (e.g., "10,000 users", "500 GB storage", "Europe region") and populates `ScaleParameters` defaults from these values when `scaleParameters` is not explicitly provided.

### 3.2 Output — CostEstimate

```typescript
interface CostEstimate {
  /** Always 'USD' in MVP */
  currency: 'USD';

  /** Per-service cost breakdown */
  items: CostLineItem[];

  /** Sum of all items[].monthlyCost */
  totalMonthly: number;

  /** totalMonthly × 12 */
  totalAnnual: number;

  /** Human-readable assumptions used in calculation */
  assumptions: string[];

  /** ISO 8601 timestamp when estimate was generated */
  generatedAt: Date;

  /** Indicates data freshness */
  pricingSource: 'live' | 'cached' | 'approximate';
}

interface CostLineItem {
  serviceName: string;
  sku: string;
  region: string;

  /** Calculated monthly cost in USD */
  monthlyCost: number;
}
```

**Example output:**

```json
{
  "currency": "USD",
  "items": [
    { "serviceName": "Azure App Service", "sku": "B1", "region": "eastus", "monthlyCost": 54.75 },
    { "serviceName": "Azure SQL Database", "sku": "S1", "region": "eastus", "monthlyCost": 30.00 },
    { "serviceName": "Azure Blob Storage", "sku": "Hot LRS", "region": "eastus", "monthlyCost": 2.08 },
    { "serviceName": "Azure Application Insights", "sku": "Enterprise", "region": "eastus", "monthlyCost": 0.00 }
  ],
  "totalMonthly": 86.83,
  "totalAnnual": 1041.96,
  "assumptions": [
    "1,000 concurrent users",
    "730 hours/month (24/7 operation)",
    "100 GB stored data",
    "50 GB/month egress data transfer",
    "East US region",
    "Pay-as-you-go pricing (no EA/CSP discounts)",
    "First 5 GB Application Insights data included free"
  ],
  "generatedAt": "2025-07-17T14:30:00.000Z",
  "pricingSource": "live"
}
```

---

## 4. Cost Calculation Logic

### 4.1 Unit Mapping

Each Azure service uses a different billing model. The agent maps architecture components to billable units:

| Service Category | Billing Unit | `unitOfMeasure` | Calculation |
|------------------|-------------|-----------------|-------------|
| App Service | Instance-hours | `1 Hour` | `retailPrice × hoursPerMonth` |
| Azure SQL Database | DTU-hours | `1 Hour` | `retailPrice × hoursPerMonth` |
| Virtual Machines | vCPU-hours | `1 Hour` | `retailPrice × hoursPerMonth × instanceCount` |
| Azure Blob Storage | GB stored | `1 GB/Month` | `retailPrice × dataVolumeGB` |
| Azure Cosmos DB | RU/s + storage | `100 RU/s`, `1 GB/Month` | `(retailPrice × RUs / 100) + (storagePrice × GB)` |
| Azure Functions | Executions + GB-s | `10,000 Executions` | `(retailPrice × executions / 10000) + (memGBs × gbsPrice)` |
| Data Transfer | GB out | `1 GB` | `retailPrice × dataTransferOutGB` (first 5 GB/month free) |
| Application Insights | GB ingested | `1 GB` | `retailPrice × max(0, ingestGB - 5)` (5 GB/month free) |
| Azure Key Vault | Operations | `10,000 Operations` | `retailPrice × estimatedOps / 10000` |

**Free tier handling:** Services with free tiers (e.g., Application Insights 5 GB, Data Transfer 5 GB, Functions 1M executions/month) subtract the free allowance before multiplying. If usage is within the free tier, `monthlyCost = 0.00` and an assumption note is added.

### 4.2 Scale Parameters

Sellers can adjust the following parameters. Each triggers a full recalculation:

| Parameter | Default | Range | Affects |
|-----------|---------|-------|---------|
| `concurrentUsers` | 1,000 | 1 – 1,000,000 | Instance count for compute services |
| `dataVolumeGB` | 100 | 0 – 100,000 | Storage services, database sizing |
| `region` | Per `ServiceSelection` | Any valid Azure region | All service prices |
| `hoursPerMonth` | 730 | 1 – 730 | Hourly-billed services |
| `dataTransferOutGB` | 50 | 0 – 100,000 | Egress/bandwidth costs |

**Instance count derivation from users:** When `concurrentUsers` changes, compute instance count is derived:

```
instanceCount = ceil(concurrentUsers / usersPerInstance)
```

Where `usersPerInstance` depends on the SKU tier (e.g., B1 ≈ 100, S1 ≈ 500, P1v3 ≈ 2,000). These defaults are documented in the assumptions.

### 4.3 Monthly Calculation

```
For each ServiceSelection:
  1. Fetch retailPrice from API (or cache)
  2. Determine quantity from scale parameters + unit mapping (§ 4.1)
  3. monthlyCost = retailPrice × quantity
  4. Subtract free tier allowance if applicable
  5. Round to 2 decimal places (USD cents)

totalMonthly = sum(items[].monthlyCost)
```

**Rounding:** All `monthlyCost` values are rounded to 2 decimal places using banker's rounding (round half to even). `totalMonthly` is the sum of already-rounded line items, not independently rounded.

### 4.4 Annual Projection

```
totalAnnual = totalMonthly × 12
```

Annual projection is a simple 12× multiplier of the monthly total. No annual discount rates or reserved instance pricing is applied in MVP.

**Future consideration:** Reserved Instance (1-year, 3-year) pricing can be added post-MVP by querying `priceType eq 'Reservation'` and offering a comparison table.

### 4.5 Assumption Generation

Every estimate must include an explicit `assumptions[]` array. Assumptions are generated from:

1. **Scale parameters used** — e.g., `"1,000 concurrent users"`, `"730 hours/month (24/7 operation)"`
2. **Derived quantities** — e.g., `"2 App Service instances (500 users per B1 instance)"`
3. **Free tier usage** — e.g., `"First 5 GB Application Insights data included free"`
4. **Pricing model** — always include: `"Pay-as-you-go pricing (no EA/CSP discounts)"`
5. **Region** — e.g., `"East US region"`
6. **Currency** — always include: `"All prices in USD"`
7. **Data freshness** — if cached: `"Pricing data retrieved from cache (last updated: {timestamp})"`

---

## 5. Parameter Adjustment Flow

### 5.1 Adjustable Parameters

The following parameters are surfaced in the UI for seller adjustment:

| Parameter | UI Control | Validation |
|-----------|-----------|------------|
| Concurrent Users | Numeric input with stepper | Integer, 1 – 1,000,000 |
| Data Volume (GB) | Numeric input with stepper | Number ≥ 0, max 100,000 |
| Region | Dropdown (populated from Azure regions) | Must be a valid `armRegionName` |
| Hours/Month | Slider or numeric input | 1 – 730 |
| Data Transfer Out (GB) | Numeric input | Number ≥ 0, max 100,000 |

### 5.2 Recalculation Trigger

When the seller changes any parameter:

1. **Validate** the new value against range constraints
2. **Debounce** input changes by 500 ms to avoid excessive API calls
3. **Call the Cost Agent** with updated `ScaleParameters`
4. If region changed → new API queries are required (different prices per region)
5. If only quantity parameters changed → reuse cached `retailPrice` values, recalculate totals
6. **Display loading indicator** during recalculation
7. Return new `CostEstimate` with updated `generatedAt` timestamp

### 5.3 Diff Display (Before / After)

When a recalculation completes, the UI shows a comparison:

| Service | SKU | Previous Monthly | New Monthly | Δ |
|---------|-----|-----------------|-------------|---|
| Azure App Service | B1 | $54.75 | $109.50 | +$54.75 (+100%) |
| Azure SQL Database | S1 | $30.00 | $30.00 | — |
| **Total** | | **$84.75** | **$139.50** | **+$54.75 (+64.6%)** |

**Diff rules:**
- Show absolute and percentage change
- Highlight increases in red/warning, decreases in green/success
- Services with no change show `"—"`
- If region changed, note that all prices may differ: `"Region changed from eastus to westeurope — all prices updated"`

---

## 6. Fallback & Caching

### 6.1 Cache Strategy (24-Hour TTL)

| Property | Value |
|----------|-------|
| Cache key | `retail-price:{serviceName}:{sku}:{region}` |
| TTL | 24 hours |
| Storage | In-memory Map (MVP); Redis for production scale |
| Invalidation | TTL-based only; no manual purge in MVP |
| Scope | Per-service, per-SKU, per-region |

**Cache behavior:**

```
On API request:
  1. Check cache for key
  2. If hit AND age < 24h → use cached price, set pricingSource = 'cached'
  3. If hit AND age ≥ 24h → discard, fetch from API
  4. If miss → fetch from API
  5. On successful API response → store in cache with current timestamp
```

### 6.2 Retry Logic (Exponential Backoff, Max 3 Attempts)

Per **Risk R-2** and **NFR-2**:

```
attempt = 1
maxAttempts = 3
baseDelay = 1000 ms

while attempt ≤ maxAttempts:
  response = callAPI(url, timeout = 10_000 ms)

  if response.ok:
    return response.data

  if response.status == 429 (Rate Limited):
    delay = baseDelay × 2^(attempt - 1)   // 1s, 2s, 4s
    wait(delay)
    attempt++
    continue

  if response.status >= 500 OR timeout:
    delay = baseDelay × 2^(attempt - 1)
    wait(delay)
    attempt++
    continue

  if response.status == 400 OR 404:
    // Client error — do not retry
    break

fallback:
  if cache has ANY data for this key (even expired):
    return cached data, set pricingSource = 'approximate'
  else:
    return error with suggestion to retry later
```

**NFR-2 compliance:** Each individual API call has a 10-second timeout. On timeout, retry once (per NFR-2 language), then fall back. The full retry sequence (up to 3 attempts per R-2) applies to server errors and rate limits.

### 6.3 Pricing Source Indicator

| Value | Meaning | UI Treatment |
|-------|---------|-------------- |
| `live` | Prices fetched from API in this request | Green badge: ✅ **Live pricing** |
| `cached` | Prices from cache, within 24h TTL | Yellow badge: 🕐 **Cached pricing** (age displayed) |
| `approximate` | Cache expired or API failed; best-effort | Orange badge: ⚠️ **Approximate pricing** — "Prices may not reflect current rates" |

**Granularity:** `pricingSource` is set at the estimate level (not per line item). If **any** line item used approximate data, the entire estimate is marked `approximate`.

---

## 7. Frontend Behavior

### 7.1 Cost Breakdown Table

The cost estimate is rendered as a responsive table:

| Column | Source | Format |
|--------|--------|--------|
| Service | `items[].serviceName` | Text |
| SKU | `items[].sku` | Text |
| Region | `items[].region` | Text, human-friendly label |
| Monthly Cost | `items[].monthlyCost` | `$X,XXX.XX` (USD, 2 decimals, comma separators) |

**Footer row:** Total Monthly (`$X,XXX.XX`) and Total Annual (`$XX,XXX.XX`).

**Sorting:** Default sort by `monthlyCost` descending (most expensive service first). Seller can re-sort by any column.

**Empty state:** If no services are selected, display: *"No services selected. The architecture step must complete before cost estimation."*

### 7.2 Parameter Adjustment Controls

Rendered as a collapsible panel above the cost table:

- **Section title:** "Adjust Estimate Parameters"
- **Layout:** Horizontal form on desktop; stacked on mobile
- **Defaults:** Pre-filled from requirements parsing or system defaults (§ 4.2)
- **"Recalculate" button:** Primary action; disabled during loading
- **"Reset to defaults" link:** Restores original parameters

### 7.3 Pricing Source Badge

Displayed prominently at the top-right of the cost table:

- Badge text and color per § 6.3
- For `cached`: include tooltip: *"Prices cached at {generatedAt}. Click Recalculate to fetch live prices."*
- For `approximate`: include inline warning text below the badge

### 7.4 Disclaimer Display

A disclaimer is **always** displayed below the cost table:

> **Disclaimer:** This estimate uses Azure Retail (pay-as-you-go) pricing and does not include Enterprise Agreement (EA), CSP, or negotiated discounts. Actual costs may vary. All prices in USD. Generated on {generatedAt}.

This fulfills the PRD acceptance criterion: *"The estimate does not include EA or CSP discounts in MVP; this limitation is stated on the output."*

---

## 8. Error Responses

| Scenario | HTTP Status | User-Facing Message | Agent Behavior |
|----------|-------------|---------------------|----------------|
| API returns 0 items for a service | 200 (empty) | "Pricing not available for {serviceName} ({sku}) in {region}" | Set `monthlyCost: 0`, add assumption: "Pricing unavailable for {service}" |
| API timeout (all retries exhausted) | — | "Unable to retrieve live pricing. Showing approximate estimates." | Fall back to cache (§ 6.2); `pricingSource = 'approximate'` |
| API rate limited (429) | 429 | *(transparent to user; retry handles it)* | Exponential backoff retry |
| API server error (5xx) | 5xx | "Azure pricing service temporarily unavailable." | Retry then cache fallback |
| Invalid region name | 400 | "Region '{region}' is not recognized. Please select a valid Azure region." | Do not retry; surface error |
| No `ServiceSelection[]` provided | — | "Architecture step must complete before cost estimation." | Block cost agent execution |
| Cache empty AND API failed | — | "Unable to estimate costs at this time. Please try again later." | Return error; no estimate generated |

---

## 9. Edge Cases

### 9.1 API Returns 0 Results

**Cause:** The `serviceName`, `sku`, or `region` combination does not exist in the retail price catalog (e.g., a preview SKU or retired tier).

**Handling:** Include the service in the output with `monthlyCost: 0.00` and add to `assumptions[]`: *"Pricing unavailable for {serviceName} ({sku}) in {region} — excluded from total."* Do **not** silently omit the service.

### 9.2 Unknown SKU

**Cause:** The Azure Specialist Agent selects a SKU not recognized by the Retail Prices API.

**Handling:** Log a warning. Attempt a broader query (`armSkuName` filter removed) and present available SKUs in the region. If a close match exists (e.g., `"B1"` vs `"B1 v2"`), use it with an assumption note. Otherwise, treat as § 9.1.

### 9.3 Region Not Available

**Cause:** Seller selects a region where the service is not offered.

**Handling:** Display: *"{serviceName} is not available in {region}. Nearest available region: {nearestRegion}."* Suggest the nearest region but do **not** auto-switch without seller confirmation.

### 9.4 Very Large Estimates

**Cause:** Scale parameters produce estimates exceeding $100,000/month.

**Handling:** Display a visual callout/warning: *"This estimate exceeds $100,000/month. Consider reserved instances or EA pricing for cost optimization."* Ensure number formatting handles 6+ digit totals with comma separators.

### 9.5 Currency Display

All prices are displayed in USD with:
- Dollar sign prefix: `$`
- Two decimal places: `$54.75`
- Comma thousands separator: `$1,234.56`
- Currency explicitly stated in table header and disclaimer

### 9.6 Free Tier Services

Services within their free tier display `$0.00` in the cost column with an assumption note (e.g., *"Azure Functions: within 1M executions/month free tier"*). They are **included** in the table to show completeness but contribute `$0.00` to the total.

### 9.7 Multiple Meters per Service

Some services (e.g., Cosmos DB = RU/s + storage, VMs = compute + disk + network) return multiple price items. Each distinct meter is listed as a **separate line item** with a descriptive `serviceName` suffix (e.g., `"Azure Cosmos DB (RU/s)"`, `"Azure Cosmos DB (Storage)"`).

### 9.8 Pagination of API Results

If `NextPageLink` is non-null, the agent **must** follow it to retrieve all price items. Set a hard cap of 10 pages (1,000 items) per query to prevent runaway pagination. If the cap is hit, log a warning and use the items collected so far.

---

## Traceability

| FRD Section | PRD Reference | Requirement |
|-------------|---------------|-------------|
| § 2 (API Integration) | US-5 AC-1 | "Cost Specialist Agent calls Azure Retail Prices REST API" |
| § 3.2 (Output Schema) | FR-4 (Data Model) | `CostEstimate` interface definition |
| § 4 (Calculation Logic) | US-5 AC-2 | "Estimate broken down by service, SKU, and region" |
| § 4.5 (Assumptions) | US-5 AC-6 | "Assumptions listed explicitly" |
| § 5 (Parameter Adjustment) | US-5 AC-3 | "Seller can adjust parameters and recalculate" |
| § 7.1 (Cost Table) | US-5 AC-4 | "Monthly and annual cost projections in table format" |
| § 7.1, 9.5 (Currency) | US-5 AC-5 | "All prices displayed in USD; currency stated explicitly" |
| § 6 (Fallback & Caching) | US-5 AC-7 | "API unavailable → warning + retry or cached/indicative pricing" |
| § 7.4 (Disclaimer) | US-5 AC-8 | "No EA/CSP discounts in MVP; limitation stated on output" |
| § 6.2 (Retry Logic) | NFR-2 | "API calls within 10s, retry once then cached fallback" |
| § 6.1 (Cache Strategy) | R-2 | "Cache with 24h TTL, approximate badge, exponential backoff" |
| § 6.3 (Pricing Source) | R-2 | "Display approximate badge on cached results" |
| § 3.1 (Input) | FR-2 | Cost Specialist agent role in pipeline |
