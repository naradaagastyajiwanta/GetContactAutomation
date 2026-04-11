"""Sentry error tracking + performance monitoring + logs + profiling.

This module wires the orchestrator into Sentry.io for:

* **Unhandled exception capture** — every uncaught error becomes a
  Sentry issue with full stack trace, request context, and tags.
* **Performance tracing** (sampled) — FastAPI endpoint duration, httpx
  outbound calls, asyncio task spans.
* **Breadcrumbs** — log messages and HTTP requests up to the point of
  failure, useful for debugging root causes.
* **Structured logs** (optional, opt-in via ``SENTRY_ENABLE_LOGS=true``)
  — forward ``sentry_sdk.logger.*`` calls as structured log events to
  the Sentry Logs product. Burns extra quota; disabled by default.
* **Continuous profiling** (optional, opt-in via
  ``SENTRY_PROFILE_SESSION_SAMPLE_RATE > 0``) — flame graphs of code
  hotspots during active transactions. Disabled by default because
  profiling burns performance-unit quota quickly.
* **PII scrubbing** — access tokens, API keys, phone numbers, and
  auth headers are stripped before events are sent to Sentry.

Activation is env-var driven. When ``SENTRY_DSN`` is unset or empty,
``init_sentry()`` is a silent no-op — the orchestrator runs exactly as
before, no dependencies on Sentry availability. This means you can
deploy this module BEFORE creating a Sentry account without breaking
anything, and activate later just by adding ``SENTRY_DSN=...`` to
``.env.production``.

Environment variables
---------------------

Required:

* ``SENTRY_DSN`` — Project DSN from sentry.io. Empty → Sentry off.

Core config:

* ``SENTRY_ENVIRONMENT`` — e.g. ``production``/``staging``/``development``
  (default: ``production``)
* ``SENTRY_RELEASE`` — release identifier, usually ``$CI_COMMIT_SHORT_SHA``
  (default: empty → no release correlation)
* ``SENTRY_TRACES_SAMPLE_RATE`` — float ``0.0-1.0`` controlling % of
  transactions to trace for performance monitoring. Default ``0.1``
  (10%). Set to ``1.0`` only if you have a paid tier — full sampling
  burns the free-tier 10K perf-units/month budget quickly.

Advanced opt-ins (all default OFF to protect free-tier budget):

* ``SENTRY_ENABLE_LOGS`` — ``true``/``false``, default ``false``.
  Enables the Sentry Logs product (``sentry_sdk.logger.*`` API +
  auto-forward of Python ``logging`` at INFO+). Quota: separate
  from errors/traces.
* ``SENTRY_PROFILE_SESSION_SAMPLE_RATE`` — float ``0.0-1.0``, default
  ``0.0`` (profiling off). Set to e.g. ``0.1`` to profile 10% of
  sessions with flame graphs.
* ``SENTRY_PROFILE_LIFECYCLE`` — ``manual`` or ``trace``, default
  ``trace``. Only meaningful when profiling is enabled. ``trace``
  means profiler runs automatically whenever a transaction is active.
* ``SENTRY_SEND_DEFAULT_PII`` — ``true``/``false``, default ``false``.
  **Kept at false** by default because this app handles sensitive
  data (OAuth tokens, Indonesian phone numbers, email targets).
  Setting True would make Sentry auto-include request.headers,
  request.body, and user.ip — our scrubber would then have to defend
  against them. Safer to never collect in the first place.

Call :func:`init_sentry` as early as possible in the FastAPI ``lifespan``
startup. Any exceptions raised before init will not be captured — this
is a fundamental Sentry limitation (module import errors escape any
error tracker that hasn't initialized yet).
"""
from __future__ import annotations

import os
from typing import Any

# NOTE: Sentry SDK import is deferred until inside init_sentry() so
# importing this module does NOT require sentry-sdk to be installed.
# Orchestrator keeps booting even if sentry-sdk is missing (e.g. an
# out-of-sync requirements.txt on a stale Docker image).


