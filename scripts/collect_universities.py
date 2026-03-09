"""
Collect Indonesian universities from PDDIKTI API.
Usage:
    python scripts/collect_universities.py                    # All provinces
    python scripts/collect_universities.py --province "Bali"  # Single province
    python scripts/collect_universities.py --province "DKI Jakarta" --dry-run
"""
import argparse
import asyncio
import re
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


# Province keyword variants for matching (handles abbreviations and alternate names)
_PROVINCE_KEYWORDS: dict[str, list[str]] = {
    "DKI Jakarta": ["Jakarta"],
    "DI Yogyakarta": ["Yogyakarta", "Jogja", "Jogjakarta"],
    "Kepulauan Bangka Belitung": ["Bangka", "Belitung"],
    "Kepulauan Riau": ["Kepri", "Kepulauan Riau"],
    "Nusa Tenggara Barat": ["NTB", "Mataram", "Lombok"],
    "Nusa Tenggara Timur": ["NTT", "Kupang", "Flores"],
    "Kalimantan Utara": ["Kaltara"],
    "Kalimantan Timur": ["Kaltim"],
    "Kalimantan Selatan": ["Kalsel"],
    "Kalimantan Tengah": ["Kalteng"],
    "Kalimantan Barat": ["Kalbar"],
    "Sulawesi Utara": ["Sulut"],
    "Sulawesi Selatan": ["Sulsel", "Makassar", "Ujung Pandang"],
    "Sulawesi Tengah": ["Sulteng"],
    "Sulawesi Tenggara": ["Sultra", "Kendari"],
    "Sulawesi Barat": ["Sulbar"],
    "Sumatera Utara": ["Sumut", "Medan"],
    "Sumatera Barat": ["Sumbar", "Padang"],
    "Sumatera Selatan": ["Sumsel", "Palembang"],
    "Papua Barat": ["Papua Barat"],
}


def _matches_province(uni_name: str, province: str) -> bool:
    """Check if a university name plausibly belongs to the given province.

    Uses word-boundary matching so 'BALE' won't match province 'Bali',
    but 'BALI DWIPA' will.
    """
    name_upper = uni_name.upper()

    # Build list of keywords to check: the province itself + any variants
    keywords = [province]
    keywords.extend(_PROVINCE_KEYWORDS.get(province, []))

    for kw in keywords:
        # Word-boundary match (case insensitive)
        if re.search(r'\b' + re.escape(kw.upper()) + r'\b', name_upper):
            return True

    return False


def _sanitize_website(url: str) -> str | None:
    """Clean up and validate a website URL from PDDIKTI.

    Filters out garbage like 'https:////http:', 'https://000', 'https://-',
    URLs with spaces, etc.
    """
    if not url:
        return None

    url = url.strip()

    # Add scheme if missing
    if not url.startswith("http"):
        url = f"https://{url}"

    # Filter obviously invalid URLs
    invalid_patterns = [
        "https://-", "http://-",
        "https://000", "http://000",
        "https:////", "http:////",
        "https://wwww.",  # quadruple w
    ]
    for pat in invalid_patterns:
        if url.startswith(pat):
            return None

    # Must contain a dot (domain) after the scheme
    after_scheme = url.split("://", 1)[1] if "://" in url else url
    if "." not in after_scheme:
        return None

    # Reject URLs with spaces in the domain
    domain_part = after_scheme.split("/")[0]
    if " " in domain_part:
        return None

    return url


