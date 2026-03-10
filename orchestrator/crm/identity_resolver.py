"""
Identity Resolver Agent — resolves full identity from name + university.

Primary source: PDDIKTI (dosen database), then DDG/web fallback.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, IdentityResult
from orchestrator.crm.tools import (
    ddg_search,
    gpt_extract_structured,
    pddikti_search_dosen,
    pddikti_get_dosen_profile,
    pddikti_get_dosen_study_history,
)


async def identity_resolver_agent(state: CrmState) -> dict:
    """
    Resolve PIC identity using PDDIKTI first, then web search.

    Returns partial state update with `identity`.
    """
    pic_name = state.get("pic_name", "")
    pic_title = state.get("pic_title", "")
    uni_name = state.get("university_name", "")

    log.info("[IdentityResolver] Starting for %s (%s) at %s", pic_name, pic_title, uni_name)

    result = IdentityResult()
    sources: list[str] = []

    # ── 1. PDDIKTI dosen search (PRIMARY — goldmine) ──────────────────
    dosen_id = None
    dosen_results = await pddikti_search_dosen(pic_name)
    if dosen_results:
        # Match by university name
        for d in dosen_results:
            nama_pt = (d.get("nama_pt") or "").lower()
            singkat_pt = (d.get("sinkatan_pt") or "").lower()
            if uni_name.lower() in nama_pt or uni_name.lower() in singkat_pt:
                dosen_id = d.get("id")
                result.full_name = d.get("nama")
                result.nidn = d.get("nidn")
                result.pddikti_dosen_id = dosen_id
                sources.append("pddikti_search")
                log.info("[IdentityResolver] PDDIKTI match: %s (NIDN: %s)", result.full_name, result.nidn)
                break

        # Fallback: if no exact match, try partial
        if not dosen_id and len(dosen_results) == 1:
            d = dosen_results[0]
            dosen_id = d.get("id")
            result.full_name = d.get("nama")
            result.nidn = d.get("nidn")
            result.pddikti_dosen_id = dosen_id
            result.confidence = 0.5  # Lower confidence for non-exact match
            sources.append("pddikti_search_partial")

    # ── 2. PDDIKTI profile (gender, jabatan, pendidikan) ──────────────
    if dosen_id:
        profile = await pddikti_get_dosen_profile(dosen_id)
        if profile:
            result.gender = profile.get("jenis_kelamin")
            sources.append("pddikti_profile")

    # ── 3. PDDIKTI study history (birth region inference, tenure) ──────
    if dosen_id:
        study_history = await pddikti_get_dosen_study_history(dosen_id)
        if study_history:
            # Infer origin from S1 location
            s1_entries = [s for s in study_history if s.get("jenjang") == "S1"]
            if s1_entries:
                s1 = s1_entries[0]
                s1_pt = s1.get("nama_pt", "")
                # Infer origin region from S1 university location
                if s1_pt and not result.origin_region:
                    origin = await _infer_origin_from_pt(s1_pt)
                    if origin:
                        result.origin_region = origin
                        result.origin_region_source = "inferred_from_s1"

                # Calculate tenure: years since first study entry
                first_year = s1.get("tahun_masuk")
                if first_year:
                    try:
                        result.confidence = max(result.confidence, 0.8)
                    except (ValueError, TypeError):
                        pass

            sources.append("pddikti_study_history")

    # ── 4. DDG search for birth info and personal details ──────────────
    if not result.birth_date or not result.origin_region:
        name_to_search = result.full_name or pic_name
        ddg_results = await ddg_search(
            f'"{name_to_search}" "{uni_name}" profil lahir OR "tanggal lahir" OR "tempat lahir"',
            max_results=5,
        )
        if ddg_results:
            combined = "\n".join(r.get("snippet", "") for r in ddg_results)
            extracted = await gpt_extract_structured(
                combined,
                (
                    f"Extract personal information about {name_to_search} from these search results:\n"
                    "Return JSON with keys:\n"
                    "- birth_date: date of birth (any format)\n"
                    "- birth_place: place of birth\n"
                    "- origin_region: origin region/city\n"
                    "- photo_url: photo URL if found\n"
                    "Return null for fields not found."
                ),
            )
            if extracted:
                if extracted.get("birth_date") and not result.birth_date:
                    result.birth_date = extracted["birth_date"]
                    result.birth_date_source = "ddg_search"
                if extracted.get("origin_region") and not result.origin_region:
                    result.origin_region = extracted["origin_region"]
                    result.origin_region_source = "ddg_search"
                if extracted.get("birth_place") and not result.origin_region:
                    result.origin_region = extracted["birth_place"]
                    result.origin_region_source = "ddg_search"
                if extracted.get("photo_url"):
                    result.photo_url = extracted["photo_url"]
            sources.append("ddg_personal")

    # ── 5. Compute age from birth_date ─────────────────────────────────
    if result.birth_date:
        age = _compute_age(result.birth_date)
        if age:
            result.age = age

    # ── Finalize ───────────────────────────────────────────────────────
    if not result.full_name:
        result.full_name = pic_name

    result.confidence = max(result.confidence, 0.3 if sources else 0.0)
    if "pddikti_search" in sources:
        result.confidence = max(result.confidence, 0.9)
    result.sources = sources

    log.info(
        "[IdentityResolver] Done for %s: name=%s, nidn=%s, confidence=%.2f",
        pic_name, result.full_name, result.nidn, result.confidence,
    )
    return {"identity": result}


async def _infer_origin_from_pt(pt_name: str) -> str | None:
    """Infer geographic origin from the university name."""
    # Common patterns: "Universitas Negeri Yogyakarta" → "Yogyakarta"
    city_patterns = [
        r'universitas\s+(?:negeri\s+)?(\w+)$',
        r'institut\s+teknologi\s+(\w+)$',
        r'universitas\s+(\w+)$',
    ]
    for pattern in city_patterns:
        match = re.search(pattern, pt_name, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _compute_age(birth_date_str: str) -> int | None:
    """Try to compute age from a date string."""
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y", "%d %B %Y", "%d %b %Y"]:
        try:
            bd = datetime.strptime(birth_date_str.strip(), fmt)
            today = datetime.now()
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            if 20 <= age <= 90:
                return age
        except ValueError:
            continue
    # Try just extracting a year
    year_match = re.search(r'(19[4-9]\d|20[0-2]\d)', birth_date_str)
    if year_match:
        year = int(year_match.group(1))
        age = datetime.now().year - year
        if 20 <= age <= 90:
            return age
    return None
