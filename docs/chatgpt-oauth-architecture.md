# ChatGPT OAuth — Architecture (In-Process Python Flow)

Technical deep-dive on how the orchestrator routes OpenAI calls
through a ChatGPT Plus subscription **without any sidecar container**.
Inspired by openclaw / pi-ai (TypeScript), implemented in Python.

## High-Level Diagram

```
┌──────────────────────────────────┐
│ Orchestrator (FastAPI, :8000)    │
│                                  │
│  conversation.py  ──┐            │
│  react_agent.py   ──┤            │
│  mkt_orchestrator ──┤            │
│  instagram.py     ──┤            │
│  learning.py      ──┤            │
│  osint/tools.py   ──┤            │
│                     │            │
│                     ▼            │
│       orchestrator/llm/gateway.py│
│        ├── chat_completions_create
│        │     (translates to /responses)
│        ├── responses_create      │
│        └── embeddings_create     │
└────┬─────────┬───────────────┬───┘
     │         │               │ (always direct)
     │         │               ▼
     │         │       ┌──────────────────┐
     │         │       │ api.openai.com   │
     │         │       │ /v1/embeddings   │
     │         │       └──────────────────┘
     │         │
     │ OAuth   │ OAuth disabled OR cooldown OR fallback
     │ enabled │
     ▼         ▼
┌────────────────┐  ┌──────────────────┐
│ CodexClient    │  │ AsyncOpenAI      │
│ (httpx + OAuth)│  │ api.openai.com   │
└────────┬───────┘  │ /v1/chat/...     │
         │          │ /v1/responses    │
         │          └──────────────────┘
         │ Bearer <access_token from auth.json>
         │ chatgpt-account-id: <from JWT>
         │ OpenAI-Beta: responses=experimental
         │ originator: codex_cli_rs
         ▼
┌────────────────────────────────┐
│ chatgpt.com/backend-api/codex  │
│  /responses                    │
└─────────────┬──────────────────┘
              │
              ▼
      ChatGPT Plus/Pro
       subscription
```

**What's gone:** the Docker `chatgpt-proxy` sidecar that previous
revisions of this plan used. Everything that sidecar did is now
implemented as Python modules inside the orchestrator process.

## Module Layout

All new code lives under `orchestrator/llm/`:

| File | Responsibility |
|---|---|
| `__init__.py` | Re-exports `gateway` and `client_factory` for convenience |
| `client_factory.py` | Lazy singletons: `get_real_client()` (AsyncOpenAI) and `get_codex()` (CodexClient) |
| `codex_oauth.py` | PKCE flow, token exchange, refresh, JWT decode |
| `codex_token_store.py` | File-locked persistence at `data/codex_auth/auth.json` + `import_external_codex_auth()` |
| `codex_login_server.py` | Local aiohttp callback server bound to `localhost:1455` during login |
| `codex_transformer.py` | Codex backend body normalization (`store=false`, `stream=true`, etc) |
| `codex_sse.py` | SSE event parser, `collect_completed_response()` |
| `codex_client.py` | High-level `CodexClient.responses_create(**kwargs) -> CodexResponse` |
| `codex_chat_translator.py` | Bidirectional Chat Completions ↔ Responses API translation |
| `gateway.py` | Routing, fallback, cooldown, metrics — single dispatch point |

## OAuth Flow

The OAuth flow is **PKCE Authorization Code Flow** — same as the
official Codex CLI and openclaw / pi-ai.

### Constants

```python
CLIENT_ID     = "app_EMoamEEZ73f0CkXaXp7hrann"          # Codex CLI client
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL     = "https://auth.openai.com/oauth/token"
REDIRECT_URI  = "http://localhost:1455/auth/callback"

# Basic scopes registered for the Codex CLI client_id.
SCOPES = (
    "openid", "profile", "email", "offline_access",
)
```

> **Note on openclaw scopes:** Earlier drafts of this implementation
> tried to add openclaw's extra scopes ``model.request`` and
> ``api.responses.write``. Those scopes are valid for openclaw / pi-ai
> because they're tied to a *different* OAuth client_id that pi-ai
> uses internally. Sending them with the Codex CLI client_id results
> in HTTP 400 ``invalid_scope`` from ``auth.openai.com``. The basic
> four scopes above are sufficient — the resulting access token has
> permission to call ``/backend-api/codex/responses`` because that
> grant is tied to the Codex CLI client_id itself, not to a scope.

### Login sequence

1. **`begin_login()`** in `codex_login_server.py`:
   - Generate PKCE pair (`verifier` + `S256(verifier)`)
   - Generate random `state`
   - Build authorize URL with all params (scopes, PKCE, originator, etc)
   - Spawn `aiohttp.web` server on `127.0.0.1:1455` with route
     `GET /auth/callback`
   - Return `AuthorizationFlow` with the URL — caller (FastAPI
     handler) returns this to the FE

