import sqlite3
conn = sqlite3.connect('/app/data/getcontact.db')
cur = conn.cursor()
cur.execute('SELECT id, name, status, total_recipients, sent_count, failed_count FROM email_blast_campaigns WHERE id=16')
print('Campaign:', cur.fetchone())
cur.execute("SELECT status, COUNT(*) FROM email_blast_recipients WHERE campaign_id=16 GROUP BY status")
print('Actual counts:')
for r in cur.fetchall():
    print(' ', r)
cur.execute("SELECT error_message, COUNT(*) FROM email_blast_recipients WHERE campaign_id=16 AND status='failed' GROUP BY error_message")
print('Errors:')
for r in cur.fetchall():
    print(' ', r)
conn.close()
