"""Cost Agent — LLM-driven Azure service mapping + pricing estimation.

Merges the former Azure Specialist (service/SKU selection) and Cost Specialist
(pricing estimation) into a single agent.  Uses an LLM to map architecture
components to Azure services with scale-appropriate SKUs, then queries the
Azure Retail Prices API to both *validate* each SKU and *estimate* its cost.

Populates both `state.services` and `state.costs` in one pass.
"""
import json
import logging
import re

from agents.llm import llm
from agents.state import AgentState
from services.pricing import query_azure_pricing_sync

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

CONSUMPTION_ASSUMPTIONS = {
    "Azure Functions": "1M executions/month, 400K GB-s",
    "Azure Blob Storage": "100 GB stored, 10K read operations/month",
    "Azure Cosmos DB": "1,000 RU/s provisioned, 50 GB stored",
    "Azure Event Hubs": "1M events/month",
    "Azure OpenAI": "1M tokens/month",
    "Azure AI Search": "1 search unit",
    "Azure Monitor": "5 GB logs ingested/month",
}

HOURLY_SERVICES = {
    "Azure App Service",
    "Azure Cache for Redis",
    "Azure Container Apps",
    "Azure Kubernetes Service",
}


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


# ── Multi-Region Handling ────────────────────────────────────────────────

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

