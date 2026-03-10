"""
QA Test Script — OSINT & CRM Pipeline Verification
Runs individual tool tests + full pipeline test.
"""

import asyncio
import json
import os
import sys
import traceback

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_PATH", "data/getcontact.db")

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"

results = []


def record(name: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    results.append((name, ok, detail))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))


async def test_ddg_search():
    """Test DDG search works."""
    print("\n═══ 1. DDG Search ═══")
    from orchestrator.osint.tools import ddg_search

    hits = await ddg_search("Universitas Brawijaya", max_results=3)
    record("ddg_search returns results", len(hits) > 0, f"{len(hits)} results")
    if hits:
        first = hits[0]
        record("result has title", bool(first.get("title")), first.get("title", "")[:60])
        record("result has link", bool(first.get("link")), first.get("link", "")[:60])
        record("result has snippet", bool(first.get("snippet")), first.get("snippet", "")[:60])


async def test_pddikti_search():
    """Test PDDIKTI university search."""
    print("\n═══ 2. PDDIKTI University Search ═══")
    from orchestrator.osint.tools import pddikti_search_pt

    results_pt = await pddikti_search_pt("Universitas Brawijaya")
    record("pddikti_search_pt returns results", len(results_pt) > 0, f"{len(results_pt)} results")
    if results_pt:
        first = results_pt[0]
        record("result has nama", bool(first.get("nama")), str(first.get("nama", ""))[:60])


async def test_pddikti_dosen():
    """Test PDDIKTI dosen (lecturer) search."""
    print("\n═══ 3. PDDIKTI Dosen Search ═══")
    from orchestrator.osint.tools import pddikti_search_dosen, pddikti_get_dosen_profile, pddikti_get_dosen_study_history

    # Search for a common lecturer name
    dosen_list = await pddikti_search_dosen("Ahmad")
    record("pddikti_search_dosen returns results", len(dosen_list) > 0, f"{len(dosen_list)} results")

    if dosen_list:
        first = dosen_list[0]
        dosen_id = first.get("id") or first.get("id_sdm")
        record("dosen has id", bool(dosen_id), str(dosen_id)[:60])
        record("dosen has nama", bool(first.get("nama_dosen") or first.get("nama")),
               str(first.get("nama_dosen") or first.get("nama", ""))[:60])

        if dosen_id:
            # Test profile fetch
            profile = await pddikti_get_dosen_profile(dosen_id)
            record("get_dosen_profile works", profile is not None, str(profile)[:80] if profile else "None")

            # Test study history
            study = await pddikti_get_dosen_study_history(dosen_id)
            record("get_dosen_study_history works", study is not None, f"{len(study) if study else 0} entries")


async def test_fetch_page():
    """Test web page fetching."""
    print("\n═══ 4. Web Page Fetch ═══")
    from orchestrator.osint.tools import fetch_page, extract_text_from_html, extract_emails, extract_social_links

    html = await fetch_page("https://ub.ac.id")
    record("fetch_page returns HTML", bool(html), f"{len(html)} chars" if html else "empty")

    if html:
        text = extract_text_from_html(html)
        record("extract_text works", len(text) > 50, f"{len(text)} chars")

        emails = extract_emails(html)
        record("extract_emails runs", True, f"{len(emails)} emails found" + (f": {emails[:3]}" if emails else ""))

        socials = extract_social_links(html)
        record("extract_social_links runs", True, f"{len(socials)} links found")


async def test_gpt_extract():
    """Test GPT structured extraction."""
    print("\n═══ 5. GPT Extract Structured ═══")
    from orchestrator.osint.tools import gpt_extract_structured

    test_text = """
    Universitas Brawijaya terletak di Jl. Veteran, Malang, Jawa Timur.
    Rektor saat ini adalah Prof. Dr. Widodo, S.Si., M.Si.
    Email: info@ub.ac.id, Telp: (0341) 551611
    """

    result = await gpt_extract_structured(
        test_text,
        'Extract address, rector name, email, and phone. Return JSON: {"address": str, "rector": str, "email": str, "phone": str}'
    )
    record("gpt_extract returns JSON", result is not None, json.dumps(result, ensure_ascii=False)[:100] if result else "None")
    if result:
        record("extracted address", bool(result.get("address")), str(result.get("address", ""))[:60])
        record("extracted rector", bool(result.get("rector")), str(result.get("rector", ""))[:60])


async def test_gemini_research():
    """Test Gemini grounded research."""
    print("\n═══ 6. Gemini Research ═══")
    from orchestrator.osint.tools import gemini_research

    result = await gemini_research("Berita terbaru tentang Universitas Brawijaya 2025")
    if isinstance(result, dict):
        text = result.get("text", "")
        urls = result.get("urls", [])
        record("gemini_research returns text", bool(text), f"{len(text)} chars, {len(urls)} urls")
    else:
        record("gemini_research returns text", bool(result), f"{len(result)} chars" if result else "empty/None")


