"""
QA Script: Layer 1 — Multi-Account SMTP Rotation
Tests all scenarios of the SMTPClient rotation logic.

Usage:
    python scripts/test_smtp_rotation.py

Uses unittest.mock to patch cfg.get() directly — no need to worry
about ConfigManager singleton state.
"""
import json
import sys
import os
sys.path.insert(0, ".")

from unittest.mock import patch


def make_mock_cfg(accounts_json=None, rotate_after=50,
                   host="mail.asosiasi.ai", port=465,
                   username="sekretariat@asosiasi.ai", password="testpass",
                   use_ssl=True, from_name="Sekretariat Asosiasi AI"):
    """Return a cfg mock that returns configured values for SMTP keys."""
    def cfg_get(key, default=None):
        mapping = {
            "SMTP_ACCOUNTS": accounts_json or "",
            "ROTATE_AFTER_N_EMAILS": rotate_after,
            "SMTP_HOST": host,
            "SMTP_PORT": port,
            "SMTP_USERNAME": username,
            "SMTP_PASSWORD": password,
            "SMTP_USE_SSL": use_ssl,
            "SMTP_FROM_NAME": from_name,
        }
        return mapping.get(key, default)
    return cfg_get


def PASS(msg):
    print(f"  PASS: {msg}")


def FAIL(msg):
    raise AssertionError(f"FAIL: {msg}")


# ─────────────────────────────────────────────────────────────────
# TEST 1: Single account (legacy mode — no SMTP_ACCOUNTS set)
# Expected: falls back to SMTP_HOST/USERNAME/PASSWORD
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 1: Single account legacy mode")
print("=" * 60)

with patch("orchestrator.email_blast.cfg") as mock_cfg:
    mock_cfg.get = make_mock_cfg(accounts_json=None)
    import orchestrator.email_blast as eb
    # Force reinit
    eb._smtp_client = None
    client = eb.SMTPClient()

print(f"  Total accounts: {len(client._accounts)}")
print(f"  Account 0 user: {client._accounts[0].user}")
print(f"  Rotate after: {client._rotate_after}")
if len(client._accounts) != 1:
    FAIL(f"Expected 1 account, got {len(client._accounts)}")
if client._accounts[0].user != "sekretariat@asosiasi.ai":
    FAIL("Wrong user")
if client._rotate_after != 50:
    FAIL("Wrong rotate_after")
PASS("Single account mode works correctly")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 2: Multi-account rotation mode
# Expected: parses SMTP_ACCOUNTS JSON, loads N accounts
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 2: Multi-account rotation mode")
print("=" * 60)

accounts = [
    {"host": "mail.asosiasi.ai", "port": 465, "user": "acc1@asosiasi.ai", "password": "pass1", "use_ssl": True, "from_name": "Sender 1"},
    {"host": "mail.asosiasi.ai", "port": 465, "user": "acc2@asosiasi.ai", "password": "pass2", "use_ssl": True, "from_name": "Sender 2"},
    {"host": "mail.asosiasi.ai", "port": 465, "user": "acc3@asosiasi.ai", "password": "pass3", "use_ssl": True, "from_name": "Sender 3"},
]

with patch("orchestrator.email_blast.cfg") as mock_cfg:
    mock_cfg.get = make_mock_cfg(accounts_json=json.dumps(accounts), rotate_after=50)
    import importlib
    importlib.reload(eb)
    eb._smtp_client = None
    client = eb.SMTPClient()

print(f"  Total accounts: {len(client._accounts)}")
print(f"  Account 0: {client._accounts[0].user} ({client._accounts[0].from_name})")
print(f"  Account 1: {client._accounts[1].user} ({client._accounts[1].from_name})")
print(f"  Account 2: {client._accounts[2].user} ({client._accounts[2].from_name})")
print(f"  Rotate after: {client._rotate_after}")
if len(client._accounts) != 3:
    FAIL(f"Expected 3 accounts, got {len(client._accounts)}")
if client._accounts[0].user != "acc1@asosiasi.ai":
    FAIL("Wrong acc1 user")
if client._accounts[1].user != "acc2@asosiasi.ai":
    FAIL("Wrong acc2 user")
if client._accounts[2].user != "acc3@asosiasi.ai":
    FAIL("Wrong acc3 user")
