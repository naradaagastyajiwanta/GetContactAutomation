"""3-layer memory manager for marketing agent orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from orchestrator.config import log

# Import db module for DB access — use aiosqlite directly to avoid circular imports
import aiosqlite
from orchestrator.config import DATABASE_PATH

# Also import the groups module for type-safe DB access
from . import groups as mkt


async def get_client_episodic_memory(client_id: int) -> dict:
    """
    Layer 2: Medium-term episodic memory for a specific client.
    Returns previous run history, contacts already found, IG handles tried.
    """
    # Get previous completed runs
    previous_runs = await mkt.list_orchestration_runs(client_id, limit=3)

    # Get contacts already found for this client
    contacts = await mkt.get_contact_results_for_client(client_id)
    contacts_found = [
        {"type": c.get("contact_type"), "value": c.get("edited_value") or c.get("value")}
        for c in contacts
        if c.get("value")
    ]

    # Get IG handles tried (from marketing_ig_candidates)
    ig_handles_tried = []
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT handle, llm_is_correct, final_score, is_selected
               FROM marketing_ig_candidates
               WHERE client_id=?
               ORDER BY rank_order ASC LIMIT 10""",
            (client_id,)
        )
        rows = await cursor.fetchall()
        for row in rows:
            ig_handles_tried.append({
                "handle": row["handle"],
                "was_correct": bool(row["llm_is_correct"]),
                "score": float(row["final_score"] or 0),
                "was_selected": bool(row["is_selected"]),
            })

    # Parse run summaries to extract what failed
    run_summaries = []
    for run in previous_runs:
        summary = {}
        if run.get("summary_json"):
            try:
                summary = json.loads(run["summary_json"]) if isinstance(run["summary_json"], str) else run["summary_json"]
            except (json.JSONDecodeError, TypeError):
                pass
        run_summaries.append({
            "mode": run.get("mode"),
            "state": run.get("state"),
            "contacts_found": summary.get("contacts_found", 0),
            "tools_that_worked": summary.get("tools_that_worked", []),
            "tools_that_failed": summary.get("tools_that_failed", []),
            "summary": summary.get("summary", ""),
        })

    return {
        "previous_runs": run_summaries,
        "contacts_already_found": contacts_found,
        "ig_handles_tried": ig_handles_tried,
        "has_prior_run": len(previous_runs) > 0,
    }


async def get_long_term_context(group_id: int, client_type: str | None) -> dict:
    """
    Layer 3: Long-term semantic memory — group strategy + global lessons.
    """
    strategy = await get_group_strategy(group_id)

    # Extract top lessons from strategy
    group_lessons = []
    tool_success_rates = {}
    group_progress = {"completed": 0, "total": 0, "found_rate": 0.0}

    if strategy:
        group_lessons = strategy.get("lessons", [])[:5]
        tool_success_rates = strategy.get("tool_success_rates", {})
        group_progress = {
            "completed": strategy.get("completed_clients", 0),
            "total": strategy.get("total_clients", 0),
            "found_rate": strategy.get("found_rate", 0.0),
        }

    # Get global lessons from the existing lessons table
    global_lessons = []
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        situation_type = f"marketing_{client_type}" if client_type else "marketing"
        cursor = await db.execute(
            """SELECT insight, recommended_strategy, success_rate
               FROM lessons
               WHERE situation_type LIKE ? AND is_active=1
               ORDER BY success_rate DESC, confidence DESC
               LIMIT 5""",
            (f"%{situation_type}%",)
        )
        rows = await cursor.fetchall()
        for row in rows:
            global_lessons.append({
                "insight": row["insight"],
                "strategy": row["recommended_strategy"],
                "success_rate": float(row["success_rate"] or 0),
            })

    return {
        "group_strategy": strategy,
        "group_lessons": group_lessons,
        "global_lessons": global_lessons,
        "group_progress": group_progress,
        "tool_success_rates": tool_success_rates,
        "decision_patterns": strategy.get("decision_patterns", {}) if strategy else {},
    }


