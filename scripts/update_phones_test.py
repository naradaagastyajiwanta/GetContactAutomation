"""One-off script: keep 1 contact per university, update all phone_numbers to test number."""
import sqlite3

DB = "data/getcontact.db"
TEST_NUMBER = "6287811152506"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# For each university that has >1 contact, delete all but the one with lowest id
cur.execute("""
    DELETE FROM ig_contacts
    WHERE id NOT IN (
        SELECT MIN(id) FROM ig_contacts GROUP BY university_id
    )
""")
deleted = cur.rowcount
print(f"Deleted {deleted} duplicate contacts (kept 1 per university)")

# Now update all remaining to the test number
cur.execute("UPDATE ig_contacts SET phone_number = ?", (TEST_NUMBER,))
updated = cur.rowcount
print(f"Updated {updated} contacts to {TEST_NUMBER}")

conn.commit()

# Verify
rows = cur.execute("SELECT id, university_id, phone_number, contact_name FROM ig_contacts").fetchall()
print(f"\nRemaining {len(rows)} contacts:")
for r in rows:
    print(f"  id={r[0]} univ={r[1]} phone={r[2]} name={r[3]}")

conn.close()
