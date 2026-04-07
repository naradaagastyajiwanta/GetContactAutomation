"""
Marketing Discovery Orchestrator Agent.

Supports two backends:
  - Gemini (default): google.genai with function calling — no OpenAI quota needed
  - OpenAI Responses API: fallback when MARKETING_ORCHESTRATOR_MODEL starts with "gpt-"

Model: cfg.MARKETING_ORCHESTRATOR_MODEL (default: gemini-3.1-pro-preview)
Tools: 9 tools including spawn_* for 4 sub-agents, memory, record_contact, mark_done

The orchestrator's context stays clean because spawn_* tools return
SUMMARIZED results (not raw HTML/posts/images).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError

from orchestrator.config import log, cfg, responses_kwargs, is_reasoning_model
from orchestrator import db
from . import groups as mkt
from .mkt_sub_agents import (
    WebSearchSubAgent,
    InstagramSubAgent,
    RegistrySearchSubAgent,
    GeminiGapFillSubAgent,
    SubAgentResult,
)
from .mkt_memory import get_client_episodic_memory, get_long_term_context, write_post_run_lessons
from .mkt_prompts import build_orchestrator_prompt


# ---------------------------------------------------------------------------
# OpenAI client (used when model starts with "gpt-")
# ---------------------------------------------------------------------------

_openai_client: AsyncOpenAI | None = None
_openai_client_key: str = ""

_RETRIABLE_STATUS_CODES = {429, 500, 503}
_MAX_RETRIES = 3


def _get_openai() -> AsyncOpenAI:
    global _openai_client, _openai_client_key
    current_key = cfg.OPENAI_API_KEY
    if _openai_client is None or current_key != _openai_client_key:
        _openai_client = AsyncOpenAI(api_key=current_key)
        _openai_client_key = current_key
    return _openai_client


async def _api_call_with_retry(coro_factory, label: str = "API call"):
    """Same retry logic as react_agent.py."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return await coro_factory()
        except APITimeoutError as e:
            last_exc = e
            log.warning("%s attempt %d/%d timed out", label, attempt, _MAX_RETRIES)
        except APIConnectionError as e:
            last_exc = e
            log.warning("%s attempt %d/%d connection error", label, attempt, _MAX_RETRIES)
        except APIStatusError as e:
            if e.status_code in _RETRIABLE_STATUS_CODES:
                last_exc = e
                log.warning("%s attempt %d/%d got %d", label, attempt, _MAX_RETRIES, e.status_code)
            else:
                raise
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(2 ** (attempt - 1))
    raise last_exc


# ---------------------------------------------------------------------------
# Gemini client (used when model starts with "gemini")
# ---------------------------------------------------------------------------

_gemini_client = None
_gemini_client_key: str = ""


def _get_gemini():
    global _gemini_client, _gemini_client_key
    from google import genai as _genai
    current_key = str(cfg.get("GEMINI_API_KEY", "") or "")
    if _gemini_client is None or current_key != _gemini_client_key:
        if not current_key:
            raise RuntimeError("GEMINI_API_KEY not configured")
        _gemini_client = _genai.Client(api_key=current_key)
        _gemini_client_key = current_key
    return _gemini_client


def _build_gemini_tools():
    """Convert _ORCHESTRATOR_TOOL_SCHEMAS (OpenAI JSON Schema) → Gemini FunctionDeclaration list."""
    from google.genai import types as gt

    _type_map = {
        "string": gt.Type.STRING,
        "number": gt.Type.NUMBER,
        "integer": gt.Type.INTEGER,
        "boolean": gt.Type.BOOLEAN,
        "array": gt.Type.ARRAY,
        "object": gt.Type.OBJECT,
    }

    def _schema(prop: dict) -> gt.Schema:
        t = _type_map.get(prop.get("type", "string"), gt.Type.STRING)
        kwargs: dict = {"type": t, "description": prop.get("description", "")}
        if t == gt.Type.ARRAY and "items" in prop:
            items_type = _type_map.get(prop["items"].get("type", "string"), gt.Type.STRING)
            kwargs["items"] = gt.Schema(type=items_type)
        if t == gt.Type.OBJECT and prop.get("properties"):
            kwargs["properties"] = {k: _schema(v) for k, v in prop["properties"].items()}
        if "enum" in prop:
            kwargs["enum"] = [str(e) for e in prop["enum"]]
        return gt.Schema(**kwargs)

    declarations = []
    for tool in _ORCHESTRATOR_TOOL_SCHEMAS:
        params = tool.get("parameters", {})
        props = params.get("properties", {})
        required = params.get("required", [])
        param_schema = gt.Schema(
            type=gt.Type.OBJECT,
            properties={k: _schema(v) for k, v in props.items()} if props else {},
            required=required,
        )
        declarations.append(gt.FunctionDeclaration(
            name=tool["name"],
            description=tool.get("description", ""),
            parameters=param_schema,
        ))

    return [gt.Tool(function_declarations=declarations)]


