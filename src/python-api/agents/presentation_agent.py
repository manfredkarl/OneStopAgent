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
from core.utils import strip_markdown_fences

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
        """Build slides — generate, auto-fix on failure, optional quick polish.

        1. LLM generates initial PptxGenJS script
        2. Execute → if it fails, LLM fixes the specific error and retries once
        3. Quick polish pass: fix formatting issues without full regeneration
        """
        slide_data = self._build_slide_data(state)
        company_name = (state.company_profile or {}).get("name", "") if not state.customer_name else ""
        customer = state.customer_name or company_name or "Customer"

        from agents.llm import llm
        from services.presentation import execute_pptxgenjs

        # Round 1: Initial generation + execution
        script = self._generate_pptxgenjs_script(slide_data, llm)

        try:
            path = execute_pptxgenjs(script, customer)
        except (RuntimeError, FileNotFoundError, OSError) as e:
            # Auto-fix: ask LLM to fix the specific error
            logger.warning("PPTX execution failed: %s — auto-fixing", e)
            try:
                script = self._fix_script(script, str(e), llm)
                path = execute_pptxgenjs(script, customer)
            except (RuntimeError, FileNotFoundError, OSError) as e2:
                logger.error("PPTX auto-fix also failed: %s", e2)
                raise RuntimeError(f"Presentation generation failed after auto-fix: {e2}") from e2

        state.presentation_path = path
        return state

    # -- data extraction (unchanged logic) ---------------------------------

    def _build_slide_data(self, state: AgentState) -> dict:
        """Extract all relevant data from state for slide generation."""
        company_name = (state.company_profile or {}).get("name", "") if not state.customer_name else ""
        customer = state.customer_name or company_name or "Customer"

        data: dict = {
            "customer": customer,
            "problem": state.user_input,
            "clarifications": state.clarifications or "",
            "industry": state.brainstorming.get("industry", "Cross-Industry"),
        }

        # Extract customer challenges/pain points from brainstorming
        if state.brainstorming:
            data["customer_challenges"] = state.brainstorming.get("pain_points", [])
            data["market_drivers"] = state.brainstorming.get("market_drivers", [])
            data["competitive_context"] = state.brainstorming.get("competitive_landscape", "")

        # Add company profile for branded slides
        company = state.company_profile
        if company:
            p = company
            data["companyProfile"] = {
                "name": p.get("name", customer),
                "industry": p.get("industry", ""),
                "headquarters": p.get("headquarters", ""),
                "employeeCount": p.get("employeeCount"),
                "annualRevenue": p.get("annualRevenue"),
                "revenueCurrency": p.get("revenueCurrency", "USD"),
                "itSpendEstimate": p.get("itSpendEstimate"),
                "knownAzureUsage": p.get("knownAzureUsage", []),
                "cloudProvider": p.get("cloudProvider", ""),
            }
            # Surface Azure usage and cloud context for "Why Azure?" slide
            if company.get("knownAzureUsage"):
                data["existing_azure_services"] = company.get("knownAzureUsage", [])
            if company.get("cloudProvider"):
                data["cloud_provider"] = company.get("cloudProvider", "")
            if company.get("erp"):
                data["erp"] = company.get("erp", "")

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
            # Compute confidence from pricing source breakdown or per-item confidence
            confidence_summary = est.get("confidenceSummary")
            if isinstance(confidence_summary, str) and confidence_summary in ("High", "Moderate", "Estimated", "high", "moderate", "low"):
                confidence = confidence_summary.capitalize() if confidence_summary.islower() else confidence_summary
            else:
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

        # Build dynamic context hints for the slide structure instructions
        challenges = slide_data.get("customer_challenges", [])
        challenges_hint = ", ".join(challenges) if challenges else "derive from the customer's stated problem"

        drivers = slide_data.get("market_drivers", [])
        drivers_hint = ", ".join(drivers) if drivers else "infer from the customer's industry and problem"

        competitive_hint = slide_data.get("competitive_context", "") or "not specified"

        # Build "Why Azure?" hint based on customer's existing cloud context
        azure_parts: list[str] = []
        existing_svcs = slide_data.get("existing_azure_services", [])
        if existing_svcs:
            azure_parts.append(
                f"Customer already uses {', '.join(existing_svcs)} -- emphasize building on existing investments."
            )
        cloud_provider = slide_data.get("cloud_provider", "")
        if cloud_provider and cloud_provider.lower() not in ("azure", "microsoft", ""):
            azure_parts.append(
                f"Customer currently uses {cloud_provider} -- frame Azure advantages specifically vs {cloud_provider}."
            )
        erp = slide_data.get("erp", "")
        if erp:
            azure_parts.append(f"Customer uses {erp} -- highlight Azure's native integration with {erp}.")
        if not azure_parts:
            azure_parts.append("3 capability cards: Enterprise scale, Security & Compliance, AI-first roadmap")
        azure_hint = " ".join(azure_parts)

        prompt = f"""Generate a COMPLETE PptxGenJS script that creates a professional \
Azure solution proposal presentation.

## DATA (inject this as a const at the top of the script):
```json
{data_json}
```

## SLIDE STRUCTURE (12 slides):
1. Title (dark bg) -- customer name, "Azure Solution Proposal", industry-specific tagline derived from the customer's use case (NOT generic), date
2. Why Now? -- Reference the customer's SPECIFIC challenges from customer_challenges: {challenges_hint}. \
Include market drivers: {drivers_hint}. \
If competitive context exists, mention it: {competitive_hint}. \
Do NOT use generic industry platitudes. Every point should be traceable to the customer's stated situation or problem.
3. Proposed Solution -- architecture visual (narrative + "Based on" reference)
4. Business Impact -- ROI, value drivers with big numbers (payback period, ROI %, annual value)
5. Use Cases -- 2-3 scenario cards side-by-side with colored top borders
6. 3-Year Total Cost -- monthly, annual, confidence level; stat callout cards + bar chart. \
Add a small note explaining confidence: High = most prices from live Azure API, Moderate = mix of live and fallback, Estimated = based on public pricing estimates.
7. Implementation Roadmap -- 3 phases: Foundation (M1-3), Pilot (M4-6), Scale (M7-12)
8. Why Azure? -- {azure_hint}
9. Next Steps (dark bg) -- numbered action items (typically 3-4 steps)
10. Thank You (dark bg) -- customer name, "Powered by OneStopAgent"
11. Appendix: Architecture Details -- component table with layer, service, role
12. Appendix: Azure Services & Costs -- services + SKU + monthly cost table

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
- Dark sandwich: slides 1, 9, 10 get dark backgrounds (navy: 003366)
- Use Microsoft-style color palette (navy, white, accent blue, teal)
- Stat callout cards with colored top border bars
- Tables with alternating row colors
- Big numbers (28-36pt) for KPIs on slides 4 and 6
- Keep all shapes within 10" x 5.625" bounds
- Use helper functions for formatting: fmt$(value), fmtPct(value)

## IMPORTANT:
- Return ONLY the JavaScript code, no markdown fences
- The DATA object should be embedded as a const at the top
- OUTPUT_PATH will be replaced by the caller -- use it as-is
- Keep the script under 450 lines -- be concise, use helper functions
- Test mentally: every addText/addShape must have valid x,y,w,h within bounds
- TRUNCATE long text: driver names max 40 chars, descriptions max 80 chars
- Format all dollar values with commas: "$1,234,567" not "$1234567"
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
        script = strip_markdown_fences(script)

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
        script = strip_markdown_fences(script)
        return script