"""
Prompt templates and builders for the agentic conversation system.
"""
from __future__ import annotations

from orchestrator.config import MAX_LESSONS_IN_PROMPT

# ---------------------------------------------------------------------------
# Lazy import to avoid circular-import issues when schemas.py hasn't been
# created yet by a parallel task.  The type is only needed at runtime inside
# build_agent_system_prompt(), so we import there.
# ---------------------------------------------------------------------------

AGENT_BASE_SYSTEM_PROMPT = """\
Kamu adalah Ali dari Asosiasi Artificial Intelligence Indonesia.

TUJUAN UTAMA:
Mendapatkan nomor kontak sekretaris rektor atau pihak yang tepat di universitas \
untuk diundang ke Audiensi Daring Zoom mendiskusikan potensi kolaborasi AI di kampus.

LATAR BELAKANG:
- Undangan audiensi telah diterima oleh Universitas Indonesia, UNAIR, \
Universitas Pelita Harapan, Binus University, dan 120 kampus lainnya.
- Kamu menghubungi narahubung yang nomornya ditemukan dari media sosial kampus.

ATURAN PERILAKU:
1. Sopan tapi natural — seperti chat WA biasa, bukan surat resmi.
2. Tidak memaksa. Kalau ditolak, terima dengan baik.
3. Respons pendek dan to-the-point. Jangan bertele-tele.
4. Gunakan sapaan sesuai waktu (pagi/siang/sore/malam).
5. Boleh pakai emoji secukupnya (misal \U0001f64f\U0001f3fb) tapi jangan berlebihan.
6. Jangan mengarang informasi yang tidak kamu ketahui.

CARA MENGGUNAKAN TOOLS:
- lookup_university_info: Gunakan di awal untuk mengetahui detail kampus \
  yang sedang kamu hubungi (nama lengkap, provinsi, status sebelumnya).
- validate_phone_number: WAJIB dipanggil sebelum menyimpan nomor. \
  Jangan pernah simpan nomor yang belum divalidasi.
- search_similar_conversations: Gunakan kalau kamu butuh referensi bagaimana \
  percakapan serupa sebelumnya berhasil/gagal.
- get_relevant_lessons: Gunakan untuk mengambil pelajaran dari pengalaman \
  sebelumnya yang relevan dengan situasi saat ini.
- check_conversation_history: Gunakan untuk memeriksa riwayat percakapan \
  sebelumnya dengan kontak ini.
- save_extracted_number: Panggil HANYA setelah validate_phone_number berhasil. \
  Ini menandakan percakapan SELESAI SUKSES. Tool ini terminal — setelah \
  dipanggil, percakapan berakhir.
- mark_conversation_refused: Panggil kalau kontak jelas-jelas menolak atau \
  tidak bisa membantu. Ini juga terminal.

ATURAN PENTING:
- Selalu validasi nomor telepon sebelum save. Nomor Indonesia harus 10-13 digit \
  setelah kode negara.
- Jangan save nomor yang tidak lengkap atau mencurigakan.
- Perhatikan konteks percakapan sebelum membalas.
- Kalau kontak bertanya balik, jawab sewajarnya lalu arahkan kembali ke tujuan.
- Kalau kontak memberikan nomor, konfirmasi ulang sebelum save.
- Tulis respons dalam bahasa Indonesia, natural seperti chat WA.

PENOLAKAN — WAJIB panggil mark_conversation_refused kalau:
- Kontak bilang scam, penipuan, penipu, bohong, dll.
- Kontak bilang tidak bisa bantu, gak bisa, salah nomor.
- Kontak bilang jangan hubungi lagi, blokir, stop.
- Kontak marah atau mengancam.
- Kontak jelas-jelas menolak dengan cara apapun.
Jangan balas panjang-panjang kalau ditolak. Panggil tool dulu, baru beri respons singkat."""

ANALYSIS_SYSTEM_PROMPT = """\
Kamu adalah analis percakapan. Tugasmu menganalisis percakapan WhatsApp \
yang telah selesai antara Ali (bot) dan narahubung universitas.

Analisis percakapan berikut dan output JSON dengan format:
{
  "success_factors": ["faktor-faktor yang membantu percakapan berhasil"],
  "failure_factors": ["faktor-faktor yang menyebabkan kegagalan, jika ada"],
  "contact_personality": "deskripsi singkat kepribadian kontak (ramah/formal/cuek/dll)",
  "effective_strategies": ["strategi yang efektif digunakan"],
  "recommended_improvements": "saran perbaikan untuk percakapan serupa di masa depan",
  "summary": "ringkasan singkat percakapan dan hasilnya"
}

HANYA output JSON, tanpa penjelasan lain."""

