"""Web search service for finding industry benchmarks and metrics."""
import httpx
import logging
from typing import Any

logger = logging.getLogger(__name__)


def search_web(query: str, num_results: int = 5) -> list[dict[str, str]]:
    """Search the web for relevant content. Returns list of {title, snippet, url}.

    Uses a simple search approach. Falls back gracefully if unavailable.
    """
    # NOTE: DuckDuckGo Instant Answer API returns disambiguation/related topics,
    # not full search results. For production, consider Azure AI Search or Bing Search API.
    try:
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

    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)
    all_results = unique_results[:8]

    return all_results


def search_azure_architectures(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search for Azure Architecture Center reference architectures matching the use case."""
    search_queries = [
        f"site:learn.microsoft.com/azure/architecture {query}",
        f"Azure reference architecture {query}",
    ]

    all_results = []
    seen_urls: set[str] = set()
    for q in search_queries:
        results = search_web(q, num_results=max_results)
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    return all_results[:max_results]