async def _fetch_pddikti_detail(pt_id: str) -> dict | None:
    """Fetch full university detail from PDDIKTI detail API."""
    import httpx

    pddikti_base = "https://api-pddikti.kemdiktisaintek.go.id"
    headers = {
        "Accept": "application/json",
        "Origin": "https://pddikti.kemdiktisaintek.go.id",
        "Referer": "https://pddikti.kemdiktisaintek.go.id/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        try:
            resp = await client.get(f"{pddikti_base}/pt/detail/{pt_id}")
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            log.warning(f"Failed to fetch PDDIKTI detail for {pt_id}: {e}")
    return None


async def search_pddikti(
    province: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Search PDDIKTI for universities, optionally filtered by province and limit.

    When limit is set, stops collecting after reaching that many results.
    Also fetches full detail (website) from PDDIKTI detail API for each university.
    """
    pddikti = api()
    all_results = []
    existing_names: list[str] = []
    duplicates_skipped = 0
    province_filtered = 0

    def _reached_limit() -> bool:
        return limit is not None and len(all_results) >= limit

    provinces = [province] if province else PROVINCES
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 3  # Stop if API fails this many times in a row

    for prov in provinces:
        if _reached_limit():
            break
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            log.warning(
                "PDDIKTI API failed %d times in a row — API likely down, stopping search",
                consecutive_errors,
            )
            break
        for prefix in INSTITUTION_PREFIXES:
            if _reached_limit():
                break
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                break
            query = f"{prefix} {prov}"
            log.info(f"Searching PDDIKTI: '{query}'")
            try:
                results = pddikti.search_pt(query)
                if results is None:
                    # pddiktipy caught an API error internally and returned None
                    consecutive_errors += 1
                    log.warning(
                        "PDDIKTI API error for '%s' (consecutive errors: %d/%d)",
                        query, consecutive_errors, MAX_CONSECUTIVE_ERRORS,
                    )
                    continue
                consecutive_errors = 0  # Reset only on genuine success
                if not results:
                    continue

                for pt in results:
                    if _reached_limit():
                        break

                    # pddiktipy v2: fields are "nama", "kode", "id", "nama_singkat"
                    name = pt.get("nama", pt.get("nama_pt", "")).strip()
                    if not name:
                        continue

                    # Filter: only keep results that match the searched province
                    if not _matches_province(name, prov):
                        province_filtered += 1
                        log.debug(f"Filtered out '{name}' — does not match province '{prov}'")
                        continue

                    if is_duplicate(name, existing_names):
                        duplicates_skipped += 1
                        continue

                    existing_names.append(name)

                    # Get PDDIKTI ID for detail lookup
                    pt_id = pt.get("id") or pt.get("kode") or pt.get("kode_pt")
                    pddikti_code = pt.get("kode") or pt.get("kode_pt") or pt.get("id")

                    # Use website from search result as fallback
                    website = pt.get("website") or pt.get("laman") or ""

                    # Fetch full detail from PDDIKTI detail API
                    if pt_id:
                        detail = await _fetch_pddikti_detail(pt_id)
                        if detail:
                            detail_website = (detail.get("website") or "").strip()
                            if detail_website:
                                if not detail_website.startswith("http"):
                                    detail_website = f"https://{detail_website}"
                                website = detail_website
                            log.info(
                                f"[PDDIKTI Detail] {name}: website={website}"
                            )
                        await asyncio.sleep(0.3)  # rate-limit detail requests

                    # Sanitize website URL
                    website = _sanitize_website(website) if website else None

                    all_results.append({
                        "name": name,
                        "pddikti_id": pddikti_code,
                        "province": prov,
                        "website": website,
                        "student_count": None,  # TODO: Extract from PDDIKTI detail API when available
                    })

            except Exception as e:
                consecutive_errors += 1
                log.warning(
                    f"Error searching '{query}': {e} "
                    f"(consecutive errors: {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})"
                )
                continue

    log.info(
        f"Found {len(all_results)} unique universities "
        f"({duplicates_skipped} duplicates skipped, {province_filtered} filtered by province)"
        + (f", limit={limit}" if limit else "")
    )
    return all_results


async def main():
    parser = argparse.ArgumentParser(description="Collect universities from PDDIKTI")
    parser.add_argument("--province", type=str, help="Search single province")
    parser.add_argument("--limit", type=int, help="Max number of universities to collect")
    parser.add_argument("--dry-run", action="store_true", help="Print results without saving")
    args = parser.parse_args()

    await init_db()

    # Get existing universities to avoid re-adding
    existing = await get_all_universities(limit=10000)
    existing_names = [u["name"] for u in existing]
    log.info(f"Already have {len(existing)} universities in database")

    universities = await search_pddikti(args.province, limit=args.limit)

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
