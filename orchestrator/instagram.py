"""
Instagram utilities: search handles, scrape posts, extract phone numbers via Vision API.

This module provides shared utility functions used by the pipeline agents in
orchestrator/agents/. It does not contain orchestration logic.

Scraping uses a **4-tier fallback** strategy:
  0. Playwright Stealth Browser (free, primary — most ban-resistant)
  1. Direct IG Web API (free, browser session cookies, multi-session rotation)
  2. Apify Instagram Scraper (paid API, robust)
  3. Scraping-Bot.io Social Media API (paid, last resort)

Search uses **DuckDuckGo** (free, no API key) instead of Serper (paid).
Serper is kept as optional legacy fallback if configured.

When Playwright is unavailable, direct sessions are tried.
When direct sessions fail/expire, Apify is tried automatically.
If Apify also fails, Scraping-Bot is used as the final fallback.
"""
import base64
import json
import os
import re
import time as _time
from datetime import datetime, timezone
from typing import TypedDict
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from orchestrator.config import (
    IG_MAX_POSTS_PER_PROFILE,
    CONTACT_KEYWORDS,
    IG_BIO_KEYWORDS,
    VISION_MODEL,
    PHONE_PATTERNS,
    log,
    cfg,
)
from orchestrator.db import validate_phone

# Fallback provider clients
from orchestrator import apify_client
from orchestrator import scrapingbot_client

# Free replacements
from orchestrator import duckduckgo_client
from orchestrator import playwright_ig

# ---------------------------------------------------------------------------
# Serper API health tracking (updated at runtime when quota/errors occur)
# ---------------------------------------------------------------------------
_serper_status: dict = {"ok": True, "error": None}


def _update_serper_status(ok: bool, error: str | None = None) -> None:
    """Update Serper API health state (called on error or success)."""
    _serper_status["ok"] = ok
    if not ok and error:
        _serper_status["error"] = error
    elif ok:
        _serper_status["error"] = None


def get_serper_status() -> dict:
    """Return Serper API key health for the /health endpoint."""
    return {
        "ok": _serper_status["ok"],
        "error": _serper_status["error"],
        "configured": bool(cfg.SERPER_API_KEY),
    }


class PhoneContact(TypedDict):
    phone: str
    name: str


GENERIC_CONTACT_NAMES = {
    "admin", "info", "customer service", "hotline", "cs",
    "informasi", "humas", "operator", "sekretariat", "panitia",
    "pendaftaran", "pmb", "admisi",
    # Common label words GPT mistakenly returns as names
    "narahubung", "contact person", "contact us", "cp",
    "hubungi", "kontak", "whatsapp", "call center",
    "konsultasi", "pendaftaran", "registrasi", "daftar",
    "more info", "info lebih lanjut",
}

# Words in a name that indicate it's an institution, not a person
_INSTITUTION_WORDS = {
    "universitas", "institut", "sekolah", "politeknik", "akademi",
    "stikes", "stie", "stkip", "fakultas", "prodi", "program studi",
    "kampus", "yayasan", "lembaga", "biro", "upt",
    # Organization-like words
    "peduli", "indonesia", "foundation", "organisasi", "komunitas",
    "asosiasi", "perkumpulan", "himpunan", "ikatan",
}

# Patterns that indicate the "name" is actually a label/heading, not a person
_LABEL_PATTERNS = re.compile(
    r"(?i)"
    r"(?:segera|gratis|sekarang|disini|di sini|klik|link|"
    r"hubungi kami|contact us|more info|info lengkap|"
    r"daftar sekarang|konsultasi segera|free)"
)


def _is_generic_name(name: str) -> bool:
    """Return True if the name is generic/institutional (not a person's name)."""
    lower = name.strip().lower()
    # Remove trailing punctuation for matching
    cleaned = re.sub(r"[!?.,:]+$", "", lower).strip()

    if cleaned in GENERIC_CONTACT_NAMES:
        return True
    # Check if name contains institution words
    if any(w in lower for w in _INSTITUTION_WORDS):
        return True
    # Check if name matches a label/CTA pattern
    if _LABEL_PATTERNS.search(lower):
        return True
    # Names are typically 2-4 words of 2+ chars; reject single-word ALL-CAPS labels
    # that look like headings (e.g. "KONSULTASI", "REGISTRASI")
    words = cleaned.split()
    if len(words) == 1 and len(cleaned) > 3 and cleaned.upper() == name.strip():
        return True
    return False

# ---------------------------------------------------------------------------
# IG session pool & rotation
# ---------------------------------------------------------------------------
import threading as _threading


class _IgSessionPool:
    """Manages multiple IG session cookies with automatic rotation.

    Sessions are parsed from a comma-separated string (``cfg.IG_SESSION_ID``).
    Each session tracks its own health status.  When a request fails on one
    session (suspended / login-required), the pool automatically rotates to
    the next healthy session.
    """

    def __init__(self) -> None:
        self._lock = _threading.Lock()
        self._sessions: list[dict] = []
        # Which raw config string was last parsed (detect config changes)
        self._last_raw: str = ""
        self._current_idx: int = 0

    # -- internal helpers ---------------------------------------------------

    def _parse_sessions(self, raw: str) -> list[dict]:
        """Parse comma-separated session IDs into session dicts."""
        sessions: list[dict] = []
        for part in raw.split(","):
            sid = part.strip()
            if sid:
                sessions.append({
                    "session_id": sid,
                    "ok": True,
                    "error": None,
                    "label": f"...{sid[-8:]}" if len(sid) > 8 else sid,
                })
        return sessions

    def _sync_from_config(self) -> None:
        """Re-parse sessions if the config value has changed."""
        raw = getattr(cfg, "IG_SESSION_ID", "") or ""
        if raw != self._last_raw:
            self._sessions = self._parse_sessions(raw)
            self._last_raw = raw
            self._current_idx = 0
            if self._sessions:
                log.info("IG session pool: loaded %d session(s)", len(self._sessions))
            else:
                log.warning("IG session pool: no sessions configured")

    # -- public API ---------------------------------------------------------

    def get_current_session_id(self) -> str | None:
        """Return the current healthy session ID, or None if all are down."""
        with self._lock:
            self._sync_from_config()
            if not self._sessions:
                return None

            # Try to find a healthy session starting from current index
            n = len(self._sessions)
            for i in range(n):
                idx = (self._current_idx + i) % n
                if self._sessions[idx]["ok"]:
                    self._current_idx = idx
                    return self._sessions[idx]["session_id"]

            # All sessions are down â€” return the current one anyway
            # (caller will get an error and see the warning)
            return self._sessions[self._current_idx]["session_id"]

    def mark_bad(self, session_id: str, error: str) -> None:
        """Mark a specific session as failed and rotate to next."""
        with self._lock:
            for i, s in enumerate(self._sessions):
                if s["session_id"] == session_id:
                    s["ok"] = False
                    s["error"] = error
                    log.warning(
                        "IG session %s marked as %s â€” rotating to next",
                        s["label"], error,
                    )
                    # Auto-rotate to next session
                    self._current_idx = (i + 1) % len(self._sessions)
                    break

    def mark_ok(self, session_id: str) -> None:
        """Mark a session as healthy (got a successful response)."""
        with self._lock:
            for s in self._sessions:
                if s["session_id"] == session_id:
                    s["ok"] = True
                    s["error"] = None
                    break

    def reset_all(self) -> None:
        """Reset all sessions to healthy (e.g. after config update)."""
        with self._lock:
            for s in self._sessions:
                s["ok"] = True
                s["error"] = None
            self._current_idx = 0

    def get_status(self) -> dict:
        """Return overall status + per-session details for health endpoint."""
        with self._lock:
            self._sync_from_config()
            if not self._sessions:
                return {
                    "ok": False,
                    "error": "no_sessions",
                    "total": 0,
                    "healthy": 0,
                    "sessions": [],
                }

            healthy = sum(1 for s in self._sessions if s["ok"])
            all_ok = healthy > 0

            # Find first error for backward compat
            first_error = None
            if not all_ok:
                for s in self._sessions:
                    if not s["ok"] and s["error"]:
                        first_error = s["error"]
                        break

            return {
                "ok": all_ok,
                "error": first_error,
                "total": len(self._sessions),
                "healthy": healthy,
                "sessions": [
                    {"label": s["label"], "ok": s["ok"], "error": s["error"]}
                    for s in self._sessions
                ],
            }


_ig_pool = _IgSessionPool()


def get_ig_session_status() -> dict:
    """Return current IG session pool health + fallback provider availability."""
    status = _ig_pool.get_status()
    # Add fallback provider status
    status["fallbacks"] = {
        "apify": {
            "configured": apify_client.is_configured(),
            "label": "Apify",
        },
        "scrapingbot": {
            "configured": scrapingbot_client.is_configured(),
            "label": "ScrapingBot",
        },
    }
    return status


# Thread-local storage to track which session ID is used by current client
_tl = _threading.local()


def _check_ig_response(resp: httpx.Response) -> bool:
    """Check if an IG response indicates a suspended/login-required session.
    Returns True if response is OK, False if session is broken."""
    url = str(resp.url)
    session_id = getattr(_tl, "current_session_id", None)

    if "/accounts/suspended" in url:
        if session_id:
            _ig_pool.mark_bad(session_id, "suspended")
        log.warning("IG session is SUSPENDED")
        return False
    if "/accounts/login" in url:
        if session_id:
            _ig_pool.mark_bad(session_id, "login_required")
        log.warning("IG session expired (login required)")
        return False
    if resp.status_code == 401:
        if session_id:
            _ig_pool.mark_bad(session_id, "unauthorized")
        log.warning("IG session unauthorized (401) — session expired or invalid")
        return False
    # If we get a normal 200 response, mark session as OK
    if resp.status_code == 200 and session_id:
        _ig_pool.mark_ok(session_id)
    return True


# Lazy-initialized clients
_openai_client: AsyncOpenAI | None = None
_openai_client_key: str = ""


def _get_openai() -> AsyncOpenAI:
    global _openai_client, _openai_client_key
    current_key = cfg.OPENAI_API_KEY
    if _openai_client is None or current_key != _openai_client_key:
        _openai_client = AsyncOpenAI(api_key=current_key)
        _openai_client_key = current_key
    return _openai_client


# ---------------------------------------------------------------------------
# Phase 2a: Find IG handle from university website (most accurate)
# ---------------------------------------------------------------------------

_IG_LINK_RE = re.compile(
    r'(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]{2,30})',
)
_IG_SKIP_PATHS = {"p", "reel", "reels", "stories", "explore", "accounts", "tv", "about", "developer"}


_PDDIKTI_BASE = "https://api-pddikti.kemdiktisaintek.go.id"
_PDDIKTI_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://pddikti.kemdiktisaintek.go.id",
    "Referer": "https://pddikti.kemdiktisaintek.go.id/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


