"""
Learning system for the agentic conversation pipeline.

Provides post-conversation analysis, lesson extraction, and periodic reflection
to continuously improve the agent's outreach strategy.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from orchestrator.config import MAX_LESSONS_IN_PROMPT, log, cfg, chat_kwargs
from orchestrator.llm import gateway
from orchestrator.db import (
    get_conversation_by_id,
    get_university_by_id,
    get_audiensi_conversation_by_id,
    save_conversation_analysis,
    get_unprocessed_analyses,
    mark_analyses_processed,
    get_lessons_by_situation,
    get_all_active_lessons,
    create_lesson,
    update_lesson,
    deactivate_lesson,
    save_strategy_metric,
    get_aggregated_strategy_metrics,
)
from orchestrator.agent.prompts import ANALYSIS_SYSTEM_PROMPT, REFLECTION_SYSTEM_PROMPT

_TERMINAL_STATES = {"GOT_NUMBER", "REFUSED", "ABANDONED"}
_AUDIENSI_TERMINAL_STATES = {"ZOOM_SENT", "REFUSED", "ABANDONED"}


def _parse_json_response(text: str) -> dict | None:
    """Extract the first JSON object from a GPT response string."""
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


class LearningSystem:
    """Analyses completed conversations and distils reusable lessons."""

    # ------------------------------------------------------------------
    # Post-conversation analysis
    # ------------------------------------------------------------------

    async def analyze_completed_conversation(self, conv_id: int) -> None:
        """Analyse a conversation that reached a terminal state.

        Calls GPT to produce a structured analysis, then stores it in
        ``conversation_analyses`` and saves strategy metrics.
        """
        conv = await get_conversation_by_id(conv_id)
        if not conv:
            log.warning("analyze_completed_conversation: conversation %d not found", conv_id)
            return

        state = conv.get("state", "")
        if state not in _TERMINAL_STATES:
            log.debug(
                "analyze_completed_conversation: conversation %d is in state %s (not terminal), skipping",
                conv_id, state,
            )
            return

        # University info
        uni = None
        if conv.get("university_id"):
            uni = await get_university_by_id(conv["university_id"])

        # Parse message history
        history: list[dict] = json.loads(conv.get("message_history") or "[]")
        total_messages = len(history)

        # Duration (hours between first and last message)
        duration_hours = 0.0
        if total_messages >= 2:
            try:
                first_ts = history[0].get("timestamp")
                last_ts = history[-1].get("timestamp")
                if first_ts and last_ts:
                    t0 = datetime.fromisoformat(first_ts)
                    t1 = datetime.fromisoformat(last_ts)
                    duration_hours = round((t1 - t0).total_seconds() / 3600, 2)
            except (ValueError, TypeError):
                pass

        outcome = state  # GOT_NUMBER | REFUSED | ABANDONED

        # Build conversation text for GPT
        conv_text_parts: list[str] = []
        for m in history:
            role_label = "Ali" if m.get("role") == "bot" else "Kontak"
            conv_text_parts.append(f"{role_label}: {m.get('content', '')}")
        conv_text = "\n".join(conv_text_parts)

        uni_name = uni["name"] if uni else "Tidak diketahui"
        province = uni.get("province") if uni else None

        user_content = (
            f"Universitas: {uni_name}\n"
            f"Provinsi: {province or 'Tidak diketahui'}\n"
            f"Outcome: {outcome}\n"
            f"Total pesan: {total_messages}\n"
            f"Durasi: {duration_hours} jam\n\n"
            f"Percakapan:\n{conv_text}"
        )

        try:
            resp = await gateway.chat_completions_create(
                model=cfg.AGENT_MODEL,
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                **chat_kwargs(cfg.AGENT_MODEL, temperature=0.2, max_tokens=500),
            )
            raw = resp.choices[0].message.content.strip()
            analysis = _parse_json_response(raw)
        except Exception:
            log.exception("GPT analysis call failed for conversation %d", conv_id)
            return

        if not analysis:
            log.warning("Failed to parse GPT analysis for conversation %d", conv_id)
            return

        # Persist analysis
        try:
            await save_conversation_analysis({
                "conversation_id": conv_id,
                "outcome": outcome,
                "total_messages": total_messages,
                "total_attempts": conv.get("attempt_count", 0),
                "duration_hours": duration_hours,
                "province": province,
                "success_factors": analysis.get("success_factors"),
                "failure_factors": analysis.get("failure_factors"),
                "contact_personality": analysis.get("contact_personality"),
                "effective_strategies": analysis.get("effective_strategies"),
                "recommended_improvements": analysis.get("recommended_improvements"),
                "summary": analysis.get("summary"),
            })
        except Exception:
            log.exception("Failed to save analysis for conversation %d", conv_id)
            return

        # Save strategy metrics from effective_strategies
        strategies = analysis.get("effective_strategies") or []
        for strategy in strategies:
            try:
                await save_strategy_metric({
                    "conversation_id": conv_id,
                    "strategy_used": strategy,
                    "situation_type": "outreach",
                    "outcome": outcome,
                    "province": province,
                    "response_time_minutes": round(duration_hours * 60, 1) if duration_hours else None,
                })
            except Exception:
                log.warning("Failed to save strategy metric '%s' for conv %d", strategy, conv_id)

        log.info(
            "Analysis saved for conversation %d (outcome=%s, messages=%d)",
            conv_id, outcome, total_messages,
        )

    # ------------------------------------------------------------------
    # Post-audiensi analysis
    # ------------------------------------------------------------------

    async def analyze_completed_audiensi(self, aud_id: int) -> None:
        """Analyse an audiensi conversation that reached a terminal state.

        Similar to ``analyze_completed_conversation`` but operates on
        ``audiensi_conversations`` and tags the analysis with
        ``source='audiensi'``.
        """
        aud = await get_audiensi_conversation_by_id(aud_id)
        if not aud:
            log.warning("analyze_completed_audiensi: audiensi %d not found", aud_id)
            return

        state = aud.get("state", "")
        if state not in _AUDIENSI_TERMINAL_STATES:
            log.debug(
                "analyze_completed_audiensi: audiensi %d is in state %s (not terminal), skipping",
                aud_id, state,
            )
            return

        # University info (already joined by get_audiensi_conversation_by_id)
        uni_name = aud.get("university_name") or "Tidak diketahui"
        province = aud.get("province")

        # Parse message history
        history: list[dict] = json.loads(aud.get("message_history") or "[]")
        total_messages = len(history)

        # Duration (hours between first and last message)
        duration_hours = 0.0
        if total_messages >= 2:
            try:
                first_ts = history[0].get("timestamp")
                last_ts = history[-1].get("timestamp")
                if first_ts and last_ts:
                    t0 = datetime.fromisoformat(first_ts)
                    t1 = datetime.fromisoformat(last_ts)
                    duration_hours = round((t1 - t0).total_seconds() / 3600, 2)
            except (ValueError, TypeError):
                pass

        outcome = state  # ZOOM_SENT | REFUSED | ABANDONED

        # Build conversation text for GPT
        conv_text_parts: list[str] = []
        for m in history:
            role_label = "Ali" if m.get("role") == "bot" else "Kontak"
            conv_text_parts.append(f"{role_label}: {m.get('content', '')}")
        conv_text = "\n".join(conv_text_parts)

        user_content = (
            f"Universitas: {uni_name}\n"
            f"Provinsi: {province or 'Tidak diketahui'}\n"
            f"Tipe: Audiensi/Penjadwalan Zoom\n"
            f"Outcome: {outcome}\n"
            f"Total pesan: {total_messages}\n"
            f"Durasi: {duration_hours} jam\n\n"
            f"Percakapan:\n{conv_text}"
        )

        try:
            resp = await gateway.chat_completions_create(
                model=cfg.AGENT_MODEL,
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                **chat_kwargs(cfg.AGENT_MODEL, temperature=0.2, max_tokens=500),
            )
            raw = resp.choices[0].message.content.strip()
            analysis = _parse_json_response(raw)
        except Exception:
            log.exception("GPT analysis call failed for audiensi %d", aud_id)
            return

        if not analysis:
            log.warning("Failed to parse GPT analysis for audiensi %d", aud_id)
            return

        # Persist analysis (with source='audiensi')
        try:
            await save_conversation_analysis({
                "conversation_id": aud_id,
                "outcome": outcome,
                "total_messages": total_messages,
                "total_attempts": aud.get("attempt_count", 0),
                "duration_hours": duration_hours,
                "province": province,
                "success_factors": analysis.get("success_factors"),
                "failure_factors": analysis.get("failure_factors"),
                "contact_personality": analysis.get("contact_personality"),
                "effective_strategies": analysis.get("effective_strategies"),
                "recommended_improvements": analysis.get("recommended_improvements"),
                "summary": analysis.get("summary"),
                "source": "audiensi",
            })
        except Exception:
            log.exception("Failed to save analysis for audiensi %d", aud_id)
            return

        # Save strategy metrics from effective_strategies
        # Determine situation_type based on whether this was a follow-up
        followup_count = aud.get("followup_count", 0)
        situation_type = "audiensi_followup" if followup_count > 0 else "audiensi_scheduling"

        strategies = analysis.get("effective_strategies") or []
        for strategy in strategies:
            try:
                await save_strategy_metric({
                    "conversation_id": aud_id,
                    "strategy_used": strategy,
                    "situation_type": situation_type,
                    "outcome": outcome,
                    "province": province,
                    "response_time_minutes": round(duration_hours * 60, 1) if duration_hours else None,
                })
            except Exception:
                log.warning("Failed to save strategy metric '%s' for audiensi %d", strategy, aud_id)

        log.info(
            "Analysis saved for audiensi %d (outcome=%s, messages=%d)",
            aud_id, outcome, total_messages,
        )

    # ------------------------------------------------------------------
    # Lesson retrieval
    # ------------------------------------------------------------------

    async def get_lessons_for_context(
        self,
        situation_type: str,
        province: str | None = None,
    ) -> list[dict]:
        """Retrieve the most relevant lessons for a given context.

        Province-specific lessons are prioritised, followed by general ones.
        Results are sorted by ``confidence * success_rate`` descending and
        capped at ``MAX_LESSONS_IN_PROMPT``.
        """
        seen_ids: set[int] = set()
        merged: list[dict] = []

        # Province-specific lessons first
        if province:
            province_lessons = await get_lessons_by_situation(
                situation_type, province=province, limit=MAX_LESSONS_IN_PROMPT
            )
            for lesson in province_lessons:
                lid = lesson.get("id")
                if lid not in seen_ids:
                    seen_ids.add(lid)
                    merged.append(lesson)

        # General lessons (province=None)
        general_lessons = await get_lessons_by_situation(
            situation_type, province=None, limit=MAX_LESSONS_IN_PROMPT
        )
        for lesson in general_lessons:
            lid = lesson.get("id")
            if lid not in seen_ids:
                seen_ids.add(lid)
                merged.append(lesson)

        # Sort by confidence * success_rate descending
        merged.sort(
            key=lambda l: (l.get("confidence", 0) * l.get("success_rate", 0)),
            reverse=True,
        )

        return merged[:MAX_LESSONS_IN_PROMPT]

    # ------------------------------------------------------------------
    # Periodic reflection
    # ------------------------------------------------------------------

    async def run_reflection(self) -> dict:
        """Review unprocessed analyses and generate/update/deactivate lessons.

        Returns a summary dict with counts of actions taken.
        """
        summary = {"new_lessons_count": 0, "updated_count": 0, "deactivated_count": 0}

        analyses = await get_unprocessed_analyses(limit=50)
        if not analyses:
            log.info("Reflection: no unprocessed analyses found")
            return summary

        # Aggregate strategy metrics for extra context
        metrics = await get_aggregated_strategy_metrics(since_days=7)

        # Existing lessons for reference
        existing_lessons = await get_all_active_lessons()

        # Build prompt content
        analyses_text_parts: list[str] = []
        analysis_ids: list[int] = []
        for a in analyses:
            analysis_ids.append(a["id"])
            analyses_text_parts.append(
                f"- ID {a['id']}: outcome={a.get('outcome')}, "
                f"province={a.get('province')}, "
                f"summary={a.get('summary', 'N/A')}, "
                f"success_factors={a.get('success_factors')}, "
                f"failure_factors={a.get('failure_factors')}"
            )
        analyses_text = "\n".join(analyses_text_parts)

        metrics_text_parts: list[str] = []
        for m in metrics:
            metrics_text_parts.append(
                f"- strategy={m.get('strategy_used')}, "
                f"situation={m.get('situation_type')}, "
                f"uses={m.get('total_uses')}, "
                f"success_rate={m.get('success_rate')}"
            )
        metrics_text = "\n".join(metrics_text_parts) if metrics_text_parts else "Belum ada metrik."

        lessons_text_parts: list[str] = []
        for l in existing_lessons:
            lessons_text_parts.append(
                f"- ID {l['id']}: [{l.get('situation_type')}] "
                f"{l.get('insight')} "
                f"(confidence={l.get('confidence')}, success_rate={l.get('success_rate')})"
            )
        lessons_text = "\n".join(lessons_text_parts) if lessons_text_parts else "Belum ada pelajaran."

        user_content = (
            f"ANALISIS PERCAKAPAN TERBARU ({len(analyses)} buah):\n{analyses_text}\n\n"
            f"METRIK STRATEGI (7 hari terakhir):\n{metrics_text}\n\n"
            f"PELAJARAN YANG SUDAH ADA:\n{lessons_text}"
        )

        try:
            resp = await gateway.chat_completions_create(
                model=cfg.AGENT_MODEL,
                messages=[
                    {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                **chat_kwargs(cfg.AGENT_MODEL, temperature=0.3, max_tokens=800),
            )
            raw = resp.choices[0].message.content.strip()
            result = _parse_json_response(raw)
        except Exception:
            log.exception("GPT reflection call failed")
            return summary

        if not result:
            log.warning("Failed to parse GPT reflection response")
            return summary

        # Apply new lessons
        new_lessons = result.get("new_lessons") or []
        for lesson_data in new_lessons:
            try:
                await create_lesson({
                    "situation_type": lesson_data.get("situation_type"),
                    "insight": lesson_data.get("insight"),
                    "recommended_strategy": lesson_data.get("recommended_strategy"),
                    "province": lesson_data.get("province"),
                    "success_rate": 0,
                    "example_count": 0,
                    "confidence": 0.5,
                    "source_analysis_ids": analysis_ids,
                })
                summary["new_lessons_count"] += 1
            except Exception:
                log.warning("Failed to create lesson: %s", lesson_data)

        # Apply updates
        updates = result.get("updates") or []
        for upd in updates:
            lesson_id = upd.get("lesson_id")
            if lesson_id is None:
                continue
            try:
                kwargs: dict = {}
                if "success_rate" in upd:
                    kwargs["success_rate"] = upd["success_rate"]
                if "confidence" in upd:
                    kwargs["confidence"] = upd["confidence"]
                if kwargs:
                    await update_lesson(lesson_id, **kwargs)
                    summary["updated_count"] += 1
            except Exception:
                log.warning("Failed to update lesson %s", lesson_id)

        # Apply deactivations
        deactivations = result.get("deactivations") or []
        for deact in deactivations:
            lesson_id = deact.get("lesson_id") if isinstance(deact, dict) else deact
            if lesson_id is None:
                continue
            try:
                await deactivate_lesson(lesson_id)
                summary["deactivated_count"] += 1
            except Exception:
                log.warning("Failed to deactivate lesson %s", lesson_id)

        # Mark analyses as processed
        await mark_analyses_processed(analysis_ids)

        log.info(
            "Reflection complete: %d new lessons, %d updated, %d deactivated",
            summary["new_lessons_count"],
            summary["updated_count"],
            summary["deactivated_count"],
        )

        return summary
