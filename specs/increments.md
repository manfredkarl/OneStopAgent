# OneStopAgent — Delivery Increments

## Increment 1: Walking Skeleton

### Goal
Prove the end-to-end architecture by enabling a seller to log in, create a project, chat with the PM Agent, and receive a basic architecture diagram.

### User Stories Covered
- **US-1** Start a New Project (core)
- **US-3** Architecture Generation (basic — Mermaid generation, no modification flow)
- **US-9** Guided Questioning (not yet — PM acknowledges and classifies only)

### FRD Sections
- **frd-chat** §2.1 POST /api/projects, §2.2 GET /api/projects, §2.3 GET /api/projects/:id, §2.4 POST /api/projects/:id/chat, §2.5 GET /api/projects/:id/chat (basic), §2.6 GET /api/projects/:id/agents, §3.1 Project description validation (core rules), §3.2 Chat message validation (core rules), §4.1 Project creation flow, §5 SEC-1/SEC-2/SEC-3 Authentication & ownership, §6.1 Landing page, §6.3 Chat interface (basic), §6.4 Agent sidebar (static display), §6.5 Rich content rendering (Mermaid only)
- **frd-orchestration** §2.1 Agent registry, §4.1 Input classification (CLEAR path only)
- **frd-architecture** §2.1 Input contract, §2.2 Output contract, §2.3 Mermaid diagram generation (basic), §2.4 Component list, §2.5 Narrative

### Gherkin Scenarios

**From `chat.feature` (18 scenarios):**
1. Create a new project with a clear description
2. Create a new project with an optional customer name
3. Reject project creation when description is missing
4. Reject project creation when description is empty whitespace
5. Reject project description exceeding maximum length
6. List all projects for the authenticated user
7. List projects when user has no projects
8. Retrieve full project state by ID
9. Reject retrieval of another user's project
10. Reject retrieval of a non-existent project
11. Send a chat message and receive PM Agent response
12. Reject chat message with empty content
13. Retrieve chat history with default pagination
14. List all agents and their statuses for a project
15. Reject request without authentication token
16. Reject request with expired authentication token
17. Landing page renders create project form
18. Chat interface auto-scrolls on new agent message

**From `orchestration.feature` (1 scenario):**
19. PM Agent classifies a detailed input as CLEAR

**From `architecture.feature` (4 scenarios):**
20. Generate a valid architecture diagram for a web application
21. Nodes use correct shapes by category
22. Architecture narrative is seller-appropriate
23. Components match diagram nodes exactly

**Total: 23 scenarios**

### Definition of Done
- Seller authenticates via Entra ID and lands on the landing page
- Seller creates a project with a description; receives a project ID
- Project is persisted and appears in the project list
- PM Agent acknowledges the description and classifies it as CLEAR
- Seller sends messages and receives PM Agent responses in the chat
- Chat history is persisted and loadable on page refresh
- System Architect Agent generates a valid Mermaid flowchart with components and narrative
- Mermaid diagram renders inline in the chat interface
- Agent sidebar shows all agents with static status indicators (all idle)
- Authentication is enforced on all endpoints; ownership checks return 403
- Basic input validation (empty/missing fields) returns proper 400 errors

### API Endpoints
| Endpoint | Method | Status |
|---|---|---|
| `/api/projects` | POST | Implemented |
| `/api/projects` | GET | Implemented |
| `/api/projects/:id` | GET | Implemented |
| `/api/projects/:id/chat` | POST | Implemented (basic) |
| `/api/projects/:id/chat` | GET | Implemented (basic — no cursor pagination) |
| `/api/projects/:id/agents` | GET | Implemented (read-only) |

### Frontend Pages
| Route | Status |
|---|---|
| `/` | Landing page — create project form + recent projects list |
| `/project/:id` | Chat interface with agent sidebar (static) and Mermaid rendering |
| `/projects` | Project list page (basic) |

---

## Increment 2: Guided Discovery

### Goal
Enable the full discovery flow — from a vague customer idea through guided questioning and envisioning to enriched context ready for architecture design.

### User Stories Covered
- **US-2** Guided Envisioning (full)
- **US-8** Agent Selection and Control (activate/deactivate, sidebar toggles)
- **US-9** Guided Questioning (full — structured questions, skip, defaults, proceed)

