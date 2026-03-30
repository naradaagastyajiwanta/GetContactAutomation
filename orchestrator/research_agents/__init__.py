"""
Multi-Agent Research Pipeline for Audiensi Background Research.

Architecture:
    Orchestrator (LangGraph StateGraph)
    ├── Rector Agent         — find rector name, birth city, birth year
    ├── Topic Agents (×5)    — parallel research on tourism & food
    │   ├── tourism_birth_youth
    │   ├── tourism_birth_current
    │   ├── tourism_uni_city
    │   ├── food_birth_city
    │   └── food_uni_city
    └── Reviewer Agent       — validate quality, trigger selective retry

Each question is handled by a dedicated agent with its own Gemini call
and Google Search grounding, yielding more accurate and source-traceable
results than a single monolithic prompt.
"""

from orchestrator.research_agents.graph import run_research  # noqa: F401
