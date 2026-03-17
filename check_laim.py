import sqlite3
db=sqlite3.connect('data/getcontact.db')
cur=db.cursor()
cur.execute("SELECT request_id, full_name, linkedin_url FROM crm_pic_profiles WHERE linkedin_url LIKE '%laimer%'")
print(cur.fetchall())
