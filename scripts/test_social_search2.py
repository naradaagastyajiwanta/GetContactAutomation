import asyncio
import json
from orchestrator.crm.tools import ddg_search

async def test():
    queries = [
        'site:linkedin.com/in "Dwi Perwitasari" "Universitas Jember"',
        'site:linkedin.com/in "Dwi Perwitasari"',
        'site:linkedin.com/in "Abdi Dharma"',
        'site:facebook.com "Dwi Perwitasari"',
        'site:instagram.com "Dwi Perwitasari"',
        'site:instagram.com "Abdi Dharma"'
    ]
    with open("scripts/out.txt", "w", encoding="utf-8") as f:
        for q in queries:
            try:
                hits = await ddg_search(q, max_results=3)
                f.write(f"Query: {q}\n")
                f.write(f"Hits: {len(hits) if hits else 0}\n")
                if hits:
                    for h in hits:
                        f.write(f" - {h.get('link')} ({h.get('title')[:30]}...)\n")
                f.write("\n")
            except Exception as e:
                f.write(f"Query: {q} -> Error: {e}\n\n")

asyncio.run(test())
