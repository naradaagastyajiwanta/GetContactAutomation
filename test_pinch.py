import asyncio
from orchestrator.osint.tools import fetch_page
async def get_fb():
    res = await fetch_page('https://www.facebook.com/jiwanta.narada/about_work_and_education')
    if not res: return
    print(len(res))
    print('IELTSpresso' in res, 'One Earth' in res)
asyncio.run(get_fb())