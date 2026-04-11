"""Bidirectional translator: Chat Completions API ↔ Responses API.

The Codex backend only exposes the Responses API. To keep the existing
``chat.completions.create`` call sites in the orchestrator working
without rewriting them, the gateway translates each call:

* request: chat-format ``messages`` → responses-format ``input`` + ``instructions``
* response: responses-format ``output`` → chat-format ``choices[0].message``

This module is the openclaw equivalent of what ``openai-oauth``'s
``chat-completions.ts`` does internally — it bridges the two API
shapes so callers don't need to know which backend they hit.

Coverage notes:
* Text + tool_calls: full support (used by react_agent, mkt_orchestrator)
* JSON mode (``response_format``): translated to ``text.format``
* Vision (``image_url`` content blocks): translated to ``input_image``
* Streaming chat completions: NOT supported — the orchestrator's
  call sites are non-streaming and translating SSE deltas isn't
  needed for our use case
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any


# --- request: chat → responses -----------------------------------------------


def chat_request_to_responses(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Convert ``chat.completions.create`` kwargs to ``responses.create`` kwargs.

    Returns a NEW dict ready to pass to the Codex backend (after the
    body normalizer adds ``store=False``, ``stream=True``, etc).
    """
    body: dict[str, Any] = {}

    if "model" in kwargs:
        body["model"] = kwargs["model"]

    messages = kwargs.get("messages") or []
    instructions, input_items = _split_messages(messages)
    if instructions:
        body["instructions"] = instructions
    body["input"] = input_items

    # Tools
    tools = kwargs.get("tools")
    if tools:
        body["tools"] = [_translate_tool(t) for t in tools if isinstance(t, dict)]
        # Filter out any None entries from invalid tool definitions
        body["tools"] = [t for t in body["tools"] if t is not None]

    tool_choice = kwargs.get("tool_choice")
    if tool_choice is not None:
        translated = _translate_tool_choice(tool_choice)
        if translated is not None:
            body["tool_choice"] = translated

    # Sampling params — Responses API uses the same names except max_tokens
    if "temperature" in kwargs:
        body["temperature"] = kwargs["temperature"]
    if "top_p" in kwargs:
        body["top_p"] = kwargs["top_p"]

    # max_tokens (chat) → max_output_tokens (responses).
    # NOTE: the Codex transformer strips max_output_tokens before sending
    # because the backend doesn't accept it. We still translate the field
    # name so non-Codex callers see the right key.
    if "max_tokens" in kwargs and "max_output_tokens" not in kwargs:
        body["max_output_tokens"] = kwargs["max_tokens"]
    elif "max_output_tokens" in kwargs:
        body["max_output_tokens"] = kwargs["max_output_tokens"]

    # Response format → text.format
    rf = kwargs.get("response_format")
    if isinstance(rf, dict):
        if rf.get("type") == "json_object":
            body["text"] = {"format": {"type": "json_object"}}
        elif rf.get("type") == "json_schema":
            body["text"] = {"format": rf}

    # Stream is not supported in our chat→responses path (non-streaming
    # callers only). Codex backend forces stream=true at the wire level
    # but we collect the full response before returning.
    if kwargs.get("stream"):
        # Caller asked for streaming chat completions — we don't support
        # that here. The Codex client will still stream internally but
        # we return a complete object, not an iterator.
        pass

    return body


