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
    contact_name TEXT,
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
    extracted_contact_name TEXT,
    extracted_contact_role TEXT,
    last_message_at TIMESTAMP,
    next_action_at TIMESTAMP,
    attempt_count INTEGER DEFAULT 0,
    followup_count INTEGER DEFAULT 0,
    is_test BOOLEAN DEFAULT 0,
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
    source TEXT DEFAULT 'outreach',
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

_DDL_AUDIENSI = """
CREATE TABLE IF NOT EXISTS audiensi_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    source_conversation_id INTEGER REFERENCES conversations(id),
    contact_phone TEXT NOT NULL,
    contact_role TEXT,
    rector_name TEXT,
    state TEXT NOT NULL DEFAULT 'QUEUED',
    message_history TEXT DEFAULT '[]',
    pdf_path TEXT,
    initial_message_draft TEXT,
    scheduled_datetime TEXT,
    zoom_link TEXT,
    agent_reasoning TEXT,
    attempt_count INTEGER DEFAULT 0,
    followup_count INTEGER DEFAULT 0,
    last_message_at TIMESTAMP,
    approved_at TIMESTAMP,
    approved_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_DDL_KNOWLEDGE = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chatbot_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    situation_tags TEXT DEFAULT '',
    trigger_keywords TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_INDEXES_KNOWLEDGE = """
CREATE INDEX IF NOT EXISTS idx_knowledge_items_type_active
    ON knowledge_items(chatbot_type, is_active);
"""

_INDEXES_AUDIENSI = """
CREATE INDEX IF NOT EXISTS idx_audiensi_phone ON audiensi_conversations(contact_phone);
CREATE INDEX IF NOT EXISTS idx_audiensi_state ON audiensi_conversations(state);
CREATE INDEX IF NOT EXISTS idx_audiensi_university ON audiensi_conversations(university_id);
"""

_DDL_API_LOGS = """
CREATE TABLE IF NOT EXISTS api_call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    chatbot_type TEXT NOT NULL,
    call_type TEXT NOT NULL DEFAULT 'reply',
    situation_tags TEXT DEFAULT '[]',
    knowledge_items_injected TEXT DEFAULT '[]',
    system_prompt TEXT,
    messages_sent TEXT,
    model_used TEXT,
    tool_calls_made TEXT DEFAULT '[]',
    response_text TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cached_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_INDEXES_API_LOGS = """
CREATE INDEX IF NOT EXISTS idx_api_logs_conv_id ON api_call_logs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_api_logs_chatbot_type ON api_call_logs(chatbot_type);
CREATE INDEX IF NOT EXISTS idx_api_logs_created_at ON api_call_logs(created_at);
"""

