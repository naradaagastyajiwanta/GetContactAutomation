"""
Audiensi Research Service
-------------------------
Uses Gemini AI with Google Search grounding to research background info
for upcoming audiensi meetings (H-1).

For each audiensi, it researches:
1. Nama rektor aktif tahun ini
2. Kota kelahiran rektor
3. Kota lokasi kampus
4. Wisata terkenal di kota kelahiran rektor saat usia ~15 tahun
5. Wisata terkenal di kota kelahiran rektor saat ini
6. Wisata terkenal di kota kampus saat ini
7. Makanan terkenal di kota kelahiran rektor
8. Makanan terkenal di kota kampus

Results are stored in SQLite and can be sent via WhatsApp.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, date, timedelta
from typing import Any

from google import genai
from google.genai import types

from orchestrator.config import log, cfg


def _use_multi_agent() -> bool:
    """Check if multi-agent pipeline is enabled via config."""
    val = cfg.get("RESEARCH_USE_MULTI_AGENT", False)
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------

_client: genai.Client | None = None

GEMINI_MODEL = "gemini-3.1-pro-preview"


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = cfg.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not configured")
        _client = genai.Client(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Core research function
# ---------------------------------------------------------------------------


async def research_university_background(
    university_name: str,
    university_city: str | None = None,
    schedule_date: str | None = None,
) -> dict[str, Any]:
    """
    Research background information for an upcoming audiensi.

    Uses Gemini with Google Search grounding to find:
    - Active rector name and birth city
    - Famous tourist spots & food in relevant cities

    Returns a dict with structured research results.

    When RESEARCH_USE_MULTI_AGENT=true, delegates to the LangGraph
    multi-agent pipeline (1 question = 1 agent + reviewer).
    Otherwise falls back to the legacy single-prompt approach.
    """
    if _use_multi_agent():
        log.info("Using MULTI-AGENT pipeline for: %s", university_name)
        from orchestrator.research_agents.graph import run_research
        return await run_research(university_name, university_city, schedule_date)

    log.info("Using LEGACY single-call pipeline for: %s", university_name)
    return await _legacy_research_university_background(
        university_name, university_city, schedule_date
    )


async def _legacy_research_university_background(
    university_name: str,
    university_city: str | None = None,
    schedule_date: str | None = None,
) -> dict[str, Any]:
    """
    Legacy single-prompt research (original implementation).
    Kept as fallback when RESEARCH_USE_MULTI_AGENT=false.
    """
    current_year = datetime.now().year

    prompt = f"""Kamu adalah research assistant untuk persiapan meeting audiensi dengan universitas di Indonesia.

Universitas: **{university_name}**
{f'Kota/lokasi kampus: {university_city}' if university_city else ''}
Tanggal audiensi: {schedule_date or 'segera'}
Tahun sekarang: {current_year}

Tolong carikan informasi berikut dengan DETAIL dan AKURAT. Gunakan Google Search untuk memverifikasi:

1. **Nama Rektor Aktif** — Siapa rektor {university_name} yang sedang menjabat di tahun {current_year}? Sebutkan nama lengkap beserta gelarnya.

2. **Kota Kelahiran Rektor** — Di kota/kabupaten mana rektor tersebut lahir? Dan kapan tahun lahirnya?

3. **Kota Lokasi Kampus** — Di kota mana kampus utama {university_name} berada?

4. **Wisata Terkenal di Kota Kelahiran Rektor (saat usia ~15 tahun)** — Apa wisata/tempat terkenal di kota kelahiran rektor sekitar 15 tahun setelah dia lahir? (tempat yang mungkin pernah dikunjungi saat remaja)

5. **Wisata Terkenal di Kota Kelahiran Rektor (saat ini {current_year})** — Apa wisata yang sedang populer/terkenal di kota kelahiran rektor saat ini?

6. **Wisata Terkenal di Kota Kampus (saat ini {current_year})** — Apa wisata yang sedang populer/terkenal di kota lokasi kampus saat ini?

7. **Makanan Terkenal di Kota Kelahiran Rektor** — Apa makanan khas/terkenal di kota kelahiran rektor?

