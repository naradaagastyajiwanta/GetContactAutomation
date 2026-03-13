from scrapling.fetchers import StealthySession
from bs4 import BeautifulSoup

user_dir = r"C:\Users\narad\Programming\GetContactAI\data\pw_sessions\chromium_sekretariataaii_1"

with StealthySession(headless=True, user_data_dir=user_dir) as session:
    print("Fetching Instagram with persistent profile...")
    page = session.fetch("https://www.instagram.com/kemenkominfo/", timeout=30000)
    
    html = page.body.decode("utf-8")
    title = BeautifulSoup(html, "html.parser").title
    print("Page Title:", title.string if title else "No Title")
    
    if "Profile isn't available" in html or "Log in" in html:
        print("FAILED: Instagram still shows login wall.")
    else:
        print("SUCCESS! Instagram profile accessed with Scrapling using Playwright User Data Dir")
