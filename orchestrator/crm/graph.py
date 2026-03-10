"""
LangGraph StateGraph — PIC Profiling (CRM) pipeline.

Workflow:
    ┌─────────────────────────────────────────────────────────┐
    │  load_existing (CRM request + university data)           │
    │         │                                                │
    │         ▼                                                │
    │  identity_resolver (PDDIKTI → DDG)                       │
    │         │                                                │
    │         ▼                                                │
    │  ┌──────────────────────────────────────┐               │
    │  │ parallel_phase_1                      │               │
    │  │  ├── academic_profiler                │               │
    │  │  ├── social_profiler                  │               │
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
    │  persist_results (save to DB)                            │
    │             │                                            │
    │            END                                           │
    └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from langgraph.graph import StateGraph, END

from orchestrator.config import log
from orchestrator.crm.state import CrmState, CRM_AGENT_KEYS
from orchestrator.crm.identity_resolver import identity_resolver_agent
from orchestrator.crm.academic_profiler import academic_profiler_agent
from orchestrator.crm.social_profiler import social_profiler_agent
from orchestrator.crm.campus_context import campus_context_agent
from orchestrator.crm.personal_interest import personal_interest_agent
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
                "SELECT phone, status, analysis FROM conversations WHERE university_id = ? LIMIT 10",
                (university_id,),
            )
            existing_conversations = [dict(r) for r in await cursor.fetchall()]

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
    """Run personal interest and family info agents in parallel."""
    log.info("[CRM Graph] Starting phase 2 (2 agents in parallel)...")

    results = await asyncio.gather(
        personal_interest_agent(state),
        family_info_agent(state),
        return_exceptions=True,
    )

    merged: dict[str, Any] = {}
    agent_names = ["personal_interest", "family_info"]
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
        profile_data["education_history_source"] = "pddikti"

    if social:
        profile_data["linkedin_url"] = social.linkedin_url
        profile_data["instagram_handle"] = social.instagram_handle
        profile_data["facebook_url"] = social.facebook_url
        profile_data["twitter_handle"] = social.twitter_handle
        profile_data["other_social"] = json.dumps(social.other_social) if social.other_social else None

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
                await add_crm_profile_source(
                    profile_id,
                    field_name=field.field_name,
                    value=value_str[:500],  # Cap length
                    source_type=field.source or "agent",
                    confidence=field.confidence,
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
    graph.add_node("persist_results", _persist_results)

    graph.set_entry_point("load_existing")

    graph.add_edge("load_existing", "identity_resolver")
    graph.add_edge("identity_resolver", "parallel_phase_1")
    graph.add_edge("parallel_phase_1", "parallel_phase_2")
    graph.add_edge("parallel_phase_2", "profile_compiler")
    graph.add_edge("profile_compiler", "persist_results")
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
