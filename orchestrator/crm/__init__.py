"""
PIC Profiling Pipeline (Customer Relation) — deep profiling of
university contacts for CRM purposes.

Architecture:
    Orchestrator (LangGraph StateGraph)
    ├── Identity Resolver      — Google + PDDIKTI identity resolution
    ├── Academic Profiler      — PDDIKTI, Scholar, teaching info
    ├── Social Media Profiler  — LinkedIn, IG, Facebook
    ├── Campus Context         — campus problems, concerns, hopes
    ├── Personal Interest      — hobbies, food, activities (best-effort)
    ├── Family Info            — marital status, family (best-effort)
    └── Profile Compiler       — compile all + confidence scoring + gap flagging
"""

from orchestrator.crm.graph import run_pic_profiling  # noqa: F401
