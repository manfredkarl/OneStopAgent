# OneStopAgent Python Backend — Deep Review

## Status: Tools work, but orchestration and prompts need fixing

### Test Results
When forced to call tools, the pipeline works:
- ✅ `generate_architecture` — generates Mermaid via LLM
- ✅ `select_azure_services` — maps 5 components to services with SKUs  
- ✅ `estimate_costs` — returns $176/month (uses mock pricing)
- ✅ Agent produces 7 streaming messages (announcements + outputs + summary)

### Problem 1: PM Agent refuses to call tools — keeps asking questions
**Severity: CRITICAL**

The system prompt says "wait for user to say go" which makes the agent overly cautious.
User says "lets go build it, proceed with all agents" → agent STILL asks more questions.
Only when user explicitly says "call generate_architecture NOW" does it work.

**Root cause:** `agents/pm_agent.py` system prompt:
```
3. Wait for user to say "go" or adjust the plan
```

The LLM interprets "lets go" as conversational, not as the "go" trigger. Also the prompt
encourages asking questions first, which creates an infinite clarification loop.

**Fix:** Rewrite the system prompt to be ACTION-BIASED:
- After 1-2 exchanges OR if the user provides detailed requirements, call tools immediately
- "go", "proceed", "start", "build it", "lets go" all trigger execution
- Don't ask more than 2 clarifying questions total
- If the user's first message has >30 words with technical details, skip questions entirely

### Problem 2: Architecture tool ignores the actual requirements
**Severity: HIGH**

`generate_architecture` receives the user's requirements as input but the `_generate_mermaid()` 
function sends a GENERIC prompt to the LLM:
```python
"Design a standard Azure architecture for a typical web application"
```
It ignores the actual description (10K users, AI recommendations, PCI-DSS, etc.).

**Fix:** Pass the full requirements to the Mermaid generation LLM call.

### Problem 3: Cost estimation uses mock prices, not real API  
**Severity: HIGH**

`services/pricing.py` calls the Azure Retail Prices API but falls back to MOCK_PRICES silently.
The mock prices produce $176/month for a 10K-user e-commerce platform — unrealistically low.

Issues in `query_azure_pricing_sync()`:
- Uses `httpx.Client` synchronously in an async context
- Filter query may not match Azure API's service naming convention
- No logging of why API call fails

**Fix:** 
- Use `httpx.AsyncClient` properly
- Log API responses to diagnose filter mismatches
- Make mock prices more realistic (thousands, not hundreds)

### Problem 4: Services tool doesn't use scale parameters
**Severity: HIGH**

`select_azure_services` maps components but ignores scale. A 10K-user platform gets the same
B1 SKU as a 10-user prototype. The `_select_sku()` function is hardcoded:
```python
def _select_sku(component_name: str) -> str:
    name = component_name.lower()
    if "database" in name or "sql" in name:
        return "Standard S1"
    return "Standard S1"  # Default everything to S1
```

**Fix:** Extract concurrent users from requirements and use SKU scaling tiers.

### Problem 5: Business value tool returns generic analysis
**Severity: MEDIUM**

`assess_business_value` calls the LLM but the prompt is generic:
```
"Analyze the business value and ROI of this Azure solution"
```
It doesn't include the actual architecture, services, or costs in the prompt.

**Fix:** Pass full context (architecture components, selected services, cost estimate, 
customer industry) to the BV LLM prompt.

### Problem 6: Presentation tool generates minimal deck
**Severity: LOW**

`services/presentation.py` creates a real PPTX but the slides are basic text-only.
No Mermaid diagram rendering, no cost tables, no visual polish.

**Fix:** Improve slide content — add tables for costs, bullet lists for services, 
proper formatting.

### Problem 7: SSE streaming sends tool announcements but not token-by-token
**Severity: MEDIUM**

The current streaming sends complete messages (one SSE event per tool call completion).
It does NOT stream the PM's text token by token. The user sees nothing for 10-30 seconds
while the LLM generates, then the full response appears at once.

**Fix:** Use LangChain's `astream_events` or `astream` with `stream_mode="messages"` 
to stream individual tokens for text responses.

### Problem 8: Agent toggle doesn't recreate the agent
**Severity: MEDIUM**

`main.py` PATCH endpoint calls `create_pm_agent()` with updated tools, but the old
agent session has LangGraph state (conversation memory) that may reference old tools.
Creating a new agent loses conversation history.

**Fix:** Use LangGraph's checkpointer to persist state, or at minimum pass 
conversation history to the new agent.

### Problem 9: No error handling in tools
**Severity: MEDIUM**

If `_generate_mermaid()` LLM call fails, the entire `generate_architecture` tool throws
an unhandled exception. The agent gets a raw Python traceback instead of a useful error.

**Fix:** Wrap each tool in try/except, return structured error JSON on failure.

### Problem 10: Conversation memory not persisted
**Severity: LOW (MVP acceptable)**

LangGraph agent uses in-memory checkpointer (`MemorySaver`). Server restart loses all
conversation context. The `project_store` persists messages but the agent's internal
reasoning state is lost.

---

## Priority Fix Order

1. **Fix PM system prompt** — make it action-biased, stop asking infinite questions
2. **Pass real requirements to architecture LLM** — not generic "typical web app"
3. **Fix SKU scaling** — use concurrent users from requirements
4. **Pass full context to business value** — architecture + costs
5. **Add error handling to all tools** — try/except with fallback
6. **Fix pricing** — async httpx, better service name mapping
7. **Token-by-token streaming** — astream_events for PM text
8. **Improve presentation slides** — tables, formatting
