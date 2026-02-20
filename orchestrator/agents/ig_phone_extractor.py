"""
Agent 3: Phone Extractor

Extracts phone numbers with contact names from ig_posts that haven't been processed yet.
Uses GPT on captions and GPT Vision OCR on images.
Only saves contacts that have a real person's name (not generic names).
"""
import asyncio

from orchestrator.config import is_paused, log
from orchestrator.db import (
    add_ig_contact,
    get_unextracted_posts,
    mark_post_extracted,
)
from orchestrator.instagram import (
    extract_named_contacts_from_text,
    extract_phone_from_image,
    PhoneContact,
)


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
            contacts: list[PhoneContact] = []
            caption = post.get("caption") or ""
            image_url = post.get("image_url")

            if image_url:
                # Image post: extract from both image and caption via GPT
                try:
                    contacts = await extract_phone_from_image(image_url, caption)
                except Exception as e:
                    log.warning(
                        "[Agent3] Vision extraction failed for post %d: %s",
                        post["id"], e,
                    )
            else:
                # No image (e.g. bio): extract named contacts from text only
                contacts = await extract_named_contacts_from_text(caption)

            # Save contacts (INSERT OR IGNORE handles dedup)
            saved = 0
            for contact in contacts:
                result = await add_ig_contact(
                    university_id=post["university_id"],
                    phone_number=contact["phone"],
                    source_post_url=post.get("post_url"),
                    source_image_url=post.get("image_url"),
                    contact_name=contact["name"],
                )
                if result is not None:
                    saved += 1

            await mark_post_extracted(post["id"], len(contacts))
            processed += 1
            total_phones += saved

            if contacts:
                details.append({
                    "post_id": post["id"],
                    "university": post.get("university_name", ""),
                    "contacts": [
                        {"phone": c["phone"], "name": c["name"]} for c in contacts
                    ],
                    "new_contacts": saved,
                })

            log.info(
                "[Agent3] Post %d: found %d named contacts (%s), %d new",
                post["id"],
                len(contacts),
                ", ".join(f"{c['name']}={c['phone']}" for c in contacts) or "none",
                saved,
            )

            await asyncio.sleep(1)  # Rate limit Vision API
        except Exception as e:
            log.error("[Agent3] Error processing post %d: %s", post["id"], e)

    log.info(
        "[Agent3] Batch complete: processed %d posts, %d new named contacts",
        processed, total_phones,
    )
    return {"processed": processed, "phones_found": total_phones, "details": details}
