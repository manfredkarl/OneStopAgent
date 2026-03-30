"""Shared Azure OpenAI LLM instance — Microsoft Agent Framework backend.

Drop-in replacement for the previous LangChain-based client.
Exposes the same interface (invoke / ainvoke / astream) so that all
consumer files (agents, orchestrator, approval) require zero changes.

Supports two auth modes:
1. Local dev: AZURE_OPENAI_TOKEN env var  → wrapped as a static credential
2. Production: AZURE_CLIENT_ID env var    → ManagedIdentityCredential
3. Fallback: AzureCliCredential / DefaultAzureCredential
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Sequence

from agent_framework import Message as MAFMessage
from agent_framework.azure import AzureOpenAIChatClient


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _build_credential():
    """Return an Azure credential suitable for the current environment."""
    token = os.environ.get("AZURE_OPENAI_TOKEN", "")
    if token:
        # Local dev — wrap pre-fetched token as a static credential
        from azure.core.credentials import AccessToken

        class _StaticTokenCredential:
            """Credential that returns a pre-fetched token (no refresh)."""
            def get_token(self, *_scopes: str, **_kw: Any) -> AccessToken:
                return AccessToken(token, 0)
            async def get_token_async(self, *_scopes: str, **_kw: Any) -> AccessToken:
                return AccessToken(token, 0)

        return _StaticTokenCredential()

    # Production / CI — use azure-identity
    try:
        from azure.identity import (
            AzureCliCredential,
            DefaultAzureCredential,
            ManagedIdentityCredential,
        )
        client_id = os.environ.get("AZURE_CLIENT_ID")
        if client_id:
            return ManagedIdentityCredential(client_id=client_id)
        # Try CLI first (fast for local dev), fall back to default chain
        try:
            cred = AzureCliCredential()
            cred.get_token("https://cognitiveservices.azure.com/.default")
            return cred
        except Exception:
            return DefaultAzureCredential()
    except Exception as e:
        raise RuntimeError(
            f"No AZURE_OPENAI_TOKEN set and credential resolution failed: {e}\n"
            "For local dev, run:\n"
            "  $env:AZURE_OPENAI_TOKEN = az account get-access-token "
            "--resource https://cognitiveservices.azure.com --query accessToken -o tsv"
        ) from e


# ---------------------------------------------------------------------------
# Response wrapper — preserves `.content` interface used by all consumers
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """Minimal wrapper so ``response.content`` keeps working everywhere."""
    content: str


@dataclass
class StreamChunk:
    """Minimal wrapper so ``chunk.content`` keeps working in astream loops."""
    content: str


# ---------------------------------------------------------------------------
# LLM client wrapper
# ---------------------------------------------------------------------------

_endpoint = os.environ.get(
    "AZURE_OPENAI_ENDPOINT",
    "https://demopresentations.services.ai.azure.com",
)
_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4")
_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")


def _to_maf_messages(messages: Sequence[dict[str, str]]) -> list[MAFMessage]:
    """Convert ``[{"role": ..., "content": ...}]`` dicts → MAF Message objects."""
    return [MAFMessage(role=m["role"], text=m["content"]) for m in messages]


class LLMClient:
    """Drop-in replacement exposing invoke / ainvoke / astream.

    Backed by Microsoft Agent Framework's ``AzureOpenAIChatClient``.
    """

    def __init__(self) -> None:
        self._client = AzureOpenAIChatClient(
            endpoint=_endpoint,
            deployment_name=_deployment,
            api_version=_api_version,
            credential=_build_credential(),
        )

    # -- synchronous (called from agent run() methods) ----------------------

    def invoke(self, messages: Sequence[dict[str, str]]) -> LLMResponse:
        """Synchronous LLM call — runs the async path in a thread."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an existing event loop (common in FastAPI).
            # Run in a fresh thread to avoid "cannot call run_until_complete
            # while another loop is running".
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self._ainvoke(messages))
                return future.result()
        else:
            return asyncio.run(self._ainvoke(messages))

    # -- asynchronous -------------------------------------------------------

    async def ainvoke(self, messages: Sequence[dict[str, str]]) -> LLMResponse:
        """Async LLM call — direct await."""
        return await self._ainvoke(messages)

    async def _ainvoke(self, messages: Sequence[dict[str, str]]) -> LLMResponse:
        maf_msgs = _to_maf_messages(messages)
        response = await self._client.get_response(maf_msgs)
        text = response.messages[-1].text if response.messages else str(response)
        return LLMResponse(content=text)

    # -- streaming ----------------------------------------------------------

    async def astream(
        self, messages: Sequence[dict[str, str]]
    ) -> AsyncIterator[StreamChunk]:
        """Async streaming — yields ``StreamChunk`` objects with ``.content``."""
        maf_msgs = _to_maf_messages(messages)
        stream = self._client.get_response(maf_msgs, stream=True)
        async for update in stream:
            if update.text:
                yield StreamChunk(content=update.text)


# ---------------------------------------------------------------------------
# Module-level singleton (same import pattern as before)
# ---------------------------------------------------------------------------

llm = LLMClient()
