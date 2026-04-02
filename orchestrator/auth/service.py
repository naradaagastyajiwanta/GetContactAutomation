import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, Response, WebSocket

from orchestrator.config import cfg
from orchestrator.db import (
    count_active_auth_roles,
    create_auth_audit_log,
    create_auth_session,
    get_auth_role_keys_for_user,
    get_auth_session,
    revoke_auth_session,
    touch_auth_session,
    upsert_auth_user_role,
)
from orchestrator.dms_mysql import get_active_karyawan_by_email

ROLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "admin": {
        "label": "Admin",
        "permissions": ["*"],
    },
    "operator": {
        "label": "Operator",
        "permissions": [
            "dashboard.view",
            "pipeline.view",
            "pipeline.manage",
            "pipeline.run",
            "universities.view",
            "universities.manage",
            "conversations.view",
            "audiensi.view",
            "audiensi.manage",
            "whatsapp.view",
            "whatsapp.manage",
            "blast.view",
            "blast.manage",
            "marketing.view",
            "marketing.manage",
            "knowledge.view",
            "knowledge.manage",
            "learning.view",
            "learning.manage",
            "crm.view",
            "crm.manage",
            "logs.view",
        ],
    },
    "viewer": {
        "label": "Viewer",
        "permissions": [
            "dashboard.view",
            "pipeline.view",
            "universities.view",
            "conversations.view",
            "audiensi.view",
            "whatsapp.view",
            "blast.view",
            "marketing.view",
            "knowledge.view",
            "learning.view",
            "crm.view",
            "logs.view",
        ],
    },
}


def _cookie_name() -> str:
    return str(cfg.get("AUTH_COOKIE_NAME", "dms_marketing_session"))


def _cookie_secure() -> bool:
    return bool(cfg.get("AUTH_COOKIE_SECURE", False))


def _session_ttl_hours() -> int:
    return int(cfg.get("AUTH_SESSION_TTL_HOURS", 12))


def _default_password() -> str:
    return str(cfg.get("AUTH_DEFAULT_PASSWORD", "") or "")


def _default_role_key() -> str:
    role_key = str(cfg.get("AUTH_DEFAULT_ROLE", "viewer") or "viewer")
    return normalize_role_key(role_key)


def _identity_from_user(user: dict[str, Any] | None) -> tuple[int | None, str | None]:
    if not user:
        return None, None

    raw_id = user.get("dms_user_id")
    email = user.get("email") or user.get("user_email")
    return (int(raw_id) if raw_id is not None else None, str(email) if email else None)


