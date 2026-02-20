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
)
from orchestrator.agents.ig_handle_finder import run_handle_search_batch
from orchestrator.agents.ig_post_scraper import run_post_scrape_batch
from orchestrator.agents.ig_phone_extractor import run_phone_extraction_batch

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
    return await run_agent_in_thread(run_handle_search_batch)


async def _threaded_post_scrape():
    return await run_agent_in_thread(run_post_scrape_batch)


async def _threaded_phone_extraction():
    return await run_agent_in_thread(run_phone_extraction_batch)


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

    if not is_within_outreach_hours():
        log.info("Outside outreach hours, skipping")
        return

    if not await can_send_today():
        log.info("Daily quota reached, skipping outreach")
        return

    quota = await get_today_quota()
    remaining = cfg.MAX_DAILY_CONVERSATIONS - quota["conversations_started"]
    log.info(f"Starting outreach loop. Remaining quota: {remaining}")

    # Get universities that have been scraped and have IG contacts ready for outreach
    universities = await get_universities_by_status("ig_scraped", limit=remaining)

    for uni in universities:
        if not await can_send_today():
            log.info("Quota reached during outreach loop")
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
        await message_queue.enqueue_send(phone, message)

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

        await message_queue.enqueue_send(conv["contact_phone"], followup_msg)

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


def _outreach_hour_range() -> str:
    """Build the cron hour range string from current cfg values."""
    return f"{cfg.OUTREACH_START_HOUR}-{cfg.OUTREACH_END_HOUR - 1}"


def reschedule_outreach_jobs() -> None:
    """Re-apply cron expressions for outreach/followup jobs after config change."""
    hour_range = _outreach_hour_range()
    scheduler.reschedule_job("daily_outreach", trigger="cron", hour=hour_range, minute="0,30", timezone=WIB)
    scheduler.reschedule_job("process_followups", trigger="cron", hour=hour_range, minute="15", timezone=WIB)
    log.info("Rescheduled outreach jobs to hours %s", hour_range)


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

    # Agent 2: Scrape posts — every 3 hours during active hours
    scheduler.add_job(
        _threaded_post_scrape,
        "cron",
        hour="8-20/3",
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

    scheduler.start()
    log.info(
        "Scheduler started: outreach every 30min, followups every hour, "
        "handle finder every 2h, post scraper every 3h, phone extractor every 1h"
        + (", learning reflection 3x daily" if cfg.LEARNING_ENABLED else "")
    )
