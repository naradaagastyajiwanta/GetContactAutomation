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
from urllib.parse import urlparse

from orchestrator.config import log
from orchestrator.crm.state import CrmState, SocialProfileResult
from orchestrator.crm.name_utils import strip_academic_titles, ai_strip_titles, build_name_variants as _central_name_variants
from orchestrator.crm.tools import (
    ddg_search,
    ddg_search,
    fetch_page,
    extract_social_links,
    extract_text_from_html,
    extract_emails,
    extract_phones_from_text,
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

    # Use AI for name cleaning, with state cache or centralized fallback
    cleaned_name = state.get("cleaned_name") or await ai_strip_titles(pic_name)
    central_variants = state.get("name_variants") or _central_name_variants(pic_name)
    # Merge central variants with local variants for social-specific needs
    name_variants = _build_name_variants(full_name)
    # Prepend cleaned name and central variants (dedup)
    seen = set()
    merged_variants: list[str] = []
    for v in central_variants + name_variants:
        v_lower = v.lower().strip()
        if v_lower and v_lower not in seen:
            seen.add(v_lower)
            merged_variants.append(v)
    name_variants = merged_variants

    log.info("[SocialProfiler] Starting for %s (variants: %s)", full_name, name_variants[:5])

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
    platform_queries = await _ai_build_dork_queries(full_name, name_variants, uni_name, nidn)

    for platform, queries in platform_queries.items():
        # Inject standard DuckDuckGo-friendly broad search
        queries.append(f'"{full_name}" {platform}')
        primary = name_variants[0] if name_variants else full_name
        queries.append(f'{primary} {platform}')

        for query in queries:
            # Prefer Serper (Google Search) for social networks due to better dynamic indexing of LI/IG
            hits = await ddg_search(query, max_results=3)
            if not hits:
                # Fallback to DDG if Serper fails or has no hits
                hits = await ddg_search(query, max_results=3)

            url = await _ai_pick_best_url(hits, full_name, name_variants, platform, uni_name)
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
        scholar_queries = [
            f'site:scholar.google.com "{full_name}" "{uni_name}"',
            f'site:scholar.google.com "{full_name}"',
        ]
        for sq in scholar_queries:
            if result.other_social.get("google_scholar"):
                break
            scholar_hits = await ddg_search(sq, max_results=3)
            # Collect scholar-specific hits for AI evaluation
            scholar_candidates = [
                sh for sh in (scholar_hits or [])
                if "scholar.google" in sh.get("link", "")
            ]
            if scholar_candidates:
                hits_text = "\n".join(
                    f"[{i+1}] URL: {sh.get('link', '')}\n"
                    f"    Title: {sh.get('title', '')}\n"
                    f"    Snippet: {sh.get('snippet', '')}"
                    for i, sh in enumerate(scholar_candidates)
                )
                ai_pick = await gpt_extract_structured(
                    hits_text,
                    (
                        f"We're looking for the Google Scholar profile of:\n"
                        f"- Name: {full_name}\n"
                        f"- University: {uni_name}\n"
                        f"- NIDN: {nidn or 'unknown'}\n\n"
                        f"Which result is the correct Scholar profile for this person?\n"
                        f"Consider name match, university affiliation in snippet/title.\n"
                        f'Return JSON: {{"best_index": <1-based or null>, "reason": "..."}}'
                    ),
                )
                if ai_pick and ai_pick.get("best_index"):
                    idx = ai_pick["best_index"] - 1
                    if 0 <= idx < len(scholar_candidates):
                        result.other_social["google_scholar"] = scholar_candidates[idx]["link"]
                        sources.append("google_scholar")
                        log.info("[SocialProfiler] AI picked Scholar: %s", scholar_candidates[idx]["link"])

    if nidn and not result.other_social.get("sinta"):
        sinta_hits = await ddg_search(
            f'site:sinta.kemdikbud.go.id "{full_name}" OR "{nidn}"', max_results=3
        )
        if sinta_hits:
            sinta_candidates = [
                h for h in sinta_hits if "sinta" in h.get("link", "").lower()
            ]
            if sinta_candidates:
                hits_text = "\n".join(
                    f"[{i+1}] URL: {h.get('link', '')}\n"
                    f"    Snippet: {h.get('snippet', '')}"
                    for i, h in enumerate(sinta_candidates)
                )
                ai_pick = await gpt_extract_structured(
                    hits_text,
                    (
                        f"We're looking for the SINTA profile of:\n"
                        f"- Name: {full_name}\n"
                        f"- University: {uni_name}\n"
                        f"- NIDN: {nidn}\n\n"
                        f"Which result is the correct SINTA profile?\n"
                        f'Return JSON: {{"best_index": <1-based or null>, "reason": "..."}}'
                    ),
                )
                if ai_pick and ai_pick.get("best_index"):
                    idx = ai_pick["best_index"] - 1
                    if 0 <= idx < len(sinta_candidates):
                        result.other_social["sinta"] = sinta_candidates[idx]["link"]
                        sources.append("sinta")
                        log.info("[SocialProfiler] AI picked SINTA: %s", sinta_candidates[idx]["link"])

    # ── 4. Email & phone extraction ──────────────────────────────────
    # 4a. Scholar page → "Verified email at" 
    scholar_url = result.other_social.get("google_scholar")
    if scholar_url and not result.email:
        html = await fetch_page(scholar_url)
        if html:
            text = extract_text_from_html(html, max_chars=4000)
            # Scholar shows "Verified email at domain.ac.id"
            email_match = re.search(
                r'[Vv]erified email at\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
                text,
            )
            if email_match:
                domain = email_match.group(1)
                # Use AI to construct the most likely email address
                ai_email = await gpt_extract_structured(
                    f"Name: {full_name}\nUniversity: {uni_name}\nEmail domain: {domain}",
                    (
                        "Based on this person's name and their verified email domain from Google Scholar, "
                        "what is the most likely email address?\n"
                        "Indonesian academic email formats vary: first.last@, firstlast@, "
                        "first@, nidn@, initial.last@, etc.\n"
                        'Return JSON: {"email": "likely_email@domain"}\n'
                        "If unsure, return null."
                    ),
                )
                if ai_email and ai_email.get("email"):
                    result.email = ai_email["email"]
                    sources.append("scholar_email_ai")
                    log.info("[SocialProfiler] AI email from Scholar domain: %s", result.email)
            # Also try direct email regex on the page
            if not result.email:
                emails = extract_emails(text)
                ac_emails = [e for e in emails if ".ac.id" in e]
                if ac_emails:
                    result.email = ac_emails[0]
                    sources.append("scholar_email")

    # 4b. SINTA profile page → email
    sinta_url = result.other_social.get("sinta")
    if sinta_url and not result.email:
        html = await fetch_page(sinta_url)
        if html:
            text = extract_text_from_html(html, max_chars=4000)
            emails = extract_emails(text)
            ac_emails = [e for e in emails if ".ac.id" in e]
            if ac_emails:
                result.email = ac_emails[0]
                sources.append("sinta_email")
                log.info("[SocialProfiler] Email from SINTA: %s", result.email)

    # 4c. University staff directory → email + phone
    if uni_website and (not result.email or not result.phone):
        staff_queries = [
            f'site:{urlparse(uni_website).netloc} "{cleaned_name}" email OR kontak OR telepon',
            f'site:{urlparse(uni_website).netloc} "{cleaned_name}"',
        ]
        for sq in staff_queries:
            if result.email and result.phone:
                break
            staff_hits = await ddg_search(sq, max_results=3)
            for sh in (staff_hits or []):
                link = sh.get("link", "")
                if not link:
                    continue
                staff_html = await fetch_page(link)
                if not staff_html:
                    continue
                staff_text = extract_text_from_html(staff_html, max_chars=5000)
                # Verify name appears on page
                if not any(p in staff_text.lower() for p in [p.lower() for p in cleaned_name.split() if len(p) > 2]):
                    continue
                if not result.email:
                    emails = extract_emails(staff_text)
                    ac_emails = [e for e in emails if ".ac.id" in e or cleaned_name.split()[-1].lower() in e.lower()]
                    if ac_emails:
                        result.email = ac_emails[0]
                        sources.append("staff_directory_email")
                        log.info("[SocialProfiler] Email from staff directory: %s", result.email)
                if not result.phone:
                    phones = extract_phones_from_text(staff_text)
                    if phones:
                        result.phone = phones[0]
                        sources.append("staff_directory_phone")
                        log.info("[SocialProfiler] Phone from staff directory: %s", result.phone)
                if result.email or result.phone:
                    break

    # 4d. DDG search for email (broad)
    if not result.email:
        email_queries = [
            f'"{cleaned_name}" email "@" "{uni_name}"',
            f'"{cleaned_name}" "@" ".ac.id"',
        ]
        if nidn:
            email_queries.append(f'"{nidn}" email')
        for eq in email_queries:
            if result.email:
                break
            hits = await ddg_search(eq, max_results=3)
            for h in (hits or []):
                snippet = h.get("snippet", "") or ""
                emails = extract_emails(snippet)
                ac_emails = [e for e in emails if ".ac.id" in e]
                if ac_emails:
                    result.email = ac_emails[0]
                    sources.append("ddg_email")
                    log.info("[SocialProfiler] Email from DDG: %s", result.email)
                    break

    # ── 5. Verify & enrich found profiles (fetch page to confirm) ──────
    await _verify_and_enrich(result, full_name, uni_name, sources)

    # ── Source URLs (social profiles are self-sourcing) ───────────────
    if result.linkedin_url:
        result.source_urls["linkedin_url"] = [result.linkedin_url]
    if result.instagram_handle:
        result.source_urls["instagram_handle"] = [f"https://instagram.com/{result.instagram_handle}"]
    if result.facebook_url:
        result.source_urls["facebook_url"] = [result.facebook_url]
    if result.twitter_handle:
        result.source_urls["twitter_handle"] = [f"https://x.com/{result.twitter_handle}"]
    if result.email:
        email_source_urls = []
        if result.other_social.get("google_scholar"):
            email_source_urls.append(result.other_social["google_scholar"])
        if result.other_social.get("sinta"):
            email_source_urls.append(result.other_social["sinta"])
        result.source_urls["email"] = email_source_urls or ["staff_directory"]
    if result.phone:
        result.source_urls["phone"] = ["staff_directory"]
    for key in ("google_scholar", "sinta"):
        url = result.other_social.get(key)
        if url:
            result.source_urls[key] = [url]

    # ── Confidence ─────────────────────────────────────────────────────
    main_platforms = sum([
        bool(result.linkedin_url), bool(result.instagram_handle),
        bool(result.facebook_url), bool(result.twitter_handle),
        bool(result.email), bool(result.phone),
    ])
    extra_platforms = len([v for k, v in result.other_social.items() if v and not k.startswith("university_")])
    filled = main_platforms + min(extra_platforms, 2)  # Cap extra at 2
    result.confidence = round(min(filled / 6, 1.0), 2)
    result.sources = sources

    log.info(
        "[SocialProfiler] Done for %s: found=%d main + %d extra, confidence=%.2f",
        full_name, main_platforms, extra_platforms, result.confidence,
    )
    return {"social_profile": result}


def _build_name_variants(full_name: str) -> list[str]:
    """Build search-friendly name variants (social-profiler-specific)."""
    from orchestrator.crm.name_utils import ACADEMIC_TITLES

    parts = full_name.strip().split()
    variants = [full_name]

    if len(parts) >= 2:
        # "WIDODO SETIYO" → also try "Widodo Setiyo"
        variants.append(" ".join(p.title() for p in parts))
        # Try without titles (uses comprehensive centralized list)
        cleaned = [p for p in parts if p.lower().strip(",. ") not in ACADEMIC_TITLES
                   and (p.lower().strip(",. ") + ".") not in ACADEMIC_TITLES]
        if cleaned and " ".join(cleaned) != full_name:
            variants.append(" ".join(cleaned))

    # First + Last name (skip middle)
    if len(parts) >= 3:
        variants.append(f"{parts[0]} {parts[-1]}")

    return list(dict.fromkeys(variants))  # Deduplicate preserving order


async def _ai_build_dork_queries(
    full_name: str,
    name_variants: list[str],
    uni_name: str,
    nidn: str | None,
) -> dict[str, list[str]]:
    """Use AI to intelligently build Google-dork queries per platform."""
    primary = name_variants[0] if name_variants else full_name
    alt = name_variants[1] if len(name_variants) > 1 else primary

    prompt = f"""Generate effective Google Search dork queries to find the social media profiles for a specific person. If University is None or Unknown, DO NOT add words like dosen or lecturer to the search queries.

Person Info:
- Full Name: {full_name}
- Name Variants: {', '.join(name_variants[:3])}
- University: {uni_name}
- NIDN: {nidn or 'Unknown'}

Platforms required: linkedin, instagram, facebook, twitter

Rules for the queries:
1. Try to DO NOT use strict exact match quotes around the university name (leave it as plain text for semantic search) unless absolutely necessary.
2. DO NOT use strict exact match quotes around the full name if the name has more than 3 words. Use the primary matching elements or title.
3. For LinkedIn, use `site:linkedin.com/in` or just `site:linkedin.com`.
4. For Instagram, use `site:instagram.com`.
5. For Facebook, use `site:facebook.com`.
6. For Twitter, use `site:twitter.com OR site:x.com`.
7. Generate exactly 3 progressively looser queries for each platform (from most specific via NIDN/name+univ, to just Name+Univ loosely, to Name+Role).

Return a JSON object with keys "linkedin", "instagram", "facebook", and "twitter", each containing an array of 3 string queries.
"""
    try:
        from orchestrator.crm.tools import gpt_extract_structured
        result = await gpt_extract_structured("", prompt)
        if result and all(k in result for k in ["linkedin", "instagram", "facebook", "twitter"]):
            log.info("[SocialProfiler] AI successfully generated dork queries for %s", full_name)
            return result
    except Exception as e:
        log.warning("[SocialProfiler] AI query generation failed: %s. Falling back to default.", e)

    # Fallback to loose manual queries
    queries: dict[str, list[str]] = {
        "linkedin": [
            f'site:linkedin.com/in "{primary}" {uni_name}',
            f'site:linkedin.com/in "{alt}" {uni_name}',
            f'site:linkedin.com/in "{primary}" dosen OR professor',
        ],
        "instagram": [
            f'"{primary}" instagram {uni_name}',
            f'site:instagram.com "{primary}"',
            f'site:instagram.com "{alt}"',
        ],
        "facebook": [
            f'site:facebook.com "{primary}" {uni_name}',
            f'site:facebook.com "{alt}" dosen OR professor',
            f'site:facebook.com "{primary}"',
        ],
        "twitter": [
            f'site:twitter.com OR site:x.com "{primary}" {uni_name}',
            f'site:twitter.com OR site:x.com "{alt}"',
            f'site:twitter.com OR site:x.com "{primary}" dosen',
        ],
    }

    if nidn:
        queries["linkedin"].insert(0, f'site:linkedin.com {nidn}')
        queries["facebook"].insert(0, f'{nidn} site:facebook.com')

    return queries


async def _ai_pick_best_url(
    hits: list[dict] | None,
    full_name: str,
    name_variants: list[str],
    platform: str,
    uni_name: str = "",
) -> str | None:
    """Use AI to pick the most likely correct profile URL from search results.

    Instead of manual scoring with heuristics, AI evaluates all candidates
    together and makes a judgment call considering name, university, role, etc.
    """
    if not hits:
        return None

    # Pre-filter to platform-relevant URLs only
    relevant_hits = []
    for hit in hits:
        url = hit.get("link", "") or hit.get("href", "") or hit.get("url", "")
        if not url:
            continue
        if platform == "linkedin" and "linkedin.com" not in url:
            continue
        if platform == "instagram" and "instagram.com" not in url:
            continue
        if platform == "facebook" and "facebook.com" not in url:
            continue
        if platform == "twitter" and "twitter.com" not in url and "x.com" not in url:
            continue
        # Skip non-profile URLs
        if platform == "instagram" and re.search(r'instagram\.com/(p|reel|reels|explore|stories|tv)/', url):
            continue
        if platform == "twitter" and "/status/" in url:
            continue
        if platform == "linkedin":
            if "/in/" not in url and "/pub/" not in url:
                # If it's a post url, extract the profile part!
                m = re.search(r"linkedin\.com/(?:posts|pulse|in)/([A-Za-z0-9-]+)", url)
                if m:
                    # override url with the inferred profile
                    url = f"https://www.linkedin.com/in/{m.group(1)}/"
                    hit["link"] = url
                else:
                    continue
        relevant_hits.append(hit)

    if not relevant_hits:
        return None

    # Format hits for AI evaluation
    hits_text = ""
    for i, hit in enumerate(relevant_hits):
        url = hit.get("link", "") or hit.get("href", "") or hit.get("url", "")
        title = hit.get("title", "")
        snippet = hit.get("snippet", "") or hit.get("body", "")
        hits_text += f"\n[{i+1}] URL: {url}\n    Title: {title}\n    Snippet: {snippet}\n"

    ai_result = await gpt_extract_structured(
        hits_text,
        (
            f"We're looking for the PERSONAL {platform} profile of:\n"
            f"- Name: {full_name}\n"
            f"- University: {uni_name}\n"
            f"From the search results below, pick the one that MOST LIKELY "
            f"belongs to this specific person.\n"
            f"Consider:\n"
            f"- Does the name in the result match? (beware of partial matches)\n"
            f"- ALWAYS reject if the name in the URL or snippet is completely different from {full_name} (e.g. returning someone else's profile).\n"
            f"- If the URL itself contains the person's exact name slug (e.g. narada-agastya), consider it a VERY STRONG match even if the snippet is empty or says 'We cannot provide a description'.\n"
            f"- If University is provided, does it match or make sense? If University is None/Unknown, just match based on Name uniqueness!\n"
            f"- For Instagram: must be PERSONAL. REJECT if title/snippet contains 'Rumah Sakit', 'RS', 'Klinik', 'BEM', 'Hima', 'Official', 'Hospital', 'Business'\n"
            f"- For Facebook: must be the actual person, not a fan page or business\n"
            f"- ALWAYS double check if it's an institution. REJECT institution accounts.\n"
            f"- If NONE clearly match this specific person, return null.\n\n"
            f'Return JSON: {{"best_index": <1-based index or null>, "reason": "..."}}'
        ),
    )

    if ai_result and ai_result.get("best_index"):
        idx = ai_result["best_index"] - 1
        if 0 <= idx < len(relevant_hits):
            url = relevant_hits[idx].get("link", "") or relevant_hits[idx].get("href", "") or relevant_hits[idx].get("url", "")
            log.info("[SocialProfiler] AI picked %s [%d]: %s (reason: %s)",
                     platform, idx + 1, url, ai_result.get("reason", ""))
            return url

    return None


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
    uni_name: str,
    sources: list[str],
) -> None:
    """Use AI to verify found social profiles actually belong to the correct person.

    Instead of heuristic name-matching and keyword checks, AI reads the
    fetched page text and makes a judgment call about identity.
    """

    async def _ai_verify_profile(platform: str, url: str) -> bool:
        """Verify a single profile using AI. Returns True if verified."""
        html = await fetch_page(url)
        if not html:
            log.info("[SocialProfiler] %s URL unfetchable (%s), assuming valid from search.", platform, url)
            return True
        text = extract_text_from_html(html, max_chars=3000)

        # Fallback to simple name matching if page text indicates a login wall
        # or if the title contains the target name.
        if full_name.lower() in text.lower():
            return True
            
        # If it's heavily JS/Login guarded (typical IG/LinkedIn), trust the search result
        if "login" in text.lower() or "log in" in text.lower() or len(text) < 200:
            log.info("[SocialProfiler] %s URL %s appears to be a login wall, assuming valid.", platform, url)
            return True

        verification = await gpt_extract_structured(
            text,
            (
                f"Verify if this {platform} profile page belongs to:\n"
                f"- Name: {full_name}\n"
                f"- University: {uni_name}\n\n"
                f"Check:\n"
                f"1. Does the name on this page match the person we're looking for?\n"
                f"2. Is there any university or professional context? (Don't be too strict, if it's just their name it can be them)\n"
                f"3. Is this a PERSONAL profile (not a business, hospital, organization)?\n"
                f"4. Could this be a different person with a similar name?\n\n"
                f"NOTE: Social media platforms often return 'Log in' pages to bots. If the text appears to be a login page BUT their name is present, consider it a MATCH.\n\n"
                f'Return JSON: {{"is_match": true/false, "reason": "..."}}'
            ),
        )
        return bool(verification and verification.get("is_match"))

    # Verify LinkedIn
    if result.linkedin_url:
        if not await _ai_verify_profile("LinkedIn", result.linkedin_url):
            log.info("[SocialProfiler] AI rejected LinkedIn: %s", result.linkedin_url)
            result.linkedin_url = None
            if "dork_linkedin" in sources:
                sources.remove("dork_linkedin")
        else:
            sources.append("linkedin_verified")

    # Verify Instagram — skip if already AI-verified during discovery
    if result.instagram_handle and "ig_handle_variant" not in sources:
        ig_url = f"https://instagram.com/{result.instagram_handle}"
        if not await _ai_verify_profile("Instagram", ig_url):
            log.info("[SocialProfiler] AI rejected Instagram: @%s", result.instagram_handle)
            result.instagram_handle = None
            if "dork_instagram" in sources:
                sources.remove("dork_instagram")
    elif result.instagram_handle and "ig_handle_variant" in sources:
        log.info("[SocialProfiler] Skipping IG re-verification (already AI-verified): @%s", result.instagram_handle)

    # Verify Facebook — also look for linked Instagram
    if result.facebook_url:
        html = await fetch_page(result.facebook_url)
        if html:
            text = extract_text_from_html(html, max_chars=3000)
            
            # Simple match
            if full_name.lower() in text.lower() or "login" in text.lower() or "log in" in text.lower() or len(text) < 200:
                is_match = True
            else:
                verification = await gpt_extract_structured(
                    text,
                    (
                        f"Verify if this Facebook page belongs to:\n"
                        f"- Name: {full_name}\n"
                        f"- Context: Associated with {uni_name} or another role.\n\n"
                        f'Return JSON: {{"is_match": true/false, "reason": "..."}}'
                    ),
                )
                is_match = bool(verification and verification.get("is_match"))

            if not is_match:
                log.info("[SocialProfiler] AI rejected Facebook: %s", result.facebook_url)
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
        else:
            log.info("[SocialProfiler] Facebook URL unfetchable, assuming valid from search hit.")
            # We don't remove the facebook_url here, just accept it

