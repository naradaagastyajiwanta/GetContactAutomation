import asyncio
from orchestrator.osint.pinchtab_client import pt_fetch_html

async def main():
    fb_url = 'https://www.facebook.com/jiwanta.narada/'
    print(f'Fetching {fb_url} with PinchTab...')
    try:
        result = await pt_fetch_html(fb_url, timeout=30.0)
        print('\n--- RAW FACEBOOK OUTPUT (First 1500 chars) ---')
        print(result[:1500])
    except Exception as e:
        print(f'Error: {e}')

    ig_url = 'https://www.instagram.com/najiwan09/'
    print(f'\nFetching {ig_url} with PinchTab...')
    try:
        ig_result = await pt_fetch_html(ig_url, timeout=30.0)
        print('\n--- RAW INSTAGRAM OUTPUT (First 1500 chars) ---')
        print(ig_result[:1500])
    except Exception as e:
        print(f'Error: {e}')

asyncio.run(main())
