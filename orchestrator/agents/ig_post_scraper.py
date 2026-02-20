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
    get_post_urls_for_university,
    get_universities_by_status,
    update_university_status,
)
from orchestrator.instagram import scrape_ig_posts_sync

# Universities with fewer contacts than this will be re-scraped deeper
MIN_CONTACTS_FOR_RESCRAPE = 5


async def run_post_scrape_batch(limit: int = 20) -> dict:
    """
    Scrape IG posts for universities in 'ig_found' status.
    Also re-scrapes 'ig_scraped' universities that have < MIN_CONTACTS
    contacts, fetching deeper (older) posts.

    Returns summary dict: {"scraped": int, "total_posts": int, "details": list}
    """
    if is_paused():
        log.info("[Agent2] Bot is paused, skipping post scraping")
        return {"scraped": 0, "total_posts": 0, "details": []}

    # Primary: universities that have never been scraped
    universities = await get_universities_by_status("ig_found", limit=limit)

    # Secondary: already-scraped universities with too few contacts — deeper scrape
    rescrape_unis: list[dict] = []
    remaining = limit - len(universities)
    if remaining > 0:
        candidates = await get_universities_by_status("ig_scraped", limit=remaining)
        for uni in candidates:
            contacts = await get_contacts_for_university(uni["id"])
            if len(contacts) < MIN_CONTACTS_FOR_RESCRAPE:
                rescrape_unis.append(uni)

    if not universities and not rescrape_unis:
        log.info("[Agent2] No universities to scrape")
        return {"scraped": 0, "total_posts": 0, "details": []}

    scraped = 0
    total_posts = 0
    details: list[dict] = []
    loop = asyncio.get_running_loop()

    # --- First-time scrape (ig_found) ---
    for uni in universities:
        handle = uni.get("ig_handle")
        if not handle:
            continue

        try:
            posts = await loop.run_in_executor(
                None, scrape_ig_posts_sync, handle
            )
            saved = await _save_posts(uni["id"], posts)

            await update_university_status(uni["id"], "ig_scraped")
            scraped += 1
            total_posts += saved
            details.append({
                "university": uni["name"],
                "handle": handle,
                "posts_found": len(posts),
                "posts_saved": saved,
                "mode": "initial",
            })
            log.info(
                "[Agent2] @%s: scraped %d posts, saved %d new",
                handle, len(posts), saved,
            )

            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent2] Error scraping @%s: %s", handle, e)

    # --- Deeper re-scrape (ig_scraped with few contacts) ---
    for uni in rescrape_unis:
        handle = uni.get("ig_handle")
        if not handle:
            continue

        try:
            known_urls = await get_post_urls_for_university(uni["id"])
            log.info(
                "[Agent2] Re-scraping @%s deeper (%d posts already known)",
                handle, len(known_urls),
            )

            scrape_fn = partial(
                scrape_ig_posts_sync,
                handle,
                deeper=True,
                known_post_urls=known_urls,
            )
            posts = await loop.run_in_executor(None, scrape_fn)
            saved = await _save_posts(uni["id"], posts)

            scraped += 1
            total_posts += saved
            details.append({
                "university": uni["name"],
                "handle": handle,
                "posts_found": len(posts),
                "posts_saved": saved,
                "mode": "deeper",
            })
            log.info(
                "[Agent2] @%s: deeper scrape found %d posts, saved %d new",
                handle, len(posts), saved,
            )

            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("[Agent2] Error re-scraping @%s: %s", handle, e)

    log.info(
        "[Agent2] Batch complete: scraped %d universities, %d posts saved",
        scraped, total_posts,
    )
    return {"scraped": scraped, "total_posts": total_posts, "details": details}


async def _save_posts(university_id: int, posts: list[dict]) -> int:
    """Save posts to DB, return count of newly inserted rows."""
    saved = 0
    for post in posts:
        result = await add_ig_post(
            university_id=university_id,
            post_url=post["post_url"],
            image_url=post.get("image_url"),
            caption=post.get("caption"),
            post_timestamp=post.get("timestamp"),
        )
        if result is not None:
            saved += 1
    return saved
