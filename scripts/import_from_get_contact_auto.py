"""
Import universities data from Get-Contact-Auto JSON files into GetContactAIAgent DB.

Data sources (from f:/Programming/Get-Contact-Auto/get-contact-auto/data/):
1. universities_with_instagram.json — 6628 universities with PDDIKTI data + IG handles
2. rektor_results_*.json — 6335 rector names with confidence scores

Mapping to GetContactAIAgent universities table:
  name            ← entry["name"]
  pddikti_id      ← entry["detail_token"]  (unique PDDIKTI identifier)
  province         ← entry["metadata"]["provinsi_pt"]  (cleaned: strip "Prov. " prefix)
  website          ← entry["website"]
  ig_handle        ← extracted from entry["instagram"] URL
  ig_verified      ← 0 (not verified via bio check)
  rector_name      ← from rektor_results (matched by name)
  status           ← "ig_found" if has IG handle, else "pending"

Usage:
  cd F:/Programming/GetContactAIAgent
  python scripts/import_from_get_contact_auto.py [--dry-run] [--aktif-only]

Options:
  --dry-run       Show what would be imported without writing to DB
  --aktif-only    Only import universities with status_pt = "Aktif" (default: all)
  --data-dir PATH Override data directory (default: auto-detect)
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure the orchestrator package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiosqlite
from orchestrator.config import DATABASE_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_province(raw: str | None) -> str | None:
    """Strip 'Prov. ' prefix and clean up province name."""
    if not raw:
        return None
    # Remove "Prov. " prefix
    cleaned = re.sub(r"^Prov\.\s*", "", raw.strip())
    return cleaned if cleaned else None


def _extract_ig_handle(url: str | None) -> str | None:
    """Extract Instagram handle from URL like https://www.instagram.com/handle."""
    if not url:
        return None
    # Match instagram.com/handle pattern
    m = re.search(r"instagram\.com/([a-zA-Z0-9_.]+)", url)
    if m:
        handle = m.group(1).lower()
        # Skip non-profile paths
        if handle in ("p", "reel", "stories", "explore", "accounts", "tv"):
            return None
        return handle
    return None


def _find_data_dir() -> Path:
    """Auto-detect the get-contact-auto data directory."""
    candidates = [
        Path(r"f:\Programming\Get-Contact-Auto\get-contact-auto\data"),
        Path(r"F:\Programming\Get-Contact-Auto\get-contact-auto\data"),
        Path(__file__).resolve().parent.parent.parent / "Get-Contact-Auto" / "get-contact-auto" / "data",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Cannot find get-contact-auto data directory. "
        "Use --data-dir to specify it."
    )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_universities(data_dir: Path) -> list[dict]:
    """Load universities_with_instagram.json."""
    path = data_dir / "universities_with_instagram.json"
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  Loaded {len(data)} universities from {path.name}")
    return data


