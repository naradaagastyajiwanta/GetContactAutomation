"""Agentic orchestration runner for marketing client discovery."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from orchestrator.config import log

from . import groups as mkt
from . import search as search_flow


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
    for result in all_results:
        await mkt.upsert_contact_result(
            client_id=client_id,
            contact_type=result.contact_type,
            value=result.value,
            source_url=result.source_url,
            source_type=result.source_type,
            confidence=result.confidence,
        )
        if result.pic_name:
            await mkt.upsert_contact_result(
                client_id=client_id,
                contact_type="pic_name",
                value=result.pic_name,
                source_url=result.source_url or "",
                source_type=result.source_type or "",
                confidence=result.confidence,
            )
        if result.pic_title:
            await mkt.upsert_contact_result(
                client_id=client_id,
                contact_type="pic_title",
                value=result.pic_title,
                source_url=result.source_url or "",
                source_type=result.source_type or "",
                confidence=result.confidence,
            )
    pruned_contacts = await search_flow._prune_stale_client_contacts(client_id)
    return all_results, pruned_contacts


async def _run_full_search(client: dict[str, Any], run_id: int, plan: dict[str, Any]) -> dict[str, Any]:
    client_id = int(client["id"])
    client_name = str(client["name"])

    await mkt.update_client_search_status(client_id, "searching")

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

    has_email = _has_contact(stage1, "email")
    has_wa_phone = _has_contact(stage1, "wa_phone")
    await _record_stage_summary(
        run_id,
        client_id,
        "planning",
        "stage_decision",
        status="continue",
        reason=(
            "Website evidence missing required contact set; continue to Instagram"
            if not (has_email and has_wa_phone)
            else "Website already produced the required contact set, but Instagram scrape remains enabled"
        ),
        payload={"has_email": has_email, "has_wa_phone": has_wa_phone},
        value="instagram",
    )
    await _set_client_stage(client_id, run_id, "collecting", "instagram")
    stage2 = await search_flow.ig_discovery(client_name)
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

    combined_results = search_flow._dedupe_results(stage1 + stage2.contacts)
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
            reason="Website and Instagram evidence still missing required contact set; continue to web fallback",
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
            reason="Website and Instagram already produced the required contact set",
            payload={"has_email": has_email, "has_wa_phone": has_wa_phone},
            value="web_fallback",
        )

    combined_results = search_flow._dedupe_results(stage1 + stage2.contacts + stage3)
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
    final_status = "found" if final_results else "not_found"
    await mkt.update_client_search_status(client_id, final_status)

    await _record_contacts(run_id, client_id, "finalize", final_results, status="accepted")
    summary = {
        "mode": plan["mode"],
        "final_status": final_status,
        "contacts_found": len(final_results),
        "website_contacts": len(stage1),
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
    """Run orchestration for all pending clients in a group."""
    await mkt.update_group_status(group_id, "searching")
    pending_clients = await mkt.get_pending_clients(group_id)
    tasks = [
        run_client_orchestration(client["id"], mode="full_search", trigger_type=trigger_type)
        for client in pending_clients
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    group_status = await mkt.get_group_search_status(group_id)
    next_status = "searching" if (group_status["pending"] or group_status["searching"]) else "done"
    await mkt.update_group_status(group_id, next_status)