"""
Initialize the SQLite database with all required tables.
Usage: python scripts/setup_db.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.db import init_db
from orchestrator.config import DATABASE_PATH, log


async def main():
    print(f"Initializing database at: {DATABASE_PATH}")
    await init_db()
    print("Database initialized successfully!")
    print("Tables created: universities, ig_contacts, conversations, daily_quota")


if __name__ == "__main__":
    asyncio.run(main())
