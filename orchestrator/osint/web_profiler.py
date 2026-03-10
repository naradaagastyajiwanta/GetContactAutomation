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

    log.info("[WebProfiler] Starting for %s (website=%s)", uni_name, website)

    result = WebProfileResult()
    sources: list[str] = []

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
            page_text = extract_text_from_html(html, max_chars=6000)

            # Extract contact info directly
            emails_found = extract_emails(page_text)
            phones_found = extract_phones_from_text(page_text)
            if emails_found:
                result.email_official = emails_found[0]
            if phones_found:
                result.phone_official = phones_found[0]

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
                if extracted.get("fax"):
                    result.fax = extracted["fax"]
                if extracted.get("email") and not result.email_official:
                    result.email_official = extracted["email"]
                if extracted.get("vision_mission"):
                    result.vision_mission = extracted["vision_mission"]

            sources.append(website)
            log.info("[WebProfiler] Website scraped successfully")

        # Try specific subpages for additional data
        for path in ["/profil", "/tentang", "/kontak", "/contact"]:
            sub_url = website.rstrip("/") + path
            sub_html = await fetch_page(sub_url)
            if sub_html:
                sub_text = extract_text_from_html(sub_html, max_chars=4000)
                if not result.address:
                    sub_extracted = await gpt_extract_structured(
                        sub_text,
                        "Extract the address, city, postal_code, phone, fax, email from this page. Return as JSON.",
                    )
                    if sub_extracted:
                        if sub_extracted.get("address") and not result.address:
                            result.address = sub_extracted["address"]
                        if sub_extracted.get("city") and not result.city:
                            result.city = sub_extracted["city"]
                sources.append(sub_url)

    # ── 3. DDG fallback for missing data ───────────────────────────────
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
        "[WebProfiler] Done for %s: address=%s, faculties=%d, confidence=%.2f",
        uni_name,
        bool(result.address),
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
