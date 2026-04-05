"""Azure AD token provider with auto-refresh for Azure OpenAI.

Provides a thread-safe credential that:
1. Uses AZURE_OPENAI_TOKEN env var on first call (backwards compatible)
2. Tracks token expiry and proactively refreshes before it expires
3. Falls back to azure-identity (AzureCliCredential / DefaultAzureCredential)
4. Works as a drop-in Azure SDK credential (get_token / close)

Usage::

    from services.token_provider import get_credential, get_token

    # As an Azure SDK credential (pass to AzureOpenAIChatClient)
    cred = get_credential()

    # Quick access to current token string
    token_str = get_token()
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from azure.core.credentials import AccessToken

logger = logging.getLogger(__name__)

_SCOPE = "https://cognitiveservices.azure.com/.default"
_REFRESH_MARGIN_SECONDS = 10 * 60  # refresh 10 min before expiry


class AutoRefreshCredential:
    """Thread-safe credential that caches and auto-refreshes Azure AD tokens.

    On first call, if ``AZURE_OPENAI_TOKEN`` is set, uses that token with
    an assumed 60-minute lifetime.  Once it approaches expiry (or immediately
    if no env var is set), obtains fresh tokens via ``azure-identity``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached: AccessToken | None = None
        self._inner_credential: Any = None  # lazy azure-identity credential

    # -- public interface (Azure SDK credential protocol) --------------------

    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        """Return a valid cached token, refreshing if needed (sync)."""
        with self._lock:
            if self._cached and not self._is_expiring(self._cached):
                return self._cached
            return self._refresh(scopes or (_SCOPE,))

    async def get_token_async(self, *scopes: str, **kwargs: Any) -> AccessToken:
        """Async variant — delegates to the sync version (tokens are quick)."""
        return self.get_token(*scopes, **kwargs)

    def close(self) -> None:
        """Release resources held by the inner credential."""
        with self._lock:
            if self._inner_credential and hasattr(self._inner_credential, "close"):
                self._inner_credential.close()
            self._inner_credential = None
            self._cached = None

    # -- internals -----------------------------------------------------------

    def _is_expiring(self, token: AccessToken) -> bool:
        """True if *token* will expire within the refresh margin."""
        return time.time() >= (token.expires_on - _REFRESH_MARGIN_SECONDS)

    def _refresh(self, scopes: tuple[str, ...]) -> AccessToken:
        """Obtain a fresh token. Caller must hold ``self._lock``."""

        # 1) First time only — try env-var bootstrap
        if self._cached is None:
            env_token = os.environ.get("AZURE_OPENAI_TOKEN", "")
            if env_token:
                # Assume token was just issued — give it a 60 min lifetime
                self._cached = AccessToken(env_token, int(time.time()) + 3600)
                if not self._is_expiring(self._cached):
                    logger.info("Token provider: using AZURE_OPENAI_TOKEN env var")
                    return self._cached
                # Token from env var is already stale; fall through to refresh

        # 2) Use azure-identity to get a fresh token
        cred = self._get_inner_credential()
        try:
            self._cached = cred.get_token(*scopes)
            # Also update the env var so any legacy code paths stay in sync
            os.environ["AZURE_OPENAI_TOKEN"] = self._cached.token
            logger.info(
                "Token provider: refreshed token (expires in %d s)",
                int(self._cached.expires_on - time.time()),
            )
            return self._cached
        except Exception:
            # Credential refresh failed — invalidate the cached credential so
            # the next call rebuilds the chain (e.g. after CLI logout).  C7 fix.
            logger.exception("Token provider: failed to refresh token; resetting credential chain")
            self._inner_credential = None
            raise

    def _get_inner_credential(self) -> Any:
        """Lazily build the azure-identity credential chain."""
        if self._inner_credential is not None:
            return self._inner_credential

        from azure.identity import (
            AzureCliCredential,
            DefaultAzureCredential,
            ManagedIdentityCredential,
        )

        client_id = os.environ.get("AZURE_CLIENT_ID")
        if client_id:
            self._inner_credential = ManagedIdentityCredential(client_id=client_id)
            logger.info("Token provider: using ManagedIdentityCredential (client_id=%s)", client_id)
            return self._inner_credential

        try:
            cred = AzureCliCredential()
            cred.get_token(_SCOPE)
            self._inner_credential = cred
            logger.info("Token provider: using AzureCliCredential")
            return self._inner_credential
        except Exception as e:
            logger.warning("AzureCliCredential failed (%s), falling back to DefaultAzureCredential", e)
            self._inner_credential = DefaultAzureCredential()
            logger.info("Token provider: using DefaultAzureCredential")
            return self._inner_credential


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_singleton: AutoRefreshCredential | None = None
_singleton_lock = threading.Lock()


def get_credential() -> AutoRefreshCredential:
    """Return the global ``AutoRefreshCredential`` singleton."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = AutoRefreshCredential()
    return _singleton


def get_token() -> str:
    """Convenience — return the current token string (auto-refreshing if needed)."""
    return get_credential().get_token(_SCOPE).token