8. **Makanan Terkenal di Kota Kampus** — Apa makanan khas/terkenal di kota lokasi kampus?

FORMAT JAWABAN (JSON):
Jawab ONLY dalam format JSON valid berikut, tanpa markdown code block:
{{
    "rector_name": "nama lengkap dengan gelar",
    "rector_birth_year": 1970,
    "rector_birth_city": "nama kota/kabupaten",
    "rector_source": "URL sumber informasi rektor (wajib — link artikel/berita/web resmi)",
    "university_city": "nama kota kampus",
    "tourism_rector_birth_youth": "deskripsi 2-3 wisata terkenal saat rektor remaja (~15 thn setelah lahir)",
    "tourism_rector_birth_youth_source": "URL sumber untuk pernyataan wisata ini",
    "tourism_rector_birth_current": "deskripsi 2-3 wisata yang sedang populer di kota kelahiran rektor saat ini",
    "tourism_rector_birth_current_source": "URL sumber untuk pernyataan wisata ini",
    "tourism_university_city": "deskripsi 2-3 wisata yang sedang populer di kota kampus saat ini",
    "tourism_university_city_source": "URL sumber untuk pernyataan wisata ini",
    "food_rector_birth_city": "deskripsi 2-3 makanan khas terkenal di kota kelahiran rektor",
    "food_rector_birth_city_source": "URL sumber untuk pernyataan makanan ini",
    "food_university_city": "deskripsi 2-3 makanan khas terkenal di kota kampus",
    "food_university_city_source": "URL sumber untuk pernyataan makanan ini",
    "notes": "catatan tambahan yang relevan untuk percakapan (opsional)"
}}

