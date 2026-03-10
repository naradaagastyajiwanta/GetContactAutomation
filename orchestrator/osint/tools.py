"""
Shared tools for OSINT agents — search, scrape, extract.

Wraps existing modules (DDG, PDDIKTI, httpx) into convenient async helpers
that all OSINT sub-agents can call.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from orchestrator.config import log, cfg
from orchestrator.duckduckgo_client import async_search_text


# ---------------------------------------------------------------------------
# Web search
# ---------------------------------------------------------------------------


async def ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo search returning [{title, link, snippet}]."""
    try:
        results = await async_search_text(query, max_results=max_results, region="id-id")
        return results
    except Exception as e:
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
    """Get list of study programs for a university."""
    api = _get_pddikti()
    if not api:
        return []
    try:
        return await asyncio.to_thread(api.get_prodi_pt, pt_id, semester)
    except Exception as e:
        log.warning("[OSINT Tools] PDDIKTI get_prodi_pt failed: %s", e)
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


async def fetch_page(url: str, timeout: float = 15.0) -> str | None:
    """Fetch a web page and return the HTML body text, or None on error."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; GetContactAI/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        log.debug("[OSINT Tools] fetch_page failed for %s: %s", url, e)
        return None


def extract_text_from_html(html: str, max_chars: int = 8000) -> str:
    """Strip HTML tags and return cleaned text content."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:max_chars]


def extract_social_links(html: str) -> dict[str, str]:
    """Extract social media links from HTML page (footer/header typically)."""
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
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            found[platform] = match.group(0)
    return found


def extract_emails(text: str) -> list[str]:
    """Extract email addresses from text."""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(pattern, text)))


def extract_phones_from_text(text: str) -> list[str]:
    """Extract Indonesian phone numbers from text."""
    patterns = [
        r'\+62\s*\d[\d\s\-\.]{8,14}',
        r'0\d[\d\s\-\.]{8,14}',
        r'\(0\d{2,3}\)\s*\d[\d\s\-\.]{6,10}',
    ]
    phones = []
    for p in patterns:
        phones.extend(re.findall(p, text))
    # Clean whitespace
    return [re.sub(r'[\s\-\.]', '', ph).strip() for ph in phones if len(re.sub(r'\D', '', ph)) >= 9]


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
                    "content": f"{instruction}\n\n---\nTEXT:\n{text[:6000]}",
                },
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return json.loads(content) if content else None
    except Exception as e:
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
        # parsed is a dict (possibly with _raw if JSON parse failed)
        raw_text = parsed.get("_raw", "") if parsed.get("_parse_failed") else json.dumps(parsed, ensure_ascii=False)
        return {"text": raw_text, "urls": urls}
    except Exception as e:
        log.warning("[OSINT Tools] Gemini research failed: %s", e)
        return {"text": "", "urls": []}
