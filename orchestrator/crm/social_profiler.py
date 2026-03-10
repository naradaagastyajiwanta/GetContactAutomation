"""
Social Profiler Agent — discovers social-media accounts for a PIC.
Uses Google dorking via DDG, university website scraping, and page-level
verification to maximize discovery rate.
"""

from __future__ import annotations

import re
from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, SocialProfileResult
from orchestrator.crm.tools import (
    ddg_search,
    fetch_page,
    extract_social_links,
    extract_text_from_html,
    gpt_extract_structured,
)


async def social_profiler_agent(state: CrmState) -> dict:
    """
    Find social-media profiles for the PIC using:
    1. Google dorking via DDG (site:, intitle:, inurl:)
    2. University website scraping (footer/header social links)
    3. Page-level verification (fetch & confirm name match)

    Returns partial state update with `social_profile`.
    """
    identity = state.get("identity")
    academic = state.get("academic")
    pic_name = state.get("pic_name", "")
    uni_name = state.get("university_name", "")

    full_name = (identity.full_name if identity else None) or pic_name
    nidn = identity.nidn if identity else None
    jabatan = identity.gender if identity else None  # for query context

    # Build name variants for search
    name_variants = _build_name_variants(full_name)

    log.info("[SocialProfiler] Starting for %s (variants: %s)", full_name, name_variants[:3])

    result = SocialProfileResult()
    sources: list[str] = []

    # ── 1. University website social links ─────────────────────────────
    uni_data = state.get("university_data") or {}
    uni_website = uni_data.get("website", "")
    if not uni_website and uni_name:
        # Try to find university website via DDG
        web_hits = await ddg_search(f'"{uni_name}" official website', max_results=2)
        for h in (web_hits or []):
            link = h.get("link", "")
            if link and ".ac.id" in link:
                uni_website = link
                break

    if uni_website:
        html = await fetch_page(uni_website)
        if html:
            socials = extract_social_links(html)
            if socials:
                sources.append("university_website")
                log.info("[SocialProfiler] University social links: %s", list(socials.keys()))
                # Store as university-level social (we'll prioritize personal later)
                if socials.get("instagram") and not result.instagram_handle:
                    result.other_social["university_instagram"] = socials["instagram"]
                if socials.get("facebook") and not result.facebook_url:
                    result.other_social["university_facebook"] = socials["facebook"]

    # ── 2. Google dorking for each platform ────────────────────────────
    platform_queries = _build_dork_queries(full_name, name_variants, uni_name, nidn)

    for platform, queries in platform_queries.items():
        for query in queries:
            hits = await ddg_search(query, max_results=3)
            url = _pick_best_url(hits, full_name, name_variants, platform)
            if url:
                _set_platform(result, platform, url)
                sources.append(f"dork_{platform}")
                log.info("[SocialProfiler] Found %s: %s", platform, url)
                break  # Found this platform, move to next

    # ── 3. Google Scholar / SINTA ──────────────────────────────────────
    if not result.other_social.get("google_scholar"):
        scholar_hits = await ddg_search(
            f'site:scholar.google.com "{full_name}"', max_results=3
        )
        url = _pick_best_url(scholar_hits, full_name, name_variants, "scholar")
        if url:
            result.other_social["google_scholar"] = url
            sources.append("google_scholar")

    if nidn and not result.other_social.get("sinta"):
        sinta_hits = await ddg_search(
            f'site:sinta.kemdikbud.go.id "{full_name}" OR "{nidn}"', max_results=2
        )
        if sinta_hits:
            for h in sinta_hits:
                link = h.get("link", "")
                if "sinta" in link.lower():
                    result.other_social["sinta"] = link
                    sources.append("sinta")
                    break

    # ── 4. Verify & enrich found profiles (fetch page to confirm) ──────
    await _verify_and_enrich(result, full_name, sources)

    # ── Confidence ─────────────────────────────────────────────────────
    main_platforms = sum([
        bool(result.linkedin_url), bool(result.instagram_handle),
        bool(result.facebook_url), bool(result.twitter_handle),
    ])
    extra_platforms = len([v for k, v in result.other_social.items() if v and not k.startswith("university_")])
    filled = main_platforms + min(extra_platforms, 2)  # Cap extra at 2
    result.confidence = round(min(filled / 4, 1.0), 2)
    result.sources = sources

    log.info(
        "[SocialProfiler] Done for %s: found=%d main + %d extra, confidence=%.2f",
        full_name, main_platforms, extra_platforms, result.confidence,
    )
    return {"social_profile": result}


def _build_name_variants(full_name: str) -> list[str]:
    """Build search-friendly name variants."""
    parts = full_name.strip().split()
    variants = [full_name]

    if len(parts) >= 2:
        # "WIDODO SETIYO" → also try "Widodo Setiyo"
        variants.append(" ".join(p.title() for p in parts))
        # Try without titles
        titles = {"prof", "prof.", "dr", "dr.", "ir", "ir.", "m.si", "s.si", "m.pd", "s.pd",
                  "m.sc", "ph.d", "phd", "drs", "drs.", "m.t", "s.t"}
        cleaned = [p for p in parts if p.lower().strip(",. ") not in titles]
        if cleaned and " ".join(cleaned) != full_name:
            variants.append(" ".join(cleaned))

    # First + Last name (skip middle)
    if len(parts) >= 3:
        variants.append(f"{parts[0]} {parts[-1]}")

    return list(dict.fromkeys(variants))  # Deduplicate preserving order


