"""Check universities in DMS MySQL database.
Requires env vars: DMS_MYSQL_HOST, DMS_MYSQL_USER, DMS_MYSQL_PASSWORD, DMS_MYSQL_DATABASE
"""
import asyncio
import os
import aiomysql

async def main():
    conn = await aiomysql.connect(
        host=os.environ["DMS_MYSQL_HOST"],
        port=int(os.environ.get("DMS_MYSQL_PORT", 3306)),
        user=os.environ["DMS_MYSQL_USER"],
        password=os.environ["DMS_MYSQL_PASSWORD"],
        db=os.environ["DMS_MYSQL_DATABASE"],
    )
    async with conn.cursor(aiomysql.DictCursor) as cur:
        # All tables containing 'lsp' or 'universitas'
        await cur.execute("SHOW TABLES")
        all_tables = [list(r.values())[0] for r in await cur.fetchall()]
        filtered = [t for t in all_tables if "lsp" in t.lower() or "universitas" in t.lower()]
        print("Relevant tables:", filtered)

        # Check universitas_lsp if exists
        if "universitas_lsp" in filtered:
            await cur.execute("DESCRIBE universitas_lsp")
            cols = await cur.fetchall()
            print("\nuniversitas_lsp columns:", [c["Field"] for c in cols])
            await cur.execute("SELECT * FROM universitas_lsp WHERE id_univ IN (6920, 10811, 10808) LIMIT 10")
            rows = await cur.fetchall()
            print("Rows for id_univ 6920/10811/10808:", rows)

        # Check schedule_follow_up_lsp for univ name column directly
        await cur.execute("DESCRIBE schedule_follow_up_lsp")
        cols = await cur.fetchall()
        col_names = [c["Field"] for c in cols]
        name_cols = [c for c in col_names if "univ" in c.lower() or "nama" in c.lower() or "kampus" in c.lower()]
        print("\nschedule_follow_up_lsp name-related cols:", name_cols)

    conn.close()

asyncio.run(main())
