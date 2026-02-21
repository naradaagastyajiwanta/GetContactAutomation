"""
FastAPI orchestrator - main server that ties everything together.
Run: uvicorn orchestrator.main:app --port 8000 --reload
"""
import asyncio
import csv
import io
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI, BackgroundTasks, UploadFile, File as FastAPIFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from orchestrator.config import WA_SERVICE_URL, WEBHOOK_URL, log, is_paused, set_paused, cfg
from orchestrator.db import (
    init_db,
    get_dashboard_stats,
    get_universities_by_status,
    get_all_universities,
    get_pipeline_status,
    get_conversation_by_phone,
    get_university_by_id,
    get_contacts_for_university,
    get_posts_for_university,
    get_conversations_filtered,
    get_conversation_by_id,
    add_university,
    search_universities,
    validate_phone,
    get_all_active_lessons,
    get_unprocessed_analyses,
    upsert_config,
    delete_config as db_delete_config,
    create_conversation,
    update_conversation_state,
    add_message_to_history,
    get_knowledge_items,
    get_knowledge_items_by_tags,
    create_knowledge_item,
    update_knowledge_item,
    delete_knowledge_item,
    get_api_call_logs,
    get_api_call_log_by_id,
    cleanup_old_api_logs,
    clear_all_response_ids,
)
from orchestrator.config_registry import (
    CONFIG_DEFINITIONS,
    CONFIG_DEFINITIONS_MAP,
    ConfigType,
)
from orchestrator.agent.learning import LearningSystem
from orchestrator.conversation import conversation_manager, ConvState
from orchestrator.message_queue import message_queue
from orchestrator.scheduler import (
    setup_scheduler,
    scheduler,
    daily_outreach_loop,
    process_followups,
    run_agent_in_thread,
)
from orchestrator.agents.ig_handle_finder import run_handle_search_batch
from orchestrator.agents.ig_post_scraper import run_post_scrape_batch
from orchestrator.agents.ig_phone_extractor import run_phone_extraction_batch
from orchestrator.config import PROVINCES

learning_system = LearningSystem()

_TERMINAL_STATES = {"GOT_NUMBER", "REFUSED", "ABANDONED"}
_AUDIENSI_TERMINAL_STATES = {"ZOOM_SENT", "REFUSED", "ABANDONED"}


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await cfg.init_from_db()
    log.info("Database initialized")

    # Cleanup old API call logs
    try:
        deleted = await cleanup_old_api_logs(days=cfg.API_LOG_RETENTION_DAYS)
        if deleted:
            log.info("Cleaned up %d old API call logs", deleted)
    except Exception as e:
        log.warning("Failed to cleanup old API logs: %s", e)

    # Register webhook with WA service
    await register_webhook()

    # Start message queue send worker
    worker_task = asyncio.create_task(message_queue.send_worker())

    # Start scheduler
    setup_scheduler()
    log.info("Orchestrator started on port 8000")

    yield

    # Cancel send worker
    worker_task.cancel()

    # Shutdown
    scheduler.shutdown(wait=False)
    log.info("Scheduler stopped, shutting down")


