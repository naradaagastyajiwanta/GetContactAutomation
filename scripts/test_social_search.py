import asyncio
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
    for q in queries:
        hits = await ddg_search(q, max_results=3)
        print(f"Query: {q}")
        print(f"Hits: {len(hits) if hits else 0}")
        if hits:
            for h in hits:
                print(f" - {h.get('link')} ({h.get('title')[:30]}...)")
        print()

asyncio.run(test())
