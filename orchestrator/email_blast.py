"""
Email Blast Module - Send bulk emails via SMTP
"""
import asyncio
import json
import os
import random
import re
import smtplib
import ssl
import sqlite3
import socket
import subprocess
import shutil
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

import socks
from docx import Document

from orchestrator.config import DATABASE_PATH, cfg, log
from orchestrator.db import get_db, get_email_blast_quota_info, increment_email_blast_quota
from orchestrator.websocket import manager as ws_manager

# ---------------------------------------------------------------------------
# Concurrency guard — prevent multiple concurrent runs for the same campaign
# ---------------------------------------------------------------------------

_running_campaigns: set[int] = set()
_running_lock = asyncio.Lock()


async def _acquire_campaign_lock(campaign_id: int) -> bool:
    """Acquire lock for a campaign. Returns True if acquired, False if already running."""
    async with _running_lock:
        if campaign_id in _running_campaigns:
            return False
        _running_campaigns.add(campaign_id)
        return True


def _release_campaign_lock(campaign_id: int) -> None:
    _running_campaigns.discard(campaign_id)


async def _get_campaign_status(campaign_id: int) -> str | None:
    """Return the latest persisted campaign status."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT status FROM email_blast_campaigns WHERE id = ?",
            (campaign_id,),
        )
        row = await cursor.fetchone()
    return row[0] if row else None


async def _abort_if_campaign_stopped(campaign_id: int) -> str | None:
    """Return the non-running status when a campaign was paused/cancelled externally."""
    status = await _get_campaign_status(campaign_id)
    if status != "running":
        log.info("[EmailBlast] Campaign %s stop requested (status=%s)", campaign_id, status)
        await broadcast_campaign_update(campaign_id)
        return status
    return None


async def _sleep_with_campaign_checks(campaign_id: int, delay_ms: int) -> str | None:
    """Sleep in short intervals so pause/cancel takes effect promptly."""
    remaining = max(0, int(delay_ms or 0))
    while remaining > 0:
        stopped = await _abort_if_campaign_stopped(campaign_id)
        if stopped:
            return stopped
        chunk = min(remaining, 500)
        await asyncio.sleep(chunk / 1000)
        remaining -= chunk
    return None


async def sync_campaign_counters(campaign_id: int) -> dict:
    """Recalculate sent_count and failed_count from the actual recipient table.

    Call this whenever counters are suspected to be out of sync with reality.
    Returns the updated counters.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT status, COUNT(*) FROM email_blast_recipients WHERE campaign_id = ? GROUP BY status",
            (campaign_id,)
        )
        rows = await cursor.fetchall()
        counts = {row[0]: row[1] for row in rows}
        sent = counts.get("sent", 0)
        failed = counts.get("failed", 0)
        pending = counts.get("pending", 0)
        invalid = counts.get("invalid", 0)

        await db.execute(
            "UPDATE email_blast_campaigns SET sent_count = ?, failed_count = ?, invalid_count = ?, total_recipients = ? WHERE id = ?",
            (sent, failed, invalid, sent + failed + pending + invalid, campaign_id)
        )
        await db.commit()

    log.info(f"[EmailBlast] Synced counters for campaign {campaign_id}: sent={sent}, failed={failed}, invalid={invalid}, pending={pending}")
    return {"sent_count": sent, "failed_count": failed, "invalid_count": invalid, "pending_count": pending}


async def _finalize_campaign_status_after_run(campaign_id: int, max_recipients: int | None) -> tuple[str | None, int]:
    """Finalize campaign status based on actual remaining pending recipients."""
    counters = await sync_campaign_counters(campaign_id)
    pending_count = int(counters.get("pending_count", 0) or 0)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT status FROM email_blast_campaigns WHERE id = ?",
            (campaign_id,)
        )
        row = await cursor.fetchone()
        current_status = row[0] if row else None

        if current_status != 'running':
            return current_status, pending_count

        now = datetime.now().isoformat()
        if pending_count > 0:
            await db.execute(
                "UPDATE email_blast_campaigns SET status = 'paused', paused_at = ?, completed_at = NULL WHERE id = ?",
                (now, campaign_id)
            )
            await db.commit()
            if max_recipients:
                log.info(
                    "[EmailBlast] Campaign %s paused after batch limit %s with %s pending recipients remaining",
                    campaign_id,
                    max_recipients,
                    pending_count,
                )
            else:
                log.warning(
                    "[EmailBlast] Campaign %s paused with %s pending recipients still remaining after run",
                    campaign_id,
                    pending_count,
                )
            return 'paused', pending_count

        await db.execute(
            "UPDATE email_blast_campaigns SET status = 'completed', completed_at = ?, paused_at = NULL WHERE id = ?",
            (now, campaign_id)
        )
        await db.commit()
        return 'completed', 0


# ---------------------------------------------------------------------------
# SOCKS Proxy Support
# ---------------------------------------------------------------------------

async def _increment_quota_and_broadcast(db, campaign_id: int, daily_limit: int) -> dict:
    """Increment daily quota inside an existing DB transaction, then broadcast outside."""
    await db.execute(
        """INSERT INTO email_blast_daily_quota (quota_date, sent_count, updated_at)
           VALUES (?, 1, datetime('now'))
           ON CONFLICT(quota_date) DO UPDATE SET
               sent_count = sent_count + 1,
               updated_at = datetime('now')""",
        (datetime.now().strftime("%Y-%m-%d"),)
    )
    cursor = await db.execute("SELECT sent_count FROM email_blast_daily_quota WHERE quota_date = ?",
                               (datetime.now().strftime("%Y-%m-%d"),))
    row = await cursor.fetchone()
    sent = row["sent_count"] if row else 1
    remaining = max(0, daily_limit - sent)
    quota = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sent_today": sent,
        "daily_limit": daily_limit,
        "remaining": remaining,
        "is_exhausted": remaining <= 0,
        "campaign_id": campaign_id,
    }
    # Broadcast outside DB transaction
    await ws_manager.broadcast_type("email_quota_updated", **quota)
    return quota


async def _broadcast_blast_progress(campaign_id: int, sent_count: int, failed_count: int,
                                    invalid_count: int, total: int, status: str = "running") -> None:
    """Broadcast blast progress to all WebSocket clients for real-time UI updates."""
    processed = sent_count + failed_count + invalid_count
    pct = round(processed / total * 100, 1) if total > 0 else 0
    await ws_manager.broadcast_type(
        "blast_progress",
        campaign_id=campaign_id,
        sent_count=sent_count,
        failed_count=failed_count,
        invalid_count=invalid_count,
        total=total,
        percent=pct,
        status=status,
    )


async def broadcast_campaign_update(campaign_id: int) -> None:
    """Broadcast the latest campaign snapshot for terminal state transitions."""
    campaign = await get_campaign_status(campaign_id)
    if campaign:
        await ws_manager.broadcast_type("email_campaign_updated", campaign=campaign)


async def broadcast_recipient_update(campaign_id: int, recipient: dict) -> None:
    """Broadcast a single recipient state change."""
    await ws_manager.broadcast_type("email_recipient_updated", campaign_id=campaign_id, recipient=recipient)


async def broadcast_outbox_logged(email: dict) -> None:
    """Broadcast a newly recorded outbox entry."""
    await ws_manager.broadcast_type("email_outbox_logged", email=email)


async def broadcast_inbox_received(email: dict, campaign_ids: list[int]) -> None:
    """Broadcast a newly cached inbound email."""
    await ws_manager.broadcast_type("email_inbox_received", email=email, campaign_ids=campaign_ids)


def _get_socks_config() -> dict:
    """Get SOCKS5 proxy configuration from environment/config."""
    return {
        "host": os.environ.get("SMTP_SOCKS_HOST", "172.18.0.2"),
        "port": int(os.environ.get("SMTP_SOCKS_PORT", "1080")),
        "enabled": os.environ.get("SMTP_SOCKS_ENABLED", "true").lower() in ("true", "1", "yes"),
    }


_original_create_connection: Optional[callable] = None


def _socks_create_connection(address, timeout=None, source_address=None, socket_options=None):
    """Wrapper around socket.create_connection that routes through SOCKS5."""
    socks_config = _get_socks_config()
    if not socks_config["enabled"]:
        return _original_create_connection(address, timeout, source_address, socket_options)

    log.debug(f"[EmailBlast] SOCKS5 routing {address} through {socks_config['host']}:{socks_config['port']}")
    sock = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
    sock.set_proxy(
        proxy_type=socks.SOCKS5,
        addr=socks_config["host"],
        port=socks_config["port"],
        username=os.environ.get("SMTP_SOCKS_USER"),
        password=os.environ.get("SMTP_SOCKS_PASSWORD"),
    )
    # Ensure timeout is a float (pysocks has a bug with None timeout in Python 3.11)
    if timeout is not None:
        try:
            sock.settimeout(float(timeout))
        except (TypeError, ValueError):
            sock.settimeout(30.0)
    sock.connect(address)
    return sock


# ---------------------------------------------------------------------------
# Email Validation
# ---------------------------------------------------------------------------

# Known disposable / throwaway email domains — skip without MX lookup
_DISPOSABLE_DOMAINS: frozenset[str] = frozenset({
    "mailinator.com", "guerrillamail.com", "temp-mail.org", "throwaway.email",
    "10minutemail.com", "tempmail.com", "fakeinbox.com", "trashmail.com",
    "maildrop.cc", "getairmail.com", "yopmail.com", "sharklasers.com",
    "tempail.com", "mohmal.com", "tempinbox.com", "dispostable.com",
})


def validate_email(email: str) -> tuple[bool, str]:
    """Validate an email address: syntax check + MX record check.

    Returns:
      (True, "")                     -> valid, proceed to send
      (False, "invalid_format")    -> syntax error
      (False, "disposable_domain")  -> throwaway domain
      (False, "no_mx_record")       -> domain has no MX record

    Be lenient on DNS/network errors — allow through rather than block.
    """
    if not isinstance(email, str) or not email or "@" not in email:
        return False, "invalid_format"

    local, _, domain = email.rpartition("@")
    if not local or not domain:
        return False, "invalid_format"

    domain_lower = domain.lower()

    # Fast path: disposable domain (no DNS needed)
    if domain_lower in _DISPOSABLE_DOMAINS:
        return False, "disposable_domain"

    # Use email_validator for full validation (syntax + MX)
    try:
        from email_validator import validate_email as _ev_validate, EmailNotValidError
        _ev_validate(email, check_deliverability=True)
        return True, ""
    except EmailNotValidError as e:
        err = str(e).lower()
        if "mx" in err or "mx record" in err or "no mx" in err:
            return False, "no_mx_record"
        # Syntax or other validation error
        return False, "invalid_format"
    except ImportError:
        log.warning("[EmailValidation] email-validator not installed, skipping MX check")
        return True, ""
    except Exception as e:
        # Network/DNS error — be lenient, don't block due to transient failures
        log.warning(f"[EmailValidation] MX check error for {domain_lower}: {e}")
        return True, ""


# ---------------------------------------------------------------------------
# SMTP Client
# ---------------------------------------------------------------------------

