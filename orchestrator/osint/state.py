"""
State definitions for the University OSINT pipeline.

Uses TypedDict for LangGraph state channels and Pydantic models
for structured agent outputs.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models for structured agent outputs
# ---------------------------------------------------------------------------


class WebProfileResult(BaseModel):
    """Output of the Web Profiler Agent."""

    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    phone_official: str | None = None
    fax: str | None = None
    email_official: str | None = None
    vision_mission: str | None = None
    faculty_count: int | None = None
    faculty_list: list[dict[str, Any]] = Field(default_factory=list)
    org_structure: dict[str, Any] | None = None
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)


class SocialMediaEntry(BaseModel):
    """A single social media account."""

    platform: str
    handle: str
    url: str | None = None
    followers: int | None = None
    confidence: float = 0.0
    source: str | None = None


class SocialIntelResult(BaseModel):
    """Output of the Social Intel Agent."""

    accounts: list[SocialMediaEntry] = Field(default_factory=list)


class KeyPerson(BaseModel):
    """A key person at the university."""

    name: str
    title: str | None = None
    department: str | None = None
    phone: str | None = None
    email: str | None = None
    source: str | None = None
    source_url: str | None = None
    confidence: float = 0.0


class KeyPeopleResult(BaseModel):
    """Output of the Key People Finder Agent."""

    people: list[KeyPerson] = Field(default_factory=list)


class NewsItem(BaseModel):
    """A single news or event item."""

    title: str
    summary: str | None = None
    url: str | None = None
    source: str | None = None
    published_date: str | None = None
    category: str | None = None
    relevance_score: float = 0.0


class NewsScanResult(BaseModel):
    """Output of the News Scanner Agent."""

    items: list[NewsItem] = Field(default_factory=list)


class EnrichedContact(BaseModel):
    """A contact enriched from multiple sources."""

    name: str | None = None
    title: str | None = None
    department: str | None = None
    phone: str | None = None
    email: str | None = None
    source: str | None = None
    source_url: str | None = None
    confidence: float = 0.0
    priority: int = 0  # higher = more important role


class ContactEnrichResult(BaseModel):
    """Output of the Contact Enricher Agent."""

    contacts: list[EnrichedContact] = Field(default_factory=list)


class ReviewVerdict(BaseModel):
    """Output of the Reviewer Agent."""

    approved: bool = False
    overall_score: float = 0.0
    feedback: dict[str, str] = Field(default_factory=dict)
    retry_agents: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LangGraph State (TypedDict)
# ---------------------------------------------------------------------------


class OsintState(TypedDict, total=False):
    """Central state passed through the LangGraph OSINT workflow."""

    # ── Input ──────────────────────────────────────────────────────────────
    university_id: int
    university_name: str
    university_data: dict[str, Any]  # full row from universities table

    # ── Existing data from DB (loaded at start) ───────────────────────────
    existing_profile: dict[str, Any] | None
    existing_contacts: list[dict[str, Any]]
    existing_social: list[dict[str, Any]]
    existing_ig_contacts: list[dict[str, Any]]

    # ── Agent outputs ─────────────────────────────────────────────────────
    web_profile: WebProfileResult | None
    social_intel: SocialIntelResult | None
    key_people: KeyPeopleResult | None
    news_scan: NewsScanResult | None
    enriched_contacts: ContactEnrichResult | None

    # ── Reviewer ──────────────────────────────────────────────────────────
    review: ReviewVerdict | None
    review_retry_count: int

    # ── Run tracking ──────────────────────────────────────────────────────
    run_id: int
    agents_completed: list[str]
    agents_failed: list[str]
    error: str | None


# ---------------------------------------------------------------------------
# Agent keys
# ---------------------------------------------------------------------------

OSINT_AGENT_KEYS: list[str] = [
    "web_profiler",
    "social_intel",
    "key_people",
    "news_scanner",
    "contact_enricher",
]

MAX_REVIEW_RETRIES = 1
