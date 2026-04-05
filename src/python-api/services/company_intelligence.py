"""Company Intelligence Service — auto-enrichment from customer name.

Provides:
- Web search + LLM extraction of structured company profiles
- Fallback size profiles (Small / Mid-Market / Enterprise)
- Helper functions for IT spend estimation, labor rate, employee scoping
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe in-memory cache for company search results (TTL: 1 hour)
# ---------------------------------------------------------------------------
_COMPANY_CACHE_TTL = 3600  # seconds
_company_cache: dict[str, tuple[float, list[dict]]] = {}  # key -> (expires_at, results)
_company_cache_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Constants — industry IT spend ratios (Gartner 2024 benchmarks)
# ---------------------------------------------------------------------------

IT_SPEND_RATIOS: dict[str, float] = {
    "financial services": 0.075,
    "banking": 0.080,
    "insurance": 0.065,
    "technology": 0.120,
    "software": 0.150,
    "healthcare": 0.045,
    "manufacturing": 0.035,
    "retail": 0.025,
    "energy": 0.020,
    "telecommunications": 0.055,
    "government": 0.040,
    "education": 0.035,
    "default": 0.040,
}

# ---------------------------------------------------------------------------
# Labor rate by region + industry ($/hr, fully loaded)
# ---------------------------------------------------------------------------

LABOR_RATE_BY_REGION: dict[str, dict[str, float]] = {
    "united states": {"technology": 95, "manufacturing": 75, "healthcare": 85,
                      "financial services": 90, "retail": 65, "default": 80},
    "germany": {"technology": 85, "manufacturing": 70, "healthcare": 75,
                "financial services": 80, "retail": 60, "default": 75},
    "united kingdom": {"technology": 90, "manufacturing": 70, "healthcare": 80,
                       "financial services": 85, "retail": 62, "default": 78},
    "france": {"technology": 82, "manufacturing": 68, "healthcare": 72,
               "financial services": 78, "retail": 58, "default": 72},
    "switzerland": {"technology": 100, "manufacturing": 85, "healthcare": 90,
                    "financial services": 95, "retail": 70, "default": 88},
    "netherlands": {"technology": 88, "manufacturing": 72, "healthcare": 78,
                    "financial services": 82, "retail": 62, "default": 76},
    "india": {"technology": 35, "manufacturing": 25, "healthcare": 30,
              "financial services": 30, "retail": 20, "default": 30},
    "china": {"technology": 45, "manufacturing": 30, "healthcare": 35,
              "financial services": 40, "retail": 25, "default": 35},
    "japan": {"technology": 75, "manufacturing": 65, "healthcare": 70,
              "financial services": 75, "retail": 55, "default": 68},
    "default": {"default": 75},
}

# ---------------------------------------------------------------------------
# Use-case scope ratios — what % of total employees are affected
# ---------------------------------------------------------------------------

USE_CASE_SCOPE_RATIOS: dict[str, float] = {
    "r&d": 0.05,
    "engineering": 0.10,
    "manufacturing": 0.15,
    "factory": 0.15,
    "all employees": 1.0,
    "company-wide": 1.0,
    "it": 0.03,
    "sales": 0.08,
    "customer service": 0.05,
    "contact center": 0.05,
    "supply chain": 0.07,
    "finance": 0.04,
    "hr": 0.03,
    "marketing": 0.05,
    "default": 0.10,
}

# ---------------------------------------------------------------------------
# Fallback size profiles for unknown companies
# ---------------------------------------------------------------------------

FALLBACK_PROFILES: dict[str, dict[str, Any]] = {
    "small": {
        "employeeCount": 200,
        "annualRevenue": 25_000_000,
        "itSpendRatio": 0.05,
        "itSpendEstimate": 1_250_000,
        "hourlyLaborRate": 65,
        "confidence": "low",
        "sources": ["Company size estimate (small business profile)"],
    },
    "mid-market": {
        "employeeCount": 2_500,
        "annualRevenue": 250_000_000,
        "itSpendRatio": 0.04,
        "itSpendEstimate": 10_000_000,
        "hourlyLaborRate": 80,
        "confidence": "low",
        "sources": ["Company size estimate (mid-market profile)"],
    },
    "enterprise": {
        "employeeCount": 25_000,
        "annualRevenue": 5_000_000_000,
        "itSpendRatio": 0.035,
        "itSpendEstimate": 175_000_000,
        "hourlyLaborRate": 95,
        "confidence": "low",
        "sources": ["Company size estimate (enterprise profile)"],
    },
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_industry_ratio(industry: str) -> float:
    """Return the IT spend ratio for the given industry string."""
    industry_key = industry.lower()
    ratio = IT_SPEND_RATIOS.get(industry_key)
    if ratio is None:
        for key, val in IT_SPEND_RATIOS.items():
            if key != "default" and key in industry_key:
                ratio = val
                break
    return ratio if ratio is not None else IT_SPEND_RATIOS["default"]


def estimate_it_spend(annual_revenue: float | None, industry: str) -> float | None:
    """Derive IT spend estimate from annual revenue × industry IT spend ratio."""
    if not annual_revenue:
        return None
    return round(annual_revenue * _get_industry_ratio(industry))


def estimate_labor_rate(headquarters: str, industry: str) -> float:
    """Derive fully-loaded hourly labor rate from HQ location + industry."""
    hq_lower = headquarters.lower() if headquarters else ""
    industry_key = industry.lower() if industry else ""

    # Normalize region from HQ string
    region_rates = LABOR_RATE_BY_REGION["default"]
    for region, rates in LABOR_RATE_BY_REGION.items():
        if region != "default" and region in hq_lower:
            region_rates = rates
            break

    # Match industry within region rates
    for ind_key, rate in region_rates.items():
        if ind_key != "default" and ind_key in industry_key:
            return float(rate)
    return float(region_rates.get("default", 75))


def scope_employees(employee_count: int | None, use_case: str) -> int:
    """Estimate affected employees based on use-case keywords and total headcount."""
    total = employee_count or 1_000
    use_case_lower = use_case.lower()
    for keyword, ratio in USE_CASE_SCOPE_RATIOS.items():
        if keyword == "default":
            continue
        # Use word-boundary matching for short/ambiguous keywords to avoid false matches
        # e.g. "it" must not match "initiative", "r&d" must not match "standard"
        if len(keyword) <= 4 or "&" in keyword:
            if re.search(r'\b' + re.escape(keyword) + r'\b', use_case_lower):
                return int(total * ratio)
        elif keyword in use_case_lower:
            return int(total * ratio)
    return int(total * USE_CASE_SCOPE_RATIOS["default"])


def build_fallback_profile(size: str, customer_name: str) -> dict[str, Any]:
    """Build a complete company profile from a size tier fallback."""
    base = FALLBACK_PROFILES.get(size, FALLBACK_PROFILES["mid-market"])
    return {
        "name": customer_name,
        "industry": None,
        "headquarters": None,
        "employeeCount": base["employeeCount"],
        "annualRevenue": base["annualRevenue"],
        "revenueCurrency": "USD",
        "itSpendRatio": base["itSpendRatio"],
        "itSpendEstimate": base["itSpendEstimate"],
        "hourlyLaborRate": base["hourlyLaborRate"],
        "confidence": base["confidence"],
        "sources": base["sources"],
        "enrichedAt": datetime.now(timezone.utc).isoformat(),
        "disambiguated": False,
        "sizeTier": size,
    }


# ---------------------------------------------------------------------------
# LLM extraction + web search
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM_PROMPT = """\
Given web search results about a company, extract a structured profile.
Return ONLY a valid JSON array with 1-3 company objects (most relevant first).

