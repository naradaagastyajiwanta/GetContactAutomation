"""
FastAPI orchestrator - main server that ties everything together.
Run: uvicorn orchestrator.main:app --port 8000 --reload
"""
import asyncio
import csv
import io
import json as _json
import functools
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

# Dedicated thread-pool for long-running Playwright operations so they
# don't starve the default executor used by normal request handlers.
_pw_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pw-login")

import httpx
from fastapi import FastAPI, BackgroundTasks, UploadFile, File as FastAPIFile, Form, Query, WebSocket, WebSocketDisconnect, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from orchestrator.config import WA_SERVICE_URL, WEBHOOK_URL, log, is_paused, set_paused, cfg
from orchestrator.websocket import manager as ws_manager
from orchestrator.db import (
    init_db,
    get_dashboard_stats,
    get_universities_by_status,
    get_all_universities,
    list_universities_paginated,
    export_universities_filtered,
    export_universities_by_ids,
    export_contacts_filtered,
    match_university_names,
    get_university_provinces,
    toggle_university_enabled,
    bulk_toggle_universities_enabled,
    get_pipeline_status,
    get_conversation_by_phone,
    get_university_by_id,
    get_contacts_for_university,
    get_posts_for_university,
    get_conversations_filtered,
    get_conversation_by_id,
    add_university,
    search_universities,
    validate_phone,
    get_all_active_lessons,
    get_unprocessed_analyses,
    upsert_config,
    get_all_config,
    delete_config as db_delete_config,
    create_conversation,
    update_conversation_state,
    add_message_to_history,
    get_knowledge_items,
    get_knowledge_items_by_tags,
    create_knowledge_item,
    update_knowledge_item,
    delete_knowledge_item,
    get_api_call_logs,
    get_api_call_log_by_id,
    cleanup_old_api_logs,
    clear_all_response_ids,
    get_audiensi_conversation_by_phone,
    update_audiensi_state,
    create_pipeline_log,
    complete_pipeline_log,
    get_pipeline_logs,
    get_pipeline_log_by_id,
    cleanup_old_pipeline_logs,
    get_email_blast_quota_info,
    get_db,
    count_active_auth_role_assignments,
    count_auth_audit_logs,
    count_auth_role_upgrade_requests,
    create_auth_role_upgrade_request,
    get_active_auth_role_assignment,
    get_auth_role_upgrade_request,
    get_pending_auth_role_upgrade_request_for_user,
    list_auth_audit_logs,
    list_auth_role_upgrade_requests,
    list_auth_role_upgrade_requests_for_user,
    list_auth_role_assignments,
    resolve_auth_role_upgrade_request,
    upsert_auth_user_role,
    deactivate_auth_user_role,
    revoke_auth_sessions_for_user,
)
from orchestrator.config_registry import (
    CONFIG_DEFINITIONS,
    CONFIG_DEFINITIONS_MAP,
    ConfigDef,
    ConfigType,
)
from orchestrator.agent.learning import LearningSystem
from orchestrator import blast_service
from orchestrator import email_blast
from orchestrator.conversation import conversation_manager, ConvState
from orchestrator.message_queue import message_queue
from orchestrator.scheduler import (
    setup_scheduler,
    scheduler,
    daily_outreach_loop,
    process_followups,
    run_agent_in_thread,
)
from orchestrator.agents.ig_handle_finder import run_handle_search_batch, run_handle_search_for_universities
from orchestrator.agents.ig_post_scraper import run_post_scrape_batch, run_post_scrape_for_universities
from orchestrator.agents.ig_phone_extractor import run_phone_extraction_batch, run_phone_extraction_for_universities
from orchestrator.agents.bem_finder import run_bem_discovery_batch, run_bem_discovery_for_universities
from orchestrator.agents.rector_finder import run_rector_finder_batch
from orchestrator.config import PROVINCES
from orchestrator.auth import (
    can_bootstrap_auth,
    clear_auth_cookie,
    create_session_for_user,
    get_request_user,
    get_user_from_session_token,
    get_websocket_user,
    has_permission,
    log_auth_event,
    normalize_role_key,
    require_permission,
    revoke_session_token,
    role_definitions_payload,
    validate_login_credentials,
)
from orchestrator.dms_mysql import get_active_karyawan_by_email

learning_system = LearningSystem()

_TERMINAL_STATES = {"GOT_NUMBER", "REFUSED", "ABANDONED"}
_AUDIENSI_TERMINAL_STATES = {"ZOOM_SENT", "REFUSED", "ABANDONED"}
_ROLE_PRIORITY = {
    "viewer": 1,
    "operator": 2,
    "admin": 3,
}

# ---------------------------------------------------------------------------
# Per-phone concurrency lock (prevents race conditions from overlapping
# debounce windows delivering two messages for the same phone concurrently)
# ---------------------------------------------------------------------------

_phone_locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
_phone_locks_guard = asyncio.Lock()
_MAX_PHONE_LOCKS = 5000


async def _get_phone_lock(phone: str) -> asyncio.Lock:
    """Return an asyncio.Lock for *phone*, creating one if needed.

    Uses an LRU strategy: the most-recently-used lock is moved to the end
    of the OrderedDict.  When the dict exceeds ``_MAX_PHONE_LOCKS`` entries
    the oldest (least-recently-used) entry is evicted.
    """
    async with _phone_locks_guard:
        if phone in _phone_locks:
            _phone_locks.move_to_end(phone)
            return _phone_locks[phone]
        if len(_phone_locks) >= _MAX_PHONE_LOCKS:
            _phone_locks.popitem(last=False)  # evict oldest
        lock = asyncio.Lock()
        _phone_locks[phone] = lock
        return lock


# ---------------------------------------------------------------------------
# Periodic IG session health check (lightweight — no browser launch)
# ---------------------------------------------------------------------------

_IG_HEALTH_INTERVAL = 300  # 5 minutes
_SMTP_HEALTH_INTERVAL = 300  # 5 minutes

async def _periodic_ig_health_check():
    """
    Background task: log IG account pool status every 5 minutes.
    Uses existing in-memory pool state (login_ok, healthy, last_error)
    that is updated by actual scraping operations & login flows —
    does NOT launch browsers.
    """
    await asyncio.sleep(60)  # initial delay — let everything boot
    while True:
        try:
            from orchestrator.playwright_ig import _account_pool
            pool = _account_pool.status()
            total = len(pool)
            healthy = sum(1 for a in pool if a["healthy"])
            if total > 0 and healthy < total:
                log.warning(
                    "[IGHealthCheck] %d/%d accounts healthy — %s",
                    healthy, total,
                    ", ".join(
                        f"@{a['username']}={a.get('last_error', 'unhealthy')}"
                        for a in pool if not a["healthy"]
                    ),
                )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.error("[IGHealthCheck] Error: %s", exc, exc_info=True)

        await asyncio.sleep(_IG_HEALTH_INTERVAL)


def _normalize_smtp_health_status(status: Any) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"unknown", "healthy", "error", "checking"}:
        return normalized
    return "unknown"


def _smtp_health_event_payload(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(account.get("id", 0)),
        "enabled": bool(account.get("enabled", True)),
        "health_status": _normalize_smtp_health_status(account.get("health_status")),
        "health_message": str(account.get("health_message") or "").strip(),
        "last_checked_at": account.get("last_checked_at"),
        "last_healthy_at": account.get("last_healthy_at"),
        "last_error_at": account.get("last_error_at"),
    }


def _apply_smtp_health_result(
    account: dict[str, Any],
    *,
    success: bool,
    message: str,
    checked_at: str,
) -> dict[str, Any]:
    updated = {
        **account,
        "health_status": "healthy" if success else "error",
        "health_message": str(message or "").strip(),
        "last_checked_at": checked_at,
    }

    if success:
        updated["last_healthy_at"] = checked_at
    else:
        updated["last_error_at"] = checked_at

    return updated


async def _set_managed_smtp_account_health(account_id: int, success: bool, message: str) -> dict[str, Any] | None:
    accounts = await _get_managed_smtp_accounts()
    index = next((i for i, account in enumerate(accounts) if int(account.get("id", 0)) == account_id), -1)
    if index == -1:
        return None

    checked_at = datetime.now(timezone.utc).isoformat()
    updated = _apply_smtp_health_result(accounts[index], success=success, message=message, checked_at=checked_at)
    accounts[index] = updated
    await _save_managed_smtp_accounts(accounts, reset_client=False)
    await ws_manager.broadcast_type("email_smtp_account_health", account=_smtp_health_event_payload(updated))
    return updated


async def _run_managed_smtp_health_checks() -> dict[str, int]:
    accounts = await _get_managed_smtp_accounts()
    if not accounts:
        return {"checked": 0, "healthy": 0, "failed": 0}

    next_accounts = list(accounts)
    health_updates: list[dict[str, Any]] = []
    checked = 0
    healthy = 0
    failed = 0

    for index, account in enumerate(accounts):
        if not bool(account.get("enabled", True)):
            continue

        success, message = await asyncio.to_thread(email_blast.test_smtp_account, account)
        checked_at = datetime.now(timezone.utc).isoformat()
        updated = _apply_smtp_health_result(account, success=success, message=message, checked_at=checked_at)
        next_accounts[index] = updated
        health_updates.append(_smtp_health_event_payload(updated))
        checked += 1
        if success:
            healthy += 1
        else:
            failed += 1

    if health_updates:
        await _save_managed_smtp_accounts(next_accounts, reset_client=False)
        for payload in health_updates:
            await ws_manager.broadcast_type("email_smtp_account_health", account=payload)

    if failed > 0:
        log.warning("[SMTPHealthCheck] %d/%d accounts unhealthy", failed, checked)
    else:
        log.debug("[SMTPHealthCheck] %d/%d accounts healthy", healthy, checked)

    return {"checked": checked, "healthy": healthy, "failed": failed}


async def _periodic_smtp_health_check() -> None:
    """Periodically verify enabled managed SMTP accounts and publish health updates."""
    await asyncio.sleep(30)

    while True:
        try:
            await _run_managed_smtp_health_checks()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.error("[SMTPHealthCheck] Error: %s", exc, exc_info=True)

        await asyncio.sleep(_SMTP_HEALTH_INTERVAL)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await cfg.init_from_db()
    await _sync_managed_smtp_accounts_from_storage()

    # Recover orphaned marketing states from any prior crash
    try:
        from orchestrator.marketing import groups as _mkt_groups
        _recovery = await _mkt_groups.recover_orphaned_states()
        if any(_recovery.values()):
            log.info(
                "Marketing startup recovery: %d run(s) interrupted, "
                "%d client(s) orchestration-state reset, "
                "%d client(s) search-status reset to pending",
                _recovery["runs_interrupted"],
                _recovery["clients_state_reset"],
                _recovery["clients_searching_reset"],
            )
    except Exception as _e:
        log.warning("Marketing startup recovery failed (non-critical): %s", _e)

    log.info("Database initialized")

    # Register the running event loop so LogStreamHandler can broadcast log lines
    from orchestrator.config import set_log_broadcast_loop
    set_log_broadcast_loop(asyncio.get_running_loop())

    # Restore persistent pause state
    try:
        all_cfg = await get_all_config()
        if all_cfg.get("BOT_PAUSED") == "true":
            set_paused(True)
            log.info("Bot started in PAUSED state (restored from DB)")
    except Exception as e:
        log.warning("Failed to restore pause state: %s", e)

    # Cleanup old API call logs
    try:
        deleted = await cleanup_old_api_logs(days=cfg.API_LOG_RETENTION_DAYS)
        if deleted:
            log.info("Cleaned up %d old API call logs", deleted)
    except Exception as e:
        log.warning("Failed to cleanup old API logs: %s", e)

    # Cleanup old pipeline logs (keep 30 days)
    try:
        deleted = await cleanup_old_pipeline_logs(days=30)
        if deleted:
            log.info("Cleaned up %d old pipeline logs", deleted)
    except Exception as e:
        log.warning("Failed to cleanup old pipeline logs: %s", e)

    # Register webhook with WA service
    await register_webhook()

    # Initialize DMS MySQL connection pool
    try:
        from orchestrator.dms_mysql import init_dms_pool, close_dms_pool
        dms_pool = await init_dms_pool()
        if dms_pool:
            log.info("DMS MySQL pool initialized")
    except Exception as e:
        log.warning("DMS MySQL init failed (non-critical): %s", e)

    # Ensure audiensi research table
    try:
        from orchestrator.audiensi_research import ensure_research_table
        await ensure_research_table()
    except Exception as e:
        log.warning("Failed to ensure research table: %s", e)

    # Start message queue send worker
    worker_task = asyncio.create_task(message_queue.send_worker())

    # Restore blast auto-resume timers after restart
    try:
        await blast_service.restore_background_tasks()
    except Exception as e:
        log.warning("Failed to restore blast background tasks: %s", e)

    # Start periodic IG session health checker (every 5 min)
    ig_health_task = asyncio.create_task(_periodic_ig_health_check())

    # Start periodic SMTP health checker for managed mailbox rotation
    smtp_health_task = asyncio.create_task(_periodic_smtp_health_check())

    # Start inbox reply watcher so IMAP replies are pushed over WebSocket
    inbox_watch_task = asyncio.create_task(email_blast.watch_inbox_replies_forever())

    # Start scheduler
    setup_scheduler()
    log.info("Orchestrator started on port 8000")

    yield

    # Cancel background tasks
    inbox_watch_task.cancel()
    ig_health_task.cancel()
    smtp_health_task.cancel()
    worker_task.cancel()

    # Shutdown
    scheduler.shutdown(wait=False)

    # Close DMS MySQL pool
    try:
        from orchestrator.dms_mysql import close_dms_pool
        await close_dms_pool()
    except Exception:
        pass

    log.info("Scheduler stopped, shutting down")


app = FastAPI(title="GetContact AI Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_PUBLIC_AUTH_PATHS = {
    "/auth/bootstrap-status",
    "/auth/login",
    "/auth/logout",
    "/auth/me",
    "/auth/setup",
    "/health",
    "/openapi.json",
    "/redoc",
    "/webhook/incoming",
}
_PUBLIC_AUTH_PREFIXES = (
    "/docs",
)


def _normalize_request_path(path: str) -> str:
    if path == "/":
        return path
    return path.rstrip("/")


def _is_public_path(path: str) -> bool:
    normalized = _normalize_request_path(path)
    if normalized in _PUBLIC_AUTH_PATHS:
        return True
    return any(normalized.startswith(prefix) for prefix in _PUBLIC_AUTH_PREFIXES)


def _required_permission_for_request(method: str, path: str) -> str | None:
    normalized = _normalize_request_path(path)
    upper_method = method.upper()

    if normalized == "/conversations/test":
        return "whatsapp.manage"

    if normalized == "/universities/with-emails":
        return "blast.manage"

    if normalized.startswith("/auth/access") or normalized == "/auth/roles":
        return "settings.manage"

    if normalized.startswith("/config"):
        return "settings.manage"

    if normalized.startswith("/email-smtp-accounts"):
        return "settings.manage"

    if normalized.startswith("/control"):
        if normalized == "/control/status":
            return "pipeline.view"
        if normalized.startswith("/control/chatbot"):
            return "settings.manage"
        return "pipeline.manage"

    if normalized.startswith("/wa"):
        return "whatsapp.view" if upper_method == "GET" else "whatsapp.manage"

    if normalized.startswith("/pipeline"):
        if upper_method == "GET":
            return "pipeline.view"
        if normalized == "/pipeline/run-agent-targeted":
            return "pipeline.run"
        return "pipeline.manage"

    if normalized.startswith("/outreach"):
        return "pipeline.run"

    if normalized.startswith("/universities") or normalized.startswith("/contacts") or normalized.startswith("/university-groups"):
        if upper_method == "GET":
            return "universities.view"
        if normalized == "/universities/match-names":
            return "universities.view"
        return "universities.manage"

    if normalized.startswith("/conversations"):
        return "conversations.view"

    if normalized.startswith("/learning"):
        return "learning.view" if upper_method == "GET" else "learning.manage"

    if normalized.startswith("/knowledge-items"):
        return "knowledge.view" if upper_method == "GET" else "knowledge.manage"

    if normalized.startswith("/api-logs"):
        return "settings.manage"

    if normalized.startswith("/audiensi"):
        return "audiensi.view" if upper_method == "GET" else "audiensi.manage"

    if normalized.startswith("/crm"):
        return "crm.view" if upper_method == "GET" else "crm.manage"

    if normalized.startswith("/blast") or normalized.startswith("/email-blast"):
        return "blast.view" if upper_method == "GET" else "blast.manage"

    return None


def _campaign_actor_name(user: dict[str, Any] | None) -> str | None:
    if not user:
        return None
    return str(user.get("name") or user.get("email") or "").strip() or None


async def _require_blast_campaign_access(campaign_id: int) -> dict[str, Any]:
    campaign = await blast_service.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


