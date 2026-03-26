# FRD-PRESENTATION: Presentation Generation

| Field        | Value                                          |
| ------------ | ---------------------------------------------- |
| **PRD Ref**  | US-7 — Presentation Generation                 |
| **Status**   | Draft                                          |
| **Author**   | spec2cloud                                     |
| **Created**  | 2025-07-15                                     |

---

## 1. Overview

The Presentation Agent is the final stage of the OneStopAgent pipeline. It consumes the accumulated outputs of all preceding agents — architecture diagrams, service selections, cost estimates, and business value assessments — and compiles them into a professional PowerPoint deck that sellers can download and present directly to customers.

**Key constraints from the PRD:**

- The deck must cover executive summary, use case description, architecture diagram, service details, cost breakdown, and business value assessment (US-7).
- Skipped agents → the deck omits those sections and notes which are missing (US-7).
- Diagram-to-image conversion failure → placeholder slide with text description (US-7).
- Maximum 20 slides (R-7), truncate verbose content, fallback PDF export (R-7).
- The seller downloads `.pptx` from the chat interface via `GET /api/projects/:id/export/pptx` (FR-1).
- The seller can regenerate the deck after making changes to any preceding agent's output (US-7).

---

## 2. Agent Input/Output Contract

### 2.1 Input

The Presentation Agent reads all fields from `ProjectContext` on the parent `Project` object. Every field except `requirements` is optional; the agent adapts its output based on which agent stages completed.

| Source Field                        | Type                  | Required | Source Agent       | Used For                         |
| ----------------------------------- | --------------------- | -------- | ------------------ | -------------------------------- |
| `Project.description`               | `string`              | Yes      | User input         | Title slide, use case slide      |
| `Project.customerName`              | `string \| undefined` | No       | User input         | Title slide branding             |
| `ProjectContext.requirements`        | `Record<string, string>` | Yes   | PM Agent           | Use case / scenario slide        |
| `ProjectContext.envisioningSelections` | `string[]`          | No       | Envisioning Agent  | Scenario context (if available)  |
| `ProjectContext.architecture`        | `ArchitectureOutput`  | No       | System Architect   | Architecture diagram slide       |
| `ProjectContext.services`            | `ServiceSelection[]`  | No       | Azure Specialist   | Azure services slide(s)          |
| `ProjectContext.costEstimate`        | `CostEstimate`        | No       | Cost Specialist    | Cost breakdown slide(s)          |
| `ProjectContext.businessValue`       | `ValueAssessment`     | No       | Business Value     | Business value slide(s)          |

**Referenced data model types (from PRD FR-4):**

```typescript
interface ArchitectureOutput {
  mermaidCode: string;
  components: { name: string; azureService: string; description: string }[];
  narrative: string;
}

interface ServiceSelection {
  componentName: string;
  serviceName: string;
  sku: string;
  region: string;
  capabilities: string[];
  alternatives?: { serviceName: string; tradeOff: string }[];
}

interface CostEstimate {
  currency: 'USD';
  items: { serviceName: string; sku: string; region: string; monthlyCost: number }[];
  totalMonthly: number;
  totalAnnual: number;
  assumptions: string[];
  generatedAt: Date;
  pricingSource: 'live' | 'cached' | 'approximate';
}

interface ValueAssessment {
  drivers: { name: string; impact: string; quantifiedEstimate?: string }[];
  executiveSummary: string;
  benchmarks: string[];
}
```

### 2.2 Output

| Output             | Type                           | Description                                                    |
| ------------------ | ------------------------------ | -------------------------------------------------------------- |
| `pptxBuffer`       | `Buffer` (binary)              | In-memory `.pptx` file ready for HTTP streaming                |
| `metadata`         | `PresentationMeta`             | Generation metadata persisted on the `ProjectContext`          |

```typescript
interface PresentationMeta {
  slideCount: number;         // Actual slides generated (≤ 20)
  fileSize: number;           // Bytes
  generatedAt: Date;          // ISO-8601
  sectionsIncluded: string[]; // e.g. ["executive-summary", "architecture", "cost"]
  sectionsOmitted: string[];  // e.g. ["business-value"]
  warnings: string[];         // e.g. ["Diagram conversion failed — placeholder used"]
  sourceHash: string;         // SHA-256 of concatenated input data for cache invalidation
}
```

