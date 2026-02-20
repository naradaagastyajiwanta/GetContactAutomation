"""Tool definitions for the ReAct agent.

Each tool has:
1. A JSON schema dict for OpenAI function-calling (`tools` param).
2. An async implementation: (arguments: dict, context: AgentContext) -> str
"""

from __future__ import annotations

import json
from typing import Callable, Awaitable

from orchestrator import db
from orchestrator.agent.schemas import AgentContext

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
        "ig_handle": uni.get("ig_handle"),
        "status": uni.get("status"),
        "secretariat_phone": uni.get("secretariat_phone"),
    })


async def _validate_phone_number(arguments: dict, context: AgentContext) -> str:
    """Validate an Indonesian phone number and return E.164 format."""
    number = arguments.get("number", "")
    result = db.validate_phone(number)
    if result:
        return json.dumps({"valid": True, "e164": result})
    return json.dumps({"valid": False, "reason": "Not a valid Indonesian phone number"})


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
    phone_number = arguments.get("phone_number", "")
    notes = arguments.get("notes", "")

    validated = db.validate_phone(phone_number)
    if not validated:
        return json.dumps({"success": False, "error": "Invalid Indonesian phone number"})

    if context.conversation_id is None:
        return json.dumps({"success": False, "error": "No conversation_id in context"})

    await db.update_conversation_state(
        context.conversation_id,
        "GOT_NUMBER",
        extracted_number=validated,
    )

    if context.university_id is not None:
        await db.update_secretariat_phone(context.university_id, validated)
        await db.update_university_status(context.university_id, "got_number")

    # Auto-queue audiensi conversation
    try:
        from orchestrator.audiensi.auto_queue import create_audiensi_from_success
        import asyncio
        asyncio.create_task(create_audiensi_from_success(context.conversation_id))
    except Exception:
        pass  # Audiensi module may not be available

    return json.dumps({
        "success": True,
        "phone_e164": validated,
        "notes": notes,
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
    "function": {
        "name": "lookup_university_info",
        "description": "Get university info (name, province, website, IG handle, status, secretariat phone) from the database.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

_SCHEMA_VALIDATE_PHONE_NUMBER = {
    "type": "function",
    "function": {
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
    },
}

_SCHEMA_SEARCH_SIMILAR_CONVERSATIONS = {
    "type": "function",
    "function": {
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
    },
}

_SCHEMA_GET_RELEVANT_LESSONS = {
    "type": "function",
    "function": {
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
    },
}

_SCHEMA_CHECK_CONVERSATION_HISTORY = {
    "type": "function",
    "function": {
        "name": "check_conversation_history",
        "description": "Get the full message history of the current conversation.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

_SCHEMA_SAVE_EXTRACTED_NUMBER = {
    "type": "function",
    "function": {
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
            },
            "required": ["phone_number"],
        },
    },
}

_SCHEMA_MARK_CONVERSATION_REFUSED = {
    "type": "function",
    "function": {
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
]

TOOL_IMPLEMENTATIONS: dict[str, Callable[..., Awaitable[str]]] = {
    "lookup_university_info": _lookup_university_info,
    "validate_phone_number": _validate_phone_number,
    "search_similar_conversations": _search_similar_conversations,
    "get_relevant_lessons": _get_relevant_lessons,
    "check_conversation_history": _check_conversation_history,
    "save_extracted_number": _save_extracted_number,
    "mark_conversation_refused": _mark_conversation_refused,
}

TERMINAL_TOOLS: set[str] = {"save_extracted_number", "mark_conversation_refused"}
