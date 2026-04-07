"""Agentic orchestration runner for marketing client discovery."""

from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Any

from orchestrator.config import log
from orchestrator.websocket import manager as ws_manager

from . import groups as mkt
from . import search as search_flow
from .discovery import bnsp_discovery, jdih_discovery, asosiasi_discovery

DISCOVERY_STAGES: dict[str | None, list[str]] = {
    "lsp_p1": ["bnsp", "website", "ig", "gemini"],
    "lsp_p2": ["bnsp", "website", "ig", "gemini"],
    "lsp_p3": ["bnsp", "website", "ig", "gemini"],
    "lembaga_negara": ["jdih", "website", "ig", "gemini"],
    "kementerian": ["jdih", "website", "ig", "gemini"],
    "asosiasi": ["asosiasi", "website", "ig", "gemini"],
    "bumn": ["website", "annual_report", "ig", "gemini"],
    "swasta_besar": ["website", "ig", "gemini"],
    "lpk": ["website", "ig", "gemini"],
    "dinas": ["website", "lkip", "ig", "gemini"],
    # fallback for unknown types
    None: ["website", "ig", "gemini"],
}


ACTIVE_ORCHESTRATION_STATES = {"planning", "collecting", "verifying", "resolving", "deciding", "repairing"}


def _serialize_contact(result: search_flow.ContactResult) -> dict[str, Any]:
    return {
        "contact_type": result.contact_type,
        "value": result.value,
        "source_url": result.source_url,
        "source_type": result.source_type,
        "confidence": result.confidence,
        "pic_name": result.pic_name,
        "pic_title": result.pic_title,
    }


def _has_contact(results: list[search_flow.ContactResult], contact_type: str) -> bool:
    return any(result.contact_type == contact_type and result.value for result in results)


def _build_plan(client: dict[str, Any], mode: str) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "mode": mode,
        "client_id": client["id"],
        "group_id": client["group_id"],
        "client_name": client["name"],
    }

    if mode == "full_search":
        plan["stages"] = ["website", "instagram", "web_fallback", "gemini_grounded", "finalize"]
        plan["stop_when"] = {
            "has_email": True,
            "has_wa_phone": True,
        }
        plan["instagram_policy"] = "always_run_full_instagram_discovery"
        plan["web_fallback_policy"] = "run_if_website_and_instagram_still_missing_required_contact"
        plan["gemini_policy"] = "run_grounded_gap_fill_when_key_contacts_or_website_are_missing"
        return plan

    if mode == "instagram_scrape_retry":
        plan["stages"] = ["instagram", "sanitize"]
        plan["instagram_policy"] = "rerun_selected_handles"
        return plan

    if mode == "instagram_contact_retry":
        plan["stages"] = ["instagram_contact_extract", "sanitize"]
        plan["instagram_policy"] = "reuse_stored_posts"
        return plan

    plan["stages"] = []
    return plan


async def _set_client_stage(
    client_id: int,
    run_id: int,
    state: str,
    stage: str | None,
    *,
    summary: dict[str, Any] | None = None,
) -> None:
    await mkt.update_client_orchestration_state(
        client_id,
        state,
        stage=stage,
        summary=summary,
        current_run_id=run_id,
    )
    await mkt.update_orchestration_run(
        run_id,
        state=state,
        current_stage=stage,
        summary=summary,
    )


async def _record_contacts(
    run_id: int,
    client_id: int,
    stage: str,
    results: list[search_flow.ContactResult],
    *,
    status: str,
    reason: str | None = None,
) -> None:
    for result in results:
        await mkt.add_orchestration_evidence(
            run_id,
            client_id,
            stage,
            "contact_candidate",
            source_type=result.source_type,
            source_url=result.source_url,
            value=result.value,
            confidence=result.confidence,
            status=status,
            reason=reason,
            payload=_serialize_contact(result),
        )


