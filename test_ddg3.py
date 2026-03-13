import asyncio
from orchestrator.osint.tools import ddg_search

async def test():
    print('Testing query IG')
    res = await ddg_search('"Narada Agastya" site:instagram.com', max_results=5)
    print(res)

if __name__ == "__main__":
    asyncio.run(test())
