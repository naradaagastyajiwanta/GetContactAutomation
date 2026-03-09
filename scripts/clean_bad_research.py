"""Remove research records where university_name is a placeholder like 'University #XXXX'."""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'getcontact.db')
conn = sqlite3.connect(db_path)
rows = conn.execute(
    "SELECT id, schedule_id, university_name FROM audiensi_research WHERE university_name LIKE 'University #%'"
).fetchall()
print(f"Found {len(rows)} records to delete:")
for r in rows:
    print(f"  id={r[0]} schedule_id={r[1]} university_name={r[2]}")

deleted = conn.execute(
    "DELETE FROM audiensi_research WHERE university_name LIKE 'University #%'"
).rowcount
conn.commit()
conn.close()
print(f"Deleted {deleted} rows.")