async def _record_stage_summary(
    run_id: int,
    client_id: int,
    stage: str,
    evidence_type: str,
    *,
    status: str,
    reason: str | None = None,
    payload: dict[str, Any] | list[Any] | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    value: str | None = None,
    confidence: float = 0.0,
) -> None:
    await mkt.add_orchestration_evidence(
        run_id,
        client_id,
        stage,
        evidence_type,
        source_type=source_type,
        source_url=source_url,
        value=value,
        confidence=confidence,
        status=status,
        reason=reason,
        payload=payload,
    )


async def _persist_final_results(
    client_id: int,
    stage1: list[search_flow.ContactResult],
    stage2: search_flow.InstagramDiscoveryResult,
    stage3: list[search_flow.ContactResult],
    stage4: list[search_flow.ContactResult],
) -> tuple[list[search_flow.ContactResult], int]:
    await mkt.replace_client_ig_candidates(client_id, stage2.candidates)
    await mkt.replace_client_ig_posts(client_id, stage2.handle or "", stage2.posts)

    if stage2.handle:
        await mkt.save_client_instagram_profile(
            client_id,
            stage2.handle,
            stage2.profile_url,
        )
    else:
        await mkt.clear_client_instagram_profile(client_id)

    if stage2.scrape_status:
        await mkt.update_client_ig_post_scrape_diagnostic(
            client_id,
            stage2.scrape_status,
            stage2.scrape_error,
        )

    all_results = search_flow._dedupe_results(stage1 + stage2.contacts + stage3 + stage4)

    # Batch upsert all contacts at once (instead of N individual DB calls)
    # Only save: website, wa_phone, email
    # pic_name: ONLY if contact_type=wa_phone AND pic_name is present
    # pic_title: NEVER
    batch_results: list[dict[str, Any]] = []
    for result in all_results:
        if result.contact_type not in ("website", "wa_phone", "email"):
            continue
        entry: dict[str, Any] = {
            "contact_type": result.contact_type,
            "value": result.value,
            "source_url": result.source_url,
            "source_type": result.source_type,
            "confidence": result.confidence,
        }
        # pic_name: only for wa_phone, stored as column on same row (not separate contact row)
        if result.contact_type == "wa_phone" and result.pic_name:
            entry["pic_name"] = result.pic_name
        batch_results.append(entry)

    if batch_results:
        await mkt.upsert_contact_results_batch(client_id, batch_results)

    # Mark which IG posts had phones extracted (used for the "Extracted" column in UI)
    if stage2.posts:
        ig_contacts = [r for r in all_results if r.source_type in ("ig_post", "ig_caption")]
        phones_found_by_post = search_flow._count_marketing_phones_found_by_post(stage2.posts, ig_contacts)
        await mkt.mark_client_ig_posts_extracted(client_id, stage2.posts, phones_found_by_post)

    pruned_contacts = await search_flow._prune_stale_client_contacts(client_id)
    return all_results, pruned_contacts