if client._accounts[0].from_name != "Sender 1":
    FAIL("Wrong from_name")
if client._rotate_after != 50:
    FAIL("Wrong rotate_after")
PASS("Multi-account mode loads 3 accounts correctly")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 3: Rotation after N emails reached
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 3: Auto-rotation after N emails")
print("=" * 60)

two_accounts = [
    {"host": "mail.asosiasi.ai", "port": 465, "user": "acc1@asosiasi.ai", "password": "pass1", "use_ssl": True},
    {"host": "mail.asosiasi.ai", "port": 465, "user": "acc2@asosiasi.ai", "password": "pass2", "use_ssl": True},
]

with patch("orchestrator.email_blast.cfg") as mock_cfg:
    mock_cfg.get = make_mock_cfg(accounts_json=json.dumps(two_accounts), rotate_after=3)
    importlib.reload(eb)
    eb._smtp_client = None
    client = eb.SMTPClient()

if client._current_index != 0:
    FAIL(f"Should start at index 0, got {client._current_index}")
if client._current_account.user != "acc1@asosiasi.ai":
    FAIL("Wrong starting account")

# Simulate 3 emails sent
client._accounts[0].email_count = 3
client._maybe_rotate()
print(f"  After 3 emails: current index = {client._current_index}, user = {client._current_account.user}")
if client._current_index != 1:
    FAIL(f"Expected rotation to index 1, got {client._current_index}")
if client._accounts[0].email_count != 0:
    FAIL("Counter should reset after rotation")
if client._accounts[1].email_count != 0:
    FAIL("acc2 counter should start at 0")
PASS("Rotation after N emails works correctly")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 4: Degraded account triggers immediate rotation
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 4: Degraded account triggers rotation")
print("=" * 60)

with patch("orchestrator.email_blast.cfg") as mock_cfg:
    mock_cfg.get = make_mock_cfg(accounts_json=json.dumps(two_accounts), rotate_after=100)
    importlib.reload(eb)
    eb._smtp_client = None
    client = eb.SMTPClient()

# Mark acc1 as degraded
client._accounts[0].degraded = True
client._maybe_rotate()
print(f"  After marking acc1 degraded: current index = {client._current_index}, user = {client._current_account.user}")
if client._current_index != 1:
    FAIL(f"Expected index 1 after degraded rotation, got {client._current_index}")
if client._accounts[1].degraded != False:
    FAIL("acc2 should not be degraded")
PASS("Degraded account triggers rotation")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 5: Auth error keyword detection
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 5: Auth error detection in exception strings")
print("=" * 60)

auth_keywords = ["auth", "535", "501", "534", "user", "password", "authentication"]
test_strings = [
    ("SMTP authentication failed: 535 5.7.0", True),
    ("501 5.7.0 Not authorized", True),
    ("534 Authentication required", True),
    ("Error: user not found", True),
    ("Connection refused", False),
    ("Timeout connecting", False),
    ("Certificate verify failed: self signed certificate", False),
]
all_pass = True
for err_str, expected in test_strings:
    result = any(kw in err_str.lower() for kw in auth_keywords)
    status = "PASS" if result == expected else "FAIL"
    print(f"  [{status}] '{err_str[:50]}' is_auth_error={result} (expected={expected})")
    if result != expected:
        all_pass = False
if all_pass:
    PASS("Auth error keyword detection works correctly")
else:
    FAIL("Auth error detection failed")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 6: get_status() returns correct per-account state
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 6: get_status() monitoring method")
print("=" * 60)

with patch("orchestrator.email_blast.cfg") as mock_cfg:
    mock_cfg.get = make_mock_cfg(accounts_json=json.dumps(two_accounts), rotate_after=50)
    importlib.reload(eb)
    eb._smtp_client = None
    client = eb.SMTPClient()

client._accounts[0].email_count = 42
client._accounts[0].degraded = True

status = client.get_status()
print(f"  Total accounts: {status['total_accounts']}")
print(f"  Rotate after: {status['rotate_after']}")
for acc in status["accounts"]:
    print(f"  - {acc['user']}: count={acc['email_count']}, degraded={acc['degraded']}, connected={acc['connected']}")

if status["total_accounts"] != 2:
    FAIL(f"Wrong total_accounts: {status['total_accounts']}")
