"""System Architect Agent — generates Azure architecture with Mermaid diagrams."""
import json
from agents.llm import llm
from agents.state import AgentState


class ArchitectAgent:
    name = "System Architect"
    emoji = "🏗️"

    def run(self, state: AgentState) -> AgentState:
        """Generate architecture based on user requirements."""
        requirements = state.to_context_string()

        # Generate Mermaid diagram via LLM
        mermaid_response = llm.invoke([
            {"role": "system", "content": "Generate a Mermaid flowchart TD diagram for an Azure architecture. Use Azure service names as nodes. Maximum 20 nodes. Return ONLY the Mermaid code, no markdown fences, no explanation."},
            {"role": "user", "content": f"Design an Azure architecture for: {requirements}"}
        ])
        mermaid_code = mermaid_response.content.strip()
        # Clean up fences if present
        if mermaid_code.startswith("```"):
            mermaid_code = mermaid_code.split("\n", 1)[1] if "\n" in mermaid_code else mermaid_code[3:]
        if mermaid_code.endswith("```"):
            mermaid_code = mermaid_code[:-3].strip()
        if not mermaid_code.startswith(("flowchart", "graph")):
            mermaid_code = "flowchart TD\n" + mermaid_code

        # Extract components via LLM
        comp_response = llm.invoke([
            {"role": "system", "content": 'Extract Azure architecture components. Return ONLY a JSON array: [{"name": "...", "azureService": "...", "description": "..."}]'},
            {"role": "user", "content": requirements}
        ])
        try:
            comp_text = comp_response.content.strip()
            if comp_text.startswith("```"):
                comp_text = comp_text.split("\n", 1)[1].rsplit("```", 1)[0]
            components = json.loads(comp_text)
        except (json.JSONDecodeError, IndexError):
            components = [
                {"name": "Web Frontend", "azureService": "Azure App Service", "description": "Web hosting"},
                {"name": "API Backend", "azureService": "Azure App Service", "description": "API layer"},
                {"name": "Database", "azureService": "Azure SQL Database", "description": "Data storage"},
            ]

        # Generate narrative via LLM
        narr_response = llm.invoke([
            {"role": "system", "content": "Write a 2-3 sentence description of this Azure architecture for a business audience. Be specific about the services used."},
            {"role": "user", "content": f"Architecture components: {json.dumps(components)}\nFor: {state.user_input}"}
        ])

        state.architecture = {
            "mermaidCode": mermaid_code,
            "components": components,
            "narrative": narr_response.content.strip(),
        }
        return state
