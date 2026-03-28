"""MCP (Model Context Protocol) client for Microsoft Learn content retrieval.

This module contains ONLY the MCP API client. No business logic —
that belongs in KnowledgeAgent (ref refactor.md §3.2, FRD-02 §4).
"""
from __future__ import annotations
import httpx
import logging
from typing import Any

logger = logging.getLogger(__name__)

MCP_ENDPOINT = "https://learn.microsoft.com/api/mcp"


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
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.endpoint,
                    json={
                        "jsonrpc": "2.0",
                        "method": "search",
                        "params": {"query": query, "top": top_k},
                        "id": 1,
                    },
                    headers={"Content-Type": "application/json"},
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("result", data.get("results", []))
                    return [self._map_result(r, query) for r in results[:top_k]]
                else:
                    logger.warning(f"MCP server returned {response.status_code}: {response.text[:200]}")
                    raise MCPUnavailableError(f"MCP server returned {response.status_code}")
        
        except httpx.ConnectError as e:
            logger.warning(f"MCP server unreachable: {e}")
            raise MCPUnavailableError(f"MCP server unreachable: {e}")
        except httpx.TimeoutException as e:
            logger.warning(f"MCP server timeout: {e}")
            raise MCPUnavailableError(f"MCP server timeout: {e}")
        except MCPUnavailableError:
            raise
        except Exception as e:
            logger.warning(f"MCP client error: {e}")
            raise MCPUnavailableError(f"MCP client error: {e}")

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
