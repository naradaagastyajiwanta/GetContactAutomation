"""
Gemini-powered client name generator for marketing groups.

Uses Google Search grounding via call_gemini to generate real Indonesian
institution names per client_type category.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TypedDict

from orchestrator.research_agents.gemini_caller import call_gemini

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunked generation config
# ---------------------------------------------------------------------------

GEMINI_CHUNK_SIZE = 30        # max names per single Gemini call (reliable JSON)
GEMINI_TIMEOUT_SECONDS = 45   # timeout per chunk call
MAX_RETRIES_PER_CHUNK = 3
RETRY_BACKOFF = (2, 5)        # seconds to wait between retries

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class GenerationResult(TypedDict):
    names: list[str]
    grounding_urls: list[str]
    suggested_count: int
    excluded_count: int  # how many Gemini-returned names were filtered as duplicates


class GenerationError(Exception):
    """Raised when Gemini fails to generate valid names."""

    def __init__(self, message: str, partial_names: list[str] | None = None) -> None:
        super().__init__(message)
        self.partial_names: list[str] = partial_names or []


# ---------------------------------------------------------------------------
# Name normalization for deduplication
# ---------------------------------------------------------------------------

_NAME_LEGAL_PREFIX_RE = re.compile(
    r"^(?:pt|cv|ud|tb|koperasi|yayasan|lembaga|badan|balai|pusat|dinas)\s+",
    re.IGNORECASE,
)
_NAME_LEGAL_SUFFIX_RE = re.compile(
    r"\s*[\(,]?\s*(?:persero|tbk|tbk\.|terbatas|perseroan|nv)\s*\)?\.?$",
    re.IGNORECASE,
)


def _normalize_name_for_dedup(name: str) -> str:
    """Lowercase + strip legal prefixes/suffixes for fuzzy duplicate detection.

    Examples:
      "PT Telkom Indonesia (Persero) Tbk"  →  "telkom indonesia"
      "Telkom Indonesia"                   →  "telkom indonesia"  (MATCH)
      "PT HM Sampoerna Tbk"                →  "hm sampoerna"
      "HM Sampoerna"                       →  "hm sampoerna"      (MATCH)
    """
    n = name.lower().strip()
    # Run suffix strip twice: "(Persero) Tbk" needs two passes
    n = _NAME_LEGAL_SUFFIX_RE.sub("", n).strip()
    n = _NAME_LEGAL_SUFFIX_RE.sub("", n).strip()
    n = _NAME_LEGAL_PREFIX_RE.sub("", n).strip()
    return re.sub(r"\s+", " ", n)


# ---------------------------------------------------------------------------
# Prompts — one per client_type (all in Indonesian)
# ---------------------------------------------------------------------------

PROMPTS: dict[str, str] = {
    "kementerian": (
        "Kamu adalah asisten riset lembaga resmi Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar lengkap "
        "50 nama lengkap kementerian dan lembaga pemerintah Indonesia "
        "yang masih aktif saat ini (tahun 2024-2025). "
        "Kementerian: Kementerian Sekretariat Negara, Kementerian Dalam Negeri, "
        "Kementerian Luar Negeri, Kementerian Pertahanan, Kementerian Agama, "
        "Kementerian Hukum, Kementerian Keuangan, Kementerian Pendidikan dan Kebudayaan, "
        "Kementerian Kesehatan, Kementerian Sosial, Kementerian Ketenagakerjaan, "
        "Kementerian Perindustrian, Kementerian Perdagangan, Kementerian Energi "
        "dan Sumber Daya Mineral, Kementerian Pekerjaan Umum dan Perumahan Rakyat, "
        "Kementerian Transportasi, Kementerian Komunikasi dan Informatika, "
        "Kementerian Pertanian, Kementerian Kelautan dan Pangan, "
        "Kementerian Lingkungan Hidup dan Kehutanan, dst. "
        "Lembaga: BIN, KPI, BNN, BMKG, BNPB, BSN, Bappenas, LAN, dll. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama Lengkap 1", "Nama Lengkap 2", ...]}'
    ),
    "lembaga_negara": (
        "Kamu adalah asisten riset lembaga resmi Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "lembaga negara non-kementerian Indonesia yang masih aktif (2024-2025). "
        "Contoh: Badan Intelijen Negara (BIN), Badan Nasional Penanggulangan Bencana (BNPB), "
        "Badan Meteorologi, Klimatologi, dan Geofisika (BMKG), "
        "Badan Pusat Statistik (BPS), Ombudsman RI, "
        "Komisi Nasional Hak Asasi Manusia (Komnas HAM), "
        "Badan Pengawas Pemilihan Umum (Bawaslu), "
        "Dewan Pertimbangan Presiden (Wantimpres), "
        "Lembaga Kebijakan Pengadaan Barang/Jasa Pemerintah (LKPP), "
        "Kementerian Agraria dan Tata Ruang/BPN, dst. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama Lengkap 1", "Nama Lengkap 2", ...]}'
    ),
    "bumn": (
        "Kamu adalah asisten riset perusahaan Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "perusahaan Badan Usaha Milik Negara (BUMN) Indonesia yang masih aktif (2024-2025). "
        "Contoh: PT Pertamina (Persero), PT PLN (Persero), PT Garuda Indonesia (Persero), "
        "PT Bank BRI (Persero) Tbk, PT Bank Mandiri (Persero) Tbk, PT Bank BNI (Persero) Tbk, "
        "PT Bank BTN (Persero) Tbk, PT Telekomunikasi Indonesia (Persero) Tbk, "
        "PT Himbara (Holding), PT Pupuk Indonesia (Persero), PT Semen Indonesia (Persero) Tbk, "
        "PT Angkasa Pura (Persero), PT KAI (Persero), PT ASDP Indonesia Ferry (Persero), "
        "PT Pelindo (Persero), PT Pegadaian (Persero), PT Jasindo (Persero), "
        "PT Jasa Raharja (Persero), PT Aviasi (Persero), PT Krakatau Steel (Persero) Tbk, dst. "
        "Prioritaskan perusahaan yang disebutkan di situs resmi Kemenkeu/BUMN. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama PT (Persero) 1", "Nama PT (Persero) 2", ...]}'
    ),
    "swasta_besar": (
        "Kamu adalah asisten riset perusahaan Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "perusahaan swasta besar Indonesia yang masih aktif dan terkenal (2024-2025). "
        "Contoh: PT Astra International Tbk, PT Salim Group, PT Sinar Mas Group, "
        "PT Indofood Sukses Makmur Tbk, PT Unilever Indonesia Tbk, "
        "PT HM Sampoerna Tbk, PT Gudang Garam Tbk, PT Djarum, "
        "PT Charoen Pokphand Indonesia Tbk, PT Japfa Comfeed Indonesia Tbk, "
        "PT Semen Padang (Holcim Indonesia), PT Freeport Indonesia, "
        "PT Adaro Energy TBK, PT Bukit Asam TBK, PT Indocement Tunggal Prakarsa Tbk, "
        "PT Barito Pacific, PT Chandra Asri Petrochemical TBK, "
        "PT XL Axiata TBK, PT Indosat TBK, PT Telekomunikasi Selular, "
        "PT Charoen Pokphand, PT Trans Corp, PT Astra Graphia, dst. "
        "Prioritaskan perusahaan yang listing di BEI atau grup perusahaan multinasional yang berbasis di RI. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama PT Tbk / Nama Grup 1", "Nama PT Tbk / Nama Grup 2", ...]}'
    ),
    "asosiasi": (
        "Kamu adalah asisten riset asosiasi Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "asosiasi dan organisasi profesional resmi Indonesia yang masih aktif (2024-2025). "
        "Contoh: Kamar Dagang dan Industri Indonesia (KADIN), Asosiasi Pengusaha Indonesia (APINDO), "
        "Persatuan Golf Indonesia (PGI), Asosiasi Fintech Indonesia (AFTECH), "
        "Indonesian Digital Association (IDA), Asosiasi Cloud Indonesia, "
        "Gabungan Industri Film Nasional (GIFN), Asosiasi Produsen Televisi Indonesia (APROJI), "
        "Asosiasi EMCEE Indonesia, Indonesian Sport Media Association, dst. "
        "Prioritaskan asosiasi yang teregistrasi di pemerintah atau memiliki website resmi aktif. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama Asosiasi / Organisasi 1", "Nama Asosiasi / Organisasi 2", ...]}'
    ),
    "lpk": (
        "Kamu adalah asisten riset pelatihan kerja Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "Lembaga Pelatihan Kerja (LPK) resmi dan terpercaya di Indonesia (2024-2025). "
        "Prioritaskan LPK yang: teregistrasi di Disnaker kabupaten/kota, "
        "memiliki izin operasional resmi, atau berafiliasi dengan Blk (Balai Latihan Kerja). "
        "Contoh pola nama: LPK Nusa Bahasa, LPK Bina Karya, LPK Mandiri Skill Center, "
        "LPK Anugerah Komputer, LPK Tunas Indonesia, LPK Berlian Teknologi, dst. "
        "Gunakan nama LPK yang nyata dan bisa diverifikasi via pencarian web. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama LPK 1", "Nama LPK 2", ...]}'
    ),
    "lkp": (
        "Kamu adalah asisten riset pendidikan dan pelatihan Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "Lembaga Kursus dan Pelatihan (LKP) resmi di Indonesia yang masih aktif (2024-2025). "
        "Prioritaskan LKP yang: memiliki NPS (Nomor Pokak Satyan), "
        "terafiliasi dengan Kemendikbud, atau memiliki reputasi baik. "
        "Contoh pola: LKP Global English, LKP Computrad Indonesia, "
        "LKP Nurul Jaziyah, LKP Kreativa Design, dst. "
        "Gunakan nama LKP yang nyata dan bisa diverifikasi via pencarian web. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama LKP 1", "Nama LKP 2", ...]}'
    ),
    "lsp_p1": (
        "Kamu adalah asisten riset lembaga sertifikasi Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "Lembaga Sertifikasi Profesi Level 1 (LSP P1) yang teregistrasi "
        "di Badan Nasional Sertifikasi Profesi (BNSP) dan masih aktif (2024-2025). "
        "LSP P1 adalah LSP yang ditetapkan oleh BNSP untuk menerbitkan sertifikat kompetensi. "
        "Contoh: LSP Industri Kimia, LSP Tekstil, LSP Perbankan dan Keuangan, "
        "LSP Pariwisata, LSP Teknologi Informasi, LSP Manajemen, LSP Konstruksi, dst. "
        "Prioritaskan yang memiliki lisensi BNSP aktif. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama LSP 1", "Nama LSP 2", ...]}'
    ),
    "lsp_p2": (
        "Kamu adalah asisten riset lembaga sertifikasi Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "Lembaga Sertifikasi Profesi Level 2 (LSP P2) yang teregistrasi "
        "di Badan Nasional Sertifikasi Profesi (BNSP) dan masih aktif (2024-2025). "
        "LSP P2 adalah LSPchema nasional yang mengajukan lisensi ke BNSP. "
        "Contoh: LSP P2 Pariwisata Nusaputera, LSP P2 Telekomunikasi, "
        "LSP P2 Farmasi Indonesia, LSP P2 Keperawatan, LSP P2 Akuntansi, dst. "
        "Prioritaskan yang memiliki lisensi BNSP aktif. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama LSP P2 1", "Nama LSP P2 2", ...]}'
    ),
    "lsp_p3": (
        "Kamu adalah asisten riset lembaga sertifikasi Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "Lembaga Sertifikasi Profesi Level 3 (LSP P3) yang teregistrasi "
        "di Badan Nasional Sertifikasi Profesi (BNSP) dan masih aktif (2024-2025). "
        "LSP P3 adalah LSP dengan lisensi penuh dari BNSP untuk sertifikasi nasional. "
        "Prioritaskan yang memiliki website resmi dan lisensi BNSP aktif. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama LSP P3 1", "Nama LSP P3 2", ...]}'
    ),
    "dinas": (
        "Kamu adalah asisten riset instansi pemerintah daerah Indonesia. "
        "Gunakan Google Search grounding untuk menemukan daftar 50 nama lengkap "
        "Dinas Pemerintah Daerah (Provinsi/Kabupaten/Kota) Indonesia yang masih aktif (2024-2025). "
        "Contoh pola: Dinas Pendidikan Provinsi DKI Jakarta, "
        "Dinas Kesehatan Kabupaten Bandung, "
        "Dinas Sosial Provinsi Jawa Barat, "
        "Dinas Ketenagakerjaan Kota Surabaya, "
        "Dinas Perdagangan dan Perindustrian Kabupaten Bekasi, "
        "Dinas Kependudukan dan Pencatatan Sipil Kota Medan, "
        "Dinas Perpustakaan dan Kearsipan Daerah Provinsi Banten, dst. "
        "Gunakan nama lengkap: Dinas [Bidang] [Tingkat] [Nama_Daerah]. "
        "Kembalikan HANYA satu JSON object dengan format: "
        '{"names": ["Nama Dinas Lengkap 1", "Nama Dinas Lengkap 2", ...]}'
    ),
}


# ---------------------------------------------------------------------------
# Internal: single Gemini call with timeout + retry
# ---------------------------------------------------------------------------


async def _call_gemini_with_retry(prompt: str) -> tuple[list[str], list[str]]:
    """Call Gemini with per-attempt timeout and exponential-backoff retry.

    Returns (names, grounding_urls). On complete failure returns ([], []).
    """
    for attempt in range(MAX_RETRIES_PER_CHUNK):
        try:
            parsed, grounding_urls = await asyncio.wait_for(
                call_gemini(prompt, use_search_grounding=True),
                timeout=GEMINI_TIMEOUT_SECONDS,
            )

            if isinstance(parsed, dict) and parsed.get("_parse_failed"):
                log.warning(
                    "[Generator] Parse failed (attempt %d/%d) — raw: %.200s",
                    attempt + 1,
                    MAX_RETRIES_PER_CHUNK,
                    parsed.get("_raw", ""),
                )
                if attempt < MAX_RETRIES_PER_CHUNK - 1:
                    await asyncio.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
                continue

            raw_names: list = []
            if isinstance(parsed, dict):
                raw_names = parsed.get("names", [])
            elif isinstance(parsed, list):
                raw_names = parsed

            names = [str(n).strip() for n in raw_names if str(n).strip()]
            return names, grounding_urls

        except asyncio.TimeoutError:
            log.warning(
                "[Generator] Gemini timeout (attempt %d/%d)",
                attempt + 1,
                MAX_RETRIES_PER_CHUNK,
            )
            if attempt < MAX_RETRIES_PER_CHUNK - 1:
                await asyncio.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
        except Exception as exc:  # noqa: BLE001
            log.error("[Generator] Gemini error: %s", exc)
            break

    return [], []


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


async def generate_client_names(
    client_type: str,
    count: int = 50,
) -> GenerationResult:
    """
    Call Gemini in chunks (up to GEMINI_CHUNK_SIZE per call) with per-chunk
    timeout + retry to generate institution names for the given client_type.

    Fetches existing names from the DB, injects them as an exclusion list,
    and post-filters the result so that duplicate names are never returned.

    Parameters
    ----------
    client_type : str
        One of the keys in PROMPTS (e.g. "kementerian", "bumn", "dinas").
    count : int
        Desired number of names (clamped to [5, 200]).

    Returns
    -------
    GenerationResult
        {"names": [...], "grounding_urls": [...], "suggested_count": int,
         "excluded_count": int}

    Raises
    ------
    ValueError
        If client_type is not a known PROMPTS key.
    GenerationError
        If all Gemini calls fail or no unique names can be returned.
    """
    if client_type not in PROMPTS:
        raise ValueError(
            f"Unknown client_type: {client_type!r}. "
            f"Valid types: {list(PROMPTS.keys())}"
        )

    count = max(5, min(200, count))
    base_prompt = PROMPTS[client_type]

    # --- Layer 1: Fetch existing names for this client_type ---
    from orchestrator.marketing import groups as _mkt_groups  # local import to avoid circular

    existing_raw = await _mkt_groups.get_all_client_names_by_type(client_type)
    existing_normalized: set[str] = {
        _normalize_name_for_dedup(n) for n in existing_raw if n.strip()
    }

    # Inflate requested count to compensate for expected exclusions
    buffer = min(len(existing_normalized) // 2, 80)
    actual_count = min(count + buffer, 200)

    # --- Chunked generation ---
    all_raw_names: list[str] = []
    all_grounding_urls: list[str] = []
    remaining = actual_count

    while remaining > 0:
        chunk_size = min(remaining, GEMINI_CHUNK_SIZE)

        # Build exclusion list: DB names + names already generated this session
        exclude_list = list(existing_raw[:150]) + all_raw_names[:100]
        if exclude_list:
            excl_lines = "\n".join(f"- {n}" for n in exclude_list)
            excl_block = (
                "\n\nPERHATIAN — WAJIB DIIKUTI:\n"
                "Nama-nama berikut SUDAH ADA dalam database dan TIDAK BOLEH kamu masukkan dalam list:\n"
                f"{excl_lines}\n\n"
                "Hasilkan HANYA nama yang BELUM ada dalam daftar di atas.\n"
            )
        else:
            excl_block = ""

        prompt = (
            f"{base_prompt}"
            f"{excl_block}"
            f"\n\nKamu HARUS mengembalikan tepat {chunk_size} nama. "
            f"Jika jumlah nama baru yang tersedia kurang dari {chunk_size}, "
            f"kembalikan saja nama-nama yang kamu temukan (boleh kurang). "
            f"Jangan menambah nama fiktif. "
            f'Kembalikan HANYA satu JSON object dengan kunci "names" berisi array string. '
            f'Format: {{"names": ["Nama 1", "Nama 2", ...]}}'
        )

        chunk_names, chunk_urls = await _call_gemini_with_retry(prompt)

        # Collect grounding URLs (deduplicated across chunks)
        for url in chunk_urls:
            if url not in all_grounding_urls:
                all_grounding_urls.append(url)

        if not chunk_names:
            log.warning(
                "[Generator] Chunk returned empty after retries — "
                "stopping with %d raw names so far (target %d)",
                len(all_raw_names),
                actual_count,
            )
            break

        all_raw_names.extend(chunk_names)
        remaining -= len(chunk_names)

        # If Gemini returned far fewer than asked, assume the category is nearly exhausted
        if len(chunk_names) < chunk_size * 0.6:
            log.info(
                "[Generator] Partial chunk (%d/%d) — assuming category exhausted",
                len(chunk_names),
                chunk_size,
            )
            break

    if not all_raw_names:
        raise GenerationError(
            f"Gemini gagal menghasilkan nama untuk kategori {client_type!r}. "
            f"Kemungkinan timeout atau format respons tidak valid. Coba lagi."
        )

    # --- Layer 2: Post-generation normalized dedup ---
    seen_normalized: set[str] = set()
    deduped_names: list[str] = []
    excluded_count = 0

    for raw in all_raw_names:
        name = str(raw).strip()
        if not name:
            continue
        norm = _normalize_name_for_dedup(name)
        if norm in existing_normalized or norm in seen_normalized:
            excluded_count += 1
            continue
        seen_normalized.add(norm)
        deduped_names.append(name)
        if len(deduped_names) >= count:
            break

    if not deduped_names:
        raise GenerationError(
            f"Semua {len(all_raw_names)} nama yang dihasilkan Gemini sudah ada di database "
            f"untuk kategori {client_type!r}. "
            f"Coba hapus group lama atau gunakan kategori berbeda."
        )

    return GenerationResult(
        names=deduped_names,
        grounding_urls=all_grounding_urls,
        suggested_count=len(deduped_names),
        excluded_count=excluded_count,
    )