async def _require_email_campaign_access(campaign_id: int) -> dict[str, Any]:
    campaign = await email_blast.get_campaign_status(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@app.middleware("http")
async def auth_http_middleware(request: Request, call_next):
    request.state.current_user = None

    if request.method == "OPTIONS" or _is_public_path(request.url.path):
        return await call_next(request)

    session_token = request.cookies.get(str(cfg.get("AUTH_COOKIE_NAME", "dms_marketing_session")))
    user = await get_user_from_session_token(session_token)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    required_permission = _required_permission_for_request(request.method, request.url.path)
    if required_permission and not has_permission(user, required_permission):
        return JSONResponse(status_code=403, content={"detail": "Insufficient permissions"})

    request.state.current_user = user
    return await call_next(request)


class AuthLoginPayload(BaseModel):
    email: str
    password: str


class AuthSetupPayload(AuthLoginPayload):
    role_key: str = "admin"


class AuthGrantRolePayload(BaseModel):
    email: str
    role_key: str


class AuthRevokeRolePayload(BaseModel):
    dms_user_id: int
    role_key: str


class AuthRoleUpgradeRequestPayload(BaseModel):
    role_key: str
    request_note: str | None = None


class AuthRoleUpgradeDecisionPayload(BaseModel):
    review_note: str | None = None


class AuthAuditLogsResponse(BaseModel):
    logs: list[dict[str, Any]]
    total: int


def _highest_role_key(user: dict[str, Any]) -> str:
    role_keys = [str(role) for role in user.get("roles", []) if role in _ROLE_PRIORITY]
    if not role_keys:
        return "viewer"
    return max(role_keys, key=lambda role_key: _ROLE_PRIORITY[role_key])


def _available_role_upgrade_keys(user: dict[str, Any]) -> list[str]:
    current_role_key = _highest_role_key(user)
    current_priority = _ROLE_PRIORITY.get(current_role_key, 0)
    return [
        role_key
        for role_key in _ROLE_PRIORITY
        if _ROLE_PRIORITY[role_key] > current_priority
    ]


@app.get("/auth/bootstrap-status")
async def auth_bootstrap_status():
    """Return whether local auth bootstrap is still required."""
    return {"required": await can_bootstrap_auth()}


@app.post("/auth/setup")
async def auth_setup(payload: AuthSetupPayload, request: Request, response: Response):
    """Bootstrap the first local dashboard admin using a valid DMS karyawan account."""
    if not await can_bootstrap_auth():
        await log_auth_event(
            "bootstrap",
            request=request,
            actor_email=payload.email.strip().lower(),
            subject_email=payload.email.strip().lower(),
            role_key=payload.role_key,
            success=False,
            detail="Auth bootstrap has already been completed",
        )
        return JSONResponse(status_code=409, content={"detail": "Auth bootstrap has already been completed"})

    try:
        dms_user = await validate_login_credentials(payload.email, payload.password)
        role_key = normalize_role_key(payload.role_key)
        await upsert_auth_user_role(
            dms_user_id=int(dms_user["dms_user_id"]),
            user_email=str(dms_user.get("user_email") or ""),
            user_name=str(dms_user.get("user_name") or "Unknown User"),
            role_key=role_key,
            granted_by_email=str(dms_user.get("user_email") or ""),
        )
        user = await create_session_for_user(response, dms_user, request)
        await log_auth_event(
            "bootstrap",
            request=request,
            actor=user,
            subject=user,
            role_key=role_key,
            success=True,
            detail="Initial dashboard admin created",
        )
        return {"status": "ok", "bootstrap_completed": True, "user": user}
    except HTTPException as exc:
        await log_auth_event(
            "bootstrap",
            request=request,
            actor_email=payload.email.strip().lower(),
            subject_email=payload.email.strip().lower(),
            role_key=payload.role_key,
            success=False,
            detail=str(exc.detail),
        )
        raise


@app.post("/auth/login")
async def auth_login(payload: AuthLoginPayload, request: Request, response: Response):
    """Authenticate using DMS karyawan credentials and create a local dashboard session."""
    try:
        dms_user = await validate_login_credentials(payload.email, payload.password)
        user = await create_session_for_user(response, dms_user, request)
        detail = "Dashboard session created"
        if dms_user.get("_auth_default_password_used"):
            detail = "Dashboard session created using default password"
        await log_auth_event(
            "login",
            request=request,
            actor=user,
            subject=user,
            success=True,
            detail=detail,
        )
        return {"status": "ok", "user": user}
    except HTTPException as exc:
        normalized_email = payload.email.strip().lower()
        await log_auth_event(
            "login",
            request=request,
            actor_email=normalized_email,
            subject_email=normalized_email,
            success=False,
            detail=str(exc.detail),
        )
        raise


@app.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    """Revoke the current dashboard session."""
    session_token = request.cookies.get(str(cfg.get("AUTH_COOKIE_NAME", "dms_marketing_session")))
    user = await get_user_from_session_token(session_token)
    await revoke_session_token(session_token)
    clear_auth_cookie(response)
    await log_auth_event(
        "logout",
        request=request,
        actor=user,
        subject=user,
        success=True,
        detail="Dashboard session revoked",
    )
    return {"status": "ok"}


@app.get("/auth/me")
async def auth_me(request: Request):
    """Return the current authenticated user from the session cookie."""
    session_token = request.cookies.get(str(cfg.get("AUTH_COOKIE_NAME", "dms_marketing_session")))
    user = await get_user_from_session_token(session_token)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return {"user": user}


@app.get("/auth/roles")
async def auth_roles(request: Request):
    """Return supported local role definitions."""
    await require_permission(request, "settings.manage")
    return {"roles": role_definitions_payload()}


@app.get("/auth/access")
async def auth_access_list(request: Request):
    """Return current local access assignments."""
    await require_permission(request, "settings.manage")
    return {
        "assignments": await list_auth_role_assignments(),
        "roles": role_definitions_payload(),
    }


@app.get("/auth/audit-logs")
async def auth_audit_logs(request: Request, limit: int = 50, offset: int = 0):
    """Return recent auth audit logs for dashboard administration."""
    await require_permission(request, "settings.manage")
    bounded_limit = max(1, min(limit, 200))
    bounded_offset = max(0, offset)
    return {
        "logs": await list_auth_audit_logs(limit=bounded_limit, offset=bounded_offset),
        "total": await count_auth_audit_logs(),
    }


@app.get("/auth/role-requests/me")
async def auth_role_requests_me(request: Request, limit: int = 20):
    """Return recent role-upgrade requests for the signed-in user."""
    current_user = await get_request_user(request)
    bounded_limit = max(1, min(limit, 50))
    return {
        "requests": await list_auth_role_upgrade_requests_for_user(
            int(current_user["dms_user_id"]),
            limit=bounded_limit,
        ),
        "available_roles": [
            role_key
            for role_key in _available_role_upgrade_keys(current_user)
            if role_key != "viewer"
        ],
    }


@app.post("/auth/role-requests")
async def auth_role_requests_create(payload: AuthRoleUpgradeRequestPayload, request: Request):
    """Create a role-upgrade request for a signed-in viewer user."""
    current_user = await get_request_user(request)
    requested_role_key = normalize_role_key(payload.role_key)
    current_role_key = _highest_role_key(current_user)
    allowed_role_keys = [
        role_key
        for role_key in _available_role_upgrade_keys(current_user)
        if role_key != "viewer"
    ]
    if current_role_key != "viewer":
        await log_auth_event(
            "request_role_upgrade",
            request=request,
            actor=current_user,
            subject=current_user,
            role_key=requested_role_key,
            success=False,
            detail="Role upgrade request is only available for viewer users",
        )
        return JSONResponse(status_code=403, content={"detail": "Role upgrade request is only available for viewer users"})

    if requested_role_key not in allowed_role_keys:
        await log_auth_event(
            "request_role_upgrade",
            request=request,
            actor=current_user,
            subject=current_user,
            role_key=requested_role_key,
            success=False,
            detail="Requested role is not a valid upgrade target",
        )
        return JSONResponse(status_code=422, content={"detail": "Requested role is not a valid upgrade target"})

    existing_request = await get_pending_auth_role_upgrade_request_for_user(int(current_user["dms_user_id"]))
    if existing_request:
        await log_auth_event(
            "request_role_upgrade",
            request=request,
            actor=current_user,
            subject=current_user,
            role_key=requested_role_key,
            success=False,
            detail=f"Pending request #{existing_request['id']} already exists",
        )
        return JSONResponse(status_code=409, content={"detail": "You already have a pending role request"})

    note = (payload.request_note or "").strip() or None
    request_id = await create_auth_role_upgrade_request(
        requester_dms_user_id=int(current_user["dms_user_id"]),
        requester_email=str(current_user.get("email") or ""),
        requester_name=str(current_user.get("name") or "Unknown User"),
        current_role_key=current_role_key,
        requested_role_key=requested_role_key,
        request_note=note,
    )
    created_request = await get_auth_role_upgrade_request(request_id)
    await log_auth_event(
        "request_role_upgrade",
        request=request,
        actor=current_user,
        subject=current_user,
        role_key=requested_role_key,
        success=True,
        detail=f"Submitted role upgrade request #{request_id}",
    )
    return {
        "status": "ok",
        "request": created_request,
    }


@app.get("/auth/role-requests")
async def auth_role_requests_list(
    request: Request,
    status: str | None = Query(default="pending"),
    limit: int = 50,
    offset: int = 0,
):
    """Return role-upgrade requests for admin review."""
    await require_permission(request, "settings.manage")
    normalized_status = None
    if status:
        normalized_status = status.strip().lower()
        if normalized_status not in {"pending", "approved", "rejected"}:
            return JSONResponse(status_code=422, content={"detail": "Invalid request status"})
    bounded_limit = max(1, min(limit, 200))
    bounded_offset = max(0, offset)
    return {
        "requests": await list_auth_role_upgrade_requests(
            status=normalized_status,
            limit=bounded_limit,
            offset=bounded_offset,
        ),
        "total": await count_auth_role_upgrade_requests(status=normalized_status),
    }


@app.post("/auth/role-requests/{request_id}/approve")
async def auth_role_requests_approve(
    request_id: int,
    payload: AuthRoleUpgradeDecisionPayload,
    request: Request,
):
    """Approve a pending role-upgrade request and grant the requested role."""
    current_user = await require_permission(request, "settings.manage")
    existing_request = await get_auth_role_upgrade_request(request_id)
    if not existing_request:
        return JSONResponse(status_code=404, content={"detail": "Role request not found"})
    if existing_request.get("status") != "pending":
        return JSONResponse(status_code=409, content={"detail": "Role request has already been processed"})

    requested_role_key = normalize_role_key(str(existing_request.get("requested_role_key") or ""))
    await upsert_auth_user_role(
        dms_user_id=int(existing_request["requester_dms_user_id"]),
        user_email=str(existing_request.get("requester_email") or ""),
        user_name=str(existing_request.get("requester_name") or "Unknown User"),
        role_key=requested_role_key,
        granted_by_email=str(current_user.get("email") or ""),
    )
    await resolve_auth_role_upgrade_request(
        request_id=request_id,
        status="approved",
        reviewed_by_dms_user_id=int(current_user["dms_user_id"]),
        reviewed_by_email=str(current_user.get("email") or ""),
        review_note=(payload.review_note or "").strip() or None,
    )
    await log_auth_event(
        "approve_role_upgrade_request",
        request=request,
        actor=current_user,
        subject_dms_user_id=int(existing_request["requester_dms_user_id"]),
        subject_email=str(existing_request.get("requester_email") or ""),
        role_key=requested_role_key,
        success=True,
        detail=f"Approved role request #{request_id}",
    )
    return {"status": "ok"}


@app.post("/auth/role-requests/{request_id}/reject")
async def auth_role_requests_reject(
    request_id: int,
    payload: AuthRoleUpgradeDecisionPayload,
    request: Request,
):
    """Reject a pending role-upgrade request."""
    current_user = await require_permission(request, "settings.manage")
    existing_request = await get_auth_role_upgrade_request(request_id)
    if not existing_request:
        return JSONResponse(status_code=404, content={"detail": "Role request not found"})
    if existing_request.get("status") != "pending":
        return JSONResponse(status_code=409, content={"detail": "Role request has already been processed"})

    requested_role_key = normalize_role_key(str(existing_request.get("requested_role_key") or ""))
    await resolve_auth_role_upgrade_request(
        request_id=request_id,
        status="rejected",
        reviewed_by_dms_user_id=int(current_user["dms_user_id"]),
        reviewed_by_email=str(current_user.get("email") or ""),
        review_note=(payload.review_note or "").strip() or None,
    )
    await log_auth_event(
        "reject_role_upgrade_request",
        request=request,
        actor=current_user,
        subject_dms_user_id=int(existing_request["requester_dms_user_id"]),
        subject_email=str(existing_request.get("requester_email") or ""),
        role_key=requested_role_key,
        success=True,
        detail=f"Rejected role request #{request_id}",
    )
    return {"status": "ok"}


@app.post("/auth/access/grant")
async def auth_access_grant(payload: AuthGrantRolePayload, request: Request):
    """Grant a local dashboard role to an active DMS karyawan user."""
    current_user = await require_permission(request, "settings.manage")
    role_key = normalize_role_key(payload.role_key)
    dms_user = await get_active_karyawan_by_email(payload.email)
    if not dms_user:
        await log_auth_event(
            "grant_role",
            request=request,
            actor=current_user,
            subject_email=payload.email.strip().lower(),
            role_key=role_key,
            success=False,
            detail="Active DMS user not found for this email",
        )
        return JSONResponse(status_code=404, content={"detail": "Active DMS user not found for this email"})

    await upsert_auth_user_role(
        dms_user_id=int(dms_user["dms_user_id"]),
        user_email=str(dms_user.get("user_email") or ""),
        user_name=str(dms_user.get("user_name") or "Unknown User"),
        role_key=role_key,
        granted_by_email=str(current_user.get("email") or ""),
    )
    await log_auth_event(
        "grant_role",
        request=request,
        actor=current_user,
        subject=dms_user,
        role_key=role_key,
        success=True,
        detail="Local dashboard role granted",
    )
    return {"status": "ok"}


@app.post("/auth/access/revoke")
async def auth_access_revoke(payload: AuthRevokeRolePayload, request: Request):
    """Revoke a local dashboard role and invalidate active sessions for that user."""
    current_user = await require_permission(request, "settings.manage")
    role_key = normalize_role_key(payload.role_key)
    assignment = await get_active_auth_role_assignment(payload.dms_user_id, role_key)
    if role_key == "admin":
        admin_count = await count_active_auth_role_assignments("admin")
        if admin_count <= 1:
            await log_auth_event(
                "revoke_role",
                request=request,
                actor=current_user,
                subject_dms_user_id=payload.dms_user_id,
                subject_email=assignment.get("user_email") if assignment else None,
                role_key=role_key,
                success=False,
                detail="At least one admin must remain active",
            )
            return JSONResponse(status_code=409, content={"detail": "At least one admin must remain active"})

    await deactivate_auth_user_role(payload.dms_user_id, role_key)
    await revoke_auth_sessions_for_user(payload.dms_user_id)
    await log_auth_event(
        "revoke_role",
        request=request,
        actor=current_user,
        subject_dms_user_id=payload.dms_user_id,
        subject_email=assignment.get("user_email") if assignment else None,
        role_key=role_key,
        success=True,
        detail="Local dashboard role revoked",
    )
    return {"status": "ok"}


async def register_webhook():
    """Register our webhook URL with the WhatsApp service."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{WA_SERVICE_URL}/webhook/register",
                json={"url": WEBHOOK_URL},
            )
            if resp.status_code == 200:
                log.info(f"Webhook registered: {WEBHOOK_URL}")
            else:
                log.warning(f"Webhook registration returned {resp.status_code}")
        except Exception as e:
            log.warning(f"Could not register webhook (WA service may not be running): {e}")


# ---------------------------------------------------------------------------
# Webhook endpoint (receives incoming WA messages from Node.js service)
# ---------------------------------------------------------------------------

class IncomingMessage(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str | None = None
    message: str
    timestamp: int | None = None
    messageId: str | None = None
    pushName: str | None = None


@app.post("/webhook/incoming")
async def handle_incoming_message(payload: dict, background_tasks: BackgroundTasks):
    """Handle incoming WhatsApp message forwarded from Node.js service."""
    phone = payload.get("from", "")
    message = payload.get("message", "")
    push_name = payload.get("pushName", "")
    msg_key = payload.get("msgKey")
    all_msg_keys = payload.get("allMsgKeys")

    if not phone or not message:
        return {"status": "ignored", "reason": "empty payload"}

    # Normalize phone to +62 format for lookup
    normalized = validate_phone(phone) or phone

    log.info(f"Incoming WA from {phone} ({push_name}): {message[:100]}")

    # Process in background to respond quickly to webhook
    background_tasks.add_task(
        _process_incoming, normalized, phone, message, push_name, msg_key, all_msg_keys,
    )

    return {"status": "received"}


# ---------------------------------------------------------------------------
# WebSocket endpoint for real-time notifications
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates to the frontend."""
    user = await get_websocket_user(websocket)
    if not user:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    websocket.state.current_user = user
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive with heartbeat
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        log.warning(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


async def _process_incoming(
    normalized_phone: str,
    raw_phone: str,
    message: str,
    push_name: str = "",
    msg_key: str | None = None,
    all_msg_keys: list | None = None,
):
    """Process incoming message and respond if needed.

    Routes to the appropriate handler: chatbot 1 (contact finder) or
    audiensi chatbot (Zoom scheduling).
    """
    if is_paused():
        log.info(f"Paused – ignoring incoming message from {raw_phone}")
        return

    # Acquire per-phone lock to prevent concurrent processing of messages
    # from the same phone number (avoids duplicate responses & state corruption).
    lock = await _get_phone_lock(normalized_phone)
    async with lock:
        # Try audiensi chatbot first (phase 2 conversations)
        if cfg.AUDIENSI_ENABLED:
            try:
                from orchestrator.audiensi.conversation import audiensi_conversation_manager
                from orchestrator.audiensi.states import AudiensiState

                aud = await get_audiensi_conversation_by_phone(normalized_phone)
                if aud and aud["state"] not in AudiensiState.terminal_states():
                    log.info(f"Routing to audiensi handler for {raw_phone}")
                    result = await message_queue.process_with_ai(
                        audiensi_conversation_manager.process_incoming_message(
                            normalized_phone, message, push_name=push_name,
                        )
                    )
                    if result.get("response_message"):
                        await message_queue.enqueue_send(
                            raw_phone, result["response_message"],
                            reply_to_msg_key=msg_key, all_msg_keys=all_msg_keys,
                        )
                    # Trigger post-audiensi analysis for terminal states
                    if result.get("conversation_state") in _AUDIENSI_TERMINAL_STATES and cfg.LEARNING_ENABLED:
                        asyncio.create_task(learning_system.analyze_completed_audiensi(aud["id"]))
                    return
            except Exception as e:
                log.warning(f"Audiensi routing check failed: {e}")
                # Send error message to the contact instead of falling through to chatbot 1
                await message_queue.enqueue_send(
                    raw_phone,
                    "Mohon maaf, ada kendala teknis. Kami akan menghubungi Anda kembali.",
                    reply_to_msg_key=msg_key, all_msg_keys=all_msg_keys,
                )
                return

        # Default: chatbot 1 (contact finder)
        if not cfg.CHATBOT_ENABLED:
            log.info(f"Contact finder chatbot disabled – ignoring message from {raw_phone}")
            return

        try:
            log.info(f"Processing message from {raw_phone} with AI (model: {cfg.AGENT_MODEL})...")
            result = await message_queue.process_with_ai(
                conversation_manager.process_incoming_message(
                    normalized_phone, message, push_name=push_name,
                )
            )
            log.info(f"AI processing done for {raw_phone}: action={result.get('action')}")
        except Exception as e:
            log.error(f"Failed to process message from {raw_phone}: {e}", exc_info=True)
            return

        if result.get("response_message"):
            await message_queue.enqueue_send(
                raw_phone, result["response_message"],
                reply_to_msg_key=msg_key, all_msg_keys=all_msg_keys,
            )
        else:
            log.warning(f"No response_message generated for {raw_phone}")

        # Trigger post-conversation analysis for terminal states
        if result.get("conversation_state") in _TERMINAL_STATES and cfg.LEARNING_ENABLED:
            conv = await get_conversation_by_phone(normalized_phone)
            if conv:
                asyncio.create_task(learning_system.analyze_completed_conversation(conv["id"]))


# ---------------------------------------------------------------------------
# Dashboard & Status
# ---------------------------------------------------------------------------

@app.get("/dashboard")
async def dashboard():
    """Get overall system statistics."""
    stats = await get_dashboard_stats()
    return stats


@app.get("/universities")
async def list_universities(
    status: str | None = None,
    search: str | None = None,
    province: str | None = None,
    has_ig: bool | None = None,
    enabled: bool | None = None,
    limit: int = 25,
    offset: int = 0,
    sort_by: str | None = None,
    order: str | None = None,
    group_id: int | None = None,
):
    """List universities with combined filters, sorting, and proper pagination."""
    return await list_universities_paginated(
        search=search,
        status=status,
        province=province,
        has_ig=has_ig,
        enabled=enabled,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        order=order,
        group_id=group_id,
    )


@app.get("/universities/export-excel")
async def export_universities_excel(
    status: str | None = None,
    search: str | None = None,
    province: str | None = None,
    has_ig: bool | None = None,
    enabled: bool | None = None,
    ids: str | None = None,
):
    """Export contacts (university name, contact name, phone) as Excel (.xlsx) file.

    Simple format with only 3 columns:
    - University Name
    - Contact Name
    - Phone Number

    Pass `ids` as comma-separated IDs to export only specific universities.
    When ids is provided, other filters are ignored.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    # Parse IDs if provided
    university_ids = None
    if ids:
        university_ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]

    # Get contacts data
    rows = await export_contacts_filtered(
        search=search,
        status=status,
        province=province,
        has_ig=has_ig,
        enabled=enabled,
        university_ids=university_ids,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Contacts"

    # -- Header style --
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_fill = PatternFill(start_color="10B981", end_color="10B981", fill_type="solid")  # Green
    header_alignment = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    headers = [
        ("Nama Universitas", 50),
        ("Nama Contact", 30),
        ("No. WhatsApp", 20),
    ]

    for col_idx, (title, width) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
        ws.column_dimensions[cell.column_letter].width = width

    # -- Data rows --
    for row_idx, row in enumerate(rows, 2):
        values = [
            row.get("university_name", ""),
            row.get("contact_name", ""),
            row.get("phone_number", ""),
        ]
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val or "")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = thin_border

    # -- Auto-filter --
    ws.auto_filter.ref = f"A1:C{len(rows) + 1}"

    # -- Freeze header row --
    ws.freeze_panes = "A2"

    # Write to bytes
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"contacts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/universities/match-names")
async def match_names_endpoint(body: dict):
    """Match a list of university names to existing records.

    Body: {"names": ["Universitas Indonesia", "ITB", ...]}
    Returns: [{"id": 1, "name": "Universitas Indonesia", "matched_query": "Universitas Indonesia"}, ...]
    """
    names = body.get("names", [])
    if not names or not isinstance(names, list):
        return JSONResponse({"error": "names must be a non-empty list"}, status_code=400)
    results = await match_university_names(names)
    return {"matches": results, "total_queries": len(names), "total_matched": len(results)}


@app.get("/universities/provinces")
async def universities_provinces():
    """Return distinct province values for filter dropdown."""
    return await get_university_provinces()


@app.get("/universities/with-emails")
async def universities_with_emails(
    province: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0
):
    """Return universities that have email_kampus, for email blast selection."""
    try:
        async with get_db() as db:
            base_query = "SELECT id, name, province, email_kampus, website FROM universities WHERE email_kampus IS NOT NULL AND email_kampus != '' AND enabled = 1"
            params = []

            if province:
                base_query += " AND province = ?"
                params.append(province)

            if search:
                base_query += " AND name LIKE ?"
                params.append(f"%{search}%")

            # Get total count
            count_query = "SELECT COUNT(*) FROM universities WHERE email_kampus IS NOT NULL AND email_kampus != '' AND enabled = 1"
            if province:
                count_query += " AND province = ?"
                params_count = [province]
            else:
                params_count = []
            cursor = await db.execute(count_query, params_count)
            total = (await cursor.fetchone())[0]

            # Get data
            data_query = base_query + " ORDER BY name LIMIT ? OFFSET ?"
            query_params = params + [limit, offset]
            cursor = await db.execute(data_query, query_params)
            rows = await cursor.fetchall()

            return {
                "data": [
                    {
                        "id": r[0],
                        "name": r[1],
                        "province": r[2],
                        "email": r[3],
                        "website": r[4]
                    }
                    for r in rows
                ],
                "total": total,
                "limit": limit,
                "offset": offset
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.patch("/universities/{university_id}/toggle-enabled")
async def toggle_enabled(university_id: int, enabled: bool = True):
    """Enable or disable a single university for pipeline processing."""
    ok = await toggle_university_enabled(university_id, enabled)
    if not ok:
        return JSONResponse({"error": "University not found"}, status_code=404)
    return {"id": university_id, "enabled": enabled}


@app.patch("/universities/bulk-toggle")
async def bulk_toggle(payload: dict):
    """Enable or disable multiple universities. Body: {ids: [1,2,3], enabled: true/false}"""
    ids = payload.get("ids", [])
    enabled = payload.get("enabled", True)
    if not ids:
        return JSONResponse({"error": "ids list required"}, status_code=400)
    updated = await bulk_toggle_universities_enabled(ids, enabled)
    return {"updated": updated, "enabled": enabled}


# ---------------------------------------------------------------------------
# PDDIKTI university collection
# ---------------------------------------------------------------------------

@app.get("/pddikti/provinces")
async def get_provinces():
    """Return the list of Indonesian provinces for PDDIKTI search."""
    return {"provinces": PROVINCES}


@app.post("/pipeline/collect-universities")
async def trigger_collect_universities(
    background_tasks: BackgroundTasks,
    province: str | None = None,
    limit: int | None = None,
):
    """Collect universities from PDDIKTI API. Optionally filter by province and limit."""
    from scripts.collect_universities import search_pddikti

    async def _collect(province: str | None, limit: int | None):
        log_id = await create_pipeline_log("collect_universities", "manual")
        try:
            existing = await get_all_universities(limit=10000)
            existing_names = [u["name"] for u in existing]

            from scripts.collect_universities import is_duplicate

            universities = await search_pddikti(province, limit=limit)
            added = 0
            failed = 0
            details = []
            for u in universities:
                if is_paused():
                    log.info("[PDDIKTI] Bot paused during collection, stopping early")
                    break
                if is_duplicate(u["name"], existing_names):
                    continue
                try:
                    await add_university(
                        name=u["name"],
                        pddikti_id=u.get("pddikti_id"),
                        province=u.get("province"),
                        website=u.get("website"),
                    )
                    existing_names.append(u["name"])
                    added += 1
                    details.append({"name": u["name"], "province": u.get("province"), "status": "added"})
                except Exception as e:
                    failed += 1
                    log.warning(f"Failed to add '{u['name']}': {e}")
            log.info(f"[PDDIKTI] Collected {added} new universities (province={province}, limit={limit})")
            await complete_pipeline_log(
                log_id,
                status="completed",
                summary={"added": added, "total_found": len(universities), "province": province},
                details=details[:100],  # Limit details to 100 entries
                items_processed=len(universities),
                items_success=added,
                items_failed=failed,
            )
            # Broadcast agent completion to frontend
            await ws_manager.broadcast_type(
                "agent_completed",
                agent="collect_universities",
                stats={"added": added, "total_found": len(universities)},
            )
        except Exception as e:
            log.error(f"[PDDIKTI] Collection failed: {e}")
            await complete_pipeline_log(log_id, status="failed", error=str(e))
            # Broadcast agent failure to frontend
            await ws_manager.broadcast_type(
                "agent_completed",
                agent="collect_universities",
                stats={"error": str(e)},
            )

    msg = f"Collecting universities from PDDIKTI"
    if province:
        msg += f" (province: {province})"
    if limit:
        msg += f" (limit: {limit})"
    background_tasks.add_task(run_agent_in_thread, _collect, province, limit)
    return {"status": "started", "message": msg}


# ---------------------------------------------------------------------------
# University manual add
# ---------------------------------------------------------------------------


class UniversityInput(BaseModel):
    name: str
    province: Optional[str] = None
    website: Optional[str] = None


class UniversityAddPayload(BaseModel):
    # Single university
    name: Optional[str] = None
    province: Optional[str] = None
    website: Optional[str] = None
    # Bulk
    universities: Optional[list[UniversityInput]] = None


async def _get_existing_university_names() -> set[str]:
    """Return a set of lowercased university names already in the database."""
    from orchestrator.db import get_db
    async with get_db() as db:
        cursor = await db.execute("SELECT LOWER(name) AS lname FROM universities")
        rows = await cursor.fetchall()
        return {r["lname"] for r in rows}


@app.post("/universities")
async def add_universities_endpoint(payload: UniversityAddPayload):
    """Add one or many universities via JSON.

    Single: {"name": "Univ X", "province": "...", "website": "..."}
    Bulk:   {"universities": [{"name": "..."}, ...]}
    """
    items: list[UniversityInput] = []

    if payload.universities:
        items = payload.universities
    elif payload.name:
        items = [UniversityInput(name=payload.name, province=payload.province, website=payload.website)]
    else:
        return JSONResponse(
            status_code=422,
            content={"detail": "Provide 'name' for a single university or 'universities' array for bulk."},
        )

    existing_names = await _get_existing_university_names()
    added = 0
    skipped = 0

    for item in items:
        name = item.name.strip()
        if not name:
            skipped += 1
            continue
        if name.lower() in existing_names:
            skipped += 1
            continue
        await add_university(
            name=name,
            province=item.province.strip() if item.province else None,
            website=item.website.strip() if item.website else None,
        )
        existing_names.add(name.lower())
        added += 1

    return {"added": added, "skipped": skipped}


# ---------------------------------------------------------------------------
# University import
# ---------------------------------------------------------------------------

# Column name aliases — maps various user-facing names to our internal fields.
_COLUMN_ALIASES: dict[str, str] = {
    # name
    "name": "name", "nama": "name", "nama universitas": "name",
    "nama_universitas": "name", "university": "name", "university name": "name",
    "university_name": "name", "institusi": "name", "perguruan tinggi": "name",
    # province
    "province": "province", "provinsi": "province", "prov": "province",
    # website
    "website": "website", "web": "website", "url": "website",
    "situs": "website", "situs web": "website", "laman": "website",
}


def _normalize_headers(raw_headers: list[str]) -> dict[int, str]:
    """Map column indices to internal field names using aliases.

    Returns {column_index: internal_field_name} for recognized columns.
    If no 'name' column is found, assumes the first column is 'name'.
    """
    mapping: dict[int, str] = {}
    found_name = False
    for i, h in enumerate(raw_headers):
        key = h.strip().lower()
        if key in _COLUMN_ALIASES:
            field = _COLUMN_ALIASES[key]
            if field not in mapping.values():  # first match wins
                mapping[i] = field
                if field == "name":
                    found_name = True
    # Fallback: if no name column found, treat column 0 as name
    if not found_name and raw_headers:
        mapping[0] = "name"
    return mapping


@app.post("/universities/import")
async def import_universities(file: UploadFile = FastAPIFile(...)):
    """Import universities from CSV or Excel (.xlsx) file.

    Recognizes flexible column names (e.g. 'nama', 'provinsi', 'web').
    If there's only one column or no header match, the first column is treated as university name.
    """
    import os

    content = await file.read()
    filename = file.filename or "upload.csv"
    ext = os.path.splitext(filename)[1].lower()

    rows_data: list[dict[str, str]] = []

    if ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return JSONResponse(status_code=400, content={"detail": "Excel file has no active sheet"})
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not header_row:
            return JSONResponse(status_code=400, content={"detail": "Excel file has no header row"})
        raw_headers = [str(h).strip() if h else "" for h in header_row]
        col_map = _normalize_headers(raw_headers)
        for row in ws.iter_rows(min_row=2, values_only=True):
            row_dict: dict[str, str] = {}
            for i, val in enumerate(row):
                if i in col_map and val is not None:
                    row_dict[col_map[i]] = str(val).strip()
            rows_data.append(row_dict)
        wb.close()
    else:
        # Default: CSV
        text = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        # Normalize CSV headers
        raw_headers = reader.fieldnames or []
        col_map = _normalize_headers(list(raw_headers))
        # Build reverse: original_header -> internal_field
        header_to_field = {raw_headers[i]: field for i, field in col_map.items() if i < len(raw_headers)}
        for row in reader:
            row_dict: dict[str, str] = {}
            for orig_header, field in header_to_field.items():
                val = row.get(orig_header, "")
                if val:
                    row_dict[field] = val.strip()
            rows_data.append(row_dict)

    existing_names = await _get_existing_university_names()
    imported = 0
    skipped = 0

    for row in rows_data:
        name = row.get("name", "").strip()
        if not name:
            continue
        if name.lower() in existing_names:
            skipped += 1
            continue
        await add_university(
            name=name,
            province=row.get("province", "").strip() or None,
            website=row.get("website", "").strip() or None,
        )
        existing_names.add(name.lower())
        imported += 1

    return {"imported": imported, "skipped": skipped}


# ---------------------------------------------------------------------------
# University detail endpoints
# ---------------------------------------------------------------------------

@app.get("/universities/{university_id}")
async def get_university(university_id: int):
    """Get a single university by ID."""
    uni = await get_university_by_id(university_id)
    if not uni:
        return JSONResponse(status_code=404, content={"detail": "University not found"})
    return uni


@app.delete("/universities/{university_id}/ig-handle")
async def reset_university_ig_handle(university_id: int):
    """Clear IG handle and reset status to pending so Agent 1 re-searches."""
    from orchestrator.db import reset_ig_handle
    ok = await reset_ig_handle(university_id)
    if not ok:
        return JSONResponse(status_code=404, content={"detail": "University not found"})
    log.info("[API] IG handle reset for university %d", university_id)
    return {"success": True, "id": university_id, "status": "pending"}


@app.get("/universities/{university_id}/contacts")
async def get_university_contacts(university_id: int):
    """Get IG contacts for a university."""
    return await get_contacts_for_university(university_id)


@app.patch("/contacts/{contact_id}/toggle-contacted")
async def toggle_contact_contacted(contact_id: int, contacted: bool = True):
    """Manually mark a contact as contacted or not."""
    from orchestrator.db import toggle_contact_manual_status
    result = await toggle_contact_manual_status(contact_id, contacted)
    if not result:
        return JSONResponse(status_code=404, content={"detail": "Contact not found"})
    return {"success": True, "id": contact_id, "manual_contacted": contacted}


@app.post("/contacts/bulk-match")
async def bulk_match_contacts(payload: dict):
    """Match a list of phone numbers against existing contacts."""
    phone_numbers = payload.get("phone_numbers", [])
    if not phone_numbers or not isinstance(phone_numbers, list):
        return JSONResponse(status_code=400, content={"detail": "Provide 'phone_numbers' array"})
    from orchestrator.db import bulk_match_contacts_by_phone
    result = await bulk_match_contacts_by_phone(phone_numbers)
    return result


@app.post("/contacts/bulk-update-status")
async def bulk_update_contacts_status(payload: dict):
    """Bulk update manual_contacted status for a list of contact IDs."""
    contact_ids = payload.get("contact_ids", [])
    contacted = payload.get("contacted", True)
    if not contact_ids or not isinstance(contact_ids, list):
        return JSONResponse(status_code=400, content={"detail": "Provide 'contact_ids' array"})
    from orchestrator.db import bulk_update_contact_status
    updated = await bulk_update_contact_status(contact_ids, contacted)
    return {"success": True, "updated": updated}


@app.get("/universities/{university_id}/posts")
async def get_university_posts(university_id: int):
    """Get IG posts for a university."""
    return await get_posts_for_university(university_id)


@app.get("/universities/{university_id}/related-igs")
async def get_university_related_igs(university_id: int, relation_type: str | None = None):
    """Get related IG accounts (BEM, humas, etc.) for a university."""
    from orchestrator.db import get_related_igs_for_university
    return await get_related_igs_for_university(university_id, relation_type)


# ---------------------------------------------------------------------------
# University Groups endpoints
# ---------------------------------------------------------------------------


@app.get("/university-groups")
async def list_university_groups():
    """List all university groups with university counts."""
    from orchestrator import university_groups as ug
    groups = await ug.list_groups()
    return {"success": True, "groups": groups}


@app.post("/university-groups")
async def create_university_group(request: dict):
    """Create a new university group."""
    from orchestrator import university_groups as ug
    name = request.get("name", "").strip()
    if not name:
        return JSONResponse({"detail": "name is required"}, status_code=400)
    group = await ug.create_group(name, request.get("description", ""))
    return {"success": True, "group": group}, 201


@app.get("/university-groups/{group_id}")
async def get_university_group(group_id: int):
    """Get a group with its member universities."""
    from orchestrator import university_groups as ug
    detail = await ug.get_group_detail(group_id)
    if not detail:
        return JSONResponse({"detail": "Group not found"}, status_code=404)
    return {"success": True, "group": detail}


@app.put("/university-groups/{group_id}")
async def update_university_group(group_id: int, request: dict):
    """Update a group's name and/or description."""
    from orchestrator import university_groups as ug
    name = request.get("name")
    description = request.get("description")
    group = await ug.update_group(group_id, name=name, description=description)
    if not group:
        return JSONResponse({"detail": "Group not found"}, status_code=404)
    return {"success": True, "group": group}


@app.delete("/university-groups/{group_id}")
async def delete_university_group(group_id: int):
    """Delete a group and all its members."""
    from orchestrator import university_groups as ug
    deleted = await ug.delete_group(group_id)
    if not deleted:
        return JSONResponse({"detail": "Group not found"}, status_code=404)
    return {"success": True, "message": "Group deleted"}


@app.post("/university-groups/{group_id}/universities/add")
async def group_add_universities(group_id: int, request: dict):
    """Add universities to a group."""
    from orchestrator import university_groups as ug
    university_ids = request.get("university_ids", [])
    if not isinstance(university_ids, list) or not university_ids:
        return JSONResponse({"detail": "university_ids must be a non-empty list"}, status_code=400)
    added = await ug.add_universities_to_group(group_id, university_ids)
    return {"success": True, "added": added}


@app.post("/university-groups/{group_id}/universities/remove")
async def group_remove_universities(group_id: int, request: dict):
    """Remove universities from a group."""
    from orchestrator import university_groups as ug
    university_ids = request.get("university_ids", [])
    if not isinstance(university_ids, list) or not university_ids:
        return JSONResponse({"detail": "university_ids must be a non-empty list"}, status_code=400)
    removed = await ug.remove_universities_from_group(group_id, university_ids)
    return {"success": True, "removed": removed}


@app.get("/university-groups/{group_id}/university-ids")
async def get_group_university_ids(group_id: int):
    """Get just the university IDs for a group (lightweight)."""
    from orchestrator import university_groups as ug
    ids = await ug.get_group_university_ids(group_id)
    return {"success": True, "university_ids": ids}


# ---------------------------------------------------------------------------
# Marketing endpoints
# ---------------------------------------------------------------------------

from orchestrator.marketing import router as marketing_router

app.include_router(marketing_router, prefix="/marketing", tags=["marketing"])


# ---------------------------------------------------------------------------
# Conversations endpoints
# ---------------------------------------------------------------------------

@app.get("/conversations")
async def list_conversations(
    state: str | None = None,
    university_id: int | None = None,
    is_test: bool | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List conversations with optional filters."""
    return await get_conversations_filtered(state, university_id, is_test, limit, offset)


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int):
    """Get a single conversation by ID."""
    from orchestrator.db import get_audiensi_by_source_conversation_id
    conv = await get_conversation_by_id(conversation_id)
    if not conv:
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})
    conv["linked_audiensi"] = await get_audiensi_by_source_conversation_id(conversation_id)
    return conv


class TestConversationPayload(BaseModel):
    phone: str
    university_name: str = "Universitas Test"
    force: bool = False


@app.post("/conversations/test")
async def start_test_conversation(payload: TestConversationPayload):
    """Start a test conversation for internal roleplay testing.

    Creates a real conversation record so incoming webhook replies
    are processed through the normal AI pipeline.
    """
    phone = validate_phone(payload.phone)
    if not phone:
        return JSONResponse(
            status_code=422,
            content={"detail": f"Invalid phone number: {payload.phone}"},
        )

    # Check for existing active conversation on this phone
    existing = await get_conversation_by_phone(phone)
    if existing and existing["state"] not in _TERMINAL_STATES:
        if payload.force:
            # Abandon the old conversation so we can start fresh
            await update_conversation_state(existing["id"], ConvState.ABANDONED)
            log.info("Force-abandoned existing conversation %d for test", existing["id"])
        else:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": f"Active conversation already exists for {phone}",
                    "existing_id": existing["id"],
                    "existing_state": existing["state"],
                },
            )

    # Also abandon any active audiensi conversation for this phone,
    # otherwise incoming replies get routed to audiensi instead of the test.
    from orchestrator.audiensi.states import AudiensiState
    existing_aud = await get_audiensi_conversation_by_phone(phone)
    if existing_aud and existing_aud["state"] not in AudiensiState.terminal_states():
        if payload.force:
            await update_audiensi_state(existing_aud["id"], "REFUSED")
            log.info("Force-abandoned existing audiensi %d for test", existing_aud["id"])
        else:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": f"Active audiensi conversation exists for {phone}",
                    "existing_audiensi_id": existing_aud["id"],
                    "existing_state": existing_aud["state"],
                },
            )

    # Generate initial message
    try:
        message = await conversation_manager.generate_initial_message(
            university_name=payload.university_name
        )
    except Exception as e:
        log.error("Failed to generate test initial message: %s", e)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to generate message: {e}"},
        )

    # Create conversation with is_test=True, university_id=None
    from datetime import datetime as _dt, timezone as _tz

    conv_id = await create_conversation(None, phone, is_test=True)

    # Enqueue via message queue
    await message_queue.enqueue_send(phone, message)

    # Update state and record message
    await update_conversation_state(
        conv_id,
        ConvState.INITIAL_SENT,
        last_message_at=_dt.now(_tz.utc).isoformat(),
    )
    await add_message_to_history(conv_id, "bot", message)

    log.info("Test conversation %d started for %s (%s)", conv_id, phone, payload.university_name)

    return {
        "id": conv_id,
        "phone": phone,
        "message": message,
        "state": ConvState.INITIAL_SENT,
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/export/csv")
async def export_csv():
    """Export all universities with contacts as CSV."""
    universities = await get_all_universities(limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "province", "website", "ig_handle", "status", "secretariat_phone", "created_at"])

    for uni in universities:
        writer.writerow([
            uni["id"], uni["name"], uni.get("province", ""),
            uni.get("website", ""), uni.get("ig_handle", ""),
            uni["status"], uni.get("secretariat_phone", ""),
            uni.get("created_at", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=universities_export.csv"},
    )


# ---------------------------------------------------------------------------
# Pipeline triggers (manual) — 3 independent agents
# ---------------------------------------------------------------------------

async def _run_agent_with_log(agent_fn, agent_type: str, trigger_type: str, limit: int):
    """Wrapper that creates a pipeline log, runs the agent, and records results."""
    log_id = await create_pipeline_log(agent_type, trigger_type)
    try:
        result = await agent_fn(limit)
        # Determine counts from agent result dict
        processed = 0
        success = 0
        failed = 0
        details = result.get("details", [])

        if agent_type == "find_handles":
            processed = result.get("searched", 0)
            success = result.get("found", 0)
            failed = processed - success
        elif agent_type == "scrape_posts":
            processed = result.get("scraped", 0)
            success = result.get("total_posts", 0)
            failed = 0
        elif agent_type == "extract_phones":
            processed = result.get("processed", 0)
            success = result.get("phones_found", 0)
            failed = 0

        summary = {k: v for k, v in result.items() if k != "details"}
        await complete_pipeline_log(
            log_id,
            status="completed",
            summary=summary,
            details=details[:100],
            items_processed=processed,
            items_success=success,
            items_failed=failed,
        )
        # Broadcast agent completion to frontend
        await ws_manager.broadcast_type(
            "agent_completed",
            agent=agent_type,
            stats={"processed": processed, "success": success, "failed": failed},
        )
        return result
    except Exception as e:
        log.error(f"[{agent_type}] Agent failed: {e}")
        await complete_pipeline_log(log_id, status="failed", error=str(e))
        # Broadcast agent failure to frontend
        await ws_manager.broadcast_type(
            "agent_completed",
            agent=agent_type,
            stats={"error": str(e)},
        )
        raise


@app.post("/pipeline/find-ig-handles")
async def trigger_find_ig_handles(background_tasks: BackgroundTasks, limit: int = 50):
    """Agent 1: Search IG handles for universities in 'pending' status."""
    background_tasks.add_task(
        run_agent_in_thread, _run_agent_with_log,
        run_handle_search_batch, "find_handles", "manual", limit,
    )
    return {"status": "started", "message": f"Agent 1: searching IG handles for up to {limit} universities"}


@app.post("/pipeline/scrape-ig-posts")
async def trigger_scrape_ig_posts(background_tasks: BackgroundTasks, limit: int = 20):
    """Agent 2: Scrape IG posts for universities in 'ig_found' status."""
    background_tasks.add_task(
        run_agent_in_thread, _run_agent_with_log,
        run_post_scrape_batch, "scrape_posts", "manual", limit,
    )
    return {"status": "started", "message": f"Agent 2: scraping posts for up to {limit} universities"}


@app.post("/pipeline/extract-phones")
async def trigger_extract_phones(background_tasks: BackgroundTasks, limit: int = 50):
    """Agent 3: Extract phones from unprocessed ig_posts."""
    background_tasks.add_task(
        run_agent_in_thread, _run_agent_with_log,
        run_phone_extraction_batch, "extract_phones", "manual", limit,
    )
    return {"status": "started", "message": f"Agent 3: extracting phones from up to {limit} posts"}


@app.post("/pipeline/discover-bem")
async def trigger_discover_bem(background_tasks: BackgroundTasks, limit: int = 30):
    """Agent 4: Discover BEM handles and scan their following lists."""
    background_tasks.add_task(
        run_agent_in_thread, _run_agent_with_log,
        run_bem_discovery_batch, "discover_bem", "manual", limit,
    )
    return {"status": "started", "message": f"Agent 4: discovering BEM for up to {limit} universities"}


@app.post("/pipeline/find-rectors")
async def trigger_find_rectors(background_tasks: BackgroundTasks, limit: int = 20):
    """Agent 5: Find rector names for universities using web search and GPT."""
    background_tasks.add_task(
        run_agent_in_thread, _run_agent_with_log,
        run_rector_finder_batch, "find_rectors", "manual", limit,
    )
    return {"status": "started", "message": f"Agent 5: finding rector names for up to {limit} universities"}


# ---------------------------------------------------------------------------
# Targeted agent triggers (per-university / bulk)
# ---------------------------------------------------------------------------

_TARGETED_AGENT_MAP = {
    "find_handles": run_handle_search_for_universities,
    "scrape_posts": run_post_scrape_for_universities,
    "extract_phones": run_phone_extraction_for_universities,
    "discover_bem": run_bem_discovery_for_universities,
}


async def _run_targeted_agent_with_log(agent_fn, agent_type: str, university_ids: list[int]):
    """Wrapper that creates a pipeline log, runs targeted agent, and records results."""
    log_id = await create_pipeline_log(agent_type, "manual")
    try:
        result = await agent_fn(university_ids)
        processed = 0
        success = 0
        failed = 0
        details = result.get("details", [])

        if agent_type == "find_handles":
            processed = result.get("searched", 0)
            success = result.get("found", 0)
            failed = processed - success
        elif agent_type == "scrape_posts":
            processed = result.get("scraped", 0)
            success = result.get("total_posts", 0)
        elif agent_type == "extract_phones":
            processed = result.get("processed", 0)
            success = result.get("phones_found", 0)
        elif agent_type == "discover_bem":
            processed = result.get("searched", 0)
            success = result.get("found", 0)
            failed = processed - success

        summary = {k: v for k, v in result.items() if k != "details"}
        summary["targeted_university_ids"] = university_ids
        await complete_pipeline_log(
            log_id,
            status="completed",
            summary=summary,
            details=details[:100],
            items_processed=processed,
            items_success=success,
            items_failed=failed,
        )
        # Broadcast agent completion to frontend
        await ws_manager.broadcast_type(
            "agent_completed",
            agent=agent_type,
            stats={"processed": processed, "success": success, "failed": failed, "targeted": len(university_ids)},
        )
        return result
    except Exception as e:
        log.error(f"[{agent_type}] Targeted agent failed: {e}")
        await complete_pipeline_log(log_id, status="failed", error=str(e))
        # Broadcast agent failure to frontend
        await ws_manager.broadcast_type(
            "agent_completed",
            agent=agent_type,
            stats={"error": str(e)},
        )
        raise


@app.post("/pipeline/run-agent-targeted")
async def trigger_targeted_agent(
    background_tasks: BackgroundTasks,
    body: dict,
):
    """Run a pipeline agent on specific universities.

    Body: {"agent_type": "find_handles"|"scrape_posts"|"extract_phones", "university_ids": [1,2,3]}
    """
    agent_type = body.get("agent_type")
    university_ids = body.get("university_ids", [])

    if agent_type not in _TARGETED_AGENT_MAP:
        return JSONResponse(
            {"error": f"Invalid agent_type. Must be one of: {list(_TARGETED_AGENT_MAP.keys())}"},
            status_code=400,
        )
    if not university_ids or not isinstance(university_ids, list):
        return JSONResponse(
            {"error": "university_ids must be a non-empty list of integers"},
            status_code=400,
        )

    agent_fn = _TARGETED_AGENT_MAP[agent_type]
    background_tasks.add_task(
        run_agent_in_thread,
        _run_targeted_agent_with_log,
        agent_fn, agent_type, university_ids,
    )

    agent_labels = {
        "find_handles": "Find IG Handles",
        "scrape_posts": "Scrape IG Posts",
        "extract_phones": "Extract Phones",
        "discover_bem": "Discover BEM",
    }
    return {
        "status": "started",
        "message": f"{agent_labels[agent_type]}: processing {len(university_ids)} universities",
    }


@app.get("/pipeline/status")
async def pipeline_status():
    """Return a breakdown of all pipeline stages."""
    return await get_pipeline_status()


@app.get("/pipeline/logs")
async def get_pipeline_logs_endpoint(
    agent_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return paginated pipeline activity logs."""
    return await get_pipeline_logs(
        agent_type=agent_type, status=status, limit=limit, offset=offset
    )


@app.get("/pipeline/logs/{log_id}")
async def get_pipeline_log_detail(log_id: int):
    """Return a single pipeline log entry with full details."""
    entry = await get_pipeline_log_by_id(log_id)
    if not entry:
        return JSONResponse({"error": "Log not found"}, status_code=404)
    return entry


# ---------------------------------------------------------------------------
# Outreach triggers (manual)
# ---------------------------------------------------------------------------

@app.post("/outreach/start")
async def trigger_outreach(background_tasks: BackgroundTasks):
    """Manually trigger the outreach loop."""
    background_tasks.add_task(daily_outreach_loop)
    return {"status": "started", "message": "Outreach loop triggered"}


@app.post("/outreach/process-followups")
async def trigger_followups(background_tasks: BackgroundTasks):
    """Manually trigger follow-up processing."""
    background_tasks.add_task(process_followups)
    return {"status": "started", "message": "Follow-up processing triggered"}


# ---------------------------------------------------------------------------
# Pause / Resume control
# ---------------------------------------------------------------------------

@app.post("/control/pause")
async def pause_bot():
    """Pause automated outreach and auto-replies."""
    set_paused(True)
    await upsert_config("BOT_PAUSED", "true")
    log.info("Bot PAUSED by operator")
    return {"paused": True}


@app.post("/control/resume")
async def resume_bot():
    """Resume automated outreach and auto-replies."""
    set_paused(False)
    await upsert_config("BOT_PAUSED", "false")
    log.info("Bot RESUMED by operator")
    return {"paused": False}


@app.get("/control/status")
async def control_status():
    """Return current pause state and chatbot toggles."""
    return {
        "paused": is_paused(),
        "chatbot_enabled": cfg.CHATBOT_ENABLED,
        "audiensi_enabled": cfg.AUDIENSI_ENABLED,
        "research_multi_agent": cfg.get("RESEARCH_USE_MULTI_AGENT", False),
    }


class ChatbotTogglePayload(BaseModel):
    enabled: bool


@app.post("/control/chatbot/{chatbot_type}")
async def toggle_chatbot(chatbot_type: str, payload: ChatbotTogglePayload):
    """Toggle a chatbot on/off. Type: 'agent' or 'audiensi'."""
    if chatbot_type == "agent":
        cfg.set("CHATBOT_ENABLED", payload.enabled)
        db_val = "true" if payload.enabled else "false"
        await upsert_config("CHATBOT_ENABLED", db_val)
        log.info("Contact finder chatbot %s", "ENABLED" if payload.enabled else "DISABLED")
        return {"chatbot_enabled": payload.enabled}
    elif chatbot_type == "audiensi":
        cfg.set("AUDIENSI_ENABLED", payload.enabled)
        db_val = "true" if payload.enabled else "false"
        await upsert_config("AUDIENSI_ENABLED", db_val)
        log.info("Audiensi chatbot %s", "ENABLED" if payload.enabled else "DISABLED")
        return {"audiensi_enabled": payload.enabled}
    elif chatbot_type == "research_multi_agent":
        cfg.set("RESEARCH_USE_MULTI_AGENT", payload.enabled)
        db_val = "true" if payload.enabled else "false"
        await upsert_config("RESEARCH_USE_MULTI_AGENT", db_val)
        log.info("Research multi-agent pipeline %s", "ENABLED" if payload.enabled else "DISABLED")
        return {"research_multi_agent": payload.enabled}
    else:
        return JSONResponse(
            status_code=422,
            content={"detail": "chatbot_type must be 'agent' or 'audiensi'"},
        )


# ---------------------------------------------------------------------------
# Learning endpoints
# ---------------------------------------------------------------------------

@app.get("/learning/lessons")
async def list_lessons():
    """Return all active lessons."""
    lessons = await get_all_active_lessons()
    return {"lessons": lessons, "total": len(lessons)}


@app.get("/learning/analyses")
async def list_analyses(limit: int = 50):
    """Return unprocessed analyses."""
    analyses = await get_unprocessed_analyses(limit=limit)
    return {"analyses": analyses, "total": len(analyses)}


@app.get("/learning/stats")
async def learning_stats():
    """Return summary statistics for the learning system."""
    lessons = await get_all_active_lessons()
    analyses = await get_unprocessed_analyses(limit=1000)

    # Count lessons by situation_type
    situation_counts: dict[str, int] = {}
    for lesson in lessons:
        sit = lesson.get("situation_type", "unknown")
        situation_counts[sit] = situation_counts.get(sit, 0) + 1

    return {
        "total_active_lessons": len(lessons),
        "unprocessed_analyses": len(analyses),
        "lessons_by_situation": situation_counts,
    }


@app.post("/learning/trigger-reflection")
async def trigger_reflection(background_tasks: BackgroundTasks):
    """Trigger a reflection cycle in the background."""
    background_tasks.add_task(learning_system.run_reflection)
    return {"status": "started", "message": "Reflection triggered"}


# ---------------------------------------------------------------------------
# WhatsApp management endpoints (proxy to WA service)
# ---------------------------------------------------------------------------

class TestMessagePayload(BaseModel):
    to: str
    message: str


@app.get("/wa/qr")
async def wa_qr():
    """Get current QR code for WhatsApp authentication."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WA_SERVICE_URL}/qr")
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"WA service unavailable: {e}", "connected": False},
        )


@app.get("/wa/status")
async def wa_status():
    """Get detailed WhatsApp connection status."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WA_SERVICE_URL}/status")
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"WA service unavailable: {e}", "connected": False},
        )


