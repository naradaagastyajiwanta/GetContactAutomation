"""
Scheduler for daily WhatsApp outreach and follow-up management.
"""
import asyncio
import concurrent.futures
import json
from datetime import datetime, timedelta, timezone
from functools import partial

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from orchestrator.config import (
    FOLLOWUP_1_AFTER_HOURS,
    FOLLOWUP_2_AFTER_HOURS,
    MAX_FOLLOWUP_ATTEMPTS,
    SYSTEM_DEVICE_ID,
    is_paused,
    log,
    cfg,
)
from orchestrator.conversation import conversation_manager, ConvState
from orchestrator.message_queue import message_queue
from orchestrator.db import (
    get_universities_by_status,
    get_contacts_for_university,
    get_conversation_by_phone,
    create_conversation,
    update_conversation_state,
    add_message_to_history,
    get_active_conversations,
    get_today_quota,
    increment_quota,
    can_send_today,
    update_university_status,
    validate_phone,
    create_pipeline_log,
    complete_pipeline_log,
)
from orchestrator.agents.ig_handle_finder import run_handle_search_batch
from orchestrator.agents.ig_post_scraper import run_post_scrape_batch
from orchestrator.agents.ig_phone_extractor import run_phone_extraction_batch
from orchestrator.agents.bem_finder import run_bem_discovery_batch
from orchestrator.websocket import manager as ws_manager

WIB = timezone(timedelta(hours=7))

scheduler = AsyncIOScheduler()

# ---------------------------------------------------------------------------
# Thread pool for heavy agent jobs
# ---------------------------------------------------------------------------
# Agent batch jobs (IG handle search, post scraping, phone extraction) can take
# minutes to complete.  Running them on the main event loop blocks ALL FastAPI
# HTTP request handling.  We offload them to a dedicated thread pool where each
# thread gets its own asyncio event loop, keeping the main loop responsive.

_agent_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="agent"
)


