#!/usr/bin/env python3
"""Quick script to check ig_accounts credentials in DB."""
import asyncio
import aiosqlite

async def main():
    async with aiosqlite.connect("data/getcontact.db") as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ig_accounts")
        rows = await cursor.fetchall()
        for row in rows:
            d = dict(row)
            pw = d.get("password", "")
            print(f"columns: {list(d.keys())}")
            print(f"id={d.get('id')} user={d.get('username')} pass_len={len(pw)} pass_first3={pw[:3]}*** enabled={d.get('is_enabled')}")
            print(f"full_row: { {k:v for k,v in d.items() if k != 'password'} }")

asyncio.run(main())