async def _ai_generate_ig_handle_variants(full_name: str, uni_name: str = "") -> list[str]:
    """Use AI to generate plausible IG handle variants based on Indonesian naming culture.

    AI understands that Indonesian academics may use handles like:
    - Full name concatenation (samuelkristiyana)
    - Period/underscore separators (samuel.kristiyana)
    - Reversed order (kristiyana.samuel)
    - Abbreviations (s.kristiyana)
    - Nicknames + professional title context
    """
    ai_result = await gpt_extract_structured(
        f"Name: {full_name}\nUniversity: {uni_name}",
        (
            "Generate 8-12 plausible Instagram handle variants for this Indonesian academic.\n"
            "Consider:\n"
            "- Common Indonesian IG naming patterns (firstname.lastname, first_last, etc.)\n"
            "- Possible nicknames or shortened versions\n"
            "- Professional handles (may include 'dosen', 'prof', etc.)\n"
            "- Handles must be valid IG format: lowercase, letters/numbers/periods/underscores only\n"
            'Return JSON: {"handles": ["handle1", "handle2", ...]}'
        ),
    )
    if ai_result and ai_result.get("handles"):
        return ai_result["handles"]
    # Fallback to basic programmatic generation
    return _generate_ig_handle_variants_basic(full_name)


def _generate_ig_handle_variants_basic(full_name: str) -> list[str]:
    """Basic programmatic IG handle generation (fallback if AI unavailable)."""
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
    """Try to find an IG handle through multiple AI-verified strategies:

    1. DDG broad search + AI evaluation of results
    2. AI-generated handle variants + Playwright probing
    3. AI-generated handle variants + DDG probing
    """

    # Strategy 1: DDG broad search for "name instagram" — AI picks best
    broad_queries = [
        f'"{full_name}" instagram',
        f'"{full_name}" @instagram',
    ]
    all_ig_candidates: list[dict] = []
    for q in broad_queries:
        hits = await ddg_search(q, max_results=5)
        for h in (hits or []):
            link = h.get("link", "")
            snippet = h.get("snippet", "") or ""
            title = h.get("title", "") or ""
            # Extract IG handles from URLs
            m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", link)
            if m:
                handle = m.group(1)
                skip = {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "about", "directory"}
                if handle.lower() not in skip:
                    all_ig_candidates.append({
                        "handle": handle, "url": link,
                        "snippet": snippet, "title": title,
                    })
            # Also collect @handle mentions in snippets
            at_matches = re.findall(r"@([A-Za-z0-9_.]{3,30})", f"{snippet} {title}")
            for at_handle in at_matches:
                all_ig_candidates.append({
                    "handle": at_handle, "url": "",
                    "snippet": snippet, "title": title,
                })

    if all_ig_candidates:
        # Deduplicate by handle
        seen_handles: set[str] = set()
        unique_candidates: list[dict] = []
        for c in all_ig_candidates:
            h_lower = c["handle"].lower()
            if h_lower not in seen_handles:
                seen_handles.add(h_lower)
                unique_candidates.append(c)

        candidates_text = "\n".join(
            f"[{i+1}] @{c['handle']} — {c['title']}: {c['snippet'][:200]}"
            for i, c in enumerate(unique_candidates[:10])
        )
        ai_pick = await gpt_extract_structured(
            candidates_text,
            (
                f"We're looking for the PERSONAL Instagram handle of:\n"
                f"- Name: {full_name}\n"
                f"- University: {uni_name}\n\n"
                f"Which handle is most likely this person's PERSONAL Instagram?\n"
                f"Must NOT be a business, hospital, organization, or different person.\n"
                f'Return JSON: {{"best_index": <1-based or null>, "reason": "..."}}'
            ),
        )
        if ai_pick and ai_pick.get("best_index"):
            idx = ai_pick["best_index"] - 1
            if 0 <= idx < len(unique_candidates):
                handle = unique_candidates[idx]["handle"]
                log.info("[SocialProfiler] AI picked IG handle: @%s (reason: %s)",
                         handle, ai_pick.get("reason", ""))
                return handle

    # Strategy 2: AI-generated handle variants + Playwright probing
    handle_variants = await _ai_generate_ig_handle_variants(full_name, uni_name)
    if handle_variants:
        try:
            from orchestrator.playwright_ig import pw_get_profile, is_available
            if is_available():
                for handle in handle_variants[:6]:
                    try:
                        profile = await asyncio.get_event_loop().run_in_executor(
                            None, pw_get_profile, handle,
                        )
                        if profile and profile.get("full_name"):
                            # Use AI to verify the profile matches
                            verify = await gpt_extract_structured(
                                f"Handle: @{handle}\nProfile name: {profile['full_name']}\n"
                                f"Bio: {profile.get('biography', '')}",
                                (
                                        f"Does this Instagram profile belong to {full_name}? It might be associated with {uni_name} or some other role. Accept if name or context matches reasonably.\n"
                                    f'Return JSON: {{"is_match": true/false, "reason": "..."}}'
                                ),
                            )
                            if verify and verify.get("is_match"):
                                log.info("[SocialProfiler] IG Playwright AI-verified: @%s", handle)
                                return handle
                    except Exception:
                        continue
        except ImportError:
            pass

    # Strategy 3: DDG probe handle variants
    for handle in handle_variants[:5]:
        hits = await ddg_search(f"site:instagram.com/{handle}", max_results=1)
        if hits:
            link = hits[0].get("link", "")
            if f"instagram.com/{handle}" in link.lower():
                snippet = hits[0].get("snippet", "") or ""
                title = hits[0].get("title", "") or ""
                verify = await gpt_extract_structured(
                    f"Handle: @{handle}\nURL: {link}\nTitle: {title}\nSnippet: {snippet}",
                    (
                        f"Does this Instagram account belong to {full_name}? It might be associated with {uni_name} or some other role. Accept if name or context matches reasonably.\n"
                        f'Return JSON: {{"is_match": true/false, "reason": "..."}}'
                    ),
                )
                if verify and verify.get("is_match"):
                    log.info("[SocialProfiler] IG DDG variant AI-verified: @%s", handle)
                    return handle

    return None
