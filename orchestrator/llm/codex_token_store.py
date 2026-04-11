"""Token persistence for the Codex OAuth flow.

Stores ``CodexTokens`` as JSON on disk under ``data/codex_auth/auth.json``,
guarded by an ``asyncio.Lock`` so concurrent refreshes can't trample each
other. The file is also marked password-equivalent — see ``.gitignore``.

Two write paths exist:

* ``save_tokens(tokens)`` — overwrite from in-process flow (login or
  programmatic refresh)
* ``import_external_codex_auth()`` — read ``~/.codex/auth.json`` if the
  user has the official ``@openai/codex`` CLI installed and prefers to
  manage credentials there. Mirrors openclaw's "token sink" pattern:
  we read the external file but never rewrite it, so refresh tokens
  rotated by the external CLI stay valid.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from orchestrator.config import log
from orchestrator.llm.codex_oauth import CodexTokens, refresh_access_token

# --- file locations ------------------------------------------------------

# Project-local store (preferred)
PROJECT_AUTH_DIR = Path("data/codex_auth")
PROJECT_AUTH_FILE = PROJECT_AUTH_DIR / "auth.json"

# External Codex CLI store (read-only mirror)
EXTERNAL_CODEX_FILE = Path.home() / ".codex" / "auth.json"

# Async lock — protects in-process token reads/writes against races
_lock = asyncio.Lock()
_cached: CodexTokens | None = None


# --- public API ----------------------------------------------------------


async def load_tokens() -> CodexTokens | None:
    """Return the current credentials, refreshing if expired.

    Returns ``None`` if no credentials exist anywhere — the caller is
    expected to trigger a login flow.
    """
    global _cached
    async with _lock:
        if _cached is None:
            _cached = _read_from_disk()
        if _cached is None:
            return None

        if _cached.is_expired():
            try:
                refreshed = await refresh_access_token(_cached.refresh_token)
            except Exception as e:
                log.warning(
                    "[codex-token-store] refresh failed; clearing cache: %s", e
                )
                _cached = None
                return None
            _cached = refreshed
            _write_to_disk(_cached)
            log.info("[codex-token-store] tokens refreshed (account=%s)", _cached.account_id)

        return _cached


async def save_tokens(tokens: CodexTokens) -> None:
    """Persist a freshly-issued token set (called from the login flow)."""
    global _cached
    async with _lock:
        _cached = tokens
        _write_to_disk(tokens)
        log.info(
            "[codex-token-store] saved new tokens (account=%s, expires_in=%ds)",
            tokens.account_id,
            int(tokens.expires_at - time.time()),
        )


async def clear_tokens() -> None:
    """Drop in-memory + on-disk credentials (logout)."""
    global _cached
    async with _lock:
        _cached = None
        try:
            if PROJECT_AUTH_FILE.exists():
                PROJECT_AUTH_FILE.unlink()
        except Exception as e:
            log.warning("[codex-token-store] failed to remove auth file: %s", e)


async def import_external_codex_auth() -> bool:
    """Copy ``~/.codex/auth.json`` into the project store, if present.

    Returns True if an import happened. Useful for users who prefer to
    log in once on their workstation via ``codex login`` and reuse the
    credentials from this project.

    Unlike openclaw's full token-sink mirror, this is a one-shot import:
    we read the external file once at startup or on demand, then manage
    refreshes via our own store. The trade-off is simplicity (no need
    to coordinate refresh tokens with an external process) vs the risk
    that running ``codex login`` again later won't propagate.
    """
    if not EXTERNAL_CODEX_FILE.exists():
        return False
    try:
        with EXTERNAL_CODEX_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.warning("[codex-token-store] failed to read external auth.json: %s", e)
        return False

    # The Codex CLI stores fields as: tokens.access_token, tokens.refresh_token,
    # tokens.id_token, expires_at (epoch ms or seconds depending on version).
    # Try to normalize.
    tokens_section = data.get("tokens") or data
    access = tokens_section.get("access_token")
    refresh = tokens_section.get("refresh_token")
    id_token = tokens_section.get("id_token")

    if not access or not refresh:
        log.warning(
            "[codex-token-store] external auth.json missing access/refresh tokens"
        )
        return False

    # Try a few fields for the expiry timestamp
    expires_raw = (
        tokens_section.get("expires_at")
        or data.get("expires_at")
        or tokens_section.get("expires")
    )
    if isinstance(expires_raw, (int, float)):
        expires_at = float(expires_raw)
        if expires_at > 1e12:  # likely milliseconds
            expires_at /= 1000.0
    else:
        # Assume 1 hour from now if missing — we'll refresh soon
        expires_at = time.time() + 3600.0

    account_id = None
    raw_for_account = id_token or access
    if raw_for_account:
        try:
            from orchestrator.llm.codex_oauth import extract_account_id_from_jwt
            account_id = extract_account_id_from_jwt(raw_for_account)
        except Exception as e:
            log.debug("[codex-token-store] could not decode account_id: %s", e)

    tokens = CodexTokens(
        access_token=access,
        refresh_token=refresh,
        expires_at=expires_at,
        account_id=account_id,
        raw_id_token=id_token,
    )
    await save_tokens(tokens)
    log.info(
        "[codex-token-store] imported external Codex CLI credentials (%s)",
        EXTERNAL_CODEX_FILE,
    )
    return True


def get_status() -> dict:
    """Return a status dict for /health/codex-oauth — never blocks."""
    if _cached is None:
        on_disk = _read_from_disk()
        if on_disk is None:
            return {"logged_in": False, "source": "none"}
        return {
            "logged_in": True,
            "account_id": on_disk.account_id,
            "expires_at": on_disk.expires_at,
            "expires_in_seconds": max(0, int(on_disk.expires_at - time.time())),
            "source": "disk",
        }
    return {
        "logged_in": True,
        "account_id": _cached.account_id,
        "expires_at": _cached.expires_at,
        "expires_in_seconds": max(0, int(_cached.expires_at - time.time())),
        "source": "cache",
    }


def reset_cache() -> None:
    """Force the next ``load_tokens`` call to re-read from disk. For tests."""
    global _cached
    _cached = None


# --- internal disk I/O ---------------------------------------------------


def _read_from_disk() -> CodexTokens | None:
    if not PROJECT_AUTH_FILE.exists():
        return None
    try:
        with PROJECT_AUTH_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return CodexTokens.from_dict(data)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.warning("[codex-token-store] auth.json malformed: %s", e)
        return None


def _write_to_disk(tokens: CodexTokens) -> None:
    try:
        PROJECT_AUTH_DIR.mkdir(parents=True, exist_ok=True)
        # Write atomically: write to a temp file, then rename
        tmp = PROJECT_AUTH_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(tokens.to_dict(), f, indent=2)
        os.replace(tmp, PROJECT_AUTH_FILE)
        # Tighten file permissions on POSIX (no-op on Windows)
        try:
            os.chmod(PROJECT_AUTH_FILE, 0o600)
        except (OSError, NotImplementedError):
            pass
    except Exception as e:
        log.error("[codex-token-store] failed to write auth.json: %s", e)
        raise
