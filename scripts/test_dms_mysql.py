"""Quick test for DMS MySQL integration."""
import asyncio
import sys
import os
import json

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()


async def test():
    # Initialize config
    from orchestrator.config import cfg
    
    print("=== DMS MySQL Config ===")
    print(f"Host: {cfg.get('DMS_MYSQL_HOST')}")
    print(f"Port: {cfg.get('DMS_MYSQL_PORT')}")
    print(f"User: {cfg.get('DMS_MYSQL_USER')}")
    print(f"Database: {cfg.get('DMS_MYSQL_DATABASE')}")
    print(f"Sync Enabled: {cfg.get('DMS_SYNC_ENABLED')}")
    print(f"Contact Sync: {cfg.get('DMS_CONTACT_SYNC_ENABLED')}")
    print(f"Reminder: {cfg.get('DMS_REMINDER_ENABLED')}")
    print()

    from orchestrator.dms_mysql import (
        init_dms_pool,
        check_dms_connection,
        get_dms_audiensi_stats,
        get_upcoming_audiensi_schedules,
        get_today_audiensi_schedules,
        get_recent_follow_ups,
        get_upcoming_meetings,
        search_dms_universities,
        close_dms_pool,
    )

    # 1. Init pool
    print("=== 1. Initialize Pool ===")
    pool = await init_dms_pool()
    print(f"Pool created: {pool is not None}")

    # 2. Health check
    print("\n=== 2. Health Check ===")
    health = await check_dms_connection()
    print(json.dumps(health, indent=2))

    # 3. Stats
    print("\n=== 3. DMS Audiensi Stats ===")
    stats = await get_dms_audiensi_stats()
    print(json.dumps(stats, indent=2))

    # 4. Upcoming schedules
    print("\n=== 4. Upcoming Schedules (14 days) ===")
    schedules = await get_upcoming_audiensi_schedules(days_ahead=14)
    print(f"Total: {len(schedules)}")
    for s in schedules[:5]:
        print(f"  {s['jadwal_audiensi']} {s.get('jam_audensi', '?')} - {s.get('nama_universitas', '?')}")

    # 5. Today's schedules
    print("\n=== 5. Today's Schedules ===")
    today = await get_today_audiensi_schedules()
    print(f"Total today: {len(today)}")
    for s in today:
        print(f"  {s.get('jam_audensi', '?')} - {s.get('nama_universitas', '?')}")

    # 6. Recent follow-ups
    print("\n=== 6. Recent Follow-ups (last 5) ===")
    followups = await get_recent_follow_ups(limit=5)
    for f in followups:
        print(f"  {f.get('tanggal_follow_up', '?')} - {f.get('nama_universitas', '?')} - {f.get('catatan', '')[:60]}")

    # 7. Search university
    print("\n=== 7. Search University 'Telkom' ===")
    results = await search_dms_universities("Telkom")
    for r in results:
        print(f"  [{r['id_univ']}] {r['universitas']}")

    # 8. Upcoming meetings
    print("\n=== 8. Upcoming Meetings (14 days) ===")
    meetings = await get_upcoming_meetings(14)
    print(f"Total: {len(meetings)}")
    for m in meetings[:5]:
        print(f"  {m.get('tanggal_meeting', '?')} - {m.get('topic', '?')}")

    # Cleanup
    await close_dms_pool()
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(test())