PENTING:
- Jika tidak bisa menemukan info tertentu, isi dengan "Tidak ditemukan" disertai alasan.
- Prioritaskan akurasi, jangan mengada-ada.
- Setiap field *_source WAJIB diisi dengan URL aktual hasil Google Search — bukan placeholder.
- URL harus dapat dikunjungi dan relevan dengan pernyataan di field yang bersangkutan.
- Format URL harus lengkap: https://...
"""

    try:
        client = _get_client()

        tools = [types.Tool(google_search=types.GoogleSearch())]

        config = types.GenerateContentConfig(
            tools=tools,
        )

        # Run in thread pool since the SDK may be sync
        result = await asyncio.to_thread(
            _call_gemini_sync, client, prompt, config
        )

        return result

    except Exception as e:
        log.error("Gemini research failed for %s: %s", university_name, e, exc_info=True)
        return {
            "error": str(e),
            "rector_name": "Tidak ditemukan",
            "rector_birth_year": None,
            "rector_birth_city": "Tidak ditemukan",
            "rector_source": "",
            "university_city": university_city or "Tidak ditemukan",
            "tourism_rector_birth_youth": "Tidak ditemukan",
            "tourism_rector_birth_youth_source": "",
            "tourism_rector_birth_current": "Tidak ditemukan",
            "tourism_rector_birth_current_source": "",
            "tourism_university_city": "Tidak ditemukan",
            "tourism_university_city_source": "",
            "food_rector_birth_city": "Tidak ditemukan",
            "food_rector_birth_city_source": "",
            "food_university_city": "Tidak ditemukan",
            "food_university_city_source": "",
            "notes": f"Error: {e}",
        }


def _resolve_redirect(url: str, timeout: float = 5.0) -> str:
    """Follow a redirect URL and return the final destination URL.

    Grounding URLs are short-lived redirect links like:
      https://vertexaisearch.cloud.google.com/grounding-api-redirect/...
    We must resolve them immediately after the API call before they expire.
    """
    import urllib.request
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final = resp.geturl()
            if final and final != url:
                return final
    except Exception:
        # HEAD might be blocked — try GET but only read headers
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                final = resp.geturl()
                if final and final != url:
                    return final
        except Exception as e2:
            log.debug("Could not resolve redirect %s: %s", url[:80], e2)
    return url  # fallback: return original if resolve fails


def _extract_grounding_urls(response: Any) -> list[str]:
    """Extract and resolve real URLs from Gemini grounding metadata.

    Grounding chunks contain short-lived redirect URIs — we resolve them
    immediately to permanent destination URLs before storing.
    """
    raw_urls: list[str] = []
    try:
        candidates = response.candidates or []
        for candidate in candidates:
            gm = getattr(candidate, "grounding_metadata", None)
            if not gm:
                continue
            chunks = getattr(gm, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if web:
                    uri = getattr(web, "uri", None)
                    if uri and uri.startswith("http"):
                        raw_urls.append(uri)
    except Exception as e:
        log.warning("Failed to extract grounding URLs: %s", e)

    # Deduplicate before resolving
    seen_raw: set[str] = set()
    deduped: list[str] = []
    for u in raw_urls:
        if u not in seen_raw:
            seen_raw.add(u)
            deduped.append(u)

    # Resolve redirects → permanent URLs
    resolved: list[str] = []
    seen_final: set[str] = set()
    for u in deduped:
        final = _resolve_redirect(u)
        if final not in seen_final:
            seen_final.add(final)
            resolved.append(final)
            log.debug("Grounding resolved: %s", final[:100])

    return resolved


def _validate_source_fields(result: dict[str, Any], grounding_urls: list[str]) -> dict[str, Any]:
    """Replace AI-generated *_source values with real grounding redirect URLs.

    Grounding URLs are vertexaisearch redirect links (always valid/clickable).
    We assign them round-robin to each source field, then put extras in sources[].
    """
    if not grounding_urls:
        log.warning("No grounding URLs available — sources will be empty")
        return result

    source_fields = [
        "rector_source",
        "tourism_rector_birth_youth_source",
        "tourism_rector_birth_current_source",
        "tourism_university_city_source",
        "food_rector_birth_city_source",
        "food_university_city_source",
    ]

    pool = list(grounding_urls)

    for i, field in enumerate(source_fields):
        if i < len(pool):
            result[field] = pool[i]
        else:
            result[field] = None

    # Remaining grounding URLs → legacy sources list
    leftover = pool[len(source_fields):]
    existing = result.get("sources") or []
    result["sources"] = list(dict.fromkeys(list(existing) + leftover))

    log.info(
        "Source assignment: %d grounding URLs assigned to %d fields, %d leftover",
        len(pool),
        min(len(source_fields), len(pool)),
        len(leftover),
    )
    return result


def _call_gemini_sync(
    client: genai.Client,
    prompt: str,
    config: types.GenerateContentConfig,
) -> dict[str, Any]:
    """Synchronous call to Gemini API (runs in thread pool)."""
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        ),
    ]

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=config,
    )

    raw_text = response.text or ""
    log.info("Gemini research raw response length: %d chars", len(raw_text))

    # Extract real grounding URLs from metadata
    grounding_urls = _extract_grounding_urls(response)
    log.info("Grounding URLs extracted: %d", len(grounding_urls))
    for u in grounding_urls:
        log.debug("  Grounding URL: %s", u)

    # Parse JSON from response
    result = _parse_research_response(raw_text)

    # Replace hallucinated *_source fields with real grounding URLs
    result = _validate_source_fields(result, grounding_urls)

    return result


def _parse_research_response(text: str) -> dict[str, Any]:
    """Parse the JSON response from Gemini, handling various formats."""
    # Try direct JSON parse
    text = text.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    # Fallback: return raw text as notes
    log.warning("Could not parse Gemini response as JSON, returning raw text")
    return {
        "rector_name": "Lihat catatan",
        "rector_birth_year": None,
        "rector_birth_city": "Lihat catatan",
        "university_city": "Lihat catatan",
        "tourism_rector_birth_youth": "Lihat catatan",
        "tourism_rector_birth_current": "Lihat catatan",
        "tourism_university_city": "Lihat catatan",
        "food_rector_birth_city": "Lihat catatan",
        "food_university_city": "Lihat catatan",
        "notes": text[:3000],
        "sources": [],
        "_raw": True,
    }


# ---------------------------------------------------------------------------
# Format WhatsApp message
# ---------------------------------------------------------------------------


def format_research_wa_message(
    university_name: str,
    schedule_date: str,
    schedule_time: str | None,
    research: dict[str, Any],
) -> str:
    """Format research results into a WhatsApp-ready message."""
    current_year = datetime.now().year

    rector = research.get("rector_name", "?")
    birth_year = research.get("rector_birth_year")
    birth_city = research.get("rector_birth_city", "?")
    uni_city = research.get("university_city", "?")

    youth_year = f"~{birth_year + 15}" if birth_year else "?"

    lines = [
        f"📋 *BRIEFING AUDIENSI*",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🏫 *{university_name}*",
        f"📅 {schedule_date}" + (f" • ⏰ {schedule_time} WIB" if schedule_time else ""),
        f"",
        f"👤 *Rektor Aktif ({current_year})*",
        f"   {rector}",
        f"   🎂 Lahir: {birth_city}" + (f" ({birth_year})" if birth_year else ""),
        f"   📍 Kota kampus: {uni_city}",
        f"",
        f"🏖️ *Wisata Kota Kelahiran Rektor*",
        f"   _Saat remaja ({youth_year}):_",
        f"   {research.get('tourism_rector_birth_youth', '-')}",
        f"",
        f"   _Saat ini ({current_year}):_",
        f"   {research.get('tourism_rector_birth_current', '-')}",
        f"",
        f"🗺️ *Wisata Kota Kampus ({uni_city})*",
        f"   {research.get('tourism_university_city', '-')}",
        f"",
        f"🍜 *Makanan Terkenal*",
        f"   _Kota kelahiran rektor ({birth_city}):_",
        f"   {research.get('food_rector_birth_city', '-')}",
        f"",
        f"   _Kota kampus ({uni_city}):_",
        f"   {research.get('food_university_city', '-')}",
    ]

    notes = research.get("notes")
    if notes and notes != "null":
        lines.extend([
            f"",
            f"📝 *Catatan:*",
            f"   {notes}",
        ])

    lines.extend([
        f"",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🤖 _Riset otomatis oleh GetContact AI_",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Research + store + notify for a schedule
# ---------------------------------------------------------------------------


async def research_and_notify_schedule(
    schedule: dict[str, Any],
    notify_phones: list[str] | None = None,
) -> dict[str, Any]:
    """
    Full pipeline for a single schedule:
    1. Research via Gemini
    2. Store result in SQLite
    3. Send WhatsApp notification

    Returns the research result dict.
    """
    from orchestrator.message_queue import message_queue
    from orchestrator.db import get_db, create_pipeline_log, complete_pipeline_log

    raw_uni_name = schedule.get("nama_universitas")
    uni_name = raw_uni_name or f"University #{schedule.get('id_univ', '?')}"
    uni_city = schedule.get("alamat") or schedule.get("alamat_universitas") or None
    jadwal = schedule.get("jadwal_audiensi", "")
    jam = schedule.get("jam_audensi", "")
    schedule_id = schedule.get("id", 0)
    source = schedule.get("source", "schedule_follow_up")

    # Guard: skip if university name is unknown/placeholder (would cause hallucination)
    if not raw_uni_name or raw_uni_name.strip().lower().startswith("university #"):
        log.warning(
            "Skipping research for schedule #%s — university name is placeholder/empty ('%s'). "
            "Wait for DMS sync to populate nama_universitas.",
            schedule_id, uni_name,
        )
        return {"error": "skipped_no_university_name", "schedule_id": schedule_id}

    log.info("Starting audiensi research for: %s (schedule #%s, date %s)",
             uni_name, schedule_id, jadwal)

    # Create pipeline log entry
    pipeline_log_id = await create_pipeline_log(
        agent_type="dms_research",
        trigger_type="manual",
    )

    try:
        # 1. Research
        research = await research_university_background(
            university_name=uni_name,
            university_city=uni_city,
            schedule_date=jadwal,
        )

        # 2. Store in SQLite
        try:
            async with get_db() as db:
                await db.execute("""
                    INSERT OR REPLACE INTO audiensi_research
                    (schedule_id, source, university_name, university_city, schedule_date,
                     research_data, researched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    schedule_id,
                    source,
                    uni_name,
                    research.get("university_city", uni_city),
                    jadwal,
                    json.dumps(research, ensure_ascii=False),
                    datetime.now().isoformat(),
                ))
                await db.commit()
            log.info("Stored research result for schedule #%s in SQLite", schedule_id)
        except Exception as e:
            log.error("Failed to store research: %s", e)

        # 3. Format and send WhatsApp
        wa_message = format_research_wa_message(uni_name, jadwal, jam, research)

        phones = notify_phones or []

        # Also get internal notification phones from config
        internal_phones = cfg.get("DMS_RESEARCH_NOTIFY_PHONES", "")
        if internal_phones:
            for p in internal_phones.split(","):
                p = p.strip()
                if p and p not in phones:
                    phones.append(p)

        for phone in phones:
            try:
                await message_queue.enqueue_send(phone, wa_message)
                log.info("Research notification queued to %s for %s", phone, uni_name)
            except Exception as e:
                log.error("Failed to queue research WA to %s: %s", phone, e)

        research["_wa_sent_to"] = phones
        research["_schedule_id"] = schedule_id
        research["_university_name"] = uni_name

        await complete_pipeline_log(
            pipeline_log_id,
            status="completed",
            summary={
                "university": uni_name,
                "schedule_date": jadwal,
                "rector": research.get("rector_name", "-"),
                "wa_sent": len(phones),
            },
            items_processed=1,
            items_success=1,
        )

        return research

    except Exception as e:
        log.error("Research failed for schedule #%s: %s", schedule_id, e, exc_info=True)
        await complete_pipeline_log(
            pipeline_log_id,
            status="failed",
            error=str(e),
            summary={"university": uni_name, "schedule_date": jadwal},
            items_processed=1,
            items_failed=1,
        )
        raise


