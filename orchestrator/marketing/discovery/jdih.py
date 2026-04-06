"""
JDIH (Jaringan Dokumentasi dan Informasi Hukum) discovery module.

Probes government institution contact pages under the JDIH network
(jdihn.go.id aggregates 100+ institutions) and the main domain's
kontak/kontak-kami/tentang/sekretariat pages.
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
)


# ---------------------------------------------------------------------------
# Known JDIH institution domains to probe
# ---------------------------------------------------------------------------

_JDIH_INSTITUTIONS: list[tuple[str, str]] = [
    # (jdih_domain, "Lembaga Name")
    ("jdihn.go.id", "JDIHN Utama"),
    ("jdih.kemenkum.go.id", "Kementerian Hukum dan HAM"),
    ("jdih.kemnaker.go.id", "Kementerian Ketenagakerjaan"),
    ("jdih.kemenkop.go.id", "Kementerian Koprasi"),
    ("jdih.bnpt.go.id", "BNPT"),
    ("jdih.lpsk.go.id", "LPSK"),
    ("jdih.pom.go.id", "BPOM"),
    ("jdih.kemdikbud.go.id", "Kementerian Pendidikan"),
]

# Known government institution main domains (probed alongside JDIH)
_MAIN_DOMAINS: list[tuple[str, str]] = [
    ("kemenkum.go.id", "Kementerian Hukum dan HAM"),
    ("kemnaker.go.id", "Kementerian Ketenagakerjaan"),
    ("kemenkop.go.id", "Kementerian Koprasi"),
    ("bnpt.go.id", "BNPT"),
    ("lpsk.go.id", "LPSK"),
    ("bpom.go.id", "BPOM"),
    ("kemdikbud.go.id", "Kemdikbud"),
]

# Contact page path variants
_CONTACT_PATHS = [
    "/kontak",
    "/kontak-kami",
    "/tentang",
    "/sekretariat",
    "/kontak-kami.html",
    "/kontak.html",
]


def _build_jdih_url(domain: str) -> str:
    return f"https://{domain}"


def _build_contact_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    return f"{base}{path}"


async def _probe_contact_page(
    url: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Fetch a contact page and extract all contact data. Returns a dict."""
    async with semaphore:
        html = await fetch_page(url)
        if not html:
            return {}

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    emails = extract_emails(text)
    phones = extract_phones_from_text(text)
    social = extract_social_links(html)

    # Look for WA/WhatsApp links
    wa_urls: list[str] = []
    wa_patterns = [
        r"https?://(?:wa\.me|chat\.whatsapp\.com|whatsapp\.com/[dl])/[^\s\"'<>]+",
        r"https?://api\.whatsapp\.com/send[^\s\"'<>]+",
    ]
    for p in wa_patterns:
        wa_urls.extend(re.findall(p, html, re.IGNORECASE))
    if "instagram" in social:
        wa_urls.extend(social["instagram"])

    # Try to extract PIC name/title near email or phone entries
    pic_name: str | None = None
    pic_title: str | None = None
    email_header_texts = []
    for email in emails[:3]:
        # Find the paragraph/section containing this email in HTML
        for tag in soup.find_all(string=re.compile(re.escape(email.split("@")[0]), re.IGNORECASE)):
            parent = tag.find_parent()
            if parent:
                email_header_texts.append(parent.get_text(strip=True))

    if email_header_texts:
        combined = " ".join(email_header_texts)
        # Simple heuristic: look for "Nama" or "Penanggung Jawab" labels
        name_match = re.search(r"(?:Penanggung\s*Jawab|Nama\s*(?:PIC|Kontak)|Ditangani\s*oleh)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})", combined)
        if name_match:
            pic_name = name_match.group(1).strip()
        title_match = re.search(r"(?:Jabatan|Posisi|Department)[:\s]+([A-Za-z\s]+)", combined)
        if title_match:
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


def _extract_name_from_jdih_result(client_name: str, domain_label: str | None) -> str | None:
    """Try to match a government institution name from client_name."""
    if not domain_label:
        return None
    # If client_name is a close match to the label, return the label
    if client_name.lower() in domain_label.lower() or domain_label.lower() in client_name.lower():
        return domain_label
    return None


