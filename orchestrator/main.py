"""
FastAPI orchestrator - main server that ties everything together.
Run: uvicorn orchestrator.main:app --port 8000 --reload
"""
import asyncio
import csv
import io
import json as _json
import functools
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

# Dedicated thread-pool for long-running Playwright operations so they
# don't starve the default executor used by normal request handlers.
_pw_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pw-login")

import httpx
from fastapi import FastAPI, BackgroundTasks, UploadFile, File as FastAPIFile, Form, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from orchestrator.config import WA_SERVICE_URL, WEBHOOK_URL, log, is_paused, set_paused, cfg
from orchestrator.websocket import manager as ws_manager
from orchestrator.db import (
    init_db,
    get_dashboard_stats,
    get_universities_by_status,
    get_all_universities,
    list_universities_paginated,
    export_universities_filtered,
    export_universities_by_ids,
    export_contacts_filtered,
    match_university_names,
    get_university_provinces,
    toggle_university_enabled,
    bulk_toggle_universities_enabled,
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
    get_audiensi_conversation_by_phone,
    update_audiensi_state,
    create_pipeline_log,
    complete_pipeline_log,
    get_pipeline_logs,
    get_pipeline_log_by_id,
    cleanup_old_pipeline_logs,
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
from orchestrator.agents.ig_handle_finder import run_handle_search_batch, run_handle_search_for_universities
from orchestrator.agents.ig_post_scraper import run_post_scrape_batch, run_post_scrape_for_universities
from orchestrator.agents.ig_phone_extractor import run_phone_extraction_batch, run_phone_extraction_for_universities
from orchestrator.agents.bem_finder import run_bem_discovery_batch, run_bem_discovery_for_universities
from orchestrator.config import PROVINCES

learning_system = LearningSystem()

_TERMINAL_STATES = {"GOT_NUMBER", "REFUSED", "ABANDONED"}
_AUDIENSI_TERMINAL_STATES = {"ZOOM_SENT", "REFUSED", "ABANDONED"}

# ---------------------------------------------------------------------------
# Per-phone concurrency lock (prevents race conditions from overlapping
# debounce windows delivering two messages for the same phone concurrently)
# ---------------------------------------------------------------------------

_phone_locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
_phone_locks_guard = asyncio.Lock()
_MAX_PHONE_LOCKS = 5000


async def _get_phone_lock(phone: str) -> asyncio.Lock:
    """Return an asyncio.Lock for *phone*, creating one if needed.

    Uses an LRU strategy: the most-recently-used lock is moved to the end
    of the OrderedDict.  When the dict exceeds ``_MAX_PHONE_LOCKS`` entries
    the oldest (least-recently-used) entry is evicted.
    """
    async with _phone_locks_guard:
        if phone in _phone_locks:
            _phone_locks.move_to_end(phone)
            return _phone_locks[phone]
        if len(_phone_locks) >= _MAX_PHONE_LOCKS:
            _phone_locks.popitem(last=False)  # evict oldest
        lock = asyncio.Lock()
        _phone_locks[phone] = lock
        return lock


# ---------------------------------------------------------------------------
# Periodic IG session health check (lightweight — no browser launch)
# ---------------------------------------------------------------------------

_IG_HEALTH_INTERVAL = 300  # 5 minutes

async def _periodic_ig_health_check():
    """
    Background task: log IG account pool status every 5 minutes.
    Uses existing in-memory pool state (login_ok, healthy, last_error)
    that is updated by actual scraping operations & login flows —
    does NOT launch browsers.
    """
    await asyncio.sleep(60)  # initial delay — let everything boot
    while True:
        try:
            from orchestrator.playwright_ig import _account_pool
            pool = _account_pool.status()
            total = len(pool)
            healthy = sum(1 for a in pool if a["healthy"])
            if total > 0 and healthy < total:
                log.warning(
                    "[IGHealthCheck] %d/%d accounts healthy — %s",
                    healthy, total,
                    ", ".join(
                        f"@{a['username']}={a.get('last_error', 'unhealthy')}"
                        for a in pool if not a["healthy"]
                    ),
                )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.error("[IGHealthCheck] Error: %s", exc, exc_info=True)

        await asyncio.sleep(_IG_HEALTH_INTERVAL)


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

    # Cleanup old pipeline logs (keep 30 days)
    try:
        deleted = await cleanup_old_pipeline_logs(days=30)
        if deleted:
            log.info("Cleaned up %d old pipeline logs", deleted)
    except Exception as e:
        log.warning("Failed to cleanup old pipeline logs: %s", e)

    # Register webhook with WA service
    await register_webhook()

    # Start message queue send worker
    worker_task = asyncio.create_task(message_queue.send_worker())

    # Start periodic IG session health checker (every 5 min)
    ig_health_task = asyncio.create_task(_periodic_ig_health_check())

    # Start scheduler
    setup_scheduler()
    log.info("Orchestrator started on port 8000")

    yield

    # Cancel background tasks
    ig_health_task.cancel()
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


# ---------------------------------------------------------------------------
# WebSocket endpoint for real-time notifications
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates to the frontend."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive with heartbeat
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        log.warning(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


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

    # Acquire per-phone lock to prevent concurrent processing of messages
    # from the same phone number (avoids duplicate responses & state corruption).
    lock = await _get_phone_lock(normalized_phone)
    async with lock:
        # Try audiensi chatbot first (phase 2 conversations)
        if cfg.AUDIENSI_ENABLED:
            try:
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
                # Send error message to the contact instead of falling through to chatbot 1
                await message_queue.enqueue_send(
                    raw_phone,
                    "Mohon maaf, ada kendala teknis. Kami akan menghubungi Anda kembali.",
                    reply_to_msg_key=msg_key, all_msg_keys=all_msg_keys,
                )
                return

        # Default: chatbot 1 (contact finder)
        if not cfg.CHATBOT_ENABLED:
            log.info(f"Contact finder chatbot disabled – ignoring message from {raw_phone}")
            return

        try:
            log.info(f"Processing message from {raw_phone} with AI (model: {cfg.AGENT_MODEL})...")
            result = await message_queue.process_with_ai(
                conversation_manager.process_incoming_message(
                    normalized_phone, message, push_name=push_name,
                )
            )
            log.info(f"AI processing done for {raw_phone}: action={result.get('action')}")
        except Exception as e:
            log.error(f"Failed to process message from {raw_phone}: {e}", exc_info=True)
            return

        if result.get("response_message"):
            await message_queue.enqueue_send(
                raw_phone, result["response_message"],
                reply_to_msg_key=msg_key, all_msg_keys=all_msg_keys,
            )
        else:
            log.warning(f"No response_message generated for {raw_phone}")

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
    province: str | None = None,
    has_ig: bool | None = None,
    enabled: bool | None = None,
    limit: int = 25,
    offset: int = 0,
):
    """List universities with combined filters and proper pagination."""
    return await list_universities_paginated(
        search=search,
        status=status,
        province=province,
        has_ig=has_ig,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )


@app.get("/universities/export-excel")
async def export_universities_excel(
    status: str | None = None,
    search: str | None = None,
    province: str | None = None,
    has_ig: bool | None = None,
    enabled: bool | None = None,
    ids: str | None = None,
):
    """Export contacts (university name, contact name, phone) as Excel (.xlsx) file.

    Simple format with only 3 columns:
    - University Name
    - Contact Name
    - Phone Number

    Pass `ids` as comma-separated IDs to export only specific universities.
    When ids is provided, other filters are ignored.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    # Parse IDs if provided
    university_ids = None
    if ids:
        university_ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]

    # Get contacts data
    rows = await export_contacts_filtered(
        search=search,
        status=status,
        province=province,
        has_ig=has_ig,
        enabled=enabled,
        university_ids=university_ids,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Contacts"

    # -- Header style --
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_fill = PatternFill(start_color="10B981", end_color="10B981", fill_type="solid")  # Green
    header_alignment = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    headers = [
        ("Nama Universitas", 50),
        ("Nama Contact", 30),
        ("No. WhatsApp", 20),
    ]

    for col_idx, (title, width) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
        ws.column_dimensions[cell.column_letter].width = width

    # -- Data rows --
    for row_idx, row in enumerate(rows, 2):
        values = [
            row.get("university_name", ""),
            row.get("contact_name", ""),
            row.get("phone_number", ""),
        ]
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val or "")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = thin_border

    # -- Auto-filter --
    ws.auto_filter.ref = f"A1:C{len(rows) + 1}"

    # -- Freeze header row --
    ws.freeze_panes = "A2"

    # Write to bytes
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"contacts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/universities/match-names")
async def match_names_endpoint(body: dict):
    """Match a list of university names to existing records.

    Body: {"names": ["Universitas Indonesia", "ITB", ...]}
    Returns: [{"id": 1, "name": "Universitas Indonesia", "matched_query": "Universitas Indonesia"}, ...]
    """
    names = body.get("names", [])
    if not names or not isinstance(names, list):
        return JSONResponse({"error": "names must be a non-empty list"}, status_code=400)
    results = await match_university_names(names)
    return {"matches": results, "total_queries": len(names), "total_matched": len(results)}


@app.get("/universities/provinces")
async def universities_provinces():
    """Return distinct province values for filter dropdown."""
    return await get_university_provinces()


@app.patch("/universities/{university_id}/toggle-enabled")
async def toggle_enabled(university_id: int, enabled: bool = True):
    """Enable or disable a single university for pipeline processing."""
    ok = await toggle_university_enabled(university_id, enabled)
    if not ok:
        return JSONResponse({"error": "University not found"}, status_code=404)
    return {"id": university_id, "enabled": enabled}


@app.patch("/universities/bulk-toggle")
async def bulk_toggle(payload: dict):
    """Enable or disable multiple universities. Body: {ids: [1,2,3], enabled: true/false}"""
    ids = payload.get("ids", [])
    enabled = payload.get("enabled", True)
    if not ids:
        return JSONResponse({"error": "ids list required"}, status_code=400)
    updated = await bulk_toggle_universities_enabled(ids, enabled)
    return {"updated": updated, "enabled": enabled}


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
        log_id = await create_pipeline_log("collect_universities", "manual")
        try:
            existing = await get_all_universities(limit=10000)
            existing_names = [u["name"] for u in existing]

            from scripts.collect_universities import is_duplicate

            universities = await search_pddikti(province, limit=limit)
            added = 0
            failed = 0
            details = []
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
                    details.append({"name": u["name"], "province": u.get("province"), "status": "added"})
                except Exception as e:
                    failed += 1
                    log.warning(f"Failed to add '{u['name']}': {e}")
            log.info(f"[PDDIKTI] Collected {added} new universities (province={province}, limit={limit})")
            await complete_pipeline_log(
                log_id,
                status="completed",
                summary={"added": added, "total_found": len(universities), "province": province},
                details=details[:100],  # Limit details to 100 entries
                items_processed=len(universities),
                items_success=added,
                items_failed=failed,
            )
            # Broadcast agent completion to frontend
            await ws_manager.broadcast_type(
                "agent_completed",
                agent="collect_universities",
                stats={"added": added, "total_found": len(universities)},
            )
        except Exception as e:
            log.error(f"[PDDIKTI] Collection failed: {e}")
            await complete_pipeline_log(log_id, status="failed", error=str(e))
            # Broadcast agent failure to frontend
            await ws_manager.broadcast_type(
                "agent_completed",
                agent="collect_universities",
                stats={"error": str(e)},
            )

    msg = f"Collecting universities from PDDIKTI"
    if province:
        msg += f" (province: {province})"
    if limit:
        msg += f" (limit: {limit})"
    background_tasks.add_task(run_agent_in_thread, _collect, province, limit)
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


@app.get("/universities/{university_id}/related-igs")
async def get_university_related_igs(university_id: int, relation_type: str | None = None):
    """Get related IG accounts (BEM, humas, etc.) for a university."""
    from orchestrator.db import get_related_igs_for_university
    return await get_related_igs_for_university(university_id, relation_type)


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
    from orchestrator.db import get_audiensi_by_source_conversation_id
    conv = await get_conversation_by_id(conversation_id)
    if not conv:
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})
    conv["linked_audiensi"] = await get_audiensi_by_source_conversation_id(conversation_id)
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

    # Also abandon any active audiensi conversation for this phone,
    # otherwise incoming replies get routed to audiensi instead of the test.
    from orchestrator.audiensi.states import AudiensiState
    existing_aud = await get_audiensi_conversation_by_phone(phone)
    if existing_aud and existing_aud["state"] not in AudiensiState.terminal_states():
        if payload.force:
            await update_audiensi_state(existing_aud["id"], "REFUSED")
            log.info("Force-abandoned existing audiensi %d for test", existing_aud["id"])
        else:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": f"Active audiensi conversation exists for {phone}",
                    "existing_audiensi_id": existing_aud["id"],
                    "existing_state": existing_aud["state"],
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

async def _run_agent_with_log(agent_fn, agent_type: str, trigger_type: str, limit: int):
    """Wrapper that creates a pipeline log, runs the agent, and records results."""
    log_id = await create_pipeline_log(agent_type, trigger_type)
    try:
        result = await agent_fn(limit)
        # Determine counts from agent result dict
        processed = 0
        success = 0
        failed = 0
        details = result.get("details", [])

        if agent_type == "find_handles":
            processed = result.get("searched", 0)
            success = result.get("found", 0)
            failed = processed - success
        elif agent_type == "scrape_posts":
            processed = result.get("scraped", 0)
            success = result.get("total_posts", 0)
            failed = 0
        elif agent_type == "extract_phones":
            processed = result.get("processed", 0)
            success = result.get("phones_found", 0)
            failed = 0

        summary = {k: v for k, v in result.items() if k != "details"}
        await complete_pipeline_log(
            log_id,
            status="completed",
            summary=summary,
            details=details[:100],
            items_processed=processed,
            items_success=success,
            items_failed=failed,
        )
        # Broadcast agent completion to frontend
        await ws_manager.broadcast_type(
            "agent_completed",
            agent=agent_type,
            stats={"processed": processed, "success": success, "failed": failed},
        )
        return result
    except Exception as e:
        log.error(f"[{agent_type}] Agent failed: {e}")
        await complete_pipeline_log(log_id, status="failed", error=str(e))
        # Broadcast agent failure to frontend
        await ws_manager.broadcast_type(
            "agent_completed",
            agent=agent_type,
            stats={"error": str(e)},
        )
        raise


@app.post("/pipeline/find-ig-handles")
async def trigger_find_ig_handles(background_tasks: BackgroundTasks, limit: int = 50):
    """Agent 1: Search IG handles for universities in 'pending' status."""
    background_tasks.add_task(
        run_agent_in_thread, _run_agent_with_log,
        run_handle_search_batch, "find_handles", "manual", limit,
    )
    return {"status": "started", "message": f"Agent 1: searching IG handles for up to {limit} universities"}


@app.post("/pipeline/scrape-ig-posts")
async def trigger_scrape_ig_posts(background_tasks: BackgroundTasks, limit: int = 20):
    """Agent 2: Scrape IG posts for universities in 'ig_found' status."""
    background_tasks.add_task(
        run_agent_in_thread, _run_agent_with_log,
        run_post_scrape_batch, "scrape_posts", "manual", limit,
    )
    return {"status": "started", "message": f"Agent 2: scraping posts for up to {limit} universities"}


@app.post("/pipeline/extract-phones")
async def trigger_extract_phones(background_tasks: BackgroundTasks, limit: int = 50):
    """Agent 3: Extract phones from unprocessed ig_posts."""
    background_tasks.add_task(
        run_agent_in_thread, _run_agent_with_log,
        run_phone_extraction_batch, "extract_phones", "manual", limit,
    )
    return {"status": "started", "message": f"Agent 3: extracting phones from up to {limit} posts"}


@app.post("/pipeline/discover-bem")
async def trigger_discover_bem(background_tasks: BackgroundTasks, limit: int = 30):
    """Agent 4: Discover BEM handles and scan their following lists."""
    background_tasks.add_task(
        run_agent_in_thread, _run_agent_with_log,
        run_bem_discovery_batch, "discover_bem", "manual", limit,
    )
    return {"status": "started", "message": f"Agent 4: discovering BEM for up to {limit} universities"}


# ---------------------------------------------------------------------------
# Targeted agent triggers (per-university / bulk)
# ---------------------------------------------------------------------------

_TARGETED_AGENT_MAP = {
    "find_handles": run_handle_search_for_universities,
    "scrape_posts": run_post_scrape_for_universities,
    "extract_phones": run_phone_extraction_for_universities,
    "discover_bem": run_bem_discovery_for_universities,
}


async def _run_targeted_agent_with_log(agent_fn, agent_type: str, university_ids: list[int]):
    """Wrapper that creates a pipeline log, runs targeted agent, and records results."""
    log_id = await create_pipeline_log(agent_type, "manual")
    try:
        result = await agent_fn(university_ids)
        processed = 0
        success = 0
        failed = 0
        details = result.get("details", [])

        if agent_type == "find_handles":
            processed = result.get("searched", 0)
            success = result.get("found", 0)
            failed = processed - success
        elif agent_type == "scrape_posts":
            processed = result.get("scraped", 0)
            success = result.get("total_posts", 0)
        elif agent_type == "extract_phones":
            processed = result.get("processed", 0)
            success = result.get("phones_found", 0)
        elif agent_type == "discover_bem":
            processed = result.get("searched", 0)
            success = result.get("found", 0)
            failed = processed - success

        summary = {k: v for k, v in result.items() if k != "details"}
        summary["targeted_university_ids"] = university_ids
        await complete_pipeline_log(
            log_id,
            status="completed",
            summary=summary,
            details=details[:100],
            items_processed=processed,
            items_success=success,
            items_failed=failed,
        )
        # Broadcast agent completion to frontend
        await ws_manager.broadcast_type(
            "agent_completed",
            agent=agent_type,
            stats={"processed": processed, "success": success, "failed": failed, "targeted": len(university_ids)},
        )
        return result
    except Exception as e:
        log.error(f"[{agent_type}] Targeted agent failed: {e}")
        await complete_pipeline_log(log_id, status="failed", error=str(e))
        # Broadcast agent failure to frontend
        await ws_manager.broadcast_type(
            "agent_completed",
            agent=agent_type,
            stats={"error": str(e)},
        )
        raise


@app.post("/pipeline/run-agent-targeted")
async def trigger_targeted_agent(
    background_tasks: BackgroundTasks,
    body: dict,
):
    """Run a pipeline agent on specific universities.

    Body: {"agent_type": "find_handles"|"scrape_posts"|"extract_phones", "university_ids": [1,2,3]}
    """
    agent_type = body.get("agent_type")
    university_ids = body.get("university_ids", [])

    if agent_type not in _TARGETED_AGENT_MAP:
        return JSONResponse(
            {"error": f"Invalid agent_type. Must be one of: {list(_TARGETED_AGENT_MAP.keys())}"},
            status_code=400,
        )
    if not university_ids or not isinstance(university_ids, list):
        return JSONResponse(
            {"error": "university_ids must be a non-empty list of integers"},
            status_code=400,
        )

    agent_fn = _TARGETED_AGENT_MAP[agent_type]
    background_tasks.add_task(
        run_agent_in_thread,
        _run_targeted_agent_with_log,
        agent_fn, agent_type, university_ids,
    )

    agent_labels = {
        "find_handles": "Find IG Handles",
        "scrape_posts": "Scrape IG Posts",
        "extract_phones": "Extract Phones",
        "discover_bem": "Discover BEM",
    }
    return {
        "status": "started",
        "message": f"{agent_labels[agent_type]}: processing {len(university_ids)} universities",
    }


@app.get("/pipeline/status")
async def pipeline_status():
    """Return a breakdown of all pipeline stages."""
    return await get_pipeline_status()


@app.get("/pipeline/logs")
async def get_pipeline_logs_endpoint(
    agent_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return paginated pipeline activity logs."""
    return await get_pipeline_logs(
        agent_type=agent_type, status=status, limit=limit, offset=offset
    )


@app.get("/pipeline/logs/{log_id}")
async def get_pipeline_log_detail(log_id: int):
    """Return a single pipeline log entry with full details."""
    entry = await get_pipeline_log_by_id(log_id)
    if not entry:
        return JSONResponse({"error": "Log not found"}, status_code=404)
    return entry


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
# IG Accounts CRUD  (for Playwright multi-account rotation)
# ---------------------------------------------------------------------------


class IGAccountPayload(BaseModel):
    username: str
    password: str
    notes: str = ""


class IGAccountUpdatePayload(BaseModel):
    username: str | None = None
    password: str | None = None
    enabled: bool | None = None
    notes: str | None = None


def _mask_password(pw: str) -> str:
    if not pw:
        return ""
    if len(pw) <= 4:
        return "\u2022" * len(pw)
    return "\u2022" * (len(pw) - 2) + pw[-2:]


@app.get("/ig-accounts")
async def list_ig_accounts():
    """Return all IG accounts (passwords masked)."""
    from orchestrator.db import get_ig_accounts
    rows = await get_ig_accounts()
    for r in rows:
        r["password"] = _mask_password(r.get("password", ""))
    # Also include live pool status
    from orchestrator.playwright_ig import _account_pool
    pool_status = _account_pool.status()
    return {"accounts": rows, "pool_status": pool_status}


@app.get("/ig-accounts/health")
async def ig_accounts_health(force: bool = False):
    """
    Return IG accounts' session health.

    By default this is **lightweight**: reads from the in-memory account
    pool (login_ok, healthy, last_error) and the DB (login_status).
    No browser is launched.

    With ``?force=true`` a real browser-based verification is performed
    for each account (slow, ~15-45 s per account). Use sparingly.
    """
    from orchestrator.playwright_ig import _account_pool
    from orchestrator.db import get_ig_accounts, update_ig_account

    # --- force mode: expensive browser-based verification ---
    if force:
        from orchestrator.playwright_ig import (
            pw_verify_all_sessions, pw_invalidate_health_cache,
        )
        pw_invalidate_health_cache()
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(_pw_executor, pw_verify_all_sessions)

        rows = await get_ig_accounts(enabled_only=True)
        uid_map = {r["username"]: r["id"] for r in rows}
        for r in results:
            acct_id = uid_map.get(r.get("username"))
            if not acct_id:
                continue
            st = r.get("status", "error")
            db_st = "success" if st == "connected" else ("banned" if st == "banned" else "failed")
            await update_ig_account(acct_id, login_status=db_st,
                                    last_login_test=datetime.now(timezone.utc).isoformat())

        total = len(results)
        connected = sum(1 for r in results if r.get("status") == "connected")
        return {
            "total": total, "connected": connected,
            "all_ok": connected == total and total > 0,
            "accounts": [
                {"username": r.get("username"), "status": r.get("status"),
                 "reason": r.get("reason"), "username_verified": r.get("username_verified")}
                for r in results
            ],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # --- default: lightweight pool + DB status ---
    pool = _account_pool.status()  # [{username, healthy, login_ok, last_error, ...}]
    rows = await get_ig_accounts(enabled_only=True)
    db_map = {r["username"]: r for r in rows}

    accounts_out = []
    for p in pool:
        uname = p["username"]
        db_row = db_map.get(uname, {})
        db_login = db_row.get("login_status", "untested")

        # Derive status from pool state + DB
        if db_login == "banned":
            status = "banned"
            reason = "account_banned"
        elif not p["login_ok"]:
            status = "disconnected"
            reason = p.get("last_error") or "login_failed"
        elif p.get("cooldown_remaining_s", 0) > 0:
            status = "rate_limited"
            reason = "cooldown_active"
        elif db_login == "success" and p["healthy"]:
            status = "connected"
            reason = None
        elif db_login in ("untested", "challenge"):
            status = "connected" if p["healthy"] else "disconnected"
            reason = None if p["healthy"] else (p.get("last_error") or db_login)
        else:
            # db_login == 'failed' but pool says healthy → trust pool
            status = "connected" if p["healthy"] else "disconnected"
            reason = None if p["healthy"] else (p.get("last_error") or "failed")

        accounts_out.append({
            "username": uname,
            "status": status,
            "reason": reason,
            "username_verified": uname if status == "connected" else None,
        })

    total = len(accounts_out)
    connected = sum(1 for a in accounts_out if a["status"] == "connected")
    return {
        "total": total,
        "connected": connected,
        "all_ok": connected == total and total > 0,
        "accounts": accounts_out,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/ig-accounts")
async def add_ig_account(payload: IGAccountPayload):
    """Add a new IG account for Playwright rotation."""
    from orchestrator.db import create_ig_account
    if not payload.username.strip() or not payload.password.strip():
        return JSONResponse(status_code=422, content={"detail": "Username and password required"})
    try:
        acct = await create_ig_account(payload.username, payload.password, payload.notes)
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return JSONResponse(status_code=409, content={"detail": f"Account @{payload.username} already exists"})
        raise
    acct["password"] = _mask_password(acct.get("password", ""))
    # Reload pool
    from orchestrator.playwright_ig import _account_pool
    await _reload_ig_account_pool()
    return {"status": "ok", "account": acct}


@app.put("/ig-accounts/{account_id}")
async def edit_ig_account(account_id: int, payload: IGAccountUpdatePayload):
    """Update an IG account."""
    from orchestrator.db import update_ig_account
    updated = await update_ig_account(
        account_id,
        username=payload.username,
        password=payload.password,
        enabled=payload.enabled,
        notes=payload.notes,
    )
    if not updated:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})
    updated["password"] = _mask_password(updated.get("password", ""))
    await _reload_ig_account_pool()
    return {"status": "ok", "account": updated}


@app.delete("/ig-accounts/{account_id}")
async def remove_ig_account(account_id: int):
    """Delete an IG account."""
    from orchestrator.db import delete_ig_account
    ok = await delete_ig_account(account_id)
    if not ok:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})
    await _reload_ig_account_pool()
    return {"status": "ok"}