async def _get_website_from_pddikti(university_name: str) -> str | None:
    """Look up the university website via PDDIKTI API."""
    name = university_name.strip().title()
    async with httpx.AsyncClient(timeout=15, headers=_PDDIKTI_HEADERS) as client:
        try:
            resp = await client.get(f"{_PDDIKTI_BASE}/pencarian/pt/{name}")
            if resp.status_code != 200:
                return None
            results = resp.json()
            if not results:
                return None

            pt_id = results[0]["id"]
            resp2 = await client.get(f"{_PDDIKTI_BASE}/pt/detail/{pt_id}")
            if resp2.status_code != 200:
                return None
            detail = resp2.json()
            website = (detail.get("website") or "").strip()
            if website:
                if not website.startswith("http"):
                    website = f"https://{website}"
                log.info("PDDIKTI: %s -> website %s", name, website)
                return website
        except Exception as e:
            log.warning("PDDIKTI lookup failed for '%s': %s", university_name, e)
    return None


async def search_ig_from_website(university_name: str, website_url: str | None = None, skip_pddikti: bool = False) -> dict | None:
    """
    Scrape a university website for instagram.com links.
    Gets the website URL from PDDIKTI first, then DuckDuckGo (free).
    Serper is kept as optional legacy fallback if configured.
    Returns: {"handle": str, "url": str, "confidence": float} or None.
    """
    # Step 1: Get website URL (PDDIKTI -> DuckDuckGo -> Serper legacy)
    if not website_url and not skip_pddikti:
        website_url = await _get_website_from_pddikti(university_name)

    # Primary search: DuckDuckGo (free, no API key needed)
    if not website_url:
        name = university_name.strip().title()
        try:
            ddg_results = await duckduckgo_client.async_search_text(
                f'"{name}" site:ac.id OR site:sch.id', max_results=5,
            )
            for r in ddg_results:
                url = r.get("link", "")
                if not (".ac.id" in url or ".edu" in url or ".sch.id" in url):
                    continue
                path = urlparse(url).path.rstrip("/")
                if path == "" or path == "/":
                    website_url = url
                    break
                else:
                    log.debug("DDG result '%s' rejected - not a homepage (path='%s')", url, path)
        except Exception as e:
            log.warning("DuckDuckGo website search failed for '%s': %s", name, e)

    # Legacy fallback: Serper (if DDG didn't find anything and key is configured)
    if not website_url and cfg.SERPER_API_KEY:
        name = university_name.strip().title()
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": cfg.SERPER_API_KEY, "Content-Type": "application/json"},
                    json={"q": f'"{name}" site:ac.id OR site:sch.id', "num": 5},
                )
                if resp.status_code != 200:
                    _update_serper_status(False, "quota_exceeded")
                else:
                    _update_serper_status(True)
                for r in resp.json().get("organic", []):
                    url = r.get("link", "")
                    if not (".ac.id" in url or ".edu" in url or ".sch.id" in url):
                        continue
                    path = urlparse(url).path.rstrip("/")
                    if path == "" or path == "/":
                        website_url = url
                        break
            except Exception:
                pass
    if not website_url:
        return None

    # Step 2: Fetch website HTML and extract IG links
    # Try original URL first, then with/without www as fallback
    urls_to_try = [website_url]
    if "://www." in website_url:
        urls_to_try.append(website_url.replace("://www.", "://"))
    elif "://" in website_url and "://www." not in website_url:
        urls_to_try.append(website_url.replace("://", "://www."))

    html = None
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for url in urls_to_try:
            try:
                resp2 = await client.get(url)
                if resp2.status_code == 200:
                    html = resp2.text
                    break
            except Exception:
                continue
    if not html:
        # No HTML but we found the website URL â€” return it without handle
        return {"handle": None, "website_url": website_url}

    handles = _IG_LINK_RE.findall(html)
    # Filter out non-profile paths
    handles = [h for h in handles if h.lower() not in _IG_SKIP_PATHS]
    # Deduplicate preserving order
    seen = set()
    unique = []
    for h in handles:
        if h.lower() not in seen:
            seen.add(h.lower())
            unique.append(h)

    if not unique:
        # Website found but no IG handle on it
        return {"handle": None, "website_url": website_url}

    # When multiple IG handles found on the website, filter out sub-entity handles
    # (clinics, hospitals, student orgs, etc.) to pick the main institutional account.
    if len(unique) > 1:
        main_handles = [
            h for h in unique
            if not any(kw in h.lower() for kw in _DEPT_HANDLE_KEYWORDS)
        ]
        if main_handles:
            log.info(
                "Website %s has %d IG links, filtered %d sub-entity handles: kept %s, removed %s",
                website_url, len(unique), len(unique) - len(main_handles),
                [f"@{h}" for h in main_handles],
                [f"@{h}" for h in unique if h not in main_handles],
            )
            unique = main_handles

    handle = unique[0]
    log.info("Website %s -> selected IG: @%s (out of %d found)", website_url, handle, len(unique))
    return {
        "handle": handle,
        "url": f"https://www.instagram.com/{handle}/",
        "confidence": 0.9,  # Very high â€” from their own website
        "website_url": website_url,
    }


# ---------------------------------------------------------------------------
# Phase 2b: Search Instagram Handle via DuckDuckGo (free) + Serper fallback
# ---------------------------------------------------------------------------

async def search_ig_handle(university_name: str) -> dict | None:
    """
    Search for university's Instagram handle via DuckDuckGo (free, primary)
    with Serper as legacy fallback if configured.
    Returns: {"handle": "@univ_name", "url": "...", "confidence": 0.0-1.0} or None
    """

    # Normalize: PDDIKTI names are ALL CAPS â†’ title case for better Google results
    name = university_name.strip().title()

    # Build search queries â€” try exact match first, then relaxed
    queries = [
        f'site:instagram.com "{name}"',
        f'site:instagram.com {name} instagram',
    ]

    # Primary: DuckDuckGo (free)
    for query in queries:
        result = await _ddg_search_ig(query, university_name)
        if result:
            return result

    # Legacy fallback: Serper (if configured)
    if cfg.SERPER_API_KEY:
        for query in queries:
            result = await _serper_search_ig(query, university_name)
            if result:
                return result

    return None



async def _ddg_search_ig(query: str, university_name: str) -> dict | None:
    """Run a single DuckDuckGo search and return first matching IG handle."""
    try:
        results = await duckduckgo_client.async_search_text(query, max_results=5)
    except Exception as e:
        log.error("DuckDuckGo search failed for '%s': %s", university_name, e)
        return None

    if not results:
        return None

    for result in results:
        url = result.get("link", "")
        title = result.get("title", "").lower()
        snippet = result.get("snippet", "").lower()

        # Extract handle from Instagram URL
        handle = _extract_ig_handle(url)
        if not handle:
            continue

        # Calculate confidence based on name match and keywords
        confidence = _calculate_confidence(
            university_name, handle, title, snippet
        )

        if confidence >= 0.65:
            return {
                "handle": handle,
                "url": url,
                "confidence": confidence,
            }

    return None


async def _serper_search_ig(query: str, university_name: str) -> dict | None:
    """Run a single Serper search and return first matching IG handle."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": cfg.SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": 5},
            )
            if resp.status_code != 200:
                body = resp.text[:300]
                _update_serper_status(False, "quota_exceeded")
                log.error(
                    "Serper quota/key error HTTP %d for '%s': %s",
                    resp.status_code, university_name, body,
                )
                return None
            data = resp.json()
            _update_serper_status(True)
        except Exception as e:
            log.error(f"Serper search failed for '{university_name}': {e}")
            return None

    organic = data.get("organic", [])
    if not organic:
        return None

    for result in organic:
        url = result.get("link", "")
        title = result.get("title", "").lower()
        snippet = result.get("snippet", "").lower()

        # Extract handle from Instagram URL
        handle = _extract_ig_handle(url)
        if not handle:
            continue

        # Calculate confidence based on name match and keywords
        confidence = _calculate_confidence(
            university_name, handle, title, snippet
        )

        if confidence >= 0.65:
            return {
                "handle": handle,
                "url": url,
                "confidence": confidence,
            }

    return None


def _extract_ig_handle(url: str) -> str | None:
    """Extract Instagram handle from URL like https://www.instagram.com/handle/"""
    try:
        parsed = urlparse(url)
        if "instagram.com" not in parsed.netloc:
            return None
        path = parsed.path.strip("/")
        # Skip non-profile URLs
        if "/" in path or path in ("p", "reel", "stories", "explore", "accounts"):
            # Could be instagram.com/p/xxx or instagram.com/handle/
            parts = path.split("/")
            if parts[0] in ("p", "reel", "stories", "explore", "accounts", "tv"):
                return None
            return parts[0] if parts[0] else None
        return path if path else None
    except Exception:
        return None


def _calculate_confidence(
    university_name: str, handle: str, title: str, snippet: str
) -> float:
    """Calculate confidence that this IG account belongs to the university."""
    score = 0.0
    uni_lower = university_name.lower()
    handle_lower = handle.lower()
    title_lower = title.lower()
    snippet_lower = snippet.lower()

    # Words that are generic institution types or location names â€” NOT unique to a specific university
    _GENERIC_WORDS = {
        # Institution types
        "universitas", "institut", "sekolah", "tinggi", "politeknik",
        "akademi", "ilmu", "kesehatan", "teknik", "teknologi",
        "bisnis", "sains", "pendidikan", "stikes", "stie", "stkip",
        # Province / location names (too common in handles)
        "bali", "jakarta", "bandung", "surabaya", "yogyakarta", "semarang",
        "malang", "medan", "makassar", "denpasar", "lombok", "solo",
        "aceh", "riau", "jambi", "lampung", "banten", "papua",
        "kalimantan", "sulawesi", "sumatera", "nusa", "indonesia",
    }

    uni_words = uni_lower.split()
    # "Unique words" = words that identify THIS university specifically
    unique_words = [
        w for w in uni_words
        if len(w) > 3 and w not in _GENERIC_WORDS
    ]

    # Build abbreviation from university name (e.g. "Institut Ilmu Kesehatan Medika Persada" â†’ "iikmp")
    # Skip common filler words
    _SKIP_ABBREV = {"dan", "dan", "di", "the", "of"}
    abbrev = "".join(
        w[0] for w in uni_words if len(w) > 1 and w not in _SKIP_ABBREV
    )

    # Strip separators from handle for matching (e.g. "std_bali" â†’ "stdbali")
    handle_stripped = re.sub(r'[_.\-]', '', handle_lower)

    # Handle matches unique words (strong signal)
    unique_in_handle = sum(1 for w in unique_words if w in handle_stripped)
    # Handle matches abbreviation (e.g. "iikmpbali" contains "iikmp", "std_bali" â†’ "stdbali" contains "stdb")
    abbrev_match = len(abbrev) >= 3 and abbrev in handle_stripped

    if unique_in_handle > 0 or abbrev_match:
        word_score = 0.35 * min(unique_in_handle / max(len(unique_words), 1), 1.0)
        abbrev_score = 0.30 if abbrev_match else 0.0
        score += max(word_score, abbrev_score)
    else:
        # Handle only matches generic words â€” weak signal
        generic_in_handle = sum(1 for w in uni_words if len(w) > 3 and w in handle_stripped)
        if generic_in_handle > 0:
            score += 0.10

    # Full name appears in title/snippet (very strong signal)
    if uni_lower in title_lower or uni_lower in snippet_lower:
        score += 0.3
    elif any(w in title_lower or w in snippet_lower for w in unique_words):
        score += 0.15

    # Bio keywords in snippet
    if any(kw in snippet_lower for kw in IG_BIO_KEYWORDS):
        score += 0.15

    # Handle doesn't look like a personal/org account
    _NON_INSTITUTION = [
        "personal", "fan", "meme", "info_", "pers", "himpunan", "bem_", "himapsi",
        # University sub-unit facilities
        "klinik", "rumahsakit", "apotek", "rsgm",
        # Student organisations
        "hima_", "dema_", "senat_", "ukm_", "ormawa",
    ]
    if any(x in handle_lower for x in _NON_INSTITUTION):
        score -= 0.15

    # Penalty: title/snippet indicates a subsidiary entity (clinic, hospital, etc.)
    if any(kw in title_lower or kw in snippet_lower for kw in _SUBSIDIARY_ENTITY_KEYWORDS):
        score -= 0.25

    # Not a personal account (basic check)
    if not any(x in handle_lower for x in ["personal", "fan", "meme"]):
        score += 0.05

    # Bonus for "official" or "resmi" in title
    if "official" in title_lower or "resmi" in title_lower:
        score += 0.15

    return max(min(score, 1.0), 0.0)


