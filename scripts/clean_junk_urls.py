"""Clean junk URLs from existing crm_profile_sources rows."""
import re
import sqlite3
from urllib.parse import urlparse

JUNK_DOMAINS = {
    "translate.google.com",
    "translate.google.co.id",
    "primevideo.com",
    "www.primevideo.com",
    "target.com",
    "www.target.com",
    "wa.me",
}

JUNK_RE = re.compile(
    r"vertexaisearch\.cloud\.google\.com"
    r"|accounts\.google\.com"
    r"|play\.google\.com/store",
    re.IGNORECASE,
)


def is_useful(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    if host in JUNK_DOMAINS:
        return False
    if JUNK_RE.search(url):
        return False
    return True


conn = sqlite3.connect("/app/data/getcontact.db")
rows = conn.execute(
    "SELECT id, source_url FROM crm_profile_sources WHERE source_url IS NOT NULL AND source_url != ''"
).fetchall()

updated = 0
for row_id, source_url in rows:
    urls = [u.strip() for u in source_url.split(", ")]
    clean = [u for u in urls if is_useful(u)]
    new_val = ", ".join(clean) if clean else None
    if new_val != source_url:
        conn.execute("UPDATE crm_profile_sources SET source_url = ? WHERE id = ?", (new_val, row_id))
        updated += 1
        print(f"  Row {row_id}: {len(urls)} -> {len(clean)} URLs")

conn.commit()
conn.close()
print(f"\nDone! Updated {updated} rows.")
