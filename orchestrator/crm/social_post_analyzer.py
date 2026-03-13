"""
Social Post Analyzer Agent
Scrapes recent posts from identified social media accounts to determine
the person's personality and character traits (orangnya seperti apa).
Uses headless browser fetching and LLM analysis.
"""

from __future__ import annotations

import json
from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, SocialPostAnalysisResult
from orchestrator.crm.tools import fetch_page, extract_text_from_html, gpt_extract_structured, ddg_search

async def social_post_analyzer_agent(state: CrmState) -> dict:
    identity = state.get("identity")
    social = state.get("social_profile")
    pic_name = state.get("pic_name", "")
    
    full_name = (identity.full_name if identity else None) or pic_name
    log.info("[SocialPostAnalyzer] Starting for %s", full_name)
    
    if not social:
        log.info("[SocialPostAnalyzer] Skipped - no social profile found.")
        return {"social_post_analysis": SocialPostAnalysisResult()}

    collected_content: dict[str, str] = {}
    
    # Facebook Phase
    if social.facebook_url:
        log.info("[SocialPostAnalyzer] Scraping Facebook timeline: %s", social.facebook_url)
        fb_html = await fetch_page(social.facebook_url, timeout=25.0)
        if fb_html:
            text = extract_text_from_html(fb_html, max_chars=12000)
            if len(text) > 100:
                collected_content["Facebook"] = text
                
    # Instagram Phase
    if social.instagram_handle and social.instagram_handle != "None" and social.instagram_handle.lower() != "tidak ditemukan":
        ig_url = f"https://www.instagram.com/{social.instagram_handle.strip('@')}/"
        log.info("[SocialPostAnalyzer] Scraping Instagram timeline: %s", ig_url)
        ig_html = await fetch_page(ig_url, timeout=25.0)
        if ig_html:
            text = extract_text_from_html(ig_html, max_chars=10000)
            if len(text) > 100:
                collected_content["Instagram"] = text
                
    # Twitter / X Phase
    if social.twitter_handle and social.twitter_handle != "None" and social.twitter_handle.lower() != "tidak ditemukan":
        x_url = f"https://x.com/{social.twitter_handle.strip('@')}"
        log.info("[SocialPostAnalyzer] Scraping Twitter timeline: %s", x_url)
        x_html = await fetch_page(x_url, timeout=20.0)
        if x_html:
            collected_content["Twitter"] = extract_text_from_html(x_html, max_chars=6000)

    # If no content found from direct scraping, attempt DDG search for their posts
    if not collected_content:
        log.info("[SocialPostAnalyzer] No direct scrape content, attempting post dorking...")
        q = f'"{full_name}" site:facebook.com OR site:instagram.com OR site:medium.com OR site:kompasiana.com'
        hits = await ddg_search(q, max_results=4)
        if hits:
            snippets = "\n".join(h.get("snippet", "") for h in hits)
            if len(snippets) > 50:
                collected_content["Search Snippets"] = snippets
                
    if not collected_content:
        log.info("[SocialPostAnalyzer] Finished - no post content could be extracted.")
        return {"social_post_analysis": SocialPostAnalysisResult()}

    # Compile the giant text wall
    prompt_text = ""
    for platform, text in collected_content.items():
        prompt_text += f"\n=== {platform} CONTENT ===\n{text[:8000]}\n"
        
    analysis_prompt = (
        f"Anda adalah seorang psikolog klinis dan ahli OSINT FBI.\n"
        f"Berikut adalah teks mentah (berisi profile, postingan, timeline, atau komentar) dari akun media sosial atau jejak digital milik: {full_name}.\n"
        f"Analisis secara mendalam karakter dan sifatnya (seperti halnya profiling FBI).\n\n"
        f"Teks:\n{prompt_text}\n\n"
        "Tugas: Evaluasi 'orangnya seperti apa', gaya bahasanya, behavior sosial, dan topik yang akhir-akhir ini dia bahas.\n"
        "Kembalikan output murni dalam JSON (tanpa markdown), dengan struktur berikut:\n"
        "{\n"
        '  "personality_summary": "Dua/Tiga paragraf ringkas namun mendalam tentang profil kepribadiannya serta minatnya. Jabarkan dengan bahasa Indonesia yang rapi dan profesional.",\n'
        '  "recent_topics": ["topik_1", "topik_2", "topik_3"],\n'
        '  "communication_style": "Gaya komunikasi (misal: formal, santai, ceplas-ceplos, suka humor, kaku, agresif dll)",\n'
        '  "social_behavior_insights": "Bagaimana dia berinteraksi secara sosial? (Misalnya: suka pamer, aktif membagikan pencapaian, reaktif, atau menjaga privasi, dsb)"\n'
        "}\n"
        "Catatan mutlak: Lakukan profiling (meski secara deduktif/menebak) berdasarkan data yang ada meskipun kelihatannya sedikit. Jangan biarkan field kosong."
    )
    
    log.info("[SocialPostAnalyzer] Requesting GPT analysis for collected texts.")
    extracted = await gpt_extract_structured(prompt_text, analysis_prompt)
    
    result = SocialPostAnalysisResult()
    if extracted:
        result.personality_summary = extracted.get("personality_summary")
        if isinstance(extracted.get("recent_topics"), list):
            result.recent_topics = extracted.get("recent_topics", [])
        result.communication_style = extracted.get("communication_style")
        result.social_behavior_insights = extracted.get("social_behavior_insights")
        result.analyzed_platforms = list(collected_content.keys())
        result.confidence = 0.85
        log.info("[SocialPostAnalyzer] Output successfully generated. Summary: %s", result.personality_summary)
    else:
        log.warning("[SocialPostAnalyzer] Failed to parse GPT output.")
        
    return {"social_post_analysis": result}