"""
Blast Campaign Service

Handles creating campaigns, adding recipients from university contacts,
rendering template messages with placeholders, and executing blast sends.
"""

import asyncio
import hashlib
import json
import random
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from orchestrator.config import log, SYSTEM_DEVICE_ID
from orchestrator.db import get_db
from orchestrator.message_queue import message_queue
from orchestrator.websocket import manager as ws_manager

DEFAULT_BLAST_TIMEZONE = "Asia/Jakarta"
PEAK_HOUR_SPEED_BOOST = 1.15
MIN_BLAST_DELAY_MS = 1000
ZERO_WIDTH_VARIANTS = ("\u200b", "\u200c", "\u200d", "\ufeff")


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stable_seed(*parts: Any) -> int:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _get_campaign_timezone(campaign: dict) -> timezone | ZoneInfo:
    timezone_name = (campaign.get("schedule_timezone") or DEFAULT_BLAST_TIMEZONE).strip()
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        log.warning("[Blast] Unknown timezone '%s', falling back to %s", timezone_name, DEFAULT_BLAST_TIMEZONE)
        return timezone(timedelta(hours=7))


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _normalize_campaign(campaign: Optional[dict]) -> Optional[dict]:
    if not campaign:
        return campaign

    normalized = dict(campaign)
    normalized["content_variation_enabled"] = _as_bool(
        normalized.get("content_variation_enabled"), True
    )
    normalized["schedule_enabled"] = _as_bool(normalized.get("schedule_enabled"), True)
    normalized["schedule_timezone"] = normalized.get("schedule_timezone") or DEFAULT_BLAST_TIMEZONE
    normalized["active_hours_start"] = max(0, min(23, _as_int(normalized.get("active_hours_start"), 8)))
    normalized["active_hours_end"] = max(1, min(24, _as_int(normalized.get("active_hours_end"), 21)))
    normalized["peak_hours_start"] = max(0, min(23, _as_int(normalized.get("peak_hours_start"), 10)))
    normalized["peak_hours_end"] = max(0, min(24, _as_int(normalized.get("peak_hours_end"), 14)))
    normalized["lunch_break_start"] = max(0, min(23, _as_int(normalized.get("lunch_break_start"), 12)))
    normalized["lunch_break_end"] = max(0, min(24, _as_int(normalized.get("lunch_break_end"), 13)))
    normalized["weekend_factor"] = max(0.0, _as_float(normalized.get("weekend_factor"), 0.5))
    normalized["auto_resume_enabled"] = _as_bool(normalized.get("auto_resume_enabled"), True)
    normalized["paused_reason"] = normalized.get("paused_reason")
    # Parse device_ids from JSON string → list (SQLite stores as TEXT)
    raw_ids = normalized.get("device_ids")
    if isinstance(raw_ids, str):
        try:
            parsed = json.loads(raw_ids)
            normalized["device_ids"] = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            normalized["device_ids"] = []
    elif not isinstance(raw_ids, list):
        normalized["device_ids"] = []
    return normalized


def _campaign_allows_schedule(campaign: dict, now_utc: datetime) -> tuple[bool, int, str | None]:
    if not campaign.get("schedule_enabled", True):
        return True, 0, None

    tz = _get_campaign_timezone(campaign)
    local_now = now_utc.astimezone(tz)
    start_hour = campaign["active_hours_start"]
    end_hour = max(start_hour + 1, campaign["active_hours_end"])
    lunch_start = campaign["lunch_break_start"]
    lunch_end = max(lunch_start, campaign["lunch_break_end"])
    weekend_factor = campaign["weekend_factor"]

    if local_now.weekday() >= 5 and weekend_factor <= 0:
        days_until_monday = (7 - local_now.weekday()) or 7
        next_start = datetime.combine(
            (local_now + timedelta(days=days_until_monday)).date(),
            time(hour=start_hour, minute=0),
            tzinfo=tz,
        )
        return False, max(0, int((next_start.astimezone(timezone.utc) - now_utc).total_seconds() * 1000)), "Weekend quiet hours"

    start_today = datetime.combine(local_now.date(), time(hour=start_hour, minute=0), tzinfo=tz)
    end_today = datetime.combine(local_now.date(), time(hour=end_hour % 24, minute=0), tzinfo=tz)
    if end_hour >= 24:
        end_today = end_today + timedelta(days=1)

    if local_now < start_today:
        wait_ms = int((start_today.astimezone(timezone.utc) - now_utc).total_seconds() * 1000)
        return False, max(0, wait_ms), "Outside active sending hours"

    if local_now >= end_today:
        next_day = local_now.date() + timedelta(days=1)
        next_start = datetime.combine(next_day, time(hour=start_hour, minute=0), tzinfo=tz)
        wait_ms = int((next_start.astimezone(timezone.utc) - now_utc).total_seconds() * 1000)
        return False, max(0, wait_ms), "Outside active sending hours"

    if lunch_end > lunch_start:
        lunch_start_at = datetime.combine(local_now.date(), time(hour=lunch_start, minute=0), tzinfo=tz)
        lunch_end_at = datetime.combine(local_now.date(), time(hour=lunch_end % 24, minute=0), tzinfo=tz)
        if lunch_end >= 24:
            lunch_end_at = lunch_end_at + timedelta(days=1)
        if lunch_start_at <= local_now < lunch_end_at:
            wait_ms = int((lunch_end_at.astimezone(timezone.utc) - now_utc).total_seconds() * 1000)
            return False, max(0, wait_ms), "Lunch-break slowdown window"

    return True, 0, None


