# Agent Streaming — Implementation Spec

## Problem

Agent responses appear all at once after 10-30 seconds of silence. Users see a "Thinking..." indicator but no progressive output. This feels slow and unresponsive.

## Goal

Stream agent LLM output token-by-token to the frontend via SSE, so users see text appearing as it's generated — like ChatGPT.

## Current Architecture

```
Agent.run(state)          # synchronous, blocks until complete
  → llm.invoke(messages)  # waits for full response
  → parses JSON/text
  → writes to state
  → returns state
```

The orchestrator runs agents in a thread pool and waits for completion:
```python
loop.run_in_executor(None, agent.run, state)  # blocks, returns everything at once
```

## Target Architecture

```
Agent.run_streaming(state, on_token)  # async, yields tokens as they arrive
  → llm.astream(messages)            # async generator, yields chunks
  → on_token(chunk.content)          # sent to SSE immediately
  → accumulates full response
  → parses JSON/text at end
  → writes to state
  → returns state
```

## What Needs to Change

### 1. Agent interface — add `run_streaming()` method

Each LLM-based agent gets a new async method:

```python
class ArchitectAgent:
    def run(self, state):
        """Synchronous — used by non-streaming path."""
        # existing code

    async def run_streaming(self, state, on_token: Callable[[str], None]):
        """Async — streams tokens via callback, returns updated state."""
        full_text = ""
        async for chunk in llm.astream([
            {"role": "system", "content": "Generate architecture..."},
            {"role": "user", "content": state.to_context_string()}
        ]):
            if chunk.content:
                on_token(chunk.content)
                full_text += chunk.content
        
        # Parse accumulated response (same as run())
        # ... JSON parsing, state updates
        return state
```

### 2. Agents that need streaming (LLM-based)

| Agent | LLM Calls | Streaming Value |
|-------|-----------|-----------------|
| **PM brainstorm_greeting** | 1 call | HIGH — first response, longest wait |
| **ArchitectAgent** | 3 calls (mermaid, components, narrative) | HIGH — architecture is complex |
| **BusinessValueAgent** | 1 call | MEDIUM — value analysis text |
| **CostAgent._llm_map_services** | 1 call | MEDIUM — service mapping |
| **PresentationAgent** | 1 call | LOW — generates script, not user-facing text |

### 3. Agents that DON'T need streaming (no LLM)

| Agent | Why |
|-------|-----|
| **ROIAgent** | Pure math, completes in <1s |
| **CostAgent._price_selections** | API calls, no LLM |

### 4. Orchestrator changes

In `_run_single_step()`, detect if agent supports streaming:

```python
if hasattr(agent, 'run_streaming') and accept_sse:
    # Stream tokens via SSE
    accumulated = ""
    msg_id = str(uuid.uuid4())
    
    def on_token(token: str):
        nonlocal accumulated
        accumulated += token
        # Yield SSE event with partial content
    
    await agent.run_streaming(state, on_token)
    
    # Final formatted output
    yield full_result_message
else:
    # Non-streaming fallback (existing code)
    state = await loop.run_in_executor(None, agent.run, state)
```

### 5. SSE event format for streaming tokens

```json
{"type": "agent_token", "agent": "architect", "token": "This ", "msg_id": "abc-123"}
{"type": "agent_token", "agent": "architect", "token": "Azure ", "msg_id": "abc-123"}
{"type": "agent_token", "agent": "architect", "token": "architecture...", "msg_id": "abc-123"}
{"type": "agent_result", "agent": "architect", "content": "full formatted output"}
```

### 6. Frontend changes

The frontend already handles `pm_response_chunk` with in-place updates by message ID. Extend this for `agent_token`:

```typescript
if (msg.metadata?.type === 'agent_token') {
    setMessages(prev => {
        const idx = prev.findIndex(m => m.id === msg.metadata.msg_id);
        if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = { ...updated[idx], content: updated[idx].content + msg.metadata.token };
            return updated;
        }
        return [...prev, { ...msg, content: msg.metadata.token }];
    });
}
```

## JSON Parsing Challenge

Some agents (architect, BV) expect JSON responses. With streaming, tokens arrive one at a time, so you can't parse until the full response is accumulated. Two approaches:

### Approach A: Stream raw text, parse at end
- Stream all tokens to the user as they arrive
- After streaming completes, parse the accumulated text as JSON
- Replace the streamed text with the formatted output
- **Pro:** Simple. **Con:** User sees raw JSON briefly.

### Approach B: Stream narrative parts only, suppress JSON
- For agents that return JSON, DON'T stream the raw output
- Instead, stream a PM summary AFTER the agent completes:
  ```python
  # Agent completes (non-streaming)
  state = agent.run(state)
  
  # PM streams a summary
  async for chunk in llm.astream([
      {"role": "system", "content": "Summarize this architecture in 2-3 sentences..."},
      {"role": "user", "content": json.dumps(state.architecture)}
  ]):
      yield token_event(chunk.content)
  
  # Then show full formatted output
  yield full_result
  ```
- **Pro:** Clean UX, no raw JSON. **Con:** Extra LLM call per agent.

### Recommendation: Approach B for JSON agents, Approach A for text agents

| Agent | Response Format | Streaming Approach |
|-------|----------------|-------------------|
| PM brainstorm | JSON with `response` field | Stream the `response` field text only |
| Architect | JSON (mermaid + components) | Approach B — stream PM summary, then show diagram |
| Business Value | JSON (drivers + summary) | Stream the `executiveSummary` field |
| Cost (LLM mapping) | JSON (selections) | Don't stream — fast enough |
| Presentation | Script text | Don't stream — not user-facing |

## Implementation Order

1. **PM brainstorm_greeting** — highest impact, users wait longest here
2. **BusinessValueAgent** — streams executive summary
3. **ArchitectAgent** — PM summary streams, then full output appears
4. **CostAgent** — optional, LLM mapping is fast

## Effort Estimate

| Task | Files | Effort |
|------|-------|--------|
| Add `run_streaming()` to 3 agents | architect, BV, PM | ~2 hours |
| Update orchestrator for streaming path | orchestrator.py | ~1 hour |
| Frontend token handling | ChatThread.tsx, api.ts | ~30 min (mostly done) |
| Testing | Manual | ~1 hour |
| **Total** | | **~4-5 hours** |

## Non-Goals

- Token streaming for non-LLM agents (ROI, pricing API calls)
- Streaming inside tool calls (MCP, web search)
- WebSocket migration (SSE is sufficient)
