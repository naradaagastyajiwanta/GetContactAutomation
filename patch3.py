
import sys
content = open('orchestrator/osint/pinchtab_client.py', encoding='utf-8').read()
new_func = '''async def pt_fetch_html(url: str, timeout: int = 30) -> str | None:
    \
\\Fetch
HTML
page
realistically
using
PinchTab
to
bypass
CF/bot
blocks.\\\
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(
                f\
PINCHTAB_URL
/v1/extract\,
                json={
                    \url\: url,
                    \render_js\: True,
                    \timeout\: (timeout - 5) * 1000
                }
            )
            if res.status_code == 200:
                data = res.json()
                return data.get(\data\, {}).get(\html\)
            else:
                log.error(\PinchTab
extract
failed:
HTTP
%s
%s\, res.status_code, res.text)
                return None
    except Exception as e:
        log.error(\PinchTab
connection
failed:
%s\, str(e))
        return None
'''
import re
content = re.sub(r'async def pt_fetch_html.*?return None', new_func, content, flags=re.DOTALL)
open('orchestrator/osint/pinchtab_client.py', 'w', encoding='utf-8').write(content)
print('Patched pinchtab_client.py')