def _compute_inter_message_delay_ms(campaign: dict, now_utc: datetime) -> int:
    base_delay = max(MIN_BLAST_DELAY_MS, _as_int(campaign.get("delay_between_ms"), 5000))
    human_min = max(0, _as_int(campaign.get("human_delay_min_ms"), 2000))
    human_max = max(human_min, _as_int(campaign.get("human_delay_max_ms"), 8000))
    effective_delay = base_delay + random.randint(human_min, human_max)

    if campaign.get("schedule_enabled", True):
        tz = _get_campaign_timezone(campaign)
        local_now = now_utc.astimezone(tz)
        speed_factor = 1.0
        if local_now.weekday() >= 5:
            weekend_factor = max(0.1, campaign["weekend_factor"])
            speed_factor *= weekend_factor
        peak_start = campaign["peak_hours_start"]
        peak_end = max(peak_start, campaign["peak_hours_end"])
        if peak_end > peak_start and peak_start <= local_now.hour < peak_end:
            speed_factor *= PEAK_HOUR_SPEED_BOOST
        if speed_factor > 0:
            effective_delay = int(effective_delay / speed_factor)

    return max(MIN_BLAST_DELAY_MS, effective_delay)


def _apply_content_variation(message: str, campaign_id: int, recipient: dict) -> str:
    if not message.strip():
        return message

    seed = _stable_seed(campaign_id, recipient.get("id"), recipient.get("phone_number"), message)
    rng = random.Random(seed)
    positions = [index for index, char in enumerate(message) if char in ".!?\n"]
    insert_at = positions[rng.randrange(len(positions))] if positions else len(message)
    if insert_at < len(message):
        insert_at += 1
    zero_width = ZERO_WIDTH_VARIANTS[rng.randrange(len(ZERO_WIDTH_VARIANTS))]
    return f"{message[:insert_at]}{zero_width}{message[insert_at:]}"


def render_campaign_message(campaign: dict, recipient: dict) -> str:
    base_message = render_template(campaign["template_message"], recipient)
    if not campaign.get("content_variation_enabled", True):
        return base_message
    return _apply_content_variation(base_message, campaign["id"], recipient)


def _format_antiban_pause_reason(result: Any) -> str:
    reason = result.error or "Blocked by anti-ban policy"
    anti_ban = result.anti_ban or {}
    health = anti_ban.get("health") or {}
    risk = health.get("risk")
    reasons = health.get("reasons") or []
    recommendation = health.get("recommendation")

    detail = reasons[0] if reasons else recommendation
    if not risk and not detail:
        return reason

    fragments = []
    if risk:
        fragments.append(f"risk={risk}")
    if detail:
        fragments.append(str(detail))

    if not fragments:
        return reason
    return f"{reason} [{' | '.join(fragments)}]"


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------


async def create_campaign(name: str, template_message: str = "", device_id: str = "device_1",
                          delay_between_ms: int = 5000,
                          human_delay_min_ms: int = 2000,
                          human_delay_max_ms: int = 8000,
                          content_variation_enabled: bool = True,
                          schedule_enabled: bool = True,
                          schedule_timezone: str = DEFAULT_BLAST_TIMEZONE,
                          active_hours_start: int = 8,
                          active_hours_end: int = 21,
                          peak_hours_start: int = 10,
                          peak_hours_end: int = 14,
                          lunch_break_start: int = 12,
                          lunch_break_end: int = 13,
                          weekend_factor: float = 0.5,
                          auto_resume_enabled: bool = True,
                          created_by_dms_user_id: Optional[int] = None,
                          created_by_email: Optional[str] = None,
                          created_by_name: Optional[str] = None) -> dict:
    """Create a new blast campaign."""
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO blast_campaigns
               (name, template_message, device_id, delay_between_ms, human_delay_min_ms, human_delay_max_ms,
                content_variation_enabled, schedule_enabled, schedule_timezone, active_hours_start, active_hours_end,
                peak_hours_start, peak_hours_end, lunch_break_start, lunch_break_end, weekend_factor,
                auto_resume_enabled, created_by_dms_user_id, created_by_email, created_by_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                template_message,
                device_id,
                delay_between_ms,
                human_delay_min_ms,
                human_delay_max_ms,
                int(content_variation_enabled),
                int(schedule_enabled),
                schedule_timezone,
                active_hours_start,
                active_hours_end,
                peak_hours_start,
                peak_hours_end,
                lunch_break_start,
                lunch_break_end,
                weekend_factor,
                int(auto_resume_enabled),
                created_by_dms_user_id,
                created_by_email,
                created_by_name,
            ),
        )
        await db.commit()
        campaign_id = cursor.lastrowid
        return await get_campaign(campaign_id)