def _split_messages(
    messages: list[dict],
) -> tuple[str, list[dict]]:
    """Pull system messages out into ``instructions`` and convert the rest.

    Multiple system messages are concatenated with double-newlines to
    preserve order. Tool messages and tool_calls are converted into
    ``function_call`` and ``function_call_output`` items.
    """
    system_parts: list[str] = []
    input_items: list[dict] = []

    # Build a map of tool_call_id → tool name from assistant messages so
    # we can correlate tool responses (Chat API doesn't include the name
    # in the tool message but Responses API needs it on function_call_output).
    tool_name_by_id: dict[str, str] = {}

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")

        if role in ("system", "developer"):
            text = _content_to_text(content)
            if text:
                system_parts.append(text)
            continue

        if role == "user":
            content_blocks = _user_content_to_responses_blocks(content)
            input_items.append({
                "role": "user",
                "content": content_blocks,
            })
            continue

        if role == "assistant":
            text = _content_to_text(content)
            tool_calls = msg.get("tool_calls") or []

            if text:
                input_items.append({
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": text},
                    ],
                })

            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                tc_id = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                name = fn.get("name") or "tool"
                args = fn.get("arguments") or "{}"
                tool_name_by_id[tc_id] = name
                input_items.append({
                    "type": "function_call",
                    "call_id": tc_id,
                    "name": name,
                    "arguments": args if isinstance(args, str) else json.dumps(args),
                })
            continue

        if role == "tool":
            tc_id = msg.get("tool_call_id") or ""
            output = content
            if not isinstance(output, str):
                try:
                    output = json.dumps(output)
                except Exception:
                    output = str(output)
            input_items.append({
                "type": "function_call_output",
                "call_id": tc_id,
                "output": output,
            })
            continue

    instructions = "\n\n".join(system_parts)
    return instructions, input_items


