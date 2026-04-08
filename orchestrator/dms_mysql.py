"""
DMS MySQL Integration Module
-----------------------------
Connects to the DMS (Document Management System) MySQL database
to read audiensi schedules, follow-up data, and sync contacts.

Tables used:
- schedule_follow_up            — audiensi schedules (jadwal_audiensi, jam_audensi, link_zoom)
- schedule_follow_up           — regular audiensi schedules
- schedule_follow_up_lsp       — LSP audiensi (joined with meeting_audiensi)
- follow_up_tbls                — follow-up activity logs per university
- meeting_audiensi              — Zoom meeting details (meeting_id, link_zoom, passcode)
- universitas                   — university directory
- kontak_universitas            — university contact persons
- kontak_auto                   — auto-discovered contacts (synced back from this system)
- schedule_audiensi             — schedule approval tracking
- audiensi_reminder_schedules / audiensi_reminder_queue — reminder system
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
from typing import Any

import aiomysql

from orchestrator.config import log, cfg

# ---------------------------------------------------------------------------
# Connection pool management
# ---------------------------------------------------------------------------

_pool: aiomysql.Pool | None = None


async def init_dms_pool() -> aiomysql.Pool | None:
    """Create and return the DMS MySQL connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    host = cfg.get("DMS_MYSQL_HOST", "")
    if not host:
        log.info("DMS MySQL: not configured (DMS_MYSQL_HOST empty), skipping")
        return None

    try:
        _pool = await aiomysql.create_pool(
            host=host,
            port=cfg.get("DMS_MYSQL_PORT", 3306),
            user=cfg.get("DMS_MYSQL_USER", ""),
            password=cfg.get("DMS_MYSQL_PASSWORD", ""),
            db=cfg.get("DMS_MYSQL_DATABASE", ""),
            charset="utf8mb4",
            autocommit=True,
            minsize=1,
            maxsize=5,
            connect_timeout=10,
            pool_recycle=3600,
        )
        log.info("DMS MySQL: pool created (%s:%s/%s)",
                 host, cfg.get("DMS_MYSQL_PORT", 3306), cfg.get("DMS_MYSQL_DATABASE", ""))
        return _pool
    except Exception as e:
        log.error("DMS MySQL: failed to create pool: %s", e)
        _pool = None
        return None


async def close_dms_pool() -> None:
    """Close the DMS MySQL connection pool."""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        log.info("DMS MySQL: pool closed")


@asynccontextmanager
async def get_dms_cursor():
    """Async context manager providing a DictCursor from the pool."""
    pool = _pool or await init_dms_pool()
    if pool is None:
        raise RuntimeError("DMS MySQL pool not available — check DMS_MYSQL_HOST config")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            yield cursor


def _serialize_row(row: dict) -> dict:
    """Convert date/datetime/timedelta objects to strings for JSON serialization."""
    out = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        elif isinstance(v, timedelta):
            total = int(v.total_seconds())
            h, remainder = divmod(total, 3600)
            m, s = divmod(remainder, 60)
            out[k] = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# READ: Audiensi Schedules
# ---------------------------------------------------------------------------


