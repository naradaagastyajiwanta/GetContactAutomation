"""
Export university contact results from SQLite to CSV or Google Sheets.
Usage:
    python scripts/export_results.py --format csv --output results.csv
    python scripts/export_results.py --format csv                         # defaults to data/results.csv
    python scripts/export_results.py --format gsheets --sheet-name "Kontak Universitas"
"""
import argparse
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.config import DATA_DIR, log
from orchestrator.db import init_db, get_db


async def fetch_export_data() -> list[dict]:
    """Fetch all universities with their contact data."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT
                u.id,
                u.name,
                u.province,
                u.website,
                u.ig_handle,
                u.secretariat_phone,
                u.status,
                u.created_at,
                (SELECT COUNT(*) FROM ig_contacts ic WHERE ic.university_id = u.id) as ig_contacts_count,
                (SELECT c.state FROM conversations c WHERE c.university_id = u.id ORDER BY c.created_at DESC LIMIT 1) as last_conv_state,
                (SELECT c.extracted_number FROM conversations c WHERE c.university_id = u.id AND c.extracted_number IS NOT NULL LIMIT 1) as conv_extracted_number
            FROM universities u
            ORDER BY u.province, u.name
            """
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


def export_csv(data: list[dict], output_path: str):
    """Export data to CSV file."""
    if not data:
        print("No data to export.")
        return

    fieldnames = [
        "id", "name", "province", "website", "ig_handle",
        "secretariat_phone", "status", "ig_contacts_count",
        "last_conv_state", "conv_extracted_number", "created_at",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)

    print(f"Exported {len(data)} rows to {output_path}")


def export_gsheets(data: list[dict], sheet_name: str):
    """Export data to Google Sheets using gspread."""
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
    except ImportError:
        print("Error: gspread and oauth2client are required for Google Sheets export.")
        print("Install with: pip install gspread oauth2client")
        return

    credentials_path = Path("credentials.json")
    if not credentials_path.exists():
        print("Error: credentials.json not found in project root.")
        print("Download service account credentials from Google Cloud Console.")
        return

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(str(credentials_path), scope)
    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open(sheet_name)
        worksheet = spreadsheet.sheet1
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(sheet_name)
        worksheet = spreadsheet.sheet1
        print(f"Created new spreadsheet: {sheet_name}")

    headers = [
        "ID", "Name", "Province", "Website", "IG Handle",
        "Secretariat Phone", "Status", "IG Contacts Count",
        "Last Conv State", "Extracted Number", "Created At",
    ]
    worksheet.clear()
    worksheet.append_row(headers)

    rows = []
    for d in data:
        rows.append([
            d.get("id", ""),
            d.get("name", ""),
            d.get("province", ""),
            d.get("website", ""),
            d.get("ig_handle", ""),
            d.get("secretariat_phone", ""),
            d.get("status", ""),
            d.get("ig_contacts_count", 0),
            d.get("last_conv_state", ""),
            d.get("conv_extracted_number", ""),
            d.get("created_at", ""),
        ])

    if rows:
        worksheet.append_rows(rows)

    print(f"Exported {len(data)} rows to Google Sheet: {sheet_name}")
    print(f"URL: {spreadsheet.url}")


async def main():
    parser = argparse.ArgumentParser(description="Export university contact results")
    parser.add_argument(
        "--format", choices=["csv", "gsheets"], default="csv",
        help="Export format (default: csv)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output file path for CSV (default: data/results.csv)",
    )
    parser.add_argument(
        "--sheet-name", type=str, default="Kontak Universitas",
        help="Google Sheets name (default: Kontak Universitas)",
    )
    parser.add_argument(
        "--status", type=str, default=None,
        help="Filter by status (e.g., got_number)",
    )
    args = parser.parse_args()

    await init_db()
    data = await fetch_export_data()

    if args.status:
        data = [d for d in data if d.get("status") == args.status]

    print(f"Found {len(data)} universities")

    # Print summary
    status_counts: dict[str, int] = {}
    for d in data:
        s = d.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
    print("Status breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    print()

    if args.format == "csv":
        output_path = args.output or str(DATA_DIR / "results.csv")
        export_csv(data, output_path)
    elif args.format == "gsheets":
        export_gsheets(data, args.sheet_name)


if __name__ == "__main__":
    asyncio.run(main())
