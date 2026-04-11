"""Smoke test: verify the LLM factory returns the right client per backend.

Does NOT make real network calls — checks that the Codex client and
real OpenAI client are different singletons and that the real client's
base_url points at api.openai.com.

Usage:
    PYTHONPATH=. python scripts/test_llm_factory.py
"""
from __future__ import annotations

import sys

from orchestrator.config import cfg
from orchestrator.llm import client_factory
from orchestrator.llm.codex_client import CodexClient


def main() -> int:
    passed = True

    # Real client should always be an AsyncOpenAI pointing at api.openai.com
    real_client = client_factory.get_real_client()
    real_url = str(real_client.base_url)
    if "api.openai.com" not in real_url:
        print(f"  FAIL: real client base_url={real_url} (expected api.openai.com)")
        passed = False
    else:
        print(f"  OK  real client     base_url={real_url}")

    # Codex client should be a CodexClient instance
    codex_client = client_factory.get_codex()
    if not isinstance(codex_client, CodexClient):
        print(f"  FAIL: get_codex() returned {type(codex_client).__name__}, expected CodexClient")
        passed = False
    else:
        from orchestrator.llm.codex_client import CODEX_BASE_URL
        print(f"  OK  codex client    upstream={CODEX_BASE_URL}")

    # Singleton check
    again = client_factory.get_codex()
    if again is not codex_client:
        print("  FAIL: get_codex() did not return a singleton")
        passed = False
    else:
        print("  OK  codex singleton stable across calls")

    print()
    if passed:
        print("ALL PASSED")
        return 0
    print("SOME CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
