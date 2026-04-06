"""
Marketing module router — corporate outreach groups, clients, contacts, and search.
"""
import io
import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, UploadFile, File as FastAPIFile
from fastapi.responses import StreamingResponse

from orchestrator.auth import require_permission
from . import groups as mkt
from .serializers import GroupCreate, GroupUpdate, ClientCreate, ContactCreate, ContactResultOut, GroupGenerate, GroupGenerateResponse

router = APIRouter()

# ---------------------------------------------------------------------------
# Handoff sub-router
# ---------------------------------------------------------------------------
from .handoff import router as handoff_router

router.include_router(handoff_router)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


@router.post("/groups", response_model=dict)
async def create_group(request: Request, body: GroupCreate):
    """Create a new marketing group."""
    await require_permission(request, "marketing.manage")
    group = await mkt.create_group(body.name, body.client_type)
    return {"success": True, "group": group}


@router.get("/groups", response_model=dict)
async def list_groups(
    request: Request,
    client_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all marketing groups with stats, paginated."""
    await require_permission(request, "marketing.view")
    result = await mkt.list_groups(
        client_type=client_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"success": True, **result}


@router.get("/groups/{group_id}", response_model=dict)
async def get_group(request: Request, group_id: int):
    """Get a group with full client list and stats."""
    await require_permission(request, "marketing.view")
    group = await mkt.get_group_with_clients(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    stats = await mkt.get_group_stats(group_id)
    return {"success": True, "group": group, "stats": stats}


@router.patch("/groups/{group_id}", response_model=dict)
async def patch_group(request: Request, group_id: int, body: GroupUpdate):
    """Update group name and/or client_type."""
    await require_permission(request, "marketing.manage")
    group = await mkt.update_group(group_id, name=body.name)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"success": True, "group": group}


@router.delete("/groups/{group_id}", response_model=dict)
async def delete_group(request: Request, group_id: int):
    """Delete a group and cascade-delete all clients and results."""
    await require_permission(request, "marketing.manage")
    deleted = await mkt.delete_group(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"success": True, "message": "Group deleted"}


# ---------------------------------------------------------------------------
# Gemini Group Generation
# ---------------------------------------------------------------------------

from . import generator
from . import search as mkt_search


@router.post("/groups/generate", response_model=dict)
async def generate_group_preview(request: Request, body: GroupGenerate):
    """
    Preview a list of institution names for a client_type using Gemini
    with Google Search grounding.
    """
    await require_permission(request, "marketing.view")
    try:
        result = await generator.generate_client_names(body.client_type, body.count)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except generator.GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Generation failed: {exc}") from exc

    return {
        "success": True,
        "names": result["names"],
        "grounding_urls": result["grounding_urls"],
        "suggested_count": result["suggested_count"],
    }


@router.post("/groups/generate/confirm", response_model=dict)
async def generate_and_create_group(
    request: Request,
    background_tasks: BackgroundTasks,
    body: GroupGenerateResponse,
):
    """
    Create a group with auto-generated name, insert all client names,
    and trigger the search pipeline.
    """
    await require_permission(request, "marketing.manage")

    auto_name = f"{body.client_type}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}"
    group = await mkt.create_group(auto_name, body.client_type)
    group_id = group["id"]

    # Update source to gemini_generated
    import aiosqlite
    from orchestrator.config import DATABASE_PATH
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE marketing_groups SET source = ? WHERE id = ?",
            ("gemini_generated", group_id),
        )
        await db.commit()

    # Batch insert all client names
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows: list[tuple[int, str, str | None, str]] = [
        (group_id, name, None, now_str) for name in body.names
    ]
    clients_created = await mkt.batch_create_clients(rows)

    # Update group and client status to searching
    await mkt.update_group_status(group_id, "searching")

    # Trigger background search pipeline
    async def wrapped_search() -> None:
        try:
            await mkt_search.process_search_queue(group_id)
        except Exception as exc:
            import logging

            logging.getLogger("marketing.search").exception(
                "process_search_queue failed for group %s: %s", group_id, exc
            )
            await mkt.mark_group_search_failed(group_id, str(exc))

    background_tasks.add_task(wrapped_search)

    return {
        "success": True,
        "group_id": group_id,
        "group_name": auto_name,
        "clients_created": clients_created,
        "status": "searching",
    }


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


@router.delete("/clients/{client_id}", response_model=dict)
async def delete_client(request: Request, client_id: int):
    """Delete a client (cascades to results)."""
    await require_permission(request, "marketing.manage")
    deleted = await mkt.delete_client(client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"success": True, "message": "Client deleted"}


@router.post("/groups/{group_id}/clients", response_model=dict)
async def add_client(request: Request, group_id: int, body: ClientCreate):
    """Add a client to a group."""
    await require_permission(request, "marketing.manage")
    # Verify group exists
    group = await mkt.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    client = await mkt.create_client(group_id, body.name, body.extra_data)
    return {"success": True, "client": client}


@router.get("/groups/{group_id}/clients", response_model=dict)
async def list_clients(
    request: Request,
    group_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None),
    search_status: str | None = Query(None),
):
    """List clients in a group with pagination and optional search/filter."""
    await require_permission(request, "marketing.view")
    result = await mkt.list_clients(
        group_id,
        limit=limit,
        offset=offset,
        q=q or None,
        search_status=search_status or None,
    )
    return {"success": True, **result}


@router.delete("/groups/{group_id}/clients", response_model=dict)
async def bulk_delete_clients(request: Request, group_id: int, body: dict):
    """Delete multiple clients from a group."""
    await require_permission(request, "marketing.manage")
    group = await mkt.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    client_ids: list[int] = body.get("client_ids", [])
    deleted = await mkt.delete_clients_by_ids(group_id, client_ids)
    return {"success": True, "deleted": deleted}


@router.get("/clients/{client_id}", response_model=dict)
async def get_client_detail(request: Request, client_id: int):
    """Get a single client with full nested data (contacts, ig_posts, ig_candidates)."""
    await require_permission(request, "marketing.view")
    client = await mkt.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    contacts = await mkt.get_contact_results_for_client(client_id)
    ig_posts = await mkt.get_client_ig_posts(client_id)

    import aiosqlite
    from orchestrator.config import DATABASE_PATH
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, client_id, handle, profile_url, source, title, snippet,
                   full_name, bio, external_url, external_domain, is_verified,
                   base_score, affinity_score, profile_score, final_score,
                   llm_is_correct, llm_confidence, llm_reason, rank_order,
                   is_primary, is_selected, created_at
            FROM marketing_ig_candidates
            WHERE client_id = ?
            ORDER BY is_selected DESC, is_primary DESC,
                     COALESCE(rank_order, 999999) ASC, final_score DESC, created_at DESC
            """,
            (client_id,),
        )
        cand_rows = await cur.fetchall()
    ig_candidates = [
        {
            "id": r[0], "client_id": r[1], "handle": r[2], "profile_url": r[3],
            "source": r[4], "title": r[5], "snippet": r[6], "full_name": r[7],
            "bio": r[8], "external_url": r[9], "external_domain": r[10],
            "is_verified": bool(r[11]), "base_score": r[12], "affinity_score": r[13],
            "profile_score": r[14], "final_score": r[15], "llm_is_correct": r[16],
            "llm_confidence": r[17], "llm_reason": r[18], "rank_order": r[19],
            "is_primary": bool(r[20]), "is_selected": bool(r[21]), "created_at": r[22],
        }
        for r in cand_rows
    ]

    return {
        "success": True,
        "client": {**client, "contacts": contacts, "ig_posts": ig_posts, "ig_candidates": ig_candidates},
    }


