import asyncio
from orchestrator.crm.tools import brave_search, ddg_search

async def test():
    queries = [
        'site:linkedin.com/in "Dwi Perwitasari" "Universitas Jember"',
        'site:instagram.com "Dwi Perwitasari"'
    ]
    for q in queries:
        print(f"--- QUERY: {q} ---")
        try:
            hits_ddg = await ddg_search(q, max_results=3)
            print(f"DDG Hits: {len(hits_ddg) if hits_ddg else 0}")
            if hits_ddg:
                for h in hits_ddg:
                    print(f" DDG - {h.get('link')}")
        except Exception as e:
            print("DDG Error:", e)

        try:
            hits_brave = await brave_search(q, max_results=3)
            print(f"Brave Hits: {len(hits_brave) if hits_brave else 0}")
            if hits_brave:
                for h in hits_brave:
                    print(f" BRV - {h.get('link')}")
        except Exception as e:
            print("Brave Error:", e)
        print()

asyncio.run(test())
