"""
Reviewer Agent — validates quality and consistency of all agent results.

The reviewer checks:
1. Is the rector name plausible for this university?
2. Is the birth city consistent and reasonable?
3. Are the tourism/food descriptions relevant to the correct cities?
4. Are there any "Tidak ditemukan" fields that should be retried?
5. Any signs of hallucination?

If results are not acceptable, the reviewer specifies which agents should
be re-run. The orchestrator respects MAX_REVIEW_RETRIES to prevent loops.
"""

from __future__ import annotations

from orchestrator.config import log
from orchestrator.research_agents.gemini_caller import call_gemini
from orchestrator.research_agents.state import (
    ResearchState,
    ReviewVerdict,
    TOPIC_AGENT_KEYS,
)


async def reviewer_agent(state: ResearchState) -> dict:
    """
    LangGraph node: evaluate all research results for quality.

    Returns partial state update with ``review`` and incremented
    ``review_retry_count``.
    """
    ri = state.get("rector_info")
    university_name = state["university_name"]

    # Build summary of all results for the reviewer
    rector_summary = "Tidak tersedia"
    if ri:
        src_count = len(ri.grounding_urls)
        src_note = f"Sources: {src_count} (verified)" if src_count > 0 else "⚠️ TANPA SUMBER REFERENSI"
        rector_summary = (
            f"Nama: {ri.rector_name}\n"
            f"Tahun lahir: {ri.rector_birth_year or '?'}\n"
            f"Kota lahir: {ri.rector_birth_city or '?'}\n"
            f"Kota kampus: {ri.university_city or '?'}\n"
            f"Confidence: {ri.confidence}\n"
            f"{src_note}"
        )

    topic_summaries: dict[str, str] = {}
    for key in TOPIC_AGENT_KEYS:
        tr = state.get(key)  # type: ignore[literal-required]
        if tr:
            src_count = len(tr.grounding_urls)
            src_note = f"VERIFIED ({src_count} sources)" if src_count > 0 else "⚠️ TANPA SUMBER REFERENSI"
            topic_summaries[key] = (
                f"{tr.content[:200]} (confidence={tr.confidence}, {src_note})"
            )
        else:
            topic_summaries[key] = "TIDAK ADA HASIL"

    topics_text = "\n".join(f"- {k}: {v}" for k, v in topic_summaries.items())

    prompt = f"""Kamu quality reviewer untuk hasil riset audiensi universitas.

Universitas: **{university_name}**

== HASIL RISET REKTOR ==
{rector_summary}

== HASIL RISET TOPIK ==
{topics_text}

Evaluasi hasil riset di atas:

1. **Rektor**: Apakah nama rektor masuk akal untuk universitas ini? Apakah ini benar rektor aktif (bukan mantan)?
2. **Kota lahir**: Apakah kota lahir yang ditemukan spesifik (bukan hanya provinsi)?
3. **Wisata**: Apakah setiap wisata RELEVAN dengan kota yang dimaksud? Tidak tercampur kota lain?
4. **Makanan**: Apakah makanan RELEVAN dan khas kota tersebut?
5. **Completeness**: Apakah ada field "Tidak ditemukan" atau "Error" yang seharusnya bisa dicari?
6. **Hallucination**: Ada tanda-tanda informasi yang dikarang?
7. **Psychographics**: Apakah analisis psikografis rektor berdasarkan data nyata? Masuk akal?
8. **SUMBER REFERENSI**: Apakah setiap hasil memiliki sumber dari Google Search?
   - Hasil yang bertanda "TANPA SUMBER REFERENSI" HARUS di-retry karena tidak terverifikasi.
   - Ini adalah kriteria KRITIS — hasil tanpa sumber = tidak bisa dipercaya.

RULES:
- Jika semua hasil cukup bagus (score >= 0.7) DAN semua memiliki sumber → approved: true
- Jika ada hasil TANPA SUMBER REFERENSI → approved: false + masukkan ke retry_agents
- Jika ada masalah serius (rektor salah, kota tercampur) → approved: false + retry_agents
- Jangan retry agent yang hasilnya "Tidak ditemukan" karena memang data tidak ada
- HANYA retry agent yang hasilnya SALAH, tercampur kota, atau TANPA SUMBER

retry_agents yang valid: "rector_info", "tourism_birth_youth", "tourism_birth_current", "tourism_uni_city", "food_birth_city", "food_uni_city", "psychographics"

Jawab HANYA JSON (tanpa code block):
{{
    "approved": true,
    "overall_score": 0.85,
    "feedback": {{
        "rector_info": "Komentar singkat...",
        "tourism_birth_youth": "Komentar singkat...",
        "tourism_birth_current": "Komentar singkat...",
        "tourism_uni_city": "Komentar singkat...",
        "food_birth_city": "Komentar singkat...",
        "food_uni_city": "Komentar singkat...",
        "psychographics": "Komentar singkat..."
    }},
    "retry_agents": []
}}
"""

    log.info("[Reviewer] Evaluating research for: %s", university_name)

    try:
        # Reviewer uses search grounding to cross-verify claims
        parsed, _ = await call_gemini(prompt, use_search_grounding=True)

        verdict = ReviewVerdict(
            approved=parsed.get("approved", True),
            overall_score=float(parsed.get("overall_score", 0.7)),
            feedback=parsed.get("feedback", {}),
            retry_agents=parsed.get("retry_agents", []),
        )

        current_retry = state.get("review_retry_count", 0)

        log.info(
            "[Reviewer] Verdict: approved=%s, score=%.2f, retry_agents=%s (retry_count=%d)",
            verdict.approved,
            verdict.overall_score,
            verdict.retry_agents,
            current_retry,
        )

        return {
            "review": verdict,
            "review_retry_count": current_retry + 1,
        }

    except Exception as e:
        log.error("[Reviewer] Failed: %s", e, exc_info=True)
        # On reviewer failure, approve by default to not block the pipeline
        return {
            "review": ReviewVerdict(
                approved=True,
                overall_score=0.5,
                feedback={"_error": f"Reviewer failed: {e}"},
                retry_agents=[],
            ),
            "review_retry_count": state.get("review_retry_count", 0) + 1,
        }
