# ChatGPT OAuth — Setup Guide (In-Process Python Flow)

This guide walks through enabling **in-process Codex OAuth** so the
orchestrator can route OpenAI chat / responses / vision calls through
a **ChatGPT Plus / Pro subscription** instead of pay-per-token API
billing.

> **No Docker sidecar required.** The OAuth flow, HTTP transport,
> SSE parsing, and request/response translation all run inside the
> orchestrator's Python process. This mirrors the openclaw approach
> (which uses TypeScript + `pi-ai`) but ported to Python.

> **Read the [ToS notice](./chatgpt-oauth-tos-notice.md) first.** This
> uses the official Codex CLI OAuth flow — intended for personal /
> small-team use, not multi-tenant hosting.

## Prerequisites

- A paid **ChatGPT Plus**, **Pro**, **Business**, or **Enterprise**
  subscription (Codex access is tied to the plan)
- Browser access on at least one machine for the initial OAuth login
  (the auth file is portable, so you can log in on a laptop and copy
  the result onto a headless server)

## Login flows

There are **three** ways to get credentials into the orchestrator —
pick the one that fits your environment.

### Flow 1: In-process login via the dashboard (recommended)

For local development and any deployment where the host has browser
access:

1. Open the orchestrator dashboard → **Settings → ChatGPT** tab
2. Click **Login with ChatGPT**
3. The orchestrator spawns a temporary callback server on
   `localhost:1455` and opens the OpenAI authorize URL in a new tab
4. Sign in with your ChatGPT subscription account
5. OpenAI redirects back to `http://localhost:1455/auth/callback`,
   the orchestrator captures the code, exchanges it for tokens, and
   stores them at `data/codex_auth/auth.json`
6. The status card flips to **Logged in** with your account ID
7. In the **Config** tab, set `CHATGPT_OAUTH_ENABLED=true` to start
   routing traffic through Codex

### Flow 2: Manual paste (headless / VPS)

When the orchestrator runs on a remote server with no browser access:

1. Click **Manual paste (headless)** in the Settings panel
2. The orchestrator generates an authorize URL — copy it
3. On a machine with a browser, paste the URL, complete the OAuth
   flow, and let the redirect happen
4. Even though the local callback server isn't there, your browser
   will show the redirect URL (something like
   `http://localhost:1455/auth/callback?code=ABC&state=XYZ`)
5. Paste the **full redirect URL** (or just the `code=...` parameter)
   back into the orchestrator's manual input field
6. Click **Submit** — the orchestrator finishes the token exchange
   and stores the credentials

### Flow 3: Import existing Codex CLI credentials

If you already have the official Codex CLI installed and logged in
on the host:

1. On the host, run `codex login` once (or you may already have
   credentials at `~/.codex/auth.json`)
2. In the Settings panel, click **Import ~/.codex/auth.json**
3. The orchestrator copies the credentials into its own store

This is the openclaw "token sink" pattern — useful when you want to
share credentials with the official Codex CLI on the same machine.
The orchestrator manages refreshes from its own store after import,
so subsequent `codex login` runs won't propagate automatically.

## Verify

After login, check the Settings → ChatGPT tab:

- **Status card**: should show "Logged in" with your account ID and
  token expiry
- **Metrics card**: starts at zero — increments as the orchestrator
  starts routing traffic
- The **Config** tab's `CHATGPT_OAUTH_ENABLED` toggle: set to `true`

You can also verify via the API:

```bash
curl http://localhost:8000/health/codex-oauth
# → {"status": "logged_in", "account_id": "acct_...", "expires_in_seconds": 3500, ...}

curl http://localhost:8000/health/llm-metrics
# → {"codex_chat_calls": 0, ..., "oauth_enabled": true}
```

## How tokens are managed

The token store at `data/codex_auth/auth.json`:

- Is **gitignored** — never commit it
- Has file permissions tightened to `0600` on POSIX systems
- Auto-refreshes the access token before expiry on every API call
  (the refresh runs under an `asyncio.Lock` to prevent races)
