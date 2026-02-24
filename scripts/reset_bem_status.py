"""Reset BEM discovery status back to pending for retesting."""
import sqlite3

conn = sqlite3.connect("data/getcontact.db")
# Show current distribution
rows = conn.execute("SELECT bem_discovery_status, count(*) FROM universities GROUP BY bem_discovery_status").fetchall()
print("Current distribution:", rows)

# Reset all non-pending statuses
conn.execute("UPDATE universities SET bem_discovery_status = 'pending' WHERE bem_discovery_status != 'pending'")
conn.commit()
print(f"Reset {conn.total_changes} rows back to pending")
conn.close()
