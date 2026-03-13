import re

with open("orchestrator/crm/social_profiler.py", "r", encoding="utf-8") as f:
    text = f.read()

# I want to inject the hardcoded fallback into the queries list right after it's retrieved from the dict
old_loop = """    for platform, queries in queries_dict.items():"""
new_loop = """    for platform, queries in queries_dict.items():
        # Inject standard DuckDuckGo-friendly broad search
        queries.append(f'"{full_name}" {platform}')
        queries.append(f'{primary} {platform}')
"""

text = text.replace(old_loop, new_loop)

with open("orchestrator/crm/social_profiler.py", "w", encoding="utf-8") as f:
    f.write(text)