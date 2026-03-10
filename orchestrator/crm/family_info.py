"""
Family Info Agent — discovers basic family information.
Best-effort and privacy-conscious — only uses publicly available data.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, FamilyInfoResult
from orchestrator.crm.tools import ddg_search, gpt_extract_structured


async def family_info_agent(state: CrmState) -> dict:
    """
    Discover publicly available family information.
    Privacy-first: only use public mentions (news, official bios, interviews).

    Returns partial state update with `family_info`.
    """
    identity = state.get("identity")
    social = state.get("social_profile")
    pic_name = state.get("pic_name", "")
    uni_name = state.get("university_name", "")

    full_name = (identity.full_name if identity else None) or pic_name

    log.info("[FamilyInfo] Starting for %s", full_name)

    snippets: list[str] = []
    sources: list[str] = []

    # ── 1. DDG search for family mentions in public context ────────────
    queries = [
        f'"{full_name}" istri OR suami OR keluarga OR anak',
        f'"{full_name}" "{uni_name}" profil pribadi OR biografi',
    ]

    for q in queries:
        hits = await ddg_search(q, max_results=3)
        for h in (hits or []):
            snippet = h.get("snippet", "") or h.get("body", "")
            if snippet:
                snippets.append(snippet)

    if snippets:
        sources.append("ddg_family")

    # ── 2. Facebook public search (via DDG) ────────────────────────────
    fb_url = social.facebook_url if social else None
    if fb_url:
        fb_hits = await ddg_search(
            f'"{full_name}" site:facebook.com family OR keluarga',
            max_results=2,
        )
        for h in (fb_hits or []):
            snippet = h.get("snippet", "") or h.get("body", "")
            if snippet:
                snippets.append(f"Facebook: {snippet}")
        if fb_hits:
            sources.append("facebook")

    # ── 3. GPT extraction ──────────────────────────────────────────────
    result = FamilyInfoResult()

    if snippets:
        combined = "\n---\n".join(snippets[:10])
        extracted = await gpt_extract_structured(
            combined,
            (
                f"From these public text snippets about {full_name}, extract family information:\n"
                "Return JSON with keys:\n"
                "- marital_status: 'married'/'single'/'unknown'\n"
                "- spouse_name: string or null\n"
                "- children_count: integer or null\n"
                "- family_residence: city/region or null\n\n"
                "IMPORTANT: Only include information that is EXPLICITLY stated "
                "in the text. Do not infer or guess. Use null if not found."
            ),
        )
        if extracted:
            result.marital_status = extracted.get("marital_status", "unknown")
            result.spouse_name = extracted.get("spouse_name")
            children = extracted.get("children_count")
            if children is not None:
                try:
                    result.children_count = int(children)
                except (ValueError, TypeError):
                    pass
            result.family_residence = extracted.get("family_residence")

    # ── Confidence ─────────────────────────────────────────────────────
    filled = sum([
        result.marital_status != "unknown",
        bool(result.spouse_name),
        result.children_count is not None,
        bool(result.family_residence),
    ])
    result.confidence = round(filled / 4, 2)
    result.sources = sources

    log.info(
        "[FamilyInfo] Done for %s: status=%s, confidence=%.2f",
        full_name, result.marital_status, result.confidence,
    )
    return {"family_info": result}
