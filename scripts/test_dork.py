import asyncio, json
from orchestrator.crm.social_profiler import _ai_build_dork_queries

async def test():
    res = await _ai_build_dork_queries('Narada Agastya Jiwanta', ['Narada', 'Narada Jiwanta'], 'None', None)
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    asyncio.run(test())