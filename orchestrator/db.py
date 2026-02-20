import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import phonenumbers

from orchestrator.config import DATABASE_PATH, log, cfg

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS universities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pddikti_id TEXT UNIQUE,
    province TEXT,
    website TEXT,
    ig_handle TEXT,
    ig_verified BOOLEAN DEFAULT 0,
    secretariat_phone TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ig_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER REFERENCES universities(id),
    phone_number TEXT NOT NULL,
    source_post_url TEXT,
    source_image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ig_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    post_url TEXT NOT NULL,
    image_url TEXT,
    caption TEXT,
    post_timestamp TEXT,
    phone_extracted BOOLEAN DEFAULT 0,
    phones_found INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(university_id, post_url)
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER REFERENCES universities(id),
    contact_phone TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING',
    message_history TEXT DEFAULT '[]',
    extracted_number TEXT,
    last_message_at TIMESTAMP,
    next_action_at TIMESTAMP,
    attempt_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_quota (
    date TEXT PRIMARY KEY,
    messages_sent INTEGER DEFAULT 0,
    conversations_started INTEGER DEFAULT 0
);
"""

_DDL_AGENT = """
CREATE TABLE IF NOT EXISTS conversation_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    outcome TEXT,
    total_messages INTEGER,
    total_attempts INTEGER,
    duration_hours REAL,
    province TEXT,
    success_factors TEXT,
    failure_factors TEXT,
    contact_personality TEXT,
    effective_strategies TEXT,
    recommended_improvements TEXT,
    summary TEXT,
    processed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    situation_type TEXT,
    insight TEXT,
    recommended_strategy TEXT,
    province TEXT,
    success_rate REAL DEFAULT 0,
    example_count INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.5,
    is_active INTEGER DEFAULT 1,
    source_analysis_ids TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    strategy_used TEXT,
    situation_type TEXT,
    outcome TEXT,
    province TEXT,
    response_time_minutes REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_ig_contacts_unique
    ON ig_contacts(university_id, phone_number);

CREATE INDEX IF NOT EXISTS idx_ig_posts_extraction ON ig_posts(phone_extracted);
CREATE INDEX IF NOT EXISTS idx_ig_posts_university ON ig_posts(university_id);
CREATE INDEX IF NOT EXISTS idx_universities_status ON universities(status);
CREATE INDEX IF NOT EXISTS idx_conversations_phone ON conversations(contact_phone);
"""

_DDL_CONFIG = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

_INDEXES_AGENT = """
CREATE INDEX IF NOT EXISTS idx_conv_analyses_conv_id ON conversation_analyses(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conv_analyses_processed ON conversation_analyses(processed);
CREATE INDEX IF NOT EXISTS idx_lessons_situation ON lessons(situation_type);
CREATE INDEX IF NOT EXISTS idx_lessons_active ON lessons(is_active);
CREATE INDEX IF NOT EXISTS idx_strategy_metrics_conv ON strategy_metrics(conversation_id);
CREATE INDEX IF NOT EXISTS idx_strategy_metrics_strategy ON strategy_metrics(strategy_used);
"""

# ---------------------------------------------------------------------------
# Initialization & connection helper
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables if they do not already exist."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(_DDL)
        await db.executescript(_DDL_AGENT)
        await db.executescript(_DDL_CONFIG)
        await db.executescript(_INDEXES)
        await db.executescript(_INDEXES_AGENT)
        # Migration: add agent_reasoning column to conversations (idempotent)
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN agent_reasoning TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        await db.commit()
    log.info("Database initialised at %s", DATABASE_PATH)


@asynccontextmanager
async def get_db():
    """Async context manager that yields an aiosqlite connection with row_factory."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


# ---------------------------------------------------------------------------
# Phone number validation
# ---------------------------------------------------------------------------


def validate_phone(number: str) -> str | None:
    """
    Validate and normalise an Indonesian phone number.

    Accepts: 08xx…, 628xx…, +628xx…
    Returns: E.164 string (+62…) or None if the number is invalid.
    """
    if not number:
        return None

    cleaned = number.strip().replace(" ", "").replace("-", "").replace(".", "")

    try:
        parsed = phonenumbers.parse(cleaned, "ID")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return dict(row)


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in rows]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# University CRUD
# ---------------------------------------------------------------------------


