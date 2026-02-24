"""
Scraping-Bot.io Instagram client — fallback provider (Tier 3).

Uses the Social Media API:
  POST http://api.scraping-bot.io/scrape/data-scraper
  GET  http://api.scraping-bot.io/scrape/data-scraper-response

Docs: https://www.scraping-bot.io/web-scraping-documentation/social-media-api

Available scrapers for Instagram:
  - ``instagramProfile`` → account param → returns profile + posts (with posts_number)
  - ``instagramPost``    → url param → returns single post data

This module is used as Fallback Tier 3 (last resort) when both direct IG
sessions and Apify fail.
"""

import base64
import time as _time

import httpx

from orchestrator.config import log, cfg

_API_BASE = "http://api.scraping-bot.io/scrape"
_SUBMIT_URL = f"{_API_BASE}/data-scraper"
_RESPONSE_URL = f"{_API_BASE}/data-scraper-response"

# Max time to wait for a scraping job to complete (seconds)
_MAX_WAIT = 90
_POLL_INTERVAL = 6  # Scraping-Bot docs recommend >= 5s between polls

# Runtime status tracking
_sb_status: dict = {"ok": True, "error": None}


def _update_status(ok: bool, error: str | None = None) -> None:
    _sb_status["ok"] = ok
    _sb_status["error"] = error if not ok else None


def get_status() -> dict:
    """Return ScrapingBot API health for the /health endpoint."""
    return {
        "ok": _sb_status["ok"],
        "error": _sb_status["error"],
        "configured": is_configured(),
    }


def _get_auth() -> tuple[str, str] | None:
    """Return (username, api_key) tuple, or None if not configured."""
    username = getattr(cfg, "SCRAPINGBOT_USERNAME", None) or None
    api_key = getattr(cfg, "SCRAPINGBOT_API_KEY", None) or None
    if not username or not api_key:
        return None
    return (username, api_key)


def _get_auth_header(auth: tuple[str, str]) -> str:
    """Build Basic auth header value."""
    creds = f"{auth[0]}:{auth[1]}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


def is_configured() -> bool:
    """Return True if Scraping-Bot credentials are set."""
    return _get_auth() is not None


def _submit_and_poll(payload: dict, scraper: str) -> dict | list | None:
    """
    Submit a social media scraping job and poll until done.

    Returns parsed JSON result or None on failure.
    """
    auth = _get_auth()
    if not auth:
        log.warning("[ScrapingBot] No credentials configured — skipping")
        return None

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": _get_auth_header(auth),
    }

    try:
        with httpx.Client(timeout=30, headers=headers) as client:
            # Step 1: Submit scraping job
            resp = client.post(_SUBMIT_URL, json=payload)
            if resp.status_code != 200:
                if resp.status_code in (401, 402, 403):
                    _update_status(False, "quota_exceeded" if resp.status_code == 402 else "invalid_key")
                log.warning("[ScrapingBot] Submit failed: HTTP %d — %s", resp.status_code, resp.text[:300])
                return None
            _update_status(True)

            response_data = resp.json()
            response_id = response_data.get("responseId")
            if not response_id:
                # Might have returned an error
                error = response_data.get("error")
                if error:
                    log.warning("[ScrapingBot] API error: %s", error)
                return None

            log.info("[ScrapingBot] Job submitted (scraper=%s), responseId=%s", scraper, response_id)

            # Step 2: Poll for result
            deadline = _time.time() + _MAX_WAIT
            while _time.time() < deadline:
                _time.sleep(_POLL_INTERVAL)

                poll_resp = client.get(
                    _RESPONSE_URL,
                    params={"scraper": scraper, "responseId": response_id},
                )
                if poll_resp.status_code != 200:
                    log.debug("[ScrapingBot] Poll returned HTTP %d", poll_resp.status_code)
                    continue

                result = poll_resp.json()

                # Check for completion
                if result is None or (isinstance(result, dict) and result.get("status") == "pending"):
                    continue

                # Check for error
                if isinstance(result, dict) and result.get("error"):
                    log.warning("[ScrapingBot] Scraping error: %s", result["error"])
                    return None

                log.info("[ScrapingBot] Got result for %s (responseId=%s)", scraper, response_id)
                return result

            log.warning("[ScrapingBot] Timeout waiting for %s result", scraper)
            return None

    except httpx.TimeoutException:
        log.warning("[ScrapingBot] HTTP timeout for %s", scraper)
        return None
    except Exception as e:
        log.error("[ScrapingBot] Unexpected error: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scrapingbot_get_profile(handle: str, posts_number: int = 12) -> dict | None:
    """
    Get IG profile + recent posts via Scraping-Bot ``instagramProfile`` scraper.

    Returns:
    {
        "bio": str,
        "full_name": str,
        "external_url": str,
        "is_verified": bool,
        "followers": int,
        "posts": [{"post_url", "image_url", "caption", "timestamp"}, ...]
    }
    or None on failure.
    """
    handle = handle.lstrip("@")
    log.info("[ScrapingBot] Fetching profile @%s (posts_number=%d)", handle, posts_number)

    result = _submit_and_poll(
        {
            "scraper": "instagramProfile",
            "account": handle,
            "posts_number": str(posts_number),
        },
        scraper="instagramProfile",
    )

    if not result:
        return None

    # The response can be a list (wrapping the profile) or a dict
    profile_data = result[0] if isinstance(result, list) and result else result
    if not isinstance(profile_data, dict):
        log.warning("[ScrapingBot] Unexpected response format for instagramProfile")
        return None

    # Parse posts from the profile data
    raw_posts = profile_data.get("posts", []) or profile_data.get("latestPosts", []) or []
    posts = []
    for p in raw_posts:
        post_url = p.get("url", "") or p.get("postUrl", "")
        image_url = p.get("displayUrl", "") or p.get("imageUrl", "") or p.get("image", "")
        caption = p.get("caption", "") or p.get("text", "") or ""
        timestamp = p.get("timestamp", "") or p.get("date", "")

        if post_url or caption:
            posts.append({
                "post_url": post_url,
                "image_url": image_url,
                "caption": caption,
                "timestamp": timestamp if timestamp else None,
            })

    return {
        "bio": profile_data.get("biography", "") or profile_data.get("bio", "") or "",
        "full_name": profile_data.get("fullName", "") or profile_data.get("name", "") or "",
        "external_url": profile_data.get("externalUrl", "") or profile_data.get("website", "") or "",
        "is_verified": profile_data.get("verified", False) or profile_data.get("isVerified", False),
        "followers": profile_data.get("followersCount", 0) or profile_data.get("followers", 0) or 0,
        "posts": posts,
    }


def scrapingbot_get_posts(handle: str, posts_number: int = 12) -> list[dict]:
    """
    Get recent posts for an IG handle via Scraping-Bot.

    Returns list of dicts matching scrape_ig_posts_sync output format:
    [{"post_url", "image_url", "caption", "timestamp"}, ...]
    """
    profile = scrapingbot_get_profile(handle, posts_number=posts_number)
    if not profile:
        return []
    return profile.get("posts", [])