# --- Sensitive data scrubbing -----------------------------------------------
#
# These keys are stripped from any event payload before it leaves our
# process. Matching is case-insensitive on the exact key name — we do
# NOT substring-match because that would catch legitimate keys like
# ``account_id`` (has "id"). Keep the set tight and explicit.

_SENSITIVE_KEYS = frozenset(
    k.lower()
    for k in (
        # Auth / credentials
        "password", "api_key", "apikey",
        "access_token", "refresh_token", "id_token", "raw_id_token",
        "authorization", "cookie", "set-cookie",
        "auth_cookie_name", "auth_session_token", "session_token",
        # Service-specific secrets
        "openai_api_key", "gemini_api_key", "serper_api_key",
        "sentry_dsn", "sentry_auth_token",
        "dms_mysql_password", "smtp_password", "imap_password",
        "vps_password", "deploy_token_pass",
        "gcs_service_account_json", "service_account_json",
        "scrapingbot_api_key", "apify_api_key",
        "chatgpt_account_id", "chatgpt-account-id",
        "ig_session_id", "ig_password", "sessionid",
        # Headers (case-insensitive already lowered)
        "x-api-key", "x-auth-token",
    )
)

# Email + phone regexes — applied to freeform string values in breadcrumb
# messages and exception messages. Redacted to first char + suffix so
# the shape is preserved for debugging but identity is not leaked.
import re

_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RE_PHONE_ID = re.compile(r"\b(?:\+?62|0)8\d{8,12}\b")  # Indonesian mobile


def _mask_pii_in_string(text: str) -> str:
    """Redact emails and Indonesian phone numbers from a freeform string."""
    text = _RE_EMAIL.sub("[email-redacted]", text)
    text = _RE_PHONE_ID.sub("[phone-redacted]", text)
    return text


