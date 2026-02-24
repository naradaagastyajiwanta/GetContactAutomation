"""Quick DB table check."""
import sqlite3
conn = sqlite3.connect("data/getcontact.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("All tables:")
for t in tables:
    print(f"  {t[0]}")
print()
# Check if university_related_igs exists
exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='university_related_igs'").fetchall()
print(f"university_related_igs exists: {bool(exists)}")
conn.close()