def _content_to_text(content: Any) -> str:
    """Flatten a chat-completions content field to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                t = item.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return str(content)


def _user_content_to_responses_blocks(content: Any) -> list[dict]:
    """Convert chat user content (string OR array of parts) to Responses blocks.

    Image inputs:
      Chat:      ``{"type": "image_url", "image_url": {"url": "..."}}``
      Responses: ``{"type": "input_image", "image_url": "..."}``
    """
    if content is None:
        return [{"type": "input_text", "text": ""}]
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    if not isinstance(content, list):
        return [{"type": "input_text", "text": str(content)}]

    blocks: list[dict] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text":
            text = item.get("text")
            if isinstance(text, str):
                blocks.append({"type": "input_text", "text": text})
        elif item_type == "image_url":
            image_url = item.get("image_url")
            url = None
            if isinstance(image_url, dict):
                url = image_url.get("url")
            elif isinstance(image_url, str):
                url = image_url
            if url:
                blocks.append({"type": "input_image", "image_url": url})
        elif item_type in ("input_text", "input_image"):
            # Already in responses format
            blocks.append(item)

    return blocks or [{"type": "input_text", "text": ""}]


def _translate_tool(tool: dict) -> dict | None:
    """Convert a chat ``tools[i]`` entry to a responses ``tools[i]`` entry.

    Chat:      ``{"type": "function", "function": {"name", "description", "parameters"}}``
    Responses: ``{"type": "function", "name", "description", "parameters"}``
    """
    if tool.get("type") != "function":
        return None
    fn = tool.get("function") or {}
    name = fn.get("name")
    if not name:
        return None
    out: dict[str, Any] = {
        "type": "function",
        "name": name,
    }
    if "description" in fn:
        out["description"] = fn["description"]
    if "parameters" in fn:
        out["parameters"] = fn["parameters"]
    if "strict" in fn:
        out["strict"] = fn["strict"]
    return out


def _translate_tool_choice(choice: Any) -> Any:
    if isinstance(choice, str):
        # "auto" / "none" / "required" — Responses API accepts these as-is
        return choice
    if isinstance(choice, dict):
        if choice.get("type") == "function":
            fn = choice.get("function") or {}
            name = fn.get("name")
            if name:
                return {"type": "function", "name": name}
    return None


# --- response: responses → chat ----------------------------------------------


def responses_to_chat_response(codex_response: Any, model: str) -> "ChatCompletionsResponse":
    """Convert a ``CodexResponse`` (or raw dict) into a chat-completions shape.

    Returned object exposes the same surface as the openai SDK's
    ``ChatCompletion`` (``.choices[0].message.content``,
    ``.choices[0].message.tool_calls``, ``.usage.prompt_tokens``,
    etc).
    """
    raw: dict
    if hasattr(codex_response, "raw"):
        raw = codex_response.raw
    elif isinstance(codex_response, dict):
        raw = codex_response
    else:
        raw = {}

    # Walk the output array, collecting text + tool_calls
    text_parts: list[str] = []
    tool_calls: list[dict] = []

    for item in raw.get("output") or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")

        if item_type == "message":
            for block in item.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") in ("output_text", "text"):
                    t = block.get("text")
                    if isinstance(t, str):
                        text_parts.append(t)
            continue

        if item_type == "function_call":
            call_id = item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:12]}"
            tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": item.get("name") or "",
                    "arguments": item.get("arguments") or "{}",
                },
            })
            continue

    text = "".join(text_parts) if text_parts else None

    # Determine finish_reason
    if tool_calls:
        finish_reason = "tool_calls"
    elif raw.get("status") == "incomplete":
        finish_reason = "length"
    else:
        finish_reason = "stop"

    message: dict[str, Any] = {
        "role": "assistant",
        "content": text,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls

    # Usage translation: Responses uses input_tokens/output_tokens,
    # Chat Completions uses prompt_tokens/completion_tokens.
    usage_dict: dict[str, int] = {}
    raw_usage = raw.get("usage")
    if isinstance(raw_usage, dict):
        usage_dict = {
            "prompt_tokens": int(raw_usage.get("input_tokens") or 0),
            "completion_tokens": int(raw_usage.get("output_tokens") or 0),
            "total_tokens": int(
                raw_usage.get("total_tokens")
                or (raw_usage.get("input_tokens", 0) + raw_usage.get("output_tokens", 0))
            ),
        }

    return ChatCompletionsResponse(
        id=raw.get("id") or f"chatcmpl_{uuid.uuid4().hex}",
        model=model,
        message=message,
        finish_reason=finish_reason,
        usage=usage_dict,
        created=int(time.time()),
    )


# --- response wrapper for chat completions shape -----------------------------


class _ChatChoiceMessage:
    def __init__(self, data: dict):
        self._data = data

    @property
    def role(self) -> str:
        return self._data.get("role") or "assistant"

    @property
    def content(self) -> str | None:
        return self._data.get("content")

    @property
    def tool_calls(self) -> list:
        return [_ChatToolCall(tc) for tc in (self._data.get("tool_calls") or [])]


class _ChatToolCall:
    def __init__(self, data: dict):
        self._data = data
        self._function = _ChatToolCallFunction(data.get("function") or {})

    @property
    def id(self) -> str:
        return self._data.get("id") or ""

    @property
    def type(self) -> str:
        return self._data.get("type") or "function"

    @property
    def function(self) -> "_ChatToolCallFunction":
        return self._function


class _ChatToolCallFunction:
    def __init__(self, data: dict):
        self._data = data

    @property
    def name(self) -> str:
        return self._data.get("name") or ""

    @property
    def arguments(self) -> str:
        return self._data.get("arguments") or "{}"


class _ChatChoice:
    def __init__(self, *, index: int, message: dict, finish_reason: str):
        self.index = index
        self.message = _ChatChoiceMessage(message)
        self.finish_reason = finish_reason


class _ChatUsage:
    def __init__(self, data: dict):
        self.prompt_tokens = int(data.get("prompt_tokens") or 0)
        self.completion_tokens = int(data.get("completion_tokens") or 0)
        self.total_tokens = int(data.get("total_tokens") or 0)


class ChatCompletionsResponse:
    """Mimics ``openai.types.chat.ChatCompletion``."""

    def __init__(
        self,
        *,
        id: str,
        model: str,
        message: dict,
        finish_reason: str,
        usage: dict,
        created: int,
    ):
        self.id = id
        self.model = model
        self.created = created
        self.object = "chat.completion"
        self.choices = [_ChatChoice(index=0, message=message, finish_reason=finish_reason)]
        self.usage = _ChatUsage(usage) if usage else None
