"""
Playwright Stealth Instagram Scraper — Tier 0 (Primary, free).

Uses a real Chromium browser with stealth patches to scrape Instagram
without triggering anti-bot detection. Unlike direct API calls with
session cookies (Tier 1), this approach:

  - Renders pages in a real browser → IG sees legitimate traffic
  - Uses playwright-stealth to defeat fingerprinting
  - Mimics human behavior (random delays, scrolling, viewport)
  - Maintains persistent login sessions across runs

Capabilities:
  - search_profile(query)     → search IG users
  - get_profile(handle)       → bio, followers, external_url
  - get_posts(handle, count)  → recent posts with captions + images
  - get_following(handle, max) → following list

All functions are SYNC (call from executor in async context).
"""

from __future__ import annotations

import asyncio
import base64 as _b64
import html as _html
import json
import os
import random
import re
import sys
import time as _time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from orchestrator.config import log, cfg

# ---------------------------------------------------------------------------
# Constants & Config
# ---------------------------------------------------------------------------

# Session persistence directory
_SESSION_DIR = Path("data/pw_sessions")

# User-agent pool (modern Chrome on Windows/Mac)
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

# Viewport sizes (common desktop resolutions)
_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
]

# Phone regex for extracting numbers from page content
_PHONE_RE = re.compile(r'(?:\+62|62|0)[\s\-.]?8\d[\s\-.]?\d{3,4}[\s\-.]?\d{3,5}')
_WA_LINK_RE = re.compile(r'(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\+?62\d{8,13})')

# Runtime status tracking
_pw_status: dict = {"ok": True, "error": None, "profiles_today": 0, "last_reset_date": ""}

# Track daily usage
def _check_daily_reset() -> None:
    """Reset daily counter if date changed."""
    today = datetime.now().strftime("%Y-%m-%d")
    if _pw_status["last_reset_date"] != today:
        _pw_status["profiles_today"] = 0
        _pw_status["last_reset_date"] = today
        _account_pool.reset_daily()


def get_status() -> dict:
    """Return Playwright scraper health for /health endpoint."""
    _check_daily_reset()
    try:
        from playwright.sync_api import sync_playwright
        installed = True
    except ImportError:
        installed = False

    daily_limit = getattr(cfg, "PW_DAILY_LIMIT", 100)
    pool_info = _account_pool.status()
    return {
        "ok": _pw_status["ok"] and installed,
        "error": "not installed" if not installed else _pw_status["error"],
        "installed": installed,
        "profiles_today": _pw_status["profiles_today"],
        "daily_limit": daily_limit,
        "accounts": pool_info,
    }


def is_available() -> bool:
    """Check if Playwright is installed and within daily limits."""
    _check_daily_reset()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    daily_limit = getattr(cfg, "PW_DAILY_LIMIT", 100)
    if _pw_status["profiles_today"] >= daily_limit:
        return False
    # At least one account must be healthy
    return _account_pool.has_healthy_account()


# ---------------------------------------------------------------------------
# Multi-account pool
# ---------------------------------------------------------------------------

import threading as _threading


class _IGAccount:
    """State for one IG account used by Playwright."""

    __slots__ = ("username", "password", "rate_limited_until",
                 "profiles_today", "last_error", "login_ok")

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.rate_limited_until: float = 0.0  # epoch when cooldown expires
        self.profiles_today: int = 0
        self.last_error: str | None = None
        self.login_ok: bool = True  # assume OK until proven otherwise

    @property
    def is_healthy(self) -> bool:
        if not self.login_ok:
            return False
        return _time.time() >= self.rate_limited_until

    @property
    def profile_dir(self) -> str:
        """Per-account persistent browser profile directory."""
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", self.username)
        return str(_SESSION_DIR / f"chromium_{safe}")

    def mark_rate_limited(self, cooldown_minutes: int = 30) -> None:
        self.rate_limited_until = _time.time() + cooldown_minutes * 60
        self.login_ok = True
        self.last_error = "rate_limited"
        log.warning(
            "[AccountPool] @%s rate-limited, cooldown %d min (until %s)",
            self.username, cooldown_minutes,
            datetime.fromtimestamp(self.rate_limited_until).strftime("%H:%M:%S"),
        )

    def mark_login_failed(self, error: str = "") -> None:
        self.login_ok = False
        self.last_error = error or "login_failed"
        log.warning("[AccountPool] @%s login failed: %s", self.username, error)


class _IGAccountPool:
    """
    Thread-safe pool of IG accounts for round-robin rotation.

    Reads account labels from the DB-backed IG accounts table.
    Password fields may still exist in the schema for legacy reasons,
    but runtime scraping no longer uses username/password login.
    """

    def __init__(self):
        self._lock = _threading.Lock()
        self._accounts: list[_IGAccount] = []
        self._index: int = 0
        self._loaded: bool = False

    def _ensure_loaded(self) -> None:
        """Lazy-load accounts from config (called under lock)."""
        if self._loaded:
            return
        self._loaded = True

        # Try DB first (sync bridge for the async call)
        try:
            import asyncio
            from orchestrator.db import get_ig_accounts as _db_get

            loop: asyncio.AbstractEventLoop | None = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            rows: list[dict] = []
            if loop and loop.is_running():
                # We're inside an async context – schedule a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    rows = pool.submit(asyncio.run, _db_get(enabled_only=True)).result(timeout=5)
            else:
                rows = asyncio.run(_db_get(enabled_only=True))

            for r in rows:
                u = r.get("username", "").strip()
                p = r.get("password", "").strip()
                if u:
                    self._accounts.append(_IGAccount(u, p))
            if self._accounts:
                log.info("[AccountPool] Loaded %d IG accounts from DB", len(self._accounts))
        except Exception as exc:
            log.debug("[AccountPool] Could not load from DB (%s)", exc)

        if not self._accounts:
            log.warning("[AccountPool] No IG browser profiles configured — import cookies via Settings dashboard")

    def next_account(self) -> _IGAccount | None:
        """
        Return the next healthy account (round-robin).
        Returns *None* if all accounts are rate-limited or broken.
        """
        with self._lock:
            self._ensure_loaded()
            if not self._accounts:
                return None

            n = len(self._accounts)
            for _ in range(n):
                acct = self._accounts[self._index % n]
                self._index += 1
                if acct.is_healthy:
                    return acct

            # All accounts exhausted -- find the one that recovers soonest
            soonest = min(self._accounts, key=lambda a: a.rate_limited_until)
            remaining = soonest.rate_limited_until - _time.time()
            if remaining > 0:
                log.warning(
                    "[AccountPool] All %d accounts rate-limited. "
                    "Soonest recovery: @%s in %.0f s",
                    n, soonest.username, remaining,
                )
            return None

    def has_healthy_account(self) -> bool:
        with self._lock:
            self._ensure_loaded()
            return any(a.is_healthy for a in self._accounts)

    def mark_rate_limited(self, username: str) -> None:
        cooldown = getattr(cfg, "PW_ACCOUNT_COOLDOWN_MINUTES", 30)
        with self._lock:
            self._ensure_loaded()
            for a in self._accounts:
                if a.username == username:
                    a.mark_rate_limited(cooldown)
                    return

    def mark_login_failed(self, username: str, error: str = "") -> None:
        with self._lock:
            self._ensure_loaded()
            for a in self._accounts:
                if a.username == username:
                    a.mark_login_failed(error)
                    return

    def mark_connected(self, username: str) -> None:
        with self._lock:
            self._ensure_loaded()
            for a in self._accounts:
                if a.username == username:
                    a.login_ok = True
                    a.last_error = None
                    a.rate_limited_until = 0.0
                    return

    def status(self) -> list[dict]:
        """Summary for /health endpoint."""
        with self._lock:
            self._ensure_loaded()
            now = _time.time()
            out = []
            for a in self._accounts:
                remaining = max(0, a.rate_limited_until - now)
                out.append({
                    "username": a.username,
                    "healthy": a.is_healthy,
                    "login_ok": a.login_ok,
                    "profiles_today": a.profiles_today,
                    "cooldown_remaining_s": int(remaining),
                    "last_error": a.last_error,
                })
            return out

    def load_from_db(self, rows: list[dict]) -> None:
        """
        Replace the account list with data from the DB.

        *rows* is a list of dicts with at least ``username`` and ``password``
        keys (as returned by ``get_ig_accounts(enabled_only=True)``).

        Preserves runtime state (rate-limit, login_ok) for accounts that
        already exist in the pool with the same username.
        """
        with self._lock:
            # Build lookup of existing state keyed by username
            existing: dict[str, _IGAccount] = {a.username: a for a in self._accounts}

            new_list: list[_IGAccount] = []
            for r in rows:
                u = r.get("username", "").strip()
                p = r.get("password", "").strip()
                if not u or not p:
                    continue
                if u in existing:
                    # Keep runtime state, but update password in case it changed
                    old = existing[u]
                    old.password = p
                    new_list.append(old)
                else:
                    new_list.append(_IGAccount(u, p))

            self._accounts = new_list
            self._loaded = True
            self._index = 0
            log.info(
                "[AccountPool] Reloaded from DB: %d enabled accounts", len(new_list)
            )

    def reset_daily(self) -> None:
        """Reset daily counters for all accounts."""
        with self._lock:
            self._ensure_loaded()
            for a in self._accounts:
                a.profiles_today = 0


# Module-level singleton
_account_pool = _IGAccountPool()


# ---------------------------------------------------------------------------
# Human-like delay helpers
# ---------------------------------------------------------------------------

def _human_delay(min_s: float | None = None, max_s: float | None = None) -> None:
    """Sleep for a random duration to mimic human behavior."""
    if min_s is None:
        min_s = getattr(cfg, "PW_MIN_DELAY_SECONDS", 8)
    if max_s is None:
        max_s = getattr(cfg, "PW_MAX_DELAY_SECONDS", 20)
    delay = random.uniform(min_s, max_s)
    _time.sleep(delay)


def _short_delay() -> None:
    """Short delay for between-action pauses."""
    _time.sleep(random.uniform(1.5, 4.0))


# ---------------------------------------------------------------------------
# Browser context manager
# ---------------------------------------------------------------------------