# ---- New headless login endpoints (simple REST, no SSE) ----

@app.post("/ig-accounts/{account_id}/login")
async def ig_account_login(account_id: int):
    """
    Start a headless login for an IG account.
    Returns immediately with status: success | challenge | failed.
    If challenge, includes session_id + screenshot for the FE to show.
    """
    from orchestrator.db import get_ig_accounts, update_ig_account
    rows = await get_ig_accounts()
    acct_row = next((r for r in rows if r["id"] == account_id), None)
    if not acct_row:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    username = acct_row["username"]
    password = acct_row["password"]

    from orchestrator.playwright_ig import pw_headless_login, _account_pool, pw_invalidate_health_cache

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_pw_executor, pw_headless_login, username, password)

    # Persist to DB
    login_status = result["status"]  # "success", "challenge", "failed", or "ip_blocked"
    now_ts = datetime.now(timezone.utc).isoformat()
    db_status = ("success" if login_status == "success"
                 else "challenge" if login_status == "challenge"
                 else "failed")  # ip_blocked → stored as "failed" in DB
    await update_ig_account(account_id, login_status=db_status, last_login_test=now_ts)

    # Update pool
    if login_status == "success":
        with _account_pool._lock:
            _account_pool._ensure_loaded()
            for a in _account_pool._accounts:
                if a.username == username:
                    a.login_ok = True
                    a.last_error = None
                    break
        pw_invalidate_health_cache()  # refresh health status
    elif login_status in ("failed", "ip_blocked"):
        _account_pool.mark_login_failed(username, result.get("message", ""))

    await _reload_ig_account_pool()
    return result


