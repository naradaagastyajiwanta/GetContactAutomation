"""
Topic Agents — 5 dedicated agents for tourism & food research.

Each agent makes its own focused Gemini call with Google Search grounding,
yielding more accurate results and properly traceable source URLs.

Agents:
    tourism_birth_youth_agent   — tourist spots in rector's birth city (~15 yrs old)
    tourism_birth_current_agent — current tourist spots in rector's birth city
    tourism_uni_city_agent      — current tourist spots in university city
    food_birth_city_agent       — famous food in rector's birth city
    food_uni_city_agent         — famous food in university city
"""

from __future__ import annotations

from datetime import datetime

from orchestrator.config import log
from orchestrator.research_agents.gemini_caller import call_gemini
from orchestrator.research_agents.state import ResearchState, TopicResult


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _make_topic_result(parsed: dict, grounding_urls: list[str], agent_name: str) -> TopicResult:
    """Build a TopicResult from parsed Gemini output + grounding URLs.
    
    Soft grounding policy: accept the result but downgrade confidence
    if no grounding URLs are present. The reviewer will flag unverified
    results for retry. This avoids throwing away valid answers for
    obscure topics where Google doesn't attach grounding metadata.
    """
    content = parsed.get("content", "Tidak ditemukan")
    confidence = parsed.get("confidence", "medium")

    if not grounding_urls:
        log.warning("[%s] No grounding sources — accepting with low confidence (unverified)", agent_name)
        confidence = "low"  # downgrade, but don't reject
        content = f"{content} [⚠️ belum terverifikasi — tanpa sumber Google Search]"

    return TopicResult(
        content=content,
        source_url=grounding_urls[0] if grounding_urls else None,
        grounding_urls=grounding_urls,
        confidence=confidence,
    )


def _get_rector_fields(state: ResearchState) -> tuple[str | None, int | None, str | None]:
    """Extract birth_city, birth_year, university_city from state."""
    ri = state.get("rector_info")
    if not ri:
        return None, None, None
    return ri.rector_birth_city, ri.rector_birth_year, ri.university_city


# ---------------------------------------------------------------------------
# Agent 1: Tourism — rector birth city (youth era)
# ---------------------------------------------------------------------------

async def tourism_birth_youth_agent(state: ResearchState) -> dict:
    """Gemini call: famous tourism spots in rector's birth city during their youth."""
    birth_city, birth_year, _ = _get_rector_fields(state)
    current_year = datetime.now().year

    if not birth_city or birth_city == "Tidak ditemukan":
        log.warning("[TourismBirthYouth] No birth city available, skipping")
        return {
            "tourism_birth_youth": TopicResult(
                content="Tidak dapat dicari — kota kelahiran rektor tidak diketahui",
                confidence="low",
            )
        }

    youth_year = (birth_year + 15) if birth_year else "tidak diketahui"

    prompt = f"""Kamu research assistant. Tugasmu HANYA satu:
Cari 2–3 tempat wisata TERKENAL di kota **{birth_city}** yang populer sekitar tahun **{youth_year}**.

Fokus pada tempat yang mungkin dikunjungi warga lokal saat remaja di era tersebut.
Jika tahun tidak diketahui, cari wisata ikonik/legendaris yang sudah ada sejak lama di {birth_city}.

PENTING:
- WAJIB gunakan Google Search untuk menemukan informasi.
- Semua jawaban HARUS berdasarkan hasil pencarian, BUKAN pengetahuan internal.
- Jika tidak menemukan informasi dari sumber terpercaya, jawab "Tidak ditemukan".
- JANGAN mengarang atau mengasumsikan informasi tanpa sumber.

Jawab HANYA JSON (tanpa code block):
{{"content": "Deskripsi 2-3 wisata terkenal di {birth_city} era ~{youth_year}", "confidence": "high/medium/low"}}
"""

    log.info("[TourismBirthYouth] Searching tourism in %s (~%s)", birth_city, youth_year)
    try:
        parsed, urls = await call_gemini(prompt, use_search_grounding=True)
        result = _make_topic_result(parsed, urls, "TourismBirthYouth")
        log.info("[TourismBirthYouth] Done: %s (sources=%d)", result.confidence, len(urls))
        return {"tourism_birth_youth": result}
    except Exception as e:
        log.error("[TourismBirthYouth] Failed: %s", e, exc_info=True)
        return {"tourism_birth_youth": TopicResult(content=f"Error: {e}", confidence="low")}


