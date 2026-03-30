"""
LangGraph StateGraph — orchestrates the multi-agent research pipeline.

Workflow
--------

    ┌──────────────────────────────────────────────────────────────────────┐
    │                         START                                        │
    │                           │                                          │
    │                           ▼                                          │
    │                   ┌───────────────┐                                  │
    │                   │ rector_agent  │  Q: Who is the rector?           │
    │                   └───────┬───────┘                                  │
    │                           │                                          │
    │                     ┌─────▼─────┐                                    │
    │                     │ rector    │                                     │
    │                     │  gate     │                                     │
    │                     └──┬──┬──┬──┘                                    │
    │          found+city   │  │  │ not found (retry ≤ 1)                 │
    │                       │  │  └──────► rector_agent (loop)            │
    │                       │  │  │ not found (retry > 1)                  │
    │                       │  │  └──────► finalize (with partial data)   │
    │                       │  │ found but NO birth city                   │
    │                       │  └──► birth_city_lookup ──┐                  │
    │                       ▼                           │                   │
    │              ┌──────────────────┐◄────────────────┘                  │
    │              │ research_topics  │  6 agents run in parallel:         │
    │              │  (asyncio.gather)│  tourism ×3, food ×2, psycho ×1  │
    │              └────────┬─────────┘                                    │
    │                       ▼                                              │
    │              ┌──────────────────┐                                    │
    │              │    reviewer      │  Validates quality & consistency   │
    │              └────────┬─────────┘                                    │
    │                       │                                              │
    │                 ┌─────▼─────┐                                        │
    │                 │ review    │                                         │
    │                 │  gate     │                                         │
    │                 └──┬──┬──┬──┘                                        │
    │         approved  │  │  │ not approved (retry ≤ 1)                  │
    │                   │  │  └──► selective_retry ──► reviewer (loop)    │
    │                   │  │ not approved (retry > 1)                      │
    │                   │  └────► finalize (accept best-effort)           │
    │                   ▼                                                   │
    │              ┌──────────────────┐                                    │
    │              │    finalize      │  Convert state → legacy dict       │
    │              └────────┬─────────┘                                    │
    │                       ▼                                              │
    │                      END                                             │
    └──────────────────────────────────────────────────────────────────────┘

Retry semantics:
    - Rector: max 1 retry if name == "Tidak ditemukan"
    - Review: max 1 selective retry — only re-runs agents flagged by reviewer
    - After max retries, pipeline accepts best-effort result (never blocks)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from langgraph.graph import StateGraph, END

from orchestrator.config import log, cfg
from orchestrator.research_agents.state import (
    ResearchState,
    TopicResult,
    MAX_RECTOR_RETRIES,
    MAX_REVIEW_RETRIES,
    TOPIC_AGENT_KEYS,
)
from orchestrator.research_agents.agents.rector_agent import rector_agent
from orchestrator.research_agents.agents.topic_agents import (
    tourism_birth_youth_agent,
    tourism_birth_current_agent,
    tourism_uni_city_agent,
    food_birth_city_agent,
    food_uni_city_agent,
)
from orchestrator.research_agents.agents.psychographics_agent import psychographics_agent
from orchestrator.research_agents.agents.birth_city_lookup import birth_city_lookup
from orchestrator.research_agents.reviewer import reviewer_agent


# ---------------------------------------------------------------------------
# Agent function registry (for selective retries)
# ---------------------------------------------------------------------------

_TOPIC_AGENT_FN = {
    "tourism_birth_youth": tourism_birth_youth_agent,
    "tourism_birth_current": tourism_birth_current_agent,
    "tourism_uni_city": tourism_uni_city_agent,
    "food_birth_city": food_birth_city_agent,
    "food_uni_city": food_uni_city_agent,
    "psychographics": psychographics_agent,
}


# ---------------------------------------------------------------------------
# Gate nodes (routing logic)
# ---------------------------------------------------------------------------


def _route_after_rector(state: ResearchState) -> str:
    """Decide what happens after the rector agent finishes."""
    ri = state.get("rector_info")
    retry_count = state.get("rector_retry_count", 0)

    if ri and ri.rector_name and ri.rector_name != "Tidak ditemukan":
        # Rector found — check if birth city is missing
        if not ri.rector_birth_city or ri.rector_birth_city == "Tidak ditemukan":
            log.info("[Graph] Rector found but birth city missing → running birth_city_lookup")
            return "lookup_birth_city"
        log.info("[Graph] Rector found (with birth city) → proceeding to topic research")
        return "topics"

    if retry_count < MAX_RECTOR_RETRIES:
        log.info("[Graph] Rector not found — retrying (%d/%d)", retry_count + 1, MAX_RECTOR_RETRIES)
        return "retry_rector"

    log.warning("[Graph] Rector not found after %d retries — proceeding with partial data", retry_count)
    return "finalize_early"


def _route_after_review(state: ResearchState) -> str:
    """Decide what happens after the reviewer finishes."""
    review = state.get("review")
    retry_count = state.get("review_retry_count", 0)

    if not review:
        log.warning("[Graph] No review result — accepting as-is")
        return "approved"

    if review.approved:
        log.info("[Graph] Reviewer approved (score=%.2f)", review.overall_score)
        return "approved"

    if not review.retry_agents:
        log.info("[Graph] Reviewer not approved but no retry targets — accepting")
        return "approved"

    # retry_count is already incremented by reviewer, so use > (not >=)
    if retry_count > MAX_REVIEW_RETRIES:
        log.warning(
            "[Graph] Reviewer not approved but max retries (%d) reached — accepting best effort",
            MAX_REVIEW_RETRIES,
        )
        return "accept_best_effort"

    log.info(
        "[Graph] Reviewer requests retry for: %s (attempt %d/%d)",
        review.retry_agents,
        retry_count,
        MAX_REVIEW_RETRIES,
    )
    return "retry_topics"


# ---------------------------------------------------------------------------
# Composite nodes
# ---------------------------------------------------------------------------


async def _increment_rector_retry(state: ResearchState) -> dict:
    """Increment rector retry counter before looping back."""
    return {"rector_retry_count": state.get("rector_retry_count", 0) + 1}


async def _research_topics_parallel(state: ResearchState) -> dict:
    """
    Fan-out: run 6 topic agents concurrently via asyncio.gather.

    Each agent makes its own Gemini call → truly parallel execution.
    """
    log.info("[Graph] Starting 6 topic agents in parallel...")

    results = await asyncio.gather(
        tourism_birth_youth_agent(state),
        tourism_birth_current_agent(state),
        tourism_uni_city_agent(state),
        food_birth_city_agent(state),
        food_uni_city_agent(state),
        psychographics_agent(state),
        return_exceptions=True,
    )

    merged: dict[str, Any] = {}
    agent_names = TOPIC_AGENT_KEYS

    for name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            log.error("[Graph] Agent %s raised: %s", name, result)
            merged[name] = TopicResult(content=f"Error: {result}", confidence="low")
        elif isinstance(result, dict):
            merged.update(result)
        else:
            log.warning("[Graph] Agent %s returned unexpected type: %s", name, type(result))

    succeeded = sum(1 for k in agent_names if merged.get(k) and "Error" not in str(getattr(merged.get(k), "content", "")))
    log.info("[Graph] Topic agents done: %d/%d succeeded", succeeded, len(agent_names))

    return merged


async def _selective_retry(state: ResearchState) -> dict:
    """
    Re-run only the agents flagged by the reviewer.

    Falls back to the existing result if the re-run fails.
    """
    review = state.get("review")
    if not review or not review.retry_agents:
        return {}

    retry_targets = review.retry_agents
    log.info("[Graph] Selective retry for: %s", retry_targets)

    tasks = {}

    # Handle rector retry
    if "rector_info" in retry_targets:
        tasks["rector_info"] = rector_agent(state)

    # Handle topic retries
    for key in retry_targets:
        if key in _TOPIC_AGENT_FN:
            tasks[key] = _TOPIC_AGENT_FN[key](state)

    if not tasks:
        log.warning("[Graph] No valid retry targets found in: %s", retry_targets)
        return {}

    # Run retries concurrently
    keys = list(tasks.keys())
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    merged: dict[str, Any] = {}
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            log.error("[Graph] Retry for %s failed: %s", key, result)
            # Keep existing result (don't overwrite)
        elif isinstance(result, dict):
            merged.update(result)

    log.info("[Graph] Selective retry done: %d/%d updated", len(merged), len(keys))
    return merged


async def _finalize(state: ResearchState) -> dict:
    """Convert the ResearchState into the legacy dict format for backward compat."""
    return {"final_result": _state_to_legacy_dict(state)}


# ---------------------------------------------------------------------------
# Legacy dict conversion
# ---------------------------------------------------------------------------


def _state_to_legacy_dict(state: ResearchState) -> dict[str, Any]:
    """
    Convert multi-agent ResearchState → same dict format as the old
    single-call ``research_university_background()`` for backward compat.
    """
    ri = state.get("rector_info")
    review = state.get("review")

    result: dict[str, Any] = {
        "rector_name": ri.rector_name if ri else "Tidak ditemukan",
        "rector_birth_year": ri.rector_birth_year if ri else None,
        "rector_birth_city": ri.rector_birth_city if ri else "Tidak ditemukan",
        "university_city": (ri.university_city if ri else None) or state.get("university_city") or "Tidak ditemukan",
    }

    # Source URLs — each agent provides its own grounding URLs (much more accurate)
    result["rector_source"] = ri.source_url if ri else None

    # Topic results
    topic_mapping = {
        "tourism_birth_youth": ("tourism_rector_birth_youth", "tourism_rector_birth_youth_source"),
        "tourism_birth_current": ("tourism_rector_birth_current", "tourism_rector_birth_current_source"),
        "tourism_uni_city": ("tourism_university_city", "tourism_university_city_source"),
        "food_birth_city": ("food_rector_birth_city", "food_rector_birth_city_source"),
        "food_uni_city": ("food_university_city", "food_university_city_source"),
        "psychographics": ("psychographics", "psychographics_source"),
    }

    all_extra_urls: list[str] = []

    for state_key, (content_key, source_key) in topic_mapping.items():
        tr: TopicResult | None = state.get(state_key)  # type: ignore[literal-required]
        if tr:
            result[content_key] = tr.content
            result[source_key] = tr.source_url
            # Collect extra grounding URLs
            if tr.grounding_urls:
                all_extra_urls.extend(tr.grounding_urls[1:])  # skip first (already in source_url)
        else:
            result[content_key] = "Tidak ditemukan"
            result[source_key] = None

    # Collect rector's extra grounding URLs
    if ri and ri.grounding_urls:
        all_extra_urls.extend(ri.grounding_urls[1:])

    # Legacy sources list (for DmsResearchCard backward compat)
    result["sources"] = list(dict.fromkeys(all_extra_urls))  # dedupe preserving order

    # Notes with review info
    notes_parts: list[str] = []
    if review:
        notes_parts.append(f"Review score: {review.overall_score:.2f}")
        if review.feedback:
            for k, v in review.feedback.items():
                if v and not k.startswith("_"):
                    notes_parts.append(f"  {k}: {v}")
    result["notes"] = "\n".join(notes_parts) if notes_parts else None

    # Metadata
    result["_multi_agent"] = True
    result["_review_score"] = review.overall_score if review else None
    result["_review_approved"] = review.approved if review else None

    return result


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------


def _build_graph() -> StateGraph:
    """Construct and compile the LangGraph research workflow."""
    graph = StateGraph(ResearchState)

    # ── Register nodes ──────────────────────────────────────────────────
    graph.add_node("rector_agent", rector_agent)
    graph.add_node("increment_rector_retry", _increment_rector_retry)
    graph.add_node("birth_city_lookup", birth_city_lookup)
    graph.add_node("research_topics", _research_topics_parallel)
    graph.add_node("reviewer", reviewer_agent)
    graph.add_node("selective_retry", _selective_retry)
    graph.add_node("finalize", _finalize)

    # ── Entry point ─────────────────────────────────────────────────────
    graph.set_entry_point("rector_agent")

    # ── Rector → gate ───────────────────────────────────────────────────
    graph.add_conditional_edges(
        "rector_agent",
        _route_after_rector,
        {
            "topics": "research_topics",
            "lookup_birth_city": "birth_city_lookup",
            "retry_rector": "increment_rector_retry",
            "finalize_early": "finalize",
        },
    )

    # Retry loop: increment counter → back to rector_agent
    graph.add_edge("increment_rector_retry", "rector_agent")

    # Birth city lookup → proceed to topics (regardless of result)
    graph.add_edge("birth_city_lookup", "research_topics")

    # ── Topics → Reviewer ───────────────────────────────────────────────
    graph.add_edge("research_topics", "reviewer")

    # ── Reviewer → gate ─────────────────────────────────────────────────
    graph.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {
            "approved": "finalize",
            "accept_best_effort": "finalize",
            "retry_topics": "selective_retry",
        },
    )

    # Retry loop: selective_retry → back to reviewer
    graph.add_edge("selective_retry", "reviewer")

    # ── Finalize → END ──────────────────────────────────────────────────
    graph.add_edge("finalize", END)

    return graph


# ---------------------------------------------------------------------------
# Compiled graph (singleton)
# ---------------------------------------------------------------------------

_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph().compile()
        log.info("[Graph] Research pipeline compiled successfully")
    return _compiled_graph


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_research(
    university_name: str,
    university_city: str | None = None,
    schedule_date: str | None = None,
) -> dict[str, Any]:
    """
    Run the full multi-agent research pipeline.

    Same return format as the legacy ``research_university_background()``:
    a flat dict with rector_name, tourism fields, food fields, sources, etc.
    """
    graph = _get_graph()

    log.info(
        "[Graph] Starting multi-agent research: %s (%s), date=%s",
        university_name,
        university_city or "?",
        schedule_date or "?",
    )

    initial_state: ResearchState = {
        "university_name": university_name,
        "university_city": university_city,
        "schedule_date": schedule_date,
        "rector_info": None,
        "rector_retry_count": 0,
        "tourism_birth_youth": None,
        "tourism_birth_current": None,
        "tourism_uni_city": None,
        "food_birth_city": None,
        "food_uni_city": None,
        "psychographics": None,
        "review": None,
        "review_retry_count": 0,
        "final_result": None,
    }

    final_state = await graph.ainvoke(initial_state)

    result = final_state.get("final_result")
    if not result:
        log.error("[Graph] Pipeline completed but no final_result — building fallback")
        result = _state_to_legacy_dict(final_state)

    review = final_state.get("review")
    log.info(
        "[Graph] Research complete: rector=%s, score=%s, approved=%s",
        result.get("rector_name", "?"),
        review.overall_score if review else "N/A",
        review.approved if review else "N/A",
    )

    return result