def load_rektor_results(data_dir: Path) -> dict[str, str]:
    """Load rektor results and return {uni_name: rektor_name} mapping."""
    # Find the rektor file (may have timestamp in name)
    rektor_files = list(data_dir.glob("rektor_results_*.json"))
    if not rektor_files:
        print("  Warning: No rektor_results file found, skipping rector data")
        return {}

    # Use the most recent one
    rektor_file = sorted(rektor_files)[-1]
    with open(rektor_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    mapping = {}
    for entry in data:
        name = (entry.get("universitas_name") or "").strip()
        rektor = (entry.get("rektor_name") or "").strip()
        if name and rektor and rektor.upper() != "UNKNOWN":
            mapping[name] = rektor

    print(f"  Loaded {len(mapping)} rector names from {rektor_file.name}")
    return mapping


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------

async def run_import(
    data_dir: Path,
    dry_run: bool = False,
    aktif_only: bool = False,
) -> dict:
    """Import universities into GetContactAIAgent database."""

    print(f"\n{'='*60}")
    print("  Import Get-Contact-Auto → GetContactAIAgent")
    print(f"{'='*60}")
    print(f"  Database: {DATABASE_PATH}")
    print(f"  Data dir: {data_dir}")
    print(f"  Dry run:  {dry_run}")
    print(f"  Aktif only: {aktif_only}")
    print()

    # Load data
    print("Loading data...")
    universities = load_universities(data_dir)
    rektor_map = load_rektor_results(data_dir)

    # Filter aktif-only if requested
    if aktif_only:
        before = len(universities)
        universities = [
            u for u in universities
            if u.get("metadata", {}).get("status_pt") == "Aktif"
        ]
        print(f"  Filtered to {len(universities)} active universities (from {before})")

    # Prepare import records
    records = []
    for entry in universities:
        name = entry.get("name", "").strip()
        if not name:
            continue

        pddikti_id = entry.get("detail_token")
        province = _clean_province(entry.get("metadata", {}).get("provinsi_pt"))
        website = entry.get("website", "").strip() or None
        ig_handle = _extract_ig_handle(entry.get("instagram"))
        rector_name = rektor_map.get(name)

        # Determine initial status
        if ig_handle:
            status = "ig_found"
        else:
            status = "pending"

        records.append({
            "name": name,
            "pddikti_id": pddikti_id,
            "province": province,
            "website": website,
            "ig_handle": ig_handle,
            "rector_name": rector_name,
            "status": status,
        })

    # Stats
    total = len(records)
    with_ig = sum(1 for r in records if r["ig_handle"])
    with_website = sum(1 for r in records if r["website"])
    with_rektor = sum(1 for r in records if r["rector_name"])

    print(f"\n  Prepared {total} records:")
    print(f"    With IG handle:  {with_ig}")
    print(f"    With website:    {with_website}")
    print(f"    With rector:     {with_rektor}")
    print(f"    Status pending:  {total - with_ig}")
    print(f"    Status ig_found: {with_ig}")

    if dry_run:
        print("\n  [DRY RUN] No changes written to database.")
        # Show sample records
        print("\n  Sample records:")
        for r in records[:5]:
            print(f"    {r['name'][:50]:50s} | {r['province'] or '-':25s} | IG: {r['ig_handle'] or '-':25s} | {r['status']}")
        return {
            "total": total,
            "with_ig": with_ig,
            "with_website": with_website,
            "with_rektor": with_rektor,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
        }

    # Ensure DB is initialized
    print("\n  Importing to database...")

    # Import using aiosqlite directly (so we can do batch INSERT)
    inserted = 0
    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")

        # Ensure rector_name column exists (migration)
        try:
            await db.execute("ALTER TABLE universities ADD COLUMN rector_name TEXT")
            await db.commit()
        except Exception:
            pass

        # Get existing universities by pddikti_id and by name for dedup
        cursor = await db.execute("SELECT id, name, pddikti_id, ig_handle, rector_name FROM universities")
        existing_rows = await cursor.fetchall()

        existing_by_pddikti = {}
        existing_by_name = {}
        for row in existing_rows:
            r = dict(row)
            if r["pddikti_id"]:
                existing_by_pddikti[r["pddikti_id"]] = r
            existing_by_name[r["name"].strip().lower()] = r

        print(f"  Existing universities in DB: {len(existing_rows)}")

        for rec in records:
            # Check for existing by pddikti_id first, then by name
            existing = None
            if rec["pddikti_id"]:
                existing = existing_by_pddikti.get(rec["pddikti_id"])
            if not existing:
                existing = existing_by_name.get(rec["name"].strip().lower())

            if existing:
                # Update: fill in missing fields only
                updates = []
                params = []

                if rec["ig_handle"] and not existing.get("ig_handle"):
                    updates.append("ig_handle = ?")
                    params.append(rec["ig_handle"])
                    updates.append("status = ?")
                    params.append("ig_found")

                if rec["rector_name"] and not existing.get("rector_name"):
                    updates.append("rector_name = ?")
                    params.append(rec["rector_name"])

                if rec["province"] and not existing.get("province"):
                    updates.append("province = ?")
                    params.append(rec["province"])

                if rec["website"] and not existing.get("website"):
                    updates.append("website = ?")
                    params.append(rec["website"])

                if rec["pddikti_id"] and not existing.get("pddikti_id"):
                    updates.append("pddikti_id = ?")
                    params.append(rec["pddikti_id"])

                if updates:
                    params.append(existing["id"])
                    sql = f"UPDATE universities SET {', '.join(updates)} WHERE id = ?"
                    await db.execute(sql, params)
                    updated += 1
                else:
                    skipped += 1
            else:
                # Insert new
                await db.execute(
                    """INSERT INTO universities
                       (name, pddikti_id, province, website, ig_handle, ig_verified, rector_name, status, created_at)
                       VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)""",
                    (
                        rec["name"],
                        rec["pddikti_id"],
                        rec["province"],
                        rec["website"],
                        rec["ig_handle"],
                        rec["rector_name"],
                        rec["status"],
                        now,
                    ),
                )
                inserted += 1

        await db.commit()

    print(f"\n  {'='*40}")
    print(f"  Import complete!")
    print(f"    Inserted: {inserted}")
    print(f"    Updated:  {updated}")
    print(f"    Skipped:  {skipped} (no new data)")
    print(f"    Total:    {total}")
    print(f"  {'='*40}")

    return {
        "total": total,
        "with_ig": with_ig,
        "with_website": with_website,
        "with_rektor": with_rektor,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import Get-Contact-Auto university data into GetContactAIAgent"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be imported without writing to DB"
    )
    parser.add_argument(
        "--aktif-only", action="store_true",
        help="Only import universities with status_pt = 'Aktif'"
    )
    parser.add_argument(
        "--data-dir", type=str, default=None,
        help="Path to get-contact-auto data directory"
    )
    args = parser.parse_args()

    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = _find_data_dir()

    result = asyncio.run(run_import(
        data_dir=data_dir,
        dry_run=args.dry_run,
        aktif_only=args.aktif_only,
    ))

    return result


if __name__ == "__main__":
    main()
