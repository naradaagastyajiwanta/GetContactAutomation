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
from orchestrator.crm.name_utils import strip_academic_titles, ai_strip_titles, build_name_variants
from orchestrator.crm.tools import (
    ddg_search,
    fetch_page,
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
    collected_urls: dict[str, list[str]] = {}  # field → urls
    earliest_study_year: int | None = None

    # ── Build name variants for agentic retry ──────────────────────────
    name_variants = build_name_variants(pic_name)
    cleaned_name = await ai_strip_titles(pic_name)
    log.info("[IdentityResolver] AI-cleaned name: '%s', variants: %s", cleaned_name, name_variants[:5])

    # ── 1. PDDIKTI dosen search (PRIMARY — goldmine) ──────────────────
    # Try multiple name variants until we get a match
    dosen_id = None
    for variant_idx, search_name in enumerate(name_variants):
        if dosen_id:
            break
        log.info("[IdentityResolver] PDDIKTI attempt %d/%d: '%s'", variant_idx + 1, len(name_variants), search_name)
        dosen_results = await pddikti_search_dosen(search_name)
        if not dosen_results:
            continue

        # AI-based matching: let AI pick the correct dosen from results
        if len(dosen_results) == 1:
            # Single result — still verify with AI
            d = dosen_results[0]
            candidates_text = (
                f"Name: {d.get('nama', 'N/A')}, "
                f"University: {d.get('nama_pt', 'N/A')} ({d.get('sinkatan_pt', '')}), "
                f"NIDN: {d.get('nidn', 'N/A')}"
            )
        else:
            candidates_text = "\n".join(
                f"[{i+1}] Name: {d.get('nama', 'N/A')}, "
                f"University: {d.get('nama_pt', 'N/A')} ({d.get('sinkatan_pt', '')}), "
                f"NIDN: {d.get('nidn', 'N/A')}"
                for i, d in enumerate(dosen_results)
            )

        ai_match = await gpt_extract_structured(
            candidates_text,
            (
                f"We're looking for a lecturer named '{cleaned_name}' "
                f"(role: {pic_title}) at '{uni_name}'.\n"
                f"From the PDDIKTI results below, which one is the correct person?\n\n"
                f"IMPORTANT: In Indonesian academia, PDDIKTI lists a lecturer's HOME "
                f"institution (where they are formally registered), which may DIFFER "
                f"from where they currently serve. A lecturer registered at University A "
                f"can hold positions (Dekan, Wakil Dekan, Dosen Tamu, etc.) at University B. "
                f"Therefore:\n"
                f"- NAME MATCH is the PRIMARY criterion\n"
                f"- University match is a SOFT bonus signal, not a requirement\n"
                f"- If the name matches well but university differs, still accept with moderate confidence\n\n"
                f"Return JSON: {{\"best_index\": <1-based index or null>, "
                f"\"confidence\": <0.0-1.0>, \"reason\": \"...\"}}\n"
                f"Return null for best_index ONLY if the name clearly does not match any candidate."
            ),
        )

        if ai_match and ai_match.get("best_index"):
            idx = ai_match["best_index"] - 1
            if 0 <= idx < len(dosen_results):
                d = dosen_results[idx]
                dosen_id = d.get("id")
                result.full_name = d.get("nama")
                result.nidn = d.get("nidn")
                result.pddikti_dosen_id = dosen_id
                ai_conf = ai_match.get("confidence", 0.7)
                result.confidence = ai_conf
                pddikti_url = f"https://pddikti.kemdiktisaintek.go.id/data_dosen/{dosen_id}"
                collected_urls["full_name"] = [pddikti_url]
                collected_urls["nidn"] = [pddikti_url]
                sources.append("pddikti_search")
                log.info(
                    "[IdentityResolver] PDDIKTI AI match (variant '%s'): %s (NIDN: %s, confidence: %.2f, reason: %s)",
                    search_name, result.full_name, result.nidn, ai_conf, ai_match.get("reason", ""),
                )

    if not dosen_id:
        log.warning("[IdentityResolver] PDDIKTI: no match after %d variants", len(name_variants))

    # ── 2. PDDIKTI profile (gender, jabatan, pendidikan, photo) ──────
    if dosen_id:
        pddikti_url = f"https://pddikti.kemdiktisaintek.go.id/data_dosen/{dosen_id}"
        profile = await pddikti_get_dosen_profile(dosen_id)
        if profile:
            result.gender = profile.get("jenis_kelamin")
            if result.gender:
                collected_urls["gender"] = [pddikti_url]
            # PDDIKTI sometimes has photo URL
            pddikti_photo = profile.get("foto") or profile.get("photo_url") or profile.get("foto_url")
            if pddikti_photo and pddikti_photo.startswith("http"):
                result.photo_url = pddikti_photo
                collected_urls["photo_url"] = [pddikti_url]
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
                        collected_urls.setdefault("origin_region", []).append(pddikti_url)

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
        # Use cleaned name (no titles) for DDG — titles pollute search results
        name_to_search = result.full_name or cleaned_name
        # Try multiple query strategies with progressively relaxed names
        ddg_queries = [
            f'"tanggal lahir" "{name_to_search}" "{uni_name}"',
            f'"{name_to_search}" lahir OR "tempat tanggal lahir" dosen',
        ]
        # Also try cleaned variant if different from name_to_search
        if cleaned_name.lower() != name_to_search.lower():
            ddg_queries.append(f'"tanggal lahir" "{cleaned_name}" "{uni_name}"')
        if result.nidn:
            ddg_queries.append(f'"{result.nidn}" "tanggal lahir" OR lahir')
        # Broadest fallback: shorter name + university
        short_variants = [v for v in name_variants if v.lower() != name_to_search.lower() and len(v.split()) <= 2]
        for sv in short_variants[:1]:
            ddg_queries.append(f'"{sv}" lahir dosen "{uni_name}"')
        all_snippets = []
        ddg_links: list[str] = []
        for q in ddg_queries:
            if result.birth_date:  # Already found in a previous query
                break
            ddg_results = await ddg_search(q, max_results=5)
            if ddg_results:
                all_snippets.extend(r.get("snippet", "") for r in ddg_results)
                ddg_links.extend(r.get("link", "") for r in ddg_results if r.get("link"))
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
                    collected_urls.setdefault("birth_date", []).extend(ddg_links)
                if extracted.get("origin_region") and not result.origin_region:
                    result.origin_region = extracted["origin_region"]
                    result.origin_region_source = "ddg_search"
                    collected_urls.setdefault("origin_region", []).extend(ddg_links)
                if extracted.get("birth_place") and not result.origin_region:
                    result.origin_region = extracted["birth_place"]
                    result.origin_region_source = "ddg_search"
                    collected_urls.setdefault("origin_region", []).extend(ddg_links)
                if extracted.get("photo_url"):
                    result.photo_url = extracted["photo_url"]
            sources.append("ddg_personal")

    # ── 4b. Gemini grounded research for birth/origin (fills DDG gaps) ─
    if not result.birth_date or not result.origin_region:
        name_to_search = result.full_name or cleaned_name
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
        gemini_urls = [u for u in (gemini_resp.get("urls") or []) if u] if gemini_resp else []
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
                    collected_urls.setdefault("birth_date", []).extend(gemini_urls)
                if gpt_parsed.get("origin_region") and not result.origin_region:
                    result.origin_region = gpt_parsed["origin_region"]
                    result.origin_region_source = "gemini_grounded"
                    collected_urls.setdefault("origin_region", []).extend(gemini_urls)
                if gpt_parsed.get("birth_place") and not result.origin_region:
                    result.origin_region = gpt_parsed["birth_place"]
                    result.origin_region_source = "gemini_grounded"
                    collected_urls.setdefault("origin_region", []).extend(gemini_urls)
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

    # ── 6. Photo URL fallback (SINTA, Scholar, DDG image) ────────────
    if not result.photo_url:
        name_for_photo = result.full_name or cleaned_name
        # Try SINTA author page for photo
        if result.nidn:
            sinta_hits = await ddg_search(
                f'site:sinta.kemdikbud.go.id "{name_for_photo}" OR "{result.nidn}"',
                max_results=2,
            )
            for sh in (sinta_hits or []):
                link = sh.get("link", "")
                if "sinta.kemdikbud.go.id/authors" in link:
                    html = await fetch_page(link)
                    if html:
                        # Look for avatar/profile image in the HTML
                        img_match = re.search(
                            r'<img[^>]+(?:avatar|profile|photo|author)[^>]*src=["\']([^"\']+)["\']',
                            html, re.IGNORECASE,
                        )
                        if not img_match:
                            img_match = re.search(
                                r'src=["\']([^"\']+)["\'][^>]*(?:avatar|profile|photo|author)',
                                html, re.IGNORECASE,
                            )
                        if img_match:
                            photo = img_match.group(1)
                            if photo.startswith("http") and "default" not in photo.lower():
                                result.photo_url = photo
                                collected_urls["photo_url"] = [link]
                                sources.append("sinta_photo")
                                log.info("[IdentityResolver] Photo from SINTA: %s", photo)
                    break
        # Try Google Scholar profile for photo
        if not result.photo_url:
            scholar_hits = await ddg_search(
                f'site:scholar.google.com "{name_for_photo}"', max_results=2,
            )
            for sh in (scholar_hits or []):
                link = sh.get("link", "")
                if "scholar.google.com" in link:
                    html = await fetch_page(link)
                    if html:
                        img_match = re.search(
                            r'<img[^>]+id=["\']gsc_prf_pup["\'][^>]*src=["\']([^"\']+)["\']',
                            html, re.IGNORECASE,
                        )
                        if img_match:
                            photo = img_match.group(1)
                            if not photo.endswith("avatar_scholar_56.png"):
                                if not photo.startswith("http"):
                                    photo = "https://scholar.google.com" + photo
                                result.photo_url = photo
                                collected_urls["photo_url"] = [link]
                                sources.append("scholar_photo")
                                log.info("[IdentityResolver] Photo from Scholar: %s", photo)
                    break

    # ── Source URLs per field ──────────────────────────────────────────
    for field, urls in collected_urls.items():
        result.source_urls[field] = list(dict.fromkeys(urls))  # dedupe

    # ── Finalize ───────────────────────────────────────────────────────
    if not result.full_name:
        result.full_name = cleaned_name or pic_name

    result.confidence = max(result.confidence, 0.3 if sources else 0.0)
    if "pddikti_search" in sources:
        result.confidence = max(result.confidence, 0.9)
    result.sources = sources

    log.info(
        "[IdentityResolver] Done for %s: name=%s, nidn=%s, confidence=%.2f",
        pic_name, result.full_name, result.nidn, result.confidence,
    )
    return {"identity": result, "cleaned_name": cleaned_name, "name_variants": name_variants}


async def _infer_origin_from_pt(pt_name: str) -> str | None:
    """Use AI to infer the city/region where a university is located.

    AI knows that ITS → Surabaya, UGM → Yogyakarta, UIN Sunan Kalijaga → Yogyakarta,
    etc. — no need for fragile regex patterns.
    """
    result = await gpt_extract_structured(
        pt_name,
        (
            "This is an Indonesian university name. "
            "What city or region is this university located in?\n"
            'Return JSON: {"city": "..."}\n'
            "Examples:\n"
            '- "Universitas Negeri Yogyakarta" → "Yogyakarta"\n'
            '- "Institut Teknologi Sepuluh Nopember" → "Surabaya"\n'
            '- "UIN Sunan Kalijaga" → "Yogyakarta"\n'
            '- "Universitas Prima Indonesia" → "Medan"\n'
            '- "Universitas Indonesia" → "Depok"\n'
            "If you don't know, return null."
        ),
    )
    if result and result.get("city"):
        return result["city"]
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