async def get_upcoming_audiensi_schedules(
    days_ahead: int = 30,
    include_past_days: int = 7,
) -> list[dict]:
    """
    Get upcoming audiensi schedules from two sources:
    - schedule_follow_up (regular audiensi)
    - schedule_follow_up_lsp (LSP audiensi, joined with meeting_audiensi for meeting date/zoom)

    Returns schedules from [today - include_past_days] to [today + days_ahead].
    Joins with universitas for campus name.  Each row has a ``source`` field
    ('schedule_follow_up' or 'schedule_follow_up_lsp') so the caller can distinguish.
    """
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            (
                SELECT
                    sf.id,
                    'schedule_follow_up' AS source,
                    sf.id_univ,
                    u.universitas AS nama_universitas,
                    sf.jadwal_audiensi,
                    sf.jam_audensi,
                    sf.type_meeting,
                    sf.type_meetingdua,
                    sf.link_zoom,
                    sf.action,
                    sf.status_approval,
                    sf.est_audiens,
                    sf.aktual_audiens,
                    sf.notulen,
                    sf.catatan,
                    sf.catatan_marketing,
                    sf.jenis_meetings,
                    sf.alamat,
                    sf.link_lokasi,
                    sf.company_profile_link,
                    sf.proposal_link,
                    sf.surat_penawaran_link,
                    sf.mou_link,
                    sf.pks_link,
                    NULL AS unit_organisasi,
                    NULL AS nomor_surat,
                    NULL AS status_surat,
                    NULL AS nama_penerima,
                    NULL AS no_telp_penerima,
                    NULL AS id_request
                FROM schedule_follow_up sf
                LEFT JOIN universitas u ON sf.id_univ = u.id_univ
                WHERE sf.jadwal_audiensi BETWEEN
                    DATE_SUB(CURDATE(), INTERVAL %s DAY) AND
                    DATE_ADD(CURDATE(), INTERVAL %s DAY)
            )
            UNION ALL
            (
                SELECT
                    s.id,
                    'schedule_follow_up_lsp' AS source,
                    s.id_univ,
                    u.universitas AS nama_universitas,
                    COALESCE(m.tanggal_meeting, s.tanggal_schedule) AS jadwal_audiensi,
                    m.jam_meeting AS jam_audensi,
                    s.type_meeting,
                    s.type_meetingdua,
                    m.link_zoom,
                    s.action,
                    s.meeting_status AS status_approval,
                    s.est_audiens,
                    s.aktual_audiens,
                    s.notulen,
                    NULL AS catatan,
                    s.catatan_marketing,
                    NULL AS jenis_meetings,
                    NULL AS alamat,
                    NULL AS link_lokasi,
                    NULL AS company_profile_link,
                    NULL AS proposal_link,
                    NULL AS surat_penawaran_link,
                    NULL AS mou_link,
                    NULL AS pks_link,
                    NULL AS unit_organisasi,
                    NULL AS nomor_surat,
                    NULL AS status_surat,
                    NULL AS nama_penerima,
                    NULL AS no_telp_penerima,
                    NULL AS id_request
                FROM schedule_follow_up_lsp s
                LEFT JOIN meeting_audiensi m ON s.id_meeting = m.id
                LEFT JOIN universitas_lsp u ON s.id_univ = u.id_univ
                WHERE s.tanggal_schedule BETWEEN
                    DATE_SUB(CURDATE(), INTERVAL %s DAY) AND
                    DATE_ADD(CURDATE(), INTERVAL %s DAY)
            )
            ORDER BY jadwal_audiensi ASC, jam_audensi ASC
        """, (include_past_days, days_ahead, include_past_days, days_ahead))
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


async def get_audiensi_schedule_by_id(
    schedule_id: int,
    source: str = "schedule_follow_up",
) -> dict | None:
    """Get a single audiensi schedule with full details.

    ``source`` can be ``'schedule_follow_up'`` or ``'schedule_follow_up_lsp'``.
    """
    if source == "schedule_follow_up_lsp":
        return await _get_lsp_schedule_by_id(schedule_id)

    # Original schedule_follow_up path
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            SELECT
                sf.*,
                'schedule_follow_up' AS source,
                u.universitas AS nama_universitas,
                u.email_kampus,
                u.alamat AS alamat_universitas
            FROM schedule_follow_up sf
            LEFT JOIN universitas u ON sf.id_univ = u.id_univ
            WHERE sf.id = %s
        """, (schedule_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        result = _serialize_row(row)

        # Also fetch PICs for this schedule
        await cursor.execute("""
            SELECT spa.nama_pic, spa.jabatan_pic, spa.no_pic
            FROM schedule_pic_audiensi spa
            INNER JOIN schedule_audiensi sa ON spa.schedule_id = sa.id
            WHERE sa.id_followup = %s
        """, (schedule_id,))
        pics = await cursor.fetchall()
        result["pics"] = [_serialize_row(p) for p in pics]

        return result


async def _get_lsp_schedule_by_id(schedule_id: int) -> dict | None:
    """Get a single LSP schedule with meeting_audiensi details."""
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            SELECT
                s.id,
                'schedule_follow_up_lsp' AS source,
                s.id_univ,
                u.universitas AS nama_universitas,
                u.email_kampus,
                u.alamat AS alamat_universitas,
                s.tanggal_schedule,
                s.id_meeting,
                s.id_lembaga,
                s.type_meeting,
                s.type_meetingdua,
                s.meeting_status,
                s.meeting_status_updated_at,
                s.meeting_start_time,
                s.meeting_end_time,
                s.est_audiens,
                s.aktual_audiens,
                s.action,
                s.notulen,
                s.catatan_marketing,
                s.est_mou,
                s.akt_mou,
                s.namapimpinan,
                s.jabatanpic,
                s.skema,
                s.expired_mou,
                s.expired_moa,
                s.status_audiensi,
                s.is_follow_up,
                COALESCE(m.tanggal_meeting, s.tanggal_schedule) AS jadwal_audiensi,
                m.jam_meeting AS jam_audensi,
                m.link_zoom,
                m.passcode,
                m.start_url,
                m.akun_zoom,
                m.host_key,
                m.topic AS meeting_topic,
                m.lembaga AS meeting_lembaga,
                m.lokasi,
                m.meeting_id AS zoom_meeting_id,
                m.tanggal_meeting,
                s.meeting_status AS status_approval
            FROM schedule_follow_up_lsp s
            LEFT JOIN meeting_audiensi m ON s.id_meeting = m.id
            LEFT JOIN universitas_lsp u ON s.id_univ = u.id_univ
            WHERE s.id = %s
        """, (schedule_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        result = _serialize_row(row)
        result["pics"] = []  # LSP uses different PIC structure
        return result


# ---------------------------------------------------------------------------
# READ: Auth / Karyawan login source
# ---------------------------------------------------------------------------


async def get_active_karyawan_by_email(email: str) -> dict[str, Any] | None:
    """Return an active karyawan record eligible for dashboard login."""
    normalized = (email or "").strip().lower()
    if not normalized:
        return None

    async with get_dms_cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                id_karywan AS dms_user_id,
                user_name,
                user_email,
                user_password,
                user_level,
                statuskerja,
                last_login
            FROM karyawan
            WHERE LOWER(TRIM(user_email)) = %s
              AND statuskerja = 1
            LIMIT 1
            """,
            (normalized,),
        )
        row = await cursor.fetchone()
        return _serialize_row(row) if row else None


