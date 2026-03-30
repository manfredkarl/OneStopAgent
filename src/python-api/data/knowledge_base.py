"""Local reference-architecture patterns conforming to FRD-02 §3.3 schema.

Each pattern carries the full retrieved-pattern schema so it can be used as a
seamless fallback when the MCP-based KnowledgeAgent is unavailable.
"""

PATTERNS: list[dict] = [
    # 1 ── Scalable E-Commerce Web App (Retail)
    {
        "title": "Scalable E-Commerce Web App",
        "url": "https://learn.microsoft.com/azure/architecture/example-scenario/apps/ecommerce-scenario",
        "summary": (
            "A highly scalable e-commerce platform built on Azure App Service "
            "with Azure SQL and Redis Cache for sub-millisecond response times. "
            "Azure CDN delivers static assets globally for fast page loads."
        ),
        "workload_type": "web-app",
        "industry": "Retail",
        "compliance_tags": ["PCI-DSS", "GDPR"],
        "recommended_services": [
            "Azure App Service",
            "Azure SQL Database",
            "Azure Cache for Redis",
            "Azure CDN",
            "Azure Blob Storage",
        ],
        "components": [
            {"name": "Web Frontend", "azureService": "Azure App Service", "description": "Hosts the customer-facing storefront"},
            {"name": "Product Database", "azureService": "Azure SQL Database", "description": "Stores product catalog, orders, and customer data"},
            {"name": "Session Cache", "azureService": "Azure Cache for Redis", "description": "Caches shopping-cart and session state for low latency"},
            {"name": "Static Assets", "azureService": "Azure CDN", "description": "Delivers images, scripts, and stylesheets globally"},
            {"name": "Media Storage", "azureService": "Azure Blob Storage", "description": "Stores product images and uploaded media"},
        ],
        "confidence_score": 1.0,
    },
    # 2 ── AI-Powered Product Recommendations (Retail)
    {
        "title": "AI-Powered Product Recommendations",
        "url": "https://learn.microsoft.com/azure/architecture/ai-ml/idea/product-recommendations",
        "summary": (
            "Uses Azure Machine Learning and Cosmos DB to deliver real-time, "
            "personalized product recommendations. The model is trained on "
            "historical purchase data and served via a managed online endpoint."
        ),
        "workload_type": "ai-ml",
        "industry": "Retail",
        "compliance_tags": ["GDPR"],
        "recommended_services": [
            "Azure Machine Learning",
            "Azure Cosmos DB",
            "Azure Kubernetes Service",
            "Azure Event Hubs",
            "Azure Blob Storage",
        ],
        "components": [
            {"name": "Recommendation Model", "azureService": "Azure Machine Learning", "description": "Trains and serves the collaborative-filtering model"},
            {"name": "User Profile Store", "azureService": "Azure Cosmos DB", "description": "Stores user behavior and preference vectors"},
            {"name": "Serving Infrastructure", "azureService": "Azure Kubernetes Service", "description": "Hosts the real-time inference API"},
            {"name": "Event Ingestion", "azureService": "Azure Event Hubs", "description": "Streams clickstream events for near-real-time retraining"},
        ],
        "confidence_score": 1.0,
    },
    # 3 ── Patient Portal / Telehealth (Healthcare)
    {
        "title": "Patient Portal and Telehealth Platform",
        "url": "https://learn.microsoft.com/azure/architecture/example-scenario/digital-health/health-portal",
        "summary": (
            "A HIPAA-compliant patient portal enabling virtual visits, secure "
            "messaging, and medical-record access. Azure API for FHIR provides "
            "standards-based health-data interoperability."
        ),
        "workload_type": "web-app",
        "industry": "Healthcare",
        "compliance_tags": ["HIPAA", "SOC2"],
        "recommended_services": [
            "Azure App Service",
            "Azure API for FHIR",
            "Azure Active Directory B2C",
            "Azure Cosmos DB",
            "Azure Communication Services",
        ],
        "components": [
            {"name": "Patient Web App", "azureService": "Azure App Service", "description": "Hosts the patient-facing portal with appointment scheduling"},
            {"name": "Health Data API", "azureService": "Azure API for FHIR", "description": "Provides FHIR-compliant access to electronic health records"},
            {"name": "Identity Provider", "azureService": "Azure Active Directory B2C", "description": "Manages patient identity and MFA enrollment"},
            {"name": "Clinical Data Store", "azureService": "Azure Cosmos DB", "description": "Stores clinical notes, messages, and attachments"},
            {"name": "Video Visits", "azureService": "Azure Communication Services", "description": "Powers real-time video telehealth consultations"},
        ],
        "confidence_score": 1.0,
    },
    # 4 ── IoT Telemetry Platform (Manufacturing)
    {
        "title": "IoT Telemetry Platform",
        "url": "https://learn.microsoft.com/azure/architecture/reference-architectures/iot",
        "summary": (
            "Ingests millions of IoT events per second from factory-floor sensors "
            "using IoT Hub and Stream Analytics. Cosmos DB stores device state "
            "while Power BI surfaces operational dashboards."
        ),
        "workload_type": "iot",
        "industry": "Manufacturing",
        "compliance_tags": ["SOC2"],
        "recommended_services": [
            "Azure IoT Hub",
            "Azure Stream Analytics",
            "Azure Cosmos DB",
            "Azure Functions",
            "Power BI",
        ],
        "components": [
            {"name": "Device Gateway", "azureService": "Azure IoT Hub", "description": "Securely connects and manages millions of IoT devices"},
            {"name": "Stream Processing", "azureService": "Azure Stream Analytics", "description": "Performs real-time aggregation and anomaly detection"},
            {"name": "Device State Store", "azureService": "Azure Cosmos DB", "description": "Stores device twins and time-series telemetry"},
            {"name": "Serverless Actions", "azureService": "Azure Functions", "description": "Triggers alerts and downstream workflows on threshold breaches"},
            {"name": "Operational Dashboard", "azureService": "Power BI", "description": "Visualizes KPIs and telemetry trends for plant operators"},
        ],
        "confidence_score": 1.0,
    },
    # 5 ── Real-Time Fraud Detection (Financial Services)
    {
        "title": "Real-Time Fraud Detection",
        "url": "https://learn.microsoft.com/azure/architecture/example-scenario/ai/fraud-detection",
        "summary": (
            "Applies machine-learning models to streaming transaction data to "
            "flag fraudulent activity in near real time. Azure Event Hubs and "
            "Stream Analytics feed scored events into Cosmos DB for investigation."
        ),
        "workload_type": "ai-ml",
        "industry": "Financial Services",
        "compliance_tags": ["SOC2", "PCI-DSS"],
        "recommended_services": [
            "Azure Machine Learning",
            "Azure Event Hubs",
            "Azure Stream Analytics",
            "Azure Cosmos DB",
            "Azure Synapse Analytics",
        ],
        "components": [
            {"name": "Fraud Model", "azureService": "Azure Machine Learning", "description": "Trains and serves the fraud-scoring classification model"},
            {"name": "Transaction Ingestion", "azureService": "Azure Event Hubs", "description": "Streams millions of payment transactions per second"},
            {"name": "Real-Time Scoring", "azureService": "Azure Stream Analytics", "description": "Applies the ML model to each transaction with sub-second latency"},
            {"name": "Case Store", "azureService": "Azure Cosmos DB", "description": "Stores flagged transactions for analyst review"},
            {"name": "Historical Analytics", "azureService": "Azure Synapse Analytics", "description": "Enables retrospective analysis and model-retraining pipelines"},
        ],
        "confidence_score": 1.0,
    },
    # 6 ── Microservices on AKS (Cross-Industry)
    {
        "title": "Microservices on AKS",
        "url": "https://learn.microsoft.com/azure/architecture/reference-architectures/containers/aks-microservices/aks-microservices",
        "summary": (
            "Cloud-native microservices architecture on Azure Kubernetes Service "
            "with API Management as the gateway. Supports independent scaling, "
            "CI/CD per service, and centralized observability via Azure Monitor."
        ),
        "workload_type": "microservices",
        "industry": "Cross-Industry",
        "compliance_tags": ["SOC2"],
        "recommended_services": [
            "Azure Kubernetes Service",
            "Azure Container Registry",
            "Azure API Management",
            "Azure Monitor",
            "Azure Key Vault",
        ],
        "components": [
            {"name": "Container Orchestration", "azureService": "Azure Kubernetes Service", "description": "Runs and scales containerized microservices"},
            {"name": "Image Registry", "azureService": "Azure Container Registry", "description": "Stores and scans container images"},
            {"name": "API Gateway", "azureService": "Azure API Management", "description": "Provides rate limiting, auth, and API versioning"},
            {"name": "Observability", "azureService": "Azure Monitor", "description": "Collects logs, metrics, and distributed traces"},
            {"name": "Secrets Management", "azureService": "Azure Key Vault", "description": "Stores certificates, connection strings, and API keys"},
        ],
        "confidence_score": 1.0,
    },
    # 7 ── Modern Data Warehouse (Cross-Industry)
    {
        "title": "Modern Data Warehouse",
        "url": "https://learn.microsoft.com/azure/architecture/solution-ideas/articles/enterprise-data-warehouse",
        "summary": (
            "Enterprise analytics solution combining Synapse Analytics, Data Lake "
            "Storage, and Data Factory for ETL orchestration. Power BI delivers "
            "self-service dashboards to business users."
        ),
        "workload_type": "data-platform",
        "industry": "Cross-Industry",
        "compliance_tags": ["SOC2", "GDPR"],
        "recommended_services": [
            "Azure Synapse Analytics",
            "Azure Data Lake Storage",
            "Azure Data Factory",
            "Power BI",
            "Microsoft Purview",
        ],
        "components": [
            {"name": "Analytics Engine", "azureService": "Azure Synapse Analytics", "description": "Serverless and dedicated SQL pools for large-scale queries"},
            {"name": "Data Lake", "azureService": "Azure Data Lake Storage", "description": "Centralized repository for structured and unstructured data"},
            {"name": "ETL Orchestration", "azureService": "Azure Data Factory", "description": "Manages data ingestion and transformation pipelines"},
            {"name": "Business Intelligence", "azureService": "Power BI", "description": "Interactive dashboards and self-service reporting"},
            {"name": "Data Governance", "azureService": "Microsoft Purview", "description": "Data catalog, lineage tracking, and classification"},
        ],
        "confidence_score": 1.0,
    },
    # 8 ── Multi-Tenant SaaS (Cross-Industry)
    {
        "title": "Multi-Tenant SaaS Application",
        "url": "https://learn.microsoft.com/azure/architecture/guide/multitenant/overview",
        "summary": (
            "A SaaS platform with tenant isolation, per-tenant scaling, and "
            "shared infrastructure on Azure. Azure Front Door provides global "
            "load balancing while Azure AD B2C handles customer identity."
        ),
        "workload_type": "web-app",
        "industry": "Cross-Industry",
        "compliance_tags": ["SOC2", "GDPR"],
        "recommended_services": [
            "Azure App Service",
            "Azure SQL Elastic Pool",
            "Azure Front Door",
            "Azure Key Vault",
            "Azure Active Directory B2C",
        ],
        "components": [
            {"name": "Application Tier", "azureService": "Azure App Service", "description": "Hosts the multi-tenant web API and UI"},
            {"name": "Tenant Databases", "azureService": "Azure SQL Elastic Pool", "description": "Provides per-tenant database isolation with shared resources"},
            {"name": "Global Load Balancer", "azureService": "Azure Front Door", "description": "Routes traffic with WAF protection and SSL offload"},
            {"name": "Secrets Management", "azureService": "Azure Key Vault", "description": "Stores tenant-specific connection strings and secrets"},
            {"name": "Customer Identity", "azureService": "Azure Active Directory B2C", "description": "Manages customer sign-up, sign-in, and profile management"},
        ],
        "confidence_score": 1.0,
    },
    # 9 ── Event-Driven Architecture (Cross-Industry)
    {
        "title": "Event-Driven Architecture",
        "url": "https://learn.microsoft.com/azure/architecture/guide/architecture-styles/event-driven",
        "summary": (
            "Loosely coupled system using Event Grid for pub/sub routing and "
            "Service Bus for reliable message queuing. Azure Functions provide "
            "serverless event handlers that scale automatically."
        ),
        "workload_type": "microservices",
        "industry": "Cross-Industry",
        "compliance_tags": ["SOC2"],
        "recommended_services": [
            "Azure Event Grid",
            "Azure Service Bus",
            "Azure Functions",
            "Azure Cosmos DB",
            "Azure Monitor",
        ],
        "components": [
            {"name": "Event Router", "azureService": "Azure Event Grid", "description": "Routes events to subscribers with filtering and fan-out"},
            {"name": "Message Broker", "azureService": "Azure Service Bus", "description": "Provides reliable queuing with dead-letter and session support"},
            {"name": "Event Handlers", "azureService": "Azure Functions", "description": "Serverless compute that processes events on demand"},
            {"name": "State Store", "azureService": "Azure Cosmos DB", "description": "Persists event-sourced state with multi-region replication"},
            {"name": "Observability", "azureService": "Azure Monitor", "description": "End-to-end distributed tracing across event flows"},
        ],
        "confidence_score": 1.0,
    },
    # 10 ── Cloud Migration – Lift & Shift (Cross-Industry)
    {
        "title": "Cloud Migration (Lift and Shift)",
        "url": "https://learn.microsoft.com/azure/architecture/cloud-adoption-framework/migrate/",
        "summary": (
            "Migrates on-premises workloads to Azure IaaS with minimal "
            "refactoring using Azure Migrate for assessment and Azure Site "
            "Recovery for replication. Ideal first step in a modernization journey."
        ),
        "workload_type": "migration",
        "industry": "Cross-Industry",
        "compliance_tags": ["SOC2", "GDPR"],
        "recommended_services": [
            "Azure Migrate",
            "Azure Site Recovery",
            "Azure Virtual Machines",
            "Azure Virtual Network",
            "Azure Monitor",
        ],
        "components": [
            {"name": "Assessment", "azureService": "Azure Migrate", "description": "Discovers and assesses on-premises servers for cloud readiness"},
            {"name": "Replication", "azureService": "Azure Site Recovery", "description": "Replicates VMs to Azure with minimal downtime cutover"},
            {"name": "Compute", "azureService": "Azure Virtual Machines", "description": "Hosts migrated workloads on IaaS virtual machines"},
            {"name": "Networking", "azureService": "Azure Virtual Network", "description": "Provides isolated network with hybrid connectivity"},
            {"name": "Monitoring", "azureService": "Azure Monitor", "description": "Tracks VM performance and health post-migration"},
        ],
        "confidence_score": 1.0,
    },
]

# Backward-compatible alias
SCENARIOS: list[dict] = PATTERNS


def search_local_patterns(query: str, top_k: int = 5) -> list[dict]:
    """Search local patterns using keyword matching. Fallback for MCP unavailability."""
    query_lower = query.lower()
    scored: list[tuple[int, dict]] = []
    for pattern in PATTERNS:
        score = 0
        for field in ["title", "summary", "industry", "workload_type"]:
            val = pattern.get(field, "").lower()
            for word in query_lower.split():
                if word in val and len(word) > 2:
                    score += 1
        for svc in pattern.get("recommended_services", []):
            if any(w in svc.lower() for w in query_lower.split() if len(w) > 2):
                score += 2
        if score > 0:
            result = {**pattern, "confidence_score": min(score / 10, 1.0)}
            scored.append((score, result))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        # No keyword matches — return empty instead of forcing irrelevant patterns
        return []
    return [r for _, r in scored[:top_k]]


def find_matching_scenarios(description: str, top_k: int = 3) -> list[dict]:
    """Return the top-k patterns whose fields match the description.

    Kept for backward compatibility – delegates to ``search_local_patterns``.
    """
    return search_local_patterns(description, top_k=top_k)
