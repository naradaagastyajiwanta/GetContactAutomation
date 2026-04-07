"""
Scraping-Bot.io Instagram client — fallback provider (Tier 3).

Uses the Social Media API:
  POST http://api.scraping-bot.io/scrape/data-scraper
  GET  http://api.scraping-bot.io/scrape/data-scraper-response

Docs: https://www.scraping-bot.io/web-scraping-documentation/social-media-api

Available scrapers for Instagram:
  - ``instagramProfile`` → account param → returns profile + posts (with posts_number)
  - ``instagramPost``    → url param → returns single post data

Supports multiple accounts for free-tier rotation via SCRAPINGBOT_ACCOUNTS config.
When one account hits quota (HTTP 402), it is automatically skipped for 24 hours
and the next available account is tried.

Config (choose one):
  # Multi-account (recommended — maximizes free tier):
  SCRAPINGBOT_ACCOUNTS=[{"username":"u1","api_key":"k1"},{"username":"u2","api_key":"k2"}]

  # Single account (legacy, backward compatible):
  SCRAPINGBOT_USERNAME=user1
  SCRAPINGBOT_API_KEY=key1
"""

import base64
import json
import time as _time
from datetime import datetime

import httpx

from orchestrator.config import log, cfg

_API_BASE = "http://api.scraping-bot.io/scrape"
_SUBMIT_URL = f"{_API_BASE}/data-scraper"
_RESPONSE_URL = f"{_API_BASE}/data-scraper-response"

# Max time to wait for a scraping job to complete (seconds)
_MAX_WAIT = 90
_POLL_INTERVAL = 6  # Scraping-Bot docs recommend >= 5s between polls

_QUOTA_COOLDOWN_SECONDS = 24 * 3600  # 24 hours


# ---------------------------------------------------------------------------
# Internal exception
# ---------------------------------------------------------------------------

class _QuotaExceededError(Exception):
    """Raised when ScrapingBot returns HTTP 402 (quota exhausted)."""
    pass


# ---------------------------------------------------------------------------
# Account & Pool
# ---------------------------------------------------------------------------

class _SBAccount:
    """Holds credentials + runtime status for one ScrapingBot account."""

    def __init__(self, username: str, api_key: str):
        self.username = username
        self.api_key = api_key
        self.quota_exceeded_until: float = 0.0  # epoch; 0 = available
        self.failures: int = 0
        self.requests_served: int = 0

    def is_available(self) -> bool:
        return _time.time() >= self.quota_exceeded_until

    def mark_quota_exceeded(self) -> None:
        """Put account on 24-hour cooldown after HTTP 402."""
        self.quota_exceeded_until = _time.time() + _QUOTA_COOLDOWN_SECONDS
        log.warning(
            "[SBPool] @%s quota exceeded — cooldown until %s",
            self.username,
            datetime.fromtimestamp(self.quota_exceeded_until).strftime("%H:%M %d/%m"),
        )

    def mark_failed(self) -> None:
        self.failures += 1

    def mark_success(self) -> None:
        self.requests_served += 1
        self.failures = 0

    def auth_header(self) -> str:
        creds = f"{self.username}:{self.api_key}"
        return "Basic " + base64.b64encode(creds.encode()).decode()


class _SBPool:
    """Round-robin ScrapingBot account pool with quota-exceeded detection."""

    def __init__(self, accounts: list[_SBAccount]):
        self._accounts = accounts
        self._rr_index = 0

    def is_configured(self) -> bool:
        return bool(self._accounts)

    def has_available(self) -> bool:
        return any(a.is_available() for a in self._accounts)

    def get_next(self) -> _SBAccount | None:
        """Return next available account (round-robin, skip cooling down)."""
        available = [a for a in self._accounts if a.is_available()]
        if not available:
            return None
        account = available[self._rr_index % len(available)]
        self._rr_index += 1
        return account

    def stats(self) -> list[dict]:
        return [
            {
                "username": a.username,
                "available": a.is_available(),
                "quota_exceeded_until": (
                    datetime.fromtimestamp(a.quota_exceeded_until).isoformat()
                    if a.quota_exceeded_until > 0 else None
                ),
                "requests_served": a.requests_served,
                "failures": a.failures,
            }
            for a in self._accounts
        ]


# ---------------------------------------------------------------------------
# Pool singleton
# ---------------------------------------------------------------------------

_pool: _SBPool | None = None


def reset_pool() -> None:
    """Reset pool singleton — call after SCRAPINGBOT_ACCOUNTS config changes."""
    global _pool
    _pool = None
    log.info("[SBPool] Pool reset — will re-initialize on next request")


