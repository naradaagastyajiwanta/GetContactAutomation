"""
Email Blast Module - Send bulk emails via SMTP
"""
import asyncio
import json
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Optional

from orchestrator.config import cfg, log
from orchestrator.db import get_db


# ---------------------------------------------------------------------------
# SMTP Client
# ---------------------------------------------------------------------------

class SMTPClient:
    """SMTP client for sending emails"""

    def __init__(self):
        self.host = cfg.get("SMTP_HOST", "mail.asosiasi.ai")
        self.port = cfg.get("SMTP_PORT", 465)
        self.username = cfg.get("SMTP_USERNAME", "sekretariat@asosiasi.ai")
        self.password = cfg.get("SMTP_PASSWORD", "")
        self.use_ssl = cfg.get("SMTP_USE_SSL", True)
        self._connection: Optional[smtplib.SMTP_SSL] = None

    def connect(self) -> bool:
        """Establish SMTP connection"""
        try:
            log.info(f"[EmailBlast] Connecting to SMTP {self.host}:{self.port}")

            if self.use_ssl:
                context = ssl.create_default_context()
                self._connection = smtplib.SMTP_SSL(self.host, self.port, context=context)
            else:
                self._connection = smtplib.SMTP(self.host, self.port)
                self._connection.ehlo()
                self._connection.starttls(context=ssl.create_default_context())

            self._connection.login(self.username, self.password)
            log.info("[EmailBlast] SMTP connected successfully")
            return True
        except Exception as e:
            log.error(f"[EmailBlast] SMTP connection failed: {e}")
            return False

    def disconnect(self):
        """Close SMTP connection"""
        if self._connection:
            try:
                self._connection.quit()
            except:
                pass
            self._connection = None

    def send_email(self, to_email: str, subject: str, body: str,
                   from_email: str = None, from_name: str = None) -> tuple[bool, str]:
        """Send single email"""
        if not self._connection:
            success = self.connect()
            if not success:
                return False, "SMTP not connected"

        try:
            msg = MIMEMultipart('alternative')
            if from_email:
                msg['From'] = f"{from_name or 'Sekretariat Asosiasi AI'} <{from_email}>"
            else:
                msg['From'] = from_name or 'Sekretariat Asosiasi AI'
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Reply-To'] = from_email or 'sekretariat@asosiasi.ai'

            # Plain text part
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)

            # HTML part (simple conversion)
            html_body = body.replace('\n', '<br>\n')
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)

            # Use sendmail with proper envelope from
            from_addr = from_email if from_email else self.username
            self._connection.sendmail(from_addr, [to_email], msg.as_string())
            log.debug(f"[EmailBlast] Sent to {to_email}")
            return True, ""
        except Exception as e:
            log.error(f"[EmailBlast] Failed to send to {to_email}: {e}")
            return False, str(e)


# Global SMTP client
_smtp_client: Optional[SMTPClient] = None


def get_smtp_client() -> SMTPClient:
    """Get or create SMTP client"""
    global _smtp_client
    if _smtp_client is None:
        _smtp_client = SMTPClient()
    return _smtp_client


# ---------------------------------------------------------------------------
# Campaign Management
# ---------------------------------------------------------------------------

async def create_email_campaign(name: str, subject: str, template: str,
                                from_email: str = "sekretariat@asosiasi.ai",
                                from_name: str = "Sekretariat Asosiasi AI",
                                delay_ms: int = 8000) -> int:
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
                await db.execute(
                    """INSERT OR IGNORE INTO email_blast_recipients
                       (campaign_id, university_id, email, university_name)
                       VALUES (?, ?, ?, ?)""",
                    (campaign_id, uni_id, email, uni_name)
                )
                added += 1
            except:
                pass

        await db.commit()

        # Update total count
        await db.execute(
            "UPDATE email_blast_campaigns SET total_recipients = ? WHERE id = ?",
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
        params = []

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
                await db.execute(
                    """INSERT OR IGNORE INTO email_blast_recipients
                       (campaign_id, university_id, email, university_name)
                       VALUES (?, ?, ?, ?)""",
                    (campaign_id, uni_id, email, uni_name)
                )
                added += 1
            except:
                pass

        await db.commit()

        # Update total count
        await db.execute(
            "UPDATE email_blast_campaigns SET total_recipients = ? WHERE id = ?",
            (added, campaign_id)
        )
        await db.commit()

        return added


async def render_template(template: str, university_name: str,
                          email: str, subject_template: str = None) -> tuple[str, str]:
    """Render template with university data"""
    # Replace placeholders
    rendered_msg = template
    rendered_msg = rendered_msg.replace('{{university_name}}', university_name)
    rendered_msg = rendered_msg.replace('{{email}}', email)
    rendered_msg = rendered_msg.replace('{{tanggal}}', datetime.now().strftime('%d %B %Y'))

    rendered_subj = subject_template or ""
    rendered_subj = rendered_subj.replace('{{university_name}}', university_name)

    return rendered_subj, rendered_msg


async def run_email_blast_campaign(campaign_id: int,
                                   smtp_client: SMTPClient = None,
                                   max_recipients: int = None):
    """Run email blast campaign"""
    async with get_db() as db:
        # Get campaign info
        cursor = await db.execute(
            "SELECT name, subject, template_message, from_email, from_name, delay_between_ms, status FROM email_blast_campaigns WHERE id = ?",
            (campaign_id,)
        )
        campaign = await cursor.fetchone()
        if not campaign:
            log.error(f"[EmailBlast] Campaign {campaign_id} not found")
            return

        name, subject, template, from_email, from_name, delay_ms, status = campaign

        if status != 'running':
            log.error(f"[EmailBlast] Campaign {campaign_id} is not running (status: {status})")
            return

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

    sent = 0
    failed = 0

    for recipient_id, email, uni_name in recipients:
        # Render template
        rendered_subject, rendered_msg = await render_template(
            template, uni_name or "Yth. Pihak Universitas",
            email, subject
        )

        # Send email
        success, error = smtp_client.send_email(
            email, rendered_subject, rendered_msg, from_email, from_name
        )

        async with get_db() as db:
            if success:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'sent', sent_at = ? WHERE id = ?""",
                    (datetime.now().isoformat(), recipient_id)
                )
                sent += 1
            else:
                await db.execute(
                    """UPDATE email_blast_recipients
                       SET status = 'failed', error_message = ? WHERE id = ?""",
                    (error, recipient_id)
                )
                failed += 1

            await db.commit()

        # Delay between emails
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

    # Update campaign stats
    async with get_db() as db:
        await db.execute(
            """UPDATE email_blast_campaigns
               SET sent_count = sent_count + ?, failed_count = failed_count + ?
               WHERE id = ?""",
            (sent, failed, campaign_id)
        )
        await db.commit()

    log.info(f"[EmailBlast] Campaign {campaign_id} completed: {sent} sent, {failed} failed")


async def get_campaign_status(campaign_id: int) -> dict:
    """Get campaign status"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, name, subject, from_email, from_name, delay_between_ms,
                      status, total_recipients, sent_count, failed_count,
                      created_at, started_at, completed_at
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
            "from_email": campaign[3],
            "from_name": campaign[4],
            "delay_between_ms": campaign[5],
            "status": campaign[6],
            "total_recipients": campaign[7],
            "sent_count": campaign[8],
            "failed_count": campaign[9],
            "created_at": campaign[10],
            "started_at": campaign[11],
            "completed_at": campaign[12]
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
