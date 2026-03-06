#!/usr/bin/env python3
"""Test if synced session works on server."""
import sys
sys.path.insert(0, "/app")
from orchestrator.playwright_ig import _verify_session_impl

r = _verify_session_impl("sekretariataaii_1", "dummy")
print(f"Status: {r['status']}")
print(f"Reason: {r.get('reason', 'N/A')}")
print(f"Username verified: {r.get('username_verified', 'N/A')}")
cookies = r.get("cookies", {})
print(f"Cookies: ds_user_id={cookies.get('ds_user_id', 'NONE')}, sessionid={'YES' if cookies.get('sessionid') else 'NONE'}")