async def get_today_audiensi_schedules() -> list[dict]:
    """Get audiensi schedules for today from both sources."""
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            (
                SELECT
                    sf.id, 'schedule_follow_up' AS source,
                    sf.id_univ,
                    u.universitas AS nama_universitas,
                    sf.jadwal_audiensi, sf.jam_audensi,
                    sf.type_meeting, sf.link_zoom,
                    sf.status_approval,
                    NULL AS unit_organisasi,
                    NULL AS status_surat,
                    NULL AS nomor_surat
                FROM schedule_follow_up sf
                LEFT JOIN universitas u ON sf.id_univ = u.id_univ
                WHERE sf.jadwal_audiensi = CURDATE()
            )
            UNION ALL
            (
                SELECT
                    s.id, 'schedule_follow_up_lsp' AS source,
                    s.id_univ,
                    u.universitas AS nama_universitas,
                    COALESCE(m.tanggal_meeting, s.tanggal_schedule) AS jadwal_audiensi,
                    m.jam_meeting AS jam_audensi,
                    s.type_meeting, m.link_zoom,
                    s.meeting_status AS status_approval,
                    NULL AS unit_organisasi,
                    NULL AS status_surat,
                    NULL AS nomor_surat
                FROM schedule_follow_up_lsp s
                LEFT JOIN meeting_audiensi m ON s.id_meeting = m.id
                LEFT JOIN universitas_lsp u ON s.id_univ = u.id_univ
                WHERE (s.tanggal_schedule = CURDATE() OR m.tanggal_meeting = CURDATE())
            )
            ORDER BY jam_audensi ASC
        """)
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


# ---------------------------------------------------------------------------
# READ: Follow-up History
# ---------------------------------------------------------------------------


async def get_follow_up_history(
    id_univ: int,
    limit: int = 20,
) -> list[dict]:
    """Get follow-up history for a specific university."""
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            SELECT
                f.id, f.id_univ,
                f.metode_followup, f.hasil_followup,
                f.catatan, f.tanggal_follow_up, f.next_follow_up_date,
                a.user_name AS user_name
            FROM follow_up_tbls f
            LEFT JOIN asesor a ON f.user_id = a.id
            WHERE f.id_univ = %s
            ORDER BY f.tanggal_follow_up DESC
            LIMIT %s
        """, (id_univ, limit))
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


