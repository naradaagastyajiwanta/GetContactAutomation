"""
Add a local admin user to auth_user_roles so login works without MySQL.
Usage: python scripts/add_local_admin.py --email you@example.com --name "Your Name"
"""
import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite
from orchestrator.config import DATABASE_PATH


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True, help="Email untuk login")
    parser.add_argument("--name", default="Admin", help="Nama tampil")
    parser.add_argument("--role", default="admin", help="Role key (default: admin)")
    args = parser.parse_args()

    email = args.email.strip().lower()

    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        # Check if already exists
        cur = await db.execute(
            "SELECT id FROM auth_user_roles WHERE user_email = ? AND role_key = ?",
            (email, args.role),
        )
        existing = await cur.fetchone()
        if existing:
            print(f"[OK] User {email} dengan role {args.role} sudah ada.")
            return

        await db.execute(
            """INSERT INTO auth_user_roles
               (dms_user_id, user_email, user_name, role_key, is_active, granted_by_email)
               VALUES (?, ?, ?, ?, 1, 'system')""",
            (999, email, args.name, args.role),
        )
        await db.commit()
        print(f"[OK] User berhasil ditambahkan:")
        print(f"     Email : {email}")
        print(f"     Name  : {args.name}")
        print(f"     Role  : {args.role}")
        print()
        print(f"Login dengan password: AUTH_FALLBACK_PASSWORD dari .env (default: dms2024!)")


asyncio.run(main())
