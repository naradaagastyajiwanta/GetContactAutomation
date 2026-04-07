"""
3-Stage Search Pipeline for corporate outreach.
Stage 1: Website discovery (DDG → website → emails/phones)
Stage 2: IG discovery (DDG → IG handle → scrape posts → GPT vision OCR)
Stage 3: Web search fallback (DDG broad search → parse snippets)
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Iterable
from urllib.parse import urlparse
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from orchestrator.config import log, cfg
from orchestrator.duckduckgo_client import get_status as get_ddg_status
from orchestrator import playwright_ig, scrapingbot_client
from orchestrator.osint.tools import (
    ddg_search,
    web_search,
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
    gemini_compare_corporate_ig_candidates,
    search_ig_handle_with_fallback,
    get_ig_session_status,
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
_MARKETING_BLOCKED_CONTACT_SOURCE_DOMAINS = {
    "signalhire.com",
    "locallead.ai",
    "rocketreach.co",
    "rocketreach.io",
    "zoominfo.com",
    "apollo.io",
    "lusha.com",
    "seamless.ai",
    "contactout.com",
    "aeroleads.com",
    "skrapp.io",
    "growjo.com",
}
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
    "076", "077", "078", "079",
)

# Feature C: Expanded Indonesian contact page paths
_CONTACT_PAGE_PATHS = (
    "/contact", "/contact-us", "/about", "/tentang-kami", "/hubungi-kami",
    "/kontak", "/hubungi", "/sekretariat", "/layanan", "/profil",
    "/tentang", "/cs", "/informasi", "/direktori",
    "/struktur-organisasi", "/pimpinan", "/profil-perusahaan",
)

# Feature B: Patterns for plain-text phone numbers in IG bio
_BIO_PHONE_LABEL_PATTERN = re.compile(
    r'(?:WA|WhatsApp|Whatsapp|wa|HP|Hp|Tlp|Tlpn|Telp|Phone|Hubungi|Hub|CP|Contact|cs|CS|Order|Info|Pesan)'
    r'[:\s\.\/]*([0-9+][0-9\s\-\.]{7,16})',
    re.IGNORECASE,
)
_BIO_EMOJI_PHONE_PATTERN = re.compile(
    r'(?:📱|☎️|📞|💬|✆|☎)\s*([0-9+][0-9\s\-\.]{7,16})',
)
_BIO_RAW_MOBILE_PATTERN = re.compile(
    r'(?<!\d)(0(?:8[1-9]\d{7,10})|628[1-9]\d{7,10})(?!\d)',
)

# Feature E: Multi-query search variants per client_type
_WEBSITE_QUERY_VARIANTS: dict[str | None, list[str]] = {
    "lsp_p1": [
        '"{name}" LSP sertifikasi kompetensi kontak WA',
        '"{name}" lembaga sertifikasi profesi sekretariat',
        '"{name}" BNSP situs resmi kontak',
    ],
    "lsp_p2": [
        '"{name}" LSP P2 sertifikasi kontak WA',
        '"{name}" lembaga sertifikasi profesi hubungi',
    ],
    "lsp_p3": [
        '"{name}" LSP sertifikasi profesi kontak email',
        '"{name}" lembaga sertifikasi WA sekretariat',
    ],
    "kementerian": [
        '"{name}" kementerian Indonesia kontak resmi sekretariat',
        '"{name}" sekretariat jenderal telepon email',
        'site:go.id "{name}" kontak',
    ],
    "lembaga_negara": [
        '"{name}" lembaga negara Indonesia kontak resmi',
        '"{name}" sekretariat kontak email telepon',
        'site:go.id "{name}" kontak',
    ],
    "bumn": [
        '"{name}" BUMN Indonesia hubungi kami kontak WA',
        '"{name}" customer service email telepon',
        '"{name}" sekretaris perusahaan kontak',
    ],
    "asosiasi": [
        '"{name}" asosiasi Indonesia kontak sekretariat WA',
        '"{name}" organisasi kontak email narahubung',
        '"{name}" association secretariat contact Indonesia',
    ],
    "lpk": [
        '"{name}" LPK pelatihan kerja kontak WA pendaftaran',
        '"{name}" lembaga pelatihan nomor telepon email',
        '"{name}" kursus pelatihan kontak daftar',
    ],
    "lkp": [
        '"{name}" LKP lembaga kursus kontak WA',
        '"{name}" kursus pelatihan nomor hubungi',
    ],
    "dinas": [
        '"{name}" dinas pemerintah kontak resmi',
        '"{name}" kantor dinas sekretariat telepon',
        'site:go.id "{name}" kontak',
    ],
    "swasta_besar": [
        '"{name}" perusahaan Indonesia hubungi kami kontak',
        '"{name}" customer service WA email',
        '"{name}" corporate contact Indonesia',
    ],
    None: [
        '"{name}" kontak WA telepon email Indonesia',
        '"{name}" official website contact',
    ],
}


def _build_website_search_queries(client_name: str, client_type: str | None = None) -> list[str]:
    """Generate up to 3 search query variants based on client_type."""
    templates = _WEBSITE_QUERY_VARIANTS.get(client_type) or _WEBSITE_QUERY_VARIANTS[None]
    return [t.replace("{name}", client_name) for t in templates[:3]]


_HIGH_TRUST_CONTACT_SOURCE_TYPES = {
    "website",
    "official_website",
    "contact_page",
    "website_social",
    "ig_post",
    "ig_caption",
}

_MEDIUM_TRUST_CONTACT_SOURCE_TYPES = {
    "ddg_result_page",
    "web_mention",
    "gemini_grounded",
}


def is_mobile_phone(phone: str) -> bool:
    """Return True if phone is a mobile Indonesian number (not landline)."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10 or len(digits) > 14:
        return False

    normalized = digits
    if digits.startswith("0"):
        normalized = f"62{digits[1:]}"
    elif digits.startswith("8"):
        normalized = f"62{digits}"

    if not normalized.startswith("628"):
        return False

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


def _extract_office_phones_from_text(text: str) -> list[str]:
    area_codes = "|".join(sorted({prefix.removeprefix("0") for prefix in _LANDLINE_PREFIXES}))
    pattern = re.compile(
        rf"(?:(?:\+62|62|0)\s*(?:{area_codes}))(?:[\s\-.()]*(?:\d{{2,4}})){{2,4}}"
    )
    phones: list[str] = []
    seen: set[str] = set()

    for match in pattern.findall(text):
        cleaned = re.sub(r"[()]", " ", match)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
        digits = re.sub(r"\D", "", cleaned)
        if len(digits) < 9 or len(digits) > 14:
            continue

        normalized = digits
        if digits.startswith("62"):
            normalized = f"0{digits[2:]}"
        elif not digits.startswith("0"):
            normalized = f"0{digits}"

        if not any(normalized.startswith(prefix) for prefix in _LANDLINE_PREFIXES):
            continue
        if normalized in seen:
            continue

        seen.add(normalized)
        phones.append(cleaned)

    return phones


