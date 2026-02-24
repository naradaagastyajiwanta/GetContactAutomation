"""
Apify Instagram Scraper client — fallback provider for IG data.

Uses the ``apify/instagram-scraper`` actor via Apify REST API v2.
Docs: https://docs.apify.com/api/v2

This module is used as Fallback Tier 2 when direct IG session cookies fail.
"""

import time as _time
from typing import Any

import httpx

from orchestrator.config import log, cfg

_APIFY_BASE = "https://api.apify.com/v2"
_ACTOR_ID = "apify~instagram-scraper"  # official Apify Instagram Scraper

# Timeout for synchronous actor runs (seconds)
_RUN_TIMEOUT = 120
_POLL_INTERVAL = 5

# Runtime status tracking
_apify_status: dict = {"ok": True, "error": None}


def _update_status(ok: bool, error: str | None = None) -> None:
    _apify_status["ok"] = ok
    _apify_status["error"] = error if not ok else None


def get_status() -> dict:
    """Return Apify API key health for the /health endpoint."""
    return {
        "ok": _apify_status["ok"],
        "error": _apify_status["error"],
        "configured": is_configured(),
    }


def _get_token() -> str | None:
    """Return the current Apify API token, or None if not configured."""
    return getattr(cfg, "APIFY_API_KEY", None) or None


def is_configured() -> bool:
    """Return True if the Apify API key is set."""
    return bool(_get_token())


def _run_actor_sync(input_data: dict, timeout: int = _RUN_TIMEOUT) -> list[dict] | None:
    """
    Run the Instagram Scraper actor synchronously and return dataset items.

    Uses the ``waitForFinish`` query parameter for synchronous execution.
    Falls back to polling if the run doesn't finish in time.
    """
    token = _get_token()
    if not token:
        log.warning("[Apify] No API key configured — skipping")
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=timeout + 30, headers=headers) as client:
            # Start actor run with waitForFinish
            resp = client.post(
                f"{_APIFY_BASE}/acts/{_ACTOR_ID}/runs",
                params={"waitForFinish": timeout},
                json=input_data,
            )
            if resp.status_code not in (200, 201):
                if resp.status_code in (401, 402, 403):
                    _update_status(False, "quota_exceeded" if resp.status_code == 402 else "invalid_key")
                log.warning("[Apify] Failed to start actor: HTTP %d — %s", resp.status_code, resp.text[:300])
                return None

            _update_status(True)
            run_data = resp.json().get("data", {})
            run_id = run_data.get("id")
            status = run_data.get("status")

            if not run_id:
                log.warning("[Apify] No run ID returned")
                return None

            # If not finished yet, poll
            if status not in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                log.info("[Apify] Run %s still running, polling...", run_id)
                deadline = _time.time() + timeout
                while _time.time() < deadline:
                    _time.sleep(_POLL_INTERVAL)
                    poll_resp = client.get(f"{_APIFY_BASE}/actor-runs/{run_id}")
                    if poll_resp.status_code == 200:
                        status = poll_resp.json().get("data", {}).get("status")
                        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                            break

            if status != "SUCCEEDED":
                log.warning("[Apify] Run %s finished with status: %s", run_id, status)
                return None

            # Fetch dataset items
            dataset_id = run_data.get("defaultDatasetId")
            if not dataset_id:
                log.warning("[Apify] No dataset ID in run response")
                return None

            items_resp = client.get(
                f"{_APIFY_BASE}/datasets/{dataset_id}/items",
                params={"format": "json"},
            )
            if items_resp.status_code != 200:
                log.warning("[Apify] Failed to fetch dataset items: HTTP %d", items_resp.status_code)
                return None

            items = items_resp.json()
            log.info("[Apify] Got %d items from run %s", len(items), run_id)
            return items

    except httpx.TimeoutException:
        log.warning("[Apify] Request timed out after %ds", timeout)
        return None
    except Exception as e:
        log.error("[Apify] Unexpected error: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public API — matches the data shapes expected by instagram.py fallback
# ---------------------------------------------------------------------------


def apify_get_profile(handle: str) -> dict | None:
    """
    Get IG profile info via Apify.

    Returns: {"user_id": int|None, "bio": str, "external_url": str,
              "full_name": str, "is_verified": bool, "followers": int}
    or None on failure.
    """
    handle = handle.lstrip("@")
    log.info("[Apify] Fetching profile for @%s", handle)

    items = _run_actor_sync({
        "directUrls": [f"https://www.instagram.com/{handle}/"],
        "resultsType": "details",
        "resultsLimit": 1,
    })

    if not items:
        return None

    item = items[0]
    return {
        "user_id": item.get("id"),
        "bio": item.get("biography", "") or "",
        "external_url": item.get("externalUrl", "") or "",
        "full_name": item.get("fullName", "") or "",
        "is_verified": item.get("verified", False),
        "followers": item.get("followersCount", 0),
    }


def apify_get_posts(handle: str, max_posts: int = 20) -> list[dict]:
    """
    Get recent posts for an IG handle via Apify.

    Returns list of dicts with keys matching scrape_ig_posts_sync output:
    [{"post_url", "image_url", "caption", "timestamp"}, ...]
    """
    handle = handle.lstrip("@")
    log.info("[Apify] Fetching posts for @%s (max %d)", handle, max_posts)

    items = _run_actor_sync({
        "directUrls": [f"https://www.instagram.com/{handle}/"],
        "resultsType": "posts",
        "resultsLimit": max_posts,
    })

    if not items:
        return []

    posts = []
    for item in items:
        post_url = item.get("url", "")
        image_url = ""
        # Apify returns images in displayUrl or imageUrl
        if item.get("displayUrl"):
            image_url = item["displayUrl"]
        elif item.get("images") and len(item["images"]) > 0:
            image_url = item["images"][0]

        caption = item.get("caption", "") or ""
        timestamp = item.get("timestamp")

        if post_url:
            posts.append({
                "post_url": post_url,
                "image_url": image_url,
                "caption": caption,
                "timestamp": timestamp,
            })

    log.info("[Apify] Got %d posts for @%s", len(posts), handle)
    return posts


def apify_search_profile(query: str, limit: int = 5) -> list[dict]:
    """
    Search for IG profiles by keyword via Apify.

    Returns list of dicts:
    [{"username": str, "full_name": str, "is_verified": bool, "bio": str, "pk": int|None}, ...]
    """
    log.info("[Apify] Searching profiles for '%s'", query)

    items = _run_actor_sync({
        "search": query,
        "searchType": "user",
        "searchLimit": limit,
        "resultsLimit": limit,
    })

    if not items:
        return []

    results = []
    for item in items:
        results.append({
            "username": item.get("username", ""),
            "full_name": item.get("fullName", "") or "",
            "is_verified": item.get("verified", False),
            "bio": item.get("biography", "") or "",
            "pk": item.get("id"),
        })

    log.info("[Apify] Found %d profiles for '%s'", len(results), query)
    return results
