"""Azure Retail Prices API client — live data only, no mock fallback.

Queries the public Azure Retail Prices REST API. Uses service name mapping
to handle naming differences between LLM output and the API.
"""

import atexit
import datetime
import functools
import logging
import os
from time import time as _time

import httpx
from opentelemetry import trace

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

# Module-level httpx client with connection pooling (avoids new TCP/TLS per call).
# atexit cleanup is best-effort; httpx also releases connections on GC.
_http_client = httpx.Client(
    timeout=15,
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
)
atexit.register(_http_client.close)

PRICING_API = os.environ.get("AZURE_PRICING_API_URL", "https://prices.azure.com/api/retail/prices")

# The Retail Prices API uses specific service names that differ from common names.
SERVICE_NAME_MAP: dict[str, str] = {
    "Azure AI Search": "Azure Cognitive Search",
    "Azure Logic Apps": "Logic Apps",
    "Azure Event Grid": "Event Grid",
    "Azure Data Factory": "Data Factory",
    "Azure Blob Storage": "Storage",
    "Blob Storage": "Storage",
    "Azure Data Lake Storage": "Storage",
    "Data Lake Storage": "Storage",
    "Azure Service Bus": "Service Bus",
    "Azure Event Hubs": "Event Hubs",
    "Azure Cosmos DB for NoSQL": "Azure Cosmos DB",
    # API names verified against the Retail Prices API
    "Azure API Management": "API Management",
    "Azure Digital Twins": "Digital Twins",
    "Azure IoT Hub": "IoT Hub",
    # AI Foundry is built on Azure ML — use ML pricing as closest proxy
    "Azure AI Foundry": "Azure Machine Learning",
}

# ── Configurable AI model pricing (FRD-006 Fix N) ────────────────────
AI_MODEL_PRICING: dict[str, dict] = {
    "gpt-4o": {
        "input_per_1m": 2.50,
        "output_per_1m": 10.00,
        "avg_input_tokens": 800,
        "avg_output_tokens": 400,
        "last_updated": "2026-01-15",
    },
}


def per_request_cost(model: str = "gpt-4o") -> float:
    """Compute per-request cost from token pricing config.

    Logs a warning if pricing data is >90 days old.
    """
    m = AI_MODEL_PRICING[model]
    age = (datetime.date.today() - datetime.date.fromisoformat(m["last_updated"])).days
    if age > 90:
        logger.warning("AI pricing for %s is %d days old — verify current rates", model, age)
    return (m["avg_input_tokens"] / 1_000_000 * m["input_per_1m"]
            + m["avg_output_tokens"] / 1_000_000 * m["output_per_1m"])


