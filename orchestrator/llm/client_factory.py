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
import threading
from openai import AsyncOpenAI

from orchestrator.config import cfg, log
from orchestrator.llm.codex_client import CodexClient, get_codex_client

# --- real-API client (thread-local) ------------------------------------------
#
# Using threading.local() instead of a module-level singleton prevents
# "Event loop is closed" errors when agent jobs run in thread-pool workers
# (each with their own event loop).  httpx binds its connection pool to the
# event loop running at first use; a thread-local client stays bound to its
# own thread's persistent loop and never sees a foreign closed loop.

_thread_local = threading.local()

_DEFAULT_TIMEOUT = httpx.Timeout(
    connect=10.0, read=120.0, write=10.0, pool=10.0
)


def get_real_client() -> AsyncOpenAI:
    """Return the ``AsyncOpenAI`` client for this thread.

    Each thread (main event loop thread + each agent pool worker) gets its
    own client instance bound to its own event loop.  Used for embeddings
    (always) and as fallback when Codex OAuth is disabled or unhealthy.
    """
    current_key = str(cfg.get("OPENAI_API_KEY", "") or "")
    client: AsyncOpenAI | None = getattr(_thread_local, "real_client", None)
    stored_key: str = getattr(_thread_local, "real_client_key", "")
    if client is None or current_key != stored_key:
        log.info("[llm-factory] (re)building OpenAI client for thread '%s'", threading.current_thread().name)
        _thread_local.real_client = AsyncOpenAI(
            api_key=current_key,
            timeout=_DEFAULT_TIMEOUT,
        )
        _thread_local.real_client_key = current_key
    return _thread_local.real_client


def get_codex() -> CodexClient:
    """Return the singleton in-process Codex OAuth client.

    Always returns the same instance — auth tokens are read fresh on
    every call inside the client itself.
    """
    return get_codex_client()


def reset_clients() -> None:
    """Drop cached client for the current thread. Used by tests and on config changes."""
    if hasattr(_thread_local, "real_client"):
        del _thread_local.real_client
    if hasattr(_thread_local, "real_client_key"):
        del _thread_local.real_client_key
