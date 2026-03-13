import asyncio
import sys
import os
sys.path.insert(0, os.getcwd())
from orchestrator.osint.tools import fetch_page

async def get_fb():
    res = await fetch_page('https://www.facebook.com/jiwanta.narada')
    if not res:
        print('Failed to fetch')
        return
    print(len(res))
    print('IELTSpresso' in res, 'One Earth' in res)

asyncio.run(get_fb())
