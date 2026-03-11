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
    earliest_study_year: int | None = None

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

            # Track earliest enrollment for birth date cross-validation
            all_years = []
            for s in study_history:
                for key in ("tahun_masuk", "tahun_lulus"):
                    y = s.get(key)
                    if y:
                        try:
                            all_years.append(int(str(y)[:4]))
                        except (ValueError, TypeError):
                            pass
            earliest_study_year = min(all_years) if all_years else None

            sources.append("pddikti_study_history")

    # ── 3b. NIDN date parsing (standard format: DDMMYYNNNN) ─────────────
    if result.nidn and not result.birth_date:
        parsed = _parse_nidn_birth(result.nidn, min_birth_year=(earliest_study_year - 17) if earliest_study_year else None)
        if parsed:
            result.birth_date = parsed
            result.birth_date_source = "nidn_parsed"
            log.info("[IdentityResolver] Birth date from NIDN: %s", parsed)

    # ── 4. DDG search for birth info and personal details ──────────────
    if not result.birth_date or not result.origin_region:
        name_to_search = result.full_name or pic_name
        # Try multiple query strategies for better coverage
        ddg_queries = [
            f'"tanggal lahir" "{name_to_search}" "{uni_name}"',
            f'"{name_to_search}" lahir OR "tempat tanggal lahir" dosen',
        ]
        if result.nidn:
            ddg_queries.append(f'"{result.nidn}" "tanggal lahir" OR lahir')
        all_snippets = []
        for q in ddg_queries:
            if result.birth_date:  # Already found in a previous query
                break
            ddg_results = await ddg_search(q, max_results=5)
            if ddg_results:
                all_snippets.extend(r.get("snippet", "") for r in ddg_results)
        ddg_results = bool(all_snippets)  # reuse name to keep downstream code working
        if ddg_results:
            combined = "\n".join(all_snippets)
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

    # ── 4b. Gemini grounded research for birth/origin (fills DDG gaps) ─
    if not result.birth_date or not result.origin_region:
        name_to_search = result.full_name or pic_name
        # Build education context for the Gemini prompt to constrain answers
        edu_context = ""
        if earliest_study_year:
            edu_context = (
                f"Data pendidikan dari PDDIKTI: mulai kuliah S1 tahun {earliest_study_year}. "
                f"Artinya orang ini lahir sekitar tahun {earliest_study_year - 22} sampai {earliest_study_year - 17}. "
            )
        nidn_hint = ""
        if result.nidn:
            nidn_hint = f"NIDN: {result.nidn}. "
        gemini_q = (
            f"Cari tanggal lahir dan tempat lahir {name_to_search}, "
            f"dosen di {uni_name}. "
            f"{nidn_hint}"
            f"{edu_context}"
            f"PENTING:\n"
            f"- Hanya jawab berdasarkan FAKTA dari sumber resmi (SINTA, kampus, jurnal, berita).\n"
            f"- Jangan mengarang atau menebak tanggal lahir.\n"
            f"- Jika tidak ditemukan fakta pasti, jawab 'tidak ditemukan'.\n"
            f"Jawab dalam format:\n"
            f"Tanggal lahir: ...\n"
            f"Tempat lahir: ...\n"
            f"Asal daerah: ..."
        )
        from orchestrator.crm.tools import gemini_research
        gemini_resp = await gemini_research(gemini_q)
        if gemini_resp and gemini_resp.get("text"):
            gpt_parsed = await gpt_extract_structured(
                gemini_resp["text"],
                (
                    f"Extract personal identity information about {name_to_search}:\n"
                    "Return JSON with keys:\n"
                    "- birth_date: date of birth (format YYYY-MM-DD or any)\n"
                    "- birth_place: place/city of birth\n"
                    "- origin_region: home region/province\n"
                    "Return null for fields not found or uncertain."
                ),
            )
            if gpt_parsed:
                if gpt_parsed.get("birth_date") and not result.birth_date:
                    result.birth_date = gpt_parsed["birth_date"]
                    result.birth_date_source = "gemini_grounded"
                if gpt_parsed.get("origin_region") and not result.origin_region:
                    result.origin_region = gpt_parsed["origin_region"]
                    result.origin_region_source = "gemini_grounded"
                if gpt_parsed.get("birth_place") and not result.origin_region:
                    result.origin_region = gpt_parsed["birth_place"]
                    result.origin_region_source = "gemini_grounded"
            sources.append("gemini_personal")

    # ── 5. Compute age from birth_date (with cross-validation) ──────────
    # earliest_study_year → person was at least 17 at that time
    min_birth_year = (earliest_study_year - 17) if earliest_study_year else None
    if result.birth_date:
        age = _compute_age(result.birth_date, min_birth_year=min_birth_year)
        if age:
            result.age = age
        else:
            # Birth date failed cross-validation — discard it
            log.warning(
                "[IdentityResolver] Birth date %s rejected (min_birth_year=%s)",
                result.birth_date, min_birth_year,
            )
            result.birth_date = None
            result.birth_date_source = None

    # ── 5b. Age estimation fallback from education history ─────────────
    if not result.age and earliest_study_year:
        # Assume ~18 years old at S1 enrollment (typical in Indonesia)
        estimated_birth_year = earliest_study_year - 18
        result.age = datetime.now().year - estimated_birth_year
        if not result.birth_date:
            result.birth_date = f"~{estimated_birth_year}"
            result.birth_date_source = "estimated_from_education"
        log.info(
            "[IdentityResolver] Age estimated from S1 enrollment %d → ~%d years old",
            earliest_study_year, result.age,
        )

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


