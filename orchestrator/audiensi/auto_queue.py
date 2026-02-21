"""
Auto-queue: Create audiensi conversations when chatbot 1 reaches GOT_NUMBER.

Called from the agent tools when a phone number is extracted.
"""
from __future__ import annotations

import asyncio

from orchestrator.config import log, cfg
from orchestrator.db import (
    get_conversation_by_id,
    get_university_by_id,
    create_audiensi_conversation,
    update_audiensi_state,
    get_audiensi_conversation_by_phone,
)


async def create_audiensi_from_success(conversation_id: int) -> int | None:
    """
    Called when chatbot 1 gets GOT_NUMBER.
    Creates an audiensi conversation record in QUEUED state.

    Returns the audiensi conversation ID, or None if creation fails.
    """
    if not cfg.AUDIENSI_ENABLED:
        log.debug("Audiensi disabled, skipping auto-queue for conv %d", conversation_id)
        return None

    from orchestrator.db import get_conversation_by_id

    conv = await get_conversation_by_id(conversation_id)
    if not conv:
        log.warning("auto_queue: conversation %d not found", conversation_id)
        return None

    extracted_number = conv.get("extracted_number")
    if not extracted_number:
        log.warning("auto_queue: conversation %d has no extracted_number", conversation_id)
        return None

    university_id = conv.get("university_id")
    if not university_id:
        log.warning("auto_queue: conversation %d has no university_id", conversation_id)
        return None

    contact_role = conv.get("extracted_contact_role")

    # Check if audiensi already exists for this phone
    existing = await get_audiensi_conversation_by_phone(extracted_number)
    if existing:
        log.info("auto_queue: audiensi already exists for %s (id=%d)", extracted_number, existing["id"])
        return existing["id"]

    # Create audiensi conversation
    aud_id = await create_audiensi_conversation(
        university_id=university_id,
        source_conversation_id=conversation_id,
        contact_phone=extracted_number,
        contact_role=contact_role,
    )

    log.info(
        "auto_queue: created audiensi conversation %d for university %d (phone: %s)",
        aud_id, university_id, extracted_number,
    )

    # Background: find rector name and prepare initial message + PDF
    asyncio.create_task(_prepare_audiensi(aud_id, university_id))

    return aud_id


async def _prepare_audiensi(aud_id: int, university_id: int) -> None:
    """
    Background task: prepare audiensi record.
    1. Find rector name
    2. Generate initial message draft
    3. Generate invitation document
    """
    try:
        # 1. Find rector name
        try:
            from orchestrator.agents.rector_finder import find_rector_name
            rector_name = await find_rector_name(university_id)
        except Exception as e:
            log.warning("auto_queue: rector finder failed for uni %d: %s", university_id, e)
            rector_name = None

        uni = await get_university_by_id(university_id)
        uni_name = uni["name"] if uni else "Unknown"

        # Update rector_name if found
        if rector_name:
            await update_audiensi_state(aud_id, "QUEUED", rector_name=rector_name)

        # 2. Generate initial message draft
        try:
            from orchestrator.audiensi.react_agent import AudiensiReactAgent
            agent = AudiensiReactAgent()
            draft = await agent.generate_initial_message(
                uni_name, rector_name=rector_name,
            )
            await update_audiensi_state(aud_id, "QUEUED", initial_message_draft=draft)
        except Exception as e:
            log.warning("auto_queue: initial message gen failed for audiensi %d: %s", aud_id, e)

        # 3. Generate invitation document
        try:
            from orchestrator.audiensi.pdf_generator import generate_audiensi_document
            pdf_path = await generate_audiensi_document(
                audiensi_id=aud_id,
                university_name=uni_name,
                rector_name=rector_name,
                province=uni.get("province") if uni else None,
            )
            if pdf_path:
                await update_audiensi_state(aud_id, "QUEUED", pdf_path=pdf_path)
        except Exception as e:
            log.warning("auto_queue: PDF gen failed for audiensi %d: %s", aud_id, e)

        log.info("auto_queue: preparation complete for audiensi %d", aud_id)

        # Auto-approve if configured
        if cfg.AUDIENSI_AUTO_APPROVE:
            await _auto_approve_and_send(aud_id)

    except Exception as e:
        log.error("auto_queue: preparation failed for audiensi %d: %s", aud_id, e)


async def _auto_approve_and_send(aud_id: int) -> None:
    """Automatically approve and send audiensi messages (skip manual review)."""
    from orchestrator.db import (
        get_audiensi_conversation_by_id,
        add_audiensi_message,
    )
    from orchestrator.message_queue import message_queue
    from datetime import datetime, timezone

    try:
        aud = await get_audiensi_conversation_by_id(aud_id)
        if not aud or aud["state"] != "QUEUED":
            return

        now = datetime.now(timezone.utc).isoformat()
        await update_audiensi_state(aud_id, "APPROVED", approved_at=now, approved_by="auto")

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
            f"Terima kasih \U0001f64f\U0001f3fb"
        )
        await message_queue.enqueue_send(phone, text)

        # Update state to INITIAL_SENT
        await update_audiensi_state(
            aud_id, "INITIAL_SENT",
            last_message_at=datetime.now(timezone.utc).isoformat(),
        )
        await add_audiensi_message(aud_id, "bot", text)

        log.info("auto_queue: auto-approved and sent audiensi %d to %s", aud_id, phone)

    except Exception as e:
        log.error("auto_queue: auto-approve failed for audiensi %d: %s", aud_id, e)
