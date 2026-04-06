"""
Association (Asosiasi) discovery module.

Discovers contacts for business and industry associations in Indonesia.
Known targets: KADIN, Apindo, GAPMMI, HIPMI, sector-specific associations.

Each association typically has a sekretariat with:
  - sekretariat email (info@, sekretariat@)
  - office landline phone
  - WhatsApp URL
  - PIC name/title
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
# Known association URLs to probe
# ---------------------------------------------------------------------------

# Key national associations — confirmed accessible
_KNOWN_ASSOCIATIONS: list[dict[str, str]] = [
    {
        "name": "Apindo",
        "base_url": "https://apindo.or.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat", "/kontak-kami", "/"],
    },
    {
        "name": "KADIN Indonesia",
        "base_url": "https://kadin.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat", "/kontak-kami", "/"],
    },
    {
        "name": "GAPMMI",
        "base_url": "https://gapmmi.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat", "/kontak-kami", "/"],
    },
    {
        "name": "HIPMI",
        "base_url": "https://hipmi.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat", "/kontak-kami", "/"],
    },
    {
        "name": "KADIN Jakarta",
        "base_url": "https://kadinjakarta.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat", "/kontak-kami", "/"],
    },
]

# Regional KADIN pattern (province-level subdomains)
_KADIN_PROVINCES = [
    "jatim", "jateng", "jabar", "sumut", "sulsel",
    "bali", "ntb", "ntt", "sumsel", "lampung",
    "kalsel", "kaltim", "papua", "diy",
]
_KADIN_REGIONAL_BASES = [
    f"https://kadin{j}.id" for j in _KADIN_PROVINCES
]

# Sector keyword → association mappings
_SECTOR_ASSOCIATIONS: list[dict[str, Any]] = [
    {
        "keywords": ["makanan", "food", "pangan", " GAPMMI", "manufacture"],
        "base_url": "https://gapmmi.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat"],
        "name": "GAPMMI",
    },
    {
        "keywords": ["bahan kimia", "chemical", "kimia", "炼油"],
        "base_url": "https://apki.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat"],
        "name": "APKI",
    },
    {
        "keywords": ["farmasi", "pharma", "obat", "obat-obatan"],
        "base_url": "https://gpfarmacia.org",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat"],
        "name": "GP Farmacia",
    },
    {
        "keywords": ["garmen", "tekstil", "textile", "apparel", "konveksi"],
        "base_url": "https://apindo.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat"],
        "name": "Apindo (Tekstil)",
    },
    {
        "keywords": ["kopi", "coffee", "sawit", "cokelat", "cocoa", "kelapa"],
        "base_url": "https://gapki.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat"],
        "name": "GAPKI",
    },
    {
        "keywords": ["tourism", "wisata", "hotel", "perhotelan", "travel"],
        "base_url": "https://hotelierindonesia.com",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat"],
        "name": "PHRI",
    },
    {
        "keywords": ["otomotif", "automotive", "mobil", "motor"],
        "base_url": "https://gaiki.net",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat"],
        "name": "GAIKINDO",
    },
    {
        "keywords": ["digital", "teknologi", "teknologi informasi", "software", "startup", "IT"],
        "base_url": "https://apjii.or.id",
        "contact_paths": ["/kontak", "/tentang", "/sekretariat"],
        "name": "APJII",
    },
]

# Contact page path variants
_GENERIC_CONTACT_PATHS = [
    "/kontak",
    "/kontak-kami",
    "/tentang",
    "/sekretariat",
    "/kontak-kami.html",
    "/kontak.html",
    "/",
]


def _build_contact_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    return f"{base}{path}"


async def _probe_page(
    url: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Fetch a page and extract all contact data."""
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
        r"https?://(?:wa\.me|chat\.whatsapp\.com|whatsapp\.com/[dl])/[^\s\"'<>]+",
        r"https?://api\.whatsapp\.com/send[^\s\"'<>]+",
    ]
    for p in wa_patterns:
        wa_urls.extend(re.findall(p, html, re.IGNORECASE))

    if social.get("instagram"):
        wa_urls.extend(social["instagram"])

    # Extract PIC from structured HTML (look for table rows or definition lists)
    pic_name: str | None = None
    pic_title: str | None = None

    # Pattern 1: look for table rows where email is mentioned
    for row in soup.select("tr, li, p"):
        row_text = row.get_text(strip=True)
        if any("@" in row_text for _ in emails):
            # Try to extract name from this row
            name_match = re.search(
                r"(?:Penanggung\s*Jawab|PIC|Ketua|Sekretaris|Direktur)[:\s]+"
                r"([A-Z][a-zà-ú]+(?:\s+[A-Z][a-zà-ú]+){0,4})",
                row_text,
            )
            if name_match and not pic_name:
                pic_name = name_match.group(1).strip()
            title_match = re.search(
                r"(?:Jabatan|Department|Bagian)[:\s]+([A-Za-z\s,]+?)(?:\d|\@|$)",
                row_text,
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


def _score_association_match(client_name: str, assoc: dict[str, str]) -> float:
    """Return a match score 0-1 for how well client_name matches this association."""
    name = (assoc.get("name") or "").lower()
    client_lower = client_name.lower()

    # Exact substring
    if client_lower in name or name in client_lower:
        return 1.0
    # Partial word match
    name_words = set(name.split())
    client_words = set(client_lower.split())
    overlap = name_words & client_words
    if overlap and max(len(name_words), len(client_words)) > 0:
        return len(overlap) / max(len(name_words), len(client_words))
    return 0.0


async def _scrape_association(
    assoc: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> list[ContactResult]:
    """Scrape all contact pages for one association."""
    base = assoc["base_url"]
    paths = assoc.get("contact_paths", _GENERIC_CONTACT_PATHS)
    assoc_name = assoc.get("name", base)

    urls = [_build_contact_url(base, p) for p in paths]
    # Deduplicate
    seen: set[str] = set()
    unique_urls: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    pages = await asyncio.gather(
        *[_probe_page(u, semaphore) for u in unique_urls],
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
                    source_type="asosiasi",
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
                    source_type="asosiasi",
                    confidence=0.9,
                ))

        for wa_url in page.get("wa_urls", []):
            results.append(ContactResult(
                contact_type="wa_url",
                value=wa_url,
                source_url=url,
                source_type="asosiasi",
                confidence=0.85,
            ))

    log.debug("[Asosiasi] Scraped %s — found %d contacts", assoc_name, len(results))
    return results


async def asosiasi_discovery(client_name: str) -> list[ContactResult]:
    """
    Discover contacts for business/industry associations.

    Known associations: KADIN, Apindo, GAPMMI, HIPMI, sector-specific.

    Sources:
      - apindo.or.id/kontak
      - kadin.id
      - Regional KADIN: kadin{province}.id pattern
      - Sector associations based on client_name keywords
    """
    semaphore = asyncio.Semaphore(5)
    results: list[ContactResult] = []

    # Step 1: DDG search for association matching client_name
    ddg_results = await ddg_search(
        f'"{client_name}" asosiasi indonesia kontak OR sekretariat',
        max_results=5,
    )

    ddg_associations: list[dict[str, str]] = []
    for r in ddg_results:
        link = r.get("link", "")
        snippet = r.get("snippet", "")
        title = r.get("title", "")
        # Only accept association-type URLs
        if any(
            kw in link.lower() or kw in title.lower() or kw in snippet.lower()
            for kw in ["asosiasi", "kadin", "apindo", "gapmmi", "hipmi", "org.id", "or.id"]
        ):
            # Extract base URL
            from urllib.parse import urlparse
            try:
                netloc = urlparse(link).netloc
                if netloc:
                    base = f"https://{netloc}"
                    ddg_associations.append({
                        "name": title or netloc,
                        "base_url": base,
                        "contact_paths": _GENERIC_CONTACT_PATHS,
                    })
            except Exception:
                pass

    # Step 2: Add known associations that match client_name keywords
    matched_known: list[dict[str, Any]] = []
    client_lower = client_name.lower()

    # Direct keyword match in sector associations
    for sec in _SECTOR_ASSOCIATIONS:
        for kw in sec.get("keywords", []):
            if kw.lower() in client_lower:
                matched_known.append(sec)
                break

    # Direct name match in known national associations
    for assoc in _KNOWN_ASSOCIATIONS:
        if _score_association_match(client_name, assoc) >= 0.4:
            matched_known.append(assoc)

    # Regional KADIN if client mentions a province
    for prov in _KADIN_PROVINCES:
        if prov in client_lower:
            matched_known.append({
                "name": f"KADIN {prov.title()}",
                "base_url": f"https://kadin{prov}.id",
                "contact_paths": _GENERIC_CONTACT_PATHS,
            })
            break

    # Deduplicate by base_url
    seen_bases: set[str] = set()
    all_target_assocs: list[dict[str, Any]] = []
    for assoc in ddg_associations + matched_known:
        base = assoc.get("base_url", "")
        if base and base not in seen_bases:
            seen_bases.add(base)
            all_target_assocs.append(assoc)

    # Step 3: Scrape all matched associations
    if all_target_assocs:
        tasks = [_scrape_association(a, semaphore) for a in all_target_assocs]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for gathered_results in gathered:
            if isinstance(gathered_results, list):
                results.extend(gathered_results)

    # Step 4: Always probe known national associations as fallback (high value sources)
    if len(results) < 2:
        tasks = [_scrape_association(a, semaphore) for a in _KNOWN_ASSOCIATIONS]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for gathered_results in gathered:
            if isinstance(gathered_results, list):
                results.extend(gathered_results)

    log.debug("[Asosiasi] asosiasi_discovery('%s') found %d contacts", client_name, len(results))
    return _dedupe_asosiasi_results(results)


def _dedupe_asosiasi_results(results: list[ContactResult]) -> list[ContactResult]:
    """Deduplicate by (contact_type, value)."""
    seen: set[tuple[str, str]] = set()
    deduped: list[ContactResult] = []
    for r in results:
        key = (r.contact_type, r.value.lower())
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped
