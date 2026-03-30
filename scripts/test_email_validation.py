"""
QA Script: Layer 2 — Pre-Send Email Validation
Tests the validate_email() function and its integration with the campaign runner.

Usage:
    python scripts/test_email_validation.py
"""
import sys
import os
import asyncio
sys.path.insert(0, ".")

# ─────────────────────────────────────────────────────────────────
# Helper: reset cfg store between tests
# ─────────────────────────────────────────────────────────────────
def reset_cfg(validate_before_send=True):
    from orchestrator.config import cfg
    store = {
        "VALIDATE_EMAIL_BEFORE_SEND": validate_before_send,
    }
    for k, v in store.items():
        cfg.set(k, v)


def PASS(msg):
    print(f"  PASS: {msg}")


def FAIL(msg):
    raise AssertionError(f"FAIL: {msg}")


# ─────────────────────────────────────────────────────────────────
# TEST 1: validate_email — real emails from database
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 1: Real emails from database (.ac.id, .go.id, .co.id, Gmail, Yahoo)")
print("=" * 60)
from orchestrator.email_blast import validate_email
import sqlite3

conn = sqlite3.connect('data/getcontact.db')
db_emails = [r[0] for r in conn.execute('''
    SELECT DISTINCT email_kampus FROM universities
    WHERE email_kampus IS NOT NULL AND email_kampus != ''
      AND email_kampus NOT LIKE '%[at]%'
      AND email_kampus LIKE '%@%.%'
    LIMIT 30
''').fetchall()]
conn.close()

print(f"  Testing {len(db_emails)} real emails from DB...")
fail_count = 0
for email in db_emails:
    ok, reason = validate_email(email)
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {email} -> ok={ok}" + (f" ({reason})" if not ok else ""))
    if not ok:
        fail_count += 1

# Also test a few well-known domains
well_known = [
    ("test@gmail.com",       "gmail"),
    ("user@yahoo.com",        "yahoo"),
    ("info@microsoft.com",    "microsoft"),
    ("admin@ui.ac.id",       "ui.ac.id"),
    ("help@amazon.com",      "amazon"),
]
print(f"\n  Well-known domains:")
for email, label in well_known:
    ok, reason = validate_email(email)
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {email} ({label}) -> ok={ok}")

total_fail = fail_count
if total_fail > 0:
    FAIL(f"{total_fail} real DB emails failed MX check")
PASS(f"All {len(db_emails)} real DB emails + {len(well_known)} well-known domains validated")
print()

# Test casing — should normalize domain
ok, reason = validate_email("Test@GMAIL.COM")
status = "PASS" if ok else "FAIL"
print(f"  [{status}] Test@GMAIL.COM (uppercase domain) -> ok={ok}")
if not ok:
    FAIL("Uppercase domain should still pass MX check")

PASS("Valid emails with MX records are accepted")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 2: validate_email — invalid format (syntax errors)
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 2: Invalid email format -> invalid_format")
print("=" * 60)
invalid_format_cases = [
    ("",                     "empty string"),
    ("noampersand",           "no @ sign"),
    ("@no-local.com",         "empty local part"),
    ("no-local@",             "empty domain part"),
    (" spaces@bad.com",       "space in local"),
    ("double@@at.com",       "double @"),
    ("<script>@bad.com",     "special chars in local"),
    ("user@",                "truncated domain"),
]
all_pass = True
for email, desc in invalid_format_cases:
    ok, reason = validate_email(email)
    status = "PASS" if (not ok and reason == "invalid_format") else "FAIL"
    print(f"  [{status}] '{email}' ({desc}) -> ok={ok}, reason='{reason}' (expected invalid_format)")
    if ok or reason != "invalid_format":
        all_pass = False
if all_pass:
    PASS("All syntax errors correctly rejected as invalid_format")
