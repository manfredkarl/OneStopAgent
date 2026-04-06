# OneStopAgent — Manual Review & Test Checklist

> **Purpose**: Comprehensive manual testing guide to validate the entire app end-to-end  
> **Last Updated**: 2026-04-06  
> **Environment**: Local (localhost:4200 + localhost:8000) or Production

---

## Pre-Requisites

- [ ] Backend running (`python -m uvicorn main:app --port 8000`)
- [ ] Frontend running (`npm run dev` → localhost:4200)
- [ ] Valid Azure token (check `az account get-access-token`)
- [ ] Company search working (test: search "Nike")

---

## 1. Project Creation & Landing Page

### 1.1 Basic Flow
- [ ] Enter a project description (e.g., "AI-powered customer support chatbot for Contoso Bank")
- [ ] Verify minimum 10 character validation works (try short text)
- [ ] Verify max 5000 character limit on textarea
- [ ] Click "Start" → project created, redirected to chat

### 1.2 Company Search
- [ ] Type a company name in the customer field (e.g., "Siemens")
- [ ] Verify debounced search triggers after ~500ms
- [ ] Verify results appear with company name, employees, revenue
- [ ] Select a company → verify it's attached to the project
- [ ] Try a nonexistent company → verify "No companies found" message
- [ ] Try with network off → verify error feedback (not silent failure)

### 1.3 Double-Click Protection
- [ ] Rapidly click "Start" twice → verify only one project created
- [ ] Verify loading spinner shows during creation

### 1.4 Agent Selection
- [ ] Toggle agents on/off in the sidebar before starting
- [ ] Verify disabled agents are skipped in the pipeline

---

## 2. Brainstorming / Envisioning Phase

- [ ] After project creation, PM agent should greet and propose scenarios
- [ ] Verify streaming tokens appear progressively (not all at once)
- [ ] Verify the plan shows which agents will run and in what order
- [ ] Type "proceed" or click ✅ Proceed → moves to assumption collection
- [ ] Try "skip" → verify it acknowledges and asks what else to adjust
- [ ] Try free-text feedback → verify it's acknowledged as clarification

---

## 3. Assumption Collection

- [ ] After proceeding, shared assumptions form should appear
- [ ] Verify fields: users, employees, spend, data volume, timeline
- [ ] Fill in values and submit → pipeline should start
- [ ] Try proceeding with defaults (no input) → verify sensible defaults used
- [ ] Verify company profile data pre-fills relevant fields (if company selected)

---

## 4. Agent Pipeline — Sequential Execution

### 4.1 Business Value Agent
- [ ] Agent starts, shows progress indicator
- [ ] Output includes value drivers with impact estimates
- [ ] Approval gate appears with ✅ Proceed / ✏️ Refine / ⏭️ Skip buttons
- [ ] **Click Refine** → should ask "What would you like to change?" (NOT immediately re-run)
- [ ] Provide feedback (e.g., "focus more on cost savings") → agent re-runs with feedback
- [ ] After re-run, approval gate appears again
- [ ] Click Proceed → moves to Architect

### 4.2 Architect Agent
- [ ] Architecture output includes Mermaid diagram
- [ ] Verify Mermaid diagram renders (not raw code)
- [ ] Output lists Azure services with descriptions
- [ ] Test refine: "add a CDN for global distribution" → re-runs with feedback
- [ ] Test skip → marks step skipped, moves to Cost

### 4.3 Cost Agent
- [ ] Two-phase: first asks usage assumptions (concurrent users, storage, etc.)
- [ ] Fill in assumptions → agent calculates costs
- [ ] Output shows monthly/annual cost breakdown per service
- [ ] Verify confidence labels (High/Moderate/Low) shown
- [ ] Verify reservation savings mentioned (if compute services present)
- [ ] Test refine: "use reserved instances for VMs" → re-runs

