"""Web search service for finding industry benchmarks and metrics."""
import os
import re
import httpx
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import unquote

logger = logging.getLogger(__name__)

AUTHORITATIVE_DOMAINS = {
    "microsoft.com", "gartner.com", "mckinsey.com", "forrester.com",
    "idc.com", "deloitte.com", "accenture.com", "pwc.com", "bcg.com",
}


def _score_result(result: dict) -> int:
    """Score a search result by source authority and title relevance."""
    url = result.get("url", "").lower()
    score = 0
    for domain in AUTHORITATIVE_DOMAINS:
        if domain in url:
            score += 10
    if any(kw in result.get("title", "").lower() for kw in ["case study", "roi", "benchmark", "report"]):
        score += 5
    return score


def search_web(query: str, num_results: int = 5) -> list[dict[str, str]]:
    """Search DuckDuckGo for web results.

    Uses the DuckDuckGo HTML endpoint to retrieve real search results
    instead of the Instant Answer API which only returns Wikipedia
    disambiguation pages.
    """
    try:
        url = os.environ.get("WEB_SEARCH_URL", "https://html.duckduckgo.com/html/")
        headers = {"User-Agent": "Mozilla/5.0 (compatible; OneStopAgent/1.0)"}
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            resp = client.post(url, data={"q": query}, headers=headers)
            if resp.status_code != 200:
                return []

            text = resp.text[:500_000]  # Cap at 500KB to prevent regex on huge pages
            results = []
            links = re.findall(
                r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.+?)</a>',
                text,
            )
            snippets = re.findall(
                r'<a class="result__snippet"[^>]*>(.+?)</a>',
                text,
            )

            for i, (url_raw, title_raw) in enumerate(links[:num_results]):
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                # Decode DuckDuckGo redirect URL
                url_match = re.search(r'uddg=([^&]+)', url_raw)
                try:
                    clean_url = unquote(url_match.group(1)) if url_match else url_raw
                except Exception:
                    clean_url = url_raw

                results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": clean_url,
                })

            if results:
                logger.info("Web search returned %d results for: %s", len(results), query[:50])
            return results

    except Exception as e:
        logger.warning("DuckDuckGo search failed: %s", e)
        return []


def search_industry_benchmarks(industry: str, use_case: str) -> list[dict[str, str]]:
    """Search for industry-specific benchmarks and metrics."""
    queries = [
        f"{industry} {use_case} Azure ROI case study site:microsoft.com OR site:gartner.com OR site:mckinsey.com",
        f"{industry} cloud digital transformation savings benchmark 2024 2025",
        f"{industry} {use_case} total cost ownership analysis",
    ]

    all_results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(search_web, q, 3): q for q in queries}
        for future in as_completed(futures):
            try:
                results = future.result(timeout=15)
                all_results.extend(results)
            except Exception as e:
                logger.warning("Search query failed for %s: %s", futures[future][:50], e)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_results = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)

    # Sort by authority/relevance score, best first
    unique_results.sort(key=_score_result, reverse=True)
    return unique_results[:8]


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