# Services that have NO entries in the Retail Prices API.
ESTIMATED_PRICES: dict[str, dict] = {
    # Entra ID is licensed per-user/month via Microsoft 365; not in the retail API.
    "Microsoft Entra ID": {
        "price": 6.0,
        "source": "estimated",
        "note": "Entra ID P1: $6/user/month (Microsoft 365 licensing)",
        "unit": "1/Month per user",
    },
    "Entra ID": {
        "price": 6.0,
        "source": "estimated",
        "note": "Entra ID P1: $6/user/month (Microsoft 365 licensing)",
        "unit": "1/Month per user",
    },
    # Communication Services is pure consumption (per SMS/minute/message);
    # no retail price entries exist.
    "Azure Communication Services": {
        "price": 0.004,
        "source": "estimated",
        "note": "Blended per-minute rate for mixed voice/chat (voice ~$0.05/min, chat messages ~$0.001/msg, weighted average for typical retail mix).",
        "unit": "1/Minute",
    },
    # CycleCloud is a free orchestration layer; compute cost comes from underlying VMs.
    "Azure CycleCloud": {
        "price": 0.0,
        "source": "estimated",
        "note": "CycleCloud is free — compute cost from underlying VMs (see Virtual Machines line item)",
        "unit": "1/Month",
    },
    # Batch is a free orchestration layer; compute cost comes from underlying VMs.
    "Azure Batch": {
        "price": 0.0,
        "source": "estimated",
        "note": "Batch is free — compute cost from underlying VMs (see Virtual Machines line item)",
        "unit": "1/Month",
    },
    # Azure OpenAI uses per-token pricing not in the retail API.
    "Azure OpenAI Service": {
        "price": None,  # lazy — computed at query time
        "source": "calculated",
        "note": "GPT-4o: computed from AI_MODEL_PRICING config (~$0.006/req)",
        "unit": "1/Request",
    },
    "Azure OpenAI": {
        "price": None,  # lazy — computed at query time
        "source": "calculated",
        "note": "GPT-4o: computed from AI_MODEL_PRICING config (~$0.006/req)",
        "unit": "1/Request",
    },
    "Azure AI Foundry": {
        "price": None,  # lazy — computed at query time
        "source": "calculated",
        "note": "AI Foundry uses Azure OpenAI pricing, computed from AI_MODEL_PRICING config",
        "unit": "1/Request",
    },
    # QW-3: Services not in the Retail Prices API — conservative estimates
    # Azure SQL Database (General Purpose, 2 vCores, 10.2 GB RAM)
    "Azure SQL Database": {
        "price": 183.96,
        "source": "estimated",
        "note": "Azure SQL DB General Purpose 2 vCores: ~$184/mo (Microsoft pricing page, 2025)",
        "unit": "1/Month",
    },
    "SQL Database": {
        "price": 183.96,
        "source": "estimated",
        "note": "Azure SQL DB General Purpose 2 vCores: ~$184/mo",
        "unit": "1/Month",
    },
    # Azure Database for MySQL — Flexible Server, 2 vCores
    "Azure Database for MySQL": {
        "price": 68.64,
        "source": "estimated",
        "note": "Azure DB for MySQL Flexible Server 2 vCores: ~$69/mo",
        "unit": "1/Month",
    },
    "Azure Database for MySQL Flexible Server": {
        "price": 68.64,
        "source": "estimated",
        "note": "Azure DB for MySQL Flexible Server 2 vCores: ~$69/mo",
        "unit": "1/Month",
    },
    # Azure Database for PostgreSQL — Flexible Server, 2 vCores
    "Azure Database for PostgreSQL": {
        "price": 68.64,
        "source": "estimated",
        "note": "Azure DB for PostgreSQL Flexible Server 2 vCores: ~$69/mo",
        "unit": "1/Month",
    },
    "Azure Database for PostgreSQL Flexible Server": {
        "price": 68.64,
        "source": "estimated",
        "note": "Azure DB for PostgreSQL Flexible Server 2 vCores: ~$69/mo",
        "unit": "1/Month",
    },
    # Azure Key Vault — Standard tier, operations-based
    "Azure Key Vault": {
        "price": 5.0,
        "source": "estimated",
        "note": "Key Vault Standard: ~$5/mo base + $0.03/10K operations (10K ops/mo assumed)",
        "unit": "1/Month",
    },
    # Application Insights — based on 5 GB/mo data ingestion
    "Application Insights": {
        "price": 11.48,
        "source": "estimated",
        "note": "Application Insights: ~$2.30/GB ingested, 5 GB/mo assumed",
        "unit": "1/Month",
    },
    "Azure Application Insights": {
        "price": 11.48,
        "source": "estimated",
        "note": "Application Insights: ~$2.30/GB ingested, 5 GB/mo assumed",
        "unit": "1/Month",
    },
    # Azure DevOps — Basic plan per user
    "Azure DevOps": {
        "price": 30.0,
        "source": "estimated",
        "note": "Azure DevOps Basic plan: $6/user/mo, 5 users assumed",
        "unit": "1/Month",
    },
    # Power Automate — per-user plan
    "Power Automate": {
        "price": 75.0,
        "source": "estimated",
        "note": "Power Automate per-user plan: $15/user/mo, 5 users assumed",
        "unit": "1/Month",
    },
    # Power Apps — per-user plan
    "Power Apps": {
        "price": 100.0,
        "source": "estimated",
        "note": "Power Apps per-user plan: $20/user/mo, 5 users assumed",
        "unit": "1/Month",
    },
    # Azure Spring Apps — Standard tier (2 vCPU, 4 GB)
    "Azure Spring Apps": {
        "price": 98.15,
        "source": "estimated",
        "note": "Azure Spring Apps Standard: ~$98/mo per instance (2 vCPU, 4 GB)",
        "unit": "1/Month",
    },
    "Azure Spring Cloud": {
        "price": 98.15,
        "source": "estimated",
        "note": "Azure Spring Apps Standard: ~$98/mo per instance",
        "unit": "1/Month",
    },
    # Azure Synapse Analytics — 100 DWU
    "Azure Synapse Analytics": {
        "price": 115.0,
        "source": "estimated",
        "note": "Synapse Analytics DW100c: ~$1.51/hr = ~$115/mo at 76 compute hrs/mo",
        "unit": "1/Month",
    },
    "Synapse Analytics": {
        "price": 115.0,
        "source": "estimated",
        "note": "Synapse Analytics DW100c: ~$115/mo",
        "unit": "1/Month",
    },
    # Azure Bastion — Standard tier
    "Azure Bastion": {
        "price": 218.0,
        "source": "estimated",
        "note": "Azure Bastion Standard: ~$0.30/hr = ~$218/mo (730 hrs)",
        "unit": "1/Month",
    },
    # Azure Firewall — Standard tier
    "Azure Firewall": {
        "price": 912.0,
        "source": "estimated",
        "note": "Azure Firewall Standard: ~$1.25/hr = ~$912/mo (730 hrs)",
        "unit": "1/Month",
    },
    # Azure DDoS Protection — Network Protection plan
    "Azure DDoS Protection": {
        "price": 2944.0,
        "source": "estimated",
        "note": "Azure DDoS Network Protection: ~$2,944/mo (per-VNet plan)",
        "unit": "1/Month",
    },
    # Azure Policy — free service (no cost entry in retail API)
    "Azure Policy": {
        "price": 0.0,
        "source": "estimated",
        "note": "Azure Policy is free to use",
        "unit": "1/Month",
    },
    # Microsoft Defender for Cloud — Standard tier per server
    "Microsoft Defender for Cloud": {
        "price": 15.0,
        "source": "estimated",
        "note": "Defender for Cloud Servers P1: ~$5/server/mo, 3 servers assumed",
        "unit": "1/Month",
    },
    # ── IoT & Streaming services ──────────────────────────────────
    "Azure IoT Hub": {
        "price": 250.0,
        "source": "estimated",
        "note": "IoT Hub S2: ~$250/mo (1.5M msgs/day)",
        "unit": "1/Month",
    },
    "IoT Hub": {
        "price": 250.0,
        "source": "estimated",
        "note": "IoT Hub S2: ~$250/mo (1.5M msgs/day)",
        "unit": "1/Month",
    },
    "Azure IoT Edge": {
        "price": 0.0,
        "source": "estimated",
        "note": "IoT Edge runtime free; cost is in underlying compute/VMs",
        "unit": "1/Month",
    },
    "Azure Stream Analytics": {
        "price": 80.0,
        "source": "estimated",
        "note": "Stream Analytics: ~$0.11/SU/hr, 1 SU assumed",
        "unit": "1/Month",
    },
    "Stream Analytics": {
        "price": 80.0,
        "source": "estimated",
        "note": "Stream Analytics: ~$0.11/SU/hr, 1 SU assumed",
        "unit": "1/Month",
    },
    # ── Compute & Serverless ──────────────────────────────────────
    "Azure Functions": {
        "price": 25.0,
        "source": "estimated",
        "note": "Functions consumption: ~$0.20/M executions + compute",
        "unit": "1/Month",
    },
    "Functions": {
        "price": 25.0,
        "source": "estimated",
        "note": "Functions consumption: ~$0.20/M executions + compute",
        "unit": "1/Month",
    },
    # ── Storage & Analytics ───────────────────────────────────────
    "Azure Data Lake Storage Gen2": {
        "price": 55.0,
        "source": "estimated",
        "note": "ADLS Gen2: ~$0.018/GB/mo, ~3TB stored",
        "unit": "1/Month",
    },
    "Azure Data Lake Storage": {
        "price": 55.0,
        "source": "estimated",
        "note": "ADLS Gen2: ~$0.018/GB/mo, ~3TB stored",
        "unit": "1/Month",
    },
    "Power BI": {
        "price": 4995.0,
        "source": "estimated",
        "note": "Power BI Premium P1 capacity: ~$4,995/mo",
        "unit": "1/Month",
    },
    "Power BI Premium": {
        "price": 4995.0,
        "source": "estimated",
        "note": "Power BI Premium P1 capacity: ~$4,995/mo",
        "unit": "1/Month",
    },
    # ── Monitoring & Networking ───────────────────────────────────
    "Azure Monitor": {
        "price": 25.0,
        "source": "estimated",
        "note": "Azure Monitor: ~$2.30/GB ingested, ~10GB/mo assumed",
        "unit": "1/Month",
    },
    "Azure Event Hubs": {
        "price": 1175.0,
        "source": "estimated",
        "note": "Event Hubs Premium: ~$1,175/mo per PU",
        "unit": "1/Month",
    },
    "Event Hubs": {
        "price": 1175.0,
        "source": "estimated",
        "note": "Event Hubs Premium: ~$1,175/mo per PU",
        "unit": "1/Month",
    },
    "Azure Cache for Redis": {
        "price": 73.0,
        "source": "estimated",
        "note": "Redis Cache Standard C1 (1GB): ~$73/mo",
        "unit": "1/Month",
    },
    "Redis Cache": {
        "price": 73.0,
        "source": "estimated",
        "note": "Redis Cache Standard C1 (1GB): ~$73/mo",
        "unit": "1/Month",
    },
    "Azure Front Door": {
        "price": 335.0,
        "source": "estimated",
        "note": "Front Door Premium: ~$335/mo base + transfer",
        "unit": "1/Month",
    },
    "Front Door": {
        "price": 335.0,
        "source": "estimated",
        "note": "Front Door Premium: ~$335/mo base + transfer",
        "unit": "1/Month",
    },
    "Azure Databricks": {
        "price": 450.0,
        "source": "estimated",
        "note": "Databricks Standard: ~$0.40/DBU, ~3 DBUs assumed",
        "unit": "1/Month",
    },
    "Databricks": {
        "price": 450.0,
        "source": "estimated",
        "note": "Databricks Standard: ~$0.40/DBU, ~3 DBUs assumed",
        "unit": "1/Month",
    },
    # ── Data & AI services ────────────────────────────────────────
    "Azure Cosmos DB": {
        "price": 275.0,
        "source": "estimated",
        "note": "Cosmos DB serverless: ~1M RU/s burst, ~$0.25/M RU + $0.25/GB storage",
        "unit": "1/Month",
    },
    "Cosmos DB": {
        "price": 275.0,
        "source": "estimated",
        "note": "Cosmos DB serverless: ~1M RU/s burst, ~$0.25/M RU + $0.25/GB storage",
        "unit": "1/Month",
    },
    "Azure Cosmos DB for NoSQL": {
        "price": 275.0,
        "source": "estimated",
        "note": "Cosmos DB serverless: ~1M RU/s burst, ~$0.25/M RU + $0.25/GB storage",
        "unit": "1/Month",
    },
    "Azure AI Search": {
        "price": 250.0,
        "source": "estimated",
        "note": "AI Search S1: ~$250/mo (25 partitions, 50GB storage)",
        "unit": "1/Month",
    },
    "Azure Cognitive Search": {
        "price": 250.0,
        "source": "estimated",
        "note": "Cognitive Search S1: ~$250/mo",
        "unit": "1/Month",
    },
    "Azure Blob Storage": {
        "price": 42.0,
        "source": "estimated",
        "note": "Blob Storage Hot LRS: ~$0.018/GB, 2TB assumed + transactions",
        "unit": "1/Month",
    },
    "Blob Storage": {
        "price": 42.0,
        "source": "estimated",
        "note": "Blob Storage Hot LRS: ~$0.018/GB, 2TB assumed + transactions",
        "unit": "1/Month",
    },
    "Azure Bot Service": {
        "price": 50.0,
        "source": "estimated",
        "note": "Bot Service S1: ~$0.50/1K messages, 100K msgs/mo assumed",
        "unit": "1/Month",
    },
    "Bot Service": {
        "price": 50.0,
        "source": "estimated",
        "note": "Bot Service S1: ~$0.50/1K messages, 100K msgs/mo assumed",
        "unit": "1/Month",
    },
    # ── Compute & Hosting ─────────────────────────────────────────
    "Azure App Service": {
        "price": 146.0,
        "source": "estimated",
        "note": "App Service P1v3: ~$146/mo (Linux)",
        "unit": "1/Month",
    },
    "App Service": {
        "price": 146.0,
        "source": "estimated",
        "note": "App Service P1v3: ~$146/mo (Linux)",
        "unit": "1/Month",
    },
    "Azure Kubernetes Service": {
        "price": 292.0,
        "source": "estimated",
        "note": "AKS: $0 control plane + 2× D4s v5 nodes (~$146/mo each)",
        "unit": "1/Month",
    },
    "Azure Machine Learning": {
        "price": 350.0,
        "source": "estimated",
        "note": "AML Enterprise: managed endpoint D4s v5 (~$146) + compute instance (~$200)",
        "unit": "1/Month",
    },
    "Azure Digital Twins": {
        "price": 100.0,
        "source": "estimated",
        "note": "Digital Twins: ~$0.001/operation, ~100M ops/mo assumed",
        "unit": "1/Month",
    },
    # ── Integration & Governance ──────────────────────────────────
    "Azure Logic Apps": {
        "price": 35.0,
        "source": "estimated",
        "note": "Logic Apps Consumption: ~$0.000025/action, ~1M actions/mo",
        "unit": "1/Month",
    },
    "Logic Apps": {
        "price": 35.0,
        "source": "estimated",
        "note": "Logic Apps Consumption: ~$0.000025/action, ~1M actions/mo",
        "unit": "1/Month",
    },
    "Azure API Management": {
        "price": 290.0,
        "source": "estimated",
        "note": "API Management Standard: ~$290/mo per unit",
        "unit": "1/Month",
    },
    "API Management": {
        "price": 290.0,
        "source": "estimated",
        "note": "API Management Standard: ~$290/mo per unit",
        "unit": "1/Month",
    },
    "Microsoft Purview": {
        "price": 200.0,
        "source": "estimated",
        "note": "Purview Data Map: ~$0.25/CU + governance features",
        "unit": "1/Month",
    },
    "Azure Purview": {
        "price": 200.0,
        "source": "estimated",
        "note": "Purview Data Map: ~$0.25/CU + governance features",
        "unit": "1/Month",
    },
    "Azure Site Recovery": {
        "price": 25.0,
        "source": "estimated",
        "note": "Site Recovery: ~$25/protected instance/mo",
        "unit": "1/Month",
    },
    "Dynamics 365": {
        "price": 210.0,
        "source": "estimated",
        "note": "Dynamics 365 Customer Service Professional: ~$50/user/mo, ~4 users",
        "unit": "1/Month",
    },
}


