"""Debug IG login from inside the server container."""
import httpx
import json
import base64

r = httpx.post("http://127.0.0.1:8000/ig-accounts/1/login", timeout=120)
d = r.json()
print("Status:", d.get("status"))
print("Message:", d.get("message"))
det = d.get("details", {})
print("Final URL:", det.get("final_url"))
print("Cookies:", list(det.get("cookies", {}).keys()))
page_text = det.get("page_text", "")
if page_text:
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    print("\n--- Page text (first 20 lines) ---")
    for l in lines[:20]:
        print(" ", l)
if d.get("screenshot"):
    raw = base64.b64decode(d["screenshot"])
    with open("/app/data/login_debug.jpg", "wb") as f:
        f.write(raw)
    print(f"\nScreenshot saved to /app/data/login_debug.jpg ({len(raw)} bytes)")
else:
    print("\nNo screenshot returned")