def _get_pool() -> _SBPool | None:
    """Get singleton pool, lazily initialized from config."""
    global _pool
    if _pool is not None:
        return _pool

    # Priority 1: SCRAPINGBOT_ACCOUNTS (JSON array of {username, api_key})
    raw = cfg.get("SCRAPINGBOT_ACCOUNTS", "") if hasattr(cfg, "get") else ""
    if not raw:
        raw = getattr(cfg, "SCRAPINGBOT_ACCOUNTS", "") or ""

    if raw:
        try:
            data = json.loads(raw)
            accounts = [
                _SBAccount(a["username"], a["api_key"])
                for a in data
                if a.get("username") and a.get("api_key")
            ]
        except Exception as e:
            log.error("[SBPool] Failed to parse SCRAPINGBOT_ACCOUNTS: %s", e)
            accounts = []
    else:
        # Fallback: legacy single-account config
        username = getattr(cfg, "SCRAPINGBOT_USERNAME", "") or ""
        api_key = getattr(cfg, "SCRAPINGBOT_API_KEY", "") or ""
        accounts = [_SBAccount(username, api_key)] if username and api_key else []

    if not accounts:
        return None

    _pool = _SBPool(accounts)
    log.info("[SBPool] Initialized with %d ScrapingBot account(s)", len(accounts))
    return _pool


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Return True if at least one ScrapingBot account is configured."""
    pool = _get_pool()
    return bool(pool and pool.is_configured())


def get_status() -> dict:
    """Return ScrapingBot pool health for the /health endpoint."""
    pool = _get_pool()
    if not pool:
        return {"configured": False, "total_accounts": 0, "available_accounts": 0, "accounts": []}
    stats = pool.stats()
    available = sum(1 for a in stats if a["available"])
    return {
        "configured": pool.is_configured(),
        "total_accounts": len(stats),
        "available_accounts": available,
        "accounts": stats,
    }


# ---------------------------------------------------------------------------
# Internal HTTP logic
# ---------------------------------------------------------------------------

def _submit_and_poll(account: _SBAccount, payload: dict, scraper: str) -> dict | list | None:
    """
    Submit a social media scraping job and poll until done.

    Raises:
        _QuotaExceededError: if HTTP 402 received (quota exhausted for this account).
    Returns:
        Parsed JSON result or None on failure.
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": account.auth_header(),
    }

    try:
        with httpx.Client(timeout=30, headers=headers) as client:
            # Step 1: Submit scraping job
            resp = client.post(_SUBMIT_URL, json=payload)
            if resp.status_code != 200:
                if resp.status_code == 402:
                    raise _QuotaExceededError(f"@{account.username} quota exceeded (HTTP 402)")
                if resp.status_code in (401, 403):
                    log.warning(
                        "[SBPool] @%s invalid credentials (HTTP %d)",
                        account.username, resp.status_code,
                    )
                    account.mark_failed()
                    return None
                log.warning(
                    "[ScrapingBot] Submit failed: HTTP %d — %s",
                    resp.status_code, resp.text[:300],
                )
                return None

            response_data = resp.json()
            response_id = response_data.get("responseId")
            if not response_id:
                error = response_data.get("error")
                if error:
                    log.warning("[ScrapingBot] API error: %s", error)
                return None

            log.info(
                "[ScrapingBot] Job submitted (scraper=%s, acct=%s), responseId=%s",
                scraper, account.username, response_id,
            )

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

                if result is None or (isinstance(result, dict) and result.get("status") == "pending"):
                    continue

                if isinstance(result, dict) and result.get("error"):
                    log.warning("[ScrapingBot] Scraping error: %s", result["error"])
                    return None

                log.info(
                    "[ScrapingBot] Got result for %s (acct=%s, responseId=%s)",
                    scraper, account.username, response_id,
                )
                return result

            log.warning("[ScrapingBot] Timeout waiting for %s result (acct=%s)", scraper, account.username)
            return None

    except _QuotaExceededError:
        raise  # propagate to caller for pool rotation
    except httpx.TimeoutException:
        log.warning("[ScrapingBot] HTTP timeout for %s (acct=%s)", scraper, account.username)
        return None
    except Exception as e:
        log.error("[ScrapingBot] Unexpected error (acct=%s): %s", account.username, e)
        return None


def _parse_profile_result(result: dict | list, handle: str) -> dict | None:
    """Parse raw ScrapingBot instagramProfile response into our standard format."""
    profile_data = result[0] if isinstance(result, list) and result else result
    if not isinstance(profile_data, dict):
        log.warning("[ScrapingBot] Unexpected response format for @%s", handle)
        return None

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrapingbot_get_profile(handle: str, posts_number: int = 12) -> dict | None:
    """
    Get IG profile + recent posts via Scraping-Bot ``instagramProfile`` scraper.

    Automatically rotates through all configured accounts if one hits quota (402).

    Returns:
    {
        "bio": str, "full_name": str, "external_url": str,
        "is_verified": bool, "followers": int,
        "posts": [{"post_url", "image_url", "caption", "timestamp"}, ...]
    }
    or None on failure / all accounts exhausted.
    """
    pool = _get_pool()
    if not pool or not pool.is_configured():
        return None

    handle = handle.lstrip("@")
    payload = {
        "scraper": "instagramProfile",
        "account": handle,
        "posts_number": str(posts_number),
    }

    max_attempts = len(pool._accounts)
    for _ in range(max_attempts):
        account = pool.get_next()
        if account is None:
            log.warning("[SBPool] All ScrapingBot accounts quota exceeded for @%s", handle)
            return None

        log.info("[ScrapingBot] Fetching profile @%s via @%s (posts=%d)", handle, account.username, posts_number)
        try:
            result = _submit_and_poll(account, payload, scraper="instagramProfile")
            if result is not None:
                profile = _parse_profile_result(result, handle)
                if profile is not None:
                    account.mark_success()
                    return profile
        except _QuotaExceededError:
            account.mark_quota_exceeded()
            continue  # try next account
        except Exception as e:
            log.warning("[SBPool] @%s (acct %s) unexpected error: %s", handle, account.username, e)
            account.mark_failed()

    return None


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
