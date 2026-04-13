"""Local OAuth callback server for the Codex login flow.

When the user clicks "Login with ChatGPT" in the FE, the orchestrator
spawns a tiny aiohttp HTTP server bound to ``http://localhost:1455``
just long enough to catch the OAuth redirect from
``auth.openai.com``. The server returns a friendly HTML success page
to the browser and resolves a pending Future with the captured code.

This is the openclaw / codex-cli pattern: the OAuth client_id is
registered with redirect_uri ``http://localhost:1455/auth/callback``,
so we MUST listen on that exact host:port for the OAuth flow to
complete.

For headless / VPS deployments where binding port 1455 isn't viable
(or where there's no browser), the FE provides a "manual paste"
fallback that lets the user open the auth URL elsewhere and paste
the redirect URL back into the orchestrator.

Lifecycle:
1. ``begin_login()`` returns ``(authorize_url, state, future)``
2. The future resolves with ``{"code": ..., "state": ...}`` when the
   browser hits the callback, or with ``None`` on timeout/error
3. ``cancel_login()`` shuts down the server early (called when the
   user clicks Cancel in the FE)

Only one login is ever in flight at a time — calling ``begin_login``
while a previous flow is still pending raises.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Optional

from aiohttp import web

from orchestrator.config import log
from orchestrator.llm.codex_oauth import (
    AuthorizationFlow,
    PKCEPair,
    build_authorization_flow,
)

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 1455
CALLBACK_PATH = "/auth/callback"

# Default timeout — if the user doesn't complete login within this
# many seconds, the future resolves with None and the server stops.
DEFAULT_LOGIN_TIMEOUT_SECONDS = 300

# Sentinel marker for superseded sessions. When a new ``begin_login``
# call cancels an in-flight session, the old future resolves with this
# marker so the caller can distinguish "user started a fresh login" from
# "timed out" or "user cancelled". The FE silently discards superseded
# results instead of showing an error toast.
SUPERSEDED_MARKER = {"superseded": True}

# Module-level state — only one in-flight login at a time
_active_session: "Optional[LoginSession]" = None

# Lock that serializes begin_login calls — prevents race when two clicks
# arrive within the same event loop tick (both try to read _active_session
# before either writes it).
_begin_login_lock = asyncio.Lock()


@dataclass
class LoginSession:
    pkce: PKCEPair
    state: str
    authorize_url: str
    future: asyncio.Future
    runner: web.AppRunner
    site: web.TCPSite
    timeout_task: asyncio.Task


SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Login Successful</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           display: flex; align-items: center; justify-content: center;
           height: 100vh; margin: 0;
           background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .card { background: white; padding: 40px 60px; border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.15); text-align: center; }
    h1 { color: #2d3748; margin: 0 0 8px; font-size: 24px; }
    p { color: #718096; margin: 0; font-size: 14px; }
    .check { width: 48px; height: 48px; margin: 0 auto 16px;
             background: #48bb78; border-radius: 50%;
             display: flex; align-items: center; justify-content: center;
             color: white; font-size: 28px; font-weight: bold; }
  </style>
</head>
<body>
  <div class="card">
    <div class="check">✓</div>
    <h1>Login Successful</h1>
    <p>You can close this tab and return to the dashboard.</p>
  </div>
</body>
</html>
"""

