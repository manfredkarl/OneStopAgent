"""Azure Specialist Agent — deterministic SKU mapping per FRD-03 §3."""
import re
from agents.state import AgentState

# ── §3.4  Core SKU Matrix ────────────────────────────────────────────────
# Scale tiers: ≤100, ≤1000, ≤10000, >10000
CORE_SKU_MATRIX = {
    "Azure App Service":     ["B1",          "S1",           "P2v3",            "P3v3"],
    "Azure SQL Database":    ["Basic",       "Standard S1",  "Premium P4",      "Business Critical"],
    "Azure Cache for Redis": ["C0",          "C1",           "P1",              "P3"],
    "Azure Cosmos DB":       ["Serverless",  "Autoscale 1000 RU/s", "Autoscale 10000 RU/s", "Autoscale 50000 RU/s"],
    "Azure Functions":       ["Consumption", "Consumption",  "Premium EP1",     "Premium EP3"],
}

SCALE_TIERS = [100, 1000, 10000, float("inf")]


def _get_core_sku(service_name: str, users: int) -> str | None:
    skus = CORE_SKU_MATRIX.get(service_name)
    if not skus:
        return None
    for i, threshold in enumerate(SCALE_TIERS):
        if users <= threshold:
            return skus[i]
    return skus[-1]


# ── §3.5  Extended Service Defaults ──────────────────────────────────────
EXTENDED_DEFAULTS = {
    "Azure OpenAI":             {"default": "Standard S0", "note": "Provisioned throughput for >1000 users"},
    "Azure AI Search":          {"default": "Standard S1", "small": "Basic"},
    "Azure Container Apps":     {"default": "Consumption", "large": "Dedicated"},
    "Azure Kubernetes Service": {"default": "Standard_D4s_v3 (3 nodes)", "note": "Scale node count with users"},
    "Azure Event Hubs":         {"default": "Standard", "large": "Premium"},
    "Azure Service Bus":        {"default": "Standard", "note": "Premium for mission-critical"},
    "Azure Blob Storage":       {"default": "Standard LRS", "ha": "GRS"},
    "Azure Key Vault":          {"default": "Standard", "note": "Premium for HSM-backed keys"},
    "Azure Monitor":            {"default": "Pay-as-you-go", "note": "Always included"},
    "Azure Front Door":         {"default": "Standard", "note": "Premium for WAF + private link"},
    "Azure API Management":     {"default": "Developer", "prod": "Standard"},
    "Microsoft Fabric":         {"default": "F2", "note": "Scale with data volume"},
}


def _get_extended_sku(service_name: str, users: int) -> tuple[str, str | None]:
    """Returns (sku, note_or_none)."""
    info = EXTENDED_DEFAULTS.get(service_name)
    if not info:
        return None, None
    sku = info["default"]
    note = info.get("note")
    if users > 10000 and "large" in info:
        sku = info["large"]
    elif users <= 100 and "small" in info:
        sku = info["small"]
    elif users > 1000 and "prod" in info:
        sku = info["prod"]
    return sku, note


# ── §3.6  Fallback Rule ─────────────────────────────────────────────────
def _get_fallback_sku(service_name: str) -> tuple[str, str]:
    """For unknown services: Standard SKU + warning note."""
    return "Standard", f"⚠️ SKU needs manual validation for {service_name}"


# ── Scale & Region Extraction ────────────────────────────────────────────
def _extract_users(text: str) -> int:
    """Extract concurrent users from text. Default: 1000."""
    match = re.search(r'(\d[\d,]*)\s*(?:concurrent|simultaneous)?\s*users', text, re.I)
    if match:
        return int(match.group(1).replace(',', ''))
    return 1000