async def get_recent_follow_ups(limit: int = 50) -> list[dict]:
    """Get most recent follow-up activities across all universities."""
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            SELECT
                f.id, f.id_univ,
                u.universitas AS nama_universitas,
                f.metode_followup, f.hasil_followup,
                f.catatan, f.tanggal_follow_up, f.next_follow_up_date
            FROM follow_up_tbls f
            LEFT JOIN universitas u ON f.id_univ = u.id_univ
            ORDER BY f.tanggal_follow_up DESC
            LIMIT %s
        """, (limit,))
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


# ---------------------------------------------------------------------------
# READ: Meeting Details (Zoom)
# ---------------------------------------------------------------------------


async def get_meeting_by_schedule(schedule_id: int) -> dict | None:
    """
    Get Zoom meeting details for a given schedule.
    Links meeting_audiensi to schedule_follow_up through lembaga/topic matching.
    """
    # First get the schedule to find the university
    schedule = await get_audiensi_schedule_by_id(schedule_id)
    if not schedule:
        return None

    uni_name = schedule.get("nama_universitas", "")
    jadwal = schedule.get("jadwal_audiensi", "")

    if not uni_name or not jadwal:
        return None

    async with get_dms_cursor() as cursor:
        # Try to find matching meeting by date
        await cursor.execute("""
            SELECT
                m.id, m.meeting_id, m.tanggal_meeting, m.jam_meeting,
                m.topic, m.lembaga, m.link_zoom, m.passcode,
                m.start_url, m.akun_zoom, m.host_key, m.lokasi
            FROM meeting_audiensi m
            WHERE m.tanggal_meeting = %s
            ORDER BY m.jam_meeting ASC
        """, (jadwal,))
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


async def get_upcoming_meetings(days_ahead: int = 14) -> list[dict]:
    """Get upcoming Zoom meetings."""
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            SELECT
                m.id, m.meeting_id, m.tanggal_meeting, m.jam_meeting,
                m.topic, m.lembaga, m.link_zoom, m.passcode,
                m.akun_zoom, m.lokasi
            FROM meeting_audiensi m
            WHERE m.tanggal_meeting BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL %s DAY)
            ORDER BY m.tanggal_meeting ASC, m.jam_meeting ASC
        """, (days_ahead,))
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


# ---------------------------------------------------------------------------
# READ: University Data
# ---------------------------------------------------------------------------


async def get_dms_university(id_univ: int) -> dict | None:
    """Get a university from the DMS database by ID."""
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            SELECT
                u.id_univ, u.universitas, u.email_kampus,
                u.no_teleponkampus, u.alamat,
                u.pic, u.jabatan, u.no_hppickampus,
                u.pic2, u.jabatan2, u.no_hppickampus2,
                u.pic3, u.jabatan3, u.no_hppickampus3
            FROM universitas u
            WHERE u.id_univ = %s
        """, (id_univ,))
        row = await cursor.fetchone()
        return _serialize_row(row) if row else None


async def search_dms_universities(
    keyword: str,
    limit: int = 20,
) -> list[dict]:
    """Search universities in DMS by keyword."""
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            SELECT u.id_univ, u.universitas, u.alamat, u.email_kampus
            FROM universitas u
            WHERE u.universitas LIKE %s
            ORDER BY u.universitas
            LIMIT %s
        """, (f"%{keyword}%", limit))
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


