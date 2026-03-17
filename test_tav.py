import asyncio
from orchestrator.osint.tavily_client import tavily_deep_search
print(asyncio.run(tavily_deep_search('\
Narada
Agastya
Jiwanta\ Indonesia', 5)))
