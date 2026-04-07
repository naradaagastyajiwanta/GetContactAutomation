"""
Gemini-powered client name generator for marketing groups.

Uses Google Search grounding via call_gemini to generate real Indonesian
institution names per client_type category.
"""

from __future__ import annotations

import re
from typing import TypedDict

from orchestrator.research_agents.gemini_caller import call_gemini


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

    pass


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
# Generator
# ---------------------------------------------------------------------------


async def generate_client_names(
    client_type: str,
    count: int = 50,
) -> GenerationResult:
    """
    Call Gemini with Google Search grounding to generate institution names
    matching the given client_type category.

    Fetches existing names for this client_type from the DB, injects them
    into the prompt as an exclusion list, and post-filters the result so
    that duplicate names are never returned.

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
        If the Gemini call fails, JSON parsing fails, or no names are returned.
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

    # Build exclusion block (cap at 150 names ≈ 600–900 extra tokens)
    exclusion_block = ""
    if existing_raw:
        exclusion_lines = "\n".join(f"- {n}" for n in existing_raw[:150])
        exclusion_block = (
            "\n\nPERHATIAN — WAJIB DIIKUTI:\n"
            "Nama-nama berikut SUDAH ADA dalam database dan TIDAK BOLEH kamu masukkan dalam list:\n"
            f"{exclusion_lines}\n\n"
            "Hasilkan HANYA nama yang BELUM ada dalam daftar di atas.\n"
        )

    # Inflate requested count to compensate for expected exclusions
    buffer = min(len(existing_normalized) // 2, 80)
    actual_count = min(count + buffer, 200)

    prompt = (
        f"{base_prompt}"
        f"{exclusion_block}"
        f"\n\nKamu HARUS mengembalikan tepat {actual_count} nama. "
        f"Jika jumlah nama baru yang tersedia kurang dari {actual_count}, "
        f"kembalikan saja nama-nama yang kamu temukan (boleh kurang). "
        f"Jangan menambah nama fiktif. "
        f'Kembalikan HANYA satu JSON object dengan kunci "names" berisi array string. '
        f'Format: {{"names": ["Nama 1", "Nama 2", ...]}}'
    )

    parsed, grounding_urls = await call_gemini(prompt, use_search_grounding=True)

    if isinstance(parsed, dict) and parsed.get("_parse_failed"):
        raise GenerationError(
            f"Gemini returned unparseable JSON for client_type={client_type!r}. "
            f"Raw: {parsed.get('_raw', '')[:300]}"
        )

    raw_names: list = []
    if isinstance(parsed, dict):
        candidate = parsed.get("names")
        if isinstance(candidate, list):
            raw_names = candidate
    elif isinstance(parsed, list):
        raw_names = parsed

    if not raw_names:
        raise GenerationError(
            f"Gemini returned zero names for client_type={client_type!r}."
        )

    # --- Layer 2: Post-generation normalized dedup ---
    seen_normalized: set[str] = set()
    deduped_names: list[str] = []
    excluded_count = 0

    for raw in raw_names:
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
            f"All {len(raw_names)} Gemini-generated names were duplicates of existing entries "
            f"for client_type={client_type!r}. "
            f"Consider clearing old groups or using a different category."
        )

    return GenerationResult(
        names=deduped_names,
        grounding_urls=grounding_urls,
        suggested_count=len(deduped_names),
        excluded_count=excluded_count,
    )
