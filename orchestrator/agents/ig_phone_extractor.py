"""
Agent 3: Phone Extractor

Extracts phone numbers from ig_posts that haven't been processed yet.
Uses regex on captions (free) and GPT Vision OCR on images.
"""
import asyncio

from orchestrator.config import is_paused, log
from orchestrator.db import (
    add_ig_contact,
    get_unextracted_posts,
    mark_post_extracted,
    validate_phone,
)
from orchestrator.instagram import extract_phone_from_image, extract_phones_from_text


async def run_phone_extraction_batch(limit: int = 50) -> dict:
    """
    Extract phones from ig_posts where phone_extracted=0.

    Returns summary dict: {"processed": int, "phones_found": int, "details": list}
    """
    if is_paused():
        log.info("[Agent3] Bot is paused, skipping phone extraction")
        return {"processed": 0, "phones_found": 0, "details": []}

    posts = await get_unextracted_posts(limit=limit)
    if not posts:
        log.info("[Agent3] No unextracted posts to process")
        return {"processed": 0, "phones_found": 0, "details": []}

    processed = 0
    total_phones = 0
    details: list[dict] = []

    for post in posts:
        try:
            phones: set[str] = set()

            # Step 1: Regex on caption (free)
            caption = post.get("caption") or ""
            caption_phones = extract_phones_from_text(caption)
            for p in caption_phones:
                validated = validate_phone(p)
                if validated:
                    phones.add(validated)

            # Step 2: Vision OCR on image (if available)
            image_url = post.get("image_url")
            if image_url:
                try:
                    image_phones = await extract_phone_from_image(image_url, caption)
                    phones.update(image_phones)
                except Exception as e:
                    log.warning(
                        "[Agent3] Vision extraction failed for post %d: %s",
                        post["id"], e,
                    )

            # Save contacts (INSERT OR IGNORE handles dedup)
            saved = 0
            for phone in phones:
                result = await add_ig_contact(
                    university_id=post["university_id"],
                    phone_number=phone,
                    source_post_url=post.get("post_url"),
                    source_image_url=post.get("image_url"),
                )
                if result is not None:
                    saved += 1

            await mark_post_extracted(post["id"], len(phones))
            processed += 1
            total_phones += saved

            if phones:
                details.append({
                    "post_id": post["id"],
                    "university": post.get("university_name", ""),
                    "phones": list(phones),
                    "new_contacts": saved,
                })

            log.info(
                "[Agent3] Post %d: found %d phones, %d new contacts",
                post["id"], len(phones), saved,
            )

            await asyncio.sleep(1)  # Rate limit Vision API
        except Exception as e:
            log.error("[Agent3] Error processing post %d: %s", post["id"], e)

    log.info(
        "[Agent3] Batch complete: processed %d posts, %d new phones",
        processed, total_phones,
    )
    return {"processed": processed, "phones_found": total_phones, "details": details}