@router.get("/clients/{client_id}/orchestration", response_model=dict)
async def get_client_orchestration(request: Request, client_id: int):
    """Get orchestration state and recent runs for a marketing client."""
    await require_permission(request, "marketing.view")
    client = await mkt.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    runs = await mkt.list_orchestration_runs(client_id)
    evidence: list[dict] = []
    if client.get("current_run_id"):
        evidence = await mkt.list_orchestration_evidence(int(client["current_run_id"]))
    return {
        "success": True,
        "client": client,
        "runs": runs,
        "current_evidence": evidence,
    }


@router.get("/orchestration/runs/{run_id}", response_model=dict)
async def get_orchestration_run(request: Request, run_id: int):
    """Get one orchestration run with all evidence rows."""
    await require_permission(request, "marketing.view")
    run = await mkt.get_orchestration_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Orchestration run not found")
    evidence = await mkt.list_orchestration_evidence(run_id)
    return {"success": True, "run": run, "evidence": evidence}


@router.post("/clients/{client_id}/instagram/retry", response_model=dict)
async def retry_client_instagram_scrape(request: Request, client_id: int):
    """Retry Instagram post scraping for one marketing client."""
    await require_permission(request, "marketing.manage")
    client = await mkt.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        result = await mkt_search.retry_client_instagram_scrape(client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"success": True, **result}


