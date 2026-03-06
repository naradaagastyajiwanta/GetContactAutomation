"""Debug IG login - capture page content after submit attempt."""
import httpx
import json
import base64

# First check: what does the page actually show?
# We'll add a direct browser test bypassing the login endpoint
print("=== Attempting login via API endpoint ===")
r = httpx.post("http://127.0.0.1:8000/ig-accounts/1/login", timeout=180)
d = r.json()
print(f"Status: {d.get('status')}")
print(f"Message: {d.get('message')}")

det = d.get("details", {})
print(f"Final URL: {det.get('final_url')}")
cookies = det.get("cookies", {})
print(f"Cookies present: {list(cookies.keys())}")
for k, v in cookies.items():
    print(f"  {k} = {v[:20]}..." if len(str(v)) > 20 else f"  {k} = {v}")

page_text = det.get("page_text", "")
if page_text:
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    print(f"\n--- Page text ({len(lines)} lines, first 30) ---")
    for l in lines[:30]:
        print(f"  {l}")

if d.get("screenshot"):
    raw = base64.b64decode(d["screenshot"])
    with open("/app/data/login_debug2.jpg", "wb") as f:
        f.write(raw)
    print(f"\nScreenshot saved ({len(raw)} bytes)")
