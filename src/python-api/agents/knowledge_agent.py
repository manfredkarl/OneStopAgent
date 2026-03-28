"""Knowledge Agent — retrieves Microsoft reference architectures via MCP with local fallback."""
import logging
from agents.state import AgentState
from services.mcp import mcp_client, MCPUnavailableError
from data.knowledge_base import search_local_patterns

logger = logging.getLogger(__name__)


class KnowledgeAgent:
    """Retrieves relevant Microsoft patterns and reference architectures.

    Primary source: Microsoft Learn MCP Server
    Fallback: Local knowledge base (data/knowledge_base.py)
    """
    name = "Knowledge Retrieval"
    emoji = "📚"

    def run(self, state: AgentState) -> AgentState:
        """Query for Azure patterns matching the user's use case."""
        query = f"{state.user_input} {state.clarifications}".strip()

        # Add industry context if available from brainstorming
        industry = state.brainstorming.get("industry", "")
        if industry and industry != "Cross-Industry":
            query += f" {industry}"

        # Try MCP first
        try:
            patterns = mcp_client.search(query=query, top_k=5)
            logger.info(f"MCP returned {len(patterns)} patterns for query: {query[:50]}")
            state.retrieved_patterns = patterns
            return state
        except MCPUnavailableError as e:
            logger.warning(f"MCP unavailable, falling back to local knowledge base: {e}")

        # Fallback to local knowledge base
        local_patterns = search_local_patterns(query=query, top_k=5)

        # Flag as ungrounded
        for pattern in local_patterns:
            pattern["_source"] = "local"
            pattern["_ungrounded"] = True

        state.retrieved_patterns = local_patterns

        if local_patterns:
            logger.info(f"Local KB returned {len(local_patterns)} patterns (ungrounded)")
        else:
            logger.warning("No patterns found in local knowledge base either")

        return state