class SMTPAccount:
    """Single SMTP account configuration."""
    def __init__(self, host: str, port: int, user: str, password: str,
                 use_ssl: bool = True, from_name: str = "Sekretariat Asosiasi AI"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_ssl = use_ssl
        self.from_name = from_name
        self._connection: Optional[smtplib.SMTP_SSL] = None
        self.email_count = 0  # emails sent with this account this session
        self.degraded = False  # True if recent auth error
        self.last_sent_monotonic: float | None = None
        self.daily_sent_count = 0
        self.daily_sent_date: str | None = None
        self.daily_count_checked_monotonic = 0.0


class SMTPClient:
    """SMTP client with multi-account rotation to prevent bans.

    Supports two modes:
    1. Multi-account (SMTP_ACCOUNTS JSON config): rotates through multiple
       SMTP accounts, switching after ROTATE_AFTER_N_EMAILS or on auth error.
    2. Legacy single-account (SMTP_HOST/USERNAME): uses one account only.

    Thread-safe via a lock for rotation decisions.
    """

    def __init__(self, accounts: list[SMTPAccount] | None = None):
        self._rotate_after = cfg.get("ROTATE_AFTER_N_EMAILS", 50)
        self._min_cooldown_seconds = max(0, int(cfg.get("SMTP_ACCOUNT_MIN_COOLDOWN_SECONDS", 60)))
        self._daily_limit_per_account = max(0, int(cfg.get("SMTP_ACCOUNT_DAILY_LIMIT", 40)))
        self._rotation_lock = threading.RLock()

        # Load accounts
        self._accounts: list[SMTPAccount] = []
        self._current_index = 0
        managed_accounts_configured = False

        if accounts is not None:
            self._accounts = accounts
            return

        raw_accounts = cfg.get("SMTP_ACCOUNTS", "")
        if raw_accounts:
            try:
                accounts_data = json.loads(raw_accounts)
                managed_accounts_configured = isinstance(accounts_data, list)
                for acc in accounts_data:
                    if not bool(acc.get("enabled", True)):
                        continue
                    self._accounts.append(SMTPAccount(
                        host=acc.get("host", "mail.asosiasi.ai"),
                        port=int(acc.get("port", 465)),
                        user=acc.get("user", ""),
                        password=acc.get("password", ""),
                        use_ssl=acc.get("use_ssl", True),
                        from_name=acc.get("from_name", "Sekretariat Asosiasi AI"),
                    ))
                log.info(f"[EmailBlast] SMTP: loaded {len(self._accounts)} enabled accounts for rotation")
            except Exception as e:
                log.error(f"[EmailBlast] SMTP_ACCOUNTS JSON parse error: {e}. Falling back to single account.")
                self._accounts = []
                managed_accounts_configured = False

        if managed_accounts_configured and not self._accounts:
            log.warning("[EmailBlast] SMTP: managed accounts configured, but none are enabled")

        # Fallback: single legacy account
        if not self._accounts and not managed_accounts_configured:
            self._accounts.append(SMTPAccount(
                host=cfg.get("SMTP_HOST", "mail.asosiasi.ai"),
                port=cfg.get("SMTP_PORT", 465),
                user=cfg.get("SMTP_USERNAME", "sekretariat@asosiasi.ai"),
                password=cfg.get("SMTP_PASSWORD", ""),
                use_ssl=cfg.get("SMTP_USE_SSL", True),
                from_name=cfg.get("SMTP_FROM_NAME", "Sekretariat Asosiasi AI"),
            ))
            log.info("[EmailBlast] SMTP: using single legacy account (no rotation)")

    @property
    def _current_account(self) -> SMTPAccount:
        return self._accounts[self._current_index]

    def _today_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _get_daily_sent_count(self, acc: SMTPAccount) -> int:
        today = self._today_key()
        now_mono = time.monotonic()
        conn: sqlite3.Connection | None = None

        if acc.daily_sent_date != today:
            acc.daily_sent_date = today
            acc.daily_sent_count = 0
            acc.daily_count_checked_monotonic = 0.0

        if now_mono - acc.daily_count_checked_monotonic < 30:
            return acc.daily_sent_count

        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.execute(
                """SELECT COUNT(*)
                   FROM email_outbox
                   WHERE status = 'sent'
                     AND lower(trim(from_email)) = ?
                     AND substr(sent_at, 1, 10) = ?""",
                (acc.user.lower().strip(), today),
            )
            row = cursor.fetchone()
            acc.daily_sent_count = int(row[0] if row else 0)
        except Exception as exc:
            log.warning("[EmailBlast] Failed to read per-account daily count for %s: %s", acc.user, exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        acc.daily_count_checked_monotonic = now_mono
        return acc.daily_sent_count

    def _remaining_cooldown(self, acc: SMTPAccount) -> float:
        if self._min_cooldown_seconds <= 0 or acc.last_sent_monotonic is None:
            return 0.0
        remaining = self._min_cooldown_seconds - (time.monotonic() - acc.last_sent_monotonic)
        return max(0.0, remaining)

    def _is_daily_limited(self, acc: SMTPAccount) -> bool:
        if self._daily_limit_per_account <= 0:
            return False
        return self._get_daily_sent_count(acc) >= self._daily_limit_per_account

    def _can_send_now(self, acc: SMTPAccount) -> bool:
        if acc.degraded:
            return False
        if self._is_daily_limited(acc):
            return False
        return self._remaining_cooldown(acc) <= 0

    def _skip_reason(self, acc: SMTPAccount) -> str | None:
        if acc.degraded:
            return "degraded"
        if self._is_daily_limited(acc):
            return "daily_limit"
        cooldown = self._remaining_cooldown(acc)
        if cooldown > 0:
            return f"cooldown:{round(cooldown, 1)}"
        return None

    def _switch_to_index(self, next_index: int, reason: str) -> None:
        if next_index == self._current_index:
            return

        old = self._current_account
        self._disconnect_account(old)
        old.email_count = 0

        self._current_index = next_index
        new_acc = self._current_account
        log.info(
            "[EmailBlast] SMTP rotated: %s -> %s (%s)",
            old.user,
            new_acc.user,
            reason,
        )

    def _rotate_to_next_sendable_account(self, reason: str) -> bool:
        if len(self._accounts) <= 1:
            return self._can_send_now(self._current_account)

        start_index = self._current_index
        for step in range(1, len(self._accounts) + 1):
            candidate_index = (start_index + step) % len(self._accounts)
            candidate = self._accounts[candidate_index]
            if self._can_send_now(candidate):
                self._switch_to_index(candidate_index, reason)
                return True

        return False

    def _wait_for_next_available_account(self) -> bool:
        wait_candidates = [
            self._remaining_cooldown(acc)
            for acc in self._accounts
            if not acc.degraded and not self._is_daily_limited(acc)
        ]
        wait_candidates = [seconds for seconds in wait_candidates if seconds > 0]
        if not wait_candidates:
            return False

        sleep_for = min(wait_candidates)
        log.info("[EmailBlast] All SMTP accounts cooling down. Waiting %.1fs", sleep_for)
        time.sleep(sleep_for)
        return True

    def _ensure_ready_account(self) -> tuple[bool, str | None]:
        if not self._accounts:
            return False, "SMTP: no enabled account configured"

        while True:
            acc = self._current_account

            if acc.email_count >= self._rotate_after and len(self._accounts) > 1:
                if self._rotate_to_next_sendable_account("rotate_after_threshold"):
                    continue

            if self._can_send_now(acc):
                return True, None

            if acc.degraded and self._rotate_to_next_sendable_account("degraded_account"):
                continue

            if self._is_daily_limited(acc) and self._rotate_to_next_sendable_account("daily_limit_reached"):
                continue

            if self._remaining_cooldown(acc) > 0 and self._rotate_to_next_sendable_account("cooldown_active"):
                continue

            if self._wait_for_next_available_account():
                continue

            return False, "SMTP: no eligible account available (daily cap reached or degraded)"

    def _maybe_rotate(self) -> None:
        """Rotate to next account if limit reached or current is degraded."""
        acc = self._current_account
        if (acc.email_count >= self._rotate_after and len(self._accounts) > 1) or acc.degraded:
            self._rotate_next()

    def _rotate_next(self) -> None:
        """Switch to next account, disconnecting the current one."""
        if not self._rotate_to_next_sendable_account("manual_rotation"):
            self._switch_to_index((self._current_index + 1) % len(self._accounts), "manual_rotation_fallback")

    def _disconnect_account(self, acc: SMTPAccount) -> None:
        """Disconnect a specific account's connection."""
        if acc._connection:
            try:
                acc._connection.quit()
            except Exception:
                pass
            acc._connection = None

    def _should_fallback_to_direct(self, exc: Exception) -> bool:
        """Return True when the failure looks like a SOCKS/WARP transport issue."""
        err_str = str(exc).lower()
        auth_keywords = ("auth", "535", "501", "534", "user", "password", "authentication")
        proxy_keywords = (
            "host unreachable",
            "can't complete socks5 connection",
            "socks5",
            "socks",
            "proxy",
            "network is unreachable",
            "no route to host",
            "connection refused",
            "timed out",
            "timeout",
            "0x04",
        )
        if any(kw in err_str for kw in auth_keywords):
            return False
        return any(kw in err_str for kw in proxy_keywords)

    def _connect_account(self, acc: SMTPAccount, socks_enabled: bool, quiet: bool) -> smtplib.SMTP:
        """Open and authenticate an SMTP connection, optionally via SOCKS."""
        global _original_create_connection
        should_patch = socks_enabled

        try:
            if should_patch:
                if _original_create_connection is None:
                    _original_create_connection = socket.create_connection
                    socket.create_connection = _socks_create_connection
                if not quiet:
                    log.info(f"[EmailBlast] SOCKS5 proxy active: {_get_socks_config()['host']}:{_get_socks_config()['port']}")

            if not quiet:
                log.info(f"[EmailBlast] SMTP connecting: {acc.host}:{acc.port} as {acc.user} (SOCKS5={socks_enabled})")

            if acc.use_ssl:
                context = ssl.create_default_context()
                conn = smtplib.SMTP_SSL(acc.host, acc.port, context=context)
            else:
                conn = smtplib.SMTP(acc.host, acc.port)
                conn.ehlo()
                conn.starttls(context=ssl.create_default_context())

            conn.login(acc.user, acc.password)
            return conn

        finally:
            if should_patch and _original_create_connection is not None:
                socket.create_connection = _original_create_connection
                _original_create_connection = None

    def _ensure_connected(self, quiet: bool = False) -> bool:
        """Ensure current account is connected. Rotates if needed.

        quiet=True suppresses routine info logs (used by health-check path).
        """
        ready, reason = self._ensure_ready_account()
        if not ready:
            log.warning("[EmailBlast] %s", reason)
            return False

        acc = self._current_account
        if acc._connection is not None:
            return True

        socks_config = _get_socks_config()

        try:
            conn = self._connect_account(acc, socks_config["enabled"], quiet)
            acc._connection = conn
            acc.degraded = False
            if not quiet:
                log.info(f"[EmailBlast] SMTP connected: {acc.user}")
            return True

        except Exception as e:
            if socks_config["enabled"] and self._should_fallback_to_direct(e):
                log.warning(
                    "[EmailBlast] SMTP SOCKS connection failed for %s, retrying direct: %s",
                    acc.user,
                    e,
                )
                try:
                    conn = self._connect_account(acc, False, quiet)
                    acc._connection = conn
                    acc.degraded = False
                    if not quiet:
                        log.info(f"[EmailBlast] SMTP connected without SOCKS fallback: {acc.user}")
                    return True
                except Exception as direct_exc:
                    e = direct_exc

            err_str = str(e).lower()
            log.error(f"[EmailBlast] SMTP connect failed for {acc.user}: {e}")
            # Mark as degraded so we rotate away
            acc.degraded = True
            acc._connection = None

            # If this is an auth error, rotate immediately
            if any(kw in err_str for kw in ("auth", "535", "501", "534", "user", "password", "authentication")):
                with self._rotation_lock:
                    self._rotate_next()
            return False
        finally:
            if should_patch and _original_create_connection is not None:
                socket.create_connection = _original_create_connection
                _original_create_connection = None

    def disconnect(self) -> None:
        """Disconnect all account connections."""
        for acc in self._accounts:
            self._disconnect_account(acc)

    def connect(self, quiet: bool = False) -> bool:
        """Pre-connect the current account. Returns True if connected.

        quiet=True suppresses routine info logs (used by health-check path).
        Backward-compatible with old single-account .connect() usage.
        Prefer letting send_email() handle connection lazily.
        """
        return self._ensure_connected(quiet=quiet)

    def send_email_with_context(self, to_email: str, subject: str, body: str,
                                from_email: str = None, from_name: str = None,
                                attachment_path: str = None,
                                attachment_filename: str = None) -> tuple[bool, str, dict[str, str | None]]:
        """Send a single email and return sender metadata for auditing."""
        with self._rotation_lock:
            connected = self._ensure_connected()
            if not connected:
                return False, "SMTP: no eligible account available (daily cap reached, cooling down, or degraded)", {
                    "smtp_account": None,
                    "from_email": from_email,
                    "from_name": from_name,
                }

        # Build message (no lock held)
        acc = self._current_account
        from_addr = from_email or acc.user
        from_display = from_name or acc.from_name
        send_context = {
            "smtp_account": acc.user,
            "from_email": from_addr,
            "from_name": from_display,
        }
        try:
            msg = MIMEMultipart('mixed')
            msg['From'] = f"{from_display} <{from_addr}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Reply-To'] = from_addr

            # Multipart alternative
            msg_alt = MIMEMultipart('alternative')
            msg_alt.attach(MIMEText(body, 'plain', 'utf-8'))
            msg_alt.attach(MIMEText(body.replace('\n', '<br>\n'), 'html', 'utf-8'))
            msg.attach(msg_alt)

            # Attachment
            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    filename = attachment_filename or re.sub(r'^\d+_\d+_', '', os.path.basename(attachment_path))
                    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                    msg.attach(part)
                    log.debug(f"[EmailBlast] Attached: {filename}")

            # Send
            acc._connection.sendmail(from_addr, [to_email], msg.as_string())
            acc.email_count += 1
            acc.last_sent_monotonic = time.monotonic()
            today = self._today_key()
            if acc.daily_sent_date != today:
                acc.daily_sent_date = today
                acc.daily_sent_count = 0
            acc.daily_sent_count += 1
            acc.daily_count_checked_monotonic = time.monotonic()

            log.info(
                f"[EmailBlast] Sent to {to_email} via {acc.user} "
                f"(account_count={acc.email_count}/{self._rotate_after}, daily_count={acc.daily_sent_count}/{self._daily_limit_per_account or 'inf'})"
            )

            # Check if we should rotate after this send
            with self._rotation_lock:
                self._maybe_rotate()

            return True, "", send_context

        except Exception as e:
            err_str = str(e).lower()
            log.error(f"[EmailBlast] Send failed to {to_email} via {acc.user}: {e}")

            # Auth error → degrade and rotate
            if any(kw in err_str for kw in ("auth", "535", "501", "534", "user", "password", "authentication")):
                with self._rotation_lock:
                    acc.degraded = True
                    self._disconnect_account(acc)
                    self._rotate_next()
                return False, f"SMTP auth error ({acc.user}), rotated: {str(e)}", send_context

            return False, str(e), send_context

    def send_email(self, to_email: str, subject: str, body: str,
                   from_email: str = None, from_name: str = None,
                   attachment_path: str = None,
                   attachment_filename: str = None) -> tuple[bool, str]:
        """Backward-compatible wrapper around send_email_with_context()."""
        success, error, _ = self.send_email_with_context(
            to_email=to_email,
            subject=subject,
            body=body,
            from_email=from_email,
            from_name=from_name,
            attachment_path=attachment_path,
            attachment_filename=attachment_filename,
        )
        return success, error

    def get_status(self) -> dict:
        """Return per-account status for monitoring."""
        return {
            "total_accounts": len(self._accounts),
            "rotate_after": self._rotate_after,
            "min_cooldown_seconds": self._min_cooldown_seconds,
            "daily_limit_per_account": self._daily_limit_per_account,
            "accounts": [
                {
                    "user": acc.user,
                    "is_current": index == self._current_index,
                    "email_count": acc.email_count,
                    "daily_sent_count": self._get_daily_sent_count(acc),
                    "daily_limit": self._daily_limit_per_account,
                    "cooldown_remaining_seconds": round(self._remaining_cooldown(acc), 1),
                    "skip_reason": self._skip_reason(acc),
                    "degraded": acc.degraded,
                    "connected": acc._connection is not None,
                }
                for index, acc in enumerate(self._accounts)
            ]
        }


# Global SMTP client
_smtp_client: Optional[SMTPClient] = None


def get_smtp_client() -> SMTPClient:
    """Get or create SMTP client"""
    global _smtp_client
    if _smtp_client is None:
        _smtp_client = SMTPClient()
    return _smtp_client


def reset_smtp_client() -> None:
    """Drop the cached SMTP client so updated account config takes effect immediately."""
    global _smtp_client
    if _smtp_client is not None:
        try:
            _smtp_client.disconnect()
        except Exception:
            pass
    _smtp_client = None


def using_managed_smtp_accounts() -> bool:
    """Return True when SMTP rotation is configured via managed accounts JSON."""
    raw_accounts = cfg.get("SMTP_ACCOUNTS", "")
    return bool(str(raw_accounts or "").strip())


def build_smtp_account(account: dict) -> SMTPAccount:
    """Build an SMTPAccount object from a serialized account dict."""
    return SMTPAccount(
        host=str(account.get("host") or "mail.asosiasi.ai").strip(),
        port=int(account.get("port") or 465),
        user=str(account.get("user") or "").strip().lower(),
        password=str(account.get("password") or ""),
        use_ssl=bool(account.get("use_ssl", True)),
        from_name=str(account.get("from_name") or "Sekretariat Asosiasi AI").strip() or "Sekretariat Asosiasi AI",
    )


def test_smtp_account(account: dict) -> tuple[bool, str]:
    """Test a single SMTP account without affecting the shared singleton."""
    client = SMTPClient(accounts=[build_smtp_account(account)])
    try:
        success = client.connect(quiet=True)  # suppress routine logs — called from health-check
        if success:
            return True, "SMTP connected"
        return False, "SMTP failed"
    except Exception as exc:
        log.error("[EmailBlast] SMTP account test failed: %s", exc, exc_info=True)
        return False, str(exc)
    finally:
        client.disconnect()


def compute_inter_send_delay_ms(base_delay_ms: int) -> int:
    """Return the actual delay after a send, with random jitter added."""
    base_delay_ms = max(0, int(base_delay_ms or 0))
    jitter_ms = max(0, int(cfg.get("EMAIL_BLAST_DELAY_JITTER_MS", 5000) or 0))
    if jitter_ms <= 0:
        return base_delay_ms
    return base_delay_ms + random.randint(0, jitter_ms)


def _resolve_from_email_for_send(from_email: str | None) -> str | None:
    """Use rotating account identity when managed SMTP accounts are enabled."""
    if using_managed_smtp_accounts():
        return None

    normalized = (from_email or "").strip()
    return normalized or None


def _get_sender_identity(send_context: dict[str, str | None], fallback_email: str | None, fallback_name: str | None) -> tuple[str, str]:
    sender_email = str(send_context.get("from_email") or fallback_email or "sekretariat@asosiasi.ai").strip() or "sekretariat@asosiasi.ai"
    sender_name = str(send_context.get("from_name") or fallback_name or "Sekretariat Asosiasi AI").strip() or "Sekretariat Asosiasi AI"
    return sender_email, sender_name


# ---------------------------------------------------------------------------
# Template Functions
# ---------------------------------------------------------------------------

TEMPLATE_DIR = Path("data/email_attachments")
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)


def convert_docx_to_pdf(docx_path: str, pdf_path: str) -> bool:
    """Convert DOCX to PDF using multiple methods"""
    import platform

    system = platform.system()

    # Convert paths to Windows format with raw strings
    docx_path_abs = os.path.abspath(docx_path)
    pdf_path_abs = os.path.abspath(pdf_path)

    # Method 1: Try comtypes on Windows (most reliable)
    if system == "Windows":
        try:
            import comtypes.client
            import comtypes
            import time

            log.info(f"[EmailBlast] Attempting comtypes conversion: {docx_path_abs}")

            # Create COM object
            word = comtypes.client.CreateObject('Word.Application')
            word.Visible = False

            # Convert - use absolute path with raw string
            doc = word.Documents.Open(docx_path_abs)
            time.sleep(0.5)  # Brief delay to ensure file is loaded
            doc.SaveAs(pdf_path_abs, FileFormat=17)  # 17 = PDF format
            doc.Close()
            word.Quit()
            time.sleep(0.5)  # Brief delay for cleanup

            if os.path.exists(pdf_path_abs):
                log.info(f"[EmailBlast] PDF created via comtypes: {pdf_path_abs}")
                return True
        except Exception as e:
            log.warning(f"[EmailBlast] comtypes failed: {e}")

    # Method 2: Try docx2pdf (works on Windows with Word installed)
    try:
        from docx2pdf import convert
        log.info(f"[EmailBlast] Attempting docx2pdf conversion: {docx_path_abs}")
        convert(docx_path_abs, pdf_path_abs)
        if os.path.exists(pdf_path_abs):
            log.info(f"[EmailBlast] PDF created via docx2pdf: {pdf_path_abs}")
            return True
    except Exception as e:
        log.warning(f"[EmailBlast] docx2pdf failed: {e}")

    # Method 3: Try LibreOffice headless (best for Linux)
    try:
        out_dir = os.path.dirname(docx_path_abs)
        result = subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'pdf',
             '--outdir', out_dir, docx_path_abs],
            capture_output=True,
            text=True,
            timeout=60
        )
        if os.path.exists(pdf_path_abs):
            log.info(f"[EmailBlast] PDF created via LibreOffice: {pdf_path_abs}")
            return True
        # LibreOffice may strip spaces/special chars from output filename
        base = os.path.splitext(os.path.basename(docx_path))[0]
        alt_pdf = os.path.join(out_dir, base + '.pdf')
        if os.path.exists(alt_pdf):
            shutil.move(alt_pdf, pdf_path_abs)
            log.info(f"[EmailBlast] PDF created via LibreOffice (renamed): {pdf_path_abs}")
            return True
        # Fallback: scan out_dir for any new PDF that might be the converted file
        for f in os.listdir(out_dir):
            if f.endswith('.pdf') and 'converted' not in f.lower():
                candidate = os.path.join(out_dir, f)
                # Only move if it's the right size (non-zero, not huge)
                if os.path.getsize(candidate) > 1000:
                    shutil.move(candidate, pdf_path_abs)
                    log.info(f"[EmailBlast] PDF created via LibreOffice (scanned): {pdf_path_abs}")
                    return True
    except Exception as e:
        log.warning(f"[EmailBlast] LibreOffice failed: {e}")

    # Method 4: Try pandoc (if installed)
    try:
        result = subprocess.run(
            ['pandoc', docx_path_abs, '-o', pdf_path_abs],
            capture_output=True,
            text=True
        )
        if os.path.exists(pdf_path_abs):
            log.info(f"[EmailBlast] PDF created via pandoc: {pdf_path_abs}")
            return True
    except Exception as e:
        log.warning(f"[EmailBlast] pandoc failed: {e}")

    log.error(f"[EmailBlast] All PDF conversion methods failed!")
    return False


