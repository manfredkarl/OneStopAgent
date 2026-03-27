"""Orchestration engine — runs agents in sequence, streams progress."""
import json
import asyncio
from typing import AsyncGenerator
from agents.state import AgentState
from agents.pm_agent import ProjectManager, AGENT_INFO
from agents.architect_agent import ArchitectAgent
from agents.azure_specialist_agent import AzureSpecialistAgent
from agents.cost_agent import CostAgent
from agents.business_value_agent import BusinessValueAgent
from agents.presentation_agent import PresentationAgent
from agents.envisioning_agent import EnvisioningAgent
from agents.llm import llm
from models.schemas import ChatMessage

AGENTS = {
    "envisioning": EnvisioningAgent(),
    "architect": ArchitectAgent(),
    "azure_services": AzureSpecialistAgent(),
    "cost": CostAgent(),
    "business_value": BusinessValueAgent(),
    "presentation": PresentationAgent(),
}

pm = ProjectManager()


def format_agent_output(agent_id: str, state: AgentState) -> str:
    """Format an agent's output as markdown for the chat."""
    if agent_id == "architect":
        arch = state.architecture
        parts = [f"## 🏗️ Architecture Design\n\n{arch.get('narrative', '')}\n"]
        mermaid = arch.get("mermaidCode", "")
        if mermaid:
            parts.append(f"```mermaid\n{mermaid}\n```\n")
        comps = arch.get("components", [])
        if comps:
            parts.append("### Components\n")
            for c in comps[:15]:
                parts.append(f"- **{c.get('name', '')}** ({c.get('azureService', '')}) — {c.get('description', '')}")
        return "\n".join(parts)

    elif agent_id == "azure_services":
        sels = state.services.get("selections", [])
        parts = [f"## ☁️ Azure Services ({len(sels)} mapped)\n"]
        for s in sels[:15]:
            parts.append(f"- **{s.get('componentName', '')}** → {s.get('serviceName', '')} ({s.get('sku', '')}) in {s.get('region', 'eastus')}")
        return "\n".join(parts)

    elif agent_id == "cost":
        est = state.costs.get("estimate", {})
        monthly = est.get("totalMonthly", 0)
        annual = est.get("totalAnnual", 0)
        source = est.get("pricingSource", "unknown")
        parts = [f"## 💰 Cost Estimate\n\n**Total: ${monthly:,.2f}/month (${annual:,.2f}/year)** — Source: {source}\n"]
        parts.append("| Service | SKU | Monthly Cost |")
        parts.append("|---------|-----|-------------|")
        for item in est.get("items", [])[:20]:
            parts.append(f"| {item.get('serviceName', '')} | {item.get('sku', '')} | ${item.get('monthlyCost', 0):,.2f} |")
        if est.get("assumptions"):
            parts.append(f"\n*Assumptions: {', '.join(est['assumptions'][:5])}*")
        return "\n".join(parts)

    elif agent_id == "business_value":
        bv = state.business_value
        summary = bv.get("executiveSummary", "")
        drivers = bv.get("drivers", [])
        confidence = bv.get("confidenceLevel", "moderate")
        parts = [f"## 📊 Business Value Assessment\n\n{summary}\n\n**Confidence:** {confidence}\n"]
        if drivers:
            parts.append("### Value Drivers\n")
            for d in drivers:
                est_text = f" — *{d.get('quantifiedEstimate', d.get('estimate', ''))}*" if d.get("quantifiedEstimate") or d.get("estimate") else ""
                parts.append(f"- **{d.get('name', '')}**: {d.get('impact', d.get('description', ''))}{est_text}")
        return "\n".join(parts)

    elif agent_id == "presentation":
        return f"## 📑 Presentation Ready\n\nPowerPoint deck generated. You can download it from the project."

    elif agent_id == "envisioning":
        scenarios = state.envisioning.get("scenarios", [])
        parts = [f"## 💡 Reference Scenarios ({len(scenarios)} found)\n"]
        for s in scenarios:
            parts.append(f"- **{s.get('title', '')}**: {s.get('description', '')}")
        return "\n".join(parts)

    return f"{agent_id} completed."