- Carries the `chatgpt_account_id` extracted from the JWT, which is
  required as a header on every Codex backend request

When the access token has fewer than 60 seconds until expiry, the
next call to the gateway transparently triggers a refresh using the
stored refresh token. Refresh tokens are typically valid for 60–90
days; after that you'll need to re-login.

## Re-login when refresh token expires

You'll see 401 errors in `/health/llm-metrics` (`codex_auth_errors`
counter increases). Either:

- Click **Login with ChatGPT** in the FE again (Flow 1), OR
- Run `codex login` on the host and click **Import ~/.codex/auth.json**

Both flows overwrite the existing `data/codex_auth/auth.json`.

## Rate limits

ChatGPT Plus has a cap of roughly **80 messages / 3 hours** on the
GPT-5 family. The orchestrator handles 429 responses automatically:

1. The 429 increments `codex_rate_limits` in the metrics
2. A process-local cooldown (default 15 min, configurable via
   `CHATGPT_OAUTH_RATE_LIMIT_COOLDOWN_SECONDS`) is armed
3. All chat / responses calls during the cooldown go straight to the
   real OpenAI API via `OPENAI_API_KEY` (assuming
   `CHATGPT_OAUTH_FALLBACK_TO_API=true`, which is the default)
4. After cooldown expires, the next call attempts Codex again

Monitor `/health/llm-metrics` to see how often you're hitting the
rate limit cap. If it's frequent, upgrade to ChatGPT Pro ($200/mo)
for higher limits.

## Fallback behavior

`CHATGPT_OAUTH_FALLBACK_TO_API` (default: `true`) controls what
happens when the Codex backend is unavailable:

| Scenario              | Fallback enabled        | Fallback disabled     |
| --------------------- | ----------------------- | --------------------- |
| Codex 200 happy path  | routes via Codex        | routes via Codex      |
| Codex 429             | cooldown + real API     | raises error          |
| Codex 401             | falls back to real API  | raises error          |
| Codex network error   | falls back to real API  | raises error          |
| Embeddings call       | always real API         | always real API       |

**Recommendation:** keep fallback **enabled** in production.

## Troubleshooting

### "Could not bind to 127.0.0.1:1455" when clicking Login

Another process is already using port 1455 (often the official
Codex CLI itself, or a previous failed login attempt). Either:

- Close the conflicting process and retry
- Use the **Manual paste** flow instead (no port binding needed)

### Login completes but `codex_chat_calls` stays at zero

`CHATGPT_OAUTH_ENABLED` is still false. Set it via the Config tab
or:

```bash
curl -X POST http://localhost:8000/config/CHATGPT_OAUTH_ENABLED -d "true"
```

### `codex_auth_errors > 0` after some time

The refresh token expired. Re-login (Flow 1 or Flow 3).

### `codex_rate_limits` is high

Your workload is exceeding ChatGPT Plus's per-window cap. The
fallback is doing its job (calls keep working via the real API),
but your `OPENAI_API_KEY` will see usage. Consider upgrading the
subscription or reducing call volume.

### How do I know which model the proxy is calling?

The Codex backend is account-aware — it returns the model your
subscription has access to. `gpt-5.4` is the general default. The
orchestrator config keys (`AGENT_MODEL`, `MARKETING_ORCHESTRATOR_MODEL`,
etc.) all default to `gpt-5.4` after this refactor.

### Originator string

By default the Python client sends `originator: codex_cli_rs` (the
same as the official Codex CLI Rust binary). If you'd rather identify
as openclaw or your own brand, set `CHATGPT_OAUTH_ORIGINATOR` in the
config registry. **Note:** custom values may be flagged by OpenAI's
anti-abuse systems — `codex_cli_rs` and `openclaw` are the only
known-safe values.

## Related Documents

- [Architecture deep-dive](./chatgpt-oauth-architecture.md)
- [Terms of Service notice](./chatgpt-oauth-tos-notice.md)