@app.post("/wa/send-test")
async def wa_send_test(payload: TestMessagePayload):
    """Send a test WhatsApp message."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{WA_SERVICE_URL}/send",
                json={"to": payload.to, "message": payload.message},
            )
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"WA service unavailable: {e}"},
        )


@app.post("/wa/logout")
async def wa_logout():
    """Logout from WhatsApp and clear auth session."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{WA_SERVICE_URL}/logout")
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"WA service unavailable: {e}"},
        )


@app.post("/wa/restart")
async def wa_restart():
    """Restart WhatsApp connection."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{WA_SERVICE_URL}/restart")
            return resp.json()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"WA service unavailable: {e}"},
        )


# ---------------------------------------------------------------------------
# Bulk Send Endpoints (Multi-Device Support)
# ---------------------------------------------------------------------------


@app.get("/wa/devices")
async def wa_get_devices():
    """Proxy to WhatsApp service to get all devices with status."""
    from orchestrator.config import WA_SERVICE_URL
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{WA_SERVICE_URL}/devices")
        return response.json()


@app.get("/wa/devices/{device_id}/qr")
async def wa_get_device_qr(device_id: str):
    """Proxy to WhatsApp service to get QR code for a device."""
    from orchestrator.config import WA_SERVICE_URL
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{WA_SERVICE_URL}/devices/{device_id}/qr")
        return response.json()


@app.post("/wa/devices/{device_id}/connect")
async def wa_connect_device(device_id: str):
    """Proxy to WhatsApp service to connect a device (triggers QR generation)."""
    from orchestrator.config import WA_SERVICE_URL
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{WA_SERVICE_URL}/devices/{device_id}/connect")
        return response.json()


@app.post("/wa/devices/{device_id}/disconnect")
async def wa_disconnect_device(device_id: str):
    """Proxy to WhatsApp service to disconnect a device."""
    from orchestrator.config import WA_SERVICE_URL
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{WA_SERVICE_URL}/devices/{device_id}/disconnect")
        return response.json()


@app.post("/wa/devices/{device_id}/recover")
async def wa_recover_device(device_id: str):
    """Proxy to WhatsApp service to force a clean auth recovery for a device."""
    from orchestrator.config import WA_SERVICE_URL
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{WA_SERVICE_URL}/devices/{device_id}/recover")
        return response.json()


@app.get("/wa/devices/{device_id}/antiban")
async def wa_get_device_antiban(device_id: str):
    """Proxy to WhatsApp service to get anti-ban status for a device."""
    from orchestrator.config import WA_SERVICE_URL
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{WA_SERVICE_URL}/devices/{device_id}/antiban")
        return response.json()


@app.post("/wa/devices/{device_id}/antiban/pause")
async def wa_pause_device_antiban(device_id: str):
    """Proxy to WhatsApp service to pause outbound sends for a device."""
    from orchestrator.config import WA_SERVICE_URL
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{WA_SERVICE_URL}/devices/{device_id}/antiban/pause")
        return response.json()


@app.post("/wa/devices/{device_id}/antiban/resume")
async def wa_resume_device_antiban(device_id: str):
    """Proxy to WhatsApp service to resume outbound sends for a device."""
    from orchestrator.config import WA_SERVICE_URL
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{WA_SERVICE_URL}/devices/{device_id}/antiban/resume")
        return response.json()


@app.post("/wa/devices/{device_id}/antiban/reset")
async def wa_reset_device_antiban(device_id: str):
    """Proxy to WhatsApp service to reset anti-ban state for a device."""
    from orchestrator.config import WA_SERVICE_URL
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{WA_SERVICE_URL}/devices/{device_id}/antiban/reset")
        return response.json()


@app.post("/wa/bulk-send")
async def wa_bulk_send(payload: dict):
    """
    Bulk send WhatsApp text messages to multiple phone numbers.

    Body: {
      phone_numbers: ["628xxx", ...],
      message: "Hello!",
      device_id: "device_1"  # Optional, defaults to "device_1"
    }
    """
    try:
        phone_numbers = payload.get("phone_numbers", [])
        message = payload.get("message", "")
        device_id = payload.get("device_id", "device_1")

        if not phone_numbers:
            return {"success": False, "error": "No phone numbers provided"}
        if not message:
            return {"success": False, "error": "No message provided"}

        for phone in phone_numbers:
            await message_queue.enqueue_send(phone, message, device_id=device_id)

        return {
            "success": True,
            "queued": len(phone_numbers),
            "device_id": device_id,
        }
    except Exception as e:
        log.error("Bulk send failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Bulk send failed: {e}"},
        )


@app.post("/wa/bulk-send-document")
async def wa_bulk_send_document(payload: dict):
    """
    Bulk send WhatsApp document messages to multiple phone numbers.

    Body: {
      phone_numbers: ["628xxx", ...],
      file_path: "/path/to/file.pdf",
      file_name: "document.pdf",
      caption: "Optional caption",
      device_id: "device_1"  # Optional, defaults to "device_1"
    }
    """
    try:
        phone_numbers = payload.get("phone_numbers", [])
        file_path = payload.get("file_path", "")
        file_name = payload.get("file_name", "")
        caption = payload.get("caption")
        device_id = payload.get("device_id", "device_1")

        if not phone_numbers:
            return {"success": False, "error": "No phone numbers provided"}
        if not file_path:
            return {"success": False, "error": "No file_path provided"}
        if not file_name:
            return {"success": False, "error": "No file_name provided"}

        for phone in phone_numbers:
            await message_queue.enqueue_send_document(
                phone, file_path, file_name, caption, device_id=device_id
            )

        return {
            "success": True,
            "queued": len(phone_numbers),
            "device_id": device_id,
            "file_name": file_name,
        }
    except Exception as e:
        log.error("Bulk send document failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Bulk send document failed: {e}"},
        )


@app.get("/wa/devices")
async def wa_get_devices():
    """Get all WhatsApp devices and their status."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{WA_SERVICE_URL}/devices")
            return resp.json()
    except Exception as e:
        log.error("Failed to get devices: %s", e)
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"Failed to get devices: {e}"},
        )


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------


