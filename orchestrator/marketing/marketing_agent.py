"""
Marketing Agent entry point.
Wires memory loading, orchestrator agent, and result reporting together.
Called by orchestration.py._run_full_search().
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from orchestrator.config import log
from .mkt_memory import get_client_episodic_memory, get_long_term_context
from .mkt_orchestrator import MarketingOrchestratorAgent, OrchestratorResult


@dataclass
class RunResult:
    contacts_recorded: list[dict] = field(default_factory=list)
    ig_handle: str | None = None
    sub_agent_calls: list[dict] = field(default_factory=list)
    tools_that_worked: list[str] = field(default_factory=list)
    tools_that_failed: list[str] = field(default_factory=list)
    status: str = "not_found"   # "found" | "partial" | "not_found" | "error"
    summary: str = ""
    total_tokens: int = 0
    duration_seconds: float = 0.0
    error_message: str | None = None


async def run_discovery(
    client: dict,
    run_id: int,
    mode: str = "full_search",
) -> RunResult:
    """
    Main entry point called by orchestration.py._run_full_search().

    1. Loads episodic memory (previous runs for this client)
    2. Loads long-term context (group strategy + global lessons)
    3. Runs MarketingOrchestratorAgent
    4. Returns RunResult
    """
    client_id = int(client["id"])
    group_id = int(client.get("group_id", 0))

    # Resolve client_type
    client_type = None
    extra_data = client.get("extra_data") or {}
    if isinstance(extra_data, str):
        try:
            extra_data = json.loads(extra_data)
        except Exception:
            extra_data = {}
    client_type = extra_data.get("client_type")

    # Load memory layers
    try:
        episodic_memory = await get_client_episodic_memory(client_id)
    except Exception as e:
        log.warning("[MarketingAgent] Failed to load episodic memory: %s", e)
        episodic_memory = {"has_prior_run": False, "previous_runs": [], "contacts_already_found": [], "ig_handles_tried": []}

    try:
        long_term_context = await get_long_term_context(group_id, client_type)
    except Exception as e:
        log.warning("[MarketingAgent] Failed to load long-term context: %s", e)
        long_term_context = {"group_strategy": None, "group_lessons": [], "global_lessons": [], "group_progress": {}, "tool_success_rates": {}}

    # Run orchestrator
    orchestrator = MarketingOrchestratorAgent()
    result: OrchestratorResult = await orchestrator.run(
        client=client,
        run_id=run_id,
        mode=mode,
        episodic_memory=episodic_memory,
        long_term_context=long_term_context,
    )

    return RunResult(
        contacts_recorded=result.contacts_recorded,
        ig_handle=result.ig_handle,
        sub_agent_calls=result.sub_agent_calls,
        tools_that_worked=result.tools_that_worked,
        tools_that_failed=result.tools_that_failed,
        status=result.status,
        summary=result.summary,
        total_tokens=result.total_tokens,
        duration_seconds=result.duration_seconds,
        error_message=result.error_message,
    )