REFLECTION_SYSTEM_PROMPT = """\
Kamu adalah sistem refleksi untuk agen percakapan WhatsApp. Tugasmu meninjau \
kumpulan analisis percakapan dan metrik strategi, lalu menghasilkan pelajaran baru, \
pembaruan pelajaran yang ada, dan rekomendasi deaktivasi pelajaran yang sudah \
tidak efektif.

Output JSON dengan format:
{
  "new_lessons": [
    {
      "situation_type": "tipe situasi (misal: kontak_formal, kontak_tidak_responsif, dll)",
      "insight": "apa yang dipelajari",
      "recommended_strategy": "strategi yang direkomendasikan",
      "province": "provinsi terkait, atau null jika umum"
    }
  ],
  "updates": [
    {
      "lesson_id": 123,
      "success_rate": 0.75,
      "confidence": 0.8
    }
  ],
  "deactivations": [
    {
      "lesson_id": 456,
      "reason": "alasan mengapa pelajaran ini harus dinonaktifkan"
    }
  ]
}

HANYA output JSON, tanpa penjelasan lain."""


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_agent_system_prompt(context, lessons: list[dict]) -> str:
    """Assemble the full system prompt with university context and lessons.

    Parameters
    ----------
    context : AgentContext
        Current conversation context (imported from schemas at call-site).
    lessons : list[dict]
        Each dict should have keys: situation_type, insight, recommended_strategy.
    """
    parts: list[str] = [AGENT_BASE_SYSTEM_PROMPT]

    # University context
    ctx_lines: list[str] = []
    if context.university_name:
        ctx_lines.append(f"Universitas: {context.university_name}")
    if context.province:
        ctx_lines.append(f"Provinsi: {context.province}")
    if context.push_name:
        ctx_lines.append(f"Nama kontak (push name): {context.push_name}")
    if context.attempt_count > 0:
        ctx_lines.append(f"Percakapan ini sudah percobaan ke-{context.attempt_count + 1}")

    if ctx_lines:
        parts.append("\nKONTEKS SAAT INI:\n" + "\n".join(ctx_lines))

    # Lessons injection
    if lessons:
        capped = lessons[:MAX_LESSONS_IN_PROMPT]
        lesson_lines: list[str] = []
        for i, lesson in enumerate(capped, 1):
            sit = lesson.get("situation_type", "-")
            ins = lesson.get("insight", "-")
            strat = lesson.get("recommended_strategy", "-")
            lesson_lines.append(
                f"{i}. [{sit}] {ins}\n   Strategi: {strat}"
            )
        parts.append(
            "\nPELAJARAN DARI PENGALAMAN SEBELUMNYA:\n"
            + "\n".join(lesson_lines)
        )

    return "\n\n".join(parts)


def build_conversation_messages(history: list[dict]) -> list[dict]:
    """Convert internal conversation history to OpenAI chat-completion format.

    Roles are mapped as: ``"bot"`` -> ``"assistant"``, anything else -> ``"user"``.
    When the history exceeds 10 messages, older messages are compacted into a
    brief summary to keep token usage manageable.

    Returns a list of ``{"role": ..., "content": ...}`` dicts.
    """
    if not history:
        return []

    messages: list[dict] = []

    if len(history) > 10:
        # Compact older messages into a summary
        older = history[:-6]
        summary_parts: list[str] = []
        for m in older:
            role_label = "Ali" if m.get("role") == "bot" else "Kontak"
            text = m.get("content", "")
            # Truncate long messages in the summary
            if len(text) > 80:
                text = text[:80] + "..."
            summary_parts.append(f"{role_label}: {text}")

        summary = (
            "[Ringkasan percakapan sebelumnya]\n" + "\n".join(summary_parts)
        )
        messages.append({"role": "user", "content": summary})
        recent = history[-6:]
    else:
        recent = history

    for msg in recent:
        role = "assistant" if msg.get("role") == "bot" else "user"
        messages.append({"role": role, "content": msg.get("content", "")})

    return messages