_CHAT_MODEL_EXCLUDE = {"audio", "realtime", "tts", "transcribe", "image", "instruct", "search", "diarize", "codex", "deep-research"}
_GEMINI_EXCLUDE = {"image", "audio", "tts", "native-audio", "embedding", "robotics", "live", "transcribe", "computer-use"}


async def _list_openai_models() -> list[str]:
    from openai import AsyncOpenAI
    api_key = cfg.OPENAI_API_KEY
    if not api_key:
        return []
    client = AsyncOpenAI(api_key=api_key)
    response = await client.models.list()
    models: list[str] = []
    for m in response.data:
        mid = m.id
        if not (mid.startswith("gpt-") or mid.startswith("o1") or mid.startswith("o3") or mid.startswith("o4")):
            continue
        if mid.startswith("ft:"):
            continue
        if any(excl in mid for excl in _CHAT_MODEL_EXCLUDE):
            continue
        models.append(mid)
    models.sort()
    return models


async def _list_gemini_models() -> list[str]:
    gemini_key = str(cfg.get("GEMINI_API_KEY", "") or "")
    if not gemini_key:
        return []
    from google import genai as _genai
    client = _genai.Client(api_key=gemini_key)
    models: list[str] = []
    for m in client.models.list():
        name = m.name  # e.g. "models/gemini-2.5-pro"
        if name.startswith("models/"):
            name = name[len("models/"):]
        if not name.startswith("gemini-"):
            continue
        if any(excl in name for excl in _GEMINI_EXCLUDE):
            continue
        models.append(name)
    models.sort()
    return models


@app.get("/config/models")
async def list_models(provider: str = "openai"):
    """Fetch chat-capable models from OpenAI, Gemini, or both.

    provider: "openai" | "gemini" | "all"
    """
    import asyncio
    errors: list[str] = []
    openai_models: list[str] = []
    gemini_models: list[str] = []

    if provider in ("openai", "all"):
        try:
            openai_models = await _list_openai_models()
        except Exception as e:
            log.warning("Failed to list OpenAI models: %s", e)
            errors.append(str(e))

    if provider in ("gemini", "all"):
        try:
            gemini_models = await _list_gemini_models()
        except Exception as e:
            log.warning("Failed to list Gemini models: %s", e)
            errors.append(str(e))

    if provider == "gemini":
        models = gemini_models
    elif provider == "all":
        # Gemini first (preferred for orchestrator), then OpenAI
        models = gemini_models + openai_models
    else:
        models = openai_models

    result: dict = {"models": models}
    if errors:
        result["error"] = "; ".join(errors)
    return result


def _mask_value(value: str) -> str:
    """Mask a sensitive string — short fixed-width prefix + last 4 chars."""
    s = str(value)
    if not s:
        return ""
    if len(s) <= 8:
        return "\u2022" * len(s)
    return "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022" + s[-4:]


@app.get("/config")
async def get_config():
    """Return all dynamic settings with metadata."""
    current = cfg.get_all()
    settings = []
    for defn in CONFIG_DEFINITIONS:
        raw_value = current.get(defn.key, defn.default)
        display_value = _mask_value(raw_value) if defn.sensitive and raw_value else raw_value
        settings.append({
            "key": defn.key,
            "value": display_value,
            "default": "" if defn.sensitive else defn.default,
            "type": defn.type.value,
            "group": defn.group.value,
            "label": defn.label,
            "description": defn.description,
            "min_value": defn.min_value,
            "max_value": defn.max_value,
            "sensitive": defn.sensitive,
            "has_value": bool(raw_value) if defn.sensitive else None,
            "choices": defn.choices,
            "model_picker": defn.model_picker,
        })
    return {"settings": settings}


class ConfigUpdatePayload(BaseModel):
    settings: dict[str, Any]


def _validate_config_value(key: str, value: Any) -> tuple[Any, str | None]:
    """Validate and coerce a config value. Returns (coerced_value, error_or_None)."""
    defn = CONFIG_DEFINITIONS_MAP.get(key)
    if defn is None:
        return None, f"Unknown config key: {key}"

    try:
        if defn.type == ConfigType.INT:
            coerced = int(value)
        elif defn.type == ConfigType.FLOAT:
            coerced = float(value)
        elif defn.type == ConfigType.BOOL:
            if isinstance(value, bool):
                coerced = value
            elif isinstance(value, str):
                coerced = value.lower() in ("true", "1", "yes")
            else:
                coerced = bool(value)
        else:
            coerced = str(value)
    except (ValueError, TypeError):
        return None, f"Invalid type for {key}: expected {defn.type.value}"

    if defn.min_value is not None and isinstance(coerced, (int, float)):
        if coerced < defn.min_value:
            return None, f"{key} must be >= {defn.min_value}"
    if defn.max_value is not None and isinstance(coerced, (int, float)):
        if coerced > defn.max_value:
            return None, f"{key} must be <= {defn.max_value}"

    return coerced, None


@app.patch("/config")
async def update_config(payload: ConfigUpdatePayload):
    """Update one or more config settings. Validates, persists to DB, and updates in-memory.
    Keys marked ``env_only=True`` are rejected (403) — those must be set via environment variables.
    """
    # Reject any env_only key upfront
    env_only_keys = [
        key for key in payload.settings
        if (defn := CONFIG_DEFINITIONS_MAP.get(key)) and defn.env_only
    ]
    if env_only_keys:
        return JSONResponse(
            status_code=403,
            content={
                "detail": "These config keys are read-only and must be set via environment variables.",
                "keys": env_only_keys,
            },
        )

    errors: dict[str, str] = {}
    validated: dict[str, Any] = {}

    for key, value in payload.settings.items():
        coerced, err = _validate_config_value(key, value)
        if err:
            errors[key] = err
        else:
            validated[key] = coerced

    if errors:
        return JSONResponse(status_code=422, content={"errors": errors})

    for key, coerced in validated.items():
        # Persist to DB as string
        if isinstance(coerced, bool):
            db_value = "true" if coerced else "false"
        else:
            db_value = str(coerced)
        await upsert_config(key, db_value)
        cfg.set(key, coerced)

    # Reschedule outreach jobs if hours changed
    if "OUTREACH_START_HOUR" in validated or "OUTREACH_END_HOUR" in validated:
        try:
            from orchestrator.scheduler import reschedule_outreach_jobs
            reschedule_outreach_jobs()
        except Exception as e:
            log.warning("Failed to reschedule outreach jobs: %s", e)

    # Invalidate Responses API sessions if custom instructions changed
    instruction_keys = {"AGENT_CUSTOM_INSTRUCTIONS", "AUDIENSI_CUSTOM_INSTRUCTIONS"}
    if instruction_keys & set(validated.keys()):
        await clear_all_response_ids("conversations")
        await clear_all_response_ids("audiensi_conversations")

    return {"status": "ok", "updated": list(validated.keys())}


@app.get("/config/{key}")
async def get_config_key(key: str):
    """Get a single config value by key."""
    value = cfg.get(key)
    if value is None:
        return JSONResponse(status_code=404, content={"detail": f"Config key '{key}' not found"})
    return {"key": key, "value": value}


@app.delete("/config/{key}")
async def reset_config(key: str):
    """Reset a config key to its default value. Env-only keys are rejected."""
    defn = CONFIG_DEFINITIONS_MAP.get(key)
    if defn is None:
        return JSONResponse(status_code=404, content={"detail": f"Unknown config key: {key}"})
    if defn.env_only:
        return JSONResponse(
            status_code=403,
            content={
                "detail": f"Config key '{key}' is read-only and must be set via environment variables.",
            },
        )

    await db_delete_config(key)
    cfg.set(key, defn.default)

    return {"status": "ok", "key": key, "value": defn.default}


# ---------------------------------------------------------------------------
# IG Accounts CRUD  (for Playwright multi-account rotation)
# ---------------------------------------------------------------------------


class IGAccountPayload(BaseModel):
    username: str
    password: str
    notes: str = ""


class IGAccountUpdatePayload(BaseModel):
    username: str | None = None
    password: str | None = None
    enabled: bool | None = None
    notes: str | None = None


def _mask_password(pw: str) -> str:
    if not pw:
        return ""
    if len(pw) <= 4:
        return "\u2022" * len(pw)
    return "\u2022" * (len(pw) - 2) + pw[-2:]


def _sanitize_smtp_account(account: dict[str, Any], *, mask_password: bool = True) -> dict[str, Any]:
    sanitized = {
        "id": int(account.get("id", 0)),
        "host": str(account.get("host") or "mail.asosiasi.ai").strip(),
        "port": int(account.get("port") or 465),
        "user": str(account.get("user") or "").strip().lower(),
        "password": str(account.get("password") or ""),
        "use_ssl": bool(account.get("use_ssl", True)),
        "from_name": str(account.get("from_name") or "Sekretariat Asosiasi AI").strip() or "Sekretariat Asosiasi AI",
        "enabled": bool(account.get("enabled", True)),
        "notes": str(account.get("notes") or "").strip(),
        "health_status": _normalize_smtp_health_status(account.get("health_status")),
        "health_message": str(account.get("health_message") or "").strip(),
        "last_checked_at": account.get("last_checked_at"),
        "last_healthy_at": account.get("last_healthy_at"),
        "last_error_at": account.get("last_error_at"),
        "created_at": account.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "updated_at": account.get("updated_at") or datetime.now(timezone.utc).isoformat(),
    }
    if mask_password:
        sanitized["password"] = _mask_password(sanitized["password"])
    return sanitized


def _validate_smtp_account_payload(payload: dict[str, Any], *, partial: bool = False) -> tuple[dict[str, Any], str | None]:
    validated: dict[str, Any] = {}

    if not partial or "host" in payload:
        host = str(payload.get("host") or "").strip()
        if not host:
            return {}, "SMTP host is required"
        validated["host"] = host

    if not partial or "user" in payload:
        user = str(payload.get("user") or "").strip().lower()
        if not user:
            return {}, "SMTP username/email is required"
        validated["user"] = user

    if not partial or "password" in payload:
        password = str(payload.get("password") or "")
        if not partial and not password:
            return {}, "SMTP password is required"
        if password:
            validated["password"] = password

    if not partial or "port" in payload:
        try:
            port = int(payload.get("port") or 0)
        except (TypeError, ValueError):
            return {}, "SMTP port must be a number"
        if port <= 0 or port > 65535:
            return {}, "SMTP port must be between 1 and 65535"
        validated["port"] = port

    if "use_ssl" in payload or not partial:
        validated["use_ssl"] = bool(payload.get("use_ssl", True))

    if "enabled" in payload or not partial:
        validated["enabled"] = bool(payload.get("enabled", True))

    if "from_name" in payload or not partial:
        validated["from_name"] = str(payload.get("from_name") or "Sekretariat Asosiasi AI").strip() or "Sekretariat Asosiasi AI"

    if "notes" in payload or not partial:
        validated["notes"] = str(payload.get("notes") or "").strip()

    return validated, None


async def _get_managed_smtp_accounts() -> list[dict[str, Any]]:
    raw = cfg.get("SMTP_ACCOUNTS", "") or ""
    if not str(raw).strip():
        return []

    try:
        accounts = _json.loads(raw)
    except Exception as exc:
        log.error("Failed to parse managed SMTP accounts JSON: %s", exc)
        return []

    if not isinstance(accounts, list):
        return []

    return [_sanitize_smtp_account(account, mask_password=False) for account in accounts if isinstance(account, dict)]


