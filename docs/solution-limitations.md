# Solution Limitations & Improvement Roadmap

> **Date**: 2026-04-06  
> **Scope**: Full analysis of OneStopAgent UX flow, routing, agent quality, state management  
> **Method**: Deep codebase analysis tracing actual execution paths with file:line references

---

## Executive Summary

OneStopAgent delivers a functional multi-agent pipeline but has **fundamental UX limitations** that prevent natural conversational interaction. The core issue: **the system is a rigid pipeline, not a conversational agent**. Users cannot freely interact with individual agents, ask out-of-flow questions, or iterate naturally on agent suggestions.

**Key numbers**: 14 routing limitations, 6 agent quality gaps, 8 state/context issues, 4 interaction flow problems.

---

## 1. Routing & Intent Classification Limitations

### 1.1 Single Intent Classification
**File**: `pm_agent.py:116-130`  
The LLM classifier returns exactly **one intent** per message. Mixed signals are lost.

**Example**: User says *"That looks good but I'm worried about cost"*  
- **Expected**: Approve current step + flag cost concern  
- **Actual**: Classified as single intent (likely INPUT or PROCEED). Cost concern lost.

**8 recognized intents**: PROCEED, REFINE, SKIP, FAST_RUN, BRAINSTORM, ITERATION, QUESTION, INPUT

### 1.2 No Direct Agent Addressing
**Impact**: 🔴 HIGH  
Users cannot say "ask the cost agent about reserved instances" or "@architect, consider CDN."  
No `@agent` syntax, no routing-by-mention. The only way to target a specific agent is through iteration keywords after the pipeline completes.

### 1.3 Out-of-Flow Messages Blocked During Execution
**File**: `maf_orchestrator.py:281-282`  
During agent execution, non-QUESTION intents get: *"I'll address that after the current step completes."*

**Scenario**: Architect is running → user says "actually make it cheaper" → message is **deferred, not queued**. The user must wait for approval, then re-state their request.

### 1.4 Phase-Blind Intent Classifier
**File**: `pm_agent.py:81-94`  
The intent classifier uses the **same system prompt** regardless of current phase. It doesn't know whether the user is in plan review, mid-execution, or post-completion. This causes misclassification of context-dependent messages.

### 1.5 Keyword-First Iteration Routing
**File**: `pm_agent.py:39-70` (ITERATION_MAPPING)  
Iteration routing uses **substring matching** on ~25 keywords. Limitations:
- First keyword match wins — "secure and cheaper" routes to "cheaper" agents only
- No semantic understanding — "cost-effective" won't match "cheaper"
- Unmatched iterations default to re-running **all 5 agents** (wasteful)

### 1.6 No Backward Navigation
**File**: `maf_orchestrator.py:531` (`_PIPELINE_ORDER`)  
The pipeline is strictly forward: `business_value → architect → cost → roi → presentation`.

- ❌ Cannot jump to a specific step (e.g., "show me just the ROI")
- ❌ Cannot re-run a single agent without its downstream chain
- ❌ "retry cost" forces re-run of cost + ROI + presentation

**Fix suggestions**:
1. Add phase context to the intent classifier prompt
2. Support multi-intent classification (return array of intents)
3. Implement `@agent_name` mention syntax for direct addressing
4. Queue out-of-flow messages during execution and process after step completes
5. Add semantic intent matching (embeddings) alongside keyword matching
6. Allow single-agent re-runs without forcing downstream cascade

---

## 2. Agent Interaction & Follow-Up Limitations

### 2.1 Agent Suggestions Are Non-Functional
**Impact**: 🔴 CRITICAL UX ISSUE  
When agents make suggestions (e.g., Architect: *"Say 'high availability' to model HA costs"*), the user's response **does NOT re-route to that agent**. Instead:

1. User responds to suggestion
2. System checks for approval keywords ("skip", "refine", "redo")
3. "high availability" → no match → treated as generic "proceed"
4. **Next agent starts. Previous agent never re-runs.**

