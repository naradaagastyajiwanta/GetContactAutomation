import asyncio
from dotenv import load_dotenv

load_dotenv('.env.production', override=True)

from orchestrator.crm.social_profiler import _ai_pick_best_url
import os

async def test():
    hits = [
        {'title': 'Narada Agastya Jiwanta (@najiwan09) - Instagram', 'link': 'https://www.instagram.com/najiwan09/', 'snippet': '986 Followers, 1,124 Following, 2 Posts - See Instagram photos and videos fromNaradaAgastyaJiwanta (@najiwan09)'}, 
        {'title': 'IELTS & Scholarship on Instagram', 'link': 'https://www.instagram.com/p/CY5i1wgtqPJ/', 'snippet': '...'}
    ]
    url = await _ai_pick_best_url(hits, "Narada Agastya Jiwanta", ["Narada Agastya Jiwanta"], "instagram", "")
    print("AI Picked URL:", url)

if __name__ == "__main__":
    asyncio.run(test())
