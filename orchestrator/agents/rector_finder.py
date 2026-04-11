"""
Agent 5: Rector Name Finder

Finds the rector's name for a university using a cascade of strategies:
1. DuckDuckGo Search (free) / Serper (legacy fallback) — most reliable
2. University website scraping — look for "Rektor", "Pimpinan"
3. GPT extraction — pass scraped text to GPT-4o-mini

Results are saved to universities.rector_name.
"""

import re

import httpx

from orchestrator.config import is_paused, log, cfg, chat_kwargs
from orchestrator.llm import gateway
from orchestrator import duckduckgo_client
from orchestrator.db import get_university_by_id, update_university_rector_name


async def find_rector_name(university_id: int) -> str | None:
    """
    Find rector name for a university using cascade strategy.
    Saves result to DB and returns the name, or None if not found.
    """
    uni = await get_university_by_id(university_id)
    if not uni:
        log.warning("rector_finder: university %d not found", university_id)
        return None

    # Already have rector name?
    if uni.get("rector_name"):
        return uni["rector_name"]

    uni_name = uni["name"]
    website = uni.get("website") or ""
    log.info("rector_finder: searching rector for %s (id=%d)", uni_name, university_id)

    # Strategy 1: Web Search (DuckDuckGo primary, Serper fallback)
    name = await _search_web(uni_name)
    if name:
        log.info("rector_finder: found via web search: %s", name)
        await update_university_rector_name(university_id, name)
        return name

    # Strategy 2: University website scraping
    if website:
        name = await _scrape_website(website, uni_name)
        if name:
            log.info("rector_finder: found via website: %s", name)
            await update_university_rector_name(university_id, name)
            return name

    # Strategy 3: GPT extraction from search snippets
    name = await _gpt_extract(uni_name)
    if name:
        log.info("rector_finder: found via GPT: %s", name)
        await update_university_rector_name(university_id, name)
        return name

    log.info("rector_finder: could not find rector name for %s", uni_name)
    return None



async def _search_web(uni_name: str) -> str | None:
    """Search for rector name using DuckDuckGo (free, primary) and Serper (fallback)."""
    # Primary: DuckDuckGo
    name = await _search_duckduckgo(uni_name)
    if name:
        return name

    # Fallback: Serper (if configured)
    return await _search_serper(uni_name)


async def _search_duckduckgo(uni_name: str) -> str | None:
    """Search for rector name using DuckDuckGo (free, no API key)."""
    query = f"nama rektor {uni_name} 2024 2025"
    try:
        results = await duckduckgo_client.async_search_text(query, max_results=5, region="id-id")

        if not results:
            return None

        # Collect text snippets
        snippets = []
        for item in results[:5]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            snippets.append(f"{title} - {snippet}")

        if not snippets:
            return None

        # Extract name from snippets using patterns
        combined = "\n".join(snippets)
        name = _extract_name_from_text(combined, uni_name)
        if name:
            return name

        # Fallback: use GPT to extract from snippets
        return await _gpt_extract_from_text(combined, uni_name)

    except Exception as e:
        log.warning("rector_finder: DuckDuckGo search failed: %s", e)
        return None