---

## 3. Slide Deck Structure

### 3.1 Slide Order

| Slide # | Title                        | Content Source                          | Required / Optional | Max Slides |
| ------- | ---------------------------- | --------------------------------------- | ------------------- | ---------- |
| 1       | Title                        | `Project.description`, `customerName`   | Required            | 1          |
| 2       | Executive Summary            | `ValueAssessment.executiveSummary`, or auto-generated summary | Required | 1 |
| 3       | Use Case / Scenario          | `ProjectContext.requirements`, `envisioningSelections` | Required | 1 |
| 4       | Architecture Diagram         | `ArchitectureOutput.mermaidCode`        | Optional¹           | 1          |
| 5       | Architecture Components      | `ArchitectureOutput.components`, `narrative` | Optional¹      | 1          |
| 6–8     | Azure Services               | `ServiceSelection[]`                    | Optional²           | 1–3        |
| 9–11    | Cost Breakdown               | `CostEstimate`                          | Optional³           | 1–3        |
| 12–14   | Business Value               | `ValueAssessment`                       | Optional⁴           | 1–3        |
| 15      | Next Steps / Call to Action  | Static template + `customerName`        | Required            | 1          |
| —       | Appendix (overflow)          | Truncated content, assumptions, caveats | As needed           | up to cap  |

¹ Omitted if System Architect Agent was skipped.
² Omitted if Azure Specialist Agent was skipped.
³ Omitted if Cost Specialist Agent was skipped.
⁴ Omitted if Business Value Agent was skipped.

**Slide count budget:** The total must not exceed **20 slides** (R-7). The generator allocates slides dynamically: required slides consume 4, optional sections share the remaining 16, overflow goes to an appendix or is truncated (see §6.3).

### 3.2 Title Slide

| Element          | Content                                                       |
| ---------------- | ------------------------------------------------------------- |
| Title            | `Project.description` (truncated to 80 characters)            |
| Subtitle         | `"Azure Solution Proposal"` (static)                          |
| Customer name    | `Project.customerName` or omitted                             |
| Date             | Generation date in `MMMM YYYY` format                        |
| Footer           | `"Confidential — Microsoft Internal Use"`                     |
| Layout           | Centered text, company logo top-right corner                  |

### 3.3 Executive Summary Slide

| Element          | Content                                                       |
| ---------------- | ------------------------------------------------------------- |
| Title            | `"Executive Summary"`                                         |
| Body             | If `ValueAssessment.executiveSummary` is available, use it verbatim (truncated to 500 characters). Otherwise, auto-generate a 3–5 sentence summary from `ProjectContext.requirements`. |
| Bullet points    | Up to 4 key highlights extracted from available agent outputs |
| Layout           | Title + body text with optional bullet list                   |

### 3.4 Use Case / Scenario Slide

| Element          | Content                                                       |
| ---------------- | ------------------------------------------------------------- |
| Title            | `"Scenario Overview"`                                         |
| Body             | Narrative built from `ProjectContext.requirements` key-value pairs. Each requirement is rendered as a labeled paragraph (e.g., **Target Users:** "10,000 concurrent users"). |
| Envisioning      | If `envisioningSelections` exist, include as a callout box: "Selected scenarios: …" |
| Layout           | Title + multi-paragraph body, optional callout                |

### 3.5 Architecture Diagram Slide

| Element          | Content                                                       |
| ---------------- | ------------------------------------------------------------- |
| Title            | `"Solution Architecture"`                                     |
| Diagram          | PNG image converted from `ArchitectureOutput.mermaidCode` (see §5.1) |
| Fallback         | If conversion fails → placeholder image with text: "Architecture diagram could not be rendered. See description below." + `ArchitectureOutput.narrative` |
| Components list  | If space allows, overlay a compact legend of top 5 components |
| Layout           | Full-width image with optional legend bar at bottom           |

A companion **Architecture Components** slide follows with a table:

| Column           | Source                                |
| ---------------- | ------------------------------------- |
| Component        | `components[].name`                   |
| Azure Service    | `components[].azureService`           |
| Description      | `components[].description`            |

If components exceed 10 rows, split across 2 slides (max).

### 3.6 Azure Services Slide(s)

One slide per logical group (up to 3 slides). Grouping heuristic: split at 5 services per slide.

