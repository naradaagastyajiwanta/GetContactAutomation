"""
Birth City Lookup Agent — focused follow-up to find the rector's birth city.

This agent is ONLY triggered when the rector agent finds the name but NOT
the birth city. It makes a dedicated Gemini + Google Search call focused
solely on discovering where the rector was born.

This is critical because 3 topic agents (tourism birth youth, tourism birth
current, food birth city) depend on knowing the birth city.
"""

from __future__ import annotations

from orchestrator.config import log
from orchestrator.research_agents.gemini_caller import call_gemini
from orchestrator.research_agents.state import RectorInfo, ResearchState


async def birth_city_lookup(state: ResearchState) -> dict:
    """
    LangGraph node: focused search for the rector's birth city/year.

    Updates ``rector_info`` with the found birth city and year,
    preserving all other fields from the original rector agent result.
    """
    ri = state.get("rector_info")
    if not ri or not ri.rector_name or ri.rector_name == "Tidak ditemukan":
        log.warning("[BirthCityLookup] No rector info — skipping")
        return {}

    rector_name = ri.rector_name
    university_name = state["university_name"]

    log.info("[BirthCityLookup] Searching birth city for: %s", rector_name)

    prompt = f"""Kamu research assistant. Tugasmu HANYA SATU: cari KOTA KELAHIRAN dan TAHUN LAHIR dari seseorang.

Orang yang dicari: **{rector_name}**
Jabatan: Rektor/Ketua **{university_name}**

Cari dari berbagai sumber:
- Profil resmi di website universitas
- Wikipedia atau profil di wiki lainnya
- Berita pelantikan, wawancara, atau profil di media
- Buku, jurnal, atau publikasi akademik
- Media sosial resmi
- PDDikti atau database pendidikan

PENTING:
- WAJIB gunakan Google Search. Coba berbagai kata kunci:
  * "{rector_name}" biografi
  * "{rector_name}" lahir
  * "{rector_name}" tempat lahir
  * "{rector_name}" profil
  * "{rector_name}" riwayat hidup
- Cari juga varian nama (tanpa gelar, nama panggilan).
- Jika menemukan provinsi tapi bukan kota, tulis provinsinya.
- Jika BENAR-BENAR tidak menemukan dari sumber manapun, jawab null — JANGAN mengarang.

Jawab HANYA JSON (tanpa markdown code block):
{{
    "rector_birth_city": "nama kota/kabupaten kelahiran",
    "rector_birth_year": 1970,
    "confidence": "high/medium/low"
}}
"""

    try:
        parsed, grounding_urls = await call_gemini(prompt, use_search_grounding=True)

        found_city = parsed.get("rector_birth_city")
        found_year = parsed.get("rector_birth_year")
        confidence = parsed.get("confidence", "medium")

        if not grounding_urls:
            confidence = "low"

        # Only update if we actually found something new
        updated_city = found_city or ri.rector_birth_city
        updated_year = found_year or ri.rector_birth_year

        if found_city:
            log.info(
                "[BirthCityLookup] Found birth city: %s (year: %s), sources=%d",
                found_city, found_year, len(grounding_urls),
            )
        else:
            log.warning("[BirthCityLookup] Still could not find birth city for %s", rector_name)

        # Merge new grounding URLs with existing ones
        all_urls = list(dict.fromkeys(ri.grounding_urls + grounding_urls))

        updated_info = RectorInfo(
            rector_name=ri.rector_name,
            rector_birth_year=updated_year,
            rector_birth_city=updated_city,
            university_city=ri.university_city,
            source_url=ri.source_url,
            grounding_urls=all_urls,
            confidence=ri.confidence if ri.confidence == "high" else confidence,
            raw_text=ri.raw_text,
        )

        return {"rector_info": updated_info}

    except Exception as e:
        log.error("[BirthCityLookup] Failed for %s: %s", rector_name, e, exc_info=True)
        # Don't break — just keep original rector_info
        return {}
