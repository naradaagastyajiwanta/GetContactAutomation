"""
3-Stage Search Pipeline for corporate outreach.
Stage 1: Website discovery (DDG → website → emails/phones)
Stage 2: IG discovery (DDG → IG handle → scrape posts → GPT vision OCR)
Stage 3: Web search fallback (DDG broad search → parse snippets)
"""
import asyncio
import json
import re
from urllib.parse import urlparse
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from orchestrator.config import log
from orchestrator.duckduckgo_client import get_status as get_ddg_status
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
    fetch_bios_for_candidates,
    llm_verify_company_ig_handle,
)

_WHATSAPP_URL_PATTERNS = (
    re.compile(r'https?://wa\.me/([0-9]{9,15})', re.IGNORECASE),
    re.compile(r'https?://api\.whatsapp\.com/send\?[^"\'<>\s]*?phone=([0-9]{9,15})', re.IGNORECASE),
    re.compile(r'https?://(?:www\.)?whatsapp\.com/send\?[^"\'<>\s]*?phone=([0-9]{9,15})', re.IGNORECASE),
)

_TEL_URL_PATTERN = re.compile(r'tel:([^"\'<>\s]+)', re.IGNORECASE)
_CORPORATE_IG_SKIP_HANDLES = {
    "",
    "p",
    "reel",
    "reels",
    "explore",
    "settings",
    "support",
    "popular",
}
_CORPORATE_GENERIC_WORDS = {
    "pt", "tbk", "cv", "co", "company", "indonesia", "group",
    "persero", "official", "resmi", "holding", "international",
}
_CORPORATE_NEGATIVE_HANDLE_WORDS = {
    "news", "media", "update", "karir", "career", "jobs", "loker",
    "promo", "promosi", "fans", "fan", "community", "komunitas", "popular",
}
_CORPORATE_NEGATIVE_PROFILE_WORDS = {
    "fan page", "fans", "community", "komunitas", "news", "media", "parody",
}

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


def _extract_mobile_phones_from_html(html: str) -> list[str]:
    """Extract mobile/WhatsApp numbers from raw HTML attributes and URLs."""
    phones: list[str] = []

    for pattern in _WHATSAPP_URL_PATTERNS:
        phones.extend(pattern.findall(html))

    phones.extend(_TEL_URL_PATTERN.findall(html))
    return filter_mobile_phones(phones)


