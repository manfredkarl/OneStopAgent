# FRD-05: Output Agents (Business Value + Presentation)

> **Source of truth:** `specs/v2/refactor.md` — §9 (Business Value Agent), §11 (Presentation Agent)
> **Related sections:** §10 (ROI Agent — consumer of BV outputs), §12 (State Model), §17 (Graceful Degradation)

---

## 1. Overview

Two agents produce the final deliverables of the OneStopAgent pipeline:

1. **BusinessValueAgent** — analyzes the proposed Azure solution in the context of the customer's industry and use case, producing quantified value drivers and an executive summary.
2. **PresentationAgent** — compiles all agent outputs (architecture, services, costs, business value, ROI) into a downloadable executive-ready PowerPoint deck.

Both agents require LLM calls. BusinessValueAgent uses Azure OpenAI to generate industry-specific analysis; PresentationAgent uses LLM-driven content generation combined with `python-pptx` rendering (or the Anthropic PPTX skill when available).

These agents run late in the pipeline — BusinessValueAgent after CostAgent, and PresentationAgent last — because they depend on the accumulated outputs of all preceding agents.

---

## 2. BusinessValueAgent

### 2.1 Purpose

Generate **use-case-specific** business value drivers that quantify the impact of the proposed Azure solution. The output feeds directly into the ROI Agent (§10) and the Business Value slide in the presentation (§11).

This agent exists because generic "cloud saves money" statements are worthless to sellers. Every value driver must reference the customer's specific industry, use case, and architecture to be credible in an executive conversation.

**Agent metadata** (from §3.1):

| Property | Value |
|----------|-------|
| Class | `BusinessValueAgent` |
| LLM Required | Yes |
| External API | No |
| Position in plan | After CostAgent, before ROIAgent |

### 2.2 Input (from AgentState)

The agent reads the following fields from shared state (§12):

| State Field | Purpose | Required |
|-------------|---------|----------|
| `state.user_input` | Original project description — grounds the analysis in what the customer actually asked for | Yes |
| `state.customer_name` | Referenced in executive summary for personalization | Yes |
| `state.architecture` | Component list and narrative — needed to tie value drivers to specific technical capabilities | Yes |
| `state.services` | Azure service selections with SKUs — needed to reference specific Azure capabilities | Yes |
| `state.costs` | Monthly/annual cost estimate — provides the cost baseline for ROI context | Yes |
| `state.brainstorming.industry` | Customer's industry (Retail, Healthcare, Financial Services, etc.) — drives industry-specific benchmarks | Yes |
| `state.clarifications` | Additional context from PM conversations | Optional |

If `state.costs` is empty (CostAgent was skipped or failed), the BusinessValueAgent still runs but flags its output: the executive summary notes that cost data is unavailable and value drivers cannot be tied to ROI calculations.

### 2.3 Processing

**Single LLM call** with full context assembled into one prompt. The prompt must include:

1. **Customer context:** user input, industry, clarifications
2. **Solution context:** architecture narrative, component list, Azure services
3. **Cost context:** total monthly/annual cost
4. **Explicit instruction:** "Generate value drivers specific to a {industry} company implementing {solution_summary}. Do NOT produce generic cloud migration benefits."

The LLM call uses `AzureChatOpenAI` via direct `llm.invoke()` — no chains, no agents (per §15).

**Industry-specific driver generation:**

The prompt must instruct the LLM to use industry-specific benchmarks and metrics:

| Industry | Example Driver Types |
|----------|---------------------|
| Retail | Average order value increase, cart abandonment reduction, inventory optimization savings |
| Healthcare | Patient no-show reduction, telehealth adoption rates, compliance cost avoidance |
| Financial Services | Fraud detection savings, regulatory reporting automation, customer onboarding acceleration |
| Manufacturing | Predictive maintenance uptime improvement, supply chain optimization, quality defect reduction |
| Cross-Industry | Developer productivity gains, infrastructure management reduction, time-to-market acceleration |

**Anti-pattern prevention:** The prompt must explicitly state: "Each value driver must reference at least one specific Azure service from the architecture and one specific business metric from the customer's industry. Reject any driver that could apply to any cloud provider without modification."

### 2.4 Value Driver Schema

Each driver in the `drivers` array must conform to:

```python
{
    "name": str,          # Short label, e.g., "AI-Driven Recommendation Revenue"
    "description": str,   # 1-2 sentences explaining the value mechanism
    "estimate": str,      # Quantified estimate, e.g., "15-25% increase in average order value"
    "monetizable": bool   # Can this estimate be converted to a dollar amount?
}
```

**What `monetizable` means:**

