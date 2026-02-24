"""Check ig_handle distribution."""
import sqlite3
conn = sqlite3.connect("data/getcontact.db")
r = conn.execute("""
    SELECT
        CASE WHEN ig_handle IS NOT NULL AND ig_handle != '' THEN 'has_ig' ELSE 'no_ig' END AS grp,
        count(*)
    FROM universities
    GROUP BY grp
""").fetchall()
print("ig_handle distribution:", r)

r2 = conn.execute("""
    SELECT count(*) FROM universities
    WHERE ig_handle IS NOT NULL AND ig_handle != ''
      AND (bem_discovery_status IS NULL OR bem_discovery_status = 'pending')
      AND (enabled = 1 OR enabled IS NULL)
""").fetchall()
print("Eligible for BEM discovery (current query):", r2[0][0])

r3 = conn.execute("""
    SELECT count(*) FROM universities
    WHERE (bem_discovery_status IS NULL OR bem_discovery_status = 'pending')
      AND (enabled = 1 OR enabled IS NULL)
""").fetchall()
print("Eligible without ig_handle requirement:", r3[0][0])
conn.close()
