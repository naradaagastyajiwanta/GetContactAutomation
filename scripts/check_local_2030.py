import pymysql
import sys

try:
    conn = pymysql.connect(
        host='127.0.0.1',
        port=3307,
        user='root',
        password='',
        database='dmsedu_db',
        charset='utf8mb4'
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
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
