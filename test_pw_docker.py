import asyncio
from playwright.async_api import async_playwright

async def test_pw():
    async with async_playwright() as p:
        print('Playwright started')
        browser = await p.chromium.launch_persistent_context('data/pw_sessions/chromium_social_scraper', headless=True)
        page = await browser.new_page()
        await page.goto('https://www.instagram.com/')
        print('Title:', await page.title())
        await browser.close()

asyncio.run(test_pw())
