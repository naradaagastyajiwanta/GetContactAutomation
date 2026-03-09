"""
Psychographics Agent — analyzes the rector's personality, values, and character
based on publicly available online information.

Researches:
- Leadership style & communication patterns
- Values, beliefs, and public advocacy
- Academic focus areas & intellectual interests
- Personality traits inferred from public appearances, writings, interviews
- Social/community engagement patterns

This agent runs in parallel with topic agents after the rector is identified.
It uses the rector's full name to search for interviews, articles, speeches,
and other public content that reveals their psychographic profile.
"""

from __future__ import annotations

from orchestrator.config import log
from orchestrator.research_agents.gemini_caller import call_gemini
from orchestrator.research_agents.state import ResearchState, TopicResult


async def psychographics_agent(state: ResearchState) -> dict:
    """
    LangGraph node: research the rector's psychographic profile.

    Uses Google Search to find public information about the rector
    (interviews, speeches, articles, academic works) and synthesize
    a personality/character profile useful for meeting preparation.

    Returns partial state update with ``psychographics``.
    """
    ri = state.get("rector_info")
    university_name = state["university_name"]

    if not ri or not ri.rector_name or ri.rector_name == "Tidak ditemukan":
        log.warning("[Psychographics] No rector info — skipping")
        return {
            "psychographics": TopicResult(
                content="Tidak ditemukan — data rektor tidak tersedia",
                confidence="low",
            )
        }

    rector_name = ri.rector_name
    log.info("[Psychographics] Analyzing profile for: %s (%s)", rector_name, university_name)

    prompt = f"""Kamu adalah research assistant khusus menganalisis profil psikografis seorang pemimpin universitas di Indonesia.

Rektor: **{rector_name}**
Universitas: **{university_name}**

Tugas kamu: Cari dan analisis informasi publik tentang {rector_name} untuk memahami karakter, kepribadian, dan gaya kepemimpinannya.

Cari dari sumber online:
1. **Gaya Kepemimpinan**: Bagaimana beliau memimpin? (visioner, konservatif, inovatif, kolaboratif, dll)
2. **Nilai & Keyakinan**: Apa yang sering beliau advokasi? Apa prinsip-prinsip yang sering ditekankan?
3. **Fokus Akademik/Intelektual**: Bidang keahlian, penelitian, atau topik yang sering dibahas
4. **Karakter Publik**: Bagaimana beliau tampil di publik? (tegas, ramah, karismatik, pendiam, dll)
5. **Engagement Sosial**: Aktivitas di luar kampus — organisasi, gerakan sosial, media sosial

PENTING:
- WAJIB gunakan Google Search. Cari: wawancara, pidato, artikel, profil, media sosial, berita tentang {rector_name}.
- Analisis HANYA berdasarkan data yang ditemukan — JANGAN mengarang atau berasumsi.
- Jika hanya sedikit data ditemukan, jelaskan apa yang ada dan note bahwa data terbatas.
- Jika tidak menemukan informasi sama sekali, jawab "Tidak ditemukan".
- Tulis dalam bahasa Indonesia, ringkas tapi informatif (3-5 paragraf).
- Fokus pada insight yang berguna untuk persiapan meeting/audiensi.

Jawab HANYA dalam format JSON (tanpa markdown code block):
{{
    "content": "Analisis psikografis lengkap di sini...",
    "confidence": "high/medium/low"
}}
"""

    try:
        parsed, grounding_urls = await call_gemini(prompt, use_search_grounding=True)

        content = parsed.get("content", "Tidak ditemukan")
        confidence = parsed.get("confidence", "medium")

        if not grounding_urls:
            log.warning("[Psychographics] No grounding sources — accepting with low confidence")
            confidence = "low"
            content = f"{content} [⚠️ belum terverifikasi — tanpa sumber Google Search]"

        result = TopicResult(
            content=content,
            source_url=grounding_urls[0] if grounding_urls else None,
            grounding_urls=grounding_urls,
            confidence=confidence,
        )

        log.info(
            "[Psychographics] Done for %s: confidence=%s, sources=%d, content_len=%d",
            rector_name,
            result.confidence,
            len(grounding_urls),
            len(result.content),
        )

        return {"psychographics": result}

    except Exception as e:
        log.error("[Psychographics] Failed for %s: %s", rector_name, e, exc_info=True)
        return {
            "psychographics": TopicResult(
                content=f"Error: {e}",
                confidence="low",
            )
        }