@app.post("/ig-accounts/{account_id}/login/challenge")
async def ig_account_login_challenge(account_id: int, body: dict):
    """
    Submit a verification code for an active challenge session.
    Body: { "session_id": "...", "code": "123456" }
    """
    session_id = body.get("session_id")
    code = body.get("code")
    if not session_id or not code:
        return JSONResponse(status_code=400, content={"detail": "session_id and code are required"})

    from orchestrator.db import get_ig_accounts, update_ig_account
    rows = await get_ig_accounts()
    acct_row = next((r for r in rows if r["id"] == account_id), None)
    if not acct_row:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    username = acct_row["username"]

    from orchestrator.playwright_ig import pw_submit_challenge, _account_pool

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_pw_executor, pw_submit_challenge, session_id, code)

    # Persist
    login_status = result["status"]
    now_ts = datetime.now(timezone.utc).isoformat()
    await update_ig_account(account_id, login_status=login_status, last_login_test=now_ts)

    if login_status == "success":
        with _account_pool._lock:
            _account_pool._ensure_loaded()
            for a in _account_pool._accounts:
                if a.username == username:
                    a.login_ok = True
                    a.last_error = None
                    break
    elif login_status == "failed":
        _account_pool.mark_login_failed(username, result.get("message", ""))

    await _reload_ig_account_pool()
    return result