async def test_crm_identity_resolver():
    """Test CRM Identity Resolver agent directly."""
    print("\n═══ 7. CRM Identity Resolver ═══")
    from orchestrator.crm.identity_resolver import identity_resolver_agent
    from orchestrator.crm.state import CrmState

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

    result = await identity_resolver_agent(state)
    identity = result.get("identity")
    record("identity_resolver returns result", identity is not None)

    if identity:
        record("found full_name", bool(identity.full_name), str(identity.full_name)[:60])
        record("found pddikti_dosen_id", bool(identity.pddikti_dosen_id), str(identity.pddikti_dosen_id)[:60])
        record("found gender", bool(identity.gender), str(identity.gender))
        record("confidence > 0", identity.confidence > 0, f"{identity.confidence}")
        print(f"    Full identity: {identity.model_dump_json(indent=2)[:500]}")


async def test_crm_academic_profiler():
    """Test Academic Profiler with a known dosen."""
    print("\n═══ 8. CRM Academic Profiler ═══")
    from orchestrator.crm.academic_profiler import academic_profiler_agent
    from orchestrator.crm.state import CrmState, IdentityResult

    # First find a real dosen ID
    from orchestrator.osint.tools import pddikti_search_dosen
    dosen_list = await pddikti_search_dosen("Widodo Brawijaya")
    dosen_id = None
    if dosen_list:
        dosen_id = dosen_list[0].get("id") or dosen_list[0].get("id_sdm")

    identity = IdentityResult(
        full_name="Prof. Dr. Widodo",
        pddikti_dosen_id=dosen_id,
    )

    state: CrmState = {
        "request_id": 0,
        "university_id": None,
        "university_name": "Universitas Brawijaya",
        "pic_name": "Widodo",
        "pic_title": "Rektor",
        "faculty": None,
        "university_data": None,
        "existing_conversations": [],
        "identity": identity,
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

    result = await academic_profiler_agent(state)
    academic = result.get("academic")
    record("academic_profiler returns result", academic is not None)

    if academic:
        record("has education_history", len(academic.education_history) > 0, f"{len(academic.education_history)} entries")
        record("has teaching_subjects", len(academic.teaching_subjects) > 0, f"{len(academic.teaching_subjects)} subjects")
        record("has publications", len(academic.publications) > 0, f"{len(academic.publications)} pubs")
        record("confidence > 0", academic.confidence > 0, f"{academic.confidence}")


async def test_crm_social_profiler():
    """Test Social Profiler."""
    print("\n═══ 9. CRM Social Profiler ═══")
    from orchestrator.crm.social_profiler import social_profiler_agent
    from orchestrator.crm.state import CrmState, IdentityResult

    state: CrmState = {
        "request_id": 0,
        "university_id": None,
        "university_name": "Universitas Brawijaya",
        "pic_name": "Widodo",
        "pic_title": "Rektor",
        "faculty": None,
        "university_data": None,
        "existing_conversations": [],
        "identity": IdentityResult(full_name="Widodo"),
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

    result = await social_profiler_agent(state)
    social = result.get("social_profile")
    record("social_profiler returns result", social is not None)
    if social:
        found = sum([bool(social.linkedin_url), bool(social.instagram_handle),
                     bool(social.facebook_url), bool(social.twitter_handle)])
        record("found social accounts", found > 0, f"{found} platforms")


async def test_crm_campus_context():
    """Test Campus Context agent."""
    print("\n═══ 10. CRM Campus Context ═══")
    from orchestrator.crm.campus_context import campus_context_agent
    from orchestrator.crm.state import CrmState

    state: CrmState = {
        "request_id": 0,
        "university_id": None,
        "university_name": "Universitas Brawijaya",
        "pic_name": "Widodo",
        "pic_title": None,
        "faculty": "Fakultas Teknik",
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

    result = await campus_context_agent(state)
    ctx = result.get("campus_context")
    record("campus_context returns result", ctx is not None)
    if ctx:
        total = len(ctx.campus_problems) + len(ctx.campus_concerns) + len(ctx.campus_hopes)
        record("found campus info", total > 0, f"problems={len(ctx.campus_problems)}, concerns={len(ctx.campus_concerns)}, hopes={len(ctx.campus_hopes)}")


async def main():
    print("=" * 70)
    print("   OSINT & CRM Pipeline — QA Test Suite")
    print("=" * 70)

    # Run tool-level tests first
    tests = [
        ("DDG Search", test_ddg_search),
        ("PDDIKTI University", test_pddikti_search),
        ("PDDIKTI Dosen", test_pddikti_dosen),
        ("Web Fetch", test_fetch_page),
        ("GPT Extract", test_gpt_extract),
        ("Gemini Research", test_gemini_research),
        ("CRM Identity Resolver", test_crm_identity_resolver),
        ("CRM Academic Profiler", test_crm_academic_profiler),
        ("CRM Social Profiler", test_crm_social_profiler),
        ("CRM Campus Context", test_crm_campus_context),
    ]

    for name, test_fn in tests:
        try:
            await test_fn()
        except Exception as e:
            record(name, False, f"EXCEPTION: {e}")
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 70)
    print("   SUMMARY")
    print("=" * 70)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  {PASS}: {passed}    {FAIL}: {failed}    Total: {len(results)}")

    if failed > 0:
        print(f"\n  Failed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"    - {name}: {detail}")

    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
