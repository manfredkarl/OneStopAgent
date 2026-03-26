# Product Requirements Document — OneStopAgent

## 1. Overview

OneStopAgent is an internal Microsoft web application that provides Azure sellers with a guided, chat-based interface to transform a customer idea — or no idea at all — into a fully scoped Azure solution. A central **Project Manager Agent** orchestrates a team of specialized AI agents that collaboratively produce architecture diagrams, cost estimates, business value analyses, and a ready-to-present PowerPoint deck.

The application is built on **Azure AI Foundry** using an agent-based architecture. It targets Microsoft field sellers, solution architects, and customer-facing teams who need to rapidly scope and present Azure opportunities.

## 2. Goals

- Reduce the time from initial customer conversation to a presentable Azure solution from days to minutes.
- Provide guided discovery so sellers can scope opportunities even when the customer has no clear technical direction.
- Deliver consistent, high-quality outputs: architecture diagrams, cost estimates, business value assessments, and presentation decks.
- Leverage authoritative Microsoft sources (Microsoft Learn, Azure Pricing APIs) for accuracy.
- Enable sellers to control the process by selecting which agents participate and reviewing outputs at each stage.

## 3. User Stories

### US-1: Start a New Project
**As an** Azure seller,  
**I want to** create a new project by describing a customer scenario or need,  
**So that** I can begin scoping an Azure solution.

**Acceptance Criteria:**
- The seller enters a free-text description of the customer opportunity in the chat interface.
- The Project Manager Agent acknowledges the input and determines which agents to activate.
- If the description is too vague to proceed, the PM Agent routes to the Envisioning Agent first.
- A new project workspace is created with a unique identifier and associated with the authenticated user.
- The seller can see all available agents and their status (Idle / Working / Error) in a sidebar.
- If the project creation fails (e.g., storage unavailable), the user sees an actionable error message and can retry.

### US-2: Guided Envisioning
**As an** Azure seller,  
**I want to** receive AI-suggested use cases and value drivers when my customer's needs are unclear,  
**So that** I can shape the opportunity before designing a solution.

**Acceptance Criteria:**
- The Envisioning Agent presents relevant scenarios (e.g., "Digital Commerce Platform", "Digital Transformation using AI") based on industry and keywords.
- The agent surfaces sample estimates from past engagements (simulated knowledge base) and reference architectures as selectable options.
- Each suggestion includes a brief description and a link to supporting material.
- The seller can select one or more items (checkboxes) and click "Proceed with Selected Items" to advance.
- The seller can also provide additional context or reject all suggestions and describe their own direction.
- If no suggestions match the customer's industry or keywords, the agent explains why and prompts the seller to provide more context.

### US-3: Architecture Generation
**As an** Azure seller,  
**I want** an architecture diagram generated for the selected use case,  
**So that** I can show the customer a technical solution design.

