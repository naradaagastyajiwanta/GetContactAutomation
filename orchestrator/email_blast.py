"""
Email Blast Module - Send bulk emails via SMTP
"""
import asyncio
import json
import os
import re
import smtplib
import ssl
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Optional
from pathlib import Path

from docx import Document

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
                   from_email: str = None, from_name: str = None,
                   attachment_path: str = None) -> tuple[bool, str]:
        """Send single email with optional attachment"""
        if not self._connection:
            success = self.connect()
            if not success:
                return False, "SMTP not connected"

        try:
            msg = MIMEMultipart('mixed')
            if from_email:
                msg['From'] = f"{from_name or 'Sekretariat Asosiasi AI'} <{from_email}>"
            else:
                msg['From'] = from_name or 'Sekretariat Asosiasi AI'
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Reply-To'] = from_email or 'sekretariat@asosiasi.ai'

            # Create multipart/alternative for body
            msg_alt = MIMEMultipart('alternative')

            # Plain text part
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg_alt.attach(text_part)

            # HTML part (simple conversion)
            html_body = body.replace('\n', '<br>\n')
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg_alt.attach(html_part)

            msg.attach(msg_alt)

            # Add attachment if provided
            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    filename = os.path.basename(attachment_path)
                    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                    msg.attach(part)
                    log.debug(f"[EmailBlast] Attached: {filename}")

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

    # Method 3: Try pandoc (if installed)
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


def generate_docx(doc_path: str, variables: dict, output_path: str) -> bool:
    """Generate DOCX from template with replaced variables"""
    try:
        log.info(f"[EmailBlast] generate_docx called: {doc_path} -> {output_path}")
        log.info(f"[EmailBlast] Variables to replace: {variables}")

        doc = Document(doc_path)

        # Debug: print all text in document
        all_text = []
        for para in doc.paragraphs:
            all_text.append(f"PARA: {repr(para.text)}")
            for run in para.runs:
                all_text.append(f"  RUN: {repr(run.text)}")
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        all_text.append(f"TABLE PARA: {repr(para.text)}")
                        for run in para.runs:
                            all_text.append(f"  TABLE RUN: {repr(run.text)}")

        log.info(f"[EmailBlast] Document text content:\n" + "\n".join(all_text[:50]))  # Limit to first 50 lines

        # Strategy: Work on paragraph level first, then handle runs
        # First, collect all text and replace in paragraphs
        replacement_count = 0

        # Replace in paragraphs - rebuild the paragraph text completely
        for para in doc.paragraphs:
            full_text = para.text
            for key, value in variables.items():
                placeholder = f'{{{{{key}}}}}'
                if placeholder in full_text:
                    log.info(f"[EmailBlast] Found placeholder {placeholder} in paragraph, replacing with: {value}")
                    replacement_count += full_text.count(placeholder)
                    full_text = full_text.replace(placeholder, str(value))
            para.text = full_text

        # Replace in tables - rebuild the cell text
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        full_text = para.text
                        for key, value in variables.items():
                            placeholder = f'{{{{{key}}}}}'
                            if placeholder in full_text:
                                log.info(f"[EmailBlast] Found placeholder {placeholder} in table, replacing with: {value}")
                                replacement_count += full_text.count(placeholder)
                                full_text = full_text.replace(placeholder, str(value))
                        para.text = full_text

        log.info(f"[EmailBlast] Total replacements made: {replacement_count}")

        doc.save(output_path)

        # Verify output file
        if os.path.exists(output_path):
            doc2 = Document(output_path)
            output_text = "\n".join([p.text for p in doc2.paragraphs])
            log.info(f"[EmailBlast] Output docx verification (first 500 chars): {output_text[:500]}")

        log.info(f"[EmailBlast] DOCX saved successfully to {output_path}")
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
        if row:
            return {
                'filename': row[0],
                'variables': json.loads(row[1]) if row[1] else {}
            }
        return {'filename': None, 'variables': {}}


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
    from datetime import datetime

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

    # Generate letter number for this campaign (once per campaign) if there's an attachment
    letter_number = None
    log.info(f"[EmailBlast] DEBUG: attachment_filename='{attachment_filename}' (type: {type(attachment_filename)})")
    if attachment_filename:  # Only generate letter number if there's an attachment
        try:
            letter_number, _ = await get_next_letter_number()
            log.info(f"[EmailBlast] Generated letter number: {letter_number}")
        except Exception as e:
            log.error(f"[EmailBlast] Error generating letter number: {e}")
    else:
        log.warning(f"[EmailBlast] No attachment_filename - letter_number will be None!")

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
        log.info(f"[EmailBlast] Processing recipient: id={recipient_id}, email={email}, uni_name={uni_name}")

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
                docx_filename = attachment_filename.replace('.docx', '')
                output_docx_name = f"{campaign_id}_{recipient_id}_{docx_filename}.docx"
                output_docx_path = TEMPLATE_DIR / output_docx_name

                # Generate DOCX with replaced variables
                docx_result = generate_docx(str(attachment_path), vars_for_recipient, str(output_docx_path))
                log.info(f"[EmailBlast] generate_docx result: {docx_result}")

                if docx_result and os.path.exists(str(output_docx_path)):
                    # MUST convert to PDF
                    output_pdf_name = f"{campaign_id}_{recipient_id}_{docx_filename}.pdf"
                    output_pdf_path = TEMPLATE_DIR / output_pdf_name

                    log.info(f"[EmailBlast] Converting DOCX to PDF: {output_docx_path} -> {output_pdf_path}")
                    pdf_result = convert_docx_to_pdf(str(output_docx_path), str(output_pdf_path))

                    if pdf_result and os.path.exists(str(output_pdf_path)):
                        final_attachment = str(output_pdf_path)
                        log.info(f"[EmailBlast] PDF created successfully: {output_pdf_path}")
                        # Remove the intermediate DOCX file
                        try:
                            os.remove(str(output_docx_path))
                        except:
                            pass
                    else:
                        log.error(f"[EmailBlast] PDF conversion FAILED - no attachment will be sent!")
                        # Remove the DOCX file
                        try:
                            os.remove(str(output_docx_path))
                        except:
                            pass
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
                attachment_path=final_attachment
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
        # Update status to completed
        await db.execute(
            "UPDATE email_blast_campaigns SET status = 'completed', completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), campaign_id)
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