# ---------------------------------------------------------------------------
# Agent 2: Tourism — rector birth city (current)
# ---------------------------------------------------------------------------

async def tourism_birth_current_agent(state: ResearchState) -> dict:
    """Gemini call: currently popular tourism in rector's birth city."""
    birth_city, _, _ = _get_rector_fields(state)
    current_year = datetime.now().year

    if not birth_city or birth_city == "Tidak ditemukan":
        log.warning("[TourismBirthCurrent] No birth city available, skipping")
        return {
            "tourism_birth_current": TopicResult(
                content="Tidak dapat dicari — kota kelahiran rektor tidak diketahui",
                confidence="low",
            )
        }

    prompt = f"""Kamu research assistant. Tugasmu HANYA satu:
Cari 2–3 tempat wisata yang sedang POPULER/TRENDING di kota **{birth_city}** saat ini (tahun {current_year}).

Fokus pada tempat wisata yang baru, viral, atau sedang ramai dikunjungi.

PENTING:
- WAJIB gunakan Google Search untuk menemukan informasi.
- Semua jawaban HARUS berdasarkan hasil pencarian, BUKAN pengetahuan internal.
- Jika tidak menemukan informasi dari sumber terpercaya, jawab "Tidak ditemukan".
- JANGAN mengarang atau mengasumsikan informasi tanpa sumber.

Jawab HANYA JSON (tanpa code block):
{{"content": "Deskripsi 2-3 wisata populer saat ini di {birth_city}", "confidence": "high/medium/low"}}
"""

    log.info("[TourismBirthCurrent] Searching current tourism in %s", birth_city)
    try:
        parsed, urls = await call_gemini(prompt, use_search_grounding=True)
        result = _make_topic_result(parsed, urls, "TourismBirthCurrent")
        log.info("[TourismBirthCurrent] Done: %s (sources=%d)", result.confidence, len(urls))
        return {"tourism_birth_current": result}
    except Exception as e:
        log.error("[TourismBirthCurrent] Failed: %s", e, exc_info=True)
        return {"tourism_birth_current": TopicResult(content=f"Error: {e}", confidence="low")}


# ---------------------------------------------------------------------------
# Agent 3: Tourism — university city (current)
# ---------------------------------------------------------------------------

async def tourism_uni_city_agent(state: ResearchState) -> dict:
    """Gemini call: currently popular tourism in the university's city."""
    _, _, uni_city = _get_rector_fields(state)
    current_year = datetime.now().year

    # Fallback to input university_city if rector agent didn't find one
    if not uni_city:
        uni_city = state.get("university_city")

    if not uni_city or uni_city == "Tidak ditemukan":
        log.warning("[TourismUniCity] No university city available, skipping")
        return {
            "tourism_uni_city": TopicResult(
                content="Tidak dapat dicari — kota kampus tidak diketahui",
                confidence="low",
            )
        }

    prompt = f"""Kamu research assistant. Tugasmu HANYA satu:
Cari 2–3 tempat wisata yang sedang POPULER di kota **{uni_city}** saat ini (tahun {current_year}).

Fokus tempat wisata yang cocok untuk ice-breaking topic dalam meeting profesional.

PENTING:
- WAJIB gunakan Google Search untuk menemukan informasi.
- Semua jawaban HARUS berdasarkan hasil pencarian, BUKAN pengetahuan internal.
- Jika tidak menemukan informasi dari sumber terpercaya, jawab "Tidak ditemukan".
- JANGAN mengarang atau mengasumsikan informasi tanpa sumber.

Jawab HANYA JSON (tanpa code block):
{{"content": "Deskripsi 2-3 wisata populer di {uni_city} saat ini", "confidence": "high/medium/low"}}
"""

    log.info("[TourismUniCity] Searching tourism in %s", uni_city)
    try:
        parsed, urls = await call_gemini(prompt, use_search_grounding=True)
        result = _make_topic_result(parsed, urls, "TourismUniCity")
        log.info("[TourismUniCity] Done: %s (sources=%d)", result.confidence, len(urls))
        return {"tourism_uni_city": result}
    except Exception as e:
        log.error("[TourismUniCity] Failed: %s", e, exc_info=True)
        return {"tourism_uni_city": TopicResult(content=f"Error: {e}", confidence="low")}


