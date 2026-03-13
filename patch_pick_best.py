import re

with open("orchestrator/crm/social_profiler.py", "r", encoding="utf-8") as f:
    text = f.read()

old_linkedin_filter = """        if platform == "linkedin" and "/in/" not in url and "/pub/" not in url:
            continue"""

new_linkedin_filter = """        if platform == "linkedin":
            if "/in/" not in url and "/pub/" not in url:
                # If it's a post url, extract the profile part!
                m = re.search(r"linkedin\.com/(?:posts|pulse)/([A-Za-z0-9-]+)(?:_|\b)", url)
                if m:
                    # override url with the inferred profile
                    url = f"https://www.linkedin.com/in/{m.group(1)}/"
                    hit["link"] = url
                else:
                    continue"""

text = text.replace(old_linkedin_filter, new_linkedin_filter)

with open("orchestrator/crm/social_profiler.py", "w", encoding="utf-8") as f:
    f.write(text)