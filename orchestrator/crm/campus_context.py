"""
Campus Context Agent — gathers problems, concerns, and aspirations
of the university relevant to the PIC's campus/faculty.
Uses news search + Gemini grounded search + OSINT data.
Agentic: if exact-match DDG queries return nothing, progressively
relaxes the university name (abbreviation, city-only).
"""

from __future__ import annotations

import json
import re
from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, CampusContextResult
from orchestrator.crm.tools import ddg_search, gemini_research, gpt_extract_structured


async def _ai_build_uni_variants(uni_name: str) -> list[str]:
    """Use AI to generate search-friendly university name variants.

    AI knows that:
    - "Institut Teknologi Sepuluh Nopember" → abbreviation "ITS", city "Surabaya"
    - "Universitas Gadjah Mada" → "UGM", city "Yogyakarta"
    - "Universitas Abdurachman Saleh Situbondo" → "UNARS Situbondo"
    """
    result = await gpt_extract_structured(
        uni_name,
        (
            "Generate search-friendly variants for this Indonesian university name.\n"
            "Return JSON: {\n"
            '  "abbreviation": "common abbreviation (e.g. ITS, UGM, UNARS)",\n'
            '  "city": "city where the university is located",\n'
            '  "variants": ["variant1", "variant2", ...]\n'
            "}\n"
            "Include: full name, abbreviation + city, 'kampus' + city.\n"
            "Examples:\n"
            '- "Institut Teknologi Sepuluh Nopember" → {"abbreviation": "ITS", "city": "Surabaya", '
            '"variants": ["Institut Teknologi Sepuluh Nopember", "ITS Surabaya", "kampus Surabaya"]}\n'
            '- "Universitas Gadjah Mada" → {"abbreviation": "UGM", "city": "Yogyakarta", '
            '"variants": ["Universitas Gadjah Mada", "UGM Yogyakarta", "kampus Yogyakarta"]}'
        ),
    )
    if result and result.get("variants"):
        # Ensure original name is first
        variants = result["variants"]
        if uni_name not in variants:
            variants.insert(0, uni_name)
        return variants
    # Fallback: return original name only
    return [uni_name]


def _build_uni_variants(uni_name: str) -> list[str]:
    """Build search-friendly university name variants (sync fallback).

    "UNIVERSITAS ABDURACHMAN SALEH SITUBONDO"
    → ["Universitas Abdurachman Saleh Situbondo",
       "UNARS Situbondo",
       "kampus Situbondo"]
    """
    variants = [uni_name]
    parts = uni_name.split()
    # Try abbreviation: first letter of each word except "UNIVERSITAS/INSTITUT/SEKOLAH" + last word
    if len(parts) >= 3:
        prefix_words = {"universitas", "institut", "sekolah", "tinggi", "politeknik", "akademi"}
        abbrev_parts = []
        city_word = parts[-1]  # Usually the city name
        for p in parts[:-1]:
            if p.lower() in prefix_words:
                abbrev_parts.append(p[0].upper())
            else:
                abbrev_parts.append(p[0].upper())
        abbreviation = "".join(abbrev_parts) + " " + city_word.title()
        variants.append(abbreviation)
        # City-only variant
        variants.append(f"kampus {city_word.title()}")
    return variants