**Acceptance Criteria:**
- The System Architect Agent generates a Mermaid diagram representing the proposed Azure architecture.
- The diagram is rendered visually in the chat interface.
- The architecture is grounded in Azure documentation retrieved via the [Microsoft Learn MCP Server](https://learn.microsoft.com/en-us/azure/ai-services/agents/how-to/tools/connected-agents).
- Key components are listed with descriptions (e.g., "Azure App Service — Web hosting", "Azure SQL — Relational data store").
- The seller can request modifications (e.g., "add a caching layer", "replace Cosmos DB with SQL").
- The diagram is exportable as an image (PNG/SVG).
- If the Microsoft Learn MCP Server is unavailable, the agent falls back to its built-in knowledge and flags outputs as "unverified — MCP source unavailable."
- If the generated Mermaid syntax is invalid, the agent retries generation up to 2 times before presenting the raw Mermaid code with an error explanation.

### US-4: Azure Service Selection
**As an** Azure seller,  
**I want** detailed guidance on which Azure services fit the architecture,  
**So that** I can confidently discuss service choices with the customer.

**Acceptance Criteria:**
- The Azure Specialist Agent maps each architecture component to specific Azure services.
- For each service, the agent provides: SKU recommendation, region availability, and key capabilities.
- Where alternatives exist, the agent presents options with trade-offs (e.g., "Azure SQL vs. Cosmos DB: relational vs. NoSQL").
- Recommendations are backed by Microsoft Learn documentation references.
- If the MCP Server is unavailable, the agent proceeds with cached or built-in recommendations and flags them as "unverified."

### US-5: Cost Estimation
**As an** Azure seller,  
**I want** a cost estimate based on the proposed architecture,  
**So that** I can discuss pricing with the customer.

**Acceptance Criteria:**
- The Cost Specialist Agent calls the [Azure Retail Prices REST API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) to retrieve current pricing.
- The estimate is broken down by service, SKU, and region.
- The seller can adjust parameters (e.g., number of users, data volume, region) and recalculate.
- Monthly and annual cost projections are presented in a table format.
- All prices are displayed in USD; currency is stated explicitly in all outputs.
- Assumptions (e.g., "10,000 concurrent users, 15-minute average session") are listed explicitly.
- If the Azure Retail Prices API is unavailable or returns an error, the agent displays a clear warning and offers to retry or proceed with cached/indicative pricing clearly marked as "approximate."
- The estimate does not include Enterprise Agreement (EA) or CSP discounts in MVP; this limitation is stated on the output.

### US-6: Business Value Assessment
**As an** Azure seller,  
**I want** an ROI and business impact analysis for the proposed solution,  
**So that** I can build a business case for the customer.

**Acceptance Criteria:**
- The Business Value Agent evaluates the solution against common value drivers: cost savings, revenue growth, operational efficiency, time-to-market, risk reduction.
- The agent produces quantified estimates where possible (e.g., "Estimated 30% reduction in infrastructure management overhead").
- Industry benchmarks and comparable customer outcomes are referenced (simulated knowledge base).
- Output includes a value summary suitable for executive audiences.
- Quantified estimates are clearly labeled as projections, not guarantees.

### US-7: Presentation Generation
**As an** Azure seller,  
**I want** a PowerPoint deck generated from all the outputs,  
**So that** I can present the solution to the customer.

**Acceptance Criteria:**
- The Presentation Agent compiles outputs from all preceding agents into a structured PowerPoint file.
- The deck includes: executive summary, use case description, architecture diagram, service details, cost breakdown, and business value assessment.
- The deck uses a clean, professional template (Microsoft-branded or neutral).
- The seller can download the `.pptx` file from the chat interface.
- The seller can regenerate the deck after making changes to any preceding agent's output.
- If some agents were skipped (deactivated), the deck omits those sections and notes which sections are missing.
- The deck generation fails gracefully if the architecture diagram cannot be converted to an embeddable image; the slide is included with a placeholder and a text description.

### US-8: Agent Selection and Control
**As an** Azure seller,  
**I want to** choose which agents participate in my project,  
**So that** I can skip steps that are not relevant (e.g., skip envisioning if I already know the use case).

**Acceptance Criteria:**
- The sidebar displays all available agents with their current status.
- The seller can activate or deactivate agents before or during the flow.
- Deactivating an agent that is currently working cancels its in-progress task; the seller is warned before confirmation.
- The Project Manager Agent adjusts the pipeline based on which agents are active.
- At minimum, the System Architect Agent must be active to produce any output. The UI prevents deactivating it and displays a tooltip explaining why.
- The seller can invoke any agent on-demand outside the guided flow (e.g., re-run cost estimation with new parameters).

### US-9: Guided Questioning
**As an** Azure seller,  
**I want** the system to ask me structured questions to gather requirements,  
**So that** agents have sufficient context to produce accurate outputs.

**Acceptance Criteria:**
- The Project Manager Agent asks structured questions covering: target users, expected scale, geographic requirements, compliance needs, integration points, timeline, and value drivers.
- Questions are asked incrementally — not all at once — in a conversational flow.
- The seller can skip questions; the agent proceeds with reasonable defaults and flags assumptions.
- Answers are persisted in the project context and available to all downstream agents.
- The system asks no more than 10 questions per session before proceeding; the seller can end questioning early by saying "proceed" or clicking a "Start Agents" button.

## 4. Functional Requirements

### FR-1: Agent Orchestration API
| Endpoint | Method | Description |
|---|---|---|
| `/api/projects` | GET | List all projects for the authenticated user. Returns 200 with `[{ projectId, description, status, updatedAt }]`. |
| `/api/projects` | POST | Create a new project. Body: `{ description, customerName? }`. Returns 201 with `{ projectId }`. |
| `/api/projects/:id` | GET | Retrieve project state including all agent outputs. Returns 200. |
| `/api/projects/:id/chat` | POST | Send a message to the orchestrator. Body: `{ message, targetAgent? }`. Returns 200 with agent response. |
| `/api/projects/:id/chat` | GET | Retrieve chat history for a project. Query params: `limit`, `before` (cursor). Returns 200. |
| `/api/projects/:id/agents` | GET | List all agents and their status for this project. Returns 200. |
| `/api/projects/:id/agents/:agentId` | PATCH | Activate or deactivate an agent. Body: `{ active: boolean }`. Returns 200. |
| `/api/projects/:id/export/pptx` | GET | Generate and download the PowerPoint deck. Returns 200 with binary `.pptx`. |
| `/api/projects/:id/export/architecture` | GET | Export architecture diagram as PNG/SVG. Returns 200 with binary image. |

### FR-2: Agent Definitions

| Agent | Role | Key Integrations |
|---|---|---|
| **Project Manager** | Orchestrates flow, asks structured questions, routes to specialists | All other agents |
| **Envisioning** | Suggests use cases, value drivers, reference scenarios | Internal knowledge base (simulated) |
| **System Architect** | Generates Mermaid architecture diagrams, maps components | Microsoft Learn MCP Server |
| **Azure Specialist** | Selects Azure services, recommends SKUs, provides trade-offs | Microsoft Learn MCP Server |
| **Cost Specialist** | Estimates costs based on architecture and parameters | Azure Retail Prices REST API |
| **Business Value** | Evaluates ROI, business impact, produces value summary | Internal knowledge base (simulated) |
| **Presentation** | Compiles all outputs into a downloadable PowerPoint deck | All agent outputs, PPTX generation library |

### FR-3: Agent Pipeline

The default sequential flow is:

```
User Input → [Envisioning*] → System Architect → Azure Specialist → Cost Specialist → Business Value → Presentation
```

\* Envisioning is invoked only when the use case is unclear or the seller explicitly activates it.

At each stage:
1. The active agent produces output and renders it in the chat.
2. The seller reviews, can request modifications, or approves (explicit "Approve & Continue" button).
3. The Project Manager Agent advances to the next agent.

**Error handling:** If an agent fails (timeout, API error, or internal error):
- The agent's status changes to Error (red dot in sidebar).
- The PM Agent notifies the seller with the failure reason and offers: (a) retry the failed agent, (b) skip and continue to the next agent, or (c) stop the pipeline.
- The project status is set to `'error'` only if the failure is unrecoverable (e.g., System Architect fails — no downstream agents can proceed).

### FR-4: Data Model

- **Project**: `{ id: string (UUID), userId: string, description: string, customerName?: string, activeAgents: string[], context: ProjectContext, status: 'in_progress' | 'completed' | 'error', createdAt: Date, updatedAt: Date }`
- **ProjectContext**: `{ requirements: Record<string, string>, architecture?: ArchitectureOutput, services?: ServiceSelection[], costEstimate?: CostEstimate, businessValue?: ValueAssessment, envisioningSelections?: string[] }`
- **ArchitectureOutput**: `{ mermaidCode: string, components: { name: string, azureService: string, description: string }[], narrative: string }`
- **ServiceSelection**: `{ componentName: string, serviceName: string, sku: string, region: string, capabilities: string[], alternatives?: { serviceName: string, tradeOff: string }[] }`
- **CostEstimate**: `{ currency: 'USD', items: { serviceName: string, sku: string, region: string, monthlyCost: number }[], totalMonthly: number, totalAnnual: number, assumptions: string[], generatedAt: Date, pricingSource: 'live' | 'cached' | 'approximate' }`
- **ValueAssessment**: `{ drivers: { name: string, impact: string, quantifiedEstimate?: string }[], executiveSummary: string, benchmarks: string[] }`
- **ChatMessage**: `{ id: string, projectId: string, role: 'user' | 'agent', agentId?: string, content: string, metadata?: Record<string, unknown>, timestamp: Date }`
- Storage: Azure Cosmos DB (or in-memory for MVP).

### FR-5: Frontend Pages

| Route | Description | Auth Required |
|---|---|---|
| `/` | Landing page — create new project or resume existing | Yes |
| `/project/:id` | Main chat interface with agent sidebar and output canvas | Yes |
| `/projects` | List of all projects for the current user | Yes |

### FR-6: Chat Interface

- Left sidebar: Agent list with avatars, names, and status indicators (Idle = grey dot, Working = animated blue dot, Error = red dot).
- Main area: Scrollable chat thread with agent-branded message cards.
- Agent responses may contain: plain text, Mermaid diagrams (rendered), tables, selectable option lists with checkboxes, and a "Proceed with Selected Items" action button.
- User input: free-text message box at the bottom.

### FR-7: External Integrations

| Integration | Purpose | Reference |
|---|---|---|
| **Microsoft Learn MCP Server** | Retrieve Azure documentation, reference architectures, best practices | [Overview](https://learn.microsoft.com/en-us/azure/ai-services/agents/how-to/tools/connected-agents) |
| **Azure Retail Prices REST API** | Fetch current Azure service pricing by SKU and region | [API Docs](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) |
| **Azure AI Foundry** | Host and orchestrate AI agents | Platform dependency |
| **Internal Knowledge Base** | Simulated source for envisioning scenarios and business benchmarks | Mock data in MVP |

### FR-8: Authentication & Authorization
- Authentication via Microsoft Entra ID (SSO with @microsoft.com accounts).
- All users have the same role (seller). No role hierarchy in MVP.
- Projects are scoped to the authenticated user; API endpoints enforce ownership checks — a user cannot access another user's project (returns 403).
- API endpoints require a valid Bearer token (JWT) in the `Authorization` header; expired or missing tokens return 401.
- User input is sanitized before being forwarded to AI agents to mitigate prompt injection risks.
- All API endpoints are rate-limited to 60 requests per minute per user; exceeding the limit returns 429.
- Agent interactions and project access events are logged for audit purposes (user ID, action, timestamp).

## 5. Non-Functional Requirements

- **NFR-1:** Agent response time < 30 seconds for any single agent step. If an agent exceeds 30 seconds, the UI displays a progress indicator and the operation continues for up to 120 seconds before timing out.
- **NFR-2:** Cost estimation API calls must complete within 10 seconds. On timeout, the agent retries once before falling back to cached pricing.
- **NFR-3:** The chat interface must render within 2 seconds on initial load.
- **NFR-4:** Support 100 concurrent users with no degradation.
- **NFR-5:** All agent outputs must be persisted — no data loss on page refresh or browser close.
- **NFR-6:** The application must work on latest Edge, Chrome, Firefox, and Safari.
- **NFR-7:** WCAG 2.1 AA accessibility compliance for all UI elements.
- **NFR-8:** All data stays within Microsoft tenant boundaries; no external LLM data leakage. Azure AI Foundry models must be deployed within the tenant's Azure subscription.
- **NFR-9:** Target 99.5% availability during business hours (Mon–Fri, 6 AM–8 PM PST). Planned maintenance windows are excluded.
- **NFR-10:** Project data is retained for 12 months. Users can manually delete their own projects at any time.

## 6. Out of Scope

- Customer-facing access (internal Microsoft users only).
- Real CRM integration (no Dynamics 365 connection in MVP).
- Multi-language support (English only).
- Collaborative editing (single user per project).
- Version history or undo for agent outputs.
- Custom agent creation by sellers.
- Real internal knowledge base integration (simulated/mock data for MVP).

## 7. Risks & Mitigations

| # | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| R-1 | Agent response times exceed 30s for complex architectures involving multiple MCP lookups | Degraded UX; sellers abandon the tool | Medium | Stream partial results to the chat (show progress). Allow 120s hard timeout with user-visible progress bar. Pre-cache common reference architectures. |
| R-2 | Azure Retail Prices API unavailable or rate-limited | Cost estimation fails; incomplete outputs | Low | Cache recent pricing data (TTL: 24 hours). Display "approximate" badge on cached results. Implement exponential backoff retry (max 3 attempts). |
| R-3 | Microsoft Learn MCP Server unavailable | Architecture and service recommendations are ungrounded | Low | Fall back to agent's built-in knowledge. Flag outputs as "unverified" so sellers know to validate. |
| R-4 | Prompt injection via user input manipulates agent behavior | Incorrect or harmful outputs; data leakage | Medium | Sanitize user inputs. Use system prompts with clear boundaries. Monitor agent outputs for anomalies. |
| R-5 | Generated Mermaid diagrams are syntactically invalid or too complex to render | Broken UI; no architecture visual | Medium | Validate Mermaid syntax server-side before sending to client. Retry generation (max 2 retries). Cap diagram complexity (max 30 nodes). |
| R-6 | Concurrent users exhaust Azure AI Foundry agent pool | Queued requests, timeouts | Medium | Implement request queuing with fair scheduling. Set per-user concurrency limits. Scale agent pool based on demand (auto-scale policy). |
| R-7 | PPTX generation fails for large or complex outputs | Seller cannot download presentation | Low | Set maximum slide count (20 slides). Truncate verbose content. Provide fallback PDF export. |

## 8. Future Considerations

- **CRM Integration:** Connect to Dynamics 365 to pre-populate customer context and log scoped opportunities.
- **Collaborative Projects:** Allow multiple sellers to contribute to the same project in real time.
- **Custom Agents:** Let sellers create or configure specialized agents for industry verticals.
- **Customer Portal:** A read-only view where customers can review the proposed solution.
- **Real Knowledge Base:** Replace simulated envisioning data with actual Microsoft case studies, success stories, and reference implementations.
- **Azure Pricing Calculator Integration:** Deep-link or embed the official Azure Pricing Calculator for detailed estimation.
- **Feedback Loop:** Track which generated solutions convert to closed deals to improve agent recommendations over time.

## 9. Technical Stack

- **Frontend:** Next.js (App Router, TypeScript, Tailwind CSS)
- **Backend:** Express.js (TypeScript)
- **AI Platform:** Azure AI Foundry (agent orchestration)
- **Agent Framework:** Multi-agent architecture with Project Manager as orchestrator
- **Diagrams:** Mermaid.js (rendered client-side)
- **Presentation Generation:** PptxGenJS or officegen (server-side PPTX creation)
- **External APIs:** Azure Retail Prices REST API, Microsoft Learn MCP Server
- **Authentication:** Microsoft Entra ID (MSAL)
- **Storage:** Azure Cosmos DB (in-memory Map for MVP)
- **Deployment:** Azure Container Apps via AZD
