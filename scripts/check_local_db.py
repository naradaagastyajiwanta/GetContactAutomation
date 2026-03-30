"""Check local dmsedu_db. Requires env vars (defaults for local dev):
DMS_LOCAL_HOST, DMS_LOCAL_PORT, DMS_LOCAL_USER, DMS_LOCAL_PASSWORD, DMS_LOCAL_DATABASE
"""
import os
import mariadb

conn = mariadb.connect(
    host=os.environ.get("DMS_LOCAL_HOST", "localhost"),
    port=int(os.environ.get("DMS_LOCAL_PORT", 3307)),
    user=os.environ.get("DMS_LOCAL_USER", "root"),
    password=os.environ.get("DMS_LOCAL_PASSWORD", ""),
    database=os.environ.get("DMS_LOCAL_DATABASE", "dmsedu_db"),
)
cur = conn.cursor(dictionary=True)
cur.execute("SELECT id, id_univ, jadwal_audiensi, jam_audensi FROM schedule_follow_up ORDER BY jadwal_audiensi DESC LIMIT 15")
for r in cur.fetchall():
    print(f"  #{r['id']} | {r['jadwal_audiensi']} | {r['jam_audensi']}")
conn.close()