async def get_campaign(campaign_id: int) -> Optional[dict]:
    """Get a single campaign by ID."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM blast_campaigns WHERE id = ?",
            (campaign_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return _normalize_campaign(dict(row))


async def list_campaigns(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List campaigns with optional status filter."""
    conditions = []
    params: list[object] = []

    if status:
        conditions.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_db() as db:
        count_cursor = await db.execute(
            f"SELECT COUNT(*) FROM blast_campaigns {where}", params
        )
        total = (await count_cursor.fetchone())[0]

        cursor = await db.execute(
            f"SELECT * FROM blast_campaigns {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        rows = await cursor.fetchall()
        return {"data": [_normalize_campaign(dict(r)) for r in rows], "total": total}


async def update_campaign(campaign_id: int, **fields) -> Optional[dict]:
    """Update campaign fields. Only draft campaigns can be fully edited."""
    allowed = {"name", "template_message", "device_id", "device_ids",
               "delay_between_ms", "human_delay_min_ms", "human_delay_max_ms",
               "content_variation_enabled", "schedule_enabled", "schedule_timezone",
               "active_hours_start", "active_hours_end", "peak_hours_start", "peak_hours_end",
               "lunch_break_start", "lunch_break_end", "weekend_factor", "auto_resume_enabled"}
    # Serialize device_ids list to JSON string before storing
    if "device_ids" in fields and isinstance(fields["device_ids"], list):
        fields = {**fields, "device_ids": json.dumps(fields["device_ids"])}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}

    if not updates:
        return await get_campaign(campaign_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [campaign_id]

    async with get_db() as db:
        await db.execute(
            f"UPDATE blast_campaigns SET {set_clause} WHERE id = ? AND status IN ('draft', 'paused')",
            params,
        )
        await db.commit()
    return await get_campaign(campaign_id)


async def delete_campaign(campaign_id: int) -> bool:
    """Delete a draft campaign and its recipients."""
    async with get_db() as db:
        # Only allow deleting draft/cancelled campaigns
        cursor = await db.execute(
            "DELETE FROM blast_campaigns WHERE id = ? AND status IN ('draft', 'completed', 'cancelled')",
            (campaign_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Recipient Management
# ---------------------------------------------------------------------------


async def add_recipients_from_contacts(
    campaign_id: int,
    contact_ids: list[int],
) -> dict:
    """Add recipients to a campaign from ig_contacts IDs.

    Joins ig_contacts with universities to get all needed data.
    Skips duplicates (same phone in same campaign).
    """
    added = 0
    skipped = 0

    async with get_db() as db:
        for contact_id in contact_ids:
            cursor = await db.execute(
                """SELECT c.id, c.phone_number, c.contact_name, c.university_id,
                          u.name as university_name
                   FROM ig_contacts c
                   LEFT JOIN universities u ON u.id = c.university_id
                   WHERE c.id = ?""",
                (contact_id,),
            )
            row = await cursor.fetchone()
            if not row:
                skipped += 1
                continue

            try:
                await db.execute(
                    """INSERT INTO blast_recipients
                       (campaign_id, contact_id, university_id, phone_number, contact_name, university_name)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (campaign_id, row["id"], row["university_id"],
                     row["phone_number"], row["contact_name"], row["university_name"]),
                )
                added += 1
            except Exception:
                # UNIQUE constraint — phone already in campaign
                skipped += 1

        # Update total count
        count_cursor = await db.execute(
            "SELECT COUNT(*) FROM blast_recipients WHERE campaign_id = ?",
            (campaign_id,),
        )
        total = (await count_cursor.fetchone())[0]
        await db.execute(
            "UPDATE blast_campaigns SET total_recipients = ? WHERE id = ?",
            (total, campaign_id),
        )
        await db.commit()

    return {"added": added, "skipped": skipped, "total": total}


async def add_recipients_from_universities(
    campaign_id: int,
    university_ids: list[int],
) -> dict:
    """Add ALL contacts from the given universities to a campaign.

    Prefers MySQL kontak_auto when dms_univ_id is set; falls back to SQLite ig_contacts.
    """
    from orchestrator.dms_mysql import get_kontak_auto_for_universities

    added = 0
    skipped = 0
    all_contacts: list[dict] = []

    async with get_db() as db:
        placeholders = ",".join("?" for _ in university_ids)

        # Split universities into MySQL-mapped vs SQLite-only
        u_cursor = await db.execute(
            f"SELECT id, name, dms_univ_id FROM universities WHERE id IN ({placeholders})",
            university_ids,
        )
        universities = await u_cursor.fetchall()

        dms_mapped = [(u["id"], u["name"], u["dms_univ_id"]) for u in universities if u["dms_univ_id"]]
        sqlite_only_ids = [u["id"] for u in universities if not u["dms_univ_id"]]

        # --- MySQL-backed contacts ---
        if dms_mapped:
            dms_univ_id_map = {dms_id: (uid, uname) for uid, uname, dms_id in dms_mapped}
            try:
                mysql_contacts = await get_kontak_auto_for_universities(list(dms_univ_id_map.keys()))
                for c in mysql_contacts:
                    uid, uname = dms_univ_id_map.get(int(c["id_univ"]), (None, c.get("universitas", "")))
                    all_contacts.append({
                        "contact_id": None,
                        "university_id": uid,
                        "phone_number": c["no_hp"],
                        "contact_name": c.get("pic") or "",
                        "university_name": uname,
                    })
            except Exception as e:
                log.warning("blast: MySQL kontak_auto fetch failed, falling back to SQLite: %s", e)
                sqlite_only_ids.extend(uid for uid, _, _ in dms_mapped)

        # --- SQLite fallback ---
        if sqlite_only_ids:
            fb_placeholders = ",".join("?" for _ in sqlite_only_ids)
            fb_cursor = await db.execute(
                f"""SELECT c.id, c.phone_number, c.contact_name, c.university_id,
                           u.name as university_name
                    FROM ig_contacts c
                    LEFT JOIN universities u ON u.id = c.university_id
                    WHERE c.university_id IN ({fb_placeholders})
                    ORDER BY u.name, c.contact_name""",
                sqlite_only_ids,
            )
            for row in await fb_cursor.fetchall():
                all_contacts.append({
                    "contact_id": row["id"],
                    "university_id": row["university_id"],
                    "phone_number": row["phone_number"],
                    "contact_name": row["contact_name"],
                    "university_name": row["university_name"],
                })

        # Insert all contacts into blast_recipients
        for c in all_contacts:
            try:
                await db.execute(
                    """INSERT INTO blast_recipients
                       (campaign_id, contact_id, university_id, phone_number, contact_name, university_name)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (campaign_id, c["contact_id"], c["university_id"],
                     c["phone_number"], c["contact_name"], c["university_name"]),
                )
                added += 1
            except Exception:
                skipped += 1

        count_cursor = await db.execute(
            "SELECT COUNT(*) FROM blast_recipients WHERE campaign_id = ?",
            (campaign_id,),
        )
        total = (await count_cursor.fetchone())[0]
        await db.execute(
            "UPDATE blast_campaigns SET total_recipients = ? WHERE id = ?",
            (total, campaign_id),
        )
        await db.commit()

    return {"added": added, "skipped": skipped, "total": total}


async def add_recipients_bulk(
    campaign_id: int,
    recipients: list[dict],
) -> dict:
    """Add recipients from a list of dicts with phone_number, contact_name, university_name, etc.

    Used when selecting from the filtered contacts query directly.
    """
    added = 0
    skipped = 0

    async with get_db() as db:
        for r in recipients:
            try:
                await db.execute(
                    """INSERT INTO blast_recipients
                       (campaign_id, contact_id, university_id, phone_number, contact_name, university_name)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (campaign_id, r.get("contact_id"), r.get("university_id"),
                     r["phone_number"], r.get("contact_name"), r.get("university_name")),
                )
                added += 1
            except Exception:
                skipped += 1

        count_cursor = await db.execute(
            "SELECT COUNT(*) FROM blast_recipients WHERE campaign_id = ?",
            (campaign_id,),
        )
        total = (await count_cursor.fetchone())[0]
        await db.execute(
            "UPDATE blast_campaigns SET total_recipients = ? WHERE id = ?",
            (total, campaign_id),
        )
        await db.commit()

    return {"added": added, "skipped": skipped, "total": total}


async def add_recipients_from_marketing_contacts(
    campaign_id: int,
    contacts: list[dict],
) -> dict:
    """Add recipients to a blast campaign from marketing contact results.

    Does NOT require university_id FK — marketing contacts live outside the
    university domain.

    Args:
        campaign_id: blast campaign ID
        contacts: list of dicts with keys:
            - phone_number  (required)
            - contact_name  (optional, client name)
            - university_name (optional, usually the value/display name)

    Returns:
        {"added": int, "skipped": int, "total": int}
    """
    added = 0
    skipped = 0

    async with get_db() as db:
        for contact in contacts:
            phone = contact.get("phone_number")
            if not phone:
                skipped += 1
                continue

            try:
                await db.execute(
                    """INSERT INTO blast_recipients
                       (campaign_id, contact_id, university_id, phone_number, contact_name, university_name)
                       VALUES (?, NULL, NULL, ?, ?, ?)""",
                    (
                        campaign_id,
                        phone,
                        contact.get("contact_name"),
                        contact.get("university_name"),
                    ),
                )
                added += 1
            except Exception:
                # UNIQUE constraint — phone already in campaign
                skipped += 1

        count_cursor = await db.execute(
            "SELECT COUNT(*) FROM blast_recipients WHERE campaign_id = ?",
            (campaign_id,),
        )
        total = (await count_cursor.fetchone())[0]
        await db.execute(
            "UPDATE blast_campaigns SET total_recipients = ? WHERE id = ?",
            (total, campaign_id),
        )
        await db.commit()

    return {"added": added, "skipped": skipped, "total": total}


async def remove_recipient(campaign_id: int, recipient_id: int) -> bool:
    """Remove a single recipient from a campaign."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM blast_recipients WHERE id = ? AND campaign_id = ? AND status = 'pending'",
            (recipient_id, campaign_id),
        )
        if cursor.rowcount > 0:
            count_cursor = await db.execute(
                "SELECT COUNT(*) FROM blast_recipients WHERE campaign_id = ?",
                (campaign_id,),
            )
            total = (await count_cursor.fetchone())[0]
            await db.execute(
                "UPDATE blast_campaigns SET total_recipients = ? WHERE id = ?",
                (total, campaign_id),
            )
        await db.commit()
        return cursor.rowcount > 0


async def clear_recipients(campaign_id: int) -> int:
    """Remove all pending recipients from a campaign."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM blast_recipients WHERE campaign_id = ? AND status = 'pending'",
            (campaign_id,),
        )
        removed = cursor.rowcount
        count_cursor = await db.execute(
            "SELECT COUNT(*) FROM blast_recipients WHERE campaign_id = ?",
            (campaign_id,),
        )
        total = (await count_cursor.fetchone())[0]
        await db.execute(
            "UPDATE blast_campaigns SET total_recipients = ? WHERE id = ?",
            (total, campaign_id),
        )
        await db.commit()
        return removed


async def get_recipients(
    campaign_id: int,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Get paginated recipients for a campaign."""
    conditions = ["campaign_id = ?"]
    params: list = [campaign_id]

    if status:
        conditions.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}"

    async with get_db() as db:
        count_cursor = await db.execute(
            f"SELECT COUNT(*) FROM blast_recipients {where}", params
        )
        total = (await count_cursor.fetchone())[0]

        cursor = await db.execute(
            f"""SELECT * FROM blast_recipients {where}
                ORDER BY id ASC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        )
        rows = await cursor.fetchall()
        return {"data": [dict(r) for r in rows], "total": total}


# ---------------------------------------------------------------------------
# Template Rendering
# ---------------------------------------------------------------------------


def render_template(template: str, recipient: dict) -> str:
    """Render a template message with placeholder substitution.

    Supported placeholders:
      {nama_universitas} — University name
      {nama_kontak}      — Contact person name
      {nomor_telepon}    — Phone number
    """
    replacements = {
        "nama_universitas": recipient.get("university_name") or "",
        "nama_kontak": recipient.get("contact_name") or "",
        "nomor_telepon": recipient.get("phone_number") or "",
    }

    result = template
    for key, value in replacements.items():
        result = result.replace(f"{{{key}}}", value)

    return result


async def render_all_messages(campaign_id: int) -> int:
    """Pre-render messages for all pending recipients. Returns count rendered."""
    campaign = await get_campaign(campaign_id)
    if not campaign:
        return 0

    rendered = 0

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM blast_recipients WHERE campaign_id = ? AND status = 'pending'",
            (campaign_id,),
        )
        rows = await cursor.fetchall()

        for row in rows:
            recipient = dict(row)
            msg = render_campaign_message(campaign, recipient)
            await db.execute(
                "UPDATE blast_recipients SET rendered_message = ? WHERE id = ?",
                (msg, recipient["id"]),
            )
            rendered += 1

        await db.commit()

    return rendered


async def preview_messages(campaign_id: int, limit: int = 3) -> list[dict]:
    """Preview rendered messages for a few recipients."""
    campaign = await get_campaign(campaign_id)
    if not campaign:
        return []

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM blast_recipients WHERE campaign_id = ? LIMIT ?",
            (campaign_id, limit),
        )
        rows = await cursor.fetchall()

    previews = []
    for row in rows:
        r = dict(row)
        previews.append({
            "phone_number": r["phone_number"],
            "contact_name": r.get("contact_name"),
            "university_name": r.get("university_name"),
            "rendered_message": render_campaign_message(campaign, r),
        })
    return previews


# ---------------------------------------------------------------------------
# Blast Execution
# ---------------------------------------------------------------------------

# Global reference to running blast task so we can cancel it
_blast_tasks: dict[int, asyncio.Task] = {}
_resume_tasks: dict[int, asyncio.Task] = {}


def _clear_resume_task(campaign_id: int) -> None:
    task = _resume_tasks.pop(campaign_id, None)
    current = asyncio.current_task()
    if task and task is not current and not task.done():
        task.cancel()


def _schedule_auto_resume_task(campaign_id: int, resume_at: datetime) -> None:
    _clear_resume_task(campaign_id)
    _resume_tasks[campaign_id] = asyncio.create_task(_auto_resume_worker(campaign_id, resume_at))


async def _auto_resume_worker(campaign_id: int, resume_at: datetime) -> None:
    try:
        delay_seconds = max(0.0, (resume_at - datetime.now(timezone.utc)).total_seconds())
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        campaign = await get_campaign(campaign_id)
        if not campaign or campaign["status"] != "paused" or not campaign["auto_resume_enabled"]:
            return

        stored_resume_at = _parse_iso_datetime(campaign.get("auto_resume_at"))
        now_utc = datetime.now(timezone.utc)
        if stored_resume_at and stored_resume_at > now_utc:
            _schedule_auto_resume_task(campaign_id, stored_resume_at)
            return

        result = await start_campaign(campaign_id)
        if result.get("success"):
            await ws_manager.broadcast_type(
                "blast_resumed",
                campaign_id=campaign_id,
                source="auto_resume",
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.error("[Blast] Auto-resume failed for campaign %d: %s", campaign_id, exc)
    finally:
        current = asyncio.current_task()
        if _resume_tasks.get(campaign_id) is current:
            _resume_tasks.pop(campaign_id, None)


async def restore_background_tasks() -> None:
    """Restore pending auto-resume timers after orchestrator restart."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT * FROM blast_campaigns
               WHERE status = 'paused' AND auto_resume_enabled = 1 AND auto_resume_at IS NOT NULL"""
        )
        rows = await cursor.fetchall()

    for row in rows:
        campaign = _normalize_campaign(dict(row))
        resume_at = _parse_iso_datetime(campaign.get("auto_resume_at"))
        if not resume_at:
            continue
        if resume_at <= datetime.now(timezone.utc):
            asyncio.create_task(_auto_resume_worker(campaign["id"], resume_at))
        else:
            _schedule_auto_resume_task(campaign["id"], resume_at)


async def start_campaign(
    campaign_id: int,
    started_by_dms_user_id: Optional[int] = None,
    started_by_email: Optional[str] = None,
    started_by_name: Optional[str] = None,
) -> dict:
    """Start or resume sending a blast campaign."""
    campaign = await get_campaign(campaign_id)
    if not campaign:
        return {"success": False, "error": "Campaign not found"}

    if campaign["status"] not in ("draft", "paused"):
        return {"success": False, "error": f"Cannot start campaign with status '{campaign['status']}'"}

    if campaign["total_recipients"] == 0:
        return {"success": False, "error": "No recipients in campaign"}

    if not campaign["template_message"].strip():
        return {"success": False, "error": "Template message is empty"}

    # Pre-render all messages
    await render_all_messages(campaign_id)
    _clear_resume_task(campaign_id)

    # Update status
    async with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """UPDATE blast_campaigns
               SET status = 'sending',
                   started_at = ?,
                   paused_at = NULL,
                   auto_resume_at = NULL,
                   paused_reason = NULL,
                   started_by_dms_user_id = ?,
                   started_by_email = ?,
                   started_by_name = ?
               WHERE id = ?""",
            (
                now,
                started_by_dms_user_id,
                started_by_email,
                started_by_name,
                campaign_id,
            ),
        )
        await db.commit()

    # Start background task
    task = asyncio.create_task(_blast_worker(campaign_id))
    _blast_tasks[campaign_id] = task

    return {"success": True, "campaign_id": campaign_id, "status": "sending"}


async def pause_campaign(campaign_id: int) -> dict:
    """Pause a running campaign."""
    campaign = await get_campaign(campaign_id)
    if not campaign or campaign["status"] != "sending":
        return {"success": False, "error": "Campaign is not currently sending"}

    # Cancel the worker task
    task = _blast_tasks.get(campaign_id)
    if task and not task.done():
        task.cancel()
    _clear_resume_task(campaign_id)

    async with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE blast_campaigns SET status = 'paused', paused_at = ?, auto_resume_at = NULL, paused_reason = ? WHERE id = ?",
            (now, "Paused manually", campaign_id),
        )
        await db.commit()

    return {"success": True, "campaign_id": campaign_id, "status": "paused"}


async def force_resume_campaign(
    campaign_id: int,
    started_by_dms_user_id: Optional[int] = None,
    started_by_email: Optional[str] = None,
    started_by_name: Optional[str] = None,
) -> dict:
    """Resume a paused campaign with anti-ban override enabled.

    The caller has explicitly acknowledged the ban risk. The campaign will run
    with force_send=True so health/cooldown/manual-pause checks are bypassed.
    Hard rate limits (per-minute, per-hour, per-day, warm-up daily cap,
    timelock-463) are still enforced by the WA service.
    """
    campaign = await get_campaign(campaign_id)
    if not campaign:
        return {"success": False, "error": "Campaign not found"}
    if campaign["status"] != "paused":
        return {"success": False, "error": f"Campaign is not paused (status: {campaign['status']})"}
    if campaign["total_recipients"] == 0:
        return {"success": False, "error": "No recipients in campaign"}

    await render_all_messages(campaign_id)
    _clear_resume_task(campaign_id)

    async with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """UPDATE blast_campaigns
               SET status = 'sending',
                   antiban_override = 1,
                   paused_at = NULL,
                   auto_resume_at = NULL,
                   paused_reason = NULL,
                   started_by_dms_user_id = ?,
                   started_by_email = ?,
                   started_by_name = ?
               WHERE id = ?""",
            (started_by_dms_user_id, started_by_email, started_by_name, campaign_id),
        )
        await db.commit()

    task = asyncio.create_task(_blast_worker(campaign_id))
    _blast_tasks[campaign_id] = task

    log.warning(
        "[Blast] Campaign %d force-resumed with anti-ban override by %s — ban risk accepted.",
        campaign_id,
        started_by_email or "unknown",
    )

    return {"success": True, "campaign_id": campaign_id, "status": "sending", "antiban_override": True}


async def cancel_campaign(campaign_id: int) -> dict:
    """Cancel a campaign (mark remaining as skipped)."""
    campaign = await get_campaign(campaign_id)
    if not campaign or campaign["status"] not in ("draft", "sending", "paused"):
        return {"success": False, "error": "Cannot cancel this campaign"}

    # Cancel worker if running
    task = _blast_tasks.get(campaign_id)
    if task and not task.done():
        task.cancel()
    _clear_resume_task(campaign_id)

    async with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE blast_recipients SET status = 'skipped' WHERE campaign_id = ? AND status = 'pending'",
            (campaign_id,),
        )
        await db.execute(
            "UPDATE blast_campaigns SET status = 'cancelled', completed_at = ?, auto_resume_at = NULL, paused_reason = NULL WHERE id = ?",
            (now, campaign_id),
        )
        await db.commit()

    return {"success": True, "campaign_id": campaign_id, "status": "cancelled"}


async def _blast_worker(campaign_id: int) -> None:
    """Background worker that sends messages one by one with configured delays."""
    log.info("[Blast] Worker started for campaign %d", campaign_id)

    try:
        campaign = await get_campaign(campaign_id)
        if not campaign:
            return

        while True:
            # Check if still sending
            current = await get_campaign(campaign_id)
            if not current or current["status"] != "sending":
                log.info("[Blast] Campaign %d no longer sending, stopping worker", campaign_id)
                break

            # Resolve device — multi-device rotation if device_ids is set.
            # current comes from get_campaign() → _normalize_campaign() which
            # already parses device_ids to a list, so handle both list and str.
            _raw_ids = current.get("device_ids") or []
            if isinstance(_raw_ids, list):
                _ids_list: list[str] = _raw_ids
            elif isinstance(_raw_ids, str):
                try:
                    _ids_list = json.loads(_raw_ids)
                except (json.JSONDecodeError, ValueError):
                    _ids_list = []
            else:
                _ids_list = []
            if len(_ids_list) >= 2:
                # Use total attempts (sent + failed) so failed sends don't
                # re-use the same device index repeatedly.
                _sent = (current.get("sent_count", 0) or 0) + (current.get("failed_count", 0) or 0)
                device_id = _ids_list[_sent % len(_ids_list)]
            else:
                device_id = (_ids_list[0] if _ids_list else None) or current["device_id"] or SYSTEM_DEVICE_ID
            allowed_now, wait_ms, wait_reason = _campaign_allows_schedule(
                current,
                datetime.now(timezone.utc),
            )
            if not allowed_now:
                sleep_ms = min(max(wait_ms, MIN_BLAST_DELAY_MS), 60_000)
                log.info(
                    "[Blast] Campaign %d waiting %dms for schedule window: %s",
                    campaign_id,
                    sleep_ms,
                    wait_reason,
                )
                await asyncio.sleep(sleep_ms / 1000.0)
                continue

            # Get next pending recipient
            async with get_db() as db:
                cursor = await db.execute(
                    """SELECT * FROM blast_recipients
                       WHERE campaign_id = ? AND status = 'pending'
                       ORDER BY id ASC LIMIT 1""",
                    (campaign_id,),
                )
                row = await cursor.fetchone()

            if not row:
                # All done
                log.info("[Blast] Campaign %d: all recipients processed", campaign_id)
                # Collect failed recipients for the completion report
                failed_list = []
                async with get_db() as db:
                    now = datetime.now(timezone.utc).isoformat()
                    await db.execute(
                        "UPDATE blast_campaigns SET status = 'completed', completed_at = ? WHERE id = ?",
                        (now, campaign_id),
                    )
                    await db.commit()
                    # Fetch failed recipients
                    cursor = await db.execute(
                        """SELECT phone_number, contact_name, university_name, error_message
                           FROM blast_recipients
                           WHERE campaign_id = ? AND status = 'failed'""",
                        (campaign_id,),
                    )
                    for frow in await cursor.fetchall():
                        failed_list.append({
                            "phone": frow["phone_number"],
                            "name": frow["contact_name"],
                            "university": frow["university_name"],
                            "error": frow["error_message"],
                        })

                await ws_manager.broadcast_type(
                    "blast_completed",
                    campaign_id=campaign_id,
                    failed=failed_list,
                )
                break

            recipient = dict(row)
            message = recipient.get("rendered_message") or render_template(
                campaign["template_message"], recipient
            )

            antiban_override = bool(current.get("antiban_override", 0))

            try:
                # Try each device in rotation order, skipping disconnected ones so a
                # single offline device never blocks the whole queue.
                _primary_idx = _sent % len(_ids_list) if _ids_list else 0
                _ordered_devices = (
                    [_ids_list[(_primary_idx + i) % len(_ids_list)] for i in range(len(_ids_list))]
                    if _ids_list else [device_id]
                )
                result = None
                for _candidate in _ordered_devices:
                    _r = await message_queue.send_now_detailed(
                        recipient["phone_number"], message,
                        device_id=_candidate, force_antiban=antiban_override,
                    )
                    if _r.device_unavailable:
                        log.warning(
                            "[Blast] Campaign %d: device %s disconnected, trying next for %s",
                            campaign_id, _candidate, recipient["phone_number"],
                        )
                        continue
                    result = _r
                    device_id = _candidate
                    break
                else:
                    # Every device is disconnected — pause campaign
                    _paused_reason = "Semua device terputus — reconnect device lalu resume"
                    async with get_db() as db:
                        _now_p = datetime.now(timezone.utc).isoformat()
                        await db.execute(
                            """UPDATE blast_campaigns SET status = 'paused', paused_at = ?, paused_reason = ?
                               WHERE id = ? AND status = 'sending'""",
                            (_now_p, _paused_reason, campaign_id),
                        )
                        await db.commit()
                    await ws_manager.broadcast_type(
                        "blast_paused", campaign_id=campaign_id,
                        reason=_paused_reason, auto_resume_at=None,
                    )
                    log.warning("[Blast] Campaign %d paused — all devices disconnected", campaign_id)
                    break  # exit outer while True

                if result is None:
                    continue  # safety — shouldn't reach here

                if result.success:
                    # Mark as sent only when WA service actually confirmed delivery
                    async with get_db() as db:
                        now = datetime.now(timezone.utc).isoformat()
                        await db.execute(
                            "UPDATE blast_recipients SET status = 'sent', rendered_message = ?, sent_at = ?, sent_device_id = ? WHERE id = ?",
                            (message, now, device_id, recipient["id"]),
                        )
                        await db.execute(
                            "UPDATE blast_campaigns SET sent_count = sent_count + 1 WHERE id = ?",
                            (campaign_id,),
                        )
                        # Auto-mark the source ig_contact as contacted
                        if recipient.get("contact_id"):
                            await db.execute(
                                "UPDATE ig_contacts SET manual_contacted = 1 WHERE id = ?",
                                (recipient["contact_id"],),
                            )
                        await db.commit()

                    # Broadcast progress
                    await ws_manager.broadcast_type(
                        "blast_progress",
                        campaign_id=campaign_id,
                        recipient_id=recipient["id"],
                        phone=recipient["phone_number"],
                        status="sent",
                    )
                elif result.blocked:
                    retry_after_ms = result.retry_after_ms or 0
                    paused_reason = _format_antiban_pause_reason(result)

                    if antiban_override:
                        # All devices already tried for disconnection (outer loop above).
                        # Primary device is connected but hit anti-ban limit — wait then retry.
                        wait_s = min(retry_after_ms / 1000.0, 30.0) if retry_after_ms > 0 else 5.0
                        log.warning(
                            "[Blast] Anti-ban override active for campaign %d — "
                            "blocked on %s (%s), waiting %.1fs then continuing. "
                            "Risk accepted by user.",
                            campaign_id,
                            recipient["phone_number"],
                            paused_reason,
                            wait_s,
                        )
                        await ws_manager.broadcast_type(
                            "blast_antiban_override_warning",
                            campaign_id=campaign_id,
                            reason=paused_reason,
                            retry_after_ms=retry_after_ms,
                            phone=recipient["phone_number"],
                        )
                        await asyncio.sleep(wait_s)
                        # Don't advance recipient — retry same recipient after wait
                        continue
                    else:
                        auto_resume_at = None
                        if current.get("auto_resume_enabled") and retry_after_ms > 0:
                            auto_resume_at = (
                                datetime.now(timezone.utc) + timedelta(milliseconds=retry_after_ms)
                            ).isoformat()

                        log.warning(
                            "[Blast] Anti-ban blocked campaign %d on %s for %sms: %s",
                            campaign_id,
                            recipient["phone_number"],
                            retry_after_ms,
                            paused_reason,
                        )

                        async with get_db() as db:
                            now = datetime.now(timezone.utc).isoformat()
                            await db.execute(
                                """UPDATE blast_campaigns
                                   SET status = 'paused', paused_at = ?, auto_resume_at = ?, paused_reason = ?
                                   WHERE id = ? AND status = 'sending'""",
                                (now, auto_resume_at, paused_reason, campaign_id),
                            )
                            await db.commit()

                        if auto_resume_at:
                            _schedule_auto_resume_task(campaign_id, _parse_iso_datetime(auto_resume_at) or datetime.now(timezone.utc))
                        else:
                            _clear_resume_task(campaign_id)

                        await ws_manager.broadcast_type(
                            "blast_paused",
                            campaign_id=campaign_id,
                            reason=paused_reason,
                            retry_after_ms=retry_after_ms,
                            auto_resume_at=auto_resume_at,
                            phone=recipient["phone_number"],
                        )
                        break
                else:
                    # WA service returned failure — mark as failed
                    log.warning(
                        "[Blast] send_now returned failure for %s: %s",
                        recipient["phone_number"],
                        result.error,
                    )
                    async with get_db() as db:
                        await db.execute(
                            "UPDATE blast_recipients SET status = 'failed', error_message = ?, sent_device_id = ? WHERE id = ?",
                            (result.error or 'WA service returned failure (not connected or send rejected)', device_id, recipient["id"]),
                        )
                        await db.execute(
                            "UPDATE blast_campaigns SET failed_count = failed_count + 1 WHERE id = ?",
                            (campaign_id,),
                        )
                        await db.commit()

                    await ws_manager.broadcast_type(
                        "blast_progress",
                        campaign_id=campaign_id,
                        recipient_id=recipient["id"],
                        phone=recipient["phone_number"],
                        status="failed",
                    )

            except Exception as e:
                log.error("[Blast] Failed to send to %s: %s", recipient["phone_number"], e)
                async with get_db() as db:
                    await db.execute(
                        "UPDATE blast_recipients SET status = 'failed', error_message = ?, sent_device_id = ? WHERE id = ?",
                        (str(e), device_id, recipient["id"]),
                    )
                    await db.execute(
                        "UPDATE blast_campaigns SET failed_count = failed_count + 1 WHERE id = ?",
                        (campaign_id,),
                    )
                    await db.commit()

            # Delay between messages
            delay_ms = _compute_inter_message_delay_ms(current, datetime.now(timezone.utc))
            await asyncio.sleep(delay_ms / 1000.0)

    except asyncio.CancelledError:
        log.info("[Blast] Worker for campaign %d was cancelled", campaign_id)
    except Exception as e:
        log.error("[Blast] Worker error for campaign %d: %s", campaign_id, e)
        # Mark campaign as paused on error
        async with get_db() as db:
            await db.execute(
                "UPDATE blast_campaigns SET status = 'paused', paused_reason = ? WHERE id = ? AND status = 'sending'",
                (str(e), campaign_id),
            )
            await db.commit()
    finally:
        _blast_tasks.pop(campaign_id, None)


# ---------------------------------------------------------------------------
# Contact Query Helpers (for the selection UI)
# ---------------------------------------------------------------------------


async def get_contacts_for_blast(
    *,
    university_ids: Optional[list[int]] = None,
    search: Optional[str] = None,
    province: Optional[str] = None,
    has_name: Optional[bool] = None,
    contacted: Optional[bool] = None,
    has_conversation: Optional[bool] = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """Query contacts suitable for blast selection with rich filters.

    Returns contacts joined with university data and conversation status.
    """
    conditions: list[str] = []
    params: list = []

    if university_ids:
        placeholders = ",".join("?" for _ in university_ids)
        conditions.append(f"c.university_id IN ({placeholders})")
        params.extend(university_ids)

    if search:
        conditions.append(
            "(u.name LIKE ? OR c.contact_name LIKE ? OR c.phone_number LIKE ?)"
        )
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    if province:
        conditions.append("u.province = ?")
        params.append(province)

    if has_name is True:
        conditions.append("c.contact_name IS NOT NULL AND c.contact_name != '' AND c.has_person_name = 1")
    elif has_name is False:
        conditions.append("(c.contact_name IS NULL OR c.contact_name = '' OR c.has_person_name = 0)")

    if contacted is True:
        conditions.append("c.manual_contacted = 1")
    elif contacted is False:
        conditions.append("(c.manual_contacted = 0 OR c.manual_contacted IS NULL)")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_db() as db:
        # Count
        count_cursor = await db.execute(
            f"""SELECT COUNT(*) FROM ig_contacts c
                LEFT JOIN universities u ON u.id = c.university_id
                {where}""",
            params,
        )
        total = (await count_cursor.fetchone())[0]

        # Data
        cursor = await db.execute(
            f"""SELECT
                    c.id as contact_id,
                    c.phone_number,
                    c.contact_name,
                    c.has_person_name,
                    c.manual_contacted,
                    c.university_id,
                    u.name as university_name,
                    u.province,
                    (SELECT conv.state FROM conversations conv
                     WHERE conv.contact_phone = c.phone_number
                     ORDER BY conv.id DESC LIMIT 1) as conversation_state
                FROM ig_contacts c
                LEFT JOIN universities u ON u.id = c.university_id
                {where}
                ORDER BY u.name, c.contact_name
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        )
        rows = await cursor.fetchall()
        return {"data": [dict(r) for r in rows], "total": total}
