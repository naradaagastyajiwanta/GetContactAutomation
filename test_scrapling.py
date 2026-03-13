import time
from scrapling.fetchers import StealthyFetcher

print("Trying Instagram...")
page = StealthyFetcher.fetch('https://www.instagram.com/kemenkominfo/', headless=True)
print(page.text[:200])

with open("scrapling_ig.html", "w", encoding="utf-8") as f:
    f.write(page.text)

print("\nTrying LinkedIn...")
page2 = StealthyFetcher.fetch('https://id.linkedin.com/in/narada-agastya-jiwanta-a58950221', headless=True)
with open("scrapling_li.html", "w", encoding="utf-8") as f:
    f.write(page2.text)
print(page2.text[:200])

print("Done! Results saved to scrapling_ig.html and scrapling_li.html")
