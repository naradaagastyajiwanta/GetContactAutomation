"""
Social Profiler Agent — discovers social-media accounts for a PIC.
Uses Google dorking via DDG, university website scraping, handle-variant
generation, Instagram direct lookup (Playwright), and page-level
verification to maximize discovery rate and accuracy.
"""

from __future__ import annotations

import asyncio
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

    # ── 2b. Instagram handle-variant discovery ─────────────────────────
    if not result.instagram_handle:
        ig_handle = await _discover_instagram_handle(
            full_name, name_variants, uni_name, nidn,
        )
        if ig_handle:
            result.instagram_handle = ig_handle
            sources.append("ig_handle_variant")
            log.info("[SocialProfiler] Found instagram via handle variant: %s", ig_handle)

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

    # For LinkedIn, use full name + university (most precise)
    queries: dict[str, list[str]] = {
        "linkedin": [
            f'site:linkedin.com/in "{primary}" "{uni_name}"',
            f'site:linkedin.com/in "{alt}" "{uni_name}"',
            f'site:linkedin.com/in "{primary}" dosen OR professor OR lecturer',
        ],
        "instagram": [
            f'"{primary}" instagram "{uni_name}"',
            f'site:instagram.com "{primary}"',
            f'site:instagram.com "{alt}"',
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
    """Pick the most likely matching URL from search results.

    Scoring prioritizes LAST NAME matches (much more distinctive than
    common first names like "Samuel", "Andi", "Muhammad", etc.).
    For LinkedIn/Instagram, requires the last name to appear in URL or snippet.
    """
    if not hits:
        return None

    # Build matching tokens; distinguish first vs last name
    name_parts_raw = full_name.strip().lower().split()
    name_parts = [p for p in name_parts_raw if len(p) > 2]
    # Last name(s) are the most distinctive identifiers
    last_name = name_parts[-1] if name_parts else ""
    first_name = name_parts[0] if name_parts else ""

    all_tokens = set()
    for variant in name_variants:
        for part in variant.lower().split():
            if len(part) > 2:
                all_tokens.add(part)

    best_url = None
    best_score = 0

    for hit in hits:
        url = hit.get("link", "") or hit.get("href", "") or hit.get("url", "")
        snippet = (hit.get("snippet", "") or hit.get("body", "")).lower()
        title = (hit.get("title", "") or "").lower()

        if not url:
            continue

        # ---------- Platform-specific URL filtering ----------
        if platform == "linkedin":
            if "/in/" not in url and "/pub/" not in url:
                continue
        elif platform == "instagram":
            if "instagram.com" not in url:
                continue
            if re.search(r'instagram\.com/(p|reel|reels|explore|stories|tv)/', url):
                continue
        elif platform == "facebook":
            if "facebook.com" not in url:
                continue
        elif platform == "twitter":
            if "twitter.com" not in url and "x.com" not in url:
                continue
            if "/status/" in url:
                continue

        # ---------- Scoring ----------
        combined_text = f"{title} {snippet} {url.lower()}"
        url_lower = url.lower()

        score = 0
        has_last_name = last_name and last_name in combined_text
        has_first_name = first_name and first_name in combined_text
        last_in_url = last_name and last_name in url_lower

        # Base: count matching tokens
        score += sum(1 for t in all_tokens if t in combined_text)

        # Heavy bonus: last name in URL (very strong signal)
        if last_in_url:
            score += 5
        # Bonus: last name in snippet/title
        elif has_last_name:
            score += 3

        # For LinkedIn: REQUIRE last name somewhere (avoid "jo-samuel" ≠ Kristiyana)
        if platform == "linkedin" and len(name_parts) >= 2:
            if not has_last_name:
                continue  # Skip this result entirely

        # Penalty: only first name matches (common names give false positives)
        if has_first_name and not has_last_name and len(name_parts) >= 2:
            score = max(score - 3, 0)

        if score > best_score:
            best_score = score
            best_url = url

    # Minimum score thresholds
    if len(name_parts) <= 1:
        min_score = 2
    elif platform == "linkedin":
        min_score = 4  # Stricter for LinkedIn (must have last name)
    else:
        min_score = 2

    return best_url if best_score >= min_score else None


def _set_platform(result: SocialProfileResult, platform: str, url: str) -> None:
    """Set the appropriate platform field on the result."""
    if platform == "linkedin":
        result.linkedin_url = url
    elif platform == "instagram":
        # Extract handle but skip non-profile paths
        m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", url)
        if m:
            handle = m.group(1)
            # Skip common non-profile segments
            skip = {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "about", "directory"}
            if handle.lower() not in skip:
                result.instagram_handle = handle
            else:
                return  # Don't set anything
        else:
            result.instagram_handle = url
    elif platform == "facebook":
        result.facebook_url = url
    elif platform == "twitter":
        m = re.search(r"(?:twitter|x)\.com/([A-Za-z0-9_]+)", url)
        if m:
            handle = m.group(1)
            skip = {"search", "explore", "hashtag", "intent", "i", "home"}
            if handle.lower() not in skip:
                result.twitter_handle = handle
            else:
                return
        else:
            result.twitter_handle = url


async def _verify_and_enrich(
    result: SocialProfileResult,
    full_name: str,
    sources: list[str],
) -> None:
    """Fetch found profile pages to verify & extract additional data."""
    name_lower = full_name.lower()
    name_parts = [p for p in name_lower.split() if len(p) > 2]

    # For single-word names, require stricter matching
    is_single_name = len(name_parts) <= 1

    def _name_matches(text: str) -> bool:
        text_lower = text.lower()
        if is_single_name:
            # Single name: require exact word match (not just substring)
            import re as _re
            return bool(_re.search(r'\b' + _re.escape(name_lower.strip()) + r'\b', text_lower))
        else:
            # Multi-word: require at least half the name parts to match
            matched = sum(1 for p in name_parts if p in text_lower)
            return matched >= max(len(name_parts) // 2, 1)

    # Verify LinkedIn — stricter: require LAST NAME on page
    if result.linkedin_url:
        html = await fetch_page(result.linkedin_url)
        if html:
            text = extract_text_from_html(html, max_chars=3000)
            text_lower = text.lower()
            # For multi-word names, require last name present
            if len(name_parts) >= 2:
                if name_parts[-1] not in text_lower:
                    log.info("[SocialProfiler] LinkedIn URL missing last name '%s', removing", name_parts[-1])
                    result.linkedin_url = None
                    if "dork_linkedin" in sources:
                        sources.remove("dork_linkedin")
                else:
                    sources.append("linkedin_verified")
            elif not _name_matches(text):
                log.info("[SocialProfiler] LinkedIn URL doesn't match name, removing")
                result.linkedin_url = None
                if "dork_linkedin" in sources:
                    sources.remove("dork_linkedin")
            else:
                sources.append("linkedin_verified")

    # Verify Facebook — also look for linked Instagram
    if result.facebook_url:
        html = await fetch_page(result.facebook_url)
        if html:
            text = extract_text_from_html(html, max_chars=3000)
            if not _name_matches(text):
                log.info("[SocialProfiler] Facebook URL doesn't match name, removing")
                result.facebook_url = None
                if "dork_facebook" in sources:
                    sources.remove("dork_facebook")
            else:
                # Check if Facebook page links to an Instagram
                if not result.instagram_handle:
                    socials = extract_social_links(html)
                    ig_url = socials.get("instagram", "")
                    if ig_url:
                        m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", ig_url)
                        if m and m.group(1).lower() not in {
                            "p", "reel", "reels", "explore", "stories",
                        }:
                            result.instagram_handle = m.group(1)
                            sources.append("ig_from_facebook")
                            log.info(
                                "[SocialProfiler] Found IG from Facebook: %s",
                                result.instagram_handle,
                            )


# ---------------------------------------------------------------------------
# Instagram handle-variant discovery
# ---------------------------------------------------------------------------

def _generate_ig_handle_variants(full_name: str) -> list[str]:
    """Generate plausible IG handle variants from a person's name.

    e.g. "Samuel Kristiyana" → [
        "samuelkristiyana", "samuel.kristiyana", "samuel_kristiyana",
        "kristiyanasamuel", "kristiyana.samuel", "s.kristiyana",
        "samuel.k", "samkristiyana",
    ]
    """
    parts = [p.lower() for p in full_name.strip().split() if len(p) > 1]
    # Remove academic titles
    titles = {"prof", "dr", "ir", "drs", "dra", "phd"}
    parts = [p.strip(".,") for p in parts if p.strip(".,") not in titles]
    if not parts:
        return []

    variants: list[str] = []
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        # Most common patterns on Indonesian IG
        variants.extend([
            f"{first}{last}",              # samuelkristiyana
            f"{first}.{last}",             # samuel.kristiyana
            f"{first}_{last}",             # samuel_kristiyana
            f"{last}{first}",              # kristiyanasamuel
            f"{last}.{first}",             # kristiyana.samuel
            f"{last}_{first}",             # kristiyana_samuel
            f"{first[0]}.{last}",          # s.kristiyana
            f"{first[0]}{last}",           # skristiyana
            f"{first}.{last[0]}",          # samuel.k
            f"{first}{last[0]}",           # samuelk
        ])
        # If there's a middle name
        if len(parts) >= 3:
            mid = parts[1]
            variants.extend([
                f"{first}.{mid}.{last}",   # samuel.middle.kristiyana
                f"{first}{mid}{last}",     # samuelmiddlekristiyana
            ])
    elif len(parts) == 1:
        variants.append(parts[0])

    return list(dict.fromkeys(variants))  # Deduplicate


async def _discover_instagram_handle(
    full_name: str,
    name_variants: list[str],
    uni_name: str,
    nidn: str | None,
) -> str | None:
    """Try to find an IG handle through multiple strategies:

    1. DDG search: "{name} instagram" (without site: restriction)
    2. Handle variant probing via Playwright (if available)
    3. Handle variant probing via DDG site:instagram.com/{variant}
    """

    name_parts = [p.lower() for p in full_name.strip().split() if len(p) > 2]
    last_name = name_parts[-1] if name_parts else ""

    # Strategy 1: DDG broad search for "name instagram"
    broad_queries = [
        f'"{full_name}" instagram',
        f'"{full_name}" @instagram',
    ]
    for q in broad_queries:
        hits = await ddg_search(q, max_results=5)
        for h in (hits or []):
            link = h.get("link", "")
            snippet = (h.get("snippet", "") or "").lower()
            title = (h.get("title", "") or "").lower()
            combined = f"{link.lower()} {snippet} {title}"

            # Look for instagram.com/handle in results
            m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", link)
            if m:
                handle = m.group(1)
                skip = {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "about", "directory"}
                if handle.lower() not in skip:
                    # Check that last name or a significant name part appears
                    if last_name and last_name in combined:
                        log.info("[SocialProfiler] IG broad search found: @%s", handle)
                        return handle

            # Look for @handle mentions in snippets
            at_matches = re.findall(r"@([A-Za-z0-9_.]{3,30})", f"{snippet} {title}")
            for at_handle in at_matches:
                at_lower = at_handle.lower()
                # Check handle contains name parts
                if any(p in at_lower for p in name_parts if len(p) > 3):
                    log.info("[SocialProfiler] IG @mention found: @%s", at_handle)
                    return at_handle

    # Strategy 2: Try Playwright direct IG profile lookup with handle variants
    handle_variants = _generate_ig_handle_variants(full_name)
    if handle_variants:
        try:
            from orchestrator.playwright_ig import pw_get_profile, is_available
            if is_available():
                for handle in handle_variants[:6]:  # Limit to avoid rate limiting
                    try:
                        profile = await asyncio.get_event_loop().run_in_executor(
                            None, pw_get_profile, handle,
                        )
                        if profile and profile.get("full_name"):
                            profile_name = profile["full_name"].lower()
                            # Verify: profile's full_name must contain last name
                            if last_name and last_name in profile_name:
                                log.info(
                                    "[SocialProfiler] IG Playwright verified: @%s (%s)",
                                    handle, profile["full_name"],
                                )
                                return handle
                    except Exception:
                        continue  # Skip failed lookups
        except ImportError:
            pass  # Playwright not available

    # Strategy 3: DDG probe handle variants
    for handle in handle_variants[:5]:
        hits = await ddg_search(f"site:instagram.com/{handle}", max_results=1)
        if hits:
            link = hits[0].get("link", "")
            if f"instagram.com/{handle}" in link.lower():
                # Verify via snippet/title
                snippet = (hits[0].get("snippet", "") or "").lower()
                title = (hits[0].get("title", "") or "").lower()
                combined = f"{snippet} {title} {link.lower()}"
                if any(p in combined for p in name_parts if len(p) > 3):
                    log.info("[SocialProfiler] IG DDG variant found: @%s", handle)
                    return handle

    return None
