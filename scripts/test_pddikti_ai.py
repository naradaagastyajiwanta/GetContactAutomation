"""Quick test: reproduce the PDDIKTI AI matching decision."""
import asyncio
import json
import sys
sys.path.insert(0, "/app")
from orchestrator.crm.tools import gpt_extract_structured

async def main():
    candidates = (
        "[1] Name: DWI PERWITASARI WIRYANINGTYAS, "
        "University: UNIVERSITAS JEMBER (UNEJ), NIDN: 0719088803"
    )

    # --- TEST 1: Current prompt (strict) ---
    prompt_strict = (
        "We're looking for a lecturer named 'DR. DWI PERWITASARI WIRYANINGTYAS, SE., MM' "
        "(role: Wakil Dekan) at 'UNIVERSITAS ABDURACHMAN SALEH SITUBONDO'.\n"
        "From the PDDIKTI results below, which one is the correct person?\n"
        "Consider: name similarity, university match, and role context.\n"
        'Return JSON: {"best_index": <1-based index or null>, '
        '"confidence": <0.0-1.0>, "reason": "..."}\n'
        "Return null for best_index if NONE match."
    )

    # --- TEST 2: Softened prompt (explains PDDIKTI home institution) ---
    prompt_soft = (
        "We're looking for a lecturer named 'DR. DWI PERWITASARI WIRYANINGTYAS, SE., MM' "
        "(role: Wakil Dekan) at 'UNIVERSITAS ABDURACHMAN SALEH SITUBONDO'.\n"
        "From the PDDIKTI results below, which one is the correct person?\n\n"
        "IMPORTANT: In Indonesian academia, PDDIKTI lists a lecturer's HOME institution "
        "(where they are formally registered), which may DIFFER from where they currently "
        "serve. A lecturer registered at University A can hold positions (Dekan, Wakil Dekan, "
        "Dosen Tamu, etc.) at University B. Therefore:\n"
        "- NAME MATCH is the PRIMARY criterion\n"
        "- University match is a SOFT signal (bonus, not requirement)\n"
        "- If the name matches well but university differs, still accept with moderate confidence\n\n"
        'Return JSON: {"best_index": <1-based index or null>, '
        '"confidence": <0.0-1.0>, "reason": "..."}\n'
        "Return null for best_index ONLY if the name clearly does not match any candidate."
    )

    print("=== TEST 1: STRICT (current) ===")
    r1 = await gpt_extract_structured(candidates, prompt_strict)
    print(json.dumps(r1, indent=2, ensure_ascii=False))

    print("\n=== TEST 2: SOFT (proposed fix) ===")
    r2 = await gpt_extract_structured(candidates, prompt_soft)
    print(json.dumps(r2, indent=2, ensure_ascii=False))

    # --- TEST 3: Pre-cleaned name (strip titles before passing to AI) ---
    prompt_clean = (
        "We're looking for a lecturer named 'DWI PERWITASARI WIRYANINGTYAS' "
        "(role: Wakil Dekan) at 'UNIVERSITAS ABDURACHMAN SALEH SITUBONDO'.\n"
        "From the PDDIKTI results below, which one is the correct person?\n\n"
        "IMPORTANT: In Indonesian academia, PDDIKTI lists a lecturer's HOME institution "
        "(where they are formally registered), which may DIFFER from where they currently "
        "serve. A lecturer registered at University A can hold positions (Dekan, Wakil Dekan, "
        "Dosen Tamu, etc.) at University B. Therefore:\n"
        "- NAME MATCH is the PRIMARY criterion\n"
        "- University match is a SOFT signal (bonus, not requirement)\n"
        "- If the name matches well but university differs, still accept with moderate confidence\n\n"
        'Return JSON: {"best_index": <1-based index or null>, '
        '"confidence": <0.0-1.0>, "reason": "..."}\n'
        "Return null for best_index ONLY if the name clearly does not match any candidate."
    )
    print("\n=== TEST 3: SOFT + CLEANED NAME ===")
    r3 = await gpt_extract_structured(candidates, prompt_clean)
    print(json.dumps(r3, indent=2, ensure_ascii=False))

asyncio.run(main())