# ---- Legacy test-login endpoints (kept for backward compatibility) ----

@app.post("/ig-accounts/{account_id}/test-login")
async def test_ig_account_login(account_id: int):
    """
    Test whether the IG credentials for this account can successfully log in.
    Runs Playwright in a thread-pool executor (blocking, ~10-30s).
    """
    from orchestrator.db import get_ig_accounts, update_ig_account
    rows = await get_ig_accounts()
    acct_row = next((r for r in rows if r["id"] == account_id), None)
    if not acct_row:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    username = acct_row["username"]
    password = acct_row["password"]

    # Run blocking Playwright test in executor
    from orchestrator.playwright_ig import pw_test_login
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, pw_test_login, username, password)

    # Persist result to DB
    login_status = "success" if result["success"] else "failed"
    now_ts = datetime.now(timezone.utc).isoformat()
    await update_ig_account(
        account_id,
        login_status=login_status,
        last_login_test=now_ts,
    )

    # Update pool runtime state if applicable
    from orchestrator.playwright_ig import _account_pool
    if not result["success"]:
        _account_pool.mark_login_failed(username, result.get("message", ""))
    else:
        # Restore login_ok if it was previously marked failed
        with _account_pool._lock:
            _account_pool._ensure_loaded()
            for a in _account_pool._accounts:
                if a.username == username:
                    a.login_ok = True
                    a.last_error = None
                    break

    await _reload_ig_account_pool()
    return {"status": "ok", "result": result, "login_status": login_status}