class _PlaywrightBrowser:
    """
    Manages a Playwright Chromium browser with stealth patches.
    Uses persistent context for session cookies (stay logged in).

    Optionally receives an ``_IGAccount`` to use a per-account
    profile directory and credentials.
    """

    def __init__(self, account: _IGAccount | None = None, *,
                 headless: bool | None = None,
                 on_screenshot: Callable[[str, str, str], Any] | None = None):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._original_policy = None
        self._account = account  # may be None (legacy single-account)
        self._headless_override = headless  # None = use cfg default
        self._on_screenshot = on_screenshot  # callback(step, base64_jpeg, message)

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        # Ensure session dir exists
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)

        # On Windows, Playwright's sync API needs ProactorEventLoop to
        # create subprocesses.  uvicorn's event loop may cause the default
        # policy to hand out a SelectorEventLoop (which raises
        # NotImplementedError on subprocess_exec).  Swap the policy
        # temporarily so Playwright gets a working loop.
        if sys.platform == "win32":
            self._original_policy = asyncio.get_event_loop_policy()
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        try:
            self._playwright = sync_playwright().start()
        except Exception:
            # Restore policy before re-raising so we don't leak state
            if self._original_policy is not None:
                asyncio.set_event_loop_policy(self._original_policy)
                self._original_policy = None
            raise

        if self._headless_override is not None:
            headless = self._headless_override
        else:
            headless = getattr(cfg, "PW_HEADLESS", True)
        user_agent = random.choice(_USER_AGENTS)
        viewport = random.choice(_VIEWPORTS)

        # Per-account profile directory or legacy default
        if self._account:
            profile_dir = self._account.profile_dir
        else:
            profile_dir = str(_SESSION_DIR / "chromium_profile")

        # Use persistent context (keeps cookies/localStorage between runs)
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            user_agent=user_agent,
            viewport=viewport,
            locale="id-ID",
            timezone_id="Asia/Jakarta",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        # Re-inject cookies from sidecar JSON (if a previous
        # pw_import_cookies() call saved them).  This is necessary
        # because add_cookies() in a prior persistent context may
        # not have been flushed to Chromium's on-disk cookie store.
        _cookie_file = Path(profile_dir) / "imported_cookies.json"
        if _cookie_file.exists():
            try:
                import json as _json
                _saved = _json.loads(_cookie_file.read_text(encoding="utf-8"))
                if _saved:
                    self._context.add_cookies(_saved)
                    log.info("[Playwright] Re-injected %d cookies from %s",
                             len(_saved), _cookie_file)
            except Exception as _exc:
                log.warning("[Playwright] Failed to reload saved cookies: %s", _exc)

        # Apply stealth patches
        self._page = self._context.new_page()
        try:
            # playwright-stealth v2.x API
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(self._page)
            log.debug("[Playwright] stealth patches applied (v2)")
        except ImportError:
            try:
                # playwright-stealth v1.x fallback
                from playwright_stealth import stealth_sync  # type: ignore
                stealth_sync(self._page)
                log.debug("[Playwright] stealth patches applied (v1)")
            except ImportError:
                log.warning("[Playwright] playwright-stealth not installed, running without stealth patches")
        except Exception as exc:
            log.warning(
                "[Playwright] stealth patches failed (%s: %s), continuing without stealth",
                type(exc).__name__, exc or "(no details)",
            )

        return self

    def __exit__(self, *args):
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        # Restore original event loop policy on Windows
        if self._original_policy is not None:
            asyncio.set_event_loop_policy(self._original_policy)
            self._original_policy = None

    @property
    def page(self):
        return self._page

    def _take_screenshot(self, step: str, message: str = "") -> None:
        """Capture a JPEG screenshot and push it to the callback (if set)."""
        if not self._on_screenshot:
            return
        try:
            raw = self._page.screenshot(type="jpeg", quality=50)
            b64 = _b64.b64encode(raw).decode("ascii")
            self._on_screenshot(step, b64, message)
        except Exception as exc:
            log.debug("[Playwright] Screenshot failed at step %s: %s", step, exc)

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        """Navigate to URL with retry on timeout."""
        try:
            self._page.goto(url, wait_until=wait_until, timeout=30000)
            _short_delay()
            return True
        except Exception as e:
            log.warning("[Playwright] Navigation failed for %s: %s", url, e)
            return False

    def ensure_logged_in(self) -> bool:
        """
        Check if we have a valid IG session from persistent/imported cookies.
        Runtime username/password login is intentionally disabled.

        Returns True only when the browser profile already contains a valid
        Instagram session cookie set.
        """
        # Quick check: navigate to IG home and see if we're redirected to login
        try:
            self._page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
            _time.sleep(3)
        except Exception as e:
            log.warning("[Playwright] Could not load IG home: %s", e)
            return False

        self._take_screenshot("open_ig", "Opened instagram.com")
        url = self._page.url.lower()
        if "/accounts/login" not in url:
            # Check if we actually have session cookies (ds_user_id)
            if self._verify_session_cookies():
                acct_label = self._account.username if self._account else "(legacy)"
                log.debug("[Playwright] Already logged in as %s (session from persistent context)", acct_label)
                return True
            # URL is not /accounts/login but no session cookies — IG may be showing
            # a login overlay or we're on a non-login page without auth.
            log.info("[Playwright] On %s but no session cookies — cookie import required", url)
        else:
            log.info("[Playwright] On login page with no valid cookies — cookie import required")

        acct_label = self._account.username if self._account else "(legacy)"
        self._take_screenshot("cookie_required", f"Instagram session missing for @{acct_label}. Import fresh cookies.")
        _pw_status["error"] = "cookie_required"
        if self._account:
            self._account.mark_login_failed("cookie_required")
        return False

    def wait_for_manual_login(self, timeout: int = 180) -> bool:
        """
        Open Instagram and wait for the **user** to log in manually in
        the visible browser window.  The system does NOT touch the
        keyboard — it only monitors cookies / URL.

        Takes periodic screenshots so the FE ``LiveBrowserView`` shows
        what is happening in real time.

        Args:
            timeout: Maximum seconds to wait for a successful login.

        Returns ``True`` once ``ds_user_id`` cookie is detected (login
        succeeded), or ``False`` on timeout / error.
        """
        acct_label = self._account.username if self._account else "(legacy)"

        # 1. Navigate to IG home
        try:
            self._page.goto(
                "https://www.instagram.com/",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            _time.sleep(3)
        except Exception as e:
            log.warning("[Playwright] Could not load IG home: %s", e)
            self._take_screenshot("nav_error", "Failed to open Instagram")
            return False

        self._take_screenshot("open_ig", "Opened instagram.com")

        # 2. Already logged in?
        url = self._page.url.lower()
        if "/accounts/login" not in url and self._verify_session_cookies():
            log.debug("[Playwright] @%s already logged in (persistent session)", acct_label)
            self._take_screenshot("already_logged_in", f"Already logged in as @{acct_label}")
            return True

        # 3. Ensure we're on the login page
        if "/accounts/login" not in self._page.url.lower():
            try:
                self._page.goto(
                    "https://www.instagram.com/accounts/login/",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                _time.sleep(2)
            except Exception:
                pass

        self._take_screenshot(
            "waiting_login",
            "Please log in manually in the browser window that appeared on your desktop.",
        )

        # 4. Poll until logged in or timeout
        interval = 3  # seconds between checks
        elapsed = 0
        screenshot_every = 6  # take a screenshot every N seconds
        last_shot = 0

        while elapsed < timeout:
            _time.sleep(interval)
            elapsed += interval

            url = self._page.url.lower()

            # Skip if still on login page
            if "/accounts/login" in url:
                if elapsed - last_shot >= screenshot_every:
                    remaining = timeout - elapsed
                    self._take_screenshot(
                        "waiting_login",
                        f"Waiting for you to log in... ({remaining}s remaining)",
                    )
                    last_shot = elapsed
                continue

            # Detect challenge / suspicious pages — still take screenshot
            if any(s in url for s in ("/challenge/", "/accounts/suspended",
                                       "/accounts/consent")):
                self._take_screenshot(
                    "challenge_detected",
                    "Challenge/verification page detected — please complete it in the browser.",
                )
                # Don't break — let the user complete the challenge
                continue

            # Check cookies
            if self._verify_session_cookies():
                # Handle "Not Now" / "Save Info" popups
                for _ in range(3):
                    try:
                        not_now = self._page.locator('text="Not Now"').first
                        if not_now.is_visible(timeout=2000):
                            not_now.click()
                            _time.sleep(1)
                    except Exception:
                        break

                log.info("[Playwright] @%s manual login detected! Session will persist.", acct_label)
                self._take_screenshot("login_success", f"Logged in as @{acct_label}!")
                return True

            # URL changed but no cookies yet — take a screenshot and keep waiting
            if elapsed - last_shot >= screenshot_every:
                self._take_screenshot("waiting_cookies", "Detecting login session...")
                last_shot = elapsed

        # 5. Timeout
        self._take_screenshot("timeout", f"Timed out after {timeout}s waiting for login.")
        log.warning("[Playwright] @%s manual login timed out after %ds", acct_label, timeout)
        return False

    def scroll_down(self, times: int = 2) -> None:
        """Scroll down the page to load lazy content."""
        for _ in range(times):
            self._page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
            _time.sleep(random.uniform(1.0, 2.5))

    def get_page_content(self) -> str:
        """Get current page HTML content."""
        return self._page.content()

    def check_login_wall(self) -> bool:
        """Check if IG is showing a login wall/popup."""
        content = self._page.content().lower()
        url = self._page.url.lower()
        if "/accounts/login" in url or "/accounts/suspended" in url:
            return True
        # Check for login modal
        if 'loginform' in content or '"loginPage"' in content:
            return True
        return False

    # ------------------------------------------------------------------
    # IG Internal API helpers
    # ------------------------------------------------------------------

    def _get_ig_cookies(self) -> dict[str, str]:
        """
        Return a dict of key IG cookies from the browser context.
        Useful for diagnosing login issues.
        """
        try:
            cookies = self._context.cookies("https://www.instagram.com")
            return {c["name"]: c["value"] for c in cookies
                    if c["name"] in ("ds_user_id", "csrftoken", "sessionid", "ig_did", "mid")}
        except Exception:
            return {}

    def _verify_session_cookies(self) -> bool:
        """
        After login, verify that critical IG session cookies are set.
        ``ds_user_id`` is the most reliable indicator of a valid session.
        """
        cookies = self._get_ig_cookies()
        has_ds = bool(cookies.get("ds_user_id"))
        has_csrf = bool(cookies.get("csrftoken"))
        log.debug("[Playwright] Cookies after login: %s", {k: v[:8] + '...' if len(v) > 8 else v for k, v in cookies.items()})
        if not has_ds:
            log.warning("[Playwright] ds_user_id cookie missing after login — session likely invalid")
        return has_ds and has_csrf

    def _force_relogin(self) -> bool:
        """
        Clear the current session and attempt a fresh login.
        Used when an API call returns 401 despite ``ensure_logged_in``
        having passed (stale cookies).
        """
        acct_label = self._account.username if self._account else "(legacy)"
        log.info("[Playwright] Forcing re-login for @%s ...", acct_label)

        # 1. Clear all cookies and storage — nukes stale session completely
        try:
            self._context.clear_cookies()
            log.debug("[Playwright] Cleared all cookies for @%s", acct_label)
        except Exception:
            pass
        try:
            self._page.evaluate("""() => {
                try { localStorage.clear(); } catch(e) {}
                try { sessionStorage.clear(); } catch(e) {}
            }""")
            log.debug("[Playwright] Cleared localStorage/sessionStorage")
        except Exception:
            pass

        _time.sleep(1)

        # 2. Navigate to login page directly (no logout needed since cookies cleared)
        try:
            self._page.goto("https://www.instagram.com/accounts/login/",
                            wait_until="domcontentloaded", timeout=15000)
            _time.sleep(3)
        except Exception as e:
            log.warning("[Playwright] Could not navigate to login page: %s", e)
            return False

        return self.ensure_logged_in()

    _IG_APP_ID = "936619743392459"

    def ig_api_fetch(self, api_url: str) -> dict | None:
        """
        Call an Instagram internal API endpoint using the browser session
        cookies via ``page.evaluate(fetch(...))``.  Returns parsed JSON or
        *None* on error.

        On HTTP error the returned dict contains ``__error: True`` and
        ``status: <int>``.  The caller can inspect this to detect 401s.

        This bypasses the need for React to render -- we get raw JSON
        directly from the same endpoints the IG frontend uses.
        Includes the same headers that IG's own frontend sends:
        ``X-IG-App-ID``, ``X-CSRFToken``, ``X-ASBD-ID``,
        ``X-IG-WWW-Claim``, and ``credentials: 'include'``.
        """
        escaped_url = api_url.replace("'", "\\'")
        result = self._page.evaluate(f"""async () => {{
            try {{
                const csrfMatch = document.cookie.match(/csrftoken=([^;]+)/);
                const csrfToken = csrfMatch ? csrfMatch[1] : '';
                const headers = {{
                    'X-IG-App-ID': '{self._IG_APP_ID}',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-ASBD-ID': '359341',
                    'X-IG-WWW-Claim': '0',
                }};
                if (csrfToken) headers['X-CSRFToken'] = csrfToken;
                const resp = await fetch('{escaped_url}', {{
                    method: 'GET',
                    credentials: 'include',
                    headers: headers,
                }});
                if (!resp.ok) return {{__error: true, status: resp.status}};
                return await resp.json();
            }} catch (e) {{
                return {{__error: true, message: e.message}};
            }}
        }}""")
        if result and result.get("__error"):
            log.warning("[Playwright] API fetch failed for %s: %s", api_url[:100], result)
            return result  # return the error dict so callers can inspect status
        return result

    def ig_get_web_profile(self, username: str, _retried: bool = False) -> dict | None:
        """
        Fetch full profile info + recent posts via IG's internal
        ``/api/v1/users/web_profile_info/`` endpoint.

        On 401, do not destroy the imported browser session immediately.
        Some accounts retain browser/profile access while IG rejects the
        internal API from the current runtime fingerprint. Callers can then
        fall back to HTML scraping in the same browser context.

        On 401 (session expired), attempts one re-login and retries.
        Returns the raw ``data.user`` dict on success, or *None*.
        """
        url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
        resp = self.ig_api_fetch(url)
        if resp is None:
            return None

        # Detect 401 — API auth may be limited even though the browser session
        # is still usable for page navigation / HTML scraping.
        if resp.get("__error") and resp.get("status") == 401 and not _retried:
            acct_label = self._account.username if self._account else "(legacy)"
            _pw_status["error"] = "profile_api_auth_limited"
            log.info(
                "[Playwright] @%s: web_profile_info returned 401 on @%s; "
                "keeping browser session and falling back to HTML profile scraping",
                username,
                acct_label,
            )
            return None

        if resp.get("__error"):
            return None

        try:
            return resp["data"]["user"]
        except (KeyError, TypeError):
            log.warning("[Playwright] Unexpected API shape for @%s: %s",
                        username, str(resp)[:200])
            return None

    def ig_get_user_feed(self, user_id: str | int, max_id: str = "", count: int = 12) -> dict | None:
        """
        Fetch a page of posts via IG's ``/api/v1/feed/user/`` REST endpoint
        using ``page.evaluate(fetch(...))``.  Includes the browser session's
        auth automatically via ``credentials: 'include'``.

        .. note::

           Instagram may rate-limit this endpoint (HTTP 401 with
           ``require_login``).  The caller should fall back to the
           initial 12 posts from ``web_profile_info`` when that happens.

        Args:
            user_id: IG numeric user ID.
            max_id:  Pagination cursor (``next_max_id`` from previous call).
                     Empty string or omitted for the first page.
            count:   Number of items to request (max ~12 per page).

        Returns a normalised dict with ``edges`` (list of ``{node: ...}``),
        ``page_info`` (``{has_next_page, end_cursor}``), and ``count``
        matching the GraphQL shape, or *None* on error.
        """
        import urllib.parse
        params: dict[str, str | int] = {"count": count}
        if max_id:
            params["max_id"] = max_id
        qs = urllib.parse.urlencode(params)
        url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/?{qs}"
        resp = self.ig_api_fetch(url)
        if resp is None or resp.get("__error"):
            return None
        try:
            items = resp.get("items") or []
            more = resp.get("more_available", False)
            next_max = resp.get("next_max_id", "")

            # Convert /api/v1/feed items to the same edge/node shape
            # used by web_profile_info so the caller doesn't need to care.
            edges = []
            for item in items:
                caption_text = ""
                cap = item.get("caption")
                if isinstance(cap, dict):
                    caption_text = cap.get("text", "")

                # Pick the best image
                image_url = ""
                image_versions = item.get("image_versions2") or {}
                candidates = image_versions.get("candidates") or []
                if candidates:
                    image_url = candidates[0].get("url", "")

                code = item.get("code", "")
                node = {
                    "shortcode": code,
                    "__typename": "GraphVideo" if item.get("media_type") == 2 else "GraphImage",
                    "is_video": item.get("media_type") == 2,
                    "display_url": image_url,
                    "taken_at_timestamp": item.get("taken_at"),
                    "edge_media_to_caption": {
                        "edges": [{"node": {"text": caption_text}}] if caption_text else []
                    },
                }
                edges.append({"node": node})

            return {
                "edges": edges,
                "page_info": {
                    "has_next_page": bool(more),
                    "end_cursor": str(next_max) if next_max else "",
                },
                "count": len(edges),
            }
        except Exception as e:
            log.debug("[Playwright] feed pagination parse error: %s", e)
            return None


# ---------------------------------------------------------------------------
# Login test helper (used by API endpoint)
# ---------------------------------------------------------------------------

# Shared event queues for live screenshot streaming.
# Key = username, value = deque of event dicts.
# The SSE endpoint in main.py reads from this while pw_test_login writes.
_test_login_events: dict[str, deque] = {}


def _emit_event(username: str, etype: str, **kwargs: Any) -> None:
    """Push an event to the live-stream queue for *username*."""
    q = _test_login_events.get(username)
    if q is not None:
        q.append({"type": etype, "ts": _time.time(), **kwargs})


# ---------------------------------------------------------------------------
# Headless login session management (new /login endpoints)
# ---------------------------------------------------------------------------

import uuid as _uuid

# Active login sessions — kept alive for challenge flow
_login_sessions: dict[str, dict[str, Any]] = {}
_LOGIN_SESSION_TIMEOUT = 300  # 5 min max


def _cleanup_login_session(session_id: str) -> None:
    """Close browser and remove session."""
    sess = _login_sessions.pop(session_id, None)
    if not sess:
        return
    browser = sess.get("browser")
    if browser:
        try:
            browser.__exit__(None, None, None)
        except Exception:
            pass
    log.debug("[LoginSession] Cleaned up session %s", session_id[:8])


def _cleanup_stale_sessions() -> None:
    """Remove sessions older than timeout."""
    now = _time.time()
    stale = [sid for sid, s in _login_sessions.items()
             if now - s.get("created_at", 0) > _LOGIN_SESSION_TIMEOUT]
    for sid in stale:
        log.info("[LoginSession] Cleaning stale session %s", sid[:8])
        _cleanup_login_session(sid)


def _headless_login_impl(username: str, password: str) -> dict:
    """Inner implementation – runs in a fresh thread."""
    _cleanup_stale_sessions()

    acct = _IGAccount(username, password)
    details: dict = {"cookies": {}, "final_url": "", "profile_nuked": False}

    _kill_orphan_chromes(acct.profile_dir)

    def _attempt(attempt: int = 1) -> dict:
        browser = _PlaywrightBrowser(acct, headless=True)
        try:
            browser.__enter__()
        except Exception as launch_err:
            err_name = type(launch_err).__name__
            if "TargetClosed" in err_name or "Target page, context or browser has been closed" in str(launch_err):
                if attempt == 1:
                    log.warning("[HeadlessLogin] Crash attempt %d, nuking profile", attempt)
                    _kill_orphan_chromes(acct.profile_dir)
                    _nuke_profile(acct)
                    details["profile_nuked"] = True
                    _time.sleep(2)
                    return _attempt(attempt=2)
                return {"status": "failed", "message": f"Browser keeps crashing for @{username}.",
                        "session_id": None, "screenshot": None, "details": details}
            raise

        try:
            browser.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
            _time.sleep(3)

            # Dismiss cookie consent banner if present (common in EU/some regions)
            for consent_sel in [
                'button:has-text("Allow all cookies")',
                'button:has-text("Allow essential and optional cookies")',
                'button:has-text("Accept")',
                'button:has-text("Accept All")',
                '[data-cookiebanner="accept_button"]',
            ]:
                try:
                    btn = browser.page.locator(consent_sel).first
                    if btn.is_visible(timeout=1000):
                        log.info("[HeadlessLogin] Dismissing cookie consent with: %s", consent_sel)
                        btn.click()
                        _time.sleep(1)
                        break
                except Exception:
                    pass

            url = browser.page.url.lower()

            # Already logged in from persistent profile?
            if "/accounts/login" not in url and "/challenge/" not in url:
                cookies = browser._get_ig_cookies()
                details["cookies"] = cookies
                details["final_url"] = browser.page.url
                if cookies.get("ds_user_id"):
                    api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
                    resp = browser.ig_api_fetch(api_url)
                    if resp and not resp.get("__error"):
                        browser.__exit__(None, None, None)
                        return {"status": "success", "message": f"Already logged in as @{username}. Session verified.",
                                "session_id": None, "screenshot": None, "details": details}

                # NOT logged in (no ds_user_id) but URL is NOT /accounts/login.
                # Modern IG may show a login overlay on the home page, or we
                # need to navigate explicitly to the login page.
                log.info("[HeadlessLogin] On %s but no ds_user_id — checking for login form or navigating to login page", url)

                # Check if login form is visible on current page (IG login modal/overlay)
                has_login_form = False
                try:
                    has_login_form = browser.page.locator('input[name="username"], input[name="email"]').first.is_visible(timeout=2000)
                except Exception:
                    pass

                if not has_login_form:
                    # Force navigate to the login page
                    log.info("[HeadlessLogin] No login form on homepage, navigating to /accounts/login/")
                    browser.page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=20000)
                    _time.sleep(3)

            # Now we should be on a page with a login form (either /accounts/login or overlay)
            # Check if login form is present, regardless of URL
            needs_login = False
            try:
                needs_login = browser.page.locator('input[name="username"], input[name="email"]').first.is_visible(timeout=5000)
            except Exception:
                pass

            if needs_login:
                log.info("[HeadlessLogin] Login form detected, filling credentials for @%s", username)
                try:
                    _short_delay()

                    uname_input = browser.page.locator('input[name="username"], input[name="email"]').first
                    pwd_input = browser.page.locator('input[name="password"], input[name="pass"]').first

                    # Method 1: Try fill() first (most reliable with React)
                    log.info("[HeadlessLogin] Filling username via fill()...")
                    uname_input.click()
                    _time.sleep(random.uniform(0.3, 0.5))
                    uname_input.fill(username)
                    _time.sleep(random.uniform(0.3, 0.5))

                    log.info("[HeadlessLogin] Filling password via fill()...")
                    pwd_input.click()
                    _time.sleep(random.uniform(0.3, 0.5))
                    pwd_input.fill(password)
                    _time.sleep(random.uniform(0.5, 1.0))

                    # Verify form values are actually set
                    filled_user = ""
                    filled_pwd_len = 0
                    try:
                        filled_user = uname_input.input_value()
                        filled_pwd_len = len(pwd_input.input_value())
                        log.info("[HeadlessLogin] Form values after fill(): username=%r, password_len=%d", filled_user, filled_pwd_len)
                    except Exception:
                        pass

                    # If fill() didn't work, try character-by-character typing
                    if not filled_user or filled_pwd_len == 0:
                        log.warning("[HeadlessLogin] fill() didn't set values, trying type() method...")
                        uname_input.click()
                        _time.sleep(0.3)
                        # Select all + delete to clear
                        browser.page.keyboard.press("Control+a")
                        browser.page.keyboard.press("Delete")
                        _time.sleep(0.2)
                        for ch in username:
                            uname_input.type(ch, delay=random.randint(40, 100))
                        _time.sleep(0.3)

                        pwd_input.click()
                        _time.sleep(0.3)
                        browser.page.keyboard.press("Control+a")
                        browser.page.keyboard.press("Delete")
                        _time.sleep(0.2)
                        for ch in password:
                            pwd_input.type(ch, delay=random.randint(40, 100))
                        _time.sleep(0.5)

                        # Re-verify
                        try:
                            filled_user = uname_input.input_value()
                            filled_pwd_len = len(pwd_input.input_value())
                            log.info("[HeadlessLogin] After type(): username=%r, password_len=%d", filled_user, filled_pwd_len)
                        except Exception:
                            pass

                    # Check submit button state
                    login_btn = browser.page.locator('button[type="submit"]').first
                    is_disabled = False
                    try:
                        is_disabled = login_btn.is_disabled()
                    except Exception:
                        pass
                    log.info("[HeadlessLogin] Submit button disabled=%s", is_disabled)

                    # Submit: try Enter key first (most reliable), then button click
                    log.info("[HeadlessLogin] Submitting login form...")
                    pwd_input.press("Enter")
                    _time.sleep(2)

                    # Wait for navigation or page change after login
                    try:
                        browser.page.wait_for_url(lambda u: "/accounts/login" not in u.lower(), timeout=12000)
                        log.info("[HeadlessLogin] URL changed after submit: %s", browser.page.url)
                    except Exception:
                        log.info("[HeadlessLogin] URL didn't change in 12s, still: %s", browser.page.url)
                    _time.sleep(3)

                    # "Not Now" popups
                    for _ in range(3):
                        try:
                            nn = browser.page.locator('text="Not Now"').first
                            if nn.is_visible(timeout=2000):
                                nn.click()
                                _time.sleep(2)
                        except Exception:
                            break
                except Exception as e:
                    browser.__exit__(None, None, None)
                    return {"status": "failed", "message": f"Could not fill login form: {e}",
                            "session_id": None, "screenshot": None, "details": details}

            # Evaluate result — retry cookie check a few times (IG sometimes sets them with delay)
            url = browser.page.url.lower()
            cookies_found = False
            for _retry in range(4):
                details["cookies"] = browser._get_ig_cookies()
                if details["cookies"].get("ds_user_id"):
                    cookies_found = True
                    log.info("[HeadlessLogin] ds_user_id found on retry %d", _retry)
                    break
                if _retry < 3:
                    log.info("[HeadlessLogin] No ds_user_id yet (attempt %d/4), waiting 3s...", _retry + 1)
                    _time.sleep(3)
                    # Re-read URL in case of redirect
                    url = browser.page.url.lower()
            details["final_url"] = browser.page.url

            # Capture body text for diagnosis (always, helps debugging)
            try:
                body_text = browser.page.locator("body").inner_text(timeout=3000)
                details["page_text"] = body_text[:2000]
                log.info("[HeadlessLogin] Page body (first 200): %s", body_text[:200].replace("\n", " | "))
            except Exception:
                pass

            # Check for suspicious login / unusual activity text on the page itself
            page_text_lower = details.get("page_text", "").lower()
            suspicious_keywords = ["suspicious", "unusual", "we detected", "confirm your identity",
                                   "verify your identity", "security code", "aktivitas mencurigakan",
                                   "konfirmasi identitas"]
            if any(kw in page_text_lower for kw in suspicious_keywords):
                log.warning("[HeadlessLogin] Suspicious login activity detected on page text!")
                screenshot_b64 = None
                try:
                    raw = browser.page.screenshot(type="jpeg", quality=60)
                    screenshot_b64 = _b64.b64encode(raw).decode("ascii")
                except Exception:
                    pass
                session_id = str(_uuid.uuid4())
                _login_sessions[session_id] = {
                    "browser": browser,
                    "account": acct,
                    "username": username,
                    "created_at": _time.time(),
                }
                return {
                    "status": "challenge",
                    "message": "Instagram detected suspicious login. Check the screenshot and verify your identity.",
                    "session_id": session_id,
                    "screenshot": screenshot_b64,
                    "details": details,
                }

            # --- CHALLENGE / VERIFICATION ---
            if "/challenge/" in url or "/accounts/suspended" in url or "/accounts/consent" in url:
                screenshot_b64 = None
                try:
                    raw = browser.page.screenshot(type="jpeg", quality=60)
                    screenshot_b64 = _b64.b64encode(raw).decode("ascii")
                except Exception:
                    pass

                session_id = str(_uuid.uuid4())
                _login_sessions[session_id] = {
                    "browser": browser,
                    "account": acct,
                    "username": username,
                    "created_at": _time.time(),
                }
                ctype = "suspended" if "/suspended" in url else "verification"
                return {
                    "status": "challenge",
                    "message": ("Instagram requires verification. Enter the code sent to your email/phone."
                                if ctype == "verification"
                                else "Account may be suspended. Check the screenshot."),
                    "session_id": session_id,
                    "screenshot": screenshot_b64,
                    "details": details,
                }

            # --- STILL LOGIN PAGE (wrong password?) ---
            # IG may show login form at homepage URL (not just /accounts/login)
            login_error_texts = ["informasi login", "incorrect", "wrong password",
                                 "doesn't match", "salah", "find your account"]
            has_login_error = any(kw in page_text_lower for kw in login_error_texts)
            has_login_form = False
            try:
                has_login_form = browser.page.locator('input[name="username"], input[name="email"]').first.is_visible(timeout=1000)
            except Exception:
                pass

            if "/accounts/login" in url or (has_login_error and has_login_form):
                error_msg = ""
                try:
                    err_el = browser.page.locator('[role="alert"], .eiCW-, #slfErrorAlert, p[data-testid="login-error-message"]')
                    if err_el.count() > 0:
                        error_msg = err_el.first.text_content(timeout=2000) or ""
                except Exception:
                    pass
                # Also try to grab any error-like text from the page
                if not error_msg:
                    try:
                        # Common IG error container selectors
                        for sel in ['[id*="error"]', '[class*="error"]', '[class*="Error"]', 'form p']:
                            el = browser.page.locator(sel)
                            if el.count() > 0 and el.first.is_visible(timeout=500):
                                txt = el.first.text_content(timeout=1000)
                                if txt and len(txt.strip()) > 5:
                                    error_msg = txt.strip()
                                    break
                    except Exception:
                        pass
                log.warning("[HeadlessLogin] Still on login page after submit. Error: %r", error_msg)
                # Try to grab page text for diagnosis
                try:
                    body_text = browser.page.locator("body").inner_text(timeout=3000)
                    # Truncate for logs
                    log.warning("[HeadlessLogin] Page body text (first 500): %s", body_text[:500])
                    details["page_text"] = body_text[:1000]
                except Exception as te:
                    log.warning("[HeadlessLogin] Could not get page text: %s", te)
                # Capture screenshot for diagnosis
                login_fail_screenshot = None
                try:
                    raw = browser.page.screenshot(type="jpeg", quality=60)
                    login_fail_screenshot = _b64.b64encode(raw).decode("ascii")
                except Exception:
                    pass
                browser.__exit__(None, None, None)

                # --- Detect datacenter / VPS IP blocking ---
                # Instagram returns "wrong password" or similar error even when
                # credentials are correct if the login comes from a datacenter IP. 
                # Detect this pattern so the frontend can guide the user to use
                # Session Sync instead.
                _ip_block_keywords = ["informasi login", "incorrect", "wrong password",
                                      "doesn't match", "salah"]
                _is_likely_ip_block = (
                    has_login_error
                    and any(kw in (error_msg or "").lower() for kw in _ip_block_keywords)
                    # URL stayed at homepage (not /accounts/login redirect) — hallmark of soft block
                    and "/accounts/login" not in url
                )
                # Also check if we're running inside Docker (strong signal for datacenter)
                _in_docker = Path("/.dockerenv").exists()
                if _is_likely_ip_block or (_in_docker and has_login_error):
                    log.warning("[HeadlessLogin] Likely datacenter IP block for @%s (docker=%s, url=%s)",
                                username, _in_docker, url)
                    return {
                        "status": "ip_blocked",
                        "message": (
                            f"Instagram blocked login for @{username} from this server's IP address. "
                            "This is normal for cloud/VPS servers. "
                            "Use Session Sync: login on your local PC, export the session, "
                            "then import it here."
                        ),
                        "session_id": None,
                        "screenshot": login_fail_screenshot,
                        "details": {**details, "reason": "datacenter_ip_block", "in_docker": _in_docker},
                    }

                return {"status": "failed",
                        "message": error_msg or f"Login failed for @{username}. Check username/password.",
                        "session_id": None, "screenshot": login_fail_screenshot, "details": details}

            # --- SUCCESS ---
            cookies = browser._get_ig_cookies()
            details["cookies"] = cookies
            if cookies.get("ds_user_id"):
                api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
                resp = browser.ig_api_fetch(api_url)
                browser.__exit__(None, None, None)
                if resp and not resp.get("__error"):
                    return {"status": "success", "message": f"Login successful for @{username}. Session verified.",
                            "session_id": None, "screenshot": None, "details": details}
                return {"status": "success",
                        "message": f"Logged in as @{username} (cookies present, API check skipped).",
                        "session_id": None, "screenshot": None, "details": details}

            # Take a diagnostic screenshot before closing browser
            diag_screenshot = None
            try:
                raw = browser.page.screenshot(type="jpeg", quality=60)
                diag_screenshot = _b64.b64encode(raw).decode("ascii")
            except Exception:
                pass
            final_url = browser.page.url
            browser.__exit__(None, None, None)
            return {"status": "failed",
                    "message": f"Login unclear for @{username}. No session cookies found. URL: {final_url}",
                    "session_id": None, "screenshot": diag_screenshot, "details": details}

        except Exception as e:
            try:
                browser.__exit__(None, None, None)
            except Exception:
                pass
            raise

    return _attempt(attempt=1)


# ---------------------------------------------------------------------------
# Session health verification (lightweight — no login attempt)
# ---------------------------------------------------------------------------

def _verify_session_impl(username: str, password: str) -> dict:
    """
    Lightweight session check: open persistent profile, read cookies,
    make one API call to confirm the session is still valid.

    Returns dict with:
      - status: 'connected' | 'disconnected' | 'banned' | 'rate_limited' | 'error'
      - reason: human-readable explanation
      - username_verified: IG username if connected
      - cookies: dict of key cookies found
    """
    acct = _IGAccount(username, password)

    # ------------------------------------------------------------------
    # Read sidecar cookies for diagnostics, but do not trust them blindly.
    # We still need a runtime verification because a stored session can be
    # degraded to profile-only access or rejected entirely by Instagram.
    # ------------------------------------------------------------------
    import json as _json
    cookie_file = Path(acct.profile_dir) / "imported_cookies.json"
    if cookie_file.exists():
        try:
            saved = _json.loads(cookie_file.read_text(encoding="utf-8"))
            saved_map = {c["name"]: c["value"] for c in saved
                         if c.get("name") in ("ds_user_id", "csrftoken", "sessionid", "ig_did", "mid")}
            if saved_map.get("ds_user_id") and saved_map.get("sessionid"):
                log.info("[VerifySession] Found imported_cookies.json for @%s "
                         "(ds_user_id=%s..., sessionid=%s...). Verifying live session.",
                         username,
                         saved_map["ds_user_id"][:6],
                         saved_map["sessionid"][:8])
        except Exception as exc:
            log.warning("[VerifySession] Failed to read imported_cookies.json for @%s: %s",
                        username, exc)

    # ------------------------------------------------------------------
    # Slow path: launch browser, navigate, check cookies + API
    # ------------------------------------------------------------------
    try:
        _kill_orphan_chromes(acct.profile_dir)
        browser = _PlaywrightBrowser(acct, headless=True)
        try:
            browser.__enter__()
        except Exception as e:
            return {"status": "error", "reason": f"browser_launch_failed: {e}",
                    "username_verified": None, "cookies": {}}

        try:
            # Check cookies BEFORE navigation — they may be cleared by IG
            # if the server IP differs from where the cookies were created.
            pre_nav_cookies = browser._get_ig_cookies()
            log.info("[VerifySession] Pre-navigation cookies for @%s: %s",
                     username, {k: v[:8] + '...' for k, v in pre_nav_cookies.items()})

            # Navigate to IG briefly to activate cookies
            try:
                browser.page.goto("https://www.instagram.com/",
                                  wait_until="domcontentloaded", timeout=15000)
                _time.sleep(2)
            except Exception as nav_exc:
                log.warning("[VerifySession] Navigation failed for @%s: %s. "
                            "Checking pre-nav cookies instead.", username, nav_exc)
                # If we had cookies before navigation blew up, report that the
                # session exists but could not be proven to support authenticated
                # endpoints from this runtime.
                if pre_nav_cookies.get("ds_user_id") and pre_nav_cookies.get("sessionid"):
                    return {"status": "auth_limited",
                            "reason": "cookies_present_navigation_failed",
                            "username_verified": username,
                            "cookies": pre_nav_cookies}
                return {"status": "error",
                        "reason": f"navigation_failed: {nav_exc}",
                        "username_verified": None, "cookies": pre_nav_cookies}

            # Check cookies after navigation
            cookies = browser._get_ig_cookies()
            log.info("[VerifySession] Post-navigation cookies for @%s: %s",
                     username, {k: v[:8] + '...' for k, v in cookies.items()})

            if not cookies.get("ds_user_id"):
                # Cookies disappeared after navigation — IG cleared them
                # If they existed before navigation, the import was fine but
                # IG rejected from this IP/fingerprint.
                if pre_nav_cookies.get("ds_user_id") and pre_nav_cookies.get("sessionid"):
                    log.warning("[VerifySession] Cookies existed pre-navigation but IG cleared them "
                                "post-navigation for @%s — likely IP/fingerprint mismatch.", username)
                    return {"status": "auth_limited",
                            "reason": "cookies_rejected_after_navigation",
                            "username_verified": username,
                            "cookies": pre_nav_cookies}

                return {"status": "disconnected", "reason": "no_session_cookie",
                        "username_verified": None, "cookies": cookies}

            if not cookies.get("sessionid"):
                return {"status": "auth_limited", "reason": "missing_sessionid",
                        "username_verified": username, "cookies": cookies}

            # Make lightweight API call to verify session is still valid
            # Try current_user first; if it fails (e.g. 400 on datacenter IPs),
            # fallback to web_profile_info which is more reliable.
            api_url = "https://www.instagram.com/api/v1/accounts/current_user/?edit=true"
            resp = browser.ig_api_fetch(api_url)

            if resp is None or resp.get("__error"):
                status_code = resp.get("status", 0) if resp else 0
                # Hard failures — session is definitely bad
                if status_code == 401:
                    return {"status": "disconnected", "reason": "session_expired",
                            "username_verified": None, "cookies": cookies}
                elif status_code == 403:
                    return {"status": "banned", "reason": "forbidden_403",
                            "username_verified": None, "cookies": cookies}
                elif status_code == 429:
                    return {"status": "rate_limited", "reason": "too_many_requests",
                            "username_verified": None, "cookies": cookies}

                # Soft failure (400 etc) — try fallback endpoint
                log.info("[VerifySession] current_user returned %s, trying fallback...", status_code)
                fallback_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
                fb_resp = browser.ig_api_fetch(fallback_url)
                if fb_resp and not fb_resp.get("__error"):
                    fb_user = fb_resp.get("data", {}).get("user", {})
                    verified_username = fb_user.get("username", username)
                    verified_user_id = fb_user.get("id")

                    # Some server runtimes cannot use ``current_user`` reliably,
                    # but the authenticated following API still works. Probe it
                    # before downgrading the session to profile-only access.
                    if verified_user_id:
                        following_probe = browser.ig_api_fetch(
                            f"https://www.instagram.com/api/v1/friendships/{verified_user_id}/following/?count=1"
                        )
                        if following_probe and not following_probe.get("__error"):
                            log.info(
                                "[VerifySession] current_user soft-failed for @%s, but following API succeeded; treating session as connected.",
                                username,
                            )
                            return {"status": "connected", "reason": None,
                                    "username_verified": verified_username, "cookies": cookies}

                    return {"status": "auth_limited", "reason": "profile_only_access",
                            "username_verified": verified_username, "cookies": cookies}

                # Also check page content — if we see feed content, session is valid
                try:
                    has_login_form = browser.page.locator(
                        'input[name="username"], input[name="email"]'
                    ).first.is_visible(timeout=2000)
                except Exception:
                    has_login_form = False

                if not has_login_form and cookies.get("ds_user_id"):
                    return {"status": "auth_limited", "reason": "cookies_valid_api_limited",
                            "username_verified": username, "cookies": cookies}

                # Truly failed
                if resp is None:
                    return {"status": "disconnected", "reason": "api_call_failed",
                            "username_verified": None, "cookies": cookies}
                return {"status": "error", "reason": f"http_{status_code}",
                        "username_verified": None, "cookies": cookies}

            # Session is valid
            user_data = resp.get("user", {})
            verified_username = user_data.get("username", username)
            return {"status": "connected", "reason": None,
                    "username_verified": verified_username, "cookies": cookies}

        finally:
            try:
                browser.__exit__(None, None, None)
            except Exception:
                pass

    except Exception as e:
        log.error("[VerifySession] Unexpected error for @%s: %s", username, e)
        return {"status": "error", "reason": str(e),
                "username_verified": None, "cookies": {}}


def pw_verify_session(username: str, password: str) -> dict:
    """
    Thread-safe session verification.
    Runs in a fresh thread to avoid asyncio loop conflicts.
    """
    result_holder: list[dict | None] = [None]
    error_holder: list[BaseException | None] = [None]

    def _worker() -> None:
        try:
            result_holder[0] = _verify_session_impl(username, password)
        except BaseException as exc:
            error_holder[0] = exc

    t = _threading.Thread(target=_worker, daemon=True,
                          name=f"pw-verify-{username}")
    t.start()
    t.join(timeout=45)  # shorter timeout than login

    if error_holder[0] is not None:
        return {"status": "error", "reason": str(error_holder[0]),
                "username_verified": None, "cookies": {}}
    if result_holder[0] is None:
        return {"status": "error", "reason": "verification_timeout",
                "username_verified": None, "cookies": {}}
    return result_holder[0]


# Cache for health results (avoid hammering IG)
_health_cache: dict[str, Any] = {"results": [], "checked_at": 0.0}
_HEALTH_CACHE_TTL = 120  # 2 minutes


def pw_verify_all_sessions() -> list[dict]:
    """
    Verify all enabled accounts' sessions. Returns list of per-account results.
    Uses a cache to avoid repeated checks.
    """
    now = _time.time()
    if now - _health_cache["checked_at"] < _HEALTH_CACHE_TTL and _health_cache["results"]:
        return _health_cache["results"]

    with _account_pool._lock:
        _account_pool._ensure_loaded()
        accounts = [(a.username, a.password) for a in _account_pool._accounts]

    if not accounts:
        return []

    results = []
    for username, password in accounts:
        log.info("[HealthCheck] Verifying session for @%s ...", username)
        result = pw_verify_session(username, password)
        result["username"] = username
        results.append(result)

        # Update pool state based on result
        status = result.get("status")
        if status == "connected":
            _account_pool.mark_connected(username)
        elif status == "rate_limited":
            _account_pool.mark_rate_limited(username)
        elif status in ("disconnected", "banned", "auth_limited"):
            _account_pool.mark_login_failed(
                username, result.get("reason", status))

        log.info("[HealthCheck] @%s → %s (%s)", username, status,
                 result.get("reason") or "ok")

    _health_cache["results"] = results
    _health_cache["checked_at"] = now
    return results


def pw_invalidate_health_cache() -> None:
    """Force next health check to re-verify."""
    _health_cache["checked_at"] = 0.0


def pw_headless_login(username: str, password: str) -> dict:
    """
    Credential-based headless login is disabled.

    Returns dict with keys: status, message, session_id, screenshot, details
    """
    return {
        "status": "failed",
        "message": f"Credential login disabled for @{username}. Import Instagram cookies instead.",
        "session_id": None,
        "screenshot": None,
        "details": {"cookies": {}, "final_url": "", "profile_nuked": False},
    }


def _submit_challenge_impl(session_id: str, code: str) -> dict:
    """Inner implementation for challenge submission — runs in fresh thread."""
    sess = _login_sessions.get(session_id)
    if not sess:
        return {"status": "failed", "message": "Session expired or not found. Try logging in again.",
                "screenshot": None, "details": {}}

    browser = sess["browser"]
    username = sess["username"]
    details: dict = {"cookies": {}, "final_url": ""}

    try:
        page = browser.page

        # Find and fill the code input
        code_filled = False
        for selector in [
            'input[name="security_code"]',
            'input[name="verificationCode"]',
            'input[aria-label*="code" i]',
            'input[type="number"]',
            'input[name="email_confirmation_code"]',
            'input[autocomplete="one-time-code"]',
        ]:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1000):
                    el.click()
                    _time.sleep(0.3)
                    el.fill("")
                    for ch in code:
                        el.type(ch, delay=random.randint(50, 120))
                    code_filled = True
                    break
            except Exception:
                continue

        if not code_filled:
            # Fallback: any visible text/tel/number input
            try:
                inputs = page.locator('input[type="text"], input[type="tel"], input[type="number"]')
                for i in range(inputs.count()):
                    inp = inputs.nth(i)
                    if inp.is_visible(timeout=500):
                        inp.click()
                        _time.sleep(0.3)
                        inp.fill("")
                        for ch in code:
                            inp.type(ch, delay=random.randint(50, 120))
                        code_filled = True
                        break
            except Exception:
                pass

        if not code_filled:
            scr = None
            try:
                raw = page.screenshot(type="jpeg", quality=60)
                scr = _b64.b64encode(raw).decode("ascii")
            except Exception:
                pass
            return {"status": "failed", "message": "Could not find code input field. See screenshot.",
                    "screenshot": scr, "details": details}

        _time.sleep(1)

        # Click submit
        submitted = False
        for sel in ['button[type="submit"]', 'button:has-text("Confirm")',
                    'button:has-text("Submit")', 'button:has-text("Next")',
                    'button:has-text("Kirim")', 'button:has-text("Konfirmasi")']:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    submitted = True
                    break
            except Exception:
                continue
        if not submitted:
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass

        _time.sleep(5)

        # "Not Now" popups
        for _ in range(3):
            try:
                nn = page.locator('text="Not Now"').first
                if nn.is_visible(timeout=2000):
                    nn.click()
                    _time.sleep(2)
            except Exception:
                break

        url = page.url.lower()
        details["cookies"] = browser._get_ig_cookies()
        details["final_url"] = page.url

        # Still on challenge
        if "/challenge/" in url:
            scr = None
            try:
                raw = page.screenshot(type="jpeg", quality=60)
                scr = _b64.b64encode(raw).decode("ascii")
            except Exception:
                pass
            return {"status": "failed", "message": "Still on verification page. Code may be incorrect.",
                    "screenshot": scr, "details": details}

        # Success
        cookies = browser._get_ig_cookies()
        details["cookies"] = cookies
        if cookies.get("ds_user_id"):
            return {"status": "success", "message": f"Verification successful! Logged in as @{username}.",
                    "screenshot": None, "details": details}

        return {"status": "failed", "message": "Verification submitted but no session cookies found.",
                "screenshot": None, "details": details}

    except Exception as e:
        return {"status": "failed", "message": f"Error submitting code: {e}",
                "screenshot": None, "details": details}
    finally:
        _cleanup_login_session(session_id)


