"""QA script for Agent 4 BEM Discovery changes."""
import sys, os
sys.path.insert(0, r"c:\Users\narad\Programming\GetContactAI")

from orchestrator.instagram import find_related_accounts_from_following

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

results_log = []

def check(label, condition, note=""):
    status = PASS if condition else FAIL
    results_log.append((status, label, note))
    mark = "✓" if condition else "✗"
    print(f"  [{status}] {mark} {label}" + (f" — {note}" if note else ""))
    return condition

# ---------------------------------------------------------------------------
print("=" * 70)
print("TEST GROUP 1: Keyword ordering & type mapping")
print("=" * 70)

following_keyword_test = [
    # Tier 1 - fakultas prefix
    {"username": "fh_uad", "full_name": "Fakultas Hukum UAD", "is_verified": False},
    # Tier 2 - bem prefix
    {"username": "bem_uad", "full_name": "BEM UAD", "is_verified": False},
    # Tier 3 - senat prefix
    {"username": "senat_uad", "full_name": "Senat Mahasiswa UAD", "is_verified": False},
    # Tier 4 - humas prefix
    {"username": "humas_uad", "full_name": "Humas UAD", "is_verified": False},
    # pmb
    {"username": "pmb_uad", "full_name": "PMB UAD", "is_verified": False},
    # kemahasiswaan
    {"username": "kemahasiswaan_uad", "full_name": "Kemahasiswaan UAD", "is_verified": False},
    # alumni
    {"username": "alumni_uad", "full_name": "Alumni UAD", "is_verified": False},
    # lppm
    {"username": "lppm_uad", "full_name": "LPPM UAD", "is_verified": False},
]

res = find_related_accounts_from_following(
    following_keyword_test, "Universitas Ahmad Dahlan"
)
type_map = {r["handle"]: r["relation_type"] for r in res}

print()
check("T1-01: fh_ prefix → 'fakultas'", type_map.get("fh_uad") == "fakultas")
check("T1-02: bem_ prefix → 'bem'", type_map.get("bem_uad") == "bem")
check("T1-03: senat_ prefix → 'senat'", type_map.get("senat_uad") == "senat")
check("T1-04: humas prefix → 'humas'", type_map.get("humas_uad") == "humas")
check("T1-05: pmb_ prefix → 'pmb'", type_map.get("pmb_uad") == "pmb")
check("T1-06: kemahasiswaan → 'kemahasiswaan'", type_map.get("kemahasiswaan_uad") == "kemahasiswaan")
check("T1-07: alumni_ prefix → 'alumni'", type_map.get("alumni_uad") == "alumni")
check("T1-08: lppm prefix → 'lppm'", type_map.get("lppm_uad") == "lppm")

# Verify that if an account matches both fakultas AND bem keywords, fakultas wins
following_ambig = [
    {"username": "bemfhuad", "full_name": "BEM Fakultas Hukum UAD", "is_verified": False},
]
res_amb = find_related_accounts_from_following(
    following_ambig, "Universitas Ahmad Dahlan"
)
type_ambig = res_amb[0]["relation_type"] if res_amb else None
check(
    "T1-09: 'bemfh' contains 'bemfh' but also fh_ — fakultas tier wins?",
    type_ambig == "bem",  # bemfh** keyword is in BEM tier
    note=f"got={type_ambig} (expected bem because 'bemfhuad' has bem tier keyword 'bemfh')",
)

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("TEST GROUP 2: Hard filter — uni_marker requirement")
print("=" * 70)

# 2a: generic national BEM must be FILTERED
following_generic = [
    {"username": "bem_indonesia", "full_name": "BEM Indonesia Nasional", "is_verified": False},
    {"username": "bem_nasional", "full_name": "BEM Nasional", "is_verified": False},
]
res_gen = find_related_accounts_from_following(
    following_generic, "Universitas Ahmad Dahlan"
)
handles_gen = [r["handle"] for r in res_gen]
check("T2-01: @bem_indonesia NOT in results (no UAD marker)", "bem_indonesia" not in handles_gen)
check("T2-02: @bem_nasional NOT in results (no UAD marker)", "bem_nasional" not in handles_gen)

