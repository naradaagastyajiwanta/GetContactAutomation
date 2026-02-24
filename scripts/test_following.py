"""Direct test of get_ig_following() with detailed logging."""
import sys
import os
import logging

# Enable verbose logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.instagram import get_ig_following, _ig_pool

print("=== IG Session Check ===")
session_id = _ig_pool.get_current_session_id()
print(f"Current session ID: {session_id}")

if not session_id:
    print("ERROR: No IG session available! get_ig_following will return empty.")
    sys.exit(1)

# Test with a known university IG handle
test_handle = "uadaceh"
print(f"\n=== Testing get_ig_following(@{test_handle}) ===")
following = get_ig_following(test_handle, max_results=50)
print(f"\nResults: {len(following)} accounts")
for f in following[:10]:
    print(f"  @{f['username']} - {f['full_name']} (verified={f['is_verified']})")
