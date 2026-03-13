import sqlite3
import json

db_path = 'data/getcontact.db'

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=== CRM Request 5 ===")
    cursor.execute("SELECT * FROM crm_requests WHERE id = 5")
    req = cursor.fetchone()
    if req:
        for key in req.keys():
            print(f"{key}: {req[key]}")
    else:
        print("Not found.")

    print("\n=== CRM PIC Profiles ===")
    cursor.execute("SELECT * FROM crm_pic_profiles WHERE request_id = 5")
    pics = cursor.fetchall()
    if pics:
        for i, pic in enumerate(pics):
            print(f"\n--- Profile {i+1} ---")
            for key in pic.keys():
                print(f"{key}: {pic[key]}")
    else:
        print("No profiles found.")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
