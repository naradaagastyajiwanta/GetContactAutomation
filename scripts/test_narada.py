import asyncio, os, sys
os.environ.setdefault("DATABASE_PATH", "data/getcontact.db")

async def test_narada():
    from orchestrator.db import init_db
    from orchestrator.crm.graph import run_crm_graph
    await init_db()

    state = {
        "request_id": 999,
        "university_id": 999,
        "university_name": "Universitas Jember", # I'll assume Jember since that's what was mentioned in Abdi, wait Narada doesn't have one in my memory. Let's just use "Universitas Indonesia"
        "pic_name": "Narada Agastya Jiwanta",
        "pic_title": "Dosen",
        "faculty": None,
        "existing_conversations": [],
    }

    try:
        final_state = await run_crm_graph(state)
        
        prof = final_state.get('compiled_profile')
        if prof:
            print("--- FINAL COMPILED PROFILE ---")
            print(f"Name: {prof.full_name.value}")
            hobbies = next((f.value for f in prof.fields if f.field_name == 'hobbies'), None)
            campus_problems = next((f.value for f in prof.fields if f.field_name == 'campus_problems'), None)
            marital_status = next((f.value for f in prof.fields if f.field_name == 'marital_status'), None)
            
            print(f"Hobbies: {hobbies}")
            print(f"Campus Problems: {campus_problems}")
            print(f"Marital Status: {marital_status}")
        else:
            print("No compiled profile returned")

    except Exception as e:
        import traceback; traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_narada())