"""
Marketing Handoff — push approved+selected contacts to WA blast or email blast campaigns.
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException

from orchestrator.config import log
from orchestrator import blast_service
from orchestrator import email_blast
from orchestrator.db import get_db

router = APIRouter()


async def _get_approved_selected_contacts(
    group_id: int, contact_type: str | None = None
) -> list[dict]:
    """Fetch contacts for a group that are both approved and selected.

    Args:
        group_id: marketing group ID
        contact_type: filter by 'wa_phone' or 'email', or None for all

    Returns:
        List of dicts with id, client_id, contact_type, value, edited_value,
        source_url, source_type, contact_name (from edited_value or client name)
    """
    async with get_db() as db:
        query = """
            SELECT
                r.id AS result_id,
                r.client_id,
                r.contact_type,
                COALESCE(r.edited_value, r.value) AS value,
                r.value AS raw_value,
                r.source_url,
                r.source_type,
                c.name AS client_name
            FROM marketing_contact_results r
            JOIN marketing_clients c ON c.id = r.client_id
            WHERE c.group_id = ?
              AND r.is_approved = 1
              AND r.is_selected = 1
        """
        params: list = [group_id]

        if contact_type:
            query += " AND r.contact_type = ?"
            params.append(contact_type)

        if contact_type == "wa_phone":
            query += """
                AND EXISTS (
                    SELECT 1
                    FROM marketing_contact_results n
                    WHERE n.client_id = r.client_id
                      AND n.contact_type = 'pic_name'
                      AND TRIM(COALESCE(n.edited_value, n.value, '')) != ''
                      AND COALESCE(n.source_url, '') = COALESCE(r.source_url, '')
                      AND COALESCE(n.source_type, '') = COALESCE(r.source_type, '')
                )
            """

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [
            {
                "result_id": row[0],
                "client_id": row[1],
                "contact_type": row[2],
                "value": row[3],
                "raw_value": row[4],
                "source_url": row[5],
                "source_type": row[6],
                "client_name": row[7],
            }
            for row in rows
        ]


async def _insert_handoffs(
    group_id: int,
    result_ids: list[int],
    handoff_type: str,
    campaign_id: int,
) -> int:
    """Insert audit records into marketing_contact_handoffs. Returns count inserted."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0
    async with get_db() as db:
        for result_id in result_ids:
            await db.execute(
                """INSERT INTO marketing_contact_handoffs
                   (group_id, result_id, handoff_type, campaign_id, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (group_id, result_id, handoff_type, campaign_id, now),
            )
            inserted += 1
        await db.commit()
    return inserted


@router.post("/groups/{group_id}/handoff")
async def handoff_group(group_id: int, body: dict):
    """
    Hand off approved+selected contacts from a marketing group to a blast campaign.

    Body: { handoff_type: "wa_blast" | "email_blast" }

    Returns: { campaign_id, wa_count, email_count, handoff_id, message }
    """
    handoff_type = body.get("handoff_type")
    if handoff_type not in ("wa_blast", "email_blast"):
        raise HTTPException(
            status_code=400,
            detail="handoff_type must be 'wa_blast' or 'email_blast'",
        )

    # Verify group exists
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, name FROM marketing_groups WHERE id = ?", (group_id,)
        )
        group_row = await cursor.fetchone()
    if not group_row:
        raise HTTPException(status_code=404, detail="Group not found")

    group_name = group_row[1]

    wa_count = 0
    email_count = 0
    campaign_id = None

    if handoff_type == "wa_blast":
        # Get approved+selected WA contacts
        wa_contacts = await _get_approved_selected_contacts(group_id, "wa_phone")
        if not wa_contacts:
            raise HTTPException(
                status_code=400,
                detail="No approved+selected WA contacts found in this group",
            )

        # Create WA blast campaign
        campaign = await blast_service.create_campaign(
            name=f"[Marketing] {group_name}",
            template_message="",
        )
        campaign_id = campaign["id"]

        # Build recipient list
        recipients = [
            {
                "phone_number": c["raw_value"],
                "contact_name": c["client_name"],
                "university_name": c["value"],  # value IS the WA name here
            }
            for c in wa_contacts
        ]

        result = await blast_service.add_recipients_from_marketing_contacts(
            campaign_id, recipients
        )
        wa_count = result["added"]

        # Audit trail
        handoff_id = await _insert_handoffs(
            group_id,
            [c["result_id"] for c in wa_contacts],
            handoff_type,
            campaign_id,
        )

        log.info(
            "[Handoff] wa_blast campaign %d created for group %d with %d recipients",
            campaign_id,
            group_id,
            wa_count,
        )

    elif handoff_type == "email_blast":
        # Get approved+selected email contacts
        email_contacts = await _get_approved_selected_contacts(group_id, "email")
        if not email_contacts:
            raise HTTPException(
                status_code=400,
                detail="No approved+selected email contacts found in this group",
            )

        # Create email blast campaign
        campaign_id = await email_blast.create_email_campaign(
            name=f"[Marketing] {group_name}",
            subject="",
            template="",
        )

        # Add recipients
        email_count = await email_blast.add_email_recipients_from_marketing_contacts(
            campaign_id, email_contacts
        )

        # Audit trail
        handoff_id = await _insert_handoffs(
            group_id,
            [c["result_id"] for c in email_contacts],
            handoff_type,
            campaign_id,
        )

        log.info(
            "[Handoff] email_blast campaign %d created for group %d with %d recipients",
            campaign_id,
            group_id,
            email_count,
        )

    return {
        "success": True,
        "campaign_id": campaign_id,
        "wa_count": wa_count,
        "email_count": email_count,
        "handoff_id": handoff_id,
        "message": f"Handed off {max(wa_count, email_count)} contact(s) to {handoff_type}",
    }
