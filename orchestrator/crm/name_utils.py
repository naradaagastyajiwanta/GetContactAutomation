"""
Centralized name cleaning utilities for CRM/PIC profiling.

Indonesian academic names often contain many titles that pollute search
queries. This module provides functions to strip titles, generate search
variants, and progressively relax name queries for agentic retries.

Example:
    "DR. DWI PERWITASARI WIRYANINGTYAS, SE., MM"
    → clean: "Dwi Perwitasari Wiryaningtyas"
    → variants: ["Dwi Perwitasari Wiryaningtyas", "Dwi Wiryaningtyas",
                  "Perwitasari Wiryaningtyas", "Wiryaningtyas"]
"""

from __future__ import annotations

import re

# ── Comprehensive Indonesian academic title patterns ──────────────────────
# Order matters: longer/more specific patterns first to avoid partial matches.
# These are normalized to lowercase for matching.
ACADEMIC_TITLES: set[str] = {
    # Doctoral / Professor
    "prof", "prof.", "professor",
    "dr", "dr.", "dr.h.c", "dr.h.c.",
    # Master degrees
    "m.si", "m.si.", "m.sc", "m.sc.", "m.pd", "m.pd.",
    "m.t", "m.t.", "m.m", "m.m.", "m.acc", "m.acc.",
    "m.kom", "m.kom.", "m.kes", "m.kes.", "m.hum", "m.hum.",
    "m.ag", "m.ag.", "m.h", "m.h.", "m.i.kom", "m.i.kom.",
    "m.sn", "m.sn.", "m.eng", "m.eng.", "m.phil", "m.phil.",
    "m.kep", "m.kep.", "m.farm", "m.farm.", "m.sos", "m.sos.",
    "m.ed", "m.ed.", "m.a", "m.a.", "m.p", "m.p.",
    "m.psi", "m.psi.", "m.ling", "m.ling.",
    "mm", "mm.", "mba", "mba.", "mpa", "mpa.",
    # Bachelor / Sarjana
    "s.e", "s.e.", "se", "se.",
    "s.t", "s.t.", "st", "st.",
    "s.si", "s.si.", "s.pd", "s.pd.",
    "s.h", "s.h.", "sh", "sh.",
    "s.sos", "s.sos.", "s.kom", "s.kom.",
    "s.ked", "s.ked.", "s.kep", "s.kep.",
    "s.farm", "s.farm.", "s.sn", "s.sn.",
    "s.ag", "s.ag.", "s.ip", "s.ip.",
    "s.hut", "s.hut.", "s.tp", "s.tp.",
    "s.kel", "s.kel.", "s.pi", "s.pi.",
    "s.psi", "s.psi.",
    # Other pre-nominal
    "ir", "ir.", "drs", "drs.", "dra", "dra.",
    "hj", "hj.", "h", "h.",
    # Other post-nominal
    "ph.d", "ph.d.", "phd", "phd.",
    "dba", "dba.",
    "ak", "ak.", "ca", "ca.",
    "apt", "apt.",  # Apoteker
    "sp.a", "sp.a.", "sp.pd", "sp.pd.",  # Specialist
    "cpa", "cpa.", "cma", "cma.",
}

# Pre-compiled regex for comma-separated title clusters like ", SE., MM"
_TRAILING_TITLES_RE = re.compile(
    r'[,\s]+(?:'
    + '|'.join(re.escape(t) for t in sorted(ACADEMIC_TITLES, key=len, reverse=True))
    + r')(?:\.|,|\s|$)',
    re.IGNORECASE,
)


def strip_academic_titles(name: str) -> str:
    """
    Remove all academic titles from a name, preserving only the core name.

    Example:
        "DR. DWI PERWITASARI WIRYANINGTYAS, SE., MM" → "Dwi Perwitasari Wiryaningtyas"
        "Prof. Dr. Ir. BUDI SANTOSO, M.T., Ph.D." → "Budi Santoso"
        "Dr. Abdi Dharma, S.Kom., M. Kom." → "Abdi Dharma"
    """
    # Step 1: Strip trailing comma-separated titles (", SE., MM")
    cleaned = _TRAILING_TITLES_RE.sub(' ', name)

    # Step 1b: Handle spaced compound titles like "M. Kom.", "S. Pd.", "S. Kom."
    # These get split into "M." + "Kom" — rejoin and remove them.
    cleaned = re.sub(
        r'\b([MSms])\.\s+([A-Za-z]{1,5})\.?\b',
        lambda m: '' if (m.group(1).lower() + '.' + m.group(2).lower()).rstrip('.') + '.' in ACADEMIC_TITLES
                      or (m.group(1).lower() + '.' + m.group(2).lower()) in ACADEMIC_TITLES
                  else m.group(0),
        cleaned,
    )

    # Step 2: Split into tokens and filter out title tokens
    parts = cleaned.strip().split()
    core_parts: list[str] = []
    for p in parts:
        # Normalize: strip commas and periods at edges for matching
        token = p.strip(",. ")
        if not token:
            continue
        if token.lower() in ACADEMIC_TITLES:
            continue
        # Also check with trailing period
        if (token.lower() + ".") in ACADEMIC_TITLES:
            continue
        # Skip single-letter tokens that might be title remnants (H., etc.)
        # but keep if the original name has them and they're 2+ chars
        if len(token) <= 1:
            continue
        core_parts.append(token)

    if not core_parts:
        # Fallback: if stripping removed everything, return original with basic cleanup
        return name.strip()

    # Title-case for clean output
    return " ".join(p.capitalize() if p.isupper() else p for p in core_parts)