def _run_async_in_new_loop(coro_fn, *args, **kwargs):
    """Execute an async function in a fresh event loop (for thread pool)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_fn(*args, **kwargs))
    finally:
        loop.close()


async def run_agent_in_thread(coro_fn, *args, **kwargs):
    """Run an async agent function in a separate thread.

    Returns the result of the agent function once it completes.
    The main event loop stays free to serve HTTP requests while the
    agent works in the background thread.
    """
    fn = partial(_run_async_in_new_loop, coro_fn, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(_agent_pool, fn)


async def _threaded_handle_search():
    log_id = await create_pipeline_log("find_handles", "scheduler")
    try:
        result = await run_agent_in_thread(run_handle_search_batch)
        searched = result.get("searched", 0)
        found = result.get("found", 0)
        summary = {k: v for k, v in result.items() if k != "details"}
        await complete_pipeline_log(
            log_id, status="completed", summary=summary,
            details=result.get("details", [])[:100],
            items_processed=searched, items_success=found, items_failed=searched - found,
        )
        # Broadcast agent completion
        await ws_manager.broadcast_type(
            "agent_completed",
            agent="find_handles",
            stats={"searched": searched, "found": found},
        )
        return result
    except Exception as e:
        await complete_pipeline_log(log_id, status="failed", error=str(e))
        raise


async def _threaded_post_scrape():
    log_id = await create_pipeline_log("scrape_posts", "scheduler")
    try:
        result = await run_agent_in_thread(run_post_scrape_batch)
        summary = {k: v for k, v in result.items() if k != "details"}
        await complete_pipeline_log(
            log_id, status="completed", summary=summary,
            details=result.get("details", [])[:100],
            items_processed=result.get("scraped", 0),
            items_success=result.get("total_posts", 0),
        )
        # Broadcast agent completion
        await ws_manager.broadcast_type(
            "agent_completed",
            agent="scrape_posts",
            stats={"scraped": result.get("scraped", 0), "total_posts": result.get("total_posts", 0)},
        )
        return result
    except Exception as e:
        await complete_pipeline_log(log_id, status="failed", error=str(e))
        raise


async def _threaded_phone_extraction():
    log_id = await create_pipeline_log("extract_phones", "scheduler")
    try:
        result = await run_agent_in_thread(run_phone_extraction_batch)
        summary = {k: v for k, v in result.items() if k != "details"}
        await complete_pipeline_log(
            log_id, status="completed", summary=summary,
            details=result.get("details", [])[:100],
            items_processed=result.get("processed", 0),
            items_success=result.get("phones_found", 0),
        )
        # Broadcast agent completion
        await ws_manager.broadcast_type(
            "agent_completed",
            agent="extract_phones",
            stats={"processed": result.get("processed", 0), "phones_found": result.get("phones_found", 0)},
        )
        return result
    except Exception as e:
        await complete_pipeline_log(log_id, status="failed", error=str(e))
        raise


async def _threaded_bem_discovery():
    log_id = await create_pipeline_log("discover_bem", "scheduler")
    try:
        result = await run_agent_in_thread(run_bem_discovery_batch)
        searched = result.get("searched", 0)
        found = result.get("found", 0)
        summary = {k: v for k, v in result.items() if k != "details"}
        await complete_pipeline_log(
            log_id, status="completed", summary=summary,
            details=result.get("details", [])[:100],
            items_processed=searched, items_success=found,
            items_failed=searched - found,
        )
        # Broadcast agent completion
        await ws_manager.broadcast_type(
            "agent_completed",
            agent="discover_bem",
            stats={"searched": searched, "found": found},
        )
        return result
    except Exception as e:
        await complete_pipeline_log(log_id, status="failed", error=str(e))
        raise


def is_within_outreach_hours() -> bool:
    """Check if current time is within allowed outreach hours (WIB)."""
    now_wib = datetime.now(WIB)
    return cfg.OUTREACH_START_HOUR <= now_wib.hour < cfg.OUTREACH_END_HOUR


async def daily_outreach_loop():
    """
    Main outreach loop: pick universities with contacts, send initial messages.
    Respects daily quota and time window.
    """
    if is_paused():
        log.info("Bot is paused, skipping outreach")
        return

    if not cfg.CHATBOT_ENABLED:
        log.info("Contact finder chatbot disabled, skipping outreach")
        return

    if not is_within_outreach_hours():
        log.info("Outside outreach hours, skipping")
        return

    if not await can_send_today():
        log.info("Daily quota reached, skipping outreach")
        # Broadcast quota reached event
        await ws_manager.broadcast_type("quota_reached", remaining=0)
        return

    quota = await get_today_quota()
    remaining = cfg.MAX_DAILY_CONVERSATIONS - quota["conversations_started"]
    log.info(f"Starting outreach loop. Remaining quota: {remaining}")

    # Get universities that have been scraped and have IG contacts ready for outreach
    universities = await get_universities_by_status("ig_scraped", limit=remaining)

    for uni in universities:
        if not await can_send_today():
            log.info("Quota reached during outreach loop")
            await ws_manager.broadcast_type("quota_reached", remaining=0)
            break

        if not is_within_outreach_hours():
            log.info("Left outreach hours during loop")
            break

        contacts = await get_contacts_for_university(uni["id"])
        if not contacts:
            continue

        # Use the first available contact phone that hasn't been contacted yet
        phone = None
        contact_name = None
        for contact in contacts:
            candidate = validate_phone(contact["phone_number"]) or contact["phone_number"]
            existing = await get_conversation_by_phone(candidate)
            if not existing:
                phone = contact["phone_number"]
                contact_name = contact.get("contact_name")
                break
            else:
                log.info(f"Skipping {candidate} — already has conversation (uni {uni['name']})")

        if not phone:
            log.info(f"All contacts for {uni['name']} already contacted, skipping")
            continue

        # Generate initial message
        try:
            message = await conversation_manager.generate_initial_message(
                university_name=uni["name"],
                contact_name=contact_name,
            )
        except Exception as e:
            log.error(f"Failed to generate message for {uni['name']}: {e}")
            continue

        # Create conversation record
        conv_id = await create_conversation(uni["id"], phone)

        # Enqueue via message queue (serial sending with interval)
        await message_queue.enqueue_send(phone, message, device_id=SYSTEM_DEVICE_ID)

        await update_conversation_state(
            conv_id,
            ConvState.INITIAL_SENT,
            last_message_at=datetime.now(timezone.utc).isoformat(),
        )
        await add_message_to_history(conv_id, "bot", message)
        await increment_quota("conversations_started")
        await increment_quota("messages_sent")
        await update_university_status(uni["id"], "contacted")
        log.info(f"Outreach enqueued for {uni['name']} via {phone}")

        # Wait between messages
        await asyncio.sleep(cfg.MIN_MESSAGE_GAP_SECONDS)


async def process_followups():
    """
    Process follow-ups for conversations that need them.
    - 24h no reply → send follow-up 1
    - 48h no reply → send follow-up 2
    - After max attempts → mark ABANDONED
    """
    if is_paused():
        log.info("Bot is paused, skipping followups")
        return

    if not cfg.CHATBOT_ENABLED:
        log.info("Contact finder chatbot disabled, skipping followups")
        return

    if not is_within_outreach_hours():
        return

    conversations = await get_active_conversations(include_test=True)
    now = datetime.now(timezone.utc)

    for conv in conversations:
        state = conv["state"]
        followups = conv.get("followup_count", 0) or 0
        last_msg = conv["last_message_at"]

        if not last_msg:
            continue

        # Parse last message time
        if isinstance(last_msg, str):
            try:
                last_msg_dt = datetime.fromisoformat(last_msg.replace("Z", "+00:00"))
            except ValueError:
                continue
        else:
            continue

        hours_since = (now - last_msg_dt).total_seconds() / 3600

        # Only follow up on conversations waiting for reply
        if state not in (ConvState.INITIAL_SENT, ConvState.WAITING_REPLY, ConvState.FOLLOWUP_SENT, ConvState.NEED_MORE):
            continue

        # Check if max scheduled follow-ups reached
        if followups >= MAX_FOLLOWUP_ATTEMPTS:
            await update_conversation_state(conv["id"], ConvState.ABANDONED)
            await update_university_status(conv["university_id"], "failed")
            log.info(f"Conversation {conv['id']} abandoned after {followups} follow-ups")
            continue

        # Determine if follow-up is needed based on scheduled follow-up count
        should_followup = False
        if followups == 0 and hours_since >= FOLLOWUP_1_AFTER_HOURS:
            should_followup = True
        elif followups == 1 and hours_since >= FOLLOWUP_2_AFTER_HOURS:
            should_followup = True
        elif followups >= 2 and hours_since >= FOLLOWUP_2_AFTER_HOURS:
            # Max attempts, mark as abandoned
            await update_conversation_state(conv["id"], ConvState.ABANDONED)
            await update_university_status(conv["university_id"], "failed")
            log.info(f"Conversation {conv['id']} abandoned (no reply after {followups} follow-ups)")
            continue

        if not should_followup:
            continue

        if not await can_send_today():
            log.info("Quota reached during followup processing")
            break

        # Generate and send follow-up
        history = json.loads(conv["message_history"] or "[]")
        try:
            followup_msg = await conversation_manager.generate_followup(
                history, followups + 1, conversation=conv
            )
        except Exception as e:
            log.error(f"Failed to generate followup for conv {conv['id']}: {e}")
            continue

        await message_queue.enqueue_send(conv["contact_phone"], followup_msg, device_id=SYSTEM_DEVICE_ID)

        await update_conversation_state(
            conv["id"],
            ConvState.FOLLOWUP_SENT,
            followup_count=followups + 1,
            last_message_at=datetime.now(timezone.utc).isoformat(),
        )
        await add_message_to_history(conv["id"], "bot", followup_msg)
        await increment_quota("messages_sent")
        log.info(f"Follow-up {followups + 1} enqueued for conv {conv['id']}")

        await asyncio.sleep(cfg.MIN_MESSAGE_GAP_SECONDS)


async def process_audiensi_followups():
    """Process follow-ups for audiensi conversations."""
    if is_paused():
        return
    if not is_within_outreach_hours():
        return
    if not cfg.AUDIENSI_ENABLED:
        return

    from orchestrator.db import (
        get_audiensi_needing_followup,
        update_audiensi_state,
        add_audiensi_message,
    )
    from orchestrator.audiensi.states import AudiensiState

    hours = cfg.AUDIENSI_FOLLOWUP_AFTER_HOURS
    max_followups = cfg.AUDIENSI_MAX_FOLLOWUPS

    conversations = await get_audiensi_needing_followup(hours)
    now = datetime.now(timezone.utc)

    for aud in conversations:
        followups = aud.get("followup_count", 0) or 0

        if followups >= max_followups:
            await update_audiensi_state(aud["id"], AudiensiState.ABANDONED)
            log.info(f"Audiensi {aud['id']} abandoned after {followups} follow-ups")
            continue

        try:
            from orchestrator.audiensi.react_agent import AudiensiReactAgent
            agent = AudiensiReactAgent()
            msg = await agent.generate_followup(aud, followups + 1)
        except Exception as e:
            log.error(f"Failed to generate audiensi followup for {aud['id']}: {e}")
            continue

        await message_queue.enqueue_send(aud["contact_phone"], msg, device_id=SYSTEM_DEVICE_ID)
        await update_audiensi_state(
            aud["id"],
            AudiensiState.FOLLOWUP_SENT,
            followup_count=followups + 1,
            last_message_at=datetime.now(timezone.utc).isoformat(),
        )
        await add_audiensi_message(aud["id"], "bot", msg)
        log.info(f"Audiensi follow-up {followups + 1} sent for {aud['id']}")

        await asyncio.sleep(cfg.MIN_MESSAGE_GAP_SECONDS)


async def _threaded_audiensi_rector_finder():
    """Run audiensi rector finder in a thread."""
    from orchestrator.agents.rector_finder import run_rector_finder_batch
    return await run_agent_in_thread(run_rector_finder_batch)


# ---------------------------------------------------------------------------
# DMS MySQL Sync Jobs
# ---------------------------------------------------------------------------


async def dms_sync_audiensi_schedules():
    """
    Sync audiensi schedules from DMS MySQL.
    Logs upcoming schedules and sends WhatsApp reminders if configured.
    """
    if is_paused():
        return
    if not cfg.get("DMS_SYNC_ENABLED", False):
        return

    try:
        from orchestrator.dms_mysql import (
            get_schedules_needing_reminder,
            get_today_audiensi_schedules,
            create_follow_up_record,
            check_dms_connection,
        )

        # Health check
        health = await check_dms_connection()
        if health["status"] != "connected":
            log.error("DMS sync: MySQL not connected: %s", health.get("error"))
            return

        # 1. Log today's schedules
        today_schedules = await get_today_audiensi_schedules()
        if today_schedules:
            log.info("DMS sync: %d audiensi scheduled for today", len(today_schedules))
            for s in today_schedules:
                log.info(
                    "  → %s at %s — %s (zoom: %s)",
                    s.get("nama_universitas", "?"),
                    s.get("jam_audensi", "?"),
                    s.get("type_meeting", "?"),
                    "yes" if s.get("link_zoom") else "no",
                )

        # 2. Send WhatsApp reminders if enabled
        if cfg.get("DMS_REMINDER_ENABLED", False):
            await _send_audiensi_reminders()

    except Exception as e:
        log.error("DMS sync failed: %s", e, exc_info=True)


async def _send_audiensi_reminders():
    """Send WhatsApp reminders for upcoming audiensi meetings."""
    from orchestrator.dms_mysql import get_schedules_needing_reminder, create_follow_up_record

    hours_before = cfg.get("DMS_REMINDER_HOURS_BEFORE", 24)
    schedules = await get_schedules_needing_reminder(hours_before)

    if not schedules:
        return

    log.info("DMS reminder: %d schedules need reminders", len(schedules))

    for schedule in schedules:
        try:
            uni_name = schedule.get("nama_universitas", "Universitas")
            jadwal = schedule.get("jadwal_audiensi", "")
            jam = schedule.get("jam_audensi", "")
            link_zoom = schedule.get("link_zoom", "")

            # Build reminder message
            msg_lines = [
                f"📋 *Reminder Audiensi*",
                f"",
                f"Universitas: *{uni_name}*",
                f"Tanggal: {jadwal}",
                f"Jam: {jam} WIB",
            ]
            if link_zoom:
                msg_lines.append(f"Zoom: {link_zoom}")
            msg_lines.append(f"\nMohon konfirmasi kehadiran. Terima kasih 🙏🏻")
            message = "\n".join(msg_lines)

            # Send to all PICs with phone numbers
            phones_sent = []
            for pic_field, phone_field in [
                ("pic", "no_hppickampus"),
                ("pic2", "no_hppickampus2"),
                ("pic3", "no_hppickampus3"),
            ]:
                phone = schedule.get(phone_field, "")
                pic_name = schedule.get(pic_field, "")
                if phone and phone.strip() and len(phone.strip()) >= 8:
                    await message_queue.enqueue_send(phone.strip(), message, device_id=SYSTEM_DEVICE_ID)
                    phones_sent.append(phone.strip())
                    log.info(
                        "DMS reminder sent to %s (%s) for %s on %s",
                        pic_name, phone.strip(), uni_name, jadwal,
                    )

            # Log the reminder as a follow-up in DMS
            if phones_sent:
                id_univ = schedule.get("id_univ")
                if id_univ:
                    await create_follow_up_record(
                        id_univ=id_univ,
                        metode_followup="6",  # WhatsApp
                        hasil_followup="1",   # Sedang Difollow-up
                        catatan=f"[Auto Reminder] Reminder audiensi {jadwal} {jam} via GetContact AI Agent. Sent to: {', '.join(phones_sent)}",
                    )

            await asyncio.sleep(cfg.MIN_MESSAGE_GAP_SECONDS)

        except Exception as e:
            log.error("DMS reminder failed for schedule %s: %s", schedule.get("id"), e)


async def dms_sync_contacts():
    """
    Sync contacts discovered by GetContact AI to DMS kontak_auto table.
    Matches local universities with DMS universities by name and syncs extracted numbers.
    """
    if is_paused():
        return
    if not cfg.get("DMS_CONTACT_SYNC_ENABLED", False):
        return

    try:
        from orchestrator.dms_mysql import (
            find_dms_university_by_name,
            sync_contact_to_dms,
            check_dms_connection,
        )
        from orchestrator.db import get_db

        health = await check_dms_connection()
        if health["status"] != "connected":
            return

        # Get conversations with extracted numbers that haven't been synced to DMS
        async with get_db() as db:
            cursor = await db.execute("""
                SELECT c.id, c.extracted_number, c.extracted_contact_role,
                       u.name AS university_name, u.province
                FROM conversations c
                JOIN universities u ON u.id = c.university_id
                WHERE c.state = 'GOT_NUMBER'
                  AND c.extracted_number IS NOT NULL
                  AND c.id NOT IN (
                      SELECT CAST(json_extract(value, '$.conv_id') AS INTEGER)
                      FROM config WHERE key = 'dms_synced_conversations'
                  )
                ORDER BY c.id
                LIMIT 20
            """)
            rows = await cursor.fetchall()

        if not rows:
            return

        synced_ids = []
        for row in rows:
            try:
                uni_name = row[3]  # university_name
                phone = row[1]     # extracted_number
                role = row[2]      # extracted_contact_role

                # Find matching DMS university
                dms_uni = await find_dms_university_by_name(uni_name)
                if not dms_uni:
                    log.debug("DMS contact sync: no DMS match for '%s'", uni_name)
                    continue

                result = await sync_contact_to_dms(
                    id_univ=dms_uni["id_univ"],
                    universitas=dms_uni["universitas"],
                    pic=role or "Staff",
                    jabatan=role or "Staff Kampus",
                    no_hp=phone,
                    source_type="getcontact_ai",
                    source_origin="GetContact AI Agent - Auto Discovery",
                    context_snippet=f"Extracted from WhatsApp conversation by AI",
                )

                if result:
                    synced_ids.append(row[0])
                    log.info(
                        "DMS contact sync: phone %s → %s (DMS ID %s)",
                        phone, dms_uni["universitas"], dms_uni["id_univ"],
                    )
            except Exception as e:
                log.error("DMS contact sync failed for conv %s: %s", row[0], e)

        if synced_ids:
            log.info("DMS contact sync: synced %d new contacts", len(synced_ids))

    except Exception as e:
        log.error("DMS contact sync failed: %s", e, exc_info=True)


async def _run_audiensi_research():
    """
    Scheduled job: Run H-1 audiensi research via Gemini AI.
    Finds tomorrow's unresearched schedules, researches background info, and sends WA notifications.
    """
    if is_paused():
        return
    if not cfg.get("DMS_RESEARCH_ENABLED", False):
        return

    try:
        from orchestrator.audiensi_research import research_tomorrow_schedules

        log.info("Starting scheduled H-1 audiensi research...")
        results = await research_tomorrow_schedules()
        successful = len([r for r in results if "error" not in r])
        log.info(
            "H-1 audiensi research completed: %d/%d successful",
            successful, len(results),
        )
    except Exception as e:
        log.error("Scheduled audiensi research failed: %s", e, exc_info=True)


async def _run_audiensi_research_check():
    """
    Periodic safety check: research any upcoming schedules (H-1 to H-3)
    that haven't been researched yet.

    Catches:
    - Newly added schedules that missed the main H-1 job
    - Failed researches that need a retry
    Runs every few hours so every audiensi is covered before its day arrives.
    """
    if is_paused():
        return
    if not cfg.get("DMS_RESEARCH_ENABLED", False):
        return
    if not cfg.get("DMS_SYNC_ENABLED", False):
        return

    try:
        from orchestrator.audiensi_research import research_unresearched_upcoming
        results = await research_unresearched_upcoming(days_ahead=3)
        if results:
            successful = len([r for r in results if "error" not in r])
            log.info(
                "Research safety check: caught and researched %d/%d new schedules",
                successful, len(results),
            )
    except Exception as e:
        log.error("Research safety check failed: %s", e, exc_info=True)


async def run_learning_reflection():
    """Run periodic learning reflection."""
    if not cfg.LEARNING_ENABLED:
        return
    try:
        from orchestrator.agent.learning import LearningSystem

        ls = LearningSystem()
        result = await ls.run_reflection()
        log.info("Learning reflection completed: %s", result)
    except Exception as e:
        log.error("Learning reflection failed: %s", e)


async def run_build_missing_embeddings():
    """Build semantic embeddings for un-embedded knowledge_items and lessons."""
    if not cfg.LEARNING_ENABLED:
        return
    try:
        from orchestrator.agent.embeddings import build_missing_embeddings
        result = await build_missing_embeddings()
        if result["knowledge_items"] or result["lessons"]:
            log.info("Embeddings built: %s", result)
    except Exception as e:
        log.error("build_missing_embeddings job failed: %s", e)


async def auto_approve_queued_audiensi():
    """Auto-approve QUEUED audiensi records that have been waiting long enough."""
    if not cfg.get("AUTO_APPROVE_AUDIENSI", False):
        return
    if not cfg.AUDIENSI_ENABLED:
        return

    delay_minutes = cfg.get("AUTO_APPROVE_DELAY_MINUTES", 60)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=delay_minutes)

    try:
        from orchestrator.db import get_db
        from orchestrator.audiensi.react_agent import AudiensiReactAgent

        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT id, contact_phone, university_id, initial_message_draft
                FROM audiensi_conversations
                WHERE state = 'QUEUED'
                  AND created_at <= ?
                LIMIT 10
                """,
                (cutoff.isoformat(),),
            )
            rows = await cursor.fetchall()

        if not rows:
            return

        log.info("Auto-approve: %d queued audiensi ready for approval", len(rows))
        for row in rows:
            aud_id = row[0]
            phone = row[1]
            draft = row[3]
            try:
                from orchestrator.db import update_audiensi_state
                await update_audiensi_state(aud_id, "APPROVED")

                # Send initial message if a draft exists
                if draft:
                    await message_queue.enqueue_send(phone, draft, device_id=SYSTEM_DEVICE_ID)
                    await update_audiensi_state(aud_id, "INITIAL_SENT")
                    log.info("Auto-approved audiensi %d → INITIAL_SENT", aud_id)
                else:
                    log.info("Auto-approved audiensi %d → APPROVED (no draft)", aud_id)

                await ws_manager.broadcast_type(
                    "audiensi_auto_approved",
                    audiensi_id=aud_id,
                    phone=phone,
                )
            except Exception as e:
                log.error("Auto-approve failed for audiensi %d: %s", aud_id, e)

    except Exception as e:
        log.error("auto_approve_queued_audiensi failed: %s", e)


