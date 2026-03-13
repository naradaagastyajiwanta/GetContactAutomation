import sqlite3

db_path = 'data/getcontact.db'
out_path = 'qa_test_output2.txt'

try:
    with open(out_path, 'w', encoding='utf-8') as f:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        f.write("=== CRM Request 5 ===\n")
        cursor.execute("SELECT * FROM crm_requests WHERE id = 5")
        req = cursor.fetchone()
        if req:
            for key in req.keys():
                f.write(f"{key}: {req[key]}\n")
        else:
            f.write("Not found.\n")

        f.write("\n=== CRM PIC Profiles ===\n")
        cursor.execute("SELECT * FROM crm_pic_profiles WHERE request_id = 5")
        pics = cursor.fetchall()
        if pics:
            for i, pic in enumerate(pics):
                f.write(f"\n--- Profile {i+1} ---\n")
                for key in pic.keys():
                    f.write(f"{key}: {pic[key]}\n")
        else:
            f.write("No profiles found.\n")

        conn.close()
except Exception as e:
    import traceback
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(traceback.format_exc())
