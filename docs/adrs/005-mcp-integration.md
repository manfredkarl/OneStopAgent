# ADR-005: Microsoft Learn MCP Server Integration

## Status
Accepted

## Date
2026-03-26

## Context
The System Architect Agent and Azure Specialist Agent must ground their recommendations in authoritative Azure documentation. The System Architect queries for architecture patterns, data flow designs, and security posture guidance; the Azure Specialist queries for SKU comparisons, scaling limits, and region availability (frd-architecture.md §4.1). Recommendations that are not grounded in official documentation risk inaccuracy and undermine seller confidence. The solution must provide structured, queryable access to Microsoft Learn content, support product-scoped filtering, and operate within Microsoft tenant boundaries (NFR-8). A fallback mechanism is required when the documentation source is unavailable (frd-architecture.md §4.3).

## Decision
Use the **Microsoft Learn MCP Server** as the primary Azure documentation grounding source for agent queries.

## Options Considered

### Option 1: Microsoft Learn MCP Server
**Pros:**
- Official Microsoft-maintained MCP server — authoritative and up-to-date content
- Structured query/response interface with product filtering (e.g., scope to `azure-app-service`, `azure-sql-database`)
- Natural-language query format integrates cleanly with LLM-based agents
- Already configured in the project's `.mcp.json` — no additional setup required
- Returns documentation URLs, capabilities, and service recommendations in a structured format
- Enables `mcpSourced: true/false` flag on agent outputs for transparency (frd-architecture.md §4.1)

**Cons:**
- External service dependency — availability affects agent output quality
- Query latency adds to overall agent response time
- Content coverage depends on Microsoft Learn publishing cadence
- No offline mode — requires network connectivity to the MCP server

### Option 2: Direct docs.microsoft.com Scraping
**Pros:**
- Access to the full breadth of Microsoft Learn content
- No dependency on a specific MCP server or API
- Could cache pages locally for faster access

**Cons:**
- Web scraping is fragile — page structure changes break extraction logic
- No structured query interface — must build search, parsing, and relevance ranking from scratch
- HTML-to-content extraction is error-prone for complex documentation pages
- Violates Microsoft Learn Terms of Use for automated scraping
- Significant engineering effort to build and maintain

### Option 3: Pre-Built Knowledge Base (RAG with Embeddings)
**Pros:**
- Low-latency retrieval — embeddings are stored and queried locally
- Full control over content selection and update cadence
- No runtime dependency on external services
- Can be optimised for the specific Azure services relevant to the product

**Cons:**
- Requires building and maintaining an embedding pipeline (ingest, chunk, embed, index)
- Content becomes stale between refresh cycles — Azure documentation updates frequently
- Storage and compute costs for embedding index
- Significant upfront engineering effort before any value is delivered
- Difficult to keep coverage comprehensive across all Azure services

### Option 4: Azure Resource Graph
**Pros:**
- Real-time query access to Azure resource metadata and configurations
- Structured query language (KQL) for precise filtering
- Authoritative data about deployed resources

**Cons:**
- Provides resource metadata, not documentation — cannot answer "what is Azure App Service?" or "how does scaling work?"
- Requires Azure subscription access with appropriate permissions
- Not designed for architecture guidance or service comparison
- Complementary data source at best, not a replacement for documentation

## Rationale
The Microsoft Learn MCP Server is selected because it provides the exact capability needed: structured, queryable access to authoritative Azure documentation through a natural-language interface. The query format (frd-architecture.md §4.1) supports both the System Architect's architecture-focused queries and the Azure Specialist's SKU-focused queries, with optional product filters to scope results.

The MCP server is already configured in the project's `.mcp.json`, indicating it is available in the development environment with no additional provisioning. Agent outputs can set `mcpSourced: true` when grounded via MCP, providing transparency to sellers about the source of recommendations (frd-architecture.md §4.1).

The fallback behaviour defined in frd-architecture.md §4.3 mitigates the availability risk: if the MCP server times out or is unavailable, agents proceed with unverified recommendations (`mcpSourced: false`), log a warning, and the UI displays an "unverified" flag on affected service cards. This graceful degradation ensures the pipeline is never blocked by MCP unavailability.

Direct scraping was rejected due to fragility and Terms of Use concerns. A pre-built knowledge base would require significant engineering investment and introduces staleness. Azure Resource Graph provides resource metadata, not documentation, making it insufficient as a primary source.

## Consequences
**Positive:**
- Agents produce documentation-grounded recommendations with verifiable source URLs
- `mcpSourced` flag provides transparency — sellers and reviewers know which recommendations are verified
- Natural-language query format requires no translation layer between agent prompts and MCP queries
- Graceful fallback ensures pipeline continuity even when MCP is unavailable
- Zero additional infrastructure — MCP server is already configured and maintained by Microsoft

**Negative:**
- Runtime dependency on an external service — MCP server outages degrade output quality (though not availability)
- Query latency contributes to overall agent response time (within the 30s soft / 120s hard timeout budget)
- Content coverage is limited to what Microsoft Learn publishes — niche or very new services may have sparse documentation
- Fallback (unverified) recommendations may reduce seller confidence when the MCP server is unavailable

## References
- PRD §9 — Technical Stack: "Microsoft Learn MCP Server (Azure documentation)"
- PRD §4.7 FR-7 — External Integrations: MCP, Azure Pricing API
- frd-architecture.md §4.1 — MCP Query Format (MCPQuery interface, product filters)
- frd-architecture.md §4.1 — Query Construction Rules (Architect vs. Azure Specialist scoping)
- frd-architecture.md §4.3 — Fallback Behavior (MCP timeout → unverified recommendation → UI flag)
- frd-architecture.md §4.3 — Region Unavailability Fallback (primary → eastus → nearest available)
- `.mcp.json` — MCP server configuration (pre-configured in project)
