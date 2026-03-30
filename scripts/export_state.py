import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    print('Mengekstrak Cookies dari Browser...')
    async with async_playwright() as p:
        # Launch using the profile we just made
        browser = await p.chromium.launch_persistent_context(
            user_data_dir='data/pw_sessions/chromium_social_scraper',
            headless=True
        )
        
        print('Menyimpan state login auth ke data/pw_sessions/state.json...')
        await browser.storage_state(path='data/pw_sessions/state.json')
        await browser.close()
        print('State berhasil diekstrak.')

if __name__ == '__main__':
    asyncio.run(main())
