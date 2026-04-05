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
from threading import Lock

from agents.llm import llm
from agents.state import AgentState
from agents.assumption_catalog import filter_already_answered
from services.pricing import query_azure_pricing_sync

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

CONSUMPTION_ASSUMPTIONS = {
    "Azure Functions": "1M executions/month, 400K GB-s",
    "Azure Blob Storage": "500 GB stored, 50K read operations/month",
    "Azure Cosmos DB": "5,000 RU/s provisioned, 100 GB stored",
    "Azure Event Hubs": "5M events/month",
    "Azure OpenAI": "150K requests/month",
    "Azure AI Search": "2 search units",
    "Azure Monitor": "10 GB logs ingested/month",
}

HOURLY_SERVICES = {
    "Azure App Service",
    "Azure Cache for Redis",
    "Azure Container Apps",
    "Azure Kubernetes Service",
}

# ── QW-1: Tiered consumption defaults by user count ──────────────────
# Small: <500 users | Medium: 500-5000 | Large: >5000
TIERED_CONSUMPTION: dict[str, dict[str, object]] = {
    "storage_gb": {"small": 100, "medium": 500, "large": 2048},
    "openai_requests_monthly": {"small": 50_000, "medium": 150_000, "large": 500_000},
    "cosmos_ru_s": {"small": 1_000, "medium": 5_000, "large": 20_000},
    "app_instances": {"small": 1, "medium": 2, "large": 3},
}


def _tier_for_users(users: int) -> str:
    """Return consumption tier based on user count."""
    if users < 500:
        return "small"
    elif users <= 5000:
        return "medium"
    else:
        return "large"


def _tiered_default(key: str, users: int) -> int:
    """Return the tiered default value for a consumption metric."""
    tier = _tier_for_users(users)
    return int(TIERED_CONSUMPTION.get(key, {}).get(tier, 0))


# ── QI-3: Per-service HA cost multipliers ────────────────────────────
HA_COST_MULTIPLIERS: dict[str, dict[str, float]] = {
    "Azure App Service": {"active-active": 2.0, "active-passive": 1.5, "default": 1.5},
    "Azure Container Apps": {"active-active": 2.0, "active-passive": 1.5, "default": 1.5},
    "Azure Kubernetes Service": {"active-active": 2.0, "active-passive": 1.5, "default": 1.5},
    "Azure Cosmos DB": {"active-active": 0.75, "active-passive": 0.50, "default": 0.50},
    "Azure Cosmos DB for NoSQL": {"active-active": 0.75, "active-passive": 0.50, "default": 0.50},
    "Azure Blob Storage": {"geo-redundant": 1.20, "active-active": 1.20, "default": 1.20},
    "Azure Service Bus": {"active-active": 1.0, "active-passive": 1.0, "default": 1.0},
    "Azure Event Hubs": {"active-active": 1.0, "active-passive": 1.0, "default": 1.0},
    "default": {"active-active": 0.50, "active-passive": 0.30, "default": 0.40},
}