ERROR_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Login Failed</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           display: flex; align-items: center; justify-content: center;
           height: 100vh; margin: 0; background: #f7fafc; }
    .card { background: white; padding: 40px 60px; border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.1); text-align: center;
            border-top: 4px solid #f56565; }
    h1 { color: #2d3748; margin: 0 0 8px; font-size: 24px; }
    p { color: #718096; margin: 0; font-size: 14px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Login Failed</h1>
    <p>{message}</p>
  </div>
</body>
</html>
"""


# --- HTTP handlers -----------------------------------------------------------


def _render_error_html(message: str) -> str:
    """Render the error HTML page with the given message.

    We deliberately avoid ``str.format`` here because the HTML/CSS body
    contains literal ``{`` and ``}`` characters in selectors and rules
    that would be misparsed as format placeholders.
    """
    return ERROR_HTML.replace("{message}", message)


def handle_callback_data(
    code: str | None,
    state: str | None,
    error: str | None,
    error_description: str | None,
) -> dict:
    """Process OAuth callback parameters and update the active session future.

    This logic is shared between:
      - The ephemeral aiohttp server (_handle_callback)
      - The persistent FastAPI endpoint (/auth/codex-callback)

    Returns a dict with keys:
      - success: bool
      - message: str
      - html: str (HTML to return to browser)

    Side effects:
      - Updates _active_session.future if active
    """
    global _active_session

    session = _active_session
    if session is None:
        return {
            "success": False,
            "message": "No login in progress.",
            "html": _render_error_html("No login in progress."),
        }

    if error:
        full_error = (
            f"{error}: {error_description}" if error_description else error
        )
        log.warning("[codex-login] callback returned error: %s", full_error)
        if not session.future.done():
            session.future.set_result({"error": full_error})
        return {
            "success": False,
            "message": f"OAuth error: {full_error}",
            "html": _render_error_html(f"OAuth error: {full_error}"),
        }

    if not code:
        if not session.future.done():
            session.future.set_result(None)
        return {
            "success": False,
            "message": "Callback missing 'code' parameter.",
            "html": _render_error_html("Callback missing 'code' parameter."),
        }

    if state and state != session.state:
        log.warning(
            "[codex-login] state mismatch: got %s expected %s", state, session.state
        )
        if not session.future.done():
            session.future.set_result(None)
        return {
            "success": False,
            "message": "State mismatch — possible CSRF.",
            "html": _render_error_html("State mismatch — possible CSRF."),
        }

    if not session.future.done():
        session.future.set_result({"code": code, "state": state})

    log.info("[codex-login] OAuth code captured successfully from callback")
    return {
        "success": True,
        "message": "OAuth code captured successfully.",
        "html": SUCCESS_HTML,
    }


async def _handle_callback(request: web.Request) -> web.Response:
    """Catch the OAuth redirect, hand the code back to the waiting future."""
    code = request.query.get("code")
    state = request.query.get("state")
    error = request.query.get("error")
    error_description = request.query.get("error_description")

    result = handle_callback_data(code, state, error, error_description)
    return web.Response(
        text=result["html"],
        content_type="text/html",
        status=400 if not result["success"] else 200,
    )


# --- public API --------------------------------------------------------------


async def begin_login(
    *,
    timeout_seconds: int = DEFAULT_LOGIN_TIMEOUT_SECONDS,
    spawn_ephemeral_server: bool = True,
) -> AuthorizationFlow:
    """Spawn the local callback server and return the authorize URL.

    Args:
      spawn_ephemeral_server: If False, skip spawning the ephemeral
        aiohttp server (use this for production with persistent /auth/codex-callback
        endpoint). If True, spawn the server on localhost:1455 (dev mode).

    **Idempotent behaviour** — if a previous login is still in flight
    (e.g. the user closed the browser tab without completing OAuth and
    clicked "Login" again), this function silently cancels the stale
    session before starting a fresh one. The stale session's waiter
    (if any) is resolved with :data:`SUPERSEDED_MARKER` so the FE can
    distinguish "superseded by new attempt" from "timed out".

    This removes the old ``RuntimeError("already in progress")`` which
    forced users to click Cancel manually before retrying.

    The caller (FastAPI handler) returns the URL to the FE; the FE
    opens it in a new tab; the user logs in; the OAuth provider
    redirects back to the callback URL; this server (if spawned) captures
    the code and resolves the in-memory future, OR a persistent endpoint
    updates the future directly.

    To wait for the result, ``await wait_for_login_result()``.
    """
    global _active_session

    async with _begin_login_lock:
        # Atomically detach the previous session (if any) and shut it
        # down BEFORE creating the new one. Setting _active_session to
        # None first ensures concurrent begin_login calls — should they
        # ever bypass the lock — don't race on the same stale reference.
        previous = _active_session
        _active_session = None

        if previous is not None:
            was_done = previous.future.done()
            log.info(
                "[codex-login] superseding previous login session "
                "(was_done=%s) — starting fresh flow",
                was_done,
            )
            # Mark the old waiter as superseded so FE can silently discard
            if not was_done:
                try:
                    previous.future.set_result(SUPERSEDED_MARKER)
                except asyncio.InvalidStateError:
                    pass
            try:
                await _shutdown_session(previous)
            except Exception as e:
                log.warning(
                    "[codex-login] error shutting down previous session: %s", e
                )

        flow = build_authorization_flow()

        # Only spawn ephemeral server for dev (callback is localhost:1455)
        if not spawn_ephemeral_server:
            log.info(
                "[codex-login] production mode: no ephemeral server, "
                "using persistent /auth/codex-callback endpoint"
            )
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()

            async def _timeout_watchdog():
                try:
                    await asyncio.sleep(timeout_seconds)
                    if not future.done():
                        future.set_result(None)
                        log.warning(
                            "[codex-login] login timed out after %ds", timeout_seconds
                        )
                except asyncio.CancelledError:
                    pass

            timeout_task = loop.create_task(_timeout_watchdog())

            _active_session = LoginSession(
                pkce=flow.pkce,
                state=flow.state,
                authorize_url=flow.url,
                future=future,
                runner=None,  # No server runner in production mode
                site=None,
                timeout_task=timeout_task,
            )
            log.info(
                "[codex-login] waiting for OAuth redirect via persistent endpoint, "
                "awaitingcode"
            )
            return flow

        # Dev mode: spawn ephemeral server on localhost:1455
        app = web.Application()
        app.router.add_get(CALLBACK_PATH, _handle_callback)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, host=CALLBACK_HOST, port=CALLBACK_PORT)
        try:
            await site.start()
        except OSError as e:
            await runner.cleanup()
            raise RuntimeError(
                f"Could not bind to {CALLBACK_HOST}:{CALLBACK_PORT} for OAuth callback. "
                f"Use the manual paste fallback instead. Error: {e}"
            ) from e

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()

        async def _timeout_watchdog():
            try:
                await asyncio.sleep(timeout_seconds)
                if not future.done():
                    future.set_result(None)
                    log.warning(
                        "[codex-login] login timed out after %ds", timeout_seconds
                    )
            except asyncio.CancelledError:
                pass

        timeout_task = loop.create_task(_timeout_watchdog())

        _active_session = LoginSession(
            pkce=flow.pkce,
            state=flow.state,
            authorize_url=flow.url,
            future=future,
            runner=runner,
            site=site,
            timeout_task=timeout_task,
        )

        log.info(
            "[codex-login] callback server listening on %s:%d, awaiting OAuth redirect",
            CALLBACK_HOST, CALLBACK_PORT,
        )
        return flow


async def wait_for_login_result(timeout: float | None = None) -> dict | None:
    """Block until the in-flight login resolves.

    Returns:
      * ``{"code": ..., "state": ...}`` on success
      * ``{"error": "..."}`` if the OAuth provider returned an error
        (e.g. ``invalid_scope``)
      * ``None`` on timeout / cancelled / no active session
    """
    if _active_session is None:
        return None

    try:
        if timeout is not None:
            result = await asyncio.wait_for(_active_session.future, timeout=timeout)
        else:
            result = await _active_session.future
    except asyncio.TimeoutError:
        return None

    return result


def get_active_pkce() -> PKCEPair | None:
    """Return the PKCE verifier for the current in-flight login.

    The token-exchange step needs this to send back to OpenAI.
    """
    if _active_session is None:
        return None
    return _active_session.pkce


async def cancel_login() -> None:
    """Tear down the in-flight login server (if any)."""
    global _active_session
    if _active_session is not None:
        await _shutdown_session(_active_session)
        _active_session = None


async def finalize_login() -> None:
    """Clean up after a successful login completes.

    Distinct from ``cancel_login`` so callers can express intent —
    finalize after the token exchange succeeds.
    """
    await cancel_login()


async def _shutdown_session(session: LoginSession) -> None:
    """Stop the callback server and cancel the timeout watchdog.
    
    Handles both dev mode (with server) and production mode (no server).
    """
    if not session.timeout_task.done():
        session.timeout_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await session.timeout_task
    if not session.future.done():
        session.future.set_result(None)
    
    # Production mode: site and runner may be None
    if session.site is not None:
        try:
            await session.site.stop()
        except Exception:
            pass
    if session.runner is not None:
        try:
            await session.runner.cleanup()
        except Exception:
            pass
