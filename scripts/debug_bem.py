"""Debug BEM discovery results."""
import sqlite3

conn = sqlite3.connect("data/getcontact.db")
conn.row_factory = sqlite3.Row

# Check which unis got no_following
print("=== Universities with no_following ===")
rows = conn.execute(
    "SELECT id, name, ig_handle, bem_discovery_status FROM universities WHERE bem_discovery_status='no_following' LIMIT 10"
).fetchall()
for r in rows:
    print(f"  ID={r['id']} | {r['name']} | @{r['ig_handle']} | {r['bem_discovery_status']}")

# Check related_igs table
print("\n=== Related IGs ===")
try:
    igs = conn.execute("SELECT * FROM related_igs ORDER BY id DESC LIMIT 10").fetchall()
    for r in igs:
        print(f"  {dict(r)}")
    if not igs:
        print("  (empty)")
except Exception as e:
    print(f"  Error: {e}")

# Check BEM status distribution
print("\n=== BEM Status Distribution ===")
rows = conn.execute(
    "SELECT bem_discovery_status, COUNT(*) as cnt FROM universities GROUP BY bem_discovery_status"
).fetchall()
for r in rows:
    print(f"  {r['bem_discovery_status']}: {r['cnt']}")

conn.close()