# ── Multi-region overhead by HA pattern (FRD-006 Fix M) ──────────────
MULTI_REGION_OVERHEAD: dict[str, float] = {
    "active-active": 0.50,
    "active-passive": 0.30,
    "default": 0.40,
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

def _ha_multiplier_for_service(service_name: str, ha_pattern: str) -> float:
    """Return the HA cost multiplier for a service and HA pattern (QI-3)."""
    svc_rules = HA_COST_MULTIPLIERS.get(service_name, HA_COST_MULTIPLIERS["default"])
    return svc_rules.get(ha_pattern, svc_rules.get("default", 0.40))


def _handle_multi_region(selections: list[dict], regions: list[str], ha_pattern: str = "default") -> list[dict]:
    """If multiple regions, add HA/DR note + overhead line item.

    Uses per-service HA cost multipliers (QI-3) instead of a flat percentage.
    """
    if len(regions) <= 1:
        return selections

    primary = regions[0]
    secondary = regions[1]

    for sel in selections:
        sel["region"] = primary
        existing_note = sel.get("skuNote", "") or ""
        svc = sel.get("serviceName", "")
        mult = _ha_multiplier_for_service(svc, ha_pattern)
        ha_note = f"For HA, deploy secondary in {secondary} ({mult:.0%} overhead)"
        sel["skuNote"] = f"{existing_note}. {ha_note}".strip(". ") if existing_note else ha_note

    selections.append({
        "componentName": "Multi-Region Replication",
        "serviceName": "Multi-region overhead",
        "sku": "N/A",
        "region": f"{primary} + {secondary}",
        "capabilities": ["High availability", "Disaster recovery", "Geo-redundancy"],
        "skuNote": "Per-service HA overhead (see individual service notes)",
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
                return filter_already_answered(assumptions[:5], state)
        except Exception:
            pass

        # Fallback generic usage questions
        fallback = [
            {"id": "concurrent_users", "label": "Expected concurrent users", "unit": "count", "default": 500, "hint": "Drives compute and scaling tier selection"},
            {"id": "requests_per_day", "label": "API requests per day", "unit": "count", "default": 10000, "hint": "Affects API Management, Functions, and App Service costs"},
            {"id": "data_storage_gb", "label": "Total data storage needed", "unit": "GB", "default": 100, "hint": "Drives storage, database, and backup costs"},
            {"id": "ai_calls_per_day", "label": "AI/ML inference calls per day", "unit": "count", "default": 5000, "hint": "Affects Azure OpenAI, Cognitive Services costs"},
        ]
        return filter_already_answered(fallback, state)

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
        typed = state.sa
        if typed.concurrent_users and not usage_dict.get("concurrent_users"):
            usage_dict["concurrent_users"] = typed.concurrent_users
        if typed.total_users and not usage_dict.get("total_users"):
            usage_dict["total_users"] = typed.total_users
        if typed.data_volume_gb and not usage_dict.get("data_storage_gb"):
            usage_dict["data_storage_gb"] = typed.data_volume_gb

        users = usage_dict.get("concurrent_users",
            typed.concurrent_users or typed.total_users or _extract_users(full_text))
        regions = _extract_regions(full_text)
        primary_region = regions[0]
        industry = state.brainstorming.get("industry", "Cross-Industry")

        # ── Step 1: LLM maps components → Azure services + SKUs ──────
        self._last_mapping_fallback = False
        selections = self._llm_map_services(components, users, primary_region, industry, state, usage_dict)

        # ── Step 2: Pricing API — validate SKUs + get prices ─────────
        items, worst_source, assumptions = self._price_selections(selections, users, usage_dict)

        # ── Step 3: Multi-region handling ────────────────────────────
        # Extract HA pattern from user text
        ha_pattern = "default"
        text_lower = full_text.lower()
        if "active-active" in text_lower or "active/active" in text_lower:
            ha_pattern = "active-active"
        elif "active-passive" in text_lower or "active/passive" in text_lower:
            ha_pattern = "active-passive"

        selections = _handle_multi_region(selections, regions, ha_pattern)

        if len(regions) > 1:
            # Per-service HA overhead (QI-3): for each service, compute the
            # additional cost of the HA/DR replica = base_cost × (multiplier - 1)
            # For services with multiplier < 1 (e.g. Cosmos geo-redundancy is cheaper
            # per-region), the overhead is negative — meaning it reduces effective cost.
            # We only add a positive overhead line item when there's a net increase.
            total_incremental = 0.0
            for item in items:
                svc = item.get("serviceName", "")
                mult = _ha_multiplier_for_service(svc, ha_pattern)
                # incremental = base_cost × (mult - 1)
                # e.g. App Service with mult=2.0 → add 100% more; Cosmos with mult=0.75 → subtract 25%
                total_incremental += item.get("monthlyCost", 0) * (mult - 1)
            overhead = round(max(total_incremental, 0.0), 2)
            items.append({
                "serviceName": "Multi-region replication overhead",
                "sku": "Estimated",
                "region": f"{regions[0]} + {regions[1]}",
                "monthlyCost": overhead,
                "pricingNote": f"Per-service HA overhead for {ha_pattern} deployment",
            })
            assumptions.append(
                f"Multi-region overhead estimated using per-service HA multipliers "
                f"({ha_pattern} pattern: see HA_COST_MULTIPLIERS)"
            )

        # Add user-provided usage context to assumptions
        for ua in user_assumptions:
            assumptions.append(f"{ua.get('label', 'Unknown')}: {ua.get('value', 0)} {ua.get('unit', '')}")

        # ── Infrastructure overhead: networking, egress, CI/CD, backup ──
        subtotal = sum(i["monthlyCost"] for i in items)
        infra_pct = 0.15  # 15% overhead for unlisted infrastructure
        infra_overhead = round(subtotal * infra_pct, 2)
        if infra_overhead > 0:
            items.append({
                "serviceName": "Infrastructure overhead",
                "sku": "Estimated 15%",
                "region": regions[0] if regions else "eastus",
                "monthlyCost": infra_overhead,
                "pricingNote": (
                    "Covers networking (VNet, private endpoints, egress), "
                    "CI/CD pipelines, backup/DR, monitoring alerts, and "
                    "other shared infrastructure not individually listed."
                ),
            })
            assumptions.append(
                "15% infrastructure overhead added for networking, egress, "
                "CI/CD, backup, and shared platform services"
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
                pct = (item["monthlyCost"] / total_monthly) * 100 if total_monthly > 0 else 0
                if pct > 90:
                    assumptions.append(
                        f"⚠️ {item['serviceName']} ({item['sku']}) accounts for {pct:.0f}% of total cost — "
                        f"verify this is correct or consider alternative SKUs"
                    )

        # ── Populate both state fields ───────────────────────────────
        state.services = {"selections": selections}

        # ── UX-2: Cost optimization insights ────────────────────────
        insights = self._build_cost_insights(items, total_monthly, total_annual, users)

        state.costs = {
            "estimate": {
                "currency": "USD",
                "items": items,
                "totalMonthly": total_monthly,
                "totalAnnual": total_annual,
                "assumptions": assumptions,
                "pricingSource": worst_source,
                "insights": insights,
            },
            "user_assumptions": user_assumptions,
        }

        # Flag fallback usage for downstream detection (FRD-008)
        if self._last_mapping_fallback:
            state.costs["_used_fallback"] = True

        # ── Plausibility check vs current baseline (FRD-004 Fix G) ───
        current_spend = state.sa.current_annual_spend
        if current_spend and current_spend > 0 and total_annual > 0:
            ratio = total_annual / current_spend
            if ratio > 2.0:
                assumptions.append(
                    f"\u26a0\ufe0f Azure estimate (${total_annual:,.0f}/yr) exceeds current spend "
                    f"(${current_spend:,.0f}/yr) by {ratio:.1f}\u00d7. Verify sizing."
                )
            elif ratio < 0.03:
                assumptions.append(
                    f"\u2139\ufe0f Azure estimate (${total_annual:,.0f}/yr) is {ratio * 100:.1f}% of "
                    f"current spend (${current_spend:,.0f}/yr). Confirm scope replacement."
                )

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
- RIGHT-SIZE the SKU for the stated workload — not the cheapest, but production-appropriate:
  - < 500 users: Standard tiers are appropriate (S1, S2)
  - 500-5000 users: Standard or Premium tiers (S2, S3, P1v3)
  - > 5000 users: Premium tiers (P1v3, P2v3) or dedicated instances
- Pick SKUs that a production workload would actually use — avoid dev/test tiers (B1, F1, Free)
- Use real Azure SKU names (e.g., "S1", "P1v3" for App Service; "Standard S0" for Azure OpenAI)
- Include 3-5 key capabilities for each service
- For each service, write a short 'reason' explaining WHY this service fits THIS use case (1 sentence)
- Do NOT add Azure Monitor / Application Insights unless the user asked for observability

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
                    "Map architecture components to specific Azure services with PRODUCTION-APPROPRIATE SKUs. "
                    "Avoid dev/test tiers (B1, Free, F1) — pick what an enterprise would actually deploy. "
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

        except json.JSONDecodeError as e:
            logger.error("LLM returned invalid JSON for SKU mapping: %s", e, exc_info=True)
            self._last_mapping_fallback = True
            selections = [
                {
                    "componentName": c.get("name", "Unknown"),
                    "serviceName": c.get("azureService", c.get("name", "Unknown")),
                    "sku": "Standard",
                    "capabilities": ["Managed service", "High availability"],
                    "skuNote": "\u26a0\ufe0f LLM returned invalid JSON \u2014 using default SKU",
                }
                for c in components
            ]

        except Exception as e:
            logger.error("LLM-based SKU mapping failed: %s", e, exc_info=True)
            self._last_mapping_fallback = True
            selections = [
                {
                    "componentName": c.get("name", "Unknown"),
                    "serviceName": c.get("azureService", c.get("name", "Unknown")),
                    "sku": "Standard",
                    "capabilities": ["Managed service", "High availability"],
                    "skuNote": "\u26a0\ufe0f LLM mapping failed \u2014 using default SKU",
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
        """Query pricing API for each selection, compute monthly cost.

        Uses parallel pricing with session cache (FRD-006 Fix K).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        items: list[dict] = []
        assumptions = [
            "Based on 730 hours/month for hourly-priced services",
            "Pay-as-you-go pricing (no reservations or savings plans)",
        ]
        source_counts: dict[str, int] = {}
        price_cache: dict[tuple, dict] = {}
        cache_lock = Lock()

        def _price_one(sel: dict) -> tuple[dict, dict] | None:
            service_name = sel.get("serviceName", "")
            sku = sel.get("sku", "")
            region = sel.get("region", "eastus")
            if service_name == "Multi-region overhead":
                return None
            cache_key = (service_name, sku, region)
            with cache_lock:
                if cache_key in price_cache:
                    return (sel, price_cache[cache_key])
            result = query_azure_pricing_sync(service_name, sku, region)
            with cache_lock:
                price_cache[cache_key] = result
            return (sel, result)

        # Parallel pricing with max 5 concurrent API calls
        results_list: list[tuple[dict, dict]] = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_price_one, sel): sel for sel in selections}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        results_list.append(result)
                except Exception as e:
                    sel = futures[future]
                    logger.warning("Pricing failed for %s: %s", sel.get("serviceName"), e)

        # Process results (maintain original ordering)
        sel_order = {id(sel): idx for idx, sel in enumerate(selections)}
        results_list.sort(key=lambda r: sel_order.get(id(r[0]), 0))

        for sel, result in results_list:
            service_name = sel.get("serviceName", "")
            sku = sel.get("sku", "")
            region = sel.get("region", "eastus")
            price = result["price"]
            source = result["source"]
            note = result.get("note")
            unit = result.get("unit", "1 Hour")

            if source not in ("live", "live-fallback"):
                existing_note = sel.get("skuNote") or ""
                warning = note or f"\u26a0\ufe0f Could not validate SKU for {service_name}"
                sel["skuNote"] = f"{existing_note}. {warning}".strip(". ") if existing_note else warning

            monthly = self._calculate_monthly(price, unit, service_name, users, usage_dict)
            monthly = self._apply_instance_count(monthly, sku)

            # Sanity cap: no single service should exceed $30K/mo in an estimate
            # (prevents LLM-generated absurd instance counts from propagating)
            MAX_SERVICE_MONTHLY = 30_000
            if monthly > MAX_SERVICE_MONTHLY:
                logger.warning(
                    "Cost cap: %s at $%.0f/mo exceeds $%d cap, clamping",
                    service_name, monthly, MAX_SERVICE_MONTHLY,
                )
                monthly = MAX_SERVICE_MONTHLY

            cost_note = note
            if monthly == 0:
                cost_note = "Usage-dependent \u2014 placeholder estimate (actual cost varies with consumption)"
                consumption = CONSUMPTION_ASSUMPTIONS.get(service_name)
                if consumption:
                    cost_note = f"Usage-dependent ({consumption}) \u2014 placeholder estimate"

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
            # Find monthly request volume from user assumptions (usage_dict
            # already includes shared_assumptions merged upstream)
            monthly_requests = 0
            if usage_dict:
                for key in ("monthly_copilot_agent_requests", "monthly_agent_requests",
                            "monthly_ai_requests", "monthly_requests",
                            "daily_agent_and_model_requests", "daily_requests"):
                    if usage_dict.get(key):
                        val = int(usage_dict[key])
                        # Convert daily to monthly if needed
                        if "daily" in key:
                            val = val * 30
                        monthly_requests = val
                        break
            if monthly_requests == 0:
                # QW-1: tiered default for OpenAI requests based on user count
                monthly_requests = _tiered_default("openai_requests_monthly", users)
                if monthly_requests == 0:
                    monthly_requests = 50_000  # absolute fallback
            return unit_price * monthly_requests

        if "hour" in unit_lower or service_name in HOURLY_SERVICES:
            monthly = unit_price * 730
            # Sanity: if hourly conversion gives >$20K, price is likely
            # already monthly or per-unit (API misclassification)
            if monthly > 20_000 and unit_price > 25:
                logger.warning(
                    "Hourly price $%.2f for %s seems too high — treating as monthly",
                    unit_price, service_name,
                )
                return unit_price
            return monthly
        elif "month" in unit_lower:
            return unit_price
        elif "day" in unit_lower:
            return unit_price * 30
        elif "gb" in unit_lower:
            # QW-1: tiered GB default based on user count
            gb_volume = _tiered_default("storage_gb", users) or 100
            if usage_dict:
                for key in ("data_storage_gb", "data_volume_gb", "engineering_data_volume_gb", "engineering_data_lake_volume_gb"):
                    if usage_dict.get(key):
                        gb_volume = int(usage_dict[key])
                        break
            return unit_price * gb_volume
        elif "minute" in unit_lower:
            monthly_minutes = 0
            if usage_dict:
                for key in ("monthly_voice_chat_minutes", "monthly_chat_voice_hours",
                             "voice_chat_minutes", "monthly_minutes",
                             "monthly_voice_chat_hours", "chat_voice_hours"):
                    if usage_dict.get(key):
                        val = float(usage_dict[key])
                        if "hour" in key:
                            val = val * 60  # convert hours to minutes
                        monthly_minutes = val
                        break
            if monthly_minutes == 0:
                monthly_minutes = 100_000  # sensible default: 100K minutes/mo
                logger.info("No voice/chat minutes in usage_dict, using default %d", monthly_minutes)
            return unit_price * monthly_minutes
        elif "10k" in unit_lower or "10,000" in unit_lower:
            return unit_price * 1
        elif any(kw in unit_lower for kw in ("transaction", "message", "event", "operation")):
            volume = 100_000  # default: 100K/month
            if usage_dict:
                for key in ("monthly_transactions", "monthly_messages", "monthly_events",
                             "monthly_operations", "requests_per_day"):
                    if usage_dict.get(key):
                        val = float(usage_dict[key])
                        if "day" in key:
                            val = val * 30
                        volume = val
                        break
            return unit_price * volume
        else:
            # Unknown unit: treat as monthly (safer than hourly × 730)
            logger.warning("Unknown pricing unit '%s' for %s — treating as monthly", unit, service_name)
            return unit_price

    def _apply_instance_count(self, monthly_cost: float, sku: str) -> float:
        """Multiply cost by instance count if SKU specifies nodes."""
        match = re.search(r"\((\d+)\s*nodes?\)", sku)
        if match:
            return monthly_cost * int(match.group(1))
        return monthly_cost

    def _build_cost_insights(
        self, items: list[dict], total_monthly: float, total_annual: float, users: int
    ) -> dict:
        """UX-2: Build cost optimization insights for seller conversations."""
        if not items or total_monthly <= 0:
            return {}

        # Top 3 cost drivers
        sorted_items = sorted(items, key=lambda x: x.get("monthlyCost", 0), reverse=True)
        top3 = [
            {
                "service": i.get("serviceName", ""),
                "sku": i.get("sku", ""),
                "monthly": round(i.get("monthlyCost", 0)),
                "pct": round(i.get("monthlyCost", 0) / total_monthly * 100) if total_monthly > 0 else 0,
            }
            for i in sorted_items[:3]
        ]

        # Reservation savings estimate (1-year reserved is ~30-40% cheaper for compute)
        compute_monthly = sum(
            i.get("monthlyCost", 0) for i in items
            if any(kw in i.get("serviceName", "").lower()
                   for kw in ("app service", "virtual machine", "kubernetes", "container apps"))
        )
        reservation_savings_annual = round(compute_monthly * 12 * 0.35) if compute_monthly > 0 else 0

        # Cost per user per month
        cost_per_user = round(total_monthly / users, 2) if users > 0 else None

        # Optimization tips
        tips = []
        for item in sorted_items[:3]:
            svc = item.get("serviceName", "")
            if "openai" in svc.lower() or "ai" in svc.lower():
                tips.append("Consider prompt caching and batching to reduce Azure OpenAI token consumption")
            elif "cosmos" in svc.lower():
                tips.append("Use Cosmos DB serverless for dev/test; switch to provisioned RU for production")
            elif "kubernetes" in svc.lower() or "aks" in svc.lower():
                tips.append("Use AKS spot node pools for batch/non-critical workloads (60-90% savings)")
            elif "app service" in svc.lower():
                tips.append("Use App Service reserved instances (1-yr) for ~35% cost reduction")

        return {
            "top3Drivers": top3,
            "reservationSavingsAnnual": reservation_savings_annual,
            "reservationNote": f"~${reservation_savings_annual:,}/yr savings with 1-yr reserved pricing on compute" if reservation_savings_annual > 0 else None,
            "costPerUserMonthly": cost_per_user,
            "optimizationTips": list(dict.fromkeys(tips))[:3],  # deduplicate, max 3
        }