app = FastAPI(title="GetContact AI Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def register_webhook():
    """Register our webhook URL with the WhatsApp service."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{WA_SERVICE_URL}/webhook/register",
                json={"url": WEBHOOK_URL},
            )
            if resp.status_code == 200:
                log.info(f"Webhook registered: {WEBHOOK_URL}")
            else:
                log.warning(f"Webhook registration returned {resp.status_code}")
        except Exception as e:
            log.warning(f"Could not register webhook (WA service may not be running): {e}")


# ---------------------------------------------------------------------------
# Webhook endpoint (receives incoming WA messages from Node.js service)
# ---------------------------------------------------------------------------

class IncomingMessage(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str | None = None
    message: str
    timestamp: int | None = None
    messageId: str | None = None
    pushName: str | None = None


@app.post("/webhook/incoming")
async def handle_incoming_message(payload: dict, background_tasks: BackgroundTasks):
    """Handle incoming WhatsApp message forwarded from Node.js service."""
    phone = payload.get("from", "")
    message = payload.get("message", "")
    push_name = payload.get("pushName", "")
    msg_key = payload.get("msgKey")
    all_msg_keys = payload.get("allMsgKeys")

    if not phone or not message:
        return {"status": "ignored", "reason": "empty payload"}

    # Normalize phone to +62 format for lookup
    normalized = validate_phone(phone) or phone

    log.info(f"Incoming WA from {phone} ({push_name}): {message[:100]}")

    # Process in background to respond quickly to webhook
    background_tasks.add_task(
        _process_incoming, normalized, phone, message, push_name, msg_key, all_msg_keys,
    )

    return {"status": "received"}


async def _process_incoming(
    normalized_phone: str,
    raw_phone: str,
    message: str,
    push_name: str = "",
    msg_key: str | None = None,
    all_msg_keys: list | None = None,
):
    """Process incoming message and respond if needed.

    Routes to the appropriate handler: chatbot 1 (contact finder) or
    audiensi chatbot (Zoom scheduling).
    """
    if is_paused():
        log.info(f"Paused – ignoring incoming message from {raw_phone}")
        return

    # Try audiensi chatbot first (phase 2 conversations)
    if cfg.AUDIENSI_ENABLED:
        try:
            from orchestrator.db import get_audiensi_conversation_by_phone
            from orchestrator.audiensi.conversation import audiensi_conversation_manager
            from orchestrator.audiensi.states import AudiensiState

            aud = await get_audiensi_conversation_by_phone(normalized_phone)
            if aud and aud["state"] not in AudiensiState.terminal_states():
                log.info(f"Routing to audiensi handler for {raw_phone}")
                result = await message_queue.process_with_ai(
                    audiensi_conversation_manager.process_incoming_message(
                        normalized_phone, message, push_name=push_name,
                    )
                )
                if result.get("response_message"):
                    await message_queue.enqueue_send(
                        raw_phone, result["response_message"],
                        reply_to_msg_key=msg_key, all_msg_keys=all_msg_keys,
                    )
                # Trigger post-audiensi analysis for terminal states
                if result.get("conversation_state") in _AUDIENSI_TERMINAL_STATES and cfg.LEARNING_ENABLED:
                    asyncio.create_task(learning_system.analyze_completed_audiensi(aud["id"]))
                return
        except Exception as e:
            log.warning(f"Audiensi routing check failed: {e}")

    # Default: chatbot 1 (contact finder)
    if not cfg.CHATBOT_ENABLED:
        log.info(f"Contact finder chatbot disabled – ignoring message from {raw_phone}")
        return

    result = await message_queue.process_with_ai(
        conversation_manager.process_incoming_message(
            normalized_phone, message, push_name=push_name,
        )
    )

    if result.get("response_message"):
        await message_queue.enqueue_send(
            raw_phone, result["response_message"],
            reply_to_msg_key=msg_key, all_msg_keys=all_msg_keys,
        )

    # Trigger post-conversation analysis for terminal states
    if result.get("conversation_state") in _TERMINAL_STATES and cfg.LEARNING_ENABLED:
        conv = await get_conversation_by_phone(normalized_phone)
        if conv:
            asyncio.create_task(learning_system.analyze_completed_conversation(conv["id"]))


# ---------------------------------------------------------------------------
# Dashboard & Status
# ---------------------------------------------------------------------------

@app.get("/dashboard")
async def dashboard():
    """Get overall system statistics."""
    stats = await get_dashboard_stats()
    return stats


@app.get("/universities")
async def list_universities(
    status: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List universities with optional status filter, search, and pagination."""
    if search:
        return await search_universities(search)
    if status:
        return await get_universities_by_status(status, limit=limit, offset=offset)
    return await get_all_universities(limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# PDDIKTI university collection
# ---------------------------------------------------------------------------

@app.get("/pddikti/provinces")
async def get_provinces():
    """Return the list of Indonesian provinces for PDDIKTI search."""
    return {"provinces": PROVINCES}


@app.post("/pipeline/collect-universities")
async def trigger_collect_universities(
    background_tasks: BackgroundTasks,
    province: str | None = None,
    limit: int | None = None,
):
    """Collect universities from PDDIKTI API. Optionally filter by province and limit."""
    from scripts.collect_universities import search_pddikti

    async def _collect(province: str | None, limit: int | None):
        existing = await get_all_universities(limit=10000)
        existing_names = [u["name"] for u in existing]

        from scripts.collect_universities import is_duplicate

        universities = await search_pddikti(province, limit=limit)
        added = 0
        for u in universities:
            if is_duplicate(u["name"], existing_names):
                continue
            try:
                await add_university(
                    name=u["name"],
                    pddikti_id=u.get("pddikti_id"),
                    province=u.get("province"),
                    website=u.get("website"),
                )
                existing_names.append(u["name"])
                added += 1
            except Exception as e:
                log.warning(f"Failed to add '{u['name']}': {e}")
        log.info(f"[PDDIKTI] Collected {added} new universities (province={province}, limit={limit})")

    msg = f"Collecting universities from PDDIKTI"
    if province:
        msg += f" (province: {province})"
    if limit:
        msg += f" (limit: {limit})"
    background_tasks.add_task(_collect, province, limit)
    return {"status": "started", "message": msg}


# ---------------------------------------------------------------------------
# University manual add
# ---------------------------------------------------------------------------


class UniversityInput(BaseModel):
    name: str
    province: Optional[str] = None
    website: Optional[str] = None


class UniversityAddPayload(BaseModel):
    # Single university
    name: Optional[str] = None
    province: Optional[str] = None
    website: Optional[str] = None
    # Bulk
    universities: Optional[list[UniversityInput]] = None


async def _get_existing_university_names() -> set[str]:
    """Return a set of lowercased university names already in the database."""
    from orchestrator.db import get_db
    async with get_db() as db:
        cursor = await db.execute("SELECT LOWER(name) AS lname FROM universities")
        rows = await cursor.fetchall()
        return {r["lname"] for r in rows}


@app.post("/universities")
async def add_universities_endpoint(payload: UniversityAddPayload):
    """Add one or many universities via JSON.

    Single: {"name": "Univ X", "province": "...", "website": "..."}
    Bulk:   {"universities": [{"name": "..."}, ...]}
    """
    items: list[UniversityInput] = []

    if payload.universities:
        items = payload.universities
    elif payload.name:
        items = [UniversityInput(name=payload.name, province=payload.province, website=payload.website)]
    else:
        return JSONResponse(
            status_code=422,
            content={"detail": "Provide 'name' for a single university or 'universities' array for bulk."},
        )

    existing_names = await _get_existing_university_names()
    added = 0
    skipped = 0

    for item in items:
        name = item.name.strip()
        if not name:
            skipped += 1
            continue
        if name.lower() in existing_names:
            skipped += 1
            continue
        await add_university(
            name=name,
            province=item.province.strip() if item.province else None,
            website=item.website.strip() if item.website else None,
        )
        existing_names.add(name.lower())
        added += 1

    return {"added": added, "skipped": skipped}


# ---------------------------------------------------------------------------
# University import
# ---------------------------------------------------------------------------

# Column name aliases — maps various user-facing names to our internal fields.
_COLUMN_ALIASES: dict[str, str] = {
    # name
    "name": "name", "nama": "name", "nama universitas": "name",
    "nama_universitas": "name", "university": "name", "university name": "name",
    "university_name": "name", "institusi": "name", "perguruan tinggi": "name",
    # province
    "province": "province", "provinsi": "province", "prov": "province",
    # website
    "website": "website", "web": "website", "url": "website",
    "situs": "website", "situs web": "website", "laman": "website",
}


def _normalize_headers(raw_headers: list[str]) -> dict[int, str]:
    """Map column indices to internal field names using aliases.

    Returns {column_index: internal_field_name} for recognized columns.
    If no 'name' column is found, assumes the first column is 'name'.
    """
    mapping: dict[int, str] = {}
    found_name = False
    for i, h in enumerate(raw_headers):
        key = h.strip().lower()
        if key in _COLUMN_ALIASES:
            field = _COLUMN_ALIASES[key]
            if field not in mapping.values():  # first match wins
                mapping[i] = field
                if field == "name":
                    found_name = True
    # Fallback: if no name column found, treat column 0 as name
    if not found_name and raw_headers:
        mapping[0] = "name"
    return mapping


@app.post("/universities/import")
async def import_universities(file: UploadFile = FastAPIFile(...)):
    """Import universities from CSV or Excel (.xlsx) file.

    Recognizes flexible column names (e.g. 'nama', 'provinsi', 'web').
    If there's only one column or no header match, the first column is treated as university name.
    """
    import os

    content = await file.read()
    filename = file.filename or "upload.csv"
    ext = os.path.splitext(filename)[1].lower()

    rows_data: list[dict[str, str]] = []

    if ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return JSONResponse(status_code=400, content={"detail": "Excel file has no active sheet"})
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not header_row:
            return JSONResponse(status_code=400, content={"detail": "Excel file has no header row"})
        raw_headers = [str(h).strip() if h else "" for h in header_row]
        col_map = _normalize_headers(raw_headers)
        for row in ws.iter_rows(min_row=2, values_only=True):
            row_dict: dict[str, str] = {}
            for i, val in enumerate(row):
                if i in col_map and val is not None:
                    row_dict[col_map[i]] = str(val).strip()
            rows_data.append(row_dict)
        wb.close()
    else:
        # Default: CSV
        text = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        # Normalize CSV headers
        raw_headers = reader.fieldnames or []
        col_map = _normalize_headers(list(raw_headers))
        # Build reverse: original_header -> internal_field
        header_to_field = {raw_headers[i]: field for i, field in col_map.items() if i < len(raw_headers)}
        for row in reader:
            row_dict: dict[str, str] = {}
            for orig_header, field in header_to_field.items():
                val = row.get(orig_header, "")
                if val:
                    row_dict[field] = val.strip()
            rows_data.append(row_dict)

    existing_names = await _get_existing_university_names()
    imported = 0
    skipped = 0

    for row in rows_data:
        name = row.get("name", "").strip()
        if not name:
            continue
        if name.lower() in existing_names:
            skipped += 1
            continue
        await add_university(
            name=name,
            province=row.get("province", "").strip() or None,
            website=row.get("website", "").strip() or None,
        )
        existing_names.add(name.lower())
        imported += 1

    return {"imported": imported, "skipped": skipped}


# ---------------------------------------------------------------------------
# University detail endpoints
# ---------------------------------------------------------------------------

@app.get("/universities/{university_id}")
async def get_university(university_id: int):
    """Get a single university by ID."""
    uni = await get_university_by_id(university_id)
    if not uni:
        return JSONResponse(status_code=404, content={"detail": "University not found"})
    return uni


@app.get("/universities/{university_id}/contacts")
async def get_university_contacts(university_id: int):
    """Get IG contacts for a university."""
    return await get_contacts_for_university(university_id)


@app.get("/universities/{university_id}/posts")
async def get_university_posts(university_id: int):
    """Get IG posts for a university."""
    return await get_posts_for_university(university_id)


# ---------------------------------------------------------------------------
# Conversations endpoints
# ---------------------------------------------------------------------------

@app.get("/conversations")
async def list_conversations(
    state: str | None = None,
    university_id: int | None = None,
    is_test: bool | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List conversations with optional filters."""
    return await get_conversations_filtered(state, university_id, is_test, limit, offset)


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int):
    """Get a single conversation by ID."""
    conv = await get_conversation_by_id(conversation_id)
    if not conv:
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})
    return conv


class TestConversationPayload(BaseModel):
    phone: str
    university_name: str = "Universitas Test"
    force: bool = False


@app.post("/conversations/test")
async def start_test_conversation(payload: TestConversationPayload):
    """Start a test conversation for internal roleplay testing.

    Creates a real conversation record so incoming webhook replies
    are processed through the normal AI pipeline.
    """
    phone = validate_phone(payload.phone)
    if not phone:
        return JSONResponse(
            status_code=422,
            content={"detail": f"Invalid phone number: {payload.phone}"},
        )

    # Check for existing active conversation on this phone
    existing = await get_conversation_by_phone(phone)
    if existing and existing["state"] not in _TERMINAL_STATES:
        if payload.force:
            # Abandon the old conversation so we can start fresh
            await update_conversation_state(existing["id"], ConvState.ABANDONED)
            log.info("Force-abandoned existing conversation %d for test", existing["id"])
        else:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": f"Active conversation already exists for {phone}",
                    "existing_id": existing["id"],
                    "existing_state": existing["state"],
                },
            )

    # Generate initial message
    try:
        message = await conversation_manager.generate_initial_message(
            university_name=payload.university_name
        )
    except Exception as e:
        log.error("Failed to generate test initial message: %s", e)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to generate message: {e}"},
        )

    # Create conversation with is_test=True, university_id=None
    from datetime import datetime as _dt, timezone as _tz

    conv_id = await create_conversation(None, phone, is_test=True)

    # Enqueue via message queue
    await message_queue.enqueue_send(phone, message)

    # Update state and record message
    await update_conversation_state(
        conv_id,
        ConvState.INITIAL_SENT,
        last_message_at=_dt.now(_tz.utc).isoformat(),
    )
    await add_message_to_history(conv_id, "bot", message)

    log.info("Test conversation %d started for %s (%s)", conv_id, phone, payload.university_name)

    return {
        "id": conv_id,
        "phone": phone,
        "message": message,
        "state": ConvState.INITIAL_SENT,
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/export/csv")
async def export_csv():
    """Export all universities with contacts as CSV."""
    universities = await get_all_universities(limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "province", "website", "ig_handle", "status", "secretariat_phone", "created_at"])

    for uni in universities:
        writer.writerow([
            uni["id"], uni["name"], uni.get("province", ""),
            uni.get("website", ""), uni.get("ig_handle", ""),
            uni["status"], uni.get("secretariat_phone", ""),
            uni.get("created_at", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=universities_export.csv"},
    )


# ---------------------------------------------------------------------------
# Pipeline triggers (manual) — 3 independent agents
# ---------------------------------------------------------------------------

@app.post("/pipeline/find-ig-handles")
async def trigger_find_ig_handles(background_tasks: BackgroundTasks, limit: int = 50):
    """Agent 1: Search IG handles for universities in 'pending' status."""
    background_tasks.add_task(run_agent_in_thread, run_handle_search_batch, limit)
    return {"status": "started", "message": f"Agent 1: searching IG handles for up to {limit} universities"}


@app.post("/pipeline/scrape-ig-posts")
async def trigger_scrape_ig_posts(background_tasks: BackgroundTasks, limit: int = 20):
    """Agent 2: Scrape IG posts for universities in 'ig_found' status."""
    background_tasks.add_task(run_agent_in_thread, run_post_scrape_batch, limit)
    return {"status": "started", "message": f"Agent 2: scraping posts for up to {limit} universities"}


@app.post("/pipeline/extract-phones")
async def trigger_extract_phones(background_tasks: BackgroundTasks, limit: int = 50):
    """Agent 3: Extract phones from unprocessed ig_posts."""
    background_tasks.add_task(run_agent_in_thread, run_phone_extraction_batch, limit)
    return {"status": "started", "message": f"Agent 3: extracting phones from up to {limit} posts"}


@app.get("/pipeline/status")
async def pipeline_status():
    """Return a breakdown of all pipeline stages."""
    return await get_pipeline_status()


# ---------------------------------------------------------------------------
# Outreach triggers (manual)
# ---------------------------------------------------------------------------

@app.post("/outreach/start")
async def trigger_outreach(background_tasks: BackgroundTasks):
    """Manually trigger the outreach loop."""
    background_tasks.add_task(daily_outreach_loop)
    return {"status": "started", "message": "Outreach loop triggered"}


@app.post("/outreach/process-followups")
async def trigger_followups(background_tasks: BackgroundTasks):
    """Manually trigger follow-up processing."""
    background_tasks.add_task(process_followups)
    return {"status": "started", "message": "Follow-up processing triggered"}


# ---------------------------------------------------------------------------
# Pause / Resume control
# ---------------------------------------------------------------------------

@app.post("/control/pause")
async def pause_bot():
    """Pause automated outreach and auto-replies."""
    set_paused(True)
    log.info("Bot PAUSED by operator")
    return {"paused": True}


@app.post("/control/resume")
async def resume_bot():
    """Resume automated outreach and auto-replies."""
    set_paused(False)
    log.info("Bot RESUMED by operator")
    return {"paused": False}


@app.get("/control/status")
async def control_status():
    """Return current pause state and chatbot toggles."""
    return {
        "paused": is_paused(),
        "chatbot_enabled": cfg.CHATBOT_ENABLED,
        "audiensi_enabled": cfg.AUDIENSI_ENABLED,
    }


class ChatbotTogglePayload(BaseModel):
    enabled: bool


@app.post("/control/chatbot/{chatbot_type}")
async def toggle_chatbot(chatbot_type: str, payload: ChatbotTogglePayload):
    """Toggle a chatbot on/off. Type: 'agent' or 'audiensi'."""
    if chatbot_type == "agent":
        cfg.set("CHATBOT_ENABLED", payload.enabled)
        db_val = "true" if payload.enabled else "false"
        await upsert_config("CHATBOT_ENABLED", db_val)
        log.info("Contact finder chatbot %s", "ENABLED" if payload.enabled else "DISABLED")
        return {"chatbot_enabled": payload.enabled}
    elif chatbot_type == "audiensi":
        cfg.set("AUDIENSI_ENABLED", payload.enabled)
        db_val = "true" if payload.enabled else "false"
        await upsert_config("AUDIENSI_ENABLED", db_val)
        log.info("Audiensi chatbot %s", "ENABLED" if payload.enabled else "DISABLED")
        return {"audiensi_enabled": payload.enabled}
    else:
        return JSONResponse(
            status_code=422,
            content={"detail": "chatbot_type must be 'agent' or 'audiensi'"},
        )


# ---------------------------------------------------------------------------
# Learning endpoints
# ---------------------------------------------------------------------------

@app.get("/learning/lessons")
async def list_lessons():
    """Return all active lessons."""
    lessons = await get_all_active_lessons()
    return {"lessons": lessons, "total": len(lessons)}


@app.get("/learning/analyses")
async def list_analyses(limit: int = 50):
    """Return unprocessed analyses."""
    analyses = await get_unprocessed_analyses(limit=limit)
    return {"analyses": analyses, "total": len(analyses)}


@app.get("/learning/stats")
async def learning_stats():
    """Return summary statistics for the learning system."""
    lessons = await get_all_active_lessons()
    analyses = await get_unprocessed_analyses(limit=1000)

    # Count lessons by situation_type
    situation_counts: dict[str, int] = {}
    for lesson in lessons:
        sit = lesson.get("situation_type", "unknown")
        situation_counts[sit] = situation_counts.get(sit, 0) + 1

    return {
        "total_active_lessons": len(lessons),
        "unprocessed_analyses": len(analyses),
        "lessons_by_situation": situation_counts,
    }


@app.post("/learning/trigger-reflection")
async def trigger_reflection(background_tasks: BackgroundTasks):
    """Trigger a reflection cycle in the background."""
    background_tasks.add_task(learning_system.run_reflection)
    return {"status": "started", "message": "Reflection triggered"}


# ---------------------------------------------------------------------------
# WhatsApp management endpoints (proxy to WA service)
# ---------------------------------------------------------------------------

class TestMessagePayload(BaseModel):
    to: str
    message: str


@app.get("/wa/qr")
async def wa_qr():
    """Get current QR code for WhatsApp authentication."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WA_SERVICE_URL}/qr")
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"WA service unavailable: {e}", "connected": False},
        )


