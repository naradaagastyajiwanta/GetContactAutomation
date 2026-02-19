"""
Collect Indonesian universities from PDDIKTI API.
Usage:
    python scripts/collect_universities.py                    # All provinces
    python scripts/collect_universities.py --province "Bali"  # Single province
    python scripts/collect_universities.py --province "DKI Jakarta" --dry-run
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pddiktipy import api
from rapidfuzz import fuzz
from orchestrator.config import PROVINCES, INSTITUTION_PREFIXES, log
from orchestrator.db import init_db, add_university, get_all_universities


def is_duplicate(name: str, existing_names: list[str], threshold: int = 85) -> bool:
    """Check if university name is a fuzzy duplicate of any existing name."""
    name_lower = name.lower().strip()
    for existing in existing_names:
        if fuzz.ratio(name_lower, existing.lower().strip()) >= threshold:
            return True
    return False


async def search_pddikti(province: str | None = None) -> list[dict]:
    """Search PDDIKTI for universities, optionally filtered by province."""
    pddikti = api()
    all_results = []
    existing_names: list[str] = []
    duplicates_skipped = 0

    provinces = [province] if province else PROVINCES

    for prov in provinces:
        for prefix in INSTITUTION_PREFIXES:
            query = f"{prefix} {prov}"
            log.info(f"Searching PDDIKTI: '{query}'")
            try:
                results = pddikti.search_pt(query)
                if not results:
                    continue

                for pt in results:
                    # pddiktipy v2: fields are "nama", "kode", "id", "nama_singkat"
                    name = pt.get("nama", pt.get("nama_pt", "")).strip()
                    if not name:
                        continue

                    if is_duplicate(name, existing_names):
                        duplicates_skipped += 1
                        continue

                    existing_names.append(name)
                    all_results.append({
                        "name": name,
                        "pddikti_id": pt.get("kode") or pt.get("kode_pt") or pt.get("id"),
                        "province": prov,
                        "website": pt.get("website") or pt.get("laman"),
                    })

            except Exception as e:
                log.warning(f"Error searching '{query}': {e}")
                continue

    log.info(f"Found {len(all_results)} unique universities ({duplicates_skipped} duplicates skipped)")
    return all_results


async def main():
    parser = argparse.ArgumentParser(description="Collect universities from PDDIKTI")
    parser.add_argument("--province", type=str, help="Search single province")
    parser.add_argument("--dry-run", action="store_true", help="Print results without saving")
    args = parser.parse_args()

    await init_db()

    # Get existing universities to avoid re-adding
    existing = await get_all_universities(limit=10000)
    existing_names = [u["name"] for u in existing]
    log.info(f"Already have {len(existing)} universities in database")

    universities = await search_pddikti(args.province)

    if args.dry_run:
        for u in universities:
            print(f"  {u['name']} | {u['province']} | {u.get('website', 'N/A')}")
        print(f"\nTotal: {len(universities)} universities (dry run, not saved)")
        return

    added = 0
    for u in universities:
        if is_duplicate(u["name"], existing_names):
            continue
        try:
            await add_university(
                name=u["name"],
                pddikti_id=u.get("pddikti_id"),
                province=u.get("province"),
                website=u.get("website"),
            )
            existing_names.append(u["name"])
            added += 1
        except Exception as e:
            log.warning(f"Failed to add '{u['name']}': {e}")

    log.info(f"Added {added} new universities to database")


if __name__ == "__main__":
    asyncio.run(main())