# ---------------------------------------------------------------------------
# Phase 3a: Scrape Instagram Posts (Web API with browser session)
# ---------------------------------------------------------------------------

_IG_WEB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
}


def _get_ig_web_client() -> httpx.Client:
    """Create an httpx Client with Instagram browser session cookies.

    Uses the session pool to pick the current healthy session.
    Stores the active session ID in thread-local so ``_check_ig_response``
    can mark the correct session when errors occur.
    """
    session_id = _ig_pool.get_current_session_id()
    if not session_id:
        raise RuntimeError(
            "No IG session IDs configured. "
            "Set IG_SESSION_ID in Settings (comma-separated for multiple sessions). "
            "Get sessionid from browser: F12 â†’ Application â†’ Cookies â†’ instagram.com â†’ sessionid"
        )
    # Store in thread-local for _check_ig_response to reference
    _tl.current_session_id = session_id
    cookies = {"sessionid": session_id}
    return httpx.Client(
        cookies=cookies,
        headers=_IG_WEB_HEADERS,
        timeout=20,
        follow_redirects=True,
    )


# Keywords that indicate event flyers / posts likely to contain phone numbers
_FLYER_KEYWORDS = [
    "pendaftaran", "registrasi", "daftar", "pmb", "penerimaan",
    "seminar", "workshop", "webinar", "lomba", "kompetisi",
    "info lengkap", "informasi", "narahubung", "contact person",
    "hubungi", "sekretariat",
]

# Simple regex for quick phone-number detection in captions
_PHONE_QUICK_RE = re.compile(r'(?:\+62|62|0)[\s\-.]?8\d[\s\-.]?\d{3,4}[\s\-.]?\d{3,5}')

# WhatsApp link patterns (wa.me/62xxx, api.whatsapp.com/send?phone=62xxx)
_WA_LINK_RE = re.compile(r'(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\+?62\d{8,13})')

# How many "has_phone" results before we stop scanning more posts
_ENOUGH_PHONE_RESULTS = 10

# Sub-department handle prefixes â€” these are NOT the main university account
_DEPT_HANDLE_KEYWORDS = [
    # Administrative / departmental sub-units
    "kemahasiswaan", "humas", "pmb", "biro", "upt", "lppm",
    "perpustakaan", "lpm", "bak", "baak", "alumni",
    # Student organisations
    "bem", "hmj", "ormawa", "ukm", "hima", "dema", "senat",
    # University-affiliated facilities (NOT the main institution)
    "klinik", "rumahsakit", "apotek", "laboratorium",
    "asrama", "kantin", "kopma", "koperasi", "masjid",
    "rsgm",  # Rumah Sakit Gigi & Mulut
]

# Words in an IG full_name / bio that indicate a sub-entity (not the main university)
_SUBSIDIARY_ENTITY_KEYWORDS = [
    "klinik", "rumah sakit", "rs ", "rsgm", "apotek", "farmasi",
    "laboratorium", "lab ", "perpustakaan", "asrama", "kantin",
    "koperasi", "kopma", "masjid", "mushola", "poliklinik",
    "rawat inap", "rawat jalan", "24 jam",
]


def _ig_web_get_user_info(client: httpx.Client, handle: str) -> dict | None:
    """
    Get user_id, bio, and external_url for an IG handle.

    Uses two requests:
      1. Search API â†’ user_id (+ basic info)
      2. Profile API â†’ bio, external_url, bio_links (search doesn't return these)

    Returns {"user_id": int, "bio": str, "external_url": str} or None.
    """
    # Step 1: Search to get user_id
    resp = client.get(
        "https://www.instagram.com/web/search/topsearch/",
        params={"query": handle, "context": "user"},
    )
    if not _check_ig_response(resp):
        return None
    if resp.status_code != 200:
        log.warning("IG web search failed for @%s: HTTP %d", handle, resp.status_code)
        return None

    try:
        users = resp.json().get("users", [])
    except (ValueError, KeyError):
        body_preview = resp.text[:200] if resp.text else "(empty)"
        log.warning("IG web search returned invalid JSON for @%s: %s", handle, body_preview)
        return None
    # Prefer exact username match
    user_data = None
    for u in users:
        if u["user"]["username"].lower() == handle.lower():
            user_data = u["user"]
            break
    if not user_data and users:
        user_data = users[0]["user"]
    if not user_data:
        return None

    user_id = int(user_data["pk"])

    # Step 2: Fetch full profile for bio + external_url
    # (search API doesn't return these fields)
    _time.sleep(1)  # Small delay to avoid rate limiting
    bio = ""
    external_url = ""
    profile = _ig_web_fetch_profile(client, handle)
    if profile:
        bio = profile.get("bio", "")
        external_url = profile.get("external_url", "")

    return {
        "user_id": user_id,
        "bio": bio,
        "external_url": external_url,
    }


_BIO_LINK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "DNT": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


def _scan_bio_link(url: str) -> list[str]:
    """
    Follow a link-in-bio URL and extract WhatsApp numbers.
    Handles Linktree (__NEXT_DATA__ JSON), beacons, direct wa.me links, etc.
    Returns list of phone numbers found.
    """
    if not url:
        return []

    phones: list[str] = []
    try:
        with httpx.Client(
            timeout=10, follow_redirects=True, headers=_BIO_LINK_HEADERS,
        ) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            text = resp.text

            # Linktree: parse __NEXT_DATA__ JSON for link URLs
            if "linktr.ee" in url or "__NEXT_DATA__" in text:
                import json as _json
                m = re.search(
                    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text,
                )
                if m:
                    try:
                        data = _json.loads(m.group(1))
                        links = (
                            data.get("props", {})
                            .get("pageProps", {})
                            .get("links", [])
                        )
                        for link in links:
                            link_url = link.get("url", "")
                            if not link_url:
                                continue
                            # Direct wa.me link
                            wa_match = _WA_LINK_RE.search(link_url)
                            if wa_match:
                                phones.append(wa_match.group(1))
                            # Phone in URL
                            for ph in _PHONE_QUICK_RE.findall(link_url):
                                phones.append(ph)
                    except Exception:
                        pass

            # Also scan raw HTML for wa.me / WhatsApp API links
            for match in _WA_LINK_RE.findall(text):
                phones.append(match)

            # Also scan page text for phone numbers
            for match in _PHONE_QUICK_RE.findall(text):
                phones.append(match)

    except Exception as e:
        log.debug("Failed to scan bio link %s: %s", url, e)

    return list(set(phones))


def _ig_web_get_posts(client: httpx.Client, user_id: int, max_posts: int, max_id: str | None = None) -> tuple[list[dict], str | None]:
    """Fetch posts via Instagram Web API feed endpoint with pagination.

    Args:
        max_id: Pagination cursor â€” pass the ``next_max_id`` from a previous
                call to fetch *older* posts.

    Returns:
        (posts, next_max_id) â€” ``next_max_id`` is ``None`` when there are no
        more pages.
    """
    params: dict = {"count": max_posts}
    if max_id:
        params["max_id"] = max_id

    resp = client.get(
        f"https://www.instagram.com/api/v1/feed/user/{user_id}/",
        params=params,
    )
    if not _check_ig_response(resp):
        return [], None
    if resp.status_code != 200:
        log.warning("IG web feed failed for user %d: HTTP %d", user_id, resp.status_code)
        return [], None

    try:
        body = resp.json()
        items = body.get("items", [])
        next_max_id = body.get("next_max_id")
    except (ValueError, KeyError):
        body_preview = resp.text[:200] if resp.text else "(empty)"
        log.warning("IG web feed returned invalid JSON for user %d: %s", user_id, body_preview)
        return [], None

    posts = []
    for item in items:
        code = item.get("code", "")
        caption_obj = item.get("caption") or {}
        caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else ""

        # Get best image URL
        img_candidates = item.get("image_versions2", {}).get("candidates", [])
        image_url = img_candidates[0].get("url", "") if img_candidates else ""

        # Timestamp
        taken_at = item.get("taken_at")
        timestamp = (
            datetime.fromtimestamp(taken_at, tz=timezone.utc).isoformat()
            if taken_at else None
        )

        if code:
            posts.append({
                "post_url": f"https://www.instagram.com/p/{code}/",
                "image_url": image_url,
                "caption": caption,
                "timestamp": timestamp,
            })

    return posts, next_max_id


def _classify_post(post: dict) -> str:
    """
    Classify a post by likelihood of containing a phone number.
    Returns: "has_phone" | "likely_flyer" | "skip"
    """
    caption = (post.get("caption") or "").lower()
    cleaned = caption.replace(" ", "").replace("-", "")

    # Tier A: caption literally contains a phone number
    if _PHONE_QUICK_RE.search(cleaned):
        return "has_phone"

    # Tier B: caption has flyer/event keywords â†’ image might contain phone
    if any(kw in caption for kw in _FLYER_KEYWORDS):
        return "likely_flyer"

    return "skip"