@app.get("/wa/status")
async def wa_status():
    """Get detailed WhatsApp connection status."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WA_SERVICE_URL}/status")
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"WA service unavailable: {e}", "connected": False},
        )


@app.post("/wa/send-test")
async def wa_send_test(payload: TestMessagePayload):
    """Send a test WhatsApp message."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{WA_SERVICE_URL}/send",
                json={"to": payload.to, "message": payload.message},
            )
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"WA service unavailable: {e}"},
        )


@app.post("/wa/logout")
async def wa_logout():
    """Logout from WhatsApp and clear auth session."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{WA_SERVICE_URL}/logout")
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"WA service unavailable: {e}"},
        )


@app.post("/wa/restart")
async def wa_restart():
    """Restart WhatsApp connection."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{WA_SERVICE_URL}/restart")
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"WA service unavailable: {e}"},
        )


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------


_CHAT_MODEL_EXCLUDE = {"audio", "realtime", "tts", "transcribe", "image", "instruct", "search", "diarize", "codex", "deep-research"}


@app.get("/config/models")
async def list_openai_models():
    """Fetch chat-completion-capable models from OpenAI."""
    from openai import AsyncOpenAI

    api_key = cfg.OPENAI_API_KEY
    if not api_key:
        return {"models": []}

    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.models.list()
        models: list[str] = []
        for m in response.data:
            mid = m.id
            # Only gpt / o-series models
            if not (mid.startswith("gpt-") or mid.startswith("o1") or mid.startswith("o3") or mid.startswith("o4")):
                continue
            # Skip fine-tuned
            if mid.startswith("ft:"):
                continue
            # Skip non-chat models (audio, image, realtime, etc.)
            if any(excl in mid for excl in _CHAT_MODEL_EXCLUDE):
                continue
            models.append(mid)
        models.sort()
        return {"models": models}
    except Exception as e:
        log.warning("Failed to list OpenAI models: %s", e)
        return {"models": [], "error": str(e)}


