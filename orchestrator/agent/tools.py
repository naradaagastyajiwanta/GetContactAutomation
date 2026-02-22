"""Tool definitions for the ReAct agent.

Each tool has:
1. A JSON schema dict for OpenAI function-calling (`tools` param).
2. An async implementation: (arguments: dict, context: AgentContext) -> str
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Callable, Awaitable

from orchestrator import db
from orchestrator.config import log, cfg
from orchestrator.agent.schemas import AgentContext

WIB = timezone(timedelta(hours=7))

_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
_BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
          "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def _format_tanggal_id(dt: datetime) -> str:
    """Format a datetime as Indonesian locale string, e.g. 'Senin, 24 Februari 2026'."""
    return f"{_HARI[dt.weekday()]}, {dt.day} {_BULAN[dt.month]} {dt.year}"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _resolve_university(
    context: AgentContext, university_name_arg: str = "",
) -> tuple[int | None, str, str | None]:
    """Resolve university_id, name, and province from context or by searching DB.

    Returns (university_id, university_name, province).
    """
    # 1. Try context.university_id first
    if context.university_id:
        uni = await db.get_university_by_id(context.university_id)
        if uni:
            return uni["id"], uni["name"], uni.get("province")

    # 2. Try searching by name
    name = university_name_arg or context.university_name
    if name:
        results = await db.search_universities(name)
        if results:
            best = results[0]
            return best["id"], best["name"], best.get("province")
        # 3. Create new university record
        new_id = await db.add_university(name)
        return new_id, name, None

    return None, "", None


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _lookup_university_info(arguments: dict, context: AgentContext) -> str:
    """Get university info from DB using the context's university_id or name."""
    uni_id, uni_name, province = await _resolve_university(context)

    if uni_id is None:
        return json.dumps({
            "note": "Tidak ada data universitas di database. Gunakan informasi dari percakapan.",
        })

    uni = await db.get_university_by_id(uni_id)
    if uni is None:
        return json.dumps({
            "note": "Tidak ada data universitas di database. Gunakan informasi dari percakapan.",
        })
    return json.dumps({
        "name": uni.get("name"),
        "province": uni.get("province"),
        "website": uni.get("website"),
        "ig_handle": uni.get("ig_handle"),
        "status": uni.get("status"),
        "secretariat_phone": uni.get("secretariat_phone"),
    })


async def _validate_phone_number(arguments: dict, context: AgentContext) -> str:
    """Validate an Indonesian phone number and return E.164 format."""
    number = arguments.get("number", "")
    result = db.validate_phone(number)
    if result:
        return json.dumps({"valid": True, "formatted": result, "note": "Nomor valid. Langsung save kalau sudah yakin, JANGAN expose format ini ke kontak."})
    return json.dumps({"valid": False, "reason": "Nomor tidak valid atau tidak lengkap. Minta kontak kirim ulang."})


async def _search_similar_conversations(arguments: dict, context: AgentContext) -> str:
    """Search past conversations by province and/or outcome."""
    province = arguments.get("province")
    outcome = arguments.get("outcome")
    limit = arguments.get("limit", 5)
    rows = await db.search_conversations_for_learning(
        province=province, outcome=outcome, limit=limit,
    )
    summaries = []
    for r in rows:
        summaries.append({
            "university_name": r.get("university_name"),
            "province": r.get("province"),
            "state": r.get("state"),
            "attempt_count": r.get("attempt_count"),
            "messages": len(json.loads(r.get("message_history") or "[]")),
        })
    return json.dumps(summaries)


async def _get_relevant_lessons(arguments: dict, context: AgentContext) -> str:
    """Get lessons learned from past conversations for a given situation."""
    situation_type = arguments.get("situation_type", "")
    province = context.province
    rows = await db.get_lessons_by_situation(
        situation_type=situation_type, province=province,
    )
    lessons = []
    for r in rows:
        lessons.append({
            "insight": r.get("insight"),
            "recommended_strategy": r.get("recommended_strategy"),
            "confidence": r.get("confidence"),
            "success_rate": r.get("success_rate"),
        })
    return json.dumps(lessons)


async def _check_conversation_history(arguments: dict, context: AgentContext) -> str:
    """Return the full conversation history from context."""
    return json.dumps(context.conversation_history)


