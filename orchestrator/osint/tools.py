"""
Shared tools for OSINT agents — search, scrape, extract.

Wraps existing modules (DDG, PDDIKTI, httpx) into convenient async helpers
that all OSINT sub-agents can call.
"""

from __future__ import annotations

import asyncio
import json
import re
from functools import wraps
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from orchestrator.config import PHONE_PATTERNS, log, cfg
from orchestrator.duckduckgo_client import async_search_text


# ---------------------------------------------------------------------------
# Retry decorator for network operations
# ---------------------------------------------------------------------------

def async_retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Retry decorator for async functions with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff ** attempt)
                        log.debug(f"[Retry] {func.__name__} attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.1f}s...")
                        await asyncio.sleep(wait_time)
            log.warning(f"[Retry] {func.__name__} failed after {max_attempts} attempts: {last_exception}")
            return None
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Web search
# ---------------------------------------------------------------------------

@async_retry(max_attempts=3, delay=2.0, backoff=2.0)
async def ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo search returning [{title, link, snippet}]."""
    try:
        results = await async_search_text(query, max_results=max_results, region="id-id")
        return results
    except (Exception, asyncio.CancelledError) as e:
        log.warning("[OSINT Tools] DDG search failed for '%s': %s", query[:60], e)
        return []


# ---------------------------------------------------------------------------
# PDDIKTI wrappers (all run in thread to avoid blocking)
# ---------------------------------------------------------------------------

_pddikti = None


def _get_pddikti():
    global _pddikti
    if _pddikti is None:
        try:
            from pddiktipy import api
            _pddikti = api()
            # PDDIKTI API has incomplete cert chain; disable SSL verification
            if hasattr(_pddikti, 'H') and hasattr(_pddikti.H, 'session'):
                _pddikti.H.session.verify = False
        except ImportError:
            log.warning("[OSINT Tools] pddiktipy not installed")
            return None
    return _pddikti


async def pddikti_search_pt(name: str) -> list[dict]:
    """Search universities by name via PDDIKTI."""
    api = _get_pddikti()
    if not api:
        return []
    try:
        return await asyncio.to_thread(api.search_pt, name)
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI search_pt failed: %s", e)
        return []


async def pddikti_get_prodi(pt_id: str, semester: str = "") -> list[dict]:
    """Get list of study programs for a university.

    Args:
        pt_id: PDDIKTI university ID (encoded or numeric kode)
        semester: Academic semester in format YYYY1 or YYYY2 (e.g., 20241)
    """
    if not semester:
        semester = "20241"  # Default to current semester

    api = _get_pddikti()
    if not api:
        return []

    # First, get the encoded ID if we have a numeric kode
    encoded_id = pt_id
    if len(pt_id) <= 10 and pt_id.isdigit():
        try:
            results = await asyncio.to_thread(api.search_pt, pt_id)
            if results and len(results) > 0:
                for r in results:
                    if r.get("kode") == pt_id:
                        encoded_id = r["id"]
                        break
                else:
                    encoded_id = results[0]["id"]
            else:
                return []
        except Exception as e:
            log.warning("[OSINT Tools] PDDIKTI search_pt failed: %s", e)
            return []

    # Use direct HTTP request
    try:
        import httpx
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        base_url = "https://api-pddikti.kemdiktisaintek.go.id"
        url = f"{base_url}/pt/prodi/{encoded_id}/{semester}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://pddikti.kemdiktisaintek.go.id",
            "Referer": "https://pddikti.kemdiktisaintek.go.id/",
        }

        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                return []
            else:
                log.warning("[OSINT Tools] PDDIKTI get_prodi HTTP %d: %s", resp.status_code, resp.text[:200])
                return []
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI get_prodi failed: %s", e)
        return []


async def pddikti_get_jumlah_dosen(pt_id: str) -> Any:
    """Get total lecturer count for a university."""
    api = _get_pddikti()
    if not api:
        return None
    try:
        return await asyncio.to_thread(api.get_jumlah_dosen_pt, pt_id)
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI get_jumlah_dosen_pt failed: %s", e)
        return None


async def pddikti_get_pt(pt_id: str) -> dict | None:
    """Get full university (PT) profile from PDDIKTI.

    Returns detailed info including:
    - name, address, phone, fax, email, website

    Note: pt_id can be either:
    - Encoded ID from search results (e.g., '_xyEoOsLCdn4d...')
    - Or numeric KODE PT (e.g., '001002' for UI)
    """
    api = _get_pddikti()
    if not api:
        return None

    # First, get the encoded ID if we have a numeric kode
    encoded_id = pt_id
    if len(pt_id) <= 10 and pt_id.isdigit():
        try:
            results = await asyncio.to_thread(api.search_pt, pt_id)
            if results and len(results) > 0:
                # Find exact match by kode
                for r in results:
                    if r.get("kode") == pt_id:
                        encoded_id = r["id"]
                        break
                else:
                    # Use first result if exact match not found
                    encoded_id = results[0]["id"]
            else:
                return None
        except Exception as e:
            log.warning("[OSINT Tools] PDDIKTI search_pt failed: %s", e)
            return None

    # Use direct HTTP request to the correct endpoint
    try:
        import httpx
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        base_url = "https://api-pddikti.kemdiktisaintek.go.id"
        url = f"{base_url}/pt/detail/{encoded_id}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://pddikti.kemdiktisaintek.go.id",
            "Referer": "https://pddikti.kemdiktisaintek.go.id/",
            "X-User-IP": "103.253.145.84",
        }

        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            else:
                log.warning("[OSINT Tools] PDDIKTI get_pt HTTP %d: %s", resp.status_code, resp.text[:200])
                return None
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI get_pt failed: %s", e)
        return None


async def pddikti_search_dosen(name: str) -> list[dict]:
    """Search lecturers by name via PDDIKTI."""
    api = _get_pddikti()
    if not api:
        return []
    try:
        return await asyncio.to_thread(api.search_dosen, name)
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI search_dosen failed: %s", e)
        return []


async def pddikti_get_dosen_profile(dosen_id: str) -> dict | None:
    """Get full lecturer profile from PDDIKTI."""
    api = _get_pddikti()
    if not api:
        return None
    try:
        return await asyncio.to_thread(api.get_dosen_profile, dosen_id)
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI get_dosen_profile failed: %s", e)
        return None


async def pddikti_get_dosen_study_history(dosen_id: str) -> list[dict]:
    """Get lecturer's education history."""
    api = _get_pddikti()
    if not api:
        return []
    try:
        return await asyncio.to_thread(api.get_dosen_study_history, dosen_id)
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI study_history failed: %s", e)
        return []


