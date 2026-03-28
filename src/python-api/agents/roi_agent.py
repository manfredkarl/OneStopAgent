"""ROI Agent — calculates return on investment from cost and business value data."""
import re
from agents.state import AgentState

DEFAULT_HOURLY_RATE = 75  # $/hr for IT staff time savings


class ROIAgent:
    name = "ROI Calculator"
    emoji = "📈"

    def run(self, state: AgentState) -> AgentState:
        annual_cost = state.costs.get("estimate", {}).get("totalAnnual", 0)
        drivers = state.business_value.get("drivers", [])

        if annual_cost <= 0:
            state.roi = self._non_calculable("No cost estimate available")
            return state

        monetized = []
        qualitative = []
        total_annual_value = 0.0
        assumptions = []

        for driver in drivers:
            is_monetizable = driver.get("monetizable", True)  # default True for backward compat
            estimate = driver.get("estimate", driver.get("quantifiedEstimate", ""))
            name = driver.get("name", "")

            if not estimate or not is_monetizable:
                qualitative.append(name)
                continue

            value, method, assumption = self._monetize_driver(estimate, annual_cost)

            if value is not None and value > 0:
                monetized.append({
                    "name": name,
                    "annual_value": round(value, 2),
                    "method": method,
                })
                total_annual_value += value
                if assumption:
                    assumptions.append(assumption)
            else:
                qualitative.append(name)

        if total_annual_value <= 0:
            state.roi = self._non_calculable("No value drivers could be monetized")
            state.roi["qualitative_benefits"] = qualitative
            return state

        roi_percent = ((total_annual_value - annual_cost) / annual_cost) * 100
        payback_months = annual_cost / (total_annual_value / 12) if total_annual_value > 0 else None

        state.roi = {
            "annual_cost": round(annual_cost, 2),
            "annual_value": round(total_annual_value, 2),
            "roi_percent": round(roi_percent, 1),
            "payback_months": round(payback_months, 1) if payback_months else None,
            "monetized_drivers": monetized,
            "qualitative_benefits": qualitative,
            "assumptions": assumptions + [
                f"IT staff hourly rate: ${DEFAULT_HOURLY_RATE}",
                "Value estimates based on industry benchmarks",
            ],
        }
        return state

    def _monetize_driver(self, estimate: str, annual_cost: float) -> tuple:
        """Convert a value driver estimate string to an annual dollar amount.

        Returns: (value, method, assumption) or (None, None, None) if not convertible.

        Patterns:
        1. "X% reduction in ..." → annual_cost * X/100
        2. "X% increase in ..." → approximate using benchmark
        3. "$X saved per month/year" → direct conversion
        4. "X hours saved per week" → X * 52 * $75
        5. Non-convertible → (None, None, None)
        """
        est = estimate.strip()

        # Pattern 1: "X% reduction in ..." or "Estimated X% reduction"
        match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:reduction|decrease|savings|save|lower)', est, re.I)
        if match:
            pct = float(match.group(1))
            value = annual_cost * (pct / 100)
            return value, f"{pct}% of annual cost", f"Assumed {pct}% cost reduction saves ${value:,.0f}/year"

        # Pattern 2: "X% increase in ..." or "X% improvement"
        match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:increase|improvement|growth|uplift|boost)', est, re.I)
        if match:
            pct = float(match.group(1))
            # Use annual_cost as a rough proxy for revenue impact
            value = annual_cost * (pct / 100) * 2  # 2x multiplier for revenue vs cost
            return value, f"{pct}% revenue benchmark", f"Assumed {pct}% revenue improvement, estimated at ${value:,.0f}/year"

        # Pattern 3: "$X saved per month" or "$X,XXX per year"
        match = re.search(r'\$\s*([\d,]+(?:\.\d+)?)\s*(?:per|/)\s*(month|year|annually|monthly)', est, re.I)
        if match:
            amount = float(match.group(1).replace(',', ''))
            period = match.group(2).lower()
            if period in ('month', 'monthly'):
                value = amount * 12
            else:
                value = amount
            return value, "Direct dollar estimate", None

        # Pattern 4: "X hours saved per week"
        match = re.search(r'(\d+(?:\.\d+)?)\s*hours?\s*(?:saved|reduced|freed)\s*(?:per|/|each)\s*week', est, re.I)
        if match:
            hours = float(match.group(1))
            value = hours * 52 * DEFAULT_HOURLY_RATE
            return value, f"{hours}h/week × 52 weeks × ${DEFAULT_HOURLY_RATE}/hr", f"Assumed {hours} hours/week saved at ${DEFAULT_HOURLY_RATE}/hr"

        # Pattern 5: Plain dollar amounts "$X" or "$X,XXX"
        match = re.search(r'\$\s*([\d,]+(?:\.\d+)?)', est, re.I)
        if match:
            value = float(match.group(1).replace(',', ''))
            if value > 10000:  # Likely annual
                return value, "Direct dollar estimate", None
            else:  # Likely monthly
                return value * 12, "Assumed monthly, annualized", None

        # Non-convertible
        return None, None, None

    def _non_calculable(self, reason: str) -> dict:
        return {
            "annual_cost": 0,
            "annual_value": None,
            "roi_percent": None,
            "payback_months": None,
            "monetized_drivers": [],
            "qualitative_benefits": [],
            "assumptions": [reason],
        }
