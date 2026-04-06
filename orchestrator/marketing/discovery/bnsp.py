"""
BNSP LSP discovery module.

Scrapes the official BNSP (Badan Nasional Sertifikasi Profesi) LSP directory
at https://bnsp.go.id/lsp to find Lembaga Sertifikasi Profesi (LSP) entries
matching a given client name, then extracts contact details from their websites.
"""

from __future__ import annotations

import asyncio
import re
from typing import NamedTuple

import httpx
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
# Types
# ---------------------------------------------------------------------------


class LSPEntry(NamedTuple):
    name: str
    registration_number: str
    status: str  # "Aktif" or "Tidak Aktif"
    city: str
    province: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BNSP_BASE = "https://bnsp.go.id"
BNSP_LSP_LIST_URL = f"{BNSP_BASE}/lsp"

# BNSP HQ fallback contacts
BNSP_HQ_EMAIL = "admin@bnsp.go.id"
BNSP_HQ_OFFICE_PHONE = "021-26966525"
BNSP_HQ_WA_PHONE = "081288887014"


async def _fetch_bnsp_page(page: int) -> str | None:
    """Fetch a single page of the BNSP LSP list."""
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
            },
        ) as client:
            # Try pagination via query param; many Indonesian gov sites use ?page= or ?hal=
            url = f"{BNSP_LSP_LIST_URL}?page={page}"
            resp = await client.get(url)
            if resp.status_code == 404:
                # Fallback: try /hal= style pagination
                url = f"{BNSP_LSP_LIST_URL}?hal={page}"
                resp = await client.get(url)
            if resp.status_code == 200:
                return resp.text
            log.debug("[BNSP] Page %d returned HTTP %d", page, resp.status_code)
            return None
    except Exception as e:
        log.debug("[BNSP] Failed to fetch page %d: %s", page, e)
        return None


def _parse_lsp_entries(html: str) -> list[LSPEntry]:
    """Parse LSP entries from the BNSP LSP list HTML."""
    soup = BeautifulSoup(html, "html.parser")
    entries: list[LSPEntry] = []

    # Strategy 1: look for a table with LSP data
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            # Build entry from table cells
            name = cells[0].get_text(strip=True)
            reg_num = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            status = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            city = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            province = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            if name and "LSP" in name.upper():
                entries.append(LSPEntry(name=name, registration_number=reg_num,
                                        status=status, city=city, province=province))

    # Strategy 2: look for card/list items with data attributes or CSS classes
    if not entries:
        for el in soup.find_all(["div", "li"],
                                 class_=re.compile(r"lsp|item|list|card", re.I)):
            name_tag = el.find(re.compile(r"h[1-6]|strong|span|b"), class_=re.compile(r"name|title", re.I))
            if not name_tag:
                continue
            name = name_tag.get_text(strip=True)
            if not name or "LSP" not in name.upper():
                continue
            text = el.get_text(separator=" ", strip=True)
            # Extract registration number
            reg_match = re.search(r"(BNSP-?LSP-?\d+-?ID)", text, re.I)
            reg_num = reg_match.group(1) if reg_match else ""
            # Extract status
            status_match = re.search(r"\b(Aktif|Tidak Aktif)\b", text)
            status = status_match.group(1) if status_match else ""
            # Extract city/province
            city_match = re.search(r"Kota\s+(\w+)|Kab\.\s+(\w+)", text)
            province_match = re.search(r"Prov\.\s+(\w+)|Provinsi\s+(\w+)", text)
            city = city_match.group(1) if city_match else ""
            province = province_match.group(1) if province_match else ""
            entries.append(LSPEntry(name=name, registration_number=reg_num,
                                    status=status, city=city, province=province))

    # Strategy 3: raw text extraction for gov sites that embed data in JSON or hidden fields
    if not entries:
        # Try to find JSON data embedded in the page
        scripts = soup.find_all("script", type="application/json")
        for script in scripts:
            try:
                import json
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else data.get("data", [])
                for item in items:
                    if isinstance(item, dict):
                        name = str(item.get("nama", item.get("name", "")))
                        if "LSP" in name.upper():
                            entries.append(LSPEntry(
                                name=name,
                                registration_number=str(item.get("no_reg", item.get("reg_number", ""))),
                                status=str(item.get("status", "")),
                                city=str(item.get("kota", item.get("city", ""))),
                                province=str(item.get("provinsi", item.get("province", ""))),
                            ))
            except Exception:
                pass

    return entries