Each object must have these fields (null if unknown — do NOT guess):
{
  "name": "Official company name",
  "legalName": "Full legal name if different",
  "industry": "Primary industry (e.g. Manufacturing, Financial Services, Healthcare)",
  "subIndustry": "More specific (e.g. Industrial Automation, Investment Banking)",
  "headquarters": "City, Country",
  "employeeCount": integer_or_null,
  "employeeCountSource": "e.g. LinkedIn 2025",
  "annualRevenue": float_in_USD_or_null,
  "revenueCurrency": "USD" or "EUR" or "GBP" etc,
  "fiscalYear": "e.g. FY2024",
  "revenueSource": "e.g. Annual Report 2024",
  "cloudProvider": "e.g. Azure, AWS, GCP, multi-cloud, or null",
  "knownAzureUsage": ["list of specific Azure services if known"],
  "erp": "e.g. SAP S/4HANA or null",
  "techStackNotes": "brief note or null",
  "confidence": "high" or "medium" or "low"
}

Rules:
- Only extract what is explicitly stated in the search results
- Do NOT invent revenue or employee numbers
- If the query matches multiple distinct entities (subsidiaries, divisions), include each as a separate object
- Convert revenue to a float (e.g. "€72 billion" → 72000000000.0). Use approximate USD if EUR/GBP mentioned
- confidence=high means multiple sources confirm the data; low means single or uncertain source
"""


async def search_and_extract_company(query: str) -> list[dict[str, Any]]:
    """Search for a company by name and extract structured profiles.

    Uses multiple targeted searches to gather rich data:
    - Wikipedia/overview for identity + HQ + employees
    - Financial data for revenue
    - Technology stack info

    Returns up to 3 ranked CompanyProfile dicts. Returns empty list on failure.
    Results are cached per query for 1 hour to avoid redundant searches.
    """
    # Check cache first (thread-safe)
    cache_key = query.strip().lower()
    now = time.monotonic()
    with _company_cache_lock:
        cached = _company_cache.get(cache_key)
        if cached is not None and now < cached[0]:
            return cached[1]

    from services.web_search import search_web
    from agents.llm import llm

    # Run multiple targeted searches in parallel for richer data
    search_queries = [
        f"{query} company Wikipedia employees headquarters founded",
        f"{query} annual revenue 2024 2025 employees number of",
        f"{query} cloud provider technology stack Azure AWS ERP",
    ]
    all_results: list[dict] = []
    try:
        for sq in search_queries:
            results = await asyncio.to_thread(search_web, sq, 5)
            all_results.extend(results)
    except Exception as e:
        logger.warning("Company web search failed for %r: %s", query, e)
        return []

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_results: list[dict] = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)

    if not unique_results:
        return []

    # Format search results for the LLM
    snippets = "\n\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('url', '')}\nSnippet: {r.get('snippet', '')}"
        for r in unique_results[:10]
    )

    try:
        response = await asyncio.to_thread(
            llm.invoke,
            [
                {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": f'Company query: "{query}"\n\nSearch results:\n{snippets}'},
            ],
        )
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        profiles = json.loads(text)
        if not isinstance(profiles, list):
            profiles = [profiles]
    except Exception as e:
        logger.warning("Company profile LLM extraction failed for %r: %s", query, e)
        return []

    now_iso = datetime.now(timezone.utc).isoformat()
    enriched: list[dict[str, Any]] = []
    for p in profiles[:3]:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        # Derive IT spend if not provided
        if not p.get("itSpendEstimate"):
            p["itSpendEstimate"] = estimate_it_spend(
                p.get("annualRevenue"), p.get("industry") or ""
            )
        if p.get("annualRevenue") and p.get("industry"):
            p["itSpendRatio"] = _get_industry_ratio(p["industry"] or "")

        p["enrichedAt"] = now_iso
        p["disambiguated"] = False
        p["sources"] = ["DuckDuckGo web search"]

        # Adjust confidence based on data completeness — LLM confidence
        # reflects identity certainty; downgrade if key financials are missing
        key_fields = [p.get("employeeCount"), p.get("annualRevenue"), p.get("headquarters")]
        filled = sum(1 for f in key_fields if f)
        if filled == 3 and p.get("confidence") == "high":
            pass  # keep high
        elif filled >= 2:
            p["confidence"] = "high"
        elif filled >= 1:
            p["confidence"] = max(p.get("confidence", "medium"), "medium") if p.get("confidence") != "high" else "medium"
        else:
            p["confidence"] = "low"

        enriched.append(p)

    # Populate cache (thread-safe)
    with _company_cache_lock:
        _company_cache[cache_key] = (time.monotonic() + _COMPANY_CACHE_TTL, enriched)

    return enriched
