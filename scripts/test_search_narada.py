import os
import asyncio
from orchestrator.osint.tools import serper_search
import json

async def test_search():
    query = 'Narada Agastya Jiwanta'
    res = await serper_search(query)
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    asyncio.run(test_search())