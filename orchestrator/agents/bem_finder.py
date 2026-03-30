"""
Agent 4: BEM & Related IG Discovery

Discovers BEM (Badan Eksekutif Mahasiswa / Student Council) and other
related Instagram accounts for universities by scanning the **official
university IG's following list**.

Flow per university:
  1. University already has ig_handle (discovered by Agent 1)
  2. Fetch the official IG account's following list
  3. Classify followed accounts as BEM, humas, pmb, kemahasiswaan, etc.
  4. Save as related IGs → Agent 2 will scrape their posts later

This works because official university IG accounts typically follow
their own BEM, humas, and other institutional sub-accounts.
"""
import asyncio

from orchestrator.config import is_paused, log, cfg
from orchestrator.db import (
    get_universities_for_bem_discovery,
    get_universities_by_ids,
    add_related_ig,
    update_bem_handle,
    update_bem_discovery_status,
)
from orchestrator.instagram import (
    get_ig_following,
    find_related_accounts_from_following,
    fetch_bios_for_candidates,
    search_related_accounts_via_search,
    verify_related_accounts_with_llm,
)

# Minimum confidence to save a related IG account.
# Raised to 0.55 so only accounts with a clear university identifier
# (acronym, location, or unique name word) in their username/bio are saved.
_MIN_CONFIDENCE = 0.55


async def _discover_bem_for_uni(uni: dict, loop) -> dict:
    """Scan the official IG's following list to find BEM & related accounts.

    Returns detail dict with discovery results.
    """
    result = {
        "university": uni["name"],
        "university_id": uni["id"],
        "ig_handle": uni.get("ig_handle", ""),
        "bem_handle": None,
        "related_igs_added": 0,
        "related_accounts": [],
    }

    async def _update_status_and_return(result_dict: dict, status_str: str) -> dict:
        await update_bem_discovery_status(uni["id"], status_str)
        # Advance funnel state if it was waiting at ig_found
        if uni.get("status") == "ig_found":
            from orchestrator.db import update_university_status
            await update_university_status(uni["id"], "bem_discovered")
        return result_dict

    ig_handle = uni.get("ig_handle", "")
    if not ig_handle:
        log.info("[Agent4-BEM] No IG handle for %s, skipping", uni["name"])
        return await _update_status_and_return(result, "no_ig_handle")

    # Step 1: Fetch official IG's following list
    log.info("[Agent4-BEM] Fetching following list of @%s (%s)", ig_handle, uni["name"])
    following = await loop.run_in_executor(
        None, get_ig_following, ig_handle, 300
    )

    # Cool-down after following fetch to avoid 429 on immediate bio requests
    if following:
        await asyncio.sleep(3)

    if not following:
        log.info("[Agent4-BEM] Empty following for @%s (%s), trying web search fallback", ig_handle, uni["name"])
        keyword_matches = await search_related_accounts_via_search(uni["name"])
        # Enrich candidates with bio before LLM
        keyword_matches = await loop.run_in_executor(None, fetch_bios_for_candidates, keyword_matches)
        related = await verify_related_accounts_with_llm(keyword_matches, uni["name"], ig_handle)

        bem_found = False
        for acct in related:
            if acct["confidence"] < _MIN_CONFIDENCE:
                continue

            added = await add_related_ig(
                university_id=uni["id"],
                ig_handle=acct["handle"],
                relation_type=acct["relation_type"],
                source="web_search",
                confidence=acct["confidence"],
            )
            if added:
                result["related_igs_added"] += 1
                result["related_accounts"].append(
                    f"@{acct['handle']} ({acct['relation_type']}, {acct['confidence']:.0%})"
                )

            if acct["relation_type"] == "bem" and not bem_found:
                bem_found = True
                result["bem_handle"] = acct["handle"]
                await update_bem_handle(uni["id"], acct["handle"])
                log.info(
                    "[Agent4-BEM] Web search fallback found BEM @%s for %s (confidence: %.2f)",
                    acct["handle"], uni["name"], acct["confidence"],
                )

        status = "discovered" if result["related_igs_added"] > 0 else "no_following"
        return await _update_status_and_return(result, status)

    log.info("[Agent4-BEM] @%s follows %d accounts", ig_handle, len(following))

    # Step 2: Classify followed accounts via keyword matching
    keyword_matches = find_related_accounts_from_following(following, uni["name"])

    if not keyword_matches:
        log.info("[Agent4-BEM] No related accounts found in @%s following for %s",
                 ig_handle, uni["name"])
        return await _update_status_and_return(result, "not_found")

    # Step 3: LLM verification — filter to only truly related accounts
    # Enrich candidates with bio before sending to LLM
    keyword_matches = await loop.run_in_executor(None, fetch_bios_for_candidates, keyword_matches)
    related = await verify_related_accounts_with_llm(keyword_matches, uni["name"], ig_handle)

    if not related:
        log.info("[Agent4-BEM] LLM filtered out all candidates for %s", uni["name"])
        return await _update_status_and_return(result, "not_found")

    # Step 4: Save verified accounts
    bem_found = False
    for acct in related:
        if acct["confidence"] < _MIN_CONFIDENCE:
            continue

        added = await add_related_ig(
            university_id=uni["id"],
            ig_handle=acct["handle"],
            relation_type=acct["relation_type"],
            source="official_following",
            confidence=acct["confidence"],
        )
        if added:
            result["related_igs_added"] += 1
            result["related_accounts"].append(
                f"@{acct['handle']} ({acct['relation_type']}, {acct['confidence']:.0%})"
            )

        # Track the first (highest confidence) BEM handle
        if acct["relation_type"] == "bem" and not bem_found:
            bem_found = True
            result["bem_handle"] = acct["handle"]
            await update_bem_handle(uni["id"], acct["handle"])
            log.info(
                "[Agent4-BEM] Found BEM @%s for %s (confidence: %.2f)",
                acct["handle"], uni["name"], acct["confidence"],
            )

    # Status = discovered if we found a BEM handle OR any related accounts
    # (even if add_related_ig returned False due to duplicate records)
    is_discovered = bool(result["bem_handle"] or result["related_accounts"] or result["related_igs_added"] > 0)
    status = "discovered" if is_discovered else "not_found"
    await _update_status_and_return(result, status)

    log.info(
        "[Agent4-BEM] %s: %d new related IGs saved, %d total found (BEM: %s)",
        uni["name"], result["related_igs_added"],
        len(result["related_accounts"]) + (1 if result["bem_handle"] and result["related_igs_added"] == 0 else 0),
        result["bem_handle"] or "none",
    )
    return result