# 2b: specific accounts with uni acronym PASS
following_specific = [
    {"username": "bemuad", "full_name": "BEM Universitas Ahmad Dahlan", "is_verified": False},
    {"username": "bemuniversitasbrawijaya", "full_name": "BEM Brawijaya", "is_verified": False},
]
res_spec = find_related_accounts_from_following(
    following_specific, "Universitas Ahmad Dahlan"
)
handles_spec = [r["handle"] for r in res_spec]
check("T2-03: @bemuad PASSES hard filter (contains 'uad')", "bemuad" in handles_spec)
# bemuniversitasbrawijaya — does it contain 'uad'? No. Does it contain 'dahlan'? No.
# location_word='dahlan', unique_words=['ahmad','dahlan'] (len>2, not generic)
# 'dahlan' IS in 'universitas ahmad dahlan' check:
# Actually unique_words = [w for w in all_words if w not in generic and len(w)>2]
# all_words = ['universitas','ahmad','dahlan'] -> generic has 'universitas'
# unique_words = ['ahmad', 'dahlan']
# combined = 'bemuniversitasbrawijaya '
# 'ahmad' in combined? NO. 'dahlan' in combined? NO.
# location_word = 'dahlan' (last word) -> 'dahlan' in combined? NO
# uni_initials = 'uad' (3 chars) -> 'uad' in 'bemuniversitasbrawijaya '? NO
# So bemuniversitasbrawijaya should be FILTERED for UAD!
check(
    "T2-04: @bemuniversitasbrawijaya FILTERED for UAD (no UAD markers)",
    "bemuniversitasbrawijaya" not in handles_spec,
    note=f"handles_spec={handles_spec}",
)

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("TEST GROUP 3: Edge cases for hard filter")
print("=" * 70)

# 3a: 2-char initials (e.g., "UI" from "Universitas Indonesia")
# all_words = ['universitas', 'indonesia'] -> 'universitas' IS in generic -> unique_words = []
# location_word = 'indonesia' (last word, but it IS in generic so won't match clean)
# Wait: unique_words = [w for w in all_words if w not in _UNI_GENERIC_WORDS and len(w) > 2]
# 'indonesia' IS in _UNI_GENERIC_WORDS -> unique_words = []
# location_word = 'indonesia' (all_words[-1] when len>1) -> location_word = 'indonesia'
# len('indonesia') > 2 -> True -> check 'indonesia' in combined
# So for UI, only location_word fallback works IF 'indonesia' appears in username/bio

following_ui = [
    {"username": "bem_ui", "full_name": "BEM Universitas Indonesia", "is_verified": False},
    {"username": "senat_ui", "full_name": "Senat UI", "is_verified": False},
    {"username": "bem_univ", "full_name": "BEM Universitas", "is_verified": False},
]
res_ui = find_related_accounts_from_following(
    following_ui, "Universitas Indonesia"
)
handles_ui = [r["handle"] for r in res_ui]
print(f"  [INFO] UI test handles found: {handles_ui}")

# uni_initials = 'ui' (2 chars) -> len >= 3? NO -> first condition FAILS
# location_word = 'indonesia' -> 'indonesia' in 'bem_ui ' -> NO
# unique_words = [] (both words in generic) -> any() over empty = False
# ALL conditions FAIL -> bem_ui is FILTERED OUT!
check(
    "T3-01: @bem_ui FILTERED for 'Universitas Indonesia' (initials='ui' len<3, unique_words=[], 'indonesia' not in username)",
    "bem_ui" not in handles_ui,
    note=f"handles_ui={handles_ui} — WARNING: this may over-filter legitimate UI accounts",
)

# 3b: empty unique_words doesn't crash
try:
    find_related_accounts_from_following([], "Universitas Indonesia")
    check("T3-02: empty following list doesn't crash", True)
except Exception as e:
    check("T3-02: empty following list doesn't crash", False, note=str(e))

# 3c: unique_words is empty but location_word check still runs
following_loc = [
    {"username": "bem_bandung", "full_name": "BEM Institut Bandung", "is_verified": False},
]
res_loc = find_related_accounts_from_following(
    following_loc, "Institut Teknologi Bandung"
)
handles_loc = [r["handle"] for r in res_loc]
# uni_initials='itb' (3 chars) -> 'itb' in 'bem_bandung '? NO
# location_word='bandung' -> 'bandung' in 'bem_bandung '? YES -> PASSES
check(
    "T3-03: @bem_bandung PASSES for 'Institut Teknologi Bandung' via location_word",
    "bem_bandung" in handles_loc,
    note=f"handles_loc={handles_loc}",
)

