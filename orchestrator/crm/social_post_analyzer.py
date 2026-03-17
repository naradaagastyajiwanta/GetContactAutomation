"""
Social Post Analyzer Agent
Scrapes recent posts from identified social media accounts or deep web searches 
to determine the person's personality and character traits.
"""

from __future__ import annotations

import json
import asyncio
from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, SocialPostAnalysisResult
from orchestrator.crm.tools import gpt_extract_structured, ddg_search
from orchestrator.osint.tavily_client import tavily_deep_search

async def social_post_analyzer_agent(state: CrmState) -> dict:
    identity = state.get("identity")
    social = state.get("social_profile")
    pic_name = state.get("pic_name", "")

    full_name = (identity.full_name if identity else None) or pic_name
    log.info("[SocialPostAnalyzer] Starting for %s", full_name)

    collected_content: dict[str, str] = {}

    log.info("[SocialPostAnalyzer] Performing deep footprint search via Tavily for: %s", full_name)
    quey_tavily = f'"{full_name}" Indonesia'
    tavily_results = await tavily_deep_search(quey_tavily, max_results=10)
    
    if tavily_results and len(tavily_results) > 100:
        collected_content["Tavily Deep Search"] = tavily_results
    else:
        log.info("[SocialPostAnalyzer] Tavily returned insufficient data or error. Fallback to DDG targeted dork.")
        q_ddg = f'"{full_name}" site:facebook.com OR site:instagram.com OR site:linkedin.com OR site:medium.com'
        hits = await ddg_search(q_ddg, max_results=10)
        if hits:
            snippets = "\n".join(f"{h.get('title')} - {h.get('snippet', '')}" for h in hits)
            if len(snippets) > 50:
                collected_content["Search Snippets"] = snippets

    if not collected_content:
        log.info("[SocialPostAnalyzer] Finished - absolutely no post content could be extracted.")
        return {"social_post_analysis": SocialPostAnalysisResult()}

    prompt_text = ""
    for platform, text in collected_content.items():
        # Allow up to massive 30000 characters context per source to maximize trait mapping
        prompt_text += f"\n=== {platform} CONTENT ===\n{text[:30000]}\n"

    analysis_prompt = (
        f"Anda adalah seorang psikolog klinis profesional dan analis intelijen spesialis profiling.\n"
        f"Berikut adalah kompilasi data JEJAK DIGITAL MENDALAM milik target bernama: {full_name}.\n"
        f"Data Teks:\n{prompt_text}\n\n"
        "Tugas:\n"
        "Lakukan analisis deduktif tingkat tinggi. Evaluasi secara komprehensif kepribadiannya (orangnya seperti apa), "
        "minat tersembunyi, topik yang ia ikuti, serta gaya komunikasi (formal, humble, reaktif, dll).\n"
        "WAJIB GUNAKAN BAHASA INDONESIA YANG RAPI DAN PROFESIONAL (JANGAN GUNAKAN BAHASA INGGRIS).\n\n"
        "Kembalikan output murni dalam format JSON (tanpa markdown blok ```json), dengan struktur berikut:\n"
        "{\n"
        '  "personality_summary": "Tiga paragraf narasi super detail (min. 400 kata), mencakup karakter dasar target, pola interaksi, kecenderungan psikologis, motivasi, hobi, dsb.",\n'
        '  "recent_topics": ["topik_spesifik_1", "topik_spesifik_2", "topik_spesifik_3", "dan lain-lain"],\n'
        '  "communication_style": "Deskripsi mendetail tentang gaya bahasa target di internet. Apakah provokatif, emosional, akademis, pasif, dsb. Beri contoh jika ada.",\n'
        '  "social_behavior_insights": "Analisis mendalam mengenai social footprint target. Apakah ia pamer, mencari validasi eksternal, family-oriented, atau tertutup? Jabarkan dengan rinci."\n'
        "}\n\n"
        "Aturan Mutlak: Jangan berhalusinasi. Evaluasi HANYA berdasarkan data yang diberikan. Jika ada bidang yang tidak bisa diisi dari data, isi dengan null atau string kosong."
    )

    log.info("[SocialPostAnalyzer] Requesting GPT analysis for collected texts (Len: %d chars).", len(prompt_text))
    extracted = await gpt_extract_structured(prompt_text, analysis_prompt)

    result = SocialPostAnalysisResult()
    if extracted:
        result.personality_summary = extracted.get("personality_summary")
        if isinstance(extracted.get("recent_topics"), list):
            result.recent_topics = extracted.get("recent_topics", [])
        result.communication_style = extracted.get("communication_style")
        result.social_behavior_insights = extracted.get("social_behavior_insights")
        result.analyzed_platforms = list(collected_content.keys())
        result.confidence = 0.90
        log.info("[SocialPostAnalyzer] Output successfully generated. Summary Snippet: %s", str(result.personality_summary)[:100])
    else:
        log.warning("[SocialPostAnalyzer] Failed to parse GPT output.")

    return {"social_post_analysis": result}
