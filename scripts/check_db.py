import sqlite3
db=sqlite3.connect('data/getcontact.db')
db.row_factory = sqlite3.Row
cur=db.cursor()
cur.execute('SELECT communication_style, recent_topics, social_behavior_insights, personality_summary FROM crm_pic_profiles WHERE request_id=5 ORDER BY id DESC LIMIT 1')
row=cur.fetchone()
if row:
    for k in row.keys():
        print(f'\n--- {k.upper()} ---')
        print(row[k])
else:
    print('Data not found')
