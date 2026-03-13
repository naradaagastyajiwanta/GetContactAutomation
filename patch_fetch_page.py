with open("orchestrator/osint/tools.py", "r", encoding="utf-8") as f:
    text = f.read()

import_statement = "from bs4 import BeautifulSoup"
new_import = "from bs4 import BeautifulSoup\nfrom orchestrator.osint.pinchtab_client import pt_fetch_html"
text = text.replace(import_statement, new_import)

old_fetch = """async def fetch_page(url: str, timeout: float = 15.0) -> str | None:
    \"\"\"Fetch a web page and return the HTML body text, or None on error.\"\"\"
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; GetContactAI/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except (Exception, asyncio.CancelledError) as e:
        log.debug("[OSINT Tools] fetch_page failed for %s: %s", url, e)
        return None"""

new_fetch = """async def fetch_page(url: str, timeout: float = 15.0) -> str | None:
    \"\"\"Fetch a web page and return the HTML body text, or None on error.\"\"\"
    try:
        # First try via PinchTab to bypass blocks (e.g. for SINTA, Scholar, University web)
        pt_html = await pt_fetch_html(url, timeout=int(timeout))
        if pt_html and len(pt_html) > 500:
            return pt_html
            
        # Fallback to standard HTTPX
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except (Exception, asyncio.CancelledError) as e:
        log.debug("[OSINT Tools] fetch_page failed for %s: %s", url, e)
        return None"""

text = text.replace(old_fetch, new_fetch)

with open("orchestrator/osint/tools.py", "w", encoding="utf-8") as f:
    f.write(text)