"""
Agent 2: IG Post Scraper

Smart-scrapes Instagram posts via Web API (browser session cookie).
Only returns posts likely to contain phone numbers:
  - Bio with phone number
  - Posts with phone number in caption
  - Event flyer / poster posts (keywords match)
Saves posts to ig_posts table for phone extraction later.

On re-scrape (universities with few contacts), fetches deeper (older)
posts that weren't covered in the initial scrape.
"""
import asyncio
from functools import partial

from orchestrator.config import is_paused, log, cfg
from orchestrator.db import (
    add_ig_post,
    get_contacts_for_university,
    get_post_count_for_university,
    get_post_urls_for_university,
    get_universities_by_status,
    get_universities_by_ids,
    get_unscraped_related_igs,
    get_related_igs_for_university,
    mark_related_ig_scraped,
    update_university_status,
)
from orchestrator.instagram import scrape_ig_posts_with_fallback

# Universities with fewer contacts than this will be re-scraped deeper
MIN_CONTACTS_FOR_RESCRAPE = 5


async def run_post_scrape_batch(limit: int = 20) -> dict:
    """
    Scrape IG posts for universities in 'ig_found' status with rolling mechanism.
    For each university, scrape posts from main IG + all related IGs until target is reached.

    Target posts per university: configured via TARGET_POSTS_PER_UNIVERSITY (default: 100)

    Returns summary dict: {"scraped": int, "total_posts": int, "details": list}
    """
    if is_paused():
        log.info("[Agent2] Bot is paused, skipping post scraping")
        return {"scraped": 0, "total_posts": 0, "details": []}

    # Get target posts per university from config
    target_posts = int(cfg.TARGET_POSTS_PER_UNIVERSITY or 100)

    # Get last processed position for rolling
    last_id = int(cfg.AGENT_LAST_PROCESSED_UNIV_ID or 0)
    universities = await get_universities_by_status("ig_found", limit=limit, last_id=last_id)

    if not universities:
        log.info("[Agent2] No universities to scrape")
        # Reset rolling if completed
        if last_id > 0:
            from orchestrator.db import upsert_config
            await upsert_config("AGENT_LAST_PROCESSED_UNIV_ID", "0")
            log.info("[Agent2] Rolling reset - completed cycle, starting from beginning")
        return {"scraped": 0, "total_posts": 0, "details": []}

    scraped = 0
    total_posts = 0
    details: list[dict] = []
    loop = asyncio.get_running_loop()
    last_processed_id = last_id

    for uni in universities:
        uni_id = uni["id"]
        handle = uni.get("ig_handle")

        if not handle:
            continue

        try:
            # Check current post count
            current_count = await get_post_count_for_university(uni_id)
            log.info("[Agent2] %s: current posts = %d, target = %d", uni["name"], current_count, target_posts)

            # If already reached target, skip
            if current_count >= target_posts:
                log.info("[Agent2] %s: already has %d posts (target: %d), skipping",
                         uni["name"], current_count, target_posts)
                await update_university_status(uni_id, "ig_scraped")
                last_processed_id = uni_id
                continue

            # Scrape main IG first
            posts = await loop.run_in_executor(
                None, scrape_ig_posts_with_fallback, handle
            )
            saved = await _save_posts(uni_id, posts, source_ig_handle=handle, source_ig_type="main")
            total_posts += saved
            current_count += saved

            details.append({
                "university": uni["name"],
                "handle": handle,
                "posts_found": len(posts),
                "posts_saved": saved,
                "mode": "main",
            })
            log.info("[Agent2] @%s: scraped %d posts, saved %d new (total: %d/%d)",
                     handle, len(posts), saved, current_count, target_posts)

            # If still below target, scrape related IGs
            if current_count < target_posts:
                related_igs = await get_related_igs_for_university(uni_id)
                log.info("[Agent2] %s: have %d related IGs to scrape (still need %d more posts)",
                         uni["name"], len(related_igs), target_posts - current_count)

                for rel in related_igs:
                    if current_count >= target_posts:
                        log.info("[Agent2] %s: reached target %d posts, stopping related IG scrape",
                                 uni["name"], current_count)
                        break

                    rel_handle = rel.get("ig_handle")
                    relation_type = rel.get("relation_type", "bem")
                    if not rel_handle:
                        continue

                    try:
                        rel_posts = await loop.run_in_executor(
                            None, scrape_ig_posts_with_fallback, rel_handle
                        )
                        rel_saved = await _save_posts(
                            uni_id, rel_posts,
                            source_ig_handle=rel_handle,
                            source_ig_type=relation_type
                        )
                        total_posts += rel_saved
                        current_count += rel_saved

                        details.append({
                            "university": uni["name"],
                            "handle": rel_handle,
                            "posts_found": len(rel_posts),
                            "posts_saved": rel_saved,
                            "mode": f"related_{relation_type}",
                        })
                        log.info(
                            "[Agent2] Related @%s (%s): scraped %d posts, saved %d new (total: %d/%d)",
                            rel_handle, relation_type, len(rel_posts), rel_saved, current_count, target_posts,
                        )

                        await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
                    except Exception as e:
                        log.error("[Agent2] Error scraping related @%s: %s", rel_handle, e)

            await update_university_status(uni_id, "ig_scraped")
            scraped += 1
            last_processed_id = uni_id
            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent2] Error scraping @%s: %s", handle, e)

    # Save rolling position
    from orchestrator.db import upsert_config
    await upsert_config("AGENT_LAST_PROCESSED_UNIV_ID", str(last_processed_id))
    # Update ConfigManager in-memory value
    cfg.AGENT_LAST_PROCESSED_UNIV_ID = last_processed_id
    log.info(
        "[Agent2] Batch complete: scraped %d universities, %d posts saved (ID range: %d-%d)",
        scraped, total_posts, last_id + 1, last_processed_id,
    )
    return {"scraped": scraped, "total_posts": total_posts, "details": details}


