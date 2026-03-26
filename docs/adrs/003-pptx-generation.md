# ADR-003: PowerPoint Generation Library

## Status
Accepted

## Date
2026-03-26

## Context
The Presentation Agent (pipeline stage 6) compiles outputs from all preceding agents — architecture diagrams, Azure service selections, cost estimates, business value assessments, and envisioning scenarios — into a downloadable PowerPoint (.pptx) file. The generation must happen server-side, support programmatic slide layout with tables, images, and formatted text, enforce a maximum of 20 slides with content truncation rules (frd-presentation.md §6.3–§6.4), and embed Mermaid-rendered architecture diagrams as raster images. The solution must run in a Node.js/TypeScript environment to match the project's technology stack (PRD §9) and must not depend on external services to avoid availability risks and tenant-boundary concerns (NFR-8).

## Decision
Use **PptxGenJS** for server-side PowerPoint file generation.

## Options Considered

### Option 1: PptxGenJS
**Pros:**
- Pure JavaScript/TypeScript — runs natively in Node.js without native binaries or external dependencies
- Supports all required slide elements: text, tables, images (base64 and buffer), shapes, charts
- Programmatic control over slide masters, layouts, positioning, and styling
- Active maintenance with regular releases and responsive issue tracking
- Well-documented API with extensive examples
- No external service calls — generation happens entirely in-process

**Cons:**
- No built-in WYSIWYG preview — output must be downloaded and opened in PowerPoint to verify
- Complex layouts require manual coordinate calculations (x, y, w, h in inches)
- Limited support for advanced PowerPoint features like animations or transitions (not needed for this use case)

### Option 2: officegen
**Pros:**
- Pure JavaScript library for generating Office documents (PPTX, DOCX, XLSX)
- Lightweight with minimal dependencies
- Simple API for basic slide creation

**Cons:**
- Significantly less active maintenance — fewer recent commits and releases
- More limited feature set compared to PptxGenJS (weaker table and image support)
- Smaller community and fewer usage examples
- PRD §9 lists it as a fallback option behind PptxGenJS

### Option 3: python-pptx (via microservice)
**Pros:**
- Mature, well-tested Python library with comprehensive PowerPoint feature support
- Strong community and documentation
- Supports complex layouts, placeholder-based templates, and slide masters

**Cons:**
- Requires a separate Python microservice, adding operational complexity (deployment, scaling, monitoring)
- Cross-language RPC introduces latency and failure modes (network, serialisation)
- Breaks the single-language stack principle (PRD §9: Node.js/TypeScript)
- Adds a service dependency that must stay available within tenant boundaries

### Option 4: LibreOffice Headless
**Pros:**
- Can convert various formats to PPTX with high fidelity
- Supports template-based generation via macro scripting
- Free and open-source

**Cons:**
- Requires LibreOffice binary installation in the container image (~500MB+)
- Slow startup time for headless instances
- Fragile scripting interface — macro-based generation is hard to maintain
- Significant container image bloat and security surface area
- Not designed for programmatic slide-by-slide construction

### Option 5: Google Slides API
**Pros:**
- Rich API for programmatic slide creation and manipulation
- Real-time collaboration and sharing features
- Web-based preview and editing

**Cons:**
- External Google service dependency — violates NFR-8 (tenant-scoped data residency)
- Requires Google Workspace accounts and API credentials
- Data leaves Microsoft tenant boundaries
- Network dependency for generation — offline/isolated environments unsupported
- Licensing and cost implications for enterprise use

## Rationale
PptxGenJS is selected because it satisfies all technical constraints with minimal complexity. As a pure JavaScript library, it runs natively in the Node.js/TypeScript stack specified in PRD §9, requiring no additional microservices, native binaries, or external API calls. This keeps the deployment footprint small and eliminates network-dependent failure modes during file generation.

The library provides the programmatic control needed to implement the rendering pipeline defined in frd-presentation.md §6.2: aggregating agent outputs, populating slide templates, enforcing the 20-slide maximum (§6.3), and applying content truncation rules (§6.4 — 400-character text limit, 10-row table limit, 400-word narrative limit). Image support (base64 buffers) enables embedding Mermaid-rendered architecture diagrams directly into slides.

officegen was considered as an alternative (PRD §9 lists both) but is less actively maintained and has weaker support for the table and image features required by the cost breakdown and architecture diagram slides. python-pptx would require a cross-language microservice, contradicting the single-stack approach. LibreOffice and Google Slides introduce unacceptable external dependencies.

## Consequences
**Positive:**
- Single-language stack — no cross-service communication for PPTX generation
- No external service dependencies — generation is self-contained and tenant-scoped
- Full programmatic control over slide layout, content placement, and styling
- Lightweight dependency — small npm package, no native binaries
- Straightforward testing — generate files and verify structure programmatically

**Negative:**
- Manual coordinate-based layout requires careful positioning logic for each slide template
- No real-time preview — generated files must be downloaded and opened to verify visual quality
- Template changes require code changes (no visual template editor)
- Complex slide designs (e.g., multi-column layouts with mixed content types) require more development effort

## References
- PRD §9 — Technical Stack: "PptxGenJS or officegen (PptxGenJS preferred)"
- frd-presentation.md §6.1 — Library Choice (PptxGenJS rationale)
- frd-presentation.md §6.2 — Server-Side Rendering Pipeline (aggregate → template → truncate → generate)
- frd-presentation.md §6.3 — Slide Count Limits (max 20 slides, fallback collapse strategy)
- frd-presentation.md §6.4 — Content Truncation Rules (400 chars text, 10 rows table, 400 words narrative)
- frd-presentation.md §3.1 — Slide Order (Title → Executive Summary → Use Case → Architecture → Services → Cost → Value → Next Steps)
- PRD §5 NFR-8 — Data Residency & LLM Privacy (no external service dependency)