@app.get("/ig-accounts/{account_id}/test-login-live")
async def test_ig_account_login_live(account_id: int):
    """
    SSE endpoint: runs the login test with a *visible* browser and streams
    live screenshot events to the frontend.

    Event types pushed over SSE:
      - ``status``      — progress text (no screenshot)
      - ``screenshot``  — base64 JPEG screenshot + step name + message
      - ``done``        — final result dict (test complete)
      - ``result``      — DB-persisted result summary (very last event)

    The frontend should connect via ``EventSource`` or ``fetch`` in
    streaming mode and react to each event type.
    """
    from orchestrator.db import get_ig_accounts, update_ig_account

    rows = await get_ig_accounts()
    acct_row = next((r for r in rows if r["id"] == account_id), None)
    if not acct_row:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    username = acct_row["username"]
    password = acct_row["password"]

    from orchestrator.playwright_ig import pw_test_login, _test_login_events, _account_pool

    # Kick off the blocking pw_test_login in a *dedicated* thread-pool
    # so it doesn't starve the default executor used by other requests.
    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(
        _pw_executor,
        functools.partial(pw_test_login, username, password, live=True),
    )

    async def _event_stream():
        seen = 0
        done_result = None  # will hold the result dict from the "done" event
        while done_result is None:
            q = _test_login_events.get(username)
            if q:
                while seen < len(q):
                    evt = q[seen]
                    seen += 1
                    yield f"data: {_json.dumps(evt, default=str)}\n\n"
                    if evt.get("type") == "done":
                        done_result = evt.get("result", {})
            if done_result is None:
                await asyncio.sleep(0.4)

        # --- persist result to DB immediately (don't wait for browser cleanup) ---
        login_status = "success" if done_result.get("success") else "failed"
        now_ts = datetime.now(timezone.utc).isoformat()
        await update_ig_account(
            account_id,
            login_status=login_status,
            last_login_test=now_ts,
        )
        if not done_result.get("success"):
            _account_pool.mark_login_failed(username, done_result.get("message", ""))
        else:
            with _account_pool._lock:
                _account_pool._ensure_loaded()
                for a in _account_pool._accounts:
                    if a.username == username:
                        a.login_ok = True
                        a.last_error = None
                        break
        await _reload_ig_account_pool()

        # Send final summary so FE can update its cache
        yield f"data: {_json.dumps({'type': 'result', 'login_status': login_status, 'result': done_result}, default=str)}\n\n"

        # Clean up event queue
        _test_login_events.pop(username, None)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _reload_ig_account_pool():
    """Reload Playwright account pool from DB."""
    from orchestrator.db import get_ig_accounts
    from orchestrator.playwright_ig import _account_pool
    rows = await get_ig_accounts(enabled_only=True)
    _account_pool.load_from_db(rows)


