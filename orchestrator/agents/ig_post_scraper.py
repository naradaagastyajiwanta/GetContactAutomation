"""
Agent 2: IG Post Scraper

Smart-scrapes Instagram posts via Web API (browser session cookie).
Only returns posts likely to contain phone numbers:
  - Bio with phone number
  - Posts with phone number in caption
  - Event flyer / poster posts (keywords match)
Saves posts to ig_posts table for phone extraction later.
"""
import asyncio

from orchestrator.config import is_paused, log, cfg
from orchestrator.db import (
    add_ig_post,
    get_universities_by_status,
    update_university_status,
)
from orchestrator.instagram import scrape_ig_posts_sync


async def run_post_scrape_batch(limit: int = 20) -> dict:
    """
    Scrape IG posts for universities in 'ig_found' status.

    Returns summary dict: {"scraped": int, "total_posts": int, "details": list}
    """
    if is_paused():
        log.info("[Agent2] Bot is paused, skipping post scraping")
        return {"scraped": 0, "total_posts": 0, "details": []}

    universities = await get_universities_by_status("ig_found", limit=limit)
    if not universities:
        log.info("[Agent2] No ig_found universities to scrape")
        return {"scraped": 0, "total_posts": 0, "details": []}

    scraped = 0
    total_posts = 0
    details: list[dict] = []
    loop = asyncio.get_event_loop()

    for uni in universities:
        handle = uni.get("ig_handle")
        if not handle:
            continue

        try:
            # scrape_ig_posts_sync is sync — run in executor
            posts = await loop.run_in_executor(
                None, scrape_ig_posts_sync, handle
            )
            saved = 0

            for post in posts:
                result = await add_ig_post(
                    university_id=uni["id"],
                    post_url=post["post_url"],
                    image_url=post.get("image_url"),
                    caption=post.get("caption"),
                    post_timestamp=post.get("timestamp"),
                )
                if result is not None:
                    saved += 1

            await update_university_status(uni["id"], "ig_scraped")
            scraped += 1
            total_posts += saved
            details.append({
                "university": uni["name"],
                "handle": handle,
                "posts_found": len(posts),
                "posts_saved": saved,
            })
            log.info(
                "[Agent2] @%s: scraped %d posts, saved %d new",
                handle, len(posts), saved,
            )

            # Delay between profiles to avoid rate limiting
            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent2] Error scraping @%s: %s", handle, e)

    log.info(
        "[Agent2] Batch complete: scraped %d universities, %d posts saved",
        scraped, total_posts,
    )
    return {"scraped": scraped, "total_posts": total_posts, "details": details}
