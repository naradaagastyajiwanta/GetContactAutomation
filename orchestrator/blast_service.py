"""
Blast Campaign Service

Handles creating campaigns, adding recipients from university contacts,
rendering template messages with placeholders, and executing blast sends.
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

from orchestrator.config import log
from orchestrator.db import get_db
from orchestrator.message_queue import message_queue
from orchestrator.websocket import manager as ws_manager


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------


async def create_campaign(name: str, template_message: str = "", device_id: str = "device_1",
                          delay_between_ms: int = 5000,
                          human_delay_min_ms: int = 2000,
                          human_delay_max_ms: int = 8000) -> dict:
    """Create a new blast campaign."""
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO blast_campaigns
               (name, template_message, device_id, delay_between_ms, human_delay_min_ms, human_delay_max_ms)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, template_message, device_id, delay_between_ms, human_delay_min_ms, human_delay_max_ms),
        )
        await db.commit()
        campaign_id = cursor.lastrowid
        return await get_campaign(campaign_id)


async def get_campaign(campaign_id: int) -> Optional[dict]:
    """Get a single campaign by ID."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM blast_campaigns WHERE id = ?", (campaign_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)


async def list_campaigns(status: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict:
    """List campaigns with optional status filter."""
    conditions = []
    params = []

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
        return {"data": [dict(r) for r in rows], "total": total}


async def update_campaign(campaign_id: int, **fields) -> Optional[dict]:
    """Update campaign fields. Only draft campaigns can be fully edited."""
    allowed = {"name", "template_message", "device_id",
               "delay_between_ms", "human_delay_min_ms", "human_delay_max_ms"}
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

    Fetches ig_contacts for each university, skips duplicates.
    """
    added = 0
    skipped = 0

    async with get_db() as db:
        placeholders = ",".join("?" for _ in university_ids)
        cursor = await db.execute(
            f"""SELECT c.id, c.phone_number, c.contact_name, c.university_id,
                       u.name as university_name
                FROM ig_contacts c
                LEFT JOIN universities u ON u.id = c.university_id
                WHERE c.university_id IN ({placeholders})
                ORDER BY u.name, c.contact_name""",
            university_ids,
        )
        rows = await cursor.fetchall()

        for row in rows:
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

    template = campaign["template_message"]
    rendered = 0

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM blast_recipients WHERE campaign_id = ? AND status = 'pending'",
            (campaign_id,),
        )
        rows = await cursor.fetchall()

        for row in rows:
            recipient = dict(row)
            msg = render_template(template, recipient)
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

    template = campaign["template_message"]

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
            "rendered_message": render_template(template, r),
        })
    return previews


# ---------------------------------------------------------------------------
# Blast Execution
# ---------------------------------------------------------------------------

# Global reference to running blast task so we can cancel it
_blast_tasks: dict[int, asyncio.Task] = {}


async def start_campaign(campaign_id: int) -> dict:
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

    # Update status
    async with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        if campaign["status"] == "draft":
            await db.execute(
                "UPDATE blast_campaigns SET status = 'sending', started_at = ? WHERE id = ?",
                (now, campaign_id),
            )
        else:
            await db.execute(
                "UPDATE blast_campaigns SET status = 'sending', paused_at = NULL WHERE id = ?",
                (campaign_id,),
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

    async with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE blast_campaigns SET status = 'paused', paused_at = ? WHERE id = ?",
            (now, campaign_id),
        )
        await db.commit()

    return {"success": True, "campaign_id": campaign_id, "status": "paused"}


async def cancel_campaign(campaign_id: int) -> dict:
    """Cancel a campaign (mark remaining as skipped)."""
    campaign = await get_campaign(campaign_id)
    if not campaign or campaign["status"] not in ("draft", "sending", "paused"):
        return {"success": False, "error": "Cannot cancel this campaign"}

    # Cancel worker if running
    task = _blast_tasks.get(campaign_id)
    if task and not task.done():
        task.cancel()

    async with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE blast_recipients SET status = 'skipped' WHERE campaign_id = ? AND status = 'pending'",
            (campaign_id,),
        )
        await db.execute(
            "UPDATE blast_campaigns SET status = 'cancelled', completed_at = ? WHERE id = ?",
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

        device_id = campaign["device_id"] or "device_1"
        delay_ms = campaign["delay_between_ms"] or 5000

        while True:
            # Check if still sending
            current = await get_campaign(campaign_id)
            if not current or current["status"] != "sending":
                log.info("[Blast] Campaign %d no longer sending, stopping worker", campaign_id)
                break

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

            try:
                # Send directly (not via queue) so we get an actual success/failure result.
                result = await message_queue.send_now_detailed(
                    recipient["phone_number"],
                    message,
                    device_id=device_id,
                )

                if result.success:
                    # Mark as sent only when WA service actually confirmed delivery
                    async with get_db() as db:
                        now = datetime.now(timezone.utc).isoformat()
                        await db.execute(
                            "UPDATE blast_recipients SET status = 'sent', rendered_message = ?, sent_at = ? WHERE id = ?",
                            (message, now, recipient["id"]),
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
                    log.warning(
                        "[Blast] Anti-ban blocked campaign %d on %s for %sms: %s",
                        campaign_id,
                        recipient["phone_number"],
                        retry_after_ms,
                        result.error,
                    )

                    async with get_db() as db:
                        now = datetime.now(timezone.utc).isoformat()
                        await db.execute(
                            "UPDATE blast_campaigns SET status = 'paused', paused_at = ? WHERE id = ? AND status = 'sending'",
                            (now, campaign_id),
                        )
                        await db.commit()

                    await ws_manager.broadcast_type(
                        "blast_paused",
                        campaign_id=campaign_id,
                        reason=result.error or "Blocked by anti-ban policy",
                        retry_after_ms=retry_after_ms,
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
                            "UPDATE blast_recipients SET status = 'failed', error_message = ? WHERE id = ?",
                            (result.error or 'WA service returned failure (not connected or send rejected)', recipient["id"]),
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
                        "UPDATE blast_recipients SET status = 'failed', error_message = ? WHERE id = ?",
                        (str(e), recipient["id"]),
                    )
                    await db.execute(
                        "UPDATE blast_campaigns SET failed_count = failed_count + 1 WHERE id = ?",
                        (campaign_id,),
                    )
                    await db.commit()

            # Delay between messages
            await asyncio.sleep(delay_ms / 1000.0)

    except asyncio.CancelledError:
        log.info("[Blast] Worker for campaign %d was cancelled", campaign_id)
    except Exception as e:
        log.error("[Blast] Worker error for campaign %d: %s", campaign_id, e)
        # Mark campaign as paused on error
        async with get_db() as db:
            await db.execute(
                "UPDATE blast_campaigns SET status = 'paused' WHERE id = ? AND status = 'sending'",
                (campaign_id,),
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
