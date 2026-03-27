"""Project Manager — plans and orchestrates the agent pipeline."""
import json
from agents.llm import llm
from agents.state import AgentState

AGENT_INFO = {
    "envisioning": {"name": "Envisioning", "emoji": "💡"},
    "architect": {"name": "System Architect", "emoji": "🏗️"},
    "azure_services": {"name": "Azure Specialist", "emoji": "☁️"},
    "cost": {"name": "Cost Specialist", "emoji": "💰"},
    "business_value": {"name": "Business Value", "emoji": "📊"},
    "presentation": {"name": "Presentation", "emoji": "📑"},
}

DEFAULT_PLAN = ["architect", "azure_services", "cost", "business_value", "presentation"]


class ProjectManager:
    def ask_clarifications(self, user_input: str) -> str:
        """Generate 2-3 clarifying questions + execution plan."""
        response = llm.invoke([
            {"role": "system", "content": """You are an Azure solution project manager. The user described a project.
Respond with:
1. A brief acknowledgment (1 sentence)
2. 2-3 clarifying questions as a numbered list
3. An execution plan showing which agents will run

Format your response in markdown. End with: "Ready when you are — just say **proceed** or answer the questions above."
"""},
            {"role": "user", "content": user_input}
        ])
        return response.content

    def build_plan(self, active_agents: list[str]) -> list[str]:
        """Build execution plan respecting agent toggles. Architect is always included."""
        # Map internal plan names to active_agents format
        PLAN_TO_ACTIVE = {
            "architect": "architect",
            "azure_services": "azure-specialist",
            "cost": "cost",
            "business_value": "business-value",
            "presentation": "presentation",
            "envisioning": "envisioning",
        }
        plan = []
        for agent_id in DEFAULT_PLAN:
            mapped = PLAN_TO_ACTIVE.get(agent_id, agent_id)
            if mapped in active_agents or agent_id == "architect":
                plan.append(agent_id)
        return plan

    def format_plan(self, plan: list[str]) -> str:
        """Format the execution plan as markdown."""
        lines = ["## 📋 Execution Plan\n"]
        for i, step in enumerate(plan, 1):
            info = AGENT_INFO.get(step, {"name": step, "emoji": "🔧"})
            lines.append(f"{i}. {info['emoji']} **{info['name']}**")
        return "\n".join(lines)
