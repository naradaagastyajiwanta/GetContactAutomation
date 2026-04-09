"""
One-time migration: move existing ig_posts.image_data (base64) to S3 bucket.

Usage (run inside orchestrator container or with correct env):
    python scripts/migrate_images_to_bucket.py [--dry-run] [--batch-size 100] [--db-path PATH]

What it does:
    1. Reads posts with image_data set but image_bucket_url empty
    2. Uploads each image to the configured bucket
    3. Sets image_bucket_url, clears image_data
    4. Runs VACUUM at the end to reclaim disk space
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import sys
from pathlib import Path

# Load .env.production before any orchestrator imports so env vars are available
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env.production", override=True)
except Exception:
    pass

import aiosqlite
from orchestrator.config import log
from orchestrator import bucket


async def migrate(dry_run: bool = False, batch_size: int = 100, db_path: str | None = None) -> None:
    if not bucket.is_configured():
        print("ERROR: Bucket not configured. Set BUCKET_* env vars first.")
        sys.exit(1)

    if not db_path:
        db_path = os.getenv("DATABASE_PATH", "data/getcontact.db")
    print(f"DB: {db_path}")
    print(f"Bucket: {bucket._bucket_name()} / {bucket._public_url()}")
    print(f"Dry run: {dry_run}\n")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Count pending
        cur = await db.execute(
            "SELECT COUNT(*) FROM ig_posts WHERE image_data IS NOT NULL AND image_bucket_url IS NULL"
        )
        total = (await cur.fetchone())[0]
        print(f"Posts to migrate: {total}")

        if total == 0:
            print("Nothing to migrate.")
            return

        migrated = 0
        failed = 0
        offset = 0

        while True:
            cur = await db.execute(
                """
                SELECT id, post_url, university_id, image_data
                FROM ig_posts
                WHERE image_data IS NOT NULL AND image_bucket_url IS NULL
                ORDER BY id
                LIMIT ? OFFSET ?
                """,
                (batch_size, offset),
            )
            rows = await cur.fetchall()
            if not rows:
                break

            for row in rows:
                post_id = row["id"]
                post_url = row["post_url"]
                university_id = row["university_id"]
                image_b64 = row["image_data"]

                try:
                    img_bytes = base64.b64decode(image_b64)
                except Exception as e:
                    print(f"  [SKIP] id={post_id} — bad base64: {e}")
                    failed += 1
                    continue

                if dry_run:
                    key = bucket.make_key(post_url, university_id)
                    print(f"  [DRY] id={post_id} -> {key}")
                    migrated += 1
                    continue

                url = await bucket.upload_image(post_url, university_id, img_bytes)
                if url:
                    await db.execute(
                        "UPDATE ig_posts SET image_bucket_url = ?, image_data = NULL WHERE id = ?",
                        (url, post_id),
                    )
                    migrated += 1
                    if migrated % 50 == 0:
                        await db.commit()
                        print(f"  Progress: {migrated}/{total} ({failed} failed)")
                else:
                    failed += 1
                    print(f"  [FAIL] id={post_id} — bucket upload failed")

            await db.commit()
            offset += batch_size

        if not dry_run:
            print(f"\nDone: {migrated} migrated, {failed} failed")
            print("Running VACUUM to reclaim disk space...")
            await db.execute("VACUUM")
            print("VACUUM complete.")
        else:
            print(f"\nDry run complete: {migrated} would be migrated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--db-path", default=None, help="Override database path")
    args = parser.parse_args()
    asyncio.run(migrate(dry_run=args.dry_run, batch_size=args.batch_size, db_path=args.db_path))
