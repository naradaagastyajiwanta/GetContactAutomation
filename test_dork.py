import asyncio
import os
from dotenv import load_dotenv

load_dotenv('.env.production', override=True)

from orchestrator.crm.social_profiler import _ai_build_dork_queries, _ai_pick_best_url
from orchestrator.crm.tools import serper_search

async def test():
    full_name = "Narada Agastya Jiwanta"
    name_variants = ["Narada Agastya Jiwanta", "Narada Agastya"]
    uni_name = ""
    nidn = None
    
    print("Building queries...")
    platform_queries = await _ai_build_dork_queries(full_name, name_variants, uni_name, nidn)
    
    for platform, queries in platform_queries.items():
        if platform not in ["linkedin", "instagram"]:
            continue
        queries.append(f'"{full_name}" {platform}')
        for q in queries:
            print(f"\n[{platform}] Searching: {q}")
            hits = await serper_search(q, max_results=5)
            if hits:
                for idx, h in enumerate(hits):
                    print(f"  Hit {idx}: {h.get('link')}")
                url = await _ai_pick_best_url(hits, full_name, name_variants, platform, uni_name)
                print(f"  => AI Picked: {url}")
            else:
                print("  => No hits")

if __name__ == "__main__":
    asyncio.run(test())
