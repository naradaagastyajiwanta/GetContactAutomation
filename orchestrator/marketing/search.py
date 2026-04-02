"""
3-Stage Search Pipeline for corporate outreach.
Stage 1: Website discovery (DDG → website → emails/phones)
Stage 2: IG discovery (DDG → IG handle → scrape posts → GPT vision OCR)
Stage 3: Web search fallback (DDG broad search → parse snippets)
"""
import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from orchestrator.config import log
from orchestrator.duckduckgo_client import async_search_text
from orchestrator.osint.tools import (
    ddg_search,
    fetch_page,
    extract_emails,
    extract_phones_from_text,
    extract_social_links,
    extract_text_from_html,
)
from orchestrator.instagram import (
    scrape_ig_posts_with_fallback,
    extract_phone_from_image,
    extract_named_contacts_from_text,
)

# Landline area codes (kode wilayah) to filter out
_LANDLINE_PREFIXES = (
    "021", "022", "023", "024", "025", "026", "027", "028",
    "029", "031", "032", "033", "034", "035", "036", "037",
    "038", "041", "042", "043", "044", "045", "046", "047",
    "048", "051", "052", "053", "054", "055", "061", "062",
    "063", "064", "065", "071", "072", "073", "074", "075",
    "076", "077", "078", "079", "0811", "0812", "0813", "0814",
    "0815", "0816", "0817", "0818", "0819", "0821", "0822",
    "0823", "0824", "0825", "0826", "0827", "0828", "0829",
    "0851", "0852", "0853", "0854", "0855", "0856", "0857",
    "0858", "0859", "0861", "0862", "0863", "0864", "0865",
    "0866", "0867", "0868", "0869", "0895", "0896", "0897",
    "0898", "0899",
)


def is_mobile_phone(phone: str) -> bool:
    """Return True if phone is a mobile Indonesian number (not landline)."""
    digits = re.sub(r"\D", "", phone)
    # Mobile: starts with 08, +628, 628 (10-14 digits total)
    if len(digits) < 10 or len(digits) > 14:
        return False
    if digits.startswith("62") and len(digits) == 12:
        return True  # +62 8xx
    if digits.startswith("0") and digits[1] == "8":
        return True  # 08xx
    if digits.startswith("8") and len(digits) == 9:
        return True  # 8xx (without leading 0)
    # Landline checks
    for prefix in _LANDLINE_PREFIXES:
        if digits.startswith(prefix) and len(digits) >= 10:
            return False
    return True


def filter_mobile_phones(phones: list[str]) -> list[str]:
    """Filter to only mobile Indonesian phone numbers."""
    return [p for p in phones if is_mobile_phone(p)]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ContactResult:
    contact_type: str       # "wa_phone", "email", "office_phone", "pic_name", "pic_title"
    value: str
    source_url: str | None = None
    source_type: str | None = None
    confidence: float = 0.0
    pic_name: str | None = None
    pic_title: str | None = None


# ---------------------------------------------------------------------------
# Stage 1 — Website Discovery
# ---------------------------------------------------------------------------


async def website_discovery(client_name: str, extra_data: dict | None = None) -> list[ContactResult]:
    """Search for official website → extract emails and phones."""
    results: list[ContactResult] = []

    # Primary search for official website
    ddg_results = await ddg_search(f'"{client_name}" official website contact', max_results=5)
    if not ddg_results:
        return results

    # Try main page + common contact sub-pages
    pages_to_check: list[tuple[str, str]] = []
    for r in ddg_results:
        url = r.get("link", "")
        if url:
            pages_to_check.append((url, "website"))
            # Also try /contact, /about, /tentang-kami
            base = url.rstrip("/")
            for path in ("/contact", "/contact-us", "/about", "/tentang-kami", "/hubungi-kami"):
                pages_to_check.append((base + path, "contact_page"))

    for url, source_type in pages_to_check:
        html = await fetch_page(url)
        if not html:
            continue
        text = extract_text_from_html(html)
        if not text:
            continue

        # Emails
        for email in extract_emails(text):
            results.append(ContactResult(
                contact_type="email",
                value=email,
                source_url=url,
                source_type=source_type,
                confidence=0.7,
            ))

        # Mobile phones
        for phone in filter_mobile_phones(extract_phones_from_text(text)):
            results.append(ContactResult(
                contact_type="wa_phone",
                value=phone,
                source_url=url,
                source_type=source_type,
                confidence=0.6,
            ))

    return _dedupe_results(results)


# ---------------------------------------------------------------------------
# Stage 2 — Instagram Discovery
# ---------------------------------------------------------------------------


