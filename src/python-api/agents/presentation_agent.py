"""Presentation Agent — generates executive-ready PowerPoint deck via PptxGenJS.

Uses the LLM to generate a complete PptxGenJS Node.js script with professional
design (color palettes, shapes, charts, icons, modern layout), then executes it
to produce the .pptx file.  Falls back to python-pptx if LLM/Node.js unavailable.
"""
import json
import logging
from agents.state import AgentState
from services.presentation import execute_pptxgenjs, create_pptx_python

logger = logging.getLogger(__name__)


# ── Design reference (from Anthropic PPTX skill) ────────────────────────

PPTXGENJS_REFERENCE = r"""
## PptxGenJS Quick Reference

### Setup
```javascript
const pptxgen = require("pptxgenjs");
let pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';  // 10" x 5.625"
pres.author = 'OneStopAgent';
let slide = pres.addSlide();
```

### Text
```javascript
slide.addText("Title", { x: 0.5, y: 0.5, w: 9, h: 0.8, fontSize: 36, fontFace: "Arial", color: "363636", bold: true });
// Rich text arrays
slide.addText([
  { text: "Bold ", options: { bold: true, breakLine: true } },
  { text: "Normal", options: {} }
], { x: 0.5, y: 1.5, w: 8, h: 2 });
// Bullets
slide.addText([
  { text: "Item 1", options: { bullet: true, breakLine: true } },
  { text: "Item 2", options: { bullet: true } }
], { x: 0.5, y: 2, w: 8, h: 2 });
```

### Shapes
```javascript
slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.5, fill: { color: "1E2761" } });
slide.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 1, w: 0.08, h: 1.5, fill: { color: "0891B2" } }); // accent bar
```

### Tables
```javascript
slide.addTable([
  [{ text: "Header", options: { fill: { color: "1E2761" }, color: "FFFFFF", bold: true } }, ...],
  ["Cell 1", "Cell 2"]
], { x: 0.5, y: 1.5, w: 9, border: { pt: 0.5, color: "E2E8F0" }, colW: [3, 3, 3] });
```

### Charts
```javascript
slide.addChart(pres.charts.BAR, [{
  name: "Cost", labels: ["Service A", "Service B"], values: [150, 300]
}], {
  x: 0.5, y: 1.5, w: 9, h: 3.5, barDir: "col",
  chartColors: ["0D9488", "14B8A6", "5EEAD4"],
  chartArea: { fill: { color: "FFFFFF" }, roundedCorners: true },
  catAxisLabelColor: "64748B", valAxisLabelColor: "64748B",
  valGridLine: { color: "E2E8F0", size: 0.5 }, catGridLine: { style: "none" },
  showValue: true, dataLabelPosition: "outEnd", dataLabelColor: "1E293B"
});
```

### Backgrounds
```javascript
slide.background = { color: "1E2761" };  // dark slide
slide.background = { color: "F8FAFC" };  // light content slide
```

### Save
```javascript
pres.writeFile({ fileName: OUTPUT_PATH });
```

## CRITICAL RULES
- NEVER use "#" with hex colors (causes corruption)
- NEVER encode opacity in hex strings (e.g. "00000020") — use opacity property
- Use bullet: true, NEVER unicode "•"
- Use breakLine: true between array items
- Each pres = new pptxgen() must be fresh — never reuse
- NEVER reuse option objects — PptxGenJS mutates them in-place
- Avoid lineSpacing with bullets — use paraSpaceAfter instead
- NEVER use accent lines under titles
"""

DESIGN_GUIDANCE = """
## Slide Design Principles

### Color Strategy
- Pick one dominant color (60-70% weight), 1-2 supporting tones, one sharp accent
- Dark backgrounds for title + conclusion, light for content ("sandwich" structure)
- Choose colors that match the customer's industry/topic

### Layout Variety
- NEVER repeat the same layout on consecutive slides
- Mix: two-column, icon rows, stat callouts, tables, charts, full-width
- Every slide needs a visual element (shape, chart, icon, or table) — no text-only slides
- Large stat callouts: big numbers 48-60pt with small labels below

### Typography
- Slide titles: 28-36pt bold
- Section headers: 18-22pt bold
- Body text: 12-14pt
- Always left-align body text; center only titles
- 0.5" minimum margins from slide edges

### Shapes for Visual Interest
- Use colored rectangles as background sections
- Thin accent bars (0.08" wide) beside key content
- Cards: white rectangles with subtle shadows for grouped content
"""


