"""Web search service for finding industry benchmarks and metrics."""
import httpx
import logging
from typing import Any

logger = logging.getLogger(__name__)


def search_web(query: str, num_results: int = 5) -> list[dict[str, str]]:
    """Search the web for relevant content. Returns list of {title, snippet, url}.

    Uses a simple search approach. Falls back gracefully if unavailable.
    """
    try:
        # Use DuckDuckGo Instant Answer API (no API key needed)
        with httpx.Client(timeout=8) as client:
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []

                # Abstract (main answer)
                if data.get("Abstract"):
                    results.append({
                        "title": data.get("Heading", ""),
                        "snippet": data["Abstract"][:300],
                        "url": data.get("AbstractURL", ""),
                        "source": data.get("AbstractSource", ""),
                    })

                # Related topics
                for topic in data.get("RelatedTopics", [])[:num_results]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "")[:100],
                            "snippet": topic.get("Text", "")[:300],
                            "url": topic.get("FirstURL", ""),
                            "source": "DuckDuckGo",
                        })

                if results:
                    logger.info(f"Web search returned {len(results)} results for: {query[:50]}")
                    return results

    except Exception as e:
        logger.warning(f"Web search failed: {e}")

    return []


def search_industry_benchmarks(industry: str, use_case: str) -> list[dict[str, str]]:
    """Search for industry-specific benchmarks and metrics."""
    queries = [
        f"{industry} {use_case} Azure ROI case study",
        f"{industry} cloud migration cost savings benchmark",
        f"{industry} digital transformation metrics statistics",
    ]

    all_results = []
    for q in queries:
        results = search_web(q, num_results=3)
        all_results.extend(results)

    return all_results[:8]  # Cap at 8 results