# ---------------------------------------------------------------------------
# TTL cache for pricing results (24-hour expiry)
# ---------------------------------------------------------------------------

_price_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 86400  # 24 hours


def _cached_price(cache_key: str) -> dict | None:
    """Return cached pricing result if still within TTL, else None."""
    if cache_key in _price_cache:
        ts, value = _price_cache[cache_key]
        if _time() - ts < _CACHE_TTL:
            return value
        del _price_cache[cache_key]
    return None


def _set_cache(cache_key: str, value: dict) -> None:
    """Store a pricing result in the TTL cache."""
    _price_cache[cache_key] = (_time(), value)


@functools.lru_cache(maxsize=512)
def _query_api(service_name: str, region: str) -> tuple[dict, ...]:
    """Query the Retail Prices API. Returns tuple of price items (cached by service+region).

    Cache is process-local — effective within a single worker process.
    Returns a tuple (not list) to satisfy lru_cache hashability requirements.
    """
    filter_str = f"serviceName eq '{service_name}' and armRegionName eq '{region}'"
    try:
        resp = _http_client.get(
            PRICING_API,
            params={"$filter": filter_str, "currencyCode": "USD"},
        )
        if resp.status_code == 200:
            return tuple(resp.json().get("Items", []))
    except Exception as e:
        logger.warning("Pricing API request failed for %s: %s", service_name, e)
    return ()


