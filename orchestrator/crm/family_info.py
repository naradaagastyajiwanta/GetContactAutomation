"""
Family Info Agent — discovers basic family information.
Best-effort and privacy-conscious — only uses publicly available data.
Uses Google dorking via DDG for deeper discovery.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, FamilyInfoResult
from orchestrator.crm.tools import ddg_search, gpt_extract_structured, fetch_page, extract_text_from_html


async def family_info_agent(state: CrmState) -> dict:
    """
    Discover publicly available family information using:
    1. Google dorking for public mentions (news, bios, interviews)
    2. Facebook public profile analysis
    3. University official bio pages
    4. GPT extraction

    Privacy-first: only use public mentions.
    Returns partial state update with `family_info`.
    """
    identity = state.get("identity")
    social = state.get("social_profile")
    pic_name = state.get("pic_name", "")
    uni_name = state.get("university_name", "")

    full_name = (identity.full_name if identity else None) or pic_name
    nidn = identity.nidn if identity else None

    log.info("[FamilyInfo] Starting for %s", full_name)

    snippets: list[str] = []
    sources: list[str] = []

    # ── 1. Google dorking for family mentions ──────────────────────────
    dork_queries = [
        f'"{full_name}" istri OR suami OR keluarga OR anak "{uni_name}"',
        f'"{full_name}" "menikah" OR "nikah" OR "pernikahan"',
        f'"{full_name}" profil pribadi OR biografi "{uni_name}"',
        f'intitle:"{full_name}" profil OR biografi',
    ]
    if nidn:
        dork_queries.append(f'"{nidn}" profil OR biografi keluarga')

    for q in dork_queries:
        hits = await ddg_search(q, max_results=3)
        for h in (hits or []):
            snippet = h.get("snippet", "") or h.get("body", "")
            if snippet and len(snippet) > 20:
                snippets.append(snippet)
            # Fetch relevant pages that might have full bio
            link = h.get("link", "")
            if link and ("profil" in link.lower() or "biografi" in link.lower()
                        or ".ac.id" in link.lower()):
                page_html = await fetch_page(link)
                if page_html:
                    page_text = extract_text_from_html(page_html, max_chars=3000)
                    name_parts = full_name.lower().split()
                    if any(p in page_text.lower() for p in name_parts if len(p) > 2):
                        snippets.append(f"[Bio page: {link}]\n{page_text}")
                        sources.append("bio_page_scrape")

    if snippets:
        sources.append("ddg_dork")

    # ── 2. Facebook public search ──────────────────────────────────────
    fb_url = social.facebook_url if social else None
    if fb_url:
        fb_queries = [
            f'"{full_name}" site:facebook.com keluarga OR family OR tentang',
            f'site:facebook.com "{full_name}" married OR menikah',
        ]
        for q in fb_queries:
            fb_hits = await ddg_search(q, max_results=2)
            for h in (fb_hits or []):
                snippet = h.get("snippet", "") or h.get("body", "")
                if snippet:
                    snippets.append(f"Facebook: {snippet}")
        if fb_hits:
            sources.append("facebook")

        # Try to fetch FB about page
        fb_about_html = await fetch_page(fb_url)
        if fb_about_html:
            fb_text = extract_text_from_html(fb_about_html, max_chars=2000)
            if fb_text and len(fb_text) > 50:
                snippets.append(f"Facebook profile:\n{fb_text}")
                sources.append("facebook_page")

    # ── 3. University staff page ───────────────────────────────────────
    staff_queries = [
        f'site:*.ac.id "{full_name}" profil OR staff OR dosen',
    ]
    for q in staff_queries:
        hits = await ddg_search(q, max_results=2)
        for h in (hits or []):
            link = h.get("link", "")
            if link and ".ac.id" in link:
                page_html = await fetch_page(link)
                if page_html:
                    page_text = extract_text_from_html(page_html, max_chars=3000)
                    name_parts = full_name.lower().split()
                    if any(p in page_text.lower() for p in name_parts if len(p) > 2):
                        snippets.append(f"University staff page:\n{page_text}")
                        sources.append("university_staff_page")
                        break

    # ── 4. Gemini grounded research for family info ────────────────────
    try:
        from orchestrator.crm.tools import gemini_research
        gemini_q = (
            f"Cari informasi keluarga tentang {full_name}, "
            f"dosen di {uni_name}. "
            f"Apakah beliau sudah menikah? Siapa nama istri/suami? "
            f"Berapa jumlah anak? Tinggal di mana?"
        )
        log.info("[FamilyInfo] Calling Gemini for %s", full_name)
        gemini_resp = await gemini_research(gemini_q)
        if gemini_resp and gemini_resp.get("text"):
            snippets.append(f"Gemini research:\n{gemini_resp['text']}")
            sources.append("gemini_grounded")
        else:
            log.warning("[FamilyInfo] Gemini returned empty for %s", full_name)
    except Exception as e:
        log.warning("[FamilyInfo] Gemini failed for %s: %s", full_name, e)

    # ── 5. GPT extraction ──────────────────────────────────────────────
    result = FamilyInfoResult()

    if snippets:
        combined = "\n---\n".join(snippets[:12])
        extracted = await gpt_extract_structured(
            combined,
            (
                f"From these public text snippets about {full_name} (dosen/professor "
                f"at {uni_name}), extract family information:\n"
                "Return JSON with keys:\n"
                "- marital_status: 'married'/'single'/'unknown'\n"
                "- spouse_name: string or null\n"
                "- children_count: integer or null\n"
                "- family_residence: city/region or null\n\n"
                "IMPORTANT: Only include information that is EXPLICITLY stated "
                "in the text. Do not infer or guess. Use null if not found."
            ),
        )
        if extracted:
            result.marital_status = extracted.get("marital_status", "unknown")
            result.spouse_name = extracted.get("spouse_name")
            children = extracted.get("children_count")
            if children is not None:
                try:
                    result.children_count = int(children)
                except (ValueError, TypeError):
                    pass
            result.family_residence = extracted.get("family_residence")

    # ── Confidence ─────────────────────────────────────────────────────
    filled = sum([
        result.marital_status not in (None, "unknown"),
        bool(result.spouse_name),
        result.children_count is not None,
        bool(result.family_residence),
    ])
    result.confidence = round(filled / 4, 2)
    result.sources = sources

    log.info(
        "[FamilyInfo] Done for %s: status=%s, confidence=%.2f",
        full_name, result.marital_status, result.confidence,
    )
    return {"family_info": result}
