import re

with open('orchestrator/crm/graph.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the family_residence inference block
old = '''    # ── Gap: family_residence — infer from university location ──────
    if family and not family.family_residence and "Tempat Tinggal Keluarga" in missing_fields:
        # University city is a strong proxy for residence
        hits = await ddg_search(f'"{uni_name}" lokasi OR alamat OR kota', max_results=2)
        if hits:
            combined = "\n".join(h.get("snippet", "") for h in hits)
            extracted = await gpt_extract_structured(
                combined,
                f"Where is {uni_name} located? Return JSON: {{"city": "...", "province": "..."}}",
            )
            if extracted and extracted.get("city"):
                family.family_residence = extracted["city"]
                family.sources = list(family.sources) + ["gap_filler_inferred"]
                updates["family_info"] = family'''

new = '''    # ── Gap: family_residence — DISABLED ────────────────────────────────────
    # DO NOT infer family_residence from university location - this is unreliable!
    # A professor may work in one city but live in another
    # Only accept explicit mentions from verified sources'''

if old in content:
    content = content.replace(old, new)
    with open('orchestrator/crm/graph.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Not found, trying alternative...')
    # Try another pattern
    if 'gap_filler_inferred' in content:
        content = re.sub(
            r'    # ── Gap: family_residence — infer from university location ──────\n    if family.*?updates\["family_info"\] = family\n',
            '''    # ── Gap: family_residence — DISABLED ────────────────────────────────────
    # DO NOT infer family_residence from university location - this is unreliable!
    # Only accept explicit mentions from verified sources
''',
            content,
            flags=re.DOTALL
        )
        with open('orchestrator/crm/graph.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Fixed with regex!')
    else:
        print('Could not find pattern')
