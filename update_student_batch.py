import asyncio
import sqlite3
import sys
import os

# Change to app directory
os.chdir('/app')

async def update_batch(limit=100):
    from orchestrator.osint.tools import pddikti_get_prodi
    from orchestrator.db import update_student_count

    conn = sqlite3.connect('data/getcontact.db')
    cursor = conn.cursor()

    # Get universities with pddikti_id (limited)
    cursor.execute(f"SELECT id, pddikti_id FROM universities WHERE pddikti_id IS NOT NULL AND pddikti_id != '' AND student_count IS NULL LIMIT {limit}")
    universities = cursor.fetchall()

    print(f"Processing {len(universities)} universities...")

    success = 0
    failed = 0

    for i, (uni_id, pddikti_id) in enumerate(universities):
        try:
            prodi_list = await pddikti_get_prodi(pddikti_id, '20241')
            if prodi_list:
                total_students = sum(p.get('jumlah_mahasiswa', 0) for p in prodi_list)
                if total_students > 0:
                    await update_student_count(uni_id, total_students)
                    success += 1
                    print(f"[{i+1}/{len(universities)}] Uni {uni_id}: {total_students} students")
                else:
                    print(f"[{i+1}/{len(universities)}] Uni {uni_id}: no students")
            else:
                print(f"[{i+1}/{len(universities)}] Uni {uni_id}: no prodi data")
        except Exception as e:
            failed += 1
            print(f"[{i+1}/{len(universities)}] Uni {uni_id}: ERROR - {e}")

    print(f"\nDone! Success: {success}, Failed: {failed}")
    conn.close()

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    asyncio.run(update_batch(limit))
