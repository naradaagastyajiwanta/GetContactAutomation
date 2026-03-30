import asyncio, os, sys
os.environ.setdefault("DATABASE_PATH", "data/getcontact.db")

async def test():
    import sqlite3
    conn = sqlite3.connect('data/getcontact.db')
    conn.row_factory = sqlite3.Row
    row = conn.cursor().execute('SELECT id as request_id, university_id, pic_name as full_name FROM crm_requests WHERE id=5').fetchone()
    if not row:
        print("Not found")
        return
    req_id = row['request_id']
    uni_id = row['university_id']

    # Delete existing
    conn.cursor().execute("DELETE FROM crm_pic_profiles WHERE request_id=5")
    conn.commit()

    print(f"Deleted profile 5. Running CRM Graph for Narada Agastya Jiwanta...")
    
    from orchestrator.db import init_db
    from orchestrator.crm.graph import run_pic_profiling
    await init_db()
    
    result = await run_pic_profiling(req_id)
    print("Done")

if __name__ == "__main__":
    asyncio.run(test())