# ---------------------------------------------------------------------------
# Batch: research all tomorrow's schedules
# ---------------------------------------------------------------------------


async def get_researched_schedule_ids() -> set[int]:
    """Return set of schedule_ids that already have research stored in SQLite."""
    from orchestrator.db import get_db
    async with get_db() as db:
        cursor = await db.execute("SELECT schedule_id FROM audiensi_research")
        rows = await cursor.fetchall()
    return {(row[0] if isinstance(row, tuple) else row["schedule_id"]) for row in rows}


async def research_tomorrow_schedules() -> list[dict[str, Any]]:
    """
    Find all audiensi schedules for tomorrow and research each one.
    This is the main function called by the scheduler at H-1.
    Skips schedules that have already been researched.
    """
    from orchestrator.dms_mysql import get_upcoming_audiensi_schedules

    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # Get schedules for tomorrow (days_ahead=1, include_past_days=0)
    all_schedules = await get_upcoming_audiensi_schedules(
        days_ahead=2,
        include_past_days=0,
    )

    # Filter exactly tomorrow
    tomorrow_schedules = [
        s for s in all_schedules
        if s.get("jadwal_audiensi", "")[:10] == tomorrow
    ]

    if not tomorrow_schedules:
        log.info("No audiensi schedules for tomorrow (%s)", tomorrow)
        return []

    # Skip already-researched schedules to avoid wasteful Gemini API calls
    already_researched = await get_researched_schedule_ids()
    pending = [s for s in tomorrow_schedules if s.get("id") not in already_researched]

    if not pending:
        log.info("All %d tomorrow (%s) schedules already researched — skipping",
                 len(tomorrow_schedules), tomorrow)
        return []

    log.info("Found %d/%d unresearched schedules for tomorrow (%s), starting research...",
             len(pending), len(tomorrow_schedules), tomorrow)

    results = []
    for schedule in pending:
        try:
            result = await research_and_notify_schedule(schedule)
            results.append(result)
            # Small delay between research calls to avoid rate limiting
            await asyncio.sleep(3)
        except Exception as e:
            log.error("Research failed for schedule %s: %s",
                      schedule.get("id"), e, exc_info=True)
            results.append({"error": str(e), "_schedule_id": schedule.get("id")})

    log.info("Completed research for %d/%d tomorrow schedules",
             len([r for r in results if "error" not in r]),
             len(pending))

    return results


