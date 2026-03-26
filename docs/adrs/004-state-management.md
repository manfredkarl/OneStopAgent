# ADR-004: Project State Management

## Status
Accepted

## Date
2026-03-26

## Context
OneStopAgent must persist project data, chat history, and agent outputs across browser sessions. Users expect that closing and reopening the browser does not lose any work (NFR-5). The primary data entity — `ProjectContext` — is a deeply nested JSON document containing requirements, architecture output (with embedded Mermaid code and component arrays), service selections, cost estimates, and business value assessments (frd-chat.md FR-4). Chat messages form an append-only time-series per project. Data must be retained for 12 months with user-initiated deletion (NFR-10), scoped to individual users with no cross-user access (SEC-7), and remain within Microsoft tenant boundaries (NFR-8). The MVP must be deliverable quickly, so the storage solution should support a low-friction development path with a clear upgrade strategy.

## Decision
Use **Azure Cosmos DB** as the primary data store, with an **in-memory `Map`-based store as a fallback for MVP** development and testing.

## Options Considered

### Option 1: Azure Cosmos DB
**Pros:**
- Native JSON document storage — `ProjectContext`'s nested structure maps directly without ORM or schema transformation
- Partition key on `userId` naturally enforces data isolation (SEC-7) and optimises per-user queries
- Global distribution capability supports future multi-region deployment
- Integrated with Azure ecosystem — Entra ID RBAC, Azure Monitor, diagnostic logging
- TTL (time-to-live) policies can enforce 12-month data retention automatically (NFR-10)
- Change feed enables event-driven patterns (e.g., triggering pipeline stages on data changes)
- Microsoft-managed service within the Azure subscription satisfies NFR-8

**Cons:**
- Higher cost compared to simpler storage options, especially at low scale
- Request Unit (RU) pricing model requires capacity planning
- Learning curve for partition key design and consistency level selection
- Local development requires the Cosmos DB emulator or a dedicated dev instance

### Option 2: Azure SQL Database
**Pros:**
- Mature, well-understood relational database with strong ACID guarantees
- Excellent tooling (SSMS, Azure Data Studio, Entity Framework)
- Cost-effective for structured data with predictable query patterns

**Cons:**
- Poor fit for deeply nested JSON documents — `ProjectContext` would need to be flattened into normalised tables or stored as JSON columns with limited query capability
- Schema migrations required as agent output formats evolve
- Relational model adds friction for the document-oriented access patterns (read/write entire project context)

### Option 3: PostgreSQL (Azure Database for PostgreSQL)
**Pros:**
- Strong JSON/JSONB support — can store and query nested documents
- Open-source with extensive community and tooling
- Cost-effective with flexible scaling options
- GIN indexes on JSONB columns enable efficient nested document queries

**Cons:**
- JSONB queries are less ergonomic than native document database operations
- Schema management still required for the relational portions of the data model
- Less tightly integrated with Azure ecosystem compared to Cosmos DB
- No built-in global distribution or change feed

### Option 4: Redis + Azure Blob Storage
**Pros:**
- Extremely fast read/write for active sessions (Redis in-memory)
- Blob storage for durable persistence of completed projects
- Simple key-value access pattern

**Cons:**
- Two-tier architecture adds complexity (sync between Redis and blob storage)
- Redis data loss risk on eviction or restart without persistence configuration
- No native query capability on blob storage — cannot search or filter projects without an index layer
- Chat message history as append-only time-series is awkward in Redis

### Option 5: In-Memory Map (MVP Only)
**Pros:**
- Zero infrastructure dependency — simplest possible implementation
- Instant read/write with no network latency
- Trivial to implement and test during early development
- No cost, no configuration, no external services

**Cons:**
- All data lost on server restart — violates NFR-5 for production use
- No durability, no backup, no recovery
- Does not scale beyond a single process
- Not suitable for any deployment beyond local development

## Rationale
Cosmos DB is selected as the production data store because `ProjectContext` is a deeply nested JSON document (frd-chat.md FR-4) that maps naturally to Cosmos DB's document model without schema transformation. The access patterns — reading and writing entire project contexts keyed by `userId` and `projectId` — align perfectly with Cosmos DB's partition key model. Partitioning on `userId` enforces per-user data isolation (SEC-7) at the database level and optimises the most common query pattern (list my projects, load a project).

NFR-5 (no data loss on refresh) and NFR-10 (12-month retention with manual deletion) are directly supported by Cosmos DB's durability guarantees and TTL policies. NFR-8 (tenant-scoped data residency) is satisfied because Cosmos DB is deployed within the organisation's Azure subscription.

The in-memory `Map` fallback is retained for MVP because it eliminates infrastructure setup during early development and testing. The data access layer will be implemented behind an interface (repository pattern), allowing the switch from in-memory to Cosmos DB without changing application code. This dual-mode approach is explicitly anticipated by the PRD (§9: "Azure Cosmos DB (primary) or in-memory (MVP)").

Azure SQL and PostgreSQL were rejected because the relational model is a poor fit for the deeply nested, schema-evolving document structure. Redis + Blob Storage adds two-tier complexity without meaningful benefit over Cosmos DB for this workload.

## Consequences
**Positive:**
- Document model eliminates impedance mismatch — `ProjectContext` is stored and retrieved as-is
- Partition key on `userId` provides built-in data isolation and query optimisation
- TTL policies automate data retention compliance (NFR-10)
- In-memory fallback enables rapid MVP development without infrastructure dependencies
- Repository pattern abstraction allows seamless migration between storage backends
- Change feed enables future event-driven features (notifications, analytics)

**Negative:**
- Cosmos DB RU-based pricing requires monitoring and capacity planning
- Local development requires either the Cosmos DB emulator or a shared dev instance
- Two storage backends (in-memory and Cosmos DB) must both be maintained and tested
- Cosmos DB's eventual consistency (default) requires careful handling for read-after-write scenarios in the pipeline

## References
- PRD §9 — Technical Stack: "Azure Cosmos DB (primary) or in-memory (MVP)"
- PRD §5 NFR-5 — Data Persistence: "No data loss on page refresh or browser close"
- PRD §5 NFR-8 — Data Residency & LLM Privacy: "All data within Microsoft tenant boundaries"
- PRD §5 NFR-10 — Data Retention & Deletion: "12-month retention, manual deletion"
- frd-chat.md FR-4 — Data Model: `Project`, `ProjectContext`, `ChatMessage` schemas
- frd-chat.md §5 SEC-7 — Data Isolation: "Projects scoped to individual users, DB queries include userId filter"
