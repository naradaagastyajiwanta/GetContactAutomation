"""
Shared Gemini caller with Google Search grounding.

Extracts reusable logic from the original audiensi_research.py so that
every agent can make focused Gemini calls and get resolved grounding URLs.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from typing import Any

from google import genai
from google.genai import types

from orchestrator.config import log, cfg

# ---------------------------------------------------------------------------
# Gemini client singleton
# ---------------------------------------------------------------------------

_client: genai.Client | None = None

GEMINI_MODEL = "gemini-3.1-pro-preview"
GEMINI_MAX_OUTPUT_TOKENS = 4096
GEMINI_MAX_ATTEMPTS = 2


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = cfg.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not configured")
        _client = genai.Client(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# URL resolution (grounding redirect → permanent URL)
# ---------------------------------------------------------------------------


def _resolve_redirect(url: str, timeout: float = 5.0) -> str:
    """Follow Vertex AI Search redirect and return the final destination URL."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final = resp.geturl()
            if final and final != url:
                return final
    except Exception:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                final = resp.geturl()
                if final and final != url:
                    return final
        except Exception as e:
            log.debug("Could not resolve redirect %s: %s", url[:80], e)
    return url


def _extract_grounding_urls(response: Any) -> list[str]:
    """Extract and resolve real URLs from Gemini grounding metadata."""
    raw_urls: list[str] = []
    try:
        candidates = response.candidates or []
        for candidate in candidates:
            gm = getattr(candidate, "grounding_metadata", None)
            if not gm:
                continue

            # Primary source: grounding_chunks (populated for non-JSON output)
            chunks = getattr(gm, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if web:
                    uri = getattr(web, "uri", None)
                    if uri and uri.startswith("http"):
                        raw_urls.append(uri)

            # Fallback: extract URLs from search_entry_point.rendered_content
            # When Gemini outputs structured JSON, grounding_chunks is often
            # empty but the redirect URLs are still embedded as href links
            # in the rendered HTML widget.
            if not raw_urls:
                sep = getattr(gm, "search_entry_point", None)
                if sep:
                    rc = getattr(sep, "rendered_content", None) or ""
                    hrefs = re.findall(r'href="(https?://[^"]+)"', rc)
                    for href in hrefs:
                        if href not in raw_urls:
                            raw_urls.append(href)
                    if hrefs:
                        log.info(
                            "Extracted %d grounding URLs from rendered_content (grounding_chunks was empty)",
                            len(hrefs),
                        )
    except Exception as e:
        log.warning("Failed to extract grounding URLs: %s", e)

    # Deduplicate
    seen_raw: set[str] = set()
    deduped: list[str] = []
    for u in raw_urls:
        if u not in seen_raw:
            seen_raw.add(u)
            deduped.append(u)

    # Resolve redirects → permanent URLs
    resolved: list[str] = []
    seen_final: set[str] = set()
    for u in deduped:
        final = _resolve_redirect(u)
        if final not in seen_final:
            seen_final.add(final)
            resolved.append(final)
            log.debug("Grounding resolved: %s", final[:120])

    return resolved


# ---------------------------------------------------------------------------
# Parse JSON from Gemini response
# ---------------------------------------------------------------------------


def parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from Gemini response, handling code blocks and partial JSON."""
    text = text.strip()

    # 1. Try to extract from markdown code blocks first (most reliable if there is chatter)
    import re
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2. Remove markdown code blocks (fallback if started with ``` but not matched above)
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Find JSON object in text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    # 4. Find JSON list in text
    start_list = text.find("[")
    end_list = text.rfind("]") + 1
    if start_list >= 0 and end_list > start_list:
        try:
            return json.loads(text[start_list:end_list])
        except json.JSONDecodeError:
            pass

    log.warning("Could not parse Gemini response as JSON (len=%d). Raw: %s", len(text), text[:500])
    return {"_raw": text[:3000], "_parse_failed": True}


# ---------------------------------------------------------------------------
# Core Gemini call
# ---------------------------------------------------------------------------


async def call_gemini(
    prompt: str,
    *,
    use_search_grounding: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """
    Make a single Gemini API call and return (parsed_json, grounding_urls).

    Google Search grounding is ALWAYS enabled by default to ensure every
    response is backed by real sources.  Only set ``use_search_grounding=False``
    for internal synthetic prompts (e.g. reviewer summarization).

    Parameters
    ----------
    prompt : str
        The full prompt text.
    use_search_grounding : bool
        Whether to attach Google Search tool for grounding.
        Default True — should almost never be False.

    Returns
    -------
    tuple[dict, list[str]]
        Parsed JSON response and list of resolved grounding URLs.
    """
    client = _get_client()

    # Always use Google Search grounding for factual accuracy.
    tools = [types.Tool(google_search=types.GoogleSearch())] if use_search_grounding else []
    config = types.GenerateContentConfig(
        tools=tools,
        temperature=0,
        max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        response_mime_type="application/json",
    )

    retry_instruction = (
        "\n\nIMPORTANT: Return exactly one complete JSON value that matches the requested schema. "
        "Do not add markdown, commentary, or trailing text."
    )
    effective_prompt = prompt

    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=effective_prompt)],
            ),
        ]

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=GEMINI_MODEL,
            contents=contents,
            config=config,
        )

        raw_text = response.text or ""
        log.info("Gemini call response length: %d chars (attempt %d)", len(raw_text), attempt)

        grounding_urls = _extract_grounding_urls(response) if use_search_grounding else []
        if grounding_urls:
            log.info("Grounding URLs: %d resolved", len(grounding_urls))
        elif use_search_grounding:
            log.warning("Gemini returned NO grounding URLs — response may be unverified")

        parsed = parse_json_response(raw_text)
        if not parsed.get("_parse_failed"):
            return parsed, grounding_urls

        if attempt == GEMINI_MAX_ATTEMPTS:
            return parsed, grounding_urls

        log.warning("Gemini JSON parse failed on attempt %d, retrying with stricter formatting instructions", attempt)
        effective_prompt = f"{prompt}{retry_instruction}"

    return {"_raw": "", "_parse_failed": True}, []
