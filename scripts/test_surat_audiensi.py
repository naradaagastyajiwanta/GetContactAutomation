"""
Quick test: verify that get_upcoming_audiensi_schedules now returns
data from both schedule_follow_up and request_surat_audiensi_detail.
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

async def main():
    from orchestrator.dms_mysql import (
        init_dms_pool,
        get_upcoming_audiensi_schedules,
        get_today_audiensi_schedules,
        get_dms_audiensi_stats,
        get_audiensi_schedule_by_id,
        close_dms_pool,
    )

    pool = await init_dms_pool()
    if not pool:
        print("ERROR: Could not connect to DMS MySQL")
        return

    print("=== Testing UNION query (365 days ahead, 365 past) ===")
    schedules = await get_upcoming_audiensi_schedules(days_ahead=365, include_past_days=365)
    print(f"Total schedules: {len(schedules)}")

    # Count by source
    sources = {}
    for s in schedules:
        src = s.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    print(f"By source: {sources}")

    # Show upcoming (future)
    from datetime import date
    today = date.today().isoformat()
    upcoming = [s for s in schedules if (s.get("jadwal_audiensi") or "")[:10] >= today]
    print(f"\nUpcoming (>= {today}): {len(upcoming)}")
    for s in upcoming[:10]:
        print(f"  [{s['source']}] #{s['id']} | {s.get('nama_universitas') or 'Univ #' + str(s['id_univ'])} | "
              f"{s['jadwal_audiensi']} | status={s.get('status_approval')} | "
              f"unit_org={s.get('unit_organisasi', '-')}")

    print("\n=== Testing today's schedules ===")
    today_schedules = await get_today_audiensi_schedules()
    print(f"Today: {len(today_schedules)}")

    print("\n=== Testing stats ===")
    stats = await get_dms_audiensi_stats()
    print(f"Stats: total={stats['total_schedules']}, upcoming={stats['upcoming_schedules']}, "
          f"today={stats['today_schedules']}")
    if stats.get("surat_audiensi_stats"):
        print(f"Surat status breakdown: {stats['surat_audiensi_stats']}")

    # Test detail for a surat audiensi
    if upcoming:
        surat_items = [s for s in upcoming if s["source"] == "surat_audiensi"]
        if surat_items:
            test_id = surat_items[0]["id"]
            print(f"\n=== Testing detail for surat_audiensi #{test_id} ===")
            detail = await get_audiensi_schedule_by_id(test_id, source="surat_audiensi")
            if detail:
                print(f"  nama_universitas: {detail.get('nama_universitas')}")
                print(f"  unit_organisasi: {detail.get('unit_organisasi')}")
                print(f"  jadwal_audiensi: {detail.get('jadwal_audiensi')}")
                print(f"  nomor_surat: {detail.get('nomor_surat')}")
                print(f"  status_approval: {detail.get('status_approval')}")
                print(f"  nama_penerima: {detail.get('nama_penerima')}")
                print(f"  jenis_instansi: {detail.get('jenis_instansi')}")
            else:
                print("  NOT FOUND!")

    await close_dms_pool()
    print("\nDone!")

asyncio.run(main())