def detect_variables(text: str) -> list[str]:
    """Detect all {{variable}} patterns in text"""
    pattern = r'\{\{(\w+)\}\}'
    return list(set(re.findall(pattern, text)))


def extract_docx_variables(doc_path: str) -> list[str]:
    """Extract variables from DOCX template"""
    variables = set()
    try:
        doc = Document(doc_path)
        for para in doc.paragraphs:
            variables.update(detect_variables(para.text))
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        variables.update(detect_variables(para.text))
    except Exception as e:
        log.error(f"[EmailBlast] Error reading DOCX: {e}")
    return sorted(list(variables))


def _escape_xml_attr(value: str) -> str:
    """Escape special XML characters for text content."""
    return (value
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;'))


def _render_filename(filename: str, vars_dict: dict) -> str:
    """
    Replace {{placeholder}} patterns in a filename with actual values.
    Also sanitizes the result to be safe for filesystem use.

    Handles filenames that may have a leading `{id}_` prefix (e.g. campaign
    uploads stored as `13_Surat Audiensi - {{university_name}}.docx`).
    """
    # Strip leading `{number}_` prefix if present (from stored upload filenames)
    result = re.sub(r'^(\d+_)', '', filename, count=1)
    for key, value in vars_dict.items():
        placeholder = f'{{{{{key}}}}}'
        if placeholder in result:
            # Sanitize: remove chars invalid in filenames, truncate if too long
            safe_value = str(value)
            safe_value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', safe_value)
            safe_value = safe_value.strip('. ')
            if len(safe_value) > 60:
                safe_value = safe_value[:60]
            result = result.replace(placeholder, safe_value)
    # Final sanitization of whole filename
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', result)
    result = result.strip('. ')
    if not result:
        result = 'attachment'
    return result


def generate_docx(doc_path: str, variables: dict, output_path: str) -> bool:
    """
    Generate DOCX from template by replacing {{variable}} patterns directly
    in the XML. This PRESERVES all embedded images, VML shapes, text boxes,
    drawings, headers, and footers — unlike python-docx which strips them.

    DOCX is a ZIP archive; we only modify word/document.xml strings.
    All other parts (media files, styles, settings) are copied as-is.
    """
    import zipfile
    try:
        log.info(f"[EmailBlast] generate_docx: {doc_path} -> {output_path}")
        log.info(f"[EmailBlast] Variables: {variables}")

        replacement_count = 0

        # Read the template DOCX (zip) and build a new DOCX with replaced text
        with zipfile.ZipFile(doc_path, 'r') as zin:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)

                    # Only modify word/document.xml — all images/shapes/headers stay untouched
                    if item.filename == 'word/document.xml':
                        xml_content = data.decode('utf-8')

                        for key, value in variables.items():
                            placeholder = f'{{{{{key}}}}}'
                            if placeholder in xml_content:
                                count = xml_content.count(placeholder)
                                replacement_count += count
                                # Escape XML special chars so the value renders as text
                                safe_value = _escape_xml_attr(str(value))
                                xml_content = xml_content.replace(placeholder, safe_value)
                                log.info(f"[EmailBlast] Replaced {count}x '{placeholder}' -> '{safe_value}'")

                        data = xml_content.encode('utf-8')
                        log.info(f"[EmailBlast] Total replacements in document.xml: {replacement_count}")

                    zout.writestr(item, data)

        log.info(f"[EmailBlast] DOCX saved to {output_path}")
        return True

    except Exception as e:
        log.error(f"[EmailBlast] Error generating DOCX: {e}")
        import traceback
        traceback.print_exc()
        return False


async def save_campaign_attachment(campaign_id: int, filename: str, variables: str) -> bool:
    """Save attachment info to campaign"""
    async with get_db() as db:
        await db.execute(
            """UPDATE email_blast_campaigns
               SET attachment_filename = ?, attachment_variables = ?
               WHERE id = ?""",
            (filename, variables, campaign_id)
        )
        await db.commit()
        return True


async def get_campaign_attachment(campaign_id: int) -> dict:
    """Get attachment info for campaign"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT attachment_filename, attachment_variables
               FROM email_blast_campaigns WHERE id = ?""",
            (campaign_id,)
        )
        row = await cursor.fetchone()
        if row and row[0]:
            # Re-extract variables from the uploaded DOCX file
            filepath = TEMPLATE_DIR / row[0]
            detected_vars = []
            if filepath.exists():
                try:
                    detected_vars = extract_docx_variables(str(filepath))
                except Exception as e:
                    log.error(f"Error extracting variables: {e}")

            return {
                'filename': row[0],
                'variables': json.loads(row[1]) if row[1] else {},
                'detected_variables': detected_vars
            }
        return {'filename': None, 'variables': {}, 'detected_variables': []}


# ---------------------------------------------------------------------------
# Letter Number Config
# ---------------------------------------------------------------------------

async def get_letter_config() -> dict:
    """Get letter number configuration"""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, format_template, last_number FROM email_blast_letter_config LIMIT 1"
        )
        row = await cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'format_template': row[1],
                'last_number': row[2]
            }
        # Create default if not exists
        cursor = await db.execute(
            "INSERT INTO email_blast_letter_config (format_template, last_number) VALUES (?, ?)",
            ("{{NUMBER}}/ASOSIASI/{{YEAR}}", 0)
        )
        await db.commit()
        return {
            'id': cursor.lastrowid,
            'format_template': "{{NUMBER}}/ASOSIASI/{{YEAR}}",
            'last_number': 0
        }


async def update_letter_config(format_template: str = None, last_number: int = None) -> dict:
    """Update letter number configuration"""
    async with get_db() as db:
        if format_template is not None:
            await db.execute(
                "UPDATE email_blast_letter_config SET format_template = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (format_template,)
            )
        if last_number is not None:
            await db.execute(
                "UPDATE email_blast_letter_config SET last_number = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (last_number,)
            )
        await db.commit()
    return await get_letter_config()


def generate_letter_number(format_template: str, last_number: int) -> str:
    """Generate letter number based on format template"""
    from datetime import datetime, timezone

    year = datetime.now().year
    next_number = last_number + 1

    result = format_template
    result = result.replace("{{NUMBER}}", str(next_number).zfill(3))  # 001, 002, etc
    result = result.replace("{{YEAR}}", str(year))
    result = result.replace("{{MONTH}}", datetime.now().strftime("%m"))
    result = result.replace("{{MONTH_NAME}}", datetime.now().strftime("%B"))

    return result


async def get_next_letter_number() -> tuple[str, int]:
    """Get next letter number and increment counter"""
    config = await get_letter_config()
    format_template = config['format_template']
    last_number = config['last_number']

    letter_number = generate_letter_number(format_template, last_number)

    # Increment counter
    await update_letter_config(last_number=last_number + 1)

    return letter_number, last_number + 1


# ---------------------------------------------------------------------------
# Campaign Management
# ---------------------------------------------------------------------------

async def create_email_campaign(name: str, subject: str, template: str,
                                from_email: str = "sekretariat@asosiasi.ai",
                                from_name: str = "Sekretariat Asosiasi AI",
                                delay_ms: int = 20_000,
                                created_by_dms_user_id: int | None = None,
                                created_by_email: str | None = None,
                                created_by_name: str | None = None) -> int:
    """Create new email blast campaign"""
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO email_blast_campaigns
               (name, subject, template_message, from_email, from_name, delay_between_ms,
                created_by_dms_user_id, created_by_email, created_by_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                subject,
                template,
                from_email,
                from_name,
                delay_ms,
                created_by_dms_user_id,
                created_by_email,
                created_by_name,
            )
        )
        await db.commit()
        return cursor.lastrowid


async def add_recipients_to_campaign(campaign_id: int, university_ids: list[int]) -> int:
    """Add university emails as recipients"""
    async with get_db() as db:
        # Get universities with emails
        placeholders = ','.join('?' * len(university_ids))
        cursor = await db.execute(
            f"""SELECT id, name, email_kampus FROM universities
                WHERE id IN ({placeholders}) AND email_kampus IS NOT NULL AND email_kampus != ''""",
            university_ids
        )
        universities = await cursor.fetchall()

        # Add recipients
        added = 0
        for uni_id, uni_name, email in universities:
            try:
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO email_blast_recipients
                       (campaign_id, university_id, email, university_name)
                       VALUES (?, ?, ?, ?)""",
                    (campaign_id, uni_id, email, uni_name)
                )
                if cursor.lastrowid is not None and cursor.lastrowid > 0:
                    added += 1
            except:
                pass

        await db.commit()

        # Update total count — accumulate (don't overwrite)
        await db.execute(
            "UPDATE email_blast_campaigns SET total_recipients = total_recipients + ? WHERE id = ?",
            (added, campaign_id)
        )
        await db.commit()

        return added


async def add_email_recipients_from_marketing_contacts(
    campaign_id: int,
    contacts: list[dict],
) -> int:
    """Add email recipients to a campaign from marketing contact results.

    Does NOT require university_id FK — marketing contacts live outside the
    university domain.

    Args:
        campaign_id: email blast campaign ID
        contacts: list of dicts with keys:
            - value         (required, the email address)
            - client_name   (optional, used as university_name)
            - source_url    (optional)
            - result_id     (optional, not used here but included for API compat)

    Returns:
        Number of recipients added.
    """
    added = 0
    async with get_db() as db:
        for contact in contacts:
            email = contact.get("value")
            if not email:
                continue

            try:
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO email_blast_recipients
                       (campaign_id, university_id, email, university_name)
                       VALUES (?, NULL, ?, ?)""",
                    (
                        campaign_id,
                        email,
                        contact.get("client_name"),
                    ),
                )
                if cursor.lastrowid is not None and cursor.lastrowid > 0:
                    added += 1
            except Exception:
                pass

        await db.commit()

        # Update total count — accumulate
        await db.execute(
            "UPDATE email_blast_campaigns SET total_recipients = total_recipients + ? WHERE id = ?",
            (added, campaign_id),
        )
        await db.commit()

    return added


async def add_external_recipients_from_rows(
    campaign_id: int,
    rows: list[dict],
) -> dict[str, int]:
    """Add external recipients directly to a campaign without touching universities.

    Expected row keys come from spreadsheet parsing and may include:
    - email
    - name
    - contact_person
    """
    added = 0
    duplicate_or_existing = 0
    skipped_missing_email = 0
    skipped_invalid_format = 0
    seen_emails: set[str] = set()

    async with get_db() as db:
        for row in rows:
            email = str(row.get("email") or "").strip()
            if not email:
                skipped_missing_email += 1
                continue

            normalized_email = email.lower()
            if normalized_email in seen_emails:
                duplicate_or_existing += 1
                continue
            seen_emails.add(normalized_email)

            # Keep import lightweight: only reject obviously malformed addresses here.
            if "@" not in email or email.startswith("@") or email.endswith("@"):
                skipped_invalid_format += 1
                continue

            display_name = (
                str(row.get("name") or "").strip()
                or str(row.get("contact_person") or "").strip()
                or email
            )

            try:
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO email_blast_recipients
                       (campaign_id, university_id, email, university_name)
                       VALUES (?, NULL, ?, ?)""",
                    (campaign_id, email, display_name),
                )
                if cursor.lastrowid is not None and cursor.lastrowid > 0:
                    added += 1
                else:
                    duplicate_or_existing += 1
            except Exception:
                duplicate_or_existing += 1

        await db.commit()

        await db.execute(
            "UPDATE email_blast_campaigns SET total_recipients = total_recipients + ? WHERE id = ?",
            (added, campaign_id),
        )
        await db.commit()

    return {
        "added": added,
        "duplicate_or_existing": duplicate_or_existing,
        "skipped_missing_email": skipped_missing_email,
        "skipped_invalid_format": skipped_invalid_format,
        "processed_rows": len(rows),
    }


async def add_all_emails_to_campaign(campaign_id: int,
                                      provinces: list[str] = None) -> int:
    """Add all universities with emails to campaign, optionally filtered"""
    async with get_db() as db:
        query = """SELECT id, name, email_kampus FROM universities
                   WHERE email_kampus IS NOT NULL AND email_kampus != '' AND enabled = 1"""
        params: list = []

        if provinces:
            placeholders = ','.join('?' * len(provinces))
            query += f" AND province IN ({placeholders})"
            params.extend(provinces)

        cursor = await db.execute(query, params)
        universities = await cursor.fetchall()

        # Add recipients
        added = 0
        for uni_id, uni_name, email in universities:
            try:
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO email_blast_recipients
                       (campaign_id, university_id, email, university_name)
                       VALUES (?, ?, ?, ?)""",
                    (campaign_id, uni_id, email, uni_name)
                )
                # Only count if actually inserted (rowcount > 0 for aiosqlite)
                if cursor.lastrowid is not None and cursor.lastrowid > 0:
                    added += 1
            except:
                pass

        await db.commit()

        # Update total count — accumulate (don't overwrite)
        await db.execute(
            "UPDATE email_blast_campaigns SET total_recipients = total_recipients + ? WHERE id = ?",
            (added, campaign_id)
        )
        await db.commit()

        return added


