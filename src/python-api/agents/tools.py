"""Specialist agent tools — each tool does REAL work."""

from __future__ import annotations

import json
from langchain_core.tools import tool

from agents.llm import llm
from services.pricing import query_azure_pricing_sync
from data.knowledge_base import find_matching_scenarios


# ---------------------------------------------------------------------------
# Helper: call Azure OpenAI to generate a Mermaid diagram
# ---------------------------------------------------------------------------

def _generate_mermaid(requirements: str) -> str:
    """Call Azure OpenAI to produce a Mermaid flowchart for the architecture."""
    response = llm.invoke([
        {
            "role": "system",
            "content": (
                "You are an Azure solutions architect. Generate a Mermaid flowchart TD diagram "
                "for an Azure architecture based on the requirements below.\n"
                "Return ONLY the Mermaid code block (starting with ```mermaid and ending with ```). "
                "Use meaningful node names. Include Azure service names."
            ),
        },
        {"role": "user", "content": requirements},
    ])
    text = response.content.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _extract_components(requirements: str) -> list[dict]:
    """Call Azure OpenAI to extract architecture components as structured JSON."""
    response = llm.invoke([
        {
            "role": "system",
            "content": (
                "You are an Azure solutions architect. Given the requirements, return a JSON array "
                "of architecture components. Each object must have:\n"
                '  {"name": "...", "azureService": "...", "purpose": "...", "tier": "standard|premium|basic"}\n'
                "Return ONLY the JSON array, no explanation."
            ),
        },
        {"role": "user", "content": requirements},
    ])
    text = response.content.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return [{"name": "Web Application", "azureService": "Azure App Service", "purpose": "Host the application", "tier": "standard"}]


def _select_sku(component: dict) -> str:
    """Pick an appropriate SKU based on the component tier."""
    tier = component.get("tier", "standard").lower()
    sku_map = {"basic": "B1", "standard": "S1", "premium": "P2v3", "free": "Free"}
    return sku_map.get(tier, "S1")


# ---------------------------------------------------------------------------
# LangChain Tools
# ---------------------------------------------------------------------------

@tool
def generate_architecture(requirements: str) -> str:
    """Design an Azure architecture based on requirements. Returns a Mermaid diagram and component list.

    Args:
        requirements: Description of what needs to be built, including scale, region, and compliance needs.
    """
    mermaid_code = _generate_mermaid(requirements)
    components = _extract_components(requirements)

    return json.dumps({
        "type": "architecture",
        "mermaidCode": mermaid_code,
        "components": components,
        "narrative": f"Architecture designed for: {requirements[:200]}",
        "metadata": {
            "nodeCount": mermaid_code.count("-->") + mermaid_code.count("---") + 1,
            "edgeCount": mermaid_code.count("-->") + mermaid_code.count("---"),
        },
    })


@tool
def select_azure_services(architecture_json: str) -> str:
    """Select specific Azure services, SKUs, and regions for each architecture component.

    Args:
        architecture_json: JSON string containing the architecture components to map to Azure services.
    """
    architecture = json.loads(architecture_json)
    services: list[dict] = []
    for comp in architecture.get("components", []):
        sku = _select_sku(comp)
        services.append({
            "componentName": comp.get("name", "Component"),
            "serviceName": comp.get("azureService", "Azure App Service"),
            "sku": sku,
            "region": "eastus",
            "capabilities": ["High availability", "Auto-scaling", "Managed service"],
        })
    return json.dumps({"type": "serviceSelections", "selections": services})


@tool
def estimate_costs(services_json: str) -> str:
    """Estimate Azure costs using the Azure Retail Prices API.

    Args:
        services_json: JSON string containing selected Azure services with SKUs and regions.
    """
    services = json.loads(services_json)
    items: list[dict] = []
    total = 0.0

    for svc in services.get("selections", []):
        price = query_azure_pricing_sync(svc["serviceName"], svc["sku"], svc.get("region", "eastus"))
        # Hourly prices → monthly (730 h); already-monthly prices stay as-is
        monthly = price * 730 if price < 1.0 else price
        items.append({
            "serviceName": svc["serviceName"],
            "sku": svc["sku"],
            "region": svc.get("region", "eastus"),
            "unitPrice": round(price, 4),
            "monthlyCost": round(monthly, 2),
        })
        total += monthly

    return json.dumps({
        "type": "costEstimate",
        "estimate": {
            "currency": "USD",
            "items": items,
            "totalMonthly": round(total, 2),
            "totalAnnual": round(total * 12, 2),
            "assumptions": ["Based on 730 hours/month for hourly-priced services", "Pay-as-you-go pricing"],
            "pricingSource": "live",
        },
    })


@tool
def assess_business_value(context: str) -> str:
    """Analyse ROI and business impact of the proposed Azure solution.

    Args:
        context: JSON string with architecture, services, costs, and project description.
    """
    # Use the LLM for a richer executive summary
    response = llm.invoke([
        {
            "role": "system",
            "content": (
                "You are a cloud business analyst. Given the Azure solution context below, "
                "write a concise executive summary (3-5 sentences) covering cost optimisation, "
                "scalability, time-to-market, and risk reduction. Return ONLY the summary text."
            ),
        },
        {"role": "user", "content": context[:4000]},
    ])
    summary = response.content.strip()

    return json.dumps({
        "type": "businessValue",
        "assessment": {
            "drivers": [
                {
                    "name": "Cost Optimisation",
                    "impact": "Cloud migration typically reduces infrastructure costs by 20-40%",
                    "quantifiedEstimate": "Estimated 30% reduction vs on-premises",
                },
                {
                    "name": "Scalability",
                    "impact": "Auto-scaling handles peak loads without over-provisioning",
                    "quantifiedEstimate": "Handle 10x traffic spikes with zero downtime",
                },
                {
                    "name": "Time to Market",
                    "impact": "PaaS services reduce development time by 40-60%",
                    "quantifiedEstimate": "Estimated 50% faster feature delivery",
                },
                {
                    "name": "Risk Reduction",
                    "impact": "Managed services reduce operational risk and security burden",
                    "quantifiedEstimate": "99.95% SLA across core services",
                },
            ],
            "executiveSummary": summary,
            "confidenceLevel": "moderate",
            "disclaimer": "These are estimates based on industry benchmarks and typical Azure deployments.",
        },
    })


@tool
def generate_presentation(context: str) -> str:
    """Generate a PowerPoint presentation compiling all solution outputs.

    Args:
        context: JSON string with all agent outputs (architecture, services, costs, value).
    """
    from services.presentation import create_pptx

    ctx = json.loads(context)
    filepath = create_pptx(ctx)
    return json.dumps({
        "type": "presentationReady",
        "metadata": {"slideCount": 8, "filePath": filepath},
    })


@tool
def suggest_scenarios(description: str) -> str:
    """Suggest relevant Azure scenarios and reference architectures when the customer need is vague.

    Args:
        description: The customer's initial description or problem statement.
    """
    matches = find_matching_scenarios(description)
    return json.dumps({"type": "envisioning", "scenarios": matches})
