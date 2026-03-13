import json
import time
from scrapling.fetchers import StealthySession
from bs4 import BeautifulSoup

COOKIE_FILE = r"C:\Users\narad\Programming\GetContactAI\data\pw_sessions\chromium_sekretariataaii_2\imported_cookies.json"

print("Loading cookies from:", COOKIE_FILE)
with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

print(f"Loaded {len(cookies)} cookies.")

print("Starting Scrapling StealthySession...")
# Add more arguments to look human
with StealthySession(headless=True) as session:
    print("Injecting cookies...")
    session.context.add_cookies(cookies)

    print("Fetching Target 2: instagram.com/jokowi/")
    page = session.fetch("https://www.instagram.com/jokowi/", timeout=30000)
    
    html = page.body.decode("utf-8")
    title = BeautifulSoup(html, "html.parser").title
    print("Page Title:", title.string if title else "No Title")
    if "Instagram" in html:
        print("Logged in!")
    
    with open("scrapling_ig_cookies.html", "w", encoding="utf-8") as f:
        f.write(html)