def _build_dork_queries(
    full_name: str,
    name_variants: list[str],
    uni_name: str,
    nidn: str | None,
) -> dict[str, list[str]]:
    """Build Google-dork-style DDG queries per platform."""
    primary = name_variants[0]
    alt = name_variants[1] if len(name_variants) > 1 else primary

    queries: dict[str, list[str]] = {
        "linkedin": [
            f'site:linkedin.com/in "{primary}" "{uni_name}"',
            f'site:linkedin.com/in "{alt}" dosen OR professor OR lecturer',
            f'site:linkedin.com "{primary}"',
        ],
        "instagram": [
            f'site:instagram.com "{primary}" "{uni_name}"',
            f'site:instagram.com "{alt}"',
            f'inurl:instagram.com "{primary}"',
        ],
        "facebook": [
            f'site:facebook.com "{primary}" "{uni_name}"',
            f'site:facebook.com "{alt}" dosen OR professor',
            f'site:facebook.com "{primary}"',
        ],
        "twitter": [
            f'site:twitter.com OR site:x.com "{primary}" "{uni_name}"',
            f'site:twitter.com OR site:x.com "{alt}"',
        ],
    }

    # Add NIDN-based queries (very specific, high precision)
    if nidn:
        queries["linkedin"].insert(0, f'site:linkedin.com "{nidn}"')
        queries["facebook"].insert(0, f'"{nidn}" site:facebook.com')

    return queries


def _pick_best_url(
    hits: list[dict] | None,
    full_name: str,
    name_variants: list[str],
    platform: str,
) -> str | None:
    """Pick the most likely matching URL from search results."""
    if not hits:
        return None

    # Build matching tokens from all name variants
    all_tokens = set()
    for variant in name_variants:
        for part in variant.lower().split():
            if len(part) > 2:  # Skip very short parts
                all_tokens.add(part)

    best_url = None
    best_score = 0

    for hit in hits:
        # DDG returns 'link' field (not 'url' or 'href')
        url = hit.get("link", "") or hit.get("href", "") or hit.get("url", "")
        snippet = (hit.get("snippet", "") or hit.get("body", "")).lower()
        title = (hit.get("title", "") or "").lower()

        if not url:
            continue

        # Skip non-profile URLs
        if platform == "linkedin" and "/in/" not in url and "/pub/" not in url:
            if "/company/" not in url:
                continue
        if platform == "instagram" and "instagram.com" not in url:
            continue
        if platform == "facebook" and "facebook.com" not in url:
            continue

        # Score: how many name tokens match in title + snippet
        combined_text = f"{title} {snippet} {url.lower()}"
        score = sum(1 for t in all_tokens if t in combined_text)

        if score > best_score:
            best_score = score
            best_url = url

    # Require at least 1 token match (prevent random links)
    return best_url if best_score >= 1 else None


def _set_platform(result: SocialProfileResult, platform: str, url: str) -> None:
    """Set the appropriate platform field on the result."""
    if platform == "linkedin":
        result.linkedin_url = url
    elif platform == "instagram":
        m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", url)
        result.instagram_handle = m.group(1) if m else url
    elif platform == "facebook":
        result.facebook_url = url
    elif platform == "twitter":
        m = re.search(r"(?:twitter|x)\.com/([A-Za-z0-9_]+)", url)
        result.twitter_handle = m.group(1) if m else url


async def _verify_and_enrich(
    result: SocialProfileResult,
    full_name: str,
    sources: list[str],
) -> None:
    """Fetch found profile pages to verify & extract additional data."""
    name_lower = full_name.lower()

    # Verify LinkedIn
    if result.linkedin_url:
        html = await fetch_page(result.linkedin_url)
        if html:
            text = extract_text_from_html(html, max_chars=3000)
            # Check if name appears on the page
            if not any(part in text.lower() for part in name_lower.split() if len(part) > 2):
                log.info("[SocialProfiler] LinkedIn URL doesn't match name, removing")
                result.linkedin_url = None
                if "dork_linkedin" in sources:
                    sources.remove("dork_linkedin")
            else:
                sources.append("linkedin_verified")

    # Verify Facebook
    if result.facebook_url:
        html = await fetch_page(result.facebook_url)
        if html:
            text = extract_text_from_html(html, max_chars=3000)
            if not any(part in text.lower() for part in name_lower.split() if len(part) > 2):
                log.info("[SocialProfiler] Facebook URL doesn't match name, removing")
                result.facebook_url = None
                if "dork_facebook" in sources:
                    sources.remove("dork_facebook")
