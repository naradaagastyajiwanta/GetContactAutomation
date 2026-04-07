"""
LKIP (Laporan Kinerja Instansi Pemerintah) Discovery for Dinas clients.

Searches for LKIP documents and government portal pages for contact
information (names, emails, phones, addresses).

Used when client_type == "dinas" (government agency / Dinas Daerah).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from bs4 import BeautifulSoup

from orchestrator.config import log
from orchestrator.marketing.search import ContactResult
from orchestrator.osint.tools import (
    ddg_search,
    fetch_page,
    extract_emails,
    extract_phones_from_text,
    extract_social_links,
    extract_text_from_html,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Common contact page paths on government (PEMDA) sites
_GOV_CONTACT_PATHS = [
    "/kontak",
    "/hubungi-kami",
    "/sekretariat",
    "/struktur-organisasi",
    "/tentang",
    "/",
]

# LKIP / performance report document path variants
_LKIP_PATHS = [
    "/lkip",
    "/lkip-2023",
    "/lkip-2024",
    "/lkip-2025",
    "/laporan-kinerja",
    "/lkjip",
    "/performance-report",
]

# Government portal path patterns
_GOV_PORTAL_PATHS = [
    "/portal",
    "/sitemap",
    "/staff",
    "/pegawai",
]


def _build_urls(base: str, paths: list[str]) -> list[str]:
    base = base.rstrip("/")
    return [f"{base}{p}" for p in paths]


def _is_valid_url(url: str) -> bool:
    return bool(url and url.startswith("http"))


async def _probe_gov_page(url: str, semaphore: asyncio.Semaphore) -> dict[str, Any]:
    """Fetch a government page and extract all contact data."""
    async with semaphore:
        html = await fetch_page(url)
        if not html:
            return {}

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    emails = extract_emails(text)
    phones = extract_phones_from_text(text)
    social = extract_social_links(html)

    # WA-specific links
    wa_urls: list[str] = []
    wa_patterns = [
        r"https?://wa\.me/\d+",
        r"https?://api\.whatsapp\.com/send[^\s\"'<>]+",
    ]
    for p in wa_patterns:
        wa_urls.extend(re.findall(p, html, re.IGNORECASE))

    for ig_urls in social.get("instagram", []):
        wa_urls.append(ig_urls)

    # Extract PIC — government agencies often list struktur organisasi / SK
    pic_name: str | None = None
    pic_title: str | None = None

    for el in soup.select("tr, li, p, div, span"):
        el_text = el.get_text(strip=True)
        if not el_text or len(el_text) > 300:
            continue
        if "@" not in el_text and not phones:
            continue

        # Try to extract PIC / kepala Dinas / sekretaris name
        name_match = re.search(
            r"(?:Kepala\s*Dinas| Sekretaris\s*Dinas| "
            r"Koordinator|Penanggung\s*Jawab|PIC|"
            r"Ketua\s*Panitia|Anggota)[:\s]+"
            r"([A-Z][a-zA-Zà-ú]+(?:\s+[A-Z][a-zA-Zà-ú]+){0,4})",
            el_text,
        )
        if name_match and not pic_name:
            pic_name = name_match.group(1).strip()

        title_match = re.search(
            r"(?:Jabatan|Bagian|Subagian|Bidang|Seksi)[:\s]+([A-Za-z\s,]+?)(?:\d|\@|$)",
            el_text,
        )
        if title_match and not pic_title:
            pic_title = title_match.group(1).strip()

    return {
        "url": url,
        "emails": emails,
        "phones": phones,
        "wa_urls": list(set(wa_urls)),
        "social": social,
        "pic_name": pic_name,
        "pic_title": pic_title,
    }


async def _scrape_gov_site(base_url: str, semaphore: asyncio.Semaphore) -> list[ContactResult]:
    """Scrape all relevant pages on a government site domain."""
    all_paths = _GOV_CONTACT_PATHS + _LKIP_PATHS
    all_urls = _build_urls(base_url, all_paths)
    # Deduplicate
    all_urls = list({u: 1 for u in all_urls}.keys())

    pages = await asyncio.gather(
        *[_probe_gov_page(u, semaphore) for u in all_urls],
        return_exceptions=True,
    )

    results: list[ContactResult] = []
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()

    for page in pages:
        if not isinstance(page, dict) or not page:
            continue
        url = page.get("url", "")

        for email in page.get("emails", []):
            if email.lower() not in seen_emails:
                seen_emails.add(email.lower())
                results.append(ContactResult(
                    contact_type="email",
                    value=email,
                    source_url=url,
                    source_type="lkip",
                    confidence=0.9,
                    pic_name=page.get("pic_name"),
                    pic_title=page.get("pic_title"),
                ))

        for phone in page.get("phones", []):
            clean = re.sub(r"\D", "", phone)
            if clean not in seen_phones:
                seen_phones.add(clean)
                contact_type = (
                    "wa_phone"
                    if len(clean) >= 10 and clean.startswith(("08", "+628", "628"))
                    else "office_phone"
                )
                results.append(ContactResult(
                    contact_type=contact_type,
                    value=phone,
                    source_url=url,
                    source_type="lkip",
                    confidence=0.9,
                ))

        for wa_url in page.get("wa_urls", []):
            results.append(ContactResult(
                contact_type="wa_url",
                value=wa_url,
                source_url=url,
                source_type="lkip",
                confidence=0.85,
            ))

    return results


async def _scrape_lkip_doc_url(doc_url: str, semaphore: asyncio.Semaphore) -> list[ContactResult]:
    """Fetch an LKIP document page and extract contacts from it."""
    async with semaphore:
        html = await fetch_page(doc_url)
        if not html:
            return []

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    emails = extract_emails(text)
    phones = extract_phones_from_text(text)

    results: list[ContactResult] = []
    for email in emails:
        results.append(ContactResult(
            contact_type="email",
            value=email,
            source_url=doc_url,
            source_type="lkip_doc",
            confidence=0.85,
        ))
    for phone in phones:
        results.append(ContactResult(
            contact_type="office_phone",
            value=phone,
            source_url=doc_url,
            source_type="lkip_doc",
            confidence=0.85,
        ))

    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def lkip_discovery(client_name: str) -> list[ContactResult]:
    """
    Discover contacts for a Dinas/government agency via LKIP documents
    and government portal pages.

    Strategy:
      1. DDG search for LKIP pages, government portal pages for the client.
      2. Also search for direct LKIP PDF/HTML documents.
      3. For each discovered URL, scrape contact pages concurrently.
      4. Extract emails, phones, WA links, and PIC names.

    Args:
        client_name: Name of the Dinas client (e.g. "Dinas Pendidikan Kota Surabaya").

    Returns:
        List of ContactResult found from LKIP and government portal sources.
    """
    if not client_name or not client_name.strip():
        return []

    semaphore = asyncio.Semaphore(5)
    results: list[ContactResult] = []

    # Step 1: DDG search for LKIP documents and government portal pages
    search_queries = [
        f'"{client_name}" LKIP kontak email telepon sekretariat',
        f'"{client_name}" "laporan kinerja" kontak email',
        f'site:gov.id "{client_name}" kontak OR sekretariat',
        f'"{client_name}" "lkip" OR "lkjiip" 2024 2025 contact email',
        f'"{client_name}" dinas kontak email telepon',
    ]

    discovered_urls: list[str] = []

    for query in search_queries:
        ddg_results = await ddg_search(query, max_results=5)
        for r in ddg_results:
            link = r.get("link", "")
            if _is_valid_url(link):
                # Normalise: strip query params and trailing slash
                normalized = link.split("?")[0].rstrip("/")
                if normalized not in discovered_urls:
                    discovered_urls.append(normalized)

    if not discovered_urls:
        log.debug("[LKIP] No LKIP/government pages found for '%s'", client_name)
        return []

    log.debug(
        "[LKIP] Found %d candidate LKIP/government pages for '%s': %s",
        len(discovered_urls),
        client_name,
        discovered_urls[:3],
    )

    # Step 2: Scrape all discovered URLs
    scrape_tasks = [_scrape_gov_site(url, semaphore) for url in discovered_urls]
    gathered = await asyncio.gather(*scrape_tasks, return_exceptions=True)
    for gathered_results in gathered:
        if isinstance(gathered_results, list):
            results.extend(gathered_results)

    # Step 3: Also probe common LKIP/document paths on each discovered domain
    doc_tasks = [
        _scrape_lkip_doc_url(url, semaphore)
        for url in discovered_urls
    ]
    doc_gathered = await asyncio.gather(*doc_tasks, return_exceptions=True)
    for gathered_results in doc_gathered:
        if isinstance(gathered_results, list):
            results.extend(gathered_results)

    log.debug(
        "[LKIP] lkip_discovery('%s') found %d contacts",
        client_name,
        len(results),
    )
    return _dedupe_results(results)


def _dedupe_results(results: list[ContactResult]) -> list[ContactResult]:
    """Deduplicate by (contact_type, value)."""
    seen: set[tuple[str, str]] = set()
    deduped: list[ContactResult] = []
    for r in results:
        key = (r.contact_type, r.value.lower())
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped
