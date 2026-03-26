# ADR-001: AI Agent Framework

## Status
Accepted

## Date
2026-03-26

## Context
OneStopAgent requires a multi-agent orchestration platform capable of hosting a Project Manager (PM) agent plus six specialist agents (Envisioning, System Architect, Azure Specialist, Cost Specialist, Business Value, Presentation). The platform must support a sequential seven-stage pipeline with gate-based approval between stages, per-agent lifecycle management (Idle → Working → Complete/Error), and strict single-agent concurrency per project (frd-orchestration.md §3.1). All data must remain within Microsoft tenant boundaries (NFR-8), and the solution must integrate with Microsoft Entra ID for authentication (SEC-1). Agents invoke external tools such as the Microsoft Learn MCP Server and the Azure Retail Prices API, requiring a framework that supports tool-use patterns and structured output schemas.

## Decision
Use **Azure AI Foundry** as the agent orchestration platform for hosting, deploying, and invoking all agents.

## Options Considered

### Option 1: Azure AI Foundry
**Pros:**
- Native Azure ecosystem integration — deploys within the organisation's Azure subscription, satisfying NFR-8 (tenant-scoped data residency)
- Built-in support for Entra ID authentication and RBAC
- Managed infrastructure for model hosting, scaling, and monitoring
- First-party Microsoft product with enterprise SLA and support
- Supports tool-use patterns (function calling) required for MCP and Pricing API integration
- Aligns with internal Microsoft engineering standards

**Cons:**
- Tighter coupling to Azure; migrating away would require significant rework
- Feature set is evolving; some orchestration patterns may need custom implementation
- Less community-driven extensibility compared to open-source alternatives

### Option 2: Semantic Kernel
**Pros:**
- Microsoft-backed open-source SDK with strong .NET and Python support
- Plugin/function model aligns well with agent tool-use patterns
- Can run on any infrastructure, not locked to Azure AI Foundry

**Cons:**
- SDK-level library, not a managed platform — requires building hosting, scaling, and monitoring separately
- Multi-agent orchestration with sequential pipelines and gate logic would need custom implementation
- No built-in deployment isolation or tenant-scoping

### Option 3: LangChain
**Pros:**
- Large ecosystem with extensive community plugins and integrations
- Well-documented patterns for agent chains, tool use, and memory
- Language-agnostic (Python and JS/TS SDKs)

**Cons:**
- No inherent Azure tenant isolation; requires additional infrastructure for NFR-8 compliance
- Rapid API churn and breaking changes across versions
- Not a Microsoft-supported product — risk for internal enterprise deployment
- Multi-agent orchestration requires LangGraph add-on, adding complexity

### Option 4: AutoGen
**Pros:**
- Purpose-built for multi-agent conversation patterns
- Supports agent-to-agent messaging natively
- Microsoft Research project with active development

**Cons:**
- Research-stage maturity; not yet enterprise-grade for production workloads
- Conversation-based paradigm may not map cleanly to our sequential pipeline with approval gates
- Limited deployment and hosting story — would need custom infrastructure

### Option 5: Custom Orchestration
**Pros:**
- Full control over pipeline logic, gate semantics, and agent lifecycle
- No external framework dependencies
- Can be optimised precisely for our seven-stage sequential pattern

**Cons:**
- Significant engineering effort to build, test, and maintain
- Must implement model hosting, scaling, retries, timeouts, and monitoring from scratch
- No leverage from existing tooling or community patterns
- Higher long-term maintenance burden

## Rationale
Azure AI Foundry is selected because it directly satisfies the most critical non-functional requirements. NFR-8 mandates that all data — including LLM interactions — stays within the Microsoft tenant's Azure subscription; Foundry's managed deployment model guarantees this by design. The platform's native Entra ID integration eliminates the need to build a separate authentication bridge for agent invocations (SEC-1, SEC-2). As a first-party Microsoft product, it aligns with internal engineering standards and provides enterprise SLA coverage, which is essential for a tool used by Microsoft sellers.

While Semantic Kernel and LangChain offer flexibility, they are SDK-level libraries that would require building the hosting, scaling, and tenant-isolation layers manually. AutoGen's multi-agent patterns are compelling but lack production maturity. A custom solution would provide maximum control but at disproportionate engineering cost for an MVP. Foundry strikes the right balance: managed infrastructure with sufficient extensibility for our sequential pipeline and gate-based orchestration (frd-orchestration.md §3.1–§3.4).

## Consequences
**Positive:**
- Tenant-scoped deployment is handled by the platform, reducing security engineering effort
- Entra ID integration is built-in, simplifying the authentication stack
- Microsoft enterprise support and SLA provide operational confidence
- Model versioning and deployment management are platform-managed
- Future scaling (multi-region, higher throughput) is supported by the platform

**Negative:**
- Vendor lock-in to Azure; switching orchestration platforms would require significant migration
- Pipeline gate logic and sequential stage orchestration must be implemented in application code on top of Foundry primitives
- Team must track Foundry's evolving feature set and adapt to API changes
- Local development and testing may require Foundry emulators or mocks

## References
- PRD §9 — Technical Stack: "Azure AI Foundry (host and orchestrate agents)"
- PRD §5 NFR-8 — Data Residency & LLM Privacy
- frd-orchestration.md §2.1 — Agent Registry (7 agents, pipeline order)
- frd-orchestration.md §2.2 — Agent Lifecycle States (Idle → Working → Complete/Error)
- frd-orchestration.md §3.1 — Pipeline State Machine (sequential 7-stage pipeline)
- frd-orchestration.md §6 — Concurrency & Timeout (120s hard, 30s soft, 1 agent per project)
- frd-chat.md §5 SEC-1, SEC-2 — Entra ID SSO and JWT validation
