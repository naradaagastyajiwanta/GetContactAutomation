"""
One-time migration: SQLite ig_contacts → MySQL kontak_auto

Steps:
1. For each university in SQLite, find matching id_univ in MySQL universitas by name
2. Update SQLite universities.dms_univ_id with matched id_univ
3. Insert ig_contacts into MySQL kontak_auto (skip duplicates)

Usage:
    python scripts/migrate_ig_contacts_to_dms.py
    python scripts/migrate_ig_contacts_to_dms.py --dry-run
"""

import asyncio
import sys
import aiosqlite

# Add project root to path
sys.path.insert(0, ".")

from orchestrator.config import DATABASE_PATH, log
from orchestrator.dms_mysql import (
    init_dms_pool,
    find_dms_university_by_name,
    sync_contact_to_dms,
    close_dms_pool,
)


async def migrate(dry_run: bool = False) -> None:
    print(f"{'[DRY RUN] ' if dry_run else ''}Starting migration: SQLite ig_contacts → MySQL kontak_auto")
    print(f"SQLite DB: {DATABASE_PATH}")

    pool = await init_dms_pool()
    if not pool:
        print("ERROR: Could not connect to MySQL. Check DMS_MYSQL_* env vars.")
        return

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Load all universities
        cursor = await db.execute(
            "SELECT id, name, dms_univ_id FROM universities ORDER BY name"
        )
        universities = await cursor.fetchall()
        print(f"Found {len(universities)} universities in SQLite\n")

        total_synced = 0
        total_skipped = 0
        total_errors = 0
        matched_univs = 0
        unmatched_univs = []

        for univ in universities:
            univ_id = univ["id"]
            univ_name = univ["name"]
            dms_univ_id = univ["dms_univ_id"]

            # Resolve MySQL id_univ if not already cached
            if not dms_univ_id:
                match = await find_dms_university_by_name(univ_name)
                if match:
                    dms_univ_id = int(match["id_univ"])
                    if not dry_run:
                        await db.execute(
                            "UPDATE universities SET dms_univ_id = ? WHERE id = ?",
                            (dms_univ_id, univ_id),
                        )
                        await db.commit()
                    print(f"  [MATCH] {univ_name} → id_univ={dms_univ_id}")
                    matched_univs += 1
                else:
                    unmatched_univs.append(univ_name)
                    continue
            else:
                matched_univs += 1

            # Get all ig_contacts for this university
            c_cursor = await db.execute(
                "SELECT phone_number, contact_name, source_post_url FROM ig_contacts WHERE university_id = ?",
                (univ_id,),
            )
            contacts = await c_cursor.fetchall()

            if not contacts:
                continue

            print(f"  {univ_name} (id_univ={dms_univ_id}): {len(contacts)} contacts")

            for contact in contacts:
                no_hp = contact["phone_number"]
                pic = contact["contact_name"] or "Unknown"
                source_url = contact["source_post_url"] or ""

                if dry_run:
                    print(f"    [DRY] would sync: {no_hp} ({pic})")
                    total_synced += 1
                    continue

                try:
                    result = await sync_contact_to_dms(
                        id_univ=dms_univ_id,
                        universitas=univ_name,
                        pic=pic,
                        jabatan="Unknown",
                        no_hp=no_hp,
                        source_type="ig_scraping",
                        source_origin="GetContact AI – Migration",
                        source_url=source_url,
                    )
                    if result:
                        total_synced += 1
                    else:
                        total_skipped += 1  # Already exists
                except Exception as e:
                    print(f"    ERROR syncing {no_hp}: {e}")
                    total_errors += 1

    await close_dms_pool()

    print(f"\n{'='*50}")
    print(f"Migration {'(DRY RUN) ' if dry_run else ''}complete:")
    print(f"  Universities matched : {matched_univs}")
    print(f"  Universities unmatched: {len(unmatched_univs)}")
    print(f"  Contacts synced      : {total_synced}")
    print(f"  Contacts skipped     : {total_skipped} (already existed)")
    print(f"  Contacts errors      : {total_errors}")

    if unmatched_univs:
        print(f"\nUnmatched universities ({len(unmatched_univs)}):")
        for name in unmatched_univs[:20]:
            print(f"  - {name}")
        if len(unmatched_univs) > 20:
            print(f"  ... and {len(unmatched_univs) - 20} more")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(migrate(dry_run=dry_run))
