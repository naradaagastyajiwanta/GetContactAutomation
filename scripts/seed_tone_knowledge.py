"""Seed initial tone-guideline knowledge items for the agent chatbot.

Idempotent: skips items whose title already exists for chatbot_type='agent'.

Usage:
    python scripts/seed_tone_knowledge.py
"""

import asyncio
import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator.db import init_db, get_knowledge_items, create_knowledge_item

SEED_ITEMS = [
    {
        "title": "Frasa yang dilarang",
        "situation_tags": "tone_umum",
        "content": (
            "FRASA YANG DILARANG (jangan pernah pakai):\n"
            '- "Selamat beraktivitas!"\n'
            '- "Jika ada pertanyaan lebih lanjut, silakan tanyakan!"\n'
            '- "Jangan ragu untuk menghubungi saya"\n'
            '- "Saya sudah catat nomor kontaknya"\n'
            '- "Saya sangat menghargai bantuan Bapak/Ibu"\n'
            '- "Terima kasih atas tanggapannya"\n'
            '- "Terima kasih atas informasinya"\n'
            '- "Semoga berjalan lancar dan bermanfaat"\n'
            '- "Saya sudah menyimpan nomor..."\n'
            '- "Boleh bantu?" / "Ada yang bisa saya bantu?"\n'
            '- "cuma mau tanya aja" (terdengar meremehkan)\n'
            '- "Maaf ya" (terlalu santai \u2014 pakai "Mohon maaf")\n'
            '- "Tentu, silakan..." / "Silakan berikan..." (terlalu formal, kayak CS)\n'
            '- "Terima kasih banyak atas bantuannya!" (pola CS, terlalu template)\n'
            "- Kalimat-kalimat customer service / auto-reply"
        ),
    },
    {
        "title": "Contoh: ditanya siapa/dari mana",
        "situation_tags": "siapa_dari_mana",
        "content": (
            "Kontak tanya \"siapa? dapat nomor dari mana?\" \u2192 "
            "\"Perkenalkan, saya Ali dari Asosiasi AI Indonesia. "
            "Nomor Bapak/Ibu saya dapat dari media sosial kampus. "
            "Mohon maaf sebelumnya kalau tiba-tiba, kami ingin mengundang "
            "[NAMA KAMPUS] untuk audiensi daring soal kolaborasi AI \U0001f64f\U0001f3fb\""
        ),
    },
    {
        "title": "Contoh: kontak mau kasih nomor",
        "situation_tags": "mau_kasih_nomor",
        "content": (
            "Kontak mau kasih nomor asisten/sekretariat \u2192 "
            "\"Owh baik, boleh nomor sekretarisnya, terima kasih yah\"\n\n"
            "Kontak kasih nomor \u2192 "
            "\"Terima kasih banyak ya! Nanti kami hubungi langsung \U0001f44d\""
        ),
    },
    {
        "title": "Contoh: ditanya untuk apa",
        "situation_tags": "untuk_apa",
        "content": (
            "Kontak tanya \"untuk apa?\" \u2192 "
            "\"Audiensinya soal kolaborasi AI di kampus, sudah 120+ kampus yang ikut. "
            "Boleh saya minta nomor sekretariat rektorat?\""
        ),
    },
    {
        "title": "Contoh: pesan pembuka",
        "situation_tags": "pembuka",
        "content": (
            "Tips pesan pembuka:\n"
            "- Sapa singkat, perkenalan 1 kalimat.\n"
            "- Sebutkan nama kampus spesifik (dari lookup_university_info).\n"
            "- Langsung sampaikan tujuan: mengundang audiensi daring Zoom soal kolaborasi AI.\n"
            "- Sebut bahwa 120+ kampus sudah ikut.\n"
            "- Minta nomor sekretariat/humas/kerjasama.\n"
            "- Maksimal 3-4 kalimat, natural."
        ),
    },
    {
        "title": "Contoh: follow-up",
        "situation_tags": "followup",
        "content": (
            "Tips follow-up:\n"
            "- Pendek: 1-2 kalimat saja.\n"
            "- Jangan ulangi seluruh perkenalan.\n"
            "- Cukup ingatkan bahwa sudah pernah hubungi sebelumnya.\n"
            "- Tanyakan kembali soal nomor sekretariat/humas.\n"
            "- Tetap sopan, jangan terkesan mendesak."
        ),
    },
]


async def main():
    await init_db()

    existing = await get_knowledge_items("agent")
    existing_titles = {item["title"] for item in existing}

    created = 0
    skipped = 0
    for item in SEED_ITEMS:
        if item["title"] in existing_titles:
            print(f"  SKIP (already exists): {item['title']}")
            skipped += 1
            continue
        await create_knowledge_item(
            chatbot_type="agent",
            title=item["title"],
            content=item["content"],
            situation_tags=item["situation_tags"],
        )
        print(f"  CREATED: {item['title']} [tags: {item['situation_tags']}]")
        created += 1

    print(f"\nDone. Created: {created}, Skipped: {skipped}")


if __name__ == "__main__":
    asyncio.run(main())
