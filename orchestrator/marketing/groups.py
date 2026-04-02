"""
Marketing Groups — service layer for managing corporate outreach groups and clients.
"""
import io
import json
from datetime import datetime
from typing import Any

import aiosqlite

from orchestrator.config import DATABASE_PATH


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
) -> list[dict[str, Any]]:
    """List all marketing groups with aggregated stats."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        query = """
            SELECT
                g.id, g.name, g.client_type, g.source, g.status,
                g.created_at, g.updated_at,
                COUNT(c.id) AS total_clients,
                SUM(CASE WHEN c.search_status = 'found' THEN 1 ELSE 0 END) AS found_count,
                SUM(CASE WHEN c.search_status = 'not_found' THEN 1 ELSE 0 END) AS not_found_count,
                SUM(CASE WHEN c.search_status IN ('pending','searching') THEN 1 ELSE 0 END) AS pending_count
            FROM marketing_groups g
            LEFT JOIN marketing_clients c ON c.group_id = g.id
            WHERE 1=1
        """
        params: list[Any] = []
        if client_type:
            query += " AND g.client_type = ?"
            params.append(client_type)
        if status:
            query += " AND g.status = ?"
            params.append(status)
        query += " GROUP BY g.id ORDER BY g.created_at DESC"

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [_row_to_group_out(r) for r in rows]


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
                f"DELETE FROM marketing_contact_results WHERE client_id IN ({placeholders})",
                client_ids,
            )
            await db.execute(
                f"DELETE FROM marketing_ig_posts WHERE client_id IN ({placeholders})",
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


async def list_clients(group_id: int) -> list[dict[str, Any]]:
    """List all clients in a group with their contact results."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                c.id, c.group_id, c.name, c.extra_data, c.search_status, c.error_message,
                c.ig_handle, c.ig_profile_url, c.ig_last_scraped_at, c.created_at,
                r.id AS r_id, r.client_id AS r_client_id, r.contact_type,
                r.value, r.source_url, r.source_type, r.confidence,
                r.is_approved, r.is_selected, r.edited_value, r.created_at AS r_created_at
            FROM marketing_clients c
            LEFT JOIN marketing_contact_results r ON r.client_id = c.id
            WHERE c.group_id = ?
            ORDER BY c.created_at DESC, r.created_at DESC
            """,
            (group_id,),
        )
        rows = await cursor.fetchall()

        client_ids = list({row[0] for row in rows})
        ig_rows: list[tuple[Any, ...]] = []
        if client_ids:
            placeholders = ",".join("?" * len(client_ids))
            ig_cursor = await db.execute(
                f"""
                SELECT id, client_id, ig_handle, post_url, image_url, caption,
                       post_timestamp, source, created_at
                FROM marketing_ig_posts
                WHERE client_id IN ({placeholders})
                ORDER BY COALESCE(post_timestamp, created_at) DESC, created_at DESC
                """,
                client_ids,
            )
            ig_rows = await ig_cursor.fetchall()

    # Group rows by client
    clients_map: dict[int, dict[str, Any]] = {}
    for row in rows:
        cid = row[0]
        if cid not in clients_map:
            clients_map[cid] = {
                "id": row[0],
                "group_id": row[1],
                "name": row[2],
                "extra_data": json.loads(row[3]) if row[3] else None,
                "search_status": row[4],
                "error_message": row[5],
                "ig_handle": row[6],
                "ig_profile_url": row[7],
                "ig_last_scraped_at": row[8],
                "created_at": row[9],
                "ig_posts": [],
                "contacts": [],
            }
        # Append contact if present (r_id is not None)
        if row[10] is not None:
            clients_map[cid]["contacts"].append({
                "id": row[10],
                "client_id": row[11],
                "contact_type": row[12],
                "value": row[13],
                "source_url": row[14],
                "source_type": row[15],
                "confidence": row[16],
                "is_approved": bool(row[17]),
                "is_selected": bool(row[18]),
                "edited_value": row[19],
                "created_at": row[20],
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
            "created_at": row[8],
        })

    return list(clients_map.values())


async def get_client(client_id: int) -> dict[str, Any] | None:
    """Get a single client by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                c.id, c.group_id, c.name, c.extra_data, c.search_status,
                c.ig_handle, c.ig_profile_url, c.ig_last_scraped_at, c.created_at,
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
        await db.execute("DELETE FROM marketing_ig_posts WHERE client_id = ?", (client_id,))
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