### 4.4 ROI Agent
- [ ] ROI dashboard renders with charts and metrics
- [ ] Verify: 3-year projection, payback period, ROI percentage
- [ ] Verify implementation costs shown (migration, training, change mgmt)
- [ ] Verify adoption curves applied (check Year 1/2/3 values)
- [ ] Bar chart: verify bars don't overflow labels (capped at 88px)
- [ ] Test with NO company profile → verify ROI still produces estimates (no "needs_info")

### 4.5 Presentation Agent
- [ ] PowerPoint generated successfully
- [ ] Download link appears and works
- [ ] Verify customer name in slides (not generic "Customer")
- [ ] Verify slides include architecture, costs, ROI data

---

## 5. Approval Gate Interactions

### 5.1 Action Buttons
- [ ] Only the LAST approval message has active buttons (older ones disabled)
- [ ] Buttons visually distinct: Proceed (primary), Refine (secondary), Skip (ghost)
- [ ] Clicking a button sends the correct message
- [ ] Buttons disable after clicking (no double-submit)

### 5.2 Refine Flow
- [ ] Click Refine → asks "What would you like to change?"
- [ ] Type feedback → agent re-runs with that feedback incorporated
- [ ] New output appears with approval gate again
- [ ] Can refine multiple times in a row

### 5.3 Questions During Approval
- [ ] Type a question: "Why did you choose App Service over AKS?" → get an answer
- [ ] Verify approval gate stays open after question (can still proceed/skip)
- [ ] Use @mention: "@cost what's the most expensive service?" → get answer from cost context
- [ ] Verify approval gate still active after @mention question

### 5.4 Skip Behavior
- [ ] Click Skip → step marked as skipped, pipeline continues
- [ ] Skipped step's data not included in downstream agents' context

---

## 6. @Agent Mentions

### 6.1 Autocomplete Dropdown
- [ ] Type `@` in chat input → dropdown appears with 5 agents
- [ ] Continue typing `@co` → filters to show only "Cost"
- [ ] Arrow keys navigate the dropdown (highlight moves)
- [ ] Enter selects highlighted agent, inserts `@cost ` into input
- [ ] Mouse click on agent also works
- [ ] Escape closes dropdown
- [ ] Dropdown appears ABOVE the input (not below/overlapping)

### 6.2 @Mention During Approval Gate
- [ ] `@architect explain the database choice` → answers question, keeps gate open
- [ ] `@cost how much is storage?` → answers from cost context

### 6.3 @Mention After Pipeline (Done Phase)
- [ ] `@cost make it cheaper` → triggers cost + downstream re-run
- [ ] `@architect add caching layer` → triggers architect + downstream re-run
- [ ] Verify iteration diff summary shown after re-run

### 6.4 @Mention During Active Execution (No Approval Gate)
- [ ] While an agent is actively running, `@roi check the numbers` → "📝 Noted" (queued)
- [ ] After current agent completes, queued feedback should be applied

---

## 7. Conversational Mode

- [ ] Type "chat with architect" → enters conversation mode
- [ ] Verify indicator shows "💬 Chatting with architect"
- [ ] Send multiple messages → responses come from architect context
- [ ] Type "done" → exits conversation mode
- [ ] Click "Done chatting" button → exits conversation mode
- [ ] Verify normal flow resumes after exiting

---

## 8. Mid-Flow Assumption Updates

- [ ] During pipeline, type "actually we have 5000 users" → should update assumptions
- [ ] Verify "📊 Updated assumptions" message appears
- [ ] Downstream agents should use updated value
- [ ] After pipeline, type "actually 10000 employees" → triggers relevant agent re-runs

---

## 9. Iteration (Done Phase)

### 9.1 Keyword-Based
- [ ] "make it cheaper" → re-runs cost + ROI + presentation
- [ ] "add high availability" → re-runs architect + cost + ROI + presentation
- [ ] "different approach" → re-runs all agents

### 9.2 Explicit Retry
- [ ] "retry cost" → re-runs cost + downstream
- [ ] "retry architect" → re-runs architect + downstream

