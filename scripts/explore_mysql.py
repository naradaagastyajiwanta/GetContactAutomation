"""Temporary script to explore dev staging MySQL database."""
import pymysql
import json

conn = pymysql.connect(
    host='35.219.13.27',
    user='dev-staging',
    password='17H1aXMqv6EavBQ0Dz',
    database='dev_staging_dmsedu',
    port=3306,
    connect_timeout=10
)
cursor = conn.cursor(pymysql.cursors.DictCursor)

def dump(rows):
    for row in rows:
        for k, v in row.items():
            row[k] = str(v) if v else None
        print(json.dumps(row, ensure_ascii=False))

print("=== Recent schedule_follow_up (upcoming) ===")
cursor.execute("""
    SELECT sf.id, sf.id_univ, u.universitas, sf.jadwal_audiensi, sf.jam_audensi,
           sf.type_meeting, sf.action, sf.status_approval, sf.link_zoom
    FROM schedule_follow_up sf
    LEFT JOIN universitas u ON sf.id_univ = u.id_univ
    ORDER BY sf.jadwal_audiensi DESC
    LIMIT 10
""")
dump(cursor.fetchall())

print("\n=== Recent audiensi entries ===")
cursor.execute("""
    SELECT id, id_univ, nama_kampus, status, tgl_audiensi, jam_audiensi,
           pic_kampus, kontak_pic, kondisi_folowup, tanggal_terakhir_follow_up
    FROM audiensi
    ORDER BY id DESC
    LIMIT 10
""")
dump(cursor.fetchall())

print("\n=== Upcoming meetings ===")
cursor.execute("""
    SELECT m.id, m.meeting_id, m.tanggal_meeting, m.jam_meeting, m.topic,
           m.lembaga, m.link_zoom, m.passcode
    FROM meeting_audiensi m
    ORDER BY m.tanggal_meeting DESC
    LIMIT 10
""")
dump(cursor.fetchall())

print("\n=== Follow up logs (recent) ===")
cursor.execute("""
    SELECT f.id, f.id_univ, u.universitas, f.metode_followup, f.hasil_followup,
           f.catatan, f.tanggal_follow_up, f.next_follow_up_date
    FROM follow_up_tbls f
    LEFT JOIN universitas u ON f.id_univ = u.id_univ
    ORDER BY f.tanggal_follow_up DESC
    LIMIT 5
""")
dump(cursor.fetchall())

print("\n=== schedule_audiensi sample ===")
cursor.execute("""
    SELECT sa.*, u.universitas
    FROM schedule_audiensi sa
    LEFT JOIN schedule_follow_up sf ON sa.id_followup = sf.id
    LEFT JOIN universitas u ON sf.id_univ = u.id_univ
    ORDER BY sa.id DESC
    LIMIT 5
""")
dump(cursor.fetchall())

print("\n=== kontak_auto sample (recent) ===")
cursor.execute("""
    SELECT id, id_univ, universitas, instagram_username, pic, jabatan,
           no_hp, source_type, created_at
    FROM kontak_auto
    ORDER BY created_at DESC
    LIMIT 5
""")
dump(cursor.fetchall())

print("\n=== kontak_universitas sample ===")
cursor.execute("""
    SELECT ku.id, ku.id_univ, u.universitas, ku.pic, ku.no_hppickampus,
           ku.jabatan, ku.status, ku.catatan
    FROM kontak_universitas ku
    LEFT JOIN universitas u ON ku.id_univ = u.id_univ
    ORDER BY ku.id DESC
    LIMIT 5
""")
dump(cursor.fetchall())

conn.close()