async def pddikti_get_dosen_teaching(dosen_id: str) -> list[dict]:
    """Get lecturer's teaching history (courses taught)."""
    api = _get_pddikti()
    if not api:
        return []
    try:
        return await asyncio.to_thread(api.get_dosen_teaching_history, dosen_id)
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI teaching_history failed: %s", e)
        return []


async def pddikti_get_dosen_penelitian(dosen_id: str) -> list[dict]:
    """Get lecturer's research activities."""
    api = _get_pddikti()
    if not api:
        return []
    try:
        return await asyncio.to_thread(api.get_dosen_penelitian, dosen_id)
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI penelitian failed: %s", e)
        return []


async def pddikti_get_dosen_karya(dosen_id: str) -> list[dict]:
    """Get lecturer's publications and works."""
    api = _get_pddikti()
    if not api:
        return []
    try:
        return await asyncio.to_thread(api.get_dosen_karya, dosen_id)
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI karya failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# HTTP fetch & parse
# ---------------------------------------------------------------------------


@async_retry(max_attempts=3, delay=1.0, backoff=2.0)
async def fetch_page(url: str, timeout: float = 30.0) -> str | None:
    """Fetch a web page and return the HTML body text, or None on error."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except (Exception, asyncio.CancelledError) as e:
        log.debug("[OSINT Tools] fetch_page failed for %s: %s", url, e)
        return None


def extract_text_from_html(html: str, max_chars: int = 15000) -> str:
    """Strip HTML tags and return cleaned text content."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:max_chars]


