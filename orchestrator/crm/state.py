"""
State definitions for the PIC Profiling (CRM) pipeline.
"""

from __future__ import annotations

from typing import Any, TypedDict

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models for structured agent outputs
# ---------------------------------------------------------------------------


class IdentityResult(BaseModel):
    """Output of the Identity Resolver Agent."""

    full_name: str | None = None
    pddikti_dosen_id: str | None = None
    nidn: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    birth_date_source: str | None = None
    age: int | None = None
    origin_region: str | None = None
    origin_region_source: str | None = None
    photo_url: str | None = None
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)
    source_urls: dict[str, list[str]] = Field(default_factory=dict)


class AcademicResult(BaseModel):
    """Output of the Academic Profiler Agent."""

    jabatan_akademik: str | None = None  # Lektor, Guru Besar, etc.
    pendidikan_tertinggi: str | None = None
    education_history: list[dict[str, Any]] = Field(default_factory=list)
    teaching_subjects: list[str] = Field(default_factory=list)
    tenure_years: int | None = None
    research_topics: list[str] = Field(default_factory=list)
    publications: list[dict[str, Any]] = Field(default_factory=list)
    sinta_id: str | None = None
    scholar_id: str | None = None
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)
    source_urls: dict[str, list[str]] = Field(default_factory=dict)


class SocialProfileResult(BaseModel):
    """Output of the Social Media Profiler Agent."""

    linkedin_url: str | None = None
    instagram_handle: str | None = None
    facebook_url: str | None = None
    twitter_handle: str | None = None
    other_social: dict[str, str] = Field(default_factory=dict)
    email: str | None = None
    phone: str | None = None
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)
    source_urls: dict[str, list[str]] = Field(default_factory=dict)


class CampusContextResult(BaseModel):
    """Output of the Campus Context Agent."""

    campus_problems: list[str] = Field(default_factory=list)
    campus_concerns: list[str] = Field(default_factory=list)
    campus_hopes: list[str] = Field(default_factory=list)
    recent_news: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)
    source_urls: dict[str, list[str]] = Field(default_factory=dict)


class PersonalInterestResult(BaseModel):
    """Output of the Personal Interest Agent (best-effort)."""

    hobbies: list[str] = Field(default_factory=list)
    favorite_food: str | None = None
    outside_activities: list[str] = Field(default_factory=list)
    personality_traits: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)
    source_urls: dict[str, list[str]] = Field(default_factory=dict)


class FamilyInfoResult(BaseModel):
    """Output of the Family Info Agent (best-effort)."""

    marital_status: str | None = None  # 'menikah', 'belum_menikah', 'unknown'
    spouse_name: str | None = None
    children_count: int | None = None
    family_residence: str | None = None
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)
    source_urls: dict[str, list[str]] = Field(default_factory=dict)


class ProfileFieldStatus(BaseModel):
    """Status of a single profile field."""

    field_name: str
    value: Any = None
    source: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    status: str = "not_found"  # 'confirmed', 'found', 'inferred', 'needs_manual', 'not_found'
    confidence: float = 0.0


class CompiledProfile(BaseModel):
    """Final compiled profile with all fields + gap analysis."""

    fields: list[ProfileFieldStatus] = Field(default_factory=list)
    overall_confidence: float = 0.0
    fields_found: int = 0
    fields_total: int = 0
    fields_manual: int = 0
    gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LangGraph State (TypedDict)
# ---------------------------------------------------------------------------


class CrmState(TypedDict, total=False):
    """Central state for PIC Profiling pipeline."""

    # ── Input ──────────────────────────────────────────────────────────────
    request_id: int
    university_id: int | None
    university_name: str
    pic_name: str
    pic_title: str | None
    faculty: str | None

    # ── Existing data ─────────────────────────────────────────────────────
    university_data: dict[str, Any] | None
    existing_conversations: list[dict[str, Any]]

    # ── Name variants (from identity resolver → all downstream agents) ──
    cleaned_name: str | None   # Academic-title-stripped name
    name_variants: list[str]   # Progressive search variants

    # ── Agent outputs ─────────────────────────────────────────────────────
    identity: IdentityResult | None
    academic: AcademicResult | None
    social_profile: SocialProfileResult | None
    campus_context: CampusContextResult | None
    personal_interest: PersonalInterestResult | None
    family_info: FamilyInfoResult | None
    compiled_profile: CompiledProfile | None

    # ── Run tracking ──────────────────────────────────────────────────────
    run_id: int
    agents_completed: list[str]
    agents_failed: list[str]
    error: str | None


CRM_AGENT_KEYS: list[str] = [
    "identity_resolver",
    "academic_profiler",
    "social_profiler",
    "campus_context",
    "personal_interest",
    "family_info",
    "profile_compiler",
]
