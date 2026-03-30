"""
Email Blast Module - Send bulk emails via SMTP
"""
import asyncio
import json
import os
import re
import smtplib
import ssl
import socket
import subprocess
import shutil
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

import socks

from orchestrator.config import cfg, log
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

        await db.execute(
            "UPDATE email_blast_campaigns SET sent_count = ?, failed_count = ?, total_recipients = ? WHERE id = ?",
            (sent, failed, sent + failed + pending, campaign_id)
        )
        await db.commit()

    log.info(f"[EmailBlast] Synced counters for campaign {campaign_id}: sent={sent}, failed={failed}, pending={pending}")
    return {"sent_count": sent, "failed_count": failed, "pending_count": pending}


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


async def _broadcast_blast_progress(campaign_id: int, sent_count: int, failed_count: int, total: int, status: str = "running") -> None:
    """Broadcast blast progress to all WebSocket clients for real-time UI updates."""
    pct = round((sent_count + failed_count) / total * 100, 1) if total > 0 else 0
    await ws_manager.broadcast_type(
        "blast_progress",
        campaign_id=campaign_id,
        sent_count=sent_count,
        failed_count=failed_count,
        total=total,
        percent=pct,
        status=status,
    )


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


class SMTPClient:
    """SMTP client with multi-account rotation to prevent bans.

    Supports two modes:
    1. Multi-account (SMTP_ACCOUNTS JSON config): rotates through multiple
       SMTP accounts, switching after ROTATE_AFTER_N_EMAILS or on auth error.
    2. Legacy single-account (SMTP_HOST/USERNAME): uses one account only.

    Thread-safe via a lock for rotation decisions.
    """

    def __init__(self):
        self._rotate_after = cfg.get("ROTATE_AFTER_N_EMAILS", 50)
        self._rotation_lock = threading.Lock()

        # Load accounts
        self._accounts: list[SMTPAccount] = []
        self._current_index = 0

        raw_accounts = cfg.get("SMTP_ACCOUNTS", "")
        if raw_accounts:
            try:
                accounts_data = json.loads(raw_accounts)
                for acc in accounts_data:
                    self._accounts.append(SMTPAccount(
                        host=acc.get("host", "mail.asosiasi.ai"),
                        port=int(acc.get("port", 465)),
                        user=acc.get("user", ""),
                        password=acc.get("password", ""),
                        use_ssl=acc.get("use_ssl", True),
                        from_name=acc.get("from_name", "Sekretariat Asosiasi AI"),
                    ))
                log.info(f"[EmailBlast] SMTP: loaded {len(self._accounts)} accounts for rotation")
            except Exception as e:
                log.error(f"[EmailBlast] SMTP_ACCOUNTS JSON parse error: {e}. Falling back to single account.")
                self._accounts = []

        # Fallback: single legacy account
        if not self._accounts:
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

    def _maybe_rotate(self) -> None:
        """Rotate to next account if limit reached or current is degraded."""
        acc = self._current_account
        if (acc.email_count >= self._rotate_after and len(self._accounts) > 1) or acc.degraded:
            self._rotate_next()

    def _rotate_next(self) -> None:
        """Switch to next account, disconnecting the current one."""
        old = self._current_account
        self._disconnect_account(old)
        old.email_count = 0  # reset counter for next round
        old.degraded = False

        # Pick next non-degraded account
        start = self._current_index
        attempts = 0
        while attempts < len(self._accounts):
            self._current_index = (self._current_index + 1) % len(self._accounts)
            attempts += 1
            if not self._accounts[self._current_index].degraded:
                break

        new_acc = self._current_account
        log.info(
            f"[EmailBlast] SMTP rotated: {old.user} (sent={old.email_count}) → {new_acc.user} "
            f"(degraded={new_acc.degraded}, total_accounts={len(self._accounts)})"
        )

    def _disconnect_account(self, acc: SMTPAccount) -> None:
        """Disconnect a specific account's connection."""
        if acc._connection:
            try:
                acc._connection.quit()
            except Exception:
                pass
            acc._connection = None

    def _ensure_connected(self) -> bool:
        """Ensure current account is connected. Rotates if needed."""
        acc = self._current_account
        if acc._connection is not None:
            return True

        # Rotate if needed before connecting
        self._maybe_rotate()
        acc = self._current_account  # may have changed

        global _original_create_connection
        socks_config = _get_socks_config()
        should_patch = socks_config["enabled"]

        try:
            if should_patch:
                if _original_create_connection is None:
                    _original_create_connection = socket.create_connection
                    socket.create_connection = _socks_create_connection
                log.info(f"[EmailBlast] SOCKS5 proxy active: {socks_config['host']}:{socks_config['port']}")

            log.info(f"[EmailBlast] SMTP connecting: {acc.host}:{acc.port} as {acc.user} (SOCKS5={socks_config['enabled']})")

            if acc.use_ssl:
                context = ssl.create_default_context()
                conn = smtplib.SMTP_SSL(acc.host, acc.port, context=context)
            else:
                conn = smtplib.SMTP(acc.host, acc.port)
                conn.ehlo()
                conn.starttls(context=ssl.create_default_context())

            conn.login(acc.user, acc.password)
            acc._connection = conn
            acc.degraded = False
            log.info(f"[EmailBlast] SMTP connected: {acc.user}")
            return True

        except Exception as e:
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

    def send_email(self, to_email: str, subject: str, body: str,
                   from_email: str = None, from_name: str = None,
                   attachment_path: str = None,
                   attachment_filename: str = None) -> tuple[bool, str]:
        """Send single email with optional attachment. Thread-safe rotation."""
        with self._rotation_lock:
            connected = self._ensure_connected()
            if not connected:
                return False, "SMTP: no account available (all degraded or rotated)"

        # Build message (no lock held)
        acc = self._current_account
        try:
            msg = MIMEMultipart('mixed')
            from_addr = from_email or acc.user
            from_display = from_name or acc.from_name
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

            log.info(
                f"[EmailBlast] Sent to {to_email} via {acc.user} "
                f"(account_count={acc.email_count}/{self._rotate_after})"
            )

            # Check if we should rotate after this send
            with self._rotation_lock:
                self._maybe_rotate()

            return True, ""

        except Exception as e:
            err_str = str(e).lower()
            log.error(f"[EmailBlast] Send failed to {to_email} via {acc.user}: {e}")

            # Auth error → degrade and rotate
            if any(kw in err_str for kw in ("auth", "535", "501", "534", "user", "password", "authentication")):
                with self._rotation_lock:
                    acc.degraded = True
                    self._disconnect_account(acc)
                    self._rotate_next()
                return False, f"SMTP auth error ({acc.user}), rotated: {str(e)}"

            return False, str(e)

    def get_status(self) -> dict:
        """Return per-account status for monitoring."""
        return {
            "total_accounts": len(self._accounts),
            "rotate_after": self._rotate_after,
            "accounts": [
                {
                    "user": acc.user,
                    "email_count": acc.email_count,
                    "degraded": acc.degraded,
                    "connected": acc._connection is not None,
                }
                for acc in self._accounts
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
                                delay_ms: int = 20_000) -> int:
    """Create new email blast campaign"""
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO email_blast_campaigns
               (name, subject, template_message, from_email, from_name, delay_between_ms)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, subject, template, from_email, from_name, delay_ms)
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

        # Get pending recipients
        query = """SELECT id, email, university_name FROM email_blast_recipients
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

    for recipient_id, email, uni_name in recipients:
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
                await ws_manager.broadcast_type(
                    "quota_exhausted",
                    campaign_id=campaign_id,
                    remaining=0,
                    daily_limit=daily_limit,
                    pending_count=len(recipients) - (sent + failed),
                )
                break

        log.info(f"[EmailBlast] Processing recipient: id={recipient_id}, email={email}, uni_name={uni_name}")

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
        try:
            success, error = smtp_client.send_email(
                email, rendered_subject, rendered_msg, from_email, from_name,
                attachment_path=final_attachment,
                attachment_filename=clean_attachment_filename,
            )
            log.info(f"[EmailBlast] Send result: success={success}, error={error}")
        except Exception as e:
            log.error(f"[EmailBlast] Exception sending email: {e}")
            success = False
            error = str(e)

        # Cleanup generated attachment
        if final_attachment and os.path.exists(final_attachment):
            try:
                os.remove(final_attachment)
            except:
                pass

        async with get_db() as db:
            if success:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'sent', sent_at = ?, rendered_subject = ?, rendered_message = ?, letter_number = ? WHERE id = ?""",
                    (datetime.now().isoformat(), rendered_subject, rendered_msg, letter_number, recipient_id)
                )
                # Log to outbox
                await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, source, email, university_name, rendered_subject, rendered_message, status, error_message)
                       VALUES (?, 'campaign', ?, ?, ?, ?, 'sent', NULL)""",
                    (campaign_id, email, uni_name, rendered_subject, rendered_msg)
                )
                # Increment quota inside same transaction (no nested connection)
                await _increment_quota_and_broadcast(db, campaign_id, daily_limit)
                # Update campaign sent_count in same transaction
                await db.execute(
                    "UPDATE email_blast_campaigns SET sent_count = sent_count + 1 WHERE id = ?",
                    (campaign_id,)
                )
                sent += 1
            else:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'failed', error_message = ? WHERE id = ?""",
                    (error, recipient_id)
                )
                # Log to outbox
                await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, source, email, university_name, rendered_subject, status, error_message)
                       VALUES (?, 'campaign', ?, ?, ?, 'failed', ?)""",
                    (campaign_id, email, uni_name, rendered_subject, error)
                )
                # Update campaign failed_count in same transaction
                await db.execute(
                    "UPDATE email_blast_campaigns SET failed_count = failed_count + 1 WHERE id = ?",
                    (campaign_id,)
                )
                failed += 1

            await db.commit()

        # Broadcast progress OUTSIDE the DB transaction (no lock contention)
        if success or error:
            await _broadcast_blast_progress(campaign_id, sent, failed, len(recipients))

        # Delay between emails
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

    # Update campaign status when done
    async with get_db() as db:
        if status == 'running':
            await db.execute(
                "UPDATE email_blast_campaigns SET status = 'completed', completed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), campaign_id)
            )
            await db.commit()

    log.info(f"[EmailBlast] Campaign {campaign_id} finished: {sent} sent, {failed} failed")

    # Always sync counters from actual recipient state — prevents drift from concurrent increments
    await sync_campaign_counters(campaign_id)


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
        query = """SELECT id, email, university_name, letter_number FROM email_blast_recipients
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

    for recipient_id, email, uni_name, stored_letter_number in recipients:
        # Check daily quota before processing
        daily_limit = cfg.get("EMAIL_BLAST_DAILY_LIMIT", 200)
        if daily_limit > 0:
            quota = await get_email_blast_quota_info(daily_limit)
            if quota["is_exhausted"]:
                log.warning(f"[EmailBlast] Retry — daily limit reached. Stopping retry for campaign {campaign_id}.")
                await ws_manager.broadcast_type(
                    "quota_exhausted",
                    campaign_id=campaign_id,
                    remaining=0,
                    daily_limit=daily_limit,
                    pending_count=0,
                )
                break

        log.info(f"[EmailBlast] Retry — processing recipient: id={recipient_id}, email={email}")

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

            ok, err = smtp_client.send_email(
                to_email=email,
                subject=rendered_subject,
                body=rendered_msg,
                from_email=from_email,
                from_name=from_name,
                attachment_path=attachment_to_send,
                attachment_filename=clean_attachment_filename,
            )
            success = ok
            error = err
        except Exception as e:
            error = str(e)
            log.error(f"[EmailBlast] Retry — send error for {email}: {e}")

        for generated_file in (generated_pdf, generated_docx):
            if generated_file and os.path.exists(generated_file):
                try:
                    os.remove(generated_file)
                except:
                    pass

        async with get_db() as db:
            if success:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'sent', sent_at = ?, rendered_subject = ?, rendered_message = ?, letter_number = ? WHERE id = ?""",
                    (datetime.now().isoformat(), rendered_subject, rendered_msg, letter_number, recipient_id)
                )
                await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, source, email, university_name, rendered_subject, rendered_message, status, error_message)
                       VALUES (?, 'campaign', ?, ?, ?, ?, 'sent', NULL)""",
                    (campaign_id, email, uni_name, rendered_subject, rendered_msg)
                )
                await _increment_quota_and_broadcast(db, campaign_id, daily_limit)
                await db.execute(
                    "UPDATE email_blast_campaigns SET sent_count = sent_count + 1 WHERE id = ?",
                    (campaign_id,)
                )
                sent += 1
            else:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'failed', error_message = ? WHERE id = ?""",
                    (error or "Unknown error", recipient_id)
                )
                await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, source, email, university_name, rendered_subject, status, error_message)
                       VALUES (?, 'campaign', ?, ?, ?, 'failed', ?)""",
                    (campaign_id, email, uni_name, rendered_subject, error or "Unknown error")
                )
                await db.execute(
                    "UPDATE email_blast_campaigns SET failed_count = failed_count + 1 WHERE id = ?",
                    (campaign_id,)
                )
                failed += 1
            await db.commit()

        # Broadcast progress OUTSIDE the DB transaction (no lock contention)
        if success or error:
            await _broadcast_blast_progress(campaign_id, sent, failed, len(recipients))

        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

    log.info(f"[EmailBlast] Retry campaign {campaign_id} done: {sent} sent, {failed} failed")