async def _save_extracted_number(arguments: dict, context: AgentContext) -> str:
    """TERMINAL: Save a phone number extracted from the conversation."""
    phone_number = arguments.get("phone_number") or ""
    notes = arguments.get("notes") or ""
    contact_name = arguments.get("contact_name") or ""
    contact_role = arguments.get("contact_role") or ""

    # Enforce: must have at least contact_name
    if not contact_name.strip():
        return json.dumps({
            "success": False,
            "error": "Belum ada nama pemilik nomor. Tanyakan dulu nama kontak sebelum menyimpan.",
            "hint": "Tanya secara natural: 'Terima kasih! Ini nomornya siapa ya?'"
        })

    validated = db.validate_phone(phone_number)
    if not validated:
        return json.dumps({"success": False, "error": "Invalid Indonesian phone number"})

    if context.conversation_id is None:
        return json.dumps({"success": False, "error": "No conversation_id in context"})

    await db.update_conversation_state(
        context.conversation_id,
        "GOT_NUMBER",
        extracted_number=validated,
        extracted_contact_name=contact_name or None,
        extracted_contact_role=contact_role or None,
    )

    if context.university_id is not None:
        await db.update_secretariat_phone(context.university_id, validated)
        await db.update_university_status(context.university_id, "got_number")

    # Auto-queue audiensi conversation
    try:
        from orchestrator.audiensi.auto_queue import create_audiensi_from_success
        import asyncio
        asyncio.create_task(create_audiensi_from_success(context.conversation_id))
    except ImportError:
        pass  # Audiensi module not installed
    except Exception as e:
        log.error("Failed to auto-queue audiensi for conversation %d: %s", context.conversation_id, e)

    return json.dumps({
        "success": True,
        "note": "Nomor berhasil disimpan. Ucapkan terima kasih secara singkat dan natural. JANGAN sebut nomor atau format teknis.",
    })


async def _mark_conversation_refused(arguments: dict, context: AgentContext) -> str:
    """TERMINAL: Mark the conversation as refused."""
    reason = arguments.get("reason", "Contact refused to share information")

    if context.conversation_id is None:
        return json.dumps({"success": False, "error": "No conversation_id in context"})

    await db.update_conversation_state(context.conversation_id, "REFUSED")

    return json.dumps({"success": True, "reason": reason})


# ---------------------------------------------------------------------------
# OpenAI function-calling schemas
# ---------------------------------------------------------------------------