def _outreach_hour_range() -> str:
    """Build the cron hour range string from current cfg values."""
    return f"{cfg.OUTREACH_START_HOUR}-{cfg.OUTREACH_END_HOUR - 1}"


def reschedule_outreach_jobs() -> None:
    """Re-apply cron expressions for outreach/followup jobs after config change."""
    hour_range = _outreach_hour_range()
    scheduler.reschedule_job("daily_outreach", trigger="cron", hour=hour_range, minute="0,30", timezone=WIB)
    scheduler.reschedule_job("process_followups", trigger="cron", hour=hour_range, minute="15", timezone=WIB)
    log.info("Rescheduled outreach jobs to hours %s", hour_range)


async def _reset_stale_error_clients(group_id: int, older_than_minutes: int = 60) -> int:
    """Reset marketing_clients stuck in 'error' state back to 'pending' after a cooldown.

    Clients with [QUOTA_EXHAUSTED] error are NOT reset — they require manual intervention
    (user tops up credits and restarts the group).
    """
    import aiosqlite
    from orchestrator.config import DATABASE_PATH
    from orchestrator.marketing.orchestration import _QUOTA_ERROR_MARKER
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        cur = await db.execute(
            """UPDATE marketing_clients
               SET search_status = 'pending', error_message = NULL
               WHERE group_id = ? AND search_status = 'error'
                 AND (error_message IS NULL OR error_message NOT LIKE ?)
                 AND updated_at < datetime('now', ? || ' minutes')""",
            (group_id, f"%{_QUOTA_ERROR_MARKER}%", f"-{older_than_minutes}"),
        )
        await db.commit()
        count = cur.rowcount or 0
    if count:
        log.info("[Scheduler] Group %d: reset %d stale error client(s) → pending", group_id, count)
    return count


