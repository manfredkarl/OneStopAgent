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

STEP 1 — When the user first describes their need:
- Acknowledge briefly (1 sentence)
- Ask 2-3 clarifying questions as a numbered list in the SAME message
- Show which agents you plan to use and why
- End with: "Ready when you are — just say **proceed** or answer the questions above."

STEP 2 — When the user responds (answers questions, says "go", "proceed", "let's go", "yes", "start", "do it", "sure", "ok", or ANY affirmative):
- IMMEDIATELY start calling tools. Do NOT ask more questions.
- Call generate_architecture first with all the context you have
- Then automatically call select_azure_services, estimate_costs, assess_business_value in sequence
- Pass each tool's full JSON output to the next tool
- Give a brief 1-sentence summary after each tool completes

IMPORTANT RULES:
- Respond to ANY positive/affirmative message by calling tools — don't be picky about exact wording
- Use markdown: **bold**, ## headings, numbered lists, bullet points
- Keep summaries brief
- When showing architecture, the tool output already includes mermaid — just present it

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
