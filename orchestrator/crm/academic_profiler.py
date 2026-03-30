"""
Academic Profiler Agent — gathers academic career info from PDDIKTI,
SINTA, Google Scholar, and web.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import CrmState, AcademicResult
from orchestrator.crm.name_utils import strip_academic_titles, ai_strip_titles, build_name_variants
from orchestrator.crm.tools import (
    pddikti_get_dosen_profile,
    pddikti_get_dosen_study_history,
    pddikti_get_dosen_teaching,
    pddikti_get_dosen_penelitian,
    pddikti_get_dosen_karya,
    sinta_search,
    scholar_search,
    ddg_search,
    gpt_extract_structured,
)
from orchestrator.osint.tavily_client import tavily_deep_search


async def academic_profiler_agent(state: CrmState) -> dict:
    """
    Profile academic career using PDDIKTI (primary) + SINTA + Scholar.

    Returns partial state update with `academic`.
    """
    identity = state.get("identity")
    pic_name = state.get("pic_name", "")
    uni_name = state.get("university_name", "")

    dosen_id = identity.pddikti_dosen_id if identity else None
    full_name = (identity.full_name if identity else None) or pic_name
    # Use cleaned name for search queries (strip titles)
    cleaned_name = state.get("cleaned_name") or await ai_strip_titles(pic_name)
    search_name = cleaned_name if cleaned_name != full_name else full_name

    log.info("[AcademicProfiler] Starting for %s (dosen_id=%s, search_name=%s)", full_name, dosen_id, search_name)

    result = AcademicResult()
    sources: list[str] = []
    pddikti_url = f"https://pddikti.kemdiktisaintek.go.id/data_dosen/{dosen_id}" if dosen_id else None

    # ── 1. PDDIKTI profile (jabatan, pendidikan) ──────────────────────
    if dosen_id:
        profile = await pddikti_get_dosen_profile(dosen_id)
        if profile:
            result.jabatan_akademik = profile.get("jabatan_akademik")
            result.pendidikan_tertinggi = profile.get("pendidikan_tertinggi")
            sources.append("pddikti_profile")

    # ── 2. PDDIKTI study history (education path) ─────────────────────
    if dosen_id:
        study_hist = await pddikti_get_dosen_study_history(dosen_id)
        if study_hist:
            result.education_history = [
                {
                    "jenjang": s.get("jenjang", ""),
                    "nama_prodi": s.get("nama_prodi", ""),
                    "nama_pt": s.get("nama_pt", ""),
                    "tahun_masuk": s.get("tahun_masuk"),
                    "tahun_lulus": s.get("tahun_lulus"),
                    "gelar": s.get("gelar_akademik") or s.get("singkatan_gelar", ""),
                }
                for s in study_hist
            ]
            # Estimate tenure from highest-degree graduation year
            # (masa kerja ≈ years since completing final degree)
            grad_years = []
            for s in study_hist:
                y = s.get("tahun_lulus")
                if y:
                    try:
                        grad_years.append(int(str(y)[:4]))
                    except (ValueError, TypeError):
                        pass
            if grad_years:
                latest_grad = max(grad_years)
                result.tenure_years = datetime.now().year - latest_grad
            sources.append("pddikti_study_history")

    # ── 3. PDDIKTI teaching history (current courses + tenure) ─────────
    if dosen_id:
        teaching = await pddikti_get_dosen_teaching(dosen_id)
        if teaching:
            # Get unique course names from recent semesters
            courses = set()
            for t in teaching[:20]:  # Last 20 entries
                name = t.get("nama_matkul", "")
                if name:
                    courses.add(name)
            result.teaching_subjects = sorted(courses)
            # Better tenure: years since earliest teaching semester
            teach_years = []
            for t in teaching:
                sem = t.get("semester", "") or t.get("nama_semester", "")
                if sem:
                    try:
                        y = int(str(sem)[:4])
                        if 1970 <= y <= datetime.now().year:
                            teach_years.append(y)
                    except (ValueError, TypeError):
                        pass
            if teach_years:
                earliest_teach = min(teach_years)
                result.tenure_years = datetime.now().year - earliest_teach
            sources.append("pddikti_teaching")

    # ── 4. PDDIKTI research publications ───────────────────────────────
    if dosen_id:
        penelitian = await pddikti_get_dosen_penelitian(dosen_id)
        karya = await pddikti_get_dosen_karya(dosen_id)

        pubs = []
        topics = set()

        for p in (penelitian or []):
            pubs.append({
                "title": p.get("judul_kegiatan", ""),
                "year": p.get("tahun_kegiatan"),
                "type": "penelitian",
            })
            # Extract research topic from title
            title = p.get("judul_kegiatan", "")
            if title:
                topics.add(title[:100])

        for k in (karya or []):
            pubs.append({
                "title": k.get("judul_kegiatan", ""),
                "year": k.get("tahun_kegiatan"),
                "type": k.get("jenis_kegiatan", "karya"),
            })

        result.publications = pubs[:30]  # Cap at 30

        # Use GPT to summarize research topics
        if topics:
            topic_text = "\n".join(list(topics)[:15])
            extracted = await gpt_extract_structured(
                topic_text,
                (
                    "These are research titles by a lecturer. Extract 3-5 main research topics/themes.\n"
                    'Return JSON: {"topics": ["topic1", "topic2", ...]}'
                ),
            )
            if extracted and extracted.get("topics"):
                result.research_topics = extracted["topics"]

        sources.append("pddikti_publications")

    # ── 5. SINTA search (h-index, sinta score) ────────────────────────
    # Try with cleaned name first, then full name; pass university for AI verification
    sinta_url: str | None = None
    for sinta_name in [search_name, full_name] if search_name != full_name else [full_name]:
        sinta = await sinta_search(sinta_name, uni_name)
        if sinta:
            result.sinta_id = sinta.get("sinta_id")
            sinta_url = sinta.get("url")
            sources.append("sinta")
            break

    # ── 6. Google Scholar ──────────────────────────────────────────
    scholar_url: str | None = None
    for scholar_name in [search_name, full_name] if search_name != full_name else [full_name]:
        scholar = await scholar_search(scholar_name, uni_name)
        if scholar:
            result.scholar_id = scholar.get("url")
            scholar_url = scholar.get("url")
            sources.append("google_scholar")
            break

    # ── 7. DDG fallback for teaching/expertise (agentic retry) ─────────
    if not result.teaching_subjects:
        # Try progressively relaxed name variants
        name_variants = state.get("name_variants") or build_name_variants(pic_name)
        ddg_results = None
        for variant in [search_name] + [v for v in name_variants if v.lower() != search_name.lower()][:2]:
            ddg_results = await ddg_search(
                f'"{variant}" "{uni_name}" mengajar OR "mata kuliah" OR dosen',
                max_results=3,
            )
            if ddg_results:
                log.info("[AcademicProfiler] DDG hit with variant: '%s'", variant)
                break
        if ddg_results:
            combined = "\n".join(r.get("snippet", "") for r in ddg_results)
            ddg_links = [r.get("link", "") for r in ddg_results if r.get("link")]
            extracted = await gpt_extract_structured(
                combined,
                (
                    f"Extract academic information about {full_name}:\n"
                    "Return JSON with keys:\n"
                    "- teaching_subjects: list of courses taught\n"
                    "- expertise: area of expertise\n"
                    "Return null/empty list if not found."
                ),
            )
            if extracted and extracted.get("teaching_subjects"):
                result.teaching_subjects = extracted["teaching_subjects"]
                if ddg_links:
                    result.source_urls["teaching_subjects"] = ddg_links
            sources.append("ddg_academic")

    # ── 8. Tavily/DDG fallback for education & academic details ─
    if not result.education_history or not result.teaching_subjects or not result.jabatan_akademik:
        log.info("[AcademicProfiler] Deep diving for academic and education history with Tavily...")
        tavily_q = f'"{search_name}" Indonesia academic OR education OR profil OR alumni'
        tavily_results = await tavily_deep_search(tavily_q, max_results=7)
        
        fallback_text = ""
        fallback_links = []
        if tavily_results and len(tavily_results) > 100:
            fallback_text = tavily_results
            fallback_links = ["https://tavily.com/search?q=" + tavily_q]
        else:
            log.info("[AcademicProfiler] Tavily fallback failed or small, using DDG...")
            ddg_results = await ddg_search(
                f'"{search_name}" "pendidikan" OR "alumni" OR "lulusan" OR "universitas"',
                max_results=5,
            )
            if ddg_results:
                fallback_text = "\n".join(r.get("snippet", "") for r in ddg_results)
                fallback_links = [r.get("link", "") for r in ddg_results if r.get("link")]

        if fallback_text:
            prompt = (
                f"Extract academic and education history for {full_name}:\n"
                "Search comprehensively for any mention of schools, universities attended, current/past roles, job titles, or subjects taught.\n"
                "If the person is not a lecturer (dosen) but rather a student, professional, or employee, extract their academic background and professional title anyway.\n"
                "Return JSON with keys:\n"
                "- education_history: array of dicts with 'jenjang' (level/degree like S1, SMA, Bootcamp), 'nama_pt' (institute name), 'gelar' (title/major).\n"
                "- jabatan_akademik: their professional or academic role (e.g. Mahasiswa, Web Developer, Dosen, etc).\n"
                "- teaching_subjects: list of their skills, courses taught, or field of expertise.\n"
                "Return null/empty for fields not found. Output pure JSON without markdown blocks."
            )
            extracted = await gpt_extract_structured(fallback_text[:25000], prompt)
            
            if extracted:
                if not result.education_history and extracted.get("education_history"):
                    result.education_history = extracted["education_history"]
                    if fallback_links:
                        result.source_urls["education_history"] = fallback_links
                    sources.append("tavily_education")
                if not result.jabatan_akademik and extracted.get("jabatan_akademik"):
                    result.jabatan_akademik = extracted["jabatan_akademik"]
                    if fallback_links:
                        result.source_urls["jabatan_akademik"] = fallback_links
                if not result.teaching_subjects and extracted.get("teaching_subjects"):
                    result.teaching_subjects = extracted["teaching_subjects"]
                    if fallback_links:
                        result.source_urls["teaching_subjects"] = fallback_links

    # ── Source URLs per field ──────────────────────────────────────────
    if pddikti_url:
        for field in ("jabatan_akademik", "pendidikan_tertinggi", "education_history",
                       "teaching_subjects", "publications", "research_topics", "tenure_years"):
            if getattr(result, field, None) and field not in result.source_urls:
                result.source_urls[field] = [pddikti_url]
    if sinta_url:
        if result.sinta_id:
            result.source_urls["sinta_id"] = [sinta_url]
    if scholar_url:
        if result.scholar_id:
            result.source_urls["scholar_id"] = [scholar_url]

    # ── Confidence ─────────────────────────────────────────────────────
    filled = sum([
        bool(result.jabatan_akademik), bool(result.education_history),
        bool(result.teaching_subjects), bool(result.publications),
        bool(result.tenure_years),
    ])
    result.confidence = round(filled / 5, 2)
    result.sources = sources

    log.info(
        "[AcademicProfiler] Done for %s: subjects=%d, pubs=%d, confidence=%.2f",
        full_name, len(result.teaching_subjects), len(result.publications), result.confidence,
    )
    return {"academic": result}