async def get_dms_university_contacts(id_univ: int) -> list[dict]:
    """Get all contacts for a university from kontak_universitas."""
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            SELECT
                ku.id, ku.id_univ, ku.pic, ku.no_hppickampus,
                ku.jabatan, ku.status, ku.catatan, ku.created_at
            FROM kontak_universitas ku
            WHERE ku.id_univ = %s
            ORDER BY ku.id DESC
        """, (id_univ,))
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


async def search_dms_pics(
    keyword: str = "",
    limit: int = 50,
) -> list[dict]:
    """
    Search PIC data across all DMS sources:
    - universitas table (pic, pic2, pic3 fields)
    - kontak_universitas table
    - schedule_pic_audiensi (linked via schedule_audiensi → schedule_follow_up)

    Returns deduplicated list of PICs with university info.
    """
    async with get_dms_cursor() as cursor:
        like_param = f"%{keyword}%" if keyword else "%"

        # Source 1: universitas table — pic, pic2, pic3
        await cursor.execute("""
            SELECT
                u.id_univ,
                u.universitas AS nama_universitas,
                u.pic AS nama_pic,
                u.jabatan AS jabatan_pic,
                u.no_hppickampus AS no_pic,
                'universitas' AS pic_source
            FROM universitas u
            WHERE u.pic IS NOT NULL AND u.pic != ''
              AND (u.pic LIKE %s OR u.universitas LIKE %s)
            UNION ALL
            SELECT
                u.id_univ,
                u.universitas AS nama_universitas,
                u.pic2 AS nama_pic,
                u.jabatan2 AS jabatan_pic,
                u.no_hppickampus2 AS no_pic,
                'universitas' AS pic_source
            FROM universitas u
            WHERE u.pic2 IS NOT NULL AND u.pic2 != ''
              AND (u.pic2 LIKE %s OR u.universitas LIKE %s)
            UNION ALL
            SELECT
                u.id_univ,
                u.universitas AS nama_universitas,
                u.pic3 AS nama_pic,
                u.jabatan3 AS jabatan_pic,
                u.no_hppickampus3 AS no_pic,
                'universitas' AS pic_source
            FROM universitas u
            WHERE u.pic3 IS NOT NULL AND u.pic3 != ''
              AND (u.pic3 LIKE %s OR u.universitas LIKE %s)
            LIMIT %s
        """, (like_param, like_param, like_param, like_param, like_param, like_param, limit * 3))
        uni_rows = await cursor.fetchall()

        # Source 2: kontak_universitas
        await cursor.execute("""
            SELECT
                ku.id_univ,
                u.universitas AS nama_universitas,
                ku.pic AS nama_pic,
                ku.jabatan AS jabatan_pic,
                ku.no_hppickampus AS no_pic,
                'kontak_universitas' AS pic_source
            FROM kontak_universitas ku
            LEFT JOIN universitas u ON ku.id_univ = u.id_univ
            WHERE ku.pic IS NOT NULL AND ku.pic != ''
              AND (ku.pic LIKE %s OR u.universitas LIKE %s)
            LIMIT %s
        """, (like_param, like_param, limit * 2))
        kontak_rows = await cursor.fetchall()

        # Source 3: schedule_pic_audiensi
        await cursor.execute("""
            SELECT
                sf.id_univ,
                u.universitas AS nama_universitas,
                spa.nama_pic,
                spa.jabatan_pic,
                spa.no_pic,
                'schedule_pic' AS pic_source
            FROM schedule_pic_audiensi spa
            INNER JOIN schedule_audiensi sa ON spa.schedule_id = sa.id
            INNER JOIN schedule_follow_up sf ON sa.id_followup = sf.id
            LEFT JOIN universitas u ON sf.id_univ = u.id_univ
            WHERE spa.nama_pic IS NOT NULL AND spa.nama_pic != ''
              AND (spa.nama_pic LIKE %s OR u.universitas LIKE %s)
            LIMIT %s
        """, (like_param, like_param, limit * 2))
        sched_rows = await cursor.fetchall()

        # Combine and deduplicate
        all_rows = [_serialize_row(r) for r in list(uni_rows) + list(kontak_rows) + list(sched_rows)]

        # Expand JSON array entries (some DMS fields store ["name1","name2",...])
        import json
        expanded = []
        for row in all_rows:
            nama = (row.get("nama_pic") or "").strip()
            if nama.startswith("["):
                try:
                    names = json.loads(nama)
                    jabatans = json.loads(row.get("jabatan_pic") or "[]") if (row.get("jabatan_pic") or "").startswith("[") else []
                    phones = json.loads(row.get("no_pic") or "[]") if (row.get("no_pic") or "").startswith("[") else []
                    for idx, n in enumerate(names):
                        if n and n.strip():
                            expanded.append({
                                **row,
                                "nama_pic": n.strip(),
                                "jabatan_pic": jabatans[idx].strip() if idx < len(jabatans) and jabatans[idx] else None,
                                "no_pic": phones[idx].strip() if idx < len(phones) and phones[idx] else None,
                            })
                except (json.JSONDecodeError, IndexError):
                    expanded.append(row)
            else:
                expanded.append(row)

        seen = set()
        deduped = []
        for row in expanded:
            name = (row.get("nama_pic") or "").strip().lower()
            uni = (row.get("nama_universitas") or "").strip().lower()
            key = f"{name}|{uni}"
            if key not in seen and name:
                seen.add(key)
                deduped.append(row)

        return deduped[:limit]


# ---------------------------------------------------------------------------
# READ: Schedule Audiensi (approval tracking)
# ---------------------------------------------------------------------------


async def get_schedule_audiensi_approvals(
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get schedule audiensi approval entries."""
    async with get_dms_cursor() as cursor:
        sql = """
            SELECT
                sa.id, sa.pic, sa.id_divisi,
                sa.status_approval, sa.task,
                sa.id_followup,
                sf.jadwal_audiensi, sf.jam_audensi,
                u.universitas AS nama_universitas
            FROM schedule_audiensi sa
            LEFT JOIN schedule_follow_up sf ON sa.id_followup = sf.id
            LEFT JOIN universitas u ON sf.id_univ = u.id_univ
        """
        params = []
        if status:
            sql += " WHERE sa.status_approval = %s"
            params.append(status)
        sql += " ORDER BY sa.id DESC LIMIT %s"
        params.append(limit)

        await cursor.execute(sql, params)
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


