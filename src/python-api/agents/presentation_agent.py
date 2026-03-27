"""Presentation Agent — generates a PowerPoint deck from all agent outputs."""
from agents.state import AgentState
from services.presentation import create_pptx


class PresentationAgent:
    name = "Presentation"
    emoji = "📑"

    def run(self, state: AgentState) -> AgentState:
        """Generate a PowerPoint presentation compiling all solution outputs."""
        # Build the context dict that create_pptx expects
        context = {
            "customerName": state.customer_name or "Customer",
            "description": state.user_input,
            "architecture": state.architecture,
            "serviceSelections": state.services,
            "costEstimate": state.costs,
            "businessValue": {"assessment": state.business_value},
        }
        filepath = create_pptx(context)
        state.presentation_path = filepath
        return state
