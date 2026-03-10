"""
News & Event Scanner Agent — finds recent news and upcoming events
related to the university.

Always runs (news is always fresh), provides conversation starters.
"""

from __future__ import annotations

from typing import Any

from orchestrator.config import log
from orchestrator.osint.state import OsintState, NewsScanResult, NewsItem
from orchestrator.osint.tools import ddg_search, gpt_extract_structured, gemini_research


async def news_scanner_agent(state: OsintState) -> dict:
    """
    Scan for recent news and events about the university.

    Returns partial state update with `news_scan`.
    """
    uni = state.get("university_data", {})
    uni_name = state.get("university_name", uni.get("name", ""))

    log.info("[NewsScanner] Starting for %s", uni_name)

    items: list[NewsItem] = []

    # ── 1. DDG news search ─────────────────────────────────────────────
    news_queries = [
        f'"{uni_name}" berita terbaru 2025 2026',
        f'"{uni_name}" wisuda OR seminar OR dies natalis OR MoU',
        f'"{uni_name}" akreditasi OR prestasi OR penghargaan',
    ]

    for query in news_queries:
        results = await ddg_search(query, max_results=5)
        for r in results:
            if _is_duplicate(items, r.get("link", "")):
                continue
            items.append(NewsItem(
                title=r.get("title", ""),
                summary=r.get("snippet", ""),
                url=r.get("link"),
                source="ddg_search",
                category=_categorize_news(r.get("title", "") + " " + r.get("snippet", "")),
                relevance_score=0.5,
            ))

    # ── 2. Gemini deep research for news summary ──────────────────────
    try:
        gemini_result = await gemini_research(
            f"Cari 5 berita terbaru tentang {uni_name} dalam 6 bulan terakhir. "
            "Untuk setiap berita, berikan: judul, ringkasan 1-2 kalimat, dan URL sumber."
        )
        if gemini_result and gemini_result.get("text"):
            extracted = await gpt_extract_structured(
                gemini_result["text"],
                (
                    "Extract news items from this text. Return JSON with key 'items':\n"
                    '[{"title": "...", "summary": "...", "category": "general|achievement|event|partnership|issue"}]'
                ),
            )
            if extracted and extracted.get("items"):
                for item in extracted["items"]:
                    items.append(NewsItem(
                        title=item.get("title", ""),
                        summary=item.get("summary"),
                        source="gemini_grounded",
                        category=item.get("category", "general"),
                        relevance_score=0.7,
                    ))
    except Exception as e:
        log.warning("[NewsScanner] Gemini news research failed: %s", e)

    # ── 3. Search for problems/challenges ──────────────────────────────
    problem_results = await ddg_search(
        f'"{uni_name}" masalah OR tantangan OR kendala 2024 2025', max_results=3,
    )
    for r in problem_results:
        if _is_duplicate(items, r.get("link", "")):
            continue
        items.append(NewsItem(
            title=r.get("title", ""),
            summary=r.get("snippet", ""),
            url=r.get("link"),
            source="ddg_search",
            category="issue",
            relevance_score=0.6,
        ))

    # Deduplicate and sort by relevance
    seen_titles = set()
    unique_items = []
    for item in items:
        title_key = item.title.lower().strip()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_items.append(item)

    unique_items.sort(key=lambda x: x.relevance_score, reverse=True)
    unique_items = unique_items[:20]  # Cap at 20 news items

    log.info("[NewsScanner] Done for %s: %d news items found", uni_name, len(unique_items))
    return {"news_scan": NewsScanResult(items=unique_items)}


def _is_duplicate(items: list[NewsItem], url: str) -> bool:
    """Check if this URL is already in our items list."""
    if not url:
        return False
    return any(i.url == url for i in items)


def _categorize_news(text: str) -> str:
    """Simple keyword-based news categorization."""
    text_lower = text.lower()
    if any(k in text_lower for k in ["wisuda", "graduation", "yudisium"]):
        return "event"
    if any(k in text_lower for k in ["prestasi", "juara", "penghargaan", "award"]):
        return "achievement"
    if any(k in text_lower for k in ["mou", "kerjasama", "partner", "kolaborasi"]):
        return "partnership"
    if any(k in text_lower for k in ["akreditasi", "masalah", "kendala", "tantangan"]):
        return "issue"
    if any(k in text_lower for k in ["seminar", "workshop", "dies natalis", "event"]):
        return "event"
    return "general"