def _mask_value(value: str) -> str:
    """Mask a sensitive string — short fixed-width prefix + last 4 chars."""
    s = str(value)
    if not s:
        return ""
    if len(s) <= 8:
        return "\u2022" * len(s)
    return "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022" + s[-4:]


@app.get("/config")
async def get_config():
    """Return all dynamic settings with metadata."""
    current = cfg.get_all()
    settings = []
    for defn in CONFIG_DEFINITIONS:
        raw_value = current.get(defn.key, defn.default)
        display_value = _mask_value(raw_value) if defn.sensitive and raw_value else raw_value
        settings.append({
            "key": defn.key,
            "value": display_value,
            "default": "" if defn.sensitive else defn.default,
            "type": defn.type.value,
            "group": defn.group.value,
            "label": defn.label,
            "description": defn.description,
            "min_value": defn.min_value,
            "max_value": defn.max_value,
            "sensitive": defn.sensitive,
            "has_value": bool(raw_value) if defn.sensitive else None,
        })
    return {"settings": settings}


class ConfigUpdatePayload(BaseModel):
    settings: dict[str, Any]


def _validate_config_value(key: str, value: Any) -> tuple[Any, str | None]:
    """Validate and coerce a config value. Returns (coerced_value, error_or_None)."""
    defn = CONFIG_DEFINITIONS_MAP.get(key)
    if defn is None:
        return None, f"Unknown config key: {key}"

    try:
        if defn.type == ConfigType.INT:
            coerced = int(value)
        elif defn.type == ConfigType.FLOAT:
            coerced = float(value)
        elif defn.type == ConfigType.BOOL:
            if isinstance(value, bool):
                coerced = value
            elif isinstance(value, str):
                coerced = value.lower() in ("true", "1", "yes")
            else:
                coerced = bool(value)
        else:
            coerced = str(value)
    except (ValueError, TypeError):
        return None, f"Invalid type for {key}: expected {defn.type.value}"

    if defn.min_value is not None and isinstance(coerced, (int, float)):
        if coerced < defn.min_value:
            return None, f"{key} must be >= {defn.min_value}"
    if defn.max_value is not None and isinstance(coerced, (int, float)):
        if coerced > defn.max_value:
            return None, f"{key} must be <= {defn.max_value}"

    return coerced, None