def extract_social_links(html: str) -> dict[str, list[str]]:
    """Extract social media links from HTML page (footer/header typically).
    Returns dict with platform -> list of URLs (since there may be multiple)."""
    patterns = {
        "facebook": r'https?://(?:www\.)?facebook\.com/[^\s"\'<>]+',
        "twitter": r'https?://(?:www\.)?(?:twitter|x)\.com/[^\s"\'<>]+',
        "youtube": r'https?://(?:www\.)?youtube\.com/(?:@|channel/|c/)[^\s"\'<>]+',
        "linkedin": r'https?://(?:www\.)?linkedin\.com/(?:company|in)/[^\s"\'<>]+',
        "tiktok": r'https?://(?:www\.)?tiktok\.com/@[^\s"\'<>]+',
        "instagram": r'https?://(?:www\.)?instagram\.com/[^\s"\'<>]+',
    }
    found = {}
    for platform, pattern in patterns.items():
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            found[platform] = list(set(matches))  # Remove duplicates
    return found


def extract_emails(text: str) -> list[str]:
    """Extract email addresses from text with basic validation."""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)
    # Filter out invalid emails
    valid_emails = []
    for email in emails:
        email_lower = email.lower()
        # Skip if contains invalid patterns
        if '@.' in email_lower:  # @.something
            continue
        if '.@' in email_lower:  # .@something (invalid local part)
            continue
        if '..' in email_lower:  # double dots
            continue
        if email_lower.startswith('.'):  # starts with dot
            continue
        if len(email) < 5:  # too short to be valid
            continue
        # Skip test/fake TLDs
        tld = email_lower.split('.')[-1]
        if tld in ('test', 'example', 'localhost', 'invalid'):
            continue
        valid_emails.append(email)
    return list(set(valid_emails))


def extract_phones_from_text(text: str) -> list[str]:
    """Extract Indonesian phone numbers from text using config patterns."""
    phones = []
    for pattern in PHONE_PATTERNS:
        matches = re.findall(pattern, text)
        phones.extend(matches)
    # Also try simple pattern for numbers like 081234567890
    simple = re.findall(r'(?:(?:\+62|62|0)8\d{8,12})', text.replace(" ", "").replace("-", ""))
    phones.extend(simple)
    # Clean and dedupe
    cleaned = []
    for ph in phones:
        cleaned_num = re.sub(r'[\s\-\.]', '', ph).strip()
        if len(re.sub(r'\D', '', cleaned_num)) >= 9:
            cleaned.append(cleaned_num)
    return list(set(cleaned))


# ---------------------------------------------------------------------------
# GPT extraction helper
# ---------------------------------------------------------------------------


async def gpt_extract_structured(
    text: str,
    instruction: str,
    model: str = "gpt-4o-mini",
) -> dict | None:
    """
    Use OpenAI to extract structured data from unstructured text.

    instruction should describe the desired JSON output schema.
    """
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a data extraction assistant. Extract the requested information from the provided text. "
                        "Respond ONLY with valid JSON. If information is not found, use null for that field."
                    ),
                },
                {
                    "role": "user",
                    "content": f"{instruction}\n\n---\nTEXT:\n{text[:12000]}",
                },
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return json.loads(content) if content else None
    except (Exception, asyncio.CancelledError) as e:
        log.warning("[OSINT Tools] GPT extraction failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Gemini with Google Search grounding (for deep research)
# ---------------------------------------------------------------------------


async def gemini_research(query: str) -> dict[str, Any]:
    """
    Run a Gemini query with Google Search grounding.
    Returns {"text": str, "urls": list[str]}.
    """
    try:
        from orchestrator.research_agents.gemini_caller import call_gemini
        parsed, urls = await call_gemini(query)
        # parsed can be a dict or a list
        if isinstance(parsed, list):
            raw_text = json.dumps(parsed, ensure_ascii=False)
        else:
            raw_text = parsed.get("_raw", "") if parsed.get("_parse_failed") else json.dumps(parsed, ensure_ascii=False)
        return {"text": raw_text, "urls": urls}
    except Exception as e:
        log.warning("[OSINT Tools] Gemini research failed: %s", e)
        return {"text": "", "urls": []}