### FRD Sections
- **frd-chat** §2.7 PATCH /api/projects/:id/agents/:agentId, §3.3 Agent activation validation, §4.2 Guided questioning flow, §4.3 Agent selection flow (basic — idle agents only), §6.4 Agent sidebar (interactive toggles)
- **frd-orchestration** §4.1 Input classification (VAGUE path), §4.2 Structured questioning (full question catalog), §4.3 Context assembly
- **frd-envisioning** §2 Knowledge base schema, §2.4 Mock data, §3 Agent input/output contract, §4 Matching logic (industry detection, keyword matching, no-match fallback), §5 Frontend behavior (selectable lists, proceed button, rejection flow), §6 Error responses, §7 Edge cases
- **frd-chat** §6.5 Rich content rendering (checkboxes, selectable lists, action buttons)

### Gherkin Scenarios

**From `chat.feature` (8 scenarios):**
1. PM Agent asks structured questions in sequence
2. Seller skips a question and PM assumes default
3. Seller ends questioning early by saying proceed
4. PM Agent caps questions at maximum of 10
5. PM Agent distinguishes intent from keyword matching
6. Deactivate an idle optional agent
7. Reject deactivation of the System Architect agent
8. Re-activate a previously deactivated agent

**From `orchestration.feature` (2 scenarios):**
9. PM Agent classifies a vague input as VAGUE
10. PM Agent handles vague input when Envisioning is disabled

**From `envisioning.feature` (18 scenarios):**
11. Match suggestions for a retail e-commerce description
12. Infer industry from description when industryHints not provided
13. Rank items by weighted keyword matching
14. Multi-industry description returns results from all matched industries
15. No industry detected defaults to Cross-Industry
16. Seller selects items and proceeds
17. Proceed button is disabled when no items selected
18. Seller selects all available items
19. Seller selects items from only one category
20. Seller rejects all suggestions and provides own direction
21. Re-invocation after rejection merges context
22. No items match across any category
23. Knowledge base is unavailable
24. Empty userDescription is provided
25. Description exceeding 5000 characters is truncated silently
26. Very short description returns low confidence with broader results
27. Seller navigates away and returns to preserved selections
28. Conflicting industry signals in description

**Total: 28 scenarios**

### Definition of Done
- PM Agent classifies vague input and routes to Envisioning Agent
- Envisioning Agent returns matched scenarios, estimates, and reference architectures from mock knowledge base
- Suggestions render as checkbox lists with category headers in the chat
- Seller can select items and click "Proceed with Selected Items"
- Seller can reject suggestions and describe their own direction
- PM Agent conducts structured questioning (up to 10 questions, skippable, with defaults)
- Requirements summary displays with assumption flags (⚠️)
- "Start Agents" button appears after questioning completes
- Agent sidebar toggles activate/deactivate agents (idle agents only)
- System Architect toggle is locked with tooltip
- PM Agent posts pipeline adjustment messages when agents are toggled
- No-match fallback prompts for more detail

### API Endpoints
| Endpoint | Method | Status |
|---|---|---|
| `/api/projects/:id/agents/:agentId` | PATCH | Implemented (idle agents) |
| `/api/projects/:id/chat` | POST | Extended (guided questioning, envisioning flow) |

### Frontend Pages
| Route | Components |
|---|---|
| `/project/:id` | Agent sidebar with interactive toggles; rich content: checkbox lists, "Proceed with Selected Items" button, "Start Agents" button; assumption flagging with ⚠️ |

---

## Increment 3: Cost & Services

### Goal
Enable the architecture → service selection → cost estimation flow with pipeline stage transitions and approval gates.

### User Stories Covered
- **US-3** Architecture Generation (MCP integration, grounding)
- **US-4** Azure Service Selection (full — SKU recommendations, trade-offs, region handling)
- **US-5** Cost Estimation (full — API integration, calculation, caching, parameter adjustment)

### FRD Sections
- **frd-orchestration** §2.2 Agent lifecycle states, §3.1 Pipeline stages, §3.2 Stage transitions (gates — Approve & Continue, Request Changes), §3.3 Skip logic (deactivated agents)
- **frd-architecture** §3 Azure Specialist Agent (input/output, SKU logic, trade-offs), §4 Microsoft Learn MCP integration (queries, fallback, attribution)
- **frd-cost** §2 Azure Retail Prices API integration (query construction, response parsing), §3 Agent input/output contract, §4 Cost calculation logic (unit mapping, scale parameters, assumptions), §5 Parameter adjustment flow (adjustable controls, recalculation, diff display), §6 Fallback & caching (24h TTL, retry logic, pricing source indicator), §7 Frontend behavior (cost table, parameter controls, disclaimer), §8 Error responses