async def render_template(template: str, university_name: str,
                          email: str, subject_template: str = None,
                          custom_vars: dict = None) -> tuple[str, str]:
    """Render template with university data"""
    # Replace auto placeholders
    rendered_msg = template
    rendered_msg = rendered_msg.replace('{{university_name}}', university_name or 'Pimpinan Universitas')
    rendered_msg = rendered_msg.replace('{{email}}', email)
    rendered_msg = rendered_msg.replace('{{tanggal}}', datetime.now().strftime('%d %B %Y'))

    # Replace custom variables if provided
    if custom_vars:
        for key, value in custom_vars.items():
            placeholder = f'{{{{{key}}}}}'
            rendered_msg = rendered_msg.replace(placeholder, str(value))

    rendered_subj = subject_template or ""
    rendered_subj = rendered_subj.replace('{{university_name}}', university_name or 'Pimpinan Universitas')

    # Replace custom variables in subject too
    if custom_vars:
        for key, value in custom_vars.items():
            placeholder = f'{{{{{key}}}}}'
            rendered_subj = rendered_subj.replace(placeholder, str(value))

    return rendered_subj, rendered_msg


async def run_email_blast_campaign(campaign_id: int,
                                   smtp_client: SMTPClient = None,
                                   max_recipients: int = None):
    """Run email blast campaign"""
    # Guard: prevent concurrent runs for the same campaign
    if not await _acquire_campaign_lock(campaign_id):
        log.warning(f"[EmailBlast] Campaign {campaign_id} is already running — skipping duplicate start")
        return
    try:
        await _run_email_blast_campaign_inner(campaign_id, smtp_client, max_recipients)
    finally:
        _release_campaign_lock(campaign_id)


async def _run_email_blast_campaign_inner(campaign_id: int,
                                          smtp_client: SMTPClient = None,
                                          max_recipients: int = None):
    """Inner implementation — always called within a campaign lock."""
    async with get_db() as db:
        # Get campaign info
        cursor = await db.execute(
            """SELECT name, subject, template_message, from_email, from_name,
               delay_between_ms, status, attachment_filename, attachment_variables
               FROM email_blast_campaigns WHERE id = ?""",
            (campaign_id,)
        )
        campaign = await cursor.fetchone()
        if not campaign:
            log.error(f"[EmailBlast] Campaign {campaign_id} not found")
            return

        (name, subject, template, from_email, from_name, delay_ms, status,
         attachment_filename, attachment_variables) = campaign

        if status != 'running':
            log.error(f"[EmailBlast] Campaign {campaign_id} is not running (status: {status})")
            return

        # Parse attachment variables
        attachment_vars = {}
        if attachment_variables:
            try:
                attachment_vars = json.loads(attachment_variables)
            except:
                pass

        query = """SELECT id, university_id, email, university_name, created_at
                   FROM email_blast_recipients
                   WHERE campaign_id = ? AND status = 'pending'
                   ORDER BY id"""
        if max_recipients:
            query += f" LIMIT {max_recipients}"

        cursor = await db.execute(query, (campaign_id,))
        recipients = await cursor.fetchall()

        if not recipients:
            log.info(f"[EmailBlast] No pending recipients for campaign {campaign_id}")
            await db.execute(
                "UPDATE email_blast_campaigns SET status = 'completed', completed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), campaign_id)
            )
            await db.commit()
            await broadcast_campaign_update(campaign_id)
            return

        log.info(f"[EmailBlast] Starting campaign {campaign_id} with {len(recipients)} recipients")

    # Use provided or create SMTP client
    if smtp_client is None:
        smtp_client = get_smtp_client()
        if not smtp_client.connect():
            log.error("[EmailBlast] Failed to connect SMTP")
            return

    # Prepare attachment path
    attachment_path = None
    if attachment_filename:
        attachment_path = TEMPLATE_DIR / attachment_filename
        if not attachment_path.exists():
            attachment_path = None

    # Check if we need to generate attachment (even without predefined vars)
    has_attachment_template = attachment_filename is not None

    sent = 0
    failed = 0
    invalid = 0

    # Default subject and message if not set
    if not subject:
        subject = "Kerja Sama - {{university_name}}"
    if not template:
        template = """Yth. Bagian Sekretariat {{university_name}},

Dengan hormat,

Kami dari Asosiasi AI ingin mengajukan kerja sama terkait pengembangan teknologi人工智能 untuk kampus Bapak/Ibu.

Hormat kami,
Sekretariat Asosiasi AI
"""

    for recipient_id, university_id, email, uni_name, recipient_created_at in recipients:
        stopped_status = await _abort_if_campaign_stopped(campaign_id)
        if stopped_status:
            break

        # Check daily quota before processing
        daily_limit = cfg.get("EMAIL_BLAST_DAILY_LIMIT", 200)
        if daily_limit > 0:
            quota = await get_email_blast_quota_info(daily_limit)
            if quota["is_exhausted"]:
                log.warning(f"[EmailBlast] Daily limit reached ({daily_limit}). Stopping campaign {campaign_id}.")
                # Mark campaign as paused and broadcast notification
                async with get_db() as db:
                    await db.execute(
                        "UPDATE email_blast_campaigns SET status = 'paused', paused_at = ? WHERE id = ?",
                        (datetime.now().isoformat(), campaign_id)
                    )
                    await db.commit()
                await broadcast_campaign_update(campaign_id)
                await ws_manager.broadcast_type(
                    "quota_exhausted",
                    campaign_id=campaign_id,
                    remaining=0,
                    daily_limit=daily_limit,
                    pending_count=len(recipients) - (sent + failed),
                )
                break

        log.info(f"[EmailBlast] Processing recipient: id={recipient_id}, email={email}, uni_name={uni_name}")

        # Email validation — skip if invalid (not counted as failed, not counted as sent)
        if cfg.get("VALIDATE_EMAIL_BEFORE_SEND", True):
            valid, reason = validate_email(email)
            if not valid:
                log.warning(f"[EmailBlast] Skipping invalid email {email} (reason={reason})")
                async with get_db() as db:
                    await db.execute(
                        """UPDATE email_blast_recipients
                           SET status = 'invalid', error_message = ? WHERE id = ?""",
                        (f"invalid: {reason}", recipient_id)
                    )
                    await db.execute(
                        "UPDATE email_blast_campaigns SET invalid_count = invalid_count + 1 WHERE id = ?",
                        (campaign_id,)
                    )
                    await db.commit()
                await broadcast_recipient_update(
                    campaign_id,
                    {
                        "id": recipient_id,
                        "campaign_id": campaign_id,
                        "university_id": university_id,
                        "email": email,
                        "university_name": uni_name,
                        "rendered_subject": None,
                        "rendered_message": None,
                        "status": "invalid",
                        "error_message": f"invalid: {reason}",
                        "sent_at": None,
                        "created_at": recipient_created_at,
                        "letter_number": None,
                    },
                )
                invalid += 1
                await _broadcast_blast_progress(campaign_id, sent, failed, invalid, len(recipients))
                continue  # Skip SMTP send for this recipient

        # Generate unique letter number per recipient
        letter_number = None
        try:
            letter_number, _ = await get_next_letter_number()
            log.info(f"[EmailBlast] Generated letter number: {letter_number}")
        except Exception as e:
            log.error(f"[EmailBlast] Error generating letter number: {e}")

        # If uni_name is None/empty, try to get from universities table by email
        if not uni_name:
            try:
                async with get_db() as db:
                    cursor = await db.execute(
                        "SELECT name FROM universities WHERE email_kampus = ? LIMIT 1",
                        (email,)
                    )
                    row = await cursor.fetchone()
                    if row:
                        uni_name = row[0]
                        log.info(f"[EmailBlast] Found university name from email: {uni_name}")
            except Exception as e:
                log.warning(f"[EmailBlast] Could not lookup university name: {e}")

        # Render template
        # Build custom vars for template rendering (only non-empty values)
        custom_vars = {}
        if letter_number:
            custom_vars['nomor_surat'] = letter_number
        if attachment_vars:
            for k, v in attachment_vars.items():
                if v:  # Only add non-empty values
                    custom_vars[k] = v

        rendered_subject, rendered_msg = await render_template(
            template, uni_name or "Yth. Pihak Universitas",
            email, subject, custom_vars
        )

        log.info(f"[EmailBlast] Rendered email body (first 200 chars): {rendered_msg[:200]}")

        log.info(f"[EmailBlast] Sending to {email}: subject='{rendered_subject}'")

        # Generate attachment if needed (always generate if attachment file exists)
        final_attachment = None
        clean_attachment_filename = None
        log.info(f"[EmailBlast] Attachment check: attachment_filename={attachment_filename}, attachment_path={attachment_path}")
        if attachment_path:
            try:
                # Build variables for this recipient - ALWAYS include auto variables
                vars_for_recipient = {
                    'university_name': uni_name or 'Pimpinan Universitas',
                    'email': email,
                    'tanggal': datetime.now().strftime('%d %B %Y'),
                }
                log.info(f"[EmailBlast] BEFORE letter_number: vars={vars_for_recipient}, letter_number={letter_number}")
                # Add letter number if available
                if letter_number:
                    vars_for_recipient['nomor_surat'] = letter_number
                    log.info(f"[EmailBlast] Added nomor_surat: {letter_number}")
                else:
                    log.warning(f"[EmailBlast] No letter_number generated!")
                # Add custom variables from attachment config (but DON'T override auto-generated ones!)
                auto_vars = {'university_name', 'email', 'tanggal', 'nomor_surat'}
                if attachment_vars:
                    for key, value in attachment_vars.items():
                        if key not in auto_vars and value:  # Only add non-empty custom vars
                            vars_for_recipient[key] = value
                    log.info(f"[EmailBlast] Added custom attachment_vars (excluding auto vars)")

                log.info(f"[EmailBlast] FINAL vars_for_recipient: {vars_for_recipient}")
                log.info(f"[EmailBlast] Calling generate_docx with vars: {vars_for_recipient}")

                log.info(f"[EmailBlast] Generating attachment for {email} with vars: {vars_for_recipient}")

                # Debug: verify attachment file exists
                log.info(f"[EmailBlast] Reading from: {attachment_path}, exists: {os.path.exists(attachment_path)}")

                # Generate unique output DOCX path
                docx_filename = _render_filename(
                    attachment_filename.replace('.docx', ''), vars_for_recipient
                )
                output_docx_name = f"{campaign_id}_{recipient_id}_{docx_filename}.docx"
                output_docx_path = TEMPLATE_DIR / output_docx_name

                # Generate DOCX with replaced variables
                docx_result = generate_docx(str(attachment_path), vars_for_recipient, str(output_docx_path))
                log.info(f"[EmailBlast] generate_docx result: {docx_result}")

                if docx_result and os.path.exists(str(output_docx_path)):
                    # Try PDF first (preferred), fall back to DOCX
                    output_pdf_name = f"{campaign_id}_{recipient_id}_{docx_filename}.pdf"
                    output_pdf_path = TEMPLATE_DIR / output_pdf_name

                    log.info(f"[EmailBlast] Converting DOCX to PDF: {output_docx_path} -> {output_pdf_path}")
                    pdf_result = convert_docx_to_pdf(str(output_docx_path), str(output_pdf_path))

                    if pdf_result and os.path.exists(str(output_pdf_path)):
                        final_attachment = str(output_pdf_path)
                        clean_attachment_filename = f"{docx_filename}.pdf"
                        log.info(f"[EmailBlast] PDF created successfully: {output_pdf_path}")
                        # Remove the intermediate DOCX file
                        try:
                            os.remove(str(output_docx_path))
                        except:
                            pass
                    else:
                        # PDF failed (Linux without Word) — send DOCX instead
                        final_attachment = str(output_docx_path)
                        clean_attachment_filename = f"{docx_filename}.docx"
                        log.warning(f"[EmailBlast] PDF conversion FAILED on Linux — sending DOCX instead: {output_docx_path}")
                else:
                    log.error(f"[EmailBlast] Failed to generate DOCX, no attachment will be sent")
            except Exception as e:
                log.error(f"[EmailBlast] Error generating attachment: {e}")
                import traceback
                traceback.print_exc()

        # Send email
        log.info(f"[EmailBlast] About to send email to {email} with attachment: {final_attachment}")
        stopped_status = await _abort_if_campaign_stopped(campaign_id)
        if stopped_status:
            break
        try:
            success, error, send_context = smtp_client.send_email_with_context(
                email, rendered_subject, rendered_msg, _resolve_from_email_for_send(from_email), from_name,
                attachment_path=final_attachment,
                attachment_filename=clean_attachment_filename,
            )
            log.info(f"[EmailBlast] Send result: success={success}, error={error}")
        except Exception as e:
            log.error(f"[EmailBlast] Exception sending email: {e}")
            success = False
            error = str(e)
            send_context = {"from_email": from_email, "from_name": from_name}

        sender_email, sender_name = _get_sender_identity(send_context, from_email, from_name)

        # Cleanup generated attachment
        if final_attachment and os.path.exists(final_attachment):
            try:
                os.remove(final_attachment)
            except:
                pass

        async with get_db() as db:
            event_time = datetime.now().isoformat()
            recipient_event = None
            outbox_event = None
            if success:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'sent', sent_at = ?, rendered_subject = ?, rendered_message = ?, letter_number = ? WHERE id = ?""",
                    (event_time, rendered_subject, rendered_msg, letter_number, recipient_id)
                )
                # Log to outbox
                outbox_cursor = await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, recipient_id, source, email, university_name, from_email, from_name,
                        rendered_subject, rendered_message, status, error_message)
                       VALUES (?, ?, 'campaign', ?, ?, ?, ?, ?, ?, 'sent', NULL)""",
                    (campaign_id, recipient_id, email, uni_name, sender_email, sender_name, rendered_subject, rendered_msg)
                )
                # Increment quota inside same transaction (no nested connection)
                await _increment_quota_and_broadcast(db, campaign_id, daily_limit)
                # Update campaign sent_count in same transaction
                await db.execute(
                    "UPDATE email_blast_campaigns SET sent_count = sent_count + 1 WHERE id = ?",
                    (campaign_id,)
                )
                recipient_event = {
                    "id": recipient_id,
                    "campaign_id": campaign_id,
                    "university_id": university_id,
                    "email": email,
                    "university_name": uni_name,
                    "rendered_subject": rendered_subject,
                    "rendered_message": rendered_msg,
                    "status": "sent",
                    "error_message": None,
                    "sent_at": event_time,
                    "created_at": recipient_created_at,
                    "letter_number": letter_number,
                }
                outbox_event = {
                    "id": outbox_cursor.lastrowid,
                    "campaign_id": campaign_id,
                    "email": email,
                    "university_name": uni_name,
                    "from_email": sender_email,
                    "from_name": sender_name,
                    "subject": rendered_subject,
                    "body": rendered_msg,
                    "status": "sent",
                    "sent_at": event_time,
                    "error_message": None,
                    "campaign_name": name,
                    "source": "campaign",
                }
                sent += 1
            else:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'failed', error_message = ? WHERE id = ?""",
                    (error, recipient_id)
                )
                # Log to outbox
                outbox_cursor = await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, recipient_id, source, email, university_name, from_email, from_name,
                        rendered_subject, status, error_message)
                       VALUES (?, ?, 'campaign', ?, ?, ?, ?, ?, 'failed', ?)""",
                    (campaign_id, recipient_id, email, uni_name, sender_email, sender_name, rendered_subject, error)
                )
                # Update campaign failed_count in same transaction
                await db.execute(
                    "UPDATE email_blast_campaigns SET failed_count = failed_count + 1 WHERE id = ?",
                    (campaign_id,)
                )
                recipient_event = {
                    "id": recipient_id,
                    "campaign_id": campaign_id,
                    "university_id": university_id,
                    "email": email,
                    "university_name": uni_name,
                    "rendered_subject": rendered_subject,
                    "rendered_message": rendered_msg,
                    "status": "failed",
                    "error_message": error,
                    "sent_at": None,
                    "created_at": recipient_created_at,
                    "letter_number": letter_number,
                }
                outbox_event = {
                    "id": outbox_cursor.lastrowid,
                    "campaign_id": campaign_id,
                    "email": email,
                    "university_name": uni_name,
                    "from_email": sender_email,
                    "from_name": sender_name,
                    "subject": rendered_subject,
                    "body": None,
                    "status": "failed",
                    "sent_at": event_time,
                    "error_message": error,
                    "campaign_name": name,
                    "source": "campaign",
                }
                failed += 1

            await db.commit()

        if recipient_event:
            await broadcast_recipient_update(campaign_id, recipient_event)
        if outbox_event:
            await broadcast_outbox_logged(outbox_event)

        # Broadcast progress OUTSIDE the DB transaction (no lock contention)
        if success or error:
            await _broadcast_blast_progress(campaign_id, sent, failed, invalid, len(recipients))

        # Delay between emails
        actual_delay_ms = compute_inter_send_delay_ms(delay_ms)
        if actual_delay_ms > 0:
            stopped_status = await _sleep_with_campaign_checks(campaign_id, actual_delay_ms)
            if stopped_status:
                break

    final_status, pending_count = await _finalize_campaign_status_after_run(campaign_id, max_recipients)
    log.info(
        f"[EmailBlast] Campaign {campaign_id} finished: {sent} sent, {failed} failed, {invalid} invalid, pending={pending_count}, final_status={final_status}"
    )

    await broadcast_campaign_update(campaign_id)


