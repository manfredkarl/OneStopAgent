"""Web search service for finding industry benchmarks and metrics."""
import atexit
import re
import httpx
import logging
from typing import Any
from urllib.parse import unquote

logger = logging.getLogger(__name__)

AUTHORITATIVE_DOMAINS = {
    "microsoft.com", "gartner.com", "mckinsey.com", "forrester.com",
    "idc.com", "deloitte.com", "accenture.com", "pwc.com", "bcg.com",
}

# Pre-compiled regex patterns (avoids recompilation on every search_web() call)
_LINK_RE = re.compile(
    r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.+?)</a>'
)
_SNIPPET_RE = re.compile(r'<a class="result__snippet"[^>]*>(.+?)</a>')
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_UDDG_RE = re.compile(r'uddg=([^&]+)')

# Module-level httpx client with connection pooling (avoids new TCP/TLS per call).
# atexit cleanup is best-effort; httpx also releases connections on GC.
_http_client = httpx.Client(
    timeout=10,
    follow_redirects=True,
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
)
atexit.register(_http_client.close)


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
        url = "https://html.duckduckgo.com/html/"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; OneStopAgent/1.0)"}
        resp = _http_client.post(url, data={"q": query}, headers=headers)
        if resp.status_code != 200:
            return []

        results = []
        links = _LINK_RE.findall(resp.text)
        snippets = _SNIPPET_RE.findall(resp.text)

        for i, (url_raw, title_raw) in enumerate(links[:num_results]):
            title = _HTML_TAG_RE.sub('', title_raw).strip()
            snippet = _HTML_TAG_RE.sub('', snippets[i]).strip() if i < len(snippets) else ""
            # Decode DuckDuckGo redirect URL
            url_match = _UDDG_RE.search(url_raw)
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
    for q in queries:
        results = search_web(q, num_results=3)
        all_results.extend(results)

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