# 3d: BEM standalone via split("_") — @bem_uad -> split('_') = ['bem','uad']
# must also pass hard filter first
following_standalone = [
    {"username": "bem_uad", "full_name": "", "is_verified": False},
]
res_st = find_related_accounts_from_following(
    following_standalone, "Universitas Ahmad Dahlan"
)
types_st = {r["handle"]: r["relation_type"] for r in res_st}
check(
    "T3-04: @bem_uad classified as 'bem' (standalone token detection)",
    types_st.get("bem_uad") == "bem",
    note=f"type={types_st.get('bem_uad')}",
)

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("TEST GROUP 4: BEM standalone detection doesn't conflict with hard filter")
print("=" * 70)

# bem_nasional passes standalone BEM detection, but hard filter should block it
following_conflict = [
    {"username": "bem_nasional", "full_name": "BEM Nasional Indonesia", "is_verified": False},
    {"username": "bem_univ_bandung", "full_name": "BEM Universitas Bandung", "is_verified": False},
]
res_conf = find_related_accounts_from_following(
    following_conflict, "Universitas Ahmad Dahlan"
)
handles_conf = [r["handle"] for r in res_conf]
check(
    "T4-01: Hard filter runs BEFORE standalone BEM detection (bem_nasional excluded)",
    "bem_nasional" not in handles_conf,
    note=f"handles={handles_conf}",
)

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("TEST GROUP 5: _MIN_CONFIDENCE threshold in bem_finder.py")
print("=" * 70)

# Simulate an account with confidence < 0.55 vs >= 0.55
# Base confidence = 0.3, + acronym 3-char = +0.35 -> 0.65 (PASSES)
# Base confidence = 0.3, no acronym, location_word (+0.15), unique_word (+0.15*1) = 0.60 (PASSES)
# Base confidence = 0.3, only unique_word = 0.30 + 0.15 = 0.45 (FAILS new threshold)

following_conf_test = [
    # High conf: acronym match (0.3 + 0.35 = 0.65)
    {"username": "bemuad", "full_name": "", "is_verified": False},
    # Low conf: only location word (0.3 + 0.15 = 0.45 < 0.55)
    {"username": "bem_yogyakarta", "full_name": "BEM", "is_verified": False},
]
res_ct = find_related_accounts_from_following(
    following_conf_test, "Universitas Ahmad Dahlan"
)
conf_map = {r["handle"]: r["confidence"] for r in res_ct}
print(f"  [INFO] Confidence map: {conf_map}")

# Check bemuad gets 0.65
check(
    "T5-01: @bemuad confidence = 0.65 (base 0.3 + acronym 0.35)",
    abs(conf_map.get("bemuad", 0) - 0.65) < 0.01,
    note=f"got={conf_map.get('bemuad')}",
)

# Check that bem_yogyakarta is filtered by hard filter too (no UAD marker)
check(
    "T5-02: @bem_yogyakarta filtered by hard filter (no UAD marker)",
    "bem_yogyakarta" not in conf_map,
    note=f"conf_map keys={list(conf_map.keys())}",
)

# Test with a UAD account that has only unique_word match
following_low = [
    {"username": "ahmad_infocenter", "full_name": "Ahmad", "is_verified": False},
]
res_low = find_related_accounts_from_following(
    following_low, "Universitas Ahmad Dahlan"
)
low_conf = [r["confidence"] for r in res_low]
print(f"  [INFO] ahmad_infocenter confidence: {low_conf}")
# Should either be filtered (no category match) or if matched, confidence would be ~0.45

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("TEST GROUP 6: _TYPE_QUERIES in search_related_accounts_via_search")
print("=" * 70)

# We can't easily call the async function here, but we can introspect the structure
import ast, inspect
from orchestrator import instagram as insta_mod

