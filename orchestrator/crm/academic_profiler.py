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

    log.info("[AcademicProfiler] Starting for %s (dosen_id=%s)", full_name, dosen_id)

    result = AcademicResult()
    sources: list[str] = []

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
            # Compute tenure from earliest record
            years = [s.get("tahun_masuk") for s in study_hist if s.get("tahun_masuk")]
            if years:
                try:
                    earliest = min(int(y) for y in years if y)
                    result.tenure_years = datetime.now().year - earliest
                except (ValueError, TypeError):
                    pass
            sources.append("pddikti_study_history")

    # ── 3. PDDIKTI teaching history (current courses) ─────────────────
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
    sinta = await sinta_search(full_name)
    if sinta:
        result.sinta_id = sinta.get("sinta_id")
        sources.append("sinta")

    # ── 6. Google Scholar ──────────────────────────────────────────────
    scholar = await scholar_search(full_name, uni_name)
    if scholar:
        result.scholar_id = scholar.get("url")
        sources.append("google_scholar")

    # ── 7. DDG fallback for teaching/expertise ─────────────────────────
    if not result.teaching_subjects:
        ddg_results = await ddg_search(
            f'"{full_name}" "{uni_name}" mengajar OR "mata kuliah" OR dosen',
            max_results=3,
        )
        if ddg_results:
            combined = "\n".join(r.get("snippet", "") for r in ddg_results)
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
            sources.append("ddg_academic")

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
