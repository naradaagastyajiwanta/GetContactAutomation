import re

with open("orchestrator/crm/social_profiler.py", "r", encoding="utf-8") as f:
    text = f.read()

new_prompt = """    prompt = f\"\"\"Generate effective Google Search dork queries to find the social media profiles for a specific person.

  Person Info:
  - Full Name: {full_name}
  - Name Variants: {', '.join(name_variants[:3])}
  - University: {uni_name}
  - NIDN: {nidn or 'Unknown'}

  Platforms required: linkedin, instagram, facebook, twitter

  Rules for the queries:
  1. DO NOT append "dosen", "lecturer" or "campus" if the University is "None" or "Unknown".
  2. Because DuckDuckGo is used, YOU MUST PROVIDE AT LEAST ONE QUERY PER PLATFORM THAT DOES **NOT** USE THE `site:` OPERATOR (e.g. `"{full_name}" linkedin profile` or `"{full_name}" instagram`).
  3. Include 2-3 queries per platform.

  Return a JSON object with keys "linkedin", "instagram", "facebook", and "twitter", each containing an array of 2-3 string queries.
  \"\"\""""

text = re.sub(r'    prompt = f\"\"\"Generate effective Google Search dork queries.*?    \"\"\"', new_prompt, text, flags=re.DOTALL)

with open("orchestrator/crm/social_profiler.py", "w", encoding="utf-8") as f:
    f.write(text)