async def campus_context_agent(state: CrmState) -> dict:
    """
    Discover campus problems, concerns, and hopes relevant to the PIC.

    Returns partial state update with `campus_context`.
    """
    identity = state.get("identity")
    pic_name = state.get("pic_name", "")
    uni_name = state.get("university_name", "")
    faculty = state.get("faculty", "")

    full_name = (identity.full_name if identity else None) or pic_name

    log.info("[CampusContext] Starting for %s at %s (%s)", full_name, uni_name, faculty)

    all_snippets: list[str] = []
    sources: list[str] = []
    collected_urls: list[str] = []

    # ── 1. DDG news about campus problems (agentic retry) ──────────────
    # Use AI to generate university name variants (knows abbreviations + cities)
    uni_variants = await _ai_build_uni_variants(uni_name)
    for uni_variant in uni_variants:
        if all_snippets:
            break  # Got results, stop trying
        log.info("[CampusContext] DDG attempt with uni variant: '%s'", uni_variant)
        queries = [
            f'"{uni_variant}" masalah OR kendala OR tantangan OR hambatan OR isu {faculty}'.strip(),
            f'"{uni_variant}" kekhawatiran OR krisis OR kekurangan OR defisit {faculty}'.strip(),
            f'"{uni_variant}" harapan OR target OR visi misi {faculty}'.strip(),
            f'"{uni_variant}" akreditasi OR prestasi OR pencapaian {faculty}'.strip(),
        ]

        for q in queries:
            hits = await ddg_search(q, max_results=5)
            for h in (hits or []):
                snippet = h.get("snippet", "") or h.get("body", "")
                link = h.get("link", "")
                if snippet:
                    all_snippets.append(snippet)
                if link:
                    collected_urls.append(link)
    if all_snippets:
        sources.append("ddg_news")

    # ── 2. Gemini grounded research ────────────────────────────────────
    gemini_q = (
        f"Cari informasi terkini tentang {uni_name}"
    )
    if faculty:
        gemini_q += f" khususnya {faculty}"
    gemini_q += (
        ". Saya butuh informasi berikut:\n"
        "1. Masalah dan tantangan kampus saat ini (campus_problems)\n"
        "2. Kekhawatiran tentang masa depan (campus_concerns)\n"
        "3. Harapan, target, dan aspirasi (campus_hopes)\n"
        "4. Berita terbaru dan pencapaian penting di tahun 2025-2026 (recent_news)\n\n"
        "PENTING:\n"
        "- Untuk SETIAP kategori (campus_problems, campus_concerns, campus_hopes, recent_news), berikan minimal 2-3 item.\n"
        "- campus_problems: masalah nyata yang sedang dihadapi (misal: akreditasi, pendanaan, fasilitas, SDM).\n"
        "- campus_concerns: kekhawatiran tentang masa depan atau risiko (misal: penurunan mahasiswa, persaingan antar kampus).\n"
        "- campus_hopes: target, harapan, aspirasi.\n"
        "- recent_news: berita terbaru dan pencapaian 2025-2026.\n"
        "Gunakan bahasa Indonesia. Hanya fakta yang didukung sumber."
    )

    gemini_resp = await gemini_research(gemini_q)
    if gemini_resp and gemini_resp.get("text"):
        all_snippets.append(gemini_resp["text"])
        sources.append("gemini_grounded")
        for u in (gemini_resp.get("urls") or []):
            if u:
                collected_urls.append(u)

    # ── 3. GPT synthesis ───────────────────────────────────────────────
    result = CampusContextResult()

    if all_snippets:
        combined = "\n---\n".join(all_snippets[:15])
        prompt = (
            f"Based on the following information about {uni_name}"
            + (f" ({faculty})" if faculty else "")
            + ", extract:\n"
            "1. campus_problems: list of current problems/challenges (e.g., accreditation, funding, facilities, HR)\n"
            "2. campus_concerns: list of concerns/worries about the future (e.g., declining enrollment, competition)\n"
            "3. campus_hopes: list of aspirations/hopes/targets\n"
            "4. recent_news: list of recent achievements or notable events\n\n"
            "Return JSON with these 4 keys, each a list of short strings (minimum 2 items each if data supports it).\n"
            "WARNING: DO NOT HALLUCINATE OR GUESS. If there is NO specific information in the context about the university, RETURN AN EMPTY LIST []. Do not attribute random global economic problems, unrelated national issues, or generic statements unless explicitly documented in the snippets. You must return ONLY facts proven by the text.\n"
            "Use Indonesian language."
        )
        extracted = await gpt_extract_structured(combined, prompt)

        if extracted:
            result.campus_problems = extracted.get("campus_problems") or []
            result.campus_concerns = extracted.get("campus_concerns") or []
            result.campus_hopes = extracted.get("campus_hopes") or []
            result.recent_news = extracted.get("recent_news") or []

    # ── Source URLs per field ──────────────────────────────────────────
    unique_urls = list(dict.fromkeys(collected_urls))  # dedupe, preserve order
    for field in ("campus_problems", "campus_concerns", "campus_hopes", "recent_news"):
        if getattr(result, field, None):
            result.source_urls[field] = unique_urls

    # ── Confidence ─────────────────────────────────────────────────────
    filled = sum([
        bool(result.campus_problems), bool(result.campus_concerns),
        bool(result.campus_hopes), bool(result.recent_news),
    ])
    result.confidence = round(filled / 4, 2)
    result.sources = sources

    log.info(
        "[CampusContext] Done for %s: problems=%d concerns=%d hopes=%d news=%d",
        uni_name,
        len(result.campus_problems),
        len(result.campus_concerns),
        len(result.campus_hopes),
        len(result.recent_news),
    )
    return {"campus_context": result}