@router.post("/clients/{client_id}/instagram/contacts/retry", response_model=dict)
async def retry_client_instagram_contact_extraction(request: Request, client_id: int):
    """Re-extract contacts from stored Instagram posts for one marketing client."""
    await require_permission(request, "marketing.manage")
    client = await mkt.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        result = await mkt_search.retry_client_instagram_contact_extraction(client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"success": True, **result}


@router.post("/clients/{client_id}/search/retry", response_model=dict)
async def retry_client_search(
    request: Request,
    client_id: int,
    background_tasks: BackgroundTasks,
):
    """Retry the full marketing search for one client."""
    await require_permission(request, "marketing.manage")
    client = await mkt.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    if client["search_status"] == "searching":
        raise HTTPException(status_code=400, detail="Client is already being searched")
    if client.get("orchestration_state") in {"planning", "collecting", "verifying", "resolving", "deciding", "repairing"}:
        raise HTTPException(status_code=400, detail="Client orchestration already in progress")

    await mkt.reset_client_search_state(client_id)
    await mkt.update_group_status(client["group_id"], "searching")
    background_tasks.add_task(mkt_search.retry_client_search, client_id)

    return {
        "success": True,
        "client_id": client_id,
        "group_id": client["group_id"],
        "status": "queued",
        "message": f"Retry search queued for {client['name']}",
    }


# ---------------------------------------------------------------------------
# Contact Results
# ---------------------------------------------------------------------------


@router.get("/clients/{client_id}/contacts", response_model=dict)
async def get_client_contacts(request: Request, client_id: int):
    """Get all contact results for a client."""
    await require_permission(request, "marketing.view")
    client = await mkt.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    contacts = await mkt.get_contact_results_for_client(client_id)
    return {"success": True, "contacts": contacts}


@router.post("/clients/{client_id}/contacts", response_model=dict)
async def add_contact_result(
    request: Request,
    client_id: int,
    body: ContactCreate,
):
    """Manually add a contact result for a client."""
    await require_permission(request, "marketing.manage")
    client = await mkt.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    contact = await mkt.create_contact_result_for_client(
        client_id,
        body.contact_type,
        body.value,
        source_url=body.source_url,
        source_type=body.source_type,
    )
    return {"success": True, "contact": contact}


@router.patch("/contacts/{result_id}", response_model=dict)
async def patch_contact(request: Request, result_id: int, body: dict):
    """Partial update for a contact result (is_approved, is_selected, edited_value)."""
    await require_permission(request, "marketing.manage")
    updated = await mkt.update_contact_result(
        result_id,
        is_approved=body.get("is_approved"),
        is_selected=body.get("is_selected"),
        edited_value=body.get("edited_value"),
    )
    if not updated:
        raise HTTPException(status_code=400, detail="No fields to update")
    return {"success": True}


@router.post("/groups/{group_id}/approve-all", response_model=dict)
async def approve_all(request: Request, group_id: int):
    """Approve all contacts for all clients in a group."""
    await require_permission(request, "marketing.manage")
    group = await mkt.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    count = await mkt.approve_all_in_group(group_id)
    return {"success": True, "approved": count}


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

from .importer import parse_excel_bytes


@router.post("/groups/{group_id}/import/preview", response_model=dict)
async def import_preview(request: Request, group_id: int, file: UploadFile = FastAPIFile(...)):
    """Preview first 5 rows of an Excel/CSV import, marking duplicates."""
    await require_permission(request, "marketing.manage")
    group = await mkt.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Check file size (10 MB limit)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File terlalu besar (max 10MB)")

    rows, columns = parse_excel_bytes(content, file.filename or "upload.xlsx")

    # Fetch existing client names for this group to detect duplicates
    existing_clients = await mkt.list_clients(group_id, limit=10000, offset=0)
    existing_names: set[str] = {c["name"].lower().strip() for c in existing_clients["clients"]}

    # Mark preview rows
    seen_in_file: set[str] = set()
    duplicate_count = 0
    preview_rows = []
    for row in rows[:10]:
        name = row.get("name", "").strip().lower()
        is_dup = (name in existing_names) or (name in seen_in_file)
        if is_dup:
            duplicate_count += 1
        seen_in_file.add(name)
        preview_rows.append({**row, "is_duplicate": is_dup})

    return {
        "success": True,
        "detected_columns": columns,
        "preview": preview_rows,
        "total_rows": len(rows),
        "duplicates": duplicate_count,
    }


