"""
FastAPI orchestrator - main server that ties everything together.
Run: uvicorn orchestrator.main:app --port 8000 --reload
"""
import asyncio
import csv
import io
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, BackgroundTasks, UploadFile, File as FastAPIFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from orchestrator.config import WA_SERVICE_URL, WEBHOOK_URL, log, is_paused, set_paused
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
)
from orchestrator.conversation import conversation_manager, ConvState
from orchestrator.message_queue import message_queue
from orchestrator.scheduler import (
    setup_scheduler,
    scheduler,
    daily_outreach_loop,
    process_followups,
)
from orchestrator.agents.ig_handle_finder import run_handle_search_batch
from orchestrator.agents.ig_post_scraper import run_post_scrape_batch
from orchestrator.agents.ig_phone_extractor import run_phone_extraction_batch
from orchestrator.config import PROVINCES


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    log.info("Database initialized")

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

    if not phone or not message:
        return {"status": "ignored", "reason": "empty payload"}

    # Normalize phone to +62 format for lookup
    normalized = validate_phone(phone) or phone

    log.info(f"Incoming WA from {phone} ({push_name}): {message[:100]}")

    # Process in background to respond quickly to webhook
    background_tasks.add_task(
        _process_incoming, normalized, phone, message, push_name, msg_key,
    )

    return {"status": "received"}


async def _process_incoming(
    normalized_phone: str,
    raw_phone: str,
    message: str,
    push_name: str = "",
    msg_key: str | None = None,
):
    """Process incoming message and respond if needed."""
    if is_paused():
        log.info(f"Paused – ignoring incoming message from {raw_phone}")
        return

    result = await message_queue.process_with_ai(
        conversation_manager.process_incoming_message(
            normalized_phone, message, push_name=push_name,
        )
    )

    if result.get("response_message"):
        await message_queue.enqueue_send(
            raw_phone, result["response_message"], reply_to_msg_key=msg_key,
        )


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
):
    """Collect universities from PDDIKTI API. Optionally filter by province."""
    from scripts.collect_universities import search_pddikti

    async def _collect(province: str | None):
        existing = await get_all_universities(limit=10000)
        existing_names = [u["name"] for u in existing]

        from scripts.collect_universities import is_duplicate

        universities = await search_pddikti(province)
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
        log.info(f"[PDDIKTI] Collected {added} new universities (province={province})")

    msg = f"Collecting universities from PDDIKTI"
    if province:
        msg += f" (province: {province})"
    background_tasks.add_task(_collect, province)
    return {"status": "started", "message": msg}


# ---------------------------------------------------------------------------
# University import
# ---------------------------------------------------------------------------

@app.post("/universities/import")
async def import_universities(file: UploadFile = FastAPIFile(...)):
    """Import universities from CSV file. Expected columns: name, province, website"""
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    for row in reader:
        name = row.get("name", "").strip()
        if not name:
            continue
        await add_university(
            name=name,
            province=row.get("province", "").strip() or None,
            website=row.get("website", "").strip() or None,
        )
        imported += 1

    return {"imported": imported}


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
    limit: int = 100,
    offset: int = 0,
):
    """List conversations with optional filters."""
    return await get_conversations_filtered(state, university_id, limit, offset)


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int):
    """Get a single conversation by ID."""
    conv = await get_conversation_by_id(conversation_id)
    if not conv:
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})
    return conv


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
    background_tasks.add_task(run_handle_search_batch, limit)
    return {"status": "started", "message": f"Agent 1: searching IG handles for up to {limit} universities"}


@app.post("/pipeline/scrape-ig-posts")
async def trigger_scrape_ig_posts(background_tasks: BackgroundTasks, limit: int = 20):
    """Agent 2: Scrape IG posts for universities in 'ig_found' status."""
    background_tasks.add_task(run_post_scrape_batch, limit)
    return {"status": "started", "message": f"Agent 2: scraping posts for up to {limit} universities"}


@app.post("/pipeline/extract-phones")
async def trigger_extract_phones(background_tasks: BackgroundTasks, limit: int = 50):
    """Agent 3: Extract phones from unprocessed ig_posts."""
    background_tasks.add_task(run_phone_extraction_batch, limit)
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
    """Return current pause state."""
    return {"paused": is_paused()}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check endpoint."""
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
    }