### Gherkin Scenarios

**From `orchestration.feature` (5 scenarios):**
1. Pipeline advances from System Architect to Azure Specialist after approval
2. Seller requests changes at a gate
3. Pipeline skips deactivated agents _(Scenario Outline — 5 examples: envisioning, azure, cost, value, presentation)_
4. Agent state transitions on events _(Scenario Outline — 7 examples: invoke, success, failure, cancel, reset, retry, skip)_
5. Deactivate agent before its stage is reached

**From `architecture.feature` (8 scenarios):**
6. Select Azure services for architecture components
7. SKU selection scales with concurrent users _(Scenario Outline — 3 examples: 50→B1, 500→S1, 10000→P2v3)_
8. Region defaults to eastus when no preference specified
9. Service unavailable in preferred region falls back to nearest
10. Trade-offs are presented in structured format
11. Architecture grounded with MCP data
12. MCP Server unavailable triggers fallback to built-in knowledge
13. MCP Server times out after 10 seconds

**From `cost.feature` (15 scenarios):**
14. Generate cost estimate with live pricing
15. Calculate App Service B1 monthly cost correctly
16. Include explicit assumptions in every estimate
17. Free-tier services display zero cost with assumption note
18. Adjust concurrent users triggers recalculation
19. Change region triggers new API queries
20. Diff display shows before and after costs
21. Use cached prices within 24-hour TTL
22. Expired cache triggers fresh API query
23. API failure with retries falls back to expired cache
24. API failure with no cache returns error
25. Pricing source indicator reflects data freshness _(Scenario Outline — 3 examples: live, cached, approximate)_
26. Disclaimer always displayed below cost table
27. Currency formatting follows USD conventions
28. Non-region parameter changes reuse cached retail prices

**Total: 28 scenarios**

### Definition of Done
- Pipeline advances through stages with "Approve & Continue" gates
- Seller can request changes at a gate; agent re-runs with feedback
- Deactivated agents are skipped; stage status set to "skipped"
- Azure Specialist maps architecture components to services with SKUs, regions, and capabilities
- Trade-offs show alternatives with structured comparison text
- MCP integration grounds recommendations; fallback marks outputs "unverified"
- Cost Specialist queries Azure Retail Prices API for live pricing
- Cost breakdown table renders with service, SKU, region, and monthly cost
- Total monthly and annual projections are calculated and displayed
- Seller can adjust parameters (users, data volume, region, hours) and recalculate
- Diff display shows before/after comparison
- 24-hour price cache with fallback to approximate pricing
- Pricing source badge (live/cached/approximate) displayed
- Disclaimer about EA/CSP exclusion always visible

### API Endpoints
| Endpoint | Method | Status |
|---|---|---|
| `/api/projects/:id/chat` | POST | Extended (Azure Specialist, Cost Specialist, gate interactions) |

### Frontend Pages
| Route | Components |
|---|---|
| `/project/:id` | "Approve & Continue" / "Request Changes" gate UI; service selection cards (expandable, with alternatives); cost breakdown table with sorting; parameter adjustment panel; pricing source badge; disclaimer footer; diff display |

---

## Increment 4: Business Value & Presentation

### Goal
Complete the seller journey from idea to downloadable PowerPoint deck with business value assessment.

### User Stories Covered
- **US-6** Business Value Assessment (full — value drivers, benchmarks, executive summary)
- **US-7** Presentation Generation (full — PPTX generation, download, regeneration)

### FRD Sections
- **frd-orchestration** §3.1 Full pipeline completion, §5.2 Output schemas (all agents)
- **frd-business-value** §2 Value driver framework (standard + custom drivers), §3 Agent input/output contract, §4 Quantification methodology (estimate sources, confidence, disclaimers), §5 Benchmark knowledge base (schema + mock data), §6 Executive summary generation, §7 Frontend behavior (driver cards, summary display, benchmarks), §8 Error responses, §9 Edge cases
- **frd-presentation** §2 Agent input/output contract, §3 Slide deck structure (all slide types), §4 Template specification (colors, fonts, layout), §5 Content mapping rules (diagram→slide, cost→slides, value→slides, missing sections), §6 PPTX generation (PptxGenJS, rendering pipeline, slide count limits, truncation), §7 Export API (GET /export/pptx, regeneration logic), §8 Frontend behavior (download button, progress, regeneration prompt)