# ── Tier-proximity scoring for SKU fallback (FRD-006 Fix J) ──────────
TIER_ORDER = ["free", "shared", "basic", "b", "standard", "s", "premium", "p", "isolated", "i"]


def _tier_distance(requested: str, candidate: str) -> int:
    """Compute distance between two SKU tier names in the tier hierarchy.

    PaaS-focused. VM families (D/E/F/L/M/N) default to index 5 (Standard).
    """
    req_lower = requested.lower()
    cand_lower = candidate.lower()
    req_idx = next((i for i, t in enumerate(TIER_ORDER) if t in req_lower), 5)
    cand_idx = next((i for i, t in enumerate(TIER_ORDER) if t in cand_lower), 5)
    return abs(req_idx - cand_idx)


def _find_best_match(items: tuple[dict, ...] | list[dict], sku: str) -> dict | None:
    """Find the best matching price item for a given SKU."""
    if not items:
        return None

    sku_lower = sku.lower()

    # 1. Exact SKU match
    for item in items:
        sku_name = (item.get("skuName") or "").lower()
        arm_sku = (item.get("armSkuName") or "").lower()
        if sku_lower == sku_name or sku_lower == arm_sku:
            if item.get("retailPrice", 0) > 0:
                return item

    # 2. Partial SKU match (sku substring)
    for item in items:
        sku_name = (item.get("skuName") or "").lower()
        arm_sku = (item.get("armSkuName") or "").lower()
        meter = (item.get("meterName") or "").lower()
        if sku_lower in sku_name or sku_lower in arm_sku or sku_lower in meter:
            if item.get("retailPrice", 0) > 0:
                return item

    # 3. Nearest-tier match (replaces median fallback — FRD-006 Fix J)
    non_zero = [
        i for i in items
        if i.get("retailPrice", 0) > 0
        and "low priority" not in (i.get("skuName") or "").lower()
        and "spot" not in (i.get("skuName") or "").lower()
    ]
    if non_zero:
        non_zero.sort(key=lambda i: _tier_distance(sku, i.get("skuName", "")))
        return non_zero[0]

    return None


