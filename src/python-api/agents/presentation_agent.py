"""Presentation Agent — generates executive-ready PowerPoint deck via PptxGenJS.

Template-based approach: a hardcoded, tested PptxGenJS script template handles
all layout / design.  The LLM is only asked to produce polished *text content*
(tagline, bullets, narrative) as structured JSON, which is injected into the
template.  If Node.js execution fails, the error is raised to the caller.
"""
import json
import logging
import re
from agents.state import AgentState
from services.presentation import execute_pptxgenjs

logger = logging.getLogger(__name__)


# ── Design reference (kept for documentation) ────────────────────────────

PPTXGENJS_REFERENCE = r"""
## PptxGenJS Quick Reference
- NEVER use "#" with hex colors
- Use bullet: true, NEVER unicode "•"
- Use breakLine: true between array items
- NEVER reuse option objects — PptxGenJS mutates them in-place
- Use paraSpaceAfter not lineSpacing with bullets
- NEVER use accent lines under titles
"""

DESIGN_GUIDANCE = """
## Slide Design Principles (embedded in template)
- Microsoft color palette: dark navy, white content, accent blue, teal highlights
- Segoe UI / Arial fonts
- Dark sandwich structure (dark title + closing, light content slides)
- Stat callout cards, tables, conditional bar chart
"""


# ── PptxGenJS slide template ─────────────────────────────────────────────
# The template reads a DATA JSON object and builds 11 slide types.
# Each slide is conditional — it only renders when the relevant data exists.

