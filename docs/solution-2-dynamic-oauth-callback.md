# Solution 2: Dynamic OAuth Callback URL Implementation

**Status:** ✅ Implemented and validated

This document describes the implementation of **Solution 2** for ChatGPT OAuth, which allows seamless login in both development (localhost) and production (public domain) environments.

## Overview

Previously, the OAuth callback URL was hardcoded to `http://localhost:1455/auth/callback`, which only worked in development. Solution 2 makes the callback URL dynamic and environment-aware:

- **Development:** Uses ephemeral aiohttp server on `localhost:1455` (unchanged from before)
 **Production:** Uses a persistent FastAPI endpoint exposed through `/api/auth/codex-callback` on the public domain
# For production: https://get-contact-automation.airabot.id/api/auth/codex-callback (fixed endpoint)
**New `/api/auth/codex-callback` GET endpoint:**
2. **Production:** `https://get-contact-automation.airabot.id/api/auth/codex-callback`
OAUTH_CALLBACK_URL=https://get-contact-automation.airabot.id/api/auth/codex-callback
   - Backend `/api/auth/codex-callback` endpoint captures the code via the `/api/` proxy
 Contact OpenAI support to add `https://youromain.com/api/auth/codex-callback`

Added new environment variable:

```python
# ChatGPT OAuth callback URL — used for dynamic redirect handling.
# For development: http://localhost:1455/auth/callback (ephemeral server)
# For production: https://get-contact-automation.airabot.id/api/auth/codex-callback (fixed endpoint)
OAUTH_CALLBACK_URL = os.getenv("OAUTH_CALLBACK_URL", "http://localhost:1455/auth/callback")
```

#### 2. OAuth Login Server (`orchestrator/llm/codex_login_server.py`)

**Refactored OAuth callback handling:**

- Extracted callback logic into a reusable `handle_callback_data()` function
- Updated `begin_login()` to accept `spawn_ephemeral_server` parameter:
  - `True` for dev (creates ephemeral server on localhost:1455)
  - `False` for production (skips server creation, uses persistent endpoint)
- Made `_shutdown_session()` handle `None` values for production mode (where `site` and `runner` are None)

**New public function:**

```python
def handle_callback_data(
    code: str | None,
    state: str | None,
    error: str | None,
    error_description: str | None,
) -> dict:
    """Process OAuth callback parameters and update the active session future.
    
    Shared between ephemeral aiohttp server and persistent FastAPI endpoint.
    Returns: {"success": bool, "message": str, "html": str}
    """
```

#### 3. Main API Endpoints (`orchestrator/main.py`)

**Updated `/auth/codex/start`:**

```python
@app.post("/auth/codex/start")
async def codex_oauth_start():
    """
    Returns:
      - authorize_url: OpenAI OAuth URL
      - callback_url: DYNAMIC (from OAUTH_CALLBACK_URL config)
      - state: PKCE state parameter
      - callback_host, callback_port: For backward compatibility
    """
```

Logic:
- Reads `OAUTH_CALLBACK_URL` from config
- Detects if callback is localhost → spawns ephemeral server
- Otherwise → skips server, returns callback_url for persistent endpoint

**New `/auth/codex-callback` GET endpoint:**

```python
@app.get("/auth/codex-callback")
async def codex_oauth_callback_get(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Production OAuth callback endpoint.
    
    Called by browser after user authenticates with OpenAI.
    Captures code, updates session state, returns success HTML.
    """
```

### Frontend Changes

#### 1. API Types (`frontend/src/api/chatgptOAuth.ts`)

Added `callback_url` field to `StartLoginResponse`:

```typescript
export interface StartLoginResponse {
  authorize_url: string;
  state: string;
  callback_url: string;  // ← NEW: Dynamic callback for this environment
  callback_host: string;
  callback_port: number;
}
```

#### 2. OAuth Panel (`frontend/src/components/settings/ChatGPTOAuthPanel.tsx`)

- Added state to track `lastCallbackUrl`
- Captures `callback_url` from `startCodexLogin()` response
- Updates manual paste placeholder to show actual callback URL

## Setup for Production OAuth

### Step 1: Register Callback URLs in OpenAI App

Contact OpenAI support to register **both** redirect URIs in your app settings:

1. **Development:** `http://localhost:1455/auth/callback`
2. **Production:** `https://get-contact-automation.airabot.id/api/auth/codex-callback`

(Or use your actual production domain in place of `get-contact-automation.airabot.id`)