async def _run_full_search(client: dict[str, Any], run_id: int, plan: dict[str, Any]) -> dict[str, Any]:
    """
    AI-powered full search using MarketingDiscoveryAgent.
    Falls back to legacy pipeline if the agent fails.
    """
    client_id = int(client["id"])
    client_name = str(client["name"])

    await mkt.update_client_search_status(client_id, "searching")
    await ws_manager.broadcast_type(
        "marketing_client_updated",
        client_id=client_id,
        group_id=int(client["group_id"]),
        search_status="searching",
    )
    await _set_client_stage(client_id, run_id, "planning", "agent_init")

    try:
        from .marketing_agent import run_discovery
        result = await run_discovery(client, run_id, mode="full_search")

        # If the orchestrator itself errored (e.g. invalid API key, model unavailable),
        # fall back to legacy rather than surfacing a bare "error" status with 0 contacts.
        if result.status == "error" and not result.contacts_recorded:
            log.warning(
                "[Marketing Orchestration] AgentSystem returned error for %s: %s — falling back to legacy pipeline",
                client_name, result.error_message,
            )
            return await _run_full_search_legacy(client, run_id, plan)

        # Build summary dict compatible with legacy pipeline expectations
        wa_found = any(c.get("contact_type") == "wa_phone" for c in result.contacts_recorded)
        email_found = any(c.get("contact_type") == "email" for c in result.contacts_recorded)

        final_status = (
            "found" if (wa_found or email_found)
            else "partial" if result.contacts_recorded
            else "not_found"
        )

        # Update client search status (agent may have already set this, but ensure it's set)
        await mkt.update_client_search_status(client_id, final_status)
        await ws_manager.broadcast_type(
            "marketing_client_updated",
            client_id=client_id,
            group_id=int(client["group_id"]),
            search_status=final_status,
            contacts_count=len(result.contacts_recorded or []),
        )

        return {
            "mode": plan["mode"],
            "final_status": final_status,
            "contacts_found": len(result.contacts_recorded),
            "agent_mode": True,
            "sub_agent_calls": result.sub_agent_calls,
            "tools_that_worked": result.tools_that_worked,
            "tools_that_failed": result.tools_that_failed,
            "summary": result.summary,
            "total_tokens": result.total_tokens,
            "duration_seconds": result.duration_seconds,
        }

    except Exception as exc:
        log.error(
            "[Marketing Orchestration] AgentSystem failed for %s: %s — falling back to legacy pipeline",
            client_name, exc,
        )
        # Fallback to legacy pipeline
        return await _run_full_search_legacy(client, run_id, plan)


