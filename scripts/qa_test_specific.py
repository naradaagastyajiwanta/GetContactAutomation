"""
Test CRM pipeline with a specific, well-known professor name.
"""
import asyncio, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_PATH", "data/getcontact.db")


async def test_specific_person():
    from orchestrator.crm.identity_resolver import identity_resolver_agent
    from orchestrator.crm.academic_profiler import academic_profiler_agent
    from orchestrator.crm.social_profiler import social_profiler_agent
    from orchestrator.crm.campus_context import campus_context_agent
    from orchestrator.crm.personal_interest import personal_interest_agent
    from orchestrator.crm.family_info import family_info_agent
    from orchestrator.crm.profile_compiler import profile_compiler_agent
    from orchestrator.crm.state import CrmState

    # Test with a specific name
    state: CrmState = {
        "request_id": 0,
        "university_id": None,
        "university_name": "Universitas Brawijaya",
        "pic_name": "Widodo",
        "pic_title": "Rektor",
        "faculty": None,
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

    agents = [
        ("Identity Resolver", identity_resolver_agent),
        ("Academic Profiler", academic_profiler_agent),
        ("Social Profiler", social_profiler_agent),
        ("Campus Context", campus_context_agent),
        ("Personal Interest", personal_interest_agent),
        ("Family Info", family_info_agent),
        ("Profile Compiler", profile_compiler_agent),
    ]

    for i, (name, agent_fn) in enumerate(agents, 1):
        print(f"\n{'='*60}")
        print(f"  Step {i}: {name}")
        print(f"{'='*60}")
        try:
            result = await agent_fn(state)
            state.update(result)
            state["agents_completed"].append(name)

            # Print key results
            if name == "Identity Resolver" and state.get("identity"):
                id_ = state["identity"]
                print(f"  Name: {id_.full_name}")
                print(f"  NIDN: {id_.nidn}")
                print(f"  Gender: {id_.gender}")
                print(f"  Birth: {id_.birth_date} (age: {id_.age})")
                print(f"  Origin: {id_.origin_region} ({id_.origin_region_source})")
                print(f"  Confidence: {id_.confidence}")
                print(f"  Sources: {id_.sources}")

            elif name == "Academic Profiler" and state.get("academic"):
                ac = state["academic"]
                print(f"  Jabatan: {ac.jabatan_akademik}")
                print(f"  Pendidikan: {ac.pendidikan_tertinggi}")
                print(f"  Education: {len(ac.education_history)} entries")
                for e in ac.education_history:
                    print(f"    - {e.get('jenjang')} @ {e.get('nama_pt')} ({e.get('tahun_lulus')})")
                print(f"  Subjects: {len(ac.teaching_subjects)} — {ac.teaching_subjects[:5]}")
                print(f"  Research: {ac.research_topics[:5]}")
                print(f"  Publications: {len(ac.publications)}")
                print(f"  Confidence: {ac.confidence}")

            elif name == "Social Profiler" and state.get("social_profile"):
                sp = state["social_profile"]
                print(f"  LinkedIn: {sp.linkedin_url}")
                print(f"  Instagram: {sp.instagram_handle}")
                print(f"  Facebook: {sp.facebook_url}")
                print(f"  Twitter: {sp.twitter_handle}")
                print(f"  Other: {dict(sp.other_social)}")
                print(f"  Confidence: {sp.confidence}")

            elif name == "Campus Context" and state.get("campus_context"):
                cc = state["campus_context"]
                print(f"  Problems: {cc.campus_problems[:3]}")
                print(f"  Concerns: {cc.campus_concerns[:3]}")
                print(f"  Hopes: {cc.campus_hopes[:3]}")
                print(f"  News: {cc.recent_news[:3]}")

            elif name == "Personal Interest" and state.get("personal_interest"):
                pi = state["personal_interest"]
                print(f"  Hobbies: {pi.hobbies}")
                print(f"  Food: {pi.favorite_food}")
                print(f"  Activities: {pi.outside_activities}")
                print(f"  Traits: {pi.personality_traits}")
                print(f"  Confidence: {pi.confidence}")

            elif name == "Family Info" and state.get("family_info"):
                fi = state["family_info"]
                print(f"  Status: {fi.marital_status}")
                print(f"  Spouse: {fi.spouse_name}")
                print(f"  Children: {fi.children_count}")
                print(f"  Residence: {fi.family_residence}")
                print(f"  Confidence: {fi.confidence}")

            elif name == "Profile Compiler" and state.get("compiled_profile"):
                cp = state["compiled_profile"]
                print(f"  Fields: {cp.fields_found}/{cp.fields_total}")
                print(f"  Manual: {cp.fields_manual}")
                print(f"  Gaps: {cp.gaps}")
                print(f"  Confidence: {cp.overall_confidence}")
                print(f"\n  --- All Found Fields ---")
                for f in cp.fields:
                    if f.status != "not_found":
                        val = str(f.value)[:100] if f.value else ""
                        print(f"  [{f.status:12s}] {f.field_name}: {val}")

        except Exception as e:
            state["agents_failed"].append(name)
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"  FINAL: {len(state['agents_completed'])}/7 completed, {len(state['agents_failed'])} failed")
    cp = state.get("compiled_profile")
    if cp:
        print(f"  Profile: {cp.fields_found}/{cp.fields_total} fields, confidence={cp.overall_confidence}")


if __name__ == "__main__":
    asyncio.run(test_specific_person())