def scrape_ig_posts_sync(
    ig_handle: str,
    max_posts: int | None = None,
    deeper: bool = False,
    known_post_urls: set[str] | None = None,
) -> list[dict]:
    """
    Smart scrape: find posts most likely to contain phone numbers.

    Args:
        deeper: If True, paginate through older posts until we find new
                content (posts not in *known_post_urls*) or run out of pages.
                Used for re-scraping universities that need more contacts.
        known_post_urls: Set of post URLs already in the database. When
                *deeper* is True this is used to skip pages of already-seen
                posts and continue to older ones.

    Strategy:
      1. Check bio text for phone numbers
      2. Check link-in-bio (Linktree, wa.me, etc.) for WhatsApp links
      3. Fetch posts and classify:
         - "has_phone"   â†’ phone regex found in caption
         - "likely_flyer" â†’ event/flyer keywords (image may have phone)
         - "skip"        â†’ not relevant
      4. Early stop once we have enough "has_phone" results
      5. Return bio + has_phone + likely_flyer for downstream extraction

    This is a SYNC function â€” call from executor in async context.
    Returns list of {"post_url", "image_url", "caption", "timestamp", "source"}.
    """
    if max_posts is None:
        max_posts = IG_MAX_POSTS_PER_PROFILE
    if known_post_urls is None:
        known_post_urls = set()

    handle = ig_handle.lstrip("@")
    results: list[dict] = []
    total_scanned = 0
    phone_count = 0
    flyer_count = 0

    # How many extra pages to fetch when going deeper
    MAX_DEEPER_PAGES = 3

    client = _get_ig_web_client()
    try:
        # Step 1: Get user info (single request â†’ user_id + bio + external_url)
        info = _ig_web_get_user_info(client, handle)
        if not info:
            log.warning("@%s: user not found via IG web search", handle)
            return []

        user_id = info["user_id"]
        bio = info["bio"]
        external_url = info["external_url"]

        # Step 2: Check bio text for phone numbers
        if bio and _PHONE_QUICK_RE.search(bio.replace(" ", "").replace("-", "")):
            results.append({
                "post_url": f"https://www.instagram.com/{handle}/",
                "image_url": "",
                "caption": f"[BIO] {bio}",
                "timestamp": None,
                "source": "bio",
            })
            log.info("@%s: phone number found in bio text!", handle)

        # Step 3: Check link-in-bio (Linktree, wa.me, etc.)
        if external_url:
            bio_link_phones = _scan_bio_link(external_url)
            if bio_link_phones:
                phone_list = ", ".join(bio_link_phones)
                results.append({
                    "post_url": external_url,
                    "image_url": "",
                    "caption": f"[LINK IN BIO] {phone_list}",
                    "timestamp": None,
                    "source": "bio_link",
                })
                log.info("@%s: phone found in link-in-bio (%s): %s", handle, external_url, phone_list)

        _time.sleep(1)

        # Step 4: Fetch posts and classify (with pagination & early stop)
        next_max_id: str | None = None
        pages_fetched = 0
        max_pages = 1 + (MAX_DEEPER_PAGES if deeper else 0)

        while pages_fetched < max_pages:
            posts, next_max_id = _ig_web_get_posts(client, user_id, max_posts, max_id=next_max_id)
            if not posts:
                break
            pages_fetched += 1
            total_scanned += len(posts)

            new_posts_on_page = 0
            for post in posts:
                # Skip posts we already have in DB
                if post["post_url"] in known_post_urls:
                    continue
                new_posts_on_page += 1

                # Save ALL posts -- Agent 3 (phone extraction) uses GPT-4o vision OCR
                # on images, so phone numbers can appear regardless of caption text.
                results.append(post)

            # In deeper mode: if the first page was all known posts, continue
            # to the next page to find older unseen content.
            # If not in deeper mode or no more pages, stop.
            if not deeper or not next_max_id:
                break

            # All posts on this page were new â€” no need to go deeper, first
            # scrape already covers this range.
            if new_posts_on_page == len(posts):
                break

            log.info("@%s: deeper scrape â€” fetching page %d", handle, pages_fetched + 1)
            _time.sleep(2)  # Rate limit between pages

    finally:
        client.close()

    bio_found = any(r.get("source") in ("bio", "bio_link") for r in results)
    log.info(
        "@%s: %d posts scanned (%d pages) → %d saved",
        handle, total_scanned, pages_fetched, len(results),
    )
    return results


# Common Indonesian university abbreviations for shorter IG search queries
_ABBREVIATIONS = {
    "universitas islam negeri": "UIN",
    "universitas islam": "UNISMA",
    "universitas negeri": "UN",
    "universitas": "Univ",
    "institut agama islam negeri": "IAIN",
    "institut agama islam": "IAI",
    "institut teknologi": "IT",
    "institut": "Institut",
    "politeknik negeri": "Poltek",
    "politeknik": "Poltek",
    "sekolah tinggi ilmu ekonomi": "STIE",
    "sekolah tinggi ilmu kesehatan": "STIKES",
    "sekolah tinggi teknologi": "STT",
    "sekolah tinggi teologi": "STT",
    "sekolah tinggi": "ST",
    "akademi": "Akad",
}


def _build_search_queries(university_name: str) -> list[str]:
    """Build multiple search query variants: full name + abbreviated."""
    name = university_name.strip().title()
    queries = [name]

    lower = university_name.lower().strip()
    for prefix, abbr in _ABBREVIATIONS.items():
        if lower.startswith(prefix):
            remainder = lower[len(prefix):].strip()
            words = remainder.split()
            if words:
                # Try abbreviation + last 1 word (location)
                short1 = f"{abbr} {words[-1].title()}"
                if short1 != name:
                    queries.append(short1)
                # Also try abbreviation + last 2 words if available
                if len(words) >= 2:
                    short2 = f"{abbr} {' '.join(words[-2:]).title()}"
                    if short2 != name and short2 != short1:
                        queries.append(short2)
            break

    return queries


def _score_ig_user(user_data: dict, university_name: str) -> float:
    """Score an IG search result against a university name."""
    username = user_data.get("username", "")
    handle_lower = username.lower()
    full_name = (user_data.get("full_name", "") or "").lower()
    is_verified = user_data.get("is_verified", False)

    uni_lower = university_name.lower()
    uni_words = [w for w in uni_lower.split() if len(w) > 3]

    # Location word = last word (city/region name) â€” most distinguishing
    all_words = university_name.lower().split()
    location_word = all_words[-1] if all_words else ""

    # Common/generic words that many universities share
    generic = {"universitas", "institut", "sekolah", "tinggi", "negeri", "islam",
               "agama", "politeknik", "akademi", "ilmu", "teknologi", "stie", "stkip"}

    score = 0.0

    # Location match is critical â€” worth the most
    if location_word and len(location_word) > 3:
        if location_word in full_name:
            score += 0.35
        elif location_word in handle_lower:
            score += 0.25

    # Non-generic word matches
    unique_words = [w for w in uni_words if w not in generic and w != location_word]
    unique_matching = 0
    if unique_words:
        unique_matching = sum(1 for w in unique_words if w in full_name or w in handle_lower)
        score += 0.2 * min(unique_matching / len(unique_words), 1.0)

    # Penalty: if university has distinctive words but NONE match, cap score low
    # e.g. "Nahdlatul Ulama" should not match random "@idbbali" just because "bali" matches
    if unique_words and unique_matching == 0:
        score = min(score, 0.4)

    # Generic institution type match (small bonus)
    generic_words = [w for w in uni_words if w in generic]
    if generic_words:
        matching = sum(1 for w in generic_words if w in full_name)
        score += 0.1 * min(matching / len(generic_words), 1.0)

    # Verified bonus
    if is_verified:
        score += 0.2

    # Bio keywords in full_name
    if any(kw in full_name for kw in IG_BIO_KEYWORDS):
        score += 0.1

    # Penalty: sub-department handles (kemahasiswaan, humas, pmb, etc.)
    if any(d in handle_lower for d in _DEPT_HANDLE_KEYWORDS):
        score -= 0.2

    # Heavy penalty: full_name indicates a subsidiary entity (clinic, hospital, etc.)
    # e.g. "Klinik Pratama UNIMUS" is NOT the university's main account
    if any(kw in full_name for kw in _SUBSIDIARY_ENTITY_KEYWORDS):
        score -= 0.35
        log.debug(
            "Subsidiary penalty for @%s: full_name='%s' matched subsidiary keywords",
            username, full_name[:60],
        )

    return max(min(score, 1.0), 0.0)


def search_ig_handle_via_ig(university_name: str) -> dict | None:
    """
    Search for university's Instagram handle directly via IG Web Search API.
    Tries multiple query variants (full name + abbreviated).
    Returns: {"handle": str, "url": str, "confidence": float} or None.
    Sync function â€” call from executor in async context.
    """
    if not _ig_pool.get_current_session_id():
        return None

    queries = _build_search_queries(university_name)

    best = None
    best_score = 0.0

    client = _get_ig_web_client()
    try:
        for query in queries:
            resp = client.get(
                "https://www.instagram.com/web/search/topsearch/",
                params={"query": query, "context": "user"},
            )
            if not _check_ig_response(resp):
                break  # Session broken, stop all queries
            if resp.status_code != 200:
                continue

            try:
                users = resp.json().get("users", [])[:10]
            except (ValueError, KeyError):
                continue

            for u in users:
                uu = u["user"]
                score = _score_ig_user(uu, university_name)
                if score > best_score:
                    best_score = score
                    best = {
                        "handle": uu["username"],
                        "url": f"https://www.instagram.com/{uu['username']}/",
                        "confidence": score,
                    }

            # If we already found a strong match, don't burn more searches
            if best_score >= 0.6:
                break
            _time.sleep(1)

        if best and best["confidence"] >= 0.65:
            return best
    finally:
        client.close()

    return None


def _ig_web_fetch_profile(client: httpx.Client, handle: str) -> dict | None:
    """
    Fetch full IG profile directly (not via search).
    Returns {"bio": str, "full_name": str, "external_url": str, "is_verified": bool} or None.
    """
    resp = client.get(
        "https://www.instagram.com/api/v1/users/web_profile_info/",
        params={"username": handle},
    )
    if not _check_ig_response(resp):
        return None
    if resp.status_code != 200:
        log.debug("IG profile fetch failed for @%s: HTTP %d", handle, resp.status_code)
        return None

    try:
        user = resp.json().get("data", {}).get("user", {})
        if not user:
            return None
        return {
            "bio": user.get("biography", "") or "",
            "full_name": user.get("full_name", "") or "",
            "external_url": user.get("external_url", "") or "",
            "is_verified": user.get("is_verified", False),
        }
    except Exception:
        return None


