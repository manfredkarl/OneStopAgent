"""Business Value Agent — analyses ROI and business impact (FRD-05 §2)."""
import json
from agents.llm import llm
from agents.state import AgentState


class BusinessValueAgent:
    name = "Business Value"
    emoji = "📊"

    def run(self, state: AgentState) -> AgentState:
        """Analyze ROI and business impact of the proposed Azure solution."""
        # Gather full context from state
        industry = state.brainstorming.get("industry", "Cross-Industry")
        customer = state.customer_name or "the customer"
        description = state.user_input
        clarifications = state.clarifications

        arch_narrative = state.architecture.get("narrative", "")
        components = state.architecture.get("components", [])
        component_names = [f"{c.get('name')} ({c.get('azureService', '')})" for c in components]

        services = state.services.get("selections", [])
        service_list = [f"{s.get('serviceName')} ({s.get('sku')})" for s in services]

        monthly_cost = state.costs.get("estimate", {}).get("totalMonthly", 0)

        prompt = f"""Analyze the business value of this Azure solution.

CUSTOMER: {customer}
INDUSTRY: {industry}
USE CASE: {description}
{f"ADDITIONAL CONTEXT: {clarifications}" if clarifications else ""}

ARCHITECTURE: {arch_narrative}
COMPONENTS: {', '.join(component_names[:10])}
AZURE SERVICES: {', '.join(service_list[:10])}
MONTHLY COST: ${monthly_cost:,.2f}

Generate 3-5 value drivers. RULES:
- Each driver MUST reference at least one specific Azure service from the architecture
- Each driver MUST reference a specific business metric from the {industry} industry
- Do NOT use generic drivers like "cloud saves money" — be specific to THIS solution
- For each driver, decide if the estimate can be converted to a dollar amount (monetizable=true) or is qualitative only (monetizable=false)
- The executive summary MUST mention {customer} by name and reference the top 2-3 value drivers

Return ONLY valid JSON (no markdown fences):
{{
    "drivers": [
        {{
            "name": "Driver name",
            "description": "1-2 sentences explaining HOW this Azure service delivers this value",
            "estimate": "Quantified estimate (e.g., '15-25% increase in conversion') or 'Qualitative — description'",
            "monetizable": true or false
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

            # Validate and set defaults per FRD-05 §2.4
            for driver in result.get("drivers", []):
                driver.setdefault("monetizable", True)
                driver.setdefault("description", "")
                driver.setdefault("estimate", "")

            state.business_value = result

        except Exception:
            # Fallback — generic but structured per §2.4 schema
            state.business_value = {
                "drivers": [
                    {"name": "Cloud Cost Optimization", "description": "Azure PaaS services reduce infrastructure management overhead.", "estimate": "Estimated 20-30% reduction in infrastructure costs", "monetizable": True},
                    {"name": "Scalability", "description": "Auto-scaling handles peak loads without over-provisioning.", "estimate": "Qualitative — elastic scaling on demand", "monetizable": False},
                    {"name": "Time to Market", "description": "Managed services accelerate development velocity.", "estimate": "Estimated 40% reduction in deployment time", "monetizable": True},
                ],
                "executiveSummary": f"The proposed Azure solution for {customer} offers significant operational and business value through cloud-native services.",
                "confidenceLevel": "conservative",
            }

        return state
