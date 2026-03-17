import asyncio
import logging
import os
import time
from playwright.async_api import async_playwright

log = logging.getLogger('pw_auth_client')

async def pw_fetch_auth_html(url: str, wait_time: int = 4000) -> str | None:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            # Load authenticated state if exists
            state_path = 'data/pw_sessions/state.json'
            if os.path.exists(state_path):
                context = await browser.new_context(storage_state=state_path)
            else:
                context = await browser.new_context()
                
            page = await context.new_page()
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Extra delay for React/Vue loading on IG/FB
            await page.wait_for_timeout(wait_time)
            
            # Scroll down slowly to trigger lazy-loaded posts
            await page.evaluate('window.scrollBy(0, 1500)')
            await page.wait_for_timeout(1000)
            await page.evaluate('window.scrollBy(0, 1500)')
            await page.wait_for_timeout(1000)
            
            content = await page.content()
            await browser.close()
            return content
    except Exception as e:
        log.error('pw_fetch_auth_html error for %s: %s', url, e)
        return None
