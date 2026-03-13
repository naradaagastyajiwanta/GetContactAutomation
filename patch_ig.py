import re

with open("orchestrator/crm/social_profiler.py", "r", encoding="utf-8") as f:
    text = f.read()

old_ig_prompt = """                f"We're looking for the PERSONAL Instagram handle of:\\n"
                f"- Name: {full_name}\\n"
                f"- University: {uni_name}\\n"
                f"- Role: Lecturer/Professor\\n\\n"
                f"Which handle is most likely this person's PERSONAL Instagram?\\n"
                f"Must NOT be a business, hospital, organization, or different person.\\n"
                f'Return JSON: {{"best_index": <1-based or null>, "reason": "..."}}'"""

new_ig_prompt = """                f"We're looking for the PERSONAL Instagram handle of:\\n"
                f"- Name: {full_name}\\n"
                f"- University: {uni_name}\\n\\n"
                f"Which handle is most likely this person's PERSONAL Instagram?\\n"
                f"Must NOT be a business, hospital, organization, or different person.\\n"
                f'Return JSON: {{"best_index": <1-based or null>, "reason": "..."}}'"""

if old_ig_prompt in text:
    print("Found old IG prompt!")
text = text.replace(old_ig_prompt, new_ig_prompt)

with open("orchestrator/crm/social_profiler.py", "w", encoding="utf-8") as f:
    f.write(text)