_INDONESIAN_STOP_WORDS = {
    # Conjunctions / prepositions
    "dan", "atau", "dari", "untuk", "dengan", "dalam", "pada", "kepada",
    "oleh", "antara", "tentang", "terhadap", "atas", "bagi", "serta",
    # Structural words in org names
    "bidang", "urusan", "unit", "pusat", "kantor", "direktorat",
    "sub", "bagian", "seksi", "sekretariat",
}

# .go.id and .or.id are verified Indonesian TLDs — always trust them
_TRUSTED_INDONESIAN_TLDS = (".go.id", ".or.id", ".ac.id", ".sch.id", ".mil.id")


def _normalize_company_tokens(company_name: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", company_name.lower())
    return [
        token for token in tokens
        if len(token) > 2
        and token not in _CORPORATE_GENERIC_WORDS
        and token not in _INDONESIAN_STOP_WORDS
    ]


def _build_company_abbreviation(company_name: str) -> str:
    tokens = _normalize_company_tokens(company_name)
    if len(tokens) < 2:
        return ""
    return "".join(token[0] for token in tokens)


def _primary_company_token(company_name: str) -> str:
    tokens = _normalize_company_tokens(company_name)
    return tokens[0] if tokens else ""


def _canonical_company_page_roots(url: str) -> list[str]:
    parsed = urlparse(url)
    if not parsed.netloc:
        return []

    scheme = parsed.scheme or "https"
    root = f"{scheme}://{parsed.netloc}"
    roots = [root.rstrip("/")]

    path = parsed.path.rstrip("/")
    if path:
        roots.append(f"{roots[0]}{path}")

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in roots:
        normalized = candidate.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _is_likely_official_company_domain(company_name: str, url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if not host:
        return False

    host = host.removeprefix("www.")
    host_flat = re.sub(r"[^a-z0-9]", "", host)

    # 1. Trusted Indonesian TLDs (.go.id, .or.id, .ac.id etc.) are verified domains —
    #    accept unconditionally since they can only be registered by the actual institution.
    if any(host.endswith(tld) for tld in _TRUSTED_INDONESIAN_TLDS):
        return True

    tokens = _normalize_company_tokens(company_name)
    abbreviation = _build_company_abbreviation(company_name)

    # 2. Full abbreviation match in domain
    if abbreviation and len(abbreviation) >= 3 and abbreviation in host_flat:
        return True

    # 3. Partial abbreviation — first 3 or 4 chars of abbreviation (catches ptba, bpom, etc.)
    if abbreviation and len(abbreviation) >= 4:
        for length in (4, 3):
            partial = abbreviation[:length]
            if partial in host_flat:
                return True

    # 4. Any meaningful token from company name appears in domain
    matching_tokens = [token for token in tokens if len(token) >= 4 and token in host_flat]
    if matching_tokens:
        return True

    # 5. First meaningful token (primary brand name) appears in domain
    primary = _primary_company_token(company_name)
    if primary and len(primary) >= 4 and primary in host_flat:
        return True

    return False


def _is_blocked_marketing_contact_source(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if not host:
        return False
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in _MARKETING_BLOCKED_CONTACT_SOURCE_DOMAINS)


def _is_blocked_marketing_email(email: str) -> bool:
    _, _, domain = (email or "").strip().lower().partition("@")
    if not domain:
        return False
    return any(domain == blocked or domain.endswith(f".{blocked}") for blocked in _MARKETING_BLOCKED_CONTACT_SOURCE_DOMAINS)


def _should_prune_persisted_contact(contact: dict[str, Any]) -> bool:
    source_url = str(contact.get("source_url") or "").strip()
    value = str(contact.get("edited_value") or contact.get("value") or "").strip()
    contact_type = str(contact.get("contact_type") or "").strip()

    if source_url and _is_blocked_marketing_contact_source(source_url):
        return True

    if contact_type == "email" and value and _is_blocked_marketing_email(value):
        return True

    if contact_type == "wa_phone" and value and not is_mobile_phone(value):
        return True

    return False


async def _prune_stale_client_contacts(client_id: int) -> int:
    from . import groups as mkt

    contacts = await mkt.get_contact_results_for_client(client_id)
    stale_contact_ids = [
        int(contact["id"])
        for contact in contacts
        if contact.get("id") is not None and _should_prune_persisted_contact(contact)
    ]
    if not stale_contact_ids:
        return 0

    await mkt.delete_client_contact_results_by_ids(client_id, stale_contact_ids)
    return len(stale_contact_ids)


def _contact_source_signature(result: "ContactResult") -> tuple[str, str]:
    source_type = (result.source_type or "").strip().lower()
    host = urlparse((result.source_url or "").strip()).netloc.lower().removeprefix("www.")
    return (source_type, host)


def _contact_source_trust(result: "ContactResult") -> int:
    source_type = (result.source_type or "").strip().lower()
    source_url = (result.source_url or "").strip()

    if source_url and _is_blocked_marketing_contact_source(source_url):
        return 0

    if source_type in _HIGH_TRUST_CONTACT_SOURCE_TYPES:
        return 3

    if source_type in _MEDIUM_TRUST_CONTACT_SOURCE_TYPES:
        return 2

    if source_type:
        return 1

    return 0


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

    # Concatenated unspaced tokens — catches handles like "charoenpokphand", "hmsampoerna"
    # Uses 2-char+ raw tokens so short prefixes like "hm" contribute (bypassing the len>2 filter)
    raw_tokens = [
        t for t in re.findall(r"[a-z0-9]+", company_name.lower())
        if len(t) >= 2 and t not in _CORPORATE_GENERIC_WORDS and t not in _INDONESIAN_STOP_WORDS
    ]
    if len(raw_tokens) >= 2:
        add_alias("".join(raw_tokens[:3]))
        if len(raw_tokens) >= 3:
            add_alias("".join(raw_tokens[:2]))

    return aliases[:8]


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


def _candidate_has_profile_evidence(candidate: dict) -> bool:
    return any(
        str(candidate.get(field_name) or "").strip()
        for field_name in ("bio", "full_name", "external_url", "external_domain")
    )


_EVENT_KEYWORDS = {
    "event", "exhibition", "expo", "booth", "seminar", "workshop",
    "trade show", "pameran", "acara", "festival", "konferensi",
    "seminar", "webinar", "training", "pelatihan", "roadshow",
    "conference", "summit", "gathering", "launch", "grand opening",
}

_CORPORATE_SIGNALS = {
    "pt", "pt.", "tbk", "cv", "corp", "company", "official",
    "direktur", "manajer", "managing", "sekretaris", "secretary",
    "holding", "group", "persero", "resmi", "internasional",
}


def _is_event_account(handle: str, bio: str, title: str) -> bool:
    """
    Returns True if this IG account is an EVENT/ANNOUNCEMENT account
    (not a corporate account).

    Event signals: bio or title contains only event keywords.
    Corporate signals: bio or title contains company indicators.
    If BOTH present -> treat as corporate (company does events too)
    If ONLY event signals -> SKIP this candidate.
    """
    combined = f"{bio} {title}".lower()
    event_hits = sum(1 for kw in _EVENT_KEYWORDS if kw in combined)
    corp_hits = sum(1 for sig in _CORPORATE_SIGNALS if sig in combined)

    if event_hits == 0:
        return False
    if corp_hits > 0:
        return False
    return True


def _normalize_raw_phone(raw: str) -> str | None:
    """Normalize raw phone string to +62 format. Returns None if not a valid mobile."""
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if digits.startswith("0"):
        normalized = f"+62{digits[1:]}"
    elif digits.startswith("62"):
        normalized = f"+{digits}"
    elif digits.startswith("8"):
        normalized = f"+62{digits}"
    else:
        normalized = f"+{digits}"
    # Validate: must be mobile Indonesian
    if not is_mobile_phone(normalized):
        return None
    return normalized


def _extract_wa_from_bio(bio: str, handle: str) -> list[ContactResult]:
    """
    Extract WA numbers from IG bio.

    Detects:
    1. wa.me / api.whatsapp.com URL links (confidence 0.8)
    2. Labeled plain-text phones: "WA: 0812xxx", "📱 628xxx" (confidence 0.75)
    3. Raw mobile numbers embedded in bio text (confidence 0.65)
    """
    results: list[ContactResult] = []
    seen: set[str] = set()

    def _add(digits: str, source_type: str, confidence: float) -> None:
        normalized = _normalize_raw_phone(digits)
        if normalized and normalized not in seen:
            seen.add(normalized)
            results.append(ContactResult(
                contact_type="wa_phone",
                value=normalized,
                source_url=f"https://www.instagram.com/{handle}/",
                source_type=source_type,
                confidence=confidence,
            ))

    # 1. wa.me / api.whatsapp.com URL links
    for pattern in _WHATSAPP_URL_PATTERNS:
        for raw_digits in pattern.findall(bio):
            _add(raw_digits, "ig_bio", 0.8)

    # 2. Labeled plain-text phones: "WA: 0812xxx", "Hub: 0821xxx"
    for m in _BIO_PHONE_LABEL_PATTERN.finditer(bio):
        _add(m.group(1), "ig_bio_text", 0.75)

    # 3. Emoji + phone: "📱 62812xxxx"
    for m in _BIO_EMOJI_PHONE_PATTERN.finditer(bio):
        _add(m.group(1), "ig_bio_text", 0.75)

    # 4. Raw mobile numbers directly in bio (only if no labeled ones found yet)
    if not results:
        for m in _BIO_RAW_MOBILE_PATTERN.finditer(bio):
            _add(m.group(1), "ig_bio_text", 0.65)

    return results


def _candidate_has_non_llm_selection_evidence(candidate: dict) -> bool:
    if _candidate_has_profile_evidence(candidate):
        return True
    return candidate.get("source") == "website_social"


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


def _select_ranked_corporate_candidates(ranked: list[dict], company_name: str) -> list[dict]:
    selected: list[dict] = []

    for candidate in ranked:
        if candidate.get("llm_is_correct") is False:
            continue
        if candidate.get("llm_is_correct") is True:
            selected.append(candidate)
        elif (
            _candidate_has_non_llm_selection_evidence(candidate)
            and _candidate_sort_score(candidate) >= 0.45
            and _has_strong_company_match(candidate, company_name)
        ):
            selected.append(candidate)

        if len(selected) >= _CORPORATE_MAX_SELECTED_HANDLES:
            break

    if selected:
        return selected[:_CORPORATE_MAX_SELECTED_HANDLES]

    if not ranked:
        return []

    # Stricter fallback: only select ranked[0] as a probe if it has at least some
    # profile evidence and a minimum sort_score. This prevents wasting scrape credits
    # on clearly wrong accounts when all candidates were rejected.
    top = ranked[0]
    top_score = _candidate_sort_score(top)
    has_evidence = _candidate_has_profile_evidence(top)
    if has_evidence and top_score >= 0.30:
        log.warning(
            "[Selection] No confident match for '%s' — weak fallback: @%s (score=%.2f)",
            company_name, top.get("handle"), top_score,
        )
        return [top]

    log.warning(
        "[Selection] All candidates rejected for '%s' with no acceptable fallback (best score=%.2f, has_evidence=%s)",
        company_name, top_score, has_evidence,
    )
    return []


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


async def _company_pages_to_check(
    client_name: str,
    client_type: str | None = None,
) -> list[tuple[str, str]]:
    """
    Feature A + C + E: Discover official pages using Google-first search
    with Indonesian-specific multi-query variants and expanded contact paths.
    """
    queries = _build_website_search_queries(client_name, client_type)

    # Collect search results across all query variants (Google first, DDG fallback)
    all_results: list[dict] = []
    seen_result_links: set[str] = set()
    for query in queries:
        results = await web_search(query, max_results=5)
        for r in results:
            link = (r.get("link") or "").strip()
            if link and link not in seen_result_links:
                seen_result_links.add(link)
                all_results.append(r)
        if len(all_results) >= 8:
            break

    if not all_results:
        return []

    pages_to_check: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for result in all_results:
        url = (result.get("link") or "").strip()
        if not url:
            continue
        if not _is_likely_official_company_domain(client_name, url):
            continue

        candidates: list[tuple[str, str]] = []
        canonical_roots = _canonical_company_page_roots(url)
        for index, base in enumerate(canonical_roots):
            candidates.append((base, "website" if index == 0 else "contact_page"))
            if index != 0 or urlparse(base).path.rstrip("/"):
                continue
            # Feature C: expanded contact paths
            for path in _CONTACT_PAGE_PATHS:
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

    # Use all aliases (including concatenated forms) as distinct search queries so
    # handles like @charoenpokphandid and @hmsampoerna are reachable via the compact form
    search_names = _build_company_search_aliases(client_name)

    for search_name in search_names[:6]:
        result = await loop.run_in_executor(
            None,
            partial(search_ig_handle_with_fallback, search_name, excluded),
        )
        if not result or not result.get("handle"):
            continue

        handle = (result.get("handle") or "").lower().strip()
        if not handle or handle in excluded:
            continue

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


def _maybe_hard_anchor_from_website(candidate: dict, known_domain: str) -> bool:
    """Return True if this candidate is unambiguously linked from the official website."""
    if candidate.get("source") != "website_social":
        return False
    ext_domain = (candidate.get("external_domain") or "").lower().strip()
    if not known_domain or not ext_domain:
        return False
    # e.g. "semenindonesia.com" ↔ "semenindonesia.co.id" — normalise by stripping TLD
    known_core = known_domain.split(".")[0]
    ext_core = ext_domain.split(".")[0]
    return known_core == ext_core or known_domain in ext_domain or ext_domain in known_domain


async def _evaluate_corporate_ig_candidates(client_name: str, client_type: str = "") -> list[dict]:
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

    # Extract WA contacts from bio URLs before filtering/verification
    for candidate in enriched:
        bio = candidate.get("bio") or ""
        handle = candidate.get("handle") or ""
        candidate["wa_contacts"] = _extract_wa_from_bio(bio, handle)

    # Filter out event accounts before LLM verification and ranking
    enriched = [
        c for c in enriched
        if not _is_event_account(c.get("handle", ""), c.get("bio", ""), c.get("title", ""))
    ]

    # Domain hard-anchor: if any website_social candidate links back to a company domain
    # that appears in another candidate's external_domain, mark it trusted immediately.
    website_social_handles = {
        c.get("handle")
        for c in enriched
        if c.get("source") == "website_social" and c.get("handle")
    }
    # Collect known domains from all enriched candidates
    known_domains = [
        (c.get("external_domain") or "").lower().strip()
        for c in enriched
        if (c.get("external_domain") or "").strip()
    ]

    for candidate in enriched:
        profile_score = _boost_company_candidate_from_profile(candidate, client_name)
        affinity_score = _company_affinity_score(candidate, client_name)
        candidate["affinity_score"] = affinity_score
        candidate["profile_score"] = profile_score
        candidate["final_score"] = float(candidate.get("base_score", 0.0)) + profile_score

        # Hard-anchor: website_social candidate whose bio URL matches a known domain
        if candidate.get("source") == "website_social":
            for known_domain in known_domains:
                if known_domain and _maybe_hard_anchor_from_website(candidate, known_domain):
                    log.info(
                        "[IG-Hard-Anchor] @%s confirmed via website_social + domain '%s'",
                        candidate.get("handle"), known_domain,
                    )
                    candidate["llm_is_correct"] = True
                    candidate["llm_confidence"] = 1.0
                    candidate["llm_reason"] = f"Linked directly from company website (domain: {known_domain})"
                    break
            else:
                candidate.setdefault("llm_is_correct", None)
                candidate.setdefault("llm_confidence", 0.0)
                candidate.setdefault("llm_reason", "")
        else:
            candidate.setdefault("llm_is_correct", None)
            candidate.setdefault("llm_confidence", 0.0)
            candidate.setdefault("llm_reason", "")

    # Candidates that still need LLM evaluation (not hard-anchored)
    needs_llm = [c for c in enriched if c.get("llm_is_correct") is None]

    if needs_llm:
        gemini_results = await gemini_compare_corporate_ig_candidates(
            needs_llm, client_name, client_type
        )
        # Map results back by handle
        gemini_by_handle = {r.get("handle", "").lower().strip(): r for r in gemini_results}
        for candidate in needs_llm:
            handle = (candidate.get("handle") or "").lower().strip()
            gemini_hit = gemini_by_handle.get(handle)
            if gemini_hit:
                is_correct = gemini_hit.get("is_correct")
                candidate["llm_is_correct"] = bool(is_correct) if is_correct is not None else None
                candidate["llm_confidence"] = float(gemini_hit.get("confidence", 0.0))
                candidate["llm_reason"] = gemini_hit.get("reason", "")
            # else: keep defaults (None, 0.0, "")

    ranked = sorted(enriched, key=_candidate_sort_score, reverse=True)

    selected = _select_ranked_corporate_candidates(ranked, client_name)

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
    scrape_status: str | None = None
    scrape_error: str | None = None


@dataclass
class GeminiGroundedDiscoveryResult:
    contacts: list[ContactResult] = field(default_factory=list)
    grounded_urls: list[str] = field(default_factory=list)
    notes: str | None = None
    unresolved_gaps: list[str] = field(default_factory=list)
    parse_failed: bool = False


class SearchDependencyError(RuntimeError):
    """Raised when a required external search backend is unavailable."""


_MARKETING_MIN_POSTS_PER_CLIENT = 50


def is_marketing_gemini_enabled() -> bool:
    """Return True when the marketing pipeline may use Gemini grounding."""
    return bool(cfg.get("MARKETING_GEMINI_ENABLED", True)) and bool(cfg.get("GEMINI_API_KEY", ""))


def needs_gemini_grounded_enrichment(results: list[ContactResult]) -> bool:
    """Return True when the current result set is still missing key contact data."""
    has_email = any(result.contact_type == "email" and (result.value or "").strip() for result in results)
    has_wa_phone = any(result.contact_type == "wa_phone" and (result.value or "").strip() for result in results)
    has_website = any(result.contact_type == "website" and (result.value or "").strip() for result in results)
    return not (has_email and has_wa_phone and has_website)


def _marketing_known_contact_summary(results: list[ContactResult]) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {
        "websites": [],
        "emails": [],
        "mobile_phones": [],
        "office_phones": [],
        "pic_names": [],
        "pic_titles": [],
    }
    seen: set[tuple[str, str]] = set()

    for result in results:
        value = (result.value or "").strip()
        if not value:
            continue
        key = (result.contact_type, value)
        if key in seen:
            continue
        seen.add(key)
        if result.contact_type == "website":
            summary["websites"].append(value)
        elif result.contact_type == "email":
            summary["emails"].append(value)
        elif result.contact_type == "wa_phone":
            summary["mobile_phones"].append(value)
        elif result.contact_type == "office_phone":
            summary["office_phones"].append(value)
        elif result.contact_type == "pic_name":
            summary["pic_names"].append(value)
        elif result.contact_type == "pic_title":
            summary["pic_titles"].append(value)

    for key, values in summary.items():
        summary[key] = values[:5]

    return summary


def _normalize_grounded_items(raw_items: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, str):
            value = item.strip()
            if value:
                normalized.append({"value": value})
            continue
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def _clamp_contact_confidence(value: Any, default: float, max_confidence: float = 1.0) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(confidence, max_confidence))


def _normalize_candidate_url(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    if not re.match(r"^https?://", candidate, re.IGNORECASE):
        candidate = f"https://{candidate.lstrip('/')}"
    parsed = urlparse(candidate)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme or 'https'}://{parsed.netloc}{parsed.path or ''}".rstrip("/")


def _select_grounded_source_url(candidate_url: str | None, grounded_urls: list[str]) -> str | None:
    explicit = _normalize_candidate_url(candidate_url)
    if explicit:
        return explicit

    return grounded_urls[0] if grounded_urls else None



def _build_gemini_grounded_prompt(
    client_name: str,
    extra_data: dict | None,
    known_results: list[ContactResult],
) -> str:
    known_summary = _marketing_known_contact_summary(known_results)
    missing_targets: list[str] = []
    if not known_summary["websites"]:
        missing_targets.append("official website")
    if not known_summary["emails"]:
        missing_targets.append("official email")
    if not known_summary["mobile_phones"]:
        missing_targets.append("mobile phone / WhatsApp number")

    condensed_extra_data = extra_data if isinstance(extra_data, dict) else {}

    return (
        f"Cari kontak publik resmi untuk perusahaan/organisasi berikut di Indonesia: {client_name}.\n\n"
        f"Prioritas gap yang belum terisi: {', '.join(missing_targets) if missing_targets else 'tidak ada gap utama, verifikasi jika ada sinyal yang lebih resmi'}.\n\n"
        "Konteks hasil pipeline yang SUDAH ditemukan:\n"
        f"{json.dumps(known_summary, ensure_ascii=False)}\n\n"
        "Konteks tambahan import/metadata klien:\n"
        f"{json.dumps(condensed_extra_data, ensure_ascii=False)}\n\n"
        "TUGAS:\n"
        "1. Temukan website resmi bila ada.\n"
        "2. Temukan email domain resmi.\n"
        "3. Temukan nomor HP/WhatsApp MOBILE Indonesia.\n"
        "4. Jika yang tersedia hanya telepon kantor/landline, taruh di office_phones.\n"
        "5. Jika ada PIC yang jelas terkait nomor/email, sertakan nama dan jabatannya.\n"
        "6. Prioritaskan kontak inti perusahaan. Hindari kontak event/campaign jika sudah ada kontak corporate yang lebih resmi.\n\n"
        "ATURAN KETAT:\n"
        "- Gunakan hanya fakta yang didukung Google Search grounding.\n"
        "- Jangan mengarang. Jika tidak yakin, jangan isi.\n"
        "- Prioritaskan domain resmi perusahaan, halaman kontak, regulator, atau berita kredibel yang menyebutkan kontak resmi.\n"
        "- Nomor mobile Indonesia harus format HP, bukan landline.\n"
        "- Jangan mengembalikan direktori broker/lead database sebagai sumber resmi.\n"
        "- supporting_url harus berupa satu URL publik yang mendukung item tersebut.\n"
        "- Batasi output: maksimal 1 official_websites, 2 emails, 2 mobile_phones, 2 office_phones, 2 contact_people.\n"
        "- Jika tidak ada data, pakai array kosong.\n"
        "- notes maksimal 1 kalimat singkat.\n\n"
        "BALAS HANYA JSON valid dengan schema berikut:\n"
        "{\n"
        '  "official_websites": [{"value": "https://...", "supporting_url": "https://...", "confidence": 0.0}],\n'
        '  "emails": [{"value": "info@example.com", "supporting_url": "https://...", "confidence": 0.0, "contact_name": "", "contact_title": ""}],\n'
        '  "mobile_phones": [{"value": "+628...", "supporting_url": "https://...", "confidence": 0.0, "contact_name": "", "contact_title": ""}],\n'
        '  "office_phones": [{"value": "+62 21 ...", "supporting_url": "https://...", "confidence": 0.0, "contact_name": "", "contact_title": ""}],\n'
        '  "contact_people": [{"name": "", "title": "", "supporting_url": "https://...", "confidence": 0.0}],\n'
        '  "notes": ""\n'
        "}"
    )


def _build_grounded_contact_results(
    payload: dict[str, Any],
    grounded_urls: list[str],
) -> list[ContactResult]:
    results: list[ContactResult] = []
    source_type = "gemini_grounded"

    for item in _normalize_grounded_items(payload.get("official_websites")):
        value = _normalize_candidate_url(str(item.get("value") or ""))
        if not value:
            continue
        source_url = _select_grounded_source_url(str(item.get("supporting_url") or value), grounded_urls)
        results.append(ContactResult(
            contact_type="website",
            value=value,
            source_url=source_url or value,
            source_type=source_type,
            confidence=_clamp_contact_confidence(item.get("confidence"), 0.7, max_confidence=0.8),
        ))

    for item in _normalize_grounded_items(payload.get("emails")):
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        source_url = _select_grounded_source_url(str(item.get("supporting_url") or ""), grounded_urls)
        results.append(ContactResult(
            contact_type="email",
            value=value,
            source_url=source_url,
            source_type=source_type,
            confidence=_clamp_contact_confidence(item.get("confidence"), 0.6, max_confidence=0.75),
        ))

    for item in _normalize_grounded_items(payload.get("mobile_phones")):
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        source_url = _select_grounded_source_url(str(item.get("supporting_url") or ""), grounded_urls)
        results.append(ContactResult(
            contact_type="wa_phone",
            value=value,
            source_url=source_url,
            source_type=source_type,
            confidence=_clamp_contact_confidence(item.get("confidence"), 0.65, max_confidence=0.75),
            pic_name=str(item.get("contact_name") or "").strip() or None,
        ))


    return _dedupe_results(results)


async def gemini_grounded_discovery(
    client_name: str,
    extra_data: dict | None,
    known_results: list[ContactResult],
) -> GeminiGroundedDiscoveryResult:
    """Run a Gemini grounded search pass to fill gaps after deterministic stages."""
    from orchestrator.research_agents.gemini_caller import call_gemini

    prompt = _build_gemini_grounded_prompt(client_name, extra_data, known_results)
    parsed, grounded_urls = await call_gemini(prompt, use_search_grounding=True)

    if not isinstance(parsed, dict):
        return GeminiGroundedDiscoveryResult(
            contacts=[],
            grounded_urls=grounded_urls,
            notes="Gemini grounded response was not a JSON object",
            unresolved_gaps=[],
            parse_failed=True,
        )

    parse_failed = bool(parsed.get("_parse_failed"))
    if parse_failed:
        return GeminiGroundedDiscoveryResult(
            contacts=[],
            grounded_urls=grounded_urls,
            notes="Gemini grounded response could not be parsed into the expected JSON schema",
            unresolved_gaps=[],
            parse_failed=True,
        )

    notes = str(parsed.get("notes") or "").strip() or None
    unresolved_gaps = [
        str(item).strip()
        for item in (parsed.get("unresolved_gaps") or [])
        if str(item).strip()
    ]
    contacts = _build_grounded_contact_results(parsed, grounded_urls)
    return GeminiGroundedDiscoveryResult(
        contacts=contacts,
        grounded_urls=grounded_urls,
        notes=notes,
        unresolved_gaps=unresolved_gaps,
        parse_failed=False,
    )


def _extract_jsonld_contacts(html: str, source_url: str) -> list[ContactResult]:
    """
    Feature D: Extract contacts from JSON-LD structured data (schema.org).
    Handles Organization, LocalBusiness, GovernmentOrganization, ContactPoint.
    Confidence 0.92 — data is self-declared by the website owner.
    """
    from bs4 import BeautifulSoup as _BS
    results: list[ContactResult] = []
    try:
        soup = _BS(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            items: list[dict] = data if isinstance(data, list) else [data]
            # Expand @graph
            expanded: list[dict] = []
            for item in items:
                if isinstance(item, dict) and "@graph" in item:
                    expanded.extend(item["@graph"])
                else:
                    expanded.append(item)

            for item in expanded:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("@type", ""))
                if not any(t in item_type for t in (
                    "Organization", "LocalBusiness", "GovernmentOrganization",
                    "NGO", "Corporation", "EducationalOrganization",
                )):
                    continue

                # Phone / fax
                for field in ("telephone", "faxNumber"):
                    raw = item.get(field) or ""
                    if not raw:
                        continue
                    normalized = _normalize_raw_phone(str(raw))
                    if normalized:
                        results.append(ContactResult(
                            contact_type="wa_phone",
                            value=normalized,
                            source_url=source_url,
                            source_type="schema_org",
                            confidence=0.92,
                        ))

                # Email
                if email := (item.get("email") or "").strip().lower():
                    if "@" in email:
                        results.append(ContactResult(
                            contact_type="email",
                            value=email,
                            source_url=source_url,
                            source_type="schema_org",
                            confidence=0.92,
                        ))

                # Website URL
                if url := (item.get("url") or "").strip():
                    if url.startswith("http"):
                        results.append(ContactResult(
                            contact_type="website",
                            value=url,
                            source_url=source_url,
                            source_type="schema_org",
                            confidence=0.95,
                        ))

                # ContactPoint nested objects
                contact_points = item.get("contactPoint") or []
                if isinstance(contact_points, dict):
                    contact_points = [contact_points]
                for cp in contact_points:
                    if not isinstance(cp, dict):
                        continue
                    for field in ("telephone", "faxNumber"):
                        raw = cp.get(field) or ""
                        if raw:
                            normalized = _normalize_raw_phone(str(raw))
                            if normalized:
                                results.append(ContactResult(
                                    contact_type="wa_phone",
                                    value=normalized,
                                    source_url=source_url,
                                    source_type="schema_org",
                                    confidence=0.90,
                                ))
                    if cp_email := (cp.get("email") or "").strip().lower():
                        if "@" in cp_email:
                            results.append(ContactResult(
                                contact_type="email",
                                value=cp_email,
                                source_url=source_url,
                                source_type="schema_org",
                                confidence=0.90,
                            ))
    except Exception as exc:
        log.debug("[JSON-LD] Parse failed for %s: %s", source_url[:60], exc)
    return results


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

    # Feature D: JSON-LD structured data (highest confidence, check first)
    results.extend(_extract_jsonld_contacts(html, source_url))

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

    for phone in _extract_office_phones_from_text(text):
        results.append(ContactResult(
            contact_type="office_phone",
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


async def website_discovery(
    client_name: str,
    extra_data: dict | None = None,
    avoid_domains: list[str] | None = None,
    refined_query: str | None = None,
    force_domain: str | None = None,
) -> list[ContactResult]:
    """Search for official website → extract emails and phones."""
    results: list[ContactResult] = []
    client_type: str | None = (extra_data or {}).get("client_type")

    # Build primary override query from refined_query / force_domain hints
    if refined_query:
        primary_query: str | None = refined_query
        if force_domain:
            primary_query = f"site:{force_domain} {refined_query}"
    elif force_domain:
        primary_query = f"site:{force_domain} {client_name}"
    else:
        primary_query = None  # use default auto-built queries

    # Run multi-query search (Google first, DDG fallback)
    queries = _build_website_search_queries(client_name, client_type)
    if primary_query:
        # Prepend the override query so it runs first; drop a duplicate if any
        queries = [primary_query] + [q for q in queries if q != primary_query]

    all_search_results: list[dict] = []
    seen_result_links: set[str] = set()
    for query in queries:
        for r in await web_search(query, max_results=5):
            link = (r.get("link") or "").strip()
            if link and link not in seen_result_links:
                seen_result_links.add(link)
                all_search_results.append(r)
        if len(all_search_results) >= 8:
            break

    # Filter out avoid_domains from search results
    if avoid_domains and all_search_results:
        filtered: list[dict] = []
        for result in all_search_results:
            url = result.get("link", "") or result.get("url", "") or ""
            if not any(domain in url for domain in avoid_domains):
                filtered.append(result)
        all_search_results = filtered

    if not all_search_results:
        return results

    # Extract contacts from search snippets (confidence 0.5 — no page visit needed)
    # Captures phone/email that appear directly in Google/DDG snippet text
    snippet_text = "\n".join(
        r.get("snippet") or ""
        for r in all_search_results
        if not _is_blocked_marketing_contact_source((r.get("link") or ""))
    )
    for email in extract_emails(snippet_text):
        results.append(ContactResult(
            contact_type="email",
            value=email,
            source_url="",
            source_type="web_snippet",
            confidence=0.5,
        ))
    for phone in filter_mobile_phones(extract_phones_from_text(snippet_text)):
        results.append(ContactResult(
            contact_type="wa_phone",
            value=phone,
            source_url="",
            source_type="web_snippet",
            confidence=0.5,
        ))

    # Build pages to fetch from official-looking domains
    pages_to_check: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for result in all_search_results:
        url = (result.get("link") or "").strip()
        if not url or not _is_likely_official_company_domain(client_name, url):
            continue
        canonical_roots = _canonical_company_page_roots(url)
        for index, base in enumerate(canonical_roots):
            source_type = "website" if index == 0 else "contact_page"
            if base not in seen_urls:
                seen_urls.add(base)
                pages_to_check.append((base, source_type))
            if index != 0 or urlparse(base).path.rstrip("/"):
                continue
            for path in _CONTACT_PAGE_PATHS:
                candidate = base + path
                if candidate not in seen_urls:
                    seen_urls.add(candidate)
                    pages_to_check.append((candidate, "contact_page"))

    if not pages_to_check:
        log.debug(
            "[Website Discovery] No official domain found for '%s' (client_type=%s). "
            "Returned %d snippet contacts.",
            client_name, client_type, len(results),
        )
        return _dedupe_results(results)

    # Record website URLs as contacts
    for url, source_type in pages_to_check:
        if source_type == "website":
            results.append(ContactResult(
                contact_type="website",
                value=url,
                source_url=url,
                source_type="official_website",
                confidence=0.9,
            ))

    # Fetch and extract from each page
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


def _build_ig_scrape_diagnostic(handle: str, diagnostics: dict | None = None) -> str:
    diagnostics = diagnostics or {}
    parts: list[str] = []

    if diagnostics.get("reason"):
        parts.append(str(diagnostics["reason"]))

    playwright_error = diagnostics.get("playwright_error")
    if playwright_error:
        parts.append(f"playwright={playwright_error}")

    session_error = diagnostics.get("session_error")
    if session_error:
        parts.append(f"ig_session={session_error}")
    elif diagnostics.get("session_configured") is False:
        parts.append("ig_session=no_sessions")

    if diagnostics.get("scrapingbot_configured") is False:
        parts.append("scrapingbot=not_configured")

    message = "; ".join(part for part in parts if part)
    if message:
        return message[:500]
    return f"No Instagram posts could be fetched for @{handle}"


async def _extract_marketing_contacts_from_posts(posts: list[dict]) -> list[ContactResult]:
    results: list[ContactResult] = []

    for post in posts:
        image_url = post.get("image_url", "")
        caption = post.get("caption", "")
        post_url = post.get("post_url", "")

        if image_url:
            try:
                phone_contacts = await extract_phone_from_image(
                    image_url,
                    caption,
                    require_person_name=False,
                )
                for phone_contact in phone_contacts:
                    results.append(ContactResult(
                        contact_type="wa_phone",
                        value=phone_contact["phone"],
                        source_url=post_url or image_url,
                        source_type="ig_post",
                        confidence=0.8,
                        pic_name=phone_contact.get("name"),
                    ))
            except Exception as exc:
                log.warning("[Marketing IG] Vision extract failed for %s: %s", image_url, exc)

        if caption:
            try:
                named_contacts = await extract_named_contacts_from_text(
                    caption,
                    require_person_name=False,
                )
                for named_contact in named_contacts:
                    results.append(ContactResult(
                        contact_type="wa_phone",
                        value=named_contact["phone"],
                        source_url=post_url,
                        source_type="ig_caption",
                        confidence=0.5,
                        pic_name=named_contact.get("name"),
                    ))
            except Exception as exc:
                log.warning("[Marketing IG] Caption extract failed: %s", exc)

    return _dedupe_results(results)


def _count_marketing_phones_found_by_post(
    posts: list[dict[str, Any]],
    contacts: list[ContactResult],
) -> dict[str, int]:
    """Count extracted IG phone contacts per stored post URL."""
    phones_by_post: dict[str, set[str]] = {
        str(post.get("post_url") or "").strip(): set()
        for post in posts
        if str(post.get("post_url") or "").strip()
    }
    image_to_post_url = {
        str(post.get("image_url") or "").strip(): str(post.get("post_url") or "").strip()
        for post in posts
        if str(post.get("image_url") or "").strip() and str(post.get("post_url") or "").strip()
    }

    for contact in contacts:
        if contact.contact_type != "wa_phone":
            continue

        source_url = str(contact.source_url or "").strip()
        if not source_url:
            continue

        normalized_phone = re.sub(r"\D", "", contact.value or "")
        if not normalized_phone:
            continue

        post_url = source_url
        if post_url not in phones_by_post:
            post_url = image_to_post_url.get(source_url, "")
        if not post_url or post_url not in phones_by_post:
            continue

        phones_by_post[post_url].add(normalized_phone)

    return {post_url: len(phones) for post_url, phones in phones_by_post.items()}


async def _replace_ig_contact_results_for_client(
    client_id: int,
    contacts: list[ContactResult],
) -> int:
    from . import groups as mkt

    await mkt.clear_client_contact_results_by_source_types(client_id, ["ig_post", "ig_caption"])

    inserted_contacts = 0
    for result in contacts:
        await mkt.upsert_contact_result(
            client_id=client_id,
            contact_type=result.contact_type,
            value=result.value,
            source_url=result.source_url,
            source_type=result.source_type,
            confidence=result.confidence,
            pic_name=result.pic_name if result.contact_type == "wa_phone" else None,
        )
        inserted_contacts += 1

    return inserted_contacts


def _scrape_instagram_posts_for_handles(handles: list[str], primary_handle: str | None = None) -> tuple[list[dict], str | None]:
    all_posts: list[dict] = []
    seen_post_urls: set[str] = set()
    diagnostics_by_handle: dict[str, str] = {}
    target_post_count = _MARKETING_MIN_POSTS_PER_CLIENT

    for handle in handles:
        clean_handle = (handle or "").strip()
        if not clean_handle:
            continue

        remaining_target = max(target_post_count - len(all_posts), 0)
        if remaining_target <= 0:
            break

        max_posts = remaining_target if clean_handle == primary_handle else max(remaining_target, 12)
        posts, diagnostics = scrape_ig_posts_with_fallback(
            clean_handle,
            max_posts,
            include_diagnostics=True,
        )
        if not posts:
            diag_reason = diagnostics.get("reason", "") or ""
            is_private = diagnostics.get("is_private", False) or "private" in diag_reason.lower()
            is_rate_limited = "rate" in diag_reason.lower() or "429" in diag_reason
            is_no_session = "session" in diag_reason.lower() or "no_session" in diag_reason
            if is_private:
                diagnostics_by_handle[clean_handle] = "account is private — cannot scrape"
            elif is_rate_limited:
                diagnostics_by_handle[clean_handle] = "rate limited — try again later"
            elif is_no_session:
                diagnostics_by_handle[clean_handle] = "no active IG session"
            elif diag_reason:
                diagnostics_by_handle[clean_handle] = _build_ig_scrape_diagnostic(clean_handle, diagnostics)

        for post in posts:
            post_url = post.get("post_url")
            if post_url and post_url in seen_post_urls:
                continue
            if post_url:
                seen_post_urls.add(post_url)
            post["ig_handle"] = clean_handle
            all_posts.append(post)

        if len(all_posts) >= target_post_count:
            break

    if all_posts:
        return all_posts, None

    if diagnostics_by_handle:
        return [], " | ".join(
            f"@{handle}: {message}" for handle, message in diagnostics_by_handle.items()
        )[:1000]

    return [], None


# ---------------------------------------------------------------------------
# Stage 2 — Instagram Discovery
# ---------------------------------------------------------------------------


async def ig_discovery(client_name: str, client_type: str = "") -> InstagramDiscoveryResult:
    """Find IG handle via DDG → scrape posts → GPT vision OCR."""
    results: list[ContactResult] = []

    candidates = await _evaluate_corporate_ig_candidates(client_name, client_type)

    # Collect WA contacts extracted from IG bios (done in _evaluate_corporate_ig_candidates)
    for candidate in candidates:
        for wa_contact in candidate.get("wa_contacts", []):
            results.append(wa_contact)

    selected_candidates = [candidate for candidate in candidates if candidate.get("is_selected")]
    primary_candidate = next((candidate for candidate in candidates if candidate.get("is_primary")), None)

    if not selected_candidates:
        # Return WA contacts found in bios even without selected IG candidates
        return InstagramDiscoveryResult(
            candidates=candidates,
            contacts=_dedupe_results(results),
            scrape_status="no_candidates",
            scrape_error="No corporate Instagram candidates passed event filter",
        )

    selected_handles = [candidate.get("handle") for candidate in selected_candidates if candidate.get("handle")]
    primary_handle = primary_candidate.get("handle") if primary_candidate else None
    loop = asyncio.get_running_loop()

    try:
        all_posts, scrape_error = await loop.run_in_executor(
            None,
            partial(_scrape_instagram_posts_for_handles, selected_handles, primary_handle),
        )
    except Exception as exc:
        log.warning("[Marketing IG Discovery] scrape batch failed for %s: %s", client_name, exc)
        return InstagramDiscoveryResult(
            handle=primary_handle,
            profile_url=primary_candidate.get("url") if primary_candidate else None,
            candidates=candidates,
            contacts=_dedupe_results(results),
            scrape_status="failed",
            scrape_error=str(exc) or type(exc).__name__,
        )

    if not all_posts:
        return InstagramDiscoveryResult(
            handle=primary_candidate.get("handle") if primary_candidate else None,
            profile_url=primary_candidate.get("url") if primary_candidate else None,
            candidates=candidates,
            contacts=_dedupe_results(results),
            scrape_status="empty",
            scrape_error=scrape_error,
        )
    post_results = await _extract_marketing_contacts_from_posts(all_posts)
    results.extend(post_results)

    return InstagramDiscoveryResult(
        handle=primary_candidate.get("handle") if primary_candidate else None,
        profile_url=primary_candidate.get("url") if primary_candidate else None,
        posts=all_posts,
        contacts=_dedupe_results(results),
        candidates=candidates,
        scrape_status="success",
        scrape_error=None,
    )


async def ig_handle_audit_discovery(client_name: str, client_type: str = "") -> InstagramDiscoveryResult:
    """Resolve and rank Instagram handles without scraping posts."""
    candidates = await _evaluate_corporate_ig_candidates(client_name, client_type)

    # Surface WA contacts extracted from bios
    wa_contacts: list[ContactResult] = []
    for candidate in candidates:
        wa_contacts.extend(candidate.get("wa_contacts", []))

    selected_candidates = [candidate for candidate in candidates if candidate.get("is_selected")]
    primary_candidate = next((candidate for candidate in candidates if candidate.get("is_primary")), None)

    if not selected_candidates:
        return InstagramDiscoveryResult(
            candidates=candidates,
            contacts=_dedupe_results(wa_contacts),
            scrape_status="not_found",
            scrape_error="No Instagram candidate matched strongly enough for audit persistence",
        )

    return InstagramDiscoveryResult(
        handle=primary_candidate.get("handle") if primary_candidate else None,
        profile_url=primary_candidate.get("url") if primary_candidate else None,
        candidates=candidates,
        contacts=_dedupe_results(wa_contacts),
        scrape_status="audit_only",
        scrape_error="Instagram post scrape skipped because website already produced the required contact set",
    )


async def retry_client_instagram_scrape(client_id: int) -> dict[str, Any]:
    """Retry Instagram post scraping for a single marketing client without rerunning the whole group."""
    from . import orchestration as mkt_orchestration

    return await mkt_orchestration.run_client_orchestration(
        client_id,
        mode="instagram_scrape_retry",
        trigger_type="manual",
    )


async def retry_client_instagram_contact_extraction(client_id: int) -> dict[str, Any]:
    """Re-extract contacts from already stored Instagram posts for one marketing client."""
    from . import orchestration as mkt_orchestration

    return await mkt_orchestration.run_client_orchestration(
        client_id,
        mode="instagram_contact_retry",
        trigger_type="manual",
    )


async def retry_client_search(client_id: int) -> dict[str, Any]:
    """Retry the full marketing search pipeline for a single client."""
    from . import orchestration as mkt_orchestration

    return await mkt_orchestration.run_client_orchestration(
        client_id,
        mode="full_search",
        trigger_type="manual",
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
        link = (r.get("link") or "").strip()
        if link and _is_blocked_marketing_contact_source(link):
            continue
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
        if _is_blocked_marketing_contact_source(link):
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
    sanitized_results: list[ContactResult] = []
    support_map: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for result in results:
        value = (result.value or "").strip()
        if not value:
            continue

        source_url = (result.source_url or "").strip()
        if source_url and _is_blocked_marketing_contact_source(source_url):
            continue

        if result.contact_type == "email" and _is_blocked_marketing_email(value):
            continue

        if result.contact_type == "wa_phone" and not is_mobile_phone(value):
            continue

        if value != result.value or source_url != (result.source_url or ""):
            normalized_result = ContactResult(
                contact_type=result.contact_type,
                value=value,
                source_url=source_url,
                source_type=result.source_type,
                confidence=result.confidence,
                pic_name=result.pic_name,
                pic_title=result.pic_title,
            )
        else:
            normalized_result = result

        sanitized_results.append(normalized_result)
        support_key = (normalized_result.contact_type, normalized_result.value)
        support_map.setdefault(support_key, set()).add(_contact_source_signature(normalized_result))

    seen: set[tuple[str, str]] = set()
    deduped: list[ContactResult] = []
    for r in sanitized_results:
        key = (r.contact_type, r.value)
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    trusted_types = {
        result.contact_type
        for result in deduped
        if _contact_source_trust(result) >= 3
    }

    trust_filtered: list[ContactResult] = []
    for result in deduped:
        trust = _contact_source_trust(result)
        support_key = (result.contact_type, result.value)
        support_count = len(support_map.get(support_key, set()))

        if trust == 0:
            continue

        if trust < 3 and result.contact_type in trusted_types:
            continue

        if trust == 1 and support_count < 2:
            continue

        trust_filtered.append(result)

    email_results = [result for result in trust_filtered if result.contact_type == "email" and result.value]
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
        return trust_filtered

    return [
        result for result in trust_filtered
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
    """Legacy compatibility wrapper; route all single-client searches through orchestration."""
    from . import orchestration as mkt_orchestration

    async with _search_semaphore:
        await update_fn(client_id, "searching")
        try:
            await mkt_orchestration.run_client_orchestration(
                client_id,
                mode="full_search",
                trigger_type="legacy_wrapper",
            )
        except Exception as e:
            error_msg = str(e) or type(e).__name__
            log.warning(f"[Marketing Search] Client {client_id} ({client_name}) failed: {error_msg}")
            from . import groups as mkt
            await mkt.update_client_error_message(client_id, error_msg)


async def process_search_queue(group_id: int) -> None:
    """Process all pending clients in a group with concurrency control."""
    from . import orchestration as mkt_orchestration

    await mkt_orchestration.process_group_orchestration_queue(group_id, trigger_type="scheduler")
