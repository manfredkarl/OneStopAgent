"""Envisioning Agent — finds matching reference scenarios."""
from agents.state import AgentState
from data.knowledge_base import find_matching_scenarios


class EnvisioningAgent:
    name = "Envisioning"
    emoji = "💡"

    def run(self, state: AgentState) -> AgentState:
        """Find relevant Azure scenarios and reference architectures."""
        matches = find_matching_scenarios(state.user_input)
        state.envisioning = {"scenarios": matches}
        return state
