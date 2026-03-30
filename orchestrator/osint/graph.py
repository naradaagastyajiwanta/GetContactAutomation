"""
LangGraph StateGraph — University OSINT pipeline.

Workflow:
    ┌─────────────────────────────────────────────────────┐
    │  load_existing_data (from DB)                        │
    │         │                                            │
    │         ▼                                            │
    │  ┌──────────────────────────────────┐               │
    │  │ parallel_research                 │               │
    │  │  ├── web_profiler                 │               │
    │  │  ├── social_intel                 │               │
    │  │  ├── key_people                   │               │
    │  │  └── news_scanner                 │               │
    │  └──────────┬───────────────────────┘               │
    │             ▼                                        │
    │  contact_enricher (needs key_people + web_profile)   │
    │             │                                        │
    │             ▼                                        │
    │  reviewer (QA gate)                                  │
    │             │                                        │
    │        ┌────┴────┐                                   │
    │   approved    retry → selective_retry → reviewer     │
    │        │                                             │
    │        ▼                                             │
    │  persist_results (save to DB)                        │
    │        │                                             │
    │       END                                            │
    └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from langgraph.graph import StateGraph, END

from orchestrator.config import log
from orchestrator.osint.state import (
    OsintState,
    OSINT_AGENT_KEYS,
    MAX_REVIEW_RETRIES,
)
from orchestrator.osint.web_profiler import web_profiler_agent
from orchestrator.osint.social_intel import social_intel_agent
from orchestrator.osint.key_people import key_people_agent
from orchestrator.osint.news_scanner import news_scanner_agent
from orchestrator.osint.contact_enricher import contact_enricher_agent
from orchestrator.osint.reviewer import reviewer_agent
from orchestrator.db import (
    get_db,
    get_osint_profile,
    get_osint_contacts,
    get_osint_social,
    upsert_osint_profile,
    upsert_osint_contact,
    upsert_osint_social,
    add_osint_news,
    create_osint_run,
    update_osint_run,
)


# ---------------------------------------------------------------------------
# Node: load existing data from DB
# ---------------------------------------------------------------------------


async def _load_existing(state: OsintState) -> dict:
    """Load existing OSINT data + university info from DB."""
    university_id = state["university_id"]

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM universities WHERE id = ?", (university_id,)
        )
        row = await cursor.fetchone()
        university_data = dict(row) if row else {}

        # Load existing IG contacts for this university
        cursor = await db.execute(
            "SELECT * FROM ig_contacts WHERE university_id = ?", (university_id,)
        )
        ig_contacts = [dict(r) for r in await cursor.fetchall()]

    existing_profile = await get_osint_profile(university_id)
    existing_contacts = await get_osint_contacts(university_id)
    existing_social = await get_osint_social(university_id)

    # Create OSINT run log
    run_id = await create_osint_run(university_id, trigger_type="manual")

    log.info(
        "[OSINT Graph] Loaded existing data for uni#%d: profile=%s, contacts=%d, social=%d, ig_contacts=%d",
        university_id,
        bool(existing_profile),
        len(existing_contacts),
        len(existing_social),
        len(ig_contacts),
    )

    return {
        "university_data": university_data,
        "university_name": university_data.get("name", ""),
        "existing_profile": existing_profile,
        "existing_contacts": existing_contacts,
        "existing_social": existing_social,
        "existing_ig_contacts": ig_contacts,
        "run_id": run_id,
        "agents_completed": [],
        "agents_failed": [],
    }


# ---------------------------------------------------------------------------
# Node: parallel research (web_profiler + social_intel + key_people + news)
# ---------------------------------------------------------------------------


async def _parallel_research(state: OsintState) -> dict:
    """Run 4 research agents concurrently."""
    log.info("[OSINT Graph] Starting 4 research agents in parallel...")

    results = await asyncio.gather(
        web_profiler_agent(state),
        social_intel_agent(state),
        key_people_agent(state),
        news_scanner_agent(state),
        return_exceptions=True,
    )

    merged: dict[str, Any] = {}
    agent_names = ["web_profiler", "social_intel", "key_people", "news_scanner"]
    completed = list(state.get("agents_completed", []))
    failed = list(state.get("agents_failed", []))

    for name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            log.error("[OSINT Graph] Agent %s raised: %s", name, result)
            failed.append(name)
        elif isinstance(result, dict):
            merged.update(result)
            completed.append(name)
        else:
            log.warning("[OSINT Graph] Agent %s returned unexpected type: %s", name, type(result))
            failed.append(name)

    merged["agents_completed"] = completed
    merged["agents_failed"] = failed

    succeeded = len(completed) - len(state.get("agents_completed", []))
    log.info("[OSINT Graph] Parallel research done: %d/4 succeeded", succeeded)
    return merged


# ---------------------------------------------------------------------------
# Node: contact enrichment (runs after parallel research)
# ---------------------------------------------------------------------------


async def _enrich_contacts(state: OsintState) -> dict:
    """Run contact enricher (needs key_people + web_profile data)."""
    try:
        result = await contact_enricher_agent(state)
        completed = list(state.get("agents_completed", []))
        completed.append("contact_enricher")
        result["agents_completed"] = completed
        return result
    except Exception as e:
        log.error("[OSINT Graph] Contact enricher failed: %s", e)
        failed = list(state.get("agents_failed", []))
        failed.append("contact_enricher")
        return {"agents_failed": failed}


# ---------------------------------------------------------------------------
# Routing: after reviewer
# ---------------------------------------------------------------------------


def _route_after_review(state: OsintState) -> str:
    """Decide what to do after the reviewer."""
    review = state.get("review")
    retry_count = state.get("review_retry_count", 0)

    if not review:
        return "persist"

    if review.approved:
        log.info("[OSINT Graph] Reviewer approved (score=%.2f)", review.overall_score)
        return "persist"

    if not review.retry_agents:
        log.info("[OSINT Graph] Not approved but no retry targets — accepting")
        return "persist"

    if retry_count > MAX_REVIEW_RETRIES:
        log.warning("[OSINT Graph] Max retries reached — accepting best effort")
        return "persist"

    log.info("[OSINT Graph] Retry requested for: %s", review.retry_agents)
    return "retry"


# ---------------------------------------------------------------------------
# Node: selective retry
# ---------------------------------------------------------------------------

_AGENT_FN = {
    "web_profiler": web_profiler_agent,
    "social_intel": social_intel_agent,
    "key_people": key_people_agent,
    "news_scanner": news_scanner_agent,
}


async def _selective_retry(state: OsintState) -> dict:
    """Re-run only agents flagged by the reviewer."""
    review = state.get("review")
    if not review or not review.retry_agents:
        return {}

    tasks = {}
    for key in review.retry_agents:
        if key in _AGENT_FN:
            tasks[key] = _AGENT_FN[key](state)

    if not tasks:
        return {}

    keys = list(tasks.keys())
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    merged: dict[str, Any] = {}
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            log.error("[OSINT Graph] Retry %s failed: %s", key, result)
        elif isinstance(result, dict):
            merged.update(result)

    return merged


# ---------------------------------------------------------------------------
# Node: persist results to DB
# ---------------------------------------------------------------------------


async def _persist_results(state: OsintState) -> dict:
    """Save OSINT results to the database."""
    university_id = state["university_id"]
    run_id = state.get("run_id", 0)

    log.info("[OSINT Graph] Persisting results for uni#%d", university_id)

    contacts_found = 0
    social_found = 0
    news_found = 0

    # ── Save web profile ──────────────────────────────────────────────
    wp = state.get("web_profile")
    if wp:
        await upsert_osint_profile(
            university_id,
            address=wp.address,
            city=wp.city,
            postal_code=wp.postal_code,
            phone_official=wp.phone_official,
            fax=wp.fax,
            email_official=wp.email_official,
            vision_mission=wp.vision_mission,
            faculty_count=wp.faculty_count,
            faculty_list=json.dumps(wp.faculty_list) if wp.faculty_list else None,
            org_structure=json.dumps(wp.org_structure) if wp.org_structure else None,
            confidence=wp.confidence,
            last_run_id=run_id,
        )

        # Also save email to universities table for easy access
        if wp.email_official:
            from orchestrator.db import update_university_email
            await update_university_email(
                university_id,
                wp.email_official,
                wp.email_source or "osint"
            )

        # Also save student count to universities table
        if wp.student_count and wp.student_count > 0:
            from orchestrator.db import update_student_count
            await update_student_count(university_id, wp.student_count)

    # ── Save social media ─────────────────────────────────────────────
    si = state.get("social_intel")
    if si:
        for acc in si.accounts:
            await upsert_osint_social(
                university_id,
                platform=acc.platform,
                handle=acc.handle,
                url=acc.url,
                followers=acc.followers,
                confidence=acc.confidence,
                source=acc.source,
            )
            social_found += 1

    # ── Save contacts ─────────────────────────────────────────────────
    ec = state.get("enriched_contacts")
    if ec:
        for c in ec.contacts:
            await upsert_osint_contact(
                university_id,
                name=c.name,
                phone=c.phone,
                title=c.title,
                department=c.department,
                email=c.email,
                source=c.source,
                source_url=c.source_url,
                confidence=c.confidence,
                priority=c.priority,
            )
            contacts_found += 1

    # ── Save news ─────────────────────────────────────────────────────
    ns = state.get("news_scan")
    if ns:
        for item in ns.items:
            await add_osint_news(
                university_id,
                title=item.title,
                summary=item.summary,
                url=item.url,
                source=item.source,
                published_date=item.published_date,
                category=item.category,
                relevance_score=item.relevance_score,
            )
            news_found += 1

    # ── Update run log ────────────────────────────────────────────────
    review = state.get("review")
    await update_osint_run(
        run_id,
        status="completed",
        agents_completed=json.dumps(state.get("agents_completed", [])),
        agents_failed=json.dumps(state.get("agents_failed", [])),
        contacts_found=contacts_found,
        social_media_found=social_found,
        news_found=news_found,
        completed_at="datetime('now')",
    )

    log.info(
        "[OSINT Graph] Persisted: contacts=%d, social=%d, news=%d",
        contacts_found, social_found, news_found,
    )

    return {}


# ---------------------------------------------------------------------------
# Build the LangGraph
# ---------------------------------------------------------------------------


def _build_graph() -> StateGraph:
    """Construct and compile the OSINT pipeline."""
    graph = StateGraph(OsintState)

    # Register nodes
    graph.add_node("load_existing", _load_existing)
    graph.add_node("parallel_research", _parallel_research)
    graph.add_node("enrich_contacts", _enrich_contacts)
    graph.add_node("reviewer", reviewer_agent)
    graph.add_node("selective_retry", _selective_retry)
    graph.add_node("persist_results", _persist_results)

    # Entry point
    graph.set_entry_point("load_existing")

    # Flow: load → research → enrich → review → persist
    graph.add_edge("load_existing", "parallel_research")
    graph.add_edge("parallel_research", "enrich_contacts")
    graph.add_edge("enrich_contacts", "reviewer")

    # Reviewer → conditional
    graph.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {
            "persist": "persist_results",
            "retry": "selective_retry",
        },
    )

    # Retry → back to reviewer
    graph.add_edge("selective_retry", "reviewer")

    # Persist → END
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
        log.info("[OSINT Graph] Pipeline compiled successfully")
    return _compiled_graph


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_osint_pipeline(university_id: int) -> dict[str, Any]:
    """
    Run the full OSINT pipeline for a university.

    Returns a summary dict with: run_id, status, contacts_found, etc.
    """
    graph = _get_graph()
    start_time = time.time()

    log.info("[OSINT Graph] Starting OSINT pipeline for university #%d", university_id)

    initial_state: OsintState = {
        "university_id": university_id,
        "university_name": "",
        "university_data": {},
        "existing_profile": None,
        "existing_contacts": [],
        "existing_social": [],
        "existing_ig_contacts": [],
        "web_profile": None,
        "social_intel": None,
        "key_people": None,
        "news_scan": None,
        "enriched_contacts": None,
        "review": None,
        "review_retry_count": 0,
        "run_id": 0,
        "agents_completed": [],
        "agents_failed": [],
        "error": None,
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as e:
        log.error("[OSINT Graph] Pipeline failed for uni#%d: %s", university_id, e)
        run_id = initial_state.get("run_id", 0)
        if run_id:
            await update_osint_run(
                run_id,
                status="failed",
                error=str(e),
                duration_seconds=time.time() - start_time,
            )
        return {"status": "failed", "error": str(e)}

    duration = time.time() - start_time
    run_id = final_state.get("run_id", 0)

    if run_id:
        await update_osint_run(run_id, duration_seconds=duration)

    review = final_state.get("review")
    return {
        "run_id": run_id,
        "status": "completed",
        "university_id": university_id,
        "agents_completed": final_state.get("agents_completed", []),
        "agents_failed": final_state.get("agents_failed", []),
        "review_score": review.overall_score if review else 0.0,
        "duration_seconds": round(duration, 1),
    }
