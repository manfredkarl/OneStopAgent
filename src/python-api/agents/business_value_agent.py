"""Business Value Agent — analyses ROI and business impact."""
import json
from agents.llm import llm
from agents.state import AgentState


class BusinessValueAgent:
    name = "Business Value"
    emoji = "📊"

    def run(self, state: AgentState) -> AgentState:
        """Analyze ROI and business impact of the proposed Azure solution."""
        est = state.costs.get("estimate", {})
        monthly_cost = est.get("totalMonthly", "N/A")

        prompt = f"""Analyze the business value of this Azure solution:

Customer: {state.customer_name or 'N/A'}
Use Case: {state.user_input}
Architecture Components: {json.dumps(state.architecture.get('components', []))}
Azure Services: {json.dumps(state.services.get('selections', []))}
Monthly Cost: ${monthly_cost}

Provide:
1. 3-5 specific value drivers relevant to THIS use case (not generic)
2. Quantified estimates where possible (e.g., "15-25% increase in conversion rates")
3. A 100-word executive summary mentioning the customer and their specific scenario
4. Confidence level (conservative/moderate/optimistic)

Return ONLY JSON:
{{"drivers": [{{"name": "...", "impact": "...", "quantifiedEstimate": "..."}}], "executiveSummary": "...", "confidenceLevel": "...", "disclaimer": "..."}}
"""

        try:
            response = llm.invoke([
                {"role": "system", "content": "You are an Azure business value analyst. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ])
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)
        except Exception:
            result = {
                "drivers": [
                    {
                        "name": "Cloud Migration Savings",
                        "impact": "Typical 20-40% cost reduction",
                        "quantifiedEstimate": "Estimated 30% savings",
                    }
                ],
                "executiveSummary": "The proposed Azure solution offers significant value for the customer.",
                "confidenceLevel": "moderate",
                "disclaimer": "These are estimates based on industry benchmarks.",
            }

        state.business_value = result
        return state
