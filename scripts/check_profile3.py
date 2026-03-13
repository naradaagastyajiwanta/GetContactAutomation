import sqlite3
conn = sqlite3.connect('/app/data/getcontact.db')
rows = conn.execute('SELECT field_name, source_url FROM crm_profile_sources WHERE profile_id = 3 AND source_url IS NOT NULL ORDER BY id').fetchall()
for r in rows:
    urls = [u for u in r[1].split(', ') if u.startswith('http')]
    print(f'{r[0]}: {len(urls)} URLs')
conn.close()