async def retry_failed_email_blast(campaign_id: int, max_recipients: int = None):
    """Retry sending to failed recipients in a campaign. Reuses run_email_blast_campaign logic."""
    if not await _acquire_campaign_lock(campaign_id):
        log.warning(f"[EmailBlast] Campaign {campaign_id} is already running — cannot retry concurrently")
        return
    try:
        await _retry_failed_email_blast_inner(campaign_id, max_recipients)
    finally:
        _release_campaign_lock(campaign_id)
        # Always sync counters after retry to reflect actual state
        await sync_campaign_counters(campaign_id)


async def _retry_failed_email_blast_inner(campaign_id: int, max_recipients: int = None):
    """Inner implementation — always called within a campaign lock."""
    async with get_db() as db:
        # Get campaign info
        cursor = await db.execute(
            """SELECT name, subject, template_message, from_email, from_name,
               delay_between_ms, status, attachment_filename, attachment_variables
               FROM email_blast_campaigns WHERE id = ?""",
            (campaign_id,)
        )
        campaign = await cursor.fetchone()
        if not campaign:
            log.error(f"[EmailBlast] Retry failed — campaign {campaign_id} not found")
            return

        (name, subject, template, from_email, from_name, delay_ms, status,
         attachment_filename, attachment_vars_raw) = campaign

        # Parse attachment variables
        attachment_vars = {}
        if attachment_vars_raw:
            try:
                attachment_vars = json.loads(attachment_vars_raw)
            except:
                pass

        # Only process 'pending' recipients (which are the retried ones)
        query = """SELECT id, university_id, email, university_name, letter_number, created_at FROM email_blast_recipients
                   WHERE campaign_id = ? AND status = 'pending'
                   ORDER BY id"""
        if max_recipients:
            query += f" LIMIT {max_recipients}"

        cursor = await db.execute(query, (campaign_id,))
        recipients = await cursor.fetchall()

        if not recipients:
            log.info(f"[EmailBlast] No pending recipients for retry campaign {campaign_id}")
            await db.execute(
                "UPDATE email_blast_campaigns SET status = 'completed', completed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), campaign_id)
            )
            await db.commit()
            await broadcast_campaign_update(campaign_id)
            return

        log.info(f"[EmailBlast] Retry campaign {campaign_id} with {len(recipients)} failed (now pending) recipients")

    # Letter numbers are reused from original send (stored in letter_number column).
    # Only generate fresh for recipients that didn't have a letter number (legacy).

    smtp_client = get_smtp_client()
    if not smtp_client.connect():
        log.error("[EmailBlast] Retry — failed to connect SMTP")
        return

    attachment_path = None
    if attachment_filename:
        attachment_path = TEMPLATE_DIR / attachment_filename
        if not attachment_path.exists():
            attachment_path = None

    sent = 0
    failed = 0
    invalid = 0

    for recipient_id, university_id, email, uni_name, stored_letter_number, recipient_created_at in recipients:
        stopped_status = await _abort_if_campaign_stopped(campaign_id)
        if stopped_status:
            break

        # Check daily quota before processing
        daily_limit = cfg.get("EMAIL_BLAST_DAILY_LIMIT", 200)
        if daily_limit > 0:
            quota = await get_email_blast_quota_info(daily_limit)
            if quota["is_exhausted"]:
                log.warning(f"[EmailBlast] Retry — daily limit reached. Stopping retry for campaign {campaign_id}.")
                async with get_db() as db:
                    await db.execute(
                        "UPDATE email_blast_campaigns SET status = 'paused', paused_at = ? WHERE id = ?",
                        (datetime.now().isoformat(), campaign_id)
                    )
                    await db.commit()
                await broadcast_campaign_update(campaign_id)
                await ws_manager.broadcast_type(
                    "quota_exhausted",
                    campaign_id=campaign_id,
                    remaining=0,
                    daily_limit=daily_limit,
                    pending_count=0,
                )
                break

        log.info(f"[EmailBlast] Retry — processing recipient: id={recipient_id}, email={email}")

        # Email validation — skip if invalid
        if cfg.get("VALIDATE_EMAIL_BEFORE_SEND", True):
            valid, reason = validate_email(email)
            if not valid:
                log.warning(f"[EmailBlast] Retry — skipping invalid email {email} (reason={reason})")
                async with get_db() as db:
                    await db.execute(
                        """UPDATE email_blast_recipients
                           SET status = 'invalid', error_message = ? WHERE id = ?""",
                        (f"invalid: {reason}", recipient_id)
                    )
                    await db.execute(
                        "UPDATE email_blast_campaigns SET invalid_count = invalid_count + 1 WHERE id = ?",
                        (campaign_id,)
                    )
                    await db.commit()
                await broadcast_recipient_update(
                    campaign_id,
                    {
                        "id": recipient_id,
                        "campaign_id": campaign_id,
                        "university_id": university_id,
                        "email": email,
                        "university_name": uni_name,
                        "rendered_subject": None,
                        "rendered_message": None,
                        "status": "invalid",
                        "error_message": f"invalid: {reason}",
                        "sent_at": None,
                        "created_at": recipient_created_at,
                        "letter_number": stored_letter_number,
                    },
                )
                invalid += 1
                await _broadcast_blast_progress(campaign_id, sent, failed, invalid, len(recipients))
                continue

        if not uni_name:
            try:
                async with get_db() as db:
                    cursor = await db.execute(
                        "SELECT name FROM universities WHERE email_kampus = ? LIMIT 1",
                        (email,)
                    )
                    row = await cursor.fetchone()
                    if row:
                        uni_name = row[0]
            except Exception:
                pass

        # Use stored letter number from original send; generate fresh only for legacy recipients
        letter_number = stored_letter_number
        if not letter_number:
            try:
                letter_number, _ = await get_next_letter_number()
                log.info(f"[EmailBlast] No stored letter number for recipient {recipient_id}, generated: {letter_number}")
            except Exception as e:
                log.error(f"[EmailBlast] Error generating letter number for recipient {recipient_id}: {e}")

        # Render template
        custom_vars = {}
        if letter_number:
            custom_vars['nomor_surat'] = letter_number
        if attachment_vars:
            for k, v in attachment_vars.items():
                if v:
                    custom_vars[k] = v

        rendered_subject, rendered_msg = await render_template(
            template, uni_name or "Yth. Pihak Universitas",
            email, subject, custom_vars
        )

        success = False
        error = None
        attachment_to_send = None
        clean_attachment_filename = None
        generated_docx = None
        generated_pdf = None

        try:
            stopped_status = await _abort_if_campaign_stopped(campaign_id)
            if stopped_status:
                break
            if attachment_path:
                has_docx_template = attachment_filename and attachment_filename.endswith('.docx')
                if has_docx_template:
                    try:
                        # Build vars first (needed for filename placeholder replacement)
                        vars_for_recipient = {
                            'university_name': uni_name or 'Pimpinan Universitas',
                            'email': email,
                            'tanggal': datetime.now().strftime('%d %B %Y'),
                        }
                        if letter_number:
                            vars_for_recipient['nomor_surat'] = letter_number
                        auto_vars = {'university_name', 'email', 'tanggal', 'nomor_surat'}
                        if attachment_vars:
                            for k, v in attachment_vars.items():
                                if k not in auto_vars and v:
                                    vars_for_recipient[k] = v

                        # Render filename with placeholders (e.g. "Surat Audiensi - {{university_name}}.docx")
                        docx_filename = _render_filename(
                            attachment_filename.replace('.docx', ''), vars_for_recipient
                        )
                        output_docx_name = f"{campaign_id}_{recipient_id}_{docx_filename}.docx"
                        output_pdf_name = f"{campaign_id}_{recipient_id}_{docx_filename}.pdf"
                        generated_docx = str(TEMPLATE_DIR / output_docx_name)
                        generated_pdf = str(TEMPLATE_DIR / output_pdf_name)

                        docx_result = generate_docx(str(attachment_path), vars_for_recipient, generated_docx)
                        if docx_result and os.path.exists(generated_docx):
                            pdf_result = convert_docx_to_pdf(generated_docx, generated_pdf)
                            if pdf_result and os.path.exists(generated_pdf):
                                attachment_to_send = generated_pdf
                                clean_attachment_filename = f"{docx_filename}.pdf"
                                log.info(f"[EmailBlast] Retry — PDF attachment ready: {generated_pdf}")
                            else:
                                log.error(f"[EmailBlast] Retry — PDF conversion failed, sending DOCX: {generated_docx}")
                                attachment_to_send = generated_docx
                                clean_attachment_filename = f"{docx_filename}.docx"
                        else:
                            log.error(f"[EmailBlast] Retry — Failed to generate DOCX attachment")
                    except Exception as e:
                        log.warning(f"[EmailBlast] Retry — Failed to generate attachment: {e}")

            ok, err, send_context = smtp_client.send_email_with_context(
                to_email=email,
                subject=rendered_subject,
                body=rendered_msg,
                from_email=_resolve_from_email_for_send(from_email),
                from_name=from_name,
                attachment_path=attachment_to_send,
                attachment_filename=clean_attachment_filename,
            )
            success = ok
            error = err
        except Exception as e:
            error = str(e)
            log.error(f"[EmailBlast] Retry — send error for {email}: {e}")
            send_context = {"from_email": from_email, "from_name": from_name}

        sender_email, sender_name = _get_sender_identity(send_context, from_email, from_name)

        for generated_file in (generated_pdf, generated_docx):
            if generated_file and os.path.exists(generated_file):
                try:
                    os.remove(generated_file)
                except:
                    pass

        async with get_db() as db:
            event_time = datetime.now().isoformat()
            recipient_event = None
            outbox_event = None
            if success:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'sent', sent_at = ?, rendered_subject = ?, rendered_message = ?, letter_number = ? WHERE id = ?""",
                    (event_time, rendered_subject, rendered_msg, letter_number, recipient_id)
                )
                outbox_cursor = await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, recipient_id, source, email, university_name, from_email, from_name,
                        rendered_subject, rendered_message, status, error_message)
                       VALUES (?, ?, 'campaign', ?, ?, ?, ?, ?, ?, 'sent', NULL)""",
                    (campaign_id, recipient_id, email, uni_name, sender_email, sender_name, rendered_subject, rendered_msg)
                )
                await _increment_quota_and_broadcast(db, campaign_id, daily_limit)
                await db.execute(
                    "UPDATE email_blast_campaigns SET sent_count = sent_count + 1 WHERE id = ?",
                    (campaign_id,)
                )
                recipient_event = {
                    "id": recipient_id,
                    "campaign_id": campaign_id,
                    "university_id": university_id,
                    "email": email,
                    "university_name": uni_name,
                    "rendered_subject": rendered_subject,
                    "rendered_message": rendered_msg,
                    "status": "sent",
                    "error_message": None,
                    "sent_at": event_time,
                    "created_at": recipient_created_at,
                    "letter_number": letter_number,
                }
                outbox_event = {
                    "id": outbox_cursor.lastrowid,
                    "campaign_id": campaign_id,
                    "email": email,
                    "university_name": uni_name,
                    "from_email": sender_email,
                    "from_name": sender_name,
                    "subject": rendered_subject,
                    "body": rendered_msg,
                    "status": "sent",
                    "sent_at": event_time,
                    "error_message": None,
                    "campaign_name": name,
                    "source": "campaign",
                }
                sent += 1
            else:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'failed', error_message = ? WHERE id = ?""",
                    (error or "Unknown error", recipient_id)
                )
                outbox_cursor = await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, recipient_id, source, email, university_name, from_email, from_name,
                        rendered_subject, status, error_message)
                       VALUES (?, ?, 'campaign', ?, ?, ?, ?, ?, 'failed', ?)""",
                    (campaign_id, recipient_id, email, uni_name, sender_email, sender_name, rendered_subject, error or "Unknown error")
                )
                await db.execute(
                    "UPDATE email_blast_campaigns SET failed_count = failed_count + 1 WHERE id = ?",
                    (campaign_id,)
                )
                recipient_event = {
                    "id": recipient_id,
                    "campaign_id": campaign_id,
                    "university_id": university_id,
                    "email": email,
                    "university_name": uni_name,
                    "rendered_subject": rendered_subject,
                    "rendered_message": rendered_msg,
                    "status": "failed",
                    "error_message": error or "Unknown error",
                    "sent_at": None,
                    "created_at": recipient_created_at,
                    "letter_number": letter_number,
                }
                outbox_event = {
                    "id": outbox_cursor.lastrowid,
                    "campaign_id": campaign_id,
                    "email": email,
                    "university_name": uni_name,
                    "from_email": sender_email,
                    "from_name": sender_name,
                    "subject": rendered_subject,
                    "body": None,
                    "status": "failed",
                    "sent_at": event_time,
                    "error_message": error or "Unknown error",
                    "campaign_name": name,
                    "source": "campaign",
                }
                failed += 1
            await db.commit()

        if recipient_event:
            await broadcast_recipient_update(campaign_id, recipient_event)
        if outbox_event:
            await broadcast_outbox_logged(outbox_event)

        # Broadcast progress OUTSIDE the DB transaction (no lock contention)
        if success or error:
            await _broadcast_blast_progress(campaign_id, sent, failed, invalid, len(recipients))

        actual_delay_ms = compute_inter_send_delay_ms(delay_ms)
        if actual_delay_ms > 0:
            stopped_status = await _sleep_with_campaign_checks(campaign_id, actual_delay_ms)
            if stopped_status:
                break

    log.info(f"[EmailBlast] Retry campaign {campaign_id} done: {sent} sent, {failed} failed")
    await broadcast_campaign_update(campaign_id)