async def get_campaign_status(campaign_id: int) -> dict:
    """Get campaign status"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, name, subject, template_message, from_email, from_name,
                      delay_between_ms, status, total_recipients, sent_count, failed_count,
                      attachment_filename, attachment_variables,
                      created_at, started_at, completed_at, paused_at
               FROM email_blast_campaigns WHERE id = ?""",
            (campaign_id,)
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
            "attachment_filename": campaign[11],
            "attachment_variables": campaign[12],
            "created_at": campaign[13],
            "started_at": campaign[14],
            "completed_at": campaign[15],
            "paused_at": campaign[16],
        }


async def list_campaigns(status: str = None) -> list[dict]:
    """List all campaigns"""
    async with get_db() as db:
        query = """SELECT id, name, subject, status, total_recipients,
                          sent_count, failed_count, created_at
                   FROM email_blast_campaigns"""

        if status:
            query += " WHERE status = ?"
            cursor = await db.execute(query, (status,))
        else:
            cursor = await db.execute(query + " ORDER BY created_at DESC")

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
                "created_at": c[7]
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
        return True


async def cancel_campaign(campaign_id: int) -> bool:
    """Cancel campaign"""
    async with get_db() as db:
        await db.execute(
            "UPDATE email_blast_campaigns SET status = 'cancelled' WHERE id = ?",
            (campaign_id,)
        )
        await db.commit()
        return True


