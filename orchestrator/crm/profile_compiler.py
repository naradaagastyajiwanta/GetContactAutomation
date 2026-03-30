"""
Profile Compiler Agent — merges all agent outputs into a single
CompiledProfile with field-level statuses and gap analysis.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.crm.state import (
    CrmState,
    CompiledProfile,
    ProfileFieldStatus,
    IdentityResult,
    AcademicResult,
    SocialProfileResult,
    CampusContextResult,
    PersonalInterestResult,
    FamilyInfoResult,
)


# ── Field mapping: (state_key, attr, display_name, category) ──────────
_FIELD_MAP: list[tuple[str, str, str, str]] = [
    # Identity
    ("identity", "full_name", "Nama Lengkap", "identity"),
    ("identity", "gender", "Gender", "identity"),
    ("identity", "age", "Usia", "identity"),
    ("identity", "birth_date", "Tanggal Lahir", "identity"),
    ("identity", "origin_region", "Asal Daerah", "identity"),
    ("identity", "photo_url", "Foto Profil", "identity"),
    # Academic
    ("academic", "jabatan_akademik", "Jabatan Akademik", "academic"),
    ("academic", "pendidikan_tertinggi", "Pendidikan Tertinggi", "academic"),
    ("academic", "education_history", "Riwayat Pendidikan", "academic"),
    ("academic", "teaching_subjects", "Mata Kuliah", "academic"),
    ("academic", "tenure_years", "Masa Kerja (tahun)", "academic"),
    ("academic", "research_topics", "Topik Riset", "academic"),
    ("academic", "publications", "Publikasi", "academic"),
    # Social / Contact
    ("social_profile", "linkedin_url", "LinkedIn", "social"),
    ("social_profile", "instagram_handle", "Instagram", "social"),
    ("social_profile", "facebook_url", "Facebook", "social"),
    ("social_profile", "twitter_handle", "Twitter/X", "social"),
    ("social_profile", "email", "Email", "social"),
    ("social_profile", "phone", "Telepon", "social"),
    # Campus Context
    ("campus_context", "campus_problems", "Masalah Kampus", "campus"),
    ("campus_context", "campus_concerns", "Kekhawatiran Kampus", "campus"),
    ("campus_context", "campus_hopes", "Harapan Kampus", "campus"),
    ("campus_context", "recent_news", "Berita Terbaru", "campus"),
    # Personal
    ("personal_interest", "hobbies", "Hobi", "personal"),
    ("personal_interest", "favorite_food", "Makanan Favorit", "personal"),
    ("personal_interest", "outside_activities", "Aktivitas Luar Kampus", "personal"),
    ("personal_interest", "personality_traits", "Sifat Kepribadian", "personal"),
    # Social Post Analysis
    ("social_post_analysis", "personality_summary", "Ringkasan Kepribadian", "personal"),
    ("social_post_analysis", "recent_topics", "Topik Relevan Sosial Media", "personal"),
    ("social_post_analysis", "communication_style", "Gaya Komunikasi", "personal"),
    ("social_post_analysis", "social_behavior_insights", "Perilaku Sosial", "personal"),
    # Family
    ("family_info", "marital_status", "Status Pernikahan", "family"),
    ("family_info", "spouse_name", "Nama Pasangan", "family"),
    ("family_info", "children_count", "Jumlah Anak", "family"),
    ("family_info", "family_residence", "Tempat Tinggal Keluarga", "family"),
]


def _is_filled(value: Any) -> bool:
    """Check whether a field value counts as 'filled'."""
    if value is None:
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    if isinstance(value, str) and value.strip() in ("", "unknown"):
        return False
    return True


def _determine_status(value: Any, source: str | None) -> str:
    if not _is_filled(value):
        return "not_found"
    if source and "pddikti" in source:
        return "confirmed"
    if source:
        return "found"
    return "inferred"


async def profile_compiler_agent(state: CrmState) -> dict:
    """
    Compile all agent outputs into a unified CompiledProfile.

    Returns partial state update with `compiled_profile`.
    """
    log.info("[ProfileCompiler] Compiling profile for request %s", state.get("request_id"))

    # Gather agent outputs
    log.info("[DEBUG] social_profile: %s", state.get("social_profile")); agent_outputs: dict[str, Any] = {
        "identity": state.get("identity"),
        "academic": state.get("academic"),
        "social_profile": state.get("social_profile"),
        "campus_context": state.get("campus_context"),
        "personal_interest": state.get("personal_interest"),
        "family_info": state.get("family_info"),
        "social_post_analysis": state.get("social_post_analysis"),
    }

    fields: list[ProfileFieldStatus] = []
    found_count = 0
    manual_count = 0
    gaps: list[str] = []

    for state_key, attr, display_name, category in _FIELD_MAP:
        agent_result = agent_outputs.get(state_key)
        value = getattr(agent_result, attr, None) if agent_result else None

        # Determine source
        source = None
        if agent_result and hasattr(agent_result, "sources"):
            srcs = agent_result.sources
            # Deduplicate sources preserving order
            source = ", ".join(list(dict.fromkeys(srcs))) if srcs else None

        # Determine confidence from agent
        confidence = 0.0
        if agent_result and hasattr(agent_result, "confidence"):
            confidence = agent_result.confidence

        # Extract source URLs for this specific field
        field_urls: list[str] = []
        if agent_result and hasattr(agent_result, "source_urls"):
            field_urls = agent_result.source_urls.get(attr, [])

        status = _determine_status(value, source)

        if _is_filled(value):
            found_count += 1
        elif category in ("identity", "academic"):
            # Important fields → flag for manual
            gaps.append(display_name)
            manual_count += 1
            status = "needs_manual"

        fields.append(
            ProfileFieldStatus(
                field_name=display_name,
                value=_serialize_value(value),
                source=source,
                source_urls=field_urls,
                status=status,
                confidence=confidence,
            )
        )

    total = len(_FIELD_MAP)
    overall = round(found_count / total, 2) if total else 0.0

    compiled = CompiledProfile(
        fields=fields,
        overall_confidence=overall,
        fields_found=found_count,
        fields_total=total,
        fields_manual=manual_count,
        gaps=gaps,
    )

    log.info(
        "[ProfileCompiler] Done: %d/%d found, %d gaps, overall=%.2f",
        found_count, total, len(gaps), overall,
    )

    return {"compiled_profile": compiled}


def _serialize_value(value: Any) -> Any:
    """Ensure value is JSON-serializable for storage."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return value[:50]  # Cap list length
    if isinstance(value, dict):
        return value
    return str(value)