async def get_campaign_status(campaign_id: int) -> dict:
    """Get campaign status"""
    query = """SELECT id, name, subject, template_message, from_email, from_name,
                      delay_between_ms, status, total_recipients, sent_count, failed_count,
                      invalid_count,
                      attachment_filename, attachment_variables,
                      created_by_dms_user_id, created_by_email, created_by_name,
                      started_by_dms_user_id, started_by_email, started_by_name,
                      created_at, started_at, completed_at, paused_at
               FROM email_blast_campaigns WHERE id = ?"""
    params: list[object] = [campaign_id]

    async with get_db() as db:
        cursor = await db.execute(
            query,
            params,
        )
        campaign = await cursor.fetchone()

        if not campaign:
            return None

        return {
            "id": campaign[0],
            "name": campaign[1],
            "subject": campaign[2],
            "template_message": campaign[3],
            "from_email": campaign[4],
            "from_name": campaign[5],
            "delay_between_ms": campaign[6],
            "status": campaign[7],
            "total_recipients": campaign[8],
            "sent_count": campaign[9],
            "failed_count": campaign[10],
            "invalid_count": campaign[11],
            "attachment_filename": campaign[12],
            "attachment_variables": campaign[13],
            "created_by_dms_user_id": campaign[14],
            "created_by_email": campaign[15],
            "created_by_name": campaign[16],
            "started_by_dms_user_id": campaign[17],
            "started_by_email": campaign[18],
            "started_by_name": campaign[19],
            "created_at": campaign[20],
            "started_at": campaign[21],
            "completed_at": campaign[22],
            "paused_at": campaign[23],
        }


async def list_campaigns(status: str = None) -> list[dict]:
    """List all campaigns"""
    async with get_db() as db:
        query = """SELECT id, name, subject, status, total_recipients,
                          sent_count, failed_count, invalid_count,
                          created_by_dms_user_id, created_by_email, created_by_name,
                          started_by_dms_user_id, started_by_email, started_by_name,
                          created_at
                   FROM email_blast_campaigns"""
        conditions: list[str] = []
        params: list[object] = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor = await db.execute(query + " ORDER BY created_at DESC", params)

        campaigns = await cursor.fetchall()

        return [
            {
                "id": c[0],
                "name": c[1],
                "subject": c[2],
                "status": c[3],
                "total_recipients": c[4],
                "sent_count": c[5],
                "failed_count": c[6],
                "invalid_count": c[7],
                "created_by_dms_user_id": c[8],
                "created_by_email": c[9],
                "created_by_name": c[10],
                "started_by_dms_user_id": c[11],
                "started_by_email": c[12],
                "started_by_name": c[13],
                "created_at": c[14]
            }
            for c in campaigns
        ]


async def pause_campaign(campaign_id: int) -> bool:
    """Pause running campaign"""
    async with get_db() as db:
        await db.execute(
            "UPDATE email_blast_campaigns SET status = 'paused', paused_at = ? WHERE id = ?",
            (datetime.now().isoformat(), campaign_id)
        )
        await db.commit()
    await broadcast_campaign_update(campaign_id)
    return True


async def cancel_campaign(campaign_id: int) -> bool:
    """Cancel campaign"""
    async with get_db() as db:
        await db.execute(
            "UPDATE email_blast_campaigns SET status = 'cancelled' WHERE id = ?",
            (campaign_id,)
        )
        await db.commit()
    await broadcast_campaign_update(campaign_id)
    return True


async def delete_recipient(recipient_id: int, campaign_id: int | None = None) -> bool:
    """Delete a recipient from campaign"""
    async with get_db() as db:
        # Get campaign_id first
        query = "SELECT campaign_id FROM email_blast_recipients WHERE id = ?"
        params: list[object] = [recipient_id]
        if campaign_id is not None:
            query += " AND campaign_id = ?"
            params.append(campaign_id)

        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        if not row:
            return False

        campaign_id = row[0]

        # Delete recipient
        await db.execute(
            "DELETE FROM email_blast_recipients WHERE id = ?",
            (recipient_id,)
        )
        await db.commit()

        # Update campaign total count
        cursor = await db.execute(
            "SELECT COUNT(*) FROM email_blast_recipients WHERE campaign_id = ?",
            (campaign_id,)
        )
        count = (await cursor.fetchone())[0]

        await db.execute(
            "UPDATE email_blast_campaigns SET total_recipients = ? WHERE id = ?",
            (count, campaign_id)
        )
        await db.commit()

        return True


# -----------------------------------------------------------------------------
# IMAP Functions for receiving email replies
# -----------------------------------------------------------------------------

import imaplib
import email
from email.header import decode_header


def _normalize_mailbox_email(value: str) -> str:
    return str(value or '').strip().lower()


def _parse_email_sort_ts(value: str) -> int:
    if not value:
        return 0

    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return int(parsed.timestamp())
    except Exception:
        pass

    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return int(parsed.timestamp())
    except Exception:
        return 0


def _build_mailbox_cache_key(mailbox_email: str, uid: int) -> str:
    return f"{_normalize_mailbox_email(mailbox_email)}:{int(uid)}"


def _load_managed_smtp_accounts_config() -> list[dict]:
    raw_accounts = cfg.get("SMTP_ACCOUNTS", "")
    if not str(raw_accounts or '').strip():
        return []

    try:
        accounts = json.loads(raw_accounts)
    except Exception as exc:
        log.error("[EmailBlast] Failed to parse SMTP_ACCOUNTS for IMAP mailbox discovery: %s", exc)
        return []

    return accounts if isinstance(accounts, list) else []


def get_imap_mailboxes() -> list[dict]:
    """Return all IMAP mailboxes that should be watched for replies/sent mail."""
    mailboxes: list[dict] = []
    seen: set[str] = set()

    imap_host = str(cfg.get("IMAP_HOST", cfg.get("SMTP_HOST", "mail.asosiasi.ai"))).strip() or "mail.asosiasi.ai"
    imap_port = int(cfg.get("IMAP_PORT", 993))
    imap_use_ssl = bool(cfg.get("IMAP_USE_SSL", True))
    legacy_user = _normalize_mailbox_email(cfg.get("IMAP_USERNAME", ""))
    legacy_password = str(cfg.get("IMAP_PASSWORD", "") or "")

    for account in _load_managed_smtp_accounts_config():
        if not account.get("enabled", True):
            continue

        user = _normalize_mailbox_email(account.get("user"))
        password = str(account.get("password") or "")
        if legacy_user and user == legacy_user and legacy_password:
            # Allow IMAP auth to use a mailbox-specific password that differs
            # from the SMTP credential stored in rotation accounts.
            password = legacy_password
        if not user or not password or user in seen:
            continue

        mailboxes.append({
            "mailbox_email": user,
            "host": imap_host,
            "port": imap_port,
            "use_ssl": imap_use_ssl,
            "user": user,
            "password": password,
        })
        seen.add(user)

    if legacy_user and legacy_password and legacy_user not in seen:
        mailboxes.append({
            "mailbox_email": legacy_user,
            "host": imap_host,
            "port": imap_port,
            "use_ssl": imap_use_ssl,
            "user": legacy_user,
            "password": legacy_password,
        })

    return mailboxes


def get_imap_connection(mailbox: dict | None = None):
    """Create IMAP connection for a specific mailbox."""
    try:
        mailbox = mailbox or ({
            "host": cfg.IMAP_HOST,
            "port": cfg.IMAP_PORT,
            "user": cfg.IMAP_USERNAME,
            "password": cfg.IMAP_PASSWORD,
            "use_ssl": cfg.IMAP_USE_SSL,
            "mailbox_email": cfg.IMAP_USERNAME,
        })
        imap_host = mailbox["host"]
        imap_port = mailbox["port"]
        imap_user = mailbox["user"]
        imap_pass = mailbox["password"]
        use_ssl = mailbox["use_ssl"]
        mailbox_email = mailbox.get("mailbox_email") or imap_user

        log.debug(f"Connecting to IMAP mailbox {mailbox_email}: {imap_host}:{imap_port} (SSL: {use_ssl})")

        if use_ssl:
            conn = imaplib.IMAP4_SSL(imap_host, imap_port)
        else:
            conn = imaplib.IMAP4(imap_host, imap_port)

        conn.login(imap_user, imap_pass)
        log.debug(f"IMAP login successful for {mailbox_email}")
        return conn
    except Exception as e:
        log.warning(f"Failed to connect to IMAP for {mailbox_email}: {e}")
        return None


def parse_email_message(msg):
    """Parse email message and extract relevant fields"""
    result = {
        'subject': '',
        'from': '',
        'to': '',
        'date': '',
        'body_text': '',
        'body_html': '',
        'message_id': '',
        'in_reply_to': '',
    }

    # Get subject
    if msg['Subject']:
        decoded = decode_header(msg['Subject'])
        subject = ''
        for part, encoding in decoded:
            if isinstance(part, bytes):
                subject += part.decode(encoding or 'utf-8')
            else:
                subject += part
        result['subject'] = subject

    # Get from
    if msg['From']:
        result['from'] = msg['From']

    # Get to
    if msg['To']:
        result['to'] = msg['To']

    # Get date
    if msg['Date']:
        result['date'] = msg['Date']

    # Get message-id
    if msg['Message-ID']:
        result['message_id'] = msg['Message-ID']

    # Get in-reply-to (for threading)
    if msg['In-Reply-To']:
        result['in_reply_to'] = msg['In-Reply-To']

    # Get body
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition'))

            if content_type == 'text/plain' and 'attachment' not in content_disposition:
                try:
                    result['body_text'] = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    pass
            elif content_type == 'text/html' and 'attachment' not in content_disposition:
                try:
                    result['body_html'] = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    pass
    else:
        try:
            result['body_text'] = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        except:
            pass

    return result


def _extract_email_address(value: str) -> str:
    """Extract a plain email address from a header field."""
    if not value:
        return ''

    match = re.search(r'<([^>]+)>', value)
    if match:
        return match.group(1).strip()

    match = re.search(r'[\w\.-]+@[\w\.-]+', value)
    if match:
        return match.group(0).strip()

    return value.strip()


def _build_inbound_email_entry(mailbox_email: str, uid: int, parsed: dict) -> dict:
    """Normalize an IMAP message into the inbox-cache payload shape."""
    from_field = parsed.get('from') or ''
    normalized_mailbox = _normalize_mailbox_email(mailbox_email)
    cache_key = _build_mailbox_cache_key(normalized_mailbox, uid)
    return {
        'id': cache_key,
        'mailbox_email': normalized_mailbox,
        'uid': uid,
        'sort_ts': _parse_email_sort_ts(parsed.get('date') or ''),
        'message_id': parsed.get('message_id') or '',
        'in_reply_to': parsed.get('in_reply_to') or '',
        'from_email': _extract_email_address(from_field),
        'from_name': re.sub(r'<.+?>', '', from_field).strip(),
        'to_email': parsed.get('to') or '',
        'subject': parsed.get('subject') or '',
        'body': (parsed.get('body_text') or '')[:2000],
        'date': parsed.get('date') or '',
        'is_read': True,
    }


def _build_sent_email_entry(mailbox_email: str, uid: int, parsed: dict) -> dict:
    from_field = parsed.get('from') or ''
    normalized_mailbox = _normalize_mailbox_email(mailbox_email)
    cache_key = _build_mailbox_cache_key(normalized_mailbox, uid)

    return {
        'id': cache_key,
        'mailbox_email': normalized_mailbox,
        'uid': uid,
        'sort_ts': _parse_email_sort_ts(parsed.get('date') or ''),
        'message_id': parsed.get('message_id') or '',
        'from_email': _extract_email_address(from_field),
        'from_name': re.sub(r'<.+?>', '', from_field).strip(),
        'to_email': parsed.get('to') or '',
        'subject': parsed.get('subject') or '',
        'body': (parsed.get('body_text') or '')[:2000],
        'date': parsed.get('date') or '',
    }


async def _get_cached_mailbox_uids(table_name: str, mailbox_email: str) -> set[int]:
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT uid FROM {table_name} WHERE mailbox_email = ?",
            (_normalize_mailbox_email(mailbox_email),),
        )
        rows = await cursor.fetchall()
    return {int(row[0]) for row in rows}


async def _store_inbox_entries(entries: list[dict]) -> None:
    if not entries:
        return

    async with get_db() as db:
        for entry in entries:
            await db.execute(
                """INSERT OR REPLACE INTO email_inbox_cache
                   (cache_key, mailbox_email, uid, sort_ts, message_id, in_reply_to,
                    from_email, from_name, to_email, subject, body, date, is_read, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    entry['id'], entry['mailbox_email'], entry['uid'], entry['sort_ts'],
                    entry['message_id'], entry['in_reply_to'], entry['from_email'],
                    entry['from_name'], entry['to_email'], entry['subject'], entry['body'],
                    entry['date'], entry['is_read'],
                ),
            )
        await db.commit()


async def _store_sent_entries(entries: list[dict]) -> None:
    if not entries:
        return

    async with get_db() as db:
        for entry in entries:
            await db.execute(
                """INSERT OR REPLACE INTO email_sent_cache
                   (cache_key, mailbox_email, uid, sort_ts, message_id, from_email,
                    from_name, to_email, subject, body, date, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    entry['id'], entry['mailbox_email'], entry['uid'], entry['sort_ts'],
                    entry['message_id'], entry['from_email'], entry['from_name'],
                    entry['to_email'], entry['subject'], entry['body'], entry['date'],
                ),
            )
        await db.commit()


def _safe_close_imap_connection(conn) -> None:
    if not conn:
        return

    try:
        conn.close()
    except Exception:
        pass

    try:
        conn.logout()
    except Exception:
        pass


def _decode_imap_id_list(messages) -> list[str]:
    if not messages or not messages[0]:
        return []
    raw_value = messages[0]
    if isinstance(raw_value, bytes):
        return raw_value.decode().split()
    return str(raw_value).split()


def _extract_uid_from_fetch_payload(msg_data, fallback_uid: str) -> int:
    payload = msg_data[0][0] if isinstance(msg_data[0], tuple) else msg_data[0]
    if isinstance(payload, bytes):
        raw_payload = payload
    else:
        raw_payload = str(payload).encode()

    uid_match = re.search(rb'UID (\d+)', raw_payload)
    return int(uid_match.group(1)) if uid_match else int(fallback_uid)


async def _lookup_campaign_ids_for_inbound_email(from_email: str) -> list[int]:
    """Find campaigns whose recipient list contains the sender email."""
    normalized_email = (from_email or '').strip().lower()
    if not normalized_email:
        return []

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT DISTINCT campaign_id FROM email_blast_recipients WHERE lower(email) = ?",
            (normalized_email,),
        )
        rows = await cursor.fetchall()

    return [int(row[0]) for row in rows if row[0] is not None]


