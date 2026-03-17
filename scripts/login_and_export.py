import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

async def main():
    session_dir = Path('data/pw_sessions/chromium_social_scraper')
    session_dir.mkdir(parents=True, exist_ok=True)
    
    print(f'Membuka browser di profil: {session_dir}')
    
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=False,
            viewport={'width': 1280, 'height': 720}
        )
        
        page = await browser.new_page()
        
        # Instagram
        print('\n=== LOGIN INSTAGRAM ===')
        print('Silakan login ke Instagram di jendela browser (jika belum).')
        await page.goto('https://www.instagram.com/')
        input('Tekan ENTER DUA KALI di terminal ini JIKA Anda SUDAH BERHASIL LOGIN Instagram dan melihat halaman home...')
        
        # Facebook
        print('\n=== LOGIN FACEBOOK ===')
        print('Silakan login ke Facebook di jendela browser (jika belum).')
        await page.goto('https://www.facebook.com/')
        input('Tekan ENTER di terminal ini JIKA Anda SUDAH BERHASIL LOGIN Facebook dan melihat halaman home...')
        
        print('Menyimpan file session.json agar bisa dibaca dari dalam Docker...')
        await browser.storage_state(path='data/pw_sessions/state.json')
        await browser.close()
        print('\nSelesai! Sesi cookie sosial media Anda berhasil disimpan di data/pw_sessions/state.json')

if __name__ == '__main__':
    asyncio.run(main())