async def _search_serper(uni_name: str) -> str | None:
    """Search for rector name using Serper Google Search API."""
    api_key = cfg.SERPER_API_KEY
    if not api_key:
        return None

    query = f"nama rektor {uni_name} 2024 2025"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                json={"q": query, "gl": "id", "hl": "id", "num": 5},
                headers={"X-API-KEY": api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        # Collect text snippets
        snippets = []
        for item in data.get("organic", [])[:5]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            snippets.append(f"{title} — {snippet}")

        if data.get("knowledgeGraph", {}).get("description"):
            snippets.append(data["knowledgeGraph"]["description"])

        if not snippets:
            return None

        # Extract name from snippets using patterns
        combined = "\n".join(snippets)
        name = _extract_name_from_text(combined, uni_name)
        if name:
            return name

        # Fallback: use GPT to extract from snippets
        return await _gpt_extract_from_text(combined, uni_name)

    except Exception as e:
        log.warning("rector_finder: Serper search failed: %s", e)
        return None


async def _scrape_website(website: str, uni_name: str) -> str | None:
    """Scrape university website for rector name."""
    # Normalize URL
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"

    # Try common paths where rector info might be
    paths_to_try = [
        "",  # homepage
        "/profil",
        "/about",
        "/tentang",
        "/pimpinan",
        "/profil/pimpinan",
        "/tentang/pimpinan",
        "/profil-pimpinan",
    ]

    for path in paths_to_try:
        url = website.rstrip("/") + path
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                if resp.status_code != 200:
                    continue

                text = resp.text
                # Look for rector patterns in HTML
                name = _extract_name_from_text(text, uni_name)
                if name:
                    return name

        except Exception:
            continue

    return None


def _extract_name_from_text(text: str, uni_name: str) -> str | None:
    """Extract rector name from text using regex patterns."""
    # Common patterns for rector names in Indonesian text
    patterns = [
        # "Rektor, Prof. Dr. Name Here" or "Rektor: Prof. Dr. Name Here"
        r"[Rr]ektor[,:\s]+(?:Prof\.?\s*)?(?:Dr\.?\s*)?(?:Ir\.?\s*)?(?:H\.?\s*)?([A-Z][a-zA-Z\.\s,\-']{5,60})",
        # "Rektor Universitas X, Prof. Dr. Name Here"
        r"[Rr]ektor\s+(?:Universitas|Politeknik|Institut|Sekolah\s+Tinggi|Akademi|UIN|IAIN|UNJ?)\s+[^,]+[,\s]+(?:Prof\.?\s*)?(?:Dr\.?\s*)?(?:Ir\.?\s*)?(?:H\.?\s*)?([A-Z][a-zA-Z\.\s,\-']{5,60})",
        # "Prof. Dr. Name Here sebagai Rektor" or "Prof. Dr. Name Here, Rektor"
        r"(?:Prof|Dr|Ir)\.\s*(?:Dr\.?\s*)?(?:Ir\.?\s*)?(?:H\.?\s*)?([A-Z][a-zA-Z\.\s,\-']{5,60})\s*(?:,\s*\w+\.?\s*)*(?:sebagai\s+)?[Rr]ektor",
        # "Rektor yang baru terpilih adalah Prof. Dr. Name"
        r"[Rr]ektor\s*(?:yang\s+)?(?:baru\s+)?(?:terpilih\s+)?(?:adalah\s+)?(?:yaitu\s+)?(?:Prof\.?\s*)?(?:Dr\.?\s*)?(?:H\.?\s*)?([A-Z][a-zA-Z\.\s,\-']{5,60})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip().rstrip(",. ")
            name = _clean_rector_name(name)
            if _is_valid_person_name(name, uni_name):
                return name

    return None


# Keywords that should NOT appear in a person's name
_REJECT_KEYWORDS = {
    # Institution types
    "universitas", "politeknik", "institut", "sekolah", "tinggi", "akademi",
    "uin", "iain", "stain", "unj", "ugm", "itb", "ipb", "its", "undip",
    "unair", "unpad", "unhas", "unsri", "unri", "unand", "uns", "usu",
    "negeri", "swasta", "fakultas", "program", "studi", "pascasarjana",
    # Common Indonesian words (not names)
    "yang", "dan", "dari", "untuk", "dengan", "ini", "itu", "adalah",
    "akan", "pada", "oleh", "dalam", "juga", "khususnya", "tentang",
    "bahwa", "atau", "serta", "maupun", "hingga", "sampai", "selain",
    "termasuk", "terutama", "antara", "melalui", "terhadap", "mengenai",
    # Common verbs/context words that appear in sentences about rectors
    "melantik", "dilantik", "menjadi", "sebagai", "terpilih", "dipilih",
    "resmi", "baru", "masa", "periode", "jabatan", "para", "wakil",
    "dekan", "dosen", "mahasiswa", "rektor", "sekretaris", "ketua",
    # City/region names (not person names)
    "indonesia", "banda", "aceh", "medan", "jakarta", "bandung", "surabaya",
    "makassar", "semarang", "yogyakarta", "malang", "denpasar", "padang",
    "palembang", "manado", "jayapura", "pontianak", "samarinda", "lampung",
}


def _normalize_words(text: str) -> list[str]:
    """Normalize text into clean lowercase words, stripping punctuation."""
    return [re.sub(r'[,.\-\'\";:!?()]+', '', w).lower() for w in text.split() if w.strip()]


def _is_valid_person_name(name: str, uni_name: str) -> bool:
    """Validate that extracted text is actually a person's name, not an institution."""
    if not name:
        return False

    words = name.split()
    clean_words = _normalize_words(name)

    # Must have at least 2 words
    if len(words) < 2:
        return False

    # Reject if any word (cleaned) matches reject keywords
    for w in clean_words:
        if w in _REJECT_KEYWORDS:
            log.debug("rector_finder: rejected '%s' — contains keyword '%s'", name, w)
            return False

    # Reject if the name overlaps heavily with the university name
    uni_words = _normalize_words(uni_name)
    uni_set = set(uni_words)
    overlap = sum(1 for w in clean_words if w in uni_set and len(w) > 2)
    if overlap >= max(1, len(clean_words) * 0.5):
        log.debug("rector_finder: rejected '%s' — overlaps with university name '%s'", name, uni_name)
        return False

    # Reject if name is mostly uppercase abbreviations (e.g., "UIN AR")
    uppercase_words = sum(1 for w in words if w.isupper() and len(w) > 1)
    if uppercase_words >= max(1, len(words) * 0.5):
        log.debug("rector_finder: rejected '%s' — too many uppercase abbreviations", name)
        return False

    # Reject very short names (likely abbreviations)
    alpha_only = re.sub(r'[^a-zA-Z]', '', name)
    if len(alpha_only) < 6:
        log.debug("rector_finder: rejected '%s' — too short", name)
        return False

    return True


def _clean_rector_name(name: str) -> str:
    """Clean up extracted rector name."""
    # First pass: truncate at known sentence-boundary words
    boundary_pattern = (
        r'\s+(?:melantik|dilantik|menjadi|sebagai|terpilih|dipilih|'
        r'resmi|pada|dalam|untuk|yang|dan|dengan|oleh|saat|ketika|'
        r'mulai|sejak|hingga|sampai|akan|telah|sudah|belum)\b.*$'
    )
    name = re.sub(boundary_pattern, '', name, flags=re.IGNORECASE)

    # Second pass: keep only name-like words (capitalized or academic titles)
    # Stop at the first lowercase word that isn't a known title/connector
    _TITLE_PATTERNS = {'m', 'ma', 'mag', 'ag', 'si', 'pd', 'hum', 'sos', 'kom',
                       'eng', 'sc', 'phil', 'ed', 'lc', 'mm', 'mba', 'mpa'}
    words = name.split()
    cleaned = []
    for w in words:
        stripped = w.rstrip('.,;:')
        # Keep: capitalized words, titles with dots (M.Ag, S.Pd), single uppercase letters
        if (stripped[0:1].isupper() or
                stripped.rstrip('.').lower() in _TITLE_PATTERNS or
                re.match(r'^[A-Z]\.?$', stripped) or
                stripped in ('bin', 'binti', 'van', 'de', 'el', 'al')):
            cleaned.append(w)
        else:
            # Lowercase non-title word — name has ended
            break
    name = ' '.join(cleaned)

    # Remove trailing punctuation
    name = re.sub(r'[,\.\s]+$', '', name)
    # Remove trailing institution name fragments
    name = re.sub(
        r'\s+(?:Universitas|Politeknik|Institut|Sekolah|Akademi|UIN|IAIN|Negeri|Swasta).*$',
        '', name, flags=re.IGNORECASE,
    )
    name = name.strip()
    return name


async def _gpt_extract(uni_name: str) -> str | None:
    """Use GPT to find rector name from general knowledge."""
    return await _gpt_extract_from_text("", uni_name)


async def _gpt_extract_from_text(text: str, uni_name: str) -> str | None:
    """Use GPT to extract rector name from provided text."""
    # If OAuth is off and no API key is configured, skip the LLM call.
    # When OAuth is on, the gateway handles the proxy path and only needs
    # OPENAI_API_KEY for the fallback path, so we proceed optimistically.
    if not cfg.CHATGPT_OAUTH_ENABLED and not cfg.OPENAI_API_KEY:
        return None

    prompt_parts = [
        f"Siapa nama lengkap Rektor {uni_name} saat ini (2024-2025)?",
    ]
    if text:
        prompt_parts.append(f"\nBerikut informasi yang ditemukan:\n{text[:2000]}")

    prompt_parts.append(
        "\nJawab HANYA dengan nama lengkap ORANG (termasuk gelar Prof/Dr jika ada). "
        "Contoh jawaban yang benar: 'Prof. Dr. Budi Santoso, M.Si.'\n"
        "JANGAN jawab dengan nama universitas, nama kota, atau nama institusi.\n"
        "Jika tidak tahu atau tidak yakin, jawab 'UNKNOWN'."
    )

    try:
        resp = await gateway.chat_completions_create(
            model=cfg.AGENT_MODEL,
            messages=[{"role": "user", "content": "\n".join(prompt_parts)}],
            **chat_kwargs(cfg.AGENT_MODEL, temperature=0.1, max_tokens=100),
        )
        answer = resp.choices[0].message.content.strip()

        if answer.upper() in ("UNKNOWN", "TIDAK DIKETAHUI", "-"):
            return None

        # Basic validation
        if len(answer.split()) < 2 or len(answer) > 100:
            return None

        # Validate it's a person's name, not institution
        if not _is_valid_person_name(answer, uni_name):
            log.debug("rector_finder: GPT answer rejected as not a person name: '%s'", answer)
            return None

        return answer

    except Exception as e:
        log.warning("rector_finder: GPT extraction failed: %s", e)
        return None


async def run_rector_finder_batch(limit: int = 20) -> dict:
    """
    Batch find rector names for universities that don't have one yet.
    Called by scheduler.
    """
    if is_paused():
        log.info("[Agent5] Bot is paused, skipping rector finder")
        return {"checked": 0, "found": 0}

    from orchestrator.db import get_db, _rows_to_dicts

    async with get_db() as db:
        cursor = await db.execute(
            """SELECT u.id, u.name FROM universities u
               JOIN audiensi_conversations a ON a.university_id = u.id
               WHERE u.rector_name IS NULL
               AND a.state = 'QUEUED'
               LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        universities = _rows_to_dicts(rows)

    found = 0
    for uni in universities:
        if is_paused():
            log.info("[Agent5] Bot paused during batch, stopping early")
            break
        name = await find_rector_name(uni["id"])
        if name:
            found += 1

    log.info("rector_finder batch: checked %d universities, found %d rector names", len(universities), found)
    return {"checked": len(universities), "found": found}
