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
│  TIER 1: Website University (MOST ACCURATE — no verify needed)
│  ─────────────────────────────────────────────────────────
│  1. Get website URL from PDDIKTI data
│  2. If no PDDIKTI website → DuckDuckGo: "nama university website"
│  3. Scrape website → find links to instagram.com/*
│  4. If found:
│     → confidence = 0.9 (very high — from official website)
│     → NO bio verification needed (already verified by website)
│     → SAVE ig_handle, status = "ig_found"
│     → DONE (skip Tier 2 & Tier 3)
│  5. If not found → proceed to Tier 2
└─────────────────────────────────────────────────────────────┘
                              │
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
│  If found: confidence = 0.60-0.70
│  → MUST do bio verification (Tier 3 below)
│  → If fail verification (confidence < 0.55) → REJECT
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 3: Google / DuckDuckGo Search (LAST RESORT)
│  ─────────────────────────────────────────────────────────
│  Search queries:
│    site:instagram.com "Nama University"
│    site:instagram.com Nama University instagram
│
│  Primary: DuckDuckGo (free, no API key needed)
│  Fallback: Serper.dev (if SERPER_API_KEY is set)
│
│  If found: confidence = 0.40-0.60
│  → MUST do bio verification
│  → If fail verification (confidence < 0.55) → REJECT
│  → If not found → university is SKIPPED (no IG handle)
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  BIO VERIFICATION (required for Tier 2 & Tier 3 results)
│  ─────────────────────────────────────────────────────────
│  Uses verify_ig_handle_with_fallback():
│  1. Fetch IG profile page for the handle
│  2. Read the profile BIO
│  3. Check if bio contains university name or related keywords
│  4. confidence_boost = +0.30 if match
│
│  Acceptance threshold:
│    initial_confidence + confidence_boost >= 0.55
│
│  Examples:
│    Handle @bem_univx_official → bio: "BEM FIKOM Universitas X" → MATCH
│    Handle @fashion_store_jakarta → bio: "Jual baju murah" → NO MATCH → REJECT
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  SAVE TO DATABASE
│  ─────────────────────────────────────────────────────────
│  UPDATE universities
│    SET ig_handle = "@handle",
│        ig_handle_verified = (confidence >= 0.6)
│  WHERE id = X
│
│  UPDATE universities
│    SET status = "ig_found"
│  WHERE id = X
└─────────────────────────────────────────────────────────────┘
```

---

## Confidence Score System

| Source | Initial Confidence | After Bio Check |
|--------|-------------------|-----------------|
| Tier 1: Website | 0.90 | Not needed |
| Tier 2: IG Web API | 0.60–0.70 | +0.30 = **0.90** |
| Tier 3: Google | 0.40–0.60 | +0.30 = **0.70–0.90** |

**Minimum to accept: 0.55**

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
Between each university. No delay between Tier 1→2→3 (they cascade synchronously).

---

## Key Functions

| Function | Purpose |
|----------|---------|
| `run_handle_search_batch(limit)` | Batch run for scheduler/manual trigger |
| `run_handle_search_for_universities(ids)` | Targeted run for specific universities |
| `_search_handle_for_uni(uni, loop)` | Core logic for one university |
| `search_ig_from_website()` | Tier 1: website scraping |
| `search_ig_handle_with_fallback()` | Tier 2: IG web search (4-tier internal) |
| `search_ig_handle()` | Tier 3: DuckDuckGo + Serper |
| `verify_ig_handle_with_fallback()` | Bio verification |

---

## Database Changes

```sql
UPDATE universities
  SET ig_handle = '@univofficial',
      ig_handle_verified = 1,
      status = 'ig_found'
  WHERE id = 123;
```

---

## Known Issues

- **Playwright IG sessions expired**: Accounts `hasetar955` and `kefey90592` — last login 13+ days ago. Session cookies invalid → Tier 0 (Playwright) fails with CAPTCHA/Timeout.
- **IG_SESSION_ID not set**: Tier 1 fails because `IG_SESSION_ID` is not configured in `.env`.
- **Tier 2 & 3 disabled**: Apify and ScrapingBot are intentionally not activated per operator request.
