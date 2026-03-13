import asyncio
import os
from dotenv import load_dotenv

# Load explicitly
load_dotenv('.env')

import openai
openai.api_key = os.getenv("OPENAI_API_KEY")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") or ''

from orchestrator.crm.social_profiler import social_profiler_agent
from orchestrator.crm.state import CrmState

async def test():
    state = CrmState()
    state["target_info"] = {
        "full_name": "Narada Agastya Jiwanta",
        "name_variants": ["Narada", "Agastya"],
        "university": "",
        "nidn": None,
        "role": []
    }
    state["cleaned_name"] = "Narada Agastya Jiwanta"
    state["name_variants"] = ["Narada Agastya", "Narada Jiwanta"]
    
    res = await social_profiler_agent(state)
    print("================ RESULT ================")
    if "social_profile" in res:
        print(res["social_profile"].dict())
    else:
        print(res)

if __name__ == "__main__":
    asyncio.run(test())