@app.patch("/config")
async def update_config(payload: ConfigUpdatePayload):
    """Update one or more config settings. Validates, persists to DB, and updates in-memory."""
    errors: dict[str, str] = {}
    validated: dict[str, Any] = {}

    for key, value in payload.settings.items():
        coerced, err = _validate_config_value(key, value)
        if err:
            errors[key] = err
        else:
            validated[key] = coerced

    if errors:
        return JSONResponse(status_code=422, content={"errors": errors})

    for key, coerced in validated.items():
        # Persist to DB as string
        if isinstance(coerced, bool):
            db_value = "true" if coerced else "false"
        else:
            db_value = str(coerced)
        await upsert_config(key, db_value)
        cfg.set(key, coerced)

    # Reschedule outreach jobs if hours changed
    if "OUTREACH_START_HOUR" in validated or "OUTREACH_END_HOUR" in validated:
        try:
            from orchestrator.scheduler import reschedule_outreach_jobs
            reschedule_outreach_jobs()
        except Exception as e:
            log.warning("Failed to reschedule outreach jobs: %s", e)

    # Invalidate Responses API sessions if custom instructions changed
    instruction_keys = {"AGENT_CUSTOM_INSTRUCTIONS", "AUDIENSI_CUSTOM_INSTRUCTIONS"}
    if instruction_keys & set(validated.keys()):
        await clear_all_response_ids("conversations")
        await clear_all_response_ids("audiensi_conversations")

    return {"status": "ok", "updated": list(validated.keys())}


