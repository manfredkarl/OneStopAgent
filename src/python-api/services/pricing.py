"""Azure Retail Prices API client — live data only, no mock fallback.

Queries the public Azure Retail Prices REST API. Uses service name mapping
to handle naming differences between LLM output and the API.
"""

import datetime
import logging

import httpx
from opentelemetry import trace

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

PRICING_API = "https://prices.azure.com/api/retail/prices"

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
        "price": 500.0,
        "source": "estimated",
        "note": "Estimated ~$500/month for moderate usage (SMS, voice, chat). Actual cost varies with volume.",
        "unit": "1/Month",
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
        "price": per_request_cost(),
        "source": "calculated",
        "note": "GPT-4o: computed from AI_MODEL_PRICING config (~$0.006/req)",
        "unit": "1/Request",
    },
    "Azure OpenAI": {
        "price": per_request_cost(),
        "source": "calculated",
        "note": "GPT-4o: computed from AI_MODEL_PRICING config (~$0.006/req)",
        "unit": "1/Request",
    },
    "Azure AI Foundry": {
        "price": per_request_cost(),
        "source": "calculated",
        "note": "AI Foundry uses Azure OpenAI pricing, computed from AI_MODEL_PRICING config",
        "unit": "1/Request",
    },
}


def _query_api(service_name: str, region: str) -> list[dict]:
    """Query the Retail Prices API. Returns list of price items."""
    filter_str = f"serviceName eq '{service_name}' and armRegionName eq '{region}'"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                PRICING_API,
                params={"$filter": filter_str, "currencyCode": "USD"},
            )
            if resp.status_code == 200:
                return resp.json().get("Items", [])
    except Exception as e:
        logger.warning("Pricing API request failed for %s: %s", service_name, e)
    return []


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


def _find_best_match(items: list[dict], sku: str) -> dict | None:
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

    Sources: "live", "live-fallback", "estimated", "unavailable"
    """
    with _tracer.start_as_current_span("azure.pricing.query") as span:
        span.set_attribute("pricing.service_name", service_name)
        span.set_attribute("pricing.sku", sku)
        span.set_attribute("pricing.region", region)

        # Return a known estimate for services not in the Retail Prices API
        if service_name in ESTIMATED_PRICES:
            est = ESTIMATED_PRICES[service_name]
            span.set_attribute("pricing.source", "estimated")
            return dict(est)  # return a copy

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

        # No data found
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
