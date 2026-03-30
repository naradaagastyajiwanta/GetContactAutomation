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


async def sinta_search(name: str, university: str = "") -> dict | None:
    """
    Search SINTA Kemdikbud for a lecturer profile.
    Uses AI to verify the found profile belongs to the correct person.

    Returns info if found: {sinta_id, url, snippet, h_index, ...}
    """
    query = f'site:sinta.kemdikbud.go.id "{name}"'
    results = await ddg_search(query, max_results=3)
    if not results:
        return None

    for r in results:
        link = r.get("link", "")
        if "sinta.kemdikbud.go.id/authors" in link:
            import re
            match = re.search(r'/authors/profile/(\d+)', link)
            if match:
                sinta_id = match.group(1)
                result = {
                    "sinta_id": sinta_id,
                    "url": link,
                    "snippet": r.get("snippet", ""),
                }
                # Deep scrape: fetch SINTA profile for h-index, affiliations, etc.
                html = await fetch_page(link)
                if html:
                    text = extract_text_from_html(html, max_chars=5000)
                    # Use AI to extract structured data from SINTA page
                    ai_extract = await gpt_extract_structured(
                        text,
                        (
                            f"Extract information from this SINTA profile page.\n"
                            f"We're looking for: {name}"
                            + (f" at {university}" if university else "") + "\n"
                            f"Return JSON:\n"
                            f'- "is_correct_person": true/false (does this profile match?)\n'
                            f'- "h_index": number or null\n'
                            f'- "affiliation": university/institution name or null\n'
                            f'- "subjects": research areas or null\n'
                            f'- "reason": brief explanation of match/mismatch'
                        ),
                    )
                    if ai_extract:
                        if ai_extract.get("is_correct_person") is False:
                            log.info("[SINTA] AI rejected profile %s: %s", link, ai_extract.get("reason"))
                            continue  # Try next result
                        if ai_extract.get("h_index"):
                            result["h_index"] = ai_extract["h_index"]
                        if ai_extract.get("affiliation"):
                            result["affiliation"] = ai_extract["affiliation"]
                        if ai_extract.get("subjects"):
                            result["subjects"] = ai_extract["subjects"]
                    result["profile_text"] = text[:2000]
                return result
    return None


async def scholar_search(name: str, university: str = "") -> dict | None:
    """
    Search Google Scholar for a researcher profile.
    Uses AI to verify the profile belongs to the correct person
    and extract structured data.

    Returns: {url, snippet, interests, email_domain} or None.
    """
    query = f'site:scholar.google.com "{name}" {university}'
    results = await ddg_search(query, max_results=3)
    if not results:
        return None

    for r in results:
        link = r.get("link", "")
        if "scholar.google.com" in link:
            result = {
                "url": link,
                "snippet": r.get("snippet", ""),
            }
            # Deep scrape: fetch Scholar page and use AI for extraction + verification
            html = await fetch_page(link)
            if html:
                text = extract_text_from_html(html, max_chars=4000)
                ai_extract = await gpt_extract_structured(
                    text,
                    (
                        f"Extract information from this Google Scholar profile page.\n"
                        f"We're looking for: {name}"
                        + (f" at {university}" if university else "") + "\n"
                        f"Return JSON:\n"
                        f'- "is_correct_person": true/false (does this Scholar profile match?)\n'
                        f'- "email_domain": domain from "Verified email at ..." or null\n'
                        f'- "interests": list of research interests or null\n'
                        f'- "reason": brief explanation of match/mismatch'
                    ),
                )
                if ai_extract:
                    if ai_extract.get("is_correct_person") is False:
                        log.info("[Scholar] AI rejected profile %s: %s", link, ai_extract.get("reason"))
                        continue  # Try next result
                    if ai_extract.get("email_domain"):
                        result["email_domain"] = ai_extract["email_domain"]
                    if ai_extract.get("interests"):
                        result["interests"] = ai_extract["interests"]
            return result
    return None
