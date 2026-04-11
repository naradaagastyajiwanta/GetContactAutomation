"""Factory for OpenAI clients used by the orchestrator.

Two backends:

* **Real OpenAI API** — ``AsyncOpenAI(api_key=cfg.OPENAI_API_KEY)``.
  Used for embeddings (always) and as the fallback path when the
  Codex OAuth flow is unavailable or returns an error.

* **In-process Codex OAuth client** — see ``codex_client.py``. Used
  for chat / responses / vision when ``CHATGPT_OAUTH_ENABLED`` is
  true. Talks directly to ``chatgpt.com/backend-api/codex/responses``
  with an OAuth token from the local store. No sidecar container.

This factory is intentionally minimal — actual routing logic
(fallback, cooldown, metrics, chat↔responses translation) lives in
``gateway.py``.
"""
from __future__ import annotations

import httpx
from openai import AsyncOpenAI

from orchestrator.config import cfg, log
from orchestrator.llm.codex_client import CodexClient, get_codex_client

# --- real-API singleton ------------------------------------------------------

_real_client: AsyncOpenAI | None = None
_real_client_key: str = ""

_DEFAULT_TIMEOUT = httpx.Timeout(
    connect=10.0, read=120.0, write=10.0, pool=10.0
)


def get_real_client() -> AsyncOpenAI:
    """Return the lazy ``AsyncOpenAI`` singleton for ``api.openai.com``.

    Used for embeddings (always) and as fallback when Codex OAuth is
    disabled or unhealthy.
    """
    global _real_client, _real_client_key
    current_key = str(cfg.get("OPENAI_API_KEY", "") or "")
    if _real_client is None or current_key != _real_client_key:
        log.info("[llm-factory] (re)building real OpenAI API client")
        _real_client = AsyncOpenAI(
            api_key=current_key,
            timeout=_DEFAULT_TIMEOUT,
        )
        _real_client_key = current_key
    return _real_client


def get_codex() -> CodexClient:
    """Return the singleton in-process Codex OAuth client.

    Always returns the same instance — auth tokens are read fresh on
    every call inside the client itself.
    """
    return get_codex_client()


def reset_clients() -> None:
    """Drop cached singletons. Used by tests and on config changes."""
    global _real_client, _real_client_key
    _real_client = None
    _real_client_key = ""
