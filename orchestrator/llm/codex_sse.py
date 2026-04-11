"""SSE parser for the Codex backend Responses API.

The Codex backend at ``chatgpt.com/backend-api/codex/responses`` always
streams its output as Server-Sent Events. Each event has the shape:

    event: <event-name>\n
    data: {"response": {...}}\n
    \n

with event names like ``response.created``, ``response.in_progress``,
``response.output_text.delta``, ``response.function_call_arguments.delta``,
``response.completed``, ``error``.

Each ``data:`` payload that contains a ``response`` field carries the
**latest snapshot** of the response object — by the time we reach
``response.completed`` (or the stream ends naturally), we have the
final, fully-populated response that we can return as if it came from
the public OpenAI API.

This module provides:

* ``iterate_sse_events(stream)`` — async generator over parsed events
* ``collect_completed_response(stream)`` — convenience that drains the
  stream and returns the final response dict (or raises ``CodexSSEError``)

Direct port of the TypeScript implementation in
``packages/openai-oauth-core/src/sse.ts``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import AsyncGenerator, AsyncIterable

import httpx


_SSE_SEPARATOR = re.compile(r"\r?\n\r?\n")
_LINE_SPLIT = re.compile(r"\r?\n")


@dataclass
class ServerSentEvent:
    event: str | None = None
    data: str | None = None


class CodexSSEError(Exception):
    """Raised when the SSE stream ends without a completed response."""


def _parse_event_block(block: str) -> ServerSentEvent:
    event = ServerSentEvent()
    data_lines: list[str] = []
    for line in _LINE_SPLIT.split(block):
        if line.startswith("event:"):
            event.event = line[len("event:"):].strip()
            continue
        if line.startswith("data:"):
            # The reference implementation uses .trimStart() — only strip
            # leading whitespace, not trailing (preserves intra-payload whitespace).
            data_lines.append(line[len("data:"):].lstrip())
    if data_lines:
        event.data = "\n".join(data_lines)
    return event


async def iterate_sse_events(
    response: httpx.Response,
) -> AsyncGenerator[ServerSentEvent, None]:
    """Yield ServerSentEvent objects from an httpx streaming response.

    Caller must have opened the response with ``client.stream("POST", ...)``.
    """
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while True:
            match = _SSE_SEPARATOR.search(buffer)
            if not match:
                break
            block = buffer[: match.start()]
            buffer = buffer[match.end():]
            if block.strip():
                yield _parse_event_block(block)

    if buffer.strip():
        yield _parse_event_block(buffer)


async def collect_completed_response(
    response: httpx.Response,
) -> dict:
    """Drain an SSE stream and return the final ``response`` snapshot.

    Mirrors ``collectCompletedResponseFromSse`` from openai-oauth-core.
    Raises ``CodexSSEError`` if no response is seen.
    """
    latest_response: dict | None = None
    latest_error: dict | None = None

    async for event in iterate_sse_events(response):
        if not event.data:
            continue
        try:
            parsed = json.loads(event.data)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue

        if event.event == "error":
            latest_error = parsed
            continue

        # Each progress event carries a snapshot of the response object.
        # The last one wins.
        candidate = parsed.get("response")
        if isinstance(candidate, dict):
            latest_response = candidate

    if latest_response is not None:
        return latest_response

    err_suffix = (
        f" Last error: {json.dumps(latest_error)}" if latest_error else ""
    )
    raise CodexSSEError(f"No completed response found in SSE stream.{err_suffix}")
