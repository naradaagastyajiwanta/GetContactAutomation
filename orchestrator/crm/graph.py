"""
LangGraph StateGraph — PIC Profiling (CRM) pipeline.

Workflow:
    ┌─────────────────────────────────────────────────────────┐
    │  load_existing (CRM request + university data)           │
    │         │                                                │
    │         ▼                                                │
    │  identity_resolver (PDDIKTI → DDG/Brave)                │
    │         │                                                │
    │         ▼                                                │
    │  ┌──────────────────────────────────────┐               │
    │  │ parallel_phase_1                      │               │
    │  │  ├── academic_profiler                │               │
    │  │  ├── social_profiler (+email/phone)   │               │
    │  │  └── campus_context                   │               │
    │  └──────────┬───────────────────────────┘               │
    │             ▼                                            │
    │  ┌──────────────────────────────────────┐               │
    │  │ parallel_phase_2 (uses phase 1)       │               │
    │  │  ├── personal_interest (uses social)  │               │
    │  │  └── family_info (uses social)        │               │
    │  └──────────┬───────────────────────────┘               │
    │             ▼                                            │
    │  profile_compiler (merge all → CompiledProfile)          │
    │             │                                            │
    │             ▼                                            │
    │  gap_filler (re-query missing fields via Gemini)         │
    │             │                                            │
    │             ▼                                            │
    │  persist_results (save to DB)                            │
    │             │                                            │
    │            END                                           │
    └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any
from urllib.parse import urlparse

from langgraph.graph import StateGraph, END

from orchestrator.config import log
from orchestrator.crm.state import CrmState, CRM_AGENT_KEYS


# ---------------------------------------------------------------------------
# Source URL quality filter — drop junk / unreachable / irrelevant links
# ---------------------------------------------------------------------------
_JUNK_DOMAINS = {
    "translate.google.com",
    "translate.google.co.id",
    "primevideo.com",
    "www.primevideo.com",
    "target.com",
    "www.target.com",
    "wa.me",
}

_JUNK_PATTERNS = re.compile(
    r"vertexaisearch\.cloud\.google\.com"
    r"|accounts\.google\.com"
    r"|play\.google\.com/store",
    re.IGNORECASE,
)


def _is_useful_url(url: str) -> bool:
    """Return True if *url* is a real, useful source link."""
    if not url or not url.startswith("http"):
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    if host in _JUNK_DOMAINS:
        return False
    if _JUNK_PATTERNS.search(url):
        return False
    return True
from orchestrator.crm.identity_resolver import identity_resolver_agent
from orchestrator.crm.academic_profiler import academic_profiler_agent
from orchestrator.crm.social_profiler import social_profiler_agent
from orchestrator.crm.campus_context import campus_context_agent
from orchestrator.crm.personal_interest import personal_interest_agent
from orchestrator.crm.social_post_analyzer import social_post_analyzer_agent
from orchestrator.crm.family_info import family_info_agent
from orchestrator.crm.profile_compiler import profile_compiler_agent
from orchestrator.db import (
    get_db,
    get_crm_request,
    update_crm_request_status,
    create_crm_profile,
    update_crm_profile,
    add_crm_profile_source,
    create_crm_profile_run,
    update_crm_profile_run,
)


# ---------------------------------------------------------------------------
# Node: load existing data
# ---------------------------------------------------------------------------


async def _load_existing(state: CrmState) -> dict:
    """Load CRM request + university data from DB."""
    request_id = state["request_id"]

    request = await get_crm_request(request_id)
    if not request:
        raise ValueError(f"CRM request #{request_id} not found")

    university_data = None
    university_id = request.get("university_id")
    if university_id:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM universities WHERE id = ?", (university_id,)
            )
            row = await cursor.fetchone()
            university_data = dict(row) if row else None

    # Existing conversations for context
    existing_conversations: list[dict] = []
    if university_id:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT contact_phone as phone, state as status, message_history FROM conversations WHERE university_id = ? LIMIT 10",
                (university_id,),
            )
            existing_conversations = [dict(r) for r in await cursor.fetchall()]

    # Load OSINT data for the university (for identity validation)
    osint_social_media: list[dict] = []
    osint_contacts: list[dict] = []
    osint_profile: dict | None = None
    if university_id:
        async with get_db() as db:
            # Load social media handles
            cursor = await db.execute(
                "SELECT platform, handle, url, source FROM osint_social_media WHERE university_id = ?",
                (university_id,),
            )
            osint_social_media = [dict(r) for r in await cursor.fetchall()]

            # Load contacts
            cursor = await db.execute(
                "SELECT name, phone, email, title, department, source FROM osint_contacts WHERE university_id = ?",
                (university_id,),
            )
            osint_contacts = [dict(r) for r in await cursor.fetchall()]

            # Load profile
            cursor = await db.execute(
                "SELECT * FROM osint_profiles WHERE university_id = ?",
                (university_id,),
            )
            row = await cursor.fetchone()
            osint_profile = dict(row) if row else None

    log.info(
        "[CRM Graph] OSINT data loaded: social=%d, contacts=%d, profile=%s",
        len(osint_social_media), len(osint_contacts), bool(osint_profile),
    )

    # Create a run log
    run_id = await create_crm_profile_run(request_id)
    await update_crm_request_status(request_id, "processing", run_id=run_id)

    log.info(
        "[CRM Graph] Loaded request #%d: pic=%s, uni=%s",
        request_id,
        request.get("pic_name"),
        request.get("university_name") or (university_data or {}).get("name", ""),
    )

    return {
        "university_id": university_id,
        "university_name": request.get("university_name") or (university_data or {}).get("name", ""),
        "pic_name": request.get("pic_name", ""),
        "pic_title": request.get("pic_title"),
        "faculty": None,
        "university_data": university_data,
        "existing_conversations": existing_conversations,
        "osint_social_media": osint_social_media,
        "osint_contacts": osint_contacts,
        "osint_profile": osint_profile,
        "run_id": run_id,
        "agents_completed": [],
        "agents_failed": [],
    }


# ---------------------------------------------------------------------------
# Node: identity resolver (sequential — feeds all others)
# ---------------------------------------------------------------------------


async def _identity_resolver(state: CrmState) -> dict:
    """Run identity resolver — must complete before other agents."""
    try:
        result = await identity_resolver_agent(state)
        completed = list(state.get("agents_completed", []))
        completed.append("identity_resolver")
        result["agents_completed"] = completed
        return result
    except Exception as e:
        log.error("[CRM Graph] Identity resolver failed: %s", e)
        failed = list(state.get("agents_failed", []))
        failed.append("identity_resolver")
        return {"agents_failed": failed}


# ---------------------------------------------------------------------------
# Node: parallel phase 1 (academic + social + campus context)
# ---------------------------------------------------------------------------


async def _parallel_phase_1(state: CrmState) -> dict:
    """Run academic, social, and campus context agents in parallel."""
    log.info("[CRM Graph] Starting phase 1 (3 agents in parallel)...")

    results = await asyncio.gather(
        academic_profiler_agent(state),
        social_profiler_agent(state),
        campus_context_agent(state),
        return_exceptions=True,
    )

    merged: dict[str, Any] = {}
    agent_names = ["academic_profiler", "social_profiler", "campus_context"]
    completed = list(state.get("agents_completed", []))
    failed = list(state.get("agents_failed", []))

    for name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            log.error("[CRM Graph] Agent %s failed: %s", name, result)
            failed.append(name)
        elif isinstance(result, dict):
            merged.update(result)
            completed.append(name)
        else:
            failed.append(name)

    merged["agents_completed"] = completed
    merged["agents_failed"] = failed

    succeeded = sum(1 for r in results if isinstance(r, dict))
    log.info("[CRM Graph] Phase 1 done: %d/3 succeeded", succeeded)
    return merged


# ---------------------------------------------------------------------------
# Node: parallel phase 2 (personal interest + family info)
# ---------------------------------------------------------------------------


async def _parallel_phase_2(state: CrmState) -> dict:
    """Run personal interest, family info, and social post analyzer agents in parallel."""
    log.info("[CRM Graph] Starting phase 2 (3 agents in parallel)...")

    results = await asyncio.gather(
        personal_interest_agent(state),
        family_info_agent(state),
        social_post_analyzer_agent(state),
        return_exceptions=True,
    )

    merged: dict[str, Any] = {}
    agent_names = ["personal_interest", "family_info", "social_post_analyzer"]
    completed = list(state.get("agents_completed", []))
    failed = list(state.get("agents_failed", []))

    for name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            log.error("[CRM Graph] Agent %s failed: %s", name, result)
            failed.append(name)
        elif isinstance(result, dict):
            merged.update(result)
            completed.append(name)
        else:
            failed.append(name)

    merged["agents_completed"] = completed
    merged["agents_failed"] = failed

    succeeded = sum(1 for r in results if isinstance(r, dict))
    log.info("[CRM Graph] Phase 2 done: %d/2 succeeded", succeeded)
    return merged


# ---------------------------------------------------------------------------
# Node: profile compiler
# ---------------------------------------------------------------------------


async def _compile_profile(state: CrmState) -> dict:
    """Run the profile compiler."""
    try:
        result = await profile_compiler_agent(state)
        completed = list(state.get("agents_completed", []))
        completed.append("profile_compiler")
        result["agents_completed"] = completed
        return result
    except Exception as e:
        log.error("[CRM Graph] Profile compiler failed: %s", e)
        failed = list(state.get("agents_failed", []))
        failed.append("profile_compiler")
        return {"agents_failed": failed}


# ---------------------------------------------------------------------------
# Node: persist results
# ---------------------------------------------------------------------------


async def _persist_results(state: CrmState) -> dict:
    """Save compiled CRM profile to DB."""
    request_id = state["request_id"]
    run_id = state.get("run_id", 0)
    university_id = state.get("university_id")

    log.info("[CRM Graph] Persisting results for request #%d", request_id)

    compiled = state.get("compiled_profile")
    identity = state.get("identity")
    academic = state.get("academic")
    social = state.get("social_profile")
    campus = state.get("campus_context")
    personal = state.get("personal_interest")
    family = state.get("family_info")

    # Build kwargs for create_crm_profile
    profile_data: dict[str, Any] = {}

    if identity:
        profile_data["full_name"] = identity.full_name
        profile_data["full_name_source"] = "pddikti" if identity.pddikti_dosen_id else "search"
        profile_data["birth_date"] = identity.birth_date
        profile_data["birth_date_source"] = identity.birth_date_source
        profile_data["age"] = identity.age
        profile_data["origin_region"] = identity.origin_region
        profile_data["origin_region_source"] = identity.origin_region_source
        profile_data["photo_url"] = identity.photo_url

    if academic:
        profile_data["title"] = academic.jabatan_akademik
        profile_data["title_source"] = "pddikti" if "pddikti_profile" in academic.sources else "search"
        profile_data["teaching_subjects"] = json.dumps(academic.teaching_subjects) if academic.teaching_subjects else None
        profile_data["teaching_subjects_source"] = "pddikti" if "pddikti_teaching" in academic.sources else "search"
        profile_data["tenure_years"] = academic.tenure_years
        profile_data["tenure_years_source"] = "pddikti" if "pddikti_study_history" in academic.sources else "search"
        profile_data["education_history"] = json.dumps(academic.education_history) if academic.education_history else None
        profile_data["education_history_source"] = "pddikti" if "pddikti_study_history" in academic.sources else "search"

    if social:
        profile_data["linkedin_url"] = social.linkedin_url
        profile_data["instagram_handle"] = social.instagram_handle
        profile_data["facebook_url"] = social.facebook_url
        profile_data["twitter_handle"] = social.twitter_handle
        profile_data["other_social"] = json.dumps(social.other_social) if social.other_social else None
        profile_data["email"] = social.email
        profile_data["phone"] = social.phone

    if campus:
        profile_data["campus_problems"] = json.dumps(campus.campus_problems) if campus.campus_problems else None
        profile_data["campus_problems_source"] = ", ".join(campus.sources) if campus.sources else None
        profile_data["campus_concerns"] = json.dumps(campus.campus_concerns) if campus.campus_concerns else None
        profile_data["campus_concerns_source"] = ", ".join(campus.sources) if campus.sources else None
        profile_data["campus_hopes"] = json.dumps(campus.campus_hopes) if campus.campus_hopes else None
        profile_data["campus_hopes_source"] = ", ".join(campus.sources) if campus.sources else None

    if personal:
        profile_data["hobbies"] = json.dumps(personal.hobbies) if personal.hobbies else None
        profile_data["hobbies_source"] = ", ".join(personal.sources) if personal.sources else None
        profile_data["favorite_food"] = personal.favorite_food
        profile_data["favorite_food_source"] = ", ".join(personal.sources) if personal.sources else None
        profile_data["outside_activities"] = json.dumps(personal.outside_activities) if personal.outside_activities else None
        profile_data["outside_activities_source"] = ", ".join(personal.sources) if personal.sources else None

    if family:
        profile_data["marital_status"] = family.marital_status
        profile_data["marital_status_source"] = ", ".join(family.sources) if family.sources else None
        profile_data["spouse_name"] = family.spouse_name
        profile_data["spouse_name_source"] = ", ".join(family.sources) if family.sources else None
        profile_data["children_count"] = family.children_count
        profile_data["children_count_source"] = ", ".join(family.sources) if family.sources else None
        profile_data["family_residence"] = family.family_residence
        profile_data["family_residence_source"] = ", ".join(family.sources) if family.sources else None

    social_post_analysis = state.get("social_post_analysis")
    if social_post_analysis:
        profile_data["personality_summary"] = social_post_analysis.personality_summary
        profile_data["recent_topics"] = json.dumps(social_post_analysis.recent_topics) if social_post_analysis.recent_topics else None
        profile_data["communication_style"] = social_post_analysis.communication_style
        profile_data["social_behavior_insights"] = social_post_analysis.social_behavior_insights

    if compiled:
        profile_data["overall_confidence"] = compiled.overall_confidence
        profile_data["fields_found"] = compiled.fields_found
        profile_data["fields_total"] = compiled.fields_total
        profile_data["fields_manual"] = compiled.fields_manual

    # Create profile in DB
    profile_id = await create_crm_profile(request_id, university_id, **profile_data)

    # Add source audit trail
    if compiled:
        for field in compiled.fields:
            if field.value is not None and field.status != "not_found":
                value_str = json.dumps(field.value) if not isinstance(field.value, str) else field.value
                # Filter out junk URLs, then join for DB
                clean_urls = [u for u in field.source_urls if _is_useful_url(u)]
                source_url = ", ".join(clean_urls) if clean_urls else None
                await add_crm_profile_source(
                    profile_id,
                    field_name=field.field_name,
                    value=value_str[:500],  # Cap length
                    source_type=field.source or "agent",
                    confidence=field.confidence,
                    source_url=source_url,
                )

    # Update run log
    await update_crm_profile_run(
        run_id,
        status="completed",
        agents_completed=json.dumps(state.get("agents_completed", [])),
        agents_failed=json.dumps(state.get("agents_failed", [])),
        completed_at="datetime('now')",
    )

    # Update request status
    await update_crm_request_status(request_id, "completed")

    log.info(
        "[CRM Graph] Persisted profile #%d for request #%d (confidence=%.2f, %d/%d fields)",
        profile_id,
        request_id,
        compiled.overall_confidence if compiled else 0.0,
        compiled.fields_found if compiled else 0,
        compiled.fields_total if compiled else 0,
    )

    return {}


# ---------------------------------------------------------------------------
# Node: gap filler (cross-reference re-query for missing fields)
# ---------------------------------------------------------------------------


async def _gap_filler(state: CrmState) -> dict:
    """Re-query specifically for fields that are still empty after compilation."""
    compiled = state.get("compiled_profile")
    if not compiled or compiled.overall_confidence >= 0.90:
        log.info("[CRM Graph] Gap filler skipped (confidence=%.2f)", compiled.overall_confidence if compiled else 0)
        return {}

    identity = state.get("identity")
    social = state.get("social_profile")
    personal = state.get("personal_interest")
    family = state.get("family_info")
    pic_name = state.get("pic_name", "")
    uni_name = state.get("university_name", "")

    full_name = (identity.full_name if identity else None) or pic_name
    cleaned_name = state.get("cleaned_name") or full_name

    from orchestrator.crm.tools import ddg_search, gpt_extract_structured, gemini_research, fetch_page, extract_text_from_html
    from orchestrator.crm.name_utils import strip_academic_titles

    log.info(
        "[CRM Graph] Gap filler starting for %s (%d/%d fields found)",
        full_name, compiled.fields_found, compiled.fields_total,
    )

    # Identify which fields are missing
    missing_fields = [f.field_name for f in compiled.fields if f.status == "not_found"]
    log.info("[CRM Graph] Missing fields: %s", missing_fields)

    updates: dict = {}

    # ── Gap: family_residence — DISABLED ────────────────────────────────────
    # DO NOT infer family_residence from university location - this is unreliable!
    # Only accept explicit mentions from verified sources

    # ── Gap: Facebook Deep Dive ──────
    fb_url = social.facebook_url if social else None
    if fb_url:
        fb_targets = []
        if "Status Pernikahan" in missing_fields or "Nama Pasangan" in missing_fields:
            fb_targets.append("status pernikahan dan nama pasangan")
        if "Tempat Tinggal Keluarga" in missing_fields or "Alamat Rumah" in missing_fields or "Kota Asal" in missing_fields:
            fb_targets.append("tempat tinggal, kota asal, dan alamat")
        if "Riwayat Akademik" in missing_fields or "Riwayat Pendidikan" in missing_fields:
            fb_targets.append("riwayat pendidikan (sekolah, kampus)")
        if "Tanggal Lahir" in missing_fields or "Umur" in missing_fields:
            fb_targets.append("tanggal lahir atau umur")
        
        if fb_targets:
            log.info("[CRM Graph] Gap filler leveraging Facebook deep scrape for: %s", fb_targets)
            
            # Step 1: Deep PinchTab Fetch of actual FB page
            page_text = ""
            about_url = fb_url.rstrip("/") + "/about"
            fb_html = await fetch_page(about_url)
            if fb_html:
                page_text = extract_text_from_html(fb_html, max_chars=8000)
            
            # Step 2: Use intelligent Search fallback as well
            fb_search = await ddg_search(f'site:facebook.com "{cleaned_name}" ' + " OR ".join(fb_targets), max_results=3)
            search_text = ""
            if fb_search:
                search_text = "\n".join(s.get("snippet", "") for s in fb_search)
            
            combined_context = f"FACEBOOK PAGE TEXT:\n{page_text}\n\nSEARCH SNIPPETS:\n{search_text}"
            
            extracted = await gpt_extract_structured(
                combined_context,
                f"Kamu adalah AI OSINT. Cari informasi spesifik mengenai sosok {cleaned_name} dosen {uni_name}: {', '.join(fb_targets)}.\nReturn JSON: {{\"marital_status\": \"married/single/unknown\", \"spouse_name\": \"...\", \"residence\": \"...\", \"education_history\": [{{\"jenjang\": \"...\", \"nama_pt\": \"...\"}}], \"birth_date\": \"YYYY-MM-DD\", \"home_address\": \"...\"}}"
            )
            
            if extracted:
                if family:
                    if extracted.get("marital_status") and extracted["marital_status"] != "unknown" and not family.marital_status:
                        family.marital_status = extracted["marital_status"]
                        family.sources.append("facebook_gap_filler")
                        updates["family_info"] = family
                    if extracted.get("spouse_name") and not family.spouse_name:
                        family.spouse_name = extracted["spouse_name"]
                        family.sources.append("facebook_gap_filler")
                        updates["family_info"] = family
                    if extracted.get("residence") and not family.family_residence:
                        family.family_residence = extracted["residence"]
                        family.sources.append("facebook_gap_filler")
                        updates["family_info"] = family

                if identity:
                    updated_id = False
                    if extracted.get("birth_date") and not identity.birth_date:
                        identity.birth_date = extracted["birth_date"]
                        identity.sources.append("facebook_gap_filler")
                        updated_id = True
                    if extracted.get("home_address") and not identity.home_address:
                        identity.home_address = extracted["home_address"]
                        identity.sources.append("facebook_gap_filler")
                        updated_id = True
                    if updated_id:
                        updates["identity"] = identity

                academic = state.get("academic")
                if academic and extracted.get("education_history") and not academic.education_history:
                    academic.education_history = extracted["education_history"]
                    academic.sources.append("facebook_gap_filler")
                    updates["academic"] = academic
                updates["family_info"] = family

    # ── Gap: hobbies / outside_activities — Gemini targeted ──────
    if personal and not personal.hobbies and "Hobi" in missing_fields:
        gemini_resp = await gemini_research(
            f"Apa hobi atau kegiatan di luar kampus {cleaned_name} dosen {uni_name}? "
            f"Cari di berita, sosial media, atau profil akademik."
        )
        if gemini_resp and gemini_resp.get("text"):
            extracted = await gpt_extract_structured(
                gemini_resp["text"],
                "Extract hobbies and activities. Return JSON: {\"hobbies\": [...], \"outside_activities\": [...]}",
            )
            if extracted:
                if extracted.get("hobbies") and isinstance(extracted["hobbies"], list):
                    personal.hobbies = extracted["hobbies"]
                if extracted.get("outside_activities") and isinstance(extracted["outside_activities"], list):
                    personal.outside_activities = extracted["outside_activities"]
                personal.sources = list(personal.sources) + ["gap_filler_gemini"]
                updates["personal_interest"] = personal

    # ── Gap: marital_status — Gemini targeted ──────
    if family and (not family.marital_status or family.marital_status == "unknown") and "Status Pernikahan" in missing_fields:
        gemini_resp = await gemini_research(
            f"Apakah {cleaned_name} dosen {uni_name} sudah menikah? "
            f"Siapa nama pasangannya? Berapa anaknya?"
        )
        if gemini_resp and gemini_resp.get("text"):
            extracted = await gpt_extract_structured(
                gemini_resp["text"],
                "Extract: {\"marital_status\": \"married\"/\"single\"/\"unknown\", \"spouse_name\": str|null, \"children_count\": int|null}",
            )
            if extracted:
                ms = extracted.get("marital_status")
                if ms and ms != "unknown":
                    family.marital_status = ms
                if extracted.get("spouse_name"):
                    family.spouse_name = extracted["spouse_name"]
                if extracted.get("children_count") is not None:
                    try:
                        family.children_count = int(extracted["children_count"])
                    except (ValueError, TypeError):
                        pass
                family.sources = list(family.sources) + ["gap_filler_gemini"]
                updates["family_info"] = family

    # ── Gap: personality_traits — infer from academic data ──────
    if personal and not personal.personality_traits and "Sifat Kepribadian" in missing_fields:
        academic = state.get("academic")
        if academic and (academic.research_topics or academic.teaching_subjects):
            context = f"Research: {academic.research_topics}, Teaching: {academic.teaching_subjects}"
            extracted = await gpt_extract_structured(
                context,
                (
                    f"Based on {full_name}'s research and teaching profile, infer 3-5 likely personality traits. "
                    "Return JSON: {\"personality_traits\": [\"trait1\", \"trait2\", ...]}"
                ),
            )
            if extracted and extracted.get("personality_traits"):
                personal.personality_traits = extracted["personality_traits"]
                personal.sources = list(personal.sources) + ["gap_filler_inferred"]
                updates["personal_interest"] = personal

    if updates:
        log.info("[CRM Graph] Gap filler filled %d agent outputs", len(updates))
        # Re-run compiler with updated data
        merged_state = dict(state)
        merged_state.update(updates)
        recompiled = await profile_compiler_agent(merged_state)
        updates.update(recompiled)
    else:
        log.info("[CRM Graph] Gap filler found nothing new")

    return updates


# ---------------------------------------------------------------------------
# Build the LangGraph
# ---------------------------------------------------------------------------


def _build_graph() -> StateGraph:
    """Construct and compile the CRM profiling pipeline."""
    graph = StateGraph(CrmState)

    graph.add_node("load_existing", _load_existing)
    graph.add_node("identity_resolver", _identity_resolver)
    graph.add_node("parallel_phase_1", _parallel_phase_1)
    graph.add_node("parallel_phase_2", _parallel_phase_2)
    graph.add_node("profile_compiler", _compile_profile)
    graph.add_node("gap_filler", _gap_filler)
    graph.add_node("persist_results", _persist_results)

    graph.set_entry_point("load_existing")

    graph.add_edge("load_existing", "identity_resolver")
    graph.add_edge("identity_resolver", "parallel_phase_1")
    graph.add_edge("parallel_phase_1", "parallel_phase_2")
    graph.add_edge("parallel_phase_2", "profile_compiler")
    graph.add_edge("profile_compiler", "gap_filler")
    graph.add_edge("gap_filler", "persist_results")
    graph.add_edge("persist_results", END)

    return graph


# ---------------------------------------------------------------------------
# Compiled graph singleton
# ---------------------------------------------------------------------------

_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph().compile()
        log.info("[CRM Graph] Pipeline compiled successfully")
    return _compiled_graph


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_pic_profiling(request_id: int) -> dict[str, Any]:
    """
    Run the full PIC profiling pipeline for a CRM request.

    Returns a summary dict with: request_id, status, profile_id, confidence, etc.
    """
    graph = _get_graph()
    start_time = time.time()

    log.info("[CRM Graph] Starting PIC profiling for request #%d", request_id)

    initial_state: CrmState = {
        "request_id": request_id,
        "university_id": None,
        "university_name": "",
        "pic_name": "",
        "pic_title": None,
        "faculty": None,
        "university_data": None,
        "existing_conversations": [],
        "identity": None,
        "academic": None,
        "social_profile": None,
        "campus_context": None,
        "personal_interest": None,
        "family_info": None,
        "compiled_profile": None,
        "run_id": 0,
        "agents_completed": [],
        "agents_failed": [],
        "error": None,
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as e:
        log.error("[CRM Graph] Pipeline failed for request #%d: %s", request_id, e)
        await update_crm_request_status(request_id, "failed")
        await update_crm_profile_run(
            initial_state.get("run_id", 0),
            status="failed",
            error=str(e),
            duration_seconds=time.time() - start_time,
        )
        return {"status": "failed", "request_id": request_id, "error": str(e)}

    duration = time.time() - start_time
    run_id = final_state.get("run_id", 0)

    if run_id:
        await update_crm_profile_run(run_id, duration_seconds=duration)

    compiled = final_state.get("compiled_profile")
    return {
        "status": "completed",
        "request_id": request_id,
        "run_id": run_id,
        "agents_completed": final_state.get("agents_completed", []),
        "agents_failed": final_state.get("agents_failed", []),
        "overall_confidence": compiled.overall_confidence if compiled else 0.0,
        "fields_found": compiled.fields_found if compiled else 0,
        "fields_total": compiled.fields_total if compiled else 0,
        "gaps": compiled.gaps if compiled else [],
        "duration_seconds": round(duration, 1),
    }