### Gherkin Scenarios

**From `orchestration.feature` (1 scenario):**
1. Full pipeline completes successfully

**From `business-value.feature` (19 scenarios):**
2. Evaluate all five standard value drivers
3. Quantify cost savings using cost estimate comparison
4. Identify custom value drivers from project context
5. Omit quantified estimate when no credible data supports it
6. Confidence level based on benchmark coverage _(Scenario Outline — 3 examples: conservative, moderate, optimistic)_
7. Reference cross-industry cloud migration benchmarks
8. Reference industry-specific benchmarks for healthcare
9. Executive summary follows required structure
10. Executive summary includes mandatory disclaimer
11. All quantified estimates use required prefix
12. Missing required project context returns error
13. No value drivers identified returns partial response
14. Benchmark knowledge base unavailable degrades gracefully
15. No cost estimate available omits cost-comparison quantification
16. Conflicting value drivers are both included transparently
17. Niche industry caps confidence at low
18. No benchmarks match yields purely qualitative assessment
19. Minimal requirements input produces generic assessment
20. Single-service architecture limits quantification scope

**From `presentation.feature` (15 scenarios):**
21. Generate a full deck with all agent outputs available
22. Deck includes all required slides in correct order
23. Title slide contains project description and customer name
24. Executive summary slide uses ValueAssessment when available
25. Next Steps slide includes standard recommended actions
26. Omit slides when agent was skipped _(Scenario Outline — 4 examples: architect, azure, cost, value)_
27. Minimal deck when only PM gathered requirements
28. Architecture diagram rendered as PNG in slide
29. Diagram conversion failure inserts placeholder slide
30. Reject export for unauthorized user
31. Reject export when no agent outputs exist
32. Serve cached deck when source data unchanged
33. Regenerate deck when agent outputs have changed
34. Download button enabled when agent outputs exist
35. Download shows generation progress

**Total: 35 scenarios**

### Definition of Done
- Business Value Agent evaluates solution against 5 standard value drivers
- Custom value drivers identified from context (max 3)
- Quantified estimates with confidence levels (conservative/moderate/optimistic)
- Benchmark references from mock knowledge base
- Executive summary generated (100–200 words, follows required structure with disclaimer)
- Value driver cards render in chat with benchmark references
- Presentation Agent compiles all outputs into a PPTX deck (≤20 slides)
- Deck includes: Title, Executive Summary, Use Case, Architecture, Services, Cost, Business Value, Next Steps
- Missing sections are omitted with notes on the Executive Summary slide
- Diagram-to-image conversion with placeholder fallback
- Download button in chat triggers PPTX generation and browser download
- Regeneration when source data changes (sourceHash comparison)
- Full pipeline end-to-end: Envisioning → Architect → Azure → Cost → Value → Presentation
- Project status transitions to "completed" after final stage

### API Endpoints
| Endpoint | Method | Status |
|---|---|---|
| `/api/projects/:id/export/pptx` | GET | Implemented |
| `/api/projects/:id/chat` | POST | Extended (Business Value, Presentation agents) |

### Frontend Pages
| Route | Components |
|---|---|
| `/project/:id` | Value driver cards with confidence badges; executive summary blockquote with copy button; benchmark references (collapsible); projection disclaimer banner; "Download PowerPoint" button with progress spinner; regeneration badge ("Updates available") |

---

## Increment 5: Polish & Hardening

### Goal
Harden the application for production: error recovery flows, rate limiting, input sanitization, architecture modification, parameter edge cases, and comprehensive edge-case handling across all agents.

### User Stories Covered
- **US-1** Start a New Project (edge cases, storage failure)
- **US-3** Architecture Generation (modification flow, diagram export, retry logic)
- **US-4** Azure Service Selection (edge cases)
- **US-5** Cost Estimation (edge cases — unknown SKU, region unavailability, pagination)
- **US-7** Presentation Generation (edge cases — truncation, fallback PDF, concurrent generation)
- **US-8** Agent Selection and Control (working agent deactivation, concurrency)
- **US-9** Guided Questioning (edge cases)

