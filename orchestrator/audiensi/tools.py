"""Tool definitions for the Audiensi ReAct agent."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Callable, Awaitable

from orchestrator import db
from orchestrator.agent.schemas import AgentContext

WIB = timezone(timedelta(hours=7))

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _lookup_university_info(arguments: dict, context: AgentContext) -> str:
    """Get university info from DB using the context's university_id."""
    if context.university_id is None:
        return json.dumps({"error": "No university_id in context"})
    uni = await db.get_university_by_id(context.university_id)
    if uni is None:
        return json.dumps({"error": f"University {context.university_id} not found"})
    return json.dumps({
        "name": uni.get("name"),
        "province": uni.get("province"),
        "website": uni.get("website"),
        "rector_name": uni.get("rector_name"),
        "status": uni.get("status"),
    })


async def _lookup_audiensi_context(arguments: dict, context: AgentContext) -> str:
    """Get audiensi-specific context for the current conversation."""
    if not context.conversation_id:
        return json.dumps({"error": "No conversation_id"})
    aud = await db.get_audiensi_conversation_by_id(context.conversation_id)
    if not aud:
        return json.dumps({"error": "Audiensi conversation not found"})
    return json.dumps({
        "rector_name": aud.get("rector_name"),
        "contact_role": aud.get("contact_role"),
        "pdf_path": aud.get("pdf_path"),
        "scheduled_datetime": aud.get("scheduled_datetime"),
        "zoom_link": aud.get("zoom_link"),
        "state": aud.get("state"),
        "attempt_count": aud.get("attempt_count"),
    })


async def _check_conversation_history(arguments: dict, context: AgentContext) -> str:
    """Return the full conversation history from context."""
    return json.dumps(context.conversation_history)


async def _get_relevant_lessons(arguments: dict, context: AgentContext) -> str:
    """Get lessons for audiensi situations."""
    situation_type = arguments.get("situation_type", "audiensi_scheduling")
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


async def _search_similar_audiensi(arguments: dict, context: AgentContext) -> str:
    """Search past audiensi conversations."""
    province = arguments.get("province")
    state = arguments.get("state")
    limit = arguments.get("limit", 5)

    convs = await db.get_audiensi_conversations_filtered(state=state, limit=limit)
    summaries = []
    for c in convs:
        if province and c.get("province") != province:
            continue
        summaries.append({
            "university_name": c.get("university_name"),
            "state": c.get("state"),
            "attempt_count": c.get("attempt_count"),
            "scheduled_datetime": c.get("scheduled_datetime"),
        })
    return json.dumps(summaries[:limit])


async def _propose_meeting_times(arguments: dict, context: AgentContext) -> str:
    """Generate 2-3 meeting time proposals for next weekdays during business hours WIB."""
    now = datetime.now(WIB)
    proposals = []
    days_checked = 0

    while len(proposals) < 3 and days_checked < 14:
        days_checked += 1
        candidate = now + timedelta(days=days_checked)
        # Skip weekends (5=Saturday, 6=Sunday)
        if candidate.weekday() >= 5:
            continue
        # Morning option (10:00 WIB)
        if len(proposals) < 3:
            proposals.append({
                "date": candidate.strftime("%A, %d %B %Y"),
                "time": "10:00 WIB",
                "datetime_iso": candidate.replace(hour=10, minute=0).isoformat(),
            })
        # Afternoon option (14:00 WIB)
        if len(proposals) < 3:
            proposals.append({
                "date": candidate.strftime("%A, %d %B %Y"),
                "time": "14:00 WIB",
                "datetime_iso": candidate.replace(hour=14, minute=0).isoformat(),
            })

    return json.dumps({
        "proposals": proposals[:3],
        "note": "Pilih salah satu waktu yang cocok, atau tawarkan waktu lain."
    })


async def _confirm_schedule(arguments: dict, context: AgentContext) -> str:
    """TERMINAL: Save agreed meeting datetime, transition to SCHEDULED."""
    scheduled_datetime = arguments.get("datetime", "")
    notes = arguments.get("notes", "")

    if not context.conversation_id:
        return json.dumps({"success": False, "error": "No conversation_id"})

    await db.update_audiensi_state(
        context.conversation_id,
        "SCHEDULED",
        scheduled_datetime=scheduled_datetime,
    )

    return json.dumps({
        "success": True,
        "scheduled_datetime": scheduled_datetime,
        "notes": notes,
    })


async def _send_zoom_link(arguments: dict, context: AgentContext) -> str:
    """TERMINAL: Record zoom link sent, transition to ZOOM_SENT."""
    zoom_link = arguments.get("zoom_link", "")

    if not context.conversation_id:
        return json.dumps({"success": False, "error": "No conversation_id"})

    # Use dummy link if none provided
    from orchestrator.config import cfg
    if not zoom_link:
        zoom_link = cfg.AUDIENSI_ZOOM_LINK_TEMPLATE or "https://zoom.us/j/placeholder"

    await db.update_audiensi_state(
        context.conversation_id,
        "ZOOM_SENT",
        zoom_link=zoom_link,
    )

    return json.dumps({
        "success": True,
        "zoom_link": zoom_link,
    })


