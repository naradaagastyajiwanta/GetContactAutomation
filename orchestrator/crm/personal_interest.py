"""
Personal Interest Agent — discovers hobbies, interests, and personal
details from social media bios, interviews, news, scholar profiles,
and web mentions. Uses Google dorking for deeper discovery.
Best-effort — many fields may remain empty.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, PersonalInterestResult
from orchestrator.crm.tools import ddg_search, gpt_extract_structured, fetch_page, extract_text_from_html


async def personal_interest_agent(state: CrmState) -> dict:
    """
    Discover personal interests and hobbies using:
    1. Google dorking for interviews, profiles, bios
    2. Social media content (from social profiler)
    3. SINTA/Scholar profile analysis
    4. GPT extraction from all collected snippets

    Returns partial state update with `personal_interest`.
    """
    identity = state.get("identity")
    academic = state.get("academic")
    social = state.get("social_profile")
    pic_name = state.get("pic_name", "")
    uni_name = state.get("university_name", "")

    full_name = (identity.full_name if identity else None) or pic_name
    nidn = identity.nidn if identity else None

    log.info("[PersonalInterest] Starting for %s", full_name)

    snippets: list[str] = []
    sources: list[str] = []

    # ── 1. Google dorking for interviews, profiles, bios ───────────────
    dork_queries = [
        f'"{full_name}" wawancara OR interview "{uni_name}"',
        f'"{full_name}" profil OR biografi OR tentang "{uni_name}"',
        f'"{full_name}" hobi OR hobby OR "waktu luang" OR "di luar kampus"',
        f'intitle:"{full_name}" profil OR wawancara',
    ]
    # NIDN-based search is very precise
    if nidn:
        dork_queries.append(f'"{nidn}" profil OR wawancara OR biografi')

    for q in dork_queries:
        hits = await ddg_search(q, max_results=3)
        for h in (hits or []):
            snippet = h.get("snippet", "") or h.get("body", "")
            if snippet and len(snippet) > 30:
                snippets.append(snippet)
        # Also try to fetch full page for most relevant results
        if hits and len(snippets) < 5:
            best_link = hits[0].get("link", "")
            if best_link and not any(x in best_link for x in ["youtube.com", "twitter.com", "facebook.com"]):
                page_html = await fetch_page(best_link)
                if page_html:
                    page_text = extract_text_from_html(page_html, max_chars=4000)
                    # Only use if name appears in text
                    name_parts = full_name.lower().split()
                    if any(p in page_text.lower() for p in name_parts if len(p) > 2):
                        snippets.append(f"[Full page: {best_link}]\n{page_text}")
                        sources.append("page_scrape")

    if snippets:
        sources.append("ddg_dork")

    # ── 2. Social media content (from social profiler) ─────────────────
    if social:
        if social.instagram_handle:
            # Strategy A: Try Playwright for real IG bio + recent posts
            ig_scraped = False
            try:
                import asyncio as _aio
                from orchestrator.playwright_ig import pw_get_profile, pw_get_posts, is_available
                if is_available():
                    loop = _aio.get_event_loop()
                    profile = await loop.run_in_executor(
                        None, pw_get_profile, social.instagram_handle,
                    )
                    if profile:
                        bio = profile.get("bio", "")
                        ig_name = profile.get("full_name", "")
                        ext_url = profile.get("external_url", "")
                        followers = profile.get("followers", 0)
                        if bio:
                            snippets.append(
                                f"Instagram bio (@{social.instagram_handle}): "
                                f"{ig_name}. {bio}. "
                                f"Followers: {followers}. External: {ext_url}"
                            )
                            ig_scraped = True
                            sources.append("instagram_profile_pw")

                    # Get recent posts for activity/interest insights
                    posts = await loop.run_in_executor(
                        None, pw_get_posts, social.instagram_handle, 6,
                    )
                    if posts:
                        captions = []
                        for p in posts[:6]:
                            cap = p.get("caption", "") or ""
                            if cap and len(cap) > 20:
                                captions.append(cap[:500])
                        if captions:
                            snippets.append(
                                f"Instagram recent posts (@{social.instagram_handle}):\n"
                                + "\n---\n".join(captions)
                            )
                            ig_scraped = True
                            sources.append("instagram_posts_pw")
            except ImportError:
                pass  # Playwright not available
            except Exception as e:
                log.warning("[PersonalInterest] IG Playwright failed: %s", e)

            # Strategy B: Fallback to DDG snippets if Playwright unavailable
            if not ig_scraped:
                ig_queries = [
                    f'site:instagram.com/{social.instagram_handle}',
                    f'"{social.instagram_handle}" instagram bio OR tentang',
                ]
                for q in ig_queries:
                    ig_hits = await ddg_search(q, max_results=2)
                    for h in (ig_hits or []):
                        snippet = h.get("snippet", "") or h.get("body", "")
                        if snippet:
                            snippets.append(f"Instagram: {snippet}")
                if ig_hits:
                    sources.append("instagram_bio")

        if social.linkedin_url:
            ln_hits = await ddg_search(
                f'"{full_name}" site:linkedin.com',
                max_results=2,
            )
            for h in (ln_hits or []):
                snippet = h.get("snippet", "") or h.get("body", "")
                if snippet:
                    snippets.append(f"LinkedIn: {snippet}")
            if ln_hits:
                sources.append("linkedin")

        if social.facebook_url:
            fb_hits = await ddg_search(
                f'"{full_name}" site:facebook.com tentang OR about',
                max_results=2,
            )
            for h in (fb_hits or []):
                snippet = h.get("snippet", "") or h.get("body", "")
                if snippet:
                    snippets.append(f"Facebook: {snippet}")
            if fb_hits:
                sources.append("facebook")

        # Check SINTA/Scholar for research interests → infer personality
        sinta_url = social.other_social.get("sinta", "")
        scholar_url = social.other_social.get("google_scholar", "")
        if sinta_url:
            sinta_html = await fetch_page(sinta_url)
            if sinta_html:
                sinta_text = extract_text_from_html(sinta_html, max_chars=3000)
                snippets.append(f"SINTA Profile:\n{sinta_text}")
                sources.append("sinta_profile")
        if scholar_url:
            scholar_html = await fetch_page(scholar_url)
            if scholar_html:
                scholar_text = extract_text_from_html(scholar_html, max_chars=3000)
                snippets.append(f"Google Scholar:\n{scholar_text}")
                sources.append("scholar_profile")

    # ── 3. Gemini grounded research for personal details ────────────────
    try:
        from orchestrator.crm.tools import gemini_research
        gemini_q = (
            f"Cari informasi personal tentang {full_name}, "
            f"dosen di {uni_name}. "
            f"Saya ingin tahu: hobi, kegiatan di luar kampus, "
            f"makanan favorit, sifat kepribadian, "
            f"aktivitas sehari-hari, dan hal menarik tentang beliau."
        )
        log.info("[PersonalInterest] Calling Gemini for %s (snippets so far: %d)", full_name, len(snippets))
        gemini_resp = await gemini_research(gemini_q)
        if gemini_resp and gemini_resp.get("text"):
            snippets.append(f"Gemini research:\n{gemini_resp['text']}")
            sources.append("gemini_personal")
        else:
            log.warning("[PersonalInterest] Gemini returned empty for %s", full_name)
    except Exception as e:
        log.warning("[PersonalInterest] Gemini failed for %s: %s", full_name, e)

    # ── 4. Academic-based personality inference ─────────────────────────
    if academic:
        # Build context from academic data for GPT inference
        acad_context = []
        if academic.research_topics:
            acad_context.append(f"Research topics: {', '.join(academic.research_topics[:10])}")
        if academic.teaching_subjects:
            acad_context.append(f"Teaching: {', '.join(academic.teaching_subjects[:10])}")
        if academic.jabatan_akademik:
            acad_context.append(f"Position: {academic.jabatan_akademik}")
        if academic.education_history:
            edu_summary = ", ".join(
                f"{e.get('jenjang', '')} at {e.get('nama_pt', '')}"
                for e in academic.education_history
            )
            acad_context.append(f"Education: {edu_summary}")
        if acad_context:
            snippets.append(f"Academic background:\n" + "\n".join(acad_context))

    # ── 4. GPT extraction ──────────────────────────────────────────────
    result = PersonalInterestResult()

    if snippets:
        combined = "\n---\n".join(snippets[:15])
        extracted = await gpt_extract_structured(
            combined,
            (
                f"From the following text snippets about {full_name} (dosen/professor "
                f"at {uni_name}), extract personal information:\n"
                "Return JSON with keys:\n"
                "- hobbies: list of hobbies/interests mentioned or clearly inferable\n"
                "- favorite_food: string or null\n"
                "- outside_activities: list of activities outside academics\n"
                "- personality_traits: list of personality traits (e.g., 'perfectionist', "
                "'collaborative', 'visionary', 'detail-oriented') based on their work, "
                "publications, teaching style, and any interviews\n\n"
                "For personality_traits: you may infer from research topics and academic "
                "behavior (e.g., someone doing AI + Biology is likely 'interdisciplinary' "
                "and 'innovative'). For hobbies, only include if explicitly mentioned."
            ),
        )
        if extracted:
            result.hobbies = extracted.get("hobbies") or []
            result.favorite_food = extracted.get("favorite_food")
            result.outside_activities = extracted.get("outside_activities") or []
            result.personality_traits = extracted.get("personality_traits") or []

    # ── Confidence ─────────────────────────────────────────────────────
    filled = sum([
        bool(result.hobbies), bool(result.favorite_food),
        bool(result.outside_activities), bool(result.personality_traits),
    ])
    result.confidence = round(filled / 4, 2)
    result.sources = sources

    log.info(
        "[PersonalInterest] Done for %s: hobbies=%d, traits=%d, confidence=%.2f",
        full_name, len(result.hobbies), len(result.personality_traits), result.confidence,
    )
    return {"personal_interest": result}
