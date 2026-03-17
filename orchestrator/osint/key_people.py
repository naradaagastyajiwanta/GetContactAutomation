"""
Key People Finder Agent — identifies key people at the university.

Skips rector (already in DB), focuses on: vice-rectors, deans,
department heads, PR/humas contacts.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.osint.state import OsintState, KeyPeopleResult, KeyPerson
from orchestrator.osint.tools import (
    ddg_search,
    fetch_page,
    extract_text_from_html,
    gpt_extract_structured,
    pddikti_search_dosen,
    pddikti_get_dosen_profile,
)


async def key_people_agent(state: OsintState) -> dict:
    """
    Identify key people (leadership, department heads, PR contacts).

    Returns partial state update with `key_people`.
    """
    uni = state.get("university_data", {})
    uni_name = state.get("university_name", uni.get("name", ""))
    website = uni.get("website", "")
    rector_name = uni.get("rector_name", "")
    existing_contacts = state.get("existing_contacts", [])
    existing_ig = state.get("existing_ig_contacts", [])

    log.info("[KeyPeople] Starting for %s", uni_name)

    # Existing known names (to avoid re-discovering)
    known_names = set()
    if rector_name:
        known_names.add(rector_name.lower())
    for c in existing_contacts:
        name = c.get("name") or c.get("contact_name") or ""
        if name:
            known_names.add(name.lower())

    people: list[KeyPerson] = []

    # ── 1. Website leadership page ─────────────────────────────────────
    if website:
        for path in ["/pimpinan", "/profil/pimpinan", "/tentang/pimpinan", "/struktur-organisasi"]:
            url = website.rstrip("/") + path
            html = await fetch_page(url)
            if html:
                text = extract_text_from_html(html, max_chars=12000)
                extracted = await gpt_extract_structured(
                    text,
                    (
                        "Extract all key people (leaders/officials) from this university page.\n"
                        "Return JSON with key 'people' containing an array of objects:\n"
                        '  [{"name": "...", "title": "...", "department": "...", "email": "...", "phone": "..."}]\n'
                        "Include: rectors, vice-rectors, deans, department heads, secretary, PR/humas.\n"
                        "Return null for fields not found."
                    ),
                )
                if extracted and extracted.get("people"):
                    for p in extracted["people"]:
                        name = p.get("name", "")
                        if name and name.lower() not in known_names:
                            people.append(KeyPerson(
                                name=name,
                                title=p.get("title"),
                                department=p.get("department"),
                                phone=p.get("phone"),
                                email=p.get("email"),
                                source="website",
                                source_url=url,
                                confidence=0.8,
                            ))
                            known_names.add(name.lower())
                    log.info("[KeyPeople] Found %d people from %s", len(extracted["people"]), path)
                    break  # Found leadership page, no need to try more paths

    # ── 2. DDG search for specific roles ───────────────────────────────
    role_queries = [
        (f'"wakil rektor" "{uni_name}" 2024 OR 2025', "Wakil Rektor"),
        (f'"humas" OR "public relation" "{uni_name}" kontak', "Humas"),
        (f'"kabag akademik" OR "kepala bagian" "{uni_name}"', "Kabag"),
    ]

    for query, role_hint in role_queries:
        if len(people) >= 15:
            break
        results = await ddg_search(query, max_results=3)
        if results:
            combined_snippets = "\n".join(
                f"Title: {r.get('title', '')}\nSnippet: {r.get('snippet', '')}"
                for r in results
            )
            extracted = await gpt_extract_structured(
                combined_snippets,
                (
                    f"From these search results about {uni_name}, extract people who hold the role of {role_hint}.\n"
                    "Return JSON with key 'people': [{\"name\": \"...\", \"title\": \"...\"}]\n"
                    "Only include people clearly identified. Return empty array if none found."
                ),
            )
            if extracted and extracted.get("people"):
                for p in extracted["people"]:
                    name = p.get("name", "")
                    if name and name.lower() not in known_names:
                        people.append(KeyPerson(
                            name=name,
                            title=p.get("title") or role_hint,
                            source="ddg_search",
                            source_url=results[0].get("link"),
                            confidence=0.5,
                        ))
                        known_names.add(name.lower())

    # ── 3. Verify people via PDDIKTI (if they're lecturers) ───────────
    for person in people[:5]:  # Limit PDDIKTI calls
        if person.name and not person.phone:
            try:
                dosen_results = await pddikti_search_dosen(person.name)
                for d in dosen_results:
                    # Match by university name
                    if uni_name.lower() in (d.get("nama_pt", "") or "").lower():
                        profile = await pddikti_get_dosen_profile(d.get("id", ""))
                        if profile:
                            person.confidence = max(person.confidence, 0.9)
                            if not person.title:
                                person.title = profile.get("jabatan_akademik")
                        break
            except Exception as e:
                log.debug("[KeyPeople] PDDIKTI verification failed for %s: %s", person.name, e)

    log.info("[KeyPeople] Done for %s: %d new people found", uni_name, len(people))
    return {"key_people": KeyPeopleResult(people=people)}
