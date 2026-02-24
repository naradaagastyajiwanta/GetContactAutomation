"""
Agent 1: IG Handle Finder

Searches for Instagram handles for universities that don't have one yet.
Three-tier search:
  1. University website scraping (most accurate — IG link from their own site)
  2. Instagram Web Search API (direct search on IG)
  3. Serper.dev Google search (fallback)
"""
import asyncio

from orchestrator.config import is_paused, log, cfg
from orchestrator.db import (
    get_universities_by_status,
    get_universities_by_ids,
    update_ig_handle,
    update_university_status,
    update_university_website,
)
from orchestrator.instagram import (
    search_ig_from_website,
    search_ig_handle,
    search_ig_handle_with_fallback,
    verify_ig_handle_with_fallback,
)


async def _search_handle_for_uni(uni: dict, loop) -> dict | None:
    """Core logic: search IG handle for a single university. Returns detail dict or None."""
    result = None
    source = ""

    # Tier 1: University website scraping
    result = await search_ig_from_website(uni["name"], website_url=uni.get("website"), skip_pddikti=True)
    source = "website"

    if result and result.get("website_url"):
        await update_university_website(uni["id"], result["website_url"])

    # Tier 2: IG Web Search API (with Apify/ScrapingBot fallback)
    if not result or not result.get("handle"):
        result = await loop.run_in_executor(None, search_ig_handle_with_fallback, uni["name"])
        source = "ig_web"

    # Tier 3: Serper/Google search
    if not result or not result.get("handle"):
        result = await search_ig_handle(uni["name"])
        source = "serper"

    if result and result["handle"]:
        final_confidence = result["confidence"]
        if source != "website":
            await asyncio.sleep(3)
            verification = await loop.run_in_executor(None, verify_ig_handle_with_fallback, result["handle"], uni["name"])
            final_confidence += verification["confidence_boost"]
            if final_confidence < 0.55:
                log.info(
                    "[Agent1] @%s REJECTED for %s after bio check (%.2f → %.2f: %s)",
                    result["handle"], uni["name"], result["confidence"], final_confidence, verification["reason"],
                )
                return None

        await update_ig_handle(uni["id"], result["handle"], verified=final_confidence >= 0.6)
        await update_university_status(uni["id"], "ig_found")
        log.info(
            "[Agent1] IG handle found for %s: @%s (confidence: %.2f, via %s)",
            uni["name"], result["handle"], final_confidence, source,
        )
        return {
            "university": uni["name"],
            "handle": result["handle"],
            "confidence": final_confidence,
            "source": source,
        }

    log.info("[Agent1] No IG handle found for %s", uni["name"])
    return None


async def run_handle_search_batch(limit: int = 50) -> dict:
    """
    Search IG handles for universities in 'pending' status.
    Uses rolling mechanism to continue from last processed university.

    Returns summary dict: {"searched": int, "found": int, "details": list}
    """
    if is_paused():
        log.info("[Agent1] Bot is paused, skipping handle search")
        return {"searched": 0, "found": 0, "details": []}

    # Get last processed position for rolling
    last_id = int(cfg.AGENT_LAST_PROCESSED_UNIV_ID or 0)
    universities = await get_universities_by_status("pending", limit=limit, last_id=last_id)

    if not universities:
        log.info("[Agent1] No pending universities to search")
        # Reset rolling if we've processed all pending universities
        if last_id > 0:
            from orchestrator.db import upsert_config
            await upsert_config("AGENT_LAST_PROCESSED_UNIV_ID", "0")
            log.info("[Agent1] Rolling reset - completed cycle, starting from beginning")
        return {"searched": 0, "found": 0, "details": []}

    found = 0
    details: list[dict] = []
    loop = asyncio.get_running_loop()
    last_processed_id = last_id  # Track the last ID we processed

    for uni in universities:
        try:
            detail = await _search_handle_for_uni(uni, loop)
            if detail:
                found += 1
                details.append(detail)
            last_processed_id = uni["id"]  # Update last processed ID
            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent1] Error searching IG for %s: %s", uni["name"], e)

    # Save rolling position
    from orchestrator.db import upsert_config
    await upsert_config("AGENT_LAST_PROCESSED_UNIV_ID", str(last_processed_id))
    # Update ConfigManager in-memory value
    cfg.AGENT_LAST_PROCESSED_UNIV_ID = last_processed_id
    log.info("[Agent1] Rolling position saved: last_id = %d", last_processed_id)

    log.info("[Agent1] Batch complete: found %d/%d handles (ID range: %d-%d)",
             found, len(universities), last_id + 1, last_processed_id)
    return {"searched": len(universities), "found": found, "details": details}


async def run_handle_search_for_universities(university_ids: list[int]) -> dict:
    """
    Search IG handles for specific universities (regardless of status).

    Returns summary dict: {"searched": int, "found": int, "details": list}
    """
    universities = await get_universities_by_ids(university_ids)
    if not universities:
        return {"searched": 0, "found": 0, "details": []}

    found = 0
    details: list[dict] = []
    loop = asyncio.get_running_loop()

    for uni in universities:
        try:
            detail = await _search_handle_for_uni(uni, loop)
            if detail:
                found += 1
                details.append(detail)
            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent1] Error searching IG for %s: %s", uni["name"], e)

    log.info("[Agent1] Targeted batch complete: found %d/%d handles", found, len(universities))
    return {"searched": len(universities), "found": found, "details": details}
