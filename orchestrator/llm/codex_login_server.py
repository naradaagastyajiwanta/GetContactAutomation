"""PKCE state store for the Codex OAuth flow.

AgentFix-style implementation:
- PKCE states stored in-memory dict (state → verifier, expires_at)
- In Docker: port 1455:8000 mapped in docker-compose → FastAPI handles
  GET /auth/callback directly, no helper server needed
- For local dev (no Docker): an ephemeral aiohttp server starts on port 1455
  when a login flow begins, catches the OpenAI redirect, exchanges the code,
  saves tokens, then redirects the browser to the FE callback page
- The FE polls GET /health/codex-oauth every 3 s until status = "logged_in"
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from orchestrator.config import log
from orchestrator.llm.codex_oauth import (
    AuthorizationFlow,
    PKCEPair,
    build_authorization_flow,
)

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 1455
CALLBACK_PATH = "/auth/callback"

_PKCE_TTL_SECONDS = 600  # 10 min

# state_token → (code_verifier, expires_at)
_pkce_states: dict[str, tuple[str, float]] = {}
_pkce_lock = asyncio.Lock()

# Ephemeral aiohttp server — kept alive after first login, reused on next
_server_runner = None
_server_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def begin_login(
    *,
    redirect_uri: str,
    spawn_ephemeral_server: bool = True,
) -> AuthorizationFlow:
    """Generate PKCE pair, store state, optionally start the callback server."""
    flow = build_authorization_flow(redirect_uri=redirect_uri)

    async with _pkce_lock:
        now = time.time()
        # Prune expired states
        expired = [s for s, (_, exp) in _pkce_states.items() if exp < now]
        for key in expired:
            del _pkce_states[key]
        _pkce_states[flow.state] = (flow.pkce.verifier, now + _PKCE_TTL_SECONDS)

    if spawn_ephemeral_server:
        await _ensure_ephemeral_server()

    log.info("[codex-login] flow started (state=%s…)", flow.state[:8])
    return flow


async def pop_pkce_verifier(state: str) -> Optional[str]:
    """One-time retrieval of the PKCE verifier for *state*."""
    async with _pkce_lock:
        entry = _pkce_states.pop(state, None)

    if entry is None:
        log.warning("[codex-login] unknown/already-used state: %s…", state[:8])
        return None

    verifier, expires_at = entry
    if time.time() > expires_at:
        log.warning("[codex-login] PKCE state expired: %s…", state[:8])
        return None

    return verifier


async def cancel_login() -> None:
    """Clear all pending PKCE states."""
    async with _pkce_lock:
        _pkce_states.clear()
    log.info("[codex-login] PKCE states cleared")


# ---------------------------------------------------------------------------
# Ephemeral aiohttp server — local dev only (Docker uses 1455:8000 mapping)
# ---------------------------------------------------------------------------


async def _ensure_ephemeral_server() -> None:
    """Start the aiohttp callback server on localhost:1455 if not running.

    Kept alive across logins — stopped only on process exit.
    In Docker the port-mapping makes this unnecessary, but for local dev
    (uvicorn on 8000) this is the only way to catch the OAuth redirect.
    """
    global _server_runner

    async with _server_lock:
        if _server_runner is not None:
            return

        try:
            from aiohttp import web
        except ImportError:
            log.warning(
                "[codex-login] aiohttp not installed — cannot start ephemeral server. "
                "Install it with: pip install aiohttp"
            )
            return

        app = web.Application()
        app.router.add_get(CALLBACK_PATH, _handle_callback)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, host=CALLBACK_HOST, port=CALLBACK_PORT)
        try:
            await site.start()
            _server_runner = runner
            log.info(
                "[codex-login] ephemeral callback server started on %s:%d",
                CALLBACK_HOST, CALLBACK_PORT,
            )
        except OSError as e:
            await runner.cleanup()
            log.warning(
                "[codex-login] cannot bind %s:%d (%s) — "
                "OAuth callback will be handled by FastAPI (Docker) "
                "or use manual paste.",
                CALLBACK_HOST, CALLBACK_PORT, e,
            )


async def _handle_callback(request) -> None:
    """Catch OAuth redirect → exchange code → save tokens → redirect to FE."""
    from aiohttp import web as _web
    from orchestrator import config
    from orchestrator.llm import codex_oauth as oauth_mod, codex_token_store

    code = request.query.get("code")
    state = request.query.get("state")
    error = request.query.get("error")
    error_description = request.query.get("error_description")

    frontend_url = str(config.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    fe_callback = f"{frontend_url}/oauth/callback"

    if error:
        log.warning("[codex-login] OAuth error: %s", error_description or error)
        raise _web.HTTPFound(f"{fe_callback}?error={error}&error_description={error_description or ''}")

    if not code or not state:
        raise _web.HTTPFound(f"{fe_callback}?error=missing_params")

    verifier = await pop_pkce_verifier(state)
    if verifier is None:
        raise _web.HTTPFound(f"{fe_callback}?error=invalid_state")

    try:
        tokens = await oauth_mod.exchange_authorization_code(code=code, verifier=verifier)
        await codex_token_store.save_tokens(tokens)
        log.info("[codex-login] login complete (account=%s)", tokens.account_id)
    except oauth_mod.CodexOAuthError as e:
        log.error("[codex-login] token exchange failed: %s", e)
        raise _web.HTTPFound(f"{fe_callback}?error=token_exchange_failed")

    raise _web.HTTPFound(f"{fe_callback}?oauth=success")
