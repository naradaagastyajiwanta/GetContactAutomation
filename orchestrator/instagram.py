"""
Instagram utilities: search handles, scrape posts, extract phone numbers via Vision API.

This module provides shared utility functions used by the pipeline agents in
orchestrator/agents/. It does not contain orchestration logic.

Scraping uses the Instagram **Web API** (same endpoints as the browser) with
a browser session cookie.  This avoids the Mobile/Private API IP-blacklist
issues that plague instagrapi / instaloader.
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
# IG session health tracking
# ---------------------------------------------------------------------------
_ig_session_status: dict = {"ok": True, "error": None}


def get_ig_session_status() -> dict:
    """Return current IG session health: {"ok": bool, "error": str|None}."""
    return dict(_ig_session_status)


def _check_ig_response(resp: httpx.Response) -> bool:
    """Check if an IG response indicates a suspended/login-required session.
    Returns True if response is OK, False if session is broken."""
    global _ig_session_status
    url = str(resp.url)
    if "/accounts/suspended" in url:
        _ig_session_status = {"ok": False, "error": "suspended"}
        log.warning("IG session is SUSPENDED — update IG_SESSION_ID in config")
        return False
    if "/accounts/login" in url:
        _ig_session_status = {"ok": False, "error": "login_required"}
        log.warning("IG session expired (login required) — update IG_SESSION_ID in config")
        return False
    # If we get a normal 200 response, mark session as OK
    if resp.status_code == 200:
        _ig_session_status = {"ok": True, "error": None}
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
    Gets the website URL from PDDIKTI first, then falls back to Google.
    Returns: {"handle": str, "url": str, "confidence": float} or None.
    """
    # Step 1: Get website URL (PDDIKTI → Google fallback)
    if not website_url and not skip_pddikti:
        website_url = await _get_website_from_pddikti(university_name)

    if not website_url and cfg.SERPER_API_KEY:
        name = university_name.strip().title()

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": cfg.SERPER_API_KEY, "Content-Type": "application/json"},
                    json={"q": f'"{name}" site:ac.id OR site:sch.id', "num": 5},
                )
                resp.raise_for_status()
                for r in resp.json().get("organic", []):
                    url = r.get("link", "")
                    if not (".ac.id" in url or ".edu" in url or ".sch.id" in url):
                        continue
                    # Only accept if the URL is the homepage of an .ac.id domain.
                    # Deep pages on other university domains (articles, news) that
                    # just *mention* this university must be rejected.
                    path = urlparse(url).path.rstrip("/")
                    is_homepage = path == "" or path == "/"
                    if is_homepage:
                        website_url = url
                        break
                    else:
                        log.debug(
                            "Serper result '%s' rejected — not a homepage (path='%s')",
                            url, path,
                        )
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
        # No HTML but we found the website URL — return it without handle
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

    # The first IG handle on a university website is almost always the official one
    handle = unique[0]
    log.info("Website %s has IG link: @%s", website_url, handle)
    return {
        "handle": handle,
        "url": f"https://www.instagram.com/{handle}/",
        "confidence": 0.9,  # Very high — from their own website
        "website_url": website_url,
    }


# ---------------------------------------------------------------------------
# Phase 2b: Search Instagram Handle via Google (Serper.dev)
# ---------------------------------------------------------------------------

async def search_ig_handle(university_name: str) -> dict | None:
    """
    Search for university's Instagram handle via Serper.dev Google search.
    Returns: {"handle": "@univ_name", "url": "...", "confidence": 0.0-1.0} or None
    """
    if not cfg.SERPER_API_KEY:
        log.warning("cfg.SERPER_API_KEY not set, skipping IG search")
        return None

    # Normalize: PDDIKTI names are ALL CAPS → title case for better Google results
    name = university_name.strip().title()

    # Build search queries — try exact match first, then relaxed
    queries = [
        f'site:instagram.com "{name}"',
        f'site:instagram.com {name} instagram',
    ]

    for query in queries:
        result = await _serper_search_ig(query, university_name)
        if result:
            return result

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
            resp.raise_for_status()
            data = resp.json()
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

    # Words that are generic institution types or location names — NOT unique to a specific university
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

    # Build abbreviation from university name (e.g. "Institut Ilmu Kesehatan Medika Persada" → "iikmp")
    # Skip common filler words
    _SKIP_ABBREV = {"dan", "dan", "di", "the", "of"}
    abbrev = "".join(
        w[0] for w in uni_words if len(w) > 1 and w not in _SKIP_ABBREV
    )

    # Strip separators from handle for matching (e.g. "std_bali" → "stdbali")
    handle_stripped = re.sub(r'[_.\-]', '', handle_lower)

    # Handle matches unique words (strong signal)
    unique_in_handle = sum(1 for w in unique_words if w in handle_stripped)
    # Handle matches abbreviation (e.g. "iikmpbali" contains "iikmp", "std_bali" → "stdbali" contains "stdb")
    abbrev_match = len(abbrev) >= 3 and abbrev in handle_stripped

    if unique_in_handle > 0 or abbrev_match:
        word_score = 0.35 * min(unique_in_handle / max(len(unique_words), 1), 1.0)
        abbrev_score = 0.30 if abbrev_match else 0.0
        score += max(word_score, abbrev_score)
    else:
        # Handle only matches generic words — weak signal
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
    _NON_INSTITUTION = ["personal", "fan", "meme", "info_", "pers", "himpunan", "bem_", "himapsi"]
    if any(x in handle_lower for x in _NON_INSTITUTION):
        score -= 0.15

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
    """Create an httpx Client with Instagram browser session cookies."""
    if not cfg.IG_SESSION_ID:
        raise RuntimeError(
            "cfg.IG_SESSION_ID not set in .env. "
            "Get it from browser: F12 → Application → Cookies → instagram.com → sessionid"
        )
    cookies = {"sessionid": cfg.IG_SESSION_ID}
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