# ---------------------------------------------------------------------------
# READ: Dashboard Stats
# ---------------------------------------------------------------------------


async def get_dms_audiensi_stats() -> dict:
    """Get aggregate stats from the DMS database (schedule_follow_up + schedule_follow_up_lsp)."""
    async with get_dms_cursor() as cursor:
        # Total schedules
        await cursor.execute("SELECT COUNT(*) AS total FROM schedule_follow_up")
        total_sf = (await cursor.fetchone())["total"]

        await cursor.execute("SELECT COUNT(*) AS total FROM schedule_follow_up_lsp")
        total_lsp = (await cursor.fetchone())["total"]

        total_schedules = total_sf + total_lsp

        # Upcoming schedules
        await cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM schedule_follow_up
            WHERE jadwal_audiensi >= CURDATE()
        """)
        upcoming_sf = (await cursor.fetchone())["cnt"]

        await cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM schedule_follow_up_lsp s
            LEFT JOIN meeting_audiensi m ON s.id_meeting = m.id
            WHERE s.tanggal_schedule >= CURDATE()
        """)
        upcoming_lsp = (await cursor.fetchone())["cnt"]

        upcoming = upcoming_sf + upcoming_lsp

        # Today's schedules
        await cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM schedule_follow_up
            WHERE jadwal_audiensi = CURDATE()
        """)
        today_sf = (await cursor.fetchone())["cnt"]

        await cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM schedule_follow_up_lsp s
            LEFT JOIN meeting_audiensi m ON s.id_meeting = m.id
            WHERE (s.tanggal_schedule = CURDATE() OR m.tanggal_meeting = CURDATE())
        """)
        today_lsp = (await cursor.fetchone())["cnt"]

        today = today_sf + today_lsp

        # Total follow-ups
        await cursor.execute("SELECT COUNT(*) AS total FROM follow_up_tbls")
        total_followups = (await cursor.fetchone())["total"]

        # Recent follow-ups (last 7 days)
        await cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM follow_up_tbls
            WHERE tanggal_follow_up >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """)
        recent_followups = (await cursor.fetchone())["cnt"]

        # Total universities
        await cursor.execute("SELECT COUNT(*) AS total FROM universitas")
        total_universities = (await cursor.fetchone())["total"]

        # Total contacts
        await cursor.execute("SELECT COUNT(*) AS total FROM kontak_universitas")
        total_contacts = (await cursor.fetchone())["total"]

        # Total auto contacts
        await cursor.execute("SELECT COUNT(*) AS total FROM kontak_auto")
        total_auto_contacts = (await cursor.fetchone())["total"]

        # Approval stats
        await cursor.execute("""
            SELECT status_approval, COUNT(*) AS cnt
            FROM schedule_audiensi
            GROUP BY status_approval
        """)
        approval_stats = {}
        for row in await cursor.fetchall():
            approval_stats[row["status_approval"] or "unknown"] = row["cnt"]

        # LSP meeting status stats
        await cursor.execute("""
            SELECT meeting_status, COUNT(*) AS cnt
            FROM schedule_follow_up_lsp
            GROUP BY meeting_status
        """)
        lsp_stats = {}
        for row in await cursor.fetchall():
            lsp_stats[row["meeting_status"] or "unknown"] = row["cnt"]

        return {
            "total_schedules": total_schedules,
            "upcoming_schedules": upcoming,
            "today_schedules": today,
            "total_followups": total_followups,
            "recent_followups_7d": recent_followups,
            "total_universities": total_universities,
            "total_contacts": total_contacts,
            "total_auto_contacts": total_auto_contacts,
            "approval_stats": approval_stats,
            "lsp_stats": lsp_stats,
            "source_counts": {
                "schedule_follow_up": total_sf,
                "schedule_follow_up_lsp": total_lsp,
            },
        }


# ---------------------------------------------------------------------------
# WRITE: Sync contacts back to DMS
# ---------------------------------------------------------------------------


async def sync_contact_to_dms(
    id_univ: int,
    universitas: str,
    pic: str,
    jabatan: str,
    no_hp: str,
    no_hp_e164: str = "",
    instagram_username: str = "",
    source_type: str = "getcontact_ai",
    source_origin: str = "GetContact AI Agent",
    context_snippet: str = "",
) -> int | None:
    """
    Sync a discovered contact back to the DMS kontak_auto table.

    Returns the inserted row ID, or None if it already exists.
    """
    async with get_dms_cursor() as cursor:
        # Check if contact already exists for this university + phone
        await cursor.execute("""
            SELECT id FROM kontak_auto
            WHERE id_univ = %s AND no_hp = %s
        """, (id_univ, no_hp))
        existing = await cursor.fetchone()
        if existing:
            return None  # Already exists

        await cursor.execute("""
            INSERT INTO kontak_auto
                (id_univ, universitas, instagram_username, pic, jabatan,
                 no_hp, no_hp_e164, source_type, source_origin,
                 context_snippet, is_default, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NOW(), NOW())
        """, (
            id_univ, universitas, instagram_username, pic, jabatan,
            no_hp, no_hp_e164, source_type, source_origin, context_snippet,
        ))
        return cursor.lastrowid


async def bulk_sync_contacts_to_dms(contacts: list[dict]) -> dict:
    """
    Sync multiple contacts to DMS kontak_auto.

    Each contact dict should contain:
        id_univ, universitas, pic, jabatan, no_hp, no_hp_e164 (optional),
        instagram_username (optional), source_type (optional)

    Returns: {synced: int, skipped: int, errors: int}
    """
    synced = skipped = errors = 0
    for c in contacts:
        try:
            result = await sync_contact_to_dms(
                id_univ=c["id_univ"],
                universitas=c.get("universitas", ""),
                pic=c.get("pic", "Unknown"),
                jabatan=c.get("jabatan", "Unknown"),
                no_hp=c["no_hp"],
                no_hp_e164=c.get("no_hp_e164", ""),
                instagram_username=c.get("instagram_username", ""),
                source_type=c.get("source_type", "getcontact_ai"),
                source_origin=c.get("source_origin", "GetContact AI Agent"),
                context_snippet=c.get("context_snippet", ""),
            )
            if result:
                synced += 1
            else:
                skipped += 1
        except Exception as e:
            log.error("bulk_sync_contacts_to_dms: failed for %s: %s", c.get("no_hp"), e)
            errors += 1

    log.info("bulk_sync_contacts_to_dms: synced=%d, skipped=%d, errors=%d",
             synced, skipped, errors)
    return {"synced": synced, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# WRITE: Create follow-up record in DMS
# ---------------------------------------------------------------------------


async def create_follow_up_record(
    id_univ: int,
    metode_followup: str = "6",  # 6 = WhatsApp
    hasil_followup: str = "1",   # 1 = Sedang Difollow-up
    catatan: str = "",
    user_id: int = 0,
    next_follow_up_date: str | None = None,
) -> int:
    """
    Create a follow-up log entry in DMS follow_up_tbls.

    metode_followup values: 1=Telepon, 2=Email, 3=Visit, 4=Online, 5=Zoom Meeting, 6=WhatsApp
    hasil_followup values: 1=Sedang Difollow-up, 2=Tidak Berminat, 3=Akan Dihubungi, 4=Audiensi
    """
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            INSERT INTO follow_up_tbls
                (id_univ, metode_followup, hasil_followup, catatan,
                 tanggal_follow_up, user_id, next_follow_up_date)
            VALUES (%s, %s, %s, %s, NOW(), %s, %s)
        """, (id_univ, metode_followup, hasil_followup, catatan,
              user_id, next_follow_up_date))
        return cursor.lastrowid