# ---------------------------------------------------------------------------
# Agent 4: Food — rector birth city
# ---------------------------------------------------------------------------

async def food_birth_city_agent(state: ResearchState) -> dict:
    """Gemini call: famous food in rector's birth city."""
    birth_city, _, _ = _get_rector_fields(state)

    if not birth_city or birth_city == "Tidak ditemukan":
        log.warning("[FoodBirthCity] No birth city available, skipping")
        return {
            "food_birth_city": TopicResult(
                content="Tidak dapat dicari — kota kelahiran rektor tidak diketahui",
                confidence="low",
            )
        }

    prompt = f"""Kamu research assistant. Tugasmu HANYA satu:
Cari 2–3 makanan KHAS/TERKENAL di kota **{birth_city}**.

Fokus pada makanan yang:
- Benar-benar identik dengan kota tersebut
- Bisa jadi bahan percakapan yang menarik
- Terkenal secara nasional maupun lokal

PENTING:
- WAJIB gunakan Google Search untuk menemukan informasi.
- Semua jawaban HARUS berdasarkan hasil pencarian, BUKAN pengetahuan internal.
- Jika tidak menemukan informasi dari sumber terpercaya, jawab "Tidak ditemukan".
- JANGAN mengarang atau mengasumsikan informasi tanpa sumber.

Jawab HANYA JSON (tanpa code block):
{{"content": "Deskripsi 2-3 makanan khas terkenal di {birth_city}", "confidence": "high/medium/low"}}
"""

    log.info("[FoodBirthCity] Searching food in %s", birth_city)
    try:
        parsed, urls = await call_gemini(prompt, use_search_grounding=True)
        result = _make_topic_result(parsed, urls, "FoodBirthCity")
        log.info("[FoodBirthCity] Done: %s (sources=%d)", result.confidence, len(urls))
        return {"food_birth_city": result}
    except Exception as e:
        log.error("[FoodBirthCity] Failed: %s", e, exc_info=True)
        return {"food_birth_city": TopicResult(content=f"Error: {e}", confidence="low")}


# ---------------------------------------------------------------------------
# Agent 5: Food — university city
# ---------------------------------------------------------------------------

async def food_uni_city_agent(state: ResearchState) -> dict:
    """Gemini call: famous food in the university's city."""
    _, _, uni_city = _get_rector_fields(state)

    # Fallback
    if not uni_city:
        uni_city = state.get("university_city")

    if not uni_city or uni_city == "Tidak ditemukan":
        log.warning("[FoodUniCity] No university city available, skipping")
        return {
            "food_uni_city": TopicResult(
                content="Tidak dapat dicari — kota kampus tidak diketahui",
                confidence="low",
            )
        }

    prompt = f"""Kamu research assistant. Tugasmu HANYA satu:
Cari 2–3 makanan KHAS/TERKENAL di kota **{uni_city}**.

Fokus pada makanan yang:
- Identik dengan kota tersebut
- Cocok jadi bahan percakapan dalam meeting
- Dikenal luas

PENTING:
- WAJIB gunakan Google Search untuk menemukan informasi.
- Semua jawaban HARUS berdasarkan hasil pencarian, BUKAN pengetahuan internal.
- Jika tidak menemukan informasi dari sumber terpercaya, jawab "Tidak ditemukan".
- JANGAN mengarang atau mengasumsikan informasi tanpa sumber.

Jawab HANYA JSON (tanpa code block):
{{"content": "Deskripsi 2-3 makanan khas terkenal di {uni_city}", "confidence": "high/medium/low"}}
"""

    log.info("[FoodUniCity] Searching food in %s", uni_city)
    try:
        parsed, urls = await call_gemini(prompt, use_search_grounding=True)
        result = _make_topic_result(parsed, urls, "FoodUniCity")
        log.info("[FoodUniCity] Done: %s (sources=%d)", result.confidence, len(urls))
        return {"food_uni_city": result}
    except Exception as e:
        log.error("[FoodUniCity] Failed: %s", e, exc_info=True)
        return {"food_uni_city": TopicResult(content=f"Error: {e}", confidence="low")}
