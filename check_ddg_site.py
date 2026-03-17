import asyncio, json
from orchestrator.osint.tools import ddg_search
print(json.dumps(asyncio.run(ddg_search('site:linkedin.com \"Narada Agastya Jiwanta\"', 5))))