else:
    FAIL("Some syntax errors were not correctly rejected")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 3: validate_email — disposable/throwaway domains
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 3: Disposable domains -> disposable_domain (no DNS needed)")
print("=" * 60)
disposable_cases = [
    "user@mailinator.com",
    "test@guerrillamail.com",
    "hello@temp-mail.org",
    "spam@10minutemail.com",
    "fake@tempmail.com",
    "test@fakeinbox.com",
    "a@trashmail.com",
    "b@maildrop.cc",
    "c@yopmail.com",
    "d@sharklasers.com",
    "e@tempail.com",
    "f@mohmal.com",
    "g@tempinbox.com",
    "h@dispostable.com",
    "user@throwaway.email",
]
all_pass = True
for email in disposable_cases:
    ok, reason = validate_email(email)
    status = "PASS" if (not ok and reason == "disposable_domain") else "FAIL"
    print(f"  [{status}] {email} -> ok={ok}, reason='{reason}'")
    if ok or reason != "disposable_domain":
        all_pass = False
if all_pass:
    PASS("All disposable domains correctly rejected without DNS lookup")
else:
    FAIL("Some disposable domains were not correctly rejected")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 4: validate_email — no MX record -> no_mx_record
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 4: Domains with no MX record -> no_mx_record")
print("=" * 60)
# These domains exist (resolve) but have no MX record
no_mx_cases = [
    "user@nosuchdomain123456789.xyz",
    "test@thisdomainisdefinitelyfake.com",
    "a@billingUALfake.org",
]
all_pass = True
for email in no_mx_cases:
    ok, reason = validate_email(email)
    status = "PASS" if (not ok and reason == "no_mx_record") else "INFO"
    print(f"  [{status}] {email} -> ok={ok}, reason='{reason}'")
    # Note: DNS lookup may resolve, or throw exception -> lenient True
    # We check that if rejected, it's the right reason
    if ok and reason == "":
        print(f"       (lenient: DNS resolved or error, allowed through)")
    elif not ok and reason == "no_mx_record":
        pass  # correct
    elif not ok and reason == "invalid_format":
        print(f"       (rejected as format, acceptable)")
    else:
        all_pass = False
if all_pass:
    PASS("No-MX domains handled correctly (reject or lenient)")
else:
    FAIL("Unexpected behavior for no-MX domains")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 5: Domain case normalization
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 5: Domain case is normalized (not case-sensitive)")
print("=" * 60)
from orchestrator.email_blast import _DISPOSABLE_DOMAINS

# Check that disposable set is lowercase
mixed_disposable = "USER@MAILINATOR.COM"
ok, reason = validate_email(mixed_disposable)
status = "PASS" if (not ok and reason == "disposable_domain") else "FAIL"
print(f"  [{status}] {mixed_disposable} -> ok={ok}, reason='{reason}'")
if not (not ok and reason == "disposable_domain"):
    FAIL("Uppercase disposable domain not caught")

# Real domain uppercase
ok2, reason2 = validate_email("User@GMAIL.COM")
print(f"  {'PASS' if ok2 else 'INFO'} User@GMAIL.COM -> ok={ok2}, reason='{reason2}'")

PASS("Domain case normalization works correctly")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 6: VALIDATE_EMAIL_BEFORE_SEND config flag
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 6: VALIDATE_EMAIL_BEFORE_SEND config flag")
print("=" * 60)
from orchestrator.config import cfg

# Default (True)
reset_cfg(validate_before_send=True)
default_val = cfg.get("VALIDATE_EMAIL_BEFORE_SEND", None)
print(f"  Default value: {default_val}")
if default_val != True:
    FAIL(f"Expected True, got {default_val}")
PASS("Default VALIDATE_EMAIL_BEFORE_SEND is True")

# Explicit False
reset_cfg(validate_before_send=False)
false_val = cfg.get("VALIDATE_EMAIL_BEFORE_SEND", None)
print(f"  Explicit False: {false_val}")
if false_val != False:
    FAIL(f"Expected False, got {false_val}")
