"""
Data Fix: Reset universities stuck in 'ig_scraped' with 0 posts back to 'ig_found'.

Root cause: ig_post_scraper.py was marking universities as 'ig_scraped'
regardless of whether any posts were actually found. This left 1,698 universities
in 'ig_scraped' status with zero posts — effectively dead records that would
never be retried.

Fix: Set status back to 'ig_found' so Agent 2 (ig_post_scraper) can retry them.
These universities will be re-processed the next time the scheduler runs.

Usage:
    python scripts/fix_ig_scraped_zero_posts.py [--dry-run]

    --dry-run  Show what would be changed without modifying the database.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/getcontact.db")


def main():
    parser = argparse.ArgumentParser(description="Fix ig_scraped universities with 0 posts")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Find ig_scraped universities with 0 posts
    cur.execute("""
        SELECT u.id, u.name, u.ig_handle,
               (SELECT COUNT(*) FROM ig_posts WHERE university_id = u.id) as post_count
        FROM universities u
        WHERE u.status = 'ig_scraped'
          AND (SELECT COUNT(*) FROM ig_posts WHERE university_id = u.id) = 0
        ORDER BY u.id
    """)
    stuck = cur.fetchall()

    if not stuck:
        print("No stuck universities found — all ig_scraped universities have posts.")
        conn.close()
        return

    print(f"Found {len(stuck)} universities stuck in 'ig_scraped' with 0 posts\n")

    # Show sample
    print(f"{'ID':<6}  {'Name':<50}  {'ig_handle'}")
    print("-" * 90)
    for row in stuck[:20]:
        print(f"{row[0]:<6}  {str(row[1])[:48]:<50}  @{row[2]}")
    if len(stuck) > 20:
        print(f"  ... and {len(stuck) - 20} more")

    if args.dry_run:
        print(f"\n[DRY RUN] Would reset {len(stuck)} universities from 'ig_scraped' to 'ig_found'")
        conn.close()
        return

    # Apply the fix
    print(f"\nResetting {len(stuck)} universities to 'ig_found'...")
    cur.execute("""
        UPDATE universities
        SET status = 'ig_found'
        WHERE status = 'ig_scraped'
          AND (SELECT COUNT(*) FROM ig_posts WHERE university_id = universities.id) = 0
    """)
    affected = cur.rowcount
    conn.commit()
    conn.close()

    print(f"Done. {affected} universities reset to 'ig_found'.")
    print("Agent 2 (ig_post_scraper) will retry these on its next run.")


if __name__ == "__main__":
    main()
