import asyncio
import os
import logging
import httpx

log = logging.getLogger('tavily_search')

async def tavily_deep_search(query: str, max_results: int = 10):
    api_key = os.environ.get('TAVILY_API_KEY')
    if not api_key:
        log.error("TAVILY_API_KEY environment variable is not set")
        return "Tavily search unavailable: API key not configured."

    payload = {
        'api_key': api_key,
        'query': query,
        'search_depth': 'advanced',
        'include_raw_content': True,
        'max_results': max_results
    }
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post('https://api.tavily.com/search', json=payload, timeout=40.0)
            if res.status_code == 200:
                data = res.json()
                results = data.get('results', [])
                
                aggregate_text = ''
                for r in results:
                    content = r.get('raw_content') or r.get('content', '')
                    url = r.get('url', 'unknown')
                    aggregate_text += f'\nSource: {url}\nContent: {content[:2000]}\n'
                return aggregate_text if aggregate_text else 'No significant footprint found on Tavily.'
            else:
                log.error('Tavily Error: %s - %s', res.status_code, res.text)
                return 'Failed to fetch Tavily data.'
        except Exception as e:
            log.error('Tavily Exception: %s', e)
            return 'Tavily search timeout or error.'