# Sub-department handle prefixes — these are NOT the main university account
_DEPT_HANDLE_KEYWORDS = [
    "kemahasiswaan", "humas", "pmb", "biro", "upt", "lppm",
    "perpustakaan", "lpm", "bak", "baak", "alumni", "bem",
    "hmj", "ormawa", "ukm",
]


def _ig_web_get_user_info(client: httpx.Client, handle: str) -> dict | None:
    """
    Get user_id, bio, and external_url for an IG handle.

    Uses two requests:
      1. Search API → user_id (+ basic info)
      2. Profile API → bio, external_url, bio_links (search doesn't return these)

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
        max_id: Pagination cursor — pass the ``next_max_id`` from a previous
                call to fetch *older* posts.

    Returns:
        (posts, next_max_id) — ``next_max_id`` is ``None`` when there are no
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

    # Tier B: caption has flyer/event keywords → image might contain phone
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
         - "has_phone"   → phone regex found in caption
         - "likely_flyer" → event/flyer keywords (image may have phone)
         - "skip"        → not relevant
      4. Early stop once we have enough "has_phone" results
      5. Return bio + has_phone + likely_flyer for downstream extraction

    This is a SYNC function — call from executor in async context.
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
        # Step 1: Get user info (single request → user_id + bio + external_url)
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

                cls = _classify_post(post)
                if cls == "has_phone":
                    post["source"] = "caption_phone"
                    results.append(post)
                    phone_count += 1
                    if phone_count >= _ENOUGH_PHONE_RESULTS:
                        log.info("@%s: early stop — %d phone posts found", handle, phone_count)
                        break
                elif cls == "likely_flyer":
                    post["source"] = "flyer"
                    results.append(post)
                    flyer_count += 1

            if phone_count >= _ENOUGH_PHONE_RESULTS:
                break

            # In deeper mode: if the first page was all known posts, continue
            # to the next page to find older unseen content.
            # If not in deeper mode or no more pages, stop.
            if not deeper or not next_max_id:
                break

            # All posts on this page were new — no need to go deeper, first
            # scrape already covers this range.
            if new_posts_on_page == len(posts):
                break

            log.info("@%s: deeper scrape — fetching page %d", handle, pages_fetched + 1)
            _time.sleep(2)  # Rate limit between pages

    finally:
        client.close()

    bio_found = any(r.get("source") in ("bio", "bio_link") for r in results)
    log.info(
        "@%s: %d posts scanned (%d pages) → %s in bio, %d with phone in caption, %d likely flyers",
        handle, total_scanned, pages_fetched,
        "YES" if bio_found else "no",
        phone_count, flyer_count,
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

    # Location word = last word (city/region name) — most distinguishing
    all_words = university_name.lower().split()
    location_word = all_words[-1] if all_words else ""

    # Common/generic words that many universities share
    generic = {"universitas", "institut", "sekolah", "tinggi", "negeri", "islam",
               "agama", "politeknik", "akademi", "ilmu", "teknologi", "stie", "stkip"}

    score = 0.0

    # Location match is critical — worth the most
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

    return max(min(score, 1.0), 0.0)


def search_ig_handle_via_ig(university_name: str) -> dict | None:
    """
    Search for university's Instagram handle directly via IG Web Search API.
    Tries multiple query variants (full name + abbreviated).
    Returns: {"handle": str, "url": str, "confidence": float} or None.
    Sync function — call from executor in async context.
    """
    if not cfg.IG_SESSION_ID:
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
    Sync function — call from executor in async context.
    """
    if not cfg.IG_SESSION_ID:
        return {"verified": False, "confidence_boost": 0, "bio": "", "reason": "no session"}

    client = _get_ig_web_client()
    try:
        profile = _ig_web_fetch_profile(client, handle)
    finally:
        client.close()

    if not profile:
        # Profile fetch failed (likely rate limited) — don't penalize,
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

    # Penalty: bio is empty → can't verify, inconclusive
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
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return base64.b64encode(resp.content).decode("utf-8")
        except Exception as e:
            log.error(f"Failed to download image {url}: {e}")
            return None


async def _vision_extract_named_contacts(image_b64: str) -> list[PhoneContact]:
    """Use OpenAI Vision to extract phone numbers with contact names from image."""
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
    except Exception as e:
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
        # Clear generic/label names — treat as no name
        if name and _is_generic_name(name):
            name = ""
        validated = validate_phone(phone)
        if validated:
            results.append(PhoneContact(phone=validated, name=name))

    return results


