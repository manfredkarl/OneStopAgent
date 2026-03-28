"""Brainstorming Agent — explores Azure scenarios and classifies Azure fit."""
import json
from agents.llm import llm
from agents.state import AgentState


class BrainstormingAgent:
    name = "Brainstorming"
    emoji = "💡"

    def run(self, state: AgentState) -> AgentState:
        """Suggest Azure scenarios and classify Azure fit."""
        context = state.to_context_string()

        try:
            response = llm.invoke([
                {"role": "system", "content": BRAINSTORM_PROMPT},
                {"role": "user", "content": context}
            ])

            # Parse JSON response
            text = response.content.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(text)

            state.brainstorming = result
            state.azure_fit = result.get("azure_fit", "unclear")
            state.azure_fit_explanation = result.get("azure_fit_explanation", "")

        except (json.JSONDecodeError, Exception) as e:
            # Fallback: classify as unclear and let PM ask more questions
            state.brainstorming = {
                "scenarios": [],
                "recommended": "",
                "azure_fit": "unclear",
                "azure_fit_explanation": f"Could not analyze Azure fit: {str(e)}",
                "industry": "Cross-Industry"
            }
            state.azure_fit = "unclear"
            state.azure_fit_explanation = "Analysis could not be completed — please provide more details."

        return state


BRAINSTORM_PROMPT = """\
You are an Azure solutions expert helping Microsoft sellers identify Azure opportunities.

Given the user's description, analyze it and respond with ONLY a JSON object (no markdown fences):

{
    "scenarios": [
        {
            "title": "Scenario name",
            "description": "2-3 sentence description of the scenario",
            "azure_services": ["Azure App Service", "Azure SQL Database", "..."],
            "industry": "Retail",
            "azure_fit_reason": "Why Azure is a good fit for this specific scenario"
        }
    ],
    "recommended": "Title of the most relevant scenario",
    "azure_fit": "strong" or "weak" or "unclear",
    "azure_fit_explanation": "1-2 sentences explaining WHY Azure is or isn't a good fit for this customer need",
    "industry": "The customer's industry (Retail, Healthcare, Financial Services, Manufacturing, or Cross-Industry)"
}

RULES:
- Generate 2-4 realistic Azure scenarios
- "strong" = clear workload mapping to Azure services (e.g., web app, data platform, AI/ML)
- "weak" = generic IT need without clear Azure advantage
- "unclear" = not enough information
- Each scenario must explain WHY Azure specifically (not just cloud in general)
- azure_fit_explanation must reference specific Azure capabilities
- Be specific about Azure services, not generic
"""
