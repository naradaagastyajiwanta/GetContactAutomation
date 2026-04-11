"""LLM access layer for the orchestrator.

This package owns all OpenAI SDK call routing. Two backends:

1. **In-process Codex OAuth client** — talks directly to
   ``chatgpt.com/backend-api/codex/responses`` using OAuth credentials
   from a ChatGPT Plus/Pro subscription. No sidecar container; the
   OAuth flow, HTTP transport, request/response transformation, and
   SSE parsing are all implemented in pure Python (mirrors the
   openclaw / pi-ai approach).

2. **Real OpenAI API** — ``api.openai.com`` with ``OPENAI_API_KEY``.
   Used for embeddings (always; Codex backend doesn't expose them)
   and as the automatic fallback when Codex is disabled, rate-limited,
   or returns an auth error.

Public entry points:

* ``gateway.chat_completions_create(**kwargs)``
* ``gateway.responses_create(**kwargs)``
* ``gateway.embeddings_create(**kwargs)``

Files in this package:

* ``gateway.py`` — routing, fallback, cooldown, metrics
* ``client_factory.py`` — lazy singletons for both backends
* ``codex_client.py`` — high-level Codex HTTP client
* ``codex_oauth.py`` — OAuth PKCE flow + JWT decode
* ``codex_token_store.py`` — file-locked token persistence
* ``codex_transformer.py`` — Codex backend body normalization
* ``codex_sse.py`` — SSE event parser
* ``codex_chat_translator.py`` — Chat Completions ↔ Responses translation
"""
from orchestrator.llm import client_factory, gateway  # noqa: F401
