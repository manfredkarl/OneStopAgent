"""Azure Retail Prices API client with mock fallback.

Implements the 5-tier pricing source behavior from FRD-04 §2.4:
  1. live          — exact SKU match from API
  2. live-fallback — cheapest non-zero result when SKU not found
  3. approximate   — mock/reference pricing (API failed or no results)
  4. approximate   — API timeout or HTTP error
  5. live (retry)  — re-query with eastus when region has no results
"""

import logging

import httpx
from opentelemetry import trace

logger = logging.getLogger(__name__)

_tracer = trace.get_tracer(__name__)

PRICING_API = "https://prices.azure.com/api/retail/prices"

HOURLY_SERVICES = {
    "Azure App Service",
    "Azure Cache for Redis",
    "Azure Container Apps",
    "Azure Kubernetes Service",
}

# Reference prices keyed by "{serviceName}-{sku}" or "{serviceName}" (monthly).
# Covers FRD-03 extended services and FRD-04 §2.4 MOCK_PRICES.
MOCK_PRICES: dict[str, dict[str, float]] = {
    "Azure App Service": {"Free": 0.0, "B1": 54.75, "B2": 109.50, "S1": 73.00, "S2": 146.00, "P1v3": 122.64, "P2v3": 245.28, "P3v3": 490.56},
    "Azure SQL Database": {"Basic": 4.99, "Standard S0": 15.00, "Standard S1": 30.00, "Standard S2": 75.00, "Premium P1": 465.00, "Premium P4": 930.00, "Business Critical": 5500.00},
    "Azure Cache for Redis": {"C0": 16.00, "C0 Basic": 16.00, "C1": 41.00, "C1 Basic": 41.00, "C1 Standard": 80.00, "P1": 224.00, "P1 Premium": 224.00, "P3": 862.00},
    "Azure Cosmos DB": {"Serverless": 25.00, "400 RU/s": 23.36, "1000 RU/s": 58.40, "Autoscale 1000 RU/s": 58.40, "Autoscale 10000 RU/s": 584.00, "Autoscale 50000 RU/s": 2920.00},
    "Azure Blob Storage": {"Hot LRS": 21.00, "Standard LRS": 21.00, "Cool LRS": 10.00, "Archive LRS": 2.00, "GRS": 43.00},
    "Azure CDN": {"Standard": 8.10, "Premium": 17.00},
    "Azure Front Door": {"Standard": 35.00, "Premium": 330.00},
    "Azure Functions": {"Consumption": 0.00, "Premium EP1": 145.28, "Premium EP3": 580.90},
    "Azure Kubernetes Service": {"Standard": 73.00, "B4ms": 121.18, "D4s v3": 140.16, "D8s v3": 280.32, "Standard_D4s_v3 (3 nodes)": 438.00},
    "Azure Container Apps": {"Consumption": 0.00, "Dedicated": 220.00},
    "Azure Container Registry": {"Basic": 5.00, "Standard": 20.00, "Premium": 50.00},
    "Azure API Management": {"Developer": 49.27, "Standard": 699.55, "Premium": 2794.00, "Consumption": 3.50},
    "API Management": {"Developer": 49.27, "Standard": 699.55, "Premium": 2794.00, "Consumption": 3.50},
    "Azure Monitor": {"Basic": 0.00, "Standard": 15.00, "Pay-as-you-go": 2.76},
    "Azure Key Vault": {"Standard": 0.00, "Premium": 0.00},
    "Key Vault": {"Standard": 0.00, "Premium": 0.00},
    "Application Insights": {"Basic": 2.30, "Pay-as-you-go": 2.76},
    "IoT Hub": {"Free": 0.00, "S1": 25.00, "S2": 250.00, "S3": 2500.00},
    "Stream Analytics": {"Standard": 80.30},
    "Azure Machine Learning": {"Basic": 0.00, "Enterprise": 400.00},
    "Databricks": {"Standard": 51.10, "Premium": 109.50},
    "Synapse Analytics": {"DW100c": 876.00, "DW200c": 1752.00, "DW500c": 4380.00},
    "Data Factory": {"Pipeline": 1.00, "Data Flow": 200.02},
    "Power BI": {"Pro": 9.99, "Premium P1": 4995.00},
    "Azure SQL Elastic Pool": {"Standard 50 eDTU": 73.00, "Standard 100 eDTU": 146.00, "Premium 125 eDTU": 465.00},
    "Entra ID": {"Free": 0.00, "P1": 6.00, "P2": 9.00},
    "Event Grid": {"Basic": 0.60},
    "Azure Event Hubs": {"Standard": 11.16, "Premium": 870.00},
    "Service Bus": {"Basic": 0.05, "Standard": 9.81, "Premium": 677.00},
    "Azure Service Bus": {"Standard": 9.81, "Premium": 677.08},
    "Data Lake Storage": {"Hot LRS": 21.00, "Cool LRS": 10.00},
    "Purview": {"Standard": 280.32},
    "Virtual Network": {"Basic": 0.00},
    "Azure AD B2C": {"Free Tier": 0.00, "Premium P1": 0.00325},
    "Load Balancer": {"Basic": 0.00, "Standard": 18.25},
    "Azure OpenAI": {"Standard S0": 500.00},  # ~$500/mo reference for moderate usage (pay-per-token)
    "Azure AI Search": {"Basic": 75.78, "Standard S1": 250.39},
    "Microsoft Fabric": {"F2": 262.80},
}


def _get_mock_price(service_name: str, sku: str) -> dict:
    """Look up mock price from reference data.

    Priority (per FRD-04 §2.8):
      1. Exact service + SKU match
      2. Fuzzy SKU match within the service
      3. Median SKU price for that service
      4. $0.00 if service not in MOCK_PRICES
    """
    service_prices = MOCK_PRICES.get(service_name, {})

    # 1. Exact key
    if sku in service_prices:
        return {"price": service_prices[sku], "source": "approximate", "note": "Reference pricing"}

    # 2. Fuzzy match — find SKU containing same tier keywords
    sku_lower = sku.lower()
    for tier_key, price in service_prices.items():
        if tier_key.lower() in sku_lower or sku_lower in tier_key.lower():
            return {"price": price, "source": "approximate", "note": f"Matched to {tier_key} (reference)"}

    # 3. Median price (not minimum) to avoid underestimation
    if service_prices:
        prices = sorted(service_prices.values())
        median_price = prices[len(prices) // 2]
        return {"price": median_price, "source": "approximate", "note": "Median tier pricing (reference)"}

    # 4. Try partial service-name match across all keys
    sn_lower = service_name.lower()
    for svc, svc_prices in MOCK_PRICES.items():
        if sn_lower in svc.lower() or svc.lower() in sn_lower:
            prices = sorted(svc_prices.values())
            median_price = prices[len(prices) // 2]
            return {"price": median_price, "source": "approximate", "note": "Median tier pricing (reference)"}

    return {"price": 0.0, "source": "approximate", "note": f"Pricing unavailable for {service_name}"}


def query_azure_pricing_sync(service_name: str, sku: str, region: str = "eastus") -> dict:
    """Query Azure Retail Prices API.  Returns {price, source, note, unit}.

    Sources: "live", "live-fallback", "approximate"
    Implements the 5-tier pricing source behavior from FRD-04 §2.4.
    """
    api_url = PRICING_API

    with _tracer.start_as_current_span("azure.pricing.query") as span:
        span.set_attribute("pricing.service_name", service_name)
        span.set_attribute("pricing.sku", sku)
        span.set_attribute("pricing.region", region)

        try:
            with httpx.Client(timeout=10) as client:
                # Build OData filter
                filter_str = f"serviceName eq '{service_name}' and armRegionName eq '{region}'"
                resp = client.get(api_url, params={"$filter": filter_str})

                if resp.status_code == 200:
                    items = resp.json().get("Items", [])
                    span.set_attribute("pricing.item_count", len(items))

                    if items:
                        # Scenario 1: Exact SKU match
                        for item in items:
                            sku_name = (item.get("skuName") or "").lower()
                            arm_sku = (item.get("armSkuName") or "").lower()
                            if sku.lower() in sku_name or sku.lower() in arm_sku:
                                if item.get("retailPrice", 0) > 0:
                                    span.set_attribute("pricing.source", "live")
                                    return {
                                        "price": item["retailPrice"],
                                        "source": "live",
                                        "note": None,
                                        "unit": item.get("unitOfMeasure", "1 Hour"),
                                    }

                        # Scenario 2: No exact SKU → cheapest non-zero
                        non_zero = [i for i in items if i.get("retailPrice", 0) > 0]
                        if non_zero:
                            cheapest = min(non_zero, key=lambda i: i["retailPrice"])
                            span.set_attribute("pricing.source", "live-fallback")
                            return {
                                "price": cheapest["retailPrice"],
                                "source": "live-fallback",
                                "note": f"Exact SKU '{sku}' not found, using closest match",
                                "unit": cheapest.get("unitOfMeasure", "1 Hour"),
                            }

                    # Scenario 5: No results in region → retry with eastus
                    if region != "eastus":
                        result = query_azure_pricing_sync(service_name, sku, "eastus")
                        if result["source"] != "approximate":
                            result["note"] = f"Service not available in {region}, pricing for eastus"
                        span.set_attribute("pricing.source", result["source"])
                        return result

        except Exception as e:
            logger.warning("Azure Pricing API query failed for %s/%s: %s", service_name, sku, e)
            span.set_attribute("pricing.error", "api_exception")
            # Fall through to mock pricing

        # Scenario 3/4: API failed or no results → use mock
        mock_result = _get_mock_price(service_name, sku)
        span.set_attribute("pricing.source", "approximate")
        return {
            "price": mock_result["price"],
            "source": "approximate",
            "note": mock_result["note"],
            "unit": "1 Hour" if service_name in HOURLY_SERVICES else "1/Month",
        }
