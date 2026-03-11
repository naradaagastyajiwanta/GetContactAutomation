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

# Backends for the ddgs metasearch library
# Include 'duckduckgo' because site: queries work better there,
# even though the engine fails sometimes through the proxy.
_DDG_BACKENDS = "auto"

# Minimum seconds between DDG queries to avoid rate-limiting
_MIN_QUERY_GAP = 2.5
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

    try:
        with DDGS(proxy=_DDG_PROXY, timeout=10) as ddgs:
            raw = list(ddgs.text(query, region=region, max_results=max_results, backend=_DDG_BACKENDS))
        if not raw:
            raise Exception("No results found.")

        _ddg_status["ok"] = True
        _ddg_status["error"] = None

        results = []
        for item in raw:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("href", ""),
                "snippet": item.get("body", ""),
            })

        log.debug("[DDG] '%s' → %d results", query[:80], len(results))
        return results

    except Exception as e:
        err_str = str(e).lower()
        if "ratelimit" in err_str or "429" in err_str:
            _ddg_status["ok"] = False
            _ddg_status["error"] = "rate_limited"
            log.warning("[DDG] Rate limited on query '%s': %s", query[:60], e)
            # Back off and retry once
            _time.sleep(10)
            try:
                from ddgs import DDGS as _DDGS2
                with _DDGS2(proxy=_DDG_PROXY, timeout=10) as ddgs:
                    raw = list(ddgs.text(query, region=region, max_results=max_results, backend=_DDG_BACKENDS))
                _ddg_status["ok"] = True
                _ddg_status["error"] = None
                _last_query_time = _time.monotonic()
                return [
                    {"title": r.get("title", ""), "link": r.get("href", ""), "snippet": r.get("body", "")}
                    for r in raw
                ]
            except Exception as e2:
                log.warning("[DDG] Retry also failed: %s", e2)
                return []
        elif "timeout" in err_str or "timed out" in err_str:
            _ddg_status["error"] = "timeout"
            log.warning("[DDG] Timeout for '%s', retrying after 5s...", query[:60])
            _time.sleep(5)
            try:
                with DDGS(proxy=_DDG_PROXY, timeout=10) as ddgs2:
                    raw = list(ddgs2.text(query, region=region, max_results=max_results, backend=_DDG_BACKENDS))
                _ddg_status["ok"] = True
                _ddg_status["error"] = None
                _last_query_time = _time.monotonic()
                return [
                    {"title": r.get("title", ""), "link": r.get("href", ""), "snippet": r.get("body", "")}
                    for r in raw
                ]
            except Exception as e2:
                log.warning("[DDG] Timeout retry also failed: %s", e2)
                return []
        else:
            _ddg_status["ok"] = False
            _ddg_status["error"] = str(e)[:200]
            log.warning("[DDG] Search failed for '%s': %s", query[:60], e)
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
