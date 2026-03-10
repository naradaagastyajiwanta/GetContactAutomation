"""
Shared tools for CRM/PIC profiling agents.

Re-exports OSINT tools + adds CRM-specific helpers
(SINTA scraping, PDDIKTI dosen, etc.)
"""

from __future__ import annotations

# Re-export shared OSINT tools
from orchestrator.osint.tools import (  # noqa: F401
    ddg_search,
    fetch_page,
    extract_text_from_html,
    extract_social_links,
    extract_emails,
    extract_phones_from_text,
    gpt_extract_structured,
    gemini_research,
    pddikti_search_dosen,
    pddikti_get_dosen_profile,
    pddikti_get_dosen_study_history,
    pddikti_get_dosen_teaching,
    pddikti_get_dosen_penelitian,
    pddikti_get_dosen_karya,
)

from orchestrator.config import log


# ---------------------------------------------------------------------------
# SINTA scraper (best-effort)
# ---------------------------------------------------------------------------


async def sinta_search(name: str) -> dict | None:
    """
    Search SINTA Kemdikbud for a lecturer profile.

    Returns basic info if found: {sinta_id, name, affiliation, h_index, ...}
    """
    query = f'site:sinta.kemdikbud.go.id "{name}"'
    results = await ddg_search(query, max_results=3)
    if not results:
        return None

    for r in results:
        link = r.get("link", "")
        if "sinta.kemdikbud.go.id/authors" in link:
            # Try to extract SINTA ID from URL
            import re
            match = re.search(r'/authors/profile/(\d+)', link)
            if match:
                sinta_id = match.group(1)
                return {
                    "sinta_id": sinta_id,
                    "url": link,
                    "snippet": r.get("snippet", ""),
                }
    return None


async def scholar_search(name: str, university: str = "") -> dict | None:
    """
    Search Google Scholar for a researcher profile.

    Returns: {scholar_url, interests, snippet} or None.
    """
    query = f'site:scholar.google.com "{name}" {university}'
    results = await ddg_search(query, max_results=3)
    if not results:
        return None

    for r in results:
        link = r.get("link", "")
        if "scholar.google.com" in link:
            return {
                "url": link,
                "snippet": r.get("snippet", ""),
            }
    return None
