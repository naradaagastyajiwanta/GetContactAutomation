with open("orchestrator/osint/tools.py", "r") as f:
    text = f.read()
text = text.replace("if pt_html and len(pt_html) > 500:", "if pt_html and '<html' in pt_html.lower() and len(pt_html) > 500:")
with open("orchestrator/osint/tools.py", "w") as f:
    f.write(text)