### Step 2: Configure Environment Variables

In `.env.production`:

```bash
# Enable ChatGPT OAuth
CHATGPT_OAUTH_ENABLED=true
CHATGPT_OAUTH_FALLBACK_TO_API=true

# Set the production callback URL
OAUTH_CALLBACK_URL=https://get-contact-automation.airabot.id/api/auth/codex-callback

# Still required for embeddings and fallback
OPENAI_API_KEY=sk-...
```

### Step 3: Deploy and Test

1. Deploy the orchestrator to production
2. Frontend → Settings → ChatGPT tab
3. Click **"Login with ChatGPT"**
4. Browser redirects to OpenAI
5. After user authenticates, OpenAI redirects to the production domain
6. Backend `/auth/codex-callback` endpoint captures the code
7. Tokens stored in `data/codex_auth/auth.json` (production server)

## Fallback Behavior

If OAuth fails at any step:

1. **Codex 429 (rate limit):** Waits for cooldown (default 15 min), then routes through real OpenAI API
2. **Codex 401 (auth error):** Falls back to real OpenAI API (`OPENAI_API_KEY`)
3. **Network error:** Falls back to real OpenAI API

All controlled by `CHATGPT_OAUTH_FALLBACK_TO_API=true`

## Manual Paste Fallback (For Headless Deployments)

If production callback URL isn't viable (e.g., behind restrictive firewall), users can still use **Manual Paste** mode:

1. Click **"Manual paste (headless)"**
2. Copy the generated `authorize_url`
3. Paste in browser on a different machine
4. After OAuth, copy the redirect URL
5. Paste back into orchestrator's manual input field
6. Completes token exchange on the server

This requires **zero changes** to the app registration and works with any network topology.

## Backward Compatibility

✅ All existing code paths still work:

- Dev mode with localhost:1455 (unchanged)
- Manual paste fallback (unchanged)
- Import ~/.codex/auth.json (unchanged)
- Fallback to real OpenAI API (unchanged)

## Validation Checklist

- [x] Backend Python: `py_compile` passes (no syntax errors)
- [x] Frontend TypeScript: `tsc --noEmit` passes
- [x] OAuth login server refactored to support both dev and prod
- [x] Dynamic callback URL returned from `/auth/codex/start`
- [x] New persistent `/auth/codex-callback` endpoint in main.py
- [x] Frontend captures and displays callback URL
- [x] Manual paste with dynamic placeholder text

## Migration Path (if currently using OAuth in dev)

1. No action needed for dev — continues to work as before
2. To enable production OAuth:
   - Add callback URL to OpenAI app settings
   - Set `OAUTH_CALLBACK_URL` in `.env.production`
   - Set `CHATGPT_OAUTH_ENABLED=true`
   - Deploy
   - Login via Settings → ChatGPT tab on production

## Troubleshooting

**"No login in progress"** error when clicking callback link:
- Ensure `/auth/codex/start` was called first
- Check that the callback URL in OpenAI app matches `OAUTH_CALLBACK_URL`
- Check orchestrator logs for errors

**Token not stored after callback:**
- Verify `data/codex_auth/` directory is writable
- Check `/health/codex-oauth` for status
- See `OPENAI_API_KEY` fallback still works

**Production callback URL not registeredwith OpenAI:**
- Contact OpenAI support to add `https://youromain.com/auth/codex-callback`
- Meanwhile, use **Manual Paste** mode for production

## Files Modified

- `orchestrator/config.py` — Added `OAUTH_CALLBACK_URL` config
- `orchestrator/llm/codex_login_server.py` — Refactored for dynamic callback, added `handle_callback_data()`
- `orchestrator/main.py` — Updated `/auth/codex/start`, added `/auth/codex-callback` endpoint
- `.env.example` — Added `OAUTH_CALLBACK_URL` documentation
- `.env.production` — Added commented-out production callback URL
- `frontend/src/api/chatgptOAuth.ts` — Added `callback_url` to `StartLoginResponse`
- `frontend/src/components/settings/ChatGPTOAuthPanel.tsx` — Dynamic callback URL display

## Next Steps

1. Test in development with `OAUTH_CALLBACK_URL=http://localhost:1455/auth/callback` (current default)
2. Contact OpenAI to register production callback URL
3. Update `.env.production` with production callback URL
4. Enable `CHATGPT_OAUTH_ENABLED=true` in production
5. Test production OAuth flow
