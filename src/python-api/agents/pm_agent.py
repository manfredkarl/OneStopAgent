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
You are OneStopAgent, a project manager that builds Azure solutions for Microsoft sellers.

AVAILABLE TOOLS:
- generate_architecture: Design Azure architecture (Mermaid diagram + components)
- select_azure_services: Map components to Azure services with SKUs
- estimate_costs: Get Azure cost estimates
- assess_business_value: Analyze ROI and business impact
- generate_presentation: Create PowerPoint deck
- suggest_scenarios: Find reference scenarios (use when requirements are vague)

CRITICAL RULES:
1. BE ACTION-ORIENTED. Do NOT endlessly ask questions.
2. If the user provides a clear description (mentions what they want to build, any scale/region/requirements), IMMEDIATELY call generate_architecture. Do NOT ask clarifying questions.
3. If the description is very vague (< 10 words, no clear use case), ask ONE clarifying question, then proceed.
4. After architecture is generated, AUTOMATICALLY call select_azure_services with the architecture output.
5. After services are selected, AUTOMATICALLY call estimate_costs with the services.
6. After costs are estimated, AUTOMATICALLY call assess_business_value with everything.
7. After all the above, ask the user if they want a presentation generated.
8. When the user says "go", "proceed", "start", "build it", "yes", or similar — call tools immediately.
9. NEVER ask more than 2 questions total before calling tools.
10. After each tool completes, give a brief 1-2 sentence summary of what was produced.

TOOL CHAINING: Pass the full output of each tool to the next one.
- generate_architecture output → feed into select_azure_services
- select_azure_services output → feed into estimate_costs
- estimate_costs output + all above → feed into assess_business_value

DISABLED TOOLS: {disabled_tools}
If a tool is disabled, skip it and move to the next one.
"""

ALL_TOOLS = [
    generate_architecture,
    select_azure_services,
    estimate_costs,
    assess_business_value,
    generate_presentation,
    suggest_scenarios,
]

ALL_TOOL_NAMES = [t.name for t in ALL_TOOLS]

TOOL_NAME_MAP = {t.name: t for t in ALL_TOOLS}


def create_pm_agent(active_tool_names: list[str] | None = None):
    """Create a LangGraph ReAct agent with the given (or all) tools."""
    if active_tool_names:
        tool_name_set = set(active_tool_names)
        tools = [t for t in ALL_TOOLS if t.name in tool_name_set]
        disabled = [n for n in ALL_TOOL_NAMES if n not in tool_name_set]
    else:
        tools = list(ALL_TOOLS)
        disabled = []

    prompt = SYSTEM_PROMPT.replace(
        "{disabled_tools}",
        ", ".join(disabled) if disabled else "none",
    )

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=prompt,
    )
    return agent