_SCHEMA_LOOKUP_UNIVERSITY_INFO = {
    "type": "function",
    "name": "lookup_university_info",
    "description": "Get university info (name, province, website, IG handle, status, secretariat phone) from the database.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

_SCHEMA_VALIDATE_PHONE_NUMBER = {
    "type": "function",
    "name": "validate_phone_number",
    "description": "Validate an Indonesian phone number and return its E.164 format.",
    "parameters": {
        "type": "object",
        "properties": {
            "number": {
                "type": "string",
                "description": "The phone number to validate (e.g. 08123456789, +628123456789).",
            },
        },
        "required": ["number"],
    },
}

_SCHEMA_SEARCH_SIMILAR_CONVERSATIONS = {
    "type": "function",
    "name": "search_similar_conversations",
    "description": "Search past completed conversations by province and/or outcome to find similar situations.",
    "parameters": {
        "type": "object",
        "properties": {
            "province": {
                "type": "string",
                "description": "Filter by province name.",
            },
            "outcome": {
                "type": "string",
                "description": "Filter by outcome state (e.g. GOT_NUMBER, REFUSED, ABANDONED).",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return.",
                "default": 5,
            },
        },
        "required": [],
    },
}

_SCHEMA_GET_RELEVANT_LESSONS = {
    "type": "function",
    "name": "get_relevant_lessons",
    "description": "Get lessons learned from past conversations for a given situation type.",
    "parameters": {
        "type": "object",
        "properties": {
            "situation_type": {
                "type": "string",
                "description": "The type of situation (e.g. initial_contact, followup, refused, got_number).",
            },
        },
        "required": ["situation_type"],
    },
}

_SCHEMA_CHECK_CONVERSATION_HISTORY = {
    "type": "function",
    "name": "check_conversation_history",
    "description": "Get the full message history of the current conversation.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

_SCHEMA_SAVE_EXTRACTED_NUMBER = {
    "type": "function",
    "name": "save_extracted_number",
    "description": "Save a phone number extracted from the conversation. This is a TERMINAL action that ends the agent loop.",
    "parameters": {
        "type": "object",
        "properties": {
            "phone_number": {
                "type": "string",
                "description": "The phone number to save (Indonesian format).",
            },
            "notes": {
                "type": "string",
                "description": "Optional notes about the extraction.",
            },
            "contact_name": {
                "type": "string",
                "description": "Nama orang yang nomornya diberikan (misal: Bu Sari, Pak Andi).",
            },
            "contact_role": {
                "type": "string",
                "description": "Jabatan/posisi (misal: Sekretariat Rektorat, Humas, Asisten Rektor).",
            },
        },
        "required": ["phone_number"],
    },
}

_SCHEMA_MARK_CONVERSATION_REFUSED = {
    "type": "function",
    "name": "mark_conversation_refused",
    "description": "Mark the current conversation as refused. This is a TERMINAL action that ends the agent loop.",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "The reason the contact refused.",
            },
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# Audiensi tools (available in chatbot 1 for direct scheduling)
# ---------------------------------------------------------------------------


async def _generate_and_send_invitation(arguments: dict, context: AgentContext) -> str:
    """Generate invitation document and send it via WhatsApp."""
    rector_name = arguments.get("rector_name") or ""
    university_name_arg = arguments.get("university_name") or ""

    # Resolve university dynamically
    uni_id, uni_name, province = await _resolve_university(context, university_name_arg)

    if not uni_id:
        return json.dumps({
            "success": False,
            "note": "Belum bisa kirim surat sekarang. Tanya nama kampusnya dulu dari kontak supaya bisa disiapkan suratnya.",
        })

    # Find or create audiensi record
    aud = await db.get_audiensi_conversation_by_phone(context.contact_phone)
    if aud:
        aud_id = aud["id"]
        # Don't downgrade state if audiensi is already past INITIAL_SENT
        _NO_DOWNGRADE_STATES = {"SCHEDULING", "SCHEDULED", "ZOOM_SENT"}
        if aud["state"] in _NO_DOWNGRADE_STATES:
            return json.dumps({
                "success": True,
                "note": f"Surat sudah pernah dikirim sebelumnya dan audiensi sudah dalam proses ({aud['state']}). Lanjutkan jadwalkan meeting.",
            })
    else:
        aud_id = await db.create_audiensi_conversation(
            university_id=uni_id,
            source_conversation_id=context.conversation_id,
            contact_phone=context.contact_phone,
            rector_name=rector_name or None,
        )
        aud = None

    # Update rector name if provided
    if rector_name:
        current_state = aud["state"] if aud else "APPROVED"
        await db.update_audiensi_state(aud_id, current_state, rector_name=rector_name)

    # Generate document
    from orchestrator.audiensi.pdf_generator import generate_audiensi_document, template_exists
    if not template_exists():
        return json.dumps({
            "success": False,
            "note": "Template surat sedang dalam persiapan. Sampaikan ke kontak bahwa surat undangan akan segera dikirimkan.",
        })

    pdf_path = await generate_audiensi_document(
        audiensi_id=aud_id,
        university_name=uni_name,
        rector_name=rector_name or "Rektor",
        province=province,
    )
    if not pdf_path:
        return json.dumps({
            "success": False,
            "note": "Surat sedang diproses, mungkin butuh waktu sebentar. Sampaikan ke kontak bahwa surat akan segera dikirim.",
        })

    await db.update_audiensi_state(aud_id, "INITIAL_SENT", pdf_path=pdf_path)

    # Send document via WhatsApp
    from pathlib import Path
    from orchestrator.message_queue import message_queue
    file_ext = Path(pdf_path).suffix  # .pdf or .docx
    await message_queue.enqueue_send_document(
        phone=context.contact_phone,
        file_path=pdf_path,
        file_name=f"Surat_Undangan_Audiensi_{uni_name.replace(' ', '_')}{file_ext}",
        caption=f"Surat undangan audiensi untuk {uni_name}",
    )

    return json.dumps({
        "success": True,
        "note": "Surat undangan berhasil dikirim. Informasikan ke kontak bahwa surat sudah dikirim.",
    })


async def _propose_meeting_times(arguments: dict, context: AgentContext) -> str:
    """Generate 2-3 meeting time proposals for next weekdays during business hours WIB."""
    now = datetime.now(WIB)
    proposals = []
    days_checked = 0

    while len(proposals) < 3 and days_checked < 14:
        days_checked += 1
        candidate = now + timedelta(days=days_checked)
        if candidate.weekday() >= 5:
            continue
        if len(proposals) < 3:
            proposals.append({
                "date": _format_tanggal_id(candidate),
                "time": "10:00 WIB",
                "datetime_iso": candidate.replace(hour=10, minute=0).isoformat(),
            })
        if len(proposals) < 3:
            proposals.append({
                "date": _format_tanggal_id(candidate),
                "time": "14:00 WIB",
                "datetime_iso": candidate.replace(hour=14, minute=0).isoformat(),
            })

    return json.dumps({
        "proposals": proposals[:3],
        "note": "Tawarkan waktu-waktu ini secara natural, JANGAN tampilkan format ISO.",
    })


async def _confirm_and_send_zoom(arguments: dict, context: AgentContext) -> str:
    """TERMINAL: Confirm schedule and send Zoom link in one step."""
    scheduled_datetime = arguments.get("datetime", "")
    zoom_link = arguments.get("zoom_link", "")
    university_name_arg = arguments.get("university_name", "")

    if not zoom_link:
        zoom_link = cfg.AUDIENSI_ZOOM_LINK_TEMPLATE or "https://zoom.us/j/placeholder"

    # Find or create audiensi record
    aud = await db.get_audiensi_conversation_by_phone(context.contact_phone)
    if aud:
        aud_id = aud["id"]
    else:
        # Resolve university dynamically
        uni_id, uni_name, province = await _resolve_university(context, university_name_arg)
        if not uni_id:
            return json.dumps({
                "success": False,
                "note": "Belum bisa simpan jadwal. Tanya nama kampusnya dulu dari kontak.",
            })
        aud_id = await db.create_audiensi_conversation(
            university_id=uni_id,
            source_conversation_id=context.conversation_id,
            contact_phone=context.contact_phone,
        )

    # Update schedule and zoom link
    await db.update_audiensi_state(
        aud_id, "ZOOM_SENT",
        scheduled_datetime=scheduled_datetime,
        zoom_link=zoom_link,
    )

    # Also update chatbot 1 conversation state
    if context.conversation_id:
        await db.update_conversation_state(context.conversation_id, "GOT_NUMBER")

    return json.dumps({
        "success": True,
        "zoom_link": zoom_link,
        "note": "Jadwal dan Zoom link tersimpan. Kirim link Zoom ke kontak dan ucapkan terima kasih.",
    })


# ---------------------------------------------------------------------------
# Audiensi tool schemas
# ---------------------------------------------------------------------------

_SCHEMA_GENERATE_AND_SEND_INVITATION = {
    "type": "function",
    "name": "generate_and_send_invitation",
    "description": (
        "Generate surat undangan audiensi (DOCX) dan kirim ke kontak via WhatsApp. "
        "Panggil ini kalau kontak mau bantu atur audiensi langsung dan kamu mau kirim surat resmi. "
        "Isi university_name kalau kampus belum terdata di sistem."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "rector_name": {
                "type": "string",
                "description": "Nama rektor universitas (kalau sudah tahu). Kosongkan kalau belum tahu.",
            },
            "university_name": {
                "type": "string",
                "description": "Nama universitas (wajib kalau kampus belum terdata di sistem, misal percakapan test).",
            },
        },
        "required": [],
    },
}

_SCHEMA_PROPOSE_MEETING_TIMES = {
    "type": "function",
    "name": "propose_meeting_times",
    "description": (
        "Generate 2-3 opsi waktu meeting Zoom di hari kerja jam kantor WIB. "
        "Panggil ini kalau kontak siap menjadwalkan audiensi."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

_SCHEMA_CONFIRM_AND_SEND_ZOOM = {
    "type": "function",
    "name": "confirm_and_send_zoom",
    "description": (
        "TERMINAL: Simpan jadwal meeting dan kirim link Zoom. "
        "Panggil ini setelah kontak menyetujui waktu audiensi. "
        "Ini mengakhiri percakapan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "datetime": {
                "type": "string",
                "description": "Waktu meeting yang disepakati (format bebas, misal 'Senin 24 Feb 2026 jam 10 WIB').",
            },
            "zoom_link": {
                "type": "string",
                "description": "Link Zoom (kosongkan untuk pakai link default dari config).",
            },
            "university_name": {
                "type": "string",
                "description": "Nama universitas (wajib kalau kampus belum terdata di sistem).",
            },
        },
        "required": ["datetime"],
    },
}


# ---------------------------------------------------------------------------
# Exported registries
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    _SCHEMA_LOOKUP_UNIVERSITY_INFO,
    _SCHEMA_VALIDATE_PHONE_NUMBER,
    _SCHEMA_SEARCH_SIMILAR_CONVERSATIONS,
    _SCHEMA_GET_RELEVANT_LESSONS,
    _SCHEMA_CHECK_CONVERSATION_HISTORY,
    _SCHEMA_SAVE_EXTRACTED_NUMBER,
    _SCHEMA_MARK_CONVERSATION_REFUSED,
    # Audiensi tools
    _SCHEMA_GENERATE_AND_SEND_INVITATION,
    _SCHEMA_PROPOSE_MEETING_TIMES,
    _SCHEMA_CONFIRM_AND_SEND_ZOOM,
]

TOOL_IMPLEMENTATIONS: dict[str, Callable[..., Awaitable[str]]] = {
    "lookup_university_info": _lookup_university_info,
    "validate_phone_number": _validate_phone_number,
    "search_similar_conversations": _search_similar_conversations,
    "get_relevant_lessons": _get_relevant_lessons,
    "check_conversation_history": _check_conversation_history,
    "save_extracted_number": _save_extracted_number,
    "mark_conversation_refused": _mark_conversation_refused,
    # Audiensi tools
    "generate_and_send_invitation": _generate_and_send_invitation,
    "propose_meeting_times": _propose_meeting_times,
    "confirm_and_send_zoom": _confirm_and_send_zoom,
}

TERMINAL_TOOLS: set[str] = {"save_extracted_number", "mark_conversation_refused", "confirm_and_send_zoom"}