def _scrub(obj: Any) -> Any:
    """Recursively redact sensitive dict keys + mask PII in strings."""
    if isinstance(obj, dict):
        return {
            k: (
                "[REDACTED]"
                if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS
                else _scrub(v)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        cls = type(obj)
        return cls(_scrub(x) for x in obj)
    if isinstance(obj, str):
        return _mask_pii_in_string(obj)
    return obj


def _before_send(event: dict, hint: dict) -> dict | None:
    """Sentry ``before_send`` hook — scrub PII before sending.

    Runs on every event (error or transaction). Any exception raised
    inside this function is swallowed by Sentry — the event is sent
    unmodified rather than lost — so be defensive.
    """
    try:
        for section in ("request", "extra", "tags", "contexts", "user"):
            if section in event and isinstance(event[section], (dict, list)):
                event[section] = _scrub(event[section])

        # Scrub breadcrumb messages too
        if "breadcrumbs" in event and isinstance(event["breadcrumbs"], dict):
            values = event["breadcrumbs"].get("values")
            if isinstance(values, list):
                for crumb in values:
                    if isinstance(crumb, dict):
                        if isinstance(crumb.get("message"), str):
                            crumb["message"] = _mask_pii_in_string(crumb["message"])
                        if isinstance(crumb.get("data"), dict):
                            crumb["data"] = _scrub(crumb["data"])

        # Scrub exception values (messages may contain PII)
        exceptions = event.get("exception", {}).get("values")
        if isinstance(exceptions, list):
            for exc in exceptions:
                if isinstance(exc, dict) and isinstance(exc.get("value"), str):
                    exc["value"] = _mask_pii_in_string(exc["value"])
    except Exception:
        # Never block an event because of a scrubber bug.
        pass
    return event


# --- Public init -------------------------------------------------------------


def _env_bool(name: str, default: bool = False) -> bool:
    """Read a bool env var. True values: '1', 'true', 'yes', 'on'."""
    val = os.getenv(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_float(name: str, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Read a float env var clamped to [lo, hi]."""
    try:
        v = float(os.getenv(name, str(default)))
    except ValueError:
        v = default
    return max(lo, min(hi, v))


def init_sentry(release: str | None = None) -> bool:
    """Initialize Sentry SDK. Safe to call multiple times (idempotent).

    Returns:
        ``True`` if Sentry was initialized and will capture events,
        ``False`` if SENTRY_DSN is unset/empty or the SDK is missing
        (in which case the function is a silent no-op and the
        orchestrator keeps booting normally).
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    # Deferred import — if sentry-sdk is missing from the container
    # image (e.g. out-of-date build), we want the orchestrator to start
    # anyway and log a warning rather than crash at import time.
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.httpx import HttpxIntegration
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        try:
            from orchestrator.config import log
            log.warning(
                "[observability] SENTRY_DSN is set but sentry-sdk is not "
                "installed; Sentry will be disabled. Run `pip install "
                "sentry-sdk[fastapi,httpx]` and rebuild the image."
            )
        except Exception:
            print("[observability] sentry-sdk missing, Sentry disabled")
        return False

    env = os.getenv("SENTRY_ENVIRONMENT", "production").strip() or "production"
    resolved_release = (
        release
        or os.getenv("SENTRY_RELEASE", "").strip()
        or None
    )
    traces_rate = _env_float("SENTRY_TRACES_SAMPLE_RATE", 0.1)

    # --- Advanced opt-in features (all OFF by default) ---
    enable_logs = _env_bool("SENTRY_ENABLE_LOGS", default=False)
    profile_session_rate = _env_float("SENTRY_PROFILE_SESSION_SAMPLE_RATE", 0.0)
    profile_lifecycle = os.getenv("SENTRY_PROFILE_LIFECYCLE", "trace").strip() or "trace"
    send_default_pii = _env_bool("SENTRY_SEND_DEFAULT_PII", default=False)

    # Build init kwargs dynamically so we don't pass profiling params
    # when profiling is off (older SDKs may ignore them, but newer ones
    # treat 0.0 as "collect session frames cheaply" — we want truly off).
    init_kwargs: dict = {
        "dsn": dsn,
        "environment": env,
        "release": resolved_release,
        "traces_sample_rate": traces_rate,
        "send_default_pii": send_default_pii,
        "attach_stacktrace": True,
        "max_breadcrumbs": 50,
        "before_send": _before_send,
        "integrations": [
            FastApiIntegration(transaction_style="endpoint"),
            HttpxIntegration(),
            AsyncioIntegration(),
            # breadcrumbs only — Sentry Logs product uses enable_logs path
            LoggingIntegration(level=None, event_level=None),
        ],
    }

    if enable_logs:
        init_kwargs["enable_logs"] = True

    if profile_session_rate > 0.0:
        init_kwargs["profile_session_sample_rate"] = profile_session_rate
        init_kwargs["profile_lifecycle"] = profile_lifecycle

    sentry_sdk.init(**init_kwargs)
    sentry_sdk.set_tag("service", "orchestrator")

    try:
        from orchestrator.config import log
        feature_flags = []
        if enable_logs:
            feature_flags.append("logs")
        if profile_session_rate > 0.0:
            feature_flags.append(f"profile@{profile_session_rate:.2f}/{profile_lifecycle}")
        if send_default_pii:
            feature_flags.append("default-pii")
        flags_str = ",".join(feature_flags) if feature_flags else "basic"
        log.info(
            "[observability] Sentry initialized "
            "(env=%s, release=%s, traces=%.2f, features=%s)",
            env, resolved_release or "(none)", traces_rate, flags_str,
        )
    except Exception:
        pass

    return True


def capture_exception(exc: BaseException, **tags: str) -> None:
    """Thin wrapper for ``sentry_sdk.capture_exception`` that is safe
    to call even when Sentry is not initialized.

    Usage from caller code:

        from orchestrator.observability import capture_exception

        try:
            await gateway.chat_completions_create(...)
        except CodexAuthError as e:
            capture_exception(e, component="llm-gateway", backend="codex")
            raise
    """
    try:
        import sentry_sdk
    except ImportError:
        return
    try:
        with sentry_sdk.push_scope() as scope:
            for k, v in tags.items():
                scope.set_tag(k, str(v))
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass  # never let observability crash the app


def set_user_context(user_id: str | int | None, **extra: str) -> None:
    """Attach user context to the current Sentry scope.

    Call this from auth middleware after a user is identified so that
    subsequent errors in the request are tagged with the user. Safe no-op
    if Sentry is not initialized.
    """
    try:
        import sentry_sdk
    except ImportError:
        return
    try:
        user_data: dict[str, Any] = {}
        if user_id is not None:
            user_data["id"] = str(user_id)
        user_data.update(extra)
        sentry_sdk.set_user(user_data if user_data else None)
    except Exception:
        pass


# --- Metrics helpers --------------------------------------------------------
#
# Thin wrappers around ``sentry_sdk.metrics`` that are safe to call even
# when Sentry is not initialized. Prefer these over direct SDK access so
# call-sites don't need try/except boilerplate.


def metric_count(
    name: str,
    value: float = 1.0,
    *,
    unit: str | None = None,
    **attributes: Any,
) -> None:
    """Emit a counter metric (cumulative, always adds).

    Example::

        from orchestrator.observability import metric_count
        metric_count("llm.codex.rate_limit", 1, api="chat")
    """
    try:
        from sentry_sdk import metrics
    except ImportError:
        return
    try:
        attrs = {k: str(v) for k, v in attributes.items()} if attributes else None
        metrics.count(name, value, unit=unit, attributes=attrs)
    except Exception:
        pass


def metric_gauge(
    name: str,
    value: float,
    *,
    unit: str | None = None,
    **attributes: Any,
) -> None:
    """Emit a gauge metric (point-in-time value, can go up or down)."""
    try:
        from sentry_sdk import metrics
    except ImportError:
        return
    try:
        attrs = {k: str(v) for k, v in attributes.items()} if attributes else None
        metrics.gauge(name, value, unit=unit, attributes=attrs)
    except Exception:
        pass


def metric_distribution(
    name: str,
    value: float,
    *,
    unit: str | None = None,
    **attributes: Any,
) -> None:
    """Emit a distribution metric (for percentiles / histograms).

    Use for values where p50/p95/p99 matter, e.g. response latency.
    """
    try:
        from sentry_sdk import metrics
    except ImportError:
        return
    try:
        attrs = {k: str(v) for k, v in attributes.items()} if attributes else None
        metrics.distribution(name, value, unit=unit, attributes=attrs)
    except Exception:
        pass


# --- Structured log helpers -------------------------------------------------
#
# Thin wrappers around ``sentry_sdk.logger.*``. These only forward to
# Sentry Logs if ``SENTRY_ENABLE_LOGS=true``. Calling these when logs
# are disabled is a safe no-op.


def log_info(message: str, **attributes: Any) -> None:
    """Send an info-level log to Sentry Logs (if enabled)."""
    try:
        from sentry_sdk import logger
    except ImportError:
        return
    try:
        logger.info(message, **attributes) if attributes else logger.info(message)
    except Exception:
        pass


def log_warning(message: str, **attributes: Any) -> None:
    """Send a warning-level log to Sentry Logs (if enabled)."""
    try:
        from sentry_sdk import logger
    except ImportError:
        return
    try:
        logger.warning(message, **attributes) if attributes else logger.warning(message)
    except Exception:
        pass


def log_error(message: str, **attributes: Any) -> None:
    """Send an error-level log to Sentry Logs (if enabled).

    Prefer :func:`capture_exception` for actual exceptions — this is for
    structured log messages without a stack trace (e.g. audit events).
    """
    try:
        from sentry_sdk import logger
    except ImportError:
        return
    try:
        logger.error(message, **attributes) if attributes else logger.error(message)
    except Exception:
        pass