def _parse_nidn_birth(nidn: str, min_birth_year: int | None = None) -> str | None:
    """
    Parse birth date from NIDN (standard format: DDMMYYNNNN).

    Indonesian NIDN encodes birth date in the first 6 digits:
      DD = day (01–31)
      MM = month (01–12 for male, 41–52 for female → subtract 40)
      YY = last 2 digits of birth year

    Returns date string like "5 Juni 1970" or None if invalid.
    """
    if not nidn or len(nidn) != 10 or not nidn.isdigit():
        return None

    dd = int(nidn[0:2])
    mm_raw = int(nidn[2:4])
    yy = int(nidn[4:6])

    # Female lecturers: month + 40 (same as NIP convention)
    if mm_raw > 40:
        mm = mm_raw - 40
    else:
        mm = mm_raw

    if not (1 <= dd <= 31 and 1 <= mm <= 12):
        return None

    # Determine century: if YY > 30 → 1900s, else 2000s
    # (Indonesia has no active lecturers born after 2005)
    year = 1900 + yy if yy > 30 else 2000 + yy

    # Cross-validate against education history
    if min_birth_year and year > min_birth_year:
        log.info(
            "[IdentityResolver] NIDN birth year %d rejected (min_birth_year=%d)",
            year, min_birth_year,
        )
        return None

    # Sanity check: age between 25 and 90
    current_year = datetime.now().year
    age = current_year - year
    if not (25 <= age <= 90):
        return None

    indo_months = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ]

    return f"{dd} {indo_months[mm]} {year}"


_INDO_MONTHS = {
    "januari": "January", "februari": "February", "maret": "March",
    "april": "April", "mei": "May", "juni": "June",
    "juli": "July", "agustus": "August", "september": "September",
    "oktober": "October", "november": "November", "desember": "December",
}


def _compute_age(birth_date_str: str, min_birth_year: int | None = None) -> int | None:
    """Try to compute age from a date string.
    
    If min_birth_year is set (e.g. from S1 graduation), reject dates
    that would make the person impossibly young.
    """
    # Normalize Indonesian month names to English
    normalized = birth_date_str.strip()
    for indo, eng in _INDO_MONTHS.items():
        normalized = re.sub(indo, eng, normalized, flags=re.IGNORECASE)

    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y", "%d %B %Y", "%d %b %Y"]:
        try:
            bd = datetime.strptime(normalized, fmt)
            today = datetime.now()
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            if 20 <= age <= 90:
                if min_birth_year and bd.year > min_birth_year:
                    continue  # Birth year too late — impossible
                return age
        except ValueError:
            continue
    # Try just extracting a year
    year_match = re.search(r'(19[4-9]\d|20[0-2]\d)', normalized)
    if year_match:
        year = int(year_match.group(1))
        if min_birth_year and year > min_birth_year:
            return None  # Too young
        age = datetime.now().year - year
        if 20 <= age <= 90:
            return age
    return None