def _get_cached_tokens(resp) -> int:
    try:
        return resp.usage.input_tokens_details.cached_tokens or 0
    except (AttributeError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Context dataclass
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorContext:
    run_id: int
    client_id: int
    group_id: int
    client_name: str
    client_type: str | None
    mode: str
    contacts_recorded: list[dict] = field(default_factory=list)
    ig_handle_saved: str | None = None
    sub_agent_calls: list[dict] = field(default_factory=list)  # audit trail
    tool_calls_made: list[str] = field(default_factory=list)
    tool_call_count: int = 0
    tools_that_worked: list[str] = field(default_factory=list)
    tools_that_failed: list[str] = field(default_factory=list)
    done_called: bool = False
    done_status: str = "not_found"
    done_summary: str = ""
    last_verify_quality: str = "good"       # from verify_contacts_batch
    last_verify_rejected_count: int = 0     # how many were rejected
    patterns_learned: dict = field(default_factory=dict)  # from mark_done
    retry_count: int = 0                    # total retries across all agents


@dataclass
class OrchestratorResult:
    contacts_recorded: list[dict]
    ig_handle: str | None
    sub_agent_calls: list[dict]
    tools_that_worked: list[str]
    tools_that_failed: list[str]
    status: str  # "found" | "partial" | "not_found"
    summary: str
    total_tokens: int
    duration_seconds: float
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Tool Definitions (JSON Schema for OpenAI function calling)
# ---------------------------------------------------------------------------

_ORCHESTRATOR_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "name": "spawn_web_search_agent",
        "description": "Spawn a specialist agent to search for the company's official website and extract contact info (email, WA phone, website URL). Returns summarized contacts found.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company or organization name to search for"},
                "hints": {"type": "object", "description": "Optional hints like client_type", "additionalProperties": True},
            },
            "required": ["company_name"],
        },
    },
    {
        "type": "function",
        "name": "spawn_registry_agent",
        "description": "Spawn a specialist agent to search official Indonesian registries (BNSP for LSP, JDIH for government, Asosiasi for associations). Very effective for lsp_p1/p2/p3 and kementerian types.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "client_type": {"type": "string", "description": "Client type: lsp_p1, lsp_p2, lsp_p3, kementerian, lembaga_negara, asosiasi"},
            },
            "required": ["company_name"],
        },
    },
    {
        "type": "function",
        "name": "spawn_instagram_agent",
        "description": "Spawn a specialist agent to find the company's Instagram account and extract WA phone numbers from post images using OCR. Most effective for finding WA phone with PIC name.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to find on Instagram"},
                "website_url": {"type": "string", "description": "Optional: company website URL (helps find IG link in social links)"},
            },
            "required": ["company_name"],
        },
    },
    {
        "type": "function",
        "name": "spawn_gemini_agent",
        "description": "LAST RESORT: Spawn a Gemini grounded search agent using Google Search. Use only when all other agents failed to find the required contacts.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "gaps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of missing contact types: e.g. ['wa_phone', 'email']"
                },
            },
            "required": ["company_name", "gaps"],
        },
    },
    {
        "type": "function",
        "name": "get_memory",
        "description": "Get long-term memory: group strategy lessons, tool success rates, and global lessons for this client type. Call this FIRST before spawning any agents.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_previous_attempts",
        "description": "Get episodic memory: previous search attempts for THIS specific client. Includes what was tried before and what failed. Call early to avoid repeating failed approaches.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "record_contact",
        "description": "Save a found contact to the database immediately. Call this as soon as a sub-agent returns contacts.",
        "parameters": {
            "type": "object",
            "properties": {
                "contact_type": {"type": "string", "enum": ["wa_phone", "email", "website"], "description": "Type of contact"},
                "value": {"type": "string", "description": "The contact value (phone number, email, or URL)"},
                "source_url": {"type": "string", "description": "URL where this contact was found"},
                "confidence": {"type": "number", "description": "Confidence score 0.0-1.0"},
                "pic_name": {"type": "string", "description": "Person in charge name (optional, for wa_phone type)"},
                "source_type": {"type": "string", "description": "Source type: website, ig_post, registry, gemini"},
            },
            "required": ["contact_type", "value", "confidence"],
        },
    },
    {
        "type": "function",
        "name": "record_ig_handle",
        "description": "Save the confirmed Instagram handle to the database.",
        "parameters": {
            "type": "object",
            "properties": {
                "handle": {"type": "string", "description": "Instagram handle (without @)"},
                "profile_url": {"type": "string", "description": "Instagram profile URL"},
                "confidence": {"type": "number", "description": "Confidence score 0.0-1.0"},
            },
            "required": ["handle", "confidence"],
        },
    },
    {
        "type": "function",
        "name": "verify_contacts_batch",
        "description": (
            "Evaluasi setiap kontak yang dikembalikan sub-agent SEBELUM merekam ke database. "
            "Panggil ini SETELAH setiap sub-agent return, SEBELUM record_contact. "
            "Berikan verdict untuk setiap kontak: accept/reject/uncertain."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "verdicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "contact_type": {"type": "string"},
                            "value": {"type": "string"},
                            "source_url": {"type": "string"},
                            "verdict": {"type": "string", "enum": ["accept", "reject", "uncertain"]},
                            "reason": {"type": "string", "description": "Mengapa accept/reject/uncertain"},
                            "adjusted_confidence": {"type": "number"},
                        },
                        "required": ["contact_type", "value", "verdict", "reason"],
                    },
                },
                "overall_quality": {
                    "type": "string",
                    "enum": ["good", "mixed", "poor"],
                    "description": "good=hasil bersih; mixed=ada yg baik ada yg buruk; poor=mayoritas tidak valid",
                },
            },
            "required": ["verdicts", "overall_quality"],
        },
    },
    {
        "type": "function",
        "name": "request_retry",
        "description": (
            "Re-spawn sub-agent dengan pendekatan yang lebih baik setelah verify_contacts_batch "
            "menunjukkan overall_quality='poor' atau tidak ada kontak valid. Maximum 1x per tipe agent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "enum": ["spawn_web_search_agent", "spawn_instagram_agent", "spawn_registry_agent", "spawn_gemini_agent"],
                },
                "reason": {"type": "string", "description": "Mengapa retry diperlukan"},
                "refined_hints": {
                    "type": "object",
                    "properties": {
                        "refined_query": {"type": "string", "description": "Query alternatif yang lebih spesifik"},
                        "avoid_source_domains": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Domain yang terbukti tidak relevan",
                        },
                        "target_contact_type": {"type": "string", "description": "Fokus: wa_phone/email/website"},
                        "force_domain": {"type": "string", "description": "Coba langsung ke domain ini dulu"},
                    },
                },
            },
            "required": ["agent", "reason"],
        },
    },
    {
        "type": "function",
        "name": "mark_done",
        "description": "TERMINAL: End this discovery run. MUST be called when done (goal achieved or all approaches exhausted). Triggers learning and updates database.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["found", "partial", "not_found"], "description": "found=has WA or email, partial=some contacts but not ideal, not_found=nothing"},
                "summary": {"type": "string", "description": "Brief 1-2 sentence description of what was found and what approach worked"},
                "tools_that_worked": {"type": "array", "items": {"type": "string"}, "description": "Sub-agent names that produced contacts"},
                "tools_that_failed": {"type": "array", "items": {"type": "string"}, "description": "Sub-agent names that found nothing"},
                "patterns_learned": {
                    "type": "object",
                    "description": "Pola yang dipelajari dari run ini",
                    "properties": {
                        "reliable_sources": {
                            "type": "array", "items": {"type": "string"},
                            "description": "Domain/sumber yang terbukti menghasilkan kontak valid",
                        },
                        "red_flag_patterns": {
                            "type": "array", "items": {"type": "string"},
                            "description": "Pola yang harus dihindari di run berikutnya",
                        },
                        "effective_approach": {
                            "type": "string",
                            "description": "Pendekatan paling efektif untuk tipe klien ini",
                        },
                    },
                },
            },
            "required": ["status", "summary"],
        },
    },
]