2. **User completes OAuth in browser** → OpenAI redirects to
   `http://localhost:1455/auth/callback?code=...&state=...`

3. **`_handle_callback()`** in `codex_login_server.py`:
   - Validate state matches the one we sent
   - Set the in-memory `Future` with `{"code": ..., "state": ...}`
   - Return success HTML page

4. **`wait_for_login_result()`** unblocks (the FastAPI handler that
   was awaiting the future)

5. **`exchange_authorization_code()`** in `codex_oauth.py`:
   - POST to `https://auth.openai.com/oauth/token` with
     `grant_type=authorization_code`, the code, the PKCE verifier
   - Receive `{access_token, refresh_token, expires_in, id_token}`
   - Decode the JWT (`id_token` or `access_token` — both are JWTs in
     this flow) and extract `chatgpt_account_id` from the
     `https://api.openai.com/auth` claim namespace

6. **`save_tokens()`** in `codex_token_store.py`:
   - Write `data/codex_auth/auth.json` atomically (write-then-rename)
   - Tighten file mode to `0600` on POSIX
   - Cache the tokens in-memory

### Token refresh

`load_tokens()` checks `expires_at` on every call:

- If valid (more than 60 seconds remaining) → return cached tokens
- If expired or near-expiry → call `refresh_access_token(refresh_token)`,
  which POSTs `grant_type=refresh_token` to the same token endpoint,
  overwrites the on-disk file, and returns the fresh tokens

The refresh runs under an `asyncio.Lock`, so concurrent gateway calls
don't trigger duplicate refreshes.

### External CLI mirror (token sink-lite)

`import_external_codex_auth()` reads `~/.codex/auth.json` (the file
the official `codex` CLI maintains) and copies it into our store.
Useful for users who already log in via the CLI on the host.

Unlike openclaw's full token-sink pattern (which keeps re-reading
the external file and never rotates the token), this is a one-shot
import — after import, the orchestrator manages refreshes from its
own copy. This is simpler at the cost of not auto-syncing if you
re-run `codex login` later.

## HTTP Client (`codex_client.py`)

The `CodexClient` class is a thin httpx wrapper that:

1. Pulls fresh tokens from `codex_token_store.load_tokens()` on every
   call (so refresh is transparent)
2. Builds the request body via `codex_transformer.transform_responses_request()`
   (forces `store=false`, `stream=true`, strips disallowed fields)
3. Constructs the headers:
   ```python
   {
     "Authorization":     f"Bearer {access_token}",
     "chatgpt-account-id": account_id,
     "OpenAI-Beta":       "responses=experimental",
     "originator":        cfg.CHATGPT_OAUTH_ORIGINATOR or "codex_cli_rs",
     "session_id":        "<uuid per CodexClient instance>",
     "conversation_id":   "<uuid per call>",
     "Content-Type":      "application/json",
     "Accept":            "text/event-stream",
   }
   ```
4. POSTs to `https://chatgpt.com/backend-api/codex/responses` using
   httpx's `client.stream()` context (we always need streaming
   response support)
5. Routes status codes:
   - **401 / 403** → raise `CodexAuthError`
   - **429** → raise `CodexRateLimitError(retry_after_seconds=...)`
   - **other 4xx / 5xx** → raise `CodexUpstreamError`
   - **200** → continue to SSE parsing
6. Calls `codex_sse.collect_completed_response()` to drain the SSE
   stream into a final `dict`
7. Wraps the dict in a `CodexResponse` object that exposes
   `.id`, `.output`, `.output_text`, `.usage` — the same surface
   the orchestrator's call sites expect from the openai SDK's
   `Response` object

## SSE Parser (`codex_sse.py`)

Direct port of `openai-oauth-core/src/sse.ts`:

- Reads bytes from the httpx streaming response via `aiter_text()`
- Buffers until a `\n\n` (or `\r\n\r\n`) separator appears
- Parses each event block: lines starting with `event:` or `data:`
- Yields `ServerSentEvent(event=..., data=...)` objects

`collect_completed_response()` walks the event stream and keeps the
**latest `parsed.response`** seen. The Codex backend emits
`response.in_progress` events with progressive snapshots, and the
final `response.completed` event has the fully-populated payload.
We just take the last one.

## Chat Completions Translator (`codex_chat_translator.py`)

The Codex backend only exposes `/responses`, but our orchestrator has
many call sites using `chat.completions.create()`. The translator
handles both directions transparently inside the gateway:

### Request: chat → responses

- `messages[role=system]` → top-level `instructions` (concatenated
  with `\n\n` if multiple)
- `messages[role=user]` → `input[].role=user` with content blocks
  (`input_text` and `input_image`, with image_url translation)
- `messages[role=assistant]` with text → `input[].role=assistant`
  with `output_text` blocks
