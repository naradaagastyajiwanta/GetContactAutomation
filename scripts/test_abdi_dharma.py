import asyncio, os, sys
os.environ.setdefault("DATABASE_PATH", "data/getcontact.db")

async def test():
    # Fetch existing request to get university_id or just mock
    PIC_NAME = "Abdi Dharma"
    UNI_NAME = "Universitas Prima Indonesia"

    import sqlite3
    conn = sqlite3.connect('data/getcontact.db')
    conn.row_factory = sqlite3.Row
    row = conn.cursor().execute('SELECT request_id, university_id, full_name FROM crm_pic_profiles WHERE id=5').fetchone()
    req_id = row['request_id'] if row else 3
    uni_id = row['university_id'] if row else None

    # We will just run the graph to see what it generates, no need to delete but maybe we can update it or just insert anew. Let's delete and reinsert
    
    conn.cursor().execute("DELETE FROM crm_pic_profiles WHERE id=5")
    conn.commit()

    print(f"Deleted profile 5. Running CRM Graph for {PIC_NAME}...")
    from orchestrator.db import init_db
    from orchestrator.crm.graph import run_pic_profiling
    
    await init_db()
    
    result = await run_pic_profiling(req_id)
    print("Done")

if __name__ == "__main__":
    asyncio.run(test())
