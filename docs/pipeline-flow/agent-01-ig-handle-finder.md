# Agent 1: IG Handle Finder

**File:** `orchestrator/agents/ig_handle_finder.py`
**Trigger:** Scheduler (every 2 hours) / Manual via PipelinePage
**Target:** Universities with `status = "pending"` (no IG handle yet)

## Purpose

Find the official Instagram handle (`@univname`) for each university that doesn't have one yet.

---

## Entry Criteria

- University `status = "pending"`
- University does NOT have `ig_handle` set
- Rolling offset: picks up from `AGENT_LAST_PROCESSED_UNIV_ID`

---

## Flow per University

```
┌─────────────────────────────────────────────────────────────┐
│  TIER 1: Google / DuckDuckGo Search (FAST — broad coverage)
│  ─────────────────────────────────────────────────────────
│  Search queries (tried in order):
│    site:instagram.com "Nama University"
│    site:instagram.com Nama University instagram
│
│  Primary: DuckDuckGo (free, no API key needed)
│  Fallback: Serper.dev (if SERPER_API_KEY is set)
│
│  If found: initial confidence = 0.40–0.65
│  → WAJIB bio verification (threshold ketat: ≥ 0.65)
│  → If confidence < 0.65 after bio → REJECT, try Tier 2
│  → If confidence ≥ 0.65 → ACCEPT, DONE
└─────────────────────────────────────────────────────────────┘
                              │
                  confidence < 0.65 or not found
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 2: IG Web Search (Playwright / IG Session)
│  ─────────────────────────────────────────────────────────
│  Uses search_ig_handle_with_fallback() which is itself
│  a 4-tier system:
│
│  ├─ Tier 0: Playwright Stealth Browser (free)
│  │           → pw_search_profiles(university_name)
│  │           → Ban-resistant headless browser
│  │
│  ├─ Tier 1: IG Web API (IG_SESSION_ID cookie)
│  │           → Direct GraphQL search
│  │
│  ├─ Tier 2: Apify (DISABLED — no API key)
│  │
│  └─ Tier 3: ScrapingBot (DISABLED — no search API)
│
│  If found: initial confidence = 0.60–0.70
│  → WAJIB bio verification (threshold standard: ≥ 0.55)
│  → If confidence < 0.55 after bio → REJECT, try Tier 3
│  → If confidence ≥ 0.55 → ACCEPT, DONE
└─────────────────────────────────────────────────────────────┘
                              │
                  confidence < 0.55 or not found
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 3: Website Scraping (MOST ACCURATE — safety net)
│  ─────────────────────────────────────────────────────────
│  1. Get website URL from DB (if already saved)
│  2. If not → DuckDuckGo: '"{name}" site:ac.id OR site:sch.id'
│  3. If not → Serper.dev legacy fallback (if SERPER_API_KEY set)
│  4. Scrape website HTML → regex untuk instagram.com/* links
│  5. Filter sub-entity handles (bem_, humas_, klinik_, dll)
│
│  If found:
│     → confidence = 0.90 (very high — dari website resmi sendiri)
│     → NO bio verification needed
│     → ACCEPT, DONE
│  If not found → university SKIPPED (no IG handle)
│
│  Note: website_url selalu disimpan ke DB meski handle tidak ada
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  BIO VERIFICATION (untuk Tier 1 & Tier 2, bukan Tier 3)
│  ─────────────────────────────────────────────────────────
│  Uses verify_ig_handle_with_fallback():
│  1. Fetch IG profile → baca bio, full_name, external_url
│  2. Hitung confidence_boost berdasarkan:
│     +0.15  unique words universitas ada di bio
│     +0.10  location word (kota) ada di bio
│     +0.10  bio keywords: resmi, official, kampus, dll
│     +0.10  domain .ac.id di external_url atau bio
│     −0.15  bio kosong
│     −0.25  sub-department handle (bem_, kemahasiswaan_, dll)
│     −0.30  bio = olshop / personal / fan page
│     −0.35  bio = klinik / rumah sakit / apotek (subsidiary)
│
│  final_confidence = initial_confidence + boost
│
│  Threshold per tier:
│    Tier 1 (Google): final_confidence ≥ 0.65
│    Tier 2 (IG Web): final_confidence ≥ 0.55
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  SAVE TO DATABASE
│  ─────────────────────────────────────────────────────────
│  UPDATE universities
│    SET ig_handle = "@handle",
│        ig_handle_verified = (confidence >= 0.6),
│        status = "ig_found"
│  WHERE id = X
└─────────────────────────────────────────────────────────────┘
```

---

## Confidence Score System

| Tier | Source | Initial | Threshold Accept | Bio Verify |
|------|--------|---------|-----------------|-----------|
| **1** | Google / DuckDuckGo | 0.40–0.65 | **≥ 0.65** (strict) | ✅ Wajib |
| **2** | IG Web API (Playwright → Session) | 0.60–0.70 | **≥ 0.55** (standard) | ✅ Wajib |
| **3** | Website Scraping | 0.90 | — (langsung accept) | ❌ Tidak perlu |

`ig_verified = 1` jika final_confidence ≥ **0.60**

**Tier 1 threshold lebih ketat (0.65)** karena Google Search hasilnya lebih broad — bio confirmation wajib kuat sebelum diterima. Tier 2 & 3 lebih selektif secara hasil, threshold standar 0.55 cukup.

---

## Stop Mechanism

```python
for uni in universities:
    if is_paused():           # ← Checked every iteration
        log.info("[Agent1] Bot paused during batch, stopping early")
        break
    try:
        detail = await _search_handle_for_uni(uni, loop)
        ...
```

Agent finishes the current university, saves `last_processed_id`, then exits the loop.

---

## Delay

```python
await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)  # default: 5 seconds
```
Antara setiap universitas. Dalam satu universitas, ada delay tambahan sebelum bio verify:
- Tier 1 (Google → bio verify): `await asyncio.sleep(2)`
- Tier 2 (IG Web → bio verify): `await asyncio.sleep(3)`

---

## Key Functions

| Function | Purpose |
|----------|---------|
| `run_handle_search_batch(limit)` | Batch run for scheduler/manual trigger |
| `run_handle_search_for_universities(ids)` | Targeted run for specific universities |
| `_search_handle_for_uni(uni, loop)` | Core logic for one university |
| `search_ig_handle()` | **Tier 1**: DuckDuckGo + Serper fallback |
| `search_ig_handle_with_fallback()` | **Tier 2**: IG web search (Playwright → Session) |
| `search_ig_from_website()` | **Tier 3**: Website scraping |
| `verify_ig_handle_with_fallback()` | Bio verification (Tier 1 & 2 only) |

---

## Database Changes

```sql
UPDATE universities
  SET ig_handle = '@univofficial',
      ig_verified   = 1,  -- jika confidence >= 0.6
      website       = 'https://...',  -- jika ditemukan di Tier 3
      status        = 'ig_found'
WHERE id = 123;
```

---

## Known Issues

- **Playwright sessions expired**: Accounts `hasetar955` and `kefey90592` — last login 13+ days ago. Session cookies invalid → Tier 2 (Playwright sub-tier) fails with CAPTCHA/Timeout.
- **IG_SESSION_ID not set**: IG direct session (Tier 2 sub-tier 1) tidak aktif karena tidak dikonfigurasi di `.env`.
- **Apify disabled**: Tidak ada API key → dikomentari dalam kode.
- **Efektif sekarang**: Tier 1 (Google/DDG) + Tier 3 (Website Scraping) yang paling sering aktif.