async def research_unresearched_upcoming(days_ahead: int = 3) -> list[dict[str, Any]]:
    """
    Safety-net: find upcoming schedules (H-1 to H-N) that haven't been
    researched yet and research them now.

    Called periodically so that:
    - Newly added schedules get caught
    - Failed researches get retried
    - Nothing reaches the day of audiensi without background info
    """
    from orchestrator.dms_mysql import get_upcoming_audiensi_schedules

    all_schedules = await get_upcoming_audiensi_schedules(
        days_ahead=days_ahead,
        include_past_days=0,
    )

    if not all_schedules:
        return []

    already_researched = await get_researched_schedule_ids()
    unresearched = [s for s in all_schedules if s.get("id") not in already_researched]

    if not unresearched:
        log.info("All %d upcoming schedules (next %d days) already have research",
                 len(all_schedules), days_ahead)
        return []

    log.info(
        "Research safety check: %d/%d upcoming schedules need research — starting...",
        len(unresearched), len(all_schedules),
    )

    results = []
    for schedule in unresearched:
        try:
            result = await research_and_notify_schedule(schedule)
            results.append(result)
            await asyncio.sleep(3)
        except Exception as e:
            log.error("Research (safety check) failed for schedule %s: %s",
                      schedule.get("id"), e, exc_info=True)
            results.append({"error": str(e), "_schedule_id": schedule.get("id")})

    log.info(
        "Research safety check done: %d/%d new schedules researched",
        len([r for r in results if "error" not in r]),
        len(unresearched),
    )
    return results