async def delete_recipient(recipient_id: int) -> bool:
    """Delete a recipient from campaign"""
    async with get_db() as db:
        # Get campaign_id first
        cursor = await db.execute(
            "SELECT campaign_id FROM email_blast_recipients WHERE id = ?",
            (recipient_id,)
        )
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


def get_imap_connection():
    """Create IMAP connection"""
    try:
        imap_host = cfg.IMAP_HOST
        imap_port = cfg.IMAP_PORT
        imap_user = cfg.IMAP_USERNAME
        imap_pass = cfg.IMAP_PASSWORD
        use_ssl = cfg.IMAP_USE_SSL

        log.info(f"Connecting to IMAP: {imap_host}:{imap_port} (SSL: {use_ssl})")

        if use_ssl:
            conn = imaplib.IMAP4_SSL(imap_host, imap_port)
        else:
            conn = imaplib.IMAP4(imap_host, imap_port)

        conn.login(imap_user, imap_pass)
        log.info(f"IMAP login successful for {imap_user}")
        return conn
    except Exception as e:
        log.error(f"Failed to connect to IMAP: {e}")
        import traceback
        log.error(traceback.format_exc())
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
            """SELECT uid, message_id, in_reply_to, from_email, from_name, to_email,
                      subject, body, date, is_read
               FROM email_inbox_cache
               ORDER BY uid DESC
               LIMIT ? OFFSET ?""",
            (limit, offset)
        )
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            'id': row[0],
            'message_id': row[1],
            'in_reply_to': row[2],
            'from_email': row[3],
            'from_name': row[4],
            'to_email': row[5],
            'subject': row[6],
            'body': row[7],
            'date': row[8],
            'is_read': bool(row[9]),
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