async def _run_full_search_legacy(client: dict[str, Any], run_id: int, plan: dict[str, Any]) -> dict[str, Any]:
    client_id = int(client["id"])
    client_name = str(client["name"])

    await mkt.update_client_search_status(client_id, "searching")
    await ws_manager.broadcast_type(
        "marketing_client_updated",
        client_id=client_id,
        group_id=int(client["group_id"]),
        search_status="searching",
    )

    # Resolve client_type from the group record (client_type lives on the group, not the client)
    extra_data = client.get("extra_data") or {}
    client_type: str | None = extra_data.get("client_type")
    if not client_type:
        group = await mkt.get_group(int(client["group_id"]))
        if group:
            client_type = group.get("client_type")
    stages = DISCOVERY_STAGES.get(client_type, DISCOVERY_STAGES[None])

    # --- Structured discovery stages (bnsp, jdih, asosiasi, etc.) ---
    structured_results: list[search_flow.ContactResult] = []
    for stage_name in stages:
        if stage_name in ("website", "ig", "web_fallback", "gemini"):
            continue  # handled separately below
        if stage_name == "bnsp":
            try:
                from .discovery import bnsp_discovery
                await _set_client_stage(client_id, run_id, "collecting", "bnsp")
                bnsp_results = await bnsp_discovery(client_name)
                structured_results = search_flow._dedupe_results(structured_results + bnsp_results)
                await _record_stage_summary(
                    run_id, client_id, "bnsp", "stage_summary",
                    status="completed",
                    payload={"contacts_found": len(bnsp_results)},
                )
                await _record_contacts(run_id, client_id, "bnsp", bnsp_results, status="accepted")
            except Exception as exc:
                log.warning("[Marketing Orchestration] bnsp stage failed for %s: %s", client_name, exc)
                await _record_stage_summary(
                    run_id, client_id, "bnsp", "stage_summary",
                    status="failed", reason=str(exc),
                    payload={"contacts_found": 0},
                )
        elif stage_name == "jdih":
            try:
                from .discovery import jdih_discovery
                await _set_client_stage(client_id, run_id, "collecting", "jdih")
                jdih_results = await jdih_discovery(client_name)
                structured_results = search_flow._dedupe_results(structured_results + jdih_results)
                await _record_stage_summary(
                    run_id, client_id, "jdih", "stage_summary",
                    status="completed",
                    payload={"contacts_found": len(jdih_results)},
                )
                await _record_contacts(run_id, client_id, "jdih", jdih_results, status="accepted")
            except Exception as exc:
                log.warning("[Marketing Orchestration] jdih stage failed for %s: %s", client_name, exc)
                await _record_stage_summary(
                    run_id, client_id, "jdih", "stage_summary",
                    status="failed", reason=str(exc),
                    payload={"contacts_found": 0},
                )
        elif stage_name == "asosiasi":
            try:
                from .discovery import asosiasi_discovery
                await _set_client_stage(client_id, run_id, "collecting", "asosiasi")
                asosiasi_results = await asosiasi_discovery(client_name)
                structured_results = search_flow._dedupe_results(structured_results + asosiasi_results)
                await _record_stage_summary(
                    run_id, client_id, "asosiasi", "stage_summary",
                    status="completed",
                    payload={"contacts_found": len(asosiasi_results)},
                )
                await _record_contacts(run_id, client_id, "asosiasi", asosiasi_results, status="accepted")
            except Exception as exc:
                log.warning("[Marketing Orchestration] asosiasi stage failed for %s: %s", client_name, exc)
                await _record_stage_summary(
                    run_id, client_id, "asosiasi", "stage_summary",
                    status="failed", reason=str(exc),
                    payload={"contacts_found": 0},
                )
        elif stage_name == "annual_report":
            # annual_report discovery not yet implemented — skip gracefully
            log.info("[Marketing Orchestration] annual_report stage not yet implemented, skipping")
        elif stage_name == "lkip":
            # lkip discovery not yet implemented — skip gracefully
            log.info("[Marketing Orchestration] lkip stage not yet implemented, skipping")
        else:
            log.info("[Marketing Orchestration] Unknown stage %r for client_type=%s, skipping", stage_name, client_type)

    # --- Website discovery (always runs) ---
    await _set_client_stage(client_id, run_id, "collecting", "website")
    stage1 = await search_flow.website_discovery(client_name, client.get("extra_data"))
    await _record_stage_summary(
        run_id,
        client_id,
        "website",
        "stage_summary",
        status="completed",
        payload={"contacts_found": len(stage1)},
    )
    await _record_contacts(run_id, client_id, "website", stage1, status="accepted")

    # --- IG discovery runs only if no WA phone found yet ---
    has_wa = (
        _has_contact(structured_results, "wa_phone")
        or _has_contact(stage1, "wa_phone")
    )
    if "ig" in stages and not has_wa:
        await _record_stage_summary(
            run_id,
            client_id,
            "planning",
            "stage_decision",
            status="continue",
            reason=(
                "No WA phone found from structured discovery; run IG discovery to find contacts"
            ),
            payload={"has_wa_phone": has_wa},
            value="instagram",
        )
        await _set_client_stage(client_id, run_id, "collecting", "instagram")
        stage2 = await search_flow.ig_discovery(client_name, client_type=client_type or "")
        await _record_stage_summary(
            run_id,
            client_id,
            "instagram",
            "stage_summary",
            status=stage2.scrape_status or "completed",
            reason=stage2.scrape_error,
            payload={
                "handle": stage2.handle,
                "profile_url": stage2.profile_url,
                "posts": len(stage2.posts),
                "contacts_found": len(stage2.contacts),
                "candidate_count": len(stage2.candidates),
            },
            value=stage2.handle,
        )
        for candidate in stage2.candidates:
            await _record_stage_summary(
                run_id,
                client_id,
                "instagram",
                "instagram_candidate",
                status="selected" if candidate.get("is_selected") else "observed",
                reason=candidate.get("llm_reason"),
                payload=candidate,
                source_type=candidate.get("source"),
                source_url=candidate.get("url"),
                value=candidate.get("handle"),
                confidence=float(candidate.get("final_score") or 0.0),
            )
        await _record_contacts(run_id, client_id, "instagram", stage2.contacts, status="accepted")
        has_wa = has_wa or _has_contact(stage2.contacts, "wa_phone")
    else:
        stage2 = search_flow.InstagramDiscoveryResult()
        ig_skipped_reason = (
            "WA phone already found from structured discovery; skip IG discovery"
            if has_wa
            else f"IG stage not in selected stages for client_type={client_type}"
        )
        await _record_stage_summary(
            run_id,
            client_id,
            "planning",
            "stage_decision",
            status="skipped",
            reason=ig_skipped_reason,
            payload={"has_wa_phone": has_wa, "client_type": client_type},
            value="instagram",
        )

    combined_results = search_flow._dedupe_results(structured_results + stage1 + stage2.contacts)
    has_email = _has_contact(combined_results, "email")
    has_wa_phone = _has_contact(combined_results, "wa_phone")
    should_run_web_fallback = not (has_email and has_wa_phone)

    if should_run_web_fallback:
        await _record_stage_summary(
            run_id,
            client_id,
            "planning",
            "stage_decision",
            status="continue",
            reason="Evidence still missing required contact set; continue to web fallback",
            payload={"has_email": has_email, "has_wa_phone": has_wa_phone},
            value="web_fallback",
        )
        await _set_client_stage(client_id, run_id, "collecting", "web_fallback")
        stage3 = await search_flow.web_search_fallback(client_name)
        await _record_stage_summary(
            run_id,
            client_id,
            "web_fallback",
            "stage_summary",
            status="completed",
            payload={"contacts_found": len(stage3)},
        )
        await _record_contacts(run_id, client_id, "web_fallback", stage3, status="accepted")
    else:
        stage3 = []
        await _record_stage_summary(
            run_id,
            client_id,
            "planning",
            "stage_decision",
            status="skipped",
            reason="Website, structured, and Instagram already produced the required contact set",
            payload={"has_email": has_email, "has_wa_phone": has_wa_phone},
            value="web_fallback",
        )

    combined_results = search_flow._dedupe_results(structured_results + stage1 + stage2.contacts + stage3)
    if search_flow.needs_gemini_grounded_enrichment(combined_results):
        if search_flow.is_marketing_gemini_enabled():
            await _record_stage_summary(
                run_id,
                client_id,
                "planning",
                "stage_decision",
                status="continue",
                reason="Run Gemini grounded gap fill to close remaining contact gaps",
                payload={
                    "has_email": _has_contact(combined_results, "email"),
                    "has_wa_phone": _has_contact(combined_results, "wa_phone"),
                    "has_website": _has_contact(combined_results, "website"),
                },
                value="gemini_grounded",
            )
            await _set_client_stage(client_id, run_id, "collecting", "gemini_grounded")
            try:
                stage4_result = await search_flow.gemini_grounded_discovery(
                    client_name,
                    client.get("extra_data"),
                    combined_results,
                )
            except Exception as exc:
                stage4 = []
                await _record_stage_summary(
                    run_id,
                    client_id,
                    "gemini_grounded",
                    "stage_summary",
                    status="failed",
                    reason=str(exc) or type(exc).__name__,
                    payload={"contacts_found": 0, "grounded_urls": []},
                )
            else:
                await _record_stage_summary(
                    run_id,
                    client_id,
                    "gemini_grounded",
                    "stage_summary",
                    status="completed" if not stage4_result.parse_failed else "failed",
                    reason=stage4_result.notes,
                    payload={
                        "contacts_found": len(stage4_result.contacts),
                        "grounded_urls": stage4_result.grounded_urls,
                        "unresolved_gaps": stage4_result.unresolved_gaps,
                        "parse_failed": stage4_result.parse_failed,
                    },
                )
                for grounded_url in stage4_result.grounded_urls:
                    await _record_stage_summary(
                        run_id,
                        client_id,
                        "gemini_grounded",
                        "grounded_source",
                        status="observed",
                        source_url=grounded_url,
                        value=grounded_url,
                    )
                await _record_contacts(
                    run_id,
                    client_id,
                    "gemini_grounded",
                    stage4_result.contacts,
                    status="accepted",
                    reason=stage4_result.notes,
                )
                stage4 = stage4_result.contacts
        else:
            stage4 = []
            await _record_stage_summary(
                run_id,
                client_id,
                "planning",
                "stage_decision",
                status="skipped",
                reason="Gemini grounded stage skipped because marketing Gemini is disabled or GEMINI_API_KEY is missing",
                payload={
                    "has_email": _has_contact(combined_results, "email"),
                    "has_wa_phone": _has_contact(combined_results, "wa_phone"),
                    "has_website": _has_contact(combined_results, "website"),
                },
                value="gemini_grounded",
            )
    else:
        stage4 = []
        await _record_stage_summary(
            run_id,
            client_id,
            "planning",
            "stage_decision",
            status="skipped",
            reason="Current results already include website, email, and WhatsApp/mobile contact",
            payload={
                "has_email": _has_contact(combined_results, "email"),
                "has_wa_phone": _has_contact(combined_results, "wa_phone"),
                "has_website": _has_contact(combined_results, "website"),
            },
            value="gemini_grounded",
        )

    await _set_client_stage(client_id, run_id, "resolving", "finalize")
    final_results, pruned_contacts = await _persist_final_results(client_id, stage1, stage2, stage3, stage4)

    # IG partial failure masking: if IG handle was found but scrape failed/empty,
    # and overall search found contacts, mark as 'partial' (not 'found').
    ig_scrape_failed = stage2.scrape_status in {"failed", "empty"}
    ig_handle_was_found = bool(stage2.handle)
    if final_results and ig_handle_was_found and ig_scrape_failed:
        final_status = "partial"
    else:
        final_status = "found" if final_results else "not_found"
    await mkt.update_client_search_status(client_id, final_status)
    await ws_manager.broadcast_type(
        "marketing_client_updated",
        client_id=client_id,
        group_id=int(client["group_id"]),
        search_status=final_status,
        contacts_count=len(final_results),
    )

    await _record_contacts(run_id, client_id, "finalize", final_results, status="accepted")
    summary = {
        "mode": plan["mode"],
        "final_status": final_status,
        "client_type": client_type,
        "stages_run": stages,
        "contacts_found": len(final_results),
        "website_contacts": len(stage1),
        "structured_contacts": len(structured_results),
        "instagram_contacts": len(stage2.contacts),
        "web_fallback_contacts": len(stage3),
        "gemini_contacts": len(stage4),
        "instagram_handle": stage2.handle,
        "instagram_scrape_status": stage2.scrape_status,
        "instagram_post_count": len(stage2.posts),
        "contacts_pruned": pruned_contacts,
    }
    return summary