def _filter_matching_lsps(entries: list[LSPEntry], client_name: str) -> list[LSPEntry]:
    """Return LSP entries whose name partially matches client_name (case-insensitive)."""
    query = client_name.lower().strip()
    # Split query into tokens for partial matching
    tokens = query.split()
    matches: list[tuple[int, LSPEntry]] = []
    for entry in entries:
        lower_name = entry.name.lower()
        if query in lower_name:
            matches.append((0, entry))  # exact substring gets priority 0
        elif all(tok in lower_name for tok in tokens):
            matches.append((1, entry))
    # Sort by priority then return entries
    matches.sort(key=lambda x: x[0])
    return [m for _, m in matches]


def _extract_wa_from_social_links(socials: dict[str, list[str]]) -> list[str]:
    """Extract WhatsApp phone numbers from social links dict."""
    wa_phones: list[str] = []
    # Check for wa.me links
    for url in socials.get("wa", []):
        match = re.search(r"wa\.me/(\d+)", url)
        if match:
            num = match.group(1)
            if not num.startswith("62"):
                num = "62" + num.lstrip("0")
            wa_phones.append(num)
    # api.whatsapp.com send?phone= links
    for platform_urls in socials.values():
        for url in platform_urls:
            if "api.whatsapp.com" in url:
                match = re.search(r"phone=(\d+)", url)
                if match:
                    num = match.group(1)
                    if not num.startswith("62"):
                        num = "62" + num.lstrip("0")
                    wa_phones.append(num)
    return list(set(wa_phones))


def _extract_wa_from_html(html: str) -> list[str]:
    """Extract WhatsApp numbers directly from HTML (wa.me, api.whatsapp.com)."""
    wa_phones: list[str] = []
    patterns = [
        r'wa\.me/(\d+)',
        r'api\.whatsapp\.com/send\?phone=(\d+)',
        r'whatsapp\.com/[^\s"\'<>]*\?phone=(\d+)',
        r'href=["\']tel:(\d+)["\']',  # tel: links that may be WA
    ]
    for pat in patterns:
        for match in re.findall(pat, html):
            num = match.strip()
            if len(num) >= 9:
                if not num.startswith("62"):
                    num = "62" + num.lstrip("0")
                wa_phones.append(num)
    return list(set(wa_phones))


