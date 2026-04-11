"""High-level Python client for ``chatgpt.com/backend-api/codex/responses``.

This is the in-process Python equivalent of what openclaw / pi-ai do
in TypeScript: take an OAuth-authenticated ChatGPT subscription and
use it to call the Codex backend's Responses API directly, returning
results in a shape that the OpenAI Python SDK consumers expect.

Public API:

* ``CodexClient.responses_create(**kwargs) -> openai.types.responses.Response``
  Drop-in replacement for ``openai.AsyncOpenAI().responses.create(...)``
  except routed through the ChatGPT subscription instead of the public
  API.

* ``CodexClient.is_available() -> bool``
  Quick check used by the gateway to decide whether to attempt the
  Codex path or skip straight to fallback.

The client is constructed once via ``get_codex_client()`` (lazy
singleton) and reused across calls. It manages its own httpx connection
pool but pulls fresh auth tokens from ``codex_token_store`` on every
call (so token refresh is transparent).

Wire format references:
- Headers: openai-oauth ``packages/openai-oauth-core/src/transport.ts``
- Body normalization: ``orchestrator/llm/codex_transformer.py``
- SSE parsing: ``orchestrator/llm/codex_sse.py``
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from orchestrator.config import cfg, log
from orchestrator.llm import codex_token_store
from orchestrator.llm.codex_oauth import DEFAULT_ORIGINATOR
from orchestrator.llm.codex_sse import CodexSSEError, collect_completed_response
from orchestrator.llm.codex_transformer import transform_responses_request

# --- constants ---------------------------------------------------------------

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"

# Headers that the Codex backend requires on every responses call
_OPENAI_BETA_VALUE = "responses=experimental"

# Connection-pool tuning
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)


# --- errors ------------------------------------------------------------------


class CodexError(Exception):
    """Base class for Codex client errors."""


class CodexAuthError(CodexError):
    """No valid token, or upstream returned 401/403."""


class CodexRateLimitError(CodexError):
    """Upstream returned 429 (subscription rate limit hit)."""

    def __init__(self, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class CodexUpstreamError(CodexError):
    """Upstream returned a non-2xx, non-429, non-401 status."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"Codex upstream HTTP {status_code}: {body[:300]}")
        self.status_code = status_code
        self.body = body


# --- response wrapper --------------------------------------------------------


class CodexResponse:
    """Lightweight wrapper that mimics the OpenAI SDK ``Response`` object.

    The orchestrator's existing call sites access fields like
    ``.output``, ``.output_text``, ``.usage``, ``.id``. Rather than
    take a hard dependency on the openai SDK's pydantic models (which
    can shift across versions), we expose those attributes via a thin
    wrapper around the raw upstream dict. This keeps decoupling clean
    and avoids version-pinning the SDK to a specific Response schema.
    """

    def __init__(self, data: dict):
        self._data = data

    # Direct dict accessor for callers that want the raw payload
    @property
    def raw(self) -> dict:
        return self._data

    @property
    def id(self) -> str | None:
        return self._data.get("id")

    @property
    def output(self) -> list:
        items = self._data.get("output") or []
        return [_OutputItem(item) for item in items]

    @property
    def output_text(self) -> str:
        """Concatenate text content from all message items in the output.

        Mirrors the behaviour of ``Response.output_text`` in the openai
        SDK: walk the output array, find ``message`` items, extract
        ``output_text`` content blocks, join them.
        """
        parts: list[str] = []
        for item in self._data.get("output") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            for block in item.get("content") or []:
                if not isinstance(block, dict):
                    continue
                # Codex backend returns text content as type=output_text
                if block.get("type") in ("output_text", "text"):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
        return "".join(parts)

    @property
    def usage(self) -> "_Usage | None":
        u = self._data.get("usage")
        if not isinstance(u, dict):
            return None
        return _Usage(u)


class _OutputItem:
    """Mimics ``ResponseOutputItem`` for ``response.output[i].type`` checks."""

    def __init__(self, data: dict):
        self._data = data

    @property
    def type(self) -> str:
        return self._data.get("type") or ""

    @property
    def name(self) -> str:
        return self._data.get("name") or ""

    @property
    def call_id(self) -> str:
        return self._data.get("call_id") or ""

    @property
    def arguments(self) -> str:
        return self._data.get("arguments") or ""

    @property
    def content(self) -> list:
        return self._data.get("content") or []

    def __getattr__(self, name: str) -> Any:
        # Fall through to the raw dict for any other field access
        return self._data.get(name)


