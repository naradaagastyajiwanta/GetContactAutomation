"""
Specialized sub-agent workers for marketing contact discovery.

Each sub-agent wraps existing pipeline functions and returns structured SubAgentResult.
The orchestrator (mkt_orchestrator.py) decides which sub-agents to spawn and in what order.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from orchestrator.config import log
from . import search as search_flow


@dataclass
class SubAgentResult:
    """Structured result returned by any sub-agent."""
    contacts: list[dict] = field(default_factory=list)
    # [{type: "wa_phone"|"email"|"website", value: str, source_url: str, confidence: float, pic_name: str}]
    ig_handle: str | None = None
    ig_candidates: list[dict] = field(default_factory=list)
    ig_posts_count: int = 0
    tool_calls_made: list[str] = field(default_factory=list)
    summary: str = ""
    tokens_used: int = 0
    duration_seconds: float = 0.0
    success: bool = True
    error: str | None = None
    queries_tried: list[str] = field(default_factory=list)


def _contact_result_to_dict(result: search_flow.ContactResult) -> dict:
    """Convert ContactResult dataclass to plain dict for JSON serialization."""
    return {
        "type": result.contact_type,
        "value": result.value,
        "source_url": result.source_url or "",
        "source_type": result.source_type or "",
        "confidence": float(result.confidence or 0.0),
        "pic_name": result.pic_name or "",
        "pic_title": result.pic_title or "",
    }


def _contacts_to_serializable(
    results: list[search_flow.ContactResult],
    allowed_types: tuple[str, ...] = ("website", "wa_phone", "email"),
) -> list[dict]:
    """Convert and filter a list of ContactResult to JSON-safe dicts."""
    out = []
    for r in results:
        if r.contact_type in allowed_types and r.value:
            out.append(_contact_result_to_dict(r))
    return out


class WebSearchSubAgent:
    """
    Searches for official website and extracts contacts from web pages.
    Wraps search_flow.website_discovery().
    """

    async def run(
        self,
        company_name: str,
        client_type: str | None = None,
        extra_data: dict | None = None,
    ) -> SubAgentResult:
        start = time.monotonic()
        log.info("[WebSearchSubAgent] Starting for: %s (type=%s)", company_name, client_type)
        try:
            hints = extra_data or {}
            avoid_domains = hints.get("avoid_source_domains", [])
            refined_query = hints.get("refined_query")
            force_domain = hints.get("force_domain")

            results = await search_flow.website_discovery(
                company_name,
                hints,
                avoid_domains=avoid_domains or None,
                refined_query=refined_query,
                force_domain=force_domain,
            )
            contacts = _contacts_to_serializable(results)

            # Build summary
            wa_count = sum(1 for c in contacts if c["type"] == "wa_phone")
            email_count = sum(1 for c in contacts if c["type"] == "email")
            website_count = sum(1 for c in contacts if c["type"] == "website")

            summary_parts = []
            if website_count:
                summary_parts.append("website ditemukan")
            if email_count:
                summary_parts.append(f"{email_count} email")
            if wa_count:
                summary_parts.append(f"{wa_count} WA phone")
            summary = (
                f"Web search: {', '.join(summary_parts)}." if summary_parts
                else "Web search: tidak ada kontak ditemukan."
            )

            duration = time.monotonic() - start
            log.info("[WebSearchSubAgent] Done in %.1fs: %s contacts", duration, len(contacts))
            return SubAgentResult(
                contacts=contacts,
                tool_calls_made=["website_discovery"],
                summary=summary,
                duration_seconds=duration,
                success=True,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            log.warning("[WebSearchSubAgent] Error for %s: %s", company_name, exc)
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Web search gagal: {exc}",
                tool_calls_made=["website_discovery"],
                duration_seconds=duration,
            )


class InstagramSubAgent:
    """
    Finds Instagram handle and extracts WA phone numbers from IG posts.
    Wraps search_flow.ig_discovery().
    """

    async def run(
        self,
        company_name: str,
        website_url: str | None = None,
        client_type: str = "",
    ) -> SubAgentResult:
        start = time.monotonic()
        log.info("[InstagramSubAgent] Starting for: %s", company_name)
        try:
            ig_result: search_flow.InstagramDiscoveryResult = await search_flow.ig_discovery(company_name, client_type=client_type)

            contacts = _contacts_to_serializable(ig_result.contacts)
            candidates = ig_result.candidates or []

            # Build summary
            wa_count = sum(1 for c in contacts if c["type"] == "wa_phone")
            handle = ig_result.handle or "tidak ditemukan"
            posts = len(ig_result.posts) if ig_result.posts else 0

            if wa_count:
                summary = f"IG: @{handle}, {posts} posts, {wa_count} WA phone ditemukan."
            elif ig_result.handle:
                summary = f"IG: @{handle} ditemukan, {posts} posts, tapi tidak ada WA phone di posts."
            else:
                summary = f"IG: Tidak ada akun yang cocok ditemukan untuk {company_name}."

            duration = time.monotonic() - start
            log.info("[InstagramSubAgent] Done in %.1fs: handle=%s, %d contacts", duration, handle, len(contacts))
            return SubAgentResult(
                contacts=contacts,
                ig_handle=ig_result.handle,
                ig_candidates=candidates,
                ig_posts_count=posts,
                tool_calls_made=["ig_discovery"],
                summary=summary,
                duration_seconds=duration,
                success=True,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            log.warning("[InstagramSubAgent] Error for %s: %s", company_name, exc)
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Instagram search gagal: {exc}",
                tool_calls_made=["ig_discovery"],
                duration_seconds=duration,
            )


class RegistrySearchSubAgent:
    """
    Searches official Indonesian registries (BNSP, JDIH, Asosiasi).
    Selects the appropriate registry based on client_type.
    """

    async def run(
        self,
        company_name: str,
        client_type: str | None = None,
    ) -> SubAgentResult:
        start = time.monotonic()
        log.info("[RegistrySubAgent] Starting for: %s (type=%s)", company_name, client_type)

        registry_used = "none"
        results: list[search_flow.ContactResult] = []

        try:
            if client_type in ("lsp_p1", "lsp_p2", "lsp_p3"):
                from .discovery.bnsp import bnsp_discovery
                results = await bnsp_discovery(company_name)
                registry_used = "bnsp"
            elif client_type in ("kementerian", "lembaga_negara"):
                from .discovery.jdih import jdih_discovery
                results = await jdih_discovery(company_name)
                registry_used = "jdih"
            elif client_type == "asosiasi":
                from .discovery.asosiasi import asosiasi_discovery
                results = await asosiasi_discovery(company_name)
                registry_used = "asosiasi"
            else:
                # Try BNSP as default for unknown types
                try:
                    from .discovery.bnsp import bnsp_discovery
                    results = await bnsp_discovery(company_name)
                    registry_used = "bnsp_fallback"
                except Exception:
                    results = []
                    registry_used = "none"

            contacts = _contacts_to_serializable(results)

            summary_parts = [f"Registry {registry_used}:"]
            if contacts:
                types = list({c["type"] for c in contacts})
                summary_parts.append(f"{len(contacts)} kontak ({', '.join(types)})")
            else:
                summary_parts.append("tidak ada kontak ditemukan")

            duration = time.monotonic() - start
            log.info("[RegistrySubAgent] Done in %.1fs: registry=%s, %d contacts", duration, registry_used, len(contacts))
            return SubAgentResult(
                contacts=contacts,
                tool_calls_made=[f"search_{registry_used}"],
                summary=" ".join(summary_parts) + ".",
                duration_seconds=duration,
                success=True,
                queries_tried=[company_name],
            )
        except Exception as exc:
            duration = time.monotonic() - start
            log.warning("[RegistrySubAgent] Error for %s: %s", company_name, exc)
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Registry search gagal ({registry_used}): {exc}",
                tool_calls_made=[f"search_{registry_used}"],
                duration_seconds=duration,
            )


class GeminiGapFillSubAgent:
    """
    Last resort: uses Gemini with Google Search grounding to fill contact gaps.
    Wraps search_flow.gemini_grounded_discovery().
    """

    async def run(
        self,
        company_name: str,
        gaps: list[str] | None = None,
        already_found: list[dict] | None = None,
        extra_data: dict | None = None,
    ) -> SubAgentResult:
        start = time.monotonic()
        log.info("[GeminiSubAgent] Starting for: %s, gaps=%s", company_name, gaps)

        # Convert already_found dicts back to ContactResult for the gemini function
        existing_contacts: list[search_flow.ContactResult] = []
        for c in (already_found or []):
            try:
                cr = search_flow.ContactResult(
                    contact_type=c.get("type", ""),
                    value=c.get("value", ""),
                    source_url=c.get("source_url", ""),
                    source_type=c.get("source_type", "manual"),
                    confidence=float(c.get("confidence", 0.5)),
                )
                existing_contacts.append(cr)
            except Exception:
                pass

        try:
            if not search_flow.is_marketing_gemini_enabled():
                return SubAgentResult(
                    success=False,
                    summary="Gemini disabled — GEMINI_API_KEY tidak dikonfigurasi.",
                    tool_calls_made=["gemini_grounded_disabled"],
                    duration_seconds=time.monotonic() - start,
                )

            gemini_result: search_flow.GeminiGroundedDiscoveryResult = await search_flow.gemini_grounded_discovery(
                company_name,
                extra_data or {},
                existing_contacts,
            )

            contacts = _contacts_to_serializable(gemini_result.contacts)
            grounded_urls = gemini_result.grounded_urls or []

            summary_parts = ["Gemini grounded:"]
            if contacts:
                types = list({c["type"] for c in contacts})
                summary_parts.append(f"{len(contacts)} kontak ({', '.join(types)})")
            else:
                summary_parts.append("tidak ada kontak tambahan ditemukan")
            if grounded_urls:
                summary_parts.append(f"dari {len(grounded_urls)} sumber")

            duration = time.monotonic() - start
            log.info("[GeminiSubAgent] Done in %.1fs: %d contacts", duration, len(contacts))
            return SubAgentResult(
                contacts=contacts,
                tool_calls_made=["gemini_grounded_discovery"],
                summary=" ".join(summary_parts) + ".",
                duration_seconds=duration,
                success=True,
                queries_tried=[f"Gemini grounded for gaps: {gaps}"],
            )
        except Exception as exc:
            duration = time.monotonic() - start
            log.warning("[GeminiSubAgent] Error for %s: %s", company_name, exc)
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Gemini search gagal: {exc}",
                tool_calls_made=["gemini_grounded_discovery"],
                duration_seconds=duration,
            )


class WebFallbackSubAgent:
    """
    Additional web search fallback using broader queries.
    Wraps search_flow.web_search_fallback().
    Used when web_search + registry + instagram all failed.
    """

    async def run(self, company_name: str) -> SubAgentResult:
        start = time.monotonic()
        log.info("[WebFallbackSubAgent] Starting for: %s", company_name)
        try:
            results = await search_flow.web_search_fallback(company_name)
            contacts = _contacts_to_serializable(results)

            summary = (
                f"Web fallback: {len(contacts)} kontak ditemukan."
                if contacts
                else "Web fallback: tidak ada kontak ditemukan."
            )

            duration = time.monotonic() - start
            return SubAgentResult(
                contacts=contacts,
                tool_calls_made=["web_search_fallback"],
                summary=summary,
                duration_seconds=duration,
                success=True,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            return SubAgentResult(
                success=False,
                error=str(exc),
                summary=f"Web fallback gagal: {exc}",
                duration_seconds=duration,
            )