# ---------------------------------------------------------------------------
# Initialization & connection helper
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables if they do not already exist."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Enable WAL mode for concurrent read/write from multiple threads
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(_DDL)
        await db.executescript(_DDL_AGENT)
        await db.executescript(_DDL_CONFIG)
        await db.executescript(_INDEXES)
        await db.executescript(_INDEXES_AGENT)
        await db.executescript(_DDL_AUDIENSI)
        await db.executescript(_INDEXES_AUDIENSI)
        await db.executescript(_DDL_KNOWLEDGE)
        await db.executescript(_INDEXES_KNOWLEDGE)
        await db.executescript(_DDL_API_LOGS)
        await db.executescript(_INDEXES_API_LOGS)
        # Migration: add agent_reasoning column to conversations (idempotent)
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN agent_reasoning TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add is_test column to conversations (idempotent)
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN is_test BOOLEAN DEFAULT 0"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add followup_count column to conversations (idempotent)
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN followup_count INTEGER DEFAULT 0"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add contact_name column to ig_contacts (idempotent)
        try:
            await db.execute(
                "ALTER TABLE ig_contacts ADD COLUMN contact_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add has_person_name flag to ig_contacts
        try:
            await db.execute(
                "ALTER TABLE ig_contacts ADD COLUMN has_person_name BOOLEAN DEFAULT 1"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add last_ig_scraped_at to universities for re-scrape cooldown
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN last_ig_scraped_at TIMESTAMP"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add rector_name to universities for audiensi
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN rector_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add source column to conversation_analyses for audiensi learning
        try:
            await db.execute(
                "ALTER TABLE conversation_analyses ADD COLUMN source TEXT DEFAULT 'outreach'"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add extracted_contact_name to conversations
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN extracted_contact_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add extracted_contact_role to conversations
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN extracted_contact_role TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add situation_tags column to knowledge_items
        try:
            await db.execute(
                "ALTER TABLE knowledge_items ADD COLUMN situation_tags TEXT DEFAULT ''"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add trigger_keywords column to knowledge_items
        try:
            await db.execute(
                "ALTER TABLE knowledge_items ADD COLUMN trigger_keywords TEXT DEFAULT ''"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add cached_tokens column to api_call_logs
        try:
            await db.execute(
                "ALTER TABLE api_call_logs ADD COLUMN cached_tokens INTEGER DEFAULT 0"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add last_response_id to conversations (Responses API session chaining)
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN last_response_id TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add last_response_id to audiensi_conversations (Responses API session chaining)
        try:
            await db.execute(
                "ALTER TABLE audiensi_conversations ADD COLUMN last_response_id TEXT"
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
    Validate and normalise an Indonesian **mobile** phone number.

    Accepts: 08xx…, 628xx…, +628xx…  (mobile only, not landlines)
    Returns: E.164 string (+62…) or None if the number is invalid/not mobile.
    """
    if not number:
        return None

    cleaned = number.strip().replace(" ", "").replace("-", "").replace(".", "")

    try:
        parsed = phonenumbers.parse(cleaned, "ID")
        if not phonenumbers.is_valid_number(parsed):
            return None
        # Only accept mobile numbers (reject landlines, toll-free, etc.)
        num_type = phonenumbers.number_type(parsed)
        if num_type not in (
            phonenumbers.PhoneNumberType.MOBILE,
            phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
        ):
            return None
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


async def update_university_website(uni_id: int, website: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET website = ? WHERE id = ? AND (website IS NULL OR website = '')",
            (website, uni_id),
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
    contact_name: str | None = None,
    has_person_name: bool = True,
) -> int | None:
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO ig_contacts
                (university_id, phone_number, contact_name, source_post_url, source_image_url, has_person_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (university_id, phone_number, contact_name, source_post_url, source_image_url, has_person_name),
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


async def count_posts_for_university(university_id: int, only_unextracted: bool = False) -> int:
    """Return total post count (or unextracted count) for a university."""
    async with get_db() as db:
        where = "university_id = ?"
        if only_unextracted:
            where += " AND phone_extracted = 0"
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM ig_posts WHERE {where}",
            (university_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_post_urls_for_university(university_id: int) -> set[str]:
    """Return set of all post_url values already stored for a university."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT post_url FROM ig_posts WHERE university_id = ?",
            (university_id,),
        )
        rows = await cursor.fetchall()
        return {row[0] for row in rows}


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


async def create_conversation(
    university_id: int | None, contact_phone: str, is_test: bool = False
) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO conversations (university_id, contact_phone, state, is_test, created_at)
            VALUES (?, ?, 'PENDING', ?, ?)
            """,
            (university_id, contact_phone, int(is_test), _utcnow()),
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
        "extracted_contact_name",
        "extracted_contact_role",
        "last_message_at",
        "next_action_at",
        "attempt_count",
        "followup_count",
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


async def get_active_conversations(include_test: bool = True) -> list[dict]:
    """Return conversations not yet in a terminal state."""
    placeholders = ",".join("?" * len(_TERMINAL_STATES))
    test_clause = "" if include_test else " AND is_test = 0"
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM conversations WHERE state NOT IN ({placeholders}){test_clause}",
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
              AND is_test = 0
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
    is_test: bool | None = None,
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
    if is_test is not None:
        conditions.append("c.is_test = ?")
        params.append(int(is_test))

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

        # Universities with IG handle
        cursor = await db.execute(
            "SELECT COUNT(*) AS total FROM universities WHERE ig_handle IS NOT NULL AND ig_handle != ''"
        )
        row = await cursor.fetchone()
        universities_with_ig = row["total"] if row else 0

        # Universities with secretariat phone
        cursor = await db.execute(
            "SELECT COUNT(*) AS total FROM universities WHERE secretariat_phone IS NOT NULL AND secretariat_phone != ''"
        )
        row = await cursor.fetchone()
        universities_with_phone = row["total"] if row else 0

        # Total IG contacts
        cursor = await db.execute("SELECT COUNT(*) AS total FROM ig_contacts")
        row = await cursor.fetchone()
        total_contacts = row["total"] if row else 0

        # Total conversations
        cursor = await db.execute("SELECT COUNT(*) AS total FROM conversations")
        row = await cursor.fetchone()
        total_conversations = row["total"] if row else 0

        # Active conversations (non-terminal)
        placeholders = ",".join("?" * len(_TERMINAL_STATES))
        cursor = await db.execute(
            f"SELECT COUNT(*) AS total FROM conversations WHERE state NOT IN ({placeholders})",
            _TERMINAL_STATES,
        )
        row = await cursor.fetchone()
        active_conversations = row["total"] if row else 0

        # Successful conversations (GOT_NUMBER)
        cursor = await db.execute(
            "SELECT COUNT(*) AS total FROM conversations WHERE state = 'GOT_NUMBER'"
        )
        row = await cursor.fetchone()
        successful_conversations = row["total"] if row else 0

    today_quota = await get_today_quota()

    return {
        "total_universities": total_universities,
        "universities_with_ig": universities_with_ig,
        "universities_with_phone": universities_with_phone,
        "total_contacts": total_contacts,
        "total_conversations": total_conversations,
        "active_conversations": active_conversations,
        "successful_conversations": successful_conversations,
        "today_messages_sent": today_quota.get("messages_sent", 0),
        "today_conversations_started": today_quota.get("conversations_started", 0),
        "daily_conversation_limit": cfg.MAX_DAILY_CONVERSATIONS,
        "status_counts": status_counts,
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
                 recommended_improvements, summary, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                data.get("source", "outreach"),
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
                SUM(CASE WHEN outcome IN ('GOT_NUMBER', 'ZOOM_SENT', 'SCHEDULED') THEN 1 ELSE 0 END) AS successes,
                ROUND(AVG(response_time_minutes), 1) AS avg_response_minutes,
                ROUND(
                    CAST(SUM(CASE WHEN outcome IN ('GOT_NUMBER', 'ZOOM_SENT', 'SCHEDULED') THEN 1 ELSE 0 END) AS REAL)
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


# ---------------------------------------------------------------------------
# Audiensi Conversations CRUD
# ---------------------------------------------------------------------------

_AUDIENSI_TERMINAL_STATES = ("ZOOM_SENT", "REFUSED", "ABANDONED")


async def create_audiensi_conversation(
    university_id: int,
    source_conversation_id: int | None,
    contact_phone: str,
    contact_role: str | None = None,
    rector_name: str | None = None,
) -> int:
    """Create audiensi conversation, return new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO audiensi_conversations
               (university_id, source_conversation_id, contact_phone, contact_role, rector_name, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (university_id, source_conversation_id, contact_phone, contact_role, rector_name, _utcnow()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_audiensi_conversation_by_id(aud_id: int) -> dict | None:
    """Return a single audiensi conversation by ID with university name."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT a.*, u.name AS university_name, u.province
               FROM audiensi_conversations a
               LEFT JOIN universities u ON u.id = a.university_id
               WHERE a.id = ?""",
            (aud_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_audiensi_conversation_by_phone(phone: str) -> dict | None:
    """Return latest non-terminal audiensi conversation for a phone."""
    placeholders = ",".join("?" * len(_AUDIENSI_TERMINAL_STATES))
    async with get_db() as db:
        cursor = await db.execute(
            f"""SELECT a.*, u.name AS university_name
                FROM audiensi_conversations a
                LEFT JOIN universities u ON u.id = a.university_id
                WHERE a.contact_phone = ? AND a.state NOT IN ({placeholders})
                ORDER BY a.created_at DESC LIMIT 1""",
            (phone, *_AUDIENSI_TERMINAL_STATES),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_audiensi_conversations_filtered(
    state: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Return audiensi conversations with optional state filter."""
    conditions = []
    params: list = []
    if state:
        conditions.append("a.state = ?")
        params.append(state)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with get_db() as db:
        cursor = await db.execute(
            f"""SELECT a.*, u.name AS university_name
                FROM audiensi_conversations a
                LEFT JOIN universities u ON u.id = a.university_id
                {where}
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def update_audiensi_state(aud_id: int, state: str, **kwargs) -> None:
    """Update state of audiensi conversation plus optional extra fields."""
    allowed_fields = {
        "message_history", "pdf_path", "initial_message_draft",
        "scheduled_datetime", "zoom_link", "agent_reasoning",
        "attempt_count", "followup_count", "last_message_at",
        "approved_at", "approved_by", "contact_role", "rector_name",
    }
    extra = {k: v for k, v in kwargs.items() if k in allowed_fields}
    set_clauses = ["state = ?"]
    values: list[Any] = [state]
    for field, value in extra.items():
        set_clauses.append(f"{field} = ?")
        values.append(value)
    values.append(aud_id)
    sql = f"UPDATE audiensi_conversations SET {', '.join(set_clauses)} WHERE id = ?"
    async with get_db() as db:
        await db.execute(sql, values)
        await db.commit()


async def add_audiensi_message(aud_id: int, role: str, content: str) -> None:
    """Append a message to audiensi conversation's message_history JSON."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT message_history FROM audiensi_conversations WHERE id = ?",
            (aud_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            log.warning("add_audiensi_message: audiensi %d not found", aud_id)
            return
        history: list[dict] = json.loads(row["message_history"] or "[]")
        history.append({"role": role, "content": content, "timestamp": _utcnow()})
        await db.execute(
            "UPDATE audiensi_conversations SET message_history = ?, last_message_at = ? WHERE id = ?",
            (json.dumps(history), _utcnow(), aud_id),
        )
        await db.commit()


async def get_queued_audiensi() -> list[dict]:
    """Return audiensi conversations in QUEUED state for approval queue."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT a.*, u.name AS university_name, u.province
               FROM audiensi_conversations a
               LEFT JOIN universities u ON u.id = a.university_id
               WHERE a.state = 'QUEUED'
               ORDER BY a.created_at""",
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_active_audiensi() -> list[dict]:
    """Return non-terminal audiensi conversations."""
    placeholders = ",".join("?" * len(_AUDIENSI_TERMINAL_STATES))
    async with get_db() as db:
        cursor = await db.execute(
            f"""SELECT a.*, u.name AS university_name
                FROM audiensi_conversations a
                LEFT JOIN universities u ON u.id = a.university_id
                WHERE a.state NOT IN ({placeholders})
                ORDER BY a.last_message_at DESC NULLS LAST""",
            _AUDIENSI_TERMINAL_STATES,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_audiensi_stats() -> dict:
    """Return aggregate counts for audiensi dashboard."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT state, COUNT(*) AS count FROM audiensi_conversations GROUP BY state"
        )
        rows = await cursor.fetchall()
        state_counts = {r["state"]: r["count"] for r in rows}
        cursor = await db.execute("SELECT COUNT(*) AS total FROM audiensi_conversations")
        row = await cursor.fetchone()
        total = row["total"] if row else 0
    return {
        "total": total,
        "queued": state_counts.get("QUEUED", 0),
        "approved": state_counts.get("APPROVED", 0),
        "in_progress": sum(state_counts.get(s, 0) for s in ("INITIAL_SENT", "WAITING_REPLY", "REPLIED", "ANALYZING", "SCHEDULING", "NEED_MORE", "FOLLOWUP_SENT")),
        "scheduled": state_counts.get("SCHEDULED", 0),
        "completed": state_counts.get("ZOOM_SENT", 0),
        "refused": state_counts.get("REFUSED", 0),
        "abandoned": state_counts.get("ABANDONED", 0),
        "state_counts": state_counts,
    }


async def update_university_rector_name(uni_id: int, rector_name: str) -> None:
    """Update rector_name on universities table."""
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET rector_name = ? WHERE id = ?",
            (rector_name, uni_id),
        )
        await db.commit()


async def get_audiensi_needing_followup(hours_threshold: int) -> list[dict]:
    """Return audiensi conversations needing follow-up."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT a.*, u.name AS university_name
               FROM audiensi_conversations a
               LEFT JOIN universities u ON u.id = a.university_id
               WHERE a.state IN ('WAITING_REPLY', 'FOLLOWUP_SENT')
                 AND a.last_message_at IS NOT NULL
                 AND (julianday('now') - julianday(a.last_message_at)) * 24 >= ?
               ORDER BY a.last_message_at""",
            (hours_threshold,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Knowledge Items CRUD
# ---------------------------------------------------------------------------


async def get_knowledge_items(
    chatbot_type: str | None = None, active_only: bool = False
) -> list[dict]:
    """Return knowledge items, optionally filtered by chatbot_type and active status."""
    conditions: list[str] = []
    params: list = []
    if chatbot_type:
        conditions.append("chatbot_type = ?")
        params.append(chatbot_type)
    if active_only:
        conditions.append("is_active = 1")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM knowledge_items {where} ORDER BY created_at DESC",
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_knowledge_items_by_tags(
    chatbot_type: str, tags: list[str], active_only: bool = True
) -> list[dict]:
    """Fetch knowledge items whose situation_tags overlap with the given tags."""
    if not tags:
        return []
    conditions = ["chatbot_type = ?"]
    params: list = [chatbot_type]
    if active_only:
        conditions.append("is_active = 1")
    # Match any tag via OR of LIKE clauses
    tag_clauses = []
    for tag in tags:
        tag_clauses.append("situation_tags LIKE ?")
        params.append(f"%{tag}%")
    conditions.append(f"({' OR '.join(tag_clauses)})")
    where = " AND ".join(conditions)
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM knowledge_items WHERE {where} ORDER BY created_at DESC",
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_knowledge_item_by_id(item_id: int) -> dict | None:
    """Return a single knowledge item by ID."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM knowledge_items WHERE id = ?", (item_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def create_knowledge_item(
    chatbot_type: str, title: str, content: str,
    situation_tags: str = "", trigger_keywords: str = "",
) -> int:
    """Insert a knowledge item and return its id."""
    now = _utcnow()
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO knowledge_items (chatbot_type, title, content, situation_tags, trigger_keywords, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (chatbot_type, title, content, situation_tags, trigger_keywords, now, now),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def match_knowledge_items_by_message(
    chatbot_type: str, message: str,
) -> list[dict]:
    """Match knowledge items against a message using trigger_keywords.

    Matching rules:
    - Items with trigger_keywords: inject if ANY keyword appears in the message
    - Items with situation_tags containing 'tone_umum' but no trigger_keywords: always inject
    - Items with neither trigger_keywords nor 'tone_umum' tag: skip

    This replaces the old flow of hardcoded detector -> tag lookup.
    """
    all_items = await get_knowledge_items(chatbot_type, active_only=True)
    msg_lower = message.lower()
    matched: list[dict] = []

    for item in all_items:
        trigger_kw = (item.get("trigger_keywords") or "").strip()
        sit_tags = (item.get("situation_tags") or "").strip()

        if trigger_kw:
            # Check if any trigger keyword appears in the message
            keywords = [kw.strip().lower() for kw in trigger_kw.split(",") if kw.strip()]
            if any(kw in msg_lower for kw in keywords):
                matched.append(item)
        elif "tone_umum" in sit_tags:
            # Always inject tone_umum items (no keywords needed)
            matched.append(item)
        # else: item has no trigger_keywords and no tone_umum tag → skip

    return matched


async def update_knowledge_item(item_id: int, **kwargs) -> None:
    """Update specific fields of a knowledge item."""
    allowed = {"title", "content", "is_active", "situation_tags", "trigger_keywords"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _utcnow()
    set_clauses = [f"{k} = ?" for k in updates]
    values = list(updates.values())
    values.append(item_id)
    async with get_db() as db:
        await db.execute(
            f"UPDATE knowledge_items SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        await db.commit()


async def delete_knowledge_item(item_id: int) -> None:
    """Delete a knowledge item."""
    async with get_db() as db:
        await db.execute("DELETE FROM knowledge_items WHERE id = ?", (item_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# API Call Logs
# ---------------------------------------------------------------------------


async def save_api_call_log(data: dict) -> int:
    """Insert a row into api_call_logs and return the new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO api_call_logs
                (conversation_id, chatbot_type, call_type, situation_tags,
                 knowledge_items_injected, system_prompt, messages_sent,
                 model_used, tool_calls_made, response_text,
                 prompt_tokens, completion_tokens, total_tokens, cached_tokens, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("conversation_id"),
                data.get("chatbot_type", "agent"),
                data.get("call_type", "reply"),
                json.dumps(data.get("situation_tags", [])),
                json.dumps(data.get("knowledge_items_injected", [])),
                data.get("system_prompt"),
                json.dumps(data.get("messages_sent")) if data.get("messages_sent") else None,
                data.get("model_used"),
                json.dumps(data.get("tool_calls_made", [])),
                data.get("response_text"),
                data.get("prompt_tokens", 0),
                data.get("completion_tokens", 0),
                data.get("total_tokens", 0),
                data.get("cached_tokens", 0),
                _utcnow(),
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_api_call_logs(
    chatbot_type: str | None = None,
    conversation_id: int | None = None,
    call_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return api_call_logs list (excludes system_prompt and messages_sent for brevity)."""
    conditions: list[str] = []
    params: list = []
    if chatbot_type:
        conditions.append("chatbot_type = ?")
        params.append(chatbot_type)
    if conversation_id is not None:
        conditions.append("conversation_id = ?")
        params.append(conversation_id)
    if call_type:
        conditions.append("call_type = ?")
        params.append(call_type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT id, conversation_id, chatbot_type, call_type,
                   situation_tags, knowledge_items_injected, model_used,
                   tool_calls_made, response_text,
                   prompt_tokens, completion_tokens, total_tokens, cached_tokens, created_at
            FROM api_call_logs
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_api_call_log_by_id(log_id: int) -> dict | None:
    """Return a full api_call_log row by ID (including system_prompt & messages_sent)."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM api_call_logs WHERE id = ?", (log_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def update_last_response_id(table: str, row_id: int, response_id: str) -> None:
    """Save a Responses API response_id for session chaining."""
    if table not in ("conversations", "audiensi_conversations"):
        raise ValueError(f"Invalid table: {table}")
    async with get_db() as db:
        await db.execute(
            f"UPDATE {table} SET last_response_id = ? WHERE id = ?",
            (response_id, row_id),
        )
        await db.commit()


async def clear_last_response_id(table: str, row_id: int) -> None:
    """Clear last_response_id when session needs to be invalidated."""
    if table not in ("conversations", "audiensi_conversations"):
        raise ValueError(f"Invalid table: {table}")
    async with get_db() as db:
        await db.execute(
            f"UPDATE {table} SET last_response_id = NULL WHERE id = ?",
            (row_id,),
        )
        await db.commit()


async def clear_all_response_ids(table: str) -> None:
    """Clear all last_response_id values (e.g. when knowledge base changes)."""
    if table not in ("conversations", "audiensi_conversations"):
        raise ValueError(f"Invalid table: {table}")
    async with get_db() as db:
        await db.execute(
            f"UPDATE {table} SET last_response_id = NULL WHERE last_response_id IS NOT NULL"
        )
        await db.commit()


async def cleanup_old_api_logs(days: int = 7) -> int:
    """Delete api_call_logs older than *days* days. Return count deleted."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM api_call_logs WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await db.commit()
        return cursor.rowcount