async def _save_posts(
    university_id: int,
    posts: list[dict],
    source_ig_handle: str | None = None,
    source_ig_type: str | None = None,
) -> int:
    """Save posts to DB, return count of newly inserted rows.

    Args:
        university_id: Parent university ID
        posts: List of post dictionaries from scraping
        source_ig_handle: Which IG account this came from
        source_ig_type: Type of IG account ('main' or 'bem', 'humas', 'pmb', etc.)
    """
    saved = 0
    for post in posts:
        result = await add_ig_post(
            university_id=university_id,
            post_url=post["post_url"],
            image_url=post.get("image_url"),
            caption=post.get("caption"),
            post_timestamp=post.get("timestamp"),
            source_ig_handle=source_ig_handle,
            source_ig_type=source_ig_type,
        )
        if result is not None:
            saved += 1
    return saved


async def run_post_scrape_for_universities(university_ids: list[int]) -> dict:
    """
    Scrape IG posts for specific universities (regardless of status).
    Skips universities without an ig_handle.

    Returns summary dict: {"scraped": int, "total_posts": int, "details": list}
    """
    universities = await get_universities_by_ids(university_ids)
    if not universities:
        return {"scraped": 0, "total_posts": 0, "details": []}

    scraped = 0
    total_posts = 0
    details: list[dict] = []
    loop = asyncio.get_running_loop()

    for uni in universities:
        handle = uni.get("ig_handle")
        if not handle:
            details.append({
                "university": uni["name"],
                "handle": None,
                "posts_found": 0,
                "posts_saved": 0,
                "mode": "skipped_no_handle",
            })
            continue

        try:
            # Check if already scraped — do deeper scrape if so
            known_urls = await get_post_urls_for_university(uni["id"])
            if known_urls:
                scrape_fn = partial(
                    scrape_ig_posts_with_fallback,
                    handle,
                    deeper=True,
                    known_post_urls=known_urls,
                )
                mode = "deeper"
            else:
                scrape_fn = partial(scrape_ig_posts_with_fallback, handle)
                mode = "initial"

            posts = await loop.run_in_executor(None, scrape_fn)
            saved = await _save_posts(uni["id"], posts, source_ig_handle=handle, source_ig_type="main")

            if uni.get("status") == "ig_found":
                await update_university_status(uni["id"], "ig_scraped")

            scraped += 1
            total_posts += saved
            details.append({
                "university": uni["name"],
                "handle": handle,
                "posts_found": len(posts),
                "posts_saved": saved,
                "posts_already_known": len(known_urls),
                "mode": mode,
            })
            log.info(
                "[Agent2] @%s: found %d posts, saved %d new, %d already in DB (targeted, %s)",
                handle, len(posts), saved, len(known_urls), mode,
            )

            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent2] Error scraping @%s: %s", handle, e)

    log.info("[Agent2] Targeted batch complete: scraped %d universities, %d posts saved", scraped, total_posts)
    return {"scraped": scraped, "total_posts": total_posts, "details": details}
