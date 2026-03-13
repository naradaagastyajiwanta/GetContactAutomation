import re

with open("orchestrator/crm/social_profiler.py", "r", encoding="utf-8") as f:
    text = f.read()

old_prompt = """        hits_text,
        (
            f"We're looking for the PERSONAL {platform} profile of:\\n"
            f"- Name: {full_name}\\n"
            f"- University: {uni_name}\\n"
            f"- Role: Lecturer/Professor at an Indonesian university\\n\\n"
            f"From the search results below, pick the one that MOST LIKELY "
            f"belongs to this specific person.\\n"
            f"Consider:\\n"
            f"- Does the name in the result match? (beware of partial matches)\\n"
            f"- Is there university or academic context confirming identity?\\n"
            f"- For LinkedIn: must be the same person at the same university\\n"
            f"- For Instagram: must be PERSONAL. REJECT if title/snippet contains 'Rumah Sakit', 'RS', 'Klinik', 'BEM', 'Hima', 'Official', 'Hospital', 'Business'\\n"
            f"- For Facebook: must be the actual person, not a fan page or business\\n"
            f"- ALWAYS double check if it's an institution masking as a person (like 'RS Panti Abdi Dharma' matching 'Abdi Dharma'). REJECT institution accounts.\\n"
            f"- If NONE clearly match this specific person, return null\\n\\n"
            f'Return JSON: {{"best_index": <1-based index or null>, "reason": "..."}}'
        ),"""

new_prompt = """        hits_text,
        (
            f"We're looking for the PERSONAL {platform} profile of:\\n"
            f"- Name: {full_name}\\n"
            f"- University: {uni_name}\\n"
            f"From the search results below, pick the one that MOST LIKELY "
            f"belongs to this specific person.\\n"
            f"Consider:\\n"
            f"- Does the name in the result match? (beware of partial matches)\\n"
            f"- If University is provided, does it match or make sense? If University is None/Unknown, just match based on Name uniqueness!\\n"
            f"- For Instagram: must be PERSONAL. REJECT if title/snippet contains 'Rumah Sakit', 'RS', 'Klinik', 'BEM', 'Hima', 'Official', 'Hospital', 'Business'\\n"
            f"- For Facebook: must be the actual person, not a fan page or business\\n"
            f"- ALWAYS double check if it's an institution. REJECT institution accounts.\\n"
            f"- If NONE clearly match this specific person, return null.\\n\\n"
            f'Return JSON: {{"best_index": <1-based index or null>, "reason": "..."}}'
        ),"""

if old_prompt in text:
    print("Found old prompt!")
text = text.replace(old_prompt, new_prompt)

with open("orchestrator/crm/social_profiler.py", "w", encoding="utf-8") as f:
    f.write(text)