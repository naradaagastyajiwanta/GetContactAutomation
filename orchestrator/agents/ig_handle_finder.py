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
    llm_verify_ig_handle,
)


async def _search_handle_for_uni(uni: dict, loop) -> dict | None:
    """Core logic: search IG handle for a single university. Returns detail dict or None.

    Tier order (optimised for speed + accuracy):
      1. Google / DuckDuckGo search  — fast, broad; bio-verified; accept ≥ 0.65
      2. IG Web Search API fallback  — Playwright → direct session; bio-verified; accept ≥ 0.55
      3. University website scraping — most accurate (0.90); no bio verify needed
    Each tier falls through to the next when confidence is insufficient.
    """
    final_handle: str | None = None
    final_confidence: float = 0.0
    final_source: str = ""

    # ------------------------------------------------------------------
    # Tier 1: Google / DuckDuckGo search (fast, no session needed)
    # Threshold after bio verify: ≥ 0.65 (stricter — Google results are
    # broad, bio confirm is mandatory to ensure we have the right account)
    # ------------------------------------------------------------------
    google_result = await search_ig_handle(uni["name"])
    if google_result and google_result.get("handle"):
        await asyncio.sleep(2)
        verification = await loop.run_in_executor(
            None, verify_ig_handle_with_fallback, google_result["handle"], uni["name"]
        )
        fc = google_result["confidence"] + verification["confidence_boost"]

        # LLM final judge: confirm the handle truly belongs to this university
        llm = await llm_verify_ig_handle(
            google_result["handle"],
            verification.get("bio", ""),
            verification.get("full_name", ""),
            uni["name"],
        )
        if llm["is_correct"] is False:
            log.info(
                "[Agent1] Tier1-Google @%s REJECTED by LLM for %s: %s — trying Tier 2",
                google_result["handle"], uni["name"], llm["reason"],
            )
        elif fc >= 0.65:
            final_handle = google_result["handle"]
            final_confidence = fc
            final_source = "serper"
            log.info(
                "[Agent1] Tier1-Google @%s ACCEPTED for %s (%.2f → %.2f: %s)",
                final_handle, uni["name"], google_result["confidence"], fc, verification["reason"],
            )
        else:
            log.info(
                "[Agent1] Tier1-Google @%s confidence too low for %s (%.2f → %.2f: %s), trying Tier 2",
                google_result["handle"], uni["name"], google_result["confidence"], fc, verification["reason"],
            )

    # ------------------------------------------------------------------
    # Tier 2: IG Web Search API (Playwright stealth → direct session)
    # Threshold after bio verify: ≥ 0.55 (standard)
    # ------------------------------------------------------------------
    if not final_handle:
        ig_result = await loop.run_in_executor(None, search_ig_handle_with_fallback, uni["name"])
        if ig_result and ig_result.get("handle"):
            await asyncio.sleep(3)
            verification = await loop.run_in_executor(
                None, verify_ig_handle_with_fallback, ig_result["handle"], uni["name"]
            )
            fc = ig_result["confidence"] + verification["confidence_boost"]

            # LLM final judge
            llm = await llm_verify_ig_handle(
                ig_result["handle"],
                verification.get("bio", ""),
                verification.get("full_name", ""),
                uni["name"],
            )
            if llm["is_correct"] is False:
                log.info(
                    "[Agent1] Tier2-IGWeb @%s REJECTED by LLM for %s: %s — trying Tier 3",
                    ig_result["handle"], uni["name"], llm["reason"],
                )
            elif fc >= 0.55:
                final_handle = ig_result["handle"]
                final_confidence = fc
                final_source = "ig_web"
                log.info(
                    "[Agent1] Tier2-IGWeb @%s ACCEPTED for %s (%.2f → %.2f: %s)",
                    final_handle, uni["name"], ig_result["confidence"], fc, verification["reason"],
                )
            else:
                log.info(
                    "[Agent1] Tier2-IGWeb @%s rejected for %s (%.2f → %.2f: %s), trying Tier 3",
                    ig_result["handle"], uni["name"], ig_result["confidence"], fc, verification["reason"],
                )

    # ------------------------------------------------------------------
    # Tier 3: University website scraping (most accurate — confidence 0.90)
    # No bio verification needed: handle comes from the university's own site.
    # Also saves website_url to DB even when no IG handle is found.
    # ------------------------------------------------------------------
    if not final_handle:
        website_result = await search_ig_from_website(
            uni["name"], website_url=uni.get("website"), skip_pddikti=True
        )
        if website_result and website_result.get("website_url"):
            await update_university_website(uni["id"], website_result["website_url"])

        if website_result and website_result.get("handle"):
            final_handle = website_result["handle"]
            final_confidence = website_result["confidence"]  # 0.90
            final_source = "website"
            log.info(
                "[Agent1] Tier3-Website @%s ACCEPTED for %s (confidence: %.2f)",
                final_handle, uni["name"], final_confidence,
            )

    # ------------------------------------------------------------------
    # Persist result
    # ------------------------------------------------------------------
    if final_handle:
        await update_ig_handle(uni["id"], final_handle, verified=final_confidence >= 0.6)
        await update_university_status(uni["id"], "ig_found")
        log.info(
            "[Agent1] IG handle found for %s: @%s (confidence: %.2f, via %s)",
            uni["name"], final_handle, final_confidence, final_source,
        )
        return {
            "university": uni["name"],
            "handle": final_handle,
            "confidence": final_confidence,
            "source": final_source,
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
        if is_paused():
            log.info("[Agent1] Bot paused during batch, stopping early")
            break
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
