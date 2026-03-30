#!/usr/bin/env python3
"""Comprehensive session test on server - checks page nav + multiple API endpoints."""
import sys, time, json
sys.path.insert(0, "/app")
from orchestrator.playwright_ig import _PlaywrightBrowser, _IGAccount, _kill_orphan_chromes

username = "sekretariataaii_1"
acct = _IGAccount(username, "dummy")
_kill_orphan_chromes(acct.profile_dir)

browser = _PlaywrightBrowser(acct, headless=True)
browser.__enter__()

try:
    # 1. Navigate to homepage
    print("=== Test 1: Navigate to instagram.com ===")
    browser.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)
    url = browser.page.url
    print(f"URL: {url}")
    
    # Check if login form is shown (meaning session invalid)
    has_login = False
    try:
        has_login = browser.page.locator('input[name="username"], input[name="email"]').first.is_visible(timeout=2000)
    except:
        pass
    print(f"Login form visible: {has_login}")
    
    # Check cookies
    cookies = browser._get_ig_cookies()
    print(f"ds_user_id: {cookies.get('ds_user_id', 'NONE')}")
    print(f"sessionid: {'YES' if cookies.get('sessionid') else 'NONE'}")
    
    # Get page text snippet
    try:
        body = browser.page.locator("body").inner_text(timeout=3000)
        print(f"Page text (first 300): {body[:300]}")
    except:
        print("Could not get page text")
    
    # 2. Try navigating to a profile
    print("\n=== Test 2: Navigate to a profile page ===")
    browser.page.goto("https://www.instagram.com/instagram/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)
    url2 = browser.page.url
    print(f"URL: {url2}")
    has_login2 = False
    try:
        has_login2 = browser.page.locator('input[name="username"], input[name="email"]').first.is_visible(timeout=2000)
    except:
        pass
    print(f"Redirected to login: {has_login2}")
    try:
        body2 = browser.page.locator("body").inner_text(timeout=3000)
        print(f"Profile page text (first 300): {body2[:300]}")
    except:
        print("Could not get page text")
    
    # 3. Try different API endpoints
    print("\n=== Test 3: API endpoints ===")
    endpoints = [
        "https://www.instagram.com/api/v1/users/web_profile_info/?username=instagram",
        "https://www.instagram.com/api/v1/accounts/current_user/?edit=true",
        "https://i.instagram.com/api/v1/users/web_profile_info/?username=instagram",
    ]
    for ep in endpoints:
        resp = browser.ig_api_fetch(ep)
        if resp and not resp.get("__error"):
            print(f"  OK: {ep[:60]}... -> keys: {list(resp.keys())[:5]}")
        else:
            status = resp.get("status", "?") if resp else "None"
            print(f"  FAIL: {ep[:60]}... -> status={status}")
    
    # 4. Take screenshot
    print("\n=== Saving screenshot ===")
    raw = browser.page.screenshot(type="jpeg", quality=60)
    with open("data/session_test_server.jpg", "wb") as f:
        f.write(raw)
    print(f"Screenshot saved: data/session_test_server.jpg ({len(raw)} bytes)")
    
finally:
    browser.__exit__(None, None, None)
    print("\nDone!")
