"""Cost Specialist Agent — estimates Azure costs using Retail Prices API.

Implements FRD-04 §2: 5-tier pricing, consumption assumptions,
instance scaling, multi-region overhead, and source tracking.
"""
import re
from agents.state import AgentState
from services.pricing import query_azure_pricing_sync

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


class CostAgent:
    name = "Cost Specialist"
    emoji = "💰"

    def run(self, state: AgentState) -> AgentState:
        """Estimate costs for all selected Azure services."""
        selections = state.services.get("selections", [])
        users = self._extract_users(state.user_input)

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

            # Skip overhead line items — handled separately below
            if service_name == "Multi-region overhead":
                continue

            # Query pricing (returns rich dict with source info)
            result = query_azure_pricing_sync(service_name, sku, region)
            price = result["price"]
            source = result["source"]
            note = result.get("note")
            unit = result.get("unit", "1 Hour")

            # Convert unit price → monthly cost
            monthly = self._calculate_monthly(price, unit, service_name, users)

            # Instance scaling from SKU (e.g. "Standard_D4s_v3 (3 nodes)")
            monthly = self._apply_instance_count(monthly, sku)

            items.append({
                "serviceName": service_name,
                "sku": sku,
                "region": region,
                "monthlyCost": round(monthly, 2),
                "pricingNote": note,
            })

            # Track worst (least reliable) source across all items
            if source_priority.get(source, 2) > source_priority.get(worst_source, 0):
                worst_source = source

            # Add consumption assumption if applicable
            consumption = CONSUMPTION_ASSUMPTIONS.get(service_name)
            if consumption:
                assumption_text = f"{service_name}: {consumption}"
                if assumption_text not in assumptions:
                    assumptions.append(assumption_text)

        # Handle multi-region overhead (40% uplift estimate)
        multi_region = next(
            (s for s in selections if s.get("serviceName") == "Multi-region overhead"),
            None,
        )
        if multi_region:
            compute_storage_total = sum(i["monthlyCost"] for i in items)
            overhead = round(compute_storage_total * 0.4, 2)
            items.append({
                "serviceName": "Multi-region replication overhead",
                "sku": "Estimated",
                "region": multi_region.get("region", "multi"),
                "monthlyCost": overhead,
                "pricingNote": "Estimated 30-50% uplift for multi-region deployment",
            })
            assumptions.append(
                "Multi-region overhead estimated at 40% of compute + storage costs"
            )

        total_monthly = round(sum(i["monthlyCost"] for i in items), 2)
        total_annual = round(total_monthly * 12, 2)

        # Warning for very large estimates
        if total_monthly > 100000:
            assumptions.append(
                "⚠️ Estimate exceeds $100K/month — recommend detailed pricing review with Azure team"
            )

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

    # ── Helpers ───────────────────────────────────────────────────────

    def _calculate_monthly(
        self, unit_price: float, unit: str, service_name: str, users: int
    ) -> float:
        """Convert unit price to monthly cost (FRD-04 §2.6)."""
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
            return unit_price * 100  # default 100 GB assumption
        elif "10k" in unit_lower or "10,000" in unit_lower:
            return unit_price * 1  # 10K operations assumption
        else:
            return unit_price * 730  # default to hourly

    def _apply_instance_count(self, monthly_cost: float, sku: str) -> float:
        """Multiply cost by instance count if SKU specifies nodes (FRD-04 §2.6)."""
        match = re.search(r"\((\d+)\s*nodes?\)", sku)
        if match:
            return monthly_cost * int(match.group(1))
        return monthly_cost

    def _extract_users(self, text: str) -> int:
        """Extract user count from input text for scaling heuristics."""
        match = re.search(
            r"(\d[\d,]*)\s*(?:concurrent|simultaneous)?\s*users", text, re.I
        )
        if match:
            return int(match.group(1).replace(",", ""))
        return 1000