async def update_client_error_message(client_id: int, error_message: str) -> None:
    """Set error_message and status='error' for a client after a search failure."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE marketing_clients SET search_status = ?, error_message = ? WHERE id = ?",
            ("error", error_message, client_id),
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
                ig_handle,
                post.get("post_url"),
                post.get("image_url"),
                post.get("caption"),
                post.get("timestamp"),
                post.get("source"),
            )
            for post in posts
            if post.get("post_url")
        ]
        if rows:
            await db.executemany(
                """
                INSERT OR IGNORE INTO marketing_ig_posts
                    (client_id, ig_handle, post_url, image_url, caption, post_timestamp, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        await db.commit()


async def upsert_contact_result(
    client_id: int,
    contact_type: str,
    value: str,
    source_url: str | None = None,
    source_type: str | None = None,
    confidence: float = 0.0,
) -> int:
    """Insert a contact result for a client. Returns result id."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = await db.execute(
            """INSERT INTO marketing_contact_results
               (client_id, contact_type, value, source_url, source_type, confidence, is_selected, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
            (client_id, contact_type, value, source_url, source_type, confidence, now),
        )
        await db.commit()
        return cursor.lastrowid


async def get_contact_results_for_client(client_id: int) -> list[dict[str, Any]]:
    """Get all contact results for a client."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, client_id, contact_type, value, source_url, source_type,
                   confidence, is_approved, is_selected, edited_value, created_at
            FROM marketing_contact_results
            WHERE client_id = ?
            ORDER BY created_at DESC
            """,
            (client_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_contact_result(r) for r in rows]


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
    """Get stats for a single group (total, found, not_found, error, pending, approved)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                COUNT(c.id) AS total,
                SUM(CASE WHEN c.search_status = 'found' THEN 1 ELSE 0 END) AS found,
                SUM(CASE WHEN c.search_status = 'not_found' THEN 1 ELSE 0 END) AS not_found,
                SUM(CASE WHEN c.search_status = 'error' THEN 1 ELSE 0 END) AS error_count,
                SUM(CASE WHEN c.search_status IN ('pending','searching') THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN r.is_approved = 1 THEN 1 ELSE 0 END) AS approved
            FROM marketing_clients c
            LEFT JOIN marketing_contact_results r ON r.client_id = c.id
            WHERE c.group_id = ?
            """,
            (group_id,),
        )
        row = await cursor.fetchone()
        return {
            "total": row[0] or 0,
            "found": row[1] or 0,
            "not_found": row[2] or 0,
            "error_count": row[3] or 0,
            "pending": row[4] or 0,
            "approved": row[5] or 0,
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
        cursor = await db.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN c.search_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN c.search_status = 'searching' THEN 1 ELSE 0 END) AS searching,
                SUM(CASE WHEN c.search_status = 'found' THEN 1 ELSE 0 END) AS found,
                SUM(CASE WHEN c.search_status = 'not_found' THEN 1 ELSE 0 END) AS not_found,
                SUM(CASE WHEN c.search_status = 'error' THEN 1 ELSE 0 END) AS error_count,
                SUM(CASE WHEN r.is_approved = 1 THEN 1 ELSE 0 END) AS approved
            FROM marketing_clients c
            LEFT JOIN marketing_contact_results r ON r.client_id = c.id
            WHERE c.group_id = ?
            """,
            (group_id,),
        )
        row = await cursor.fetchone()

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

        return {
            "total": row[0] or 0,
            "pending": row[1] or 0,
            "searching": row[2] or 0,
            "found": row[3] or 0,
            "not_found": row[4] or 0,
            "error_count": row[5] or 0,
            "approved": row[6] or 0,
            "errors": errors,
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
        "ig_handle": row[5],
        "ig_profile_url": row[6],
        "ig_last_scraped_at": row[7],
        "created_at": row[8],
        "contact_count": row[9] or 0,
        "ig_post_count": row[10] or 0,
    }


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
        "created_at": row[10],
    }