@router.post("/groups/{group_id}/import/commit", response_model=dict)
async def import_commit(request: Request, group_id: int, file: UploadFile = FastAPIFile(...)):
    """Import all rows from an Excel/CSV into a group. Additive (never destructive)."""
    await require_permission(request, "marketing.manage")
    group = await mkt.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    MAX_FILE_SIZE = 10 * 1024 * 1024
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File terlalu besar (max 10MB)")

    rows, _ = parse_excel_bytes(content, file.filename or "upload.xlsx")

    # Collect names to insert (skip empty / already-seen)
    to_insert: list[tuple[int, str, str | None, str]] = []
    seen_names: set[str] = set()
    skipped_empty = 0
    duplicates = 0

    for row in rows:
        name = row.get("name", "").strip()
        if not name:
            skipped_empty += 1
            continue
        if name.lower() in seen_names:
            duplicates += 1
            continue
        seen_names.add(name.lower())
        extra_json = json.dumps(row.get("_extra")) if row.get("_extra") else None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        to_insert.append((group_id, name, extra_json, now))

    if to_insert:
        inserted = await mkt.batch_create_clients(to_insert)
    else:
        inserted = 0

    return {
        "success": True,
        "inserted": inserted,
        "skipped_empty": skipped_empty,
        "duplicates": duplicates,
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

from . import search as mkt_search


@router.post("/groups/{group_id}/search/start", response_model=dict)
async def start_search(request: Request, group_id: int, background_tasks: BackgroundTasks):
    """Trigger background search for all pending clients in a group."""
    await require_permission(request, "marketing.manage")
    group = await mkt.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    pending = await mkt.get_pending_clients(group_id)
    triggered = len(pending)

    async def wrapped_search() -> None:
        try:
            await mkt_search.process_search_queue(group_id)
        except Exception as exc:
            import logging
            logging.getLogger("marketing.search").exception(
                "process_search_queue failed for group %s: %s", group_id, exc
            )
            await mkt.mark_group_search_failed(group_id, str(exc))

    background_tasks.add_task(wrapped_search)

    return {"success": True, "triggered": triggered}


@router.get("/groups/{group_id}/search/status", response_model=dict)
async def search_status(request: Request, group_id: int):
    """Get search status breakdown for a group."""
    await require_permission(request, "marketing.view")
    group = await mkt.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    status = await mkt.get_group_search_status(group_id)
    return {"success": True, "stats": status}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.get("/clients/{client_id}/runs")
async def get_client_runs(request: Request, client_id: int):
    """Return recent orchestration runs with full plan + summary JSON."""
    await require_permission(request, "marketing.view")
    runs = await mkt.list_orchestration_runs(client_id, limit=5)
    return {"success": True, "runs": runs}


@router.get("/groups/{group_id}/strategy")
async def get_group_strategy(request: Request, group_id: int):
    """Return the AI strategy memo for a group."""
    await require_permission(request, "marketing.view")
    from .mkt_memory import get_group_strategy as _get_strategy
    strategy = await _get_strategy(group_id)
    return {"success": True, "strategy": strategy}


@router.get("/groups/{group_id}/export")
async def export_group_contacts(request: Request, group_id: int):
    """Export all contacts in a group as an Excel file."""
    await require_permission(request, "marketing.view")
    group = await mkt.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    contacts = await mkt.get_all_group_contacts_for_export(group_id)
    if not contacts:
        raise HTTPException(status_code=404, detail="No contacts to export")

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Contacts"

    headers = [
        "Client Name", "Contact Type", "Value", "Source URL",
        "Source Type", "Confidence", "Is Approved", "Edited Value",
    ]
    ws.append(headers)

    for c in contacts:
        ws.append([
            c["client_name"],
            c["contact_type"],
            c["value"],
            c["source_url"],
            c["source_type"],
            c["confidence"],
            "Yes" if c["is_approved"] else "No",
            c["edited_value"],
        ])

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"marketing_export_{group_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
