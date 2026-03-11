"""
Campus Context Agent — gathers problems, concerns, and aspirations
of the university relevant to the PIC's campus/faculty.
Uses news search + Gemini grounded search + OSINT data.
"""

from __future__ import annotations

import json
from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, CampusContextResult
from orchestrator.crm.tools import ddg_search, gemini_research, gpt_extract_structured


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

    # ── 1. DDG news about campus problems ──────────────────────────────
    queries = [
        f'"{uni_name}" masalah OR kendala OR tantangan {faculty}'.strip(),
        f'"{uni_name}" harapan OR target OR visi misi {faculty}'.strip(),
        f'"{uni_name}" akreditasi OR prestasi OR pencapaian {faculty}'.strip(),
    ]

    for q in queries:
        hits = await ddg_search(q, max_results=5)
        for h in (hits or []):
            snippet = h.get("snippet", "") or h.get("body", "")
            if snippet:
                all_snippets.append(snippet)
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
        "PENTING: Sertakan berita terbaru (recent_news) minimal 2-3 item.\n"
        "Gunakan bahasa Indonesia. Hanya fakta yang didukung sumber."
    )

    gemini_resp = await gemini_research(gemini_q)
    if gemini_resp and gemini_resp.get("text"):
        all_snippets.append(gemini_resp["text"])
        sources.append("gemini_grounded")

    # ── 3. GPT synthesis ───────────────────────────────────────────────
    result = CampusContextResult()

    if all_snippets:
        combined = "\n---\n".join(all_snippets[:15])
        prompt = (
            f"Based on the following information about {uni_name}"
            + (f" ({faculty})" if faculty else "")
            + ", extract:\n"
            "1. campus_problems: list of current problems/challenges\n"
            "2. campus_concerns: list of concerns/worries\n"
            "3. campus_hopes: list of aspirations/hopes/targets\n"
            "4. recent_news: list of recent achievements or notable events\n\n"
            "Return JSON with these 4 keys, each a list of short strings.\n"
            "Only include clearly supported items. Use Indonesian language."
        )
        extracted = await gpt_extract_structured(combined, prompt)

        if extracted:
            result.campus_problems = extracted.get("campus_problems") or []
            result.campus_concerns = extracted.get("campus_concerns") or []
            result.campus_hopes = extracted.get("campus_hopes") or []
            result.recent_news = extracted.get("recent_news") or []

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