def pw_submit_challenge(session_id: str, code: str) -> dict:
    """
    Submit a verification code. Runs in fresh thread.
    Always cleans up the browser session afterward.

    Returns dict with keys: status, message, screenshot, details
    """
    result_holder: list[dict | None] = [None]
    error_holder: list[BaseException | None] = [None]

    def _worker() -> None:
        try:
            result_holder[0] = _submit_challenge_impl(session_id, code)
        except BaseException as exc:
            error_holder[0] = exc

    t = _threading.Thread(target=_worker, daemon=True, name=f"pw-challenge-{session_id[:8]}")
    t.start()
    t.join(timeout=60)

    if error_holder[0] is not None:
        _cleanup_login_session(session_id)
        return {"status": "failed", "message": f"Error: {error_holder[0]}",
                "screenshot": None, "details": {}}
    if result_holder[0] is None:
        _cleanup_login_session(session_id)
        return {"status": "failed", "message": "Challenge submission timed out.",
                "screenshot": None, "details": {}}
    return result_holder[0]


# ---------------------------------------------------------------------------
# Legacy test-login flow (SSE-based, kept for backward compatibility)
# ---------------------------------------------------------------------------

def pw_test_login(username: str, password: str, *, live: bool = False) -> dict:
    """
    Test / establish an IG login session for the given account.

    When *live=True* (the normal FE flow) the browser opens **headed**
    (visible window) and the **user logs in manually** — the system only
    watches cookies and takes periodic screenshots streamed to the FE
    via SSE.

    When *live=False* (background / automated) the old auto-fill flow is
    used via ``ensure_logged_in()``.

    Returns ``{"success": bool, "message": str, "details": dict}``.

    This is a **sync** function — run it in an executor from async code.

    Internally spawns a **fresh** ``threading.Thread`` so that the
    Playwright sync API never sees an asyncio event loop (uvicorn's
    executor threads can carry loop references that confuse Playwright).
    """
    result_holder: list[dict | None] = [None]
    error_holder: list[BaseException | None] = [None]

    def _worker() -> None:
        try:
            result_holder[0] = _pw_test_login_impl(
                username, password, live=live,
            )
        except BaseException as exc:          # noqa: BLE001
            error_holder[0] = exc

    t = _threading.Thread(target=_worker, daemon=True, name=f"pw-login-{username}")
    t.start()
    t.join(timeout=300)  # 5 min hard upper-bound

    if error_holder[0] is not None:
        raise error_holder[0]
    if result_holder[0] is None:
        # Thread timed out or died without setting a result
        return {
            "success": False,
            "message": f"Login test thread for @{username} timed out.",
            "details": {"cookies": {}, "final_url": "", "profile_nuked": False},
        }
    return result_holder[0]