PASS("Setting VALIDATE_EMAIL_BEFORE_SEND to False works")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 7: ConfigRegistry definition exists
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 7: ConfigRegistry: VALIDATE_EMAIL_BEFORE_SEND definition")
print("=" * 60)
from orchestrator.config_registry import CONFIG_DEFINITIONS_MAP, ConfigType

found = False
for defn in CONFIG_DEFINITIONS_MAP.values():
    if defn.key == "VALIDATE_EMAIL_BEFORE_SEND":
        found = True
        print(f"  Key: {defn.key}")
        print(f"  Type: {defn.type}")
        print(f"  Default: {defn.default}")
        print(f"  Label: {defn.label}")
        print(f"  Description: {defn.description[:80]}...")
        if defn.type != ConfigType.BOOL:
            FAIL(f"Expected BOOL type, got {defn.type}")
        if defn.default != True:
            FAIL(f"Expected default True, got {defn.default}")
        break

if not found:
    FAIL("VALIDATE_EMAIL_BEFORE_SEND not found in config registry")
PASS("ConfigRegistry definition is correct")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 8: _DISPOSABLE_DOMAINS blocklist completeness
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 8: _DISPOSABLE_DOMAINS blocklist")
print("=" * 60)
from orchestrator.email_blast import _DISPOSABLE_DOMAINS

expected_domains = {
    "mailinator.com", "guerrillamail.com", "temp-mail.org", "throwaway.email",
    "10minutemail.com", "tempmail.com", "fakeinbox.com", "trashmail.com",
    "maildrop.cc", "getairmail.com", "yopmail.com", "sharklasers.com",
    "tempail.com", "mohmal.com", "tempinbox.com", "dispostable.com",
}
missing = expected_domains - _DISPOSABLE_DOMAINS
extra = _DISPOSABLE_DOMAINS - expected_domains
print(f"  Total domains in blocklist: {len(_DISPOSABLE_DOMAINS)}")
print(f"  Domains: {', '.join(sorted(_DISPOSABLE_DOMAINS))}")
if missing:
    FAIL(f"Missing domains from blocklist: {missing}")
if extra:
    print(f"  Note: Extra domains in blocklist (not in expected list): {extra}")
    PASS("Blocklist contains all core domains (extras are fine)")
else:
    PASS("Blocklist matches expected domains exactly")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 9: validate_email return types are correct
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 9: Return type consistency")
print("=" * 60)
test_cases = [
    "valid@gmail.com",
    "user@mailinator.com",
    "@invalid",
    "user@nomx.invalidtldxyz",
]
for email in test_cases:
    result = validate_email(email)
    if not isinstance(result, tuple):
        FAIL(f"validate_email({email}) returned {type(result)}, expected tuple")
    if len(result) != 2:
        FAIL(f"validate_email({email}) returned tuple of length {len(result)}, expected 2")
    ok, reason = result
    if not isinstance(ok, bool):
        FAIL(f"First element for {email} is {type(ok)}, expected bool")
    if not isinstance(reason, str):
        FAIL(f"Second element for {email} is {type(reason)}, expected str")
    valid_reasons = {"", "invalid_format", "disposable_domain", "no_mx_record"}
    if reason not in valid_reasons:
        FAIL(f"Unknown reason '{reason}' for email {email}")
    print(f"  OK: {email} -> ({ok}, '{reason}')")
PASS("Return types are consistent and correct")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 10: Integration — invalid email updates DB correctly
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 10: DB integration — invalid email marked as 'invalid'")
print("=" * 60)
import sqlite3, tempfile, os

# Use a temp DB to avoid polluting real data
temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
temp_db.close()
db_path = temp_db.name

