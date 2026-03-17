with open('orchestrator/crm/social_post_analyzer.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("\\'", "'")

with open('orchestrator/crm/social_post_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(text)
