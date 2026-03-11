"""Quick DDG connectivity test."""
from ddgs import DDGS
import os
import time

proxy = os.environ.get("DDG_PROXY")
print(f"DDG_PROXY: {proxy}")

queries = [
    'site:linkedin.com "SAMUEL KRISTIYANA"',
    'site:facebook.com "SAMUEL KRISTIYANA"',
    '"SAMUEL KRISTIYANA" "Universitas Akprind" profil lahir',
    '"SAMUEL KRISTIYANA" instagram',
    '"SAMUEL KRISTIYANA" hobi OR hobby',
]

print("\n=== WITH PROXY ===")
for q in queries:
    try:
        with DDGS(proxy=proxy) as ddgs:
            results = list(ddgs.text(q, region="id-id", max_results=3))
        print(f"  OK ({len(results):d}): {q[:55]}")
    except Exception as e:
        print(f"  FAIL: {q[:55]} -> {type(e).__name__}")
    time.sleep(2.5)

print("\n=== WITHOUT PROXY ===")
for q in queries:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(q, region="id-id", max_results=3))
        print(f"  OK ({len(results):d}): {q[:55]}")
    except Exception as e:
        print(f"  FAIL: {q[:55]} -> {type(e).__name__}")
    time.sleep(2.5)
