import httpx
import asyncio

async def test_li():
    base_url = "http://localhost:9867"
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(f"{base_url}/instances/launch", json={"name": "test_li", "mode": "headless"})
        inst_id = res.json().get("id")
        for _ in range(15):
            chk = await client.get(f"{base_url}/instances")
            if next((i for i in chk.json() if i.get("id") == inst_id), {}).get("status") == "running": break
            await asyncio.sleep(1)
        
        # Test LinkedIn Sinta
        url = "https://id.linkedin.com/in/narada-agastya-jiwanta-a58950221"
        res = await client.post(f"{base_url}/instances/{inst_id}/tabs/open", json={"url": url})
        tab_id = res.json().get("tabId")

        await asyncio.sleep(6)
        text_res = await client.get(f"{base_url}/tabs/{tab_id}/text")
        print(text_res.text)
        await client.post(f"{base_url}/instances/{inst_id}/stop")

asyncio.run(test_li())