### 9.3 Iteration Tracking
- [ ] After re-run, verify diff summary shows (e.g., "📉 Cost: $45K → $38K/mo")
- [ ] GET `/api/projects/{id}/iterations` → returns iteration history

### 9.4 Undo
- [ ] Type "undo" → reverts to previous checkpoint (if Cosmos enabled)
- [ ] Verify state restored correctly

### 9.5 Fresh Start
- [ ] Type "start fresh" or "new project" → resets everything

---

## 10. Company Intelligence

- [ ] Search populates: name, employees, revenue, industry, HQ
- [ ] Company card shows in chat sidebar
- [ ] Click company card → detail modal opens with full info
- [ ] Verify company data flows to agents (check presentation for customer name)

---

## 11. Error Handling & Edge Cases

### 11.1 Network Errors
- [ ] Kill backend mid-pipeline → frontend shows error message (not blank)
- [ ] Refresh page during pipeline → chat history preserved (messages shown)
- [ ] Send message with backend down → error shown to user

### 11.2 Token Expiry
- [ ] Let token expire (~60 min) → backend should auto-refresh
- [ ] If auto-refresh fails, verify error message (not silent failure)

### 11.3 Empty/Minimal Input
- [ ] Create project with minimal description → pipeline still runs
- [ ] Skip all agents → presentation handles gracefully
- [ ] No company selected → agents use defaults

### 11.4 Long Input
- [ ] Paste very long description (1000+ chars) → verify no truncation
- [ ] Long feedback during refine → verify fully processed

---

## 12. UI/UX Quality

### 12.1 Visual Consistency
- [ ] Dark theme consistent across all components
- [ ] No unstyled elements (check for missing CSS variables)
- [ ] Mermaid diagrams render with proper styling
- [ ] ROI dashboard charts readable (labels not overlapping)
- [ ] Loading states shown during all async operations

### 12.2 Responsive
- [ ] Chat scrolls to bottom on new messages
- [ ] Long agent outputs are readable (no horizontal overflow)
- [ ] Action buttons wrap properly on narrow screens

### 12.3 Input UX
- [ ] Input placeholder changes during approval ("Type proceed, skip, refine...")
- [ ] Input enabled after approval gate (user can type response)
- [ ] Input disabled while agent is actively generating
- [ ] Enter sends message, Shift+Enter adds newline

---

## 13. API Endpoints Verification

| Endpoint | Method | Test |
|----------|--------|------|
| `/health` | GET | Returns `{"status": "healthy"}` |
| `/api/projects` | GET | Returns user's projects (requires x-user-id) |
| `/api/projects` | POST | Creates project (requires description) |
| `/api/projects/{id}` | GET | Returns project details (user-scoped) |
| `/api/projects/{id}/chat` | GET | Returns chat history |
| `/api/projects/{id}/chat` | POST | Sends message, returns SSE stream |
| `/api/projects/{id}/agents` | GET | Returns agent statuses |
| `/api/projects/{id}/agents/{agent_id}` | PATCH | Toggles individual agent active state |
| `/api/projects/{id}/iterations` | GET | Returns iteration history (user-scoped) |
| `/api/company/search?q=X` | GET | Returns company search results |
| `/api/projects/{id}/export/pptx` | GET | Downloads PPTX file |

### Security Checks
- [ ] All endpoints require `x-user-id` header (400 without)
- [ ] Users can only access their own projects (try different user IDs)
- [ ] Iterations endpoint validates project ownership
- [ ] PPTX download validates path (no directory traversal)

---

## 14. Performance

- [ ] Brainstorming response starts streaming within 3-5 seconds
- [ ] Company search returns within 5 seconds
- [ ] Each agent completes within 60 seconds
- [ ] Full pipeline (all agents) completes within 5 minutes
- [ ] No visible UI lag during streaming

---

## 15. Production Deployment

- [ ] `azd deploy` succeeds
- [ ] Production health check passes
- [ ] CORS allows production web origin
- [ ] Company search works in production
- [ ] Full pipeline works end-to-end in production
- [ ] PPTX download works in production
