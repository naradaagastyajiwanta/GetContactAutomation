"""
State definitions for the multi-agent research pipeline.

Uses TypedDict for LangGraph state channels and Pydantic models
for structured agent outputs.
"""

from __future__ import annotations

from typing import Any, TypedDict

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models for structured agent outputs
# ---------------------------------------------------------------------------


class RectorInfo(BaseModel):
    """Output of the Rector Agent."""

    rector_name: str = Field(description="Full name with academic title")
    rector_birth_year: int | None = Field(default=None, description="Year of birth")
    rector_birth_city: str | None = Field(default=None, description="City/regency of birth")
    university_city: str | None = Field(default=None, description="City where main campus is located")
    source_url: str | None = Field(default=None, description="Primary grounding URL")
    grounding_urls: list[str] = Field(default_factory=list, description="All resolved grounding URLs")
    confidence: str = Field(default="medium", description="high / medium / low")
    raw_text: str = Field(default="", description="Raw Gemini response for debugging")


class TopicResult(BaseModel):
    """Output of a single topic agent (tourism / food)."""

    content: str = Field(description="2–3 item description")
    source_url: str | None = Field(default=None, description="Best grounding URL for this topic")
    grounding_urls: list[str] = Field(default_factory=list, description="All resolved grounding URLs")
    confidence: str = Field(default="medium", description="high / medium / low")


class ReviewVerdict(BaseModel):
    """Output of the Reviewer Agent."""

    approved: bool = Field(description="Whether the overall result is acceptable")
    overall_score: float = Field(default=0.0, description="Quality score 0.0–1.0")
    feedback: dict[str, str] = Field(
        default_factory=dict,
        description="Per-field feedback, e.g. {'rector_info': 'looks correct', ...}",
    )
    retry_agents: list[str] = Field(
        default_factory=list,
        description="Agent keys to re-run, e.g. ['tourism_birth_youth', 'food_uni_city']",
    )


# ---------------------------------------------------------------------------
# LangGraph State (TypedDict)
# ---------------------------------------------------------------------------


class ResearchState(TypedDict, total=False):
    """Central state passed through the LangGraph workflow."""

    # ── Input (set once at invocation) ──────────────────────────────────────
    university_name: str
    university_city: str | None
    schedule_date: str | None

    # ── Agent outputs ───────────────────────────────────────────────────────
    rector_info: RectorInfo | None
    rector_retry_count: int

    tourism_birth_youth: TopicResult | None
    tourism_birth_current: TopicResult | None
    tourism_uni_city: TopicResult | None
    food_birth_city: TopicResult | None
    food_uni_city: TopicResult | None
    psychographics: TopicResult | None

    # ── Reviewer ────────────────────────────────────────────────────────────
    review: ReviewVerdict | None
    review_retry_count: int

    # ── Final output ────────────────────────────────────────────────────────
    final_result: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: All topic agent keys (used by orchestrator for fan-out and retry)
TOPIC_AGENT_KEYS: list[str] = [
    "tourism_birth_youth",
    "tourism_birth_current",
    "tourism_uni_city",
    "food_birth_city",
    "food_uni_city",
    "psychographics",
]

#: Maximum retries for the rector agent
MAX_RECTOR_RETRIES = 1

#: Maximum review→retry loops
MAX_REVIEW_RETRIES = 1