async def ig_discovery(client_name: str) -> list[ContactResult]:
    """Find IG handle via DDG → scrape posts → GPT vision OCR."""
    results: list[ContactResult] = []

    # Find IG handle
    ddg_results = await ddg_search(f'"{client_name}" site:instagram.com', max_results=5)
    ig_handle: str | None = None
    ig_url: str | None = None

    for r in ddg_results:
        link = r.get("link", "") or ""
        match = re.search(r"instagram\.com/([^/?]+)", link)
        if match:
            handle = match.group(1).strip()
            if handle not in ("", "p", "explore", "settings", "support"):
                ig_handle = handle
                ig_url = link
                break

    if not ig_handle:
        return results

    # Scrape posts (run sync function in executor)
    try:
        loop = asyncio.get_running_loop()
        posts = await loop.run_in_executor(
            None, partial(scrape_ig_posts_with_fallback, ig_handle, 6)
        )
    except Exception as e:
        log.warning(f"[Marketing IG Discovery] scrape failed for {ig_handle}: {e}")
        return results

    for post in posts:
        image_url = post.get("image_url", "")
        caption = post.get("caption", "")
        post_url = post.get("post_url", "")

        if not image_url:
            continue

        # Extract phones from post image via GPT Vision
        try:
            phone_contacts = await extract_phone_from_image(image_url, caption)
            for pc in phone_contacts:
                results.append(ContactResult(
                    contact_type="wa_phone",
                    value=pc["phone"],
                    source_url=post_url or image_url,
                    source_type="ig_post",
                    confidence=0.8,
                    pic_name=pc.get("name"),
                ))
        except Exception as e:
            log.warning(f"[Marketing IG] Vision extract failed for {image_url}: {e}")

        # Extract named contacts from caption
        if caption:
            try:
                named_contacts = await extract_named_contacts_from_text(caption)
                for nc in named_contacts:
                    if nc.get("name"):
                        results.append(ContactResult(
                            contact_type="wa_phone",
                            value=nc["phone"],
                            source_url=post_url,
                            source_type="ig_caption",
                            confidence=0.5,
                            pic_name=nc.get("name"),
                        ))
            except Exception as e:
                log.warning(f"[Marketing IG] Caption extract failed: {e}")

    return _dedupe_results(results)


# ---------------------------------------------------------------------------
# Stage 3 — Web Search Fallback
# ---------------------------------------------------------------------------


async def web_search_fallback(client_name: str) -> list[ContactResult]:
    """Broad DDG search → parse snippets for contacts."""
    results: list[ContactResult] = []

    query = f'"{client_name}" WhatsApp email kontak PIC jabatan sekretariat'
    ddg_results = await ddg_search(query, max_results=8)

    all_text = ""
    for r in ddg_results:
        snippet = r.get("snippet", "")
        link = r.get("link", "")
        if snippet:
            all_text += snippet + "\n"

    for email in extract_emails(all_text):
        results.append(ContactResult(
            contact_type="email",
            value=email,
            source_url="",
            source_type="ddg_snippet",
            confidence=0.4,
        ))

    for phone in filter_mobile_phones(extract_phones_from_text(all_text)):
        results.append(ContactResult(
            contact_type="wa_phone",
            value=phone,
            source_url="",
            source_type="ddg_snippet",
            confidence=0.4,
        ))

    return _dedupe_results(results)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedupe_results(results: list[ContactResult]) -> list[ContactResult]:
    """Remove duplicates by (contact_type, value)."""
    seen: set[tuple[str, str]] = set()
    deduped: list[ContactResult] = []
    for r in results:
        key = (r.contact_type, r.value)
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


# ---------------------------------------------------------------------------
# Background task: process search queue
# ---------------------------------------------------------------------------

# Global semaphore for concurrent client searches (max 3 at a time)
_search_semaphore = asyncio.Semaphore(3)


async def _search_single_client(
    client_id: int,
    client_name: str,
    extra_data: dict | None,
    update_fn: Callable[[int, str], None],
) -> None:
    """Run all 3 stages for a single client."""
    async with _search_semaphore:
        await update_fn(client_id, "searching")

        # Import here to avoid circular
        from . import groups as mkt

        try:
            stage1 = await website_discovery(client_name, extra_data)
            stage2 = await ig_discovery(client_name)
            stage3 = await web_search_fallback(client_name)

            all_results = stage1 + stage2 + stage3
            status = "found" if all_results else "not_found"

            for r in all_results:
                await mkt.upsert_contact_result(
                    client_id=client_id,
                    contact_type=r.contact_type,
                    value=r.value,
                    source_url=r.source_url,
                    source_type=r.source_type,
                    confidence=r.confidence,
                )

                # Also store pic_name/pic_title if present
                if r.pic_name:
                    await mkt.upsert_contact_result(
                        client_id=client_id,
                        contact_type="pic_name",
                        value=r.pic_name,
                        source_url=r.source_url or "",
                        source_type=r.source_type or "",
                        confidence=r.confidence,
                    )

            await mkt.update_client_search_status(client_id, status)

        except Exception as e:
            error_msg = str(e) or type(e).__name__
            log.warning(f"[Marketing Search] Client {client_id} ({client_name}) failed: {error_msg}")
            await mkt.update_client_error_message(client_id, error_msg)


async def process_search_queue(group_id: int) -> None:
    """Process all pending clients in a group with concurrency control."""
    from . import groups as mkt

    # Update group status
    await mkt.update_group_status(group_id, "searching")

    pending = await mkt.get_pending_clients(group_id)

    async def update_status(client_id: int, status: str) -> None:
        await mkt.update_client_search_status(client_id, status)

    tasks = [
        _search_single_client(
            client_id=c["id"],
            client_name=c["name"],
            extra_data=c.get("extra_data"),
            update_fn=update_status,
        )
        for c in pending
    ]

    if tasks:
        await asyncio.gather(*tasks)

    # Update group status
    await mkt.update_group_status(group_id, "done")
