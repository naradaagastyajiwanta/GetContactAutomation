import asyncio
import sqlite3
import sys

async def update_all_student_counts():
    from orchestrator.osint.tools import pddikti_get_prodi
    from orchestrator.db import update_student_count

    conn = sqlite3.connect('data/getcontact.db')
    cursor = conn.cursor()

    # Get universities with pddikti_id
    cursor.execute("SELECT id, pddikti_id FROM universities WHERE pddikti_id IS NOT NULL AND pddikti_id != '' AND student_count IS NULL")
    universities = cursor.fetchall()

    print(f"Total universities to process: {len(universities)}")

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
                    print(f"[{i+1}/{len(universities)}] University {uni_id}: {total_students} students")
                else:
                    print(f"[{i+1}/{len(universities)}] University {uni_id}: no students")
            else:
                print(f"[{i+1}/{len(universities)}] University {uni_id}: no prodi data")
        except Exception as e:
            failed += 1
            print(f"[{i+1}/{len(universities)}] University {uni_id}: ERROR - {e}")

        # Progress every 100
        if (i + 1) % 100 == 0:
            print(f"Progress: {i+1}/{len(universities)}")

    print(f"\nDone! Success: {success}, Failed: {failed}")

    # Final count
    cursor.execute("SELECT COUNT(*) FROM universities WHERE student_count IS NOT NULL")
    total_with_count = cursor.fetchone()[0]
    print(f"Universities with student_count: {total_with_count}")

    conn.close()

if __name__ == "__main__":
    asyncio.run(update_all_student_counts())
