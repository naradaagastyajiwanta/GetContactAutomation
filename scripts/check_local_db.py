import mariadb

conn = mariadb.connect(host='localhost', port=3307, user='root', password='', database='dmsedu_db')
cur = conn.cursor(dictionary=True)
cur.execute('SELECT id, id_univ, jadwal_audiensi, jam_audensi FROM schedule_follow_up ORDER BY jadwal_audiensi DESC LIMIT 15')
for r in cur.fetchall():
    print(f"  #{r['id']} | {r['jadwal_audiensi']} | {r['jam_audensi']}")
conn.close()