@app.delete("/config/{key}")
async def reset_config(key: str):
    """Reset a config key to its default value."""
    defn = CONFIG_DEFINITIONS_MAP.get(key)
    if defn is None:
        return JSONResponse(status_code=404, content={"detail": f"Unknown config key: {key}"})

    await db_delete_config(key)
    cfg.set(key, defn.default)

    return {"status": "ok", "key": key, "value": defn.default}


# ---------------------------------------------------------------------------
# Knowledge Items CRUD
# ---------------------------------------------------------------------------


class KnowledgeItemPayload(BaseModel):
    chatbot_type: str  # 'agent' | 'audiensi'
    title: str
    content: str
    situation_tags: str = ""
    trigger_keywords: str = ""


class KnowledgeItemUpdatePayload(BaseModel):
    title: str | None = None
    content: str | None = None
    is_active: bool | None = None
    situation_tags: str | None = None
    trigger_keywords: str | None = None


@app.get("/knowledge-items")
async def list_knowledge_items(chatbot_type: str | None = None):
    """List knowledge items, optionally filtered by chatbot_type."""
    items = await get_knowledge_items(chatbot_type)
    return {"items": items}


@app.post("/knowledge-items")
async def create_knowledge_item_endpoint(payload: KnowledgeItemPayload):
    """Create a new knowledge item."""
    if payload.chatbot_type not in ("agent", "audiensi"):
        return JSONResponse(
            status_code=422,
            content={"detail": "chatbot_type must be 'agent' or 'audiensi'"},
        )
    item_id = await create_knowledge_item(
        payload.chatbot_type, payload.title, payload.content,
        situation_tags=payload.situation_tags,
        trigger_keywords=payload.trigger_keywords,
    )
    # Invalidate Responses API sessions — knowledge base changed
    await clear_all_response_ids("conversations")
    await clear_all_response_ids("audiensi_conversations")
    return {"id": item_id, "status": "ok"}


@app.patch("/knowledge-items/{item_id}")
async def update_knowledge_item_endpoint(item_id: int, payload: KnowledgeItemUpdatePayload):
    """Update a knowledge item."""
    updates = {}
    if payload.title is not None:
        updates["title"] = payload.title
    if payload.content is not None:
        updates["content"] = payload.content
    if payload.is_active is not None:
        updates["is_active"] = int(payload.is_active)
    if payload.situation_tags is not None:
        updates["situation_tags"] = payload.situation_tags
    if payload.trigger_keywords is not None:
        updates["trigger_keywords"] = payload.trigger_keywords
    if not updates:
        return JSONResponse(status_code=422, content={"detail": "No fields to update"})
    await update_knowledge_item(item_id, **updates)
    # Invalidate Responses API sessions — knowledge base changed
    await clear_all_response_ids("conversations")
    await clear_all_response_ids("audiensi_conversations")
    return {"status": "ok"}


@app.delete("/knowledge-items/{item_id}")
async def delete_knowledge_item_endpoint(item_id: int):
    """Delete a knowledge item."""
    await delete_knowledge_item(item_id)
    # Invalidate Responses API sessions — knowledge base changed
    await clear_all_response_ids("conversations")
    await clear_all_response_ids("audiensi_conversations")
    return {"status": "ok"}