def _get_runtime_smtp_status_map() -> dict[str, dict[str, Any]]:
    try:
        status = email_blast.get_smtp_client().get_status()
    except Exception as exc:
        log.warning("Failed to read runtime SMTP status: %s", exc)
        return {}

    result: dict[str, dict[str, Any]] = {}
    for account in status.get("accounts", []):
        user = str(account.get("user") or "").strip().lower()
        if user:
            result[user] = account
    return result


async def _save_managed_smtp_accounts(accounts: list[dict[str, Any]], *, reset_client: bool = True) -> None:
    serialized = _json.dumps(accounts)
    await upsert_config("SMTP_ACCOUNTS", serialized)
    cfg.set("SMTP_ACCOUNTS", serialized)
    if reset_client:
        email_blast.reset_smtp_client()


async def _sync_managed_smtp_accounts_from_storage() -> None:
    rows = await get_all_config()
    raw_accounts = rows.get("SMTP_ACCOUNTS", "")
    if raw_accounts:
        cfg.set("SMTP_ACCOUNTS", raw_accounts)
    email_blast.reset_smtp_client()


class SMTPAccountPayload(BaseModel):
    host: str
    port: int = 465
    user: str
    password: str
    use_ssl: bool = True
    from_name: str = "Sekretariat Asosiasi AI"
    enabled: bool = True
    notes: str = ""


class SMTPAccountUpdatePayload(BaseModel):
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    use_ssl: bool | None = None
    from_name: str | None = None
    enabled: bool | None = None
    notes: str | None = None


@app.get("/email-smtp-accounts")
async def list_email_smtp_accounts(request: Request):
    """Return FE-managed SMTP accounts for rotation (passwords masked)."""
    await require_permission(request, "settings.manage")
    accounts = await _get_managed_smtp_accounts()
    runtime_map = _get_runtime_smtp_status_map()
    merged_accounts: list[dict[str, Any]] = []

    for account in accounts:
        sanitized = _sanitize_smtp_account(account, mask_password=True)
        runtime = runtime_map.get(str(sanitized.get("user") or "").strip().lower(), {})
        cooldown_remaining = float(runtime.get("cooldown_remaining_seconds") or 0)
        merged_accounts.append({
            **sanitized,
            "is_current": bool(runtime.get("is_current", False)),
            "connected": bool(runtime.get("connected", False)),
            "email_count": int(runtime.get("email_count", 0) or 0),
            "daily_sent_count": int(runtime.get("daily_sent_count", 0) or 0),
            "daily_limit": runtime.get("daily_limit"),
            "cooldown_remaining_seconds": cooldown_remaining,
            "skip_reason": runtime.get("skip_reason") or ("disabled" if not sanitized.get("enabled", True) else None),
        })

    return {"accounts": merged_accounts}


@app.post("/email-smtp-accounts/check-all")
async def check_all_email_smtp_accounts(request: Request):
    """Run an immediate health check for all enabled managed SMTP accounts."""
    await require_permission(request, "settings.manage")
    summary = await _run_managed_smtp_health_checks()
    return {"success": True, **summary}


@app.post("/email-smtp-accounts")
async def create_email_smtp_account(payload: SMTPAccountPayload, request: Request):
    """Create a managed SMTP account for email blast rotation."""
    await require_permission(request, "settings.manage")
    data, err = _validate_smtp_account_payload(payload.model_dump(), partial=False)
    if err:
        return JSONResponse(status_code=422, content={"detail": err})

    accounts = await _get_managed_smtp_accounts()
    if any(str(account.get("user") or "").lower() == data["user"] for account in accounts):
        return JSONResponse(status_code=409, content={"detail": f"SMTP account {data['user']} already exists"})

    next_id = max((int(account.get("id", 0)) for account in accounts), default=0) + 1
    now = datetime.now(timezone.utc).isoformat()
    record = {
        **data,
        "id": next_id,
        "health_status": "unknown",
        "health_message": "Awaiting first health check",
        "last_checked_at": None,
        "last_healthy_at": None,
        "last_error_at": None,
        "created_at": now,
        "updated_at": now,
    }
    accounts.append(record)
    await _save_managed_smtp_accounts(accounts)
    return {"status": "ok", "account": _sanitize_smtp_account(record, mask_password=True)}


@app.put("/email-smtp-accounts/{account_id}")
async def update_email_smtp_account(account_id: int, payload: SMTPAccountUpdatePayload, request: Request):
    """Update a managed SMTP account."""
    await require_permission(request, "settings.manage")
    changes, err = _validate_smtp_account_payload(payload.model_dump(exclude_none=True), partial=True)
    if err:
        return JSONResponse(status_code=422, content={"detail": err})
    if not changes:
        return JSONResponse(status_code=422, content={"detail": "No changes provided"})

    accounts = await _get_managed_smtp_accounts()
    index = next((i for i, account in enumerate(accounts) if int(account.get("id", 0)) == account_id), -1)
    if index == -1:
        return JSONResponse(status_code=404, content={"detail": "SMTP account not found"})

    existing = accounts[index]
    next_user = str(changes.get("user") or existing.get("user") or "").lower()
    if any(i != index and str(account.get("user") or "").lower() == next_user for i, account in enumerate(accounts)):
        return JSONResponse(status_code=409, content={"detail": f"SMTP account {next_user} already exists"})

    updated = {**existing, **changes, "updated_at": datetime.now(timezone.utc).isoformat()}
    if {"host", "port", "user", "password", "use_ssl"}.intersection(changes):
        updated["health_status"] = "unknown"
        updated["health_message"] = "Awaiting health check after config change"
    accounts[index] = updated
    await _save_managed_smtp_accounts(accounts)
    return {"status": "ok", "account": _sanitize_smtp_account(updated, mask_password=True)}


@app.delete("/email-smtp-accounts/{account_id}")
async def delete_email_smtp_account(account_id: int, request: Request):
    """Delete a managed SMTP account."""
    await require_permission(request, "settings.manage")
    accounts = await _get_managed_smtp_accounts()
    remaining = [account for account in accounts if int(account.get("id", 0)) != account_id]
    if len(remaining) == len(accounts):
        return JSONResponse(status_code=404, content={"detail": "SMTP account not found"})

    await _save_managed_smtp_accounts(remaining)
    return {"status": "ok"}


@app.post("/email-smtp-accounts/{account_id}/test")
async def test_email_smtp_account(account_id: int, request: Request):
    """Test a managed SMTP account without mutating the shared SMTP singleton."""
    await require_permission(request, "settings.manage")
    accounts = await _get_managed_smtp_accounts()
    account = next((entry for entry in accounts if int(entry.get("id", 0)) == account_id), None)
    if not account:
        return JSONResponse(status_code=404, content={"detail": "SMTP account not found"})

    success, message = await asyncio.to_thread(email_blast.test_smtp_account, account)
    updated = await _set_managed_smtp_account_health(account_id, success, message)
    return {
        "success": success,
        "message": message,
        "account": _sanitize_smtp_account(updated, mask_password=True) if updated else None,
    }


def _map_ig_account_login_status(status: str | None, current_status: str = "untested") -> str:
    """Map runtime verification status to the DB login_status field."""
    if status == "connected":
        return "success"
    if status == "auth_limited":
        return "auth_limited"
    if status == "banned":
        return "banned"
    if status == "rate_limited":
        return "rate_limited"
    if status == "challenge":
        return "challenge"
    if status == "disconnected":
        return "failed"
    return current_status or "failed"


def _apply_ig_account_runtime_status(account_pool: Any, username: str, status: str | None, reason: str | None) -> None:
    """Keep the in-memory Playwright pool aligned with a verification result."""
    if status == "connected":
        account_pool.mark_connected(username)
        return
    if status == "rate_limited":
        account_pool.mark_rate_limited(username)
        return
    if status in {"disconnected", "banned", "error", "auth_limited"}:
        account_pool.mark_login_failed(username, reason or status or "login_failed")


@app.get("/ig-accounts")
async def list_ig_accounts():
    """Return all IG accounts (passwords masked)."""
    from orchestrator.db import get_ig_accounts
    rows = await get_ig_accounts()
    for r in rows:
        r["password"] = _mask_password(r.get("password", ""))
    # Also include live pool status
    from orchestrator.playwright_ig import _account_pool
    pool_status = _account_pool.status()
    return {"accounts": rows, "pool_status": pool_status}


@app.get("/ig-accounts/health")
async def ig_accounts_health(force: bool = False):
    """
    Return IG accounts' session health.

    By default this is **lightweight**: reads from the in-memory account
    pool (login_ok, healthy, last_error) and the DB (login_status).
    No browser is launched.

    With ``?force=true`` a real browser-based verification is performed
    for each account (slow, ~15-45 s per account). Use sparingly.
    """
    from orchestrator.playwright_ig import _account_pool
    from orchestrator.db import get_ig_accounts, update_ig_account

    # --- force mode: expensive browser-based verification ---
    if force:
        from orchestrator.playwright_ig import (
            pw_verify_all_sessions, pw_invalidate_health_cache,
        )
        pw_invalidate_health_cache()
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(_pw_executor, pw_verify_all_sessions)

        rows = await get_ig_accounts(enabled_only=True)
        row_map = {r["username"]: r for r in rows}
        for r in results:
            username = r.get("username")
            row = row_map.get(username)
            if not row:
                continue
            st = r.get("status", "error")
            db_st = _map_ig_account_login_status(st, row.get("login_status", "untested"))
            await update_ig_account(row["id"], login_status=db_st,
                                    last_login_test=datetime.now(timezone.utc).isoformat())

        total = len(results)
        connected = sum(1 for r in results if r.get("status") == "connected")
        return {
            "total": total, "connected": connected,
            "all_ok": connected == total and total > 0,
            "accounts": [
                {"username": r.get("username"), "status": r.get("status"),
                 "reason": r.get("reason"), "username_verified": r.get("username_verified")}
                for r in results
            ],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # --- default: lightweight pool + DB status ---
    pool = _account_pool.status()  # [{username, healthy, login_ok, last_error, ...}]
    rows = await get_ig_accounts(enabled_only=True)
    db_map = {r["username"]: r for r in rows}

    accounts_out = []
    for p in pool:
        uname = p["username"]
        db_row = db_map.get(uname, {})
        db_login = db_row.get("login_status", "untested")

        # Derive status from pool state + DB
        if db_login == "banned":
            status = "banned"
            reason = "account_banned"
        elif db_login == "auth_limited" or (p.get("last_error") or "").startswith((
            "profile_only_access",
            "cookies_valid_api_limited",
            "cookies_rejected_after_navigation",
            "missing_sessionid",
            "cookies_present_navigation_failed",
            "following_requires_login",
            "public_profile_only",
            "following_link_not_visible",
            "following_click_failed",
            "following_dialog_missing",
            "following_api_no_response",
            "profile_navigation_failed",
            "following_http_",
        )):
            status = "auth_limited"
            reason = p.get("last_error") or "auth_limited"
        elif not p["login_ok"]:
            status = "disconnected"
            reason = p.get("last_error") or "login_failed"
        elif p.get("cooldown_remaining_s", 0) > 0 or db_login == "rate_limited":
            status = "rate_limited"
            reason = "cooldown_active" if p.get("cooldown_remaining_s", 0) > 0 else "rate_limited"
        elif db_login == "success" and p["healthy"]:
            status = "connected"
            reason = None
        elif db_login in ("untested", "challenge"):
            status = "connected" if p["healthy"] else "disconnected"
            reason = None if p["healthy"] else (p.get("last_error") or db_login)
        else:
            # db_login == 'failed' but pool says healthy → trust pool
            status = "connected" if p["healthy"] else "disconnected"
            reason = None if p["healthy"] else (p.get("last_error") or "failed")

        accounts_out.append({
            "username": uname,
            "status": status,
            "reason": reason,
            "username_verified": uname if status == "connected" else None,
        })

    total = len(accounts_out)
    connected = sum(1 for a in accounts_out if a["status"] == "connected")
    return {
        "total": total,
        "connected": connected,
        "all_ok": connected == total and total > 0,
        "accounts": accounts_out,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/ig-accounts")
async def add_ig_account(payload: IGAccountPayload):
    """Add a new IG account for Playwright rotation."""
    from orchestrator.db import create_ig_account
    if not payload.username.strip() or not payload.password.strip():
        return JSONResponse(status_code=422, content={"detail": "Username and password required"})
    try:
        acct = await create_ig_account(payload.username, payload.password, payload.notes)
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return JSONResponse(status_code=409, content={"detail": f"Account @{payload.username} already exists"})
        raise
    acct["password"] = _mask_password(acct.get("password", ""))
    # Reload pool
    from orchestrator.playwright_ig import _account_pool
    await _reload_ig_account_pool()
    return {"status": "ok", "account": acct}


@app.put("/ig-accounts/{account_id}")
async def edit_ig_account(account_id: int, payload: IGAccountUpdatePayload):
    """Update an IG account."""
    from orchestrator.db import get_ig_accounts, update_ig_account

    rows = await get_ig_accounts()
    existing = next((r for r in rows if r["id"] == account_id), None)
    if not existing:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    old_username = existing.get("username", "")
    updated = await update_ig_account(
        account_id,
        username=payload.username,
        password=payload.password,
        enabled=payload.enabled,
        notes=payload.notes,
    )
    if not updated:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    profile_sync_warning = None
    new_username = updated.get("username", "")
    if payload.username and new_username and new_username != old_username:
        from orchestrator.playwright_ig import pw_rename_profile

        rename_result = pw_rename_profile(old_username, new_username)
        if not rename_result.get("success"):
            profile_sync_warning = rename_result.get("error")
            log.warning(
                "IG account profile rename incomplete for @%s -> @%s: %s",
                old_username,
                new_username,
                profile_sync_warning,
            )

    updated["password"] = _mask_password(updated.get("password", ""))
    await _reload_ig_account_pool()
    response = {"status": "ok", "account": updated}
    if profile_sync_warning:
        response["warning"] = profile_sync_warning
    return response


@app.delete("/ig-accounts/{account_id}")
async def remove_ig_account(account_id: int):
    """Delete an IG account."""
    from orchestrator.db import delete_ig_account
    ok = await delete_ig_account(account_id)
    if not ok:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})
    await _reload_ig_account_pool()
    return {"status": "ok"}


# ---- New headless login endpoints (simple REST, no SSE) ----

@app.post("/ig-accounts/{account_id}/login")
async def ig_account_login(account_id: int):
    """
    Credential-based login is disabled.
    """
    return JSONResponse(
        status_code=410,
        content={"detail": "Credential login disabled. Use /ig-accounts/{account_id}/session/import-cookies instead."},
    )


@app.post("/ig-accounts/{account_id}/login/challenge")
async def ig_account_login_challenge(account_id: int, body: dict):
    """
    Challenge submission is disabled because credential login is disabled.
    """
    return JSONResponse(
        status_code=410,
        content={"detail": "Credential login challenge disabled. Import fresh cookies instead."},
    )


# ---- Legacy test-login endpoints (kept for backward compatibility) ----

@app.post("/ig-accounts/{account_id}/test-login")
async def test_ig_account_login(account_id: int):
    """
    Credential-based login testing is disabled.
    """
    return JSONResponse(
        status_code=410,
        content={"detail": "Credential login testing disabled. Use session import and session verify endpoints instead."},
    )


@app.get("/ig-accounts/{account_id}/test-login-live")
async def test_ig_account_login_live(account_id: int):
    """
    Visible credential login testing is disabled.
    """
    return JSONResponse(
        status_code=410,
        content={"detail": "Visible credential login testing disabled. Import cookies instead."},
    )


async def _reload_ig_account_pool():
    """Reload Playwright account pool from DB."""
    from orchestrator.db import get_ig_accounts
    from orchestrator.playwright_ig import _account_pool
    rows = await get_ig_accounts(enabled_only=True)
    _account_pool.load_from_db(rows)


# ---------------------------------------------------------------------------
# Session Sync (export from local → import on server)
# ---------------------------------------------------------------------------


@app.get("/ig-accounts/{account_id}/session/export")
async def export_ig_session(account_id: int):
    """
    Export Playwright session profile as a tar.gz download.
    Use this to download a working session from local machine,
    then import it on the server where direct IG login may be blocked.
    """
    from orchestrator.db import get_ig_accounts
    rows = await get_ig_accounts()
    acct_row = next((r for r in rows if r["id"] == account_id), None)
    if not acct_row:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    username = acct_row["username"]

    from orchestrator.playwright_ig import pw_export_session
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, pw_export_session, username)

    if data is None:
        return JSONResponse(status_code=404, content={
            "detail": f"No session profile found for @{username}. Login first."
        })

    filename = f"ig_session_{username}.tar.gz"
    return StreamingResponse(
        iter([data]),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/ig-accounts/{account_id}/session/import")
async def import_ig_session(account_id: int, file: UploadFile = FastAPIFile(...)):
    """
    Import a Playwright session profile from a tar.gz upload.
    Replaces any existing profile for this account's username.
    After import, the session is verified with a lightweight check.
    """
    from orchestrator.db import get_ig_accounts, update_ig_account
    rows = await get_ig_accounts()
    acct_row = next((r for r in rows if r["id"] == account_id), None)
    if not acct_row:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    username = acct_row["username"]

    # Read uploaded file
    data = await file.read()
    if len(data) < 100:
        return JSONResponse(status_code=400, content={"detail": "File too small — not a valid session archive"})

    from orchestrator.playwright_ig import pw_import_session, pw_verify_session, _account_pool, pw_invalidate_health_cache

    # Import (blocking I/O)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, pw_import_session, username, data)

    if not result.get("success"):
        return JSONResponse(status_code=400, content={"detail": result.get("error", "Import failed")})

    # Verify the imported session
    verify = await loop.run_in_executor(_pw_executor, pw_verify_session, username, acct_row["password"])

    # Update DB status based on verification
    v_status = verify.get("status", "error")
    db_status = _map_ig_account_login_status(v_status, acct_row.get("login_status", "untested"))
    now_ts = datetime.now(timezone.utc).isoformat()
    await update_ig_account(account_id, login_status=db_status, last_login_test=now_ts)

    # Update pool
    _apply_ig_account_runtime_status(_account_pool, username, v_status, verify.get("reason"))
    pw_invalidate_health_cache()

    await _reload_ig_account_pool()

    return {
        "status": "ok",
        "import": result,
        "verify": {
            "status": v_status,
            "reason": verify.get("reason"),
            "username_verified": verify.get("username_verified"),
        },
    }


@app.post("/ig-accounts/{account_id}/session/import-cookies")
async def import_ig_cookies(account_id: int, body: dict):
    """
    Import raw browser cookies into the Playwright profile.
    Body: { "cookies": [ {name, value, domain, path, ...}, ... ] }

    Typical workflow:
        1. User logs into IG in their normal browser
        2. Uses a cookie extension (Cookie-Editor, EditThisCookie) or DevTools
           to export cookies for instagram.com as JSON
        3. Pastes the JSON here
        4. Server injects cookies + verifies session

    This avoids the need to login from the server's IP (which IG may block).
    """
    from orchestrator.db import get_ig_accounts, update_ig_account
    rows = await get_ig_accounts()
    acct_row = next((r for r in rows if r["id"] == account_id), None)
    if not acct_row:
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    username = acct_row["username"]
    cookies = body.get("cookies")
    if not cookies or not isinstance(cookies, list):
        return JSONResponse(status_code=400, content={
            "detail": "Body must contain 'cookies' array. "
                      "Example: {\"cookies\": [{\"name\":\"sessionid\",\"value\":\"...\",\"domain\":\".instagram.com\",\"path\":\"/\"}]}"
        })

    from orchestrator.playwright_ig import pw_import_cookies, pw_verify_session, _account_pool, pw_invalidate_health_cache

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_pw_executor, pw_import_cookies, username, cookies)

    if not result.get("success"):
        return JSONResponse(status_code=400, content={"detail": result.get("error", "Cookie import failed")})

    # Verify the imported session
    verify = await loop.run_in_executor(_pw_executor, pw_verify_session, username, acct_row["password"])

    v_status = verify.get("status", "error")
    db_status = _map_ig_account_login_status(v_status, acct_row.get("login_status", "untested"))
    now_ts = datetime.now(timezone.utc).isoformat()
    await update_ig_account(account_id, login_status=db_status, last_login_test=now_ts)

    # Update pool
    _apply_ig_account_runtime_status(_account_pool, username, v_status, verify.get("reason"))
    pw_invalidate_health_cache()

    await _reload_ig_account_pool()

    return {
        "status": "ok",
        "import": result,
        "verify": {
            "status": v_status,
            "reason": verify.get("reason"),
            "username_verified": verify.get("username_verified"),
        },
    }


# ---------------------------------------------------------------------------
# Knowledge Items CRUD
# ---------------------------------------------------------------------------

class KnowledgeItemPayload(BaseModel):
    chatbot_type: str  # 'agent' | 'audiensi'
    title: str
    content: str
    situation_tags: str = ""
    trigger_keywords: str = ""


class KnowledgeItemUpdatePayload(BaseModel):
    title: str | None = None
    content: str | None = None
    is_active: bool | None = None
    situation_tags: str | None = None
    trigger_keywords: str | None = None


@app.get("/knowledge-items")
async def list_knowledge_items(chatbot_type: str | None = None):
    """List knowledge items, optionally filtered by chatbot_type."""
    items = await get_knowledge_items(chatbot_type)
    return {"items": items}


@app.post("/knowledge-items")
async def create_knowledge_item_endpoint(payload: KnowledgeItemPayload):
    """Create a new knowledge item."""
    if payload.chatbot_type not in ("agent", "audiensi"):
        return JSONResponse(
            status_code=422,
            content={"detail": "chatbot_type must be 'agent' or 'audiensi'"},
        )
    item_id = await create_knowledge_item(
        payload.chatbot_type, payload.title, payload.content,
        situation_tags=payload.situation_tags,
        trigger_keywords=payload.trigger_keywords,
    )
    # Invalidate Responses API sessions — knowledge base changed
    await clear_all_response_ids("conversations")
    await clear_all_response_ids("audiensi_conversations")
    return {"id": item_id, "status": "ok"}


@app.patch("/knowledge-items/{item_id}")
async def update_knowledge_item_endpoint(item_id: int, payload: KnowledgeItemUpdatePayload):
    """Update a knowledge item."""
    updates = {}
    if payload.title is not None:
        updates["title"] = payload.title
    if payload.content is not None:
        updates["content"] = payload.content
    if payload.is_active is not None:
        updates["is_active"] = int(payload.is_active)
    if payload.situation_tags is not None:
        updates["situation_tags"] = payload.situation_tags
    if payload.trigger_keywords is not None:
        updates["trigger_keywords"] = payload.trigger_keywords
    if not updates:
        return JSONResponse(status_code=422, content={"detail": "No fields to update"})
    await update_knowledge_item(item_id, **updates)
    # Invalidate Responses API sessions — knowledge base changed
    await clear_all_response_ids("conversations")
    await clear_all_response_ids("audiensi_conversations")
    return {"status": "ok"}