A driver is `monetizable: True` when its `estimate` can be converted to an annual dollar value using reasonable assumptions (see §10 ROI Agent conversion rules). Examples:

| Estimate | Monetizable | Reason |
|----------|-------------|--------|
| "$50,000 saved annually in infrastructure management" | ✅ True | Direct dollar amount |
| "30% reduction in patient no-shows" | ✅ True | Can be converted: no-show rate × avg visit revenue × patient volume |
| "15-25% increase in average order value" | ✅ True | Can be converted: AOV × order volume × percentage |
| "4 hours/week saved on manual reporting" | ✅ True | Can be converted: hours × 52 weeks × $75/hr |
| "Improved compliance posture" | ❌ False | No quantifiable metric |
| "Better developer experience" | ❌ False | Subjective, not quantifiable |
| "Enhanced brand reputation" | ❌ False | No reliable conversion to dollars |

**Why `monetizable` matters for ROI:** The ROI Agent (§10) uses ONLY `monetizable: True` drivers for its quantitative ROI calculation (ROI %, payback period). Non-monetizable drivers are listed as qualitative benefits. If no drivers are monetizable, the ROI Agent reports "ROI cannot be calculated quantitatively." This distinction is critical because it determines whether the presentation's ROI slide shows hard numbers or a qualitative summary.

The agent must produce **3–5 value drivers**, with at least 2 being `monetizable: True` to enable meaningful ROI calculation.

### 2.5 Executive Summary

A 100–200 word narrative summary that:

- **References the customer by name** (`state.customer_name`)
- **References the specific solution** (not "cloud migration" but "AI-powered inventory management platform on Azure")
- **Highlights the top 2-3 value drivers** with their estimates
- **Mentions the industry** context
- **Provides a forward-looking statement** about competitive advantage or operational improvement

**Example structure:**

> "For {customer_name}, the proposed {solution_summary} on Azure addresses {key_challenge}. By leveraging {Azure_service_1} and {Azure_service_2}, {customer_name} can expect {value_driver_1_estimate} and {value_driver_2_estimate}. In the {industry} sector, these improvements translate to {business_impact}. The solution positions {customer_name} to {forward_looking_statement}."

**Anti-pattern:** The summary must NOT read as a generic cloud pitch. It must be specific enough that it could only apply to this customer's scenario.

### 2.6 Confidence Level

The agent assigns one confidence level to the overall analysis:

| Level | Definition | When to Use |
|-------|-----------|-------------|
| `conservative` | Estimates use lower bounds of ranges; excludes speculative benefits; only well-documented industry benchmarks used | Customer is risk-averse, limited data available, highly regulated industry |
| `moderate` | Estimates use midpoint of ranges; includes reasonable extrapolations from industry data | Default for most scenarios; sufficient context available |
| `optimistic` | Estimates use upper bounds of ranges; includes potential upside scenarios; assumes successful adoption | Customer has strong digital maturity, proven Azure track record, or explicitly asked for best-case |

The LLM prompt should instruct: "Assess whether estimates should be conservative, moderate, or optimistic based on the customer's industry, the maturity of the proposed solution, and available data. Default to moderate unless there's a specific reason to adjust."

The confidence level is displayed in the presentation and helps sellers set expectations appropriately.

### 2.7 Output Schema

Written to `state.business_value` (§12):

```python
state.business_value = {
    "drivers": [
        {
            "name": "AI-Driven Product Recommendations",
            "description": "Azure OpenAI-powered recommendation engine increases cross-sell and upsell conversion by suggesting relevant products based on purchase history and browsing behavior.",
            "estimate": "15-25% increase in average order value",
            "monetizable": True
        },
        {
            "name": "Reduced Infrastructure Management",
            "description": "Migration from on-premises servers to Azure App Service and Azure SQL eliminates 80% of manual infrastructure maintenance tasks.",
            "estimate": "$48,000 annually (4 hrs/week × $75/hr × 52 weeks × 3 staff)",
            "monetizable": True
        },
        {
            "name": "Enhanced Compliance Posture",
            "description": "Azure's built-in PCI-DSS compliance controls reduce audit preparation effort and regulatory risk.",
            "estimate": "Qualitative — reduced audit findings and compliance risk",
            "monetizable": False
        }
    ],
    "executiveSummary": "For Contoso Retail, the proposed AI-powered e-commerce platform on Azure...",
    "confidenceLevel": "moderate"
}
```

### 2.8 Anti-Patterns

The BusinessValueAgent **MUST NOT**:

| Anti-Pattern | Why It's Wrong | What to Do Instead |
|-------------|----------------|-------------------|
| Generic drivers like "cloud saves money" | Not credible in executive conversations; every cloud vendor says this | "Azure App Service eliminates 4 hrs/week of IIS server patching for {customer}" |
| Omit the customer's industry | Industry context is the #1 differentiator for credible value analysis | Always reference industry-specific benchmarks and metrics |
| "Improved efficiency" without specifics | Unmeasurable, unactionable, useless for ROI | "30% reduction in order processing time via Azure Logic Apps automation" |
| Drivers that apply to any cloud | Doesn't help the Azure seller's pitch | Reference specific Azure capabilities (Cosmos DB global distribution, Azure AI, etc.) |
| All drivers `monetizable: False` | Makes ROI slide qualitative-only, weakening the business case | Ensure at least 2 of 3-5 drivers have quantifiable estimates |
| Executive summary without customer name | Generic pitch, not personalized proposal | Always use `state.customer_name` in the summary |
| Overpromising without confidence level | Seller loses credibility if estimates are unrealistic | Set appropriate confidence level and use range estimates |

---

## 3. PresentationAgent

### 3.1 Purpose

Compile all agent outputs into a downloadable, executive-ready PowerPoint deck. This is the tangible deliverable that sellers bring to customer meetings — it must be professional, concise, and correctly reference all data generated by upstream agents.

**Agent metadata** (from §3.1):

| Property | Value |
|----------|-------|
| Class | `PresentationAgent` |
| LLM Required | Yes (Anthropic or Azure OpenAI) |
| External API | No |
| Position in plan | Last in pipeline |

### 3.2 Input (from AgentState)

The PresentationAgent consumes the output of every preceding agent:

| State Field | Used In Slide(s) | Required |
|-------------|-------------------|----------|
| `state.customer_name` | Slide 1 (Title) | Yes |
| `state.user_input` | Slide 2 (Problem/Opportunity) | Yes |
| `state.brainstorming.recommended` | Slide 2 (Problem/Opportunity) | Yes |
| `state.architecture.narrative` | Slide 3 (Solution Overview) | Yes |
| `state.architecture.mermaidCode` | Slide 4 (Architecture Diagram) | Yes |
| `state.architecture.components` | Slide 4 fallback (component table) | Yes |
| `state.services.selections` | Slide 5 (Azure Services) | Yes |
| `state.costs.estimate` | Slide 6 (Cost Estimate) | Yes (or skip slide if missing) |
| `state.business_value.drivers` | Slide 7 (Business Value) | Yes (or skip slide if missing) |
| `state.business_value.executiveSummary` | Slide 7 (Business Value) | Optional |
| `state.roi` | Slide 8 (ROI) | Yes (or skip slide if missing) |

If any upstream agent was skipped or failed, the corresponding slide is either omitted or shows a placeholder: "Data not available — {agent_name} was skipped."

### 3.3 Anthropic PPTX Skill Integration

#### 3.3.1 Primary Approach (from §11)