# ---------------------------------------------------------------------------
# Scheduler helper: check for schedules needing reminders
# ---------------------------------------------------------------------------


async def get_schedules_needing_reminder(
    hours_before: int = 24,
) -> list[dict]:
    """
    Find audiensi schedules happening in the next N hours
    that haven't had a reminder sent yet (no recent follow-up via WA method).
    Checks schedule_follow_up, request_surat_audiensi_detail, and schedule_follow_up_lsp.

    Used by the scheduler to automatically send WhatsApp reminders.
    """
    async with get_dms_cursor() as cursor:
        await cursor.execute("""
            (
                SELECT
                    sf.id, 'schedule_follow_up' AS source,
                    sf.id_univ,
                    u.universitas AS nama_universitas,
                    sf.jadwal_audiensi, sf.jam_audensi,
                    sf.link_zoom, sf.type_meeting,
                    u.pic, u.no_hppickampus,
                    u.pic2, u.no_hppickampus2,
                    u.pic3, u.no_hppickampus3,
                    NULL AS unit_organisasi,
                    NULL AS nama_penerima,
                    NULL AS no_telp_penerima
                FROM schedule_follow_up sf
                LEFT JOIN universitas u ON sf.id_univ = u.id_univ
                WHERE sf.jadwal_audiensi BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL %s HOUR)
                  AND sf.id NOT IN (
                      SELECT DISTINCT f.id_univ
                      FROM follow_up_tbls f
                      WHERE f.metode_followup = '6'
                        AND f.tanggal_follow_up >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                        AND f.id_univ = sf.id_univ
                  )
            )
            UNION ALL
            (
                SELECT
                    s.id, 'schedule_follow_up_lsp' AS source,
                    s.id_univ,
                    u.universitas AS nama_universitas,
                    COALESCE(m.tanggal_meeting, s.tanggal_schedule) AS jadwal_audiensi,
                    m.jam_meeting AS jam_audensi,
                    m.link_zoom, s.type_meeting,
                    u.pic, u.no_hppickampus,
                    u.pic2, u.no_hppickampus2,
                    u.pic3, u.no_hppickampus3,
                    NULL AS unit_organisasi,
                    NULL AS nama_penerima,
                    NULL AS no_telp_penerima
                FROM schedule_follow_up_lsp s
                LEFT JOIN meeting_audiensi m ON s.id_meeting = m.id
                LEFT JOIN universitas_lsp u ON s.id_univ = u.id_univ
                WHERE COALESCE(m.tanggal_meeting, s.tanggal_schedule) BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL %s HOUR)
                  AND s.id_univ NOT IN (
                      SELECT DISTINCT f.id_univ
                      FROM follow_up_tbls_lsp f
                      WHERE f.metode_followup = '6'
                        AND f.tanggal_follow_up >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                        AND f.id_univ = s.id_univ
                  )
            )
            ORDER BY jadwal_audiensi ASC, jam_audensi ASC
        """, (hours_before, hours_before))
        rows = await cursor.fetchall()
        return [_serialize_row(r) for r in rows]