| Column           | Source                                |
| ---------------- | ------------------------------------- |
| Component        | `ServiceSelection.componentName`      |
| Service          | `ServiceSelection.serviceName`        |
| SKU              | `ServiceSelection.sku`                |
| Region           | `ServiceSelection.region`             |
| Key Capabilities | `ServiceSelection.capabilities` (first 3, comma-separated) |

**Alternatives:** If any `ServiceSelection` has `.alternatives`, add a footnote row: _"Alternative: {serviceName} — {tradeOff}"_.

### 3.7 Cost Breakdown Slide(s)

**Primary slide — Cost Summary:**

| Element          | Content                                                       |
| ---------------- | ------------------------------------------------------------- |
| Title            | `"Estimated Azure Costs"`                                     |
| Summary bar      | Total monthly: `$X,XXX/mo` · Total annual: `$XX,XXX/yr`      |
| Pricing badge    | `pricingSource` indicator — "(Live pricing)" / "(Cached — approximate)" |
| Disclaimer       | `"Estimates exclude EA/CSP discounts. All prices in USD."`    |

**Detail table slide(s):** If `CostEstimate.items` has >5 items, split into pages of 10 rows max per slide (see §5.2).

| Column           | Source                                |
| ---------------- | ------------------------------------- |
| Service          | `items[].serviceName`                 |
| SKU              | `items[].sku`                         |
| Region           | `items[].region`                      |
| Monthly Cost     | `items[].monthlyCost` formatted as currency |

**Assumptions slide (if needed):** If `CostEstimate.assumptions.length > 3`, add a dedicated assumptions slide listing all assumptions as bullet points. Otherwise, embed as footnotes on the summary slide.

### 3.8 Business Value Slide(s)

**Primary slide — Value Drivers:**

| Element          | Content                                                       |
| ---------------- | ------------------------------------------------------------- |
| Title            | `"Business Value Assessment"`                                 |
| Driver cards     | Each `ValueAssessment.drivers[]` rendered as a card: **{name}** — {impact}. If `quantifiedEstimate` exists, show bold metric. |
| Layout           | 2-column card layout, max 6 drivers per slide                 |

**Benchmarks slide (if data available):**

| Element          | Content                                                       |
| ---------------- | ------------------------------------------------------------- |
| Title            | `"Industry Benchmarks"`                                       |
| Bullet list      | `ValueAssessment.benchmarks[]` (max 8 items)                  |
| Layout           | Title + bulleted list                                         |

### 3.9 Next Steps / Call to Action Slide

| Element          | Content                                                       |
| ---------------- | ------------------------------------------------------------- |
| Title            | `"Next Steps"`                                                |
| Body             | Static content with 3–4 recommended actions:                  |
|                  | 1. Review and refine the proposed architecture                |
|                  | 2. Validate cost estimates with customer workload data        |
|                  | 3. Schedule a deep-dive workshop with the Microsoft account team |
|                  | 4. Begin proof-of-concept in Azure                            |
| Contact          | `"Your Microsoft Account Team"` placeholder                   |
| Layout           | Numbered list, centered, contact info at bottom               |

---

## 4. Template Specification

### 4.1 Color Scheme

The deck uses a neutral professional palette that avoids trademarked brand colors to stay safe for external sharing. Specific branded templates can be substituted via configuration in future iterations.

| Role            | Color       | Hex       | Usage                              |
| --------------- | ----------- | --------- | ---------------------------------- |
| Primary         | Dark Blue   | `#0078D4` | Slide titles, header bars          |
| Secondary       | Light Blue  | `#50E6FF` | Accent elements, chart highlights  |
| Background      | White       | `#FFFFFF` | Slide background                   |
| Text Primary    | Charcoal    | `#323130` | Body text                          |
| Text Secondary  | Grey        | `#605E5C` | Captions, footnotes                |
| Accent          | Green       | `#107C10` | Positive metrics, success callouts |
| Warning         | Amber       | `#FF8C00` | "Approximate" badges, caveats      |
| Table Header    | Medium Blue | `#005A9E` | Table header background            |
| Table Alt Row   | Light Grey  | `#F3F2F1` | Alternating row background         |

### 4.2 Font Stack

