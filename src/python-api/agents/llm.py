"""Shared Azure OpenAI LLM instance — Microsoft Agent Framework backend.

Drop-in replacement for the previous LangChain-based client.
Exposes the same interface (invoke / ainvoke / astream) so that all
consumer files (agents, orchestrator, approval) require zero changes.

Auth is handled by ``services.token_provider.AutoRefreshCredential`` which:
- Bootstraps from AZURE_OPENAI_TOKEN env var (backwards compatible)
- Auto-refreshes tokens via azure-identity before they expire
- Is thread-safe (shared singleton across all agents)
"""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass
from typing import AsyncIterator, Sequence

from agent_framework import Message as MAFMessage
from agent_framework.azure import AzureOpenAIChatClient

from services.token_provider import get_credential


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _build_credential():
    """Return the shared auto-refreshing Azure credential."""
    return get_credential()


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

_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4")
_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")


def _to_maf_messages(messages: Sequence[dict[str, str]]) -> list[MAFMessage]:
    """Convert ``[{"role": ..., "content": ...}]`` dicts → MAF Message objects."""
    return [MAFMessage(role=m["role"], text=m["content"]) for m in messages]


class LLMClient:
    """Drop-in replacement exposing invoke / ainvoke / astream.

    Backed by Microsoft Agent Framework's ``AzureOpenAIChatClient``.

    Uses two client instances:
    - ``_async_client`` for ainvoke / astream (runs on the main event loop)
    - ``_sync_client_factory`` creates a fresh client per invoke() call to
      avoid cross-event-loop issues when called from thread pools.
    """

    def __init__(self) -> None:
        if not _endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")
        self._async_client = AzureOpenAIChatClient(
            endpoint=_endpoint,
            deployment_name=_deployment,
            api_version=_api_version,
            credential=_build_credential(),
        )
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._loop_lock = threading.Lock()
        self._sync_client: AzureOpenAIChatClient | None = None

    def _new_client(self) -> AzureOpenAIChatClient:
        """Create a fresh client (safe for use on any event loop)."""
        return AzureOpenAIChatClient(
            endpoint=_endpoint,
            deployment_name=_deployment,
            api_version=_api_version,
            credential=_build_credential(),
        )

    def _get_sync_client(self) -> AzureOpenAIChatClient:
        """Return a cached sync client, creating one lazily if needed."""
        if self._sync_client is None:
            self._sync_client = self._new_client()
        return self._sync_client

    # -- synchronous (called from agent run() methods) ----------------------

    def invoke(self, messages: Sequence[dict[str, str]]) -> LLMResponse:
        """Synchronous LLM call.

        When called from a thread (e.g. via ``run_in_executor``), schedules
        the call on the main event loop if available.  Otherwise creates a
        fresh event loop with a dedicated client instance.
        """
        # Fast path: if we have a reference to the main loop and it's running,
        # schedule there to reuse connections.
        with self._loop_lock:
            loop = self._main_loop
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._ainvoke(messages), loop,
            )
            return future.result(timeout=300)  # 5 min for long generation (e.g. full PPTX scripts)

        # Slow path: reuse a cached sync client on a fresh event loop.
        # This avoids cross-loop issues with aiohttp/httpx connection pools.
        client = self._get_sync_client()

        async def _call() -> LLMResponse:
            maf_msgs = _to_maf_messages(messages)
            response = await client.get_response(maf_msgs)
            text = response.messages[-1].text if response.messages else str(response)
            return LLMResponse(content=text)

        return asyncio.run(_call())

    # -- asynchronous -------------------------------------------------------

    async def ainvoke(self, messages: Sequence[dict[str, str]]) -> LLMResponse:
        """Async LLM call — direct await."""
        self._capture_loop()
        return await self._ainvoke(messages)

    async def _ainvoke(self, messages: Sequence[dict[str, str]]) -> LLMResponse:
        maf_msgs = _to_maf_messages(messages)
        response = await self._async_client.get_response(maf_msgs)
        text = response.messages[-1].text if response.messages else str(response)
        return LLMResponse(content=text)

    # -- streaming ----------------------------------------------------------

    async def astream(
        self, messages: Sequence[dict[str, str]]
    ) -> AsyncIterator[StreamChunk]:
        """Async streaming — yields ``StreamChunk`` objects with ``.content``."""
        self._capture_loop()
        maf_msgs = _to_maf_messages(messages)
        stream = self._async_client.get_response(maf_msgs, stream=True)
        async for update in stream:
            if update.text:
                yield StreamChunk(content=update.text)

    # -- helpers ------------------------------------------------------------

    def _capture_loop(self) -> None:
        """Capture the running event loop for cross-thread invoke() calls."""
        with self._loop_lock:
            if self._main_loop is None:
                try:
                    self._main_loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass


# ---------------------------------------------------------------------------
# Module-level singleton (same import pattern as before)
# ---------------------------------------------------------------------------

llm = LLMClient()

# Re-export shared JSON parsing utility so callers can use:
#   from agents.llm import llm, parse_llm_json
from utils import parse_llm_json  # noqa: F401