class PresentationAgent:
    name = "Presentation"
    emoji = "📑"

    def run(self, state: AgentState) -> AgentState:
        """Generate a professional PptxGenJS script via LLM, review it, then execute.

        Two-pass approach:
        1. Generate the full PptxGenJS script
        2. LLM reviews for visual quality & common errors, returns corrected script
        Falls back to python-pptx if the LLM or Node.js execution fails.
        """
        slide_data = self._build_slide_data(state)
        customer = state.customer_name or "Customer"

        try:
            from agents.llm import llm
            script = self._generate_pptxgenjs_script(slide_data, state, llm)
            script = self._review_script(script, llm)
            path = execute_pptxgenjs(script, customer)
        except Exception as exc:
            logger.warning("PptxGenJS path failed (%s), falling back to python-pptx", exc)
            path = create_pptx_python(slide_data, customer)

        state.presentation_path = path
        return state

    def _build_slide_data(self, state: AgentState) -> dict:
        """Extract all relevant data from state for the LLM to design slides."""
        customer = state.customer_name or "Customer"

        data = {
            "customer": customer,
            "problem": state.user_input,
            "clarifications": state.clarifications or "",
            "industry": state.brainstorming.get("industry", "Cross-Industry"),
        }

        if state.architecture:
            data["architecture"] = {
                "narrative": state.architecture.get("narrative", ""),
                "basedOn": state.architecture.get("basedOn", ""),
                "components": state.architecture.get("components", [])[:12],
            }

        if state.services.get("selections"):
            data["services"] = [
                {"name": s.get("serviceName", ""), "sku": s.get("sku", ""), "region": s.get("region", "")}
                for s in state.services["selections"][:12]
            ]

        if state.costs.get("estimate"):
            est = state.costs["estimate"]
            data["costs"] = {
                "totalMonthly": est.get("totalMonthly", 0),
                "totalAnnual": est.get("totalAnnual", 0),
                "pricingSource": est.get("pricingSource", "N/A"),
                "items": [
                    {"service": i.get("serviceName", ""), "sku": i.get("sku", ""), "monthly": i.get("monthlyCost", 0)}
                    for i in est.get("items", [])[:12]
                ],
            }

        if state.business_value.get("drivers"):
            data["businessValue"] = {
                "summary": state.business_value.get("executiveSummary", ""),
                "confidence": state.business_value.get("confidenceLevel", "moderate"),
                "drivers": [
                    {"name": d.get("name", ""), "impact": d.get("impact", d.get("estimate", ""))}
                    for d in state.business_value["drivers"]
                ],
            }

        if state.roi:
            roi = state.roi
            data["roi"] = {
                "percent": roi.get("roi_percent"),
                "paybackMonths": roi.get("payback_months"),
                "annualCost": roi.get("annual_cost"),
                "annualValue": roi.get("annual_value"),
                "monetizedDrivers": roi.get("monetized_drivers", []),
                "qualitativeBenefits": roi.get("qualitative_benefits", []),
            }

        return data

    def _generate_pptxgenjs_script(self, slide_data: dict, state: AgentState, llm) -> str:
        """Use LLM to generate a complete PptxGenJS Node.js script."""
        data_json = json.dumps(slide_data, indent=2, default=str)

        response = llm.invoke([
            {
                "role": "system",
                "content": (
                    "You are an expert presentation designer. Generate a COMPLETE, EXECUTABLE "
                    "Node.js script using PptxGenJS that creates a professional executive deck.\n\n"
                    "The script must:\n"
                    "1. require('pptxgenjs') and create a new presentation\n"
                    "2. Create 8-12 visually distinct slides\n"
                    "3. Use the OUTPUT_PATH placeholder for the file name: pres.writeFile({ fileName: OUTPUT_PATH })\n"
                    "4. Be a complete, runnable script — no imports other than pptxgenjs\n"
                    "5. Use modern, professional design (not default PowerPoint templates)\n\n"
                    "Return ONLY the JavaScript code, no markdown fences, no explanation.\n\n"
                    f"{PPTXGENJS_REFERENCE}\n\n"
                    f"{DESIGN_GUIDANCE}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Create an executive Azure solution proposal deck for this data:\n\n"
                    f"{data_json}\n\n"
                    "REQUIRED SLIDES (in order):\n"
                    "1. Title slide — dark background, customer name, 'Azure Solution Proposal'\n"
                    "2. Problem & Opportunity — the user's challenge with visual emphasis\n"
                    "3. Solution Overview — architecture narrative with key highlights\n"
                    "4. Architecture Components — table or card layout showing Azure services\n"
                    "5. Azure Services & SKUs — table with service selections\n"
                    "6. Cost Estimate — bar chart of top costs + summary stats\n"
                    "7. Business Value — value drivers with impact metrics\n"
                    "8. ROI — large stat callouts (ROI %, payback period, annual value)\n"
                    "9. Next Steps — actionable recommendations\n\n"
                    "Skip any slide where data is missing. Add a closing slide.\n"
                    "Use a bold color palette appropriate for the customer's industry.\n"
                    "Make every slide visually distinct — vary layouts across slides."
                ),
            },
        ])

        script = response.content.strip()
        # Strip markdown fences if present
        if script.startswith("```"):
            script = script.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        return script

    def _review_script(self, script: str, llm) -> str:
        """LLM reviews the generated PptxGenJS script for quality and common errors.

        Catches issues like:
        - '#' prefixed hex colors (causes file corruption)
        - Overlapping elements (same x/y on multiple items)
        - Text overflow (too much text in small boxes)
        - Missing visual variety (all slides look the same)
        - Reused option objects (PptxGenJS mutates in-place)
        - Unicode bullets instead of bullet:true
        """
        response = llm.invoke([
            {
                "role": "system",
                "content": (
                    "You are a PptxGenJS code reviewer. Review the script below and return "
                    "the CORRECTED, COMPLETE script. Fix any issues you find.\n\n"
                    "CHECK FOR AND FIX:\n"
                    "1. Hex colors must NEVER have '#' prefix — strip it (e.g. '363636' not '#363636')\n"
                    "2. Never encode opacity in hex (e.g. '00000020' is wrong)\n"
                    "3. Use bullet:true, NEVER unicode '•' characters\n"
                    "4. Use breakLine:true between text array items\n"
                    "5. Never reuse option objects — clone them for each element\n"
                    "6. Avoid lineSpacing with bullets — use paraSpaceAfter instead\n"
                    "7. Elements must not overlap — check x/y/w/h coordinates\n"
                    "8. Text boxes should be large enough for their content\n"
                    "9. Tables must have enough height for all rows\n"
                    "10. Slide backgrounds must contrast with text colors (dark bg = light text)\n"
                    "11. Vary slide layouts — no two consecutive slides should look identical\n"
                    "12. Every chart needs proper colors and labels\n"
                    "13. Never use accent lines under titles\n\n"
                    "Return ONLY the corrected JavaScript code. No markdown fences, no explanation.\n"
                    "If the script is already good, return it unchanged."
                ),
            },
            {
                "role": "user",
                "content": f"Review and fix this PptxGenJS script:\n\n{script}",
            },
        ])

        reviewed = response.content.strip()
        if reviewed.startswith("```"):
            reviewed = reviewed.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        # Sanity check — reviewed script should still be valid JS
        if "pptxgenjs" in reviewed and "writeFile" in reviewed:
            return reviewed
        logger.warning("Review produced invalid script — using original")
        return script