SLIDE_TEMPLATE = r"""
const pptxgen = require("pptxgenjs");
const DATA = __DATA_PLACEHOLDER__;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "OneStopAgent";

// ── Color palette ──
const DARK   = "0F1B2D";
const WHITE  = "FFFFFF";
const ACCENT = "0078D4";
const TEAL   = "00B7C3";
const LIGHT  = "F5F5F5";
const TEXT_C  = "1E293B";
const MUTED  = "64748B";
const BORDER = "E2E8F0";
const FONT   = "Segoe UI";

// ── Helpers ──
function fmt$(v) {
  if (v == null) return "$0";
  const n = typeof v === "string" ? parseFloat(v.replace(/[^0-9.]/g, "")) : v;
  if (isNaN(n)) return String(v);
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}
function fmtPct(v) {
  if (v == null) return "N/A";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (isNaN(n)) return String(v);
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 }) + "%";
}
function safe(v, fallback) { return (v != null && v !== "") ? String(v) : (fallback || ""); }

// ════════════════════════════════════════════════════════════════════════
// SLIDE 1 — Title (dark)
// ════════════════════════════════════════════════════════════════════════
(function titleSlide() {
  const s = pres.addSlide();
  s.background = { color: DARK };
  // Customer name
  s.addText(safe(DATA.customer, "Customer"), {
    x: 0.5, y: 1.0, w: 9.0, h: 0.7,
    fontSize: 18, fontFace: FONT, color: TEAL, bold: true,
    align: "left"
  });
  // Main title
  s.addText("Azure Solution Proposal", {
    x: 0.5, y: 1.7, w: 9.0, h: 1.0,
    fontSize: 36, fontFace: FONT, color: WHITE, bold: true,
    align: "left"
  });
  // Tagline
  if (DATA.tagline) {
    s.addText(DATA.tagline, {
      x: 0.5, y: 2.9, w: 9.0, h: 0.6,
      fontSize: 14, fontFace: FONT, color: MUTED, italic: true,
      align: "left"
    });
  }
  // Bottom accent bar
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.8, w: 2.0, h: 0.06, fill: { color: ACCENT }
  });
  s.addText("Powered by OneStopAgent", {
    x: 0.5, y: 5.0, w: 4.0, h: 0.35,
    fontSize: 9, fontFace: FONT, color: MUTED
  });
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 2 — Executive Summary
// ════════════════════════════════════════════════════════════════════════
(function execSummarySlide() {
  if (!DATA.executiveSummary || DATA.executiveSummary.length === 0) return;
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText("Executive Summary", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: FONT, color: TEXT_C, bold: true
  });
  // Problem statement
  if (DATA.problemStatement) {
    s.addText(DATA.problemStatement, {
      x: 0.5, y: 1.05, w: 9.0, h: 0.7,
      fontSize: 13, fontFace: FONT, color: MUTED, italic: true,
      valign: "top"
    });
  }
  // Key highlights as bullets
  const bullets = DATA.executiveSummary.map(function(item, i) {
    return { text: item, options: { bullet: true, breakLine: i < DATA.executiveSummary.length - 1, fontSize: 13, fontFace: FONT, color: TEXT_C, paraSpaceAfter: 8 } };
  });
  const bulletY = DATA.problemStatement ? 1.9 : 1.1;
  s.addText(bullets, {
    x: 0.5, y: bulletY, w: 9.0, h: 3.5,
    valign: "top"
  });
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 3 — Use Cases
// ════════════════════════════════════════════════════════════════════════
(function useCasesSlide() {
  if (!DATA.scenarios || DATA.scenarios.length === 0) return;
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText("Exemplary Use Cases", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: FONT, color: TEXT_C, bold: true
  });
  const cases = DATA.scenarios.slice(0, 3);
  cases.forEach(function(sc, i) {
    const bullets = [
      { text: safe(sc.title, "Use Case"), options: { fontSize: 16, fontFace: FONT, color: TEXT_C, bold: true, paraSpaceAfter: 4 } },
      { text: safe(sc.description, ""), options: { fontSize: 12, fontFace: FONT, color: MUTED, paraSpaceAfter: 8 } }
    ];
    if (sc.azure_services && sc.azure_services.length > 0) {
      bullets.push({ text: "Services: " + sc.azure_services.join(", "), options: { fontSize: 10, fontFace: FONT, color: ACCENT, italic: true } });
    }
    const yPos = 1.1 + i * 1.5;
    s.addText(bullets, { x: 0.5, y: yPos, w: 9.0, h: 1.3, valign: "top" });
  });
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 4 — Business Value
// ════════════════════════════════════════════════════════════════════════
(function bvSlide() {
  if (!DATA.drivers || DATA.drivers.length === 0) return;
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText("Business Value", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: FONT, color: TEXT_C, bold: true
  });
  // Show up to 3 value-driver cards side by side
  const cards = DATA.drivers.slice(0, 3);
  const cardW = cards.length === 1 ? 9.0 : (9.0 - 0.3 * (cards.length - 1)) / cards.length;
  cards.forEach(function(d, i) {
    const cx = 0.5 + i * (cardW + 0.3);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: cx, y: 1.1, w: cardW, h: 2.8,
      fill: { color: LIGHT }, rectRadius: 0.1
    });
    // Impact metric big
    s.addText(safe(d.metric || d.impact, "—"), {
      x: cx + 0.2, y: 1.3, w: cardW - 0.4, h: 0.8,
      fontSize: 28, fontFace: FONT, color: ACCENT, bold: true, align: "center", shrinkText: true
    });
    // Driver name
    s.addText(safe(d.name, "Value Driver"), {
      x: cx + 0.2, y: 2.15, w: cardW - 0.4, h: 0.4,
      fontSize: 14, fontFace: FONT, color: TEXT_C, bold: true, align: "center"
    });
    // Description
    if (d.description) {
      s.addText(d.description, {
        x: cx + 0.2, y: 2.6, w: cardW - 0.4, h: 1.1,
        fontSize: 10, fontFace: FONT, color: MUTED, align: "center", valign: "top"
      });
    }
  });
  // If more than 3 drivers, add remaining as bullets below
  if (DATA.drivers.length > 3) {
    const extra = DATA.drivers.slice(3).map(function(d, i) {
      return { text: safe(d.name, "") + (d.impact ? " — " + d.impact : ""), options: { bullet: true, breakLine: i < DATA.drivers.length - 4, fontSize: 11, fontFace: FONT, color: TEXT_C, paraSpaceAfter: 4 } };
    });
    s.addText(extra, { x: 0.5, y: 4.1, w: 9.0, h: 1.2, valign: "top" });
  }
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 5 — Cost Summary
// ════════════════════════════════════════════════════════════════════════
(function costSlide() {
  if (!DATA.costs) return;
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText("Cost Summary", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: FONT, color: TEXT_C, bold: true
  });
  // Stat callout cards
  const stats = [
    { label: "Monthly Estimate", value: fmt$(DATA.costs.totalMonthly) },
    { label: "Annual Estimate", value: fmt$(DATA.costs.totalAnnual) },
    { label: "Pricing Source", value: safe(DATA.costs.pricingSource, "Azure Pricing") }
  ];
  stats.forEach(function(st, i) {
    const cardX = 0.5 + i * 3.1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: cardX, y: 1.1, w: 2.8, h: 1.3,
      fill: { color: LIGHT }, rectRadius: 0.1
    });
    s.addText(st.value, {
      x: cardX, y: 1.2, w: 2.8, h: 0.7,
      fontSize: 26, fontFace: FONT, color: ACCENT, bold: true, align: "center"
    });
    s.addText(st.label, {
      x: cardX, y: 1.85, w: 2.8, h: 0.4,
      fontSize: 11, fontFace: FONT, color: MUTED, align: "center"
    });
  });
  // Bar chart of top 5 services (if cost items exist)
  const items = (DATA.costs.items || []).filter(function(ci) { return ci.monthly > 0; });
  if (items.length > 0) {
    items.sort(function(a, b) { return b.monthly - a.monthly; });
    const top = items.slice(0, 5);
    s.addChart(pres.charts.BAR, [{
      name: "Monthly Cost",
      labels: top.map(function(ci) { return ci.service; }),
      values: top.map(function(ci) { return ci.monthly; })
    }], {
      x: 0.5, y: 2.7, w: 9.0, h: 2.7, barDir: "col",
      chartColors: [ACCENT, TEAL, "5B9BD5", "A5A5A5", "FFC000"],
      chartArea: { fill: { color: WHITE }, roundedCorners: true },
      catAxisLabelColor: MUTED, catAxisLabelFontSize: 9, catAxisLabelFontFace: FONT,
      valAxisLabelColor: MUTED, valAxisLabelFontSize: 9,
      valGridLine: { color: BORDER, size: 0.5 }, catGridLine: { style: "none" },
      showValue: true, dataLabelPosition: "outEnd", dataLabelColor: TEXT_C, dataLabelFontSize: 9,
      valAxisNumFmt: "$#,##0"
    });
  }
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 6 — Architecture (narrative only)
// ════════════════════════════════════════════════════════════════════════
(function archSlide() {
  if (!DATA.architecture) return;
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText("Architecture", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: FONT, color: TEXT_C, bold: true
  });
  const narr = DATA.solutionNarrative || DATA.architecture.narrative || "";
  if (narr) {
    s.addText(narr, {
      x: 0.5, y: 1.1, w: 9.0, h: 3.0,
      fontSize: 14, fontFace: FONT, color: TEXT_C, valign: "top"
    });
  }
  const basedOn = DATA.architecture.basedOn;
  if (basedOn) {
    s.addText("Based on: " + basedOn, {
      x: 0.5, y: 4.3, w: 9.0, h: 0.4,
      fontSize: 11, fontFace: FONT, color: ACCENT, italic: true
    });
  }
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 7 — ROI
// ════════════════════════════════════════════════════════════════════════
(function roiSlide() {
  if (!DATA.roi) return;
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText("Return on Investment", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: FONT, color: TEXT_C, bold: true
  });
  const roiStats = [
    { label: "ROI", value: fmtPct(DATA.roi.percent) },
    { label: "Payback Period", value: DATA.roi.paybackMonths != null ? DATA.roi.paybackMonths + " mo" : "N/A" },
    { label: "Annual Value", value: fmt$(DATA.roi.annualValue) },
    { label: "Annual Cost", value: fmt$(DATA.roi.annualCost) }
  ];
  roiStats.forEach(function(st, i) {
    const cx = 0.3 + i * 2.4;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: cx, y: 1.1, w: 2.2, h: 1.4,
      fill: { color: i === 0 ? ACCENT : LIGHT }, rectRadius: 0.1
    });
    s.addText(st.value, {
      x: cx, y: 1.2, w: 2.2, h: 0.8,
      fontSize: 28, fontFace: FONT, color: i === 0 ? WHITE : ACCENT, bold: true, align: "center", shrinkText: true
    });
    s.addText(st.label, {
      x: cx, y: 1.95, w: 2.2, h: 0.4,
      fontSize: 11, fontFace: FONT, color: i === 0 ? WHITE : MUTED, align: "center"
    });
  });
  // Qualitative benefits
  var quals = DATA.roi.qualitativeBenefits || [];
  if (quals.length > 0) {
    var qBullets = quals.slice(0, 5).map(function(b, i) {
      return { text: String(b), options: { bullet: true, breakLine: i < Math.min(quals.length, 5) - 1, fontSize: 11, fontFace: FONT, color: TEXT_C, paraSpaceAfter: 6 } };
    });
    s.addText("Additional Benefits", {
      x: 0.5, y: 2.7, w: 9.0, h: 0.4,
      fontSize: 14, fontFace: FONT, color: TEXT_C, bold: true
    });
    s.addText(qBullets, { x: 0.5, y: 3.1, w: 9.0, h: 2.2, valign: "top" });
  }
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 8 — Next Steps (dark)
// ════════════════════════════════════════════════════════════════════════
(function nextStepsSlide() {
  if (!DATA.nextSteps || DATA.nextSteps.length === 0) return;
  const s = pres.addSlide();
  s.background = { color: DARK };
  s.addText("Next Steps", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: FONT, color: WHITE, bold: true
  });
  const steps = DATA.nextSteps.slice(0, 6).map(function(step, i) {
    return { text: step, options: { bullet: true, breakLine: i < Math.min(DATA.nextSteps.length, 6) - 1, fontSize: 14, fontFace: FONT, color: WHITE, paraSpaceAfter: 12 } };
  });
  s.addText(steps, {
    x: 0.5, y: 1.1, w: 9.0, h: 3.8,
    valign: "top"
  });
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 9 — Closing (dark)
// ════════════════════════════════════════════════════════════════════════
(function closingSlide() {
  const s = pres.addSlide();
  s.background = { color: DARK };
  s.addText("Thank You", {
    x: 0.5, y: 1.5, w: 9.0, h: 1.0,
    fontSize: 40, fontFace: FONT, color: WHITE, bold: true, align: "center"
  });
  s.addText(safe(DATA.customer, ""), {
    x: 0.5, y: 2.6, w: 9.0, h: 0.6,
    fontSize: 20, fontFace: FONT, color: TEAL, align: "center"
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 4.0, y: 3.5, w: 2.0, h: 0.06, fill: { color: ACCENT }
  });
  s.addText("Powered by OneStopAgent", {
    x: 0.5, y: 3.8, w: 9.0, h: 0.4,
    fontSize: 10, fontFace: FONT, color: MUTED, align: "center"
  });
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 10 — Appendix: Solution Architecture (component table)
// ════════════════════════════════════════════════════════════════════════
(function appendixArchSlide() {
  if (!DATA.architecture || !DATA.architecture.components || DATA.architecture.components.length === 0) return;
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText("Solution Architecture", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: FONT, color: TEXT_C, bold: true
  });
  // Narrative summary
  const narr = DATA.solutionNarrative || DATA.architecture.narrative || "";
  if (narr) {
    s.addText(narr, {
      x: 0.5, y: 0.95, w: 9.0, h: 0.7,
      fontSize: 12, fontFace: FONT, color: MUTED, valign: "top"
    });
  }
  // Component table
  const comps = DATA.architecture.components.slice(0, 12);
  const headerRow = [
    { text: "Component", options: { fill: { color: ACCENT }, color: WHITE, bold: true, fontSize: 11, fontFace: FONT } },
    { text: "Azure Service", options: { fill: { color: ACCENT }, color: WHITE, bold: true, fontSize: 11, fontFace: FONT } },
    { text: "Description", options: { fill: { color: ACCENT }, color: WHITE, bold: true, fontSize: 11, fontFace: FONT } }
  ];
  const rows = [headerRow];
  comps.forEach(function(c, idx) {
    const bg = idx % 2 === 0 ? WHITE : LIGHT;
    rows.push([
      { text: safe(c.name || c.component, ""), options: { fill: { color: bg }, fontSize: 10, fontFace: FONT, color: TEXT_C, bold: true } },
      { text: safe(c.service || c.azureService || "", ""), options: { fill: { color: bg }, fontSize: 10, fontFace: FONT, color: TEXT_C } },
      { text: safe(c.description || c.purpose || "", ""), options: { fill: { color: bg }, fontSize: 10, fontFace: FONT, color: MUTED } }
    ]);
  });
  s.addTable(rows, {
    x: 0.5, y: 1.75, w: 9.0,
    border: { pt: 0.5, color: BORDER },
    colW: [2.5, 2.5, 4.0],
    rowH: 0.3,
    autoPage: false
  });
})();

// ════════════════════════════════════════════════════════════════════════
// SLIDE 11 — Appendix: Azure Services & SKUs
// ════════════════════════════════════════════════════════════════════════
(function servicesSlide() {
  if (!DATA.services || DATA.services.length === 0) return;
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText("Azure Services", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: FONT, color: TEXT_C, bold: true
  });
  const headerRow = [
    { text: "Service", options: { fill: { color: ACCENT }, color: WHITE, bold: true, fontSize: 11, fontFace: FONT } },
    { text: "SKU / Tier", options: { fill: { color: ACCENT }, color: WHITE, bold: true, fontSize: 11, fontFace: FONT } },
    { text: "Region", options: { fill: { color: ACCENT }, color: WHITE, bold: true, fontSize: 11, fontFace: FONT } },
    { text: "Monthly Cost", options: { fill: { color: ACCENT }, color: WHITE, bold: true, fontSize: 11, fontFace: FONT } }
  ];
  const rows = [headerRow];
  // Merge cost items if available
  const costMap = {};
  if (DATA.costs && DATA.costs.items) {
    DATA.costs.items.forEach(function(ci) { costMap[ci.service] = ci.monthly; });
  }
  DATA.services.slice(0, 12).forEach(function(svc, idx) {
    const bg = idx % 2 === 0 ? WHITE : LIGHT;
    const cost = costMap[svc.name] != null ? fmt$(costMap[svc.name]) : "—";
    rows.push([
      { text: safe(svc.name), options: { fill: { color: bg }, fontSize: 10, fontFace: FONT, color: TEXT_C, bold: true } },
      { text: safe(svc.sku, "—"), options: { fill: { color: bg }, fontSize: 10, fontFace: FONT, color: TEXT_C } },
      { text: safe(svc.region, "—"), options: { fill: { color: bg }, fontSize: 10, fontFace: FONT, color: TEXT_C } },
      { text: cost, options: { fill: { color: bg }, fontSize: 10, fontFace: FONT, color: TEXT_C, align: "right" } }
    ]);
  });
  s.addTable(rows, {
    x: 0.5, y: 1.05, w: 9.0,
    border: { pt: 0.5, color: BORDER },
    colW: [3.0, 2.0, 2.0, 2.0],
    rowH: 0.35,
    autoPage: false
  });
})();

// ── Save ──
pres.writeFile({ fileName: OUTPUT_PATH });
"""


