"""
ProxyPool — tiered IP rotation for Instagram scraping.

Tier 0: Cloudflare WARP instances (free, CF edge IPs)
Tier 1+: Reserved for future expansion (free public proxies, Tor, etc.)

Inspired by Crawlee's ProxyConfiguration.tiered_proxy_urls — escalates
from cheap/free proxies to paid ones on repeated failure.

Config:
  PROXY_POOL_ENABLED=true
  PROXY_POOL_WARP_URLS=socks5://warp:1080,socks5://warp2:1080
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("getcontact")

_FAILURE_COOLDOWN_SECONDS = 300  # 5-minute cooldown after failure


class _ProxyEntry:
    def __init__(self, url: str, tier: int):
        self.url = url
        self.tier = tier
        self.failures = 0
        self.last_failure: float = 0.0
        self.requests_served = 0

    def is_available(self) -> bool:
        if self.failures == 0:
            return True
        elapsed = time.monotonic() - self.last_failure
        return elapsed >= _FAILURE_COOLDOWN_SECONDS

    def mark_failed(self) -> None:
        self.failures += 1
        self.last_failure = time.monotonic()
        log.warning("[ProxyPool] %s marked failed (total: %d)", self.url[:40], self.failures)

    def mark_success(self) -> None:
        if self.failures > 0:
            self.failures = 0
            log.debug("[ProxyPool] %s recovered", self.url[:40])
        self.requests_served += 1


class ProxyPool:
    """
    Round-robin proxy pool with failure cooldown.

    Usage:
        pool = ProxyPool(warp_urls=["socks5://warp:1080", "socks5://warp2:1080"])
        proxy_cfg = pool.get_for_playwright()  # {"server": "socks5://..."} or None
    """

    def __init__(self, warp_urls: list[str]):
        self._entries: list[_ProxyEntry] = []
        for url in warp_urls:
            self._entries.append(_ProxyEntry(url, tier=0))
        self._rr_index = 0

    def get_next(self) -> str | None:
        """Get next available proxy (round-robin, skip failed/cooling down)."""
        available = [e for e in self._entries if e.is_available()]
        if not available:
            # All cooling down — use first one anyway (best effort)
            log.warning("[ProxyPool] All proxies in cooldown, using first anyway")
            available = self._entries[:1]
        if not available:
            return None
        entry = available[self._rr_index % len(available)]
        self._rr_index += 1
        return entry.url

    def get_for_playwright(self) -> dict | None:
        """
        Return Playwright-compatible proxy config dict.
        Returns None if pool is empty (no proxy = direct connection).
        """
        url = self.get_next()
        if not url:
            return None
        return {"server": url}

    def mark_failed(self, proxy_url: str) -> None:
        for e in self._entries:
            if e.url == proxy_url:
                e.mark_failed()
                return

    def mark_success(self, proxy_url: str) -> None:
        for e in self._entries:
            if e.url == proxy_url:
                e.mark_success()
                return

    def stats(self) -> list[dict]:
        return [
            {
                "url": e.url,
                "tier": e.tier,
                "failures": e.failures,
                "available": e.is_available(),
                "requests_served": e.requests_served,
            }
            for e in self._entries
        ]


# ── Singleton ─────────────────────────────────────────────────────────────────

_pool: ProxyPool | None = None


def get_proxy_pool() -> ProxyPool | None:
    """Get singleton ProxyPool built from config. Returns None if disabled."""
    global _pool
    if _pool is not None:
        return _pool

    from orchestrator.config import cfg
    if not cfg.get("PROXY_POOL_ENABLED", False):
        return None

    raw = cfg.get("PROXY_POOL_WARP_URLS", "")
    urls = [u.strip() for u in raw.split(",") if u.strip()]
    if not urls:
        return None

    _pool = ProxyPool(warp_urls=urls)
    log.info("[ProxyPool] Initialized with %d WARP proxies", len(urls))
    return _pool