async def _scrape_institution(
    client_name: str,
    jdih_domain: str,
    lembaga: str,
    semaphore: asyncio.Semaphore,
) -> list[ContactResult]:
    """Scrape all contact paths for one JDIH institution."""
    results: list[ContactResult] = []
    base_jdih = _build_jdih_url(jdih_domain)

    # Probe JDIH contact pages
    jdih_urls = [base_jdih] + [_build_contact_url(base_jdih, p) for p in _CONTACT_PATHS]

    # Also probe main domain if we have a mapping
    main_domain = jdih_domain.replace("jdih.", "")
    if main_domain != jdih_domain:  # was actually a jdih subdomain
        main_base = f"https://{main_domain}"
        main_urls = [main_base] + [_build_contact_url(main_base, p) for p in _CONTACT_PATHS]
    else:
        main_urls = []

    all_urls = jdih_urls + main_urls

    # Deduplicate
    seen_urls: set[str] = set()
    unique_urls: list[str] = []
    for u in all_urls:
        if u not in seen_urls:
            seen_urls.add(u)
            unique_urls.append(u)

    # Probe all in parallel (limited by semaphore)
    pages = await asyncio.gather(
        *[_probe_contact_page(u, semaphore) for u in unique_urls],
        return_exceptions=True,
    )

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
                    source_type="jdih",
                    confidence=0.9,
                    pic_name=page.get("pic_name"),
                    pic_title=page.get("pic_title"),
                ))

        for phone in page.get("phones", []):
            clean = re.sub(r"\D", "", phone)
            if clean not in seen_phones:
                seen_phones.add(clean)
                contact_type = "wa_phone" if len(clean) >= 10 and clean.startswith(("08", "+628", "628")) else "office_phone"
                results.append(ContactResult(
                    contact_type=contact_type,
                    value=phone,
                    source_url=url,
                    source_type="jdih",
                    confidence=0.9,
                ))

        for wa_url in page.get("wa_urls", []):
            results.append(ContactResult(
                contact_type="wa_url",
                value=wa_url,
                source_url=url,
                source_type="jdih",
                confidence=0.85,
            ))

    return results


async def jdih_discovery(client_name: str) -> list[ContactResult]:
    """
    Scrape government institution contacts via JDIH (Jaringan Dokumentasi
    dan Informasi Hukum) network.

    JDIH network: jdihn.go.id aggregates 100+ government institutions.
    Each institution has: jdih.{lembaga}.go.id

    For each institution matching client_name:
      1. Probe jdih.{domain}.go.id/kontak
      2. Also probe main domain /kontak-kami, /tentang, /sekretariat
      3. Extract: email, phone (Indonesian), WA URL, PIC name
    """
    semaphore = asyncio.Semaphore(5)
    results: list[ContactResult] = []

    # Step 1: DDG search for JDIH URL matching client_name
    ddg_results = await ddg_search(
        f'"{client_name}" JDIH site:go.id',
        max_results=5,
    )

    found_jdih_urls: list[tuple[str, str]] = []  # (url, label)

    for r in ddg_results:
        link = r.get("link", "")
        if "go.id" in link and ("jdih" in link.lower() or "jdi" in link.lower()):
            found_jdih_urls.append((link, r.get("title", "")))

    # Step 2: Also try direct JDIH subdomain pattern from known institutions
    # that partially match client_name
    client_lower = client_name.lower()
    for domain, label in _JDIH_INSTITUTIONS:
        if (
            client_lower in label.lower()
            or label.lower().split()[0] in client_lower
            or any(word in client_lower for word in label.lower().split()[:2])
        ):
            found_jdih_urls.append((f"https://{domain}", label))

    # Probe found JDIH URLs first (highest relevance)
    if found_jdih_urls:
        tasks = [
            _scrape_institution(client_name, _url_to_domain(url), label, semaphore)
            for url, label in found_jdih_urls
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for gathered_results in gathered:
            if isinstance(gathered_results, list):
                results.extend(gathered_results)

    # Step 3: Probe all known JDIH institutions broadly (catch-all pass)
    # Only if we didn't find much
    if len(results) < 2:
        all_tasks = [
            _scrape_institution(client_name, domain, label, semaphore)
            for domain, label in _JDIH_INSTITUTIONS
        ]
        gathered = await asyncio.gather(*all_tasks, return_exceptions=True)
        for gathered_results in gathered:
            if isinstance(gathered_results, list):
                results.extend(gathered_results)

    log.debug("[JDIH] jdih_discovery('%s') found %d contacts", client_name, len(results))
    return _dedupe_jdih_results(results)


def _url_to_domain(url: str) -> str:
    """Extract hostname from URL."""
    from urllib.parse import urlparse
    try:
        return urlparse(url).netloc
    except Exception:
        return url


def _dedupe_jdih_results(results: list[ContactResult]) -> list[ContactResult]:
    """Deduplicate by (contact_type, value)."""
    seen: set[tuple[str, str]] = set()
    deduped: list[ContactResult] = []
    for r in results:
        key = (r.contact_type, r.value.lower())
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped
