"""Azure Retail Prices API client with mock fallback."""

import httpx

PRICING_API = "https://prices.azure.com/api/retail/prices"

MOCK_PRICES: dict[str, dict[str, float]] = {
    "Azure App Service": {"Free": 0.0, "B1": 0.075, "B2": 0.15, "S1": 0.10, "S2": 0.20, "P1v3": 0.20, "P2v3": 0.30, "P3v3": 0.60},
    "Azure SQL Database": {"Basic": 4.99, "Standard S0": 15.0, "Standard S1": 30.0, "Standard S2": 75.0, "Premium P1": 465.0, "Premium P4": 930.0},
    "Azure Cache for Redis": {"C0 Basic": 16.0, "C1 Basic": 40.0, "C1 Standard": 80.0, "P1 Premium": 172.0},
    "Azure Cosmos DB": {"Serverless": 0.25, "400 RU/s": 23.36, "1000 RU/s": 58.40},
    "Azure Blob Storage": {"Hot LRS": 0.018, "Cool LRS": 0.01, "Archive LRS": 0.002},
    "Azure CDN": {"Standard": 0.081, "Premium": 0.17},
    "Azure Front Door": {"Standard": 35.0, "Premium": 330.0},
    "Azure Functions": {"Consumption": 0.0, "Premium EP1": 0.173},
    "Azure Kubernetes Service": {"Standard": 0.10, "B4ms": 0.166, "D4s v3": 0.192, "D8s v3": 0.384},
    "Azure Container Registry": {"Basic": 5.0, "Standard": 20.0, "Premium": 50.0},
    "API Management": {"Developer": 49.0, "Standard": 686.0, "Premium": 2794.0, "Consumption": 3.50},
    "Azure Monitor": {"Basic": 0.0, "Standard": 15.0},
    "Key Vault": {"Standard": 0.03, "Premium": 1.0},
    "Application Insights": {"Basic": 2.30},
    "IoT Hub": {"Free": 0.0, "S1": 25.0, "S2": 250.0, "S3": 2500.0},
    "Stream Analytics": {"Standard": 0.11},
    "Azure Machine Learning": {"Basic": 0.0, "Enterprise": 400.0},
    "Databricks": {"Standard": 0.07, "Premium": 0.15},
    "Synapse Analytics": {"DW100c": 1.20, "DW200c": 2.40, "DW500c": 6.00},
    "Data Factory": {"Pipeline": 1.0, "Data Flow": 0.274},
    "Power BI": {"Pro": 9.99, "Premium P1": 4995.0},
    "Azure SQL Elastic Pool": {"Standard 50 eDTU": 73.0, "Standard 100 eDTU": 146.0, "Premium 125 eDTU": 465.0},
    "Entra ID": {"Free": 0.0, "P1": 6.0, "P2": 9.0},
    "Event Grid": {"Basic": 0.60},
    "Service Bus": {"Basic": 0.05, "Standard": 9.81, "Premium": 677.0},
    "Data Lake Storage": {"Hot LRS": 0.018, "Cool LRS": 0.01},
    "Purview": {"Standard": 0.384},
    "Virtual Network": {"Basic": 0.0},
    "Azure AD B2C": {"Free Tier": 0.0, "Premium P1": 0.00325},
    "Load Balancer": {"Basic": 0.0, "Standard": 0.025},
}


def query_azure_pricing_sync(service_name: str, sku: str, region: str = "eastus") -> float:
    """Query Azure Retail Prices API (synchronous). Falls back to mock prices."""
    try:
        with httpx.Client(timeout=8) as client:
            filter_str = f"serviceName eq '{service_name}' and armRegionName eq '{region}'"
            resp = client.get(PRICING_API, params={"$filter": filter_str})
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("Items", [])
                for item in items:
                    sku_name = (item.get("skuName") or "").lower()
                    arm_sku = (item.get("armSkuName") or "").lower()
                    if sku.lower() in sku_name or sku.lower() in arm_sku:
                        price = item.get("retailPrice", 0.0)
                        if price > 0:
                            return price
    except Exception:
        pass

    # Fallback to mock
    service_prices = MOCK_PRICES.get(service_name, {})
    for mock_sku, price in service_prices.items():
        if sku.lower() in mock_sku.lower() or mock_sku.lower() in sku.lower():
            return price
    # Last resort: return first price for the service
    if service_prices:
        return list(service_prices.values())[0]
    return 0.0
