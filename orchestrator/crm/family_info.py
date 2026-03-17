"""
Family Info Agent — discovers basic family information.
Best-effort and privacy-conscious — only uses publicly available data.
Uses Google dorking via DDG for deeper discovery.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, FamilyInfoResult
from orchestrator.crm.name_utils import strip_academic_titles, ai_strip_titles, build_name_variants
from orchestrator.crm.tools import ddg_search, ddg_search, gpt_extract_structured, fetch_page, extract_text_from_html


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
    # Use cleaned name for DDG queries (strip academic titles)
    cleaned_name = state.get("cleaned_name") or await ai_strip_titles(pic_name)
    search_name = cleaned_name if cleaned_name != full_name else full_name

    log.info("[FamilyInfo] Starting for %s (search_name=%s)", full_name, search_name)

    snippets: list[str] = []
    sources: list[str] = []
    collected_urls: list[str] = []

    # ── 1. Google dorking for family mentions (agentic retry) ─────────
    # Use cleaned name for better DDG results
    dork_queries = [
        f'"{search_name}" istri OR suami OR keluarga OR anak "{uni_name}"',
        f'"{search_name}" "menikah" OR "nikah" OR "pernikahan"',
        f'"{search_name}" tinggal OR domisili OR alamat OR "berdomisili di"',
        f'"{search_name}" profil pribadi OR biografi "{uni_name}"',
        f'intitle:"{search_name}" profil OR biografi',
    ]
    if nidn:
        dork_queries.append(f'"{nidn}" profil OR biografi keluarga')
    # Add shorter name variant as broadest fallback
    name_variants = state.get("name_variants") or build_name_variants(pic_name)
    short_variants = [v for v in name_variants if v.lower() != search_name.lower() and len(v.split()) <= 2]
    for sv in short_variants[:1]:
        dork_queries.append(f'"{sv}" dosen "{uni_name}" profil keluarga')

    for q in dork_queries:
        hits = await ddg_search(q, max_results=3)
        for h in (hits or []):
            snippet = h.get("snippet", "") or h.get("body", "")
            link = h.get("link", "")
            if snippet and len(snippet) > 20:
                snippets.append(snippet)
            if link:
                collected_urls.append(link)
            # Fetch relevant pages that might have full bio
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
        collected_urls.append(fb_url)
        fb_queries = [
            f'"{search_name}" site:facebook.com keluarga OR family OR tentang',
            f'site:facebook.com "{search_name}" married OR menikah',
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
        about_url = fb_url.rstrip("/") + "/about"
        fb_about_html = await fetch_page(about_url)
        if fb_about_html:
            fb_text = extract_text_from_html(fb_about_html, max_chars=4000)
            if fb_text and len(fb_text) > 50:
                snippets.append(f"Facebook profile:\n{fb_text}")
                sources.append("facebook_page")

    # ── 3. University staff page ───────────────────────────────────────
    staff_queries = [
        f'site:*.ac.id "{search_name}" profil OR staff OR dosen',
    ]
    for q in staff_queries:
        hits = await ddg_search(q, max_results=2)
        for h in (hits or []):
            link = h.get("link", "")
            if link and ".ac.id" in link:
                collected_urls.append(link)
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
        gemini_queries = [
            (
                f"Cari informasi keluarga tentang {search_name}, "
                f"dosen di {uni_name}. "
                f"Apakah beliau sudah menikah? Siapa nama istri/suami? "
                f"Berapa jumlah anak? Tinggal di mana? "
                f"WARNING: JANGAN MENGARANG (HALUSINASI). Jika tidak ada informasi terpublikasi, katakan saja 'tidak diketahui'. Jangan asal tebak atau campur aduk dengan orang lain."
            ),
        ]
        # Add targeted residence query if we're missing that
        if not any("domisili" in s.lower() or "tinggal" in s.lower() for s in snippets):
            gemini_queries.append(
                f"Di mana {search_name} dosen {uni_name} berdomisili? "
                f"Sebutkan kotanya JIKA ADA BUKTI SAJA. JANGAN MENGARANG."
            )
        for gq in gemini_queries:
            log.info("[FamilyInfo] Calling Gemini for %s", search_name)
            gemini_resp = await gemini_research(gq)
            if gemini_resp and gemini_resp.get("text"):
                snippets.append(f"Gemini research:\n{gemini_resp['text']}")
                sources.append("gemini_grounded")
                for u in (gemini_resp.get("urls") or []):
                    if u:
                        collected_urls.append(u)
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
                "CRITICAL RULES:\n"
                "- ONLY include marital_status/spouse_name/children_count if EXPLICITLY stated in the text\n"
                "- Do NOT guess or infer - if not clearly stated, return 'unknown' or null\n"
                "- For family_residence: ONLY include if the person explicitly mentions living in a city\n"
                "- Do NOT infer from university location - professors may work in one city but live elsewhere\n"
                "- Better to return 'unknown' than to guess incorrectly\n"
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

    # ── Source URLs per field ──────────────────────────────────────────
    unique_urls = list(dict.fromkeys(collected_urls))
    for field in ("marital_status", "spouse_name", "children_count", "family_residence"):
        val = getattr(result, field, None)
        if val is not None and val != "unknown":
            result.source_urls[field] = unique_urls

    # ── Confidence ─────────────────────────────────────────────────────
    # Family info is sensitive - use lower confidence by default
    filled = sum([
        result.marital_status not in (None, "unknown"),
        bool(result.spouse_name),
        result.children_count is not None,
        bool(result.family_residence),
    ])
    # Apply penalty: family info is hard to verify, cap confidence at 0.5
    base_confidence = round(filled / 4, 2)
    result.confidence = min(base_confidence, 0.5)
    result.sources = sources

    log.info(
        "[FamilyInfo] Done for %s: status=%s, confidence=%.2f",
        full_name, result.marital_status, result.confidence,
    )
    return {"family_info": result}
