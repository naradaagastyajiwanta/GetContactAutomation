import asyncio
import urllib.parse
from bs4 import BeautifulSoup

from orchestrator.osint.pinchtab_client import pt_fetch_html

async def test_ddg_pinchtab():
    query = 'site:instagram.com "Narada Agastya Jiwanta"'
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    
    print(f"Fetching {url} via PinchTab pt_fetch_html...")
    
    try:
        html = await pt_fetch_html(url, timeout=30)
        
        if not html:
            print("Failed to get HTML")
            return
            
        # Check if it hit captcha/cloudflare
        if "Cloudflare" in html or "cf-browser-verification" in html:
            print("Hit Cloudflare on PinchTab :(")
            
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for item in soup.select('.result'):
            title_el = item.select_one('.result__title a')
            link_el = item.select_one('.result__url')
            snippet_el = item.select_one('.result__snippet')
            
            if title_el and link_el:
                href = link_el.get("href", "").strip()
                if href.startswith('//'):
                    href = "https:" + href
                if "duckduckgo.com/l/?uddg=" in href:
                    parsed = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if 'uddg' in qs:
                        href = urllib.parse.unquote(qs['uddg'][0])
                        
                results.append({
                    "title": title_el.get_text(separator=' ', strip=True),
                    "link": href,
                    "snippet": snippet_el.get_text(separator=' ', strip=True) if snippet_el else ""
                })
        
        print(f"Found {len(results)} results")
        for r in results:
            print(r)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ddg_pinchtab())