async def _run_instagram_scrape_retry(client: dict[str, Any], run_id: int, plan: dict[str, Any]) -> dict[str, Any]:
    client_id = int(client["id"])
    handles = await mkt.get_selected_instagram_handles_for_client(client_id)
    if not handles:
        raise ValueError("No selected Instagram handle available for retry")

    primary_handle = handles[0]
    await mkt.update_client_ig_post_scrape_diagnostic(client_id, "scraping", None)
    await _set_client_stage(client_id, run_id, "collecting", "instagram")

    loop = asyncio.get_running_loop()
    posts, scrape_error = await loop.run_in_executor(
        None,
        partial(search_flow._scrape_instagram_posts_for_handles, handles, primary_handle),
    )

    await _record_stage_summary(
        run_id,
        client_id,
        "instagram",
        "stage_summary",
        status="completed" if posts else "empty",
        reason=scrape_error,
        payload={"handles": handles, "posts": len(posts)},
        value=primary_handle,
    )

    if not posts:
        diagnostic = scrape_error or search_flow._build_ig_scrape_diagnostic(primary_handle)
        await mkt.update_client_ig_post_scrape_diagnostic(client_id, "empty", diagnostic)
        return {
            "mode": plan["mode"],
            "status": "empty",
            "handles": handles,
            "posts": 0,
            "contacts_added": 0,
            "contacts_pruned": 0,
            "message": diagnostic,
        }

    await mkt.replace_client_ig_posts(client_id, primary_handle, posts)
    contacts = await search_flow._extract_marketing_contacts_from_posts(posts)
    phones_found_by_post = search_flow._count_marketing_phones_found_by_post(posts, contacts)
    await mkt.mark_client_ig_posts_extracted(client_id, posts, phones_found_by_post)
    await _record_contacts(run_id, client_id, "instagram", contacts, status="accepted")
    inserted_contacts = await search_flow._replace_ig_contact_results_for_client(client_id, contacts)
    pruned_contacts = await search_flow._prune_stale_client_contacts(client_id)
    await mkt.update_client_ig_post_scrape_diagnostic(client_id, "success", None)

    summary = {
        "mode": plan["mode"],
        "status": "success",
        "handles": handles,
        "posts": len(posts),
        "contacts_added": inserted_contacts,
        "contacts_pruned": pruned_contacts,
        "message": f"Scraped {len(posts)} Instagram post(s)",
    }
    if pruned_contacts:
        summary["message"] = f"{summary['message']}; pruned {pruned_contacts} stale contact(s)"
    return summary


