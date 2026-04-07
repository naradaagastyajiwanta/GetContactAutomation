"""
Safe migration script for marketing tables.
Run with: python scripts/migrate_marketing.py
"""
import asyncio
import aiosqlite
import os

DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/getcontact.db")


async def run_migration():
    print(f"Connecting to database: {DATABASE_PATH}")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")

        statements = [
            """
            CREATE TABLE IF NOT EXISTS marketing_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                client_type TEXT NOT NULL,
                source TEXT DEFAULT 'manual',
                status TEXT DEFAULT 'draft',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS marketing_clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES marketing_groups(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                extra_data TEXT,
                search_status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS marketing_contact_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL REFERENCES marketing_clients(id) ON DELETE CASCADE,
                contact_type TEXT NOT NULL,
                value TEXT NOT NULL,
                source_url TEXT,
                source_type TEXT,
                confidence REAL DEFAULT 0.0,
                is_approved INTEGER DEFAULT 0,
                is_selected INTEGER DEFAULT 1,
                edited_value TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS marketing_contact_handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES marketing_groups(id) ON DELETE CASCADE,
                result_id INTEGER NOT NULL REFERENCES marketing_contact_results(id) ON DELETE CASCADE,
                handoff_type TEXT NOT NULL,
                campaign_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Indexes
            "CREATE INDEX IF NOT EXISTS idx_mc_group ON marketing_clients(group_id);",
            "CREATE INDEX IF NOT EXISTS idx_mc_status ON marketing_clients(search_status);",
            "CREATE INDEX IF NOT EXISTS idx_mcr_client ON marketing_contact_results(client_id);",
            "CREATE INDEX IF NOT EXISTS idx_mcr_type ON marketing_contact_results(contact_type);",
            "CREATE INDEX IF NOT EXISTS idx_mch_group ON marketing_contact_handoffs(group_id);",
            "CREATE INDEX IF NOT EXISTS idx_mch_result ON marketing_contact_handoffs(result_id);",
        ]

        for sql in statements:
            try:
                await db.executescript(sql)
                print(f"OK: {sql[:60].strip()}")
            except Exception as e:
                print(f"ERROR: {e}: {sql[:60].strip()}")

        await db.commit()

        # Verify tables exist
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'marketing_%' ORDER BY name;"
        )
        rows = await cursor.fetchall()
        print("\nMarketing tables created:")
        for row in rows:
            print(f"  - {row[0]}")

    print("\nMigration complete.")


if __name__ == "__main__":
    asyncio.run(run_migration())
