import asyncio
import os
import logging
import httpx

log = logging.getLogger('tavily_search')

async def check_tavily(query: str):
    api_key = os.environ.get('TAVILY_API_KEY', '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')
    payload = {
        'api_key': api_key,
        'query': query,
        'search_depth': 'advanced',
        'include_raw_content': True,
        'max_results': 5
    }
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post('https://api.tavily.com/search', json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                results = data.get('results', [])
                print(f'Got {len(results)} results from Tavily:')
                for r in results:
                    print(f'- {r.get('title')} ({r.get('url')})')
                return results
            else:
                print(f'Error: {res.status_code} - {res.text}')
        except Exception as e:
            print(f'Exception: {e}')

if __name__ == '__main__':
    asyncio.run(check_tavily('Narada Agastya Jiwanta'))