def _extract_regions(text: str) -> list[str]:
    """Extract Azure regions from text. Default: ['eastus']."""
    regions: list[str] = []
    text_lower = text.lower()

    # Compound patterns first (e.g. "US East and West")
    compound_patterns = [
        (r'us\s+east\s+and\s+west', ["eastus", "westus2"]),
        (r'east\s+and\s+west\s+us', ["eastus", "westus2"]),
        (r'east\s*us\s+and\s+west\s*us', ["eastus", "westus2"]),
    ]
    for pattern, region_list in compound_patterns:
        if re.search(pattern, text_lower):
            for r in region_list:
                if r not in regions:
                    regions.append(r)

    # Single-region phrases
    region_map = {
        "us east": "eastus", "east us": "eastus", "us west": "westus2", "west us": "westus2",
        "europe": "westeurope", "west europe": "westeurope", "uk": "uksouth",
        "asia": "southeastasia", "southeast asia": "southeastasia", "japan": "japaneast",
        "australia": "australiaeast",
    }
    for phrase, region in region_map.items():
        if phrase in text_lower and region not in regions:
            regions.append(region)

    return regions if regions else ["eastus"]


# ── §3.7  Multi-Region Handling ──────────────────────────────────────────
def _handle_multi_region(selections: list[dict], regions: list[str]) -> list[dict]:
    """If multiple regions, add HA/DR note + overhead line item."""
    if len(regions) <= 1:
        return selections

    primary = regions[0]
    secondary = regions[1]

    for sel in selections:
        sel["region"] = primary
        existing_note = sel.get("skuNote", "") or ""
        ha_note = f"For HA, deploy secondary in {secondary}"
        sel["skuNote"] = f"{existing_note}. {ha_note}".strip(". ") if existing_note else ha_note

    selections.append({
        "componentName": "Multi-Region Replication",
        "serviceName": "Multi-region overhead",
        "sku": "N/A",
        "region": f"{primary} + {secondary}",
        "capabilities": ["High availability", "Disaster recovery", "Geo-redundancy"],
        "skuNote": "Estimated 30-50% uplift on compute + storage costs",
    })

    return selections


# ── Agent ─────────────────────────────────────────────────────────────────
class AzureSpecialistAgent:
    name = "Azure Specialist"
    emoji = "☁️"

    def run(self, state: AgentState) -> AgentState:
        """Deterministic Azure service + SKU mapping — no LLM calls."""
        components = state.architecture.get("components", [])
        full_text = f"{state.user_input} {state.clarifications}"
        users = _extract_users(full_text)
        regions = _extract_regions(full_text)
        primary_region = regions[0]

        selections: list[dict] = []
        for comp in components:
            service_name = comp.get("azureService", comp.get("name", "Unknown"))
            component_name = comp.get("name", service_name)

            # Try core matrix first
            sku = _get_core_sku(service_name, users)
            sku_note = None

            if sku is None:
                # Try extended defaults
                sku, sku_note = _get_extended_sku(service_name, users)

            if sku is None:
                # Fallback for unknown services
                sku, sku_note = _get_fallback_sku(service_name)

            selections.append({
                "componentName": component_name,
                "serviceName": service_name,
                "sku": sku,
                "region": primary_region,
                "capabilities": self._get_capabilities(service_name),
                "skuNote": sku_note,
            })

        selections = _handle_multi_region(selections, regions)

        state.services = {"selections": selections}
        return state

    def _get_capabilities(self, service_name: str) -> list[str]:
        """Return standard capabilities for a service."""
        caps = {
            "Azure App Service": ["Auto-scaling", "Managed SSL", "Custom domains", "Deployment slots"],
            "Azure SQL Database": ["Automatic backups", "Geo-replication", "Advanced security"],
            "Azure Cache for Redis": ["Low latency", "Session management", "Data caching"],
            "Azure Cosmos DB": ["Global distribution", "Multi-model", "Automatic indexing"],
            "Azure Functions": ["Serverless", "Event-driven", "Pay-per-execution"],
            "Azure OpenAI": ["GPT models", "Embeddings", "Fine-tuning"],
            "Azure AI Search": ["Full-text search", "Semantic ranking", "Vector search"],
            "Azure Kubernetes Service": ["Container orchestration", "Auto-scaling", "Helm support"],
            "Azure Front Door": ["Global load balancing", "WAF", "CDN"],
        }
        return caps.get(service_name, ["Managed service", "High availability"])