class _Usage:
    """Mimics ``ResponseUsage`` for token-counting access patterns."""

    def __init__(self, data: dict):
        self._data = data

    @property
    def input_tokens(self) -> int:
        return int(self._data.get("input_tokens") or 0)

    @property
    def output_tokens(self) -> int:
        return int(self._data.get("output_tokens") or 0)

    @property
    def total_tokens(self) -> int:
        return int(self._data.get("total_tokens") or self.input_tokens + self.output_tokens)

    @property
    def input_tokens_details(self) -> "_UsageDetails | None":
        details = self._data.get("input_tokens_details")
        if isinstance(details, dict):
            return _UsageDetails(details)
        return None


class _UsageDetails:
    def __init__(self, data: dict):
        self._data = data

    @property
    def cached_tokens(self) -> int:
        return int(self._data.get("cached_tokens") or 0)


# --- client ------------------------------------------------------------------


class CodexClient:
    """In-process Python equivalent of openai-oauth's proxy.

    Build once, share across the orchestrator. Reads tokens fresh from
    ``codex_token_store`` on every call so the token refresh handled
    by the store is transparent to callers.
    """

    def __init__(self):
        self._http = httpx.AsyncClient(
            base_url=CODEX_BASE_URL,
            timeout=_HTTP_TIMEOUT,
        )
        self._session_id = str(uuid.uuid4())

    async def aclose(self) -> None:
        await self._http.aclose()

    async def is_available(self) -> bool:
        """True if the store currently has valid (or refreshable) tokens."""
        tokens = await codex_token_store.load_tokens()
        return tokens is not None

    async def responses_create(self, **kwargs: Any) -> CodexResponse:
        """Send a ``responses.create``-style request to the Codex backend.

        Returns a ``CodexResponse`` object compatible with the openai
        SDK's Response shape. Raises ``CodexAuthError`` /
        ``CodexRateLimitError`` / ``CodexUpstreamError`` on failure.
        """
        tokens = await codex_token_store.load_tokens()
        if tokens is None:
            raise CodexAuthError(
                "No Codex OAuth credentials available — login required."
            )
        if not tokens.account_id:
            raise CodexAuthError(
                "Codex token has no account_id; re-login may be required."
            )

        body = transform_responses_request(kwargs)
        body_json = json.dumps(body, ensure_ascii=False).encode("utf-8")

        headers = self._build_headers(
            access_token=tokens.access_token,
            account_id=tokens.account_id,
        )

        # We always stream — the Codex backend forces stream=true.
        # Use httpx's streaming response context to read SSE chunks.
        try:
            async with self._http.stream(
                "POST",
                "/responses",
                headers=headers,
                content=body_json,
            ) as response:
                if response.status_code == 401 or response.status_code == 403:
                    text = (await response.aread()).decode("utf-8", errors="replace")
                    raise CodexAuthError(
                        f"Codex auth failed (HTTP {response.status_code}): {text[:200]}"
                    )
                if response.status_code == 429:
                    text = (await response.aread()).decode("utf-8", errors="replace")
                    retry_after = _parse_retry_after(response.headers.get("retry-after"))
                    raise CodexRateLimitError(
                        f"Codex rate limit hit: {text[:200]}",
                        retry_after_seconds=retry_after,
                    )
                if response.status_code >= 400:
                    text = (await response.aread()).decode("utf-8", errors="replace")
                    raise CodexUpstreamError(response.status_code, text)

                final = await collect_completed_response(response)
        except (CodexAuthError, CodexRateLimitError, CodexUpstreamError):
            raise
        except CodexSSEError as e:
            raise CodexUpstreamError(0, f"SSE parse error: {e}") from e
        except httpx.HTTPError as e:
            raise CodexUpstreamError(0, f"HTTP error: {e}") from e

        return CodexResponse(final)

    def _build_headers(self, *, access_token: str, account_id: str) -> dict[str, str]:
        originator = str(cfg.get("CHATGPT_OAUTH_ORIGINATOR", DEFAULT_ORIGINATOR) or DEFAULT_ORIGINATOR)
        # Match openai-oauth header set exactly. Field names are
        # case-insensitive at the HTTP level but Codex backend has been
        # observed to be picky about a few — use lowercase for the
        # custom Codex headers.
        return {
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "OpenAI-Beta": _OPENAI_BETA_VALUE,
            "originator": originator,
            "session_id": self._session_id,
            "conversation_id": str(uuid.uuid4()),
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "GetContactAI-Codex-Client/1.0",
        }


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# --- module-level singleton --------------------------------------------------

_singleton: CodexClient | None = None


def get_codex_client() -> CodexClient:
    """Return the process-wide ``CodexClient`` (build on first call)."""
    global _singleton
    if _singleton is None:
        _singleton = CodexClient()
        log.info("[codex-client] initialized in-process Codex OAuth client")
    return _singleton


async def reset_codex_client() -> None:
    """Tear down the singleton (close HTTP pool). For tests / config changes."""
    global _singleton
    if _singleton is not None:
        try:
            await _singleton.aclose()
        except Exception:
            pass
        _singleton = None