def verify_ig_handle(handle: str, university_name: str) -> dict:
    """
    Verify an IG handle by fetching the profile and checking bio content.
    Returns: {"verified": bool, "confidence_boost": float, "bio": str, "reason": str}
    Sync function â€” call from executor in async context.
    """
    if not _ig_pool.get_current_session_id():
        return {"verified": False, "confidence_boost": 0, "bio": "", "reason": "no session"}

    client = _get_ig_web_client()
    try:
        profile = _ig_web_fetch_profile(client, handle)
    finally:
        client.close()

    if not profile:
        # Profile fetch failed (likely rate limited) â€” don't penalize,
        # let the search-phase confidence stand as-is.
        return {"verified": True, "confidence_boost": 0, "bio": "", "reason": "profile fetch failed (skipped)"}

    bio = profile["bio"].lower()
    external_url = profile["external_url"].lower()
    uni_lower = university_name.lower()
    all_words = uni_lower.split()

    # Location word (last word, e.g. "malang", "bali")
    location_word = all_words[-1] if all_words else ""

    # Generic words to exclude
    generic = {
        "universitas", "institut", "sekolah", "tinggi", "negeri", "islam",
        "agama", "politeknik", "akademi", "ilmu", "teknologi", "stie", "stkip",
        "dan", "yang", "dari",
    }

    # Unique distinguishing words (len > 3, not generic, not location)
    unique_words = [w for w in all_words if len(w) > 3 and w not in generic and w != location_word]

    boost = 0.0
    reasons = []

    # Penalty: sub-department handles (kemahasiswaan, humas, pmb, etc.)
    handle_lower = handle.lower()
    dept_match = [d for d in _DEPT_HANDLE_KEYWORDS if d in handle_lower]
    if dept_match:
        boost -= 0.25
        reasons.append(f"sub-department handle ({', '.join(dept_match)})")

    # Penalty: bio is empty â†’ can't verify, inconclusive
    if not bio.strip():
        boost -= 0.15
        reasons.append("empty bio")
    else:
        # Check 1: University name / unique words in bio
        unique_in_bio = sum(1 for w in unique_words if w in bio)
        if unique_in_bio > 0:
            boost += 0.15 * min(unique_in_bio / max(len(unique_words), 1), 1.0)
            reasons.append(f"{unique_in_bio} unique words in bio")

        # Check 2: Location word in bio
        if location_word and len(location_word) > 3 and location_word in bio:
            boost += 0.1
            reasons.append(f"location '{location_word}' in bio")

        # Check 3: IG_BIO_KEYWORDS in bio (resmi, official, kampus, etc.)
        bio_kw_matches = [kw for kw in IG_BIO_KEYWORDS if kw in bio]
        if bio_kw_matches:
            boost += 0.1
            reasons.append(f"bio keywords: {', '.join(bio_kw_matches)}")

        # Check 4: University website domain in external_url or bio
        if ".ac.id" in external_url or ".ac.id" in bio or ".sch.id" in external_url:
            boost += 0.1
            reasons.append("academic domain in link/bio")

        # Negative: bio clearly unrelated (personal account, shop, etc.)
        negative_keywords = ["olshop", "online shop", "jualan", "personal", "fan page", "parody"]
        if any(nk in bio for nk in negative_keywords):
            boost = -0.3
            reasons = ["bio indicates non-university account"]

        # Negative: bio indicates a subsidiary entity (clinic, hospital, etc.)
        subsidiary_matches = [kw for kw in _SUBSIDIARY_ENTITY_KEYWORDS if kw in bio]
        if subsidiary_matches:
            boost -= 0.35
            reasons.append(f"bio indicates subsidiary entity ({', '.join(subsidiary_matches[:3])})")

    verified = boost > 0
    reason_str = "; ".join(reasons) if reasons else "no university signals in bio"

    log.info(
        "Bio verify @%s for '%s': boost=%.2f (%s) | bio='%s'",
        handle, university_name[:40], boost, reason_str, bio[:100],
    )
    return {
        "verified": verified,
        "confidence_boost": boost,
        "bio": profile["bio"],
        "reason": reason_str,
    }


# ---------------------------------------------------------------------------
# Fallback wrappers: 4-tier Playwright -> IG Session -> Apify -> ScrapingBot â†’ Apify â†’ ScrapingBot
# ---------------------------------------------------------------------------

def scrape_ig_posts_with_fallback(
    ig_handle: str,
    max_posts: int | None = None,
    deeper: bool = False,
    known_post_urls: set[str] | None = None,
) -> list[dict]:
    """
    Smart scrape with 4-tier fallback.

    Tier 0: Playwright Stealth Browser (free, most ban-resistant)
    Tier 1: Direct IG Web API (session cookies)
    Tier 2: Apify Instagram Scraper (paid)
    Tier 3: Scraping-Bot.io (paid, last resort)

    When *deeper* is True (re-scrape), paid tiers request more posts
    (known count + max_posts) so they can reach beyond already-saved content.
    Known post URLs are filtered out before returning.

    Returns list of {"post_url", "image_url", "caption", "timestamp", "source"}.
    """
    handle = ig_handle.lstrip("@")
    effective_max = max_posts or IG_MAX_POSTS_PER_PROFILE
    known = known_post_urls or set()

    # For Apify/ScrapingBot we do NOT inflate fetch_count â€” they can only
    # return the N most-recent posts and don't support cursor pagination.
    # Requesting more just wastes paid API credits on posts we already have.
    # Any genuinely new posts (posted since last scrape) will appear at the
    # top of the results and get saved via INSERT OR IGNORE dedup.
    fetch_count = effective_max
    if deeper and known:
        log.info(
            "[Fallback] @%s: re-scrape mode â€” %d posts already in DB, fetching latest %d",
            handle, len(known), fetch_count,
        )

    # Tier 0: Playwright Stealth Browser (free, ban-resistant)
    if playwright_ig.is_available():
        log.info("[Tier0-Playwright] @%s: attempting scrape (max %d posts)", handle, effective_max)
        try:
            posts = playwright_ig.pw_get_posts(handle, max_posts=effective_max)
            if posts:
                for p in posts:
                    p.setdefault("source", "playwright")
                if known:
                    before = len(posts)
                    posts = [p for p in posts if p.get("post_url") not in known]
                    log.info(
                        "[Tier0-Playwright] @%s: %d fetched, %d new (filtered %d known)",
                        handle, before, len(posts), before - len(posts),
                    )
                else:
                    log.info("[Tier0-Playwright] @%s: got %d posts", handle, len(posts))
                # Tier 0 succeeded (fetched posts from IG).  Return whatever
                # we have -- even an empty list means "scrape worked, nothing
                # new".  Do NOT cascade to paid tiers just because all posts
                # are already in the DB; that wastes credits.
                return posts
            else:
                log.info("[Tier0-Playwright] @%s: returned 0 posts, falling through to next tier", handle)
        except Exception as e:
            log.warning("[Tier0-Playwright] @%s failed: %s", handle, e)
    else:
        log.info("[Tier0-Playwright] Skipping -- not available (daily_used=%d)",
                 playwright_ig._pw_status.get("profiles_today", 0))

    # Tier 1: Direct IG session
    if _ig_pool.get_current_session_id():
        try:
            results = scrape_ig_posts_sync(ig_handle, max_posts, deeper, known_post_urls)
            if results:
                log.info("[Tier1-Direct] @%s: got %d posts", handle, len(results))
                return results
            # If zero results but no error, session might still be OK
        except Exception as e:
            log.warning("[Tier1-Direct] @%s failed: %s", handle, e)
    else:
        log.info("[Tier1-Direct] Skipping â€” no healthy IG sessions")

    # Tier 2: Apify
    if apify_client.is_configured():
        try:
            posts = apify_client.apify_get_posts(handle, fetch_count)
            if posts:
                for p in posts:
                    p.setdefault("source", "apify")
                # Filter out known posts on re-scrape
                if known:
                    before = len(posts)
                    posts = [p for p in posts if p.get("post_url") not in known]
                    log.info(
                        "[Tier2-Apify] @%s: %d fetched, %d new (filtered %d known)",
                        handle, before, len(posts), before - len(posts),
                    )
                else:
                    log.info("[Tier2-Apify] @%s: got %d posts", handle, len(posts))
                if posts:
                    return posts
        except Exception as e:
            log.warning("[Tier2-Apify] @%s failed: %s", handle, e)
    else:
        log.debug("[Tier2-Apify] Skipping â€” not configured")

    # Tier 3: Scraping-Bot
    if scrapingbot_client.is_configured():
        try:
            posts = scrapingbot_client.scrapingbot_get_posts(
                handle,
                posts_number=fetch_count,
            )
            if posts:
                for p in posts:
                    p.setdefault("source", "scrapingbot")
                # Filter out known posts on re-scrape
                if known:
                    before = len(posts)
                    posts = [p for p in posts if p.get("post_url") not in known]
                    log.info(
                        "[Tier3-ScrapingBot] @%s: %d fetched, %d new (filtered %d known)",
                        handle, before, len(posts), before - len(posts),
                    )
                else:
                    log.info("[Tier3-ScrapingBot] @%s: got %d posts", handle, len(posts))
                if posts:
                    return posts
        except Exception as e:
            log.warning("[Tier3-ScrapingBot] @%s failed: %s", handle, e)
    else:
        log.debug("[Tier3-ScrapingBot] Skipping â€” not configured")

    log.warning("[Fallback] @%s: all tiers failed or 0 new posts", handle)
    return []


