"""
Marketing module router — corporate outreach groups, clients, contacts, and search.
"""
import io
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, UploadFile, File as FastAPIFile
from fastapi.responses import StreamingResponse

from orchestrator.auth import require_permission
from . import groups as mkt
from .serializers import GroupCreate, ClientCreate, ContactResultOut

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
):
    """List all marketing groups with stats."""
    await require_permission(request, "marketing.view")
    groups = await mkt.list_groups(client_type=client_type, status=status)
    return {"success": True, "groups": groups}


@router.get("/groups/{group_id}", response_model=dict)
async def get_group(request: Request, group_id: int):
    """Get a group with full client list and stats."""
    await require_permission(request, "marketing.view")
    group = await mkt.get_group_with_clients(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    stats = await mkt.get_group_stats(group_id)
    return {"success": True, "group": group, "stats": stats}


@router.delete("/groups/{group_id}", response_model=dict)
async def delete_group(request: Request, group_id: int):
    """Delete a group and cascade-delete all clients and results."""
    await require_permission(request, "marketing.manage")
    deleted = await mkt.delete_group(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"success": True, "message": "Group deleted"}


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
async def list_clients(request: Request, group_id: int):
    """List all clients in a group."""
    await require_permission(request, "marketing.view")
    clients = await mkt.list_clients(group_id)
    return {"success": True, "clients": clients}


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
    """Preview first 5 rows of an Excel/CSV import."""
    await require_permission(request, "marketing.manage")
    group = await mkt.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    rows, columns = parse_excel_bytes(content, file.filename or "upload.xlsx")
    preview = rows[:5]
    return {
        "success": True,
        "detected_columns": columns,
        "preview": preview,
        "total_rows": len(rows),
        "duplicates": 0,
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

    rows, _ = parse_excel_bytes(content, file.filename or "upload.xlsx")

    # Get existing client names in this group
    existing_clients = await mkt.list_clients(group_id)
    existing_names = {c["name"].lower().strip() for c in existing_clients}

    inserted = 0
    skipped_empty = 0
    duplicates = 0

    for row in rows:
        name = row.get("name", "").strip()
        if not name:
            skipped_empty += 1
            continue
        if name.lower() in existing_names:
            duplicates += 1
            continue

        extra = row.get("_extra")
        await mkt.create_client(group_id, name, extra)
        existing_names.add(name.lower())
        inserted += 1

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

    background_tasks.add_task(mkt_search.process_search_queue, group_id)

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
