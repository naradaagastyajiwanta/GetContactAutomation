"""
Agent 3: Phone Extractor

Extracts phone numbers with contact names from ig_posts that haven't been processed yet.
Uses GPT on captions and GPT Vision OCR on images.
Only saves contacts that have a real person's name (not generic names).
Deduplicates by contact name per university to avoid OCR-variant duplicates.
"""
import asyncio
import re

from orchestrator.config import is_paused, log
from orchestrator.db import (
    add_ig_contact,
    get_contacts_for_university,
    get_unextracted_posts,
    get_unextracted_posts_for_universities,
    mark_post_extracted,
)
from orchestrator.instagram import (
    extract_named_contacts_from_text,
    extract_phone_from_image,
    PhoneContact,
)


def _normalize_name(name: str) -> str:
    """Normalize a contact name for dedup comparison.

    Strips titles, punctuation, and lowercases so that
    'Dr. Anindya, S.Psi, K.' and 'dr. Anindya, S.Psi' match.
    """
    lower = name.lower().strip()
    # Remove common titles/degrees
    lower = re.sub(
        r'\b(dr|drs|prof|ir|s\.?psi|s\.?pd|s\.?sos|s\.?kom|s\.?e|'
        r'm\.?pd|m\.?si|m\.?kom|m\.?sc|ph\.?d|s\.?t|s\.?h|m\.?m|'
        r's\.?kep|ns|apt|k)\b\.?',
        '', lower,
    )
    # Remove punctuation and extra spaces
    lower = re.sub(r'[,.\-_()]+', ' ', lower)
    lower = re.sub(r'\s+', ' ', lower).strip()
    return lower


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

    # Build per-university set of already-saved normalized names for dedup
    saved_names_by_uni: dict[int, set[str]] = {}

    async def _get_saved_names(uni_id: int) -> set[str]:
        if uni_id not in saved_names_by_uni:
            existing = await get_contacts_for_university(uni_id)
            saved_names_by_uni[uni_id] = {
                _normalize_name(c["contact_name"])
                for c in existing
                if c.get("contact_name")
            }
        return saved_names_by_uni[uni_id]

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

            uni_id = post["university_id"]
            saved_names = await _get_saved_names(uni_id)

            # Save contacts (phone dedup via INSERT OR IGNORE, name dedup via set)
            saved = 0
            for contact in contacts:
                name = contact["name"]
                has_person_name = bool(name)  # empty string = no person name

                # Dedup by normalized name (only if name is not empty)
                if name:
                    norm_name = _normalize_name(name)
                    if norm_name in saved_names:
                        log.debug(
                            "[Agent3] Skipping duplicate name '%s' for uni %d",
                            name, uni_id,
                        )
                        continue

                result = await add_ig_contact(
                    university_id=uni_id,
                    phone_number=contact["phone"],
                    source_post_url=post.get("post_url"),
                    source_image_url=post.get("image_url"),
                    contact_name=name or None,
                    has_person_name=has_person_name,
                )
                if result is not None:
                    saved += 1
                    if name:
                        saved_names.add(_normalize_name(name))

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

            named = sum(1 for c in contacts if c["name"])
            log.info(
                "[Agent3] Post %d: found %d contacts (%d with name), %d new — %s",
                post["id"],
                len(contacts),
                named,
                saved,
                ", ".join(
                    f"{c['name'] or '(no name)'}={c['phone']}" for c in contacts
                ) or "none",
            )

            await asyncio.sleep(1)  # Rate limit Vision API
        except Exception as e:
            log.error("[Agent3] Error processing post %d: %s", post["id"], e)

    log.info(
        "[Agent3] Batch complete: processed %d posts, %d new named contacts",
        processed, total_phones,
    )
    return {"processed": processed, "phones_found": total_phones, "details": details}


async def run_phone_extraction_for_universities(university_ids: list[int]) -> dict:
    """
    Extract phones from unprocessed ig_posts for specific universities.

    Returns summary dict: {"processed": int, "phones_found": int, "details": list}
    """
    posts = await get_unextracted_posts_for_universities(university_ids)
    if not posts:
        return {"processed": 0, "phones_found": 0, "details": []}

    processed = 0
    total_phones = 0
    details: list[dict] = []
    saved_names_by_uni: dict[int, set[str]] = {}

    async def _get_saved_names(uni_id: int) -> set[str]:
        if uni_id not in saved_names_by_uni:
            existing = await get_contacts_for_university(uni_id)
            saved_names_by_uni[uni_id] = {
                _normalize_name(c["contact_name"])
                for c in existing
                if c.get("contact_name")
            }
        return saved_names_by_uni[uni_id]

    for post in posts:
        try:
            contacts: list[PhoneContact] = []
            caption = post.get("caption") or ""
            image_url = post.get("image_url")

            if image_url:
                try:
                    contacts = await extract_phone_from_image(image_url, caption)
                except Exception as e:
                    log.warning("[Agent3] Vision extraction failed for post %d: %s", post["id"], e)
            else:
                contacts = await extract_named_contacts_from_text(caption)

            uni_id = post["university_id"]
            saved_names = await _get_saved_names(uni_id)

            saved = 0
            for contact in contacts:
                name = contact["name"]
                has_person_name = bool(name)

                if name:
                    norm_name = _normalize_name(name)
                    if norm_name in saved_names:
                        continue

                result = await add_ig_contact(
                    university_id=uni_id,
                    phone_number=contact["phone"],
                    source_post_url=post.get("post_url"),
                    source_image_url=post.get("image_url"),
                    contact_name=name or None,
                    has_person_name=has_person_name,
                )
                if result is not None:
                    saved += 1
                    if name:
                        saved_names.add(_normalize_name(name))

            await mark_post_extracted(post["id"], len(contacts))
            processed += 1
            total_phones += saved

            if contacts:
                details.append({
                    "post_id": post["id"],
                    "university": post.get("university_name", ""),
                    "contacts": [{"phone": c["phone"], "name": c["name"]} for c in contacts],
                    "new_contacts": saved,
                })

            await asyncio.sleep(1)
        except Exception as e:
            log.error("[Agent3] Error processing post %d: %s", post["id"], e)

    log.info("[Agent3] Targeted batch complete: processed %d posts, %d new contacts", processed, total_phones)
    return {"processed": processed, "phones_found": total_phones, "details": details}