async def _scrape_lsp_website(lsp: LSPEntry) -> list[ContactResult]:
    """Search for and scrape an LSP's official website to extract contacts."""
    results: list[ContactResult] = []

    # Step 1: DDG search for the official website
    query = f"{lsp.name} LSP situs resmi kontak"
    search_results = await ddg_search(query, max_results=5)
    site_url: str | None = None
    for r in search_results:
        link = r.get("link", "")
        if link and "bnsp.go.id" not in link and link.startswith("http"):
            # Prefer exact domain match over search engine redirects
            site_url = link.split("?")[0].rstrip("/")
            break

    if not site_url:
        log.debug("[BNSP] No website found for LSP: %s", lsp.name)
        # Return BNSP HQ fallback contacts
        if BNSP_HQ_EMAIL:
            results.append(ContactResult(
                contact_type="email",
                value=BNSP_HQ_EMAIL,
                source_type="bnsp",
                source_url=BNSP_BASE,
                confidence=0.7,
            ))
        if BNSP_HQ_OFFICE_PHONE:
            results.append(ContactResult(
                contact_type="office_phone",
                value=BNSP_HQ_OFFICE_PHONE,
                source_type="bnsp",
                source_url=BNSP_BASE,
                confidence=0.8,
            ))
        if BNSP_HQ_WA_PHONE:
            results.append(ContactResult(
                contact_type="wa_phone",
                value=BNSP_HQ_WA_PHONE,
                source_type="bnsp",
                source_url=f"https://wa.me/{BNSP_HQ_WA_PHONE.lstrip('62')}",
                confidence=0.8,
            ))
        return results

    log.debug("[BNSP] Found website for '%s': %s", lsp.name, site_url)

    # Step 2: Scrape contact pages concurrently
    contact_paths = ["/kontak", "/hubungi-kami", "/tentang", "/contact", "/about"]
    pages: dict[str, str] = {}
    awaitables = [fetch_page(f"{site_url.rstrip('/')}{path}") for path in contact_paths]
    fetched = await asyncio.gather(*awaitables, return_exceptions=True)
    for path, result in zip(contact_paths, fetched):
        if isinstance(result, str) and result:
            pages[path] = result

    # Also fetch the homepage for links
    homepage = await fetch_page(site_url)
    if isinstance(homepage, str) and homepage:
        pages["/"] = homepage

    # Step 3: Extract contacts from all pages
    all_emails: set[str] = set()
    all_phones: set[str] = set()
    all_wa_phones: set[str] = set()
    all_wa_phones.add(BNSP_HQ_WA_PHONE)  # always include HQ WA

    for path, html in pages.items():
        text = extract_text_from_html(html)
        all_emails.update(extract_emails(text))
        all_phones.update(extract_phones_from_text(text))

        # WA-specific extraction
        socials = extract_social_links(html)
        all_wa_phones.update(_extract_wa_from_social_links(socials))
        all_wa_phones.update(_extract_wa_from_html(html))

    # Deduplicate and normalize emails
    for email in all_emails:
        if email.lower() not in (BNSP_HQ_EMAIL.lower(),):
            results.append(ContactResult(
                contact_type="email",
                value=email,
                source_type="bnsp",
                source_url=site_url,
                confidence=0.9,
            ))

    # Deduplicate and normalize phones
    seen_phones: set[str] = set()
    for phone in all_phones:
        normalized = re.sub(r"[^\d+]", "", phone)
        if normalized in seen_phones:
            continue
        seen_phones.add(normalized)
        if phone == BNSP_HQ_WA_PHONE:
            continue  # handled as WA
        # Classify as office_phone or wa_phone
        is_wa = any(phone.startswith(p) for p in ["628", "+628", "08"]) and len(re.sub(r"\D", "", phone)) >= 10
        contact_type = "wa_phone" if is_wa else "office_phone"
        results.append(ContactResult(
            contact_type=contact_type,
            value=phone,
            source_type="bnsp",
            source_url=site_url,
            confidence=0.9,
        ))

    # WA phones
    for wa in all_wa_phones:
        results.append(ContactResult(
            contact_type="wa_phone",
            value=wa,
            source_type="bnsp",
            source_url=f"https://wa.me/{wa.lstrip('62')}" if not wa.startswith("62") else f"https://wa.me/{wa[2:]}",
            confidence=0.9,
        ))

    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def bnsp_discovery(client_name: str) -> list[ContactResult]:
    """
    Discover LSP entries from BNSP directory matching client_name and
    extract contact information from their websites.

    Args:
        client_name: Name to match against LSP entries (case-insensitive partial match).

    Returns:
        List of ContactResult objects with contacts found for matching LSPs.
    """
    if not client_name or not client_name.strip():
        return []

    results: list[ContactResult] = []

    # Step 1: Fetch BNSP LSP list pages (1, 2, 3)
    all_entries: list[LSPEntry] = []
    pages = await asyncio.gather(*[_fetch_bnsp_page(p) for p in [1, 2, 3]], return_exceptions=True)

    for page_html in pages:
        if isinstance(page_html, str) and page_html:
            entries = _parse_lsp_entries(page_html)
            all_entries.extend(entries)

    if not all_entries:
        log.debug("[BNSP] No LSP entries found on bnsp.go.id/lsp pages")
        return []

    log.debug("[BNSP] Found %d total LSP entries across pages", len(all_entries))

    # Step 2: Filter to those matching client_name
    matches = _filter_matching_lsps(all_entries, client_name)
    if not matches:
        log.debug("[BNSP] No LSP entries matched client_name: %s", client_name)
        return []

    log.debug("[BNSP] %d LSP entries matched '%s'", len(matches), client_name)

    # Step 3: Scrape each matching LSP's website concurrently (semaphore limit = 5)
    semaphore = asyncio.Semaphore(5)

    async def scrape_with_limit(lsp: LSPEntry) -> list[ContactResult]:
        async with semaphore:
            return await _scrape_lsp_website(lsp)

    lsp_results = await asyncio.gather(
        *[scrape_with_limit(lsp) for lsp in matches],
        return_exceptions=True,
    )

    for lsp_result in lsp_results:
        if isinstance(lsp_result, list):
            results.extend(lsp_result)
        elif isinstance(lsp_result, Exception):
            log.debug("[BNSP] Exception during LSP scrape: %s", lsp_result)

    return results
