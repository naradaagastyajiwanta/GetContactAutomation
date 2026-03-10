"""
Contact Enricher Agent — aggregates and validates all contacts found
from other agents + existing DB data.

Merges, deduplicates, normalizes phone numbers, and assigns priority.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.db import validate_phone
from orchestrator.osint.state import (
    OsintState,
    ContactEnrichResult,
    EnrichedContact,
)


async def contact_enricher_agent(state: OsintState) -> dict:
    """
    Aggregate contacts from all sources, deduplicate, and rank.

    Returns partial state update with `enriched_contacts`.
    """
    uni_name = state.get("university_name", "")
    existing_contacts = state.get("existing_contacts", [])
    existing_ig = state.get("existing_ig_contacts", [])
    key_people = state.get("key_people")
    web_profile = state.get("web_profile")

    log.info("[ContactEnricher] Starting for %s", uni_name)

    contacts_map: dict[str, EnrichedContact] = {}

    # ── 1. Load existing DB contacts ──────────────────────────────────
    for c in existing_contacts:
        key = _contact_key(c.get("name"), c.get("phone"))
        if key:
            contacts_map[key] = EnrichedContact(
                name=c.get("name"),
                title=c.get("title"),
                department=c.get("department"),
                phone=c.get("phone"),
                email=c.get("email"),
                source="db_osint_contacts",
                confidence=c.get("confidence", 0.5),
                priority=c.get("priority", 0),
            )

    # ── 2. Load existing IG contacts ──────────────────────────────────
    for c in existing_ig:
        phone = c.get("phone_number")
        name = c.get("contact_name")
        key = _contact_key(name, phone)
        if key and key not in contacts_map:
            contacts_map[key] = EnrichedContact(
                name=name,
                phone=phone,
                source="db_ig_contacts",
                source_url=c.get("source_post_url"),
                confidence=0.6,
                priority=1,
            )

    # ── 3. Add key people from OSINT ──────────────────────────────────
    if key_people:
        for p in key_people.people:
            key = _contact_key(p.name, p.phone)
            if key:
                if key in contacts_map:
                    # Merge: upgrade confidence if seen in multiple sources
                    existing = contacts_map[key]
                    existing.confidence = min(1.0, existing.confidence + 0.2)
                    if p.title and not existing.title:
                        existing.title = p.title
                    if p.email and not existing.email:
                        existing.email = p.email
                    if p.department and not existing.department:
                        existing.department = p.department
                else:
                    contacts_map[key] = EnrichedContact(
                        name=p.name,
                        title=p.title,
                        department=p.department,
                        phone=p.phone,
                        email=p.email,
                        source=p.source,
                        source_url=p.source_url,
                        confidence=p.confidence,
                        priority=_role_priority(p.title),
                    )

    # ── 4. Add contacts from web profile ──────────────────────────────
    if web_profile:
        if web_profile.phone_official:
            key = _contact_key("Official", web_profile.phone_official)
            if key and key not in contacts_map:
                contacts_map[key] = EnrichedContact(
                    name="Sekretariat",
                    phone=web_profile.phone_official,
                    source="website",
                    confidence=0.8,
                    priority=8,
                )
        if web_profile.email_official:
            key = f"email:{web_profile.email_official.lower()}"
            if key not in contacts_map:
                contacts_map[key] = EnrichedContact(
                    name="Official Email",
                    email=web_profile.email_official,
                    source="website",
                    confidence=0.8,
                    priority=7,
                )

    # ── 5. Normalize phone numbers ────────────────────────────────────
    for contact in contacts_map.values():
        if contact.phone:
            normalized = validate_phone(contact.phone)
            if normalized:
                contact.phone = normalized

    # ── 6. Sort by priority and confidence ────────────────────────────
    all_contacts = sorted(
        contacts_map.values(),
        key=lambda c: (c.priority, c.confidence),
        reverse=True,
    )

    log.info("[ContactEnricher] Done for %s: %d total contacts", uni_name, len(all_contacts))
    return {"enriched_contacts": ContactEnrichResult(contacts=all_contacts)}


def _contact_key(name: str | None, phone: str | None) -> str | None:
    """Generate a dedup key from name + phone."""
    if phone:
        cleaned = phone.strip().replace(" ", "").replace("-", "")
        return f"phone:{cleaned}"
    if name:
        return f"name:{name.strip().lower()}"
    return None


def _role_priority(title: str | None) -> int:
    """Assign a priority score based on role/title (higher = more important)."""
    if not title:
        return 0
    t = title.lower()
    if any(k in t for k in ["rektor", "rector", "president"]):
        return 10
    if any(k in t for k in ["wakil rektor", "vice rector"]):
        return 9
    if any(k in t for k in ["sekretaris", "secretary"]):
        return 8
    if any(k in t for k in ["dekan", "dean"]):
        return 7
    if any(k in t for k in ["humas", "public relation", "pr"]):
        return 7
    if any(k in t for k in ["kabag", "kepala bagian", "head"]):
        return 6
    if any(k in t for k in ["ketua", "koordinator"]):
        return 5
    return 3