The only working mid-pipeline interaction is the **two-phase assumptions flow** (Cost and BV agents' "needs_input" phase), which correctly routes responses back to the same agent.

### 2.2 Approval Flow Is Fragile
**File**: `maf_orchestrator.py:264-283`  
After each agent completes, the system shows output and waits for approval. But:

- **Approval detection is keyword-based**: must say "proceed", "skip", "refine", etc.
- **Feedback mixed with approval is ambiguous**: "Looks good, but add caching" → classified as INPUT, not PROCEED+REFINE
- **No structured approval UI**: the frontend doesn't show dedicated approve/reject/refine buttons for agent outputs

### 2.3 No Conversational Back-and-Forth With Agents
Users cannot have a multi-turn conversation with a specific agent. Each agent is **one-shot** (or two-shot for assumption collection). After an agent produces output:
- User can approve → next agent
- User can type "retry [agent]" → re-runs with new context
- User **cannot** ask follow-up questions to the same agent

### 2.4 Iteration Only Works in "Done" Phase
**File**: `maf_orchestrator.py:331-366`  
The ITERATION intent is only handled when `phase == "done"`. During execution:
- User says "make it cheaper" → *"I'll address that after the current step completes."*
- User must wait for entire pipeline to finish, then re-iterate

**Fix suggestions**:
1. Make agent suggestions actionable — parse and route suggestion responses back to the originating agent
2. Add structured approval UI (approve/refine/skip buttons)
3. Enable conversational mode — allow multi-turn exchanges with the currently-active agent
4. Process ITERATION intents during execution by queuing for the next appropriate agent
5. Add a "talk to [agent]" command that opens a dialogue with a specific agent

---

## 3. Individual Agent Quality Gaps

### 3.1 Architect Agent
- **MCP dependency**: Architecture quality depends on MCP server availability. When MCP is down, falls back to hardcoded reference patterns (`_FALLBACK_PATTERNS` in architect_agent.py). These are generic and may not match the customer's scenario.
- **No existing environment awareness**: Doesn't consider what Azure services the customer already uses. Suggests greenfield architectures even when the customer has existing infrastructure.
- **Mermaid diagram quality**: LLM-generated Mermaid code sometimes produces rendering errors. The `_cap_mermaid_nodes()` function limits complexity but can over-simplify.

### 3.2 Cost Agent
- **~30% live pricing**: Of all services in a typical architecture, only ~30% get live prices from the Azure Retail Prices API. The rest fall back to `ESTIMATED_PRICES` (68+ hardcoded entries in pricing.py).
- **No reservations/savings plans**: Estimates are based on pay-as-you-go pricing only. No consideration for Reserved Instances, Savings Plans, or Hybrid Benefit — which can reduce costs 30-70%.
- **Misleading confidence labels**: Cost confidence is presented as "Moderate" or "High" even when 40-60% of services use hardcoded estimates. This undermines credibility.
- **No multi-region pricing**: Uses a single region (default: eastus). Doesn't model multi-region architectures.

### 3.3 Business Value Agent
- **Generic methodologies**: Value drivers use industry-standard formulas but lack customer-specific calibration. Productivity savings calculations are template-based.
- **No industry benchmarks**: Despite having company intelligence, BV calculations don't reference industry-specific benchmark data.
- **Source labeling is inconsistent**: PR #25 fixed contradictions between "clearly mark sources" and "cite specific case studies", but the agent still mixes real and generated data.

### 3.4 ROI Agent
- **Unvalidated adoption curves**: Uses assumed adoption rates (Year 1: 60%, Year 2: 80%, Year 3: 95%) without customer input or industry validation.
- **Missing implementation costs**: ROI calculations don't account for migration costs, training, change management, or opportunity costs.
- **Estimated baselines**: When current spend isn't provided, the agent estimates baselines from architecture costs — circular reasoning.

### 3.5 Presentation Agent
- **LLM-generated slide content**: All text is generated by the LLM, not from structured data. Quality varies significantly.
- **Limited customer tailoring**: Despite recent improvements (customer name, challenges, Azure context), slides still feel template-driven rather than bespoke.
- **Node.js dependency**: PowerPoint generation requires Node.js. If Node fails, the entire pipeline's final output is lost.

### 3.6 PM / Envisioning Agent
- **No domain knowledge**: Brainstorming doesn't integrate real industry data, Microsoft case studies, or Azure solution accelerators. Suggestions come purely from LLM knowledge.
- **Azure fit assessment is subjective**: The "strong/weak/unclear" classification has no structured criteria or scoring model.

**Fix suggestions**:
1. Add reservation/savings plan modeling to cost estimates
2. Clearly label estimated vs live pricing in output and UI
3. Integrate industry benchmark data for BV calculations
4. Allow user input on adoption curves for ROI
5. Include implementation costs in ROI model
6. Add structured domain knowledge for envisioning (industry-specific solution templates)

---

## 4. State & Context Limitations

### 4.1 Zero Persistence — All Data Lost on Restart
**File**: `services/project_store.py:8-58`  
`ProjectStore` is a Python dict in memory. **Server restart = all projects, conversations, and agent outputs deleted.** No database, no file-based persistence, no checkpointing.

| Scenario | Data Lost | Recovery |
|----------|-----------|----------|
| Server restart / deploy | ALL projects + chat | ❌ None |
| Pipeline timeout (600s) | Workflow deleted, state incomplete | ❌ None |
| Process crash | Everything | ❌ None |
| Page refresh | Nothing (same project_id) | ✅ OK |

### 4.2 Cannot Scale Horizontally
**File**: `main.py:72` (global singletons)  
`orchestrator = MAFOrchestrator()` and `store = ProjectStore()` are in-process singletons. Multiple replicas = users hitting different pods see different/missing state. **Single-instance only.**

### 4.3 Agents Don't See Conversation History
**File**: `agents/state.py:233-279`  
Each agent receives `state.to_context_string()` — a summary of structured fields (user input, assumptions, prior agent outputs). But agents **never see the full chat history**. This means:
- Agent doesn't know what the user discussed in earlier turns
- Feedback stored as plain text in `state.clarifications`, not structured
- Multi-turn context within an agent session is lost

### 4.4 Context Gaps Between Agents

| Agent | Receives | Missing |
|-------|----------|---------|
| Architect | User input, industry, assumptions, patterns | Cost constraints, budget limits |
| Cost | Architecture, assumptions, user count | Budget ceiling, BV drivers |
| Business Value | Assumptions, architecture | Cost data, ROI targets |
| ROI | Full state (all fields) | Implementation timeline details |
| Presentation | Full state | Customer's specific pain points from chat |

### 4.5 Shared Assumptions Are Locked Once
**File**: `maf_orchestrator.py:244-250`  
Assumptions are set before the pipeline starts and **never updated during execution**. If the user provides new information mid-flow (e.g., "actually we have 5000 users, not 1000"), it's stored in `clarifications` as text but **assumptions fields remain unchanged**.

### 4.6 Unused Concurrency Guards
**File**: `maf_orchestrator.py:50-73`  
Per-project asyncio locks are defined (`self._locks`) but **never acquired** in any method. Concurrent messages to the same project could cause race conditions.

**Fix suggestions**:
1. Add persistence layer (Redis, CosmosDB, or SQLite) for project state and chat history
2. Pass relevant chat history to agents for better context
3. Allow assumption updates mid-pipeline (with agent re-run)
4. Add state checkpointing before each agent for resume capability
5. Use the defined per-project locks for concurrent message handling
6. For horizontal scaling, use a shared state store (Redis/Cosmos)

---

## 5. Complete Routing Decision Tree

```
Message received
├─ [phase = "new"]
│  └─ → Brainstorm greeting → plan_shown
│
├─ [phase = "plan_shown"]
│  ├─ Intent = PROCEED/FAST_RUN → collecting_assumptions → executing
│  ├─ Intent = SKIP → "What else..."
│  └─ Intent = OTHER → Stored in clarifications (NO ACTION)
│
├─ [phase = "executing"]
│  ├─ pending_requests exist
│  │  └─ → Feed to workflow (PROCEED/SKIP/REFINE only)
│  ├─ Intent = QUESTION
│  │  └─ → LLM answers from state context (no routing)
│  └─ Intent = OTHER
│     └─ → "I'll address that after the current step completes."
│
└─ [phase = "done"]
   ├─ "retry [agent]" pattern matched
   │  └─ → Re-run agent + all downstream
   ├─ Intent = ITERATION
   │  ├─ Keyword matched → ITERATION_MAPPING agents
   │  └─ No keyword → ALL 5 agents re-run
   ├─ Intent = BRAINSTORM
   │  └─ → Full reset → phase="new"
   └─ Intent = OTHER
      └─ → LLM generic response (no routing)
```

**Key insight**: The only paths that route to specific agents are ITERATION (done phase) and assumption collection (executing phase with pending_requests). Everything else is either deferred or answered generically.

---

## 6. Improvement Roadmap

### Phase 1 — Critical UX Fixes
1. **Make agent suggestions actionable**: When an agent outputs a suggestion, parse it and create a quick-action that routes back to that agent
2. **Add structured approval UI**: Approve/Refine/Skip buttons instead of keyword parsing
3. **Queue out-of-flow messages**: Instead of "I'll address that later", queue the message and process it after the current step
4. **Allow assumption updates mid-flow**: Let users correct assumptions without restarting

### Phase 2 — Conversational Intelligence
5. **Multi-intent classification**: Return array of intents for mixed messages
6. **Phase-aware classifier**: Include current phase, step, and recent context in classifier prompt
7. **Agent addressing**: Support `@agent_name` or "ask [agent] about..." syntax
8. **Conversational agent mode**: Allow multi-turn dialogue with the active agent before proceeding
9. **Semantic intent matching**: Use embeddings for iteration routing instead of keyword substring

### Phase 3 — Agent Quality
10. **Live pricing coverage**: Expand Azure Retail API mapping to cover 80%+ of services
11. **Add reservation modeling**: Include RI, Savings Plans, Hybrid Benefit in cost estimates
12. **Industry benchmarks for BV**: Integrate benchmark datasets for credible value calculations
13. **Customizable adoption curves**: Let users input their own adoption assumptions
14. **Include implementation costs in ROI**: Migration, training, change management

### Phase 4 — Infrastructure
15. **Add persistence**: Redis or CosmosDB for state, with resume-on-restart capability
16. **State checkpointing**: Save state before each agent for undo/resume
17. **Horizontal scaling**: Shared state store for multi-replica deployment
18. **Pass chat history to agents**: Give agents conversational context, not just structured state
19. **Before/after tracking**: Show diffs when iterating on agent outputs
