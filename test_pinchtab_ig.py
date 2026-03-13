import httpx
import asyncio
import json

async def test_ig():
    base_url = "http://localhost:9867"
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Launch instance
        res = await client.post(f"{base_url}/instances/launch", json={"name": "test_ig", "mode": "headless"})
        if res.status_code not in (200, 201, 202):
            print("Failed to launch:", res.text)
            return
        inst_id = res.json().get("id")
        print(f"Launched instance: {inst_id}")
        
        # Wait for running
        for _ in range(15):
            chk = await client.get(f"{base_url}/instances")
            if chk.status_code == 200:
                current = next((i for i in chk.json() if i.get("id") == inst_id), None)
                if current and current.get("status") == "running":
                    break
            await asyncio.sleep(1)
        
        # Open tab
        print("Opening Instagram...")
        res = await client.post(f"{base_url}/instances/{inst_id}/tabs/open", json={"url": "https://www.instagram.com/kemenkominfo/"})
        if res.status_code not in (200, 201, 202):
            print("Failed to open tab:", res.text)
            return
        tab_id = res.json().get("tabId")
        print(f"Opened tab: {tab_id}")

        # Wait for lazy loading to render page elements
        await asyncio.sleep(6)
        
        # Get Snapshot JSON (PinchTab's primary format)
        print("Fetching Snapshot JSON...")
        snap_res = await client.get(f"{base_url}/tabs/{tab_id}/snapshot?filter=all")
        with open("ig_snapshot_pinchtab.json", "w", encoding="utf-8") as f:
            f.write(snap_res.text)
        
        # Get Text format
        print("Fetching Plain Text extraction...")
        text_res = await client.get(f"{base_url}/tabs/{tab_id}/text")
        with open("ig_text_pinchtab.json", "w", encoding="utf-8") as f:
            f.write(text_res.text)
        
        # Clean up
        await client.post(f"{base_url}/instances/{inst_id}/stop")
        print("Done! Check ig_snapshot_pinchtab.json and ig_text_pinchtab.json")

asyncio.run(test_ig())