| Element          | Font                | Size   | Weight     |
| ---------------- | ------------------- | ------ | ---------- |
| Slide title      | Segoe UI Semibold   | 28 pt  | 600        |
| Section header   | Segoe UI Semibold   | 22 pt  | 600        |
| Body text        | Segoe UI            | 14 pt  | 400        |
| Table text       | Segoe UI            | 12 pt  | 400        |
| Footnote         | Segoe UI            | 10 pt  | 400 Italic |
| Metric callout   | Segoe UI Bold       | 36 pt  | 700        |

**Fallback:** If Segoe UI is unavailable on the rendering system, the library embeds Calibri as a secondary font. PptxGenJS sets font preferences in slide master XML; the viewing application handles substitution.

### 4.3 Layout Grid

All slides use a consistent layout grid:

| Property           | Value                                      |
| ------------------ | ------------------------------------------ |
| Slide size         | Widescreen 16:9 (13.33″ × 7.5″)          |
| Left/right margin  | 0.5″                                      |
| Top margin         | 1.0″ (below title bar)                    |
| Bottom margin      | 0.5″ (above footer)                       |
| Title bar height   | 0.9″                                      |
| Footer bar height  | 0.35″                                     |
| Content area       | 12.33″ × 5.65″                            |
| Column gutter      | 0.3″ (for 2-column layouts)               |

### 4.4 Logo / Branding

| Element            | Placement                                  | Asset                         |
| ------------------ | ------------------------------------------ | ----------------------------- |
| Logo               | Title slide: top-right (0.8″ × 0.8″)      | Configurable via `LOGO_PATH` env variable; defaults to a generic cloud icon embedded as base64 PNG |
| Footer text        | All slides except title: bottom-left        | `"Generated by OneStopAgent"` |
| Slide number       | All slides except title: bottom-right       | `"Slide {n} of {total}"`     |
| Confidentiality    | Title slide only: bottom-center            | `"Confidential — Microsoft Internal Use"` |

---

## 5. Content Mapping Rules

### 5.1 How Architecture Diagram Becomes a Slide

**Pipeline:**

```
ArchitectureOutput.mermaidCode
  → Server-side Mermaid CLI (mmdc) renders to PNG at 1920×1080
  → PNG buffer is embedded into slide via PptxGenJS addImage()
  → Image is centered in the content area, scaled to fit (max 11″ × 5″)
```

**Mermaid CLI invocation:**

```bash
npx @mermaid-js/mermaid-cli -i input.mmd -o output.png -w 1920 -H 1080 --backgroundColor transparent
```

**Fallback cascade (on failure):**

1. **Retry once** with simplified theme (`--theme neutral`).
2. **SVG fallback** — attempt SVG render and convert with `sharp` library.
3. **Placeholder** — insert a slide with:
   - Grey box (dashed border) centered on slide with text: _"Architecture diagram could not be rendered as an image."_
   - Below the box: `ArchitectureOutput.narrative` as body text (truncated to 400 characters).
   - `warnings[]` entry: `"Diagram conversion failed — placeholder used"`.

**Complexity guard:** If `mermaidCode` contains >30 nodes (detected via regex count of node declarations), log a warning and proceed. The PRD caps diagram complexity at 30 nodes (R-5), so this should not occur under normal operation.

### 5.2 How Cost Table Maps to Slides

| Line Items | Slide Strategy                                                    |
| ---------- | ----------------------------------------------------------------- |
| 1–5        | Single slide: summary bar + inline table                          |
| 6–10       | Two slides: summary slide + one detail table slide                |
| 11–20      | Three slides: summary slide + two detail table slides (10 rows each) |
| 21+        | Three slides: summary slide + two detail slides (top 20 by cost). Remaining items collapsed into "Other services" row with summed cost. |

Each detail slide includes page indicator: _"Cost Details (Page 1 of 2)"_.

### 5.3 How Value Drivers Map to Slides

| Drivers  | Slide Strategy                                               |
| -------- | ------------------------------------------------------------ |
| 1–3      | Single slide: drivers as full-width cards                    |
| 4–6      | Single slide: 2-column card layout                           |
| 7+       | Two slides: first 6 on slide 1, remainder on slide 2         |

Benchmarks get a dedicated slide only if `benchmarks.length ≥ 1`. If benchmarks array is empty, the benchmarks slide is omitted.

### 5.4 Missing Section Handling