async def _run_marketing_search_queue():
    """Run marketing client orchestration for groups that still have pending clients."""
    from orchestrator.marketing.search import process_search_queue
    from orchestrator.marketing.groups import get_group_search_status, list_groups

    groups = await list_groups()
    for group in groups["groups"]:
        if group["status"] not in {"draft", "searching"}:
            continue
        status = await get_group_search_status(group["id"])

        # Reset clients stuck in 'error' for > 1 hour so they get retried next run
        if status.get("error", 0) > 0:
            await _reset_stale_error_clients(group["id"], older_than_minutes=60)
            status = await get_group_search_status(group["id"])

        if status["pending"] > 0:
            asyncio.create_task(process_search_queue(group["id"]))


def setup_scheduler():
    """Configure and start the APScheduler."""
    hour_range = _outreach_hour_range()

    # Run outreach every 30 minutes during active hours
    scheduler.add_job(
        daily_outreach_loop,
        "cron",
        hour=hour_range,
        minute="0,30",
        timezone=WIB,
        id="daily_outreach",
        replace_existing=True,
    )

    # Check followups every hour
    scheduler.add_job(
        process_followups,
        "cron",
        hour=hour_range,
        minute="15",
        timezone=WIB,
        id="process_followups",
        replace_existing=True,
    )

    # Agent 1: Find IG handles — every 2 hours during active hours
    # Uses _threaded_ wrapper to run in a separate thread (keeps event loop free)
    scheduler.add_job(
        _threaded_handle_search,
        "cron",
        hour="8-20/2",
        minute="0",
        timezone=WIB,
        id="agent_handle_finder",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,  # Skip if more than 5 min late (avoids fire-on-startup)
    )

    # Agent 2: Scrape posts — every hour, 24 hours a day
    scheduler.add_job(
        _threaded_post_scrape,
        "cron",
        hour="*/1",
        minute="10",
        timezone=WIB,
        id="agent_post_scraper",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    # Agent 3: Extract phones — every hour during active hours
    scheduler.add_job(
        _threaded_phone_extraction,
        "cron",
        hour="8-21",
        minute="30",
        timezone=WIB,
        id="agent_phone_extractor",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    # Agent 4: BEM discovery — every hour, 24 hours a day
    scheduler.add_job(
        _threaded_bem_discovery,
        "cron",
        hour="*/1",
        minute="40",
        timezone=WIB,
        id="agent_bem_discovery",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    # Learning reflection — 3 times a day
    if cfg.LEARNING_ENABLED:
        scheduler.add_job(
            run_learning_reflection,
            "cron",
            hour="8,14,20",
            minute="45",
            timezone=WIB,
            id="learning_reflection",
            replace_existing=True,
        )
        # Build semantic embeddings every 6 hours
        scheduler.add_job(
            run_build_missing_embeddings,
            "cron",
            hour="*/6",
            minute="55",
            timezone=WIB,
            id="build_embeddings",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=300,
        )

    # Auto-approve queued audiensi — every 15 minutes
    if cfg.AUDIENSI_ENABLED:
        scheduler.add_job(
            auto_approve_queued_audiensi,
            "interval",
            minutes=15,
            timezone=WIB,
            id="auto_approve_audiensi",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=120,
        )

    # Audiensi follow-ups — every hour during active hours
    if cfg.AUDIENSI_ENABLED:
        scheduler.add_job(
            process_audiensi_followups,
            "cron",
            hour=hour_range,
            minute="45",
            timezone=WIB,
            id="audiensi_followups",
            replace_existing=True,
        )

        # Audiensi rector finder — every 4 hours
        scheduler.add_job(
            _threaded_audiensi_rector_finder,
            "cron",
            hour="8-20/4",
            minute="20",
            timezone=WIB,
            id="audiensi_rector_finder",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=300,
        )

    # DMS MySQL sync — scheduled at configured interval
    if cfg.get("DMS_SYNC_ENABLED", False):
        dms_interval = cfg.get("DMS_SYNC_INTERVAL_MINUTES", 30)
        scheduler.add_job(
            dms_sync_audiensi_schedules,
            "interval",
            minutes=dms_interval,
            timezone=WIB,
            id="dms_sync_schedules",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=300,
        )

        # DMS contact sync — every 2 hours
        if cfg.get("DMS_CONTACT_SYNC_ENABLED", False):
            scheduler.add_job(
                dms_sync_contacts,
                "cron",
                hour="8-20/2",
                minute="50",
                timezone=WIB,
                id="dms_contact_sync",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300,
            )

    scheduler.add_job(
        _run_marketing_search_queue,
        "cron",
        hour="*",
        minute=0,
        timezone=WIB,
        id="marketing_search_queue",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=600,
    )

    # DMS Audiensi Research — daily H-1 research via Gemini AI
    if cfg.get("DMS_RESEARCH_ENABLED", False):
        research_hour = cfg.get("DMS_RESEARCH_HOUR", 18)
        scheduler.add_job(
            _run_audiensi_research,
            "cron",
            hour=research_hour,
            minute=0,
            timezone=WIB,
            id="dms_audiensi_research",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=600,
        )

        # Safety check every 4 hours — catch unresearched upcoming schedules
        scheduler.add_job(
            _run_audiensi_research_check,
            "cron",
            hour="8-22/4",
            minute=30,
            timezone=WIB,
            id="dms_research_safety_check",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=600,
        )

    # Codex OAuth health monitor — checks token validity every 15 minutes
    # when OAuth is enabled. The token store auto-refreshes on every
    # gateway call, so this is a sanity check + nudge for refresh +
    # WebSocket state change emitter.
    scheduler.add_job(
        _check_codex_oauth_health,
        "interval",
        minutes=15,
        id="codex_oauth_health",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    scheduler.start()
    log.info(
        "Scheduler started: outreach every 30min, followups every hour, "
        "handle finder every 2h, post scraper every 3h, phone extractor every 1h, "
        "BEM discovery every 4h"
        + (", learning reflection 3x daily" if cfg.LEARNING_ENABLED else "")
        + (", audiensi followups + rector finder" if cfg.AUDIENSI_ENABLED else "")
        + (", DMS sync" if cfg.get("DMS_SYNC_ENABLED", False) else "")
        + (f", audiensi research @{research_hour}:00 WIB + safety check every 4h" if cfg.get("DMS_RESEARCH_ENABLED", False) else "")
        + ", codex-oauth health every 15min"
    )


# --- Codex OAuth health monitor job ------------------------------------------

_codex_oauth_last_state: str | None = None


async def _check_codex_oauth_health() -> None:
    """Touch the in-process Codex token store, log state transitions.

    Calls ``codex_token_store.load_tokens()`` which auto-refreshes if
    the access token is close to expiry. Emits a WebSocket event on
    logged_out→logged_in or vice versa so the FE can update its
    indicator without polling.
    """
    global _codex_oauth_last_state
    if not cfg.CHATGPT_OAUTH_ENABLED:
        return

    new_state: str
    try:
        from orchestrator.llm import codex_token_store
        tokens = await codex_token_store.load_tokens()
        new_state = "logged_in" if tokens is not None else "logged_out"
    except Exception as e:
        log.debug("codex-oauth health probe failed: %s", e)
        new_state = "error"

    if new_state != _codex_oauth_last_state:
        log.info(
            "codex-oauth state: %s -> %s",
            _codex_oauth_last_state or "unknown", new_state,
        )
        try:
            from orchestrator.websocket import manager as ws_manager
            await ws_manager.broadcast({
                "event": "codex_oauth_state",
                "state": new_state,
            })
        except Exception:
            pass
        _codex_oauth_last_state = new_state