# ---------------------------------------------------------------------------
# Session Sync (export from local → import on server)
# ---------------------------------------------------------------------------


@app.get("/ig-accounts/{account_id}/session/export")
async def export_ig_session(account_id: int):
    """
    Export Playwright session profile as a tar.gz download.
    Use this to download a working session from local machine,
    then import it on the server where direct IG login may be blocked.
    """
    from orchestrator.db import get_ig_accounts
    rows = await get_ig_accounts()
    acct_row = next((r for r in rows if r["id"] == account_id), None)
    if not acct_row:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    username = acct_row["username"]

    from orchestrator.playwright_ig import pw_export_session
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, pw_export_session, username)

    if data is None:
        return JSONResponse(status_code=404, content={
            "detail": f"No session profile found for @{username}. Login first."
        })

    filename = f"ig_session_{username}.tar.gz"
    return StreamingResponse(
        iter([data]),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/ig-accounts/{account_id}/session/import")
async def import_ig_session(account_id: int, file: UploadFile = FastAPIFile(...)):
    """
    Import a Playwright session profile from a tar.gz upload.
    Replaces any existing profile for this account's username.
    After import, the session is verified with a lightweight check.
    """
    from orchestrator.db import get_ig_accounts, update_ig_account
    rows = await get_ig_accounts()
    acct_row = next((r for r in rows if r["id"] == account_id), None)
    if not acct_row:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    username = acct_row["username"]

    # Read uploaded file
    data = await file.read()
    if len(data) < 100:
        return JSONResponse(status_code=400, content={"detail": "File too small — not a valid session archive"})

    from orchestrator.playwright_ig import pw_import_session, pw_verify_session, _account_pool, pw_invalidate_health_cache

    # Import (blocking I/O)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, pw_import_session, username, data)

    if not result.get("success"):
        return JSONResponse(status_code=400, content={"detail": result.get("error", "Import failed")})

    # Verify the imported session
    verify = await loop.run_in_executor(_pw_executor, pw_verify_session, username, acct_row["password"])

    # Update DB status based on verification
    v_status = verify.get("status", "error")
    db_status = "success" if v_status == "connected" else "failed"
    now_ts = datetime.now(timezone.utc).isoformat()
    await update_ig_account(account_id, login_status=db_status, last_login_test=now_ts)

    # Update pool
    if v_status == "connected":
        with _account_pool._lock:
            _account_pool._ensure_loaded()
            for a in _account_pool._accounts:
                if a.username == username:
                    a.login_ok = True
                    a.last_error = None
                    break
        pw_invalidate_health_cache()
    else:
        _account_pool.mark_login_failed(username, verify.get("reason", ""))

    await _reload_ig_account_pool()

    return {
        "status": "ok",
        "import": result,
        "verify": {
            "status": v_status,
            "reason": verify.get("reason"),
            "username_verified": verify.get("username_verified"),
        },
    }


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
    from orchestrator.instagram import get_ig_session_status, get_serper_status
    from orchestrator import apify_client, scrapingbot_client, duckduckgo_client, playwright_ig

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
        "scraping": {
            "playwright": playwright_ig.get_status(),
            "duckduckgo": duckduckgo_client.get_status(),
        },
        "api_keys": {
            "serper": get_serper_status(),
            "apify": apify_client.get_status(),
            "scrapingbot": scrapingbot_client.get_status(),
        },
    }


