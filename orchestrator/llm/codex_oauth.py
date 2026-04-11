"""OAuth PKCE flow for ChatGPT Codex (in-process Python port).

Mirrors the openclaw / pi-ai approach:

1. Generate PKCE verifier + challenge + state
2. Build the authorize URL with the same scopes openclaw requests
   (``openid profile email offline_access model.request api.responses.write``)
3. Redirect user to ``https://auth.openai.com/oauth/authorize``
4. Catch the callback at ``http://localhost:1455/auth/callback`` (or accept
   a manual paste of the redirect URL for headless / VPS deployments)
5. Exchange the authorization code for ``access_token`` + ``refresh_token``
   at ``https://auth.openai.com/oauth/token``
6. Decode the JWT to extract ``chatgpt_account_id`` from the
   ``https://api.openai.com/auth`` claim
7. Persist via ``codex_token_store``

Refresh flow uses standard ``grant_type=refresh_token`` and overwrites
the stored credentials in-place under a file lock.

Reference: https://github.com/openclaw/openclaw — `src/plugins/provider-openai-codex-oauth.ts`
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

from orchestrator.config import log

# --- OAuth constants -----------------------------------------------------
#
# These match the official Codex CLI OAuth client. The same client_id is
# used by openai-oauth (npm), so any token issued via this flow is
# interchangeable with credentials from `codex login`.
#
# Scopes are the four basic ones the Codex CLI client_id is registered
# for. Some openclaw / pi-ai code paths add `model.request` and
# `api.responses.write`, but those scopes are tied to a *different*
# client_id that pi-ai uses internally — adding them to a request that
# uses Codex CLI's client_id results in HTTP 400 ``invalid_scope`` from
# auth.openai.com. Token returned from this flow already has access to
# /backend-api/codex/responses without those extra scopes.

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
REDIRECT_URI = "http://localhost:1455/auth/callback"

SCOPES = (
    "openid",
    "profile",
    "email",
    "offline_access",
)

# JWT claim namespace where ChatGPT account metadata lives
JWT_AUTH_CLAIM = "https://api.openai.com/auth"

# Default originator string sent on /authorize and on every API call.
# Configurable via CHATGPT_OAUTH_ORIGINATOR; defaults to `codex_cli_rs`
# because that's the safest, well-known value (matches openai-oauth).
DEFAULT_ORIGINATOR = "codex_cli_rs"


# --- public dataclasses --------------------------------------------------


@dataclass
class PKCEPair:
    verifier: str
    challenge: str


@dataclass
class AuthorizationFlow:
    pkce: PKCEPair
    state: str
    url: str


@dataclass
class CodexTokens:
    access_token: str
    refresh_token: str
    expires_at: float  # unix epoch seconds
    account_id: str | None = None
    raw_id_token: str | None = None

    def is_expired(self, leeway_seconds: int = 60) -> bool:
        return time.time() >= (self.expires_at - leeway_seconds)

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "account_id": self.account_id,
            "raw_id_token": self.raw_id_token,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CodexTokens":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=float(data["expires_at"]),
            account_id=data.get("account_id"),
            raw_id_token=data.get("raw_id_token"),
        )


# --- PKCE helpers --------------------------------------------------------


def generate_pkce_pair() -> PKCEPair:
    """Generate a fresh PKCE code_verifier + S256 code_challenge."""
    # 96 bytes → 128 base64url chars, well within RFC 7636 limits.
    raw = secrets.token_urlsafe(96)
    verifier = raw[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PKCEPair(verifier=verifier, challenge=challenge)


def generate_state() -> str:
    """Random hex string for CSRF protection on the authorize round-trip."""
    return secrets.token_hex(16)


# --- Authorize URL builder -----------------------------------------------


def build_authorization_flow(
    *,
    redirect_uri: str = REDIRECT_URI,
    originator: str = DEFAULT_ORIGINATOR,
) -> AuthorizationFlow:
    """Generate a fresh PKCE pair + state and build the OAuth authorize URL.

    The caller is expected to:
      1. Open the returned URL in a browser
      2. Capture the authorization code from the callback (or paste it
         manually for headless deployments)
      3. Call ``exchange_authorization_code`` with the same PKCE verifier
    """
    pkce = generate_pkce_pair()
    state = generate_state()

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
        "state": state,
        # openclaw and codex-cli send these — they unlock the Codex
        # backend with simplified flow + organization context.
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": originator,
    }
    url = f"{AUTHORIZE_URL}?{urlencode(params)}"
    return AuthorizationFlow(pkce=pkce, state=state, url=url)


# --- Authorization code parsing ------------------------------------------


def parse_authorization_input(raw: str) -> dict[str, str | None]:
    """Parse a raw user input (URL, ``code#state``, or bare code) into parts.

    Used by the manual-paste fallback in headless setups.
    """
    value = (raw or "").strip()
    if not value:
        return {}

    # Try parsing as a full URL first
    try:
        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            qs = parse_qs(parsed.query)
            return {
                "code": (qs.get("code") or [None])[0],
                "state": (qs.get("state") or [None])[0],
            }
    except Exception:
        pass

    # Fragment notation: ``code#state``
    if "#" in value:
        code, state = value.split("#", 1)
        return {"code": code.strip(), "state": state.strip()}

    # Query-string fragment: ``code=xxx&state=yyy``
    if "code=" in value:
        qs = parse_qs(value)
        return {
            "code": (qs.get("code") or [None])[0],
            "state": (qs.get("state") or [None])[0],
        }

    # Bare code
    return {"code": value, "state": None}


# --- Token exchange ------------------------------------------------------


async def exchange_authorization_code(
    *,
    code: str,
    verifier: str,
    redirect_uri: str = REDIRECT_URI,
) -> CodexTokens:
    """Exchange a freshly-issued OAuth code for access + refresh tokens.

    Raises on HTTP error or malformed response.
    """
    body = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
    }
    return await _post_token_endpoint(body, label="code->token")


async def refresh_access_token(refresh_token: str) -> CodexTokens:
    """Refresh an expiring access token using the stored refresh token.

    Don't re-send the ``scope`` parameter — RFC 6749 §6 says omitting
    it on refresh keeps the originally-granted scopes, and including
    extras can be rejected. The reference openai-oauth implementation
    also doesn't include scope on refresh.
    """
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }
    return await _post_token_endpoint(body, label="refresh")


async def _post_token_endpoint(body: dict, *, label: str) -> CodexTokens:
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        response = await client.post(
            TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        snippet = response.text[:300]
        log.error(
            "[codex-oauth] %s failed: HTTP %d body=%s",
            label, response.status_code, snippet,
        )
        raise CodexOAuthError(
            f"OAuth {label} failed: HTTP {response.status_code} — {snippet}"
        )

    payload = response.json()
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token") or body.get("refresh_token")
    expires_in = payload.get("expires_in")
    id_token = payload.get("id_token")

    if not access_token or not refresh_token or not isinstance(expires_in, (int, float)):
        log.error(
            "[codex-oauth] %s response missing fields: access=%s refresh=%s expires=%s",
            label,
            bool(access_token),
            bool(refresh_token),
            expires_in,
        )
        raise CodexOAuthError(
            f"OAuth {label} response missing required fields"
        )

    # The account_id we want lives in the JWT id_token (or sometimes the
    # access_token, which is also a JWT in this flow).
    account_id = None
    raw_jwt_for_account = id_token or access_token
    if raw_jwt_for_account:
        try:
            account_id = extract_account_id_from_jwt(raw_jwt_for_account)
        except Exception as e:
            log.warning("[codex-oauth] failed to extract account_id from JWT: %s", e)

    return CodexTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=time.time() + float(expires_in),
        account_id=account_id,
        raw_id_token=id_token,
    )


# --- JWT helpers ---------------------------------------------------------


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode a JWT's payload section without signature verification.

    OpenAI's JWTs are signed by their own JWKS — we don't need to
    verify because we got the token from a TLS-protected POST to their
    own token endpoint. We only need to read the claims.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError(f"not a JWT (expected 3 parts, got {len(parts)})")

    payload_b64 = parts[1]
    # Re-pad to a multiple of 4 for base64
    pad = "=" * (-len(payload_b64) % 4)
    decoded = base64.urlsafe_b64decode(payload_b64 + pad).decode("utf-8")
    return json.loads(decoded)


def extract_account_id_from_jwt(token: str) -> str | None:
    """Pull the ``chatgpt_account_id`` claim out of a Codex JWT."""
    claims = decode_jwt_payload(token)
    auth_claim = claims.get(JWT_AUTH_CLAIM) or {}
    if isinstance(auth_claim, dict):
        return (
            auth_claim.get("chatgpt_account_id")
            or auth_claim.get("organization_id")
            or None
        )
    return None


# --- Errors --------------------------------------------------------------


class CodexOAuthError(Exception):
    """Raised on any OAuth flow failure (HTTP error, malformed response)."""
