"""
Rector Agent — dedicated agent for finding the active rector profile.

Researches:
- Full name with academic title
- Year of birth
- City/regency of birth
- City of the main campus

This agent MUST run first because all topic agents depend on its output
(birth city, university city).
"""

from __future__ import annotations

from datetime import datetime

from orchestrator.config import log
from orchestrator.research_agents.gemini_caller import call_gemini
from orchestrator.research_agents.state import RectorInfo, ResearchState


async def rector_agent(state: ResearchState) -> dict:
    """
    LangGraph node: research rector profile via Gemini + Google Search.

    Returns partial state update with ``rector_info``.
    """
    university_name = state["university_name"]
    university_city = state.get("university_city") or ""
    current_year = datetime.now().year

    prompt = f"""Kamu research assistant khusus mencari profil REKTOR universitas di Indonesia.

Universitas: **{university_name}**
{f'Lokasi kampus: {university_city}' if university_city else ''}
Tahun sekarang: {current_year}

Tugas kamu HANYA satu: cari informasi tentang REKTOR AKTIF universitas ini.

Carikan:
1. Nama lengkap rektor beserta gelar akademiknya yang sedang menjabat di {current_year}
2. Tahun lahir rektor
3. Kota/kabupaten kelahiran rektor
4. Kota lokasi kampus utama {university_name}

PENTING:
- Pastikan ini rektor yang SEDANG MENJABAT, bukan mantan rektor.
- Cari dari sumber resmi: website universitas, berita pelantikan, SK Kemendikti.
- WAJIB gunakan Google Search untuk verifikasi. Semua informasi HARUS bersumber dari hasil pencarian.
- Jika tidak menemukan dari sumber terpercaya, tulis "Tidak ditemukan" — JANGAN mengarang.
- Jika hanya menemukan sebagian info (misal nama tapi tidak tahun lahir), isi yang ada saja, sisanya null.

Jawab HANYA dalam format JSON (tanpa markdown code block):
{{
    "rector_name": "nama lengkap dengan gelar",
    "rector_birth_year": 1970,
    "rector_birth_city": "nama kota/kabupaten kelahiran",
    "university_city": "nama kota kampus utama",
    "confidence": "high/medium/low"
}}
"""

    log.info("[RectorAgent] Researching rector for: %s", university_name)

    try:
        parsed, grounding_urls = await call_gemini(prompt, use_search_grounding=True)

        rector_name = parsed.get("rector_name", "Tidak ditemukan")

        # Soft grounding: accept result but downgrade confidence if no sources
        confidence = parsed.get("confidence", "medium")
        if not grounding_urls:
            log.warning(
                "[RectorAgent] No grounding sources for %s — accepting with low confidence (unverified)",
                university_name,
            )
            confidence = "low"  # downgrade, but don't reject

        rector_info = RectorInfo(
            rector_name=rector_name,
            rector_birth_year=parsed.get("rector_birth_year"),
            rector_birth_city=parsed.get("rector_birth_city"),
            university_city=parsed.get("university_city") or university_city or None,
            source_url=grounding_urls[0] if grounding_urls else None,
            grounding_urls=grounding_urls,
            confidence=confidence,
            raw_text=str(parsed),
        )

        log.info(
            "[RectorAgent] Found: %s (birth: %s, %s) confidence=%s, sources=%d",
            rector_info.rector_name,
            rector_info.rector_birth_city,
            rector_info.rector_birth_year,
            rector_info.confidence,
            len(grounding_urls),
        )

        return {"rector_info": rector_info}

    except Exception as e:
        log.error("[RectorAgent] Failed for %s: %s", university_name, e, exc_info=True)
        return {
            "rector_info": RectorInfo(
                rector_name="Tidak ditemukan",
                rector_birth_city=None,
                university_city=university_city or None,
                confidence="low",
                raw_text=f"Error: {e}",
            )
        }
