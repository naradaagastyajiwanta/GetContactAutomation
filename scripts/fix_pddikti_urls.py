"""Fix old PDDIKTI URLs in the database."""
import sqlite3

conn = sqlite3.connect("data/getcontact.db")

old = "pddikti.kemdikbud.go.id"
new = "pddikti.kemdiktisaintek.go.id"

c = conn.execute("SELECT COUNT(*) FROM crm_profile_sources WHERE source_url LIKE ?", (f"%{old}%",))
print(f"Rows with old URL: {c.fetchone()[0]}")

conn.execute(
    "UPDATE crm_profile_sources SET source_url = REPLACE(source_url, ?, ?) WHERE source_url LIKE ?",
    (old, new, f"%{old}%"),
)
conn.commit()

c2 = conn.execute("SELECT COUNT(*) FROM crm_profile_sources WHERE source_url LIKE ?", (f"%{old}%",))
print(f"After fix: {c2.fetchone()[0]}")

conn.close()
print("Done!")