When an agent was skipped (not present in `Project.activeAgents`) or its output is `undefined`/`null`:

| Missing Section        | Behavior                                                        |
| ---------------------- | --------------------------------------------------------------- |
| Architecture           | Omit slides 4–5. Add note on Executive Summary: _"Architecture diagram not generated."_ |
| Azure Services         | Omit slides 6–8. Add note: _"Azure service details not generated."_ |
| Cost Estimate          | Omit slides 9–11. Add note: _"Cost estimate not generated."_   |
| Business Value         | Omit slides 12–14. Add note: _"Business value assessment not generated."_ |
| Envisioning            | No slide impact (envisioning enriches the use case slide but is not required). |
| All optional agents    | Deck contains only: Title, Executive Summary (auto-generated), Use Case, Next Steps (4 slides minimum). |

Missing-section notes are collected into a bulleted list appended to the Executive Summary slide body, visually styled in the Warning color (`#FF8C00`).

The `PresentationMeta.sectionsOmitted` array records the omitted section identifiers (e.g., `["architecture", "services", "cost", "business-value"]`).

---

## 6. PPTX Generation

### 6.1 Library Choice (PptxGenJS)

The server uses [PptxGenJS](https://github.com/gitbrent/PptxGenJS) (MIT license) for PPTX generation.

**Rationale:**

- Pure JavaScript — no native dependencies, runs in Node.js without external binaries.
- Supports images, tables, charts, custom layouts, and slide masters.
- Active maintenance and wide adoption.
- PRD §9 lists "PptxGenJS or officegen" — PptxGenJS is preferred due to richer API and active maintenance.

**Dependency:**

```json
{
  "pptxgenjs": "^3.12.0"
}
```

### 6.2 Server-Side Rendering Pipeline

```
[1] Route handler receives GET /api/projects/:id/export/pptx
[2] Load Project from store (Cosmos DB / in-memory Map)
[3] Validate project exists and belongs to authenticated user
[4] Check cache: compare sourceHash of current inputs vs last generated
      → If match and cached buffer exists: serve cached buffer (skip to step 9)
[5] Initialize PptxGenJS Presentation with slide master + template
[6] Iterate slide builder functions in order (§3.1):
      - buildTitleSlide(project)
      - buildExecutiveSummarySlide(context, meta)
      - buildUseCaseSlide(context)
      - buildArchitectureDiagramSlide(context)   // if available
      - buildArchitectureComponentsSlide(context) // if available
      - buildServicesSlides(context)              // if available, 1–3 slides
      - buildCostSlides(context)                  // if available, 1–3 slides
      - buildValueSlides(context)                 // if available, 1–3 slides
      - buildNextStepsSlide(project)
[7] Enforce slide count limit (§6.3)
[8] Generate binary buffer: pptx.write({ outputType: 'nodebuffer' })
[9] Populate PresentationMeta, persist to ProjectContext
[10] Stream buffer to HTTP response with appropriate headers (§7.1)
```

**Concurrency:** Generation is guarded by a per-project mutex (keyed on `projectId`). If a second request arrives while generation is in progress, it waits for the first to complete and serves the same result.

### 6.3 Slide Count Limits (Max 20)

After all builder functions execute, if `slideCount > 20`:

1. **Remove appendix slides** first (lowest priority).
2. **Merge cost detail slides** — collapse to a single detail slide with top-10 items + "Other" row.
3. **Merge service slides** — collapse to a single slide with top-8 services.
4. **Merge value slides** — collapse benchmarks into the value drivers slide.
5. **If still >20**, truncate body text on remaining slides and log a warning.

The `PresentationMeta.warnings` array records any truncation actions taken.

### 6.4 Content Truncation Rules

| Content Type       | Max Length     | Truncation Strategy                          |
| ------------------ | -------------- | -------------------------------------------- |
| Slide title        | 60 characters  | Ellipsis (`…`)                               |
| Body text block    | 500 characters | Truncate at last sentence boundary + `…`     |
| Table cell         | 100 characters | Truncate + `…`                               |
| Bullet item        | 150 characters | Truncate at last word boundary + `…`         |
| Narrative text     | 400 characters | Truncate at last sentence boundary + `…`     |
| Assumptions list   | 8 items        | Show first 8, footnote: `"+ N more"`         |
| Components table   | 20 rows        | Show first 20, footnote: `"+ N more"`        |

---

## 7. Export API

### 7.1 GET /api/projects/:id/export/pptx

**Request:**

```
GET /api/projects/:id/export/pptx
Authorization: Bearer <jwt>
```

No query parameters in MVP. Future: `?template=microsoft|neutral`, `?sections=arch,cost`.

**Success Response (200):**

```
HTTP/1.1 200 OK
Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation
Content-Disposition: attachment; filename="OneStopAgent-{customerName|projectId}-{YYYY-MM-DD}.pptx"
Content-Length: {fileSize}
X-Slide-Count: {slideCount}
X-Generated-At: {ISO-8601}
Cache-Control: no-store

<binary pptx body>
```

**Error Responses:**

| Status | Condition                                            | Body                                                            |
| ------ | ---------------------------------------------------- | --------------------------------------------------------------- |
| 401    | Missing or invalid Bearer token                      | `{ "error": "Unauthorized" }`                                   |
| 403    | Project belongs to a different user                  | `{ "error": "Forbidden" }`                                      |
| 404    | Project ID not found                                 | `{ "error": "Project not found" }`                              |
| 409    | Generation already in progress for this project      | `{ "error": "Generation in progress", "retryAfter": 5 }`       |
| 422    | No agent outputs available (nothing to compile)      | `{ "error": "No agent outputs available to generate a deck" }`  |
| 500    | Unrecoverable generation failure                     | `{ "error": "Presentation generation failed", "details": "…" }` |
| 503    | Server overloaded (generation queue full)            | `{ "error": "Service temporarily unavailable", "retryAfter": 10 }` |

### 7.2 Regeneration Logic

The agent computes a `sourceHash` (SHA-256) from the serialized `ProjectContext` inputs each time a request is received.

| Condition                                   | Action                                              |
| ------------------------------------------- | --------------------------------------------------- |
| `sourceHash` matches cached `PresentationMeta.sourceHash` | Serve cached `.pptx` buffer without regeneration |
| `sourceHash` differs (agent outputs changed) | Regenerate the deck, update cache and metadata     |
| No cached deck exists                        | Generate for the first time                        |
| User appends `?force=true` query parameter   | Always regenerate regardless of hash               |

Cache is stored in memory (MVP) alongside the project. The cached buffer is evicted when the project is deleted or when memory pressure triggers LRU eviction.

---

## 8. Frontend Behavior

### 8.1 Download Button

| Element          | Specification                                                     |
| ---------------- | ----------------------------------------------------------------- |
| Location         | Chat interface — appears as an action button in the Presentation Agent's chat card, and as a toolbar button in the project header. |
| Label            | `"Download PowerPoint"` with a document icon                      |
| Enabled when     | At least one agent besides the PM Agent has completed output      |
| Disabled state   | Grey button with tooltip: `"No agent outputs to export yet"`      |
| Click action     | `fetch('GET /api/projects/:id/export/pptx')` → trigger browser download via `Blob` + `URL.createObjectURL` |

### 8.2 Generation Progress

When the user clicks Download:

1. Button text changes to `"Generating…"` with a spinner.
2. If the server responds within 10 seconds, the download starts automatically.
3. If the request takes longer than 10 seconds, show an inline progress message: _"Building your deck — this may take a moment…"_
4. On completion, show a toast notification: _"PowerPoint downloaded successfully ({slideCount} slides)"_.
5. On error, show an error toast with the message from the API response body. If 422, suggest: _"Run at least one agent before exporting."_

### 8.3 Regeneration Prompt

When the user modifies any agent output (e.g., requests architecture changes) and a previously generated deck exists:

1. The Download button shows a badge indicator: _"Updates available"_.
2. Clicking the button triggers regeneration (the `sourceHash` will differ from the cached version).
3. A brief toast confirms: _"Deck regenerated with latest changes."_
4. No confirmation dialog is required — regeneration is non-destructive (the previous file is not persisted on disk).

---

## 9. Error Responses

All error responses follow the standard `ApiError` shape defined in the codebase:

```typescript
interface ApiError {
  error: string;
  details?: string;
}
```

**Error handling matrix:**

| Failure Scenario                            | HTTP Status | Recovery                                           |
| ------------------------------------------- | ----------- | -------------------------------------------------- |
| Project not found                           | 404         | User navigates to project list                     |
| No agent outputs at all                     | 422         | User runs at least one agent                       |
| Mermaid diagram conversion fails            | —           | Not an HTTP error; placeholder slide inserted, warning logged |
| PptxGenJS throws during generation          | 500         | Log full stack trace; return generic error          |
| Generated file exceeds 50 MB               | 500         | Truncate content aggressively; log warning          |
| Request timeout (>120 s)                    | 504         | User retries; consider simplifying project         |
| Concurrent generation for same project      | 409         | Client retries after `retryAfter` seconds          |

**Fallback PDF export (R-7):** If PPTX generation fails after 2 retries, the server attempts a simplified PDF export using the same content:

1. Render slides as HTML pages.
2. Convert to PDF via a headless renderer (e.g., Puppeteer or `pdf-lib`).
3. Serve with `Content-Type: application/pdf` and filename `…-.pdf`.
4. Response includes header `X-Export-Fallback: pdf` so the frontend can notify the user.

---

## 10. Edge Cases

| # | Edge Case                                     | Expected Behavior                                                             |
|---|-----------------------------------------------|-------------------------------------------------------------------------------|
| 1 | No agents completed (only project description) | Return 422 with message. Minimum viable deck requires at least `requirements`. |
| 2 | Only PM Agent gathered requirements, no specialists ran | Generate a minimal 4-slide deck: Title, Executive Summary (auto-generated), Use Case, Next Steps. |
| 3 | Architecture diagram has >30 nodes             | Proceed with rendering; if Mermaid CLI fails, use placeholder (§5.1).         |
| 4 | Mermaid code is syntactically invalid          | Fallback cascade in §5.1; `warnings[]` entry added.                           |
| 5 | Cost estimate has >50 line items               | Show top 20 by cost on slides; collapse remainder into "Other services" row.  |
| 6 | Value drivers exceed 12 items                  | Show first 12, truncate with footnote.                                        |
| 7 | `customerName` contains special characters     | Sanitize for filename (replace non-alphanumeric with `-`); render as-is in slide text. |
| 8 | `Project.description` is extremely long (>500 chars) | Truncate to 80 characters on title slide; full text on use case slide (truncated to 500 chars). |
| 9 | Concurrent download requests for same project  | Mutex ensures one generation at a time; second request waits or receives 409. |
| 10 | User downloads while an agent is still running | Generate with currently available outputs; agent-in-progress sections are omitted with note: _"Section in progress — regenerate after completion."_ |
| 11 | Project has been deleted mid-generation        | Return 404.                                                                   |
| 12 | Server out of memory during generation         | Catch `ENOMEM`; return 503 with `retryAfter`.                                 |
| 13 | Exported file exceeds 50 MB                    | Reduce embedded image resolution to 1280×720 and retry; if still too large, omit images and add placeholders. |
| 14 | Browser blocks download (popup blocker)        | Frontend detects failed download and shows manual download link.              |
| 15 | `CostEstimate.pricingSource` is `'approximate'` | Add visible amber badge on cost slides: _"⚠ Approximate pricing — API was unavailable"_. |

---

## Traceability

| FRD Section                | PRD Reference                                       |
| -------------------------- | --------------------------------------------------- |
| §2 Input/Output Contract   | FR-4 (Data Model), US-7                             |
| §3 Slide Deck Structure    | US-7 acceptance criteria (deck content list)        |
| §4 Template Specification  | US-7 ("clean, professional template")               |
| §5.1 Diagram → Slide       | US-7 (diagram conversion fallback), R-5             |
| §5.4 Missing Sections      | US-7 ("skipped agents → omit and note")             |
| §6.1 PptxGenJS             | §9 Technical Stack ("PptxGenJS or officegen")       |
| §6.3 Slide Limits          | R-7 (max 20 slides)                                |
| §6.4 Truncation            | R-7 ("truncate verbose content")                    |
| §7.1 Export API             | FR-1 (`GET /api/projects/:id/export/pptx`)          |
| §7.2 Regeneration           | US-7 ("regenerate after changes")                   |
| §8 Frontend Behavior       | US-7 ("download from chat interface"), FR-6         |
| §9 Error / PDF Fallback    | R-7 ("fallback PDF export")                         |
| §10 Edge Cases              | R-5 (diagram complexity), R-7 (large outputs)      |
