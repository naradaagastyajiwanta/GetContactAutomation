"""
Social Intel Agent — discovers social media accounts for the university.

Skips platforms already known (IG, BEM IG) from DB.
Focuses on finding: Facebook, YouTube, LinkedIn, Twitter/X, TikTok.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.osint.state import OsintState, SocialIntelResult, SocialMediaEntry
from orchestrator.osint.tools import (
    ddg_search,
    fetch_page,
    extract_social_links,
)


async def social_intel_agent(state: OsintState) -> dict:
    """
    Discover social media accounts for the university.

    Returns partial state update with `social_intel`.
    """
    uni = state.get("university_data", {})
    uni_name = state.get("university_name", uni.get("name", ""))
    website = uni.get("website", "")
    existing_social = state.get("existing_social", [])

    log.info("[SocialIntel] Starting for %s", uni_name)

    # Build set of already-known platforms
    known_platforms = set()
    for s in existing_social:
        known_platforms.add(s.get("platform", "").lower())

    # Also mark instagram as known if ig_handle exists
    if uni.get("ig_handle"):
        known_platforms.add("instagram")

    accounts: list[SocialMediaEntry] = []

    # ── 1. Extract from university website footer/header ───────────────
    if website:
        html = await fetch_page(website)
        if html:
            social_links = extract_social_links(html)
            for platform, urls in social_links.items():
                if platform.lower() not in known_platforms:
                    # Iterate over all URLs found for this platform
                    for url in urls:
                        handle = _extract_handle(url, platform)
                        accounts.append(SocialMediaEntry(
                            platform=platform,
                            handle=handle or url,
                            url=url,
                            confidence=0.8,
                            source=website,
                        ))
                        log.info("[SocialIntel] Found %s from website: %s", platform, url)
                    known_platforms.add(platform.lower())

    # ── 2. DDG search for each missing platform ────────────────────────
    search_targets = {
        "facebook": f'"{uni_name}" facebook page official site:facebook.com',
        "youtube": f'"{uni_name}" youtube channel resmi site:youtube.com',
        "linkedin": f'"{uni_name}" site:linkedin.com/company',
        "twitter": f'"{uni_name}" official site:twitter.com OR site:x.com',
        "tiktok": f'"{uni_name}" tiktok official site:tiktok.com',
    }

    for platform, query in search_targets.items():
        if platform in known_platforms:
            continue

        results = await ddg_search(query, max_results=3)
        if results:
            best = results[0]
            url = best.get("link", "")
            if _is_valid_social_url(url, platform):
                handle = _extract_handle(url, platform)
                accounts.append(SocialMediaEntry(
                    platform=platform,
                    handle=handle or url,
                    url=url,
                    confidence=0.6,
                    source="ddg_search",
                ))
                known_platforms.add(platform)
                log.info("[SocialIntel] Found %s via DDG: %s", platform, url)

    log.info("[SocialIntel] Done for %s: %d new accounts found", uni_name, len(accounts))
    return {"social_intel": SocialIntelResult(accounts=accounts)}


def _extract_handle(url: str, platform: str) -> str | None:
    """Extract handle/username from a social media URL."""
    import re
    patterns = {
        "facebook": r'facebook\.com/([^/?#]+)',
        "twitter": r'(?:twitter|x)\.com/([^/?#]+)',
        "youtube": r'youtube\.com/(?:@|channel/|c/)([^/?#]+)',
        "linkedin": r'linkedin\.com/(?:company|in)/([^/?#]+)',
        "tiktok": r'tiktok\.com/@([^/?#]+)',
        "instagram": r'instagram\.com/([^/?#]+)',
    }
    pattern = patterns.get(platform)
    if pattern:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _is_valid_social_url(url: str, platform: str) -> bool:
    """Check if a URL is a valid social media profile URL."""
    platform_domains = {
        "facebook": "facebook.com",
        "twitter": ("twitter.com", "x.com"),
        "youtube": "youtube.com",
        "linkedin": "linkedin.com",
        "tiktok": "tiktok.com",
    }
    domains = platform_domains.get(platform)
    if not domains:
        return False
    if isinstance(domains, str):
        domains = (domains,)
    return any(d in url.lower() for d in domains)