async def add_university(
    name: str,
    pddikti_id: str | None = None,
    province: str | None = None,
    website: str | None = None,
) -> int:
    """Insert a university row and return the new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO universities (name, pddikti_id, province, website)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(pddikti_id) DO UPDATE SET
                name = excluded.name,
                province = excluded.province,
                website = excluded.website
            """,
            (name, pddikti_id, province, website),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_universities_by_status(status: str, limit: int = 100, offset: int = 0) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM universities WHERE status = ? LIMIT ? OFFSET ?",
            (status, limit, offset),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def update_university_status(uni_id: int, status: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET status = ? WHERE id = ?",
            (status, uni_id),
        )
        await db.commit()


async def update_ig_handle(uni_id: int, handle: str, verified: bool = False) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET ig_handle = ?, ig_verified = ? WHERE id = ?",
            (handle, int(verified), uni_id),
        )
        await db.commit()


async def update_secretariat_phone(uni_id: int, phone: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET secretariat_phone = ? WHERE id = ?",
            (phone, uni_id),
        )
        await db.commit()


async def get_university_by_id(uni_id: int) -> dict | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM universities WHERE id = ?",
            (uni_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def search_universities(query: str) -> list[dict]:
    pattern = f"%{query}%"
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM universities WHERE name LIKE ? OR province LIKE ?",
            (pattern, pattern),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_all_universities(limit: int = 5000, offset: int = 0) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM universities ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# IG Contacts CRUD
# ---------------------------------------------------------------------------


async def add_ig_contact(
    university_id: int,
    phone_number: str,
    source_post_url: str | None = None,
    source_image_url: str | None = None,
) -> int | None:
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO ig_contacts (university_id, phone_number, source_post_url, source_image_url)
            VALUES (?, ?, ?, ?)
            """,
            (university_id, phone_number, source_post_url, source_image_url),
        )
        await db.commit()
        return cursor.lastrowid if cursor.rowcount > 0 else None


async def get_contacts_for_university(university_id: int) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM ig_contacts WHERE university_id = ?",
            (university_id,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_unused_contacts() -> list[dict]:
    """Return IG contacts that have no matching conversation yet."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT ic.*
            FROM ig_contacts ic
            LEFT JOIN conversations c ON c.contact_phone = ic.phone_number
            WHERE c.id IS NULL
            ORDER BY ic.created_at
            """,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# IG Posts CRUD
# ---------------------------------------------------------------------------


async def add_ig_post(
    university_id: int,
    post_url: str,
    image_url: str | None = None,
    caption: str | None = None,
    post_timestamp: str | None = None,
) -> int | None:
    """Insert a scraped post row (INSERT OR IGNORE for dedup)."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO ig_posts
                (university_id, post_url, image_url, caption, post_timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (university_id, post_url, image_url, caption, post_timestamp),
        )
        await db.commit()
        return cursor.lastrowid if cursor.rowcount > 0 else None


async def get_unextracted_posts(limit: int = 50) -> list[dict]:
    """Return ig_posts rows that haven't been processed for phone extraction."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT p.*, u.name AS university_name
            FROM ig_posts p
            JOIN universities u ON u.id = p.university_id
            WHERE p.phone_extracted = 0
            ORDER BY p.created_at
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def mark_post_extracted(post_id: int, phones_found: int) -> None:
    """Mark a post as processed and record how many phones were found."""
    async with get_db() as db:
        await db.execute(
            "UPDATE ig_posts SET phone_extracted = 1, phones_found = ? WHERE id = ?",
            (phones_found, post_id),
        )
        await db.commit()


async def get_pipeline_status() -> dict:
    """Return a breakdown of pipeline stages for /pipeline/status."""
    async with get_db() as db:
        # University status counts
        cursor = await db.execute(
            "SELECT status, COUNT(*) AS count FROM universities GROUP BY status"
        )
        rows = await cursor.fetchall()
        status_counts = {r["status"]: r["count"] for r in rows}

        # Unprocessed posts
        cursor = await db.execute(
            "SELECT COUNT(*) AS total FROM ig_posts WHERE phone_extracted = 0"
        )
        row = await cursor.fetchone()
        posts_unprocessed = row["total"] if row else 0

        # Total contacts
        cursor = await db.execute("SELECT COUNT(*) AS total FROM ig_contacts")
        row = await cursor.fetchone()
        total_contacts = row["total"] if row else 0

    return {
        "pending": status_counts.get("pending", 0),
        "ig_found": status_counts.get("ig_found", 0),
        "ig_scraped": status_counts.get("ig_scraped", 0),
        "contacted": status_counts.get("contacted", 0),
        "got_number": status_counts.get("got_number", 0),
        "failed": status_counts.get("failed", 0),
        "posts_unprocessed": posts_unprocessed,
        "total_contacts": total_contacts,
    }


# ---------------------------------------------------------------------------
# Conversations CRUD
# ---------------------------------------------------------------------------

_TERMINAL_STATES = ("GOT_NUMBER", "REFUSED", "ABANDONED")


async def create_conversation(university_id: int, contact_phone: str) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO conversations (university_id, contact_phone, state, created_at)
            VALUES (?, ?, 'PENDING', ?)
            """,
            (university_id, contact_phone, _utcnow()),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def update_conversation_state(conv_id: int, state: str, **kwargs) -> None:
    """
    Update the state of a conversation plus any extra fields supplied as
    keyword arguments (message_history, extracted_number, last_message_at,
    next_action_at, attempt_count).
    """
    allowed_fields = {
        "message_history",
        "extracted_number",
        "last_message_at",
        "next_action_at",
        "attempt_count",
        "agent_reasoning",
    }
    extra = {k: v for k, v in kwargs.items() if k in allowed_fields}

    set_clauses = ["state = ?"]
    values: list[Any] = [state]

    for field, value in extra.items():
        set_clauses.append(f"{field} = ?")
        values.append(value)

    values.append(conv_id)
    sql = f"UPDATE conversations SET {', '.join(set_clauses)} WHERE id = ?"

    async with get_db() as db:
        await db.execute(sql, values)
        await db.commit()


async def get_active_conversations() -> list[dict]:
    """Return conversations not yet in a terminal state."""
    placeholders = ",".join("?" * len(_TERMINAL_STATES))
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM conversations WHERE state NOT IN ({placeholders})",
            _TERMINAL_STATES,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_conversations_needing_followup(hours_threshold: int) -> list[dict]:
    """
    Return conversations in WAITING_REPLY or FOLLOWUP_SENT state whose
    last_message_at is older than *hours_threshold* hours.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT * FROM conversations
            WHERE state IN ('WAITING_REPLY', 'FOLLOWUP_SENT')
              AND last_message_at IS NOT NULL
              AND (
                (julianday('now') - julianday(last_message_at)) * 24 >= ?
              )
            ORDER BY last_message_at
            """,
            (hours_threshold,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_conversation_by_phone(phone: str) -> dict | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM conversations WHERE contact_phone = ? ORDER BY created_at DESC LIMIT 1",
            (phone,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_posts_for_university(university_id: int) -> list[dict]:
    """Return all ig_posts for a given university."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM ig_posts WHERE university_id = ? ORDER BY created_at DESC",
            (university_id,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_conversations_filtered(
    state: str | None = None,
    university_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Return conversations with optional filters and pagination."""
    conditions = []
    params: list = []

    if state:
        conditions.append("c.state = ?")
        params.append(state)
    if university_id:
        conditions.append("c.university_id = ?")
        params.append(university_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT c.*, u.name AS university_name
            FROM conversations c
            LEFT JOIN universities u ON u.id = c.university_id
            {where}
            ORDER BY c.last_message_at DESC NULLS LAST
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_conversation_by_id(conv_id: int) -> dict | None:
    """Return a single conversation by ID with university name."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT c.*, u.name AS university_name
            FROM conversations c
            LEFT JOIN universities u ON u.id = c.university_id
            WHERE c.id = ?
            """,
            (conv_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def add_message_to_history(conv_id: int, role: str, content: str) -> None:
    """Append a {role, content, timestamp} entry to the JSON message_history column."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT message_history FROM conversations WHERE id = ?",
            (conv_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            log.warning("add_message_to_history: conversation %d not found", conv_id)
            return

        history: list[dict] = json.loads(row["message_history"] or "[]")
        history.append({"role": role, "content": content, "timestamp": _utcnow()})

        await db.execute(
            "UPDATE conversations SET message_history = ?, last_message_at = ? WHERE id = ?",
            (json.dumps(history), _utcnow(), conv_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Daily Quota
# ---------------------------------------------------------------------------


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def get_today_quota() -> dict:
    today = _today()
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT messages_sent, conversations_started FROM daily_quota WHERE date = ?",
            (today,),
        )
        row = await cursor.fetchone()
        if row:
            return _row_to_dict(row)
        return {"messages_sent": 0, "conversations_started": 0}


async def increment_quota(field: str) -> None:
    """Increment *field* (messages_sent or conversations_started) for today."""
    if field not in ("messages_sent", "conversations_started"):
        raise ValueError(f"Unknown quota field: {field}")

    today = _today()
    async with get_db() as db:
        await db.execute(
            f"""
            INSERT INTO daily_quota (date, {field}) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET {field} = {field} + 1
            """,
            (today,),
        )
        await db.commit()


async def can_send_today() -> bool:
    """Return True if conversations_started is below MAX_DAILY_CONVERSATIONS."""
    quota = await get_today_quota()
    return quota["conversations_started"] < cfg.MAX_DAILY_CONVERSATIONS


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


async def get_dashboard_stats() -> dict:
    """Return aggregate counts for the dashboard."""
    async with get_db() as db:
        # Status breakdown for universities
        cursor = await db.execute(
            "SELECT status, COUNT(*) AS count FROM universities GROUP BY status"
        )
        rows = await cursor.fetchall()
        status_counts = {r["status"]: r["count"] for r in rows}

        # Total universities
        cursor = await db.execute("SELECT COUNT(*) AS total FROM universities")
        row = await cursor.fetchone()
        total_universities = row["total"] if row else 0

        # Total IG contacts
        cursor = await db.execute("SELECT COUNT(*) AS total FROM ig_contacts")
        row = await cursor.fetchone()
        total_ig_contacts = row["total"] if row else 0

        # Active conversations
        placeholders = ",".join("?" * len(_TERMINAL_STATES))
        cursor = await db.execute(
            f"SELECT COUNT(*) AS total FROM conversations WHERE state NOT IN ({placeholders})",
            _TERMINAL_STATES,
        )
        row = await cursor.fetchone()
        active_conversations = row["total"] if row else 0

    today_quota = await get_today_quota()

    return {
        "total_universities": total_universities,
        "total_ig_contacts": total_ig_contacts,
        "active_conversations": active_conversations,
        "status_counts": status_counts,
        "today_quota": today_quota,
    }


# ---------------------------------------------------------------------------
# Agent reasoning
# ---------------------------------------------------------------------------


async def update_agent_reasoning(conv_id: int, reasoning: str) -> None:
    """Update the agent_reasoning column for a conversation."""
    async with get_db() as db:
        await db.execute(
            "UPDATE conversations SET agent_reasoning = ? WHERE id = ?",
            (reasoning, conv_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Conversation analyses
# ---------------------------------------------------------------------------


async def search_conversations_for_learning(
    province: str | None = None,
    outcome: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search completed conversations by province/outcome for learning."""
    conditions = [f"c.state IN ({','.join('?' * len(_TERMINAL_STATES))})"]
    params: list[Any] = list(_TERMINAL_STATES)

    if province:
        conditions.append("u.province = ?")
        params.append(province)
    if outcome:
        conditions.append("c.state = ?")
        params.append(outcome)

    where = " AND ".join(conditions)
    params.append(limit)

    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT c.*, u.name AS university_name, u.province
            FROM conversations c
            LEFT JOIN universities u ON u.id = c.university_id
            WHERE {where}
            ORDER BY c.last_message_at DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def save_conversation_analysis(data: dict) -> int:
    """Insert a row into conversation_analyses and return the new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO conversation_analyses
                (conversation_id, outcome, total_messages, total_attempts,
                 duration_hours, province, success_factors, failure_factors,
                 contact_personality, effective_strategies,
                 recommended_improvements, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("conversation_id"),
                data.get("outcome"),
                data.get("total_messages"),
                data.get("total_attempts"),
                data.get("duration_hours"),
                data.get("province"),
                json.dumps(data.get("success_factors")) if data.get("success_factors") else None,
                json.dumps(data.get("failure_factors")) if data.get("failure_factors") else None,
                data.get("contact_personality"),
                json.dumps(data.get("effective_strategies")) if data.get("effective_strategies") else None,
                data.get("recommended_improvements"),
                data.get("summary"),
                _utcnow(),
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_unprocessed_analyses(limit: int = 50) -> list[dict]:
    """Return conversation_analyses rows that haven't been processed yet."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM conversation_analyses WHERE processed = 0 ORDER BY created_at LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def mark_analyses_processed(ids: list[int]) -> None:
    """Mark the given conversation_analyses as processed."""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    async with get_db() as db:
        await db.execute(
            f"UPDATE conversation_analyses SET processed = 1 WHERE id IN ({placeholders})",
            ids,
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Lessons CRUD
# ---------------------------------------------------------------------------


async def get_lessons_by_situation(
    situation_type: str,
    province: str | None = None,
    min_confidence: float = 0.3,
    limit: int = 5,
) -> list[dict]:
    """
    Get active lessons for a situation type.

    Returns province-specific lessons first, then general ones,
    sorted by confidence * success_rate descending.
    """
    params: list[Any] = [situation_type, min_confidence]
    province_clause = ""
    if province:
        province_clause = """
            CASE WHEN province = ? THEN 0
                 WHEN province IS NULL THEN 1
                 ELSE 2
            END,
        """
        params.insert(1, province)

    params.append(limit)

    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT * FROM lessons
            WHERE situation_type = ?
              AND is_active = 1
              AND confidence >= ?
            ORDER BY
                {province_clause}
                (confidence * success_rate) DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_all_active_lessons() -> list[dict]:
    """Return all active lessons."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM lessons WHERE is_active = 1 ORDER BY situation_type, confidence DESC"
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def create_lesson(data: dict) -> int:
    """Insert a new lesson and return its id."""
    async with get_db() as db:
        now = _utcnow()
        cursor = await db.execute(
            """
            INSERT INTO lessons
                (situation_type, insight, recommended_strategy, province,
                 success_rate, example_count, confidence, is_active,
                 source_analysis_ids, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("situation_type"),
                data.get("insight"),
                data.get("recommended_strategy"),
                data.get("province"),
                data.get("success_rate", 0),
                data.get("example_count", 0),
                data.get("confidence", 0.5),
                data.get("is_active", 1),
                json.dumps(data.get("source_analysis_ids")) if data.get("source_analysis_ids") else None,
                now,
                now,
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def update_lesson(lesson_id: int, **kwargs) -> None:
    """Update specific fields of a lesson."""
    allowed = {
        "situation_type", "insight", "recommended_strategy", "province",
        "success_rate", "example_count", "confidence", "is_active",
        "source_analysis_ids",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return

    # JSON-encode source_analysis_ids if present
    if "source_analysis_ids" in updates and isinstance(updates["source_analysis_ids"], (list, dict)):
        updates["source_analysis_ids"] = json.dumps(updates["source_analysis_ids"])

    updates["updated_at"] = _utcnow()

    set_clauses = [f"{k} = ?" for k in updates]
    values = list(updates.values())
    values.append(lesson_id)

    async with get_db() as db:
        await db.execute(
            f"UPDATE lessons SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        await db.commit()


async def deactivate_lesson(lesson_id: int) -> None:
    """Set is_active=0 for a lesson."""
    async with get_db() as db:
        await db.execute(
            "UPDATE lessons SET is_active = 0, updated_at = ? WHERE id = ?",
            (_utcnow(), lesson_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Strategy metrics
# ---------------------------------------------------------------------------


async def save_strategy_metric(data: dict) -> int:
    """Insert a row into strategy_metrics and return the new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO strategy_metrics
                (conversation_id, strategy_used, situation_type, outcome,
                 province, response_time_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("conversation_id"),
                data.get("strategy_used"),
                data.get("situation_type"),
                data.get("outcome"),
                data.get("province"),
                data.get("response_time_minutes"),
                _utcnow(),
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_aggregated_strategy_metrics(since_days: int = 7) -> list[dict]:
    """
    Aggregate strategy_metrics grouped by strategy_used and situation_type
    for the last *since_days* days.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT
                strategy_used,
                situation_type,
                COUNT(*) AS total_uses,
                SUM(CASE WHEN outcome = 'GOT_NUMBER' THEN 1 ELSE 0 END) AS successes,
                ROUND(AVG(response_time_minutes), 1) AS avg_response_minutes,
                ROUND(
                    CAST(SUM(CASE WHEN outcome = 'GOT_NUMBER' THEN 1 ELSE 0 END) AS REAL)
                    / COUNT(*), 3
                ) AS success_rate
            FROM strategy_metrics
            WHERE created_at >= datetime('now', ?)
            GROUP BY strategy_used, situation_type
            ORDER BY total_uses DESC
            """,
            (f"-{since_days} days",),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Config CRUD
# ---------------------------------------------------------------------------


async def get_all_config() -> dict[str, str]:
    """Return all rows from the config table as {key: value}."""
    async with get_db() as db:
        cursor = await db.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
        return {r["key"]: r["value"] for r in rows}


async def upsert_config(key: str, value: str) -> None:
    """Insert or update a config key."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO config (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
            """,
            (key, value),
        )
        await db.commit()


async def delete_config(key: str) -> None:
    """Delete a config key (resets to default)."""
    async with get_db() as db:
        await db.execute("DELETE FROM config WHERE key = ?", (key,))
        await db.commit()