async def ai_strip_titles(name: str) -> str:
    """Use AI to extract the core name, removing all academic titles.

    This is the primary method — AI understands Indonesian academic
    naming conventions (Dr., Prof., S.Kom., M. Kom., etc.) without
    needing a hardcoded title set.  Falls back to regex if AI fails.

    Example:
        "DR. DWI PERWITASARI WIRYANINGTYAS, SE., MM" → "Dwi Perwitasari Wiryaningtyas"
        "Dr. Abdi Dharma, S.Kom., M. Kom." → "Abdi Dharma"
    """
    from orchestrator.crm.tools import gpt_extract_structured

    result = await gpt_extract_structured(
        name,
        (
            "Extract ONLY the person's core name from this Indonesian academic name. "
            "Remove ALL academic titles, degrees, and honorifics "
            "(Dr., Prof., Ir., Drs., H., Hj., S.Kom., M.Kom., S.E., M.M., Ph.D., etc.). "
            "Keep ONLY the actual personal name parts. "
            'Return JSON: {"core_name": "..."}\n'
            "Examples:\n"
            '- "DR. DWI PERWITASARI WIRYANINGTYAS, SE., MM" → "Dwi Perwitasari Wiryaningtyas"\n'
            '- "Prof. Dr. Ir. H. BUDI SANTOSO, M.T., Ph.D." → "Budi Santoso"\n'
            '- "Dr. Abdi Dharma, S.Kom., M. Kom." → "Abdi Dharma"\n'
            '- "H. M. Ali Ramdhani, S.T., M.T." → "M. Ali Ramdhani"'
        ),
    )
    if result and result.get("core_name"):
        return result["core_name"]
    # Fallback to regex if AI unavailable
    return strip_academic_titles(name)


def build_name_variants(name: str, include_original: bool = True) -> list[str]:
    """
    Generate progressively relaxed name variants for search.

    Returns variants from most specific to least specific:
    1. Cleaned name (no titles)
    2. Title-cased version
    3. First + Last name only (skip middle)
    4. Last two name parts (common in Indonesia)
    5. First two name parts
    6. Last name only (broadest)

    All variants are deduplicated, preserving order.
    """
    variants: list[str] = []

    if include_original:
        variants.append(name.strip())

    # Clean version without titles
    cleaned = strip_academic_titles(name)
    if cleaned != name.strip():
        variants.append(cleaned)

    # Title-cased
    title_cased = " ".join(p.title() for p in cleaned.split())
    variants.append(title_cased)

    parts = cleaned.split()

    if len(parts) >= 3:
        # First + Last (skip middle names)
        variants.append(f"{parts[0]} {parts[-1]}")
        # Last two parts (common Indonesian pattern)
        variants.append(f"{parts[-2]} {parts[-1]}")
        # First two parts
        variants.append(f"{parts[0]} {parts[1]}")

    if len(parts) >= 2:
        # Last name only (broadest — combine with university for context)
        variants.append(parts[-1])

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for v in variants:
        v_lower = v.lower().strip()
        if v_lower and v_lower not in seen:
            seen.add(v_lower)
            deduped.append(v)
    return deduped


def build_search_queries_progressive(
    name: str,
    university: str,
    query_template: str = '"{name}" "{university}"',
    max_queries: int = 4,
) -> list[str]:
    """
    Build progressively relaxed search queries using name variants.

    Starts with the most specific (cleaned full name + university) and
    progressively relaxes (shorter name, no university).

    Args:
        name: Raw PIC name (may contain titles)
        university: University name
        query_template: Template with {name} and {university} placeholders
        max_queries: Maximum number of queries to generate

    Returns:
        List of queries from most to least specific.
    """
    variants = build_name_variants(name, include_original=False)
    queries: list[str] = []

    for variant in variants[:max_queries]:
        q = query_template.replace("{name}", variant).replace("{university}", university)
        queries.append(q)

    return queries