def search_ig_handle_with_fallback(university_name: str) -> dict | None:
    """
    Search for university IG handle with 4-tier fallback.

    Tier 0: Playwright Stealth Browser (free)
    Tier 1: Direct IG Web API (session cookies)
    Tier 2: Apify search (paid)
    Tier 3: ScrapingBot (no search API, skipped)

    Returns: {"handle": str, "url": str, "confidence": float} or None.
    """
    # Tier 0: Playwright Stealth Browser (free, ban-resistant)
    if playwright_ig.is_available():
        try:
            profiles = playwright_ig.pw_search_profiles(university_name)
            if profiles:
                best = None
                best_score = 0.0
                for p in profiles:
                    uu = {
                        "username": p.get("username", ""),
                        "full_name": p.get("full_name", ""),
                        "is_verified": p.get("is_verified", False),
                    }
                    score = _score_ig_user(uu, university_name)
                    if score > best_score:
                        best_score = score
                        best = {
                            "handle": p["username"],
                            "url": f"https://www.instagram.com/{p['username']}/",
                            "confidence": score,
                        }
                if best and best["confidence"] >= 0.65:
                    log.info("[Tier0-Playwright] Found @%s (score=%.2f) for '%s'",
                             best["handle"], best["confidence"], university_name[:40])
                    return best
        except Exception as e:
            log.warning("[Tier0-Playwright] Search failed for '%s': %s", university_name[:40], e)
    else:
        log.debug("[Tier0-Playwright] Skipping search - not available")

    # Tier 1: Direct IG session
    if _ig_pool.get_current_session_id():
        try:
            result = search_ig_handle_via_ig(university_name)
            if result:
                log.info("[Tier1-Direct] Found @%s for '%s'", result["handle"], university_name[:40])
                return result
        except Exception as e:
            log.warning("[Tier1-Direct] Search failed for '%s': %s", university_name[:40], e)
    else:
        log.info("[Tier1-Direct] Skipping search â€” no healthy IG sessions")

    # Tier 2: Apify search
    if apify_client.is_configured():
        try:
            profiles = apify_client.apify_search_profile(university_name, limit=10)
            if profiles:
                # Score each result using existing scoring logic
                best = None
                best_score = 0.0
                for p in profiles:
                    uu = {
                        "username": p["username"],
                        "full_name": p["full_name"],
                        "is_verified": p["is_verified"],
                    }
                    score = _score_ig_user(uu, university_name)
                    if score > best_score:
                        best_score = score
                        best = {
                            "handle": p["username"],
                            "url": f"https://www.instagram.com/{p['username']}/",
                            "confidence": score,
                        }

                if best and best["confidence"] >= 0.65:
                    log.info("[Tier2-Apify] Found @%s (score=%.2f) for '%s'",
                             best["handle"], best["confidence"], university_name[:40])
                    return best
        except Exception as e:
            log.warning("[Tier2-Apify] Search failed for '%s': %s", university_name[:40], e)
    else:
        log.debug("[Tier2-Apify] Skipping search â€” not configured")

    # Tier 3: Scraping-Bot doesn't have search, skip
    log.info("[Fallback] No IG handle found for '%s' across all tiers", university_name[:40])
    return None


def verify_ig_handle_with_fallback(handle: str, university_name: str) -> dict:
    """
    Verify an IG handle with 4-tier fallback for profile fetching.

    Tier 0: Playwright Stealth Browser (free)
    Tier 1: Direct IG Web API (session cookies)
    Tier 2: Apify profile fetch (paid)
    Tier 3: ScrapingBot profile fetch (paid, last resort)

    Returns: {"verified": bool, "confidence_boost": float, "bio": str, "reason": str}
    """
    # Tier 0: Playwright Stealth Browser (free, ban-resistant)
    if playwright_ig.is_available():
        try:
            profile = playwright_ig.pw_get_profile(handle)
            if profile:
                return _verify_from_profile_data(handle, university_name, profile)
        except Exception as e:
            log.warning("[Tier0-Playwright] Verify failed for @%s: %s", handle, e)
    else:
        log.debug("[Tier0-Playwright] Skipping verify - not available")

    # Tier 1: Direct IG session
    if _ig_pool.get_current_session_id():
        try:
            result = verify_ig_handle(handle, university_name)
            if result.get("reason") != "no session":
                return result
        except Exception as e:
            log.warning("[Tier1-Direct] Verify failed for @%s: %s", handle, e)

    # Tier 2: Apify profile fetch
    if apify_client.is_configured():
        try:
            profile = apify_client.apify_get_profile(handle)
            if profile:
                return _verify_from_profile_data(handle, university_name, profile)
        except Exception as e:
            log.warning("[Tier2-Apify] Verify failed for @%s: %s", handle, e)

    # Tier 3: Scraping-Bot profile fetch
    if scrapingbot_client.is_configured():
        try:
            profile = scrapingbot_client.scrapingbot_get_profile(handle, posts_number=0)
            if profile:
                return _verify_from_profile_data(handle, university_name, profile)
        except Exception as e:
            log.warning("[Tier3-ScrapingBot] Verify failed for @%s: %s", handle, e)

    return {"verified": True, "confidence_boost": 0, "bio": "", "reason": "all providers failed (skipped)"}


def _verify_from_profile_data(handle: str, university_name: str, profile: dict) -> dict:
    """
    Run verification logic on profile data from any provider (Apify/ScrapingBot).

    The profile dict should have: bio, full_name, external_url, is_verified.
    """
    bio = (profile.get("bio", "") or "").lower()
    external_url = (profile.get("external_url", "") or "").lower()
    uni_lower = university_name.lower()
    all_words = uni_lower.split()

    location_word = all_words[-1] if all_words else ""
    generic = {
        "universitas", "institut", "sekolah", "tinggi", "negeri", "islam",
        "agama", "politeknik", "akademi", "ilmu", "teknologi", "stie", "stkip",
        "dan", "yang", "dari",
    }
    unique_words = [w for w in all_words if len(w) > 3 and w not in generic and w != location_word]

    boost = 0.0
    reasons = []

    handle_lower = handle.lower()
    dept_match = [d for d in _DEPT_HANDLE_KEYWORDS if d in handle_lower]
    if dept_match:
        boost -= 0.25
        reasons.append(f"sub-department handle ({', '.join(dept_match)})")

    if not bio.strip():
        boost -= 0.15
        reasons.append("empty bio")
    else:
        unique_in_bio = sum(1 for w in unique_words if w in bio)
        if unique_in_bio > 0:
            boost += 0.15 * min(unique_in_bio / max(len(unique_words), 1), 1.0)
            reasons.append(f"{unique_in_bio} unique words in bio")

        if location_word and len(location_word) > 3 and location_word in bio:
            boost += 0.1
            reasons.append(f"location '{location_word}' in bio")

        bio_kw_matches = [kw for kw in IG_BIO_KEYWORDS if kw in bio]
        if bio_kw_matches:
            boost += 0.1
            reasons.append(f"bio keywords: {', '.join(bio_kw_matches)}")

        if ".ac.id" in external_url or ".ac.id" in bio or ".sch.id" in external_url:
            boost += 0.1
            reasons.append("academic domain in link/bio")

        negative_keywords = ["olshop", "online shop", "jualan", "personal", "fan page", "parody"]
        if any(nk in bio for nk in negative_keywords):
            boost = -0.3
            reasons = ["bio indicates non-university account"]

        # Negative: bio indicates a subsidiary entity (clinic, hospital, etc.)
        subsidiary_matches = [kw for kw in _SUBSIDIARY_ENTITY_KEYWORDS if kw in bio]
        if subsidiary_matches:
            boost -= 0.35
            reasons.append(f"bio indicates subsidiary entity ({', '.join(subsidiary_matches[:3])})")

    verified = boost > 0
    reason_str = "; ".join(reasons) if reasons else "no university signals in bio"

    log.info(
        "Bio verify @%s for '%s' (via fallback): boost=%.2f (%s) | bio='%s'",
        handle, university_name[:40], boost, reason_str, bio[:100],
    )
    return {
        "verified": verified,
        "confidence_boost": boost,
        "bio": profile.get("bio", ""),
        "reason": reason_str,
    }


# ---------------------------------------------------------------------------
# Phase 3b: Extract Phone Numbers from Images (OpenAI Vision)
# ---------------------------------------------------------------------------

async def extract_phone_from_image(image_url: str, caption: str = "") -> list[PhoneContact]:
    """
    Extract Indonesian phone numbers with contact names from a flyer/poster image.
    Uses GPT for both caption text and Vision OCR on images.
    Only returns contacts that have a real person's name (not generic names).
    """
    by_phone: dict[str, PhoneContact] = {}

    # 1. Extract named contacts from caption text via GPT
    caption_contacts = await extract_named_contacts_from_text(caption)
    for c in caption_contacts:
        by_phone[c["phone"]] = c

    # 2. Extract named contacts from image via Vision API
    try:
        image_b64 = await _download_image_as_base64(image_url)
        if image_b64:
            vision_contacts = await _vision_extract_named_contacts(image_b64)
            for c in vision_contacts:
                existing = by_phone.get(c["phone"])
                if not existing or (not existing["name"] and c["name"]):
                    by_phone[c["phone"]] = c
    except Exception as e:
        log.error(f"Vision extraction failed for {image_url}: {e}")

    return list(by_phone.values())


async def extract_named_contacts_from_text(text: str) -> list[PhoneContact]:
    """
    Extract phone numbers with contact names from text using GPT-4o-mini.
    Only returns contacts where a person's name is associated with the number.
    Skips GPT call if no phone number is detected in the text.
    """
    if not text or not _PHONE_QUICK_RE.search(text.replace(" ", "").replace("-", "")):
        return []

    client = _get_openai()
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Kamu adalah asisten yang mengekstrak nomor HP/WhatsApp Indonesia dari teks. "
                        "HANYA ambil nomor HANDPHONE/WHATSAPP (08xx/+628xx). ABAIKAN nomor telepon rumah/kantor (021-xxx, 0361-xxx, dll). "
                        "Untuk setiap nomor, cari nama orang yang LANGSUNG BERDEKATAN dengan nomor tersebut. "
                        "Jika tidak ada nama orang di dekat nomor, isi name dengan string kosong \"\". "
                        "JANGAN pasangkan nama yang jauh dari nomor atau tidak terkait (misal nama mahasiswa, pembicara, rektor). "
                        "Format: 08xx-xxxx-xxxx atau +62-8xx-xxxx-xxxx. "
                        "Jawab dalam format JSON array: [{\"phone\": \"08xxx\", \"name\": \"Nama atau kosong\"}]\n"
                        "Jika tidak ada nomor HP/WA, jawab: []"
                    ),
                },
                {
                    "role": "user",
                    "content": f"Ekstrak semua nomor telepon dari teks ini:\n\n{text}",
                },
            ],
            max_tokens=300,
            temperature=0,
        )
    except Exception as e:
        log.error(f"GPT text extraction error: {e}")
        return []

    raw = response.choices[0].message.content or ""
    return _parse_phone_contacts_json(raw)


def extract_phones_from_text(text: str) -> list[str]:
    """Extract phone numbers from text using regex patterns."""
    phones = []
    for pattern in PHONE_PATTERNS:
        matches = re.findall(pattern, text)
        phones.extend(matches)

    # Also try simple pattern for numbers like 081234567890
    simple = re.findall(r'(?:(?:\+62|62|0)8\d{8,12})', text.replace(" ", "").replace("-", ""))
    phones.extend(simple)

    return list(set(phones))


async def _download_image_as_base64(url: str) -> str | None:
    """Download image and return as base64 string."""
    from orchestrator.config import is_paused

    if is_paused():
        return None

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return base64.b64encode(resp.content).decode("utf-8")
        except asyncio.CancelledError:
            log.warning(f"Image download cancelled (shutdown/pause): {url[:80]}...")
            return None
        except Exception as e:
            # Only log error if not a shutdown-related error
            error_msg = str(e)
            if "cannot schedule new futures" not in error_msg and "interpreter shutdown" not in error_msg:
                log.error(f"Failed to download image {url[:80]}...: {e}")
            return None