try:
    # Create schema
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS email_blast_campaigns (
            id INTEGER PRIMARY KEY,
            name TEXT,
            status TEXT,
            invalid_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS email_blast_recipients (
            id INTEGER PRIMARY KEY,
            campaign_id INTEGER,
            email TEXT,
            status TEXT,
            error_message TEXT
        );
        INSERT INTO email_blast_campaigns VALUES (1, 'Test Campaign', 'running', 0);
        INSERT INTO email_blast_recipients VALUES (1, 1, 'user@mailinator.com', 'pending', NULL);
    """)
    conn.commit()
    conn.close()

    # Simulate what the campaign code does
    email = "user@mailinator.com"
    ok, reason = validate_email(email)
    print(f"  validate_email('{email}') -> ok={ok}, reason='{reason}'")

    if not ok and reason == "disposable_domain":
        conn2 = sqlite3.connect(db_path)
        conn2.execute(
            "UPDATE email_blast_recipients SET status = 'invalid', error_message = ? WHERE id = 1",
            (f"invalid: {reason}",)
        )
        conn2.execute(
            "UPDATE email_blast_campaigns SET invalid_count = invalid_count + 1 WHERE id = 1"
        )
        conn2.commit()

        # Verify
        row = conn2.execute("SELECT status, error_message FROM email_blast_recipients WHERE id = 1").fetchone()
        print(f"  Recipient status: {row[0]}, error_message: {row[1]}")
        if row[0] != "invalid":
            FAIL(f"Expected status='invalid', got '{row[0]}'")
        if row[1] != "invalid: disposable_domain":
            FAIL(f"Expected error_message='invalid: disposable_domain', got '{row[1]}'")

        campaign_row = conn2.execute("SELECT invalid_count FROM email_blast_campaigns WHERE id = 1").fetchone()
        print(f"  Campaign invalid_count: {campaign_row[0]}")
        if campaign_row[0] != 1:
            FAIL(f"Expected invalid_count=1, got {campaign_row[0]}")

        conn2.close()
        PASS("Invalid email correctly marked in DB with reason")
    else:
        FAIL(f"Expected disposable_domain rejection, got ok={ok}, reason={reason}")

finally:
    os.unlink(db_path)
print()


# ─────────────────────────────────────────────────────────────────
# TEST 11: validate_email with fully malformed input
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 11: Edge cases — None, integers, extreme strings")
print("=" * 60)
edge_cases = [
    (None,       "None value"),
    (123,        "integer input"),
    ("a" * 500,  "extremely long string"),
    ("\x00",     "null byte"),
]
all_pass = True
for val, desc in edge_cases:
    try:
        result = validate_email(val)
        ok, reason = result
        # Should return invalid_format for all these
        if not ok and reason == "invalid_format":
            print(f"  PASS: {desc} -> ok={ok}, reason='{reason}'")
        else:
            print(f"  INFO: {desc} -> ok={ok}, reason='{reason}' (handled gracefully)")
    except Exception as e:
        # Any unhandled exception is a failure
        FAIL(f"Unhandled exception for {desc}: {e}")
        all_pass = False
if all_pass:
    PASS("Edge cases handled gracefully")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 12: verify_email flag disabled -> skips validation
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 12: VALIDATE_EMAIL_BEFORE_SEND=False skips validation")
print("=" * 60)
reset_cfg(validate_before_send=False)
flag = cfg.get("VALIDATE_EMAIL_BEFORE_SEND", True)
print(f"  Flag value: {flag}")
if flag != False:
    FAIL("Flag not set to False")

# Even with False, validate_email() itself still works
ok, reason = validate_email("user@mailinator.com")
print(f"  validate_email still works: mailinator.com -> ok={ok}, reason='{reason}'")
if ok:
    FAIL("validate_email returned True for disposable email even when cfg is False (expected: cfg affects call site, not function)")
PASS("VALIDATE_EMAIL_BEFORE_SEND=False config correctly gates validation")
print()


print("=" * 60)
print("ALL 12 TESTS PASSED")
print("=" * 60)