_TERMINAL_TOOLS = {"mark_done"}


# ---------------------------------------------------------------------------
# MarketingOrchestratorAgent
# ---------------------------------------------------------------------------

class MarketingOrchestratorAgent:
    """
    High-level orchestrator using a capable model (default: gpt-4.5-preview).
    Spawns sub-agents, synthesizes results, learns from outcomes.

    Context window stays clean because spawn_* tools return only
    SUMMARIZED results (not raw HTML/posts/images).
    """

    async def run(
        self,
        client: dict,
        run_id: int,
        mode: str,
        episodic_memory: dict,
        long_term_context: dict,
    ) -> OrchestratorResult:
        start = time.monotonic()
        client_id = int(client["id"])
        group_id = int(client.get("group_id", 0))
        client_name = str(client["name"])

        # Resolve client_type from group if not on client
        extra_data = client.get("extra_data") or {}
        if isinstance(extra_data, str):
            try:
                extra_data = json.loads(extra_data)
            except Exception:
                extra_data = {}
        client_type = extra_data.get("client_type")
        if not client_type:
            group = await mkt.get_group(group_id)
            if group:
                client_type = group.get("client_type")

        context = OrchestratorContext(
            run_id=run_id,
            client_id=client_id,
            group_id=group_id,
            client_name=client_name,
            client_type=client_type,
            mode=mode,
        )

        # Build system prompt with memory injected
        system_prompt = build_orchestrator_prompt(
            client_name=client_name,
            client_type=client_type,
            episodic_memory=episodic_memory,
            long_term_context=long_term_context,
        )

        # Initial user message
        input_items = [{
            "role": "user",
            "content": (
                f"Temukan kontak untuk: {client_name}\n"
                f"Tipe: {client_type or 'umum'}\n"
                f"Mulai dengan get_memory dan get_previous_attempts untuk cek konteks sebelumnya."
            )
        }]

        # Load previous_response_id for session chaining (fetched directly from DB)
        previous_response_id: str | None = None
        try:
            previous_response_id = await _get_run_last_response_id(run_id)
        except Exception:
            pass

        model_name = cfg.MARKETING_ORCHESTRATOR_MODEL.lower()
        use_gemini = model_name.startswith("gemini")

        try:
            if use_gemini:
                result = await self._run_react_loop_gemini(
                    instructions=system_prompt,
                    input_items=input_items,
                    context=context,
                )
            else:
                result = await self._run_react_loop(
                    instructions=system_prompt,
                    input_items=input_items,
                    context=context,
                    previous_response_id=previous_response_id,
                )

            duration = time.monotonic() - start

            # Trigger learning if mark_done was called
            if context.done_called:
                try:
                    await write_post_run_lessons(
                        group_id=group_id,
                        client_type=client_type,
                        run_summary={
                            "status": context.done_status,
                            "tools_that_worked": context.tools_that_worked,
                            "tools_that_failed": context.tools_that_failed,
                            "contacts_found": len(context.contacts_recorded),
                            "summary": context.done_summary,
                            "patterns_learned": context.patterns_learned,  # NEW
                        },
                    )
                except Exception as learn_err:
                    log.warning("[OrchestratorAgent] write_post_run_lessons failed: %s", learn_err)

            return OrchestratorResult(
                contacts_recorded=context.contacts_recorded,
                ig_handle=context.ig_handle_saved,
                sub_agent_calls=context.sub_agent_calls,
                tools_that_worked=context.tools_that_worked,
                tools_that_failed=context.tools_that_failed,
                status=context.done_status,
                summary=context.done_summary or result.get("response_text", ""),
                total_tokens=result.get("total_tokens", 0),
                duration_seconds=duration,
            )

        except Exception as exc:
            duration = time.monotonic() - start
            log.error("[OrchestratorAgent] run failed for %s: %s", client_name, exc)
            return OrchestratorResult(
                contacts_recorded=context.contacts_recorded,
                ig_handle=context.ig_handle_saved,
                sub_agent_calls=context.sub_agent_calls,
                tools_that_worked=context.tools_that_worked,
                tools_that_failed=context.tools_that_failed,
                status="error",
                summary=str(exc),
                total_tokens=0,
                duration_seconds=duration,
                error_message=str(exc),
            )

    async def _run_react_loop(
        self,
        instructions: str,
        input_items: list[dict],
        context: OrchestratorContext,
        previous_response_id: str | None = None,
    ) -> dict:
        """ReAct loop — same pattern as react_agent.py._run_react_loop()."""
        client = _get_openai()
        model = cfg.MARKETING_ORCHESTRATOR_MODEL
        max_iterations = cfg.MARKETING_AGENT_MAX_TOOL_ITERATIONS
        total_tokens = 0

        def _track_usage(resp) -> None:
            nonlocal total_tokens
            if resp.usage:
                total_tokens += resp.usage.input_tokens + resp.usage.output_tokens

        kwargs: dict = {
            "model": model,
            "instructions": instructions,
            "input": input_items,
            "store": True,
            "tools": _ORCHESTRATOR_TOOL_SCHEMAS,
            **responses_kwargs(model, temperature=0.1, max_output_tokens=2048),
        }
        if previous_response_id:
            kwargs["previous_response_id"] = previous_response_id

        response = await _api_call_with_retry(
            lambda: client.responses.create(**kwargs),
            label="OrchestratorAgent initial",
        )
        _track_usage(response)

        iterations = 0
        terminal_reached = False

        while iterations < max_iterations:
            function_calls = [item for item in response.output if item.type == "function_call"]

            if not function_calls:
                break

            # Parallel tool execution
            async def _run_one_tool(fc) -> tuple[dict, bool]:
                name = fc.name
                try:
                    args = json.loads(fc.arguments)
                except json.JSONDecodeError:
                    args = {}
                log.info(
                    "[OrchestratorAgent] tool call: %s(%s)",
                    name,
                    {k: v for k, v in args.items() if k != "hints"},
                )
                try:
                    result_str = await self._execute_tool(name, args, context)
                except Exception as tool_err:
                    log.error("[OrchestratorAgent] tool %s error: %s", name, tool_err)
                    result_str = json.dumps({"error": f"Tool {name} failed: {tool_err}"})
                output = {
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": result_str,
                }
                return output, name in _TERMINAL_TOOLS

            _tool_results = await asyncio.gather(*[_run_one_tool(fc) for fc in function_calls])

            function_outputs = []
            terminal_reached = False
            for _output, _is_terminal in _tool_results:
                function_outputs.append(_output)
                if _is_terminal:
                    terminal_reached = True

            # Update context after gather (avoids concurrent list mutation)
            for fc in function_calls:
                context.tool_calls_made.append(fc.name)
                context.tool_call_count += 1

            # Deduplicate contacts_recorded (parallel record_contact race edge case)
            _seen: set[str] = set()
            context.contacts_recorded = [
                c for c in context.contacts_recorded
                if c["value"] not in _seen and not _seen.add(c["value"])  # type: ignore[func-returns-value]
            ]

            next_kwargs: dict = {
                "model": model,
                "input": function_outputs,
                "previous_response_id": response.id,
                "store": True,
                **responses_kwargs(model, temperature=0.1, max_output_tokens=2048),
            }
            if not terminal_reached:
                next_kwargs["tools"] = _ORCHESTRATOR_TOOL_SCHEMAS

            # Save response_id for session chaining
            try:
                await db.update_marketing_run_response_id(context.run_id, response.id)
            except Exception:
                pass

            _nk = next_kwargs
            response = await _api_call_with_retry(
                lambda: client.responses.create(**_nk),
                label="OrchestratorAgent loop",
            )
            _track_usage(response)
            iterations += 1

            if terminal_reached:
                break

        # Extract response text
        response_text = ""
        try:
            response_text = response.output_text
        except (ValueError, AttributeError):
            pass

        return {"response_text": response_text, "total_tokens": total_tokens}

    async def _run_react_loop_gemini(
        self,
        instructions: str,
        input_items: list[dict],
        context: OrchestratorContext,
    ) -> dict:
        """ReAct loop using Gemini function calling (multi-turn chat)."""
        from google import genai as _genai
        from google.genai import types as gt

        client = _get_gemini()
        model = cfg.MARKETING_ORCHESTRATOR_MODEL
        max_iterations = cfg.MARKETING_AGENT_MAX_TOOL_ITERATIONS
        total_tokens = 0

        gemini_tools = _build_gemini_tools()
        config = gt.GenerateContentConfig(
            tools=gemini_tools,
            system_instruction=instructions,
            temperature=0.1,
            max_output_tokens=4096,
        )

        # Initial message text
        initial_text = input_items[0]["content"] if input_items else "Mulai discovery."

        # Create a chat session
        chat = await asyncio.to_thread(
            client.chats.create,
            model=model,
            config=config,
        )

        # Send initial message
        response = await asyncio.to_thread(chat.send_message, initial_text)

        if response.usage_metadata:
            total_tokens += (response.usage_metadata.total_token_count or 0)

        iterations = 0
        response_text = ""

        while iterations < max_iterations:
            # Collect function calls from this response
            function_calls = []
            for part in (response.candidates[0].content.parts if response.candidates else []):
                if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                    function_calls.append(part.function_call)
                elif hasattr(part, "text") and part.text:
                    response_text = part.text

            if not function_calls:
                break

            # Parallel tool execution
            async def _run_one_tool_gemini(fc) -> tuple[Any, bool]:
                name = fc.name
                args = dict(fc.args) if fc.args else {}
                log.info(
                    "[OrchestratorAgent/Gemini] tool call: %s(%s)",
                    name,
                    {k: v for k, v in args.items() if k != "hints"},
                )
                try:
                    result_str = await self._execute_tool(name, args, context)
                except Exception as tool_err:
                    log.error("[OrchestratorAgent/Gemini] tool %s error: %s", name, tool_err)
                    result_str = json.dumps({"error": f"Tool {name} failed: {tool_err}"})
                part = gt.Part.from_function_response(
                    name=name,
                    response={"result": result_str},
                )
                return part, name in _TERMINAL_TOOLS

            _tool_results = await asyncio.gather(*[_run_one_tool_gemini(fc) for fc in function_calls])

            tool_response_parts = []
            terminal_reached = False
            for _part, _is_terminal in _tool_results:
                tool_response_parts.append(_part)
                if _is_terminal:
                    terminal_reached = True

            # Update context after gather (avoids concurrent list mutation)
            for fc in function_calls:
                context.tool_calls_made.append(fc.name)
                context.tool_call_count += 1

            # Deduplicate contacts_recorded (parallel record_contact race edge case)
            _seen: set[str] = set()
            context.contacts_recorded = [
                c for c in context.contacts_recorded
                if c["value"] not in _seen and not _seen.add(c["value"])  # type: ignore[func-returns-value]
            ]

            # Send all tool results back in one message
            response = await asyncio.to_thread(chat.send_message, tool_response_parts)

            if response.usage_metadata:
                total_tokens += (response.usage_metadata.total_token_count or 0)

            iterations += 1

            if terminal_reached:
                break

        # Try to get final text response
        try:
            for part in (response.candidates[0].content.parts if response.candidates else []):
                if hasattr(part, "text") and part.text:
                    response_text = part.text
                    break
        except Exception:
            pass

        return {"response_text": response_text, "total_tokens": total_tokens}

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: dict,
        context: OrchestratorContext,
    ) -> str:
        """Dispatch tool calls to sub-agents or DB operations."""

        # ------------------------------------------------------------------ #
        # SPAWN TOOLS — call sub-agents, return summarized JSON               #
        # ------------------------------------------------------------------ #

        if tool_name == "spawn_web_search_agent":
            company_name = arguments.get("company_name", context.client_name)
            hints = arguments.get("hints", {})
            agent = WebSearchSubAgent()
            result = await agent.run(
                company_name=company_name,
                client_type=context.client_type,
                extra_data=hints.get("extra_data"),
            )
            self._record_sub_agent_call(context, "spawn_web_search_agent", result)
            return self._summarize_result(result)

        if tool_name == "spawn_registry_agent":
            company_name = arguments.get("company_name", context.client_name)
            client_type = arguments.get("client_type", context.client_type)
            agent = RegistrySearchSubAgent()
            result = await agent.run(
                company_name=company_name,
                client_type=client_type,
            )
            self._record_sub_agent_call(context, "spawn_registry_agent", result)
            return self._summarize_result(result)

        if tool_name == "spawn_instagram_agent":
            company_name = arguments.get("company_name", context.client_name)
            website_url = arguments.get("website_url")
            agent = InstagramSubAgent()
            result = await agent.run(
                company_name=company_name,
                website_url=website_url,
            )
            self._record_sub_agent_call(context, "spawn_instagram_agent", result)
            # Auto-save IG handle if found
            if result.ig_handle and not context.ig_handle_saved:
                try:
                    await mkt.save_client_instagram_profile(
                        context.client_id,
                        result.ig_handle,
                        f"https://www.instagram.com/{result.ig_handle}/",
                    )
                    context.ig_handle_saved = result.ig_handle
                except Exception as e:
                    log.warning("[OrchestratorAgent] Failed to save IG handle: %s", e)
            return self._summarize_result(result)

        if tool_name == "spawn_gemini_agent":
            company_name = arguments.get("company_name", context.client_name)
            gaps = arguments.get("gaps", [])
            agent = GeminiGapFillSubAgent()
            result = await agent.run(
                company_name=company_name,
                gaps=gaps,
                already_found=context.contacts_recorded,
            )
            self._record_sub_agent_call(context, "spawn_gemini_agent", result)
            return self._summarize_result(result)

        # ------------------------------------------------------------------ #
        # MEMORY TOOLS                                                        #
        # ------------------------------------------------------------------ #

        if tool_name == "get_memory":
            try:
                lt = await get_long_term_context(context.group_id, context.client_type)
                progress = lt.get("group_progress", {})
                lessons = lt.get("group_lessons", [])[:3]
                global_lessons = lt.get("global_lessons", [])[:3]
                tool_rates = lt.get("tool_success_rates", {})

                summary = {
                    "group_progress": (
                        f"{progress.get('completed', 0)}/{progress.get('total', 0)} selesai, "
                        f"hit rate {progress.get('found_rate', 0):.0%}"
                    ),
                    "group_lessons": lessons,
                    "global_lessons": [
                        f"{l['insight']} \u2192 {l['strategy']}" for l in global_lessons
                    ],
                    "tool_success_rates": {
                        k: f"{v['produced_contacts']}/{v['spawns']} contact/spawn"
                        for k, v in tool_rates.items()
                    },
                }
                return json.dumps(summary, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": f"get_memory failed: {e}", "group_lessons": [], "global_lessons": []})

        if tool_name == "get_previous_attempts":
            try:
                ep = await get_client_episodic_memory(context.client_id)
                summary = {
                    "has_prior_run": ep.get("has_prior_run", False),
                    "contacts_already_found": ep.get("contacts_already_found", []),
                    "ig_handles_tried": ep.get("ig_handles_tried", []),
                    "previous_runs_summary": [
                        {
                            "mode": r.get("mode"),
                            "state": r.get("state"),
                            "contacts_found": r.get("contacts_found", 0),
                            "tools_that_worked": r.get("tools_that_worked", []),
                        }
                        for r in ep.get("previous_runs", [])[:2]
                    ],
                }
                return json.dumps(summary, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": f"get_previous_attempts failed: {e}", "has_prior_run": False})

        # ------------------------------------------------------------------ #
        # RECORDING TOOLS                                                     #
        # ------------------------------------------------------------------ #

        if tool_name == "record_contact":
            contact_type = arguments.get("contact_type", "")
            value = str(arguments.get("value", "")).strip()
            source_url = arguments.get("source_url", "") or None
            confidence = float(arguments.get("confidence", 0.7))
            pic_name = arguments.get("pic_name", "") or None
            source_type = arguments.get("source_type", "agent") or "agent"

            if not value or not contact_type:
                return json.dumps({"error": "contact_type and value are required"})

            # Avoid recording duplicates in this run
            existing_values = {c.get("value") for c in context.contacts_recorded}
            if value in existing_values:
                return json.dumps({"status": "skipped", "reason": "duplicate in this run"})

            try:
                # Use upsert_contact_result directly to support confidence + pic_name
                await mkt.upsert_contact_result(
                    context.client_id,
                    contact_type=contact_type,
                    value=value,
                    source_url=source_url,
                    source_type=source_type,
                    confidence=confidence,
                    pic_name=pic_name,
                )
                context.contacts_recorded.append({
                    "contact_type": contact_type,
                    "value": value,
                    "confidence": confidence,
                    "pic_name": pic_name or "",
                })
                # Record evidence
                await mkt.add_orchestration_evidence(
                    context.run_id,
                    context.client_id,
                    "agent_recording",
                    "contact_candidate",
                    source_url=source_url,
                    source_type=source_type,
                    value=value,
                    confidence=confidence,
                    status="accepted",
                    payload={"contact_type": contact_type, "pic_name": pic_name},
                )
                return json.dumps({"status": "saved", "contact_type": contact_type, "value": value})
            except Exception as e:
                log.warning("[OrchestratorAgent] record_contact failed: %s", e)
                return json.dumps({"error": f"Failed to save: {e}"})

        if tool_name == "record_ig_handle":
            handle = arguments.get("handle", "").strip().lstrip("@")
            profile_url = arguments.get("profile_url") or f"https://www.instagram.com/{handle}/"
            confidence = float(arguments.get("confidence", 0.8))
            if not handle:
                return json.dumps({"error": "handle is required"})
            try:
                await mkt.save_client_instagram_profile(context.client_id, handle, profile_url)
                context.ig_handle_saved = handle
                return json.dumps({"status": "saved", "handle": handle})
            except Exception as e:
                return json.dumps({"error": f"Failed to save IG handle: {e}"})

        # ------------------------------------------------------------------ #
        # TERMINAL TOOL                                                       #
        # ------------------------------------------------------------------ #

        if tool_name == "mark_done":
            status = arguments.get("status", "not_found")
            summary = arguments.get("summary", "")
            context.tools_that_worked = arguments.get("tools_that_worked", [])
            context.tools_that_failed = arguments.get("tools_that_failed", [])
            context.done_called = True
            context.done_status = status
            context.done_summary = summary
            context.patterns_learned = arguments.get("patterns_learned", {})

            # Record final evidence summary
            try:
                await mkt.add_orchestration_evidence(
                    context.run_id,
                    context.client_id,
                    "finalize",
                    "agent_summary",
                    status=status,
                    value=summary,
                    payload={
                        "contacts_found": len(context.contacts_recorded),
                        "tools_that_worked": context.tools_that_worked,
                        "tools_that_failed": context.tools_that_failed,
                    },
                )
            except Exception:
                pass

            return json.dumps({
                "status": "done",
                "contacts_recorded": len(context.contacts_recorded),
                "final_status": status,
            })

        if tool_name == "verify_contacts_batch":
            return await self._handle_verify_contacts_batch(arguments, context)

        if tool_name == "request_retry":
            return await self._handle_request_retry(arguments, context)

        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    async def _handle_verify_contacts_batch(self, arguments: dict, context: OrchestratorContext) -> str:
        verdicts = arguments.get("verdicts", [])
        overall_quality = arguments.get("overall_quality", "mixed")

        accepted, rejected, uncertain = [], [], []
        for v in verdicts:
            try:
                contact_value = v.get("value") or v.get("contact_value")
                await mkt.add_orchestration_evidence(
                    context.run_id,
                    context.client_id,
                    "decide",
                    f"contact_verdict_{v['verdict']}",
                    source_url=v.get("source_url"),
                    value=contact_value,
                    confidence=float(v.get("adjusted_confidence") or 0.0),
                    status=v["verdict"],
                    reason=v.get("reason"),
                    payload={
                        "contact_type": v.get("contact_type"),
                        "value": contact_value,
                        "source_url": v.get("source_url"),
                        "reason": v.get("reason"),
                        "adjusted_confidence": v.get("adjusted_confidence"),
                    },
                )
            except Exception as e:
                log.warning("[OrchestratorAgent] verify_contacts_batch evidence failed: %s", e)

            if v["verdict"] == "accept":
                accepted.append(v)
            elif v["verdict"] == "reject":
                rejected.append(v)
            else:
                uncertain.append(v)

        context.last_verify_quality = overall_quality
        context.last_verify_rejected_count = len(rejected)

        msg = "Lanjutkan dengan record_contact hanya untuk kontak 'accepted'."
        if overall_quality == "poor":
            msg += " Pertimbangkan request_retry karena majority contacts ditolak."

        return json.dumps({
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "uncertain_count": len(uncertain),
            "overall_quality": overall_quality,
            "accepted_contacts": accepted,
            "message": msg,
        }, ensure_ascii=False)

    async def _handle_request_retry(self, arguments: dict, context: OrchestratorContext) -> str:
        agent = arguments["agent"]
        reason = arguments.get("reason", "")
        refined_hints = arguments.get("refined_hints", {})

        retry_key = f"retry_{agent}"
        if retry_key in context.tool_calls_made:
            return json.dumps({
                "status": "denied",
                "reason": f"Agent {agent} sudah pernah di-retry. Coba agent lain atau panggil mark_done.",
            })

        try:
            await mkt.add_orchestration_evidence(
                context.run_id,
                context.client_id,
                "repair",
                "retry_requested",
                value=agent,
                status="approved",
                payload={"reason": reason, "refined_hints": refined_hints},
            )
        except Exception as e:
            log.warning("[OrchestratorAgent] request_retry evidence failed: %s", e)

        context.tool_calls_made.append(retry_key)
        context.retry_count += 1

        return json.dumps({
            "status": "approved",
            "message": f"Retry disetujui. Panggil {agent} sekarang dengan hints berikut.",
            "suggested_hints": refined_hints,
            "instruction": (
                f"Panggil {agent} segera dengan hints yang telah di-refine. "
                "Setelah hasilnya kembali, lakukan verify_contacts_batch lagi."
            ),
        }, ensure_ascii=False)

    def _summarize_result(self, result: SubAgentResult) -> str:
        """Convert SubAgentResult to compact JSON string for orchestrator context."""
        compact_contacts = [
            {
                "type": c["type"],
                "value": c["value"],
                "confidence": round(c["confidence"], 2),
                "source_url": c.get("source_url", ""),
                "source_type": c.get("source_type", ""),
                **({"pic_name": c["pic_name"]} if c.get("pic_name") else {}),
            }
            for c in result.contacts
        ]
        return json.dumps({
            "contacts_found": compact_contacts,
            "contact_count": len(result.contacts),
            "ig_handle": result.ig_handle,
            "summary": result.summary,
            "success": result.success,
            **({"error": result.error} if result.error else {}),
        }, ensure_ascii=False)

    def _record_sub_agent_call(
        self,
        context: OrchestratorContext,
        agent_name: str,
        result: SubAgentResult,
    ) -> None:
        """Audit trail for sub-agent calls."""
        context.sub_agent_calls.append({
            "agent": agent_name,
            "contacts_found": len(result.contacts),
            "ig_handle": result.ig_handle,
            "summary": result.summary,
            "success": result.success,
            "duration_seconds": round(result.duration_seconds, 1),
        })
        if result.contacts:
            if agent_name not in context.tools_that_worked:
                context.tools_that_worked.append(agent_name)
        elif result.error:
            if agent_name not in context.tools_that_failed:
                context.tools_that_failed.append(agent_name)


# ---------------------------------------------------------------------------
# Helper: fetch last_response_id from DB for session chaining
# ---------------------------------------------------------------------------

async def _get_run_last_response_id(run_id: int) -> str | None:
    """Read last_response_id from marketing_orchestration_runs directly."""
    import aiosqlite
    from orchestrator.config import DATABASE_PATH
    async with aiosqlite.connect(DATABASE_PATH) as _db:
        cursor = await _db.execute(
            "SELECT last_response_id FROM marketing_orchestration_runs WHERE id=?",
            (run_id,),
        )
        row = await cursor.fetchone()
    if row and row[0]:
        return str(row[0])
    return None
