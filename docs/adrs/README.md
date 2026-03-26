# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records for the OneStopAgent project. ADRs document significant technical decisions, the context behind them, the options considered, and the rationale for the chosen approach.

## Index

| ADR | Title | Status | Summary |
|-----|-------|--------|---------|
| [001](001-agent-framework.md) | AI Agent Framework | Accepted | Use Azure AI Foundry for multi-agent orchestration with tenant-scoped deployment |
| [002](002-diagram-rendering.md) | Architecture Diagram Rendering | Accepted | Use Mermaid.js for client-side diagram rendering with LLM-native syntax output |
| [003](003-pptx-generation.md) | PowerPoint Generation Library | Accepted | Use PptxGenJS for server-side PPTX creation within the Node.js/TS stack |
| [004](004-state-management.md) | Project State Management | Accepted | Use Azure Cosmos DB with in-memory Map fallback for MVP development |
| [005](005-mcp-integration.md) | Microsoft Learn MCP Server Integration | Accepted | Use the official MCP server for Azure documentation grounding with graceful fallback |
| [006](006-authentication.md) | Authentication Strategy | Accepted | Use Microsoft Entra ID with MSAL.js for SSO and JWT-based API authorisation |

## Format

All ADRs follow a consistent structure:

- **Status** — Accepted, Proposed, Deprecated, or Superseded
- **Date** — When the decision was made
- **Context** — The problem and constraints driving the decision
- **Decision** — What was decided
- **Options Considered** — Each alternative with pros and cons
- **Rationale** — Why the chosen option wins, linked to specific requirements
- **Consequences** — Positive and negative impacts of the decision
- **References** — Links to PRD sections, FRD sections, and external documentation

## Contributing

When adding a new ADR:

1. Use the next available number (e.g., `007-topic.md`)
2. Follow the format template above
3. Set status to `Proposed` until reviewed and accepted
4. Update this README index table