src = inspect.getsource(insta_mod.search_related_accounts_via_search)
check(
    "T6-01: 'fakultas' key present in _TYPE_QUERIES source",
    '"fakultas"' in src.lower() or "'fakultas'" in src.lower(),
)
check(
    "T6-02: 'senat' key present in _TYPE_QUERIES source",
    '"senat"' in src.lower() or "'senat'" in src.lower(),
)
# Check ordering: fakultas before bem in source
fak_pos = src.lower().find('"fakultas"')
bem_pos = src.lower().find('"bem"')
check(
    "T6-03: 'fakultas' appears before 'bem' in _TYPE_QUERIES (priority order)",
    fak_pos < bem_pos,
    note=f"fakultas@{fak_pos} bem@{bem_pos}",
)
senat_pos = src.lower().find('"senat"')
humas_pos = src.lower().find('"humas"')
check(
    "T6-04: 'senat' appears before 'humas' in _TYPE_QUERIES",
    senat_pos < humas_pos,
    note=f"senat@{senat_pos} humas@{humas_pos}",
)
# Verify prefixes[:1] pattern is used
check(
    "T6-05: 'prefixes[:1]' pattern present (1 query per type)",
    "prefixes[:1]" in src,
)
check(
    "T6-06: 'Fakultas' in prefixes list for 'fakultas' type",
    '"Fakultas"' in src,
)
check(
    "T6-07: 'Senat Mahasiswa' in prefixes for 'senat' type",
    '"Senat Mahasiswa"' in src,
)

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("TEST GROUP 7: _RELATION_KEYWORDS ordering in find_related_accounts_from_following")
print("=" * 70)

import inspect
src_follow = inspect.getsource(insta_mod.find_related_accounts_from_following)

fk_pos = src_follow.lower().find('"fakultas"')
bem_pos2 = src_follow.lower().find('"bem"')
senat_pos2 = src_follow.lower().find('"senat"')

check(
    "T7-01: 'fakultas' is first in _RELATION_KEYWORDS list",
    fk_pos < bem_pos2,
    note=f"fakultas@{fk_pos}, bem@{bem_pos2}",
)
check(
    "T7-02: 'bem' comes before 'senat' in _RELATION_KEYWORDS",
    bem_pos2 < senat_pos2,
    note=f"bem@{bem_pos2}, senat@{senat_pos2}",
)
check(
    "T7-03: 'fkip' in fakultas keywords (variation coverage)",
    '"fkip"' in src_follow or "'fkip'" in src_follow,
)
check(
    "T7-04: 'fisip' in fakultas keywords",
    '"fisip"' in src_follow or "'fisip'" in src_follow,
)
check(
    "T7-05: 'dpm_' in senat keywords",
    '"dpm_"' in src_follow or "'dpm_'" in src_follow,
)

# Also verify BIO_KEYWORDS contain 'fakultas' and 'senat'
check(
    "T7-06: 'fakultas' key in _BIO_KEYWORDS",
    '"fakultas"' in src_follow,
)
check(
    "T7-07: 'senat' key in _BIO_KEYWORDS",
    '"senat"' in src_follow,
)

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("TEST GROUP 8: Regression — existing types still classified correctly")
print("=" * 70)

following_regress = [
    {"username": "pmb_uad", "full_name": "PMB UAD", "is_verified": False},
    {"username": "kemahasiswaan_uad", "full_name": "Kemahasiswaan UAD", "is_verified": False},
    {"username": "alumni_uad", "full_name": "Alumni UAD", "is_verified": False},
    {"username": "lppm_uad", "full_name": "LPPM UAD", "is_verified": False},
]
res_regress = find_related_accounts_from_following(
    following_regress, "Universitas Ahmad Dahlan"
)
type_regress = {r["handle"]: r["relation_type"] for r in res_regress}

check("T8-01: pmb_ still → 'pmb'", type_regress.get("pmb_uad") == "pmb")
check("T8-02: kemahasiswaan_ still → 'kemahasiswaan'", type_regress.get("kemahasiswaan_uad") == "kemahasiswaan")
check("T8-03: alumni_ still → 'alumni'", type_regress.get("alumni_uad") == "alumni")
check("T8-04: lppm_ still → 'lppm'", type_regress.get("lppm_uad") == "lppm")

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)

passed = sum(1 for s, _, _ in results_log if s == PASS)
failed = sum(1 for s, _, _ in results_log if s == FAIL)
warned = sum(1 for s, _, _ in results_log if s == WARN)
total = len(results_log)

print(f"\nTotal: {total}  |  PASS: {passed}  |  FAIL: {failed}  |  WARN: {warned}")
print()

if failed:
    print("FAILED checks:")
    for s, label, note in results_log:
        if s == FAIL:
            print(f"  ✗ {label}" + (f" — {note}" if note else ""))
    print()
    print("VERDICT: ❌ Issues found — review before deploy")
else:
    print("VERDICT: ✅ All checks pass — safe to deploy")