@app.delete("/knowledge-items/{item_id}")
async def delete_knowledge_item_endpoint(item_id: int):
    """Delete a knowledge item."""
    await delete_knowledge_item(item_id)
    # Invalidate Responses API sessions — knowledge base changed
    await clear_all_response_ids("conversations")
    await clear_all_response_ids("audiensi_conversations")
    return {"status": "ok"}


_ALLOWED_KB_EXTENSIONS = {".txt", ".md", ".csv", ".docx", ".pdf"}


def _extract_text_from_file(filename: str, content: bytes) -> str:
    """Extract plain text from an uploaded file."""
    import os
    ext = os.path.splitext(filename)[1].lower()

    if ext in (".txt", ".md"):
        return content.decode("utf-8", errors="replace")

    if ext == ".csv":
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        lines = []
        for row in reader:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    if ext == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if ext == ".pdf":
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(content))
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n".join(pages)
        except ImportError:
            raise ValueError("PDF support requires PyPDF2. Install with: pip install PyPDF2")

    raise ValueError(f"Unsupported file type: {ext}")


@app.post("/knowledge-items/upload")
async def upload_knowledge_item(
    file: UploadFile = FastAPIFile(...),
    chatbot_type: str = Form(...),
):
    """Upload a file (.txt, .md, .csv, .docx, .pdf) as a knowledge item."""
    import os

    if chatbot_type not in ("agent", "audiensi"):
        return JSONResponse(
            status_code=422,
            content={"detail": "chatbot_type must be 'agent' or 'audiensi'"},
        )

    if not file.filename:
        return JSONResponse(status_code=400, content={"detail": "No filename provided"})

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _ALLOWED_KB_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Unsupported file type: {ext}. Allowed: {', '.join(_ALLOWED_KB_EXTENSIONS)}"},
        )

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:  # 5MB limit
        return JSONResponse(status_code=400, content={"detail": "File too large (max 5MB)"})

    try:
        text = _extract_text_from_file(file.filename, raw)
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": f"Failed to extract text: {e}"})

    if not text.strip():
        return JSONResponse(status_code=400, content={"detail": "File contains no extractable text"})

    title = os.path.splitext(file.filename)[0]
    item_id = await create_knowledge_item(chatbot_type, title, text.strip())

    return {"id": item_id, "status": "ok", "title": title, "content_length": len(text.strip())}


# ---------------------------------------------------------------------------
# API Call Logs
# ---------------------------------------------------------------------------


@app.get("/api-logs")
async def list_api_logs(
    chatbot_type: str | None = None,
    conversation_id: int | None = None,
    call_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List API call logs with optional filters and pagination."""
    logs = await get_api_call_logs(chatbot_type, conversation_id, call_type, limit, offset)
    return {"logs": logs}


@app.get("/api-logs/{log_id}")
async def get_api_log(log_id: int):
    """Get full detail of a single API call log."""
    log_entry = await get_api_call_log_by_id(log_id)
    if not log_entry:
        return JSONResponse(status_code=404, content={"detail": "API log not found"})
    return log_entry


# ---------------------------------------------------------------------------
# Audiensi endpoints
# ---------------------------------------------------------------------------


@app.get("/audiensi")
async def list_audiensi(
    state: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List audiensi conversations with optional state filter."""
    from orchestrator.db import get_audiensi_conversations_filtered
    return await get_audiensi_conversations_filtered(state, limit, offset)


@app.get("/audiensi/queue")
async def audiensi_queue():
    """Get pending approval queue."""
    from orchestrator.db import get_queued_audiensi
    return await get_queued_audiensi()


@app.get("/audiensi/stats")
async def audiensi_stats():
    """Get audiensi dashboard stats."""
    from orchestrator.db import get_audiensi_stats
    return await get_audiensi_stats()


@app.get("/audiensi/{aud_id}")
async def get_audiensi(aud_id: int):
    """Get a single audiensi conversation by ID."""
    from orchestrator.db import get_audiensi_conversation_by_id
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    return aud


class RectorNamePayload(BaseModel):
    rector_name: str


@app.put("/audiensi/{aud_id}/rector-name")
async def update_audiensi_rector_name(aud_id: int, payload: RectorNamePayload):
    """Edit rector name for an audiensi conversation."""
    from orchestrator.db import get_audiensi_conversation_by_id, update_audiensi_state, update_university_rector_name
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    await update_audiensi_state(aud_id, aud["state"], rector_name=payload.rector_name)
    # Also update university record
    if aud.get("university_id"):
        await update_university_rector_name(aud["university_id"], payload.rector_name)
    return {"status": "ok"}


class InitialMessagePayload(BaseModel):
    message: str


@app.put("/audiensi/{aud_id}/initial-message")
async def update_audiensi_initial_message(aud_id: int, payload: InitialMessagePayload):
    """Edit initial message draft."""
    from orchestrator.db import get_audiensi_conversation_by_id, update_audiensi_state
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    await update_audiensi_state(aud_id, aud["state"], initial_message_draft=payload.message)
    return {"status": "ok"}


@app.post("/audiensi/{aud_id}/regenerate-pdf")
async def regenerate_audiensi_pdf(aud_id: int):
    """Regenerate PDF after edits (rector name, etc.)."""
    from orchestrator.db import get_audiensi_conversation_by_id, update_audiensi_state
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})

    try:
        from orchestrator.audiensi.pdf_generator import generate_audiensi_document
        pdf_path = await generate_audiensi_document(
            audiensi_id=aud_id,
            university_name=aud.get("university_name", ""),
            rector_name=aud.get("rector_name"),
            province=aud.get("province"),
        )
        if pdf_path:
            await update_audiensi_state(aud_id, aud["state"], pdf_path=pdf_path)
        return {"status": "ok", "pdf_path": pdf_path}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"PDF generation failed: {e}"})


@app.get("/audiensi/{aud_id}/pdf")
async def get_audiensi_pdf(aud_id: int):
    """Download/preview the generated PDF."""
    from orchestrator.db import get_audiensi_conversation_by_id
    import os
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud or not aud.get("pdf_path"):
        return JSONResponse(status_code=404, content={"detail": "PDF not found"})
    pdf_path = aud["pdf_path"]
    if not os.path.exists(pdf_path):
        return JSONResponse(status_code=404, content={"detail": "PDF file not found on disk"})
    from fastapi.responses import FileResponse
    filename = os.path.basename(pdf_path)
    return FileResponse(pdf_path, filename=filename, media_type="application/octet-stream")


@app.post("/audiensi/{aud_id}/approve")
async def approve_audiensi(aud_id: int, background_tasks: BackgroundTasks):
    """Approve audiensi & send initial message + document."""
    from orchestrator.db import (
        get_audiensi_conversation_by_id,
        update_audiensi_state,
        add_audiensi_message,
    )
    from datetime import datetime as _dt, timezone as _tz

    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    if aud["state"] != "QUEUED":
        return JSONResponse(status_code=400, content={"detail": f"Cannot approve: state is {aud['state']}"})

    # Update state to APPROVED
    now = _dt.now(_tz.utc).isoformat()
    await update_audiensi_state(aud_id, "APPROVED", approved_at=now)

    # Send document first (if available), then text message
    async def _send_messages():
        phone = aud["contact_phone"]
        uni_name = aud.get("university_name", "University")

        # 1. Send PDF/document if available
        if aud.get("pdf_path"):
            import os
            if os.path.exists(aud["pdf_path"]):
                doc_name = f"Undangan_Audiensi_{uni_name.replace(' ', '_')}.docx"
                await message_queue.enqueue_send_document(
                    phone, aud["pdf_path"], doc_name,
                    caption="Surat Undangan Audiensi Daring - Asosiasi AI Indonesia",
                )

        # 2. Send text message
        text = aud.get("initial_message_draft") or (
            f"Selamat pagi,\n\n"
            f"Saya Ali dari Asosiasi Artificial Intelligence Indonesia.\n"
            f"Kami telah mengirimkan surat undangan audiensi daring Zoom untuk {uni_name}.\n"
            f"Mohon kesediaannya untuk menjadwalkan pertemuan ~40 menit.\n\n"
            f"Terima kasih 🙏🏻"
        )
        await message_queue.enqueue_send(phone, text)

        # Update state to INITIAL_SENT
        await update_audiensi_state(
            aud_id, "INITIAL_SENT",
            last_message_at=_dt.now(_tz.utc).isoformat(),
        )
        await add_audiensi_message(aud_id, "bot", text)

    background_tasks.add_task(_send_messages)
    return {"status": "ok", "message": "Audiensi approved, messages being sent"}


@app.post("/audiensi/{aud_id}/reject")
async def reject_audiensi(aud_id: int):
    """Reject/cancel an audiensi."""
    from orchestrator.db import get_audiensi_conversation_by_id, update_audiensi_state
    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})
    await update_audiensi_state(aud_id, "ABANDONED")
    return {"status": "ok"}


@app.post("/audiensi/{aud_id}/send-zoom")
async def send_zoom_link(aud_id: int, background_tasks: BackgroundTasks):
    """Manually send zoom link for a scheduled audiensi."""
    from orchestrator.db import (
        get_audiensi_conversation_by_id,
        update_audiensi_state,
        add_audiensi_message,
    )
    from datetime import datetime as _dt, timezone as _tz

    aud = await get_audiensi_conversation_by_id(aud_id)
    if not aud:
        return JSONResponse(status_code=404, content={"detail": "Audiensi not found"})

    zoom_link = cfg.AUDIENSI_ZOOM_LINK_TEMPLATE or "https://zoom.us/j/placeholder"

    async def _send():
        phone = aud["contact_phone"]
        msg = f"Berikut link Zoom untuk audiensi:\n\n{zoom_link}\n\nTerima kasih 🙏🏻"
        await message_queue.enqueue_send(phone, msg)
        await update_audiensi_state(
            aud_id, "ZOOM_SENT",
            zoom_link=zoom_link,
            last_message_at=_dt.now(_tz.utc).isoformat(),
        )
        await add_audiensi_message(aud_id, "bot", msg)

    background_tasks.add_task(_send)
    return {"status": "ok", "zoom_link": zoom_link}


# Audiensi template management

@app.post("/audiensi/template/upload")
async def upload_audiensi_template(file: UploadFile = FastAPIFile(...)):
    """Upload a new .docx template for audiensi invitations."""
    if not file.filename or not file.filename.endswith(".docx"):
        return JSONResponse(status_code=400, content={"detail": "Only .docx files allowed"})
    content = await file.read()
    try:
        from orchestrator.audiensi.pdf_generator import save_uploaded_template
        path = await save_uploaded_template(content, file.filename)
        return {"status": "ok", "path": path}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/audiensi/template/placeholders")
async def audiensi_template_placeholders():
    """List available template placeholders."""
    from orchestrator.audiensi.pdf_generator import get_available_placeholders
    return {"placeholders": get_available_placeholders()}


# ---------------------------------------------------------------------------
# DMS MySQL Integration Endpoints
# ---------------------------------------------------------------------------


@app.get("/dms/health")
async def dms_health():
    """Check DMS MySQL connection health."""
    try:
        from orchestrator.dms_mysql import check_dms_connection
        return await check_dms_connection()
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/dms/stats")
async def dms_stats():
    """Get aggregate stats from DMS database."""
    try:
        from orchestrator.dms_mysql import get_dms_audiensi_stats
        return await get_dms_audiensi_stats()
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/schedules")
async def dms_schedules(
    days_ahead: int = 30,
    include_past_days: int = 7,
):
    """Get upcoming audiensi schedules from DMS."""
    try:
        from orchestrator.dms_mysql import get_upcoming_audiensi_schedules
        schedules = await get_upcoming_audiensi_schedules(days_ahead, include_past_days)
        return {"total": len(schedules), "schedules": schedules}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/schedules/today")
async def dms_schedules_today():
    """Get today's audiensi schedules from DMS."""
    try:
        from orchestrator.dms_mysql import get_today_audiensi_schedules
        schedules = await get_today_audiensi_schedules()
        return {"total": len(schedules), "schedules": schedules}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/schedules/{schedule_id}")
async def dms_schedule_detail(schedule_id: int, source: str = "schedule_follow_up"):
    """Get detailed info for a specific audiensi schedule.

    ``source`` can be ``schedule_follow_up`` (default) or ``surat_audiensi``.
    """
    try:
        from orchestrator.dms_mysql import get_audiensi_schedule_by_id, get_meeting_by_schedule
        schedule = await get_audiensi_schedule_by_id(schedule_id, source=source)
        if not schedule:
            return JSONResponse(status_code=404, content={"detail": "Schedule not found"})
        if source == "schedule_follow_up":
            meetings = await get_meeting_by_schedule(schedule_id)
            schedule["meetings"] = meetings or []
        else:
            schedule["meetings"] = []
        return schedule
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/followups")
async def dms_followups(limit: int = 50):
    """Get recent follow-up activities from DMS."""
    try:
        from orchestrator.dms_mysql import get_recent_follow_ups
        followups = await get_recent_follow_ups(limit)
        return {"total": len(followups), "followups": followups}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/followups/{id_univ}")
async def dms_followups_by_university(id_univ: int, limit: int = 20):
    """Get follow-up history for a specific university from DMS."""
    try:
        from orchestrator.dms_mysql import get_follow_up_history
        followups = await get_follow_up_history(id_univ, limit)
        return {"total": len(followups), "followups": followups}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/meetings")
async def dms_meetings(days_ahead: int = 14):
    """Get upcoming Zoom meetings from DMS."""
    try:
        from orchestrator.dms_mysql import get_upcoming_meetings
        meetings = await get_upcoming_meetings(days_ahead)
        return {"total": len(meetings), "meetings": meetings}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# OSINT Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.post("/osint/run/{university_id}")
async def osint_run(university_id: int, background_tasks: BackgroundTasks):
    """Start OSINT pipeline for a single university (background)."""
    from orchestrator.osint.graph import run_osint_pipeline

    background_tasks.add_task(run_osint_pipeline, university_id)
    return {"status": "started", "university_id": university_id}


class OsintBatchRequest(BaseModel):
    university_ids: list[int]


@app.post("/osint/run-batch")
async def osint_run_batch(req: OsintBatchRequest, background_tasks: BackgroundTasks):
    """Start OSINT pipeline for multiple universities (background)."""
    from orchestrator.osint.graph import run_osint_pipeline

    for uid in req.university_ids:
        background_tasks.add_task(run_osint_pipeline, uid)
    return {"status": "started", "count": len(req.university_ids)}


@app.get("/osint/profile/{university_id}")
async def osint_profile(university_id: int):
    """Get OSINT profile + contacts + social + news for a university."""
    from orchestrator.db import (
        get_osint_profile,
        get_osint_contacts,
        get_osint_social,
        get_osint_news,
    )

    profile = await get_osint_profile(university_id)
    contacts = await get_osint_contacts(university_id)
    social = await get_osint_social(university_id)
    news = await get_osint_news(university_id)
    return {
        "profile": profile,
        "contacts": contacts,
        "social_media": social,
        "news": news,
    }


@app.get("/osint/runs")
async def osint_runs(limit: int = 25, offset: int = 0):
    """List OSINT pipeline runs."""
    from orchestrator.db import get_osint_runs

    return await get_osint_runs(limit=limit, offset=offset)


@app.get("/osint/runs/{run_id}")
async def osint_run_detail(run_id: int):
    """Get details of a specific OSINT run."""
    from orchestrator.db import get_osint_run

    run = await get_osint_run(run_id)
    if not run:
        return JSONResponse(status_code=404, content={"detail": "Run not found"})
    return run


# ═══════════════════════════════════════════════════════════════════════════
# CRM / PIC Profiling Endpoints
# ═══════════════════════════════════════════════════════════════════════════


class CrmRequestCreate(BaseModel):
    pic_name: str
    university_id: int | None = None
    university_name: str | None = None
    pic_title: str | None = None
    requested_by: str | None = None
    priority: str = "normal"
    notes: str | None = None


@app.post("/crm/requests")
async def crm_create_request(req: CrmRequestCreate):
    """Create a new PIC profiling request."""
    from orchestrator.db import create_crm_request

    request_id = await create_crm_request(
        pic_name=req.pic_name,
        university_id=req.university_id,
        university_name=req.university_name,
        pic_title=req.pic_title,
        requested_by=req.requested_by,
        priority=req.priority,
        notes=req.notes,
    )
    return {"id": request_id, "status": "pending"}


@app.get("/crm/requests")
async def crm_list_requests(
    status: str | None = None,
    limit: int = 25,
    offset: int = 0,
):
    """List CRM profiling requests with optional status filter."""
    from orchestrator.db import get_crm_requests

    return await get_crm_requests(status=status, limit=limit, offset=offset)


@app.get("/crm/requests/{request_id}")
async def crm_get_request(request_id: int):
    """Get a single CRM request with its profile if available."""
    from orchestrator.db import get_crm_request, get_crm_profile_by_request

    request = await get_crm_request(request_id)
    if not request:
        return JSONResponse(status_code=404, content={"detail": "Request not found"})

    profile = await get_crm_profile_by_request(request_id)
    return {"request": request, "profile": profile}


@app.post("/crm/requests/{request_id}/run")
async def crm_run_profiling(request_id: int, background_tasks: BackgroundTasks):
    """Start PIC profiling pipeline for a request (background)."""
    from orchestrator.db import get_crm_request
    from orchestrator.crm.graph import run_pic_profiling

    request = await get_crm_request(request_id)
    if not request:
        return JSONResponse(status_code=404, content={"detail": "Request not found"})

    if request.get("status") == "processing":
        return JSONResponse(status_code=409, content={"detail": "Already processing"})

    background_tasks.add_task(run_pic_profiling, request_id)
    return {"status": "started", "request_id": request_id}


@app.get("/crm/profiles/{profile_id}")
async def crm_get_profile(profile_id: int):
    """Get a PIC profile with its source audit trail."""
    from orchestrator.db import get_crm_profile, get_crm_profile_sources

    profile = await get_crm_profile(profile_id)
    if not profile:
        return JSONResponse(status_code=404, content={"detail": "Profile not found"})

    sources = await get_crm_profile_sources(profile_id)
    return {"profile": profile, "sources": sources}


class CrmProfileUpdate(BaseModel):
    """Manual profile field updates."""
    fields: dict[str, Any]


@app.patch("/crm/profiles/{profile_id}")
async def crm_update_profile(profile_id: int, req: CrmProfileUpdate):
    """Manually update fields on a PIC profile."""
    from orchestrator.db import update_crm_profile

    updated = await update_crm_profile(profile_id, source_type="manual", **req.fields)
    if not updated:
        return JSONResponse(status_code=404, content={"detail": "Profile not found or no valid fields"})
    return {"profile": updated}


@app.get("/crm/stats")
async def crm_stats():
    """Get CRM dashboard statistics."""
    from orchestrator.db import get_crm_stats

    return await get_crm_stats()


