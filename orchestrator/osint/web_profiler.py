"""
Web Profiler Agent — scrapes the university website and PDDIKTI
to gather structural information (address, faculties, contacts, etc.).

Follows "Check Before Search": skips data already in DB.
"""

from __future__ import annotations

import json
from typing import Any

from orchestrator.config import log
from orchestrator.osint.state import OsintState, WebProfileResult
from orchestrator.osint.tools import (
    ddg_search,
    fetch_page,
    extract_text_from_html,
    extract_emails,
    extract_phones_from_text,
    gpt_extract_structured,
    pddikti_search_pt,
    pddikti_get_prodi,
    pddikti_get_jumlah_dosen,
    pddikti_get_pt,
)


async def web_profiler_agent(state: OsintState) -> dict:
    """
    Scrape the university website + PDDIKTI for structural info.

    Returns partial state update with `web_profile`.
    """
    uni = state.get("university_data", {})
    uni_name = state.get("university_name", uni.get("name", ""))
    website = uni.get("website", "")
    pddikti_id = uni.get("pddikti_id", "")

    # ── 0. Fallback: search for website if not in DB ─────────────────────
    if not website:
        log.info("[WebProfiler] No website in DB, searching via DDG...")
        # Search specifically for university website, exclude social media
        ddg_results = await ddg_search(
            f'"{uni_name}" site:.ac.id official',
            max_results=10
        )
        # Filter out social media domains
        social_domains = ['facebook', 'twitter', 'instagram', 'youtube', 'tiktok', 'linkedin']

        for r in ddg_results:
            link = r.get("link", "")
            # Skip social media
            if any(sd in link.lower() for sd in social_domains):
                continue
            # Look for .ac.id domain
            if link and ".ac.id" in link.lower():
                website = link
                log.info("[WebProfiler] Found website via DDG: %s", website)
                break

        # If still no website, try broader search with site: filter
        if not website:
            ddg_results = await ddg_search(
                f'"{uni_name}" official website -facebook -twitter -instagram -youtube',
                max_results=5
            )
            for r in ddg_results:
                link = r.get("link", "")
                if any(sd in link.lower() for sd in social_domains):
                    continue
                if link and ".ac.id" in link.lower():
                    website = link
                    log.info("[WebProfiler] Found website via DDG: %s", website)
                    break

        if not website:
            log.warning("[WebProfiler] Could not find official website via DDG")

    log.info("[WebProfiler] Starting for %s (website=%s, pddikti_id=%s)", uni_name, website, pddikti_id)

    result = WebProfileResult()
    sources: list[str] = []

    # ── 0b. PDDIKTI PT profile (email, phone, address) ─────────────────
    if pddikti_id:
        try:
            pt_data = await pddikti_get_pt(pddikti_id)
            if pt_data:
                # Extract email from PDDIKTI
                pt_email = (
                    pt_data.get("email") or
                    pt_data.get("email_pt") or
                    pt_data.get("email_upt") or
                    pt_data.get("kontak_email")
                )
                if pt_email:
                    result.email_official = pt_email
                    result.email_source = "pddikti"
                    sources.append("pddikti_pt")
                    log.info("[WebProfiler] Email from PDDIKTI: %s", pt_email)

                # Extract phone from PDDIKTI
                pt_phone = (
                    pt_data.get("telephone") or
                    pt_data.get("phone") or
                    pt_data.get("telp_pt") or
                    pt_data.get("no_telepon")
                )
                if pt_phone:
                    result.phone_official = pt_phone
                    result.phone_source = "pddikti"
                    sources.append("pddikti_pt")

                # Extract address from PDDIKTI if not already set
                if not result.address:
                    pt_address = pt_data.get("alamat") or pt_data.get("alamat_pt")
                    if pt_address:
                        result.address = pt_address
                        sources.append("pddikti_pt")

                if not result.city:
                    pt_city = pt_data.get("kota") or pt_data.get("kabupaten")
                    if pt_city:
                        result.city = pt_city

                log.info("[WebProfiler] PDDIKTI PT profile loaded successfully")
        except Exception as e:
            log.warning("[WebProfiler] PDDIKTI get_detail_pt error: %s", e)

    # ── 1. PDDIKTI data (free, reliable, always run) ───────────────────
    if pddikti_id:
        try:
            prodi_list = await pddikti_get_prodi(pddikti_id)
            if prodi_list:
                result.faculty_list = [
                    {
                        "nama_prodi": p.get("nama_prodi", ""),
                        "jenjang": p.get("jenjang", ""),
                        "akreditasi": p.get("akreditasi", ""),
                        "jumlah_dosen": p.get("jumlah_dosen", 0),
                        "jumlah_mahasiswa": p.get("jumlah_mahasiswa", 0),
                    }
                    for p in prodi_list
                ]
                result.faculty_count = len(prodi_list)

                # Calculate total students from all prodi
                total_students = sum(p.get("jumlah_mahasiswa", 0) for p in prodi_list)
                if total_students > 0:
                    result.student_count = total_students
                    sources.append("pddikti_student_count")
                    log.info("[WebProfiler] Total students from %d prodi: %d", len(prodi_list), total_students)

                sources.append("pddikti_prodi")
                log.info("[WebProfiler] PDDIKTI: %d study programs found", len(prodi_list))

            dosen_count = await pddikti_get_jumlah_dosen(pddikti_id)
            if dosen_count:
                sources.append("pddikti_dosen_count")
        except Exception as e:
            log.warning("[WebProfiler] PDDIKTI error: %s", e)

    # ── 2. Website scraping (for address, email, phone, visi-misi) ─────
    if website:
        html = await fetch_page(website)
        if html:
            page_text = extract_text_from_html(html, max_chars=12000)

            # Extract contact info directly
            emails_found = extract_emails(page_text)
            phones_found = extract_phones_from_text(page_text)
            if emails_found and not result.email_official:
                result.email_official = emails_found[0]
                result.email_source = "website"
            if phones_found and not result.phone_official:
                result.phone_official = phones_found[0]
                result.phone_source = "website"

            # GPT extraction for structured data
            extracted = await gpt_extract_structured(
                page_text,
                (
                    "Extract the following from this university website text:\n"
                    "- address: full campus address\n"
                    "- city: city name\n"
                    "- postal_code: postal/zip code\n"
                    "- phone: official phone number\n"
                    "- fax: fax number\n"
                    "- email: official email\n"
                    "- vision_mission: vision and mission statement (brief summary)\n"
                    "Return as JSON with these exact keys."
                ),
            )
            if extracted:
                if extracted.get("address"):
                    result.address = extracted["address"]
                if extracted.get("city"):
                    result.city = extracted["city"]
                if extracted.get("postal_code"):
                    result.postal_code = extracted["postal_code"]
                if extracted.get("phone") and not result.phone_official:
                    result.phone_official = extracted["phone"]
                    result.phone_source = "website"
                if extracted.get("fax"):
                    result.fax = extracted["fax"]
                if extracted.get("email") and not result.email_official:
                    result.email_official = extracted["email"]
                    result.email_source = "website"
                if extracted.get("vision_mission"):
                    result.vision_mission = extracted["vision_mission"]

            sources.append(website)
            log.info("[WebProfiler] Website scraped successfully")

        # Try specific subpages for additional data
        for path in ["/profil", "/tentang", "/kontak", "/contact"]:
            sub_url = website.rstrip("/") + path
            sub_html = await fetch_page(sub_url)
            if sub_html:
                sub_text = extract_text_from_html(sub_html, max_chars=8000)
                if not result.address or not result.email_official or not result.phone_official:
                    sub_extracted = await gpt_extract_structured(
                        sub_text,
                        "Extract the address, city, postal_code, phone, fax, email from this page. Return as JSON.",
                    )
                    if sub_extracted:
                        if sub_extracted.get("address") and not result.address:
                            result.address = sub_extracted["address"]
                        if sub_extracted.get("city") and not result.city:
                            result.city = sub_extracted["city"]
                        if sub_extracted.get("phone") and not result.phone_official:
                            result.phone_official = sub_extracted["phone"]
                            result.phone_source = "website"
                        if sub_extracted.get("email") and not result.email_official:
                            result.email_official = sub_extracted["email"]
                            result.email_source = "website"
                sources.append(sub_url)

    # ── 3. DDG fallback for missing data ───────────────────────────────
    # Email fallback
    if not result.email_official:
        ddg_email = await ddg_search(f'"{uni_name}" email kampus OR "contact" OR "@" ".ac.id"', max_results=3)
        if ddg_email:
            for r in ddg_email:
                snippet = r.get("snippet", "")
                emails_in_snippet = extract_emails(snippet)
                if emails_in_snippet:
                    result.email_official = emails_in_snippet[0]
                    result.email_source = "ddg"
                    sources.append("ddg_email")
                    log.info("[WebProfiler] Email from DDG: %s", result.email_official)
                    break

    # Phone fallback
    if not result.phone_official:
        ddg_phone = await ddg_search(f'"{uni_name}" telepon OR "phone" OR "hubungi"', max_results=3)
        if ddg_phone:
            for r in ddg_phone:
                snippet = r.get("snippet", "")
                phones_in_snippet = extract_phones_from_text(snippet)
                if phones_in_snippet:
                    result.phone_official = phones_in_snippet[0]
                    result.phone_source = "ddg"
                    sources.append("ddg_phone")
                    log.info("[WebProfiler] Phone from DDG: %s", result.phone_official)
                    break

    # Address fallback (keep existing)
    if not result.address:
        ddg = await ddg_search(f'"{uni_name}" alamat kampus address', max_results=3)
        if ddg:
            snippets = "\n".join(r.get("snippet", "") for r in ddg)
            extracted = await gpt_extract_structured(
                snippets,
                "Extract the university address and city from these search results. Return as JSON with keys: address, city.",
            )
            if extracted:
                result.address = extracted.get("address")
                result.city = extracted.get("city")
            sources.append("ddg_address")

    result.confidence = _compute_confidence(result)
    result.sources = sources

    log.info(
        "[WebProfiler] Done for %s: email=%s (%s), phone=%s (%s), faculties=%d, confidence=%.2f",
        uni_name,
        result.email_official,
        result.email_source or "none",
        result.phone_official,
        result.phone_source or "none",
        result.faculty_count or 0,
        result.confidence,
    )

    return {"web_profile": result}


def _compute_confidence(result: WebProfileResult) -> float:
    """Score 0-1 based on how many fields were populated."""
    fields = [
        result.address, result.city, result.phone_official,
        result.email_official, result.vision_mission,
        result.faculty_count, result.faculty_list,
    ]
    filled = sum(1 for f in fields if f)
    return round(filled / len(fields), 2)
