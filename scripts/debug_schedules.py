import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def check():
    from orchestrator.dms_mysql import init_dms_pool, get_upcoming_audiensi_schedules, close_dms_pool
    pool = await init_dms_pool()
    print("Pool:", pool)
    schedules = await get_upcoming_audiensi_schedules(days_ahead=365, include_past_days=365)
    print(f"Total schedules: {len(schedules)}")
    for s in schedules[:10]:
        sid = s.get("id")
        date = s.get("jadwal_audiensi")
        name = s.get("nama_universitas")
        print(f"  #{sid} | {date} | {name}")
    if not schedules:
        print("NO SCHEDULES FOUND!")
    await close_dms_pool()

asyncio.run(check())