async def _mark_audiensi_refused(arguments: dict, context: AgentContext) -> str:
    """TERMINAL: Mark audiensi as refused."""
    reason = arguments.get("reason", "Contact refused audiensi invitation")

    if not context.conversation_id:
        return json.dumps({"success": False, "error": "No conversation_id"})

    await db.update_audiensi_state(context.conversation_id, "REFUSED")

    return json.dumps({"success": True, "reason": reason})


# ---------------------------------------------------------------------------
# OpenAI function-calling schemas
# ---------------------------------------------------------------------------

_SCHEMA_LOOKUP_UNIVERSITY_INFO = {
    "type": "function",
    "function": {
        "name": "lookup_university_info",
        "description": "Get university info (name, province, website, rector name, status).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

_SCHEMA_LOOKUP_AUDIENSI_CONTEXT = {
    "type": "function",
    "function": {
        "name": "lookup_audiensi_context",
        "description": "Get audiensi-specific context (rector name, PDF sent, scheduled datetime, current state).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

_SCHEMA_CHECK_CONVERSATION_HISTORY = {
    "type": "function",
    "function": {
        "name": "check_conversation_history",
        "description": "Get the full message history of the current audiensi conversation.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

_SCHEMA_GET_RELEVANT_LESSONS = {
    "type": "function",
    "function": {
        "name": "get_relevant_lessons",
        "description": "Get lessons from past audiensi conversations.",
        "parameters": {
            "type": "object",
            "properties": {
                "situation_type": {
                    "type": "string",
                    "description": "Situation type (audiensi_initial, audiensi_scheduling, audiensi_followup).",
                },
            },
            "required": ["situation_type"],
        },
    },
}

_SCHEMA_SEARCH_SIMILAR_AUDIENSI = {
    "type": "function",
    "function": {
        "name": "search_similar_audiensi",
        "description": "Search past audiensi conversations by province or state.",
        "parameters": {
            "type": "object",
            "properties": {
                "province": {"type": "string", "description": "Filter by province."},
                "state": {"type": "string", "description": "Filter by audiensi state."},
                "limit": {"type": "integer", "description": "Max results.", "default": 5},
            },
            "required": [],
        },
    },
}

_SCHEMA_PROPOSE_MEETING_TIMES = {
    "type": "function",
    "function": {
        "name": "propose_meeting_times",
        "description": "Generate 2-3 meeting time proposals for next available weekdays during business hours WIB.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

_SCHEMA_CONFIRM_SCHEDULE = {
    "type": "function",
    "function": {
        "name": "confirm_schedule",
        "description": "TERMINAL: Save the agreed meeting datetime. Call this when the contact confirms a specific time.",
        "parameters": {
            "type": "object",
            "properties": {
                "datetime": {
                    "type": "string",
                    "description": "The agreed meeting datetime (ISO format or descriptive).",
                },
                "notes": {"type": "string", "description": "Optional notes about the agreement."},
            },
            "required": ["datetime"],
        },
    },
}

_SCHEMA_SEND_ZOOM_LINK = {
    "type": "function",
    "function": {
        "name": "send_zoom_link",
        "description": "TERMINAL: Send Zoom meeting link after schedule is confirmed.",
        "parameters": {
            "type": "object",
            "properties": {
                "zoom_link": {
                    "type": "string",
                    "description": "The Zoom meeting link to send. Leave empty to use default.",
                },
            },
            "required": [],
        },
    },
}

_SCHEMA_MARK_AUDIENSI_REFUSED = {
    "type": "function",
    "function": {
        "name": "mark_audiensi_refused",
        "description": "TERMINAL: Mark the audiensi as refused by the contact.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Reason for refusal."},
            },
            "required": [],
        },
    },
}

# ---------------------------------------------------------------------------
# Exported registries
# ---------------------------------------------------------------------------

AUDIENSI_TOOL_SCHEMAS: list[dict] = [
    _SCHEMA_LOOKUP_UNIVERSITY_INFO,
    _SCHEMA_LOOKUP_AUDIENSI_CONTEXT,
    _SCHEMA_CHECK_CONVERSATION_HISTORY,
    _SCHEMA_GET_RELEVANT_LESSONS,
    _SCHEMA_SEARCH_SIMILAR_AUDIENSI,
    _SCHEMA_PROPOSE_MEETING_TIMES,
    _SCHEMA_CONFIRM_SCHEDULE,
    _SCHEMA_SEND_ZOOM_LINK,
    _SCHEMA_MARK_AUDIENSI_REFUSED,
]

AUDIENSI_TOOL_IMPLEMENTATIONS: dict[str, Callable[..., Awaitable[str]]] = {
    "lookup_university_info": _lookup_university_info,
    "lookup_audiensi_context": _lookup_audiensi_context,
    "check_conversation_history": _check_conversation_history,
    "get_relevant_lessons": _get_relevant_lessons,
    "search_similar_audiensi": _search_similar_audiensi,
    "propose_meeting_times": _propose_meeting_times,
    "confirm_schedule": _confirm_schedule,
    "send_zoom_link": _send_zoom_link,
    "mark_audiensi_refused": _mark_audiensi_refused,
}

AUDIENSI_TERMINAL_TOOLS: set[str] = {"confirm_schedule", "send_zoom_link", "mark_audiensi_refused"}
