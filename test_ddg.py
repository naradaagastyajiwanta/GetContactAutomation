import asyncio
from orchestrator.osint.tools import ddg_search

async def test():
    res = await ddg_search('site:linkedin.com/in "Narada Agastya Jiwanta"', max_results=5)
    print(res)

if __name__ == "__main__":
    asyncio.run(test())