@app.get("/dms/pics/search")
async def dms_search_pics(q: str = "", limit: int = 50):
    """Search PICs across all DMS sources (universitas, kontak_universitas, schedule_pic_audiensi)."""
    try:
        from orchestrator.dms_mysql import search_dms_pics
        results = await search_dms_pics(keyword=q, limit=limit)
        return {"total": len(results), "pics": results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/universities/search")
async def dms_search_universities(q: str = "", limit: int = 20):
    """Search universities in DMS by keyword."""
    if not q or len(q) < 2:
        return JSONResponse(status_code=400, content={"detail": "Query must be at least 2 characters"})
    try:
        from orchestrator.dms_mysql import search_dms_universities
        results = await search_dms_universities(q, limit)
        return {"total": len(results), "universities": results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/universities/{id_univ}")
async def dms_university_detail(id_univ: int):
    """Get university details from DMS."""
    try:
        from orchestrator.dms_mysql import get_dms_university, get_dms_university_contacts
        uni = await get_dms_university(id_univ)
        if not uni:
            return JSONResponse(status_code=404, content={"detail": "University not found"})
        uni["contacts"] = await get_dms_university_contacts(id_univ)
        return uni
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/approvals")
async def dms_approvals(status: str = None, limit: int = 50):
    """Get schedule audiensi approval entries."""
    try:
        from orchestrator.dms_mysql import get_schedule_audiensi_approvals
        approvals = await get_schedule_audiensi_approvals(status, limit)
        return {"total": len(approvals), "approvals": approvals}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/dms/sync/contacts")
async def dms_trigger_contact_sync(background_tasks: BackgroundTasks):
    """Manually trigger contact sync from GetContact to DMS."""
    from orchestrator.scheduler import dms_sync_contacts
    background_tasks.add_task(dms_sync_contacts)
    return {"status": "ok", "message": "Contact sync started in background"}


@app.post("/dms/sync/schedules")
async def dms_trigger_schedule_sync(background_tasks: BackgroundTasks):
    """Manually trigger DMS schedule sync and reminder check."""
    from orchestrator.scheduler import dms_sync_audiensi_schedules
    background_tasks.add_task(dms_sync_audiensi_schedules)
    return {"status": "ok", "message": "Schedule sync started in background"}


# ---------------------------------------------------------------------------
# DMS Audiensi Research (Gemini AI)
# ---------------------------------------------------------------------------

@app.post("/dms/research/run-tomorrow")
async def dms_research_run_tomorrow(background_tasks: BackgroundTasks):
    """Trigger H-1 audiensi research for tomorrow's schedules."""
    from orchestrator.audiensi_research import research_tomorrow_schedules
    background_tasks.add_task(research_tomorrow_schedules)
    return {"status": "ok", "message": "H-1 audiensi research started in background"}


@app.post("/dms/research/schedule/{schedule_id}")
async def dms_research_single(
    schedule_id: int,
    background_tasks: BackgroundTasks,
    source: str = "schedule_follow_up",
):
    """Trigger research for a specific schedule."""
    try:
        from orchestrator.dms_mysql import get_audiensi_schedule_by_id
        from orchestrator.audiensi_research import research_and_notify_schedule
        schedule = await get_audiensi_schedule_by_id(schedule_id, source=source)
        if not schedule:
            return {"status": "error", "message": "Schedule not found"}
        background_tasks.add_task(research_and_notify_schedule, schedule)
        return {"status": "ok", "message": f"Research started for schedule #{schedule_id} ({source})"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/dms/research/test")
async def dms_research_test(body: dict):
    """
    Test research with a dummy/custom university — no MySQL schedule needed.
    Body: { "university_name": "...", "university_city": "...", "schedule_date": "2026-03-08" }
    Calls Gemini AI, stores result in local SQLite (GetContactAIAgent DB), and returns it.
    Pass "notify": true to also send WA notification to configured phones.
    """
    from orchestrator.audiensi_research import research_and_notify_schedule

    university_name = body.get("university_name", "").strip()
    if not university_name:
        return JSONResponse(status_code=400, content={"detail": "university_name is required"})

    university_city = body.get("university_city", "").strip() or None
    schedule_date = body.get("schedule_date", "").strip() or None
    send_notify = body.get("notify", False)

    # Build a dummy schedule dict — use id=0 so it's clearly a test entry
    dummy_schedule = {
        "id": 0,
        "source": "test",
        "nama_universitas": university_name,
        "alamat": university_city,
        "jadwal_audiensi": schedule_date or "",
        "jam_audensi": "",
    }

    # notify_phones=[] suppresses WA notification unless "notify": true
    notify_phones = None if send_notify else []

    try:
        log.info("TEST research for: %s (%s) on %s (notify=%s)",
                 university_name, university_city, schedule_date, send_notify)
        result = await research_and_notify_schedule(dummy_schedule, notify_phones=notify_phones)
        return {"status": "ok", "university": university_name, "stored": True, "result": result}
    except Exception as e:
        log.error("TEST research failed: %s", e, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/research/results")
async def dms_research_results(date: str = None, limit: int = 50):
    """Get research results, optionally filtered by date."""
    from orchestrator.audiensi_research import get_all_research, get_research_by_date
    try:
        if date:
            results = await get_research_by_date(date)
        else:
            results = await get_all_research(limit)
        return {"results": results, "count": len(results)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/dms/research/results/{schedule_id}")
async def dms_research_result_by_schedule(schedule_id: int):
    """Get research result for a specific schedule."""
    from orchestrator.audiensi_research import get_research_by_schedule_id
    try:
        result = await get_research_by_schedule_id(schedule_id)
        if not result:
            return {"status": "not_found", "message": "No research found for this schedule"}
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# System Logs — in-memory buffer
# ---------------------------------------------------------------------------

@app.get("/api/logs/recent")
async def get_recent_logs(limit: int = Query(default=200, ge=1, le=2000)):
    """Return the most recent log lines from the in-memory buffer."""
    from orchestrator.config import get_log_buffer
    buf = get_log_buffer()
    # Return tail (newest last), capped at limit
    return buf[-limit:]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check endpoint."""
    from orchestrator.instagram import get_ig_session_status, get_serper_status
    from orchestrator import apify_client, scrapingbot_client, duckduckgo_client, playwright_ig

    # Check WA service connectivity
    wa_status = {"connected": False}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{WA_SERVICE_URL}/status")
            wa_status = resp.json()
    except Exception:
        pass

    # Check DMS MySQL connectivity
    dms_status = {"status": "disabled"}
    if cfg.get("DMS_MYSQL_HOST"):
        try:
            from orchestrator.dms_mysql import check_dms_connection
            dms_status = await check_dms_connection()
        except Exception as e:
            dms_status = {"status": "error", "error": str(e)}

    return {
        "status": "ok",
        "whatsapp": wa_status,
        "instagram": get_ig_session_status(),
        "dms_mysql": dms_status,
        "scraping": {
            "playwright": playwright_ig.get_status(),
            "duckduckgo": duckduckgo_client.get_status(),
        },
        "api_keys": {
            "serper": get_serper_status(),
            "apify": apify_client.get_status(),
            "scrapingbot": scrapingbot_client.get_status(),
        },
    }


@app.get("/instagram/session-status")
async def get_ig_session_status_endpoint():
    """Return current IG session pool status."""
    from orchestrator.instagram import _ig_pool
    return _ig_pool.get_status()


@app.post("/instagram/reset-sessions")
async def reset_ig_sessions():
    """Reset all IG sessions to healthy state (e.g. after updating session IDs)."""
    from orchestrator.instagram import _ig_pool
    _ig_pool.reset_all()
    return {"success": True, "message": "All IG sessions reset to healthy", "status": _ig_pool.get_status()}


# ---------------------------------------------------------------------------
# Image Proxy Endpoint - Bypass Instagram hotlinking protection
# ---------------------------------------------------------------------------

@app.get("/api/v1/test-endpoint")
async def test_endpoint():
    """Test endpoint to verify routing works"""
    log.info("[TEST] Test endpoint called!")
    return {"status": "ok", "message": "Test endpoint works"}

@app.get("/api/v1/proxy-image")
async def proxy_image(url: str = Query(..., description="Instagram image URL to proxy")):
    """
    Proxy Instagram images to bypass hotlinking protection.

    Downloads image from Instagram and serves it directly.
    Returns original image content-type and caches for 1 hour.
    """
    import httpx
    from fastapi.responses import Response

    # Validate URL - only allow Instagram domains
    from urllib.parse import urlparse
    parsed = urlparse(url)
    netloc_lower = parsed.netloc.lower()

    allowed_domains = ["instagram.com", "cdninstagram.com", "fbcdn.net",
                       "scontent.cdninstagram.com", "scontent-*.cdninstagram.com"]

    if not any(domain in netloc_lower or netloc_lower.endswith("." + domain) for domain in allowed_domains):
        return JSONResponse(
            {"detail": "Only Instagram images are allowed"},
            status_code=400
        )

    # Download image with proper headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            log.info(f"[Proxy] Fetching image from: {url[:100]}...")
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            # Determine content type
            content_type = response.headers.get("content-type", "image/jpeg")

            log.info(f"[Proxy] Successfully fetched image: {len(response.content)} bytes, {content_type}")

            # Return image directly
            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                    "X-Image-URL": url,  # For debugging
                }
            )
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to proxy image from {url}: {e}")
            return JSONResponse(
                {"detail": "Failed to fetch image from Instagram"},
                status_code=502
            )
        except Exception as e:
            log.error(f"Unexpected error proxying image from {url}: {e}")
            return JSONResponse(
                {"detail": "Failed to fetch image"},
                status_code=500
            )


# ---------------------------------------------------------------------------
# Instagram Image URL Scraper - Get fresh image URLs from post pages
# ---------------------------------------------------------------------------

@app.get("/api/v1/instagram-image")
async def get_instagram_image_url(post_url: str = Query(..., description="Instagram post URL")):
    """
    Get fresh image URL using Instagram oEmbed API.

    Instagram's oEmbed API returns valid image URLs that work.
    This is more reliable than scraping HTML.

    Returns: {"image_url": "...", "post_url": "..."}
    """
    import httpx
    import re

    log.info(f"[IG oEmbed] Fetching image URL from: {post_url}")

    # Extract short code from URL
    # https://www.instagram.com/p/DPvdidrkYGi/ -> DPvdidrkYGi
    short_code_match = re.search(r'/p/([^/]+)', post_url)
    if not short_code_match:
        return JSONResponse(
            {"detail": "Invalid Instagram post URL"},
            status_code=400
        )

    short_code = short_code_match.group(1)

    # Method 1: Try Instagram oEmbed API (no auth required for public posts)
    oembed_url = f"https://www.instagram.com/p/{short_code}/embed/captioned/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Fetch embed page (simpler than full page)
            response = await client.get(oembed_url, headers=headers)

            if response.status_code == 200:
                html = response.text

                # Extract image URL from embed page
                og_image_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
                if og_image_match:
                    image_url = og_image_match.group(1).replace('&amp;', '&')
                    log.info(f"[IG oEmbed] Found image URL ({len(image_url)} chars)")
                    return {
                        "image_url": image_url,
                        "post_url": post_url,
                        "source": "oembed"
                    }

            # Fallback: Try full post page
            response = await client.get(post_url, headers=headers)
            if response.status_code == 200:
                html = response.text

                og_image_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
                if og_image_match:
                    image_url = og_image_match.group(1).replace('&amp;', '&')
                    log.info(f"[IG Direct] Found image URL ({len(image_url)} chars)")
                    return {
                        "image_url": image_url,
                        "post_url": post_url,
                        "source": "direct"
                    }

            log.warning(f"[IG] Could not find image URL")
            return JSONResponse(
                {"detail": "Could not find image in Instagram page"},
                status_code=404
            )

    except Exception as e:
        log.error(f"[IG] Error: {e}")
        return JSONResponse(
            {"detail": "Failed to fetch image URL"},
            status_code=500
        )


# ============================================================================
# Blast Campaign Endpoints
# ============================================================================


@app.get("/blast/contacts")
async def blast_get_contacts(
    university_ids: Optional[str] = Query(None, description="Comma-separated university IDs"),
    search: Optional[str] = Query(None),
    province: Optional[str] = Query(None),
    has_name: Optional[bool] = Query(None),
    contacted: Optional[bool] = Query(None),
    has_conversation: Optional[bool] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
):
    """Get contacts available for blast selection with filters."""
    uid_list = None
    if university_ids:
        uid_list = [int(x.strip()) for x in university_ids.split(",") if x.strip().isdigit()]

    result = await blast_service.get_contacts_for_blast(
        university_ids=uid_list,
        search=search,
        province=province,
        has_name=has_name,
        contacted=contacted,
        has_conversation=has_conversation,
        limit=limit,
        offset=offset,
    )
    return result


@app.post("/blast/check-previously-blasted")
async def blast_check_previously_blasted(payload: dict):
    """Check which contacts have already been blasted (sent) in any campaign.

    Body: { contact_ids: [1, 2, 3] }           — check specific contacts
    OR:   { university_ids: [10, 20] }          — check all contacts from universities
    Returns: { previously_blasted: [{contact_id, phone_number, contact_name, university_name, campaign_name, sent_at}], total_contacts: N }
    """
    contact_ids = payload.get("contact_ids", [])
    university_ids = payload.get("university_ids", [])
    from orchestrator.db import get_db

    async with get_db() as db:
        # Resolve university_ids to contact_ids if needed
        if university_ids and not contact_ids:
            placeholders = ",".join("?" for _ in university_ids)
            cursor = await db.execute(
                f"SELECT id FROM ig_contacts WHERE university_id IN ({placeholders})",
                university_ids,
            )
            contact_ids = [r["id"] for r in await cursor.fetchall()]

        total_contacts = len(contact_ids)
        if not contact_ids:
            return {"previously_blasted": [], "total_contacts": 0}

        placeholders = ",".join("?" for _ in contact_ids)
        query = f"""SELECT DISTINCT
                    br.contact_id,
                    br.phone_number,
                    br.contact_name,
                    br.university_name,
                    bc.name as campaign_name,
                    br.sent_at
                FROM blast_recipients br
                JOIN blast_campaigns bc ON bc.id = br.campaign_id
                WHERE br.contact_id IN ({placeholders})
                  AND br.status = 'sent'
        """
        params: list[object] = list(contact_ids)
        query += " ORDER BY br.sent_at DESC"

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

    # Deduplicate by contact_id (keep the most recent blast)
    seen = {}
    for r in rows:
        cid = r["contact_id"]
        if cid not in seen:
            seen[cid] = dict(r)
    return {
        "previously_blasted": list(seen.values()),
        "total_contacts": total_contacts,
        "all_contact_ids": contact_ids,
    }


@app.post("/blast/campaigns")
async def blast_create_campaign(payload: dict, request: Request):
    """Create a new blast campaign.

    Body: { name, template_message?, device_id?, delay_between_ms?, human_delay_min_ms?, human_delay_max_ms?,
            content_variation_enabled?, schedule_enabled?, schedule_timezone?, active_hours_start?, active_hours_end?,
            peak_hours_start?, peak_hours_end?, lunch_break_start?, lunch_break_end?, weekend_factor?,
            auto_resume_enabled? }
    """
    name = payload.get("name", "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "Campaign name is required"}, status_code=400)

    current_user = await get_request_user(request)

    campaign = await blast_service.create_campaign(
        name=name,
        template_message=payload.get("template_message", ""),
        device_id=payload.get("device_id", "device_1"),
        delay_between_ms=payload.get("delay_between_ms", 5000),
        human_delay_min_ms=payload.get("human_delay_min_ms", 2000),
        human_delay_max_ms=payload.get("human_delay_max_ms", 8000),
        content_variation_enabled=payload.get("content_variation_enabled", True),
        schedule_enabled=payload.get("schedule_enabled", True),
        schedule_timezone=payload.get("schedule_timezone", "Asia/Jakarta"),
        active_hours_start=payload.get("active_hours_start", 8),
        active_hours_end=payload.get("active_hours_end", 21),
        peak_hours_start=payload.get("peak_hours_start", 10),
        peak_hours_end=payload.get("peak_hours_end", 14),
        lunch_break_start=payload.get("lunch_break_start", 12),
        lunch_break_end=payload.get("lunch_break_end", 13),
        weekend_factor=payload.get("weekend_factor", 0.5),
        auto_resume_enabled=payload.get("auto_resume_enabled", True),
        created_by_dms_user_id=current_user.get("dms_user_id"),
        created_by_email=current_user.get("email"),
        created_by_name=_campaign_actor_name(current_user),
    )
    return {"success": True, "campaign": campaign}


@app.get("/blast/campaigns")
async def blast_list_campaigns(
    status: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """List all blast campaigns."""
    return await blast_service.list_campaigns(
        status=status,
        limit=limit,
        offset=offset,
    )


@app.get("/blast/campaigns/{campaign_id}")
async def blast_get_campaign(campaign_id: int, request: Request):
    """Get campaign detail."""
    campaign = await _require_blast_campaign_access(campaign_id)
    return campaign


@app.put("/blast/campaigns/{campaign_id}")
async def blast_update_campaign(campaign_id: int, payload: dict, request: Request):
    """Update campaign settings.

    Body: { name?, template_message?, device_id?, delay_between_ms?, human_delay_min_ms?, human_delay_max_ms?,
            content_variation_enabled?, schedule_enabled?, schedule_timezone?, active_hours_start?, active_hours_end?,
            peak_hours_start?, peak_hours_end?, lunch_break_start?, lunch_break_end?, weekend_factor?,
            auto_resume_enabled? }
    """
    await _require_blast_campaign_access(campaign_id)

    campaign = await blast_service.update_campaign(campaign_id, **payload)
    if not campaign:
        return JSONResponse({"detail": "Campaign not found"}, status_code=404)
    return {"success": True, "campaign": campaign}


@app.delete("/blast/campaigns/{campaign_id}")
async def blast_delete_campaign(campaign_id: int, request: Request):
    """Delete a draft/completed/cancelled campaign."""
    await _require_blast_campaign_access(campaign_id)

    deleted = await blast_service.delete_campaign(campaign_id)
    if not deleted:
        return JSONResponse(
            {"detail": "Campaign not found or cannot be deleted (must be draft/completed/cancelled)"},
            status_code=400,
        )
    return {"success": True}


@app.post("/blast/campaigns/{campaign_id}/recipients")
async def blast_add_recipients(campaign_id: int, payload: dict, request: Request):
    """Add recipients to a campaign.

    Body: { contact_ids: [1,2,3] }  — from ig_contacts
    OR:   { university_ids: [10,20] } — all contacts from these universities
    OR:   { recipients: [{phone_number, contact_name?, university_name?, university_id?, contact_id?}] }
    OR:   { group_ids: [1,2] } — all universities from these groups
    """
    await _require_blast_campaign_access(campaign_id)

    contact_ids = payload.get("contact_ids", [])
    university_ids = payload.get("university_ids", [])
    recipients = payload.get("recipients", [])
    group_ids = payload.get("group_ids", [])

    if contact_ids:
        result = await blast_service.add_recipients_from_contacts(campaign_id, contact_ids)
    elif university_ids:
        result = await blast_service.add_recipients_from_universities(campaign_id, university_ids)
    elif recipients:
        result = await blast_service.add_recipients_bulk(campaign_id, recipients)
    elif group_ids:
        from orchestrator.university_groups import get_university_ids_from_groups
        resolved_ids = await get_university_ids_from_groups(group_ids)
        result = await blast_service.add_recipients_from_universities(campaign_id, resolved_ids)
    else:
        return JSONResponse({"success": False, "error": "Provide contact_ids, university_ids, recipients, or group_ids"}, status_code=400)

    return {"success": True, **result}


@app.get("/blast/campaigns/{campaign_id}/recipients")
async def blast_get_recipients(
    campaign_id: int,
    request: Request,
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
):
    """Get recipients of a campaign."""
    await _require_blast_campaign_access(campaign_id)
    return await blast_service.get_recipients(campaign_id, status=status, limit=limit, offset=offset)


@app.delete("/blast/campaigns/{campaign_id}/recipients/{recipient_id}")
async def blast_remove_recipient(campaign_id: int, recipient_id: int, request: Request):
    """Remove a pending recipient."""
    await _require_blast_campaign_access(campaign_id)

    removed = await blast_service.remove_recipient(campaign_id, recipient_id)
    if not removed:
        return JSONResponse({"detail": "Recipient not found or already sent"}, status_code=400)
    return {"success": True}


@app.delete("/blast/campaigns/{campaign_id}/recipients")
async def blast_clear_recipients(campaign_id: int, request: Request):
    """Remove all pending recipients from a campaign."""
    await _require_blast_campaign_access(campaign_id)

    removed = await blast_service.clear_recipients(campaign_id)
    return {"success": True, "removed": removed}


@app.get("/blast/campaigns/{campaign_id}/preview")
async def blast_preview_messages(campaign_id: int, request: Request, limit: int = Query(3)):
    """Preview rendered messages for a few recipients."""
    await _require_blast_campaign_access(campaign_id)

    previews = await blast_service.preview_messages(campaign_id, limit=limit)
    return {"previews": previews}


@app.post("/blast/campaigns/{campaign_id}/start")
async def blast_start_campaign(campaign_id: int, request: Request):
    """Start or resume sending a blast campaign."""
    current_user = await get_request_user(request)
    await _require_blast_campaign_access(campaign_id)

    result = await blast_service.start_campaign(
        campaign_id,
        started_by_dms_user_id=current_user.get("dms_user_id"),
        started_by_email=current_user.get("email"),
        started_by_name=_campaign_actor_name(current_user),
    )
    if not result.get("success"):
        return JSONResponse(result, status_code=400)
    return result


@app.post("/blast/campaigns/{campaign_id}/pause")
async def blast_pause_campaign(campaign_id: int, request: Request):
    """Pause a running campaign."""
    await _require_blast_campaign_access(campaign_id)

    result = await blast_service.pause_campaign(campaign_id)
    if not result.get("success"):
        return JSONResponse(result, status_code=400)
    return result


@app.post("/blast/campaigns/{campaign_id}/cancel")
async def blast_cancel_campaign(campaign_id: int, request: Request):
    """Cancel a campaign."""
    await _require_blast_campaign_access(campaign_id)

    result = await blast_service.cancel_campaign(campaign_id)
    if not result.get("success"):
        return JSONResponse(result, status_code=400)
    return result


# ---------------------------------------------------------------------------
# Email Blast Endpoints
# ---------------------------------------------------------------------------

class EmailBlastCampaignCreate(BaseModel):
    name: str
    subject: str = ""
    template_message: str = ""
    from_email: str | None = None
    from_name: str | None = None
    delay_between_ms: int | None = None


class EmailBlastStartRequest(BaseModel):
    max_recipients: int | None = None


@app.post("/email-blast/campaigns")
async def create_email_campaign(payload: EmailBlastCampaignCreate, request: Request):
    """Create new email blast campaign."""
    current_user = await get_request_user(request)
    campaign_id = await email_blast.create_email_campaign(
        name=payload.name,
        subject=payload.subject,
        template=payload.template_message,
        from_email=payload.from_email or "sekretariat@asosiasi.ai",
        from_name=payload.from_name or "Sekretariat Asosiasi AI",
        delay_ms=payload.delay_between_ms or 20_000,
        created_by_dms_user_id=current_user.get("dms_user_id"),
        created_by_email=current_user.get("email"),
        created_by_name=_campaign_actor_name(current_user),
    )
    return {"success": True, "campaign_id": campaign_id}


@app.get("/email-blast/campaigns")
async def list_email_campaigns(request: Request, status: str | None = None):
    """List email blast campaigns."""
    campaigns = await email_blast.list_campaigns(status)
    return {"success": True, "campaigns": campaigns}


@app.get("/email-blast/campaigns/{campaign_id}")
async def get_email_campaign(campaign_id: int, request: Request):
    """Get email campaign details."""
    campaign = await _require_email_campaign_access(campaign_id)
    return {"success": True, "campaign": campaign}


@app.patch("/email-blast/campaigns/{campaign_id}")
async def update_email_campaign(campaign_id: int, payload: dict, request: Request):
    """Update email campaign details."""
    await _require_email_campaign_access(campaign_id)

    async with get_db() as db:
        updates = []
        params = []

        if 'name' in payload:
            updates.append("name = ?")
            params.append(payload['name'])
        if 'subject' in payload:
            updates.append("subject = ?")
            params.append(payload['subject'])
        if 'template_message' in payload:
            updates.append("template_message = ?")
            params.append(payload['template_message'])
        if 'delay_between_ms' in payload:
            updates.append("delay_between_ms = ?")
            params.append(payload['delay_between_ms'])

        if not updates:
            return {"success": False, "error": "No fields to update"}

        params.append(campaign_id)
        query = f"UPDATE email_blast_campaigns SET {', '.join(updates)} WHERE id = ?"
        await db.execute(query, params)
        await db.commit()

    campaign = await email_blast.get_campaign_status(campaign_id)
    return {"success": True, "campaign": campaign}


@app.post("/email-blast/campaigns/{campaign_id}/recipients/add-all")
async def add_all_recipients_to_email_campaign(
    campaign_id: int,
    request: Request,
    payload: dict | None = None,
):
    """Add all universities with emails as recipients."""
    await _require_email_campaign_access(campaign_id)

    provinces = payload.get("provinces") if payload else None
    count = await email_blast.add_all_emails_to_campaign(campaign_id, provinces)
    return {"success": True, "recipients_added": count}


@app.post("/email-blast/campaigns/{campaign_id}/recipients/add")
async def add_selected_recipients(
    campaign_id: int,
    payload: dict,
    request: Request,
):
    """Add selected universities as recipients.
    Body: { university_ids: [...] }  — specific universities
    OR:   { group_ids: [...] } — all universities from these groups
    """
    await _require_email_campaign_access(campaign_id)

    university_ids = payload.get("university_ids", [])
    group_ids = payload.get("group_ids", [])

    if group_ids:
        from orchestrator.university_groups import get_university_ids_from_groups
        resolved_ids = await get_university_ids_from_groups(group_ids)
        count = await email_blast.add_recipients_to_campaign(campaign_id, resolved_ids)
    elif university_ids:
        count = await email_blast.add_recipients_to_campaign(campaign_id, university_ids)
    else:
        return JSONResponse({"success": False, "error": "Provide university_ids or group_ids"}, status_code=400)

    return {"success": True, "recipients_added": count}


@app.post("/email-blast/campaigns/{campaign_id}/start")
async def start_email_campaign(campaign_id: int, payload: EmailBlastStartRequest, request: Request):
    """Start email blast campaign."""
    current_user = await get_request_user(request)
    await _require_email_campaign_access(campaign_id)

    async with get_db() as db:
        await db.execute(
            """UPDATE email_blast_campaigns
               SET status = 'running',
                   started_at = datetime('now'),
                   started_by_dms_user_id = ?,
                   started_by_email = ?,
                   started_by_name = ?
               WHERE id = ?""",
            (
                current_user.get("dms_user_id"),
                current_user.get("email"),
                _campaign_actor_name(current_user),
                campaign_id,
            )
        )
        await db.commit()

    await email_blast.broadcast_campaign_update(campaign_id)

    # Run async
    asyncio.create_task(
        email_blast.run_email_blast_campaign(
            campaign_id,
            max_recipients=payload.max_recipients
        )
    )

    return {"success": True, "message": "Campaign started"}


@app.post("/email-blast/campaigns/{campaign_id}/pause")
async def pause_email_campaign(campaign_id: int, request: Request):
    """Pause email campaign."""
    await _require_email_campaign_access(campaign_id)

    await email_blast.pause_campaign(campaign_id)
    return {"success": True, "message": "Campaign paused"}


@app.post("/email-blast/campaigns/{campaign_id}/cancel")
async def cancel_email_campaign(campaign_id: int, request: Request):
    """Cancel email campaign."""
    await _require_email_campaign_access(campaign_id)

    await email_blast.cancel_campaign(campaign_id)
    return {"success": True, "message": "Campaign cancelled"}


@app.post("/email-blast/campaigns/{campaign_id}/retry-failed")
async def retry_failed_email_campaign(campaign_id: int, payload: EmailBlastStartRequest, request: Request):
    """Retry sending emails to failed recipients in a campaign."""
    current_user = await get_request_user(request)
    await _require_email_campaign_access(campaign_id)

    async with get_db() as db:
        await db.execute(
            """UPDATE email_blast_campaigns
               SET status = 'running',
                   started_at = datetime('now'),
                   completed_at = NULL,
                   paused_at = NULL,
                   started_by_dms_user_id = ?,
                   started_by_email = ?,
                   started_by_name = ?
               WHERE id = ?""",
            (
                current_user.get("dms_user_id"),
                current_user.get("email"),
                _campaign_actor_name(current_user),
                campaign_id,
            )
        )
        # Count failed recipients
        cursor = await db.execute(
            "SELECT COUNT(*) FROM email_blast_recipients WHERE campaign_id = ? AND status = 'failed'",
            (campaign_id,)
        )
        row = await cursor.fetchone()
        failed_count = row[0] if row else 0

        if failed_count == 0:
            return {"success": True, "message": "No failed recipients to retry", "recipients_retried": 0}

        # Reset failed recipients to pending
        await db.execute(
            "UPDATE email_blast_recipients SET status = 'pending', error_message = NULL WHERE campaign_id = ? AND status = 'failed'",
            (campaign_id,)
        )
        await db.commit()

    await email_blast.broadcast_campaign_update(campaign_id)

    # Run async with only failed (now-pending) recipients
    asyncio.create_task(
        email_blast.retry_failed_email_blast(campaign_id, max_recipients=payload.max_recipients)
    )

    return {"success": True, "message": f"Retrying {failed_count} failed emails", "recipients_retried": failed_count}


@app.post("/email-blast/campaigns/{campaign_id}/sync-counters")
async def sync_email_blast_counters(campaign_id: int, request: Request):
    """Force-recalculate sent_count, failed_count, and total_recipients from the actual
    recipient table. Use when counters have drifted from reality (e.g. after a crash or
    concurrent run). Returns the corrected counters."""
    await _require_email_campaign_access(campaign_id)

    result = await email_blast.sync_campaign_counters(campaign_id)
    return {"success": True, "campaign_id": campaign_id, **result}


class EmailBlastTestEmailRequest(BaseModel):
    to_email: str
    subject: str | None = None
    body: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    attachment_filename: str | None = None
    custom_vars: dict | None = None


@app.post("/email-blast/campaigns/{campaign_id}/test-email")
async def send_test_email(campaign_id: int, payload: EmailBlastTestEmailRequest, request: Request):
    """Send a test email to validate campaign template and SMTP connection."""
    await _require_email_campaign_access(campaign_id)

    success, message = await email_blast.send_test_email(
        campaign_id,
        payload.to_email,
        subject=payload.subject,
        body=payload.body,
        from_email=payload.from_email,
        from_name=payload.from_name,
        attachment_filename=payload.attachment_filename,
        custom_vars=payload.custom_vars
    )
    if success:
        return {"success": True, "message": message}
    return JSONResponse({"success": False, "message": message}, status_code=400)



@app.get("/email-blast/campaigns/{campaign_id}/recipients")
async def get_email_recipients(campaign_id: int, request: Request, status: str | None = None):
    """Get recipients of an email campaign."""
    await _require_email_campaign_access(campaign_id)

    async with get_db() as db:
        query = """SELECT id, university_id, email, university_name, status, error_message,
                          sent_at, rendered_subject, rendered_message, letter_number
                   FROM email_blast_recipients WHERE campaign_id = ?"""
        params = [campaign_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        cursor = await db.execute(query + " ORDER BY id", params)
        recipients = await cursor.fetchall()

        return {
            "success": True,
            "recipients": [
                {
                    "id": r[0],
                    "university_id": r[1],
                    "email": r[2],
                    "university_name": r[3],
                    "status": r[4],
                    "error_message": r[5],
                    "sent_at": r[6],
                    "rendered_subject": r[7],
                    "rendered_message": r[8],
                    "letter_number": r[9],
                }
                for r in recipients
            ]
        }


@app.delete("/email-blast/campaigns/{campaign_id}/recipients/{recipient_id}")
async def delete_email_recipient(campaign_id: int, recipient_id: int, request: Request):
    """Delete a recipient from campaign"""
    from orchestrator.email_blast import delete_recipient

    await _require_email_campaign_access(campaign_id)

    success = await delete_recipient(recipient_id, campaign_id=campaign_id)
    if success:
        return {"success": True, "message": "Recipient deleted"}
    return {"success": False, "message": "Recipient not found"}


@app.get("/email-blast/campaigns/{campaign_id}/sent-emails")
async def get_sent_emails(campaign_id: int, request: Request, status: str = None):
    """Get sent emails for a campaign"""
    from orchestrator.db import get_db

    await _require_email_campaign_access(campaign_id)

    query = """SELECT r.id, r.email, r.university_name, r.rendered_subject, r.rendered_message,
                      r.status, r.sent_at, r.error_message,
                      c.name as campaign_name, c.started_by_email, c.started_by_name,
                      c.created_by_email, c.created_by_name,
                      COALESCE(
                          (SELECT o.from_email FROM email_outbox o
                           WHERE o.recipient_id = r.id
                           ORDER BY o.sent_at DESC, o.id DESC
                           LIMIT 1),
                          c.from_email
                      ) as from_email,
                      COALESCE(
                          (SELECT o.from_name FROM email_outbox o
                           WHERE o.recipient_id = r.id
                           ORDER BY o.sent_at DESC, o.id DESC
                           LIMIT 1),
                          c.from_name
                      ) as from_name
               FROM email_blast_recipients r
               JOIN email_blast_campaigns c ON c.id = r.campaign_id
               WHERE r.campaign_id = ? AND r.sent_at IS NOT NULL"""
    params = [campaign_id]

    if status:
        query += " AND r.status = ?"
        params.append(status)

    query += " ORDER BY r.sent_at DESC"

    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

    emails = []
    for row in rows:
        emails.append({
            "id": row[0],
            "email": row[1],
            "university_name": row[2],
            "subject": row[3],
            "body": row[4],
            "status": row[5],
            "sent_at": row[6],
            "error_message": row[7],
            "campaign_name": row[8],
            "started_by_email": row[9],
            "started_by_name": row[10],
            "created_by_email": row[11],
            "created_by_name": row[12],
            "from_email": row[13],
            "from_name": row[14],
        })

    return {"success": True, "emails": emails, "total": len(emails)}


@app.get("/email-blast/campaigns/{campaign_id}/sent-emails/{email_id}")
async def get_sent_email(campaign_id: int, email_id: int, request: Request):
    """Get a specific sent email details"""
    from orchestrator.db import get_db

    await _require_email_campaign_access(campaign_id)

    async with get_db() as db:
        cursor = await db.execute(
            """SELECT r.id, r.email, r.university_name, r.rendered_subject, r.rendered_message,
                      r.status, r.sent_at, r.error_message,
                      COALESCE(
                          (SELECT o.from_email FROM email_outbox o
                           WHERE o.recipient_id = r.id
                           ORDER BY o.sent_at DESC, o.id DESC
                           LIMIT 1),
                          c.from_email
                      ) as from_email,
                      COALESCE(
                          (SELECT o.from_name FROM email_outbox o
                           WHERE o.recipient_id = r.id
                           ORDER BY o.sent_at DESC, o.id DESC
                           LIMIT 1),
                          c.from_name
                      ) as from_name
               FROM email_blast_recipients r
               JOIN email_blast_campaigns c ON c.id = r.campaign_id
               WHERE r.id = ? AND r.campaign_id = ?""",
            (email_id, campaign_id)
        )
        row = await cursor.fetchone()

    if not row:
        return {"success": False, "message": "Email not found"}

    return {
        "success": True,
        "email": {
            "id": row[0],
            "email": row[1],
            "university_name": row[2],
            "subject": row[3],
            "body": row[4],
            "status": row[5],
            "sent_at": row[6],
            "error_message": row[7],
            "from_email": row[8],
            "from_name": row[9],
        }
    }


@app.get("/email-blast/campaigns/{campaign_id}/inbox")
async def get_inbox_emails(campaign_id: int, request: Request, limit: int = 50, offset: int = 0):
    """Get inbound emails (replies) for a campaign with pagination"""
    from orchestrator import email_blast

    await _require_email_campaign_access(campaign_id)

    replies, total = await email_blast.get_campaign_replies(campaign_id, limit)
    return {"success": True, "emails": replies, "total": total, "offset": offset, "limit": limit}


@app.get("/email-blast/inbox")
async def get_all_inbox_emails(request: Request, limit: int = 50, offset: int = 0):
    """Get all inbound emails from INBOX with pagination"""
    from orchestrator import email_blast

    emails, total = await email_blast.fetch_inbox_emails(limit, offset=offset)
    return {"success": True, "emails": emails, "total": total, "offset": offset, "limit": limit}


@app.get("/email-blast/sent-emails")
async def get_all_sent_emails(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    status: str = None
):
    """Get all sent emails across all campaigns with pagination"""
    from orchestrator.db import get_db

    # Query from email_outbox (captures campaign emails + test emails)
    count_query = "SELECT COUNT(*) FROM email_outbox"
    count_params: list = []
    if status:
        count_query += " WHERE status = ?"
        count_params.append(status)

    async with get_db() as db:
        count_cursor = await db.execute(count_query, count_params)
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0

        data_query = """SELECT o.id, o.email, o.university_name, o.from_email, o.from_name,
                   o.rendered_subject, o.rendered_message, o.status, o.sent_at, o.error_message,
                       c.name as campaign_name, o.source,
                       c.started_by_email, c.started_by_name,
                       c.created_by_email, c.created_by_name
                        FROM email_outbox o
                        LEFT JOIN email_blast_campaigns c ON o.campaign_id = c.id"""
        data_params: list = []
        if status:
            data_query += " WHERE o.status = ?"
            data_params.append(status)
        data_query += " ORDER BY o.sent_at DESC LIMIT ? OFFSET ?"
        data_params.extend([limit, offset])

        cursor = await db.execute(data_query, data_params)
        rows = await cursor.fetchall()

    emails = []
    for row in rows:
        emails.append({
            "id": row[0],
            "email": row[1],
            "university_name": row[2],
            "from_email": row[3],
            "from_name": row[4],
            "subject": row[5],
            "body": row[6],
            "status": row[7],
            "sent_at": row[8],
            "error_message": row[9],
            "campaign_name": row[10],
            "source": row[11],
            "started_by_email": row[12],
            "started_by_name": row[13],
            "created_by_email": row[14],
            "created_by_name": row[15],
        })

    return {"success": True, "emails": emails, "total": total, "offset": offset, "limit": limit}


@app.get("/email-blast/sent-folder")
async def get_sent_folder_emails(request: Request, limit: int = 50, offset: int = 0):
    """Get emails from the Sent folder (IMAP) with pagination."""
    from orchestrator import email_blast

    emails, total = await email_blast.fetch_sent_emails(limit, offset)
    return {"success": True, "emails": emails, "total": total, "offset": offset, "limit": limit}


@app.post("/email-blast/test-smtp")
async def test_smtp_connection(request: Request):
    """Test SMTP connection."""
    smtp = email_blast.get_smtp_client()
    success = smtp.connect()
    smtp.disconnect()
    return {"success": success, "message": "SMTP connected" if success else "SMTP failed"}


@app.get("/email-blast/quota")
async def get_email_blast_quota():
    """Get today's email blast quota usage."""
    daily_limit = cfg.get("EMAIL_BLAST_DAILY_LIMIT", 200)
    quota = await get_email_blast_quota_info(daily_limit)
    return quota


@app.post("/email-blast/test-imap")
async def test_imap_connection(request: Request):
    """Test IMAP connection."""
    from orchestrator import email_blast

    conn = email_blast.get_imap_connection()
    if conn:
        conn.close()
        conn.logout()
        return {"success": True, "message": "IMAP connected successfully"}
    return {"success": False, "message": "IMAP connection failed - check credentials and host"}


@app.get("/email-blast/test-inbox")
async def test_inbox_fetch(request: Request, limit: int = 10):
    """Test fetching from INBOX - debug endpoint."""
    from orchestrator import email_blast

    emails, total = await email_blast.fetch_inbox_emails(limit=limit)
    return {
        "success": True,
        "message": f"Found {total} emails",
        "emails": emails
    }


@app.get("/email-blast/debug-campaign-replies/{campaign_id}")
async def debug_campaign_replies(campaign_id: int, request: Request):
    """Debug endpoint to see campaign recipients and matching inbox emails."""
    from orchestrator import email_blast

    # Get recipient emails
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, email, university_name FROM email_blast_recipients WHERE campaign_id = ?",
            (campaign_id,)
        )
        rows = await cursor.fetchall()
        recipient_emails = [{'id': row[0], 'email': row[1], 'name': row[2]} for row in rows]

    # Fetch inbox
    all_inbox, _ = await email_blast.fetch_inbox_emails(limit=100)

    # Debug matching
    matched = []
    for inbox_email in all_inbox:
        from_email = inbox_email.get('from_email', '').lower()
        for recipient in recipient_emails:
            if from_email == recipient['email'].lower():
                matched.append({
                    'inbox_email': inbox_email,
                    'matched_recipient': recipient
                })
                break

    return {
        "success": True,
        "campaign_id": campaign_id,
        "recipient_emails": recipient_emails,
        "inbox_count": len(all_inbox),
        "matched_count": len(matched),
        "matched": matched
    }


@app.post("/email-blast/campaigns/{campaign_id}/attachment")
async def upload_attachment(
    campaign_id: int,
    request: Request,
    file: UploadFile = FastAPIFile(...),
    variables: str = Form("")
):
    """Upload DOCX template and set variables for campaign"""
    try:
        from orchestrator.email_blast import TEMPLATE_DIR, extract_docx_variables, save_campaign_attachment

        await _require_email_campaign_access(campaign_id)

        # Validate file type
        if not file.filename.endswith('.docx'):
            raise HTTPException(status_code=400, detail="Only .docx files allowed")

        # Save uploaded file
        filename = f"{campaign_id}_{file.filename}"
        filepath = TEMPLATE_DIR / filename

        content = await file.read()
        with open(filepath, 'wb') as f:
            f.write(content)

        # Extract variables from document
        detected_vars = extract_docx_variables(str(filepath))

        # Auto-generated variables (should NOT be shown as user input)
        AUTO_VARS = {"university_name", "email", "tanggal", "nomor_surat"}

        # Filter out auto-generated variables - only show custom variables
        custom_vars = [v for v in detected_vars if v not in AUTO_VARS]

        # Parse user-provided variables (JSON string like {"nomor_surat": "123/2024"})
        user_vars = {}
        if variables:
            try:
                user_vars = _json.loads(variables)
            except:
                pass

        # Merge: custom detected + user (user overrides detected if same key)
        all_vars = {v: "" for v in custom_vars}
        all_vars.update(user_vars)

        # Save to campaign
        await save_campaign_attachment(campaign_id, filename, _json.dumps(all_vars))

        return {
            "success": True,
            "filename": filename,
            "variables": all_vars,
            "detected_variables": detected_vars
        }
    except Exception as e:
        log.error(f"[EmailBlast] Error uploading attachment: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error uploading attachment: {str(e)}")

    return {
        "success": True,
        "filename": filename,
        "variables": all_vars,
        "detected_variables": detected_vars
    }


@app.get("/email-blast/campaigns/{campaign_id}/attachment")
async def get_attachment(campaign_id: int, request: Request):
    """Get attachment info for campaign"""
    from orchestrator.email_blast import get_campaign_attachment

    await _require_email_campaign_access(campaign_id)

    attachment = await get_campaign_attachment(campaign_id)
    return {
        "success": True,
        "filename": attachment['filename'],
        "variables": attachment['variables'],
        "detected_variables": attachment.get('detected_variables', [])
    }


@app.get("/email-blast/letter-config")
async def get_letter_config():
    """Get letter number configuration"""
    from orchestrator.email_blast import get_letter_config

    config = await get_letter_config()
    return {
        "success": True,
        "format_template": config['format_template'],
        "last_number": config['last_number']
    }


@app.post("/email-blast/letter-config")
async def update_letter_config(request: Request):
    """Update letter number configuration"""
    from orchestrator.email_blast import update_letter_config

    body = await request.json()
    format_template = body.get('format_template')
    last_number = body.get('last_number')

    config = await update_letter_config(format_template, last_number)
    return {
        "success": True,
        "format_template": config['format_template'],
        "last_number": config['last_number']
    }


@app.get("/email-blast/letter-history")
async def get_letter_history(
    request: Request,
    campaign_id: int | None = None,
    duplicate_only: bool = False,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    Get all sent letters with letter numbers.
    Highlights duplicates for easy identification.
    """
    if campaign_id is not None:
        await _require_email_campaign_access(campaign_id)

    async with get_db() as db:
        # Base query — only sent recipients with letter_number
        base_cols = """
            r.id, r.campaign_id, c.name as campaign_name,
            r.letter_number, r.university_name, r.email, r.sent_at,
            c.started_by_email, c.started_by_name,
            c.created_by_email, c.created_by_name
        """
        query = f"""
            SELECT {base_cols}
            FROM email_blast_recipients r
            JOIN email_blast_campaigns c ON c.id = r.campaign_id
            WHERE r.status = 'sent'
              AND r.letter_number IS NOT NULL
              AND r.letter_number != ''
        """
        count_query = """
            SELECT COUNT(*) FROM email_blast_recipients r
            JOIN email_blast_campaigns c ON c.id = r.campaign_id
            WHERE r.status = 'sent'
              AND r.letter_number IS NOT NULL
              AND r.letter_number != ''
        """
        params: list = []

        if campaign_id is not None:
            query += " AND r.campaign_id = ?"
            count_query += " AND r.campaign_id = ?"
            params.append(campaign_id)

        if search:
            query += " AND (r.letter_number LIKE ? OR r.university_name LIKE ? OR r.email LIKE ? OR c.name LIKE ? OR c.started_by_name LIKE ? OR c.started_by_email LIKE ?)"
            count_query += " AND (r.letter_number LIKE ? OR r.university_name LIKE ? OR r.email LIKE ? OR c.name LIKE ? OR c.started_by_name LIKE ? OR c.started_by_email LIKE ?)"
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern, pattern, pattern, pattern])

        query += " ORDER BY r.sent_at DESC"

        # Get all rows (needed for duplicate detection)
        rows_query = f"SELECT {base_cols} FROM email_blast_recipients r JOIN email_blast_campaigns c ON c.id = r.campaign_id WHERE r.status = 'sent' AND r.letter_number IS NOT NULL AND r.letter_number != ''"
        if campaign_id is not None:
            rows_query += " AND r.campaign_id = ?"
        if search:
            rows_query += " AND (r.letter_number LIKE ? OR r.university_name LIKE ? OR r.email LIKE ? OR c.name LIKE ? OR c.started_by_name LIKE ? OR c.started_by_email LIKE ?)"
        rows_query += " ORDER BY r.sent_at DESC"

        async with get_db() as db2:
            all_cursor = await db2.execute(rows_query, params)
            all_rows = await all_cursor.fetchall()

        # Detect duplicates: same letter_number appearing more than once
        letter_count: dict[str, int] = {}
        for row in all_rows:
            ln = row[3]  # letter_number
            if ln:
                letter_count[ln] = letter_count.get(ln, 0) + 1

        duplicate_letters = {ln for ln, cnt in letter_count.items() if cnt > 1}

        # Apply duplicate filter
        if duplicate_only:
            filtered_rows = [r for r in all_rows if r[3] in duplicate_letters]
            total = len(filtered_rows)
        else:
            total = len(all_rows)
            filtered_rows = all_rows

        # Apply pagination
        paginated = filtered_rows[offset:offset + limit]

        items = [
            {
                "id": row[0],
                "campaign_id": row[1],
                "campaign_name": row[2],
                "letter_number": row[3],
                "university_name": row[4],
                "email": row[5],
                "sent_at": row[6],
                "started_by_email": row[7],
                "started_by_name": row[8],
                "created_by_email": row[9],
                "created_by_name": row[10],
                "is_duplicate": row[3] in duplicate_letters,
            }
            for row in paginated
        ]

        duplicate_count = sum(cnt for ln, cnt in letter_count.items() if cnt > 1)

        return {
            "success": True,
            "items": items,
            "total": total,
            "duplicate_count": duplicate_count,
            "limit": limit,
            "offset": offset,
        }
