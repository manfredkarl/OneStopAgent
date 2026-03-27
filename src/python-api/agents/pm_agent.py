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

YOUR BEHAVIOR:

FIRST MESSAGE from user — Respond with:
1. A brief acknowledgment of their request (1 sentence)
2. 2-3 quick clarifying questions in a numbered list
3. An execution plan showing which agents will run

Example first response (use this FORMAT, adapt content):
"Great — an e-commerce platform for retail! A few quick questions:

1. How many concurrent users should we design for?
2. Any compliance requirements (PCI-DSS, HIPAA, GDPR)?
3. Preferred Azure region?

## 📋 Execution Plan
Once you answer (or say **go** to use defaults):
1. 🏗️ **System Architect** — Design the Azure architecture
2. ☁️ **Azure Specialist** — Select services and SKUs
3. 💰 **Cost Specialist** — Estimate monthly costs
4. 📊 **Business Value** — Analyze ROI and impact

Say **go** when ready!"

SECOND MESSAGE (user answers or says "go") — IMMEDIATELY call tools:
- Call generate_architecture with ALL the context you have
- Then call select_azure_services with the architecture output
- Then call estimate_costs with the services
- Then call assess_business_value with everything
- Do NOT ask any more questions — just execute

IMPORTANT:
- When passing data between tools, pass the FULL JSON output string
- Use markdown: **bold**, ## headings, bullet lists
- Keep summaries brief (1-2 sentences per tool result)

DISABLED TOOLS: {disabled_tools}
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
