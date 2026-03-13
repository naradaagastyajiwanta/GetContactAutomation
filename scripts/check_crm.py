import asyncio
from orchestrator.db import get_db

async def check():
    async with get_db() as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'crm%'")
        tables = await cursor.fetchall()
        for t in tables:
            print("Table:", dict(t))
        
        # Check latest profile for request 2
        cursor = await db.execute("SELECT id, request_id, full_name, overall_confidence, fields_found, fields_total, created_at FROM crm_pic_profiles WHERE request_id=2 ORDER BY id DESC LIMIT 5")
        rows = await cursor.fetchall()
        for r in rows:
            print("Profile:", dict(r))
        
        # Check runs
        cursor = await db.execute("SELECT * FROM crm_profile_runs WHERE request_id=2 ORDER BY id DESC LIMIT 5")
        rows = await cursor.fetchall()
        for r in rows:
            print("Run:", dict(r))

asyncio.run(check())
