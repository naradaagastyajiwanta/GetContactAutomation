"""
Instagram utilities: search handles, scrape posts, extract phone numbers via Vision API.

This module provides shared utility functions used by the pipeline agents in
orchestrator/agents/. It does not contain orchestration logic.

Scraping uses the Instagram **Web API** (same endpoints as the browser) with
a browser session cookie.  This avoids the Mobile/Private API IP-blacklist
issues that plague instagrapi / instaloader.
"""
import base64
import os
import re
import time as _time
from datetime import datetime, timezone
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


async def search_ig_from_website(university_name: str, website_url: str | None = None) -> dict | None:
    """
    Scrape a university website for instagram.com links.
    Gets the website URL from PDDIKTI first, then falls back to Google.
    Returns: {"handle": str, "url": str, "confidence": float} or None.
    """
    # Step 1: Get website URL (PDDIKTI → Google fallback)
    if not website_url:
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
                    if ".ac.id" in url or ".edu" in url or ".sch.id" in url:
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
        return None

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
        return None

    # The first IG handle on a university website is almost always the official one
    handle = unique[0]
    log.info("Website %s has IG link: @%s", website_url, handle)
    return {
        "handle": handle,
        "url": f"https://www.instagram.com/{handle}/",
        "confidence": 0.9,  # Very high — from their own website
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

    # Name appears in handle
    uni_words = uni_lower.split()
    matching_words = sum(1 for w in uni_words if len(w) > 3 and w in handle_lower)
    if matching_words > 0:
        score += 0.3 * min(matching_words / max(len(uni_words) - 1, 1), 1.0)

    # Name appears in title/snippet
    if uni_lower in title or uni_lower in snippet:
        score += 0.3
    elif any(w in title or w in snippet for w in uni_words if len(w) > 4):
        score += 0.15

    # Bio keywords in snippet
    if any(kw in snippet for kw in IG_BIO_KEYWORDS):
        score += 0.2

    # Handle doesn't look like a personal account
    if not any(x in handle_lower for x in ["personal", "fan", "meme", "info_"]):
        score += 0.1

    # Bonus for "official" or "resmi" in title
    if "official" in title or "resmi" in title:
        score += 0.15

    return min(score, 1.0)


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
_ENOUGH_PHONE_RESULTS = 3


def _ig_web_get_user_info(client: httpx.Client, handle: str) -> dict | None:
    """
    Single request to get user_id, bio, and external_url from IG search API.
    Returns {"user_id": int, "bio": str, "external_url": str} or None.
    """
    resp = client.get(
        "https://www.instagram.com/web/search/topsearch/",
        params={"query": handle, "context": "user"},
    )
    if resp.status_code != 200:
        log.warning("IG web search failed for @%s: HTTP %d", handle, resp.status_code)
        return None

    users = resp.json().get("users", [])
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

    return {
        "user_id": int(user_data["pk"]),
        "bio": user_data.get("biography", "") or "",
        "external_url": user_data.get("external_url", "") or "",
    }


def _scan_bio_link(url: str) -> list[str]:
    """
    Follow a link-in-bio URL and extract WhatsApp numbers.
    Handles Linktree, beacons, direct wa.me links, etc.
    Returns list of phone numbers found.
    """
    if not url:
        return []

    phones: list[str] = []
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            text = resp.text

            # Extract wa.me / WhatsApp API links
            for match in _WA_LINK_RE.findall(text):
                phones.append(match)

            # Also scan page text for phone numbers
            for match in _PHONE_QUICK_RE.findall(text):
                phones.append(match)

    except Exception as e:
        log.debug("Failed to scan bio link %s: %s", url, e)

    return list(set(phones))


def _ig_web_get_posts(client: httpx.Client, user_id: int, max_posts: int) -> list[dict]:
    """Fetch recent posts via Instagram Web API feed endpoint."""
    resp = client.get(
        f"https://www.instagram.com/api/v1/feed/user/{user_id}/",
        params={"count": max_posts},
    )
    if resp.status_code != 200:
        log.warning("IG web feed failed for user %d: HTTP %d", user_id, resp.status_code)
        return []

    items = resp.json().get("items", [])
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

    return posts


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


def scrape_ig_posts_sync(ig_handle: str, max_posts: int | None = None) -> list[dict]:
    """
    Smart scrape: find posts most likely to contain phone numbers.

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

    handle = ig_handle.lstrip("@")
    results: list[dict] = []
    total_scanned = 0
    phone_count = 0
    flyer_count = 0

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

        # Step 4: Fetch posts and classify (with early stop)
        posts = _ig_web_get_posts(client, user_id, max_posts)
        total_scanned = len(posts)

        for post in posts:
            cls = _classify_post(post)
            if cls == "has_phone":
                post["source"] = "caption_phone"
                results.append(post)
                phone_count += 1
                # Early stop: enough phone numbers found in captions
                if phone_count >= _ENOUGH_PHONE_RESULTS:
                    log.info("@%s: early stop — %d phone posts found", handle, phone_count)
                    break
            elif cls == "likely_flyer":
                post["source"] = "flyer"
                results.append(post)
                flyer_count += 1

    finally:
        client.close()

    bio_found = any(r.get("source") in ("bio", "bio_link") for r in results)
    log.info(
        "@%s: %d posts scanned → %s in bio, %d with phone in caption, %d likely flyers",
        handle, total_scanned,
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
        elif location_word in username.lower():
            score += 0.25

    # Non-generic word matches
    unique_words = [w for w in uni_words if w not in generic]
    if unique_words:
        matching = sum(1 for w in unique_words if w in full_name)
        score += 0.2 * min(matching / len(unique_words), 1.0)

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

    return min(score, 1.0)


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
            if resp.status_code != 200:
                continue

            for u in resp.json().get("users", [])[:10]:
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


# ---------------------------------------------------------------------------
# Phase 3b: Extract Phone Numbers from Images (OpenAI Vision)
# ---------------------------------------------------------------------------

async def extract_phone_from_image(image_url: str, caption: str = "") -> list[str]:
    """
    Extract Indonesian phone numbers from a flyer/poster image using GPT-4o Vision.
    Also extracts from caption text. Returns list of validated phone numbers.
    """
    phones: set[str] = set()

    # 1. Extract from caption text first (free, no API call needed)
    caption_phones = extract_phones_from_text(caption)
    for p in caption_phones:
        validated = validate_phone(p)
        if validated:
            phones.add(validated)

    # 2. Extract from image via Vision API
    try:
        image_b64 = await _download_image_as_base64(image_url)
        if image_b64:
            vision_phones = await _vision_extract_phones(image_b64)
            for p in vision_phones:
                validated = validate_phone(p)
                if validated:
                    phones.add(validated)
    except Exception as e:
        log.error(f"Vision extraction failed for {image_url}: {e}")

    return list(phones)


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


async def _vision_extract_phones(image_b64: str) -> list[str]:
    """Use OpenAI Vision to extract phone numbers from image."""
    client = _get_openai()

    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Kamu adalah asisten yang mengekstrak nomor telepon Indonesia dari gambar. "
                        "Cari semua nomor HP/WhatsApp yang tertera di gambar flyer/poster. "
                        "Format nomor Indonesia biasanya: 08xx-xxxx-xxxx atau +62-8xx-xxxx-xxxx. "
                        "Jawab HANYA dengan daftar nomor telepon, satu per baris. "
                        "Jika tidak ada nomor telepon, jawab: NONE"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Ekstrak semua nomor telepon/HP/WhatsApp dari gambar ini:",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                                "detail": "low",
                            },
                        },
                    ],
                },
            ],
            max_tokens=200,
            temperature=0,
        )
    except Exception as e:
        log.error(f"OpenAI Vision API error: {e}")
        return []

    text = response.choices[0].message.content or ""
    if "NONE" in text.upper():
        return []

    # Extract phone numbers from GPT response
    return extract_phones_from_text(text)