async def _vision_extract_named_contacts(image_b64: str) -> list[PhoneContact]:
    """Use OpenAI Vision to extract phone numbers with contact names from image."""
    from orchestrator.config import is_paused

    if is_paused():
        return []

    client = _get_openai()

    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Kamu adalah asisten yang mengekstrak nomor HP/WhatsApp Indonesia dari gambar flyer/poster. "
                        "HANYA ambil nomor HANDPHONE/WHATSAPP (08xx/+628xx). ABAIKAN nomor telepon rumah/kantor (021-xxx, 0361-xxx, dll). "
                        "ATURAN:\n"
                        "1. Untuk setiap nomor HP, cari nama orang yang LANGSUNG BERDEKATAN dengan nomor tersebut.\n"
                        "2. Jika tidak ada nama orang di dekat nomor, isi name dengan string kosong \"\".\n"
                        "3. JANGAN pasangkan nama yang letaknya JAUH dari nomor.\n"
                        "4. JANGAN ambil nama dari bagian lain gambar yang tidak terkait (misal: nama mahasiswa, pembicara, rektor).\n"
                        "5. Format: 08xx-xxxx-xxxx atau +62-8xx-xxxx-xxxx.\n"
                        "Jawab dalam format JSON array: [{\"phone\": \"08xxx\", \"name\": \"Nama atau kosong\"}]\n"
                        "Jika tidak ada nomor HP/WA, jawab: []"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Ekstrak semua nomor telepon/HP/WhatsApp dari gambar ini. Sertakan nama orang jika ada di dekat nomor:",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=500,
            temperature=0,
        )
    except asyncio.CancelledError:
        log.warning("GPT Vision extraction cancelled (shutdown/pause)")
        return []
    except Exception as e:
        error_msg = str(e)
        if "cannot schedule new futures" not in error_msg and "interpreter shutdown" not in error_msg:
            log.error(f"OpenAI Vision API error: {e}")
        return []

    raw = response.choices[0].message.content or ""
    if "NONE" in raw.upper():
        return []

    return _parse_phone_contacts_json(raw)


def _parse_phone_contacts_json(raw: str) -> list[PhoneContact]:
    """Parse GPT JSON response into validated PhoneContact list."""
    # Try to extract JSON array from response
    raw = raw.strip()
    # Handle markdown code blocks
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find JSON array in the text
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                log.debug("Failed to parse phone contacts JSON: %s", raw[:200])
                return []
        else:
            return []

    if not isinstance(data, list):
        return []

    results: list[PhoneContact] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        phone = str(item.get("phone", "")).strip()
        name = str(item.get("name", "")).strip()
        if not phone:
            continue
        # Clear generic/label names â€” treat as no name
        if name and _is_generic_name(name):
            name = ""
        validated = validate_phone(phone)
        if validated:
            results.append(PhoneContact(phone=validated, name=name))

    return results


# ---------------------------------------------------------------------------
# BEM discovery: search BEM handle & scan following list
# ---------------------------------------------------------------------------

# Keywords that indicate a BEM (student council) account
_BEM_HANDLE_KEYWORDS = [
    "bem_", "bem.", "bemfh", "bemft", "bemfe", "bemfk", "bemfi",
    "bemfp", "bemfs", "bemfa", "bemu", "bemuniv", "bem",
]

_BEM_BIO_KEYWORDS = [
    "badan eksekutif mahasiswa", "bem ", "student executive board",
    "kabinet", "mahasiswa", "student council", "student government",
    "dema", "dewan eksekutif mahasiswa",
]

# Generic institution words â€” not distinctive for search queries
_UNI_GENERIC_WORDS = {
    "universitas", "institut", "sekolah", "tinggi", "negeri", "islam",
    "agama", "politeknik", "akademi", "ilmu", "teknologi", "swasta",
    "katolik", "kristen", "stie", "stkip",
}

# Non-institutional handles to skip in following scan
_NON_INSTITUTION_HANDLES = {
    "instagram", "threads", "facebook", "twitter", "tiktok",
    "youtube", "spotify", "linkedin", "google",
}


def _build_bem_queries(university_name: str) -> list[str]:
    """Build effective IG search queries for discovering a university's BEM.

    BEM accounts typically use the university *abbreviation* in their handle,
    e.g. @bemuad, @bem_uia, @bemunmuha.  We generate:
      1. Acronym-based: "BEM UAD"
      2. Distinctive-words: "BEM Ahmad Dahlan Aceh"
      3. Full name (short): "BEM Universitas Ahmad Dahlan"
    """
    words = university_name.lower().strip().split()
    if not words:
        return [f"BEM {university_name}"]

    location = words[-1] if len(words) > 1 else ""
    unique = [w for w in words if w not in _UNI_GENERIC_WORDS and w != location and len(w) > 2]

    seen: set[str] = set()
    queries: list[str] = []

    def _add(q: str):
        key = q.lower()
        if key not in seen:
            seen.add(key)
            queries.append(q)

    # --- 1. Acronym from non-generic words (most effective) ---------
    # "Universitas Ahmad Dahlan Aceh" â†’ initials of all: U-A-D-A
    # Take all-words acronym (the way Indonesians abbreviate)
    all_initials = "".join(w[0].upper() for w in words)
    if len(all_initials) >= 3:
        _add(f"BEM {all_initials}")
        # Also without location initial: "UAD" from "UADA"
        if location and len(all_initials) > 3:
            no_loc = all_initials[:-1]
            if len(no_loc) >= 3:
                _add(f"BEM {no_loc}")

    # --- 2. Distinctive words + location -------------------------
    if unique:
        parts = [w.title() for w in unique]
        if location:
            parts.append(location.title())
        _add(f"BEM {' '.join(parts)}")
        # Also just distinctive words (no location)
        if location and len(unique) >= 1:
            _add(f"BEM {' '.join(w.title() for w in unique)}")

    # --- 3. Shorter full name (drop "universitas"/"institut" prefix) --
    # "Ahmad Dahlan Aceh" or "Muhammadiyah Aceh"
    non_prefix = [w for w in words if w not in {"universitas", "institut", "politeknik",
                                                  "sekolah", "tinggi", "akademi"}]
    if non_prefix and len(non_prefix) < len(words):
        _add(f"BEM {' '.join(w.title() for w in non_prefix)}")

    # --- 4. Full name as fallback --------------------------------
    _add(f"BEM {university_name.strip().title()}")

    return queries


def search_bem_handle_via_ig(university_name: str) -> dict | None:
    """Search for a university's BEM Instagram handle via IG Web Search API.

    Uses acronym-based and distinctive-word queries for better hit rate.
    Returns: {"handle": str, "confidence": float} or None.
    Sync function â€” call from executor in async context.
    """
    if not _ig_pool.get_current_session_id():
        log.warning("[BEM-Search] No IG session available, skipping %s", university_name)
        return None

    queries = _build_bem_queries(university_name)
    log.info("[BEM-Search] %s â†’ queries: %s", university_name, queries[:5])

    best = None
    best_score = 0.0

    client = _get_ig_web_client()
    try:
        for query in queries[:5]:  # Up to 5 queries
            resp = client.get(
                "https://www.instagram.com/web/search/topsearch/",
                params={"query": query, "context": "user"},
            )
            if not _check_ig_response(resp):
                log.warning("[BEM-Search] IG rate-limit/block on query '%s'", query)
                break
            if resp.status_code != 200:
                continue

            try:
                users = resp.json().get("users", [])[:10]
            except (ValueError, KeyError):
                continue

            if users:
                log.debug(
                    "[BEM-Search] Query '%s' â†’ %d candidates: %s",
                    query, len(users),
                    [u["user"]["username"] for u in users[:5]],
                )

            for u in users:
                uu = u["user"]
                score = _score_bem_user(uu, university_name)
                if score > best_score:
                    best_score = score
                    best = {
                        "handle": uu["username"],
                        "confidence": score,
                    }
                    log.debug(
                        "[BEM-Search] New best: @%s score=%.2f (query='%s')",
                        uu["username"], score, query,
                    )

            if best_score >= 0.7:
                break
            _time.sleep(cfg.IG_REQUEST_DELAY_SECONDS)

        if best and best["confidence"] >= 0.5:
            log.info(
                "[BEM-Search] Winner for %s: @%s (score=%.2f)",
                university_name, best["handle"], best["confidence"],
            )
            return best

        log.info(
            "[BEM-Search] No match for %s (best_score=%.2f)",
            university_name, best_score,
        )
    finally:
        client.close()

    return None


async def search_related_accounts_via_search(university_name: str) -> list[dict]:
    """Search for BEM, humas, pmb, kemahasiswaan, alumni, and lppm IG accounts
    via DuckDuckGo (free, primary) with Serper as optional fallback.
    Does NOT require an IG session.

    Strategy: build keyword-prefixed queries per relation type, collect all
    handles from search results, then pipe them through the existing
    find_related_accounts_from_following() classifier - same scoring logic
    as the IG-following approach.

    Returns list of {"handle": str, "relation_type": str, "confidence": float}
    sorted by confidence descending.
    """
    # Query prefixes per relation type (Indonesian + English)
    _TYPE_QUERIES: dict[str, list[str]] = {
        "bem":            ["BEM", "Badan Eksekutif Mahasiswa"],
        "humas":          ["Humas", "Hubungan Masyarakat"],
        "pmb":            ["PMB", "Penerimaan Mahasiswa Baru", "Admisi"],
        "kemahasiswaan":  ["Kemahasiswaan", "Bidang Kemahasiswaan"],
        "alumni":         ["Alumni", "IKA"],
        "lppm":           ["LPPM", "LP2M"],
    }

    # Build university acronym for queries (e.g. "Universitas Ahmad Dahlan" -> "UAD")
    uni_words = university_name.strip().split()
    acronym = "".join(w[0] for w in uni_words).upper()

    candidate_users: list[dict] = []
    seen_handles: set[str] = set()

    # ------------- Primary: DuckDuckGo (free) -------------
    for rel_type, prefixes in _TYPE_QUERIES.items():
        for prefix in prefixes[:1]:  # 1 prefix per type to limit queries
            ddg_query = f'site:instagram.com "{prefix} {acronym}"'
            try:
                results = await duckduckgo_client.async_search_text(ddg_query, max_results=5)
                for result in results:
                    handle = _extract_ig_handle(result.get("link", ""))
                    if not handle or handle in seen_handles:
                        continue
                    seen_handles.add(handle)
                    candidate_users.append({
                        "username": handle,
                        "full_name": result.get("title", ""),
                        "is_verified": False,
                    })
            except Exception as e:
                log.warning("[BEM-DDG] Query '%s' failed: %s", ddg_query, e)

    # ------------- Fallback: Serper (if configured and DDG found nothing) -------------
    if not candidate_users and cfg.SERPER_API_KEY:
        consecutive_errors = 0
        async with httpx.AsyncClient(timeout=15) as client:
            for rel_type, prefixes in _TYPE_QUERIES.items():
                if consecutive_errors >= 2:
                    log.warning(
                        "[BEM-Serper] Aborting early - %d consecutive failures",
                        consecutive_errors,
                    )
                    break
                for prefix in prefixes[:1]:
                    serper_query = f'site:instagram.com "{prefix} {acronym}"'
                    try:
                        resp = await client.post(
                            "https://google.serper.dev/search",
                            headers={
                                "X-API-KEY": cfg.SERPER_API_KEY,
                                "Content-Type": "application/json",
                            },
                            json={"q": serper_query, "num": 5},
                        )
                        if resp.status_code != 200:
                            _update_serper_status(False, "quota_exceeded")
                            consecutive_errors += 1
                            continue
                        _update_serper_status(True)
                        consecutive_errors = 0
                        data = resp.json()
                    except Exception as e:
                        log.warning("[BEM-Serper] Query '%s' failed: %s", serper_query, e)
                        consecutive_errors += 1
                        continue

                    for result in data.get("organic", []):
                        handle = _extract_ig_handle(result.get("link", ""))
                        if not handle or handle in seen_handles:
                            continue
                        seen_handles.add(handle)
                        candidate_users.append({
                            "username": handle,
                            "full_name": result.get("title", ""),
                            "is_verified": False,
                        })

    if not candidate_users:
        log.info("[BEM-Search] No candidates found for %s", university_name)
        return []

    log.info("[BEM-Search] %s -> %d candidates, classifying...", university_name, len(candidate_users))

    # Reuse existing classifier
    results = find_related_accounts_from_following(candidate_users, university_name)

    log.info(
        "[BEM-Search] %s -> %d classified: %s",
        university_name, len(results),
        [(r["handle"], r["relation_type"], r["confidence"]) for r in results[:5]],
    )
    return results