The **Anthropic PPTX generation skill** ([anthropics/skills/pptx](https://github.com/anthropics/skills/tree/main/skills/pptx)) is the primary method. Claude can create PowerPoint files directly as file artifacts when the skill is available.

The skill works by providing Claude with a structured prompt containing all slide content. Claude generates the `.pptx` file directly as a binary file artifact.

**Key principle from §11:** Use the Anthropic skill's **prompt engineering approach** for content quality, even when the physical file isn't generated by Claude directly.

#### 3.3.2 Integration Path (from §11 Integration Approach)

The practical integration follows a two-step process:

```
Step 1: LLM generates slide CONTENT as structured JSON
Step 2: python-pptx renders the JSON into a physical .pptx file
```

**Detailed flow:**

1. **Call Azure OpenAI** (or Anthropic API if available) with the slide content structured per the Anthropic skill's prompt template
2. **If the model supports file artifact generation** (e.g., Claude via Anthropic API) → receive the `.pptx` binary directly. Save to `output/{uuid}.pptx`
3. **If the model does NOT support file artifacts** (e.g., Azure OpenAI GPT-4.1) → the LLM returns slide content as structured JSON, and `python-pptx` renders it to `.pptx`

**MVP reality (from §11):** In practice for MVP, the LLM generates the slide **content** (titles, bullets, tables, speaker notes), and `python-pptx` renders the physical file. The Anthropic skill's prompt engineering approach is used for content quality, even if the file isn't generated by Claude directly.

**Content JSON structure** (output of Step 1):

```json
{
  "slides": [
    {
      "slide_number": 1,
      "layout": "title",
      "title": "Contoso Retail — Azure Solution Proposal",
      "subtitle": "AI-Powered E-Commerce Platform",
      "speaker_notes": "Opening slide — introduce the engagement context."
    },
    {
      "slide_number": 5,
      "layout": "table",
      "title": "Azure Services",
      "table": {
        "headers": ["Service", "SKU", "Region", "Purpose"],
        "rows": [["Azure App Service", "P2v3", "eastus", "Web application hosting"], ...]
      }
    }
  ]
}
```

#### 3.3.3 Fallback

If the Anthropic PPTX skill is unavailable AND LLM content generation fails:

- Use `python-pptx` directly with hardcoded slide templates
- Content is pulled from state fields without LLM refinement
- Output is functional but lacks the polished executive language of the LLM-generated version
- File is saved to `output/{uuid}.pptx` with the same naming convention

Fallback hierarchy:
1. Anthropic PPTX skill (direct `.pptx` generation) — **preferred**
2. LLM content JSON → `python-pptx` rendering — **MVP default**
3. Direct `python-pptx` with state data (no LLM) — **emergency fallback**

### 3.4 Slide Structure

Full 9-slide deck (from §11):

| # | Slide | Content Source | Layout |
|---|-------|---------------|--------|
| 1 | **Title** | `state.customer_name` + "Azure Solution Proposal" | Title slide |
| 2 | **Problem / Opportunity** | `state.user_input` + `state.brainstorming.recommended` | Bullet list |
| 3 | **Solution Overview** | `state.architecture.narrative` | Text with key points |
| 4 | **Architecture Diagram** | `state.architecture.mermaidCode` rendered as PNG (or component table fallback) | Full-slide image or table |
| 5 | **Azure Services** | `state.services.selections` as table (Service, SKU, Region, Purpose) | Table |
| 6 | **Cost Estimate** | `state.costs.estimate.items` as table + `totalMonthly` / `totalAnnual` totals | Table with summary row |
| 7 | **Business Value** | `state.business_value.drivers` as bullet list + executive summary | Bullet list |
| 8 | **ROI** | `state.roi` — ROI %, payback period, key numbers (or qualitative summary) | Key metrics + supporting data |
| 9 | **Next Steps** | Static recommendations | Numbered list |

**Slide 9 — Next Steps** content is static (not state-dependent):
1. Schedule technical deep-dive with Azure Solution Architect
2. Set up Azure subscription / PoC environment
3. Define success criteria and timeline
4. Identify pilot scope and stakeholders
5. Begin implementation with Microsoft FastTrack (if eligible)

### 3.5 Slide Content Generation

The LLM prompt for content generation must specify (from §11):

> "Write slide content for an executive audience. Use bullet points, keep text concise, highlight key numbers."

**Content rules:**
- **Bullet points:** Maximum 5 bullets per slide, each ≤ 20 words
- **Key numbers:** Always bold or highlight cost totals, ROI %, payback months
- **Tables:** Maximum 8 rows visible; if more services, group by category
- **No jargon:** Translate technical terms for executive audience (e.g., "auto-scaling" → "automatically adjusts capacity to match demand")
- **Speaker notes:** Each slide includes 2-3 sentence speaker notes for the presenter

### 3.6 Architecture Diagram Handling

The architecture diagram (Slide 4) requires special handling because Mermaid code must be converted to an image:

**Primary path — Mermaid → PNG:**
1. Use a Mermaid rendering library or CLI (`mermaid-cli` / `@mermaid-js/mermaid-cli`) to render `state.architecture.mermaidCode` to PNG
2. Embed the PNG as a full-slide image in the PPTX
3. If rendering succeeds, add the component list as speaker notes

**Fallback — Component Table:**
If Mermaid rendering fails (invalid syntax, library unavailable, timeout):
1. **Do not crash** — silently fall back (per §17: "Malformed Mermaid from LLM → Show component table instead. Hide diagram silently.")
2. Render `state.architecture.components` as a table:

| Component | Azure Service | Description |
|-----------|--------------|-------------|
| Web Frontend | Azure App Service | Hosts the React SPA and API layer |
| Database | Azure SQL Database | Stores product catalog and orders |
| ... | ... | ... |

3. Add a subtitle: "Architecture Components" (instead of "Architecture Diagram")

### 3.7 ROI Slide Handling

The ROI slide (Slide 8) must handle two scenarios based on the ROI Agent's output:

**Scenario A — ROI is calculable** (`state.roi.roi_percent` is not None):

Display key metrics prominently:
- **ROI:** {roi_percent}%
- **Payback Period:** {payback_months} months
- **Annual Azure Cost:** ${annual_cost}
- **Annual Value Generated:** ${annual_value}
- **Monetized Drivers:** list with annual values
- **Additional Qualitative Benefits:** bullet list

**Scenario B — ROI is not calculable** (`state.roi.roi_percent` is None):

Display qualitative summary:
- Heading: "Business Impact Assessment"
- Bullet list of all value drivers (monetizable and non-monetizable)
- Note: "Quantitative ROI requires additional data — contact your Azure specialist for a detailed analysis"
- List assumptions that prevented calculation

Both scenarios include `state.roi.assumptions` as a footnote or speaker notes.

### 3.8 Output Schema

Written to `state.presentation_path` (§12):

```python
state.presentation_path = "output/{uuid}.pptx"
```

The file is saved to the `output/` directory with a UUID-based filename. The API serves this file as a downloadable attachment.

**Error case:** If PPTX generation fails entirely (§17), set `state.presentation_path = ""` and the PM announces: "Presentation generation failed." The PM offers slide content as markdown in the chat as an alternative.

---

## 4. Agent Interaction

### 4.1 Data Flow

```
CostAgent ──→ BusinessValueAgent ──→ ROIAgent ──→ PresentationAgent
                                        ↑
              BusinessValueAgent.monetizable flags feed ROI calculation
```

**BusinessValueAgent → ROIAgent:**
- `monetizable: True` drivers are the ONLY inputs to the ROI Agent's quantitative calculation (§10)
- `monetizable: False` drivers are listed as qualitative benefits in `state.roi.qualitative_benefits`
- If all drivers are `monetizable: False`, the ROI Agent sets `roi_percent = None`

**All agents → PresentationAgent:**
- PresentationAgent reads the final state of every agent's output
- It does NOT re-process or re-analyze data — it formats and presents what's already been computed
- If any upstream agent was skipped/failed, the corresponding slide adapts (placeholder or omission)

### 4.2 Iteration Impact (from §13)

| User Says | BusinessValueAgent Re-runs? | PresentationAgent Re-runs? |
|-----------|---------------------------|---------------------------|
| "Make it cheaper" | No | Yes (updated costs/ROI) |
| "Add high availability" | No | Yes (updated architecture/costs) |
| "Add AI capabilities" | Yes (new value drivers) | Yes (updated everything) |
| "Regenerate the deck" | No | Yes |
| "More aggressive ROI" | Yes (change confidence to optimistic) | Yes |

### 4.3 Communication Rule (from §3.2)

Both agents communicate with other agents **only through `AgentState`**. No agent imports logic from another agent. No direct function calls between agents. State is the single interface.

---

## 5. Acceptance Criteria

### BusinessValueAgent

- [ ] Generates 3–5 use-case-specific value drivers per run
- [ ] Each driver has a `monetizable` boolean flag
- [ ] At least 2 drivers are `monetizable: True` when sufficient context is available
- [ ] Executive summary is 100–200 words
- [ ] Executive summary mentions customer name (`state.customer_name`)
- [ ] Executive summary references the specific solution (not generic cloud pitch)
- [ ] No generic drivers without industry/use-case specifics (anti-patterns enforced)
- [ ] Each driver references at least one specific Azure service
- [ ] Confidence level is set to one of: `conservative`, `moderate`, `optimistic`
- [ ] Agent handles missing `state.costs` gracefully (flags output, still produces drivers)
- [ ] LLM prompt includes industry, architecture, services, and cost context
- [ ] Output conforms to `state.business_value` schema (§12)

### PresentationAgent

- [ ] Generates a 9-slide PPTX file
- [ ] PPTX is saved to `output/{uuid}.pptx`
- [ ] PPTX is downloadable via API endpoint
- [ ] Slide content is executive-quality (concise bullets, key numbers highlighted, professional tone)
- [ ] Title slide includes customer name
- [ ] Architecture diagram renders from Mermaid → PNG when possible
- [ ] Architecture diagram falls back to component table when Mermaid rendering fails
- [ ] Mermaid failures are silent — no crash, no error shown to user (§17)
- [ ] ROI slide handles calculable case (shows ROI %, payback period, annual values)
- [ ] ROI slide handles non-calculable case (shows qualitative summary)
- [ ] Cost table shows per-service breakdown with totals
- [ ] Skipped/failed agent outputs produce placeholder slides (not crashes)
- [ ] LLM content generation follows Anthropic PPTX skill prompt patterns
- [ ] Fallback to direct `python-pptx` works when LLM is unavailable (§17)
- [ ] Speaker notes are included on each slide
- [ ] Slide 9 (Next Steps) contains static recommendations
- [ ] File generation failure is handled gracefully — markdown alternative offered in chat (§17)
