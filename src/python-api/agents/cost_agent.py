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

    def generate_usage_assumptions(self, state: AgentState) -> list[dict]:
        """Generate usage-specific questions so cost estimates are grounded in real numbers."""
        components = state.architecture.get("components", [])
        industry = state.brainstorming.get("industry", "Cross-Industry")
        description = state.user_input

        comp_names = [c.get("name", c.get("azureService", "")) for c in components[:8]]

        try:
            response = llm.invoke([
                {"role": "system", "content": """Generate 3-5 usage assumption questions to accurately estimate Azure costs for this solution.
Return ONLY a JSON array. Each item:
{
    "id": "unique_key",
    "label": "Human-readable question",
    "unit": "count" or "GB" or "hours" or "requests" or "$",
    "default": numeric_default_value,
    "hint": "Brief explanation of how this affects cost"
}

Focus on CONSUMPTION metrics that drive Azure pricing:
- Number of users, requests, transactions, or documents processed
- Data volume (storage, ingestion, transfer)
- Compute hours or concurrent workloads
- API calls or model inference requests
Keep it to 3-5 questions max. Be specific to the architecture and use case."""},
                {"role": "user", "content": f"Industry: {industry}\nUse case: {description}\nArchitecture components: {', '.join(comp_names)}"}
            ])

            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            assumptions = json.loads(text)
            if isinstance(assumptions, list) and len(assumptions) > 0:
                return assumptions[:5]
        except Exception:
            pass

        # Fallback generic usage questions
        return [
            {"id": "concurrent_users", "label": "Expected concurrent users", "unit": "count", "default": 500, "hint": "Drives compute and scaling tier selection"},
            {"id": "requests_per_day", "label": "API requests per day", "unit": "count", "default": 10000, "hint": "Affects API Management, Functions, and App Service costs"},
            {"id": "data_storage_gb", "label": "Total data storage needed", "unit": "GB", "default": 100, "hint": "Drives storage, database, and backup costs"},
            {"id": "ai_calls_per_day", "label": "AI/ML inference calls per day", "unit": "count", "default": 5000, "hint": "Affects Azure OpenAI, Cognitive Services costs"},
        ]

    def run(self, state: AgentState) -> AgentState:
        """Two-phase cost estimation.

        Phase 1: Generate usage assumption questions for user input.
        Phase 2: Map architecture → Azure services + SKUs using real consumption numbers.
        """
        # Check if we have user-provided usage assumptions
        user_assumptions = state.costs.get("user_assumptions")

        if not user_assumptions:
            # Phase 1: Generate usage assumption questions
            assumptions = self.generate_usage_assumptions(state)
            state.costs = {
                "phase": "needs_input",
                "assumptions_needed": assumptions,
            }
            return state

        # Phase 2: Calculate with real usage numbers
        components = state.architecture.get("components", [])
        full_text = f"{state.user_input} {state.clarifications}"

        # Build usage context from user-provided values
        usage_dict = {a.get("id", ""): a.get("value", 0) for a in user_assumptions if a.get("id")}

        # Use shared assumptions as authoritative baseline
        sa = state.shared_assumptions
        if sa:
            if not usage_dict.get("concurrent_users") and sa.get("concurrent_users"):
                usage_dict["concurrent_users"] = sa["concurrent_users"]
            if not usage_dict.get("total_users") and sa.get("total_users"):
                usage_dict["total_users"] = sa["total_users"]
            if not usage_dict.get("data_storage_gb") and sa.get("data_volume_gb"):
                usage_dict["data_storage_gb"] = sa["data_volume_gb"]

        users = usage_dict.get("concurrent_users",
            sa.get("concurrent_users", sa.get("total_users", _extract_users(full_text))) if sa else _extract_users(full_text))
        regions = _extract_regions(full_text)
        primary_region = regions[0]
        industry = state.brainstorming.get("industry", "Cross-Industry")

        # ── Step 1: LLM maps components → Azure services + SKUs ──────
        selections = self._llm_map_services(components, users, primary_region, industry, state, usage_dict)

        # ── Step 2: Pricing API — validate SKUs + get prices ─────────
        items, worst_source, assumptions = self._price_selections(selections, users, usage_dict)

        # ── Step 3: Multi-region handling ────────────────────────────
        selections = _handle_multi_region(selections, regions)

        if len(regions) > 1:
            # Multi-region overhead: 40% accounts for data replication, cross-region networking,
            # and secondary region compute. Adjust via user assumptions for specific scenarios.
            overhead = sum(item.get("monthlyCost", 0) for item in items) * 0.4
            overhead = round(overhead, 2)
            items.append({
                "serviceName": "Multi-region replication overhead",
                "sku": "Estimated",
                "region": f"{regions[0]} + {regions[1]}",
                "monthlyCost": overhead,
                "pricingNote": "Estimated 30-50% uplift for multi-region deployment",
            })
            assumptions.append(
                "Multi-region overhead estimated at 40% (replication + networking + secondary compute)"
            )

        # Add user-provided usage context to assumptions
        for ua in user_assumptions:
            assumptions.append(f"{ua.get('label', 'Unknown')}: {ua.get('value', 0)} {ua.get('unit', '')}")

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
            },
            "user_assumptions": user_assumptions,
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
        usage: dict | None = None,
    ) -> list[dict]:
        """Use LLM to map architecture components to Azure services + SKUs."""
        component_list = json.dumps(components, indent=2)

        usage_context = ""
        if usage:
            usage_lines = [f"- {k.replace('_', ' ').title()}: {v}" for k, v in usage.items()]
            usage_context = "\nUSAGE ASSUMPTIONS (from user — use these for SKU sizing):\n" + "\n".join(usage_lines)

        prompt = f"""Map these architecture components to specific Azure services with appropriate SKUs.

COMPONENTS:
{component_list}

CONTEXT:
- Concurrent users: {users}
- Primary region: {primary_region}
- Industry: {industry}
- Use case: {state.user_input}
{f"- Additional context: {state.clarifications}" if state.clarifications else ""}
{usage_context}

RULES:
- For each component, select the most appropriate Azure service and a specific SKU/tier
- RIGHT-SIZE the SKU: use the SMALLEST tier that handles the workload
  - < 500 users: use Basic/Standard tiers (B1, S1)
  - 500-5000 users: use Standard tiers (S2, S3)
  - > 5000 users: consider Premium only if needed (P1v3, P2v3)
- Use real Azure SKU names (e.g., "B1", "S1", "P2v3" for App Service; "Standard S0" for Azure OpenAI)
- Include 3-5 key capabilities for each service
- For each service, write a short 'reason' explaining WHY this service fits THIS use case (1 sentence)
- Do NOT add Azure Monitor / Application Insights unless the user asked for observability
- Avoid Premium SKUs unless compliance or scale requires them

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
                    "Map architecture components to specific Azure services with COST-EFFICIENT, right-sized SKUs. "
                    "Prefer Standard/Basic tiers over Premium unless the use case demands it. "
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
                for c in components
            ]

        # Add region to each selection
        for sel in selections:
            sel["region"] = sel.get("region", "eastus")

        return selections

    # ── Pricing + Cost Estimation ────────────────────────────────────

    def _price_selections(
        self, selections: list[dict], users: int, usage_dict: dict | None = None,
    ) -> tuple[list[dict], str, list[str]]:
        """Query pricing API for each selection, compute monthly cost."""
        items: list[dict] = []
        assumptions = [
            "Based on 730 hours/month for hourly-priced services",
            "Pay-as-you-go pricing (no reservations or savings plans)",
        ]
        source_counts: dict[str, int] = {}
        source_priority = {"live": 0, "live-fallback": 1, "estimated": 2, "unavailable": 3}

        # TODO: Parallelize pricing lookups with concurrent.futures.ThreadPoolExecutor
        # Current: sequential calls, ~10s timeout each → 100s worst case for 10 services
        # Improvement: concurrent calls → ~10s worst case for 10 services
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

            monthly = self._calculate_monthly(price, unit, service_name, users, usage_dict)
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

            source_counts[source] = source_counts.get(source, 0) + 1

            consumption = CONSUMPTION_ASSUMPTIONS.get(service_name)
            if consumption:
                assumption_text = f"{service_name}: {consumption}"
                if assumption_text not in assumptions:
                    assumptions.append(assumption_text)

        # Build pricing source summary (e.g. "12 live, 3 estimated")
        label_order = ["live", "live-fallback", "estimated", "unavailable"]
        parts = [f"{source_counts[s]} {s}" for s in label_order if s in source_counts]
        pricing_source_label = ", ".join(parts) if parts else "unavailable"

        return items, pricing_source_label, assumptions

    # ── Helpers ──────────────────────────────────────────────────────

    def _calculate_monthly(
        self, unit_price: float, unit: str, service_name: str, users: int,
        usage_dict: dict | None = None,
    ) -> float:
        """Convert unit price to monthly cost.

        For per-request services (Azure OpenAI), multiplies by the user's
        monthly request volume from usage assumptions.
        """
        if unit_price <= 0:
            return 0.0

        unit_lower = unit.lower()

        # Per-request pricing (Azure OpenAI, AI Foundry)
        if "request" in unit_lower:
            # Find monthly request volume from user assumptions
            monthly_requests = 0
            if usage_dict:
                for key in ("monthly_copilot_agent_requests", "monthly_agent_requests",
                            "monthly_ai_requests", "monthly_requests"):
                    if key in usage_dict:
                        monthly_requests = int(usage_dict[key])
                        break
            if monthly_requests == 0:
                monthly_requests = 100_000  # default if not provided
            return unit_price * monthly_requests

        if "hour" in unit_lower or service_name in HOURLY_SERVICES:
            return unit_price * 730
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