async def run_bem_discovery_batch(limit: int = 30) -> dict:
    """
    Discover BEM & related accounts for universities that have an IG handle.
    Uses rolling mechanism to continue from last processed university.

    Returns summary dict: {"searched": int, "found": int, "details": list}
    """
    if is_paused():
        log.info("[Agent4-BEM] Bot is paused, skipping BEM discovery")
        return {"searched": 0, "found": 0, "details": []}

    # Get last processed position for rolling
    last_id = int(cfg.AGENT_LAST_PROCESSED_UNIV_ID or 0)
    universities = await get_universities_for_bem_discovery(limit=limit, last_id=last_id)

    if not universities:
        log.info("[Agent4-BEM] No universities pending BEM discovery")
        # Reset rolling if we've processed all
        if last_id > 0:
            from orchestrator.db import upsert_config
            await upsert_config("AGENT_LAST_PROCESSED_UNIV_ID", "0")
            log.info("[Agent4-BEM] Rolling reset - completed cycle, starting from beginning")
        return {"searched": 0, "found": 0, "details": []}

    found = 0
    details: list[dict] = []
    loop = asyncio.get_running_loop()
    last_processed_id = last_id

    for uni in universities:
        if is_paused():
            log.info("[Agent4-BEM] Bot paused during batch, stopping early")
            break
        try:
            detail = await _discover_bem_for_uni(uni, loop)
            details.append(detail)
            if detail["related_igs_added"] > 0 or detail["bem_handle"]:
                found += 1
            last_processed_id = uni["id"]
            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent4-BEM] Error for %s: %s", uni["name"], e, exc_info=True)

    # Save rolling position
    from orchestrator.db import upsert_config
    await upsert_config("AGENT_LAST_PROCESSED_UNIV_ID", str(last_processed_id))
    # Update ConfigManager in-memory value
    cfg.AGENT_LAST_PROCESSED_UNIV_ID = last_processed_id
    log.info("[Agent4-BEM] Rolling position saved: last_id = %d", last_processed_id)

    log.info(
        "[Agent4-BEM] Batch complete: %d/%d universities had related accounts (ID range: %d-%d)",
        found, len(universities), last_id + 1, last_processed_id,
    )
    return {"searched": len(universities), "found": found, "details": details}


async def run_bem_discovery_for_universities(university_ids: list[int]) -> dict:
    """
    Discover BEM & related accounts for specific universities (regardless of status).

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
            detail = await _discover_bem_for_uni(uni, loop)
            details.append(detail)
            if detail["related_igs_added"] > 0 or detail["bem_handle"]:
                found += 1
            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent4-BEM] Error for %s: %s", uni["name"], e, exc_info=True)

    log.info(
        "[Agent4-BEM] Targeted batch: %d/%d universities had related accounts",
        found, len(universities),
    )
    return {"searched": len(universities), "found": found, "details": details}