@app.post("/instagram/reset-sessions")
async def reset_ig_sessions():
    """Reset all IG sessions to healthy state (e.g. after updating session IDs)."""
    from orchestrator.instagram import _ig_pool
    _ig_pool.reset_all()
    return {"success": True, "message": "All IG sessions reset to healthy", "status": _ig_pool.get_status()}


# ---------------------------------------------------------------------------
# Image Proxy Endpoint - Bypass Instagram hotlinking protection
# ---------------------------------------------------------------------------

@app.get("/api/v1/test-endpoint")
async def test_endpoint():
    """Test endpoint to verify routing works"""
    log.info("[TEST] Test endpoint called!")
    return {"status": "ok", "message": "Test endpoint works"}

@app.get("/api/v1/proxy-image")
async def proxy_image(url: str = Query(..., description="Instagram image URL to proxy")):
    """
    Proxy Instagram images to bypass hotlinking protection.

    Downloads image from Instagram and serves it directly.
    Returns original image content-type and caches for 1 hour.
    """
    import httpx
    from fastapi.responses import Response

    # Validate URL - only allow Instagram domains
    from urllib.parse import urlparse
    parsed = urlparse(url)
    netloc_lower = parsed.netloc.lower()

    allowed_domains = ["instagram.com", "cdninstagram.com", "fbcdn.net",
                       "scontent.cdninstagram.com", "scontent-*.cdninstagram.com"]

    if not any(domain in netloc_lower or netloc_lower.endswith("." + domain) for domain in allowed_domains):
        return JSONResponse(
            {"detail": "Only Instagram images are allowed"},
            status_code=400
        )

    # Download image with proper headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            log.info(f"[Proxy] Fetching image from: {url[:100]}...")
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            # Determine content type
            content_type = response.headers.get("content-type", "image/jpeg")

            log.info(f"[Proxy] Successfully fetched image: {len(response.content)} bytes, {content_type}")

            # Return image directly
            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                    "X-Image-URL": url,  # For debugging
                }
            )
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to proxy image from {url}: {e}")
            return JSONResponse(
                {"detail": "Failed to fetch image from Instagram"},
                status_code=502
            )
        except Exception as e:
            log.error(f"Unexpected error proxying image from {url}: {e}")
            return JSONResponse(
                {"detail": "Failed to fetch image"},
                status_code=500
            )


