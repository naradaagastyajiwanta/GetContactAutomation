"""Smoke test: exercise the LLM gateway routing + metrics (no network).

Uses monkey-patching on the CodexClient and the real AsyncOpenAI client
so the test can verify routing without making real API calls.

Scenarios:
    1. OAuth ON  + Codex 200            → codex_chat_calls++,  no fallback
    2. OAuth ON  + Codex 429            → cooldown armed, fallback_chat_calls++
    3. Cooldown active                  → direct path (no Codex attempt)
    4. OAuth OFF                        → direct_chat_calls++
    5. Embeddings call                  → direct_embeddings_calls++ regardless
    6. Responses path: OAuth ON 200     → codex_responses_calls++

Exits 0 on pass, 1 on any assertion failure.

Usage:
    PYTHONPATH=. python scripts/test_llm_gateway.py
"""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock

from orchestrator.config import cfg
from orchestrator.llm import client_factory, gateway
from orchestrator.llm.codex_client import CodexRateLimitError, CodexResponse


class Scenario:
    def __init__(self, name: str):
        self.name = name
        self.passed = True

    def check(self, label: str, actual, expected) -> None:
        ok = actual == expected
        self.passed &= ok
        marker = "OK  " if ok else "FAIL"
        print(f"    [{marker}] {label}: {actual} (expected {expected})")


async def run() -> int:
    passed = True

    cfg.set("CHATGPT_OAUTH_FALLBACK_TO_API", True)
    cfg.set("CHATGPT_OAUTH_RATE_LIMIT_COOLDOWN_SECONDS", 900)

    # ---- Scenario 1: Codex success on chat ----
    print("Scenario 1: Codex 200 (chat completions translation)")
    gateway.reset_metrics()
    gateway.reset_cooldown()
    cfg.set("CHATGPT_OAUTH_ENABLED", True)

    codex_client = client_factory.get_codex()
    fake_codex_response = CodexResponse({
        "id": "resp_test",
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": "Codex says hi"}],
        }],
        "usage": {"input_tokens": 5, "output_tokens": 3},
    })
    codex_client.responses_create = AsyncMock(return_value=fake_codex_response)

    real_client = client_factory.get_real_client()
    real_client.chat.completions.create = AsyncMock(return_value="real-fallback")

    result = await gateway.chat_completions_create(
        model="gpt-5.4",
        messages=[{"role": "user", "content": "hi"}],
    )
    s1 = Scenario("s1")
    s1.check("translated content", result.choices[0].message.content, "Codex says hi")
    s1.check("codex_chat_calls", gateway.get_metrics()["codex_chat_calls"], 1)
    s1.check("fallback_chat_calls", gateway.get_metrics()["fallback_chat_calls"], 0)
    passed &= s1.passed

    # ---- Scenario 2: Codex 429 → fallback + cooldown armed ----
    print("Scenario 2: Codex 429 -> fallback + cooldown armed")
    gateway.reset_metrics()
    gateway.reset_cooldown()

    codex_client.responses_create = AsyncMock(
        side_effect=CodexRateLimitError("rate limited", retry_after_seconds=60)
    )

    class FakeChatResponse:
        choices = [type("c", (), {"message": type("m", (), {"content": "fallback-ok"})()})()]
        usage = None

    real_client.chat.completions.create = AsyncMock(return_value=FakeChatResponse())

    result = await gateway.chat_completions_create(
        model="gpt-5.4",
        messages=[{"role": "user", "content": "hi"}],
    )
    m = gateway.get_metrics()
    s2 = Scenario("s2")
    s2.check("result content", result.choices[0].message.content, "fallback-ok")
    s2.check("codex_rate_limits", m["codex_rate_limits"], 1)
    s2.check("fallback_chat_calls", m["fallback_chat_calls"], 1)
    s2.check("cooldown armed", m["cooldown_remaining_seconds"] > 0, True)
    passed &= s2.passed

    # ---- Scenario 3: cooldown active -> direct, Codex NOT attempted ----
    print("Scenario 3: cooldown active -> direct, Codex NOT attempted")
    gateway.reset_metrics()
    # Do NOT reset cooldown — we want it still armed from scenario 2

    codex_client.responses_create = AsyncMock(return_value="SHOULD-NOT-BE-CALLED")
    real_client.chat.completions.create = AsyncMock(return_value=FakeChatResponse())

    result = await gateway.chat_completions_create(
        model="gpt-5.4",
        messages=[{"role": "user", "content": "hi"}],
    )
    m = gateway.get_metrics()
    s3 = Scenario("s3")
    s3.check("direct_chat_calls", m["direct_chat_calls"], 1)
    s3.check("codex_chat_calls (not attempted)", m["codex_chat_calls"], 0)
    codex_client.responses_create.assert_not_called()
    passed &= s3.passed

    # ---- Scenario 4: OAuth OFF -> direct ----
    print("Scenario 4: OAuth OFF -> direct")
    gateway.reset_metrics()
    gateway.reset_cooldown()
    cfg.set("CHATGPT_OAUTH_ENABLED", False)

    codex_client.responses_create = AsyncMock(return_value="SHOULD-NOT-BE-CALLED")
    real_client.chat.completions.create = AsyncMock(return_value=FakeChatResponse())

    await gateway.chat_completions_create(
        model="gpt-5.4",
        messages=[{"role": "user", "content": "hi"}],
    )
    m = gateway.get_metrics()
    s4 = Scenario("s4")
    s4.check("direct_chat_calls", m["direct_chat_calls"], 1)
    s4.check("codex_chat_calls", m["codex_chat_calls"], 0)
    codex_client.responses_create.assert_not_called()
    passed &= s4.passed

    # ---- Scenario 5: embeddings always direct ----
    print("Scenario 5: embeddings always direct (regardless of OAuth)")
    gateway.reset_metrics()
    gateway.reset_cooldown()
    cfg.set("CHATGPT_OAUTH_ENABLED", True)

    real_client.embeddings.create = AsyncMock(return_value="emb-ok")
    result = await gateway.embeddings_create(
        model="text-embedding-3-small", input="hello"
    )
    m = gateway.get_metrics()
    s5 = Scenario("s5")
    s5.check("result", result, "emb-ok")
    s5.check("direct_embeddings_calls", m["direct_embeddings_calls"], 1)
    passed &= s5.passed

    # ---- Scenario 6: responses path on Codex ----
    print("Scenario 6: responses_create routes to Codex")
    gateway.reset_metrics()
    gateway.reset_cooldown()
    cfg.set("CHATGPT_OAUTH_ENABLED", True)

    codex_client.responses_create = AsyncMock(return_value=fake_codex_response)
    result = await gateway.responses_create(
        model="gpt-5.4",
        input=[{"role": "user", "content": "hi"}],
    )
    m = gateway.get_metrics()
    s6 = Scenario("s6")
    s6.check("output_text", result.output_text, "Codex says hi")
    s6.check("codex_responses_calls", m["codex_responses_calls"], 1)
    passed &= s6.passed

    print()
    print("ALL PASSED" if passed else "SOME SCENARIOS FAILED")
    return 0 if passed else 1


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
