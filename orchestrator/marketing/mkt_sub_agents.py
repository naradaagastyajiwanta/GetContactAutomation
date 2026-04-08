"""
Specialized sub-agent workers for marketing contact discovery.

WebSearchSubAgent and InstagramSubAgent now use LLM ReAct loops (model: MARKETING_SUB_AGENT_MODEL)
with graceful fallback to the deterministic pipeline if the LLM call fails or returns nothing.

RegistrySearchSubAgent and GeminiGapFillSubAgent remain deterministic (their logic is already smart).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError

from orchestrator.config import log, cfg, responses_kwargs
from .errors import QuotaExhaustedException
from orchestrator.osint.tools import (
    web_search,
    fetch_page,
    extract_text_from_html,
    extract_emails,
    extract_phones_from_text,
    extract_social_links,
)
from . import search as search_flow
from .mkt_prompts import (
    build_web_search_prompt,
    build_instagram_prompt,
    build_website_scraper_prompt,
    build_chrome_devtools_ig_prompt,
)
from orchestrator.mcp_browser_client import get_mcp_browser, MCPBrowserClient, MCPBrowserError


# ---------------------------------------------------------------------------
# OpenAI client singleton for sub-agents
# ---------------------------------------------------------------------------

_sub_agent_client: AsyncOpenAI | None = None
_sub_agent_client_key: str = ""


def _get_sub_agent_openai() -> AsyncOpenAI:
    global _sub_agent_client, _sub_agent_client_key
    current_key = cfg.OPENAI_API_KEY
    if _sub_agent_client is None or current_key != _sub_agent_client_key:
        _sub_agent_client = AsyncOpenAI(api_key=current_key)
        _sub_agent_client_key = current_key
    return _sub_agent_client


# ---------------------------------------------------------------------------
# Gemini client singleton for sub-agents
# ---------------------------------------------------------------------------

_sub_agent_gemini_client = None
_sub_agent_gemini_key: str = ""


def _get_sub_agent_gemini():
    global _sub_agent_gemini_client, _sub_agent_gemini_key
    from google import genai as _genai
    current_key = str(cfg.get("GEMINI_API_KEY", "") or "")
    if _sub_agent_gemini_client is None or current_key != _sub_agent_gemini_key:
        if not current_key:
            raise RuntimeError("GEMINI_API_KEY not configured")
        _sub_agent_gemini_client = _genai.Client(api_key=current_key)
        _sub_agent_gemini_key = current_key
    return _sub_agent_gemini_client


def _schemas_to_gemini_tools(tool_schemas: list[dict]):
    """Convert OpenAI JSON Schema tool list → Gemini FunctionDeclaration list."""
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
    for tool in tool_schemas:
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


def _llm_available() -> bool:
    """True if the configured sub-agent model has a working API key."""
    model = cfg.MARKETING_SUB_AGENT_MODEL.lower()
    if model.startswith("gemini"):
        return bool(cfg.get("GEMINI_API_KEY"))
    return bool(cfg.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Retry helpers for API calls
# ---------------------------------------------------------------------------

_SUB_AGENT_RETRIABLE_STATUS = {429, 500, 503}


async def _openai_call_with_retry(coro_factory, label: str = "SubAgent/OpenAI"):
    """Retry OpenAI Responses API calls on 429/500/503 with exponential backoff."""
    last_exc = None
    for attempt in range(1, 4):  # 3 attempts
        try:
            return await coro_factory()
        except APITimeoutError as e:
            last_exc = e
            log.warning("%s attempt %d/3 timed out", label, attempt)
        except APIConnectionError as e:
            last_exc = e
            log.warning("%s attempt %d/3 connection error", label, attempt)
        except APIStatusError as e:
            if e.status_code in _SUB_AGENT_RETRIABLE_STATUS:
                if "insufficient_quota" in str(e).lower():
                    raise QuotaExhaustedException(
                        "OpenAI API credit habis (insufficient_quota). Hubungi developer."
                    ) from e
                last_exc = e
                log.warning("%s attempt %d/3 got %d", label, attempt, e.status_code)
            else:
                raise
        if attempt < 3:
            await asyncio.sleep(2 ** (attempt - 1))
    raise last_exc


async def _gemini_call_with_retry(coro_factory, label: str = "SubAgent/Gemini"):
    """Retry Gemini API calls on 429/500/503 with exponential backoff."""
    last_exc = None
    for attempt in range(1, 4):  # 3 attempts
        try:
            return await coro_factory()
        except Exception as e:
            msg = str(e).lower()
            # Gemini errors come wrapped from asyncio.to_thread; detect by message or code
            code = getattr(e, "status_code", None) or getattr(e, "code", None)
            is_retriable = (
                (code in _SUB_AGENT_RETRIABLE_STATUS) or
                any(k in msg for k in ("quota", "429", "rate limit", "resource exhausted",
                                       "500", "503", "unavailable", "overloaded"))
            )
            if is_retriable:
                if any(k in msg for k in ("resource_exhausted", "insufficient_quota",
                                          "quota exceeded", "quota has been exceeded")):
                    raise QuotaExhaustedException(
                        "Gemini API credit habis (RESOURCE_EXHAUSTED). Hubungi developer."
                    ) from e
                last_exc = e
                log.warning("%s attempt %d/3 retriable error: %s", label, attempt, str(e)[:120])
            else:
                raise
        if attempt < 3:
            await asyncio.sleep(2 ** (attempt - 1))
    raise last_exc


# ---------------------------------------------------------------------------
# Generic sub-agent LLM loop — routes to Gemini or OpenAI based on model
# ---------------------------------------------------------------------------

async def _run_sub_agent_llm_loop(
    system_prompt: str,
    initial_message: str,
    tool_schemas: list[dict],
    terminal_tools: set[str],
    tool_dispatch: dict[str, Callable],
    max_iterations: int = 8,
    model_override: str | None = None,
) -> tuple[dict, int]:
    """
    Generic ReAct loop for sub-agents.
    Routes to Gemini or OpenAI Responses API based on MARKETING_SUB_AGENT_MODEL.
    Returns (terminal_tool_args, total_tokens).
    """
    model = model_override or cfg.MARKETING_SUB_AGENT_MODEL
    if model.lower().startswith("gemini"):
        return await _run_sub_agent_llm_loop_gemini(
            system_prompt=system_prompt,
            initial_message=initial_message,
            tool_schemas=tool_schemas,
            terminal_tools=terminal_tools,
            tool_dispatch=tool_dispatch,
            max_iterations=max_iterations,
            model_override=model,
        )

    # --- OpenAI Responses API path ---
    client = _get_sub_agent_openai()
    total_tokens = 0

    _init_kwargs = dict(
        model=model,
        instructions=system_prompt,
        input=[{"role": "user", "content": initial_message}],
        tools=tool_schemas,
        store=True,
        **responses_kwargs(model, temperature=0.2, max_output_tokens=1500),
    )
    response = await _openai_call_with_retry(
        lambda: client.responses.create(**_init_kwargs),
        label="SubAgent/OpenAI initial",
    )
    if response.usage:
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

    for _ in range(max_iterations):
        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            break

        outputs = []
        terminal_args: dict | None = None

        for fc in function_calls:
            name = fc.name
            try:
                args = json.loads(fc.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}

            if name in terminal_tools:
                terminal_args = args
                result_str = json.dumps({"status": "done"})
            else:
                fn = tool_dispatch.get(name)
                if fn is None:
                    result_str = json.dumps({"error": f"Unknown tool: {name}"})
                else:
                    try:
                        result_str = await fn(args)
                    except Exception as exc:
                        log.warning("[SubAgentLLMLoop] tool %s error: %s", name, exc)
                        result_str = json.dumps({"error": str(exc)})

            outputs.append({
                "type": "function_call_output",
                "call_id": fc.call_id,
                "output": result_str,
            })

        if terminal_args is not None:
            return terminal_args, total_tokens

        next_kwargs: dict = {
            "model": model,
            "input": outputs,
            "previous_response_id": response.id,
            "store": True,
            **responses_kwargs(model, temperature=0.2, max_output_tokens=1500),
        }
        if not terminal_args:
            next_kwargs["tools"] = tool_schemas

        _nk = next_kwargs
        response = await _openai_call_with_retry(
            lambda: client.responses.create(**_nk),
            label="SubAgent/OpenAI loop",
        )
        if response.usage:
            total_tokens += response.usage.input_tokens + response.usage.output_tokens

    return {}, total_tokens


async def _run_sub_agent_llm_loop_gemini(
    system_prompt: str,
    initial_message: str,
    tool_schemas: list[dict],
    terminal_tools: set[str],
    tool_dispatch: dict[str, Callable],
    max_iterations: int = 8,
    model_override: str | None = None,
) -> tuple[dict, int]:
    """
    Gemini-based ReAct loop for sub-agents (mirrors _run_sub_agent_llm_loop).
    Uses google.genai chat API with function calling.
    Returns (terminal_tool_args, total_tokens).
    """
    from google.genai import types as gt

    client = _get_sub_agent_gemini()
    model = model_override or cfg.MARKETING_SUB_AGENT_MODEL
    total_tokens = 0

    gemini_tools = _schemas_to_gemini_tools(tool_schemas)
    config = gt.GenerateContentConfig(
        tools=gemini_tools,
        system_instruction=system_prompt,
        temperature=0.2,
        max_output_tokens=1500,
    )

    chat = await asyncio.to_thread(client.chats.create, model=model, config=config)
    response = await _gemini_call_with_retry(
        lambda: asyncio.to_thread(chat.send_message, initial_message),
        label="SubAgent/Gemini initial",
    )

    if response.usage_metadata:
        total_tokens += response.usage_metadata.total_token_count or 0

    for _ in range(max_iterations):
        function_calls = []
        for part in (response.candidates[0].content.parts if response.candidates else []):
            if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                function_calls.append(part.function_call)

        if not function_calls:
            break

        outputs = []
        terminal_args: dict | None = None

        for fc in function_calls:
            name = fc.name
            args = dict(fc.args) if fc.args else {}

            if name in terminal_tools:
                terminal_args = args
                result_str = json.dumps({"status": "done"})
            else:
                fn = tool_dispatch.get(name)
                if fn is None:
                    result_str = json.dumps({"error": f"Unknown tool: {name}"})
                else:
                    try:
                        result_str = await fn(args)
                    except Exception as exc:
                        log.warning("[SubAgentLLMLoop/Gemini] tool %s error: %s", name, exc)
                        result_str = json.dumps({"error": str(exc)})

            outputs.append(gt.Part.from_function_response(
                name=name,
                response={"result": result_str},
            ))

        if terminal_args is not None:
            return terminal_args, total_tokens

        _out = outputs
        response = await _gemini_call_with_retry(
            lambda: asyncio.to_thread(chat.send_message, _out),
            label="SubAgent/Gemini loop",
        )
        if response.usage_metadata:
            total_tokens += response.usage_metadata.total_token_count or 0

    return {}, total_tokens


# ---------------------------------------------------------------------------
# WebSearchSubAgent tool schemas
# ---------------------------------------------------------------------------

_WEB_SEARCH_AGENT_TOOLS: list[dict] = [
    {
        "type": "function",
        "name": "search_web",
        "description": "Cari di internet. Returns list of {title, link, snippet}.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Jumlah hasil (default 8)", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "fetch_page",
        "description": "Buka halaman web dan ekstrak teks bersih + email + telepon. Gunakan untuk /kontak, /about, /tentang-kami.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL yang akan di-fetch"},
            },
            "required": ["url"],
        },
    },
    {
        "type": "function",
        "name": "finish",
        "description": "TERMINAL: Selesai mencari. Kembalikan semua kontak yang ditemukan.",
        "parameters": {
            "type": "object",
            "properties": {
                "contacts": {
                    "type": "array",
                    "description": "Daftar kontak yang ditemukan",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["website", "email", "wa_phone"]},
                            "value": {"type": "string"},
                            "source_url": {"type": "string"},
                            "confidence": {"type": "number"},
                            "pic_name": {"type": "string"},
                        },
                        "required": ["type", "value", "source_url", "confidence"],
                    },
                },
                "queries_tried": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
            },
            "required": ["contacts", "summary"],
        },
    },
]
_WEB_SEARCH_TERMINAL = {"finish"}


async def _web_search_tool(args: dict) -> str:
    query = args.get("query", "")
    num = int(args.get("num_results", 8))
    results = await web_search(query, max_results=min(num, 10))
    return json.dumps(results[:10], ensure_ascii=False)


async def _fetch_page_tool(args: dict) -> str:
    url = args.get("url", "")
    html = await fetch_page(url, timeout=20.0)
    if not html:
        return json.dumps({"error": "Could not fetch page", "url": url})
    text = extract_text_from_html(html, max_chars=8000)
    emails = extract_emails(html)
    phones = extract_phones_from_text(html)
    return json.dumps({
        "url": url,
        "text_preview": text[:4000],
        "emails_found": emails[:10],
        "phones_found": phones[:10],
    }, ensure_ascii=False)


_WEB_SEARCH_DISPATCH: dict[str, Callable] = {
    "search_web": _web_search_tool,
    "fetch_page": _fetch_page_tool,
}


# ---------------------------------------------------------------------------
# InstagramSubAgent tool schemas
# ---------------------------------------------------------------------------

_INSTAGRAM_AGENT_TOOLS: list[dict] = [
    {
        "type": "function",
        "name": "find_ig_handle",
        "description": "Cari akun Instagram resmi perusahaan. Returns daftar kandidat handle.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "website_url": {"type": "string", "description": "URL website (jika ada, akan di-scan untuk IG link)"},
            },
            "required": ["company_name"],
        },
    },
    {
        "type": "function",
        "name": "scrape_ig_contacts",
        "description": "Scrape posts dari IG handle tertentu dan ekstrak nomor WA + nama PIC dari foto/caption.",
        "parameters": {
            "type": "object",
            "properties": {
                "handle": {"type": "string", "description": "Instagram handle (tanpa @)"},
                "limit": {"type": "integer", "description": "Jumlah posts (default 20)", "default": 20},
            },
            "required": ["handle"],
        },
    },
    {
        "type": "function",
        "name": "finish",
        "description": "TERMINAL: Selesai. Kembalikan kontak dan handle yang ditemukan.",
        "parameters": {
            "type": "object",
            "properties": {
                "contacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["wa_phone", "email"]},
                            "value": {"type": "string"},
                            "source_url": {"type": "string"},
                            "confidence": {"type": "number"},
                            "pic_name": {"type": "string"},
                        },
                        "required": ["type", "value", "source_url", "confidence"],
                    },
                },
                "ig_handle": {"type": "string", "description": "Handle IG yang terverifikasi (tanpa @)"},
                "summary": {"type": "string"},
            },
            "required": ["contacts", "summary"],
        },
    },
]
_INSTAGRAM_TERMINAL = {"finish"}


async def _find_ig_handle_tool(args: dict) -> str:
    """Search for IG handle: check website social links first, then search DDG."""
    company_name = args.get("company_name", "")
    website_url = args.get("website_url")

    candidates: list[dict] = []

    # Step 1: Check website's social links if website_url provided
    if website_url:
        try:
            html = await fetch_page(website_url, timeout=15.0)
            if html:
                social = extract_social_links(html)
                ig_links = social.get("instagram", [])
                for link in ig_links[:3]:
                    handle = link.rstrip("/").split("/")[-1]
                    if handle and len(handle) > 1 and "." not in handle:
                        candidates.append({
                            "handle": handle,
                            "source": "website_social_link",
                            "confidence": 0.9,
                            "url": link,
                        })
        except Exception as e:
            log.debug("[InstagramSubAgent] website fetch failed: %s", e)

    # Step 2: DDG search for IG handle
    try:
        query = f'"{company_name}" site:instagram.com'
        results = await web_search(query, max_results=8)
        for r in results:
            link = r.get("link", "")
            if "instagram.com/" in link:
                handle = link.rstrip("/").split("instagram.com/")[-1].split("/")[0]
                if handle and len(handle) > 1 and handle not in {"p", "reel", "explore"}:
                    candidates.append({
                        "handle": handle,
                        "source": "search_result",
                        "confidence": 0.6,
                        "url": link,
                        "context": r.get("snippet", "")[:200],
                    })
    except Exception as e:
        log.debug("[InstagramSubAgent] DDG search failed: %s", e)

    # Deduplicate by handle
    seen: set[str] = set()
    unique: list[dict] = []
    for c in candidates:
        h = c["handle"].lower()
        if h not in seen:
            seen.add(h)
            unique.append(c)

    return json.dumps({
        "candidates": unique[:6],
        "note": "Pilih handle yang paling relevan dengan perusahaan. website_social_link paling dipercaya.",
    }, ensure_ascii=False)


async def _scrape_ig_contacts_tool(args: dict) -> str:
    """Scrape IG posts for a specific handle and extract WA contacts."""
    handle = args.get("handle", "").strip().lstrip("@")
    limit = int(args.get("limit", 20))

    if not handle:
        return json.dumps({"error": "handle is required"})

    try:
        from orchestrator.instagram import scrape_ig_posts_with_fallback, extract_phone_from_image, extract_named_contacts_from_text

        posts_result = await asyncio.to_thread(
            scrape_ig_posts_with_fallback, handle, min(limit, 25), False, None, True
        )
        posts, scrape_diag = posts_result if isinstance(posts_result, tuple) else (posts_result, {})
        is_private = scrape_diag.get("is_private", False) or "private" in str(scrape_diag.get("reason", "")).lower()
        tier_used = scrape_diag.get("tier_used") or (
            "playwright" if scrape_diag.get("playwright_attempted") and not scrape_diag.get("playwright_error") else
            "instaloader" if scrape_diag.get("instaloader_success") else "none"
        )

        if not posts:
            reason = "private_account" if is_private else scrape_diag.get("reason") or "no_posts"
            return json.dumps({"handle": handle, "posts_found": 0, "contacts": [], "is_private": is_private, "scrape_tier": tier_used, "note": f"Tidak ada posts: {reason}"})

        wa_contacts: list[dict] = []
        for post in posts[:20]:
            caption = post.get("caption") or post.get("text") or ""
            image_url = post.get("image_url") or post.get("thumbnail_url") or ""
            post_url = post.get("url") or post.get("link") or f"https://instagram.com/{handle}/"

            # Extract from caption text
            if caption:
                named = await extract_named_contacts_from_text(caption, require_person_name=False)
                for nc in named:
                    if nc.phone and search_flow.is_mobile_phone(nc.phone):
                        wa_contacts.append({
                            "type": "wa_phone",
                            "value": nc.phone,
                            "source_url": post_url,
                            "confidence": 0.8,
                            "pic_name": nc.name or "",
                        })

            # Extract from image via Vision API
            if image_url:
                try:
                    phone_contacts = await extract_phone_from_image(image_url, caption, require_person_name=False)
                    for pc in phone_contacts:
                        if pc.phone and search_flow.is_mobile_phone(pc.phone):
                            wa_contacts.append({
                                "type": "wa_phone",
                                "value": pc.phone,
                                "source_url": post_url,
                                "confidence": 0.85,
                                "pic_name": getattr(pc, "name", "") or "",
                            })
                except Exception:
                    pass

        # Deduplicate by value
        seen_vals: set[str] = set()
        unique_contacts = []
        for c in wa_contacts:
            if c["value"] not in seen_vals:
                seen_vals.add(c["value"])
                unique_contacts.append(c)

        return json.dumps({
            "handle": handle,
            "posts_found": len(posts),
            "contacts": unique_contacts[:5],
            "scrape_tier": tier_used,
            "summary": f"Scraped {len(posts)} posts via {tier_used}, found {len(unique_contacts)} WA contacts.",
        }, ensure_ascii=False)

    except Exception as exc:
        log.warning("[InstagramSubAgent] scrape_ig_contacts_tool error for %s: %s", handle, exc)
        return json.dumps({"error": str(exc), "handle": handle})


@dataclass
class SubAgentResult:
    """Structured result returned by any sub-agent."""
    contacts: list[dict] = field(default_factory=list)
    # [{type: "wa_phone"|"email"|"website", value: str, source_url: str, confidence: float, pic_name: str}]
    ig_handle: str | None = None
    ig_candidates: list[dict] = field(default_factory=list)
    ig_posts_count: int = 0
    tool_calls_made: list[str] = field(default_factory=list)
    summary: str = ""
    tokens_used: int = 0
    duration_seconds: float = 0.0
    success: bool = True
    error: str | None = None
    queries_tried: list[str] = field(default_factory=list)
    # Failure diagnostics — help orchestrator reason about what went wrong
    failure_reason: str | None = None      # e.g. "scrape_failed_private", "handle_not_found", "all_tiers_blocked"
    is_ig_private: bool = False            # True if account is private
    scrape_tier_used: str | None = None    # "playwright", "instaloader", "ig_session", "scrapingbot", "none"
    posts_scraped: int = 0                 # actual posts count scraped


def _contact_result_to_dict(result: search_flow.ContactResult) -> dict:
    """Convert ContactResult dataclass to plain dict for JSON serialization."""
    return {
        "type": result.contact_type,
        "value": result.value,
        "source_url": result.source_url or "",
        "source_type": result.source_type or "",
        "confidence": float(result.confidence or 0.0),
        "pic_name": result.pic_name or "",
        "pic_title": result.pic_title or "",
    }


def _contacts_to_serializable(
    results: list[search_flow.ContactResult],
    allowed_types: tuple[str, ...] = ("website", "wa_phone", "email"),
) -> list[dict]:
    """Convert and filter a list of ContactResult to JSON-safe dicts."""
    out = []
    for r in results:
        if r.contact_type in allowed_types and r.value:
            out.append(_contact_result_to_dict(r))
    return out


class WebSearchSubAgent:
    """
    Searches for official website and extracts contacts from web pages.
    PRIMARY: LLM ReAct loop (MARKETING_SUB_AGENT_MODEL) with search_web + fetch_page tools.
    FALLBACK: search_flow.website_discovery() if LLM unavailable or returns nothing.
    """

    async def run(
        self,
        company_name: str,
        client_type: str | None = None,
        extra_data: dict | None = None,
    ) -> SubAgentResult:
        start = time.monotonic()
        hints = extra_data or {}
        log.info("[WebSearchSubAgent] Starting for: %s (type=%s, hints=%s)", company_name, client_type, list(hints.keys()))

        # --- PRIMARY: LLM ReAct loop ---
        if _llm_available():
            try:
                system_prompt = build_web_search_prompt(
                    company_name,
                    client_type=client_type,
                    refined_query=hints.get("refined_query"),
                    avoid_domains=hints.get("avoid_source_domains"),
                    force_domain=hints.get("force_domain"),
                )
                initial_msg = f"Temukan kontak resmi untuk: {company_name}"
                if hints.get("refined_query"):
                    initial_msg += f"\nGunakan query ini sebagai titik awal: {hints['refined_query']}"
                if hints.get("force_domain"):
                    initial_msg += f"\nCoba langsung ke domain: {hints['force_domain']}"

                terminal_args, tokens = await _run_sub_agent_llm_loop(
                    system_prompt=system_prompt,
                    initial_message=initial_msg,
                    tool_schemas=_WEB_SEARCH_AGENT_TOOLS,
                    terminal_tools=_WEB_SEARCH_TERMINAL,
                    tool_dispatch=_WEB_SEARCH_DISPATCH,
                    max_iterations=8,
                )

                llm_contacts = terminal_args.get("contacts", [])
                queries_tried = terminal_args.get("queries_tried", [])
                summary = terminal_args.get("summary", "")

                if llm_contacts:
                    duration = time.monotonic() - start
                    log.info("[WebSearchSubAgent/LLM] Done in %.1fs: %d contacts, %d tokens", duration, len(llm_contacts), tokens)
                    return SubAgentResult(
                        contacts=llm_contacts,
                        tool_calls_made=["llm_web_search"],
                        summary=summary or f"LLM web search: {len(llm_contacts)} kontak ditemukan.",
                        queries_tried=queries_tried,
                        tokens_used=tokens,
                        duration_seconds=duration,
                        success=True,
                    )
                else:
                    log.info("[WebSearchSubAgent/LLM] LLM returned 0 contacts — falling back to website_discovery")

            except Exception as llm_exc:
                log.warning("[WebSearchSubAgent] LLM loop failed: %s — falling back", llm_exc)

        # --- FALLBACK: deterministic pipeline ---
        try:
            avoid_domains = hints.get("avoid_source_domains", [])
            refined_query = hints.get("refined_query")
            force_domain = hints.get("force_domain")

            results = await search_flow.website_discovery(
                company_name,
                hints,
                avoid_domains=avoid_domains or None,
                refined_query=refined_query,
                force_domain=force_domain,
            )
            contacts = _contacts_to_serializable(results)

            wa_count = sum(1 for c in contacts if c["type"] == "wa_phone")
            email_count = sum(1 for c in contacts if c["type"] == "email")
            website_count = sum(1 for c in contacts if c["type"] == "website")
            parts = []
            if website_count:
                parts.append("website ditemukan")
            if email_count:
                parts.append(f"{email_count} email")
            if wa_count:
                parts.append(f"{wa_count} WA phone")
            summary = f"Web search: {', '.join(parts)}." if parts else "Web search: tidak ada kontak ditemukan."

            duration = time.monotonic() - start
            log.info("[WebSearchSubAgent/Fallback] Done in %.1fs: %d contacts", duration, len(contacts))
            return SubAgentResult(
                contacts=contacts,
                tool_calls_made=["website_discovery"],
                summary=summary,
                duration_seconds=duration,
                success=True,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            log.warning("[WebSearchSubAgent] Fallback also failed for %s: %s", company_name, exc)
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Web search gagal: {exc}",
                tool_calls_made=["website_discovery"],
                duration_seconds=duration,
            )


class InstagramSubAgent:
    """
    Finds Instagram handle and extracts WA phone numbers from IG posts.
    PRIMARY: LLM ReAct loop that intelligently selects handles and scrapes contacts.
    FALLBACK: search_flow.ig_discovery() if LLM unavailable or returns nothing.
    """

    async def run(
        self,
        company_name: str,
        website_url: str | None = None,
        client_type: str = "",
        prior_web_contacts: list[dict] | None = None,
    ) -> SubAgentResult:
        start = time.monotonic()

        # Cross-agent knowledge sharing: extract website URL from prior WebSearch results
        if prior_web_contacts and not website_url:
            for c in prior_web_contacts:
                if c.get("type") == "website" and c.get("value"):
                    website_url = c["value"]
                    log.info("[InstagramSubAgent] Using website from prior WebSearch: %s", website_url)
                    break

        log.info("[InstagramSubAgent] Starting for: %s (website_url=%s)", company_name, bool(website_url))

        # Build dispatch with website_url closure
        async def _find_ig(args: dict) -> str:
            args_with_website = dict(args)
            if website_url and not args_with_website.get("website_url"):
                args_with_website["website_url"] = website_url
            return await _find_ig_handle_tool(args_with_website)

        ig_dispatch: dict[str, Callable] = {
            "find_ig_handle": _find_ig,
            "scrape_ig_contacts": _scrape_ig_contacts_tool,
        }

        # Tracks handle discovered by LLM path (may be set even if 0 contacts)
        ig_handle: str | None = None

        # --- PRIMARY: LLM ReAct loop (with retry) ---
        # Attempt 1: normal search with website_url hint
        # Attempt 2 (if nothing found): retry with abbreviation as search hint + broader instruction
        _LLM_MAX_ATTEMPTS = 2
        if _llm_available():
            abbreviation_hint = search_flow._build_company_abbreviation(company_name)
            llm_attempt_configs = [
                {
                    "label": "attempt1",
                    "msg_suffix": "",
                },
                {
                    "label": "attempt2_broader",
                    "msg_suffix": (
                        f"\n\nCatatan: pencarian sebelumnya gagal menemukan akun. "
                        f"Coba cari dengan nama singkatan '{abbreviation_hint}' saja. "
                        f"Juga coba variasi handle seperti '{abbreviation_hint.lower()}id', "
                        f"'{abbreviation_hint.lower()}indonesia', '{abbreviation_hint.lower()}_official'."
                    ) if abbreviation_hint else "\n\nCoba strategi pencarian berbeda.",
                },
            ]

            for llm_cfg in llm_attempt_configs[:_LLM_MAX_ATTEMPTS]:
                try:
                    system_prompt = build_instagram_prompt(company_name, website_url=website_url)
                    initial_msg = f"Temukan akun Instagram dan nomor WA untuk: {company_name}"
                    if website_url:
                        initial_msg += f"\nWebsite resmi: {website_url} — scan untuk IG link dulu"
                    initial_msg += llm_cfg["msg_suffix"]

                    log.info(
                        "[InstagramSubAgent/LLM] %s for '%s'",
                        llm_cfg["label"], company_name,
                    )
                    terminal_args, tokens = await _run_sub_agent_llm_loop(
                        system_prompt=system_prompt,
                        initial_message=initial_msg,
                        tool_schemas=_INSTAGRAM_AGENT_TOOLS,
                        terminal_tools=_INSTAGRAM_TERMINAL,
                        tool_dispatch=ig_dispatch,
                        max_iterations=8,
                    )

                    llm_contacts = terminal_args.get("contacts", [])
                    ig_handle = (terminal_args.get("ig_handle") or "").lstrip("@") or None
                    summary = terminal_args.get("summary", "")

                    if llm_contacts:
                        # Contacts found — success, return immediately
                        duration = time.monotonic() - start
                        log.info(
                            "[InstagramSubAgent/LLM] %s done in %.1fs: %d contacts, handle=%s, %d tokens",
                            llm_cfg["label"], duration, len(llm_contacts), ig_handle, tokens,
                        )
                        return SubAgentResult(
                            contacts=llm_contacts,
                            ig_handle=ig_handle,
                            tool_calls_made=[f"llm_instagram_{llm_cfg['label']}"],
                            summary=summary or f"IG LLM: {len(llm_contacts)} WA contacts, handle=@{ig_handle}",
                            tokens_used=tokens,
                            duration_seconds=duration,
                            success=True,
                        )

                    if ig_handle:
                        # Handle found but 0 contacts (scraping may have failed) — fall through to
                        # deterministic fallback with the known handle so it can be scraped directly
                        log.info(
                            "[InstagramSubAgent/LLM] Handle @%s found but 0 contacts after %s — "
                            "passing to deterministic fallback",
                            ig_handle, llm_cfg["label"],
                        )
                        break  # exit LLM attempt loop, keep ig_handle for fallback

                    log.info(
                        "[InstagramSubAgent/LLM] %s returned nothing — %s",
                        llm_cfg["label"],
                        "retrying with broader hints" if llm_cfg["label"] == "attempt1" else "falling back to ig_discovery",
                    )

                except Exception as llm_exc:
                    log.warning(
                        "[InstagramSubAgent/LLM] %s failed for '%s': %s — %s",
                        llm_cfg["label"], company_name, llm_exc,
                        "retrying" if llm_cfg["label"] == "attempt1" else "falling back",
                    )

        # --- FALLBACK: deterministic pipeline with retry loop ---
        # Round 0 (if LLM found a handle): skip discovery, scrape known handle directly
        # Round 1 = full name search, Round 2 = abbreviation (if round 1 finds no handle)
        # Inner loop: up to MAX_ATTEMPTS retries per round on transient errors (with backoff)
        _MAX_ATTEMPTS = 2
        _RETRY_DELAY = 3.0  # seconds before retry on error

        abbreviation = search_flow._build_company_abbreviation(company_name)
        # ig_handle may be set from the LLM path above (handle found, 0 contacts)
        known_handle_from_llm: str | None = ig_handle  # set earlier in this function scope
        search_rounds: list[tuple[str, str]] = []
        if known_handle_from_llm:
            search_rounds.append((company_name, "known_handle"))  # use known handle, skip discovery
        search_rounds.append((company_name, "full_name"))
        if abbreviation and abbreviation.lower() != company_name.lower():
            search_rounds.append((abbreviation, "abbreviation"))

        last_result: search_flow.InstagramDiscoveryResult | None = None
        tool_calls: list[str] = []

        for search_name, round_label in search_rounds:
            round_succeeded = False
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    log.info(
                        "[InstagramSubAgent/Fallback] Round=%s attempt=%d/%d — searching as '%s'",
                        round_label, attempt, _MAX_ATTEMPTS, search_name,
                    )
                    ig_result = await search_flow.ig_discovery(
                        search_name,
                        client_type=client_type,
                        known_website_url=website_url,
                        known_handle=known_handle_from_llm if round_label == "known_handle" else None,
                    )
                    tool_calls.append(f"ig_discovery_{round_label}_attempt{attempt}")
                    last_result = ig_result
                    round_succeeded = True
                    break  # no exception → exit retry loop

                except Exception as exc:
                    log.warning(
                        "[InstagramSubAgent] Round=%s attempt=%d error for '%s': %s",
                        round_label, attempt, search_name, exc,
                    )
                    tool_calls.append(f"ig_discovery_{round_label}_attempt{attempt}_error")
                    if attempt < _MAX_ATTEMPTS:
                        log.info("[InstagramSubAgent] Retrying in %.0fs…", _RETRY_DELAY)
                        await asyncio.sleep(_RETRY_DELAY)

            if not round_succeeded:
                log.warning(
                    "[InstagramSubAgent] Round=%s exhausted all %d attempts — moving on",
                    round_label, _MAX_ATTEMPTS,
                )
                continue  # try next round (abbreviation)

            # Round succeeded — check if we got a useful result
            if last_result and last_result.handle:
                break  # handle found → no need for next round
            log.info(
                "[InstagramSubAgent/Fallback] Round=%s found no handle — %s",
                round_label,
                "retrying with abbreviation" if round_label == "full_name" and len(search_rounds) > 1
                else "giving up",
            )

        if last_result is None:
            duration = time.monotonic() - start
            return SubAgentResult(
                success=False,
                error="All Instagram search rounds failed",
                summary=f"Instagram search gagal untuk {company_name}",
                tool_calls_made=tool_calls,
                duration_seconds=duration,
            )

        contacts = _contacts_to_serializable(last_result.contacts)
        candidates = last_result.candidates or []
        wa_count = sum(1 for c in contacts if c["type"] == "wa_phone")
        handle = last_result.handle or "tidak ditemukan"
        posts = len(last_result.posts) if last_result.posts else 0

        if wa_count:
            summary = f"IG: @{handle}, {posts} posts, {wa_count} WA phone ditemukan."
        elif last_result.handle:
            summary = f"IG: @{handle} ditemukan, {posts} posts, tapi tidak ada WA phone."
        else:
            summary = f"IG: Tidak ada akun yang cocok ditemukan untuk {company_name}."

        # Derive failure diagnostics from scrape_status
        scrape_status = last_result.scrape_status or ""
        scrape_error = last_result.scrape_error or ""
        is_private = "private" in scrape_error.lower()
        if is_private:
            failure_reason = "scrape_failed_private"
        elif scrape_status == "no_candidates":
            failure_reason = "handle_not_found"
        elif scrape_status in ("empty", "failed"):
            failure_reason = "scrape_failed_no_posts" if scrape_status == "empty" else "scrape_failed_error"
        else:
            failure_reason = None

        duration = time.monotonic() - start
        log.info("[InstagramSubAgent/Fallback] Done in %.1fs: handle=%s, %d contacts (%d rounds)",
                 duration, handle, len(contacts), len(tool_calls))
        return SubAgentResult(
            contacts=contacts,
            ig_handle=last_result.handle,
            ig_candidates=candidates,
            ig_posts_count=posts,
            tool_calls_made=tool_calls,
            summary=summary,
            duration_seconds=duration,
            success=True,
            failure_reason=failure_reason,
            is_ig_private=is_private,
            posts_scraped=posts,
        )


class RegistrySearchSubAgent:
    """
    Searches official Indonesian registries (BNSP, JDIH, Asosiasi).
    Selects the appropriate registry based on client_type.
    """

    async def run(
        self,
        company_name: str,
        client_type: str | None = None,
    ) -> SubAgentResult:
        start = time.monotonic()
        log.info("[RegistrySubAgent] Starting for: %s (type=%s)", company_name, client_type)

        registry_used = "none"
        results: list[search_flow.ContactResult] = []

        try:
            if client_type in ("lsp_p1", "lsp_p2", "lsp_p3"):
                from .discovery.bnsp import bnsp_discovery
                results = await bnsp_discovery(company_name)
                registry_used = "bnsp"
            elif client_type in ("kementerian", "lembaga_negara"):
                from .discovery.jdih import jdih_discovery
                results = await jdih_discovery(company_name)
                registry_used = "jdih"
            elif client_type == "asosiasi":
                from .discovery.asosiasi import asosiasi_discovery
                results = await asosiasi_discovery(company_name)
                registry_used = "asosiasi"
            else:
                # Try BNSP as default for unknown types
                try:
                    from .discovery.bnsp import bnsp_discovery
                    results = await bnsp_discovery(company_name)
                    registry_used = "bnsp_fallback"
                except Exception:
                    results = []
                    registry_used = "none"

            contacts = _contacts_to_serializable(results)

            summary_parts = [f"Registry {registry_used}:"]
            if contacts:
                types = list({c["type"] for c in contacts})
                summary_parts.append(f"{len(contacts)} kontak ({', '.join(types)})")
            else:
                summary_parts.append("tidak ada kontak ditemukan")

            duration = time.monotonic() - start
            log.info("[RegistrySubAgent] Done in %.1fs: registry=%s, %d contacts", duration, registry_used, len(contacts))
            return SubAgentResult(
                contacts=contacts,
                tool_calls_made=[f"search_{registry_used}"],
                summary=" ".join(summary_parts) + ".",
                duration_seconds=duration,
                success=True,
                queries_tried=[company_name],
            )
        except Exception as exc:
            duration = time.monotonic() - start
            log.warning("[RegistrySubAgent] Error for %s: %s", company_name, exc)
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Registry search gagal ({registry_used}): {exc}",
                tool_calls_made=[f"search_{registry_used}"],
                duration_seconds=duration,
            )


# ---------------------------------------------------------------------------
# WebsiteContactScraperSubAgent — tool schemas, dispatch, and implementation
# ---------------------------------------------------------------------------

_WEBSITE_SCRAPER_TOOLS: list[dict] = [
    {
        "type": "function",
        "name": "fetch_website",
        "description": (
            "Fetch satu halaman website dan ekstrak: email, nomor telepon, dan daftar "
            "link internal yang relevan (halaman kontak, tentang, struktur organisasi, dll)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL halaman yang akan di-fetch"},
            },
            "required": ["url"],
        },
    },
    {
        "type": "function",
        "name": "finish",
        "description": "TERMINAL: selesai mengekstrak kontak dari website. Kembalikan semua kontak valid.",
        "parameters": {
            "type": "object",
            "properties": {
                "contacts": {
                    "type": "array",
                    "description": "Daftar kontak yang ditemukan",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["wa_phone", "email"]},
                            "value": {"type": "string"},
                            "source_url": {"type": "string"},
                            "confidence": {"type": "number"},
                            "pic_name": {"type": "string", "description": "Nama PIC jika ada"},
                        },
                        "required": ["type", "value", "source_url", "confidence"],
                    },
                },
                "pages_visited": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "URL halaman yang sudah dikunjungi",
                },
                "summary": {"type": "string"},
            },
            "required": ["contacts", "summary"],
        },
    },
]
_WEBSITE_SCRAPER_TERMINAL: set[str] = {"finish"}


async def _fetch_website_tool(args: dict) -> str:
    """Fetch a page and return emails, phones, and contact-relevant internal links."""
    from urllib.parse import urljoin, urlparse
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None  # type: ignore[assignment,misc]

    url = args.get("url", "").strip()
    if not url:
        return json.dumps({"error": "url is required"})

    html = await fetch_page(url, timeout=20.0)
    if not html:
        return json.dumps({"error": "Tidak bisa fetch halaman", "url": url})

    emails = extract_emails(html)
    phones = extract_phones_from_text(html)
    text_preview = extract_text_from_html(html, max_chars=3000)

    # Discover contact-relevant internal links via BeautifulSoup
    relevant_links: list[dict] = []
    if BeautifulSoup is not None:
        _CONTACT_KEYWORDS = {
            "kontak", "contact", "hubungi", "about", "tentang", "struktur",
            "pengurus", "direktori", "sekretariat", "pimpinan", "tim", "team",
            "profil", "info", "layanan", "cs", "informasi",
        }
        try:
            base_domain = urlparse(url).netloc
            soup = BeautifulSoup(html, "html.parser")
            seen_links: set[str] = set()
            for a in soup.find_all("a", href=True):
                href = str(a.get("href", "")).strip()
                link_text = a.get_text(strip=True).lower()
                if not href or href.startswith("#") or "javascript:" in href:
                    continue
                full_url = urljoin(url, href)
                parsed = urlparse(full_url)
                if parsed.netloc != base_domain:
                    continue
                if full_url in seen_links:
                    continue
                href_lower = parsed.path.lower()
                if any(kw in link_text or kw in href_lower for kw in _CONTACT_KEYWORDS):
                    seen_links.add(full_url)
                    relevant_links.append({"url": full_url, "text": a.get_text(strip=True)[:60]})
                    if len(relevant_links) >= 15:
                        break
        except Exception as exc:
            log.debug("[WebsiteScraperTool] Link extraction failed: %s", exc)

    return json.dumps({
        "url": url,
        "emails": emails[:10],
        "phones": phones[:10],
        "relevant_links": relevant_links,
        "text_preview": text_preview[:2000],
    }, ensure_ascii=False)


class WebsiteContactScraperSubAgent:
    """
    Deep-crawls a known official website URL to extract WA phone numbers and emails.
    PRIMARY: LLM ReAct loop — LLM decides which sub-pages to visit based on discovered links.
    FALLBACK: Deterministic — fetches homepage + all _CONTACT_PAGE_PATHS concurrently.
    """

    async def run(
        self,
        company_name: str,
        website_url: str,
    ) -> SubAgentResult:
        start = time.monotonic()
        log.info("[WebsiteScraperSubAgent] Starting for: %s (%s)", company_name, website_url)

        # --- PRIMARY: LLM ReAct loop ---
        if _llm_available():
            try:
                system_prompt = build_website_scraper_prompt(company_name, website_url)
                terminal_args, tokens = await _run_sub_agent_llm_loop(
                    system_prompt=system_prompt,
                    initial_message=f"Scrape website resmi {company_name} untuk cari nomor WA dan email: {website_url}",
                    tool_schemas=_WEBSITE_SCRAPER_TOOLS,
                    terminal_tools=_WEBSITE_SCRAPER_TERMINAL,
                    tool_dispatch={"fetch_website": _fetch_website_tool},
                    max_iterations=10,
                )
                llm_contacts = terminal_args.get("contacts", [])
                pages_visited = terminal_args.get("pages_visited", [])
                summary = terminal_args.get("summary", "")
                if llm_contacts:
                    duration = time.monotonic() - start
                    log.info(
                        "[WebsiteScraperSubAgent/LLM] Done in %.1fs: %d contacts, %d pages, %d tokens",
                        duration, len(llm_contacts), len(pages_visited), tokens,
                    )
                    return SubAgentResult(
                        contacts=llm_contacts,
                        tool_calls_made=["llm_website_scraper"],
                        summary=summary or f"Website scrape: {len(llm_contacts)} kontak dari {website_url}",
                        tokens_used=tokens,
                        duration_seconds=duration,
                        success=True,
                    )
                log.info("[WebsiteScraperSubAgent/LLM] LLM found 0 contacts — falling back to deterministic")
            except Exception as exc:
                log.warning("[WebsiteScraperSubAgent] LLM loop failed: %s — falling back", exc)

        # --- FALLBACK: Deterministic scraper ---
        try:
            results = await search_flow.scrape_website_contacts(website_url, company_name)
            contacts = _contacts_to_serializable(results)
            wa_count = sum(1 for c in contacts if c["type"] == "wa_phone")
            email_count = sum(1 for c in contacts if c["type"] == "email")
            parts = []
            if wa_count:
                parts.append(f"{wa_count} WA phone")
            if email_count:
                parts.append(f"{email_count} email")
            summary = f"Website scrape: {', '.join(parts)}." if parts else f"Tidak ada kontak ditemukan di {website_url}"

            duration = time.monotonic() - start
            log.info("[WebsiteScraperSubAgent/Fallback] Done in %.1fs: %d contacts", duration, len(contacts))
            return SubAgentResult(
                contacts=contacts,
                tool_calls_made=["scrape_website_contacts"],
                summary=summary,
                duration_seconds=duration,
                success=True,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            log.warning("[WebsiteScraperSubAgent] Fallback also failed for %s: %s", website_url, exc)
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Website scrape gagal: {exc}",
                tool_calls_made=["scrape_website_contacts"],
                duration_seconds=duration,
            )


class GeminiGapFillSubAgent:
    """
    Last resort: uses Gemini with Google Search grounding to fill contact gaps.
    Wraps search_flow.gemini_grounded_discovery().
    """

    async def run(
        self,
        company_name: str,
        gaps: list[str] | None = None,
        already_found: list[dict] | None = None,
        extra_data: dict | None = None,
    ) -> SubAgentResult:
        start = time.monotonic()
        log.info("[GeminiSubAgent] Starting for: %s, gaps=%s", company_name, gaps)

        # Convert already_found dicts back to ContactResult for the gemini function
        existing_contacts: list[search_flow.ContactResult] = []
        for c in (already_found or []):
            try:
                cr = search_flow.ContactResult(
                    contact_type=c.get("type", ""),
                    value=c.get("value", ""),
                    source_url=c.get("source_url", ""),
                    source_type=c.get("source_type", "manual"),
                    confidence=float(c.get("confidence", 0.5)),
                )
                existing_contacts.append(cr)
            except Exception:
                pass

        try:
            if not search_flow.is_marketing_gemini_enabled():
                return SubAgentResult(
                    success=False,
                    summary="Gemini disabled — GEMINI_API_KEY tidak dikonfigurasi.",
                    tool_calls_made=["gemini_grounded_disabled"],
                    duration_seconds=time.monotonic() - start,
                )

            gemini_result: search_flow.GeminiGroundedDiscoveryResult = await search_flow.gemini_grounded_discovery(
                company_name,
                extra_data or {},
                existing_contacts,
            )

            contacts = _contacts_to_serializable(gemini_result.contacts)
            grounded_urls = gemini_result.grounded_urls or []

            summary_parts = ["Gemini grounded:"]
            if contacts:
                types = list({c["type"] for c in contacts})
                summary_parts.append(f"{len(contacts)} kontak ({', '.join(types)})")
            else:
                summary_parts.append("tidak ada kontak tambahan ditemukan")
            if grounded_urls:
                summary_parts.append(f"dari {len(grounded_urls)} sumber")

            duration = time.monotonic() - start
            log.info("[GeminiSubAgent] Done in %.1fs: %d contacts", duration, len(contacts))
            return SubAgentResult(
                contacts=contacts,
                tool_calls_made=["gemini_grounded_discovery"],
                summary=" ".join(summary_parts) + ".",
                duration_seconds=duration,
                success=True,
                queries_tried=[f"Gemini grounded for gaps: {gaps}"],
            )
        except Exception as exc:
            duration = time.monotonic() - start
            log.warning("[GeminiSubAgent] Error for %s: %s", company_name, exc)
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Gemini search gagal: {exc}",
                tool_calls_made=["gemini_grounded_discovery"],
                duration_seconds=duration,
            )


# ---------------------------------------------------------------------------
# Chrome DevTools MCP Sub-Agent
# ---------------------------------------------------------------------------

_CHROME_IG_TOOLS = [
    {
        "type": "function",
        "name": "navigate_to_ig_profile",
        "description": (
            "Navigasi ke halaman profil Instagram dan tunggu sampai halaman load. "
            "Selalu panggil ini PERTAMA sebelum extract data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ig_handle": {
                    "type": "string",
                    "description": "Handle Instagram tanpa @, e.g. 'universitasgadjahmadasli'",
                },
            },
            "required": ["ig_handle"],
        },
    },
    {
        "type": "function",
        "name": "extract_ig_data",
        "description": (
            "Jalankan JavaScript di halaman Instagram untuk mengekstrak data posts, bio, "
            "nomor telepon, atau informasi lainnya. Gunakan ini setelah navigate_to_ig_profile."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "JavaScript yang akan dijalankan di browser. Harus punya return statement.",
                },
                "purpose": {
                    "type": "string",
                    "description": "Penjelasan singkat apa yang diextract (untuk logging)",
                },
            },
            "required": ["script", "purpose"],
        },
    },
    {
        "type": "function",
        "name": "get_page_snapshot",
        "description": (
            "Ambil accessibility tree halaman saat ini sebagai teks terstruktur. "
            "Berguna untuk membaca konten halaman tanpa JavaScript."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "finish",
        "description": "TERMINAL: selesai, kembalikan semua kontak yang ditemukan.",
        "parameters": {
            "type": "object",
            "properties": {
                "contacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["wa_phone", "email"]},
                            "value": {"type": "string"},
                            "source_url": {"type": "string"},
                            "confidence": {"type": "number"},
                            "pic_name": {"type": "string"},
                        },
                        "required": ["type", "value", "source_url", "confidence"],
                    },
                },
                "ig_handle_found": {"type": "string"},
                "summary": {"type": "string"},
                "failure_reason": {
                    "type": "string",
                    "enum": [
                        "session_expired",
                        "account_private",
                        "account_not_found",
                        "checkpoint_required",
                        "no_contacts_found",
                        "js_extraction_failed",
                    ],
                },
            },
            "required": ["contacts", "summary"],
        },
    },
]
_CHROME_IG_TERMINAL: set[str] = {"finish"}


async def _cdp_navigate_tool(args: dict, client: MCPBrowserClient) -> str:
    handle = args.get("ig_handle", "").strip().lstrip("@")
    if not handle:
        return json.dumps({"error": "ig_handle kosong"})
    target_url = f"https://www.instagram.com/{handle}/"
    try:
        await client.navigate(target_url)
        # chrome-devtools-mcp navigate response doesn't include current URL,
        # so evaluate window.location.href to detect login/challenge redirects
        current_url = await client.get_current_url()
        if "/accounts/login" in current_url:
            return json.dumps({
                "status": "error",
                "error_type": "session_expired",
                "message": "Instagram meminta login. Buka Chrome dan login ke instagram.com dulu.",
                "url": current_url,
            })
        if "/challenge/" in current_url or "/accounts/suspended" in current_url:
            return json.dumps({
                "status": "error",
                "error_type": "checkpoint_required",
                "message": "IG membutuhkan verifikasi akun.",
                "url": current_url,
            })
        return json.dumps({
            "status": "ok",
            "url": current_url,
            "message": f"Navigasi ke @{handle} berhasil",
        })
    except MCPBrowserError as e:
        return json.dumps({"status": "error", "error_type": "mcp_error", "message": str(e)})


async def _cdp_evaluate_tool(args: dict, client: MCPBrowserClient) -> str:
    script = args.get("script", "").strip()
    purpose = args.get("purpose", "extract")
    if not script:
        return json.dumps({"error": "script kosong"})
    try:
        result = await client.evaluate(script)
        log.debug("[CDPAgent] JS eval (%s): %s chars result", purpose, len(str(result)))
        return json.dumps({"status": "ok", "result": result})
    except MCPBrowserError as e:
        return json.dumps({"status": "error", "error_type": "js_error", "message": str(e)})


async def _cdp_snapshot_tool(args: dict, client: MCPBrowserClient) -> str:
    try:
        result = await client.snapshot()
        text = str(result.get("raw") or result)[:5000]
        return json.dumps({"status": "ok", "snapshot": text})
    except MCPBrowserError as e:
        return json.dumps({"status": "error", "error_type": "snapshot_error", "message": str(e)})


class ChromeDevToolsInstagramSubAgent:
    """
    Scrapes Instagram via Chrome DevTools MCP — uses real Chrome with existing IG session.
    PRIMARY: LLM (GPT-4o) navigates IG using browser tools + JS extraction.
    FALLBACK: delegates to InstagramSubAgent (Playwright + tiers).
    """

    async def run(
        self,
        company_name: str,
        website_url: str | None = None,
        prior_web_contacts: list[dict] | None = None,
    ) -> SubAgentResult:
        from functools import partial
        start = time.monotonic()

        # 1. Check MCP availability
        mcp_client = get_mcp_browser()
        if not mcp_client:
            log.info("[CDPAgent] MCP_DEVTOOLS_URL not set — falling back to InstagramSubAgent")
            return await self._fallback(company_name, website_url, prior_web_contacts)

        available = await mcp_client.is_available()
        if not available:
            log.warning("[CDPAgent] MCP server not reachable — falling back to InstagramSubAgent")
            return await self._fallback(company_name, website_url, prior_web_contacts)

        # 2. LLM ReAct loop
        model = cfg.get("MCP_DEVTOOLS_MODEL", "gpt-4o")
        dispatch = {
            "navigate_to_ig_profile": partial(_cdp_navigate_tool, client=mcp_client),
            "extract_ig_data": partial(_cdp_evaluate_tool, client=mcp_client),
            "get_page_snapshot": partial(_cdp_snapshot_tool, client=mcp_client),
        }

        try:
            system_prompt = build_chrome_devtools_ig_prompt(company_name, website_url, prior_web_contacts)
            terminal_args, tokens = await _run_sub_agent_llm_loop(
                system_prompt=system_prompt,
                initial_message=f"Cari dan scrape Instagram untuk {company_name}",
                tool_schemas=_CHROME_IG_TOOLS,
                terminal_tools=_CHROME_IG_TERMINAL,
                tool_dispatch=dispatch,
                max_iterations=12,
                model_override=model,
            )
        except Exception as exc:
            log.warning("[CDPAgent] LLM loop failed for '%s': %s — falling back", company_name, exc)
            return await self._fallback(company_name, website_url, prior_web_contacts)

        # 3. Process result
        contacts = terminal_args.get("contacts", [])
        failure_reason = terminal_args.get("failure_reason")
        ig_handle = terminal_args.get("ig_handle_found")
        summary = terminal_args.get("summary", "")
        duration = time.monotonic() - start

        # Hard failures — do NOT trigger fallback (would waste quota with same result)
        no_fallback_reasons = {"session_expired", "checkpoint_required"}
        if not contacts and failure_reason in no_fallback_reasons:
            log.warning("[CDPAgent] Hard failure for '%s': %s — NOT falling back", company_name, failure_reason)
            return SubAgentResult(
                contacts=[],
                ig_handle=ig_handle,
                failure_reason=failure_reason,
                summary=f"CDP: {summary}",
                tokens_used=tokens,
                duration_seconds=duration,
                scrape_tier_used="chrome_devtools_mcp",
                success=False,
                error=failure_reason,
            )

        if contacts:
            log.info("[CDPAgent] '%s': %d contacts in %.1fs", company_name, len(contacts), duration)
            return SubAgentResult(
                contacts=contacts,
                ig_handle=ig_handle,
                summary=summary,
                tokens_used=tokens,
                duration_seconds=duration,
                scrape_tier_used="chrome_devtools_mcp",
                tool_calls_made=["chrome_devtools_llm"],
                success=True,
            )

        # 4. No contacts — try fallback
        log.info("[CDPAgent] '%s': 0 contacts (reason: %s) — trying fallback", company_name, failure_reason)
        return await self._fallback(company_name, website_url, prior_web_contacts)

    async def _fallback(
        self,
        company_name: str,
        website_url: str | None,
        prior_web_contacts: list[dict] | None,
    ) -> SubAgentResult:
        return await InstagramSubAgent().run(
            company_name=company_name,
            website_url=website_url,
            prior_web_contacts=prior_web_contacts,
        )


class WebFallbackSubAgent:
    """
    Additional web search fallback using broader queries.
    Wraps search_flow.web_search_fallback().
    Used when web_search + registry + instagram all failed.
    """

    async def run(self, company_name: str) -> SubAgentResult:
        start = time.monotonic()
        log.info("[WebFallbackSubAgent] Starting for: %s", company_name)
        try:
            results = await search_flow.web_search_fallback(company_name)
            contacts = _contacts_to_serializable(results)

            summary = (
                f"Web fallback: {len(contacts)} kontak ditemukan."
                if contacts
                else "Web fallback: tidak ada kontak ditemukan."
            )

            duration = time.monotonic() - start
            return SubAgentResult(
                contacts=contacts,
                tool_calls_made=["web_search_fallback"],
                summary=summary,
                duration_seconds=duration,
                success=True,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Web fallback gagal: {exc}",
                duration_seconds=duration,
            )