async def fetch_inbox_emails(limit: int = 50, unread_only: bool = False, offset: int = 0) -> tuple[list[dict], int]:
    """
    Fetch emails from INBOX with SQLite caching.
    Strategy:
    - On first request: fetch from IMAP, populate cache
    - On subsequent requests: return from cache (instant), fetch new emails in background
    - Cache TTL: 60 seconds (controlled by cache_fetched_at)
    """
    CACHE_TTL_SECONDS = 60

    log.info(f"Fetching inbox emails (limit: {limit}, offset: {offset})")

    # Step 1: Always try to serve from cache first (stale-while-revalidate)
    results, total_count = await _fetch_from_cache(limit, offset)

    # Check cache freshness
    cache_age: float | None = None
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT fetched_at FROM email_inbox_cache ORDER BY fetched_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if row:
            fetched_at_str = row[0]
            if '+' in fetched_at_str or fetched_at_str.endswith('Z'):
                fetched_at = datetime.fromisoformat(fetched_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
            else:
                fetched_at = datetime.fromisoformat(fetched_at_str)
            cache_age = (datetime.now() - fetched_at).total_seconds()

    cache_fresh = cache_age is not None and cache_age < CACHE_TTL_SECONDS
    if cache_age is not None:
        log.info(f"[InboxCache] Cache age: {cache_age:.1f}s, fresh: {cache_fresh}, total: {total_count}")

    # Cache is empty — must block on IMAP to populate
    if total_count == 0:
        log.info("[InboxCache] Cache empty — blocking IMAP fetch")
        return await _blocking_imap_fetch(limit, offset, unread_only)

    # Cache has data. Serve it immediately (even if stale).
    # Trigger background refresh if stale and no refresh is already running.
    if not cache_fresh:
        _maybe_trigger_background_refresh()

    return results, total_count


async def _fetch_from_cache(limit: int, offset: int) -> tuple[list[dict], int]:
    """Return emails from cache with pagination."""
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM email_inbox_cache")
        row = await cursor.fetchone()
        total_count = row[0] if row else 0

        cursor = await db.execute(
            """SELECT cache_key, mailbox_email, uid, message_id, in_reply_to,
                      from_email, from_name, to_email, subject, body, date, is_read
               FROM email_inbox_cache
               ORDER BY sort_ts DESC, uid DESC, fetched_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset)
        )
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            'id': row[0],
            'mailbox_email': row[1],
            'uid': row[2],
            'message_id': row[3],
            'in_reply_to': row[4],
            'from_email': row[5],
            'from_name': row[6],
            'to_email': row[7],
            'subject': row[8],
            'body': row[9],
            'date': row[10],
            'is_read': bool(row[11]),
        })
    return results, total_count


async def _fetch_from_cache_fallback(limit: int, offset: int) -> tuple[list[dict], int]:
    """Fallback to cache even if stale."""
    log.info("[InboxCache] Fallback to stale cache")
    return await _fetch_from_cache(limit, offset)


# Module-level flag to prevent concurrent background refreshes
_inbox_bg_refresh_running = False


def _maybe_trigger_background_refresh():
    """Trigger background refresh if one isn't already running."""
    global _inbox_bg_refresh_running
    if not _inbox_bg_refresh_running:
        _inbox_bg_refresh_running = True
        asyncio.create_task(_refresh_inbox_cache_background())


async def refresh_inbox_cache_now() -> bool:
    """Synchronously refresh inbox cache if no other refresh is running."""
    global _inbox_bg_refresh_running
    if _inbox_bg_refresh_running:
        return False

    _inbox_bg_refresh_running = True
    await _refresh_inbox_cache_background()
    return True


async def watch_inbox_replies_forever() -> None:
    """Periodically poll IMAP so new replies can be pushed over WebSocket.

    Honors the runtime flag ``EMAIL_BLAST_INBOX_WATCH_ENABLED`` (default
    True). When false, the loop sleeps and re-checks every minute so the
    operator can flip the flag back on without restarting the orchestrator
    — useful when the upstream mail server (e.g. mail.asosiasi.ai) is down
    and IMAP polling is just spamming warnings.
    """
    startup_delay = max(0, int(cfg.get("EMAIL_BLAST_INBOX_WATCH_STARTUP_DELAY_SECONDS", 15)))
    poll_interval = max(10, int(cfg.get("EMAIL_BLAST_INBOX_WATCH_INTERVAL_SECONDS", 30)))

    if startup_delay:
        await asyncio.sleep(startup_delay)

    disabled_announced = False
    while True:
        if not bool(cfg.get("EMAIL_BLAST_INBOX_WATCH_ENABLED", True)):
            if not disabled_announced:
                log.info(
                    "[InboxWatch] Disabled via EMAIL_BLAST_INBOX_WATCH_ENABLED=false; "
                    "sleeping (will re-check flag every 60s)"
                )
                disabled_announced = True
            await asyncio.sleep(60)
            continue

        if disabled_announced:
            log.info("[InboxWatch] Re-enabled via flag; resuming polling")
            disabled_announced = False

        try:
            await refresh_inbox_cache_now()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("[InboxWatch] Polling error: %s", exc, exc_info=True)

        await asyncio.sleep(poll_interval)


async def _blocking_imap_fetch(limit: int, offset: int, unread_only: bool) -> tuple[list[dict], int]:
    """Fetch emails from IMAP synchronously (blocking). Used when cache is empty."""
    mailboxes = get_imap_mailboxes()
    if not mailboxes:
        log.error("[InboxCache] No IMAP mailboxes configured")
        return await _fetch_from_cache_fallback(limit, offset)

    fetch_window = max(limit + offset, 100)
    fetched_entries: list[dict] = []

    try:
        for mailbox in mailboxes:
            conn = get_imap_connection(mailbox)
            if not conn:
                continue

            try:
                status, folder_count = conn.select('INBOX')
                if status != 'OK':
                    log.error("[InboxCache] IMAP select failed for %s: %s", mailbox['mailbox_email'], status)
                    continue

                log.debug("[InboxCache] INBOX select for %s: %s messages=%s", mailbox['mailbox_email'], status, folder_count)

                search_criteria = 'UNSEEN' if unread_only else 'ALL'
                status, messages = conn.search(None, search_criteria)
                if status != 'OK':
                    log.error("[InboxCache] IMAP search failed for %s: %s", mailbox['mailbox_email'], status)
                    continue

                email_ids = _decode_imap_id_list(messages)
                cached_uids = await _get_cached_mailbox_uids('email_inbox_cache', mailbox['mailbox_email'])
                all_reversed = email_ids[::-1]
                recent_ids = all_reversed[:fetch_window]
                new_ids = [email_id for email_id in all_reversed if int(email_id) not in cached_uids][:500]
                to_fetch_ids = list(dict.fromkeys([*recent_ids, *new_ids]))

                log.debug(
                    "[InboxCache] Mailbox %s total=%s cached=%s fetching=%s",
                    mailbox['mailbox_email'], len(email_ids), len(cached_uids), len(to_fetch_ids),
                )

                for email_id in to_fetch_ids:
                    try:
                        status, msg_data = conn.fetch(email_id, '(RFC822)')
                        if status != 'OK' or not msg_data or not msg_data[0]:
                            continue

                        msg = email.message_from_bytes(msg_data[0][1])
                        parsed = parse_email_message(msg)
                        fetched_entries.append(_build_inbound_email_entry(mailbox['mailbox_email'], int(email_id), parsed))
                    except Exception as exc:
                        log.error("[InboxCache] Error parsing email %s for %s: %s", email_id, mailbox['mailbox_email'], exc)
            finally:
                _safe_close_imap_connection(conn)

        await _store_inbox_entries(fetched_entries)
        if fetched_entries:
            log.info("[InboxCache] Updated cache with %s emails across %s mailbox(es)", len(fetched_entries), len(mailboxes))
        return await _fetch_from_cache(limit, offset)
    except Exception as e:
        log.error(f"Error in blocking IMAP fetch: {e}")
        return await _fetch_from_cache_fallback(limit, offset)


async def _refresh_inbox_cache_background():
    """Background task: fetch new emails and update cache without blocking."""
    global _inbox_bg_refresh_running
    try:
        log.debug("[InboxCache] Background refresh starting")
        new_entries: list[dict] = []

        for mailbox in get_imap_mailboxes():
            conn = get_imap_connection(mailbox)
            if not conn:
                continue

            try:
                status, _ = conn.select('INBOX')
                if status != 'OK':
                    continue

                status, messages = conn.search(None, 'ALL')
                if status != 'OK':
                    continue

                email_ids = _decode_imap_id_list(messages)
                all_reversed = email_ids[::-1]
                cached_uids = await _get_cached_mailbox_uids('email_inbox_cache', mailbox['mailbox_email'])
                new_ids = [email_id for email_id in all_reversed if int(email_id) not in cached_uids][:500]

                if not new_ids:
                    log.debug("[InboxCache] Mailbox %s: no new emails", mailbox['mailbox_email'])
                    continue

                log.info("[InboxCache] Mailbox %s: fetching %s new emails", mailbox['mailbox_email'], len(new_ids))

                for email_id in new_ids:
                    try:
                        status, msg_data = conn.fetch(email_id, '(RFC822)')
                        if status != 'OK' or not msg_data or not msg_data[0]:
                            continue

                        msg = email.message_from_bytes(msg_data[0][1])
                        parsed = parse_email_message(msg)
                        new_entries.append(_build_inbound_email_entry(mailbox['mailbox_email'], int(email_id), parsed))
                    except Exception:
                        continue
            finally:
                _safe_close_imap_connection(conn)

        if not new_entries:
            log.debug("[InboxCache] Background refresh: no parsable new emails")
            return

        await _store_inbox_entries(new_entries)

        for entry in sorted(new_entries, key=lambda item: (item.get('sort_ts', 0), str(item.get('id', '')))):
            campaign_ids = await _lookup_campaign_ids_for_inbound_email(entry['from_email'])
            await broadcast_inbox_received(entry, campaign_ids)

        log.debug("[InboxCache] Background refresh complete")
    except Exception as e:
        log.error(f"[InboxCache] Background refresh error: {e}")
    finally:
        _inbox_bg_refresh_running = False


# ─── Sent Folder Fetching ──────────────────────────────────────────────────────

_sent_cache_running = False


def _find_sent_folder(conn) -> str | None:
    """Find the correct Sent folder name on the IMAP server."""
    # Common Sent folder names
    candidates = [
        'INBOX.Sent',
        '[Gmail]/Sent Mail',
        'INBOX.Sent Items',
        'Sent',
        'INBOX.SENT',
        'Sent Items',
    ]

    try:
        status, folders = conn.list()
        if status != 'OK':
            return None

        # Parse folder list response
        # Format 1: (attrs, delimiter, name) tuple — e.g. (b'(\\HasNoChildren)', b'.', b'INBOX.Sent')
        # Format 2: raw bytes — e.g. b'(\\HasNoChildren) "." INBOX.Sent'
        folder_names = []
        for folder in folders:
            if isinstance(folder, tuple):
                # Second element is the folder name (bytes)
                name_bytes = folder[1]
                if isinstance(name_bytes, bytes):
                    folder_names.append(name_bytes.decode('utf-8', errors='ignore'))
            elif isinstance(folder, bytes):
                # Try to extract folder name from raw bytes
                # Format: b'(\\HasNoChildren) "." INBOX.Sent'
                try:
                    decoded = folder.decode('utf-8', errors='ignore')
                    # Find the folder name after the last quote
                    parts = decoded.rsplit('"', 2)
                    if len(parts) >= 3:
                        folder_names.append(parts[-1].strip())
                    else:
                        folder_names.append(decoded)
                except Exception:
                    pass

        log.info(f"[SentFolder] Available folders: {folder_names}")

        # Try each candidate
        for candidate in candidates:
            for fname in folder_names:
                fname_lower = fname.lower()
                cand_lower = candidate.lower()
                if fname_lower == cand_lower or fname_lower.endswith(cand_lower) or cand_lower in fname_lower:
                    log.info(f"[SentFolder] Matched folder: '{fname}' (candidate: '{candidate}')")
                    return fname

        # Fallback: search for anything with 'sent' in name
        for fname in folder_names:
            if 'sent' in fname.lower():
                log.info(f"[SentFolder] Fallback match: '{fname}'")
                return fname

        log.warning(f"[SentFolder] No Sent folder found among: {folder_names}")
        return None
    except Exception as e:
        log.error(f"[SentFolder] Error listing folders: {e}")
        import traceback
        log.error(traceback.format_exc())
        return None


async def fetch_sent_emails(limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """
    Fetch sent emails from the IMAP Sent folder + email_outbox (for real-time).
    Merges both sources so newly sent emails appear immediately without waiting for IMAP.

    Data flow:
    1. IMAP cache (SQLite) — historical emails fetched from IMAP Sent folder
    2. email_outbox — emails just sent (up to 24h old, for real-time)
    3. Merge by (to_email, subject) dedup, sort by date descending
    """
    CACHE_TTL_SECONDS = 60

    log.info(f"[SentFolder] Fetching sent emails (limit: {limit}, offset: {offset})")

    # Check cache freshness
    cache_age: float | None = None
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT fetched_at FROM email_sent_cache ORDER BY fetched_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if row:
            fetched_at_str = row[0]
            if '+' in fetched_at_str or fetched_at_str.endswith('Z'):
                fetched_at = datetime.fromisoformat(fetched_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
            else:
                fetched_at = datetime.fromisoformat(fetched_at_str)
            cache_age = (datetime.now() - fetched_at).total_seconds()

    cache_fresh = cache_age is not None and cache_age < CACHE_TTL_SECONDS
    if cache_age is not None:
        log.info(f"[SentFolder] Cache age: {cache_age:.1f}s, fresh: {cache_fresh}")

    # ── Fetch from IMAP cache ──────────────────────────────
    imap_results, imap_total = await _fetch_sent_from_cache(limit=10_000, offset=0)

    # ── Fetch recent outbox entries (last 24h, not yet in IMAP cache) ──
    OUTBOX_WINDOW_HOURS = 24
    outbox_results: list[dict] = []

    async with get_db() as db:
        cursor = await db.execute(
                        f"""SELECT id, campaign_id, recipient_id, email, university_name,
                                                from_email, from_name, rendered_subject, rendered_message, sent_at
                                 FROM email_outbox
                                 WHERE status = 'sent'
                                     AND sent_at >= datetime('now', '-{OUTBOX_WINDOW_HOURS} hours')
                                 ORDER BY sent_at DESC"""
        )
        outbox_rows = await cursor.fetchall()
        for row in outbox_rows:
            outbox_results.append({
                'id': row[0],
              'message_id': f"outbox-{row[0]}",
              'recipient_id': row[2],
              'from_email': row[5] or 'sekretariat@asosiasi.ai',
              'from_name': row[6] or 'Sekretariat Asosiasi AI',
              'to_email': row[3],
              'subject': row[7],
              'body': row[8],
              'date': row[9],
            })

    # ── Merge: dedup outbox entries that are already in IMAP ──
    dedup_keys: set[tuple] = {
        (
            (r.get('from_email') or '').lower().strip(),
            (r.get('to_email') or '').lower().strip(),
            (r.get('subject') or '').lower().strip(),
        )
        for r in imap_results if r.get('to_email') and r.get('subject')
    }

    merged: list[dict] = []
    for item in outbox_results:
        key = (
            (item.get('from_email') or '').lower().strip(),
            (item.get('to_email') or '').lower().strip(),
            (item.get('subject') or '').lower().strip(),
        )
        if key not in dedup_keys:
            merged.append(item)
            dedup_keys.add(key)

    merged.extend(imap_results)

    # Sort by date descending (newest first)
    def parse_date(item: dict) -> datetime:
        d = item.get('date')
        if not d:
            return datetime.min
        # Try SQLite format first (YYYY-MM-DD HH:MM:SS)
        try:
            return datetime.fromisoformat(d)
        except Exception:
            pass
        # Try RFC2822 format (Wed, 25 Mar 2026 17:29:58 +0700)
        try:
            # email module is imported at module level — accessible via enclosing scope
            parsed = email.utils.parsedate_to_datetime(d)
            return parsed.replace(tzinfo=None)
        except Exception:
            pass
        return datetime.min

    merged.sort(key=parse_date, reverse=True)
    total_count = len(merged)
    paginated = merged[offset:offset + limit]

    log.info(f"[SentFolder] Merged total: {total_count} (imap={imap_total}, outbox={len(outbox_results)})")

    # ── Decide whether to fetch IMAP ──────────────────────
    if imap_total == 0 and len(outbox_results) == 0:
        # Both empty — block on IMAP fetch and merge the result
        log.info("[SentFolder] Both IMAP cache and outbox empty — blocking IMAP fetch")
        imap_fetch_result = await _blocking_sent_fetch(limit, offset)
        if imap_fetch_result:
            imap_fetched, _ = imap_fetch_result
            # Merge those into the response too
            for item in imap_fetched:
                key = (
                    (item.get('from_email') or '').lower().strip(),
                    (item.get('to_email') or '').lower().strip(),
                    (item.get('subject') or '').lower().strip(),
                )
                if key not in dedup_keys:
                    merged.append(item)
                    dedup_keys.add(key)
            merged.sort(key=parse_date, reverse=True)
            total_count = len(merged)
            paginated = merged[offset:offset + limit]
            log.info(f"[SentFolder] After blocking fetch: total={total_count}")
    elif not cache_fresh:
        _maybe_trigger_sent_refresh()

    return paginated, total_count


async def _fetch_sent_from_cache(limit: int, offset: int) -> tuple[list[dict], int]:
    """Return sent emails from cache with pagination."""
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM email_sent_cache")
        row = await cursor.fetchone()
        total_count = row[0] if row else 0

        cursor = await db.execute(
            """SELECT cache_key, mailbox_email, uid, message_id, from_email, from_name,
                      to_email, subject, body, date
               FROM email_sent_cache
               ORDER BY sort_ts DESC, uid DESC, fetched_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset)
        )
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            'id': row[0],
            'mailbox_email': row[1],
            'uid': row[2],
            'message_id': row[3],
            'from_email': row[4],
            'from_name': row[5],
            'to_email': row[6],
            'subject': row[7],
            'body': row[8],
            'date': row[9],
        })
    return results, total_count


def _maybe_trigger_sent_refresh():
    """Trigger background refresh if one isn't already running."""
    global _sent_cache_running
    if not _sent_cache_running:
        _sent_cache_running = True
        asyncio.create_task(_refresh_sent_cache_background())


async def _blocking_sent_fetch(limit: int, offset: int) -> tuple[list[dict], int] | None:
    """
    Fetch sent emails from IMAP using stable UIDs (not sequence numbers).
    Returns (results, total) on success, None on failure.
    """
    mailboxes = get_imap_mailboxes()
    if not mailboxes:
        log.error("[SentFolder] No IMAP mailboxes configured")
        return None

    try:
        fetch_window = max(limit + offset, 100)
        results: list[dict] = []

        for mailbox in mailboxes:
            conn = get_imap_connection(mailbox)
            if not conn:
                continue

            try:
                sent_folder = _find_sent_folder(conn)
                if not sent_folder:
                    log.error("[SentFolder] Could not find Sent folder for %s", mailbox['mailbox_email'])
                    continue

                log.info("[SentFolder] Selecting folder %s for %s", sent_folder, mailbox['mailbox_email'])
                status, _ = conn.select(f'"{sent_folder}"')
                if status != 'OK':
                    log.error("[SentFolder] Failed to select folder for %s: %s", mailbox['mailbox_email'], status)
                    continue

                try:
                    status, messages = conn.uid('SEARCH', None, 'ALL')
                    fetch_mode = 'uid'
                except Exception as exc:
                    log.warning("[SentFolder] UID SEARCH not supported for %s (%s), falling back", mailbox['mailbox_email'], exc)
                    status, messages = conn.search(None, 'ALL')
                    fetch_mode = 'sequence'

                if status != 'OK':
                    log.error("[SentFolder] IMAP search failed for %s: %s", mailbox['mailbox_email'], status)
                    continue

                raw_uids = _decode_imap_id_list(messages)
                cached_uids = await _get_cached_mailbox_uids('email_sent_cache', mailbox['mailbox_email'])
                all_uids_reversed = raw_uids[::-1]
                recent_uids = all_uids_reversed[:fetch_window]
                new_uids = [uid for uid in all_uids_reversed if int(uid) not in cached_uids][:500]
                to_fetch_uids = list(dict.fromkeys([*recent_uids, *new_uids]))

                log.info(
                    "[SentFolder] Mailbox %s total=%s cached=%s fetching=%s",
                    mailbox['mailbox_email'], len(raw_uids), len(cached_uids), len(to_fetch_uids),
                )

                for uid_str in to_fetch_uids:
                    try:
                        if fetch_mode == 'uid':
                            status, msg_data = conn.uid('FETCH', uid_str, '(UID RFC822)')
                        else:
                            status, msg_data = conn.fetch(uid_str, '(RFC822)')
                        if status != 'OK' or not msg_data or not msg_data[0]:
                            continue

                        actual_uid = _extract_uid_from_fetch_payload(msg_data, uid_str) if fetch_mode == 'uid' else int(uid_str)
                        msg_bytes = msg_data[0][1]
                        msg = email.message_from_bytes(msg_bytes)
                        parsed = parse_email_message(msg)
                        results.append(_build_sent_email_entry(mailbox['mailbox_email'], actual_uid, parsed))
                    except Exception as exc:
                        log.error("[SentFolder] Error fetching UID %s for %s: %s", uid_str, mailbox['mailbox_email'], exc)
                        continue
            finally:
                _safe_close_imap_connection(conn)

        await _store_sent_entries(results)
        cached_results, total = await _fetch_sent_from_cache(limit, offset)
        log.info("[SentFolder] Blocking fetch complete: %s emails fetched across %s mailbox(es)", len(results), len(mailboxes))
        return cached_results, total

    except Exception as e:
        log.error(f"[SentFolder] Error in blocking fetch: {e}")
        return None


async def _refresh_sent_cache_background():
    """Background task: fetch new sent emails."""
    global _sent_cache_running
    try:
        log.debug("[SentFolder] Background refresh starting")
        new_entries: list[dict] = []

        for mailbox in get_imap_mailboxes():
            conn = get_imap_connection(mailbox)
            if not conn:
                continue

            try:
                sent_folder = _find_sent_folder(conn)
                if not sent_folder:
                    continue

                status, _ = conn.select(f'"{sent_folder}"')
                if status != 'OK':
                    continue

                try:
                    status, messages = conn.uid('SEARCH', None, 'ALL')
                    fetch_mode = 'uid'
                except Exception as exc:
                    log.warning("[SentFolder] UID SEARCH not supported for %s (%s), falling back", mailbox['mailbox_email'], exc)
                    status, messages = conn.search(None, 'ALL')
                    fetch_mode = 'sequence'

                if status != 'OK':
                    continue

                raw_uids = _decode_imap_id_list(messages)
                cached_uids = await _get_cached_mailbox_uids('email_sent_cache', mailbox['mailbox_email'])
                new_uids = [uid for uid in raw_uids[::-1] if int(uid) not in cached_uids][:500]

                if not new_uids:
                    log.debug("[SentFolder] Mailbox %s: no new emails", mailbox['mailbox_email'])
                    continue

                log.info("[SentFolder] Mailbox %s: fetching %s new emails", mailbox['mailbox_email'], len(new_uids))

                for uid_str in new_uids:
                    try:
                        if fetch_mode == 'uid':
                            status, msg_data = conn.uid('FETCH', uid_str, '(UID RFC822)')
                        else:
                            status, msg_data = conn.fetch(uid_str, '(RFC822)')
                        if status != 'OK' or not msg_data or not msg_data[0]:
                            continue

                        actual_uid = _extract_uid_from_fetch_payload(msg_data, uid_str) if fetch_mode == 'uid' else int(uid_str)
                        msg = email.message_from_bytes(msg_data[0][1])
                        parsed = parse_email_message(msg)
                        new_entries.append(_build_sent_email_entry(mailbox['mailbox_email'], actual_uid, parsed))
                    except Exception as e:
                        log.warning(f"[SentFolder] Background refresh error for UID {uid_str}: {e}")
                        continue
            finally:
                _safe_close_imap_connection(conn)

        await _store_sent_entries(new_entries)
        log.debug("[SentFolder] Background refresh complete")
    except Exception as e:
        log.error(f"[SentFolder] Background refresh error: {e}")
    finally:
        _sent_cache_running = False




async def get_campaign_replies(campaign_id: int, limit: int = 50) -> tuple[list[dict], int]:
    """Get replies for a specific campaign by matching recipient emails. Returns (replies, total)."""
    # First get the campaign's recipient emails
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT email FROM email_blast_recipients WHERE campaign_id = ?",
            (campaign_id,)
        )
        rows = await cursor.fetchall()
        recipient_emails = [row[0] for row in rows]

    if not recipient_emails:
        return [], 0

    # Fetch inbox emails
    all_inbox, _ = await fetch_inbox_emails(limit=limit)

    # Filter emails that are replies from recipients
    replies = []
    for inbox_email in all_inbox:
        from_email = inbox_email.get('from_email', '').lower()
        for recipient_email in recipient_emails:
            if from_email == recipient_email.lower():
                inbox_email['campaign_id'] = campaign_id
                replies.append(inbox_email)
                break

    return replies, len(replies)


async def send_test_email(
    campaign_id: int,
    to_email: str,
    subject: str = None,
    body: str = None,
    from_email: str = None,
    from_name: str = None,
    attachment_filename: str = None,
    custom_vars: dict = None
) -> tuple[bool, str]:
    """
    Send a single test email using campaign's template and attachment.
    If subject/body are provided, use them directly (unsaved draft state).
    Otherwise fall back to saved campaign data.
    Does NOT create a recipient record — purely for validation.
    Returns (success, message).
    """
    # Get campaign data from DB (for fallback and attachment vars)
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT name, subject, template_message, from_email, from_name,
                      attachment_filename, attachment_variables
               FROM email_blast_campaigns WHERE id = ?""",
            (campaign_id,)
        )
        row = await cursor.fetchone()

    if not row:
        return False, "Campaign not found"

    db_name, db_subject, db_template, db_from_email, db_from_name, db_attachment_filename, attachment_vars_json = row

    if not to_email:
        return False, "Recipient email is required"

    # Use provided values, or fall back to saved campaign
    final_subject = subject if subject is not None else db_subject
    final_body = body if body is not None else db_template
    final_from_email = from_email if from_email is not None else db_from_email
    final_from_name = from_name if from_name is not None else db_from_name
    final_attachment_filename = attachment_filename if attachment_filename is not None else db_attachment_filename

    # Merge provided custom vars with defaults
    vars_for_recipient = {
        'university_name': 'Universitas Contoh Indonesia',
        'email': to_email,
        'tanggal': datetime.now().strftime('%d %B %Y'),
    }

    # Generate letter number (always, for {{nomor_surat}} placeholder)
    letter_number, _ = await get_next_letter_number()
    vars_for_recipient['nomor_surat'] = letter_number

    # Add custom vars (but not auto ones)
    auto_vars = {'university_name', 'email', 'tanggal', 'nomor_surat'}
    if custom_vars:
        for key, value in custom_vars.items():
            if key not in auto_vars and value:
                vars_for_recipient[key] = value

    # Render subject and body
    rendered_subject, rendered_msg = await render_template(
        final_body or '',
        vars_for_recipient['university_name'],
        to_email,
        final_subject or '',
        vars_for_recipient
    )

    # Handle attachment
    final_attachment = None
    clean_attachment_filename = None
    if final_attachment_filename:
        attachment_path = str(TEMPLATE_DIR / final_attachment_filename)
        if os.path.exists(attachment_path):
            docx_filename = _render_filename(final_attachment_filename.replace('.docx', ''), vars_for_recipient)
            output_docx_name = f"{campaign_id}_{docx_filename}.docx"
            output_docx_path = TEMPLATE_DIR / output_docx_name

            docx_result = generate_docx(attachment_path, vars_for_recipient, str(output_docx_path))

            if docx_result and os.path.exists(str(output_docx_path)):
                # Convert to PDF (preferred), fall back to DOCX on Linux
                output_pdf_name = f"{campaign_id}_{docx_filename}.pdf"
                output_pdf_path = TEMPLATE_DIR / output_pdf_name
                pdf_result = convert_docx_to_pdf(str(output_docx_path), str(output_pdf_path))

                if pdf_result and os.path.exists(str(output_pdf_path)):
                    final_attachment = str(output_pdf_path)
                    clean_attachment_filename = f"{docx_filename}.pdf"
                    log.info(f"[EmailBlast] PDF generated: {output_pdf_path}")
                    # Remove intermediate DOCX only when PDF succeeded
                    try:
                        os.remove(str(output_docx_path))
                    except:
                        pass
                else:
                    # PDF failed (Linux without Word) — send DOCX instead
                    final_attachment = str(output_docx_path)
                    clean_attachment_filename = f"{docx_filename}.docx"
                    log.warning(f"[EmailBlast] Test email — PDF conversion FAILED on Linux, sending DOCX: {output_docx_path}")

    # Send email
    smtp_client = SMTPClient()
    sender_email = str(final_from_email or "sekretariat@asosiasi.ai")
    sender_name = str(final_from_name or "Sekretariat Asosiasi AI")
    try:
        success, error, send_context = smtp_client.send_email_with_context(
            to_email,
            rendered_subject,
            rendered_msg,
            _resolve_from_email_for_send(final_from_email) or "sekretariat@asosiasi.ai",
            final_from_name or "Sekretariat Asosiasi AI",
            attachment_path=final_attachment,
            attachment_filename=clean_attachment_filename,
        )

        sender_email, sender_name = _get_sender_identity(send_context, final_from_email, final_from_name)

        if success:
            log.info(f"[EmailBlast] Test email sent to {to_email}")
            # Log to outbox
            async with get_db() as db:
                outbox_cursor = await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, source, email, from_email, from_name, rendered_subject, rendered_message, status, error_message)
                       VALUES (?, 'test', ?, ?, ?, ?, ?, 'sent', NULL)""",
                    (campaign_id, to_email, sender_email, sender_name, rendered_subject, rendered_msg)
                )
                await db.commit()
            await broadcast_outbox_logged(
                {
                    "id": outbox_cursor.lastrowid,
                    "campaign_id": campaign_id,
                    "email": to_email,
                    "university_name": None,
                    "from_email": sender_email,
                    "from_name": sender_name,
                    "subject": rendered_subject,
                    "body": rendered_msg,
                    "status": "sent",
                    "sent_at": datetime.now().isoformat(),
                    "error_message": None,
                    "campaign_name": db_name,
                    "source": "test",
                }
            )
            # Cleanup
            if final_attachment and os.path.exists(final_attachment):
                try:
                    os.remove(final_attachment)
                except:
                    pass
            return True, f"Test email sent to {to_email}"
        else:
            # Log failure
            async with get_db() as db:
                outbox_cursor = await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, source, email, from_email, from_name, rendered_subject, status, error_message)
                       VALUES (?, 'test', ?, ?, ?, ?, 'failed', ?)""",
                    (campaign_id, to_email, sender_email, sender_name, rendered_subject or '', error)
                )
                await db.commit()
            await broadcast_outbox_logged(
                {
                    "id": outbox_cursor.lastrowid,
                    "campaign_id": campaign_id,
                    "email": to_email,
                    "university_name": None,
                    "from_email": sender_email,
                    "from_name": sender_name,
                    "subject": rendered_subject or '',
                    "body": None,
                    "status": "failed",
                    "sent_at": datetime.now().isoformat(),
                    "error_message": error,
                    "campaign_name": db_name,
                    "source": "test",
                }
            )
            return False, f"Failed to send: {error}"
    finally:
        smtp_client.disconnect()
