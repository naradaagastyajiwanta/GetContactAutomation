"""Keyword-based situation detector for RAG-based tone guidelines."""

from __future__ import annotations

import re

# Regex pattern for Indonesian phone numbers (08xx, 628xx, +628xx with 10-13 digits)
_PHONE_RE = re.compile(r"(?:\+?62|0)8\d{8,11}")

# Mapping of tags to their trigger keywords/conditions
_KEYWORD_MAP: dict[str, list[str]] = {
    "siapa_dari_mana": [
        "siapa", "dari mana", "dapat nomor", "kenal", "ini siapa",
        "tau nomor", "tahu nomor", "dapet nomor",
    ],
    "untuk_apa": [
        "untuk apa", "buat apa", "maksudnya", "tujuan", "ngapain",
        "keperluan", "perihal",
    ],
    "menolak": [
        "ga bisa", "tidak bisa", "gabisa", "tdk bisa", "gak bisa",
        "nggak bisa", "ndak bisa", "tidak dapat", "ga bisa kasih",
        "tidak bersedia", "tidak berkenan",
    ],
    "sibuk": [
        "sibuk", "meeting", "nanti aja", "nanti saja", "lagi rapat",
        "sedang rapat", "belum bisa", "lain kali",
    ],
    "bukan_orangnya": [
        "salah nomor", "bukan saya", "saya bukan", "salah orang",
        "salah sambung",
    ],
    "kolaborasi_seperti_apa": [
        "kolaborasi seperti apa", "kolaborasi apa", "kerjasama apa",
        "kerja sama apa", "bentuk kolaborasi", "bentuk kerjasama",
        "bentuk kerja sama", "programnya apa", "program apa",
        "seperti apa", "kayak gimana", "gimana bentuknya",
        "apa saja", "apa aja", "detailnya", "rincinya",
        "lebih detail", "lebih rinci", "jelaskan", "maksudnya apa",
    ],
}

# Keywords that indicate the contact is giving a phone number
_MAU_KASIH_KEYWORDS = [
    "ini nomor", "hubungi", "nomornya", "nomor hp", "nomor wa",
    "kontak", "bisa dihubungi", "coba hubungi",
]


def detect_situation_tags(
    message: str, conv_state: str, attempt_count: int = 0
) -> list[str]:
    """Analyze the latest contact message + conversation state, return relevant tags.

    Always includes ``tone_umum``. Additional tags are added based on keyword
    matching against the incoming message.
    """
    tags: list[str] = ["tone_umum"]
    msg_lower = message.lower()

    # Keyword-based detection
    for tag, keywords in _KEYWORD_MAP.items():
        if any(kw in msg_lower for kw in keywords):
            tags.append(tag)

    # Phone number detection — contact might be giving a number
    if _PHONE_RE.search(message) or any(kw in msg_lower for kw in _MAU_KASIH_KEYWORDS):
        tags.append("mau_kasih_nomor")

    return tags