async def _run_instagram_contact_retry(client: dict[str, Any], run_id: int, plan: dict[str, Any]) -> dict[str, Any]:
    client_id = int(client["id"])
    posts = await mkt.get_client_ig_posts(client_id)
    if not posts:
        raise ValueError("No stored Instagram posts available for extraction")

    await _set_client_stage(client_id, run_id, "collecting", "instagram_contact_extract")
    contacts = await search_flow._extract_marketing_contacts_from_posts(posts)
    phones_found_by_post = search_flow._count_marketing_phones_found_by_post(posts, contacts)
    await mkt.mark_client_ig_posts_extracted(client_id, posts, phones_found_by_post)
    await _record_stage_summary(
        run_id,
        client_id,
        "instagram_contact_extract",
        "stage_summary",
        status="completed",
        payload={"posts": len(posts), "contacts_found": len(contacts)},
    )
    await _record_contacts(run_id, client_id, "instagram_contact_extract", contacts, status="accepted")

    inserted_contacts = await search_flow._replace_ig_contact_results_for_client(client_id, contacts)
    pruned_contacts = await search_flow._prune_stale_client_contacts(client_id)
    summary = {
        "mode": plan["mode"],
        "posts": len(posts),
        "contacts_added": inserted_contacts,
        "contacts_pruned": pruned_contacts,
        "message": f"Extracted {inserted_contacts} contact(s) from {len(posts)} stored Instagram post(s)",
    }
    if not inserted_contacts:
        summary["message"] = f"Processed {len(posts)} stored Instagram post(s), but no contacts were found"
    if pruned_contacts:
        summary["message"] = f"{summary['message']}; pruned {pruned_contacts} stale contact(s)"
    return summary


