"""
University Groups — service layer for managing university groups.

Groups are named collections of universities for quick selection in blast campaigns.
"""

from datetime import datetime
from typing import Any, TypedDict

import aiosqlite

from orchestrator.config import DATABASE_PATH


class UniversityGroup(TypedDict):
    id: int
    name: str
    description: str
    university_count: int
    created_at: str
    updated_at: str


class UniversityGroupDetail(TypedDict):
    id: int
    name: str
    description: str
    created_at: str
    updated_at: str
    universities: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_group(name: str, description: str = "") -> UniversityGroup:
    """Create a new university group."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = await db.execute(
            "INSERT INTO university_groups (name, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, description, now, now),
        )
        await db.commit()
        group_id = cursor.lastrowid

        cursor2 = await db.execute(
            """
            SELECT g.id, g.name, g.description, g.created_at, g.updated_at,
                   COUNT(m.id) AS university_count
            FROM university_groups g
            LEFT JOIN university_group_members m ON m.group_id = g.id
            WHERE g.id = ?
            GROUP BY g.id
            """,
            (group_id,),
        )
        row = await cursor2.fetchone()
        return _row_to_group(row)


async def list_groups() -> list[UniversityGroup]:
    """List all university groups with university counts."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT g.id, g.name, g.description, g.created_at, g.updated_at,
                   COUNT(m.id) AS university_count
            FROM university_groups g
            LEFT JOIN university_group_members m ON m.group_id = g.id
            GROUP BY g.id
            ORDER BY g.created_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [_row_to_group(r) for r in rows]


async def get_group(group_id: int) -> UniversityGroup | None:
    """Get a single group by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT g.id, g.name, g.description, g.created_at, g.updated_at,
                   COUNT(m.id) AS university_count
            FROM university_groups g
            LEFT JOIN university_group_members m ON m.group_id = g.id
            WHERE g.id = ?
            GROUP BY g.id
            """,
            (group_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_group(row)


async def get_group_detail(group_id: int) -> UniversityGroupDetail | None:
    """Get a group with all member universities."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        group_cursor = await db.execute(
            "SELECT id, name, description, created_at, updated_at FROM university_groups WHERE id = ?",
            (group_id,),
        )
        group_row = await group_cursor.fetchone()
        if group_row is None:
            return None

        member_cursor = await db.execute(
            """
            SELECT u.id, u.name, u.province, u.website, u.ig_handle, u.email_kampus,
                   u.student_count, u.status, u.enabled, u.created_at, u.updated_at,
                   m.added_at,
                   (SELECT COUNT(*) FROM ig_contacts c WHERE c.university_id = u.id) AS total_contacts,
                   (SELECT COUNT(*) FROM ig_contacts c WHERE c.university_id = u.id AND c.manual_contacted = 1) AS contacted_contacts
            FROM university_group_members m
            JOIN universities u ON u.id = m.university_id
            WHERE m.group_id = ?
            ORDER BY m.added_at DESC
            """,
            (group_id,),
        )
        member_rows = await member_cursor.fetchall()

        return {
            "id": group_row[0],
            "name": group_row[1],
            "description": group_row[2],
            "created_at": group_row[3],
            "updated_at": group_row[4],
            "universities": [
                {
                    "id": r[0],
                    "name": r[1],
                    "province": r[2],
                    "website": r[3],
                    "ig_handle": r[4],
                    "email_kampus": r[5],
                    "student_count": r[6],
                    "status": r[7],
                    "enabled": r[8],
                    "created_at": r[9],
                    "updated_at": r[10],
                    "added_at": r[11],
                    "total_contacts": r[12] or 0,
                    "contacted_contacts": r[13] or 0,
                }
                for r in member_rows
            ],
        }


async def update_group(group_id: int, name: str | None = None, description: str | None = None) -> UniversityGroup | None:
    """Update a group's name and/or description."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Build update dynamically
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        updates.append("updated_at = ?")
        params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        params.append(group_id)

        if updates:
            await db.execute(
                f"UPDATE university_groups SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await db.commit()

        return await get_group(group_id)


async def delete_group(group_id: int) -> bool:
    """Delete a group and all its members (cascade)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM university_groups WHERE id = ?", (group_id,))
        await db.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


async def add_universities_to_group(group_id: int, university_ids: list[int]) -> int:
    """Add universities to a group. Skips already-existing memberships."""
    if not university_ids:
        return 0

    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        added = 0
        for uid in university_ids:
            try:
                await db.execute(
                    "INSERT INTO university_group_members (group_id, university_id, added_at) VALUES (?, ?, ?)",
                    (group_id, uid, now),
                )
                added += 1
            except aiosqlite.IntegrityError:
                pass  # already a member
        await db.commit()
        # Update group's updated_at
        await db.execute(
            "UPDATE university_groups SET updated_at = ? WHERE id = ?",
            (now, group_id),
        )
        await db.commit()
        return added


async def remove_universities_from_group(group_id: int, university_ids: list[int]) -> int:
    """Remove universities from a group."""
    if not university_ids:
        return 0

    async with aiosqlite.connect(DATABASE_PATH) as db:
        placeholders = ",".join("?" * len(university_ids))
        cursor = await db.execute(
            f"DELETE FROM university_group_members WHERE group_id = ? AND university_id IN ({placeholders})",
            [group_id] + university_ids,
        )
        await db.commit()
        # Update group's updated_at
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "UPDATE university_groups SET updated_at = ? WHERE id = ?",
            (now, group_id),
        )
        await db.commit()
        return cursor.rowcount


async def get_group_university_ids(group_id: int) -> list[int]:
    """Get just the university IDs for a group (lightweight)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT university_id FROM university_group_members WHERE group_id = ?",
            (group_id,),
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def get_university_ids_from_groups(group_ids: list[int]) -> list[int]:
    """Resolve multiple group IDs to a list of unique university IDs."""
    if not group_ids:
        return []

    async with aiosqlite.connect(DATABASE_PATH) as db:
        placeholders = ",".join("?" * len(group_ids))
        cursor = await db.execute(
            f"SELECT DISTINCT university_id FROM university_group_members WHERE group_id IN ({placeholders})",
            group_ids,
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_group(row: tuple[Any, ...]) -> UniversityGroup:
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "created_at": row[3],
        "updated_at": row[4],
        "university_count": row[5],
    }
