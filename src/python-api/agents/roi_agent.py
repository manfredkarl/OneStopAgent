"""ROI Agent — calculates return on investment from cost and business value data.

Pure math — no LLM calls, no regex parsing, no made-up numbers.
Uses the structured annual_value_estimate from BusinessValueAgent.
If drivers lack dollar estimates, signals that user input is needed.
"""
from agents.state import AgentState


class ROIAgent:
    name = "ROI Calculator"
    emoji = "📈"

    def run(self, state: AgentState) -> AgentState:
        annual_cost = state.costs.get("estimate", {}).get("totalAnnual", 0)
        drivers = state.business_value.get("drivers", [])

        if annual_cost <= 0:
            state.roi = self._needs_info(
                reason="No cost estimate available.",
                questions=["Please run the Cost agent first or provide an estimated annual Azure spend."],
            )
            return state

        monetized = []
        qualitative = []
        questions = []
        total_annual_value = 0.0

        for driver in drivers:
            name = driver.get("name", "")
            annual_value = driver.get("annual_value_estimate")
            info_needed = driver.get("info_needed")

            if annual_value is not None and isinstance(annual_value, (int, float)) and annual_value > 0:
                monetized.append({
                    "name": name,
                    "annual_value": round(float(annual_value), 2),
                })
                total_annual_value += float(annual_value)
            else:
                qualitative.append(name)
                if info_needed:
                    questions.append(f"To monetize **{name}**: {info_needed}")

        if total_annual_value <= 0:
            state.roi = self._needs_info(
                reason="None of the value drivers have dollar estimates yet.",
                questions=questions or ["Could you share approximate annual revenue, headcount, or current infrastructure spend so we can estimate ROI?"],
                qualitative=qualitative,
            )
            return state

        roi_percent = ((total_annual_value - annual_cost) / annual_cost) * 100
        payback_months = (annual_cost / (total_annual_value / 12)) if total_annual_value > 0 else None

        state.roi = {
            "annual_cost": round(annual_cost, 2),
            "annual_value": round(total_annual_value, 2),
            "roi_percent": round(roi_percent, 1),
            "payback_months": round(payback_months, 1) if payback_months else None,
            "monetized_drivers": monetized,
            "qualitative_benefits": qualitative,
            "needs_info": questions if questions else None,
        }
        return state

    def _needs_info(self, reason: str, questions: list[str], qualitative: list[str] | None = None) -> dict:
        """Return an ROI result that signals we need user input to calculate."""
        return {
            "annual_cost": 0,
            "annual_value": None,
            "roi_percent": None,
            "payback_months": None,
            "monetized_drivers": [],
            "qualitative_benefits": qualitative or [],
            "needs_info": questions,
        }