def _kill_orphan_chromes(profile_dir: str) -> None:
    """Kill Chrome processes that are using a specific Playwright profile dir."""
    if sys.platform != "win32":
        return
    import subprocess
    try:
        # Use WMIC to find chrome.exe processes whose command line contains our profile dir
        result = subprocess.run(
            ["wmic", "process", "where",
             f"Name='chrome.exe' and CommandLine like '%{Path(profile_dir).name}%'",
             "get", "ProcessId"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.isdigit():
                pid = int(line)
                try:
                    import signal
                    os.kill(pid, signal.SIGTERM)
                    log.info("[TestLogin] Killed orphan Chrome pid=%d for profile %s", pid, Path(profile_dir).name)
                except OSError:
                    pass
        _time.sleep(1)
    except Exception as exc:
        log.debug("[TestLogin] _kill_orphan_chromes failed (non-fatal): %s", exc)


def _pw_test_login_impl(username: str, password: str, *, live: bool = False) -> dict:
    """Inner implementation — runs in a **fresh** thread with no asyncio loop."""
    acct = _IGAccount(username, password)
    details: dict = {"cookies": {}, "final_url": "", "profile_nuked": False}

    # Prepare live-stream queue
    if live:
        _test_login_events[username] = deque()

    def _ss_cb(step: str, b64: str, message: str) -> None:
        """Screenshot callback — also push to SSE queue."""
        _emit_event(username, "screenshot", step=step, screenshot=b64, message=message)

    def _launch_and_login(attempt: int = 1) -> dict | None:
        """
        Try to launch browser + login.
        Returns result dict on success/known-failure, or *None* if the
        browser crashed on launch (TargetClosedError) and should be retried
        after nuking the profile.
        """
        nonlocal details

        browser_kwargs: dict[str, Any] = {}
        if live:
            browser_kwargs["headless"] = False
            browser_kwargs["on_screenshot"] = _ss_cb

        _emit_event(username, "status",
                     message="Opening browser..." if attempt == 1
                     else "Retrying with fresh profile...")

        try:
            with _PlaywrightBrowser(acct, **browser_kwargs) as browser:
                if live:
                    _emit_event(username, "status",
                                message="Browser opened — please log in manually in the browser window.")
                    logged_in = browser.wait_for_manual_login(timeout=180)
                else:
                    _emit_event(username, "status", message="Browser opened — checking imported cookies...")
                    logged_in = browser.ensure_logged_in()

                details["cookies"] = browser._get_ig_cookies()
                details["final_url"] = browser.page.url

                if not logged_in:
                    browser._take_screenshot("login_failed", "Login failed or timed out")
                    reason = _pw_status.get("error", "timeout" if live else "unknown")
                    if not live and reason != "cookie_required":
                        _nuke_profile(acct)
                        details["profile_nuked"] = True
                    msg = (
                        f"Login timed out for @{username}. Please try again."
                        if live
                        else (
                            f"Cookie session missing/invalid for @{username}. Import fresh Instagram cookies."
                            if reason == "cookie_required"
                            else f"Login failed for @{username}: {reason}. Browser profile wiped for fresh retry."
                        )
                    )
                    return {"success": False, "message": msg, "details": details}

                # Verify API cookies actually work by fetching own profile
                _emit_event(username, "status", message="Login detected — verifying API session...")
                browser._take_screenshot("api_verify", "Verifying API cookies...")
                api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
                resp = browser.ig_api_fetch(api_url)
                if resp is None or resp.get("__error"):
                    status_code = resp.get("status", "unknown") if resp else "no_response"
                    if status_code == 401:
                        log.info("[TestLogin] @%s: API returned 401, attempting force re-login ...", username)
                        _emit_event(username, "status", message="API returned 401 — force re-login...")
                        relogged = browser._force_relogin()
                        if relogged:
                            details["cookies"] = browser._get_ig_cookies()
                            details["final_url"] = browser.page.url
                            _time.sleep(2)
                            browser._take_screenshot("re_login_done", "Re-login complete, retrying API...")
                            resp2 = browser.ig_api_fetch(api_url)
                            if resp2 and not resp2.get("__error"):
                                acct.login_ok = True
                                browser._take_screenshot("api_ok", "API verified after re-login!")
                                return {
                                    "success": True,
                                    "message": f"Login successful for @{username} (session refreshed).",
                                    "details": details,
                                }
                        # Still 401 after re-login — nuke profile
                        browser._take_screenshot("api_fail_401", "API still 401 after re-login. Nuking profile...")
                        _nuke_profile(acct)
                        details["profile_nuked"] = True
                        details["cookies"] = browser._get_ig_cookies()
                        return {
                            "success": False,
                            "message": (
                                f"Login appeared OK but API returned 401 after re-login. "
                                f"Browser profile wiped. Possible causes: account restricted, "
                                f"challenge required, or IG blocking this device."
                            ),
                            "details": details,
                        }
                    return {
                        "success": False,
                        "message": f"Login appeared OK but API verification failed (status: {status_code}).",
                        "details": details,
                    }

                acct.login_ok = True
                browser._take_screenshot("all_ok", "Login and API verified!")
                return {
                    "success": True,
                    "message": f"Login successful for @{username}. Session cookies verified.",
                    "details": details,
                }
        except Exception as launch_err:
            err_name = type(launch_err).__name__
            # TargetClosedError = browser profile is corrupt / locked by orphan process
            if "TargetClosed" in err_name or "Target page, context or browser has been closed" in str(launch_err):
                log.warning("[TestLogin] @%s browser crashed on launch (attempt %d): %s", username, attempt, launch_err)
                return None  # signal caller to nuke & retry
            raise  # other errors bubble up

    # --- Main flow: attempt launch with auto-recovery ---
    try:
        # Kill orphan Chrome processes that may hold the profile lock
        _kill_orphan_chromes(acct.profile_dir)

        result = _launch_and_login(attempt=1)
        if result is None:
            # Browser crashed (corrupt profile) — nuke and retry once
            log.info("[TestLogin] @%s: nuking profile and retrying...", username)
            _emit_event(username, "status", message="Browser crashed — cleaning up and retrying...")
            _kill_orphan_chromes(acct.profile_dir)
            _nuke_profile(acct)
            details["profile_nuked"] = True
            _time.sleep(2)
            result = _launch_and_login(attempt=2)
            if result is None:
                result = {
                    "success": False,
                    "message": f"Browser keeps crashing for @{username}. Profile nuked twice. Try restarting.",
                    "details": details,
                }

        _emit_event(username, "done", result=result)
        return result
    except Exception as e:
        log.warning("[TestLogin] @%s error: %s: %s", username, type(e).__name__, e)
        result = {
            "success": False,
            "message": f"Error during login test: {type(e).__name__}: {e}",
            "details": details,
        }
        _emit_event(username, "done", result=result)
        return result
    finally:
        # Keep the queue around briefly so the SSE endpoint can drain it;
        # the endpoint itself cleans up after sending "done".
        pass


def _nuke_profile(acct: _IGAccount) -> None:
    """
    Delete the persistent browser profile directory for an account.
    This forces a completely fresh browser session on next attempt.
    """
    import shutil
    profile_path = Path(acct.profile_dir)
    if profile_path.exists():
        try:
            shutil.rmtree(profile_path, ignore_errors=True)
            log.info("[TestLogin] Nuked browser profile for @%s at %s", acct.username, profile_path)
        except Exception as e:
            log.warning("[TestLogin] Could not delete profile for @%s: %s", acct.username, e)


# ---------------------------------------------------------------------------
# IG Scraping functions
# ---------------------------------------------------------------------------

def pw_search_profiles(query: str, max_results: int = 10) -> list[dict]:
    """
    Search for IG profiles using the web search bar.

    Returns list of: {"username": str, "full_name": str, "is_verified": bool}
    """
    if not is_available():
        return []

    max_account_retries = 3
    account_attempts = 0
    last_error = ""

    while account_attempts < max_account_retries:
        account = _account_pool.next_account()
        if account is None:
            log.warning("[Playwright] No healthy IG accounts available for search '%s'", query[:50])
            break

        account_attempts += 1
        acct_label = account.username
        results = []

        try:
            with _PlaywrightBrowser(account=account) as browser:
                # Ensure we have a logged-in session
                if not browser.ensure_logged_in():
                    log.warning("[Playwright] Cannot search as @%s — not logged in", acct_label)
                    last_error = "not_logged_in"
                    continue

                _human_delay(3, 6)

                # Prefer the same IG topsearch endpoint used by the web app.
                try:
                    import urllib.parse

                    api_url = (
                        "https://www.instagram.com/web/search/topsearch/"
                        f"?context=user&query={urllib.parse.quote(query)}"
                    )
                    resp = browser.ig_api_fetch(api_url)
                    if resp and not resp.get("__error"):
                        users = resp.get("users") or []
                        seen = set()
                        for item in users:
                            user = item.get("user") or {}
                            username = (user.get("username") or "").strip().lower()
                            if not username or username in seen:
                                continue
                            seen.add(username)
                            results.append({
                                "username": username,
                                "full_name": (user.get("full_name") or username).strip(),
                                "is_verified": bool(user.get("is_verified", False)),
                            })
                            if len(results) >= max_results:
                                break

                        _pw_status["ok"] = True
                        _pw_status["error"] = None
                        log.info(
                            "[Playwright] Search '%s' via API on @%s → %d results",
                            query[:50], acct_label, len(results),
                        )
                        return results

                    if resp and resp.get("__error"):
                        status = resp.get("status", 0)
                        last_error = f"search_api_http_{status}" if status else "search_api_error"
                        if status == 401:
                            _pw_status["error"] = "search_api_auth_limited"
                            log.warning(
                                "[Playwright] Search API 401 on @%s for '%s' — keeping session and falling back to UI search",
                                acct_label,
                                query[:50],
                            )
                        elif status == 429:
                            _account_pool.mark_rate_limited(acct_label)
                            log.warning(
                                "[Playwright] Search API 429 on @%s for '%s' — trying next account (%d/%d)",
                                acct_label, query[:50], account_attempts, max_account_retries,
                            )
                            continue
                except Exception as e:
                    log.warning("[Playwright] API search failed for '%s' on @%s: %s", query[:50], acct_label, e)
                    last_error = str(e)

                # Navigate to explicit search page before UI fallback.
                try:
                    browser.page.goto(
                        "https://www.instagram.com/explore/search/",
                        wait_until="domcontentloaded",
                        timeout=20000,
                    )
                    _short_delay()
                except Exception:
                    pass

                # Click search icon/bar
                try:
                    search_btn = browser.page.locator('[aria-label="Search"]').first
                    if search_btn.is_visible(timeout=5000):
                        search_btn.click()
                        _short_delay()
                except Exception:
                    pass

                # Type search query
                try:
                    search_selectors = [
                        'input[aria-label="Search input"]',
                        'input[aria-label="Search"]',
                        'input[aria-label="Cari"]',
                        'input[placeholder="Search"]',
                        'input[placeholder="Cari"]',
                        'input[type="search"]',
                        'input[type="text"]',
                    ]
                    search_input = None
                    for selector in search_selectors:
                        candidate = browser.page.locator(selector).first
                        try:
                            if candidate.is_visible(timeout=1500):
                                search_input = candidate
                                break
                        except Exception:
                            continue

                    if search_input is None:
                        raise RuntimeError("search input not found")

                    search_input.fill("")
                    _short_delay()

                    for char in query:
                        search_input.type(char, delay=random.randint(50, 150))
                        _time.sleep(random.uniform(0.05, 0.15))

                    _human_delay(2, 4)

                except Exception as e:
                    last_error = str(e)
                    log.warning(
                        "[Playwright] Could not interact with search on @%s: %s",
                        acct_label, e,
                    )
                    continue

                # Extract search results from the dropdown
                try:
                    browser.page.wait_for_selector('[role="listbox"], [role="dialog"]', timeout=8000)
                    _short_delay()

                    links = browser.page.locator('a[href*="instagram.com/"]').all()
                    seen = set()

                    for link in links[:max_results * 2]:
                        try:
                            href = link.get_attribute("href") or ""
                            text = link.inner_text().strip()

                            match = re.search(r'instagram\.com/([a-zA-Z0-9_.]+)', href)
                            if not match:
                                continue
                            username = match.group(1).lower()
                            if username in seen or username in ("explore", "accounts", "p", "reel"):
                                continue
                            seen.add(username)

                            lines = [l.strip() for l in text.split("\n") if l.strip()]
                            full_name = lines[0] if lines else username

                            results.append({
                                "username": username,
                                "full_name": full_name,
                                "is_verified": False,
                            })

                            if len(results) >= max_results:
                                break
                        except Exception:
                            continue
                except Exception as e:
                    last_error = str(e)
                    log.warning("[Playwright] Could not extract search results on @%s: %s", acct_label, e)
                    continue

                _pw_status["ok"] = True
                _pw_status["error"] = None
                log.info("[Playwright] Search '%s' via UI on @%s → %d results", query[:50], acct_label, len(results))
                return results

        except Exception as e:
            last_error = str(e) or type(e).__name__
            log.warning(
                "[Playwright] search_profiles failed on @%s: %s: %s",
                acct_label, type(e).__name__, e or '(no details)',
            )
            continue

    if last_error:
        _pw_status["ok"] = False
        _pw_status["error"] = last_error[:200]
    return []


def pw_get_profile(handle: str) -> dict | None:
    """
    Get profile info for an IG handle via IG internal API.

    Returns: {"bio": str, "full_name": str, "external_url": str,
              "is_verified": bool, "followers": int, "user_id": int | None}
    or None if profile not found / blocked.
    """
    if not is_available():
        return None

    _check_daily_reset()
    handle = handle.lstrip("@")

    account = _account_pool.next_account()

    try:
        with _PlaywrightBrowser(account=account) as browser:
            if not browser.ensure_logged_in():
                log.warning("[Playwright] Cannot get profile -- not logged in")
                return None

            _human_delay(2, 5)

            user = browser.ig_get_web_profile(handle)
            if user is None:
                # Fallback: navigate to profile page and parse HTML
                log.info("[Playwright] API failed for @%s, falling back to HTML scraping", handle)
                if not browser.navigate(f"https://www.instagram.com/{handle}/"):
                    return None
                _human_delay(3, 6)
                content = browser.get_page_content()
                if browser.check_login_wall():
                    _pw_status["error"] = "login_wall_after_nav"
                    return None
                if "Sorry, this page isn't available" in content or "Page Not Found" in content:
                    log.info("[Playwright] Profile @%s not found", handle)
                    return None
                profile = _extract_profile_from_html(content, handle)
                if profile:
                    _pw_status["profiles_today"] += 1
                    _pw_status["ok"] = True
                    _pw_status["error"] = None
                return profile

            # Build profile dict from API response
            bio = user.get("biography", "")
            full_name = user.get("full_name", "")
            external_url = user.get("external_url", "") or ""
            is_verified = user.get("is_verified", False)
            followers = (user.get("edge_followed_by") or {}).get("count", 0)
            user_id = user.get("id")
            if user_id is not None:
                try:
                    user_id = int(user_id)
                except (ValueError, TypeError):
                    user_id = None

            _pw_status["profiles_today"] += 1
            _pw_status["ok"] = True
            _pw_status["error"] = None

            log.info("[Playwright] API profile @%s: %s, %d followers",
                     handle, full_name[:40], followers)

            return {
                "bio": bio,
                "full_name": full_name,
                "external_url": external_url,
                "is_verified": is_verified,
                "followers": followers,
                "user_id": user_id,
            }

    except Exception as e:
        _pw_status["ok"] = False
        _pw_status["error"] = (str(e) or type(e).__name__)[:200]
        log.warning("[Playwright] get_profile @%s failed: %s: %s", handle, type(e).__name__, e or '(no details)')
        return None


def pw_get_posts(handle: str, max_posts: int = 12) -> list[dict]:
    """
    Scrape recent posts from an IG profile via internal API.

    Uses ``/api/v1/users/web_profile_info/`` to get post data directly
    as JSON -- no DOM rendering or per-post navigation needed.

    When pagination is needed (max_posts > 12) and the current account
    gets rate-limited (401), marks it for cooldown and retries with the
    next healthy account from the pool.

    Returns list of: {"post_url": str, "image_url": str, "caption": str,
                      "timestamp": str | None, "source": "playwright"}
    """
    if not is_available():
        return []

    _check_daily_reset()
    handle = handle.lstrip("@")
    posts: list[dict] = []

    # How many accounts to try before giving up on pagination
    max_account_retries = 3
    account_attempts = 0
    pagination_done = False

    while account_attempts < max_account_retries and not pagination_done:
        account = _account_pool.next_account()
        if account is None:
            log.warning("[Playwright] No healthy IG accounts available")
            break
        account_attempts += 1
        acct_label = account.username

        try:
            with _PlaywrightBrowser(account=account) as browser:
                if not browser.ensure_logged_in():
                    log.warning("[Playwright] Cannot scrape posts as @%s -- not logged in", acct_label)
                    continue

                _human_delay(2, 5)

                user = browser.ig_get_web_profile(handle)

                if user is not None:
                    # ---- API path (preferred) ----
                    media = user.get("edge_owner_to_timeline_media") or {}
                    initial_edges = list(media.get("edges") or [])
                    total_available = media.get("count", 0)
                    user_id = user.get("id")

                    if total_available and not initial_edges:
                        recovered_feed = browser.ig_get_user_feed(
                            user_id,
                            count=min(max_posts, 12),
                        ) if user_id else None
                        recovered_edges = list((recovered_feed or {}).get("edges") or [])

                        if recovered_edges:
                            initial_edges = recovered_edges
                            log.info(
                                "[Playwright] API @%s (acct @%s): profile timeline empty, recovered %d posts from feed fallback",
                                handle,
                                acct_label,
                                len(initial_edges),
                            )
                        else:
                            log.info(
                                "[Playwright] API @%s (acct @%s): profile resolved but timeline empty (count=%d), falling back to DOM",
                                handle,
                                acct_label,
                                total_available,
                            )
                            user = None

                    if user is not None:
                        if max_posts <= 12 or not user_id:
                            # Initial response has enough posts — no pagination needed
                            all_edges = initial_edges
                            pagination_done = True
                            log.info("[Playwright] API @%s (acct @%s): %d posts available, %d in response",
                                     handle, acct_label, total_available, len(all_edges))
                        else:
                            # Need pagination — use /api/v1/feed/user/ endpoint.
                            # If this account is rate-limited (401), mark it and
                            # retry with the next healthy account.
                            all_edges = []
                            next_max_id = ""
                            pagination_failed = False
                            for page_num in range(1, (max_posts // 12) + 3):
                                if len(all_edges) >= max_posts:
                                    break
                                _human_delay(2, 5)
                                feed = browser.ig_get_user_feed(
                                    user_id, max_id=next_max_id,
                                    count=min(max_posts - len(all_edges), 12),
                                )
                                if not feed:
                                    # 401 or other error — mark account as rate-limited
                                    pagination_failed = True
                                    break
                                new_edges = feed.get("edges") or []
                                if not new_edges:
                                    break
                                all_edges.extend(new_edges)
                                pi = feed.get("page_info") or {}
                                if not pi.get("has_next_page"):
                                    break
                                next_max_id = pi.get("end_cursor", "")
                                if not next_max_id:
                                    break
                                log.debug("[Playwright] API @%s (acct @%s): page %d, cumulative %d edges",
                                          handle, acct_label, page_num, len(all_edges))

                            if pagination_failed and not all_edges:
                                # Pagination failed on first page — mark this account
                                # as rate-limited and try the next one.
                                _account_pool.mark_rate_limited(acct_label)
                                log.info(
                                    "[Playwright] @%s rate-limited on pagination for @%s, "
                                    "trying next account (%d/%d)...",
                                    acct_label, handle, account_attempts, max_account_retries,
                                )
                                # Fall back to initial 12 if no more accounts
                                if not _account_pool.has_healthy_account() or account_attempts >= max_account_retries:
                                    all_edges = initial_edges
                                    pagination_done = True
                                    log.info("[Playwright] No more healthy accounts, using %d initial posts for @%s",
                                             len(all_edges), handle)
                                else:
                                    continue  # retry with next account
                            elif all_edges:
                                pagination_done = True
                                log.info("[Playwright] API @%s (acct @%s): %d posts available, %d fetched (paginated)",
                                         handle, acct_label, total_available, len(all_edges))
                            else:
                                # Pagination returned 0 edges without error — unusual
                                all_edges = initial_edges
                                pagination_done = True
                                log.info("[Playwright] API @%s: pagination empty, using %d initial posts",
                                         handle, len(all_edges))

                        for edge in all_edges[:max_posts]:
                            node = edge.get("node") or {}
                            shortcode = node.get("shortcode", "")
                            if not shortcode:
                                continue

                            # Caption
                            caption = ""
                            caption_edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
                            if caption_edges:
                                caption = (caption_edges[0].get("node") or {}).get("text", "")

                            # Image
                            image_url = node.get("display_url", "")

                            # Timestamp
                            timestamp = None
                            taken_at = node.get("taken_at_timestamp")
                            if taken_at:
                                try:
                                    timestamp = datetime.fromtimestamp(int(taken_at), tz=timezone.utc).isoformat()
                                except (ValueError, OSError):
                                    pass

                            # Determine post vs reel
                            is_video = node.get("is_video", False)
                            typename = node.get("__typename", "")
                            if is_video and typename == "GraphVideo":
                                post_url = f"https://www.instagram.com/reel/{shortcode}/"
                            else:
                                post_url = f"https://www.instagram.com/p/{shortcode}/"

                            posts.append({
                                "post_url": post_url,
                                "image_url": image_url,
                                "caption": caption,
                                "timestamp": timestamp,
                                "source": "playwright",
                            })

                        _pw_status["profiles_today"] += 1
                        if account:
                            account.profiles_today += 1
                        _pw_status["ok"] = True
                        _pw_status["error"] = None
                        pagination_done = True  # ensure we exit the while loop

                if user is None:
                    # ---- DOM fallback (if API fails) ----
                    log.info("[Playwright] API failed for @%s posts, falling back to HTML", handle)
                    if not browser.navigate(f"https://www.instagram.com/{handle}/"):
                        pagination_done = True
                        break
                    _human_delay(3, 6)

                    content = browser.get_page_content()
                    login_wall_after_nav = browser.check_login_wall()
                    if "Sorry, this page isn't available" in content:
                        pagination_done = True
                        break

                    browser.scroll_down(times=min(max_posts // 4, 5))
                    _human_delay(2, 4)
                    content = browser.get_page_content()

                    dom_posts = _extract_posts_from_profile_dom(browser, max_posts)
                    if dom_posts:
                        log.info(
                            "[Playwright] DOM @%s: extracted %d rendered grid posts — enriching captions",
                            handle,
                            len(dom_posts),
                        )
                        dom_posts = _enrich_posts_with_full_captions(
                            browser, dom_posts, max_to_enrich=min(max_posts, 10)
                        )
                        posts.extend(dom_posts)
                        _pw_status["profiles_today"] += 1
                        if account:
                            account.profiles_today += 1
                        _pw_status["ok"] = True
                        _pw_status["error"] = None
                        pagination_done = True
                        continue

                    if login_wall_after_nav:
                        _pw_status["error"] = "login_wall_after_nav"
                        pagination_done = True
                        break

                    preview_posts = _extract_posts_from_profile_html(content, handle, max_posts)
                    if preview_posts:
                        log.info(
                            "[Playwright] DOM @%s: extracted %d grid posts — enriching captions",
                            handle,
                            len(preview_posts),
                        )
                        preview_posts = _enrich_posts_with_full_captions(
                            browser, preview_posts, max_to_enrich=min(max_posts, 10)
                        )
                        posts.extend(preview_posts)
                        _pw_status["profiles_today"] += 1
                        if account:
                            account.profiles_today += 1
                        _pw_status["ok"] = True
                        _pw_status["error"] = None
                        pagination_done = True
                        continue

                    post_links = re.findall(
                        r'href="(/(?:[^"/]+/)?(?:p|reel)/[A-Za-z0-9_-]+/)"',
                        content,
                    )
                    post_links = list(dict.fromkeys(post_links))
                    log.info("[Playwright] DOM @%s: found %d post/reel links", handle, len(post_links))

                    for link in post_links[:max_posts]:
                        _human_delay(4, 10)
                        post_url = f"https://www.instagram.com{link}"
                        if not browser.navigate(post_url):
                            continue
                        _human_delay(2, 5)
                        post_content = browser.get_page_content()
                        post_data = _extract_post_from_html(post_content, post_url)
                        if post_data:
                            post_data["source"] = "playwright"
                            posts.append(post_data)
                        browser.page.go_back()
                        _short_delay()

                    _pw_status["profiles_today"] += 1
                    if account:
                        account.profiles_today += 1
                    _pw_status["ok"] = True
                    _pw_status["error"] = None
                    pagination_done = True

        except Exception as e:
            _pw_status["ok"] = False
            _pw_status["error"] = (str(e) or type(e).__name__)[:200]
            log.warning("[Playwright] get_posts @%s (acct @%s) failed: %s: %s",
                        handle, acct_label, type(e).__name__, e or '(no details)')
            pagination_done = True  # don't retry on unexpected errors

    log.info("[Playwright] @%s: scraped %d posts total", handle, len(posts))
    return posts


def _extract_posts_from_profile_dom(browser, max_posts: int) -> list[dict]:
    """Extract visible post previews from the rendered profile grid DOM."""
    try:
        anchors = browser.page.locator('a[href*="/p/"], a[href*="/reel/"]')
        anchor_count = anchors.count()
    except Exception:
        return []

    posts: list[dict] = []
    seen_urls: set[str] = set()

    for index in range(min(anchor_count, max_posts)):
        try:
            anchor = anchors.nth(index)
            href = anchor.get_attribute("href") or ""
            if not href:
                continue

            post_url = href if href.startswith("http") else f"https://www.instagram.com{href}"
            if post_url in seen_urls:
                continue
            seen_urls.add(post_url)

            image_url = ""
            caption = ""

            try:
                image = anchor.locator("img").first
                image_url = image.get_attribute("src") or ""
                caption = image.get_attribute("alt") or ""
            except Exception:
                image_url = ""
                caption = ""

            posts.append({
                "post_url": post_url,
                "image_url": image_url,
                "caption": caption,
                "timestamp": None,
                "source": "playwright",
            })
        except Exception:
            continue

    return posts


def _enrich_posts_with_full_captions(
    browser,
    posts: list[dict],
    max_to_enrich: int = 10,
) -> list[dict]:
    """Navigate to individual post pages to replace alt-text captions with full captions.

    Used when web_profile_info API returned 401 and DOM/HTML fallback only captured
    truncated alt-text or accessibility captions. Full captions contain WA phone numbers.

    Args:
        browser: Active _PlaywrightBrowser with valid session.
        posts: Post dicts with post_url but potentially truncated captions.
        max_to_enrich: Max posts to navigate (keeps runtime reasonable).

    Returns:
        List of posts with full captions where available; originals for the rest.
    """
    enriched: list[dict] = []
    enriched_count = 0

    for post in posts:
        post_url = post.get("post_url", "")
        if not post_url or enriched_count >= max_to_enrich:
            enriched.append(post)
            continue
        try:
            _human_delay(2, 4)
            if not browser.navigate(post_url):
                enriched.append(post)
                continue
            _human_delay(1, 2)
            html = browser.get_page_content()
            full_post = _extract_post_from_html(html, post_url)
            if full_post and (full_post.get("caption") or full_post.get("image_url")):
                full_post["source"] = "playwright"
                # Preserve CDN image URL from DOM if enrichment page didn't return one
                if post.get("image_url") and not full_post.get("image_url"):
                    full_post["image_url"] = post["image_url"]
                enriched.append(full_post)
                enriched_count += 1
                log.debug("[Playwright] Enriched caption for %s (%d chars)",
                          post_url.split("/p/")[-1].rstrip("/"), len(full_post.get("caption", "")))
            else:
                enriched.append(post)
        except Exception as exc:
            log.debug("[Playwright] Caption enrichment failed for %s: %s", post_url[:80], exc)
            enriched.append(post)

    log.info("[Playwright] Caption enrichment: %d/%d posts enriched with full captions",
             enriched_count, len(posts))
    return enriched


def pw_get_following(handle: str, max_results: int = 200) -> list[dict] | None:
    """
    Get following list from an IG profile.

    Returns list of: {"username": str, "full_name": str, "is_verified": bool}
    """
    if not is_available():
        return None

    _check_daily_reset()
    handle = handle.lstrip("@")
    following = []

    account = _account_pool.next_account()

    def _mark_auth_limited(reason: str) -> None:
        if account:
            account.mark_login_failed(reason)

    try:
        with _PlaywrightBrowser(account=account) as browser:
            if not browser.ensure_logged_in():
                log.warning("[Playwright] Cannot get following -- not logged in")
                _mark_auth_limited("not_logged_in")
                return None

            user = browser.ig_get_web_profile(handle)
            user_id = (user or {}).get("id")
            if user_id:
                try:
                    user_id = int(user_id)
                except (TypeError, ValueError):
                    user_id = None

            if user_id:
                following: list[dict] = []
                max_id = ""
                max_pages = max_results // 50 + 1

                for _ in range(max_pages):
                    if len(following) >= max_results:
                        break

                    params = [f"count={min(50, max_results - len(following))}"]
                    if max_id:
                        params.append(f"max_id={max_id}")
                    api_url = (
                        f"https://www.instagram.com/api/v1/friendships/{user_id}/following/?"
                        + "&".join(params)
                    )
                    resp = browser.ig_api_fetch(api_url)
                    if resp is None:
                        log.warning("[Playwright] Following API returned no response for @%s", handle)
                        _mark_auth_limited("following_api_no_response")
                        return None
                    if resp.get("__error"):
                        status_code = resp.get("status")
                        if status_code == 401:
                            log.warning(
                                "[Playwright] Following API requires authenticated session for @%s",
                                handle,
                            )
                            _mark_auth_limited("following_requires_login")
                            return None
                        if status_code == 429:
                            _pw_status["ok"] = False
                            _pw_status["error"] = "following_rate_limited"
                            if account:
                                account.mark_rate_limited(getattr(cfg, "PW_ACCOUNT_COOLDOWN_MINUTES", 30))
                            log.warning("[Playwright] Following API rate-limited for @%s", handle)
                            return None
                        log.warning(
                            "[Playwright] Following API failed for @%s with status %s",
                            handle,
                            status_code,
                        )
                        _mark_auth_limited(f"following_http_{status_code}")
                        return None

                    users = resp.get("users") or []
                    for raw_user in users:
                        username = (raw_user.get("username") or "").strip().lower()
                        if not username or username in (handle.lower(), "explore"):
                            continue
                        following.append({
                            "username": username,
                            "full_name": raw_user.get("full_name", ""),
                            "is_verified": raw_user.get("is_verified", False),
                        })

                    max_id = resp.get("next_max_id") or ""
                    if not max_id:
                        break
                    _time.sleep(random.uniform(1.5, 3.0))

                _pw_status["profiles_today"] += 1
                _pw_status["ok"] = True
                _pw_status["error"] = None
                log.info("[Playwright] @%s: got %d following via API", handle, len(following))
                return following[:max_results]

            if not browser.navigate(f"https://www.instagram.com/{handle}/"):
                _mark_auth_limited("profile_navigation_failed")
                return None

            _human_delay(3, 6)

            page_text = ""
            try:
                page_text = browser.page.locator("body").inner_text(timeout=5000).lower()
            except Exception:
                page_text = ""

            if "masuk" in page_text and "daftar" in page_text:
                log.warning(
                    "[Playwright] Profile @%s opened in public view only; following requires a stronger IG session",
                    handle,
                )
                _mark_auth_limited("public_profile_only")
                return None

            # Click "following" link
            try:
                following_link = browser.page.locator(f'a[href="/{handle}/following/"]').first
                if not following_link.is_visible(timeout=5000):
                    following_link = browser.page.locator('a').filter(has_text=re.compile(r'\\bdiikuti\\b', re.IGNORECASE)).first
                if not following_link.is_visible(timeout=5000):
                    log.warning("[Playwright] Following link not visible for @%s", handle)
                    _mark_auth_limited("following_link_not_visible")
                    return None
                try:
                    following_link.click(timeout=5000, force=True)
                except Exception:
                    following_link.evaluate("(el) => el.click()")
                _human_delay(3, 6)
            except Exception as e:
                log.warning("[Playwright] Could not click following for @%s: %s", handle, e)
                _mark_auth_limited("following_click_failed")
                return None

            # Wait for dialog/list to appear
            try:
                browser.page.wait_for_selector('[role="dialog"]', timeout=8000)
            except Exception:
                log.warning("[Playwright] Following dialog did not appear for @%s", handle)
                _mark_auth_limited("following_dialog_missing")
                return None

            # Scroll through the following list
            seen_usernames = set()
            no_new_count = 0
            max_scrolls = max_results // 10 + 5

            for scroll_i in range(max_scrolls):
                if len(following) >= max_results:
                    break

                # Find all user rows in the dialog
                try:
                    dialog = browser.page.locator('[role="dialog"]').first
                    links = dialog.locator('a[href*="/"]').all()

                    for link in links:
                        try:
                            href = link.get_attribute("href") or ""
                            match = re.match(r'^/([a-zA-Z0-9_.]+)/$', href)
                            if not match:
                                continue
                            username = match.group(1).lower()
                            if username in seen_usernames or username in (handle.lower(), "explore"):
                                continue
                            seen_usernames.add(username)

                            text = link.inner_text().strip()
                            lines = [l.strip() for l in text.split("\n") if l.strip()]
                            full_name = lines[1] if len(lines) > 1 else ""

                            following.append({
                                "username": username,
                                "full_name": full_name,
                                "is_verified": False,
                            })
                        except Exception:
                            continue

                except Exception:
                    break

                if len(following) <= len(seen_usernames) - 5:
                    # No real new entries
                    no_new_count += 1
                    if no_new_count > 3:
                        break

                # Scroll the dialog
                try:
                    dialog = browser.page.locator('[role="dialog"]').first
                    dialog.evaluate("el => el.querySelector('[style*=\"overflow\"]')?.scrollBy(0, 500) || el.scrollBy(0, 500)")
                except Exception:
                    break

                _time.sleep(random.uniform(1.5, 3.0))

            _pw_status["profiles_today"] += 1
            _pw_status["ok"] = True
            _pw_status["error"] = None

    except Exception as e:
        _pw_status["ok"] = False
        _pw_status["error"] = (str(e) or type(e).__name__)[:200]
        log.warning("[Playwright] get_following @%s failed: %s: %s", handle, type(e).__name__, e or '(no details)')

    log.info("[Playwright] @%s: got %d following", handle, len(following))
    return following


# ---------------------------------------------------------------------------
# HTML extraction helpers
# ---------------------------------------------------------------------------

def _extract_profile_from_html(html: str, handle: str) -> dict | None:
    """Extract profile info from IG profile page HTML."""
    bio = ""
    full_name = ""
    external_url = ""
    is_verified = False
    followers = 0
    user_id = None

    # Try to find embedded JSON data (SharedData or additional_data)
    # Instagram embeds profile data in <script> tags
    json_patterns = [
        r'"biography"\s*:\s*"([^"]*)"',
        r'"full_name"\s*:\s*"([^"]*)"',
        r'"external_url"\s*:\s*"([^"]*)"',
        r'"is_verified"\s*:\s*(true|false)',
        r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)',
        r'"follower_count"\s*:\s*(\d+)',
        r'"pk"\s*:\s*(\d+)',
        r'"id"\s*:\s*"(\d+)"',
    ]

    # Biography
    m = re.search(json_patterns[0], html)
    if m:
        bio = m.group(1).encode().decode("unicode_escape", errors="ignore")

    # Full name
    m = re.search(json_patterns[1], html)
    if m:
        full_name = m.group(1).encode().decode("unicode_escape", errors="ignore")

    # External URL
    m = re.search(json_patterns[2], html)
    if m:
        external_url = m.group(1).encode().decode("unicode_escape", errors="ignore")

    # Verified
    m = re.search(json_patterns[3], html)
    if m:
        is_verified = m.group(1) == "true"

    # Followers
    m = re.search(json_patterns[4], html)
    if m:
        followers = int(m.group(1))
    else:
        m = re.search(json_patterns[5], html)
        if m:
            followers = int(m.group(1))

    # User ID
    m = re.search(json_patterns[6], html)
    if m:
        user_id = int(m.group(1))
    else:
        m = re.search(json_patterns[7], html)
        if m:
            user_id = int(m.group(1))

    # Fallback: try meta tags
    if not bio:
        desc = _extract_meta_content(html, "og:description", "description")
        if desc:
            # IG meta description format: "X Followers, Y Following, Z Posts - See photos..."
            # The bio is after the dash
            if " - " in desc:
                bio_part = desc.split(" - ", 1)[1]
                bio = bio_part.strip()

    if not full_name:
        title = _extract_meta_content(html, "og:title")
        if title:
            # Format: "Full Name (@handle) • Instagram..."
            if "(" in title:
                full_name = title.split("(")[0].strip()

    if not bio and not full_name:
        log.debug("[Playwright] Could not extract profile data for @%s", handle)
        return None

    return {
        "bio": bio,
        "full_name": full_name,
        "external_url": external_url,
        "is_verified": is_verified,
        "followers": followers,
        "user_id": user_id,
    }


def _extract_post_from_html(html: str, post_url: str) -> dict | None:
    """Extract post data from an IG post page HTML."""
    caption = ""
    image_url = ""
    timestamp = None

    # Caption from meta or JSON
    m = re.search(r'"caption"\s*:\s*\{[^}]*"text"\s*:\s*"([^"]*)"', html)
    if m:
        caption = m.group(1).encode().decode("unicode_escape", errors="ignore")
    else:
        # Fallback: og:description
        caption = _extract_meta_content(html, "og:description", "description")

    # Image URL from meta
    image_url = _extract_meta_content(html, "og:image")

    # Timestamp
    m = re.search(r'"taken_at"\s*:\s*(\d+)', html)
    if m:
        ts = int(m.group(1))
        timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    else:
        m = re.search(r'<time[^>]+datetime="([^"]+)"', html)
        if m:
            timestamp = m.group(1)

    if not caption and not image_url:
        return None

    return {
        "post_url": post_url,
        "image_url": image_url,
        "caption": caption,
        "timestamp": timestamp,
    }


def _extract_posts_from_profile_html(html: str, handle: str, max_posts: int) -> list[dict]:
    """Extract visible post previews from an Instagram profile page HTML snapshot.

    This is a lighter fallback than opening each post page individually and is
    good enough for downstream OCR because the grid often exposes the image URL.
    """
    if not html:
        return []

    posts: list[dict] = []
    seen_shortcodes: set[str] = set()
    pattern = re.compile(
        r'"shortcode":"(?P<shortcode>[A-Za-z0-9_-]+)"'
        r'.{0,4000}?'
        r'"display_url":"(?P<image_url>https:[^"\\]+(?:\\/[^"\\]+)*)"'
        r'.{0,2500}?'
        r'(?:"taken_at_timestamp":(?P<timestamp>\d+))?'
        r'.{0,2500}?'
        r'(?:"accessibility_caption":"(?P<caption>(?:\\.|[^"\\])*)")?',
        re.DOTALL,
    )

    for match in pattern.finditer(html):
        shortcode = match.group("shortcode")
        if not shortcode or shortcode in seen_shortcodes:
            continue
        seen_shortcodes.add(shortcode)

        raw_image_url = match.group("image_url") or ""
        image_url = raw_image_url.replace("\\/", "/")
        raw_caption = match.group("caption") or ""
        caption = raw_caption.encode().decode("unicode_escape", errors="ignore")

        timestamp = None
        raw_timestamp = match.group("timestamp")
        if raw_timestamp:
            try:
                timestamp = datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                timestamp = None

        posts.append({
            "post_url": f"https://www.instagram.com/p/{shortcode}/",
            "image_url": image_url,
            "caption": caption,
            "timestamp": timestamp,
            "source": "playwright",
        })

        if len(posts) >= max_posts:
            break

    if posts:
        return posts

    link_pattern = re.compile(
        r'href="/(?:[^"/]+/)?(?P<kind>p|reel)/(?P<shortcode>[A-Za-z0-9_-]+)/"[^>]*>'
        r'.{0,2500}?'
        r'<img[^>]+src="(?P<image_url>[^"]+)"'
        r'(?:[^>]+alt="(?P<caption>[^"]*)")?',
        re.DOTALL,
    )

    for match in link_pattern.finditer(html):
        shortcode = match.group("shortcode")
        if not shortcode or shortcode in seen_shortcodes:
            continue
        seen_shortcodes.add(shortcode)

        kind = match.group("kind") or "p"
        image_url = _html.unescape(match.group("image_url") or "")
        caption = _html.unescape(match.group("caption") or "")
        posts.append({
            "post_url": f"https://www.instagram.com/{kind}/{shortcode}/",
            "image_url": image_url,
            "caption": caption,
            "timestamp": None,
            "source": "playwright",
        })

        if len(posts) >= max_posts:
            break

    return posts


def _extract_meta_content(html: str, *meta_names: str) -> str:
    """Return the first meta tag content matching any property/name, regardless of attribute order."""
    if not html or not meta_names:
        return ""

    meta_tags = re.findall(r"<meta\b[^>]*>", html, flags=re.IGNORECASE)
    for tag in meta_tags:
        for attr_name in ("property", "name"):
            for meta_name in meta_names:
                attr_pattern = rf'\b{attr_name}\s*=\s*["\']{re.escape(meta_name)}["\']'
                if not re.search(attr_pattern, tag, flags=re.IGNORECASE):
                    continue

                content_match = re.search(r'\bcontent\s*=\s*["\']([^"\']*)["\']', tag, flags=re.IGNORECASE)
                if content_match:
                    return _html.unescape(content_match.group(1)).strip()

    return ""


# ---------------------------------------------------------------------------
# Session Export / Import (for syncing sessions between local ↔ server)
# ---------------------------------------------------------------------------

import tarfile as _tarfile
import io as _io
import shutil as _shutil


def pw_export_session(username: str) -> bytes | None:
    """
    Export a Playwright session profile as a tar.gz blob.
    Returns bytes of the archive, or None if no profile exists.
    """
    profile_dir = _SESSION_DIR / f"chromium_{username}"
    if not profile_dir.exists():
        log.warning("[SessionExport] No profile found for @%s at %s", username, profile_dir)
        return None

    buf = _io.BytesIO()
    with _tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(profile_dir), arcname=f"chromium_{username}")
    buf.seek(0)
    log.info("[SessionExport] Exported profile for @%s (%d bytes)", username, buf.getbuffer().nbytes)
    return buf.getvalue()


def pw_rename_profile(old_username: str, new_username: str) -> dict:
    """Rename the on-disk Playwright profile when an account username changes."""
    old_profile_dir = _SESSION_DIR / f"chromium_{old_username}"
    new_profile_dir = _SESSION_DIR / f"chromium_{new_username}"

    if old_username == new_username:
        return {"success": True, "renamed": False}
    if not old_profile_dir.exists():
        return {"success": True, "renamed": False}
    if new_profile_dir.exists():
        return {
            "success": False,
            "error": f"Target profile for @{new_username} already exists.",
        }

    try:
        old_profile_dir.rename(new_profile_dir)
        log.info("[SessionRename] Renamed profile @%s -> @%s", old_username, new_username)
        return {"success": True, "renamed": True}
    except Exception as exc:
        log.error("[SessionRename] Failed to rename @%s -> @%s: %s", old_username, new_username, exc)
        return {"success": False, "error": str(exc)}


def pw_import_session(username: str, data: bytes) -> dict:
    """
    Import a Playwright session profile from a tar.gz blob.
    Replaces any existing profile for the given username.
    Returns dict with status info.
    """
    profile_dir = _SESSION_DIR / f"chromium_{username}"
    expected_arcname = f"chromium_{username}"

    try:
        buf = _io.BytesIO(data)
        with _tarfile.open(fileobj=buf, mode="r:gz") as tar:
            # Security: check all members are under the expected directory
            members = tar.getmembers()
            if not members:
                return {"success": False, "error": "Empty archive"}

            for m in members:
                if not m.name.startswith(expected_arcname):
                    return {"success": False, "error": f"Unexpected path in archive: {m.name}"}
                # Prevent path traversal
                if ".." in m.name:
                    return {"success": False, "error": f"Path traversal detected: {m.name}"}

            # Kill any orphan chrome processes using this profile
            _kill_orphan_chromes(profile_dir)

            # Remove old profile
            if profile_dir.exists():
                _shutil.rmtree(profile_dir, ignore_errors=True)
                log.info("[SessionImport] Removed old profile for @%s", username)

            # Extract
            tar.extractall(path=str(_SESSION_DIR))
            log.info("[SessionImport] Imported profile for @%s (%d members, %d bytes)",
                     username, len(members), len(data))

        return {"success": True, "message": f"Session imported for @{username}",
                "profile_dir": str(profile_dir), "members": len(members)}

    except _tarfile.TarError as e:
        log.error("[SessionImport] Invalid tar.gz for @%s: %s", username, e)
        return {"success": False, "error": f"Invalid archive: {e}"}
    except Exception as e:
        log.error("[SessionImport] Import failed for @%s: %s", username, e)
        return {"success": False, "error": str(e)}


def pw_import_cookies(username: str, cookies: list[dict]) -> dict:
    """
    Import browser cookies into a Playwright persistent profile.
    This creates/updates the Chromium profile so that subsequent launches
    will have a valid IG session — without ever needing to login from
    this machine.

    *cookies* should be a list of dicts, each with at least:
        {name, value, domain, path}
    Typically exported from a browser extension like "Cookie-Editor" or
    Chrome DevTools.

    Returns dict with status info.
    """
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    profile_dir = _SESSION_DIR / f"chromium_{username}"

    # Normalise cookies into Playwright format
    pw_cookies: list[dict] = []
    required_found = set()
    IMPORTANT_NAMES = {"sessionid", "ds_user_id", "csrftoken"}

    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if not name or not value:
            continue

        domain = c.get("domain", ".instagram.com")
        # strip leading dot for Playwright if needed — PW accepts both forms
        pw_cookie: dict = {
            "name": name,
            "value": value,
            "domain": domain if domain else ".instagram.com",
            "path": c.get("path", "/"),
        }
        # Optional fields
        if c.get("httpOnly") is not None:
            pw_cookie["httpOnly"] = bool(c["httpOnly"])
        if c.get("secure") is not None:
            pw_cookie["secure"] = bool(c["secure"])
        if c.get("sameSite"):
            ss = str(c["sameSite"]).capitalize()
            if ss in ("Strict", "Lax", "None"):
                pw_cookie["sameSite"] = ss

        pw_cookies.append(pw_cookie)
        if name in IMPORTANT_NAMES:
            required_found.add(name)

    # Validate: must have sessionid + ds_user_id at minimum
    missing = {"sessionid", "ds_user_id"} - required_found
    if missing:
        return {"success": False, "error": f"Missing required cookies: {', '.join(sorted(missing))}. "
                "Make sure you export ALL cookies from instagram.com."}

    log.info("[CookieImport] Importing %d cookies for @%s (has: %s)",
             len(pw_cookies), username, ", ".join(sorted(required_found)))

    # Launch a temporary persistent context, inject cookies, then close.
    # This writes the cookies into the Chromium profile on disk.
    try:
        from playwright.sync_api import sync_playwright

        original_policy = None
        if sys.platform == "win32":
            original_policy = asyncio.get_event_loop_policy()
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        try:
            pw = sync_playwright().start()
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=True,
                args=["--disable-blink-features=AutomationControlled",
                      "--disable-dev-shm-usage", "--no-sandbox"],
            )

            # Inject cookies
            ctx.add_cookies(pw_cookies)

            # Quick verification: check cookies were stored
            stored = ctx.cookies("https://www.instagram.com")
            stored_names = {c["name"] for c in stored}
            has_session = "sessionid" in stored_names and "ds_user_id" in stored_names

            # Persist cookies to a sidecar JSON file.
            # Chromium's add_cookies() may NOT flush to the profile
            # directory on disk, so a subsequent launch_persistent_context
            # loses them.  We write them ourselves and re-inject on
            # every _PlaywrightBrowser.__enter__().
            import json as _json
            cookie_file = profile_dir / "imported_cookies.json" if isinstance(profile_dir, Path) else Path(profile_dir) / "imported_cookies.json"
            cookie_file.write_text(_json.dumps(pw_cookies, ensure_ascii=False, indent=2), encoding="utf-8")
            log.info("[CookieImport] Saved %d cookies to %s", len(pw_cookies), cookie_file)

            ctx.close()
            pw.stop()
        finally:
            if original_policy is not None:
                asyncio.set_event_loop_policy(original_policy)

        if not has_session:
            return {"success": False, "error": "Cookies were injected but sessionid/ds_user_id not detected in profile."}

        log.info("[CookieImport] Successfully imported %d cookies for @%s into %s",
                 len(pw_cookies), username, profile_dir)
        return {
            "success": True,
            "message": f"Imported {len(pw_cookies)} cookies for @{username}",
            "cookies_count": len(pw_cookies),
            "has_sessionid": "sessionid" in required_found,
            "has_ds_user_id": "ds_user_id" in required_found,
            "has_csrftoken": "csrftoken" in required_found,
        }

    except Exception as e:
        log.error("[CookieImport] Failed for @%s: %s", username, e)
        return {"success": False, "error": str(e)}
