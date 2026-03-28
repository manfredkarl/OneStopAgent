"""Business Value Agent — analyses business impact and value drivers.

Runs BEFORE architecture to establish the business case first.
Uses user input, brainstorming output, and retrieved patterns as context.
If architecture/cost data is available (e.g., during iteration re-runs),
it incorporates that too.
"""
import json
from agents.llm import llm
from agents.state import AgentState


class BusinessValueAgent:
    name = "Business Value"
    emoji = "📊"

    def run(self, state: AgentState) -> AgentState:
        """Analyze business impact and value drivers for the proposed Azure solution."""
        industry = state.brainstorming.get("industry", "Cross-Industry")
        customer = state.customer_name or "the customer"
        description = state.user_input
        clarifications = state.clarifications

        # Build context from whatever is available
        context_parts = []

        # Retrieved patterns (from MCP / local KB) — may be populated by a prior architect run
        patterns = state.retrieved_patterns
        if patterns:
            pattern_info = [f"- {p.get('title', '')}: {p.get('summary', '')}" for p in patterns[:3]]
            context_parts.append(f"REFERENCE ARCHITECTURES:\n" + "\n".join(pattern_info))

        # Brainstorming scenarios
        scenarios = state.brainstorming.get("scenarios", [])
        if scenarios:
            scenario_info = [f"- {s.get('title', '')}: {s.get('description', '')}" for s in scenarios[:3]]
            context_parts.append(f"BRAINSTORMED SCENARIOS:\n" + "\n".join(scenario_info))

        # Architecture (available during iteration re-runs)
        arch_narrative = state.architecture.get("narrative", "")
        components = state.architecture.get("components", [])
        if arch_narrative:
            component_names = [f"{c.get('name')} ({c.get('azureService', '')})" for c in components]
            context_parts.append(f"ARCHITECTURE: {arch_narrative}")
            context_parts.append(f"COMPONENTS: {', '.join(component_names[:10])}")

        # Services + cost (available during iteration re-runs)
        services = state.services.get("selections", [])
        if services:
            service_list = [f"{s.get('serviceName')} ({s.get('sku')})" for s in services]
            context_parts.append(f"AZURE SERVICES: {', '.join(service_list[:10])}")

        monthly_cost = state.costs.get("estimate", {}).get("totalMonthly", 0)
        if monthly_cost > 0:
            context_parts.append(f"MONTHLY COST: ${monthly_cost:,.2f}")

        extra_context = "\n".join(context_parts)

        prompt = f"""Analyze the business value of this Azure solution.

CUSTOMER: {customer}
INDUSTRY: {industry}
USE CASE: {description}
{f"ADDITIONAL CONTEXT: {clarifications}" if clarifications else ""}
{extra_context}

Generate 3-5 value drivers. RULES:
- Each driver MUST be specific to the {industry} industry and this use case
- Each driver MUST reference specific Azure capabilities or services
- Do NOT use generic drivers like "cloud saves money" — be specific to THIS solution
- For each driver, decide if the value can be expressed as an annual dollar amount
- If monetizable: set annual_value_estimate to your best conservative annual dollar estimate (a number, not a string)
- If NOT monetizable (qualitative only): set annual_value_estimate to null
- Do NOT invent revenue or salary figures you don't know — if you can't estimate a dollar value without knowing the customer's revenue, headcount, or other specifics, set annual_value_estimate to null and list what info you'd need in "info_needed"
- The executive summary MUST mention {customer} by name and reference the top 2-3 value drivers

Return ONLY valid JSON (no markdown fences):
{{
    "drivers": [
        {{
            "name": "Driver name",
            "description": "1-2 sentences explaining HOW Azure delivers this value",
            "estimate": "Human-readable estimate (e.g., '15-25% reduction in deployment time')",
            "annual_value_estimate": 50000 or null,
            "info_needed": null or "What info would be needed to monetize this (e.g., 'current annual infrastructure spend')?"
        }}
    ],
    "executiveSummary": "100-200 word summary mentioning {customer} and {industry}",
    "confidenceLevel": "conservative" | "moderate" | "optimistic"
}}"""

        try:
            response = llm.invoke([
                {"role": "system", "content": "You are an Azure business value analyst. Return ONLY valid JSON. Be specific to the customer's industry and use case — no generic cloud benefits."},
                {"role": "user", "content": prompt},
            ])

            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(text)

            # Validate and set defaults
            for driver in result.get("drivers", []):
                driver.setdefault("description", "")
                driver.setdefault("estimate", "")
                driver.setdefault("annual_value_estimate", None)
                driver.setdefault("info_needed", None)

            state.business_value = result

        except Exception:
            # Fallback — generic but structured per §2.4 schema
            state.business_value = {
                "drivers": [
                    {"name": "Cloud Cost Optimization", "description": "Azure PaaS services reduce infrastructure management overhead.", "estimate": "Estimated 20-30% reduction in infrastructure costs", "annual_value_estimate": None, "info_needed": "Current annual infrastructure spend"},
                    {"name": "Scalability", "description": "Auto-scaling handles peak loads without over-provisioning.", "estimate": "Elastic scaling on demand", "annual_value_estimate": None, "info_needed": None},
                    {"name": "Time to Market", "description": "Managed services accelerate development velocity.", "estimate": "Estimated 40% reduction in deployment time", "annual_value_estimate": None, "info_needed": "Current average deployment cycle time and developer team size"},
                ],
                "executiveSummary": f"The proposed Azure solution for {customer} offers significant operational and business value through cloud-native services.",
                "confidenceLevel": "conservative",
            }

        return state
