import sqlite3
db = sqlite3.connect('data/getcontact.db')
db.execute("UPDATE crm_requests SET status='pending' WHERE id=5")
db.commit()
db.close()
