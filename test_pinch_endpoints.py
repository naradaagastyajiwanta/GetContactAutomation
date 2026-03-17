import asyncio, httpx, uuid
async def test():
    async with httpx.AsyncClient() as c:
        res = await c.post('http://localhost:9867/instances/launch', json={'name':'test_html', 'mode':'headless'})
        inst_id = res.json().get('id')
        if not inst_id: print('failed launch'); return
        await asyncio.sleep(2)
        res = await c.post(f'http://localhost:9867/instances/{inst_id}/tabs/open', json={'url':'https://example.com'})
        tab_id = res.json().get('tabId')
        
        # Test endpoints
        for ep in ['/html', '/content', '/source', '/page']:
            r = await c.get(f'http://localhost:9867/tabs/{tab_id}{ep}')
            print(ep, r.status_code)
        await c.post(f'http://localhost:9867/instances/{inst_id}/stop')
asyncio.run(test())