_ALLOWED_KB_EXTENSIONS = {".txt", ".md", ".csv", ".docx", ".pdf"}


def _extract_text_from_file(filename: str, content: bytes) -> str:
    """Extract plain text from an uploaded file."""
    import os
    ext = os.path.splitext(filename)[1].lower()

    if ext in (".txt", ".md"):
        return content.decode("utf-8", errors="replace")

    if ext == ".csv":
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        lines = []
        for row in reader:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    if ext == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if ext == ".pdf":
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(content))
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n".join(pages)
        except ImportError:
            raise ValueError("PDF support requires PyPDF2. Install with: pip install PyPDF2")

    raise ValueError(f"Unsupported file type: {ext}")


@app.post("/knowledge-items/upload")
async def upload_knowledge_item(
    file: UploadFile = FastAPIFile(...),
    chatbot_type: str = Form(...),
):
    """Upload a file (.txt, .md, .csv, .docx, .pdf) as a knowledge item."""
    import os

    if chatbot_type not in ("agent", "audiensi"):
        return JSONResponse(
            status_code=422,
            content={"detail": "chatbot_type must be 'agent' or 'audiensi'"},
        )

    if not file.filename:
        return JSONResponse(status_code=400, content={"detail": "No filename provided"})

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _ALLOWED_KB_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Unsupported file type: {ext}. Allowed: {', '.join(_ALLOWED_KB_EXTENSIONS)}"},
        )

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:  # 5MB limit
        return JSONResponse(status_code=400, content={"detail": "File too large (max 5MB)"})

    try:
        text = _extract_text_from_file(file.filename, raw)
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": f"Failed to extract text: {e}"})

    if not text.strip():
        return JSONResponse(status_code=400, content={"detail": "File contains no extractable text"})

    title = os.path.splitext(file.filename)[0]
    item_id = await create_knowledge_item(chatbot_type, title, text.strip())

    return {"id": item_id, "status": "ok", "title": title, "content_length": len(text.strip())}


# ---------------------------------------------------------------------------
# API Call Logs
# ---------------------------------------------------------------------------


@app.get("/api-logs")
async def list_api_logs(
    chatbot_type: str | None = None,
    conversation_id: int | None = None,
    call_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List API call logs with optional filters and pagination."""
    logs = await get_api_call_logs(chatbot_type, conversation_id, call_type, limit, offset)
    return {"logs": logs}


@app.get("/api-logs/{log_id}")
async def get_api_log(log_id: int):
    """Get full detail of a single API call log."""
    log_entry = await get_api_call_log_by_id(log_id)
    if not log_entry:
        return JSONResponse(status_code=404, content={"detail": "API log not found"})
    return log_entry


# ---------------------------------------------------------------------------
# Audiensi endpoints
# ---------------------------------------------------------------------------


@app.get("/audiensi")
async def list_audiensi(
    state: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List audiensi conversations with optional state filter."""
    from orchestrator.db import get_audiensi_conversations_filtered
    return await get_audiensi_conversations_filtered(state, limit, offset)


@app.get("/audiensi/queue")
async def audiensi_queue():
    """Get pending approval queue."""
    from orchestrator.db import get_queued_audiensi
    return await get_queued_audiensi()


@app.get("/audiensi/stats")
async def audiensi_stats():
    """Get audiensi dashboard stats."""
    from orchestrator.db import get_audiensi_stats
    return await get_audiensi_stats()


@app.get("/audiensi/{aud_id}")
async def get_audiensi(aud_id: int):
    """Get a single audiensi conversation by ID."""
    from orchestrator.db import get_audiensi_conversation_by_id
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    return aud


class RectorNamePayload(BaseModel):
    rector_name: str


@app.put("/audiensi/{aud_id}/rector-name")
async def update_audiensi_rector_name(aud_id: int, payload: RectorNamePayload):
    """Edit rector name for an audiensi conversation."""
    from orchestrator.db import get_audiensi_conversation_by_id, update_audiensi_state, update_university_rector_name
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    await update_audiensi_state(aud_id, aud["state"], rector_name=payload.rector_name)
    # Also update university record
    if aud.get("university_id"):
        await update_university_rector_name(aud["university_id"], payload.rector_name)
    return {"status": "ok"}


class InitialMessagePayload(BaseModel):
    message: str


@app.put("/audiensi/{aud_id}/initial-message")
async def update_audiensi_initial_message(aud_id: int, payload: InitialMessagePayload):
    """Edit initial message draft."""
    from orchestrator.db import get_audiensi_conversation_by_id, update_audiensi_state
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    await update_audiensi_state(aud_id, aud["state"], initial_message_draft=payload.message)
    return {"status": "ok"}


@app.post("/audiensi/{aud_id}/regenerate-pdf")
async def regenerate_audiensi_pdf(aud_id: int):
    """Regenerate PDF after edits (rector name, etc.)."""
    from orchestrator.db import get_audiensi_conversation_by_id, update_audiensi_state
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})

    try:
        from orchestrator.audiensi.pdf_generator import generate_audiensi_document
        pdf_path = await generate_audiensi_document(
            audiensi_id=aud_id,
            university_name=aud.get("university_name", ""),
            rector_name=aud.get("rector_name"),
            province=aud.get("province"),
        )
        if pdf_path:
            await update_audiensi_state(aud_id, aud["state"], pdf_path=pdf_path)
        return {"status": "ok", "pdf_path": pdf_path}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"PDF generation failed: {e}"})


