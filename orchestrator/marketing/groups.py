"""
Marketing Groups — service layer for managing corporate outreach groups and clients.
"""
import io
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import aiosqlite

from orchestrator.config import DATABASE_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_extra_data(raw: str) -> dict | None:
    """Parse extra_data JSON safely. Returns None on parse failure."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Group CRUD
# ---------------------------------------------------------------------------


async def create_group(name: str, client_type: str) -> dict[str, Any]:
    """Create a new marketing group."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO marketing_groups (name, client_type, source, status, created_at, updated_at)
               VALUES (?, ?, 'manual', 'draft', ?, ?)""",
            (name, client_type, now, now),
        )
        await db.commit()
        group_id = cursor.lastrowid
        return await get_group(group_id)


async def list_groups(
    client_type: str | None = None,
    status: str | None = None,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List all marketing groups with aggregated stats, paginated."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        conditions: list[str] = []
        params: list[Any] = []
        if client_type:
            conditions.append("g.client_type = ?")
            params.append(client_type)
        if status:
            conditions.append("g.status = ?")
            params.append(status)
        where = " AND ".join(conditions) if conditions else "1=1"

        # Total count (ignoring pagination for accurate total)
        count_query = f"SELECT COUNT(*) FROM marketing_groups g WHERE {where}"
        count_cursor = await db.execute(count_query, params)
        total = (await count_cursor.fetchone())[0]

        query = f"""
            SELECT
                g.id, g.name, g.client_type, g.source, g.status,
                g.created_at, g.updated_at,
                COUNT(c.id) AS total_clients,
                SUM(CASE WHEN c.search_status = 'found' THEN 1 ELSE 0 END) AS found_count,
                SUM(CASE WHEN c.search_status = 'not_found' THEN 1 ELSE 0 END) AS not_found_count,
                SUM(CASE WHEN c.search_status IN ('pending','searching') THEN 1 ELSE 0 END) AS pending_count
            FROM marketing_groups g
            LEFT JOIN marketing_clients c ON c.group_id = g.id
            WHERE {where}
            GROUP BY g.id
            ORDER BY g.created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor = await db.execute(query, [*params, limit, offset])
        rows = await cursor.fetchall()
        return {
            "groups": [_row_to_group_out(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


async def get_group(group_id: int) -> dict[str, Any] | None:
    """Get a single group by ID with stats."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                g.id, g.name, g.client_type, g.source, g.status,
                g.created_at, g.updated_at,
                COUNT(c.id) AS total_clients,
                SUM(CASE WHEN c.search_status = 'found' THEN 1 ELSE 0 END) AS found_count,
                SUM(CASE WHEN c.search_status = 'not_found' THEN 1 ELSE 0 END) AS not_found_count,
                SUM(CASE WHEN c.search_status IN ('pending','searching') THEN 1 ELSE 0 END) AS pending_count
            FROM marketing_groups g
            LEFT JOIN marketing_clients c ON c.group_id = g.id
            WHERE g.id = ?
            GROUP BY g.id
            """,
            (group_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_group_out(row)


async def get_group_with_clients(group_id: int) -> dict[str, Any] | None:
    """Get group with full client list."""
    group = await get_group(group_id)
    if group is None:
        return None
    clients = await list_clients(group_id)
    return {**group, "clients": clients}


async def update_group_status(group_id: int, status: str) -> None:
    """Update group status."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE marketing_groups SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, group_id),
        )
        await db.commit()


async def update_group(group_id: int, name: str | None = None) -> dict[str, Any] | None:
    """Update group name (and optionally other fields). Returns updated group."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if name is not None:
            await db.execute(
                "UPDATE marketing_groups SET name = ?, updated_at = ? WHERE id = ?",
                (name, now, group_id),
            )
        await db.commit()
    return await get_group(group_id)


async def delete_clients_by_ids(group_id: int, client_ids: list[int]) -> int:
    """Delete multiple clients by ID within a group. Returns count deleted.
    Cascade-deletes all related tables in a single transaction."""
    if not client_ids:
        return 0
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            placeholders = ",".join("?" * len(client_ids))
            await db.execute(
                f"DELETE FROM marketing_orchestration_evidence WHERE client_id IN ({placeholders})",
                client_ids,
            )
            await db.execute(
                f"DELETE FROM marketing_orchestration_runs WHERE client_id IN ({placeholders})",
                client_ids,
            )
            await db.execute(
                f"DELETE FROM marketing_contact_results WHERE client_id IN ({placeholders})",
                client_ids,
            )
            await db.execute(
                f"DELETE FROM marketing_ig_posts WHERE client_id IN ({placeholders})",
                client_ids,
            )
            await db.execute(
                f"DELETE FROM marketing_ig_candidates WHERE client_id IN ({placeholders})",
                client_ids,
            )
            cursor = await db.execute(
                f"DELETE FROM marketing_clients WHERE group_id = ? AND id IN ({placeholders})",
                [group_id, *client_ids],
            )
            await db.commit()
            return cursor.rowcount
        except Exception:
            await db.rollback()
            raise


async def delete_group(group_id: int) -> bool:
    """Delete a group and all its clients (cascade)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Get all client IDs in this group
        cursor = await db.execute(
            "SELECT id FROM marketing_clients WHERE group_id = ?", (group_id,)
        )
        client_ids = [r[0] for r in await cursor.fetchall()]

        # Delete results for all clients
        if client_ids:
            placeholders = ",".join("?" * len(client_ids))
            await db.execute(
                f"DELETE FROM marketing_orchestration_evidence WHERE client_id IN ({placeholders})",
                client_ids,
            )
            await db.execute(
                f"DELETE FROM marketing_orchestration_runs WHERE client_id IN ({placeholders})",
                client_ids,
            )
            await db.execute(
                f"DELETE FROM marketing_contact_results WHERE client_id IN ({placeholders})",
                client_ids,
            )
            await db.execute(
                f"DELETE FROM marketing_ig_posts WHERE client_id IN ({placeholders})",
                client_ids,
            )
            await db.execute(
                f"DELETE FROM marketing_ig_candidates WHERE client_id IN ({placeholders})",
                client_ids,
            )

        # Delete clients
        await db.execute("DELETE FROM marketing_clients WHERE group_id = ?", (group_id,))
        # Delete handoffs
        await db.execute("DELETE FROM marketing_contact_handoffs WHERE group_id = ?", (group_id,))
        # Delete group
        cursor = await db.execute("DELETE FROM marketing_groups WHERE id = ?", (group_id,))
        await db.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Client CRUD
# ---------------------------------------------------------------------------


async def create_client(group_id: int, name: str, extra_data: dict | None = None) -> dict[str, Any]:
    """Create a new client in a group."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    extra_data_json = json.dumps(extra_data) if extra_data else None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO marketing_clients (group_id, name, extra_data, search_status, created_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (group_id, name, extra_data_json, now),
        )
        await db.commit()
        client_id = cursor.lastrowid
        return await get_client(client_id)


async def batch_create_clients(
    rows: list[tuple[int, str, str | None, str]],
) -> int:
    """Batch insert clients using executemany. Returns inserted row count.
    Each row: (group_id, name, extra_data_json_or_None, created_at)."""
    if not rows:
        return 0
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO marketing_clients
               (group_id, name, extra_data, search_status, created_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            rows,
        )
        inserted = db.total_changes
        await db.commit()
        return inserted


async def get_all_client_names_by_type(client_type: str) -> list[str]:
    """Return all client names (across all groups) for a given client_type.

    Used by the generator to build a deduplication exclusion list before
    calling Gemini. Returns names ordered most-recently-created first so
    that the 150-name prompt cap covers the most likely duplicates.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT mc.name
               FROM marketing_clients mc
               JOIN marketing_groups mg ON mc.group_id = mg.id
               WHERE mg.client_type = ?
               ORDER BY mc.created_at DESC""",
            (client_type,),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows if row[0]]


async def list_all_clients(
    *,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    search_status: str | None = None,
    client_type: str | None = None,
    group_id: int | None = None,
    has_contact: bool | None = None,
) -> dict[str, Any]:
    """List all clients across all groups (lightweight — no nested posts/candidates).

    Returns {clients: [...], total, limit, offset}.
    Each client includes group_name, client_type, wa_count, email_count, approved_count.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if q:
        conditions.append("LOWER(mc.name) LIKE ?")
        params.append(f"%{q.lower()}%")
    if search_status:
        conditions.append("mc.search_status = ?")
        params.append(search_status)
    if client_type:
        conditions.append("mg.client_type = ?")
        params.append(client_type)
    if group_id is not None:
        conditions.append("mc.group_id = ?")
        params.append(group_id)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    having = ""
    if has_contact is True:
        having = "HAVING (wa_count + email_count) > 0"
    elif has_contact is False:
        having = "HAVING (wa_count + email_count) = 0"

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT mc.id
                FROM marketing_clients mc
                JOIN marketing_groups mg ON mc.group_id = mg.id
                LEFT JOIN marketing_contact_results mr ON mr.client_id = mc.id
                {where}
                GROUP BY mc.id
                {having}
            )
        """
        count_cursor = await db.execute(count_sql, params)
        total = (await count_cursor.fetchone())[0]

        data_sql = f"""
            SELECT
                mc.id, mc.name, mc.search_status, mc.created_at,
                mc.group_id,
                mg.name AS group_name, mg.client_type,
                COUNT(CASE WHEN mr.contact_type = 'wa_phone' THEN 1 END) AS wa_count,
                COUNT(CASE WHEN mr.contact_type = 'email'    THEN 1 END) AS email_count,
                COUNT(CASE WHEN mr.is_approved  = 1          THEN 1 END) AS approved_count
            FROM marketing_clients mc
            JOIN marketing_groups mg ON mc.group_id = mg.id
            LEFT JOIN marketing_contact_results mr ON mr.client_id = mc.id
            {where}
            GROUP BY mc.id
            {having}
            ORDER BY mc.created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor = await db.execute(data_sql, [*params, limit, offset])
        rows = await cursor.fetchall()

    clients = [
        {
            "id": row["id"],
            "name": row["name"],
            "search_status": row["search_status"],
            "created_at": row["created_at"],
            "group_id": row["group_id"],
            "group_name": row["group_name"],
            "client_type": row["client_type"],
            "wa_count": row["wa_count"],
            "email_count": row["email_count"],
            "approved_count": row["approved_count"],
        }
        for row in rows
    ]
    return {"clients": clients, "total": total, "limit": limit, "offset": offset}


async def list_clients(
    group_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    search_status: str | None = None,
) -> dict[str, Any]:
    """List clients in a group with their contact results, paginated.
    Returns {clients: [...], total: int, limit: int, offset: int}.
    """
    # Build filter conditions
    conditions: list[str] = ["c.group_id = ?"]
    params: list[Any] = [group_id]

    if q:
        conditions.append("LOWER(c.name) LIKE ?")
        params.append(f"%{q.lower()}%")
    if search_status:
        conditions.append("c.search_status = ?")
        params.append(search_status)

    where_clause = " AND ".join(conditions)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Get total count
        count_cursor = await db.execute(
            f"SELECT COUNT(*) FROM marketing_clients c WHERE {where_clause}",
            params,
        )
        total = (await count_cursor.fetchone())[0]

        # Get paginated client IDs
        cursor = await db.execute(
            f"""
            SELECT
                c.id, c.group_id, c.name, c.extra_data, c.search_status, c.error_message,
                c.ig_handle, c.ig_profile_url, c.ig_last_scraped_at,
                c.ig_post_scrape_status, c.ig_post_scrape_error, c.ig_post_scrape_last_attempt_at,
                c.created_at,
                r.id AS r_id, r.client_id AS r_client_id, r.contact_type,
                r.value, r.source_url, r.source_type, r.confidence,
                r.is_approved, r.is_selected, r.edited_value, r.created_at AS r_created_at
            FROM marketing_clients c
            LEFT JOIN marketing_contact_results r ON r.client_id = c.id
            WHERE {where_clause}
            ORDER BY c.created_at DESC, r.created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        rows = await cursor.fetchall()

        client_ids = list({row[0] for row in rows})
        ig_rows: list[tuple[Any, ...]] = []
        candidate_rows: list[tuple[Any, ...]] = []
        if client_ids:
            placeholders = ",".join("?" * len(client_ids))
            ig_cursor = await db.execute(
                f"""
                  SELECT id, client_id, ig_handle, post_url, image_url, caption,
                      post_timestamp, source, phone_extracted, phones_found, created_at
                FROM marketing_ig_posts
                WHERE client_id IN ({placeholders})
                ORDER BY COALESCE(post_timestamp, created_at) DESC, created_at DESC
                """,
                client_ids,
            )
            ig_rows = await ig_cursor.fetchall()

            candidate_cursor = await db.execute(
                f"""
                SELECT id, client_id, handle, profile_url, source, title, snippet,
                       full_name, bio, external_url, external_domain, is_verified,
                      base_score, affinity_score, profile_score, final_score,
                      llm_is_correct, llm_confidence, llm_reason, rank_order,
                      is_primary, is_selected, created_at
                FROM marketing_ig_candidates
                WHERE client_id IN ({placeholders})
                ORDER BY is_selected DESC, is_primary DESC,
                         COALESCE(rank_order, 999999) ASC, final_score DESC, created_at DESC
                """,
                client_ids,
            )
            candidate_rows = await candidate_cursor.fetchall()

    # Group rows by client
    clients_map: dict[int, dict[str, Any]] = {}
    for row in rows:
        cid = row[0]
        if cid not in clients_map:
            clients_map[cid] = {
                "id": row[0],
                "group_id": row[1],
                "name": row[2],
                "extra_data": (_parse_extra_data(row[3]) if row[3] else None),
                "search_status": row[4],
                "error_message": row[5],
                "ig_handle": row[6],
                "ig_profile_url": row[7],
                "ig_last_scraped_at": row[8],
                "ig_post_scrape_status": row[9],
                "ig_post_scrape_error": row[10],
                "ig_post_scrape_last_attempt_at": row[11],
                "created_at": row[12],
                "ig_candidates": [],
                "ig_posts": [],
                "contacts": [],
            }
        # Append contact if present (r_id is not None)
        if row[13] is not None:
            clients_map[cid]["contacts"].append({
                "id": row[13],
                "client_id": row[14],
                "contact_type": row[15],
                "value": row[16],
                "source_url": row[17],
                "source_type": row[18],
                "confidence": row[19],
                "is_approved": bool(row[20]),
                "is_selected": bool(row[21]),
                "edited_value": row[22],
                "created_at": row[23],
            })

    for row in ig_rows:
        client = clients_map.get(row[1])
        if client is None:
            continue
        client["ig_posts"].append({
            "id": row[0],
            "client_id": row[1],
            "ig_handle": row[2],
            "post_url": row[3],
            "image_url": row[4],
            "caption": row[5],
            "post_timestamp": row[6],
            "source": row[7],
            "phone_extracted": bool(row[8]),
            "phones_found": int(row[9] or 0),
            "created_at": row[10],
        })

    for row in candidate_rows:
        client = clients_map.get(row[1])
        if client is None:
            continue
        llm_is_correct = None if row[16] is None else bool(row[16])
        client["ig_candidates"].append({
            "id": row[0],
            "client_id": row[1],
            "handle": row[2],
            "profile_url": row[3],
            "source": row[4],
            "title": row[5],
            "snippet": row[6],
            "full_name": row[7],
            "bio": row[8],
            "external_url": row[9],
            "external_domain": row[10],
            "is_verified": bool(row[11]),
            "base_score": row[12] or 0.0,
            "affinity_score": row[13] or 0.0,
            "profile_score": row[14] or 0.0,
            "final_score": row[15] or 0.0,
            "llm_is_correct": llm_is_correct,
            "llm_confidence": row[17] or 0.0,
            "llm_reason": row[18],
            "rank_order": row[19],
            "is_primary": bool(row[20]),
            "is_selected": bool(row[21]),
            "created_at": row[22],
        })

    for client in clients_map.values():
        client["contacts"] = _filter_visible_contact_results(client["contacts"])

    return {
        "clients": list(clients_map.values()),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def get_client(client_id: int) -> dict[str, Any] | None:
    """Get a single client by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                c.id, c.group_id, c.name, c.extra_data, c.search_status,
                c.error_message,
                c.orchestration_state, c.orchestration_stage, c.orchestration_summary, c.current_run_id,
                c.ig_handle, c.ig_profile_url, c.ig_last_scraped_at,
                c.ig_post_scrape_status, c.ig_post_scrape_error, c.ig_post_scrape_last_attempt_at,
                c.created_at,
                (SELECT COUNT(*) FROM marketing_contact_results r WHERE r.client_id = c.id) AS contact_count,
                (SELECT COUNT(*) FROM marketing_ig_posts p WHERE p.client_id = c.id) AS ig_post_count
            FROM marketing_clients c
            WHERE c.id = ?
            """,
            (client_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_client_out(row)


async def delete_client(client_id: int) -> bool:
    """Delete a client (cascade deletes results)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM marketing_orchestration_evidence WHERE client_id = ?", (client_id,))
        await db.execute("DELETE FROM marketing_orchestration_runs WHERE client_id = ?", (client_id,))
        await db.execute("DELETE FROM marketing_ig_posts WHERE client_id = ?", (client_id,))
        await db.execute("DELETE FROM marketing_ig_candidates WHERE client_id = ?", (client_id,))
        cursor = await db.execute("DELETE FROM marketing_clients WHERE id = ?", (client_id,))
        await db.commit()
        return cursor.rowcount > 0


async def update_client_search_status(client_id: int, status: str) -> None:
    """Update client search status."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE marketing_clients SET search_status = ?, error_message = NULL WHERE id = ?",
            (status, client_id),
        )
        await db.commit()


async def update_client_orchestration_state(
    client_id: int,
    state: str,
    *,
    stage: str | None = None,
    summary: dict[str, Any] | None = None,
    current_run_id: int | None = None,
) -> None:
    """Persist orchestration state metadata on a marketing client."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE marketing_clients
            SET orchestration_state = ?,
                orchestration_stage = ?,
                orchestration_summary = ?,
                current_run_id = COALESCE(?, current_run_id)
            WHERE id = ?
            """,
            (
                state,
                stage,
                json.dumps(summary) if summary is not None else None,
                current_run_id,
                client_id,
            ),
        )
        await db.commit()


async def create_orchestration_run(
    client_id: int,
    group_id: int,
    mode: str,
    trigger_type: str,
    *,
    state: str = "queued",
    current_stage: str | None = None,
    plan: dict[str, Any] | None = None,
) -> int:
    """Create a new orchestration run for a marketing client."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO marketing_orchestration_runs (
                client_id, group_id, mode, trigger_type, state, current_stage, plan_json, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                group_id,
                mode,
                trigger_type,
                state,
                current_stage,
                json.dumps(plan) if plan else None,
                now,
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def update_orchestration_run(
    run_id: int,
    *,
    state: str | None = None,
    current_stage: str | None = None,
    summary: dict[str, Any] | None = None,
    error_message: str | None = None,
    completed: bool = False,
) -> None:
    """Update the state of an orchestration run."""
    fields: list[str] = []
    params: list[Any] = []

    if state is not None:
        fields.append("state = ?")
        params.append(state)
    if current_stage is not None:
        fields.append("current_stage = ?")
        params.append(current_stage)
    if summary is not None:
        fields.append("summary_json = ?")
        params.append(json.dumps(summary))
    if error_message is not None:
        fields.append("error_message = ?")
        params.append(error_message)

    if completed:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT started_at FROM marketing_orchestration_runs WHERE id = ?",
                (run_id,),
            )
            row = await cursor.fetchone()
            duration_seconds: float | None = None
            if row and row[0]:
                try:
                    started_at = datetime.strptime(str(row[0])[:19], "%Y-%m-%d %H:%M:%S")
                    completed_at = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
                    duration_seconds = max((completed_at - started_at).total_seconds(), 0.0)
                except ValueError:
                    duration_seconds = None
            fields.extend(["completed_at = ?", "duration_seconds = ?"])
            params.extend([now, duration_seconds])
            params.append(run_id)
            await db.execute(
                f"UPDATE marketing_orchestration_runs SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            await db.commit()
        return

    if not fields:
        return

    params.append(run_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            f"UPDATE marketing_orchestration_runs SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        await db.commit()


async def add_orchestration_evidence(
    run_id: int,
    client_id: int,
    stage: str,
    evidence_type: str,
    *,
    source_type: str | None = None,
    source_url: str | None = None,
    value: str | None = None,
    confidence: float = 0.0,
    status: str = "observed",
    reason: str | None = None,
    payload: dict[str, Any] | list[Any] | None = None,
) -> int:
    """Persist a single evidence record for an orchestration run."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO marketing_orchestration_evidence (
                run_id, client_id, stage, evidence_type, source_type, source_url,
                value, confidence, status, reason, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                client_id,
                stage,
                evidence_type,
                source_type,
                source_url,
                value,
                confidence,
                status,
                reason,
                json.dumps(payload) if payload is not None else None,
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def list_orchestration_runs(client_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent orchestration runs for a client."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, client_id, group_id, mode, trigger_type, state, current_stage,
                   plan_json, summary_json, error_message, started_at, completed_at, duration_seconds
            FROM marketing_orchestration_runs
            WHERE client_id = ?
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            (client_id, limit),
        )
        rows = await cursor.fetchall()
    return [_row_to_orchestration_run(row) for row in rows]


async def get_orchestration_run(run_id: int) -> dict[str, Any] | None:
    """Return one orchestration run by id."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, client_id, group_id, mode, trigger_type, state, current_stage,
                   plan_json, summary_json, error_message, started_at, completed_at, duration_seconds
            FROM marketing_orchestration_runs
            WHERE id = ?
            """,
            (run_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_orchestration_run(row)


async def list_orchestration_evidence(run_id: int) -> list[dict[str, Any]]:
    """Return orchestration evidence rows for a run."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, run_id, client_id, stage, evidence_type, source_type, source_url,
                   value, confidence, status, reason, payload_json, created_at
            FROM marketing_orchestration_evidence
            WHERE run_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (run_id,),
        )
        rows = await cursor.fetchall()
    return [_row_to_orchestration_evidence(row) for row in rows]


async def reset_client_search_state(client_id: int) -> None:
    """Clear previous search artifacts so a client can be retried from scratch."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            DELETE FROM marketing_contact_handoffs
            WHERE result_id IN (
                SELECT id FROM marketing_contact_results WHERE client_id = ?
            )
            """,
            (client_id,),
        )
        await db.execute("DELETE FROM marketing_contact_results WHERE client_id = ?", (client_id,))
        await db.execute("DELETE FROM marketing_ig_posts WHERE client_id = ?", (client_id,))
        await db.execute("DELETE FROM marketing_ig_candidates WHERE client_id = ?", (client_id,))
        await db.execute(
            """
            UPDATE marketing_clients
            SET search_status = 'pending',
                error_message = NULL,
                orchestration_state = 'idle',
                orchestration_stage = NULL,
                orchestration_summary = NULL,
                current_run_id = NULL,
                ig_handle = NULL,
                ig_profile_url = NULL,
                ig_last_scraped_at = NULL,
                ig_post_scrape_status = NULL,
                ig_post_scrape_error = NULL,
                ig_post_scrape_last_attempt_at = NULL
            WHERE id = ?
            """,
            (client_id,),
        )
        await db.commit()


async def update_client_error_message(client_id: int, error_message: str) -> None:
    """Set error_message and status='error' for a client after a search failure."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE marketing_clients SET search_status = ?, error_message = ? WHERE id = ?",
            ("error", error_message, client_id),
        )
        await db.commit()


async def mark_group_search_failed(group_id: int, error_message: str) -> None:
    """Set group status back to 'draft' and record the search error so UI can display it."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE marketing_groups SET status = ?, search_error = ?, updated_at = ? WHERE id = ?",
            ("draft", error_message, now, group_id),
        )
        await db.commit()


async def save_client_instagram_profile(
    client_id: int,
    ig_handle: str,
    ig_profile_url: str | None = None,
) -> None:
    """Persist the resolved Instagram profile for a marketing client."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE marketing_clients
            SET ig_handle = ?,
                ig_profile_url = ?,
                ig_last_scraped_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (ig_handle, ig_profile_url, client_id),
        )
        await db.commit()


async def set_client_ig_override(client_id: int, ig_handle: str) -> None:
    """Manually override the IG handle for a client, deselecting all existing candidates
    and inserting a manual_override candidate as primary."""
    handle = ig_handle.strip().lstrip("@").lower()
    profile_url = f"https://instagram.com/{handle}/"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Deselect all existing candidates
        await db.execute(
            "UPDATE marketing_ig_candidates SET is_primary = 0, is_selected = 0 WHERE client_id = ?",
            (client_id,),
        )
        # Upsert the manual override candidate
        await db.execute(
            """
            INSERT INTO marketing_ig_candidates
                (client_id, handle, profile_url, source, is_primary, is_selected,
                 base_score, affinity_score, profile_score, final_score,
                 llm_is_correct, llm_confidence, llm_reason, rank_order)
            VALUES (?, ?, ?, 'manual_override', 1, 1, 1.0, 1.0, 1.0, 1.0, 1, 1.0, 'Manual override by user', 0)
            ON CONFLICT(client_id, handle) DO UPDATE SET
                is_primary = 1, is_selected = 1,
                source = 'manual_override',
                llm_is_correct = 1, llm_confidence = 1.0,
                llm_reason = 'Manual override by user',
                rank_order = 0
            """,
            (client_id, handle, profile_url),
        )
        # Update the client ig_handle
        await db.execute(
            "UPDATE marketing_clients SET ig_handle = ?, ig_profile_url = ? WHERE id = ?",
            (handle, profile_url, client_id),
        )
        await db.commit()


async def clear_client_instagram_profile(client_id: int) -> None:
    """Clear the resolved Instagram profile for a marketing client."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE marketing_clients
            SET ig_handle = NULL,
                ig_profile_url = NULL,
                ig_last_scraped_at = NULL
            WHERE id = ?
            """,
            (client_id,),
        )
        await db.commit()