class CostAgent:
    name = "Cost Specialist"
    emoji = "💰"

    def run(self, state: AgentState) -> AgentState:
        """Map architecture → Azure services + SKUs, then estimate costs in one pass."""
        components = state.architecture.get("components", [])
        full_text = f"{state.user_input} {state.clarifications}"
        users = _extract_users(full_text)
        regions = _extract_regions(full_text)
        primary_region = regions[0]
        industry = state.brainstorming.get("industry", "Cross-Industry")

        # ── Step 1: LLM maps components → Azure services + SKUs ──────
        selections = self._llm_map_services(components, users, primary_region, industry, state)

        # ── Step 2: Pricing API — validate SKUs + get prices ─────────
        items, worst_source, assumptions = self._price_selections(selections, users)

        # ── Step 3: Multi-region handling ────────────────────────────
        selections = _handle_multi_region(selections, regions)

        if len(regions) > 1:
            compute_total = sum(i["monthlyCost"] for i in items)
            overhead = round(compute_total * 0.4, 2)
            items.append({
                "serviceName": "Multi-region replication overhead",
                "sku": "Estimated",
                "region": f"{regions[0]} + {regions[1]}",
                "monthlyCost": overhead,
                "pricingNote": "Estimated 30-50% uplift for multi-region deployment",
            })
            assumptions.append(
                "Multi-region overhead estimated at 40% of compute + storage costs"
            )

        total_monthly = round(sum(i["monthlyCost"] for i in items), 2)
        total_annual = round(total_monthly * 12, 2)

        if total_monthly > 100000:
            assumptions.append(
                "⚠️ Estimate exceeds $100K/month — recommend detailed pricing review with Azure team"
            )

        # Skew check: if one service is >90% of total cost, flag it
        if total_monthly > 0 and items:
            for item in items:
                pct = (item["monthlyCost"] / total_monthly) * 100
                if pct > 90:
                    assumptions.append(
                        f"⚠️ {item['serviceName']} ({item['sku']}) accounts for {pct:.0f}% of total cost — "
                        f"verify this is correct or consider alternative SKUs"
                    )

        # ── Populate both state fields ───────────────────────────────
        state.services = {"selections": selections}
        state.costs = {
            "estimate": {
                "currency": "USD",
                "items": items,
                "totalMonthly": total_monthly,
                "totalAnnual": total_annual,
                "assumptions": assumptions,
                "pricingSource": worst_source,
            }
        }
        return state

    # ── LLM Service Mapping ──────────────────────────────────────────

    def _llm_map_services(
        self,
        components: list[dict],
        users: int,
        primary_region: str,
        industry: str,
        state: AgentState,
    ) -> list[dict]:
        """Use LLM to map architecture components to Azure services + SKUs."""
        component_list = json.dumps(components, indent=2)

        prompt = f"""Map these architecture components to specific Azure services with appropriate SKUs.

COMPONENTS:
{component_list}

CONTEXT:
- Concurrent users: {users}
- Primary region: {primary_region}
- Industry: {industry}
- Use case: {state.user_input}
{f"- Additional context: {state.clarifications}" if state.clarifications else ""}

RULES:
- For each component, select the most appropriate Azure service and a specific SKU/tier
- Scale the SKU appropriately for {users} concurrent users
- Use real Azure SKU names (e.g., "B1", "S1", "P2v3" for App Service; "Standard S0" for Azure OpenAI)
- Include 3-5 key capabilities for each service
- For each service, write a short 'reason' explaining WHY this service fits THIS use case (1 sentence)
- If a component already has an azureService specified, validate and refine the SKU choice
- Always include Azure Monitor / Application Insights for observability
- Consider the industry ({industry}) for compliance needs (e.g., Premium SKUs for healthcare/finance)

Return ONLY valid JSON (no markdown fences) as an array:
[
    {{
        "componentName": "Name from the architecture",
        "serviceName": "Azure Service Name (exact official name)",
        "sku": "Specific SKU/tier",
        "reason": "Why this service fits: e.g. 'Handles PLM document indexing with vector search for engineering queries'",
        "capabilities": ["capability1", "capability2", "capability3"],
        "skuNote": null or "Reason for this SKU choice if notable"
    }}
]"""

        try:
            response = llm.invoke([
                {"role": "system", "content": (
                    "You are an Azure infrastructure specialist. "
                    "Map architecture components to specific Azure services with real, production-appropriate SKUs. "
                    "Use official Azure service names and SKU identifiers. Return ONLY valid JSON."
                )},
                {"role": "user", "content": prompt},
            ])

            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            selections = json.loads(text)
            if not isinstance(selections, list):
                raise ValueError("Expected JSON array")

        except Exception:
            logger.exception("LLM-based SKU mapping failed — using component pass-through")
            selections = [
                {
                    "componentName": c.get("name", "Unknown"),
                    "serviceName": c.get("azureService", c.get("name", "Unknown")),
                    "sku": "Standard",
                    "capabilities": ["Managed service", "High availability"],
                    "skuNote": "⚠️ LLM mapping failed — using default SKU",
                }
                for c in (self._last_components if hasattr(self, '_last_components') else [])
            ] if not selections else selections
            # Final fallback: pass through from components
            selections = [
                {
                    "componentName": c.get("name", "Unknown"),
                    "serviceName": c.get("azureService", c.get("name", "Unknown")),
                    "sku": "Standard",
                    "capabilities": ["Managed service", "High availability"],
                    "skuNote": "⚠️ LLM mapping failed — using default SKU",
                }
                for c in components
            ]

        # Add region to each selection
        for sel in selections:
            sel["region"] = sel.get("region", "eastus")

        return selections

    # ── Pricing + Cost Estimation ────────────────────────────────────

    def _price_selections(
        self, selections: list[dict], users: int,
    ) -> tuple[list[dict], str, list[str]]:
        """Query pricing API for each selection, compute monthly cost."""
        items: list[dict] = []
        assumptions = [
            "Based on 730 hours/month for hourly-priced services",
            "Pay-as-you-go pricing (no reservations or savings plans)",
        ]
        worst_source = "live"
        source_priority = {"live": 0, "live-fallback": 1, "approximate": 2}

        for sel in selections:
            service_name = sel.get("serviceName", "")
            sku = sel.get("sku", "")
            region = sel.get("region", "eastus")

            if service_name == "Multi-region overhead":
                continue

            result = query_azure_pricing_sync(service_name, sku, region)
            price = result["price"]
            source = result["source"]
            note = result.get("note")
            unit = result.get("unit", "1 Hour")

            # Attach validation warning to the selection if SKU wasn't live-confirmed
            if source not in ("live", "live-fallback"):
                existing_note = sel.get("skuNote") or ""
                warning = note or f"⚠️ Could not validate SKU for {service_name}"
                sel["skuNote"] = f"{existing_note}. {warning}".strip(". ") if existing_note else warning

            monthly = self._calculate_monthly(price, unit, service_name, users)
            monthly = self._apply_instance_count(monthly, sku)

            # Tag $0 items so downstream rendering explains the zero
            cost_note = note
            if monthly == 0:
                cost_note = "Usage-dependent — placeholder estimate (actual cost varies with consumption)"
                consumption = CONSUMPTION_ASSUMPTIONS.get(service_name)
                if consumption:
                    cost_note = f"Usage-dependent ({consumption}) — placeholder estimate"

            items.append({
                "serviceName": service_name,
                "sku": sku,
                "region": region,
                "monthlyCost": round(monthly, 2),
                "pricingNote": cost_note,
            })

            if source_priority.get(source, 2) > source_priority.get(worst_source, 0):
                worst_source = source

            consumption = CONSUMPTION_ASSUMPTIONS.get(service_name)
            if consumption:
                assumption_text = f"{service_name}: {consumption}"
                if assumption_text not in assumptions:
                    assumptions.append(assumption_text)

        return items, worst_source, assumptions

    # ── Helpers ──────────────────────────────────────────────────────

    def _calculate_monthly(
        self, unit_price: float, unit: str, service_name: str, users: int,
    ) -> float:
        """Convert unit price to monthly cost."""
        if unit_price <= 0:
            return 0.0

        unit_lower = unit.lower()

        if "hour" in unit_lower or service_name in HOURLY_SERVICES:
            instances = max(1, users // 500) if users > 500 else 1
            return unit_price * 730 * instances
        elif "month" in unit_lower:
            return unit_price
        elif "day" in unit_lower:
            return unit_price * 30
        elif "gb" in unit_lower:
            return unit_price * 100
        elif "10k" in unit_lower or "10,000" in unit_lower:
            return unit_price * 1
        else:
            return unit_price * 730

    def _apply_instance_count(self, monthly_cost: float, sku: str) -> float:
        """Multiply cost by instance count if SKU specifies nodes."""
        match = re.search(r"\((\d+)\s*nodes?\)", sku)
        if match:
            return monthly_cost * int(match.group(1))
        return monthly_cost
