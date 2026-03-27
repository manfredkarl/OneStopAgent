"""Cost Specialist Agent — estimates Azure costs using the Retail Prices API."""
from agents.state import AgentState
from services.pricing import query_azure_pricing_sync


class CostAgent:
    name = "Cost Specialist"
    emoji = "💰"

    def run(self, state: AgentState) -> AgentState:
        """Estimate costs for all selected Azure services."""
        selections = state.services.get("selections", [])
        items: list[dict] = []
        total = 0.0

        for svc in selections:
            price = query_azure_pricing_sync(
                svc["serviceName"], svc["sku"], svc.get("region", "eastus")
            )
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

        state.costs = {
            "estimate": {
                "currency": "USD",
                "items": items,
                "totalMonthly": round(total, 2),
                "totalAnnual": round(total * 12, 2),
                "assumptions": [
                    "Based on 730 hours/month for hourly-priced services",
                    "Pay-as-you-go pricing",
                ],
                "pricingSource": "live",
            }
        }
        return state