async def _blocking_imap_fetch(limit: int, offset: int, unread_only: bool) -> tuple[list[dict], int]:
    """Fetch emails from IMAP synchronously (blocking). Used when cache is empty."""
    conn = get_imap_connection()
    if not conn:
        log.error("Failed to get IMAP connection")
        return await _fetch_from_cache_fallback(limit, offset)

    try:
        status, folder_count = conn.select('INBOX')
        if status != 'OK':
            log.error(f"IMAP select failed: {status}")
            return await _fetch_from_cache_fallback(limit, offset)

        log.info(f"INBOX select status: {status}, messages: {folder_count}")

        search_criteria = 'UNSEEN' if unread_only else 'ALL'
        status, messages = conn.search(None, search_criteria)
        if status != 'OK':
            log.error(f"IMAP search failed: {status}")
            return await _fetch_from_cache_fallback(limit, offset)

        email_ids = messages[0].split()
        log.info(f"Found {len(email_ids)} total emails")

        # Get cached UIDs
        cached_uids: set[int] = set()
        async with get_db() as db:
            cursor = await db.execute("SELECT uid FROM email_inbox_cache")
            for r in await cursor.fetchall():
                cached_uids.add(r[0])

        log.info(f"[InboxCache] Already cached: {len(cached_uids)} emails")

        all_reversed = email_ids[::-1]  # newest first
        new_ids = [eid for eid in all_reversed if int(eid) not in cached_uids]

        # Fetch needed page + new emails
        to_fetch_ids_set: set[int] = set()
        for eid in all_reversed[offset:offset + limit]:
            to_fetch_ids_set.add(int(eid))
        for eid in new_ids[:500]:
            to_fetch_ids_set.add(int(eid))

        to_fetch_ids = [eid for eid in all_reversed if int(eid) in to_fetch_ids_set]
        log.info(f"[InboxCache] Fetching {len(to_fetch_ids)} emails from IMAP")

        results: list[dict] = []
        for email_id in to_fetch_ids:
            try:
                status, msg_data = conn.fetch(email_id, '(RFC822)')
                if status != 'OK':
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                parsed = parse_email_message(msg)

                from_field = parsed['from']
                from_match = re.search(r'<([^>]+)>', from_field)
                from_email = from_match.group(1) if from_match else ''
                if not from_email:
                    email_match = re.search(r'[\w\.-]+@[\w\.-]+', from_field)
                    from_email = email_match.group(0) if email_match else from_field

                entry = {
                    'id': int(email_id),
                    'message_id': parsed['message_id'],
                    'in_reply_to': parsed['in_reply_to'],
                    'from_email': from_email,
                    'from_name': re.sub(r'<.+?>', '', parsed['from']).strip(),
                    'to_email': parsed['to'],
                    'subject': parsed['subject'],
                    'body': parsed['body_text'][:2000],
                    'date': parsed['date'],
                    'is_read': True,
                }
                results.append(entry)
            except Exception as e:
                log.error(f"Error parsing email {email_id}: {e}")
                continue

        conn.close()
        conn.logout()

        if results:
            async with get_db() as db:
                for entry in results:
                    await db.execute(
                        """INSERT OR REPLACE INTO email_inbox_cache
                           (uid, message_id, in_reply_to, from_email, from_name, to_email,
                            subject, body, date, is_read, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                        (entry['id'], entry['message_id'], entry['in_reply_to'],
                         entry['from_email'], entry['from_name'], entry['to_email'],
                         entry['subject'], entry['body'], entry['date'], entry['is_read'])
                    )
                await db.commit()
            log.info(f"[InboxCache] Updated cache with {len(results)} emails")

        return await _fetch_from_cache(limit, offset)

    except Exception as e:
        log.error(f"Error in blocking IMAP fetch: {e}")
        try:
            conn.close()
            conn.logout()
        except Exception:
            pass
        return await _fetch_from_cache_fallback(limit, offset)


async def _refresh_inbox_cache_background():
    """Background task: fetch new emails and update cache without blocking."""
    global _inbox_bg_refresh_running
    try:
        log.info("[InboxCache] Background refresh starting")
        conn = get_imap_connection()
        if not conn:
            return

        status, folder_count = conn.select('INBOX')
        if status != 'OK':
            conn.close()
            conn.logout()
            return

        status, messages = conn.search(None, 'ALL')
        if status != 'OK':
            conn.close()
            conn.logout()
            return

        email_ids = messages[0].split()
        all_reversed = email_ids[::-1]

        # Get cached UIDs
        cached_uids: set[int] = set()
        async with get_db() as db:
            cursor = await db.execute("SELECT uid FROM email_inbox_cache")
            for r in await cursor.fetchall():
                cached_uids.add(r[0])

        new_ids = [eid for eid in all_reversed if int(eid) not in cached_uids][:500]

        if not new_ids:
            log.info("[InboxCache] Background refresh: no new emails")
            conn.close()
            conn.logout()
            return

        log.info(f"[InboxCache] Background refresh: fetching {len(new_ids)} new emails")

        for email_id in new_ids:
            try:
                status, msg_data = conn.fetch(email_id, '(RFC822)')
                if status != 'OK':
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                parsed = parse_email_message(msg)

                from_field = parsed['from']
                from_match = re.search(r'<([^>]+)>', from_field)
                from_email = from_match.group(1) if from_match else ''
                if not from_email:
                    email_match = re.search(r'[\w\.-]+@[\w\.-]+', from_field)
                    from_email = email_match.group(0) if email_match else from_field

                async with get_db() as db:
                    await db.execute(
                        """INSERT OR REPLACE INTO email_inbox_cache
                           (uid, message_id, in_reply_to, from_email, from_name, to_email,
                            subject, body, date, is_read, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                        (int(email_id), parsed['message_id'], parsed['in_reply_to'],
                         from_email, re.sub(r'<.+?>', '', parsed['from']).strip(),
                         parsed['to'], parsed['subject'], parsed['body_text'][:2000],
                         parsed['date'], 1)
                    )
            except Exception:
                continue

        async with get_db() as db:
            await db.commit()
        conn.close()
        conn.logout()
        log.info("[InboxCache] Background refresh complete")
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
    imap_results: list[dict] = []
    imap_total: int = 0
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM email_sent_cache")
        row = await cursor.fetchone()
        imap_total = row[0] if row else 0

        cursor = await db.execute(
            """SELECT uid, message_id, from_email, from_name, to_email,
                      subject, body, date
               FROM email_sent_cache
               ORDER BY uid DESC"""
        )
        rows = await cursor.fetchall()
        for row in rows:
            imap_results.append({
                'id': row[0],
                'message_id': row[1],
                'from_email': row[2],
                'from_name': row[3],
                'to_email': row[4],
                'subject': row[5],
                'body': row[6],
                'date': row[7],
            })

    # ── Fetch recent outbox entries (last 24h, not yet in IMAP cache) ──
    OUTBOX_WINDOW_HOURS = 24
    outbox_results: list[dict] = []

    async with get_db() as db:
        cursor = await db.execute(
            f"""SELECT id, campaign_id, email, university_name,
                      rendered_subject, rendered_message, sent_at
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
                'from_email': 'sekretariat@asosiasi.ai',
                'from_name': 'Sekretariat Asosiasi AI',
                'to_email': row[2],
                'subject': row[4],
                'body': row[5],
                'date': row[6],
            })

    # ── Merge: dedup outbox entries that are already in IMAP ──
    dedup_keys: set[tuple] = {
        (r['to_email'].lower().strip(), r['subject'].lower().strip())
        for r in imap_results if r['to_email'] and r['subject']
    }

    merged: list[dict] = []
    for item in outbox_results:
        key = (item['to_email'].lower().strip(), item['subject'].lower().strip())
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
                key = (item.get('to_email', '').lower().strip(), item.get('subject', '').lower().strip())
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
            """SELECT uid, message_id, from_email, from_name, to_email,
                      subject, body, date
               FROM email_sent_cache
               ORDER BY uid DESC
               LIMIT ? OFFSET ?""",
            (limit, offset)
        )
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            'id': row[0],
            'message_id': row[1],
            'from_email': row[2],
            'from_name': row[3],
            'to_email': row[4],
            'subject': row[5],
            'body': row[6],
            'date': row[7],
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
    conn = get_imap_connection()
    if not conn:
        log.error("[SentFolder] Failed to get IMAP connection")
        return None

    try:
        sent_folder = _find_sent_folder(conn)
        if not sent_folder:
            log.error("[SentFolder] Could not find Sent folder")
            return None

        log.info(f"[SentFolder] Selecting folder: {sent_folder}")
        status, _ = conn.select(f'"{sent_folder}"')
        if status != 'OK':
            log.error(f"[SentFolder] Failed to select folder: {status}")
            return None

        # Use UID SEARCH (not sequence number search) for stable IDs
        try:
            status, messages = conn.uid('SEARCH', None, 'ALL')
        except Exception as e:
            log.warning(f"[SentFolder] UID SEARCH not supported ({e}), falling back to sequence search")
            status, messages = conn.search(None, 'ALL')

        if status != 'OK':
            log.error(f"[SentFolder] IMAP search failed: {status}")
            return None

        raw_uids = messages[0].decode().split() if messages[0] else []
        log.info(f"[SentFolder] Found {len(raw_uids)} sent emails via UID search")

        # Get cached UIDs
        cached_uids: set[int] = set()
        async with get_db() as db:
            cursor = await db.execute("SELECT uid FROM email_sent_cache")
            for r in await cursor.fetchall():
                cached_uids.add(r[0])

        log.info(f"[SentFolder] Already cached: {len(cached_uids)} emails")

        all_uids_reversed = raw_uids[::-1]
        new_uids = [uid for uid in all_uids_reversed if int(uid) not in cached_uids]

        # Determine which UIDs to fetch (page + new)
        to_fetch_uids = all_uids_reversed[offset:offset + limit]
        for uid in new_uids[:500]:
            if int(uid) not in {int(u) for u in to_fetch_uids}:
                to_fetch_uids = list(to_fetch_uids) + [uid]

        log.info(f"[SentFolder] Fetching {len(to_fetch_uids)} emails via UID")

        results: list[dict] = []
        for uid_str in to_fetch_uids:
            try:
                # Fetch by UID to get both UID and RFC822 content
                status, msg_data = conn.uid('FETCH', uid_str, '(UID RFC822)')
                if status != 'OK' or not msg_data or not msg_data[0]:
                    continue

                # Parse UID from response
                uid_match = re.search(rb'UID (\d+)', msg_data[0][0] if isinstance(msg_data[0], bytes) else msg_data[0][0].encode())
                actual_uid = int(uid_match.group(1)) if uid_match else int(uid_str)

                # Parse message
                msg_bytes = msg_data[0][1]
                msg = email.message_from_bytes(msg_bytes)
                parsed = parse_email_message(msg)

                from_field = parsed['from']
                from_match = re.search(r'<([^>]+)>', from_field)
                from_email = from_match.group(1) if from_match else ''
                if not from_email:
                    email_match = re.search(r'[\w\.-]+@[\w\.-]+', from_field)
                    from_email = email_match.group(0) if email_match else from_field

                entry = {
                    'id': actual_uid,
                    'message_id': parsed['message_id'],
                    'from_email': from_email,
                    'from_name': re.sub(r'<.+?>', '', parsed['from']).strip(),
                    'to_email': parsed['to'],
                    'subject': parsed['subject'],
                    'body': parsed['body_text'][:2000],
                    'date': parsed['date'],
                }
                results.append(entry)

                # Save to cache with real UID (stable across sessions)
                async with get_db() as db:
                    await db.execute(
                        """INSERT OR REPLACE INTO email_sent_cache
                           (uid, message_id, from_email, from_name, to_email,
                            subject, body, date, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                        (actual_uid, entry['message_id'], entry['from_email'],
                         entry['from_name'], entry['to_email'], entry['subject'],
                         entry['body'], entry['date'])
                    )
                    await db.commit()
            except Exception as e:
                log.error(f"[SentFolder] Error fetching UID {uid_str}: {e}")
                continue

        conn.close()
        conn.logout()
        log.info(f"[SentFolder] Blocking fetch complete: {len(results)} emails fetched, {len(raw_uids)} total")
        return results, len(raw_uids)

    except Exception as e:
        log.error(f"[SentFolder] Error in blocking fetch: {e}")
        try:
            conn.close()
            conn.logout()
        except Exception:
            pass
        return None


async def _refresh_sent_cache_background():
    """Background task: fetch new sent emails."""
    global _sent_cache_running
    try:
        log.info("[SentFolder] Background refresh starting")
        conn = get_imap_connection()
        if not conn:
            return

        sent_folder = _find_sent_folder(conn)
        if not sent_folder:
            conn.close()
            conn.logout()
            return

        status, _ = conn.select(f'"{sent_folder}"')
        if status != 'OK':
            conn.close()
            conn.logout()
            return

        # Use UID SEARCH for stable IDs (not sequence numbers)
        try:
            status, messages = conn.uid('SEARCH', None, 'ALL')
        except Exception as e:
            log.warning(f"[SentFolder] UID SEARCH not supported ({e}), skipping background refresh")
            return

        if status != 'OK':
            return

        raw_uids = messages[0].decode().split() if messages[0] else []
        log.info(f"[SentFolder] Background refresh: {len(raw_uids)} total emails")

        # Get cached UIDs
        cached_uids: set[int] = set()
        async with get_db() as db:
            cursor = await db.execute("SELECT uid FROM email_sent_cache")
            for r in await cursor.fetchall():
                cached_uids.add(r[0])

        new_uids = [uid for uid in raw_uids if int(uid) not in cached_uids][:500]

        if not new_uids:
            log.info("[SentFolder] Background refresh: no new emails")
            return

        log.info(f"[SentFolder] Background refresh: fetching {len(new_uids)} new emails")

        for uid_str in new_uids:
            try:
                status, msg_data = conn.uid('FETCH', uid_str, '(UID RFC822)')
                if status != 'OK' or not msg_data or not msg_data[0]:
                    continue

                uid_match = re.search(rb'UID (\d+)', msg_data[0][0] if isinstance(msg_data[0], bytes) else msg_data[0][0].encode())
                actual_uid = int(uid_match.group(1)) if uid_match else int(uid_str)

                msg = email.message_from_bytes(msg_data[0][1])
                parsed = parse_email_message(msg)

                from_field = parsed['from']
                from_match = re.search(r'<([^>]+)>', from_field)
                from_email = from_match.group(1) if from_match else ''
                if not from_email:
                    email_match = re.search(r'[\w\.-]+@[\w\.-]+', from_field)
                    from_email = email_match.group(0) if email_match else from_field

                async with get_db() as db:
                    await db.execute(
                        """INSERT OR REPLACE INTO email_sent_cache
                           (uid, message_id, from_email, from_name, to_email,
                            subject, body, date, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                        (actual_uid, parsed['message_id'], from_email,
                         re.sub(r'<.+?>', '', parsed['from']).strip(),
                         parsed['to'], parsed['subject'],
                         parsed['body_text'][:2000], parsed['date'])
                    )
            except Exception as e:
                log.warning(f"[SentFolder] Background refresh error for UID {uid_str}: {e}")
                continue

        async with get_db() as db:
            await db.commit()
        log.info("[SentFolder] Background refresh complete")
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
    all_inbox, total = await fetch_inbox_emails(limit=limit)

    # Filter emails that are replies from recipients
    replies = []
    for inbox_email in all_inbox:
        from_email = inbox_email.get('from_email', '').lower()
        for recipient_email in recipient_emails:
            if from_email == recipient_email.lower():
                inbox_email['campaign_id'] = campaign_id
                replies.append(inbox_email)
                break

    return replies, total


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
    try:
        success, error = smtp_client.send_email(
            to_email,
            rendered_subject,
            rendered_msg,
            final_from_email or "sekretariat@asosiasi.ai",
            final_from_name or "Sekretariat Asosiasi AI",
            attachment_path=final_attachment,
            attachment_filename=clean_attachment_filename,
        )

        if success:
            log.info(f"[EmailBlast] Test email sent to {to_email}")
            # Log to outbox
            async with get_db() as db:
                await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, source, email, rendered_subject, rendered_message, status, error_message)
                       VALUES (?, 'test', ?, ?, ?, 'sent', NULL)""",
                    (campaign_id, to_email, rendered_subject, rendered_msg)
                )
                await db.commit()
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
                await db.execute(
                    """INSERT INTO email_outbox
                       (campaign_id, source, email, rendered_subject, status, error_message)
                       VALUES (?, 'test', ?, ?, 'failed', ?)""",
                    (campaign_id, to_email, rendered_subject or '', error)
                )
                await db.commit()
            return False, f"Failed to send: {error}"
    finally:
        smtp_client.disconnect()
