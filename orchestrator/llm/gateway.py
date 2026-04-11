"""LLM gateway: routes calls to in-process Codex OAuth or real OpenAI API.

This is the single dispatch point for every OpenAI SDK call in the
orchestrator. Two flavours:

* ``responses_create(**kwargs)`` — Responses API. Routes to the
  ``CodexClient`` (in-process Python OAuth flow) when
  ``CHATGPT_OAUTH_ENABLED`` is true, falls back to ``api.openai.com``
  otherwise (or on error / rate-limit cooldown).

* ``chat_completions_create(**kwargs)`` — Chat Completions API. When
  routing through Codex, the request is translated to Responses API
  format on the way out and the response is translated back on the
  way in (mirrors what openai-oauth's chat-completions handler does).

* ``embeddings_create(**kwargs)`` — always real API. Codex backend
  doesn't expose ``/v1/embeddings``.

Resilience features:

* **Automatic fallback** to real API on Codex 401 / 429 / connection
  errors when ``CHATGPT_OAUTH_FALLBACK_TO_API`` is true.
* **Rate-limit cooldown** — 429 trips a process-local cooldown timer
  (default 15 min). All chat/responses calls go straight to the real
  API during cooldown without even attempting Codex.
* **Metrics** — counters per backend exposed via
  ``GET /health/llm-metrics``.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError

from orchestrator.config import cfg, log
from orchestrator.llm.client_factory import get_codex, get_real_client
from orchestrator.llm.codex_chat_translator import (
    ChatCompletionsResponse,
    chat_request_to_responses,
    responses_to_chat_response,
)
from orchestrator.llm.codex_client import (
    CodexAuthError,
    CodexRateLimitError,
    CodexResponse,
    CodexUpstreamError,
)

# --- module state ------------------------------------------------------------

# Monotonic timestamp until which Codex is considered cooling down
_codex_cooldown_until: float = 0.0

_metrics: dict[str, int] = {
    "codex_chat_calls": 0,
    "codex_responses_calls": 0,
    "codex_errors": 0,
    "codex_rate_limits": 0,
    "codex_auth_errors": 0,
    "fallback_chat_calls": 0,
    "fallback_responses_calls": 0,
    "direct_chat_calls": 0,
    "direct_responses_calls": 0,
    "direct_embeddings_calls": 0,
}


# --- public coroutines -------------------------------------------------------


async def chat_completions_create(**kwargs: Any) -> Any:
    """Codex-OAuth-first wrapper around ``client.chat.completions.create``.

    When Codex is the active backend, the chat-format request is
    translated to a Responses API request, sent to the Codex backend,
    and the response is translated back. The returned object exposes
    the same surface as the openai SDK's ChatCompletion (``.choices``,
    ``.usage``, etc).
    """
    if _should_use_codex():
        try:
            _metrics["codex_chat_calls"] += 1
            translated = chat_request_to_responses(kwargs)
            codex_response = await get_codex().responses_create(**translated)
            return responses_to_chat_response(codex_response, model=kwargs.get("model") or "")
        except CodexRateLimitError as e:
            _trip_cooldown(e.retry_after_seconds)
            if not cfg.CHATGPT_OAUTH_FALLBACK_TO_API:
                raise
            log.warning("[llm-gateway] Codex rate-limited, falling back to real API")
        except CodexAuthError as e:
            _metrics["codex_auth_errors"] += 1
            if not cfg.CHATGPT_OAUTH_FALLBACK_TO_API:
                raise
            log.warning("[llm-gateway] Codex auth error, falling back: %s", e)
        except CodexUpstreamError as e:
            _metrics["codex_errors"] += 1
            if not cfg.CHATGPT_OAUTH_FALLBACK_TO_API:
                raise
            log.warning("[llm-gateway] Codex upstream error, falling back: %s", e)

        _metrics["fallback_chat_calls"] += 1
        return await _call_real_chat(kwargs)

    _metrics["direct_chat_calls"] += 1
    return await _call_real_chat(kwargs)


async def responses_create(**kwargs: Any) -> Any:
    """Codex-OAuth-first wrapper around ``client.responses.create``.

    When Codex is active, ``previous_response_id`` is silently
    stripped (Codex backend is stateless). The returned object
    exposes ``.output``, ``.output_text``, ``.usage`` like the openai
    SDK's Response.

    Callers that need the openai SDK's full Pydantic Response object
    (e.g. for downstream serialization) should not use this gateway —
    they should call ``get_real_client().responses.create`` directly.
    """
    if _should_use_codex():
        try:
            _metrics["codex_responses_calls"] += 1
            return await get_codex().responses_create(**kwargs)
        except CodexRateLimitError as e:
            _trip_cooldown(e.retry_after_seconds)
            if not cfg.CHATGPT_OAUTH_FALLBACK_TO_API:
                raise
            log.warning("[llm-gateway] Codex rate-limited, falling back to real API")
        except CodexAuthError as e:
            _metrics["codex_auth_errors"] += 1
            if not cfg.CHATGPT_OAUTH_FALLBACK_TO_API:
                raise
            log.warning("[llm-gateway] Codex auth error, falling back: %s", e)
        except CodexUpstreamError as e:
            _metrics["codex_errors"] += 1
            if not cfg.CHATGPT_OAUTH_FALLBACK_TO_API:
                raise
            log.warning("[llm-gateway] Codex upstream error, falling back: %s", e)

        _metrics["fallback_responses_calls"] += 1
        return await _call_real_responses(kwargs)

    _metrics["direct_responses_calls"] += 1
    return await _call_real_responses(kwargs)


async def embeddings_create(**kwargs: Any) -> Any:
    """Always-real-API wrapper around ``client.embeddings.create``.

    The Codex backend does not expose ``/v1/embeddings``. Callers
    using this wrapper get a uniform import path while embeddings
    transparently bypass the Codex routing.
    """
    _metrics["direct_embeddings_calls"] += 1
    return await get_real_client().embeddings.create(**kwargs)


# --- metrics + cooldown helpers ---------------------------------------------


def get_metrics() -> dict[str, Any]:
    cooldown_remaining = max(0.0, _codex_cooldown_until - time.monotonic())
    return {
        **_metrics,
        "cooldown_remaining_seconds": round(cooldown_remaining, 1),
        "oauth_enabled": bool(cfg.CHATGPT_OAUTH_ENABLED),
        "fallback_enabled": bool(cfg.CHATGPT_OAUTH_FALLBACK_TO_API),
    }


def reset_metrics() -> None:
    for key in list(_metrics.keys()):
        _metrics[key] = 0


def reset_cooldown() -> None:
    global _codex_cooldown_until
    _codex_cooldown_until = 0.0


# --- internal helpers --------------------------------------------------------


def _should_use_codex() -> bool:
    if not cfg.CHATGPT_OAUTH_ENABLED:
        return False
    if time.monotonic() < _codex_cooldown_until:
        return False
    return True


def _trip_cooldown(retry_after_seconds: int | None = None) -> None:
    global _codex_cooldown_until
    _metrics["codex_rate_limits"] += 1
    cooldown = retry_after_seconds or int(
        cfg.get("CHATGPT_OAUTH_RATE_LIMIT_COOLDOWN_SECONDS", 900) or 900
    )
    _codex_cooldown_until = time.monotonic() + cooldown
    log.warning(
        "[llm-gateway] Codex rate-limited (429), cooldown armed for %ds",
        cooldown,
    )
    _broadcast_rate_limit_notification(cooldown)


def _broadcast_rate_limit_notification(cooldown_seconds: int) -> None:
    """Push a WebSocket notification so the FE can show a toast / banner.

    Fire-and-forget — never blocks or raises into the gateway path. The
    FE listens for ``codex_rate_limited`` events on its WebSocket and
    surfaces them as a notification with the cooldown duration so the
    user knows traffic has temporarily fallen back to the real OpenAI
    API key.
    """
    try:
        from orchestrator.websocket import manager as ws_manager
    except Exception:
        return

    payload = {
        "type": "codex_rate_limited",
        "cooldown_seconds": int(cooldown_seconds),
        "fallback_active": bool(cfg.get("CHATGPT_OAUTH_FALLBACK_TO_API", True)),
        "message": (
            f"ChatGPT subscription rate limit reached. "
            f"Falling back to OpenAI API for the next {cooldown_seconds // 60} minutes."
        ),
    }

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — gateway must always be called from async,
        # but defend in case _trip_cooldown is invoked in a sync context.
        return

    async def _send():
        try:
            await ws_manager.broadcast(payload)
        except Exception as e:
            log.debug("[llm-gateway] failed to broadcast rate-limit notification: %s", e)

    loop.create_task(_send())


async def _call_real_chat(kwargs: dict) -> Any:
    return await get_real_client().chat.completions.create(**kwargs)


async def _call_real_responses(kwargs: dict) -> Any:
    return await get_real_client().responses.create(**kwargs)