async def run_client_orchestration(
    client_id: int,
    *,
    mode: str = "full_search",
    trigger_type: str = "manual",
) -> dict[str, Any]:
    client = await mkt.get_client(client_id)
    if client is None:
        raise ValueError("Client not found")
    if client.get("orchestration_state") in ACTIVE_ORCHESTRATION_STATES:
        raise ValueError("Client orchestration already in progress")

    plan = _build_plan(client, mode)
    run_id = await mkt.create_orchestration_run(
        client_id,
        int(client["group_id"]),
        mode,
        trigger_type,
        state="planning",
        current_stage="planning",
        plan=plan,
    )
    await _set_client_stage(client_id, run_id, "planning", "planning", summary={"mode": mode})
    await _record_stage_summary(
        run_id,
        client_id,
        "planning",
        "plan",
        status="accepted",
        payload=plan,
    )

    try:
        if mode == "full_search":
            summary = await _run_full_search(client, run_id, plan)
        elif mode == "instagram_scrape_retry":
            summary = await _run_instagram_scrape_retry(client, run_id, plan)
        elif mode == "instagram_contact_retry":
            summary = await _run_instagram_contact_retry(client, run_id, plan)
        else:
            raise ValueError(f"Unsupported orchestration mode: {mode}")

        await _set_client_stage(client_id, run_id, "idle", None, summary=summary)
        await mkt.update_orchestration_run(
            run_id,
            state="completed",
            current_stage="done",
            summary=summary,
            completed=True,
        )
        return {
            "client_id": client_id,
            "group_id": int(client["group_id"]),
            "run_id": run_id,
            **summary,
        }
    except Exception as exc:
        error_message = str(exc) or type(exc).__name__
        log.warning("[Marketing Orchestration] Client %s failed in mode %s: %s", client_id, mode, error_message)
        await _set_client_stage(
            client_id,
            run_id,
            "failed",
            "failed",
            summary={"mode": mode, "error": error_message},
        )
        await mkt.update_orchestration_run(
            run_id,
            state="failed",
            current_stage="failed",
            summary={"mode": mode, "error": error_message},
            error_message=error_message,
            completed=True,
        )
        if mode == "full_search":
            await mkt.update_client_error_message(client_id, error_message)
        raise


