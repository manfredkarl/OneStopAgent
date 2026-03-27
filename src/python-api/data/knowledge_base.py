"""Mock envisioning scenarios and reference architectures."""

SCENARIOS: list[dict] = [
    {
        "id": "ecommerce-web",
        "title": "E-Commerce Web Application",
        "description": (
            "A scalable e-commerce platform on Azure using App Service, "
            "Azure SQL, Redis Cache, and CDN for global reach."
        ),
        "keywords": ["ecommerce", "retail", "shopping", "cart", "store", "online"],
        "referenceArchitecture": "https://learn.microsoft.com/azure/architecture/example-scenario/apps/ecommerce-scenario",
        "components": ["App Service", "Azure SQL Database", "Azure Cache for Redis", "Azure CDN", "Azure Blob Storage"],
    },
    {
        "id": "iot-telemetry",
        "title": "IoT Telemetry & Analytics",
        "description": (
            "Ingest and analyse millions of IoT events per second with "
            "IoT Hub, Stream Analytics, and Cosmos DB."
        ),
        "keywords": ["iot", "telemetry", "sensor", "device", "streaming", "real-time"],
        "referenceArchitecture": "https://learn.microsoft.com/azure/architecture/reference-architectures/iot",
        "components": ["IoT Hub", "Stream Analytics", "Cosmos DB", "Azure Functions", "Power BI"],
    },
    {
        "id": "ai-ml-platform",
        "title": "AI / ML Platform",
        "description": (
            "End-to-end machine learning platform with Azure ML, "
            "Databricks, and GPU-backed compute for training."
        ),
        "keywords": ["ai", "ml", "machine learning", "model", "training", "inference", "data science"],
        "referenceArchitecture": "https://learn.microsoft.com/azure/architecture/data-guide/technology-choices/data-science-and-machine-learning",
        "components": ["Azure Machine Learning", "Databricks", "Azure Blob Storage", "Azure Container Registry", "AKS"],
    },
    {
        "id": "microservices-aks",
        "title": "Microservices on AKS",
        "description": (
            "Cloud-native microservices architecture running on Azure "
            "Kubernetes Service with API Management front door."
        ),
        "keywords": ["microservices", "kubernetes", "k8s", "container", "docker", "api"],
        "referenceArchitecture": "https://learn.microsoft.com/azure/architecture/reference-architectures/containers/aks-microservices/aks-microservices",
        "components": ["AKS", "Azure Container Registry", "API Management", "Azure Monitor", "Key Vault"],
    },
    {
        "id": "data-warehouse",
        "title": "Modern Data Warehouse",
        "description": (
            "Enterprise analytics with Synapse Analytics, Data Lake, "
            "and Power BI for business intelligence."
        ),
        "keywords": ["data", "warehouse", "analytics", "bi", "reporting", "etl", "synapse"],
        "referenceArchitecture": "https://learn.microsoft.com/azure/architecture/solution-ideas/articles/enterprise-data-warehouse",
        "components": ["Synapse Analytics", "Data Lake Storage", "Data Factory", "Power BI", "Purview"],
    },
    {
        "id": "saas-multitenant",
        "title": "Multi-Tenant SaaS Application",
        "description": (
            "A SaaS platform with tenant isolation, per-tenant scaling, "
            "and shared infrastructure on Azure."
        ),
        "keywords": ["saas", "multitenant", "multi-tenant", "tenant", "subscription", "platform"],
        "referenceArchitecture": "https://learn.microsoft.com/azure/architecture/guide/multitenant/overview",
        "components": ["App Service", "Azure SQL Elastic Pool", "Azure Front Door", "Key Vault", "Azure AD B2C"],
    },
    {
        "id": "line-of-business",
        "title": "Line-of-Business Web App",
        "description": (
            "Internal enterprise application with Entra ID authentication, "
            "App Service, and Azure SQL."
        ),
        "keywords": ["lob", "internal", "enterprise", "business", "corporate", "intranet", "web app"],
        "referenceArchitecture": "https://learn.microsoft.com/azure/architecture/web-apps/app-service/architectures/basic-web-app",
        "components": ["App Service", "Azure SQL Database", "Entra ID", "Application Insights", "Key Vault"],
    },
    {
        "id": "event-driven",
        "title": "Event-Driven Architecture",
        "description": (
            "Loosely coupled system using Event Grid, Service Bus, and "
            "Azure Functions for event processing."
        ),
        "keywords": ["event", "event-driven", "queue", "message", "pub/sub", "serverless"],
        "referenceArchitecture": "https://learn.microsoft.com/azure/architecture/guide/architecture-styles/event-driven",
        "components": ["Event Grid", "Service Bus", "Azure Functions", "Cosmos DB", "Application Insights"],
    },
]


def find_matching_scenarios(description: str, top_k: int = 3) -> list[dict]:
    """Return the top-k scenarios whose keywords appear in the description."""
    desc_lower = description.lower()
    scored: list[tuple[int, dict]] = []
    for scenario in SCENARIOS:
        score = sum(1 for kw in scenario["keywords"] if kw in desc_lower)
        if score > 0:
            scored.append((score, scenario))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return SCENARIOS[:top_k]
    return [s for _, s in scored[:top_k]]
