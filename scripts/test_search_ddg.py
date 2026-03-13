import asyncio, json
from orchestrator.osint.tools import ddg_search

async def search_all():
    print("--- DDG WEB ---")
    web = await ddg_search('"Narada Agastya Jiwanta"')
    print(json.dumps(web, indent=2))

asyncio.run(search_all())