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
    search_ig_handle_with_fallback,
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
_CORPORATE_INVALID_HANDLE_SUFFIXES = (".js", ".css", ".json", ".php", ".xml")
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
_CORPORATE_SOURCE_BONUS = {
    "website_social": 0.22,
    "web_mention": 0.14,
    "ig_web_search": 0.12,
    "ddg_search": 0.08,
}
_CORPORATE_MAX_CANDIDATES = 8
_CORPORATE_MAX_SELECTED_HANDLES = 3
_INSTAGRAM_URL_PATTERN = re.compile(
    r'https?:\\?/\\?/(?:www\\.)?instagram\.com\\?/[^\s"\'<>\\]+|'
    r'https?://(?:www\.)?instagram\.com/[^\s"\'<>]+|'
    r'(?:www\.)?instagram\.com/[^\s"\'<>]+',
    re.IGNORECASE,
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


def _primary_company_token(company_name: str) -> str:
    tokens = _normalize_company_tokens(company_name)
    return tokens[0] if tokens else ""


def _is_likely_official_company_domain(company_name: str, url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if not host:
        return False

    host = host.removeprefix("www.")
    host_flat = re.sub(r"[^a-z0-9]", "", host)
    tokens = _normalize_company_tokens(company_name)
    abbreviation = _build_company_abbreviation(company_name)

    if abbreviation and len(abbreviation) >= 3 and abbreviation in host_flat:
        return True

    matching_tokens = [token for token in tokens if token in host_flat]
    if len(matching_tokens) >= 1:
        return True

    return False


def _build_company_search_aliases(company_name: str) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()

    def add_alias(value: str) -> None:
        alias = re.sub(r"\s+", " ", value).strip()
        if not alias:
            return
        key = alias.lower()
        if key in seen:
            return
        seen.add(key)
        aliases.append(alias)

    tokens = _normalize_company_tokens(company_name)
    if company_name.strip():
        add_alias(company_name)
    if tokens:
        add_alias(" ".join(tokens))
        add_alias(tokens[0])
    if len(tokens) >= 2:
        add_alias(" ".join(tokens[:2]))
    if len(tokens) >= 3:
        add_alias(" ".join(tokens[:3]))

    abbreviation = _build_company_abbreviation(company_name)
    if abbreviation:
        add_alias(abbreviation)

    if tokens and tokens[0] not in {"info", "official"}:
        add_alias(f"info {tokens[0]}")
        add_alias(f"{tokens[0]} official")

    return aliases[:6]


def _extract_instagram_urls_from_html(html: str) -> list[str]:
    normalized_html = html.replace("\\/", "/")
    links: set[str] = set(extract_social_links(normalized_html).get("instagram", []))

    for match in _INSTAGRAM_URL_PATTERN.findall(normalized_html):
        cleaned = match.replace("\\/", "/")
        if cleaned.startswith("www."):
            cleaned = f"https://{cleaned}"
        elif cleaned.startswith("instagram.com/"):
            cleaned = f"https://www.{cleaned}"
        elif cleaned.startswith("http://instagram.com/"):
            cleaned = cleaned.replace("http://instagram.com/", "https://www.instagram.com/", 1)
        elif cleaned.startswith("https://instagram.com/"):
            cleaned = cleaned.replace("https://instagram.com/", "https://www.instagram.com/", 1)
        links.add(cleaned)

    return sorted(links)


def _candidate_base_score_from_source(
    company_name: str,
    handle: str,
    title: str,
    snippet: str,
    source: str,
) -> float:
    return _score_company_ig_candidate(company_name, handle, title, snippet)


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
    if handle.endswith(_CORPORATE_INVALID_HANDLE_SUFFIXES):
        return None
    if not re.fullmatch(r"[a-z0-9._]{1,30}", handle):
        return None
    return handle


def _score_company_ig_candidate(company_name: str, handle: str, title: str, snippet: str) -> float:
    tokens = _normalize_company_tokens(company_name)
    primary_token = _primary_company_token(company_name)
    abbreviation = _build_company_abbreviation(company_name)
    handle_lower = handle.lower()
    handle_stripped = re.sub(r"[_.\-]", "", handle_lower)
    title_lower = title.lower()
    snippet_lower = snippet.lower()

    score = 0.0

    token_hits = sum(1 for token in tokens if token in handle_stripped)
    if token_hits:
        score += 0.35 * min(token_hits / max(len(tokens), 1), 1.0)

    if primary_token and primary_token in handle_stripped:
        score += 0.12
        if handle_stripped.startswith(primary_token) or handle_stripped.endswith(primary_token):
            score += 0.05

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

    return max(min(score, 1.0), -1.0)


def _company_affinity_score(candidate: dict, company_name: str) -> float:
    tokens = _normalize_company_tokens(company_name)
    primary_token = _primary_company_token(company_name)
    abbreviation = _build_company_abbreviation(company_name)
    handle = (candidate.get("handle") or "").lower()
    handle_flat = re.sub(r"[^a-z0-9]", "", handle)
    combined_text = " ".join(
        str(candidate.get(field_name) or "").lower()
        for field_name in ("title", "snippet", "full_name", "bio", "external_domain")
    )
    combined_flat = re.sub(r"[^a-z0-9\s]", " ", combined_text)

    score = 0.0

    if primary_token and primary_token in handle_flat:
        score += 0.45
        if handle_flat.startswith(primary_token) or handle_flat.endswith(primary_token):
            score += 0.1

    weights = [1.0, 0.7, 0.55, 0.4]
    for index, token in enumerate(tokens):
        weight = weights[index] if index < len(weights) else 0.3
        if token in handle_flat:
            score += 0.18 * weight
        if token in combined_flat:
            score += 0.1 * weight

    if abbreviation and len(abbreviation) >= 3 and abbreviation in handle_flat:
        score += 0.15

    exact_phrase = company_name.lower()
    if exact_phrase in combined_text:
        score += 0.18

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


def _candidate_sort_score(candidate: dict) -> float:
    source_bonus = _CORPORATE_SOURCE_BONUS.get(candidate.get("source", ""), 0.0)
    llm_bonus = 0.0
    if candidate.get("llm_is_correct") is True:
        llm_bonus = 0.2 + min(float(candidate.get("llm_confidence", 0.0)), 1.0) * 0.1
    elif candidate.get("llm_is_correct") is False:
        llm_bonus = -0.35
    if candidate.get("llm_is_correct") is not True:
        source_bonus *= 0.15
    affinity_bonus = float(candidate.get("affinity_score", 0.0)) * 0.18
    return float(candidate.get("final_score", 0.0)) + source_bonus + llm_bonus + affinity_bonus


def _has_strong_company_match(candidate: dict, company_name: str) -> bool:
    tokens = _normalize_company_tokens(company_name)
    abbreviation = _build_company_abbreviation(company_name)
    handle = (candidate.get("handle") or "").lower()
    text = " ".join(
        str(candidate.get(field_name) or "").lower()
        for field_name in ("title", "snippet", "full_name", "bio", "external_domain")
    )
    handle_flat = re.sub(r"[^a-z0-9]", "", handle)
    text_flat = re.sub(r"[^a-z0-9\s]", " ", text)

    if abbreviation and len(abbreviation) >= 3 and abbreviation in handle_flat:
        return True

    handle_hits = sum(1 for token in tokens if token in handle_flat)
    text_hits = sum(1 for token in tokens if token in text_flat)

    if handle_hits >= 1:
        return True
    if text_hits >= 2:
        return True

    exact_phrase = company_name.lower()
    return exact_phrase in text


def _upsert_company_candidate(candidates_by_handle: dict[str, dict], candidate: dict) -> None:
    handle = (candidate.get("handle") or "").lower().strip()
    if not handle:
        return

    candidate["handle"] = handle
    existing = candidates_by_handle.get(handle)
    if existing is None:
        candidates_by_handle[handle] = candidate
        return

    if float(candidate.get("base_score", 0.0)) > float(existing.get("base_score", 0.0)):
        existing["base_score"] = candidate.get("base_score", existing.get("base_score", 0.0))
        existing["source"] = candidate.get("source", existing.get("source"))
        existing["title"] = candidate.get("title", existing.get("title", ""))
        existing["snippet"] = candidate.get("snippet", existing.get("snippet", ""))
        existing["url"] = candidate.get("url", existing.get("url"))

    for field_name in ("title", "snippet", "url", "full_name", "bio", "external_url", "external_domain"):
        if not existing.get(field_name) and candidate.get(field_name):
            existing[field_name] = candidate[field_name]


async def _company_pages_to_check(client_name: str) -> list[tuple[str, str]]:
    ddg_results = await _ddg_search_or_raise(
        f'"{client_name}" official website contact',
        max_results=5,
        stage="website discovery",
    )
    if not ddg_results:
        return []

    pages_to_check: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for result in ddg_results:
        url = (result.get("link") or "").strip()
        if not url:
            continue
        if not _is_likely_official_company_domain(client_name, url):
            continue

        candidates = [(url, "website")]
        base = url.rstrip("/")
        for path in ("/contact", "/contact-us", "/about", "/tentang-kami", "/hubungi-kami"):
            candidates.append((base + path, "contact_page"))

        for candidate_url, source_type in candidates:
            if candidate_url in seen_urls:
                continue
            seen_urls.add(candidate_url)
            pages_to_check.append((candidate_url, source_type))

    return pages_to_check


async def _collect_ddg_company_candidates(client_name: str) -> list[dict]:
    candidates: list[dict] = []
    for alias in _build_company_search_aliases(client_name):
        ddg_results = await _ddg_search_or_raise(
            f'"{alias}" site:instagram.com',
            max_results=8,
            stage="instagram discovery",
        )

        for result in ddg_results:
            link = (result.get("link") or "").strip()
            handle = _extract_direct_ig_profile_handle(link)
            if not handle:
                continue
            title = result.get("title", "") or ""
            snippet = result.get("snippet", "") or ""
            candidates.append({
                "handle": handle,
                "url": link,
                "source": "ddg_search",
                "title": title,
                "snippet": snippet,
                "base_score": _candidate_base_score_from_source(
                    client_name,
                    handle,
                    title,
                    snippet,
                    "ddg_search",
                ),
            })
    return candidates


async def _collect_ig_web_company_candidates(client_name: str) -> list[dict]:
    loop = asyncio.get_running_loop()
    excluded: set[str] = set()
    candidates: list[dict] = []

    for _ in range(4):
        result = await loop.run_in_executor(
            None,
            partial(search_ig_handle_with_fallback, client_name, excluded),
        )
        if not result or not result.get("handle"):
            break

        handle = (result.get("handle") or "").lower().strip()
        if not handle or handle in excluded:
            break

        excluded.add(handle)
        candidates.append({
            "handle": handle,
            "url": result.get("url"),
            "source": "ig_web_search",
            "title": result.get("title", "") or "",
            "snippet": result.get("snippet", "") or "",
            "base_score": float(result.get("confidence", 0.0)),
        })

    return candidates


async def _collect_website_company_candidates(client_name: str) -> list[dict]:
    candidates: list[dict] = []
    pages_to_check = await _company_pages_to_check(client_name)
    for url, source_type in pages_to_check:
        html = await fetch_page(url)
        if not html:
            continue
        for link in _extract_instagram_urls_from_html(html):
            handle = _extract_direct_ig_profile_handle(link)
            if not handle:
                continue
            title = f"Found on {urlparse(url).netloc}"
            snippet = f"Instagram link extracted from {source_type}: {url}"
            base_score = _candidate_base_score_from_source(
                client_name,
                handle,
                title,
                snippet,
                "website_social",
            )
            candidates.append({
                "handle": handle,
                "url": link,
                "source": "website_social",
                "title": title,
                "snippet": snippet,
                "base_score": base_score,
            })
    return candidates


async def _collect_web_mention_company_candidates(client_name: str) -> list[dict]:
    candidates: list[dict] = []
    seen_pages: set[str] = set()

    for alias in _build_company_search_aliases(client_name)[:4]:
        results = await _ddg_search_or_raise(
            f'"{alias}" instagram official',
            max_results=6,
            stage="instagram web mentions",
        )
        for result in results:
            result_link = (result.get("link") or "").strip()
            if not result_link or result_link in seen_pages:
                continue
            seen_pages.add(result_link)

            direct_handle = _extract_direct_ig_profile_handle(result_link)
            if direct_handle:
                title = result.get("title", "") or ""
                snippet = result.get("snippet", "") or ""
                candidates.append({
                    "handle": direct_handle,
                    "url": result_link,
                    "source": "web_mention",
                    "title": title,
                    "snippet": snippet,
                    "base_score": _candidate_base_score_from_source(
                        client_name,
                        direct_handle,
                        title,
                        snippet,
                        "web_mention",
                    ),
                })
                continue

            html = await fetch_page(result_link)
            if not html:
                continue

            for instagram_url in _extract_instagram_urls_from_html(html):
                handle = _extract_direct_ig_profile_handle(instagram_url)
                if not handle:
                    continue
                title = result.get("title", "") or ""
                snippet = result.get("snippet", "") or ""
                candidates.append({
                    "handle": handle,
                    "url": instagram_url,
                    "source": "web_mention",
                    "title": title,
                    "snippet": snippet or f"Instagram URL extracted from {result_link}",
                    "base_score": _candidate_base_score_from_source(
                        client_name,
                        handle,
                        title,
                        snippet,
                        "web_mention",
                    ),
                })

    return candidates


async def _evaluate_corporate_ig_candidates(client_name: str) -> list[dict]:
    candidates_by_handle: dict[str, dict] = {}

    for candidate in await _collect_ddg_company_candidates(client_name):
        _upsert_company_candidate(candidates_by_handle, candidate)

    for candidate in await _collect_ig_web_company_candidates(client_name):
        _upsert_company_candidate(candidates_by_handle, candidate)

    try:
        for candidate in await _collect_website_company_candidates(client_name):
            _upsert_company_candidate(candidates_by_handle, candidate)
        for candidate in await _collect_web_mention_company_candidates(client_name):
            _upsert_company_candidate(candidates_by_handle, candidate)
    except SearchDependencyError:
        raise
    except Exception as exc:
        log.warning("[Marketing IG] Website candidate collection failed for %s: %s", client_name, exc)

    if not candidates_by_handle:
        return []

    candidates = list(candidates_by_handle.values())
    candidates.sort(key=lambda item: float(item.get("base_score", 0.0)), reverse=True)

    loop = asyncio.get_running_loop()
    enriched = await loop.run_in_executor(
        None,
        fetch_bios_for_candidates,
        candidates,
        min(_CORPORATE_MAX_CANDIDATES, len(candidates)),
    )

    for candidate in enriched:
        profile_score = _boost_company_candidate_from_profile(candidate, client_name)
        affinity_score = _company_affinity_score(candidate, client_name)
        candidate["affinity_score"] = affinity_score
        candidate["profile_score"] = profile_score
        candidate["final_score"] = float(candidate.get("base_score", 0.0)) + profile_score
        llm = await llm_verify_company_ig_handle(
            candidate.get("handle", ""),
            candidate.get("bio", "") or "",
            candidate.get("full_name", "") or "",
            client_name,
            candidate.get("external_url", "") or "",
        )
        candidate["llm_is_correct"] = llm.get("is_correct")
        candidate["llm_confidence"] = float(llm.get("confidence", 0.0))
        candidate["llm_reason"] = llm.get("reason", "")

    ranked = sorted(enriched, key=_candidate_sort_score, reverse=True)

    selected: list[dict] = []
    for candidate in ranked:
        if candidate.get("llm_is_correct") is False:
            continue
        if candidate.get("llm_is_correct") is True:
            selected.append(candidate)
        elif _candidate_sort_score(candidate) >= 0.45 and _has_strong_company_match(candidate, client_name):
            selected.append(candidate)
        if len(selected) >= _CORPORATE_MAX_SELECTED_HANDLES:
            break

    if not selected and ranked:
        selected.append(ranked[0])

    selected_handles = {candidate.get("handle") for candidate in selected}
    primary_handle = selected[0].get("handle") if selected else None
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank_order"] = index
        candidate["is_selected"] = candidate.get("handle") in selected_handles
        candidate["is_primary"] = candidate.get("handle") == primary_handle

    return ranked[:_CORPORATE_MAX_CANDIDATES]


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
    candidates: list[dict] = field(default_factory=list)


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
    combined_email_text = f"{text}\n{html}"

    for email in extract_emails(combined_email_text):
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

    pages_to_check = await _company_pages_to_check(client_name)
    if not pages_to_check:
        return results

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

    candidates = await _evaluate_corporate_ig_candidates(client_name)
    selected_candidates = [candidate for candidate in candidates if candidate.get("is_selected")]
    primary_candidate = next((candidate for candidate in candidates if candidate.get("is_primary")), None)

    if not selected_candidates:
        return InstagramDiscoveryResult(candidates=candidates)

    all_posts: list[dict] = []
    seen_post_urls: set[str] = set()
    loop = asyncio.get_running_loop()

    for candidate in selected_candidates:
        ig_handle = candidate.get("handle")
        if not ig_handle:
            continue

        max_posts = 6 if candidate.get("is_primary") else 4
        try:
            posts = await loop.run_in_executor(
                None, partial(scrape_ig_posts_with_fallback, ig_handle, max_posts)
            )
        except Exception as e:
            log.warning("[Marketing IG Discovery] scrape failed for %s: %s", ig_handle, e)
            continue

        for post in posts:
            post_url = post.get("post_url")
            if post_url and post_url in seen_post_urls:
                continue
            if post_url:
                seen_post_urls.add(post_url)
            post["ig_handle"] = ig_handle
            all_posts.append(post)

    if not all_posts:
        return InstagramDiscoveryResult(
            handle=primary_candidate.get("handle") if primary_candidate else None,
            profile_url=primary_candidate.get("url") if primary_candidate else None,
            candidates=candidates,
        )

    for post in all_posts:
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
        handle=primary_candidate.get("handle") if primary_candidate else None,
        profile_url=primary_candidate.get("url") if primary_candidate else None,
        posts=all_posts,
        contacts=_dedupe_results(results),
        candidates=candidates,
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

    email_results = [result for result in deduped if result.contact_type == "email" and result.value]
    suppressed_emails: set[str] = set()
    for result in email_results:
        local_part, _, domain = result.value.lower().partition("@")
        for other in email_results:
            if other is result:
                continue
            other_local, _, other_domain = other.value.lower().partition("@")
            if domain != other_domain:
                continue
            if len(other_local) <= len(local_part):
                continue
            if len(other_local) - len(local_part) > 2:
                continue
            if other_local.endswith(local_part):
                suppressed_emails.add(result.value)
                break

    if not suppressed_emails:
        return deduped

    return [
        result for result in deduped
        if result.contact_type != "email" or result.value not in suppressed_emails
    ]


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

            await mkt.replace_client_ig_candidates(client_id, stage2.candidates)

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
