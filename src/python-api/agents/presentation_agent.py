"""Presentation Agent - generates executive-ready PowerPoint deck via PptxGenJS.

LLM-generated approach: the LLM produces a complete PptxGenJS script each time,
guided by the PPTX skill reference (pptxgenjs.md + SKILL.md).  Structured data
is extracted from pipeline state and passed to the LLM as context.  If Node.js
execution fails, the error is raised to the caller.
"""
import json
import logging
import os
from agents.state import AgentState

logger = logging.getLogger(__name__)


class PresentationAgent:
    name = "Presentation"
    emoji = "\U0001f4d1"

    # Loaded once from the installed PPTX skill
    _PPTXGENJS_GUIDE = ""
    _DESIGN_RULES = ""

    @classmethod
    def _load_skill(cls):
        """Load PptxGenJS skill guide from installed skill."""
        skill_dir = os.path.expanduser("~/.agents/skills/pptx")
        guide_path = os.path.join(skill_dir, "pptxgenjs.md")
        design_path = os.path.join(skill_dir, "SKILL.md")
        if os.path.exists(guide_path):
            with open(guide_path, "r", encoding="utf-8") as f:
                cls._PPTXGENJS_GUIDE = f.read()
        if os.path.exists(design_path):
            with open(design_path, "r", encoding="utf-8") as f:
                cls._DESIGN_RULES = f.read()

    def run(self, state: AgentState) -> AgentState:
        """Build slides with a refinement round for quality.

        1. Extract structured data from pipeline state
        2. LLM generates initial PptxGenJS script
        3. Execute → if it fails, LLM fixes the error
        4. If it succeeds, LLM reviews and polishes the script
        5. Execute the refined script
        """
        slide_data = self._build_slide_data(state)
        customer = state.customer_name or "Customer"

        from agents.llm import llm
        from services.presentation import execute_pptxgenjs

        # Round 1: Initial generation
        script = self._generate_pptxgenjs_script(slide_data, llm)

        try:
            path = execute_pptxgenjs(script, customer)
        except Exception as e:
            # Round 1 failed — LLM fixes the error
            logger.warning("Round 1 PPTX failed: %s — asking LLM to fix", e)
            script = self._fix_script(script, str(e), llm)
            path = execute_pptxgenjs(script, customer)

        # Round 2: Refinement — LLM reviews and polishes
        try:
            refined = self._refine_script(script, slide_data, llm)
            refined_path = execute_pptxgenjs(refined, customer)
            path = refined_path  # Use refined version
            logger.info("Presentation refined successfully")
        except Exception as e:
            logger.warning("Refinement failed: %s — keeping round 1 output", e)
            # Keep the round 1 output — it worked

        state.presentation_path = path
        return state

    # -- data extraction (unchanged logic) ---------------------------------

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
            # Compute confidence from pricing source breakdown
            source_str = est.get("pricingSource", "")
            if "live" in source_str:
                def _safe_leading_int(text: str) -> int:
                    """Extract leading integer from a string like '5 live', return 0 on failure."""
                    try:
                        return int(text.split()[0])
                    except (ValueError, IndexError):
                        return 0

                parts = [p.strip() for p in source_str.split(",") if p.strip()]
                live_count = sum(
                    _safe_leading_int(p) for p in parts
                    if "live" in p and "fallback" not in p
                )
                total_items = sum(_safe_leading_int(p) for p in parts)
                confidence = "High" if live_count / max(total_items, 1) > 0.7 else "Moderate"
            else:
                confidence = "Estimated"

            data["costs"] = {
                "totalMonthly": est.get("totalMonthly", 0),
                "totalAnnual": est.get("totalAnnual", 0),
                "confidence": confidence,
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
            # Add business case data for slides
            dashboard = roi.get("dashboard", {})
            bc = dashboard.get("businessCase")
            if bc:
                data["businessCase"] = bc

        if state.brainstorming.get("scenarios"):
            data["scenarios"] = state.brainstorming["scenarios"][:3]

        return data

    # -- LLM generates full PptxGenJS script -------------------------------

    def _generate_pptxgenjs_script(self, slide_data: dict, llm) -> str:
        """Have the LLM generate a complete PptxGenJS script."""
        # Ensure skill is loaded
        if not self._PPTXGENJS_GUIDE:
            self._load_skill()

        data_json = json.dumps(slide_data, indent=2, default=str)

        prompt = f"""Generate a COMPLETE PptxGenJS script that creates a professional \
Azure solution proposal presentation.

## DATA (inject this as a const at the top of the script):
```json
{data_json}
```

## SLIDE STRUCTURE (11 slides):
1. Title (dark bg) -- customer name, "Azure Solution Proposal", tagline, date
2. Executive Summary -- problem statement + key highlight bullets
3. Use Cases -- 2-3 scenario cards side-by-side with colored top borders
4. Business Value -- value driver cards with big metric numbers
5. Cost Summary -- stat callout cards (monthly, annual, confidence) + bar chart
6. Architecture -- narrative text + "Based on" reference
7. Business Case -- value bridge cards + sensitivity table
8. Next Steps (dark bg) -- numbered action items
9. Thank You (dark bg) -- customer name, "Powered by OneStopAgent"
10. Appendix: Solution Architecture -- component table
11. Appendix: Azure Services -- services + SKU + cost table

## RULES:
- Start with: const pptxgen = require("pptxgenjs");
- End with: pres.writeFile({{ fileName: OUTPUT_PATH }});
- Use LAYOUT_16x9 (10" x 5.625")
- NEVER use "#" prefix with hex colors
- NEVER use unicode/emoji characters -- use text labels instead
- Use breakLine: true between array items
- Use paraSpaceAfter not lineSpacing
- NEVER reuse option objects
- 0.5" minimum margins on all slides
- Dark sandwich: slides 1, 8, 9 get dark backgrounds
- Use Microsoft-style color palette (navy, white, accent blue, teal)
- Stat callout cards with colored top border bars
- Tables with alternating row colors
- Big numbers (28-36pt) for KPIs
- Keep all shapes within 10" x 5.625" bounds
- Use helper functions for formatting: fmt$(value), fmtPct(value)

## IMPORTANT:
- Return ONLY the JavaScript code, no markdown fences
- The DATA object should be embedded as a const at the top
- OUTPUT_PATH will be replaced by the caller -- use it as-is
"""

        system_parts = ["You are a PptxGenJS expert. Generate clean, professional presentation scripts."]
        if self._PPTXGENJS_GUIDE:
            system_parts.append(f"\nPptxGenJS Reference:\n{self._PPTXGENJS_GUIDE[:3000]}")
        if self._DESIGN_RULES:
            system_parts.append(f"\nDesign Rules:\n{self._DESIGN_RULES[:2000]}")

        response = llm.invoke([
            {"role": "system", "content": "\n".join(system_parts)},
            {"role": "user", "content": prompt},
        ])

        script = response.content.strip()
        # Strip markdown fences if present
        if script.startswith("```"):
            script = script.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        if "pptxgenjs" not in script.lower() or "writefile" not in script.lower():
            raise ValueError("Generated script missing required PptxGenJS structure")

        return script

    def _fix_script(self, broken_script: str, error: str, llm) -> str:
        """Ask LLM to fix a broken PptxGenJS script based on the error."""
        response = llm.invoke([
            {"role": "system", "content": "You are a PptxGenJS expert. Fix the JavaScript error in this script. Return ONLY the corrected JavaScript code, no markdown fences."},
            {"role": "user", "content": f"This PptxGenJS script failed with error:\n{error[:500]}\n\nFix the script:\n{broken_script[:8000]}"},
        ])
        script = response.content.strip()
        if script.startswith("```"):
            script = script.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return script

    def _refine_script(self, working_script: str, slide_data: dict, llm) -> str:
        """LLM reviews a working script and polishes it for quality."""
        data_summary = json.dumps({
            "customer": slide_data.get("customer", ""),
            "industry": slide_data.get("industry", ""),
            "driverCount": len(slide_data.get("valueDrivers", [])),
            "serviceCount": len(slide_data.get("services", [])),
            "hasROI": bool(slide_data.get("roi")),
        }, default=str)

        response = llm.invoke([
            {"role": "system", "content": (
                "You are a PptxGenJS expert and presentation design critic. "
                "Review this working script and improve it. Focus on:\n"
                "1. Visual polish — ensure consistent spacing, alignment, margins\n"
                "2. Text fitting — shorten any text that would overflow slide bounds\n"
                "3. Data accuracy — verify all numbers from the DATA object are used correctly\n"
                "4. Color consistency — ensure the Microsoft color palette is applied throughout\n"
                "5. Professional feel — add subtle design touches (accent lines, card shadows)\n\n"
                "Return the COMPLETE improved script. Do NOT return a diff or partial changes."
            )},
            {"role": "user", "content": (
                f"Context: {data_summary}\n\n"
                f"Review and improve this working PptxGenJS script:\n{working_script}"
            )},
        ])

        script = response.content.strip()
        if script.startswith("```"):
            script = script.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        if "pptxgenjs" not in script.lower() or "writefile" not in script.lower():
            raise ValueError("Refined script missing required PptxGenJS structure")

        return script