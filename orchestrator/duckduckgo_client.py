"""
DuckDuckGo Search client — free replacement for Serper (Google Search).

Uses the ``ddgs`` library (formerly ``duckduckgo_search``) which requires NO API key.
Provides the same search interface used by the rest of the pipeline.

Replaces:
  - Serper Google Search for IG handle discovery
  - Serper Google Search for BEM/related IG discovery
  - Serper Google Search for rector name finding
  - Serper Google Search for university website lookup
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time as _time
from typing import Any

from orchestrator.config import log

# Suppress noisy HTTP-level logging from primp/ddgs (DDG's HTTP client)
for _noisy in ("primp", "httpx", "httpcore", "ddgs", "ddgs.ddgs"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# DuckDuckGo wrapper with retry + rate-limit awareness
# ---------------------------------------------------------------------------

# SOCKS5 proxy to bypass ISP DPI blocking (e.g. Cloudflare WARP)
_DDG_PROXY: str | None = os.environ.get("DDG_PROXY")
_LOCAL_WARP_PROXY = "socks5h://127.0.0.1:1080"
_proxy_probe_checked_at: float = 0.0
_proxy_probe_result: str | None = None

# Engine rotation for ddgs v9.x (html/lite/api backends no longer exist).
# ddgs v9 is a metasearch engine: each backend is a real search engine.
# 'duckduckgo' is best for site: queries; 'google' and 'brave' as fallbacks.
# 'auto' uses all engines but includes wikipedia/grokipedia which pollute results.
_DDG_BACKEND_ROTATION = ["duckduckgo", "google", "brave", "yahoo"]

# Comma-delimited string for passing multiple backends at once
_DDG_BACKENDS = "auto"

# Minimum seconds between DDG queries to avoid rate-limiting
_MIN_QUERY_GAP = 1.5
_last_query_time: float = 0.0

# Runtime status tracking (mirrors Serper status shape)
_ddg_status: dict = {"ok": True, "error": None}


def get_status() -> dict:
    """Return DuckDuckGo health for the /health endpoint."""
    return {
        "ok": _ddg_status["ok"],
        "error": _ddg_status["error"],
        "configured": True,  # Always configured — no API key needed
    }


def _rate_limit_wait() -> None:
    """Enforce minimum gap between queries."""
    global _last_query_time
    now = _time.monotonic()
    elapsed = now - _last_query_time
    if elapsed < _MIN_QUERY_GAP:
        _time.sleep(_MIN_QUERY_GAP - elapsed)
    _last_query_time = _time.monotonic()


def _resolve_ddg_proxy() -> str | None:
    """Resolve the proxy to use for DDG queries.

    Priority:
    1. Explicit DDG_PROXY env var
    2. Host-local WARP SOCKS proxy on 127.0.0.1:1080 (for local dev)
    """
    global _proxy_probe_checked_at, _proxy_probe_result

    if _DDG_PROXY:
        return _DDG_PROXY

    now = _time.monotonic()
    if now - _proxy_probe_checked_at < 15:
        return _proxy_probe_result

    _proxy_probe_checked_at = now
    try:
        with socket.create_connection(("127.0.0.1", 1080), timeout=0.5):
            _proxy_probe_result = _LOCAL_WARP_PROXY
    except OSError:
        _proxy_probe_result = None

    return _proxy_probe_result


def search_text(
    query: str,
    max_results: int = 5,
    region: str = "id-id",
) -> list[dict]:
    """
    Perform a DuckDuckGo text search (synchronous).

    Returns list of:
        {"title": str, "link": str, "snippet": str}

    Compatible shape with Serper ``organic`` results.
    """
    global _last_query_time

    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # legacy fallback
        except ImportError:
            log.error("[DDG] ddgs not installed — run: pip install ddgs")
            _ddg_status["ok"] = False
            _ddg_status["error"] = "library_not_installed"
            return []

    _rate_limit_wait()

    last_exc: Exception | None = None
    saw_hard_failure = False

    for backend in _DDG_BACKEND_ROTATION:
        try:
            with DDGS(proxy=_resolve_ddg_proxy(), timeout=10) as ddgs:
                raw = list(ddgs.text(query, region=region, max_results=max_results, backend=backend))

            if not raw:
                # Genuine empty result — not an error, just no indexed pages.
                # Move to next backend immediately without waiting.
                log.debug("[DDG] '%s' → no results (backend=%s) — trying next backend", query[:60], backend)
                continue

            _ddg_status["ok"] = True
            _ddg_status["error"] = None
            _last_query_time = _time.monotonic()

            results = [
                {
                    "title": item.get("title", ""),
                    "link": item.get("href", ""),
                    "snippet": item.get("body", ""),
                }
                for item in raw
            ]
            log.debug("[DDG] '%s' → %d results (backend=%s)", query[:80], len(results), backend)
            return results

        except Exception as e:
            last_exc = e
            err_str = str(e).lower()

            # "no results" surfaces as an exception in some ddgs versions — same treatment:
            # genuine empty, not a transient error, skip to next backend.
            if "no results" in err_str:
                log.debug("[DDG] '%s' → no results (backend=%s) — trying next backend", query[:60], backend)
                continue

            is_connect_error = "connecterror" in err_str or (
                "connect" in err_str and "error" in err_str and "timeout" not in err_str
            )

            if is_connect_error:
                # This backend's endpoint is blocked right now — try next backend immediately
                log.debug("[DDG] ConnectError on backend=%s for '%s' — trying next backend", backend, query[:60])
                continue

            saw_hard_failure = True

            # Transient error (rate-limit, timeout) — wait then retry same backend once
            if "ratelimit" in err_str or "429" in err_str:
                wait = 15
                _ddg_status["ok"] = False
                _ddg_status["error"] = "rate_limited"
            else:
                wait = 3
                _ddg_status["error"] = err_str[:100]

            log.warning("[DDG] Query '%s' failed (backend=%s): %s — retrying in %ds", query[:60], backend, e, wait)
            _time.sleep(wait)
            # Retry the same backend once for transient errors
            try:
                with DDGS(proxy=_resolve_ddg_proxy(), timeout=10) as ddgs2:
                    raw = list(ddgs2.text(query, region=region, max_results=max_results, backend=backend))
                if raw:
                    _ddg_status["ok"] = True
                    _ddg_status["error"] = None
                    _last_query_time = _time.monotonic()
                    return [
                        {"title": r.get("title", ""), "link": r.get("href", ""), "snippet": r.get("body", "")}
                        for r in raw
                    ]
            except Exception:
                pass
            # Still failed — try next backend
            continue

    if not saw_hard_failure and last_exc and "no results" in str(last_exc).lower():
        _ddg_status["ok"] = True
        _ddg_status["error"] = None
        log.debug("[DDG] '%s' → no results across all backends", query[:60])
        return []

    if not saw_hard_failure and last_exc is None:
        _ddg_status["ok"] = True
        _ddg_status["error"] = None
        log.debug("[DDG] '%s' → no results across all backends", query[:60])
        return []

    _ddg_status["ok"] = False
    _ddg_status["error"] = str(last_exc)[:200] if last_exc else "all_backends_failed"
    log.warning("[DDG] Search failed for '%s' — all backends exhausted: %s", query[:60], last_exc)
    return []


async def async_search_text(
    query: str,
    max_results: int = 5,
    region: str = "id-id",
) -> list[dict]:
    """Async wrapper around search_text — runs in executor to avoid blocking."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, search_text, query, max_results, region,
    )
