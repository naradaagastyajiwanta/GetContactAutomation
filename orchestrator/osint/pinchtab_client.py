import os
import httpx
import logging
import asyncio
import uuid

log = logging.getLogger("pinchtab")

# Fallback to local default if env missing
PINCHTAB_URL = os.environ.get("PINCHTAB_URL", "http://localhost:9867")

async def pt_fetch_html(url: str, timeout: int = 20) -> str | None:
    """Fetch HTML page realistically using PinchTab to bypass CF/bot blocks.""" 
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # 1. Start headless instance
            instance_name = f"osint_{uuid.uuid4().hex[:8]}"
            res = await client.post(
                f"{PINCHTAB_URL}/instances/launch",
                json={"name": instance_name, "mode": "headless"}
            )
            if res.status_code not in (200, 201, 202):
                log.error("PinchTab instance launch failed: HTTP %s, %s", res.status_code, res.text)
                return None

            inst_data = res.json()
            inst_id = inst_data.get("id")
            if not inst_id:
                return None

            try:
                # Wait for instance to become 'running' (it starts in 'starting')
                running = False
                for _ in range(30):
                    chk = await client.get(f"{PINCHTAB_URL}/instances")
                    if chk.status_code == 200:
                        instances = chk.json()
                        current = next((i for i in instances if i.get("id") == inst_id), None)
                        if current and current.get("status") == "running":      
                            running = True
                            break
                    await asyncio.sleep(1.0)
                
                if not running:
                    log.error("PinchTab instance %s failed to become running and timed out", inst_id)
                    return None

                # 2. Open tab with URL
                res = await client.post(
                    f"{PINCHTAB_URL}/instances/{inst_id}/tabs/open",
                    json={"url": url}
                )
                if res.status_code not in (200, 201, 202):
                    log.error("PinchTab open tab failed: HTTP %s, %s", res.status_code, res.text)
                    return None

                tab_id = res.json().get("tabId")

                # Wait for Cloudflare/Incapsula to complete if any
                await asyncio.sleep(4)

                # 3. Request page snapshot
                snap_res = await client.get(
                    f"{PINCHTAB_URL}/tabs/{tab_id}/snapshot?filter=all"
                )

                html_content = snap_res.text
                return html_content

            finally:
                # 4. Stop instance to clean up
                try:
                    await client.post(f"{PINCHTAB_URL}/instances/{inst_id}/stop")   
                except:
                    pass

    except Exception as e:
        log.warning("PinchTab fetch failed for %s: %s", url, e)
        return None