class Orchestrator:
    """Manages project sessions and runs the agent pipeline."""

    def __init__(self):
        self.states: dict[str, AgentState] = {}
        self.phases: dict[str, str] = {}  # project_id -> "clarify" | "ready" | "executing" | "done"
        self.plans: dict[str, list[str]] = {}

    def get_state(self, project_id: str) -> AgentState:
        if project_id not in self.states:
            self.states[project_id] = AgentState()
        return self.states[project_id]

    async def handle_message(
        self, project_id: str, message: str, active_agents: list[str], description: str
    ) -> AsyncGenerator[ChatMessage, None]:
        """Handle a user message and yield response ChatMessages."""
        state = self.get_state(project_id)
        phase = self.phases.get(project_id, "clarify")

        if phase == "clarify":
            # First message — store input and ask clarifications
            state.user_input = message
            state.customer_name = ""

            loop = asyncio.get_event_loop()
            clarification_text = await loop.run_in_executor(
                None, pm.ask_clarifications, message
            )

            # Build and show plan
            plan = pm.build_plan(active_agents)
            self.plans[project_id] = plan
            plan_text = pm.format_plan(plan)

            full_response = f"{clarification_text}\n\n{plan_text}"

            self.phases[project_id] = "ready"

            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id="pm",
                content=full_response,
                metadata={"type": "pm_response"},
            )

        elif phase == "ready":
            # User confirmed — store clarifications and execute plan
            state.clarifications = message
            self.phases[project_id] = "executing"

            plan = self.plans.get(project_id, pm.build_plan(active_agents))

            # Acknowledge
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id="pm",
                content=f"Starting execution with {len(plan)} agents...",
                metadata={"type": "pm_response"},
            )

            # Execute each agent in sequence
            loop = asyncio.get_event_loop()

            for step in plan:
                info = AGENT_INFO.get(step, {"name": step, "emoji": "🔧"})
                agent = AGENTS.get(step)
                if not agent:
                    continue

                # Announce
                yield ChatMessage(
                    project_id=project_id,
                    role="agent",
                    agent_id="pm",
                    content=f"{info['emoji']} **{info['name']}** is working...",
                    metadata={"type": "agent_start", "agent": step},
                )

                # Run agent in thread pool (sync LLM calls inside)
                try:
                    state = await loop.run_in_executor(None, agent.run, state)
                except Exception as e:
                    yield ChatMessage(
                        project_id=project_id,
                        role="agent",
                        agent_id=step,
                        content=f"⚠️ {info['name']} failed: {str(e)}",
                        metadata={"type": "agent_error", "agent": step},
                    )
                    continue

                # Format and yield result
                formatted = format_agent_output(step, state)
                yield ChatMessage(
                    project_id=project_id,
                    role="agent",
                    agent_id=step,
                    content=formatted,
                    metadata={"type": "agent_result", "agent": step},
                )

            # Done
            self.phases[project_id] = "done"
            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id="pm",
                content="✅ All agents have completed. Review the results above. You can ask me to adjust anything or generate a presentation.",
                metadata={"type": "pm_response"},
            )

        elif phase in ("executing", "done"):
            # Follow-up message — let PM respond conversationally
            loop = asyncio.get_event_loop()

            response = await loop.run_in_executor(
                None,
                lambda: llm.invoke([
                    {"role": "system", "content": "You are an Azure solution project manager. The solution has been designed. Help the user with follow-up questions or modifications. Be brief."},
                    {"role": "user", "content": f"Context: {state.to_context_string()}\n\nUser says: {message}"}
                ]).content
            )

            yield ChatMessage(
                project_id=project_id,
                role="agent",
                agent_id="pm",
                content=response,
                metadata={"type": "pm_response"},
            )