### FRD Sections
- **frd-chat** §3.1–3.4 Remaining validation rules (max-length edge cases, sanitization), §5 SEC-4/SEC-5/SEC-6 Rate limiting, input sanitization, audit logging, §7 Error catalogue (complete), §8 Edge cases (EC-3 through EC-25)
- **frd-orchestration** §3.3 Skip logic (cancel working agent, downstream impact), §3.4 Error recovery (Retry/Skip/Stop, auto-escalation, required agent exhaustion), §6.1 Timeout policy (soft/hard timeouts, agent-specific overrides), §6.2 Concurrency limits (per-user, global pool, queuing), §7 Error catalog (complete), §8 Edge cases (E-1 through E-18)
- **frd-architecture** §2.3.2 Complexity limits (consolidation), §2.3.5 Validation pipeline (retry after syntax error), §5 Modification flow (add/remove/replace, delta updates, re-validation), §6 Diagram export (PNG/SVG), §8 Error responses, §9 Edge cases
- **frd-cost** §9 Edge cases (zero results, unknown SKU, region unavailability, large estimates, multiple meters, pagination)
- **frd-presentation** §6.3 Slide count limits (truncation strategy), §6.4 Content truncation rules, §7.2 Force regeneration, §9 Error responses (concurrent generation, PDF fallback), §10 Edge cases

### Gherkin Scenarios

**From `chat.feature` (20 scenarios):**
1. Accept project description at exact maximum length
2. Reject project with customer name exceeding 200 characters
3. Reject project description containing script injection
4. Reject project creation when storage is unavailable
5. Send a message targeting a specific agent
6. Accept chat message at exact maximum length of 10000 characters
7. Reject chat message exceeding maximum length
8. Reject chat message targeting an unknown agent
9. Reject chat message targeting an inactive agent
10. Reject chat when agent exceeds hard timeout
11. Retrieve next page of chat history using cursor
12. Reject chat history with invalid limit parameter
13. Reject deactivation of a working agent without confirmation
14. Deactivate a working agent with explicit confirmation
15. Idempotent deactivation from concurrent tabs
16. Enforce rate limiting at 60 requests per minute
17. Chat interface shows new message pill when scrolled up
18. User message is queued while agent is working
19. Agent produces an empty response
20. All optional agents deactivated leaves only PM and System Architect

**From `orchestration.feature` (20 scenarios):**
21. Seller reaches maximum revision limit at a gate
22. Only one agent can be in Working state per project
23. Deactivate agent while it is working mid-execution
24. System Architect cannot be skipped
25. Cost Specialist handles missing Azure Specialist output
26. Agent error presents Retry, Skip, and Stop options
27. Retry a failed agent successfully
28. Auto-escalate after 3 failed attempts on non-required agent
29. Required agent exhausts retries without Skip option
30. Stop pipeline sets project to error state
31. Soft timeout triggers progress streaming
32. Hard timeout forces agent termination
33. Agent-specific timeout overrides _(Scenario Outline — 3 examples: cost 15/60, presentation 45/180, architect 30/120)_
34. Reject creating a 4th active project
35. Queue agent invocation when global pool is exhausted
36. Reject invocation when global queue is also full
37. Pipeline completes with only System Architect active
38. Browser disconnects mid-pipeline
39. Agent returns output that fails schema validation
40. Prompt injection is detected in seller input

**From `architecture.feature` (11 scenarios):**
41. Diagram exceeding 30 nodes triggers consolidation
42. Invalid Mermaid syntax triggers auto-retry
43. Mermaid validation fails after all retries
44. Reject input with empty requirements
45. Reject input with invalid project ID
46. Reject modification request exceeding 500 characters
47. Add a component via modification request
48. Replace a service via modification request
49. Remove a component via modification request
50. Modification rejected when it would exceed 30-node limit
51. Export architecture diagram as PNG
52. Export architecture diagram as SVG
53. Export fails when no architecture has been generated
54. Export with unsupported format returns error

**From `cost.feature` (6 scenarios):**
55. API returns zero results for a service SKU
56. Unknown SKU triggers broader query
57. Service not available in selected region
58. Very large estimate exceeding $100K per month
59. Multiple meters per service produce separate line items
60. API pagination follows NextPageLink up to 10 pages