# ---------------------------------------------------------------------------
# DB schema for storing research results
# ---------------------------------------------------------------------------


async def ensure_research_table():
    """Create the audiensi_research table if it doesn't exist."""
    from orchestrator.db import get_db
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audiensi_research (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'schedule_follow_up',
                university_name TEXT NOT NULL,
                university_city TEXT,
                schedule_date TEXT,
                research_data TEXT NOT NULL,
                researched_at TEXT NOT NULL,
                UNIQUE(schedule_id, source)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_research_schedule_date
            ON audiensi_research(schedule_date)
        """)
        # Migrate: add source column if missing (table was created before source support)
        try:
            cursor = await db.execute("PRAGMA table_info(audiensi_research)")
            cols = await cursor.fetchall()
            col_names = [c[1] if isinstance(c, tuple) else c["name"] for c in cols]
            if "source" not in col_names:
                await db.execute(
                    "ALTER TABLE audiensi_research ADD COLUMN source TEXT NOT NULL DEFAULT 'schedule_follow_up'"
                )
                log.info("Migrated audiensi_research: added 'source' column")
        except Exception as e:
            log.warning("audiensi_research migration check: %s", e)
        await db.commit()
    log.info("audiensi_research table ensured")


async def get_research_by_schedule_id(schedule_id: int) -> dict | None:
    """Get stored research result for a schedule."""
    from orchestrator.db import get_db
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM audiensi_research WHERE schedule_id = ?",
            (schedule_id,),
        )
        row = await cursor.fetchone()
    if row:
        r = dict(row)
        if r.get("research_data"):
            try:
                r["research_data"] = json.loads(r["research_data"])
            except json.JSONDecodeError:
                pass
        return r
    return None


async def get_research_by_date(target_date: str) -> list[dict]:
    """Get all research results for a specific date."""
    from orchestrator.db import get_db
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM audiensi_research WHERE schedule_date = ? ORDER BY researched_at DESC",
            (target_date,),
        )
        rows = await cursor.fetchall()
    results = []
    for row in rows:
        r = dict(row)
        if r.get("research_data"):
            try:
                r["research_data"] = json.loads(r["research_data"])
            except json.JSONDecodeError:
                pass
        results.append(r)
    return results


async def get_all_research(limit: int = 50) -> list[dict]:
    """Get recent research results."""
    from orchestrator.db import get_db
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM audiensi_research ORDER BY researched_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    results = []
    for row in rows:
        r = dict(row)
        if r.get("research_data"):
            try:
                r["research_data"] = json.loads(r["research_data"])
            except json.JSONDecodeError:
                pass
        results.append(r)
    return results
