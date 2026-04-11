"""Request body transforms for the Codex backend.

The ChatGPT backend at ``chatgpt.com/backend-api/codex/responses`` is
**stateless** and only supports the GPT-5 / Codex model family. This
module mirrors the transformations done by the ``openai-oauth``
reference implementation (and the equivalent ``pi-ai`` library used
by openclaw):

* Force ``store=False``
* Force ``stream=True`` (the backend always streams)
* Strip ``previous_response_id`` (no session chaining)
* Strip ``id`` from input items (the backend re-issues IDs)
* Add ``include=["reasoning.encrypted_content"]`` for reasoning continuity
* Drop ``max_output_tokens`` and ``max_completion_tokens``
* **Normalize the model name** — legacy names like ``gpt-4o``,
  ``gpt-4o-mini``, ``gpt-3.5-turbo`` are silently rewritten to
  ``gpt-5.4`` (or whichever Codex-compatible default is configured)
  because the backend rejects them with HTTP 400.
* Inject default reasoning effort + text verbosity for GPT-5 family

Returns a NEW dict — the input is never mutated.
"""
from __future__ import annotations

from typing import Any


# --- model normalization -------------------------------------------------
#
# The Codex backend accepts only the GPT-5 / Codex family. If a caller
# passes a legacy model name (gpt-4o-mini, gpt-4o, gpt-4-turbo, etc.) we
# silently rewrite it to a Codex-compatible model. This is the same
# pattern used by openai-oauth's request-transformer.ts.

# Default Codex-compatible model when nothing else matches
_DEFAULT_CODEX_MODEL = "gpt-5.4"

# Models that the Codex backend is known to accept (kept as a substring
# whitelist — exact matches like ``gpt-5.4-pro`` count as ``gpt-5.4``).
_CODEX_SUPPORTED_PREFIXES = (
    "gpt-5.4",
    "gpt-5.3",
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5-codex",
    "gpt-5",
    "codex-mini",
    "o1",
    "o3",
    "o4",
)


def normalize_model_for_codex(model: str | None) -> str:
    """Map any model name to a Codex-backend-compatible value.

    * ``None`` / empty → default Codex model
    * Already in the Codex whitelist → returned unchanged
    * Legacy ``gpt-4*`` / ``gpt-3.5*`` → rewritten to default Codex model
    * Provider-prefixed ``openai/gpt-5.4`` → strip prefix, then check
    """
    if not model:
        return _DEFAULT_CODEX_MODEL

    # Strip provider prefix if present (e.g. "openai/gpt-5.4" → "gpt-5.4")
    name = model.strip()
    if "/" in name:
        name = name.rsplit("/", 1)[-1]

    lower = name.lower()
    for prefix in _CODEX_SUPPORTED_PREFIXES:
        if lower.startswith(prefix):
            return name

    # Anything else (gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo,
    # text-embedding-*, etc.) gets rewritten to the default. The
    # gateway will surface the substitution in metrics — callers should
    # update their hardcoded model names to use the project default.
    return _DEFAULT_CODEX_MODEL


# --- input filter --------------------------------------------------------


def _strip_input_ids(items: list[dict]) -> list[dict]:
    """Remove ``id`` field from input items (Codex backend re-issues them).

    Also drops AI-SDK-specific item types like ``item_reference`` that
    refer to server-side state we don't have.
    """
    cleaned: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            cleaned.append(item)
            continue
        if item.get("type") == "item_reference":
            # AI SDK construct — references server state, drop it
            continue
        without_id = {k: v for k, v in item.items() if k != "id"}
        cleaned.append(without_id)
    return cleaned


# --- reasoning effort defaults -------------------------------------------


_REASONING_EFFORT_NORMAL = "medium"


def _build_reasoning_block(
    model: str,
    existing: dict | None,
) -> dict:
    """Build the ``reasoning`` block for a Responses API request.

    GPT-5 family models support ``effort`` (``none|low|medium|high|xhigh``)
    and ``summary`` (``auto|concise|detailed``). We default to
    ``effort=medium`` and ``summary=auto`` to match Codex CLI behaviour.
    """
    existing = existing or {}
    return {
        "effort": existing.get("effort") or _REASONING_EFFORT_NORMAL,
        "summary": existing.get("summary") or "auto",
    }


def _build_text_block(existing: dict | None) -> dict:
    existing = existing or {}
    return {
        "verbosity": existing.get("verbosity") or "medium",
    }


# --- main transform -----------------------------------------------------


# Fields that are always stripped before sending to the Codex backend.
# The Codex backend exposes only GPT-5 / reasoning-family models which
# do not accept temperature / top_p / max_tokens-style parameters, and
# the backend explicitly returns 400 ``Unsupported parameter`` for any
# of these.
_STRIP_FIELDS = frozenset({
    "previous_response_id",
    "max_output_tokens",
    "max_completion_tokens",
    "max_tokens",
    "temperature",
    "top_p",
    "presence_penalty",
    "frequency_penalty",
    "logit_bias",
    "logprobs",
    "top_logprobs",
    "n",
    "seed",
    # The OpenAI SDK sometimes adds these — Codex backend doesn't accept
    # them.
    "extra_body",
    "extra_headers",
    "extra_query",
})


def transform_responses_request(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return a Codex-backend-compatible copy of a ``responses.create`` body.

    Mutations applied:
      * ``store`` → False (mandatory)
      * ``stream`` → True (mandatory)
      * Strip blacklisted fields
      * Strip IDs from ``input`` items
      * Add ``include=["reasoning.encrypted_content"]``
      * Inject ``reasoning`` and ``text`` blocks for GPT-5 family
    """
    body: dict[str, Any] = {
        k: v for k, v in kwargs.items() if k not in _STRIP_FIELDS
    }

    body["store"] = False
    body["stream"] = True

    # Normalize model name — Codex backend rejects legacy gpt-4o /
    # gpt-4o-mini etc with HTTP 400. Silent rewrite to a Codex-supported
    # model so existing call sites with hardcoded legacy names keep
    # working when CHATGPT_OAUTH_ENABLED=true.
    body["model"] = normalize_model_for_codex(body.get("model"))

    # Filter input items
    if isinstance(body.get("input"), list):
        body["input"] = _strip_input_ids(body["input"])

    # ``include`` defaults — preserve existing values, ensure
    # encrypted_content is present
    include = body.get("include") or []
    if not isinstance(include, list):
        include = []
    if "reasoning.encrypted_content" not in include:
        include = list(include) + ["reasoning.encrypted_content"]
    body["include"] = include

    # Reasoning + text defaults (only relevant for GPT-5 family models;
    # cheap to send for all models since the backend ignores unknown
    # fields gracefully).
    model = str(body.get("model") or "")
    if model.startswith("gpt-5") or "codex" in model:
        body["reasoning"] = _build_reasoning_block(model, body.get("reasoning"))
        body["text"] = _build_text_block(body.get("text"))

    return body
