"""LangChain ReAct agent acting as the PM orchestrator."""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

from agents.llm import llm
from agents.tools import (
    generate_architecture,
    select_azure_services,
    estimate_costs,
    assess_business_value,
    generate_presentation,
    suggest_scenarios,
)

SYSTEM_PROMPT = """\
You are OneStopAgent, a project manager helping Microsoft Azure sellers scope customer solutions.

You have specialist tools available. Use them to build a complete Azure solution:
- generate_architecture: Design Azure architecture with Mermaid diagrams
- select_azure_services: Map architecture to specific Azure services with SKUs
- estimate_costs: Get Azure cost estimates from the pricing API
- assess_business_value: Analyse ROI and business impact
- generate_presentation: Create a PowerPoint deck
- suggest_scenarios: Find reference scenarios for vague requirements

WORKFLOW:
1. Understand the customer's needs (ask 1-2 clarifying questions if vague)
2. Present a plan: list which tools you'll use and why
3. Wait for user to say "go" or adjust the plan
4. Execute: call tools in logical order, passing outputs between them
5. After each tool, briefly summarise what was produced
6. When done, offer to generate the presentation

RULES:
- Be conversational and professional
- Pass the FULL output of each tool to the next (architecture → services → costs)
- If a tool fails, explain and offer alternatives
- Keep responses concise
"""

ALL_TOOLS = [
    generate_architecture,
    select_azure_services,
    estimate_costs,
    assess_business_value,
    generate_presentation,
    suggest_scenarios,
]

TOOL_NAME_MAP = {t.name: t for t in ALL_TOOLS}


def create_pm_agent(active_tool_names: list[str] | None = None):
    """Create a LangGraph ReAct agent with the given (or all) tools."""
    if active_tool_names:
        tools = [TOOL_NAME_MAP[n] for n in active_tool_names if n in TOOL_NAME_MAP]
    else:
        tools = list(ALL_TOOLS)

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )
    return agent