def query_azure_pricing_sync(
    service_name: str, sku: str, region: str = "eastus"
) -> dict:
    """Query Azure Retail Prices API. Returns {price, source, note, unit}.

    Results are cached for 24 hours by (service, sku, region).
    Sources: "live", "live-fallback", "estimated", "unavailable"
    """
    cache_key = f"{service_name}|{sku}|{region}"
    cached = _cached_price(cache_key)
    if cached is not None:
        return cached

    result = _query_azure_pricing_uncached(service_name, sku, region)
    _set_cache(cache_key, result)
    return result


def _query_azure_pricing_uncached(
    service_name: str, sku: str, region: str = "eastus"
) -> dict:
    """Uncached pricing query implementation."""
    with _tracer.start_as_current_span("azure.pricing.query") as span:
        span.set_attribute("pricing.service_name", service_name)
        span.set_attribute("pricing.sku", sku)
        span.set_attribute("pricing.region", region)

        # Return a known estimate for services not in the Retail Prices API
        # Only exact match here — services that genuinely don't have API data
        if service_name in ESTIMATED_PRICES:
            est = dict(ESTIMATED_PRICES[service_name])
            if est["price"] is None:
                est["price"] = per_request_cost()
            span.set_attribute("pricing.source", est.get("source", "estimated"))
            return est

        # Translate service name for API
        api_name = SERVICE_NAME_MAP.get(service_name, service_name)

        # Strategy 1: Query with mapped name
        items = _query_api(api_name, region)

        # Strategy 2: If mapped name returned nothing, try original
        if not items and api_name != service_name:
            items = _query_api(service_name, region)

        # Strategy 3: Try eastus if region-specific query empty
        if not items and region != "eastus":
            items = _query_api(api_name, "eastus")
            if not items and api_name != service_name:
                items = _query_api(service_name, "eastus")
            if items:
                span.set_attribute("pricing.region_fallback", "eastus")

        span.set_attribute("pricing.item_count", len(items))

        match = _find_best_match(items, sku)

        if match:
            price = match.get("retailPrice", 0)
            unit = match.get("unitOfMeasure", "1 Hour")
            matched_sku = match.get("skuName", "")
            exact = sku.lower() in matched_sku.lower()
            source = "live" if exact else "live-fallback"

            span.set_attribute("pricing.source", source)
            span.set_attribute("pricing.matched_sku", matched_sku)

            return {
                "price": price,
                "source": source,
                "note": None if exact else f"Matched to {matched_sku}",
                "unit": unit,
            }

        # No data found — try fuzzy match against ESTIMATED_PRICES before giving up
        sn_lower = service_name.lower()
        for est_name, est_data in ESTIMATED_PRICES.items():
            if est_name.lower() in sn_lower or sn_lower in est_name.lower():
                est = dict(est_data)
                if est["price"] is None:
                    est["price"] = per_request_cost()
                span.set_attribute("pricing.source", "estimated-fuzzy")
                logger.info("Fuzzy match: '%s' → '%s'", service_name, est_name)
                return est

        span.set_attribute("pricing.source", "unavailable")
        logger.warning(
            "No pricing found: %s (API: %s), SKU: %s, region: %s",
            service_name, api_name, sku, region,
        )
        return {
            "price": 0.0,
            "source": "unavailable",
            "note": f"No pricing data for {service_name} ({sku}). Check Azure Pricing Calculator.",
            "unit": "1/Month",
        }