async def get_group_strategy(group_id: int) -> dict | None:
    """Read strategy_json for a group."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT strategy_json FROM marketing_groups WHERE id=?",
            (group_id,)
        )
        row = await cursor.fetchone()
        if not row or not row["strategy_json"]:
            return None
        try:
            return json.loads(row["strategy_json"])
        except (json.JSONDecodeError, TypeError):
            return None


async def update_group_strategy(group_id: int, strategy: dict) -> None:
    """Write strategy_json for a group (full replace)."""
    strategy["updated_at"] = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE marketing_groups SET strategy_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(strategy, ensure_ascii=False), group_id)
        )
        await db.commit()
    log.info("[MktMemory] Updated group strategy for group_id=%d", group_id)


def _extract_auto_patterns(run_summary: dict) -> dict:
    """Deterministically extract reliable_sources and red_flags from run data.
    Does NOT depend on LLM providing patterns_learned in mark_done."""
    patterns: dict = {"reliable_sources": [], "red_flag_patterns": []}
    for tool in run_summary.get("tools_that_worked", []):
        label = tool.replace("spawn_", "").replace("_agent", "") + "_effective"
        patterns["reliable_sources"].append(label)
    for tool in run_summary.get("tools_that_failed", []):
        label = tool.replace("spawn_", "").replace("_agent", "") + "_insufficient"
        patterns["red_flag_patterns"].append(label)
    return patterns


async def write_post_run_lessons(
    group_id: int,
    client_type: str | None,
    run_summary: dict,
) -> None:
    """
    After a run completes, update strategy_json and write to global lessons table.
    run_summary: {
        "status": "found"|"partial"|"not_found",
        "tools_that_worked": ["spawn_web_search_agent"],
        "tools_that_failed": ["spawn_registry_agent"],
        "contacts_found": 2,
        "summary": "Found WA phone from Instagram after web search yielded email",
    }
    """
    strategy = await get_group_strategy(group_id) or {
        "version": 2,
        "client_type": client_type,
        "tool_success_rates": {},
        "lessons": [],
        "decision_patterns": {
            "reliable_sources": [],
            "red_flag_patterns": [],
            "effective_approaches": {},
        },
        "completed_clients": 0,
        "total_clients": 0,
        "found_rate": 0.0,
    }

    # Update tool success rates
    tool_success_rates = strategy.get("tool_success_rates", {})
    for tool in run_summary.get("tools_that_worked", []):
        if tool not in tool_success_rates:
            tool_success_rates[tool] = {"spawns": 0, "produced_contacts": 0}
        tool_success_rates[tool]["spawns"] += 1
        tool_success_rates[tool]["produced_contacts"] += run_summary.get("contacts_found", 0)
    for tool in run_summary.get("tools_that_failed", []):
        if tool not in tool_success_rates:
            tool_success_rates[tool] = {"spawns": 0, "produced_contacts": 0}
        tool_success_rates[tool]["spawns"] += 1  # count spawn even if failed
    strategy["tool_success_rates"] = tool_success_rates

    # Update completion counters
    strategy["completed_clients"] = strategy.get("completed_clients", 0) + 1

    # Update found rate
    found = strategy.get("found_clients", 0)
    if run_summary.get("status") in ("found", "partial"):
        found += 1
    strategy["found_clients"] = found
    completed = strategy["completed_clients"]
    strategy["found_rate"] = found / completed if completed > 0 else 0.0

    # Add lesson if summary is meaningful — stored as structured dict (backward compat: old entries may be plain strings)
    summary_text = run_summary.get("summary", "")
    if summary_text and len(summary_text) > 10:
        lessons = strategy.get("lessons", [])
        lessons.insert(0, {
            "summary": summary_text[:300],
            "status": run_summary.get("status"),
            "tools_worked": run_summary.get("tools_that_worked", []),
            "tools_failed": run_summary.get("tools_that_failed", []),
        })
        strategy["lessons"] = lessons[:20]

    # Deterministic pattern extraction — always runs, does not depend on LLM patterns_learned
    dp = strategy.setdefault("decision_patterns", {
        "reliable_sources": [],
        "red_flag_patterns": [],
        "effective_approaches": {},
    })
    auto_patterns = _extract_auto_patterns(run_summary)
    for src in auto_patterns.get("reliable_sources", []):
        if src not in dp.get("reliable_sources", []):
            dp.setdefault("reliable_sources", []).append(src)
    for flag in auto_patterns.get("red_flag_patterns", []):
        if flag not in dp.get("red_flag_patterns", []):
            dp.setdefault("red_flag_patterns", []).append(flag)
    strategy["decision_patterns"] = dp

    # Also merge LLM-provided patterns_learned on top (when orchestrator includes them in mark_done)
    patterns = run_summary.get("patterns_learned", {})
    if patterns:
        dp = strategy.setdefault("decision_patterns", {
            "reliable_sources": [],
            "red_flag_patterns": [],
            "effective_approaches": {},
        })
        for src in patterns.get("reliable_sources", []):
            if src and src not in dp.get("reliable_sources", []):
                dp.setdefault("reliable_sources", []).append(src)
        for flag in patterns.get("red_flag_patterns", []):
            if flag and flag not in dp.get("red_flag_patterns", []):
                dp.setdefault("red_flag_patterns", []).append(flag)
        effective = patterns.get("effective_approach")
        if effective and client_type:
            dp.setdefault("effective_approaches", {})[client_type] = effective
        # Enforce reasonable caps
        dp["reliable_sources"] = dp.get("reliable_sources", [])[:30]
        dp["red_flag_patterns"] = dp.get("red_flag_patterns", [])[:30]
        strategy["decision_patterns"] = dp

    await update_group_strategy(group_id, strategy)

    # Write to global lessons table if we have a useful insight
    if summary_text and run_summary.get("tools_that_worked"):
        situation_type = f"marketing_{client_type}" if client_type else "marketing_general"
        insight = summary_text[:500]
        strategy_text = f"Use: {', '.join(run_summary['tools_that_worked'])}"
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute(
                    """INSERT INTO lessons (situation_type, insight, recommended_strategy,
                       success_rate, example_count, confidence, is_active, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 1, 0.7, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    (situation_type, insight, strategy_text, 0.7 if run_summary.get("status") == "found" else 0.3)
                )
                await db.commit()
        except Exception as exc:
            log.warning("[MktMemory] Failed to write global lesson: %s", exc)