async def search_bem_handle_via_search(university_name: str) -> dict | None:
    """Thin wrapper returning only the top BEM result from search_related_accounts_via_search()."""
    results = await search_related_accounts_via_search(university_name)
    bem_results = [r for r in results if r["relation_type"] == "bem"]
    if bem_results:
        return {"handle": bem_results[0]["handle"], "confidence": bem_results[0]["confidence"]}
    return None


def _score_bem_user(user_data: dict, university_name: str) -> float:
    """Score an IG search result for BEM relevance to a university.

    Checks:
      - BEM keyword presence (mandatory gate)
      - University acronym in handle  (very common: @bemuad, @bemfia)
      - Location word in full_name or handle
      - Distinctive name words in full_name or handle
      - Verified badge bonus
    """
    username = user_data.get("username", "").lower()
    full_name = (user_data.get("full_name", "") or "").lower()

    uni_lower = university_name.lower()
    all_words = uni_lower.split()
    location_word = all_words[-1] if len(all_words) > 1 else ""

    score = 0.0

    # â”€â”€ Gate: must contain BEM keyword â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    has_bem = any(kw in username for kw in _BEM_HANDLE_KEYWORDS) or any(
        kw in full_name for kw in _BEM_BIO_KEYWORDS
    )
    if not has_bem:
        return 0.0

    score += 0.25  # Base score for being BEM

    # â”€â”€ Acronym check (strongest signal) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # "universitas ahmad dahlan aceh" â†’ "uada"; without location â†’ "uad"
    all_initials = "".join(w[0] for w in all_words).lower()
    no_loc_initials = "".join(w[0] for w in all_words[:-1]).lower() if len(all_words) > 1 else all_initials
    combined = username + " " + full_name
    if len(no_loc_initials) >= 2 and no_loc_initials in combined:
        score += 0.35
    elif len(all_initials) >= 2 and all_initials in combined:
        score += 0.30

    # â”€â”€ Location match â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if location_word and len(location_word) > 2:
        if location_word in full_name:
            score += 0.20
        elif location_word in username:
            score += 0.15

    # â”€â”€ Distinctive words match â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    unique_words = [w for w in all_words if w not in _UNI_GENERIC_WORDS
                    and w != location_word and len(w) > 2]
    if unique_words:
        matching = sum(1 for w in unique_words if w in full_name or w in username)
        score += 0.20 * min(matching / len(unique_words), 1.0)

    # â”€â”€ Verified bonus â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if user_data.get("is_verified", False):
        score += 0.10

    return max(min(score, 1.0), 0.0)


def get_ig_following(handle: str, max_results: int = 200) -> list[dict]:
    """Fetch the following list of an IG account via Web API.

    Returns list of: {"username": str, "full_name": str, "is_verified": bool}
    Sync function â€” call from executor in async context.
    """
    if not _ig_pool.get_current_session_id():
        return []

    client = _get_ig_web_client()
    try:
        # Step 1: Get user_id
        info = _ig_web_get_user_info(client, handle)
        if not info:
            log.warning("[BEM] Could not get user_id for @%s", handle)
            return []

        user_id = info["user_id"]

        # Step 2: Paginate through following list
        following: list[dict] = []
        max_id = ""
        page = 0
        max_pages = max_results // 50 + 1  # ~50 per page

        while page < max_pages and len(following) < max_results:
            _time.sleep(2)  # Rate limit
            params = {"count": 50}
            if max_id:
                params["max_id"] = max_id

            resp = client.get(
                f"https://www.instagram.com/api/v1/friendships/{user_id}/following/",
                params=params,
            )
            if not _check_ig_response(resp):
                break
            if resp.status_code != 200:
                log.warning("[BEM] Following API returned %d for @%s", resp.status_code, handle)
                break

            try:
                data = resp.json()
            except (ValueError, KeyError):
                break

            users = data.get("users", [])
            if not users:
                break

            for u in users:
                uname = u.get("username", "").lower()
                if uname in _NON_INSTITUTION_HANDLES:
                    continue
                following.append({
                    "username": u.get("username", ""),
                    "full_name": u.get("full_name", ""),
                    "is_verified": u.get("is_verified", False),
                })

            # Check for next page
            if not data.get("next_max_id"):
                break
            max_id = data["next_max_id"]
            page += 1

        log.info("[BEM] Fetched %d following for @%s", len(following), handle)
        return following

    except Exception as e:
        log.error("[BEM] Error fetching following for @%s: %s", handle, e)
        return []
    finally:
        client.close()


def find_related_accounts_from_following(
    following: list[dict], university_name: str,
) -> list[dict]:
    """Categorise the following list of an official university IG account.

    Scans each followed account and classifies it as BEM, humas, pmb,
    kemahasiswaan, alumni, lppm, or unknown.  Returns only accounts that
    were positively matched to a category, sorted by confidence descending.

    Each item: {"handle": str, "relation_type": str, "confidence": float,
                "full_name": str}
    """
    if not following:
        return []

    # â”€â”€ Keyword â†’ relation_type mapping â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _RELATION_KEYWORDS: list[tuple[list[str], str]] = [
        (["bem_", "bem.", "bemfh", "bemft", "bemfe", "bemfk", "bemfi",
          "bemfp", "bemfs", "bemfa", "bemu", "bemuniv"], "bem"),
        (["humas", "humasuniv", "humas_", "public_relation"], "humas"),
        (["pmb_", "pmb.", "pmbuniv", "admisi", "admission", "pendaftaran"], "pmb"),
        (["kemahasiswaan", "kemahasiswaanuniv", "kemhs"], "kemahasiswaan"),
        (["alumni_", "alumni.", "alumniassoc", "ika_"], "alumni"),
        (["lppm", "lp2m", "penelitian"], "lppm"),
    ]

    _BIO_KEYWORDS: dict[str, list[str]] = {
        "bem": ["badan eksekutif mahasiswa", "student executive", "kabinet",
                "dema ", "dewan eksekutif"],
        "humas": ["humas", "public relation", "kehumasan", "informasi publik"],
        "pmb": ["penerimaan mahasiswa", "pendaftaran", "admission"],
        "kemahasiswaan": ["kemahasiswaan", "student affair"],
        "alumni": ["alumni", "ikatan alumni"],
        "lppm": ["penelitian", "pengabdian", "research"],
    }

    uni_lower = university_name.lower()
    all_words = uni_lower.split()
    # Build university acronym (e.g. "universitas ahmad dahlan" â†’ "uad")
    uni_initials = "".join(w[0] for w in all_words).lower() if all_words else ""
    # Unique words for matching
    unique_words = [w for w in all_words if w not in _UNI_GENERIC_WORDS and len(w) > 2]
    location_word = all_words[-1] if len(all_words) > 1 else ""

    results: list[dict] = []

    for user in following:
        username = user.get("username", "").lower()
        full_name = (user.get("full_name", "") or "").lower()
        combined = username + " " + full_name

        # Skip super-generic / platform accounts
        if username in _NON_INSTITUTION_HANDLES:
            continue

        # â”€â”€ Try to classify by handle keywords â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        matched_type = None
        for keywords, rel_type in _RELATION_KEYWORDS:
            if any(kw in username for kw in keywords):
                matched_type = rel_type
                break

        # â”€â”€ Fallback: classify by bio/full_name keywords â”€â”€â”€â”€â”€
        if not matched_type:
            for rel_type, bio_kws in _BIO_KEYWORDS.items():
                if any(kw in full_name for kw in bio_kws):
                    matched_type = rel_type
                    break

        # Also detect BEM via standalone "bem" token in username
        if not matched_type and ("bem" in username.split("_") or
                                  "bem" in username.split(".")):
            matched_type = "bem"

        if not matched_type:
            continue

        # â”€â”€ Score: how likely is this account related to THIS university? â”€
        confidence = 0.3  # base: matched a category

        # Acronym match  (e.g. "bemuad" contains "uad")
        if len(uni_initials) >= 3 and uni_initials in combined:
            confidence += 0.35
        # No-location acronym  (e.g. "uad" from "uada")
        elif len(uni_initials) >= 4:
            no_loc = uni_initials[:-1]
            if no_loc in combined:
                confidence += 0.30

        # Location word
        if location_word and len(location_word) > 2 and location_word in combined:
            confidence += 0.15

        # Unique word match
        if unique_words:
            matching = sum(1 for w in unique_words if w in combined)
            confidence += 0.15 * min(matching / len(unique_words), 1.0)

        # Verified bonus
        if user.get("is_verified", False):
            confidence += 0.05

        confidence = round(min(confidence, 1.0), 3)

        results.append({
            "handle": user["username"],
            "relation_type": matched_type,
            "confidence": confidence,
            "full_name": user.get("full_name", ""),
        })

    # Sort by confidence descending
    results.sort(key=lambda r: r["confidence"], reverse=True)

    log.info(
        "[BEM-Scan] '%s' following scan: found %d related accounts: %s",
        university_name, len(results),
        [(r["handle"], r["relation_type"], r["confidence"]) for r in results[:10]],
    )
    return results

# Backward-compatible aliases
search_related_accounts_via_serper = search_related_accounts_via_search
search_bem_handle_via_serper = search_bem_handle_via_search
