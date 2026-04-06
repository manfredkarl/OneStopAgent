"""MCP (Model Context Protocol) client for Microsoft Learn content retrieval.

This module contains ONLY the MCP API client. No business logic —
that belongs in KnowledgeAgent (ref refactor.md §3.2, FRD-02 §4).
"""
from __future__ import annotations
import atexit
import httpx
import logging
import os
from typing import Any

from opentelemetry import trace

_tracer = trace.get_tracer(__name__)

logger = logging.getLogger(__name__)

MCP_ENDPOINT = os.environ.get("MCP_ENDPOINT", "https://learn.microsoft.com/api/mcp")

# Module-level httpx client with connection pooling (avoids new TCP/TLS per call).
# atexit cleanup is best-effort; httpx also releases connections on GC.
_http_client = httpx.Client(
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
)
atexit.register(_http_client.close)


class MCPUnavailableError(Exception):
    """Raised when the MCP server is unreachable or returns an error."""
    pass


class MCPClient:
    """Client for querying Microsoft Learn MCP Server for Azure patterns and reference architectures."""

    def __init__(self, endpoint: str = MCP_ENDPOINT, timeout: float = 10.0):
        self.endpoint = endpoint
        self.timeout = timeout

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search Microsoft Learn for Azure patterns matching the query.
        
        Returns a list of patterns with schema:
        {
            "title": str,
            "url": str,
            "summary": str,
            "workload_type": str,  # web-app, data-platform, ai-ml, iot, microservices, migration, custom
            "industry": str,       # Retail, Healthcare, Financial Services, Manufacturing, Cross-Industry
            "compliance_tags": list[str],  # PCI-DSS, HIPAA, GDPR, SOC2
            "recommended_services": list[str],  # Azure service names
            "components": list[dict],  # [{name, azureService, description}]
            "confidence_score": float  # 0-1 how well this matches the query
        }
        
        Raises MCPUnavailableError if the server is unreachable.
        """
        if len(query) > 2000:
            query = query[:2000]
        top_k = max(1, min(top_k, 100))
        with _tracer.start_as_current_span("mcp.search") as span:
            span.set_attribute("mcp.query", query)
            span.set_attribute("mcp.top_k", top_k)
            span.set_attribute("mcp.endpoint", self.endpoint)
            try:
                response = _http_client.post(
                    self.endpoint,
                    json={
                        "jsonrpc": "2.0",
                        "method": "search",
                        "params": {"query": query, "top": top_k},
                        "id": 1,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if not isinstance(data, dict) or "result" not in data:
                        logger.warning("Malformed MCP response: %s", type(data))
                        return []
                    results = data.get("result", data.get("results", []))
                    mapped = [self._map_result(r, query) for r in results[:top_k]]
                    span.set_attribute("mcp.result_count", len(mapped))
                    return mapped
                else:
                    logger.warning("MCP server returned %d: %s", response.status_code, response.text[:200])
                    span.set_attribute("mcp.error", "HTTP %d" % response.status_code)
                    raise MCPUnavailableError("MCP server returned %d" % response.status_code)
            
            except httpx.ConnectError as e:
                logger.warning("MCP server unreachable: %s", e)
                span.set_attribute("mcp.error", "connect_error")
                raise MCPUnavailableError("MCP server unreachable: %s" % e)
            except httpx.TimeoutException as e:
                logger.warning("MCP server timeout: %s", e)
                span.set_attribute("mcp.error", "timeout")
                raise MCPUnavailableError("MCP server timeout: %s" % e)
            except MCPUnavailableError:
                raise
            except Exception as e:
                logger.warning("MCP client error: %s", e)
                span.set_attribute("mcp.error", str(e))
                raise MCPUnavailableError("MCP client error: %s" % e)

    def _map_result(self, raw: dict, query: str) -> dict[str, Any]:
        """Map a raw MCP response to the standard pattern schema (ref FRD-02 §4.3)."""
        return {
            "title": raw.get("title", raw.get("name", "Untitled")),
            "url": raw.get("url", raw.get("uri", "")),
            "summary": raw.get("summary", raw.get("description", raw.get("snippet", ""))),
            "workload_type": self._infer_workload_type(raw),
            "industry": raw.get("industry", "Cross-Industry"),
            "compliance_tags": raw.get("compliance_tags", []),
            "recommended_services": raw.get("services", raw.get("recommended_services", [])),
            "components": raw.get("components", []),
            "confidence_score": raw.get("score", raw.get("relevance", 0.5)),
        }

    def _infer_workload_type(self, raw: dict) -> str:
        """Infer workload type from raw result metadata."""
        text = f"{raw.get('title', '')} {raw.get('summary', '')} {raw.get('category', '')}".lower()
        if any(w in text for w in ["web app", "web application", "frontend", "spa"]):
            return "web-app"
        if any(w in text for w in ["data", "analytics", "warehouse", "lake"]):
            return "data-platform"
        if any(w in text for w in ["ai", "ml", "machine learning", "cognitive", "openai"]):
            return "ai-ml"
        if any(w in text for w in ["iot", "telemetry", "device", "edge"]):
            return "iot"
        if any(w in text for w in ["microservice", "kubernetes", "aks", "container"]):
            return "microservices"
        if any(w in text for w in ["migration", "modernize", "lift"]):
            return "migration"
        return "custom"


# Singleton client
mcp_client = MCPClient()
