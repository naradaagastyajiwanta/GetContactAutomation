with open('orchestrator/crm/social_post_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_code = '''
    # If no content found from direct scraping, attempt deep research via Gemini
    if not collected_content:
        from orchestrator.config import log
        from orchestrator.crm.tools import gemini_research
        
        log.info("[SocialPostAnalyzer] No direct scrape content, doing deep scan via Gemini Research...")
        
        # Build search contexts based on found urls
        targets = []
        if social.facebook_url:
            targets.append(f"Facebook profile {social.facebook_url}")
        if social.instagram_handle and social.instagram_handle not in ["None", "tidak ditemukan", "tidak ada"]:
            targets.append(f"Instagram @{social.instagram_handle}")
        if getattr(social, 'linkedin_url', None):
            targets.append(f"LinkedIn {social.linkedin_url}")
            
        target_str = ", ".join(targets) if targets else ""
        
        research_prompt = f"Lakukan deep web scan secara menyeluruh pada jejak digital dan media sosial dari {full_name}."
        if target_str:
            research_prompt += f" Fokuskan pencarian pada akun-akun berikut: {target_str}."
        # Use more robust prompting for Gemini to go deep!
        research_prompt += " Tolong kumpulkan informasi selengkap-lengkapnya mengenai kegiatan terbaru dari media sosial itu, hobi/minat personal, gaya bahasa dari postingan yang ada (santai/kaku), opini pribadinya, serta hal-hal yang sering dia pamerkan. Kumpulkan semua info sebanyak-banyaknya hingga menjadi profil deep scan yang padat dan komprehensif. Anda juga bisa menelusuri nama lengkapnya di internet untuk menambah detail. Berikan laporan teks sedetail mungkin."
        
        research_result = await gemini_research(research_prompt)
        text = research_result.get("text", "")
        if len(text) > 100:
            collected_content["Gemini Deep Scan"] = text
        else:
            log.info("[SocialPostAnalyzer] Gemini research yielded no result, attempting post dorking...")
            q = f'"{full_name}" site:facebook.com OR site:instagram.com OR site:medium.com OR site:kompasiana.com'
            from orchestrator.crm.tools import ddg_search
            hits = await ddg_search(q, max_results=4)
            if hits:
                snippets = "\\n".join(h.get("snippet", "") for h in hits)
                if len(snippets) > 50:
                    collected_content["Search Snippets"] = snippets
'''

part1 = content.split('    # If no content found from direct scraping, attempt DDG search')[0]
part2 = content.split('    if not collected_content:\n        log.info("[SocialPostAnalyzer] Finished - no post content could be extra')[1]

final_content = part1 + new_code + '\n    if not collected_content:\n        log.info("[SocialPostAnalyzer] Finished - no post content could be extra' + part2

with open('orchestrator/crm/social_post_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(final_content)
    
print('PATCHED')
