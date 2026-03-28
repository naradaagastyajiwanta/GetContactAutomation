"""Check local dmsedu_db for 2030+ schedules. Requires env vars:
DMS_LOCAL_HOST, DMS_LOCAL_PORT, DMS_LOCAL_USER, DMS_LOCAL_PASSWORD, DMS_LOCAL_DATABASE
"""
import os
import sys
import pymysql

conn = pymysql.connect(
    host=os.environ.get("DMS_LOCAL_HOST", "127.0.0.1"),
    port=int(os.environ.get("DMS_LOCAL_PORT", 3307)),
    user=os.environ.get("DMS_LOCAL_USER", "root"),
    password=os.environ.get("DMS_LOCAL_PASSWORD", ""),
    database=os.environ.get("DMS_LOCAL_DATABASE", "dmsedu_db"),
    charset='utf8mb4',
)
cur = conn.cursor(pymysql.cursors.DictCursor)

print("=== schedule_follow_up (2030+) ===")
cur.execute("SELECT id, id_univ, jadwal_audiensi, est_audiens FROM schedule_follow_up WHERE jadwal_audiensi >= '2030-01-01' ORDER BY jadwal_audiensi")
rows = cur.fetchall()
print(f"Count: {len(rows)}")
for r in rows:
    print(f"  ID={r['id']} univ={r['id_univ']} date={r['jadwal_audiensi']} audiens={r['est_audiens']}")

print("\n=== request_surat_audiensi_detail (2030+) ===")
cur.execute("""
    SELECT d.id, d.id_univ, d.tanggal_audiensi, d.status_surat, d.nomor_surat, d.nama_penerima, u.universitas
    FROM request_surat_audiensi_detail d
    LEFT JOIN universitas u ON d.id_univ = u.id_univ
    WHERE d.tanggal_audiensi >= '2030-01-01'
    ORDER BY d.tanggal_audiensi
""")
rows = cur.fetchall()
print(f"Count: {len(rows)}")
for r in rows:
    print(f"  ID={r['id']} univ={r['id_univ']} date={r['tanggal_audiensi']} status={r['status_surat']} surat={r['nomor_surat']} univ={r['universitas']}")

conn.close()
