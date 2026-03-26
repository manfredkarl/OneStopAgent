# OneStopAgent — Shortcomings & Gaps

## What This App Should Do

An Azure seller opens the app, describes a customer need, and gets:
1. **Architecture** — a real Mermaid diagram of Azure services that makes sense for the use case
2. **Cost Estimate** — real pricing from the Azure Retail Prices API based on the architecture
3. **Business Value** — an ROI/impact assessment grounded in the architecture and costs
4. **PowerPoint** — a downloadable deck compiling everything above

The PM Agent orchestrates this by having a short conversation, then handing off to specialist agents sequentially. The seller approves each step or gives feedback.

---

## What Actually Works Today

- ✅ Project creation
- ✅ PM Agent asks questions (LLM-driven)
- ✅ Pipeline runs agents sequentially
- ✅ "approve" text advances the pipeline
- ✅ Backend generates agent outputs and stores them
- ✅ PPTX generation (PptxGenJS)

## What Is Broken (Functionality)

### 1. Agent outputs are invisible to the user
**The #1 problem.** The pipeline runs agents and stores outputs in chat history, but the HTTP response only returns the gate message. The frontend appends only the returned message, so users see "✅ Architect completed. Approve to continue" but never see the actual architecture diagram, cost table, or value assessment.

**Root cause:** `sendMessage()` returns `ChatMessage` (single) but the pipeline produces multiple messages (announcement + output + gate). Only the gate comes back.

**Status:** Fix in progress (`fix-pipeline-outputs` agent running).

### 2. "Proceed with Selected Items" doesn't work
When the envisioning agent shows scenarios and the user selects items and clicks proceed, the message is sent as plain text ("I selected these items: ..."). The backend treats this as a "request changes" feedback because the pipeline is in `gated` status and the message doesn't match any approve keywords.

**Root cause:** No special handling for selection messages. The `handlePipelinePhase` method falls through to `handleRequestChanges`.

**Fix needed:** Detect selection messages (they contain "selected" + item IDs) and treat them as pipeline advancement, storing the selections in context.

### 3. 10+ interactive UI components have unwired callbacks
The ChatThread renders buttons, inputs, and interactive components — but the project page never passes the callback handlers. Clicking does nothing silently.

| Component | Callback | Broken? |
|-----------|----------|---------|
| SelectableList | `onSelectableListProceed` | ✅ Recently wired |
| GuidedQuestions | `onGuidedAnswer`, `onGuidedSkip`, `onGuidedProceed` | ❌ NOT WIRED |
| RejectionInput | `onRejectionSubmit` | ❌ NOT WIRED |
| ArchitectureModification | `onModifyArchitecture` | ❌ NOT WIRED |
| ParameterAdjustment | `onRecalculateCost` | ❌ NOT WIRED |
| ErrorRecoveryModal | `onErrorRetry`, `onErrorSkip`, `onErrorStop` | ❌ NOT WIRED |
| Action buttons | `onActionButton` | ❌ NOT WIRED |

**Fix needed:** Wire ALL callbacks in `project/[id]/page.tsx`. Each should send the appropriate message through `sendMessage()`.

### 4. Agent toggle response shape mismatch
Backend PATCH `/agents/{agentId}` returns a single `AgentStatus` object. Frontend expects `AgentStatus[]` or `{ agents: AgentStatus[] }`. Falls back to an extra GET request, which is fragile.

**Fix needed:** Backend should return `{ agents: AgentStatus[] }` (the full list) from the PATCH endpoint.

### 5. Cost Specialist doesn't actually call the Azure Retail Prices API
The cost agent has mock pricing fallback that runs silently when the real API fails or times out. The mock prices are hardcoded and likely outdated. Users get "live" pricing that's actually from a static dictionary.

**Fix needed:** Actually call `https://prices.azure.com/api/retail/prices` with proper OData filters. The API requires no authentication. Fall back to mock ONLY on real failure, and clearly label the output as "approximate".

### 6. Architect generates template diagrams, not contextual ones
When the LLM call fails (which happens often due to timeouts), the architect falls back to a hardcoded 4-component template (App Service, SQL, Key Vault, App Insights) regardless of what the user described.

**Fix needed:** The LLM prompt needs to be more specific. The fallback should at least vary based on detected use case keywords (e-commerce vs healthcare vs IoT).

### 7. No shared memory / conversation thread between agents
Each agent gets a snapshot of context at invocation time. Agents don't see each other's reasoning, only outputs. The PM Agent's conversation history is not available to the architect. The architect's component descriptions are not available to the cost agent in a meaningful way.

**Fix needed:** Build a shared context object that accumulates through the pipeline. Each agent reads from and writes to it. Pass the full context (including PM conversation summary) to each agent's LLM prompt.

### 8. Envisioning selections don't influence the architecture
When a user selects scenarios/reference architectures from the envisioning suggestions, those selections are stored but never passed to the architect agent's LLM prompt. The architect generates a generic architecture regardless.

**Fix needed:** Include envisioning selections in the architect's prompt: "The user selected these reference scenarios: [list]. Design an architecture that addresses these use cases."

### 9. No streaming output
All agent responses are synchronous — the user waits 10-30 seconds with no feedback while the LLM generates. For complex architectures or cost calculations, this feels broken.

**Fix needed:** Implement Server-Sent Events (SSE) or chunked responses so the user sees output being generated in real-time.

### 10. Pipeline completion doesn't produce a useful summary
When all agents complete, the user gets a generic "🎉 Complete!" message but no actionable summary of what was produced. No download button for the PPTX unless they scroll up.

**Fix needed:** The completion message should include: architecture component count, total monthly cost, key value drivers, and a prominent download button.

### 11. The PM Agent sometimes asks irrelevant questions
Despite prompt improvements, the PM still occasionally asks generic questions that the user already answered in their description. The conversation doesn't feel intelligent.

**Fix needed:** The PM prompt must explicitly list what's already known (extracted from the user's description) and only ask about gaps.

### 12. No way to go back or re-run a specific agent
Once you approve past an agent, you can't go back. If you want to change the architecture after seeing costs, you have to start over.

**Fix needed:** Allow the user to say "re-run architect" or click on a previous agent's output to modify it, with downstream stages automatically re-running.

---

## Architecture Issues

### A. Tight coupling — ChatService is 1600+ lines
All orchestration, all agent invocation, all message formatting, all pipeline state management lives in one massive file. This makes it nearly impossible to fix individual issues without breaking something else.

### B. In-memory only — no persistence
Everything is in JavaScript Maps. Server restart = total data loss. Not suitable for any real usage.

### C. No observability
No logging of agent decisions, no tracing of LLM calls, no metrics on success/failure rates. When something breaks, there's no way to diagnose it.

### D. Auth is a stub
The `x-user-id` header is not real authentication. Any user can access any project.

---

## Priority Order for Fixes

1. **Make agent outputs visible** (fix sendMessage to return message arrays)
2. **Wire all callbacks** (10+ broken buttons)
3. **Fix proceed/selection flow** (envisioning → architect transition)
4. **Pass shared context between agents** (envisioning → architect → cost chain)
5. **Actually call Azure Pricing API** (cost agent)
6. **Improve architect LLM prompts** (contextual diagrams)
7. **Fix agent toggle response** (shape mismatch)
8. **Add streaming** (SSE for agent responses)
9. **Persistence** (Cosmos DB or at minimum SQLite)
10. **Real auth** (Entra ID)
