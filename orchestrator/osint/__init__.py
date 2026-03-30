"""
University OSINT Pipeline — automated intelligence gathering.

Architecture:
    Orchestrator (LangGraph StateGraph)
    ├── Web Profiler Agent     — website scraping & info extraction
    ├── Social Intel Agent     — social media discovery
    ├── Key People Agent       — key people identification
    ├── News Scanner Agent     — news & events
    ├── Contact Enricher Agent — contact aggregation & validation
    └── Reviewer Agent         — QA gate

Each agent uses DuckDuckGo, PDDIKTI, Gemini, and direct HTTP scraping
to gather data, following the "Check Before Search" principle.
"""

from orchestrator.osint.graph import run_osint_pipeline  # noqa: F401