def _normalize_company_tokens(company_name: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", company_name.lower())
    return [token for token in tokens if len(token) > 2 and token not in _CORPORATE_GENERIC_WORDS]


def _build_company_abbreviation(company_name: str) -> str:
    tokens = _normalize_company_tokens(company_name)
    if len(tokens) < 2:
        return ""
    return "".join(token[0] for token in tokens)


def _extract_direct_ig_profile_handle(url: str) -> str | None:
    parsed = urlparse(url)
    if "instagram.com" not in parsed.netloc.lower():
        return None

    path_parts = [part.strip() for part in parsed.path.split("/") if part.strip()]
    if len(path_parts) != 1:
        return None

    handle = path_parts[0].lower()
    if handle in _CORPORATE_IG_SKIP_HANDLES:
        return None
    return handle


def _score_company_ig_candidate(company_name: str, handle: str, title: str, snippet: str) -> float:
    tokens = _normalize_company_tokens(company_name)
    abbreviation = _build_company_abbreviation(company_name)
    handle_lower = handle.lower()
    handle_stripped = re.sub(r"[_.\-]", "", handle_lower)
    title_lower = title.lower()
    snippet_lower = snippet.lower()

    score = 0.0

    token_hits = sum(1 for token in tokens if token in handle_stripped)
    if token_hits:
        score += 0.35 * min(token_hits / max(len(tokens), 1), 1.0)

    if abbreviation and len(abbreviation) >= 3 and abbreviation in handle_stripped:
        score += 0.2

    exact_phrase = company_name.lower()
    if exact_phrase in title_lower or exact_phrase in snippet_lower:
        score += 0.3
    else:
        text_hits = sum(1 for token in tokens if token in title_lower or token in snippet_lower)
        if text_hits:
            score += 0.2 * min(text_hits / max(len(tokens), 1), 1.0)

    if any(word in handle_lower for word in _CORPORATE_NEGATIVE_HANDLE_WORDS):
        score -= 0.2

    return score


def _boost_company_candidate_from_profile(candidate: dict, company_name: str) -> float:
    tokens = _normalize_company_tokens(company_name)
    abbreviation = _build_company_abbreviation(company_name)
    bio = (candidate.get("bio") or "").lower()
    full_name = (candidate.get("full_name") or "").lower()
    external_url = (candidate.get("external_url") or "").lower()
    combined = " ".join(part for part in (bio, full_name) if part)

    boost = 0.0

    exact_phrase = company_name.lower()
    if exact_phrase in combined:
        boost += 0.3
    else:
        token_hits = sum(1 for token in tokens if token in combined)
        if token_hits:
            boost += 0.2 * min(token_hits / max(len(tokens), 1), 1.0)

    if abbreviation and len(abbreviation) >= 3 and abbreviation in re.sub(r"[_.\-\s]", "", combined):
        boost += 0.1

    if candidate.get("is_verified"):
        boost += 0.05

    if external_url:
        external_host = urlparse(external_url).netloc.lower()
        if external_host:
            candidate["external_domain"] = external_host
        if any(token in external_host for token in tokens):
            boost += 0.2

    if any(word in combined for word in _CORPORATE_NEGATIVE_PROFILE_WORDS):
        boost -= 0.25

    return boost


async def _select_corporate_ig_candidate(client_name: str) -> tuple[str | None, str | None]:
    ddg_results = await _ddg_search_or_raise(
        f'"{client_name}" site:instagram.com',
        max_results=8,
        stage="instagram discovery",
    )

    candidates: list[dict] = []
    seen_handles: set[str] = set()
    for result in ddg_results:
        link = (result.get("link") or "").strip()
        handle = _extract_direct_ig_profile_handle(link)
        if not handle or handle in seen_handles:
            continue
        seen_handles.add(handle)
        candidates.append({
            "handle": handle,
            "url": link,
            "title": result.get("title", "") or "",
            "snippet": result.get("snippet", "") or "",
            "confidence": _score_company_ig_candidate(
                client_name,
                handle,
                result.get("title", "") or "",
                result.get("snippet", "") or "",
            ),
        })

    if not candidates:
        return None, None

    candidates.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
    loop = asyncio.get_running_loop()
    enriched = await loop.run_in_executor(None, fetch_bios_for_candidates, candidates, min(5, len(candidates)))

    for candidate in enriched:
        candidate["confidence"] = float(candidate.get("confidence", 0.0)) + _boost_company_candidate_from_profile(candidate, client_name)

    enriched.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)

    for candidate in enriched:
        llm = await llm_verify_company_ig_handle(
            candidate.get("handle", ""),
            candidate.get("bio", "") or "",
            candidate.get("full_name", "") or "",
            client_name,
            candidate.get("external_url", "") or "",
        )
        if llm["is_correct"] is False:
            log.info(
                "[Marketing IG] Candidate @%s rejected by LLM for %s: %s",
                candidate.get("handle", ""),
                client_name,
                llm["reason"],
            )
            continue

        if llm["is_correct"] is True or candidate.get("confidence", 0.0) >= 0.35:
            log.info(
                "[Marketing IG] Candidate @%s accepted for %s (score=%.2f, llm=%s: %s)",
                candidate.get("handle", ""),
                client_name,
                candidate.get("confidence", 0.0),
                llm["is_correct"],
                llm["reason"],
            )
            return candidate.get("handle"), candidate.get("url")

    return None, None


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


@dataclass
class InstagramDiscoveryResult:
    handle: str | None = None
    profile_url: str | None = None
    posts: list[dict] = field(default_factory=list)
    contacts: list[ContactResult] = field(default_factory=list)


class SearchDependencyError(RuntimeError):
    """Raised when a required external search backend is unavailable."""


def _results_from_page_content(
    *,
    html: str,
    text: str,
    source_url: str,
    source_type: str,
    email_confidence: float,
    phone_confidence: float,
) -> list[ContactResult]:
    """Build contact results from fetched page content."""
    results: list[ContactResult] = []

    for email in extract_emails(text):
        results.append(ContactResult(
            contact_type="email",
            value=email,
            source_url=source_url,
            source_type=source_type,
            confidence=email_confidence,
        ))

    phone_candidates = extract_phones_from_text(text) + _extract_mobile_phones_from_html(html)
    for phone in filter_mobile_phones(phone_candidates):
        results.append(ContactResult(
            contact_type="wa_phone",
            value=phone,
            source_url=source_url,
            source_type=source_type,
            confidence=phone_confidence,
        ))

    return _dedupe_results(results)