**From `presentation.feature` (12 scenarios):**
61. Envisioning skipped does not affect slide count
62. Reject concurrent generation for same project
63. Unrecoverable generation failure returns 500
64. Force regeneration with query parameter
65. Deck exceeding 20 slides is truncated
66. Long content is truncated per content type rules
67. Download button disabled when no agent outputs exist
68. Regeneration prompt after agent output changes
69. Cost line items exceed 50 items
70. Customer name with special characters sanitized for filename
71. Approximate pricing flagged on cost slides
72. PPTX generation fails and PDF fallback is attempted

**Total: 72 scenarios**

### Definition of Done
- Error recovery flow: Retry / Skip & Continue / Stop presented on agent failure
- Auto-escalation after 3 failed retries (disable Retry button)
- Required agent (System Architect) failure sets project to "error"
- Soft timeout (30s) triggers progress message; hard timeout (120s) terminates agent
- Agent-specific timeout overrides (cost: 15/60, presentation: 45/180)
- Rate limiting enforced at 60 req/min per user with 429 + Retry-After
- Input sanitization strips injection patterns; flagged inputs return error
- Audit logging for all API requests
- Architecture modification flow: add, remove, replace components via delta updates
- Modification re-validates Mermaid syntax and constraint limits
- Architecture diagram exportable as PNG and SVG via `/export/architecture`
- Cost edge cases: unknown SKU fallback, region unavailability, zero-result handling, pagination
- Parameter re-adjustment uses cached prices for non-region changes
- Working agent deactivation with confirmation dialog
- Concurrent tab handling (idempotent deactivation)
- Per-user concurrency limits (3 active projects, 2 concurrent invocations)
- Global agent pool limits (50 concurrent, 100 queue depth)
- Browser disconnect recovery (server-side continuation, state re-render)
- Schema validation failure auto-retry with format instructions
- Prompt injection detection and audit logging
- PPTX slide count enforcement (≤20) with truncation strategy
- PDF fallback export when PPTX generation fails
- Concurrent generation guard (409 with retryAfter)
- All edge cases from EC-1 through EC-25 (chat) and E-1 through E-18 (orchestration)

### API Endpoints
| Endpoint | Method | Status |
|---|---|---|
| `/api/projects/:id/export/architecture` | GET | Implemented (PNG/SVG) |
| All existing endpoints | * | Hardened (rate limiting, sanitization, audit logging, edge cases) |

### Frontend Pages
| Route | Components |
|---|---|
| `/project/:id` | Error recovery modal (Retry/Skip/Stop); working-agent deactivation confirmation dialog; "↓ New messages" scroll pill; queued message indicator; architecture modification UI (suggested chips, shimmer overlay); timeout progress indicators; rate-limit error handling |

---

## Summary

| Increment | Theme | Scenarios | Key Deliverable |
|---|---|---|---|
| **1** | Walking Skeleton | 23 | Login → Create project → Chat → Architecture diagram |
| **2** | Guided Discovery | 28 | Vague idea → Envisioning suggestions → Structured Q&A → Enriched context |
| **3** | Cost & Services | 28 | Architecture → Service selection with SKUs → Cost estimate with adjustable parameters |
| **4** | Business Value & Presentation | 35 | Value assessment → Downloadable PPTX deck → Full pipeline end-to-end |
| **5** | Polish & Hardening | 72 | Error recovery, rate limiting, modification flow, export, edge cases |
| | **Total** | **186** | |

### Cumulative API Coverage

| Endpoint | Inc 1 | Inc 2 | Inc 3 | Inc 4 | Inc 5 |
|---|---|---|---|---|---|
| `POST /api/projects` | ✅ | | | | hardened |
| `GET /api/projects` | ✅ | | | | hardened |
| `GET /api/projects/:id` | ✅ | | | | hardened |
| `POST /api/projects/:id/chat` | ✅ basic | extended | extended | extended | hardened |
| `GET /api/projects/:id/chat` | ✅ basic | | | | paginated |
| `GET /api/projects/:id/agents` | ✅ | | | | hardened |
| `PATCH /api/projects/:id/agents/:agentId` | | ✅ | | | hardened |
| `GET /api/projects/:id/export/pptx` | | | | ✅ | hardened |
| `GET /api/projects/:id/export/architecture` | | | | | ✅ |
