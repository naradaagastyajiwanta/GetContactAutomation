import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv('.env.production', override=True)

import httpx

async def test():
    api_key = os.getenv("SERPER_API_KEY") or ''
    # print(f"Key preview: {api_key[:5]}...")
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    payload = {"q": '"Narada Agastya Jiwanta" instagram', "num": 5}
    
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload)
        print(r.status_code)
        import pprint
        pprint.pprint(r.json())

if __name__ == "__main__":
    asyncio.run(test())
