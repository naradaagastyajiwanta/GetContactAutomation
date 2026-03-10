"""
Full CRM Pipeline — End-to-End Test
Runs all 7 agents sequentially simulating the real pipeline.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_PATH", "data/getcontact.db")


async def test_full_crm_pipeline():
    from orchestrator.crm.identity_resolver import identity_resolver_agent
    from orchestrator.crm.academic_profiler import academic_profiler_agent
    from orchestrator.crm.social_profiler import social_profiler_agent
    from orchestrator.crm.campus_context import campus_context_agent
    from orchestrator.crm.personal_interest import personal_interest_agent
    from orchestrator.crm.family_info import family_info_agent
    from orchestrator.crm.profile_compiler import profile_compiler_agent
    from orchestrator.crm.state import CrmState

    state: CrmState = {
        "request_id": 0,
        "university_id": None,
        "university_name": "Universitas Brawijaya",
        "pic_name": "Widodo",
        "pic_title": "Rektor",
        "faculty": "Fakultas MIPA",
        "university_data": None,
        "existing_conversations": [],
        "identity": None,
        "academic": None,
        "social_profile": None,
        "campus_context": None,
        "personal_interest": None,
        "family_info": None,
        "compiled_profile": None,
        "run_id": 0,
        "agents_completed": [],
        "agents_failed": [],
        "error": None,
    }

    print("=== Step 1: Identity Resolver ===")
    try:
        result = await identity_resolver_agent(state)
        state.update(result)
        state["agents_completed"].append("identity_resolver")
        id_res = state["identity"]
        print(f"  Name: {id_res.full_name}, NIDN: {id_res.nidn}, Gender: {id_res.gender}, Confidence: {id_res.confidence}")
        print(f"  Origin: {id_res.origin_region} ({id_res.origin_region_source})")
        print(f"  Sources: {id_res.sources}")
    except Exception as e:
        state["agents_failed"].append("identity_resolver")
        print(f"  FAILED: {e}")

    print("\n=== Step 2: Academic Profiler ===")
    try:
        result = await academic_profiler_agent(state)
        state.update(result)
        state["agents_completed"].append("academic_profiler")
        acad = state["academic"]
        print(f"  Education: {len(acad.education_history)} entries")
        for e in acad.education_history:
            print(f"    - {e}")
        print(f"  Teaching subjects: {len(acad.teaching_subjects)}")
        for s in acad.teaching_subjects[:5]:
            print(f"    - {s}")
        print(f"  Publications: {len(acad.publications)}")
        for p in acad.publications[:3]:
            print(f"    - {p}")
        print(f"  Confidence: {acad.confidence}")
    except Exception as e:
        state["agents_failed"].append("academic_profiler")
        print(f"  FAILED: {e}")

    print("\n=== Step 3: Social Profiler ===")
    try:
        result = await social_profiler_agent(state)
        state.update(result)
        state["agents_completed"].append("social_profiler")
        soc = state["social_profile"]
        print(f"  LinkedIn: {soc.linkedin_url}")
        print(f"  Instagram: {soc.instagram_handle}")
        print(f"  Facebook: {soc.facebook_url}")
        print(f"  Twitter: {soc.twitter_handle}")
        print(f"  Confidence: {soc.confidence}")
    except Exception as e:
        state["agents_failed"].append("social_profiler")
        print(f"  FAILED: {e}")

    print("\n=== Step 4: Campus Context ===")
    try:
        result = await campus_context_agent(state)
        state.update(result)
        state["agents_completed"].append("campus_context")
        ctx = state["campus_context"]
        print(f"  Problems: {ctx.campus_problems[:2]}")
        print(f"  Concerns: {ctx.campus_concerns[:2]}")
        print(f"  Hopes: {ctx.campus_hopes[:2]}")
        print(f"  News: {ctx.recent_news[:2]}")
    except Exception as e:
        state["agents_failed"].append("campus_context")
        print(f"  FAILED: {e}")

    print("\n=== Step 5: Personal Interest ===")
    try:
        result = await personal_interest_agent(state)
        state.update(result)
        state["agents_completed"].append("personal_interest")
        pi = state["personal_interest"]
        print(f"  Hobbies: {pi.hobbies}")
        print(f"  Favorite food: {pi.favorite_food}")
        print(f"  Outside activities: {pi.outside_activities}")
        print(f"  Personality: {pi.personality_traits}")
        print(f"  Confidence: {pi.confidence}")
    except Exception as e:
        state["agents_failed"].append("personal_interest")
        print(f"  FAILED: {e}")

    print("\n=== Step 6: Family Info ===")
    try:
        result = await family_info_agent(state)
        state.update(result)
        state["agents_completed"].append("family_info")
        fam = state["family_info"]
        print(f"  Marital status: {fam.marital_status}")
        print(f"  Spouse: {fam.spouse_name}")
        print(f"  Children: {fam.children_count}")
        print(f"  Residence: {fam.family_residence}")
        print(f"  Confidence: {fam.confidence}")
    except Exception as e:
        state["agents_failed"].append("family_info")
        print(f"  FAILED: {e}")

    print("\n=== Step 7: Profile Compiler ===")
    try:
        result = await profile_compiler_agent(state)
        state.update(result)
        state["agents_completed"].append("profile_compiler")
        profile = state["compiled_profile"]
        print(f"  Profile compiled: {bool(profile)}")
        if profile:
            print(f"  Fields found: {profile.fields_found}/{profile.fields_total}")
            print(f"  Needs manual: {profile.fields_manual}")
            print(f"  Gaps: {profile.gaps}")
            print(f"  Overall confidence: {profile.overall_confidence}")
            for f in profile.fields:
                if f.status != 'not_found':
                    val = str(f.value)[:80] if f.value else ''
                    print(f"    [{f.status}] {f.field_name}: {val}")
    except Exception as e:
        state["agents_failed"].append("profile_compiler")
        print(f"  FAILED: {e}")

    print("\n" + "=" * 60)
    completed = state["agents_completed"]
    failed = state["agents_failed"]
    print(f"  Completed ({len(completed)}): {completed}")
    print(f"  Failed ({len(failed)}): {failed}")
    print(f"  Success rate: {len(completed)}/{len(completed) + len(failed)}")
    return len(failed) == 0


if __name__ == "__main__":
    ok = asyncio.run(test_full_crm_pipeline())
    sys.exit(0 if ok else 1)
