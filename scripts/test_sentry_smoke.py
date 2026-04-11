"""Smoke test: send 3 deliberate events to Sentry to verify integration.

Usage:

    # Required env vars
    export SENTRY_DSN="https://<public-key>@oXXX.ingest.sentry.io/YYY"
    export SENTRY_ENVIRONMENT="local-test"      # optional, default "production"
    export SENTRY_TRACES_SAMPLE_RATE="0.1"      # optional

    PYTHONPATH=. python scripts/test_sentry_smoke.py

Then check https://<your-org>.sentry.io/issues/ within ~30 seconds.

The script intentionally exercises:
  1. ``capture_message`` — verifies basic event transport
  2. ``capture_exception`` with tags — verifies error capture + tag
     attachment
  3. ``capture_exception`` with PII in the message — verifies the
     ``_before_send`` scrubber masks emails + Indonesian phone numbers
     before the event leaves the process

If env var ``SENTRY_DSN`` is empty, the script exits with a clear
message instead of silently no-op.
"""
from __future__ import annotations

import os
import sys

from orchestrator.observability import capture_exception, init_sentry


def main() -> int:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        print("ERROR: SENTRY_DSN env var is empty. Set it and re-run:")
        print('  export SENTRY_DSN="https://<public-key>@oXXX.ingest.sentry.io/YYY"')
        return 1

    print(f"Initializing Sentry (DSN ends with ...{dsn[-24:]})")
    active = init_sentry(release=os.getenv("SENTRY_RELEASE", "smoke-test"))
    if not active:
        print("FAIL: init_sentry returned False — check SENTRY_DSN format")
        return 1

    import sentry_sdk
    client = sentry_sdk.Hub.current.client
    print(f"  Environment: {client.options['environment']}")
    print(f"  Release:     {client.options['release']}")
    print(f"  PII:         send_default_pii={client.options['send_default_pii']} (expect False)")
    print()

    # --- Event 1: plain message -----------------------------------------
    print("[1/3] capture_message — plain info event")
    eid1 = sentry_sdk.capture_message(
        "GetContactAI Sentry smoke test — capture_message",
        level="info",
    )
    print(f"  event_id={eid1}")

    # --- Event 2: tagged exception --------------------------------------
    print("[2/3] capture_exception — tagged error")
    try:
        raise ValueError("GetContactAI Sentry smoke test — tagged ValueError")
    except ValueError as e:
        capture_exception(
            e,
            component="observability-smoke-test",
            kind="tagged_error",
            phase="1",
        )
    print("  captured")

    # --- Event 3: PII scrubbing ------------------------------------------
    print("[3/3] capture_exception — PII scrub test (should be masked)")
    try:
        raise RuntimeError(
            "Contact smoke-test@example.com at 081234567890 — PII must be masked"
        )
    except RuntimeError as e:
        capture_exception(e, component="pii-scrub-test")
    print("  captured (verify masked in Sentry dashboard)")
    print()

    # Flush so all events are uploaded before we exit
    print("Flushing Sentry queue (up to 5s)...")
    client.flush(timeout=5.0)
    print("  flushed")
    print()
    print("SUCCESS — 3 events sent. Check your Sentry dashboard within ~30s.")
    print("  - #1 info: 'GetContactAI Sentry smoke test'")
    print("  - #2 error: tagged ValueError (tags: component, kind, phase)")
    print("  - #3 error: PII scrub test — 'smoke-test@example.com' and")
    print("    '081234567890' should be shown as '[email-redacted]' and")
    print("    '[phone-redacted]' respectively")
    return 0


if __name__ == "__main__":
    sys.exit(main())