async def log_auth_event(
    action: str,
    *,
    request: Request | None = None,
    actor: dict[str, Any] | None = None,
    actor_email: str | None = None,
    subject: dict[str, Any] | None = None,
    subject_dms_user_id: int | None = None,
    subject_email: str | None = None,
    role_key: str | None = None,
    success: bool = True,
    detail: str | None = None,
) -> None:
    """Persist a structured auth audit log entry."""
    actor_dms_user_id, resolved_actor_email = _identity_from_user(actor)
    resolved_subject_dms_user_id, resolved_subject_email = _identity_from_user(subject)

    await create_auth_audit_log(
        action=action,
        actor_dms_user_id=actor_dms_user_id,
        actor_email=resolved_actor_email or actor_email,
        subject_dms_user_id=resolved_subject_dms_user_id if resolved_subject_dms_user_id is not None else subject_dms_user_id,
        subject_email=resolved_subject_email or subject_email,
        role_key=role_key,
        success=success,
        detail=detail,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_password_md5(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def normalize_role_key(role_key: str) -> str:
    normalized = (role_key or "").strip().lower()
    if normalized not in ROLE_DEFINITIONS:
        raise HTTPException(status_code=422, detail="Invalid role_key")
    return normalized


def _parse_dms_levels(raw_level: Any) -> list[str]:
    if raw_level is None:
        return []
    return [part.strip() for part in str(raw_level).split(",") if part.strip()]


def _permissions_for_roles(role_keys: list[str]) -> list[str]:
    if not role_keys:
        return []
    if "admin" in role_keys:
        return ["*"]
    permissions: set[str] = set()
    for role_key in role_keys:
        role_def = ROLE_DEFINITIONS.get(role_key)
        if role_def:
            permissions.update(role_def["permissions"])
    return sorted(permissions)


def has_permission(user: dict[str, Any] | None, permission: str) -> bool:
    if not user:
        return False
    permissions = set(user.get("permissions", []))
    return "*" in permissions or permission in permissions


def build_app_user(dms_user: dict[str, Any], role_keys: list[str]) -> dict[str, Any]:
    return {
        "dms_user_id": int(dms_user["dms_user_id"]),
        "name": dms_user.get("user_name") or "Unknown User",
        "email": dms_user.get("user_email") or "",
        "dms_user_level": str(dms_user.get("user_level") or ""),
        "dms_user_levels": _parse_dms_levels(dms_user.get("user_level")),
        "roles": sorted(role_keys),
        "permissions": _permissions_for_roles(role_keys),
    }


async def can_bootstrap_auth() -> bool:
    return await count_active_auth_roles() == 0


async def validate_login_credentials(email: str, password: str) -> dict[str, Any]:
    normalized_email = (email or "").strip().lower()
    if not normalized_email or not password:
        raise HTTPException(status_code=422, detail="Email and password are required")

    dms_user = await get_active_karyawan_by_email(normalized_email)
    if not dms_user:
        raise HTTPException(status_code=401, detail="Email or password is invalid")

    default_password = _default_password()
    if default_password and hmac.compare_digest(default_password, password):
        dms_user = dict(dms_user)
        dms_user["_auth_default_password_used"] = True
        return dms_user

    stored_hash = str(dms_user.get("user_password") or "")
    computed_hash = _hash_password_md5(password)
    if not stored_hash or not hmac.compare_digest(stored_hash.lower(), computed_hash.lower()):
        raise HTTPException(status_code=401, detail="Email or password is invalid")

    return dms_user


async def create_session_for_user(
    response: Response,
    dms_user: dict[str, Any],
    request: Request | None = None,
) -> dict[str, Any]:
    role_keys = await get_auth_role_keys_for_user(int(dms_user["dms_user_id"]))
    if not role_keys and dms_user.get("_auth_default_password_used"):
        default_role_key = _default_role_key()
        await upsert_auth_user_role(
            dms_user_id=int(dms_user["dms_user_id"]),
            user_email=str(dms_user.get("user_email") or ""),
            user_name=str(dms_user.get("user_name") or "Unknown User"),
            role_key=default_role_key,
            granted_by_email="system:auto-grant",
        )
        await log_auth_event(
            "auto_grant_role",
            request=request,
            actor_email="system:auto-grant",
            subject=dms_user,
            role_key=default_role_key,
            success=True,
            detail="Granted default role after successful default-password login",
        )
        role_keys = [default_role_key]

    if not role_keys:
        raise HTTPException(status_code=403, detail="Access has not been granted for this account")

    session_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_session_ttl_hours())
    await create_auth_session(
        session_hash=_hash_token(session_token),
        dms_user_id=int(dms_user["dms_user_id"]),
        user_email=str(dms_user.get("user_email") or ""),
        user_name=str(dms_user.get("user_name") or "Unknown User"),
        dms_user_level=str(dms_user.get("user_level") or ""),
        expires_at=expires_at.isoformat(),
        user_agent=request.headers.get("user-agent") if request else None,
        ip_address=request.client.host if request and request.client else None,
    )
    response.set_cookie(
        key=_cookie_name(),
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        max_age=_session_ttl_hours() * 3600,
        expires=expires_at,
        path="/",
    )
    return build_app_user(dms_user, role_keys)


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_cookie_name(),
        path="/",
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )


async def get_user_from_session_token(session_token: str | None) -> dict[str, Any] | None:
    if not session_token:
        return None

    session = await get_auth_session(_hash_token(session_token))
    if not session or session.get("revoked_at"):
        return None

    expires_at_raw = session.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(str(expires_at_raw)) if expires_at_raw else None
    except ValueError:
        expires_at = None
    if expires_at is None or expires_at <= datetime.now(timezone.utc):
        await revoke_auth_session(session["session_hash"])
        return None

    role_keys = await get_auth_role_keys_for_user(int(session["dms_user_id"]))
    if not role_keys:
        return None

    await touch_auth_session(session["session_hash"])
    return build_app_user(
        {
            "dms_user_id": session["dms_user_id"],
            "user_name": session.get("user_name"),
            "user_email": session.get("user_email"),
            "user_level": session.get("dms_user_level"),
        },
        role_keys,
    )


async def revoke_session_token(session_token: str | None) -> None:
    if not session_token:
        return
    await revoke_auth_session(_hash_token(session_token))


async def get_request_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def require_permission(request: Request, permission: str) -> dict[str, Any]:
    user = await get_request_user(request)
    if not has_permission(user, permission):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


async def get_websocket_user(websocket: WebSocket) -> dict[str, Any] | None:
    token = websocket.cookies.get(_cookie_name())
    return await get_user_from_session_token(token)


def role_definitions_payload() -> list[dict[str, Any]]:
    return [
        {
            "key": role_key,
            "label": role_def["label"],
            "permissions": list(role_def["permissions"]),
        }
        for role_key, role_def in ROLE_DEFINITIONS.items()
    ]