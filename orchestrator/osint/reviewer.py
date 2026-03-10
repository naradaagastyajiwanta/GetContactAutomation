"""
Reviewer Agent — QA gate for the OSINT pipeline.

Validates data consistency, computes confidence scores,
flags data that needs manual verification.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.osint.state import OsintState, ReviewVerdict


async def reviewer_agent(state: OsintState) -> dict:
    """
    Validate OSINT results for consistency and quality.

    Returns partial state update with `review`.
    """
    uni_name = state.get("university_name", "")
    log.info("[Reviewer] Starting QA review for %s", uni_name)

    feedback: dict[str, str] = {}
    retry_agents: list[str] = []
    score = 0.0
    max_score = 0.0

    # ── Check web_profile ──────────────────────────────────────────────
    max_score += 1.0
    wp = state.get("web_profile")
    if wp:
        if wp.address or wp.faculty_count:
            score += 1.0
            feedback["web_profiler"] = "OK"
        else:
            score += 0.3
            feedback["web_profiler"] = "Partial — missing address or faculty data"
    else:
        feedback["web_profiler"] = "MISSING — no web profile data"
        retry_agents.append("web_profiler")

    # ── Check social_intel ─────────────────────────────────────────────
    max_score += 1.0
    si = state.get("social_intel")
    if si and si.accounts:
        score += 1.0
        feedback["social_intel"] = f"OK — {len(si.accounts)} accounts found"
    elif si:
        score += 0.5
        feedback["social_intel"] = "No new social accounts found (may all be known)"
    else:
        feedback["social_intel"] = "MISSING"

    # ── Check key_people ───────────────────────────────────────────────
    max_score += 1.0
    kp = state.get("key_people")
    if kp and kp.people:
        if len(kp.people) >= 3:
            score += 1.0
            feedback["key_people"] = f"OK — {len(kp.people)} people found"
        else:
            score += 0.6
            feedback["key_people"] = f"Partial — only {len(kp.people)} people found"
    else:
        feedback["key_people"] = "MISSING — no key people found"
        retry_agents.append("key_people")

    # ── Check news_scan ────────────────────────────────────────────────
    max_score += 1.0
    ns = state.get("news_scan")
    if ns and ns.items:
        if len(ns.items) >= 3:
            score += 1.0
            feedback["news_scanner"] = f"OK — {len(ns.items)} news items"
        else:
            score += 0.5
            feedback["news_scanner"] = f"Partial — only {len(ns.items)} news items"
    else:
        feedback["news_scanner"] = "No news found"
        score += 0.2  # News can genuinely be absent

    # ── Check enriched_contacts ────────────────────────────────────────
    max_score += 1.0
    ec = state.get("enriched_contacts")
    if ec and ec.contacts:
        score += 1.0
        feedback["contact_enricher"] = f"OK — {len(ec.contacts)} contacts"
    else:
        feedback["contact_enricher"] = "No contacts found"
        score += 0.1

    # ── Compute final score ────────────────────────────────────────────
    overall_score = round(score / max_score, 2) if max_score > 0 else 0.0
    approved = overall_score >= 0.5

    # Only retry on first review
    retry_count = state.get("review_retry_count", 0)
    if retry_count > 0:
        retry_agents = []

    verdict = ReviewVerdict(
        approved=approved,
        overall_score=overall_score,
        feedback=feedback,
        retry_agents=retry_agents,
    )

    log.info(
        "[Reviewer] %s: score=%.2f, approved=%s, retry=%s",
        uni_name, overall_score, approved, retry_agents,
    )

    return {
        "review": verdict,
        "review_retry_count": retry_count + 1,
    }
