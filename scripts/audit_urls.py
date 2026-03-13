"""Audit all source URLs in the database."""
import sqlite3

conn = sqlite3.connect("/app/data/getcontact.db")
rows = conn.execute(
    "SELECT DISTINCT source_url FROM crm_profile_sources WHERE source_url IS NOT NULL AND source_url != ''"
).fetchall()

all_urls = set()
for r in rows:
    for u in r[0].split(", "):
        u = u.strip()
        if u.startswith("http"):
            all_urls.add(u)

for u in sorted(all_urls):
    print(u[:150])

conn.close()
