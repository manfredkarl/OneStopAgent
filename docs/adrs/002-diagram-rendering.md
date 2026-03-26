# ADR-002: Architecture Diagram Rendering

## Status
Accepted

## Date
2026-03-26

## Context
The System Architect Agent (pipeline stage 2) generates architecture diagrams as part of every project. These diagrams must render in the browser within the chat interface (FR-6), be exportable to PNG and SVG for inclusion in the PowerPoint deck (frd-presentation.md §6.2), and respect hard complexity limits of 30 nodes and 60 edges (frd-architecture.md §2.3.2, R-5). The rendering solution must work with LLM-generated diagram code, since the agent produces diagram definitions programmatically. The Presentation Agent also needs to convert diagrams to raster images for PPTX embedding, with a fallback cascade if rendering fails (frd-presentation.md §6.2).

## Decision
Use **Mermaid.js** for client-side diagram rendering in the browser and server-side rendering for PPTX image export.

## Options Considered

### Option 1: Mermaid.js
**Pros:**
- LLMs produce Mermaid syntax natively and reliably — no translation layer needed
- Client-side rendering eliminates server compute for diagram display
- Supports flowchart, sequence, class, and other diagram types out of the box
- Built-in export to SVG; can convert to PNG via canvas API or `sharp` library
- Lightweight library with no heavy dependencies
- Wide adoption — well-documented, actively maintained, large community
- Complexity validation (node/edge counting) can be done by parsing the text before rendering

**Cons:**
- Limited visual customisation compared to programmatic drawing libraries
- Complex diagrams with many nodes can become visually cluttered without manual layout
- Server-side rendering for PPTX requires a headless browser or the `@mermaid-js/mermaid-cli` package

### Option 2: D3.js
**Pros:**
- Extremely powerful and flexible — full control over every visual element
- Can produce highly polished, interactive, custom visualisations
- Massive ecosystem of examples and extensions

**Cons:**
- Requires imperative code to define each diagram — LLMs cannot generate D3 code as reliably as declarative Mermaid syntax
- Significantly higher development effort to build architecture diagram templates
- No built-in architecture diagram primitives; would need to build node/edge/layout logic from scratch
- Overkill for standard flowchart-style architecture diagrams

### Option 3: draw.io Embed
**Pros:**
- Rich interactive editing experience (drag, drop, resize, connect)
- Supports a wide range of diagram types and shape libraries
- Users could manually refine generated diagrams

**Cons:**
- Requires embedding a third-party iframe or web component
- LLM output would need to be translated to draw.io's XML format — fragile and complex
- External service dependency conflicts with tenant-scoping requirements (NFR-8)
- No clean programmatic API for server-side PPTX generation

### Option 4: Excalidraw
**Pros:**
- Clean, hand-drawn aesthetic that is visually appealing
- Open-source with React integration
- Collaborative editing support

**Cons:**
- LLM-to-Excalidraw format translation is not well-supported
- No declarative text-based format comparable to Mermaid
- Hand-drawn style may not meet enterprise presentation expectations
- Limited architecture-specific shape libraries

### Option 5: Server-Side Image Generation (e.g., Puppeteer + HTML templates)
**Pros:**
- Full control over rendering output and visual fidelity
- Can use any HTML/CSS/SVG for diagram layout
- Consistent rendering across all clients

**Cons:**
- Adds server compute cost and latency for every diagram render
- Requires headless browser infrastructure (Puppeteer/Playwright)
- Eliminates interactive client-side features (zoom, pan, click-to-inspect)
- More complex deployment (browser binaries in container images)

## Rationale
Mermaid.js is selected because it uniquely aligns with the LLM-driven diagram generation workflow. The System Architect Agent produces Mermaid flowchart syntax (e.g., `flowchart TD`) as structured output (frd-architecture.md §2.3), and Mermaid renders this directly in the browser without any translation step. This eliminates an entire class of bugs related to format conversion.

The complexity limits (R-5: max 30 nodes, 60 edges) can be enforced by parsing the Mermaid text definition before rendering — counting nodes and edges is straightforward in the text format. If limits are exceeded, the agent consolidates nodes into logical groups and regenerates (frd-architecture.md §2.3.2), keeping the validation loop entirely within the text domain.

For PPTX generation, the Presentation Agent renders Mermaid to SVG/PNG server-side using the `@mermaid-js/mermaid-cli` package or the `sharp` library (frd-presentation.md §6.2). A three-step fallback cascade handles render failures: retry with simplified theme → SVG fallback via `sharp` → placeholder image with narrative text.

D3.js and Excalidraw were rejected because LLMs cannot reliably generate their formats. draw.io introduces an external service dependency. Server-side-only rendering adds unnecessary infrastructure complexity and eliminates the interactive in-browser experience.

## Consequences
**Positive:**
- Zero-friction LLM → diagram pipeline: agent output renders directly without transformation
- Client-side rendering reduces server load and improves perceived latency
- Mermaid text is human-readable and version-controllable
- Export to PNG/SVG supports both in-app viewing and PPTX embedding
- Complexity validation is simple text parsing, not DOM inspection

**Negative:**
- Layout is automatic and not manually adjustable by the user in the chat view
- Very dense diagrams (near the 30-node limit) may be visually cramped
- Server-side rendering for PPTX still requires `mermaid-cli` or `sharp` as a dependency
- Mermaid's styling options are more limited than fully custom SVG/D3 approaches

## References
- PRD §9 — Technical Stack: "Mermaid (flowchart TD format)"
- frd-architecture.md §2.3 — Mermaid Diagram Generation
- frd-architecture.md §2.3.2 R-5 — Complexity Limits (max 30 nodes, max 60 edges)
- frd-architecture.md §2.3.5 — Validation Pipeline (parse → count → validate → render)
- frd-presentation.md §6.2 — Server-Side Rendering Pipeline (Mermaid → SVG/PNG for PPTX)
- frd-presentation.md §6.2 — Diagram Rendering Fallback Cascade (retry → SVG fallback → placeholder)
- PRD §4.6 FR-6 — Chat Interface (in-browser Mermaid rendering)