async def _ddg_search_or_raise(
    query: str,
    *,
    max_results: int,
    stage: str,
) -> list[dict]:
    """Return DDG results or raise when the backend is unavailable."""
    results = await ddg_search(query, max_results=max_results)
    if results:
        return results

    ddg_status = get_ddg_status()
    if not ddg_status.get("ok", True):
        error_message = ddg_status.get("error") or "unknown_ddg_error"
        raise SearchDependencyError(
            f"DDG unavailable during {stage}: {error_message}"
        )

    return []


# ---------------------------------------------------------------------------
# Stage 1 — Website Discovery
# ---------------------------------------------------------------------------


async def website_discovery(client_name: str, extra_data: dict | None = None) -> list[ContactResult]:
    """Search for official website → extract emails and phones."""
    results: list[ContactResult] = []

    # Primary search for official website
    ddg_results = await _ddg_search_or_raise(
        f'"{client_name}" official website contact',
        max_results=5,
        stage="website discovery",
    )
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

        results.extend(_results_from_page_content(
            html=html,
            text=text,
            source_url=url,
            source_type=source_type,
            email_confidence=0.7,
            phone_confidence=0.6,
        ))

    return _dedupe_results(results)


# ---------------------------------------------------------------------------
# Stage 2 — Instagram Discovery
# ---------------------------------------------------------------------------


async def ig_discovery(client_name: str) -> InstagramDiscoveryResult:
    """Find IG handle via DDG → scrape posts → GPT vision OCR."""
    results: list[ContactResult] = []

    ig_handle, ig_url = await _select_corporate_ig_candidate(client_name)

    if not ig_handle:
        return InstagramDiscoveryResult()

    # Scrape posts (run sync function in executor)
    try:
        loop = asyncio.get_running_loop()
        posts = await loop.run_in_executor(
            None, partial(scrape_ig_posts_with_fallback, ig_handle, 6)
        )
    except Exception as e:
        log.warning(f"[Marketing IG Discovery] scrape failed for {ig_handle}: {e}")
        return InstagramDiscoveryResult(handle=ig_handle, profile_url=ig_url)

    for post in posts:
        image_url = post.get("image_url", "")
        caption = post.get("caption", "")
        post_url = post.get("post_url", "")

        if not image_url:
            continue

        # Extract phones from post image via GPT Vision
        try:
            phone_contacts = await extract_phone_from_image(
                image_url,
                caption,
                require_person_name=False,
            )
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
                named_contacts = await extract_named_contacts_from_text(
                    caption,
                    require_person_name=False,
                )
                for nc in named_contacts:
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

    return InstagramDiscoveryResult(
        handle=ig_handle,
        profile_url=ig_url,
        posts=posts,
        contacts=_dedupe_results(results),
    )


# ---------------------------------------------------------------------------
# Stage 3 — Web Search Fallback
# ---------------------------------------------------------------------------


async def web_search_fallback(client_name: str) -> list[ContactResult]:
    """Broad DDG search → parse snippets and fetch result pages for contacts."""
    results: list[ContactResult] = []

    query = f'"{client_name}" WhatsApp email kontak PIC jabatan sekretariat'
    ddg_results = await _ddg_search_or_raise(
        query,
        max_results=8,
        stage="web search fallback",
    )

    all_text = ""
    for r in ddg_results:
        snippet = r.get("snippet", "")
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

    page_fetches = []
    seen_links: set[str] = set()
    for result in ddg_results:
        link = (result.get("link") or "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        page_fetches.append((link, "ddg_result_page"))

    for url, source_type in page_fetches:
        html = await fetch_page(url)
        if not html:
            continue
        text = extract_text_from_html(html)
        if not text:
            continue
        results.extend(_results_from_page_content(
            html=html,
            text=text,
            source_url=url,
            source_type=source_type,
            email_confidence=0.45,
            phone_confidence=0.5,
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

            if stage2.handle:
                await mkt.save_client_instagram_profile(
                    client_id,
                    stage2.handle,
                    stage2.profile_url,
                )
                await mkt.replace_client_ig_posts(client_id, stage2.handle, stage2.posts)

            all_results = _dedupe_results(stage1 + stage2.contacts + stage3)
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