async def process_group_orchestration_queue(group_id: int, *, trigger_type: str = "scheduler") -> None:
    """Run orchestration for all pending clients in a group, with auto-retry for errors."""
    MAX_CONCURRENT = int(os.getenv("MARKETING_MAX_CONCURRENT", "20"))
    MAX_AUTO_RETRIES = int(os.getenv("MARKETING_MAX_AUTO_RETRIES", "2"))
    RETRY_DELAY_SECONDS = float(os.getenv("MARKETING_RETRY_DELAY_SECONDS", "30"))

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    await mkt.update_group_status(group_id, "searching")

    async def bounded_orchestrate(client_id: int) -> None:
        async with semaphore:
            await run_client_orchestration(client_id, mode="full_search", trigger_type=trigger_type)

    # --- Initial batch ---
    pending_clients = await mkt.get_pending_clients(group_id)
    if pending_clients:
        await asyncio.gather(
            *[bounded_orchestrate(c["id"]) for c in pending_clients],
            return_exceptions=True,
        )

    # --- Auto-retry loop ---
    for attempt in range(1, MAX_AUTO_RETRIES + 1):
        error_clients = await mkt.get_error_clients(group_id)
        if not error_clients:
            break
        log.info(
            "[Marketing Orchestration] Group %d: %d error client(s) — auto-retry %d/%d in %gs",
            group_id, len(error_clients), attempt, MAX_AUTO_RETRIES, RETRY_DELAY_SECONDS,
        )
        await asyncio.sleep(RETRY_DELAY_SECONDS)
        for client in error_clients:
            await mkt.update_client_search_status(client["id"], "pending")
        await asyncio.gather(
            *[bounded_orchestrate(c["id"]) for c in error_clients],
            return_exceptions=True,
        )

    # --- Final status & broadcast ---
    group_status = await mkt.get_group_search_status(group_id)
    next_status = "searching" if (group_status["pending"] or group_status["searching"]) else "done"
    await mkt.update_group_status(group_id, next_status)

    if next_status == "done":
        await ws_manager.broadcast_type(
            "marketing_search_completed",
            group_id=group_id,
            total=group_status.get("total", 0),
            found=group_status.get("found", 0),
            not_found=group_status.get("not_found", 0),
            partial=group_status.get("partial", 0),
            error_count=group_status.get("error", 0),
        )