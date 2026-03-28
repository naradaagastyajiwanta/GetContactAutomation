"""Cleanup script: remove DMS_MYSQL_* config values from the database.

These keys are now env-only and must be set via environment variables.
This script removes any stale DB overrides so env values take effect.

Usage:
    python scripts/cleanup_dms_env_only.py

Requires .env or environment variables.
"""
import asyncio
import os
import sys

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from orchestrator.db import init_db, get_all_config, delete_config


DMS_KEYS = [
    "DMS_MYSQL_HOST",
    "DMS_MYSQL_PORT",
    "DMS_MYSQL_USER",
    "DMS_MYSQL_PASSWORD",
    "DMS_MYSQL_DATABASE",
]


async def main():
    await init_db()

    rows = await get_all_config()
    deleted = 0
    for key in DMS_KEYS:
        if key in rows:
            print(f"  Removing DB override for {key} (DB value: {rows[key]!r})")
            await delete_config(key)
            deleted += 1
        else:
            print(f"  {key}: no DB override, using env/default")

    print(f"\nDone. Removed {deleted} DB overrides.")
    if deleted > 0:
        print("Restart the orchestrator for changes to take effect.")


asyncio.run(main())