# ---------------------------------------------------------------------------
# Instagram Image URL Scraper - Get fresh image URLs from post pages
# ---------------------------------------------------------------------------

@app.get("/api/v1/instagram-image")
async def get_instagram_image_url(post_url: str = Query(..., description="Instagram post URL")):
    """
    Get fresh image URL using Instagram oEmbed API.

    Instagram's oEmbed API returns valid image URLs that work.
    This is more reliable than scraping HTML.

    Returns: {"image_url": "...", "post_url": "..."}
    """
    import httpx
    import re

    log.info(f"[IG oEmbed] Fetching image URL from: {post_url}")

    # Extract short code from URL
    # https://www.instagram.com/p/DPvdidrkYGi/ -> DPvdidrkYGi
    short_code_match = re.search(r'/p/([^/]+)', post_url)
    if not short_code_match:
        return JSONResponse(
            {"detail": "Invalid Instagram post URL"},
            status_code=400
        )

    short_code = short_code_match.group(1)

    # Method 1: Try Instagram oEmbed API (no auth required for public posts)
    oembed_url = f"https://www.instagram.com/p/{short_code}/embed/captioned/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Fetch embed page (simpler than full page)
            response = await client.get(oembed_url, headers=headers)

            if response.status_code == 200:
                html = response.text

                # Extract image URL from embed page
                og_image_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
                if og_image_match:
                    image_url = og_image_match.group(1).replace('&amp;', '&')
                    log.info(f"[IG oEmbed] Found image URL ({len(image_url)} chars)")
                    return {
                        "image_url": image_url,
                        "post_url": post_url,
                        "source": "oembed"
                    }

            # Fallback: Try full post page
            response = await client.get(post_url, headers=headers)
            if response.status_code == 200:
                html = response.text

                og_image_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
                if og_image_match:
                    image_url = og_image_match.group(1).replace('&amp;', '&')
                    log.info(f"[IG Direct] Found image URL ({len(image_url)} chars)")
                    return {
                        "image_url": image_url,
                        "post_url": post_url,
                        "source": "direct"
                    }

            log.warning(f"[IG] Could not find image URL")
            return JSONResponse(
                {"detail": "Could not find image in Instagram page"},
                status_code=404
            )

    except Exception as e:
        log.error(f"[IG] Error: {e}")
        return JSONResponse(
            {"detail": "Failed to fetch image URL"},
            status_code=500
        )