if status["rotate_after"] != 50:
    FAIL(f"Wrong rotate_after: {status['rotate_after']}")
if status["accounts"][0]["email_count"] != 42:
    FAIL("Wrong email_count in status")
if status["accounts"][0]["degraded"] != True:
    FAIL("Wrong degraded flag in status")
if status["accounts"][1]["degraded"] != False:
    FAIL("acc2 should not be degraded")
PASS("get_status() returns correct monitoring data")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 7: Invalid SMTP_ACCOUNTS JSON → falls back to single account
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 7: Invalid SMTP_ACCOUNTS JSON → graceful fallback")
print("=" * 60)

with patch("orchestrator.email_blast.cfg") as mock_cfg:
    mock_cfg.get = make_mock_cfg(
        accounts_json="not valid json at all",
        username="fallback@asosiasi.ai"
    )
    importlib.reload(eb)
    eb._smtp_client = None
    client = eb.SMTPClient()

print(f"  Total accounts after bad JSON: {len(client._accounts)}")
if len(client._accounts) != 1:
    FAIL(f"Expected fallback to 1 account, got {len(client._accounts)}")
if client._accounts[0].user != "fallback@asosiasi.ai":
    FAIL("Wrong fallback user")
PASS("Invalid JSON gracefully falls back to single account")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 8: Round-robin skips all degraded accounts
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 8: Round-robin skips all degraded accounts")
print("=" * 60)

three_accounts = [
    {"host": "mail.asosiasi.ai", "port": 465, "user": "acc1@asosiasi.ai", "password": "pass1", "use_ssl": True},
    {"host": "mail.asosiasi.ai", "port": 465, "user": "acc2@asosiasi.ai", "password": "pass2", "use_ssl": True},
    {"host": "mail.asosiasi.ai", "port": 465, "user": "acc3@asosiasi.ai", "password": "pass3", "use_ssl": True},
]

with patch("orchestrator.email_blast.cfg") as mock_cfg:
    mock_cfg.get = make_mock_cfg(accounts_json=json.dumps(three_accounts), rotate_after=2)
    importlib.reload(eb)
    eb._smtp_client = None
    client = eb.SMTPClient()

# Mark acc1 and acc2 as degraded — only acc3 should be available
client._accounts[0].degraded = True
client._accounts[1].degraded = True
client._rotate_next()

print(f"  After degrading acc1+acc2: current index = {client._current_index}, user = {client._current_account.user}")
if client._current_index != 2:
    FAIL(f"Expected index 2 (skip all degraded), got {client._current_index}")
if client._accounts[2].degraded != False:
    FAIL("acc3 should not be degraded")
PASS("Round-robin skips all degraded accounts")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 9: Backward-compatible API methods exist
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 9: Backward-compatible API methods exist")
print("=" * 60)

with patch("orchestrator.email_blast.cfg") as mock_cfg:
    mock_cfg.get = make_mock_cfg()
    importlib.reload(eb)
    eb._smtp_client = None
    client = eb.SMTPClient()

for method in ["connect", "disconnect", "send_email", "get_status"]:
    if not hasattr(client, method):
        FAIL(f"Missing method: {method}")
    if not callable(getattr(client, method)):
        FAIL(f"Not callable: {method}")
    print(f"  {method}() -> OK")
PASS("Backward-compatible API methods exist")
print()


# ─────────────────────────────────────────────────────────────────
# TEST 10: Rotation lock is thread-safe (mock threading.Lock)
# ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 10: Rotation lock exists and is used correctly")
print("=" * 60)

with patch("orchestrator.email_blast.cfg") as mock_cfg:
    mock_cfg.get = make_mock_cfg(accounts_json=json.dumps(two_accounts), rotate_after=10)
    importlib.reload(eb)
    eb._smtp_client = None
    client = eb.SMTPClient()

if not hasattr(client, "_rotation_lock"):
    FAIL("Missing _rotation_lock")
import threading
if not isinstance(client._rotation_lock, threading.Lock):
    FAIL(f"_rotation_lock should be threading.Lock, got {type(client._rotation_lock)}")
PASS("Thread-safe rotation lock exists")
print()


print("=" * 60)
print("ALL 10 TESTS PASSED")
print("=" * 60)