- `messages[role=assistant]` with `tool_calls` → separate
  `function_call` items in `input[]`
- `messages[role=tool]` → `function_call_output` items in `input[]`
- `tools[i].function.{name,description,parameters}` → flattened
  `tools[i].{name,description,parameters}`
- `max_tokens` → `max_output_tokens`
- `response_format.type=json_object` → `text.format.type=json_object`

### Response: responses → chat

- `output[type=message]` blocks → `choices[0].message.content`
  (joined text)
- `output[type=function_call]` items → `choices[0].message.tool_calls`
- `usage.input_tokens` → `usage.prompt_tokens`
- `usage.output_tokens` → `usage.completion_tokens`
- Returns a `ChatCompletionsResponse` wrapper that mimics the openai
  SDK's `ChatCompletion` shape

## Gateway (`gateway.py`)

Single dispatch point for all LLM traffic. Three coroutines:

```python
async def chat_completions_create(**kwargs) -> ChatCompletionsResponse | ChatCompletion
async def responses_create(**kwargs) -> CodexResponse | Response
async def embeddings_create(**kwargs) -> CreateEmbeddingResponse
```

Routing logic:

```
if not cfg.CHATGPT_OAUTH_ENABLED:
    → real API
elif cooldown is active:
    → real API (skip Codex attempt)
else:
    try Codex:
        chat → translate, call CodexClient.responses_create, translate back
        responses → call CodexClient.responses_create directly
    on CodexRateLimitError:
        arm cooldown
        if fallback enabled → real API
        else → raise
    on CodexAuthError, CodexUpstreamError:
        if fallback enabled → real API
        else → raise

embeddings is always direct → real API
```

Cooldown is process-local: `_codex_cooldown_until` is a monotonic
timestamp. The cooldown duration is read from
`CHATGPT_OAUTH_RATE_LIMIT_COOLDOWN_SECONDS` (default 900s) but is
overridden by the upstream `Retry-After` header if present.

## FastAPI Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health/codex-oauth` | GET | Login state + account ID + expiry |
| `/health/llm-metrics` | GET | Routing counters (codex/fallback/direct) |
| `/auth/codex/start` | POST | Spawn callback server, return authorize URL |
| `/auth/codex/wait` | POST | Long-poll until OAuth callback completes |
| `/auth/codex/manual` | POST | Headless fallback: paste redirect URL |
| `/auth/codex/cancel` | POST | Tear down in-flight login |
| `/auth/codex/logout` | POST | Clear stored tokens |
| `/auth/codex/refresh` | POST | Force refresh now |
| `/auth/codex/import-external` | POST | Mirror `~/.codex/auth.json` |

## Scheduler Integration

A background job in `orchestrator/scheduler.py` runs every 15 minutes
when `CHATGPT_OAUTH_ENABLED=true`:

`_check_codex_oauth_health()` calls `codex_token_store.load_tokens()`
which auto-refreshes if needed, and tracks state transitions
(`logged_in` ↔ `logged_out`). On a transition, it broadcasts a
WebSocket event so the FE can update its indicator without polling.

## Comparison vs Sidecar Approach

| Aspect | Old (sidecar) | New (in-process) |
|---|---|---|
| Container count | 4 services + 1 sidecar | 4 services (no sidecar) |
| Language | Node.js sidecar + Python | Pure Python |
| OAuth flow | `openai-oauth` npm package | `codex_oauth.py` (Python port) |
| Token storage | `data/codex_auth/auth.json` mounted into sidecar | `data/codex_auth/auth.json` read directly |
| Login flow | Manual: `codex login` on host then copy file | In-FE button + browser callback OR manual paste |
| HTTP client | `AsyncOpenAI(base_url=sidecar)` | Custom `CodexClient` (httpx + headers) |
| chat ↔ responses translation | npm package handles it | `codex_chat_translator.py` |
| SSE parsing | npm package handles it | `codex_sse.py` |
| Originator | `codex_cli_rs` (hardcoded) | Configurable via `CHATGPT_OAUTH_ORIGINATOR` |
| Match with openclaw | similar at wire level | identical wire format + scopes |

The wire format (URL, headers, body shape) is **identical** between
the two approaches. The difference is purely architectural — moving
the implementation from a Node sidecar into Python modules.

## Testing

```bash
# Routing logic (no network — uses mocks)
PYTHONPATH=. python scripts/test_llm_factory.py
PYTHONPATH=. python scripts/test_llm_gateway.py
```

The factory test verifies the singleton patterns and base URLs. The
gateway test exercises all 6 routing scenarios with mocked CodexClient
and AsyncOpenAI: success, rate-limit fallback, cooldown skip, OAuth
disabled, embeddings always direct, responses path.

## Related Documents

- [Setup guide](./chatgpt-oauth-setup.md)
- [Terms of Service notice](./chatgpt-oauth-tos-notice.md)
