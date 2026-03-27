"""Azure Specialist Agent — maps architecture components to Azure services with SKUs."""
import re
from agents.state import AgentState


def _select_sku(component_name: str, requirements: str = "") -> str:
    """Select SKU based on component type and scale requirements."""
    # Extract concurrent users from requirements
    users = 1000  # default
    match = re.search(r'(\d[\d,]*)\s*(?:concurrent|simultaneous)?\s*users', requirements, re.I)
    if match:
        users = int(match.group(1).replace(',', ''))

    name = component_name.lower()

    if "sql" in name or "database" in name:
        if users > 5000:
            return "Premium P4"
        if users > 1000:
            return "Standard S3"
        return "Standard S1"
    elif "redis" in name or "cache" in name:
        if users > 5000:
            return "P1"
        if users > 1000:
            return "C1"
        return "C0"
    elif "app service" in name or "web" in name or "api" in name or "frontend" in name or "backend" in name:
        if users > 5000:
            return "P2v3"
        if users > 1000:
            return "S1"
        return "B1"
    elif "search" in name:
        return "Standard S1"
    elif "cosmos" in name:
        return "Standard"

    return "Standard S1"


class AzureSpecialistAgent:
    name = "Azure Specialist"
    emoji = "☁️"

    def run(self, state: AgentState) -> AgentState:
        """Map architecture components to Azure services with appropriate SKUs."""
        components = state.architecture.get("components", [])
        requirements = state.user_input

        selections: list[dict] = []
        for comp in components:
            sku = _select_sku(comp.get("name", ""), requirements)
            selections.append({
                "componentName": comp.get("name", "Component"),
                "serviceName": comp.get("azureService", "Azure App Service"),
                "sku": sku,
                "region": "eastus",
                "capabilities": ["High availability", "Auto-scaling", "Managed service"],
            })

        state.services = {"selections": selections}
        return state
