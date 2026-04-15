"""
Migration: Move BEM UPNVJ data from univ 1517 (Undiknas Bali) to 4010 (UPNVJ Jakarta)

Root cause: BEM finder assigned bem_upnvj to both universities.
Posts & contacts scraped from bem_upnvj ended up in 1517 instead of 4010.
"""
import sqlite3

con = sqlite3.connect("data/getcontact.db")
con.row_factory = sqlite3.Row
cur = con.cursor()

print("=== MIGRATION: 1517 (Undiknas) -> 4010 (UPNVJ) ===\n")

# 1. Hapus posts duplikat di 1517 (sudah ada di 4010)
cur.execute("""
    DELETE FROM ig_posts
    WHERE university_id=1517
    AND post_url IN (
        SELECT post_url FROM ig_posts WHERE university_id=4010
    )
""")
print(f"Posts duplikat dihapus dari 1517: {cur.rowcount}")

# 2. Pindahkan sisa posts dari 1517 ke 4010
cur.execute("UPDATE ig_posts SET university_id=4010 WHERE university_id=1517")
print(f"Posts dipindah ke 4010: {cur.rowcount}")

# 3. Hapus contacts duplikat di 1517 (same phone sudah ada di 4010)
cur.execute("""
    DELETE FROM ig_contacts
    WHERE university_id=1517
    AND phone_number IN (
        SELECT phone_number FROM ig_contacts WHERE university_id=4010
    )
""")
print(f"Contacts duplikat dihapus dari 1517: {cur.rowcount}")

# 4. Pindahkan sisa contacts dari 1517 ke 4010
cur.execute("UPDATE ig_contacts SET university_id=4010 WHERE university_id=1517")
print(f"Contacts dipindah ke 4010: {cur.rowcount}")

# 5. Reset univ 1517: hapus bem_ig_handle yang salah, biarkan re-discovery
cur.execute("""
    UPDATE universities
    SET bem_ig_handle = NULL,
        bem_discovery_status = NULL,
        bem_discovery_attempts = 0,
        status = 'ig_found'
    WHERE id = 1517
""")
print("Univ 1517 di-reset: bem_ig_handle=NULL, status=ig_found")

con.commit()

print("\n=== Verifikasi ===")
cur.execute("SELECT COUNT(*) as c FROM ig_posts WHERE university_id=1517")
print(f"Posts di 1517 (Undiknas): {cur.fetchone()['c']} (harusnya 0)")
cur.execute("SELECT COUNT(*) as c FROM ig_contacts WHERE university_id=1517")
print(f"Contacts di 1517 (Undiknas): {cur.fetchone()['c']} (harusnya 0)")
cur.execute("SELECT COUNT(*) as c FROM ig_posts WHERE university_id=4010")
print(f"Posts di 4010 (UPNVJ): {cur.fetchone()['c']}")
cur.execute("SELECT COUNT(*) as c FROM ig_contacts WHERE university_id=4010")
print(f"Contacts di 4010 (UPNVJ): {cur.fetchone()['c']}")
cur.execute("SELECT bem_ig_handle, bem_discovery_status, status FROM universities WHERE id=1517")
r = cur.fetchone()
print(f"Univ 1517 status: {dict(r)}")

con.close()
print("\nMigration selesai.")