# ---------------------------------------------------------------------------
# University ID mapping (GetContact SQLite ↔ DMS MySQL)
# ---------------------------------------------------------------------------


async def find_dms_university_by_name(name: str) -> dict | None:
    """
    Try to find a matching university in DMS by fuzzy name match.
    Used to map GetContact's local university records to DMS IDs.
    """
    async with get_dms_cursor() as cursor:
        # Try exact match first
        await cursor.execute("""
            SELECT id_univ, universitas, alamat
            FROM universitas
            WHERE universitas = %s
            LIMIT 1
        """, (name,))
        row = await cursor.fetchone()
        if row:
            return _serialize_row(row)

        # Try LIKE match
        await cursor.execute("""
            SELECT id_univ, universitas, alamat
            FROM universitas
            WHERE universitas LIKE %s
            ORDER BY universitas
            LIMIT 5
        """, (f"%{name}%",))
        rows = await cursor.fetchall()
        if rows:
            return _serialize_row(rows[0])

        return None


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def check_dms_connection() -> dict:
    """Check if connection to DMS MySQL is healthy."""
    try:
        async with get_dms_cursor() as cursor:
            await cursor.execute("SELECT 1 AS ok")
            row = await cursor.fetchone()
            return {
                "status": "connected",
                "host": cfg.get("DMS_MYSQL_HOST", ""),
                "database": cfg.get("DMS_MYSQL_DATABASE", ""),
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "host": cfg.get("DMS_MYSQL_HOST", ""),
            "database": cfg.get("DMS_MYSQL_DATABASE", ""),
        }


async def get_active_karyawan_by_email(email: str) -> dict[str, Any] | None:
    """Return an active karyawan record eligible for dashboard login."""
    normalized = (email or "").strip().lower()
    if not normalized:
        return None

    async with get_dms_cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                id_karywan AS dms_user_id,
                user_name,
                user_email,
                user_password,
                user_level,
                statuskerja,
                last_login
            FROM karyawan
            WHERE LOWER(TRIM(user_email)) = %s
              AND statuskerja = 1
            LIMIT 1
            """,
            (normalized,),
        )
        row = await cursor.fetchone()
        return _serialize_row(row) if row else None