@app.get("/audiensi/{aud_id}/pdf")
async def get_audiensi_pdf(aud_id: int):
    """Download/preview the generated PDF."""
    from orchestrator.db import get_audiensi_conversation_by_id
    import os
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud or not aud.get("pdf_path"):
        return JSONResponse(status_code=404, content={"detail": "PDF not found"})
    pdf_path = aud["pdf_path"]
    if not os.path.exists(pdf_path):
        return JSONResponse(status_code=404, content={"detail": "PDF file not found on disk"})
    from fastapi.responses import FileResponse
    filename = os.path.basename(pdf_path)
    return FileResponse(pdf_path, filename=filename, media_type="application/octet-stream")


@app.post("/audiensi/{aud_id}/approve")
async def approve_audiensi(aud_id: int, background_tasks: BackgroundTasks):
    """Approve audiensi & send initial message + document."""
    from orchestrator.db import (
        get_audiensi_conversation_by_id,
        update_audiensi_state,
        add_audiensi_message,
    )
    from datetime import datetime as _dt, timezone as _tz

    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    if aud["state"] != "QUEUED":
        return JSONResponse(status_code=400, content={"detail": f"Cannot approve: state is {aud['state']}"})

    # Update state to APPROVED
    now = _dt.now(_tz.utc).isoformat()
    await update_audiensi_state(aud_id, "APPROVED", approved_at=now)

    # Send document first (if available), then text message
    async def _send_messages():
        phone = aud["contact_phone"]
        uni_name = aud.get("university_name", "University")

        # 1. Send PDF/document if available
        if aud.get("pdf_path"):
            import os
            if os.path.exists(aud["pdf_path"]):
                doc_name = f"Undangan_Audiensi_{uni_name.replace(' ', '_')}.docx"
                await message_queue.enqueue_send_document(
                    phone, aud["pdf_path"], doc_name,
                    caption="Surat Undangan Audiensi Daring - Asosiasi AI Indonesia",
                )

        # 2. Send text message
        text = aud.get("initial_message_draft") or (
            f"Selamat pagi,\n\n"
            f"Saya Ali dari Asosiasi Artificial Intelligence Indonesia.\n"
            f"Kami telah mengirimkan surat undangan audiensi daring Zoom untuk {uni_name}.\n"
            f"Mohon kesediaannya untuk menjadwalkan pertemuan ~40 menit.\n\n"
            f"Terima kasih 🙏🏻"
        )
        await message_queue.enqueue_send(phone, text)

        # Update state to INITIAL_SENT
        await update_audiensi_state(
            aud_id, "INITIAL_SENT",
            last_message_at=_dt.now(_tz.utc).isoformat(),
        )
        await add_audiensi_message(aud_id, "bot", text)

    background_tasks.add_task(_send_messages)
    return {"status": "ok", "message": "Audiensi approved, messages being sent"}


@app.post("/audiensi/{aud_id}/reject")
async def reject_audiensi(aud_id: int):
    """Reject/cancel an audiensi."""
    from orchestrator.db import get_audiensi_conversation_by_id, update_audiensi_state
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    await update_audiensi_state(aud_id, "ABANDONED")
    return {"status": "ok"}


@app.post("/audiensi/{aud_id}/send-zoom")
async def send_zoom_link(aud_id: int, background_tasks: BackgroundTasks):
    """Manually send zoom link for a scheduled audiensi."""
    from orchestrator.db import (
        get_audiensi_conversation_by_id,
        update_audiensi_state,
        add_audiensi_message,
    )
    from datetime import datetime as _dt, timezone as _tz

    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})

    zoom_link = cfg.AUDIENSI_ZOOM_LINK_TEMPLATE or "https://zoom.us/j/placeholder"

    async def _send():
        phone = aud["contact_phone"]
        msg = f"Berikut link Zoom untuk audiensi:\n\n{zoom_link}\n\nTerima kasih 🙏🏻"
        await message_queue.enqueue_send(phone, msg)
        await update_audiensi_state(
            aud_id, "ZOOM_SENT",
            zoom_link=zoom_link,
            last_message_at=_dt.now(_tz.utc).isoformat(),
        )
        await add_audiensi_message(aud_id, "bot", msg)

    background_tasks.add_task(_send)
    return {"status": "ok", "zoom_link": zoom_link}


# Audiensi template management

@app.post("/audiensi/template/upload")
async def upload_audiensi_template(file: UploadFile = FastAPIFile(...)):
    """Upload a new .docx template for audiensi invitations."""
    if not file.filename or not file.filename.endswith(".docx"):
        return JSONResponse(status_code=400, content={"detail": "Only .docx files allowed"})
    content = await file.read()
    try:
        from orchestrator.audiensi.pdf_generator import save_uploaded_template
        path = await save_uploaded_template(content, file.filename)
        return {"status": "ok", "path": path}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/audiensi/template/placeholders")
async def audiensi_template_placeholders():
    """List available template placeholders."""
    from orchestrator.audiensi.pdf_generator import get_available_placeholders
    return {"placeholders": get_available_placeholders()}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check endpoint."""
    from orchestrator.instagram import get_ig_session_status

    # Check WA service connectivity
    wa_status = {"connected": False}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{WA_SERVICE_URL}/status")
            wa_status = resp.json()
    except Exception:
        pass

    return {
        "status": "ok",
        "whatsapp": wa_status,
        "instagram": get_ig_session_status(),
    }
