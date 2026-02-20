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
    update_ig_handle,
    update_university_status,
    update_university_website,
)
from orchestrator.instagram import (
    search_ig_from_website,
    search_ig_handle,
    search_ig_handle_via_ig,
    verify_ig_handle,
)


async def run_handle_search_batch(limit: int = 50) -> dict:
    """
    Search IG handles for universities in 'pending' status.

    Returns summary dict: {"searched": int, "found": int, "details": list}
    """
    if is_paused():
        log.info("[Agent1] Bot is paused, skipping handle search")
        return {"searched": 0, "found": 0, "details": []}

    universities = await get_universities_by_status("pending", limit=limit)
    if not universities:
        log.info("[Agent1] No pending universities to search")
        return {"searched": 0, "found": 0, "details": []}

    found = 0
    details: list[dict] = []
    loop = asyncio.get_running_loop()

    for uni in universities:
        try:
            result = None
            source = ""

            # Tier 1: University website scraping (highest accuracy)
            # Skip PDDIKTI lookup — already queried during collect_universities
            result = await search_ig_from_website(uni["name"], website_url=uni.get("website"), skip_pddikti=True)
            source = "website"

            # Save website URL if found (regardless of IG handle)
            if result and result.get("website_url"):
                await update_university_website(uni["id"], result["website_url"])

            # Tier 2: IG Web Search API
            if not result or not result.get("handle"):
                result = await loop.run_in_executor(
                    None, search_ig_handle_via_ig, uni["name"]
                )
                source = "ig_web"

            # Tier 3: Serper/Google search
            if not result or not result.get("handle"):
                result = await search_ig_handle(uni["name"])
                source = "serper"

            if result and result["handle"]:
                # Verify by checking IG bio (skip for website source — already trusted)
                final_confidence = result["confidence"]
                if source != "website":
                    await asyncio.sleep(3)  # Avoid IG rate limiting before profile fetch
                    verification = await loop.run_in_executor(
                        None, verify_ig_handle, result["handle"], uni["name"]
                    )
                    final_confidence += verification["confidence_boost"]
                    if final_confidence < 0.55:
                        log.info(
                            "[Agent1] @%s REJECTED for %s after bio check (%.2f → %.2f: %s)",
                            result["handle"], uni["name"],
                            result["confidence"], final_confidence,
                            verification["reason"],
                        )
                        result = None

                if result:
                    await update_ig_handle(
                        uni["id"],
                        result["handle"],
                        verified=final_confidence >= 0.6,
                    )
                    await update_university_status(uni["id"], "ig_found")
                    found += 1
                    details.append({
                        "university": uni["name"],
                        "handle": result["handle"],
                        "confidence": final_confidence,
                        "source": source,
                    })
                    log.info(
                        "[Agent1] IG handle found for %s: @%s (confidence: %.2f, via %s)",
                        uni["name"], result["handle"], final_confidence, source,
                    )

            if not result:
                log.info("[Agent1] No IG handle found for %s", uni["name"])

            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent1] Error searching IG for %s: %s", uni["name"], e)

    log.info("[Agent1] Batch complete: found %d/%d handles", found, len(universities))
    return {"searched": len(universities), "found": found, "details": details}