class PresentationAgent:
    name = "Presentation"
    emoji = "📑"

    def run(self, state: AgentState) -> AgentState:
        """Build slides using a fixed template + LLM-generated text content.

        1. Extract structured data from pipeline state
        2. Ask LLM to polish/generate text content only (JSON)
        3. Merge data + LLM content → inject into JS template
        4. Execute via Node.js
        """
        slide_data = self._build_slide_data(state)
        customer = state.customer_name or "Customer"

        from agents.llm import llm
        content = self._generate_slide_content(slide_data, llm)
        merged = self._merge_data(slide_data, content)
        script = SLIDE_TEMPLATE.replace("__DATA_PLACEHOLDER__", json.dumps(merged, default=str))
        path = execute_pptxgenjs(script, customer)

        state.presentation_path = path
        return state

    # ── data extraction (unchanged logic) ────────────────────────────────

    def _build_slide_data(self, state: AgentState) -> dict:
        """Extract all relevant data from state for slide generation."""
        customer = state.customer_name or "Customer"

        data: dict = {
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

        if state.brainstorming.get("scenarios"):
            data["scenarios"] = state.brainstorming["scenarios"][:3]

        return data

    # ── LLM generates text content only ──────────────────────────────────

    def _generate_slide_content(self, slide_data: dict, llm) -> dict:
        """Ask the LLM to produce polished text content as JSON.

        The LLM never writes code — only human-readable slide copy.
        """
        data_json = json.dumps(slide_data, indent=2, default=str)

        response = llm.invoke([
            {
                "role": "system",
                "content": (
                    "You are an expert executive-presentation copywriter. "
                    "Given raw data about an Azure solution proposal, produce polished, "
                    "concise slide TEXT CONTENT as a JSON object.\n\n"
                    "Return ONLY valid JSON (no markdown fences, no explanation).\n\n"
                    "Required JSON keys:\n"
                    "  tagline        — string, 6-12 word inspirational subtitle\n"
                    "  problemStatement — string, 1-2 sentence problem framing\n"
                    "  executiveSummary — array of 3-5 bullet strings (key highlights)\n"
                    "  solutionNarrative — string, 2-3 sentence architecture overview\n"
                    "  drivers         — array of objects {name, metric, description} "
                    "(up to 3 top value drivers, metric = concise impact figure)\n"
                    "  nextSteps       — array of 4-5 actionable recommendation strings\n\n"
                    "Rules:\n"
                    "- Keep bullets under 15 words each\n"
                    "- Use concrete numbers from the data when available\n"
                    "- Write for C-level executives — no jargon, no filler\n"
                    "- If data for a field is missing, still provide a reasonable default"
                ),
            },
            {
                "role": "user",
                "content": f"Produce slide text content for this proposal:\n\n{data_json}",
            },
        ])

        raw = response.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON object from the response
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning("LLM returned invalid JSON for slide content — using defaults")
            return {
                "tagline": "Azure Solution Proposal",
                "problemStatement": "Business challenge requiring cloud-native solution",
                "executiveSummary": ["Scalable Azure architecture", "Cost-optimized design", "Enterprise-grade security"],
                "solutionNarrative": "Leveraging Azure services for scalability and reliability.",
                "drivers": [],
                "nextSteps": ["Schedule technical deep-dive", "Define proof of concept scope", "Align on timeline and resources"],
            }

    # ── Merge structured data + LLM text ─────────────────────────────────

    @staticmethod
    def _merge_data(slide_data: dict, content: dict) -> dict:
        """Combine pipeline data with LLM-polished text into the DATA object
        consumed by the PptxGenJS template."""
        merged: dict = {
            "customer": slide_data.get("customer", "Customer"),
            "tagline": content.get("tagline", ""),
            "problemStatement": content.get("problemStatement", slide_data.get("problem", "")),
            "executiveSummary": content.get("executiveSummary", []),
            "solutionNarrative": content.get("solutionNarrative", ""),
        }

        # Architecture (from pipeline)
        if slide_data.get("architecture"):
            merged["architecture"] = slide_data["architecture"]

        # Services (from pipeline)
        if slide_data.get("services"):
            merged["services"] = slide_data["services"]

        # Scenarios / use cases (from pipeline)
        if slide_data.get("scenarios"):
            merged["scenarios"] = slide_data["scenarios"]

        # Costs (from pipeline)
        if slide_data.get("costs"):
            merged["costs"] = slide_data["costs"]

        # Business-value drivers — prefer LLM-polished, fall back to pipeline
        if content.get("drivers"):
            merged["drivers"] = content["drivers"]
        elif slide_data.get("businessValue", {}).get("drivers"):
            merged["drivers"] = slide_data["businessValue"]["drivers"]

        # ROI (from pipeline)
        if slide_data.get("roi"):
            merged["roi"] = slide_data["roi"]

        # Next steps (from LLM)
        merged["nextSteps"] = content.get("nextSteps", [])

        # Truncate LLM content to prevent slide overflow
        if isinstance(merged.get("executiveSummary"), list):
            merged["executiveSummary"] = [s[:150] for s in merged["executiveSummary"]]
        if isinstance(merged.get("nextSteps"), list):
            merged["nextSteps"] = [s[:150] for s in merged["nextSteps"]]
        if isinstance(merged.get("tagline"), str) and len(merged["tagline"]) > 80:
            merged["tagline"] = merged["tagline"][:77] + "..."
        if isinstance(merged.get("problemStatement"), str) and len(merged["problemStatement"]) > 300:
            merged["problemStatement"] = merged["problemStatement"][:297] + "..."

        return merged