async def update_client_ig_post_scrape_diagnostic(
    client_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """Persist the last Instagram post scrape outcome for a marketing client."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE marketing_clients
            SET ig_post_scrape_status = ?,
                ig_post_scrape_error = ?,
                ig_post_scrape_last_attempt_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, error_message, client_id),
        )
        await db.commit()


async def get_selected_instagram_handles_for_client(client_id: int) -> list[str]:
    """Return selected IG candidate handles ordered by primary/rank, with profile handle fallback."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT handle
            FROM marketing_ig_candidates
            WHERE client_id = ? AND is_selected = 1
            ORDER BY is_primary DESC, COALESCE(rank_order, 999999) ASC, final_score DESC
            """,
            (client_id,),
        )
        handles = [row[0] for row in await cursor.fetchall() if row[0]]
        if handles:
            return handles

        cursor = await db.execute(
            "SELECT ig_handle FROM marketing_clients WHERE id = ?",
            (client_id,),
        )
        row = await cursor.fetchone()
        if row and row[0]:
            return [row[0]]
        return []


async def get_client_ig_posts(client_id: int) -> list[dict[str, Any]]:
    """Return stored Instagram posts for one marketing client."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, client_id, ig_handle, post_url, image_url, caption,
                   post_timestamp, source, phone_extracted, phones_found, created_at
            FROM marketing_ig_posts
            WHERE client_id = ?
            ORDER BY COALESCE(post_timestamp, created_at) DESC, created_at DESC
            """,
            (client_id,),
        )
        rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "client_id": row[1],
            "ig_handle": row[2],
            "post_url": row[3],
            "image_url": row[4],
            "caption": row[5],
            "post_timestamp": row[6],
            "source": row[7],
            "phone_extracted": bool(row[8]),
            "phones_found": int(row[9] or 0),
            "created_at": row[10],
        }
        for row in rows
    ]


async def clear_client_contact_results_by_source_types(
    client_id: int,
    source_types: list[str],
) -> None:
    """Delete contact results and dependent handoffs for the given client/source types."""
    normalized_source_types = [source_type for source_type in source_types if source_type]
    if not normalized_source_types:
        return

    placeholders = ",".join("?" * len(normalized_source_types))
    params: list[Any] = [client_id, *normalized_source_types]

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            f"""
            DELETE FROM marketing_contact_handoffs
            WHERE result_id IN (
                SELECT id FROM marketing_contact_results
                WHERE client_id = ? AND source_type IN ({placeholders})
            )
            """,
            params,
        )
        await db.execute(
            f"""
            DELETE FROM marketing_contact_results
            WHERE client_id = ? AND source_type IN ({placeholders})
            """,
            params,
        )
        await db.commit()


async def delete_client_contact_results_by_ids(
    client_id: int,
    result_ids: list[int],
) -> None:
    """Delete specific contact results and dependent handoffs for a client."""
    normalized_result_ids = [int(result_id) for result_id in result_ids]
    if not normalized_result_ids:
        return

    placeholders = ",".join("?" * len(normalized_result_ids))
    params: list[Any] = [client_id, *normalized_result_ids]

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            f"""
            DELETE FROM marketing_contact_handoffs
            WHERE result_id IN (
                SELECT id FROM marketing_contact_results
                WHERE client_id = ? AND id IN ({placeholders})
            )
            """,
            params,
        )
        await db.execute(
            f"""
            DELETE FROM marketing_contact_results
            WHERE client_id = ? AND id IN ({placeholders})
            """,
            params,
        )
        await db.commit()


async def replace_client_ig_posts(
    client_id: int,
    ig_handle: str,
    posts: list[dict[str, Any]],
) -> None:
    """Replace stored Instagram posts for a marketing client with the latest scrape."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM marketing_ig_posts WHERE client_id = ?", (client_id,))

        rows = [
            (
                client_id,
                post.get("ig_handle") or ig_handle,
                post.get("post_url"),
                post.get("image_url"),
                post.get("caption"),
                post.get("timestamp"),
                post.get("source"),
                0,
                0,
            )
            for post in posts
            if post.get("post_url")
        ]
        if rows:
            await db.executemany(
                """
                INSERT OR IGNORE INTO marketing_ig_posts
                    (client_id, ig_handle, post_url, image_url, caption, post_timestamp, source, phone_extracted, phones_found)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        await db.commit()


async def mark_client_ig_posts_extracted(
    client_id: int,
    posts: list[dict[str, Any]],
    phones_found_by_post: dict[str, int],
) -> None:
    """Mark stored marketing IG posts as processed by the phone extractor."""
    if not posts:
        return

    async with aiosqlite.connect(DATABASE_PATH) as db:
        for post in posts:
            post_url = str(post.get("post_url") or "").strip()
            if not post_url:
                continue

            await db.execute(
                """
                UPDATE marketing_ig_posts
                SET phone_extracted = 1,
                    phones_found = ?
                WHERE client_id = ? AND post_url = ?
                """,
                (int(phones_found_by_post.get(post_url, 0)), client_id, post_url),
            )

        await db.commit()


async def replace_client_ig_candidates(
    client_id: int,
    candidates: list[dict[str, Any]],
) -> None:
    """Replace stored Instagram candidate audit trail for a marketing client."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM marketing_ig_candidates WHERE client_id = ?", (client_id,))

        rows = [
            (
                client_id,
                candidate.get("handle"),
                candidate.get("url"),
                candidate.get("source"),
                candidate.get("title"),
                candidate.get("snippet"),
                candidate.get("full_name"),
                candidate.get("bio"),
                candidate.get("external_url"),
                candidate.get("external_domain"),
                1 if candidate.get("is_verified") else 0,
                candidate.get("base_score", 0.0),
                candidate.get("affinity_score", 0.0),
                candidate.get("profile_score", 0.0),
                candidate.get("final_score", 0.0),
                None if candidate.get("llm_is_correct") is None else (1 if candidate.get("llm_is_correct") else 0),
                candidate.get("llm_confidence", 0.0),
                candidate.get("llm_reason"),
                candidate.get("rank_order"),
                1 if candidate.get("is_primary") else 0,
                1 if candidate.get("is_selected") else 0,
            )
            for candidate in candidates
            if candidate.get("handle")
        ]
        if rows:
            await db.executemany(
                """
                INSERT OR REPLACE INTO marketing_ig_candidates (
                    client_id, handle, profile_url, source, title, snippet,
                    full_name, bio, external_url, external_domain, is_verified,
                    base_score, affinity_score, profile_score, final_score,
                    llm_is_correct, llm_confidence, llm_reason, rank_order,
                    is_primary, is_selected
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        await db.commit()


async def create_contact_result_for_client(
    client_id: int,
    contact_type: str,
    value: str,
    source_url: str | None = None,
    source_type: str | None = None,
) -> dict[str, Any]:
    """Insert a manual contact result for a client. Returns the created result dict."""
    result_id = await upsert_contact_result(
        client_id,
        contact_type,
        value,
        source_url=source_url,
        source_type=source_type,
    )
    # Fetch and return the created result
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT id, client_id, contact_type, value, source_url, source_type,
                      confidence, is_approved, is_selected, edited_value, created_at
               FROM marketing_contact_results WHERE id = ?""",
            (result_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Contact result {result_id} not found after insert")
        return {
            "id": row[0],
            "client_id": row[1],
            "contact_type": row[2],
            "value": row[3],
            "source_url": row[4],
            "source_type": row[5],
            "confidence": row[6],
            "is_approved": bool(row[7]),
            "is_selected": bool(row[8]),
            "edited_value": row[9],
            "created_at": row[10],
        }


async def upsert_contact_results_batch(
    client_id: int,
    results: list[dict[str, Any]],
) -> int:
    """Batch upsert contact results for a client using executemany.
    Returns the number of rows inserted.
    Uses BEGIN IMMEDIATE transaction for race-condition safety."""
    if not results:
        return 0

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows_to_insert = [
                (
                    client_id,
                    r["contact_type"],
                    r["value"],
                    r.get("source_url"),
                    r.get("source_type"),
                    float(r.get("confidence", 0.0)),
                    r.get("pic_name"),
                    now,
                )
                for r in results
            ]
            await db.executemany(
                """INSERT OR IGNORE INTO marketing_contact_results
                   (client_id, contact_type, value, source_url, source_type, confidence, pic_name, is_selected, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                rows_to_insert,
            )
            inserted = db.total_changes
            await db.commit()
            return inserted
        except Exception:
            await db.rollback()
            raise


async def upsert_contact_result(
    client_id: int,
    contact_type: str,
    value: str,
    source_url: str | None = None,
    source_type: str | None = None,
    confidence: float = 0.0,
    pic_name: str | None = None,
) -> int:
    """Insert a contact result for a client. Returns result id.
    Uses BEGIN IMMEDIATE transaction to avoid race-condition duplicates."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                """
                SELECT id
                FROM marketing_contact_results
                WHERE client_id = ?
                  AND contact_type = ?
                  AND value = ?
                  AND COALESCE(source_url, '') = COALESCE(?, '')
                  AND COALESCE(source_type, '') = COALESCE(?, '')
                LIMIT 1
                """,
                (client_id, contact_type, value, source_url, source_type),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                # Update pic_name if provided
                if pic_name:
                    await db.execute(
                        "UPDATE marketing_contact_results SET pic_name = ? WHERE id = ?",
                        (pic_name, int(existing[0])),
                    )
                await db.commit()
                return int(existing[0])

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor = await db.execute(
                """INSERT INTO marketing_contact_results
                   (client_id, contact_type, value, source_url, source_type, confidence, pic_name, is_selected, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (client_id, contact_type, value, source_url, source_type, confidence, pic_name, now),
            )
            await db.commit()
            return cursor.lastrowid
        except Exception:
            await db.rollback()
            raise


async def get_contact_results_for_client(client_id: int) -> list[dict[str, Any]]:
    """Get all contact results for a client."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, client_id, contact_type, value, source_url, source_type,
                   confidence, is_approved, is_selected, edited_value, pic_name, created_at
            FROM marketing_contact_results
            WHERE client_id = ?
            ORDER BY created_at DESC
            """,
            (client_id,),
        )
        rows = await cursor.fetchall()
        return _filter_visible_contact_results([_row_to_contact_result(r) for r in rows])


async def update_contact_result(
    result_id: int,
    is_approved: bool | None = None,
    is_selected: bool | None = None,
    edited_value: str | None = None,
) -> bool:
    """Patch a contact result. Returns True if updated."""
    fields: list[str] = []
    params: list[Any] = []
    if is_approved is not None:
        fields.append("is_approved = ?")
        params.append(1 if is_approved else 0)
    if is_selected is not None:
        fields.append("is_selected = ?")
        params.append(1 if is_selected else 0)
    if edited_value is not None:
        fields.append("edited_value = ?")
        params.append(edited_value)
    if not fields:
        return False
    params.append(result_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            f"UPDATE marketing_contact_results SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        await db.commit()
        return True


async def get_group_stats(group_id: int) -> dict[str, int]:
    """Get stats for a single group. Uses a single GROUP BY query instead of 6 subqueries."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        status_cursor = await db.execute(
            """
            SELECT search_status, COUNT(*) as cnt
            FROM marketing_clients
            WHERE group_id = ?
            GROUP BY search_status
            """,
            (group_id,),
        )
        status_counts = {row[0]: row[1] for row in await status_cursor.fetchall()}
        total = sum(status_counts.values())
        approved_cursor = await db.execute(
            """
            SELECT COUNT(*)
            FROM marketing_contact_results r
            JOIN marketing_clients c ON c.id = r.client_id
            WHERE c.group_id = ? AND r.is_approved = 1
            """,
            (group_id,),
        )
        approved = (await approved_cursor.fetchone())[0] or 0
        return {
            "total": total,
            "found": status_counts.get("found", 0),
            "partial": status_counts.get("partial", 0),
            "not_found": status_counts.get("not_found", 0),
            "error_count": status_counts.get("error", 0),
            "pending": status_counts.get("pending", 0) + status_counts.get("searching", 0),
            "approved": approved,
        }


async def approve_all_in_group(group_id: int) -> int:
    """Set is_approved=1 for all contacts in all clients of a group. Returns count."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """UPDATE marketing_contact_results
               SET is_approved = 1
               WHERE client_id IN (SELECT id FROM marketing_clients WHERE group_id = ?)""",
            (group_id,),
        )
        await db.commit()
        return cursor.rowcount


async def get_group_search_status(group_id: int) -> dict[str, Any]:
    """Get search status counts for a group."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Single GROUP BY query instead of 6 separate COUNT subqueries
        status_cursor = await db.execute(
            """
            SELECT search_status, COUNT(*) as cnt
            FROM marketing_clients
            WHERE group_id = ?
            GROUP BY search_status
            """,
            (group_id,),
        )
        status_counts = {row[0]: row[1] for row in await status_cursor.fetchall()}

        total = sum(status_counts.values())

        approved_cursor = await db.execute(
            """
            SELECT COUNT(*)
            FROM marketing_contact_results r
            JOIN marketing_clients c ON c.id = r.client_id
            WHERE c.group_id = ? AND r.is_approved = 1
            """,
            (group_id,),
        )
        approved = (await approved_cursor.fetchone())[0] or 0

        # Fetch error messages for clients in error state
        err_cursor = await db.execute(
            """SELECT c.id, c.name, c.error_message
               FROM marketing_clients c
               WHERE c.group_id = ? AND c.search_status = 'error'""",
            (group_id,),
        )
        errors = [
            {"client_id": r[0], "client_name": r[1], "message": r[2] or "Unknown error"}
            for r in await err_cursor.fetchall()
        ]

        # Fetch group-level search error (set when the entire background job crashes)
        grp_cursor = await db.execute(
            "SELECT search_error FROM marketing_groups WHERE id = ?",
            (group_id,),
        )
        grp_row = await grp_cursor.fetchone()
        group_search_error: str | None = grp_row[0] if grp_row else None

        return {
            "total": total,
            "pending": status_counts.get("pending", 0),
            "searching": status_counts.get("searching", 0),
            "found": status_counts.get("found", 0),
            "not_found": status_counts.get("not_found", 0),
            "error_count": status_counts.get("error", 0),
            "partial": status_counts.get("partial", 0),
            "approved": approved,
            "errors": errors,
            "group_search_error": group_search_error,
        }


async def get_pending_clients(group_id: int) -> list[dict[str, Any]]:
    """Get all pending clients in a group."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT id, group_id, name, extra_data, search_status, created_at
               FROM marketing_clients
               WHERE group_id = ? AND search_status = 'pending'
               ORDER BY created_at ASC""",
            (group_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "group_id": r[1],
                "name": r[2],
                "extra_data": json.loads(r[3]) if r[3] else None,
                "search_status": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]


async def get_error_clients(group_id: int) -> list[dict[str, Any]]:
    """Get clients with search_status='error' for auto-retry loop."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT id, group_id, name, extra_data, search_status, error_message, created_at
               FROM marketing_clients
               WHERE group_id = ? AND search_status = 'error'
               ORDER BY created_at ASC""",
            (group_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "group_id": r[1],
                "name": r[2],
                "extra_data": json.loads(r[3]) if r[3] else None,
                "search_status": r[4],
                "error_message": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]


async def recover_orphaned_states() -> dict[str, int]:
    """On startup: reset any clients/runs left in mid-flight state due to crash.
    Does NOT restart searches — leaves groups at 'draft' so the user can decide."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            # 1. Mark incomplete orchestration runs as 'interrupted'
            cur = await db.execute(
                """UPDATE marketing_orchestration_runs
                   SET state = 'interrupted',
                       error_message = 'Server restarted while run was in progress',
                       completed_at = datetime('now')
                   WHERE state NOT IN ('completed', 'failed', 'interrupted')"""
            )
            runs_fixed = cur.rowcount

            # 2. Reset clients with active orchestration_state → 'idle'
            cur = await db.execute(
                """UPDATE marketing_clients
                   SET orchestration_state = 'idle', orchestration_stage = NULL
                   WHERE orchestration_state IN
                     ('planning','collecting','verifying','resolving','deciding','repairing')"""
            )
            clients_state_fixed = cur.rowcount

            # 3. Reset clients stuck at search_status='searching' → 'pending'
            cur = await db.execute(
                """UPDATE marketing_clients
                   SET search_status = 'pending',
                       error_message = 'Reset after server restart'
                   WHERE search_status = 'searching'"""
            )
            clients_searching_fixed = cur.rowcount

            # 4. Revert groups still 'searching' (with no actually-running clients) → 'draft'
            await db.execute(
                """UPDATE marketing_groups
                   SET status = 'draft', updated_at = datetime('now')
                   WHERE status = 'searching'
                     AND NOT EXISTS (
                       SELECT 1 FROM marketing_clients
                       WHERE group_id = marketing_groups.id
                         AND search_status = 'searching'
                     )"""
            )
            await db.commit()
            return {
                "runs_interrupted": runs_fixed,
                "clients_state_reset": clients_state_fixed,
                "clients_searching_reset": clients_searching_fixed,
            }
        except Exception:
            await db.rollback()
            raise


async def get_all_group_contacts_for_export(group_id: int) -> list[dict[str, Any]]:
    """Get all contact results for a group (for Excel export)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                c.name AS client_name,
                r.contact_type,
                COALESCE(r.edited_value, r.value) AS value,
                r.source_url,
                r.source_type,
                r.confidence,
                r.is_approved,
                r.edited_value
            FROM marketing_contact_results r
            JOIN marketing_clients c ON c.id = r.client_id
            WHERE c.group_id = ?
            ORDER BY c.name, r.contact_type
            """,
            (group_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "client_name": r[0],
                "contact_type": r[1],
                "value": r[2],
                "source_url": r[3] or "",
                "source_type": r[4] or "",
                "confidence": r[5] or 0.0,
                "is_approved": bool(r[6]),
                "edited_value": r[7] or "",
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_group_out(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "client_type": row[2],
        "source": row[3],
        "status": row[4],
        "created_at": row[5],
        "updated_at": row[6],
        "total_clients": row[7] or 0,
        "found_count": row[8] or 0,
        "not_found_count": row[9] or 0,
        "pending_count": row[10] or 0,
    }


def _row_to_client_out(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "group_id": row[1],
        "name": row[2],
        "extra_data": json.loads(row[3]) if row[3] else None,
        "search_status": row[4],
        "error_message": row[5],
        "orchestration_state": row[6] or "idle",
        "orchestration_stage": row[7],
        "orchestration_summary": json.loads(row[8]) if row[8] else None,
        "current_run_id": row[9],
        "ig_handle": row[10],
        "ig_profile_url": row[11],
        "ig_last_scraped_at": row[12],
        "ig_post_scrape_status": row[13],
        "ig_post_scrape_error": row[14],
        "ig_post_scrape_last_attempt_at": row[15],
        "created_at": row[16],
        "contact_count": row[17] or 0,
        "ig_post_count": row[18] or 0,
    }


def _contact_result_source_signature(contact: dict[str, Any]) -> tuple[str, str]:
    source_type = str(contact.get("source_type") or "").strip().lower()
    source_url = str(contact.get("source_url") or "").strip()
    host = urlparse(source_url).netloc.lower().removeprefix("www.")
    return (source_type, host)


def _contact_result_source_trust(contact: dict[str, Any]) -> int:
    from . import search as mkt_search

    value = str(contact.get("edited_value") or contact.get("value") or "").strip()
    result = mkt_search.ContactResult(
        contact_type=str(contact.get("contact_type") or "").strip(),
        value=value,
        source_url=str(contact.get("source_url") or "").strip() or None,
        source_type=str(contact.get("source_type") or "").strip() or None,
        confidence=float(contact.get("confidence") or 0.0),
    )
    return mkt_search._contact_source_trust(result)


def _filter_visible_contact_results(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from . import search as mkt_search

    if not contacts:
        return contacts

    support_map: dict[tuple[str, str], set[tuple[str, str]]] = {}
    sanitized: list[dict[str, Any]] = []
    for contact in contacts:
        normalized = dict(contact)
        normalized["value"] = str(contact.get("edited_value") or contact.get("value") or "").strip()
        normalized["source_url"] = str(contact.get("source_url") or "").strip()
        normalized["source_type"] = str(contact.get("source_type") or "").strip()

        # pic_name and pic_title are stored as columns on wa_phone rows — never as separate rows
        if normalized.get("contact_type") in ("pic_name", "pic_title"):
            continue

        if not normalized["value"]:
            continue
        if mkt_search._should_prune_persisted_contact(normalized):
            continue

        key = (str(normalized.get("contact_type") or ""), normalized["value"])
        support_map.setdefault(key, set()).add(_contact_result_source_signature(normalized))
        sanitized.append(normalized)

    trusted_types = {
        str(contact.get("contact_type") or "")
        for contact in sanitized
        if _contact_result_source_trust(contact) >= 3
    }

    visible: list[dict[str, Any]] = []
    for contact in sanitized:
        contact_type = str(contact.get("contact_type") or "")
        value = str(contact.get("value") or "")
        support_count = len(support_map.get((contact_type, value), set()))
        trust = _contact_result_source_trust(contact)

        if trust == 0:
            continue
        if trust < 3 and contact_type in trusted_types:
            continue
        if trust == 1 and support_count < 2:
            continue

        visible.append(contact)

    return visible


def _row_to_contact_result(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "client_id": row[1],
        "contact_type": row[2],
        "value": row[3],
        "source_url": row[4],
        "source_type": row[5],
        "confidence": row[6] or 0.0,
        "is_approved": bool(row[7]),
        "is_selected": bool(row[8]),
        "edited_value": row[9],
        "pic_name": row[10],
        "created_at": row[11],
    }


def _row_to_orchestration_run(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "client_id": row[1],
        "group_id": row[2],
        "mode": row[3],
        "trigger_type": row[4],
        "state": row[5],
        "current_stage": row[6],
        "plan": json.loads(row[7]) if row[7] else None,
        "summary": json.loads(row[8]) if row[8] else None,
        "error_message": row[9],
        "started_at": row[10],
        "completed_at": row[11],
        "duration_seconds": row[12],
    }


def _row_to_orchestration_evidence(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "run_id": row[1],
        "client_id": row[2],
        "stage": row[3],
        "evidence_type": row[4],
        "source_type": row[5],
        "source_url": row[6],
        "value": row[7],
        "confidence": row[8] or 0.0,
        "status": row[9],
        "reason": row[10],
        "payload": json.loads(row[11]) if row[11] else None,
        "created_at": row[12],
    }
