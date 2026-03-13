import json, re

html = open("scrapling_ig_cookies.html", "r", encoding="utf-8").read()

# Let's search for "edge_followed_by":{"count": or "followerCount": or similar
m = re.search(r'"follower_count":\s*(\d+)', html)
if m:
    print("Found follower_count:", m.group(1))

m2 = re.search(r'"edge_followed_by":\{"count":\s*(\d+)', html)
if m2:
    print("Found edge_followed_by count:", m2.group(1))

# Search script tags
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, "html.parser")
found = False
for s in soup.find_all("script"):
    if s.string and "jokowi" in s.string and "edge_followed_by" in s.string:
        print("Found JSON payload with user data!")
        found = True
        break
        
print("Has followers?", "followers" in html.lower())
