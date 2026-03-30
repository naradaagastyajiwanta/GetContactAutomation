# Agent 4: BEM & Related IG Discovery

**File:** `orchestrator/agents/bem_finder.py`
**Trigger:** Scheduler (every 4 hours) / Manual via PipelinePage
**Target:** Universities with `status = "ig_found"` (IG handle known)

## Purpose

Discover **related Instagram accounts** for each university by analyzing who the official university IG account follows. These related accounts (BEM, humas, PMB) are where Agent 2 finds contact information that the main university account doesn't post.

---

## Key Insight

Official university IG accounts typically **follow** their own sub-organizations:
- `@bem_universitasx` — Student council
- `@humas_universitasx` — Public relations
- `@pmb_universitasx` — Admissions
- `@kemahasiswaan_universitasx` — Student affairs

Agent 4 exploits this by fetching the following list and classifying these accounts.

---

## Entry Criteria

- University `status = "ig_found"` (IG handle known)
- University has an `ig_handle` set
- Rolling offset: picks up from `AGENT_LAST_PROCESSED_UNIV_ID`

---

## Flow per University

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Get Official IG Following List
│  ─────────────────────────────────────────────────────────
│  ig_handle = university.ig_handle  (e.g. "@universitasx")
│
│  following = get_ig_following(ig_handle, limit=300)
│
│  Uses Playwright to:
│    1. Open instagram.com/{ig_handle}
│    2. Click "Following" button
│    3. Scroll through the following list
│    4. Extract: username, full_name, is_verified
│
│  Returns up to 300 accounts
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2A: Following List Found
│  ─────────────────────────────────────────────────────────
│  related = find_related_accounts_from_following(following, uni_name)
│
│  Classification algorithm scores each followed account:
│
│  BEM accounts (bem):
│    Keywords: "bem", "badan eksekutif", "mahasiswa", "senat"
│    Boost: username or full_name contains university name
│    Penalty: if full_name looks like a clinic/hospital/store
│
│  Humaskes accounts (humas):
│    Keywords: "humas", "kep藻", "hubungan masyarakat", "protokol"
│
│  PMB accounts (pmb):
│    Keywords: "pmb", "ppmb", "pendaftaran", "admisi", "Seleksi"
│
│  Kemahasiswaan accounts (kemahasiswaan):
│    Keywords: "kemahasiswaan", "mahasiswa", "kemahasiswa"
│
│  Alumni accounts (alumni):
│    Keywords: "alumni", "alumni association"
│
│  Each account gets a confidence score (0.0 - 1.0)
│  Minimum to save: confidence >= 0.40
└─────────────────────────────────────────────────────────────┘
                              │
                              │  (following list empty or failed)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2B: No Following — Web Search Fallback
│  ─────────────────────────────────────────────────────────
│  related = search_related_accounts_via_search(uni_name)
│
│  Uses Google/DuckDuckGo to find related accounts:
│    Query: "site:instagram.com bem {university_name}"
│    Query: "site:instagram.com humas {university_name}"
│    Query: "site:instagram.com pmb {university_name}"
│
│  Falls back to: Serper Google Search (if API key set)
│
│  Same classification + confidence scoring
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Save Related Accounts to DB
│  ─────────────────────────────────────────────────────────
│  For each related account (confidence >= 0.40):
│
│    add_related_ig(
│      university_id = X,
│      ig_handle    = "@bem_univx",
│      relation_type = "bem",       # bem, humas, pmb, dll
│      source        = "official_following",  # or "web_search"
│      confidence    = 0.75,
│    )
│
│  First BEM account found (highest confidence):
│    → update universities SET bem_handle = "@bem_univx"
│
│  Multiple related accounts CAN be saved per university
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Update Status
│  ─────────────────────────────────────────────────────────
│  If related_igs_added > 0:
│    → status = "bem_discovered"
│    (advances the funnel: ig_found → bem_discovered)
│
│  If related_igs_added == 0:
│    → status remains "ig_found" (will retry next cycle)
│    → status stored as "no_following" or "not_found"
└─────────────────────────────────────────────────────────────┘
```

---

## Why the Following List Works

```
Official IG @universitasx follows:
  ✅ @bem_universitasx       ← BEM (primary contact source)
  ✅ @humas_universitasx     ← Public relations
  ✅ @pmb_universitasx       ← Admissions
  ✅ @kemahasiswaan_univx    ← Student affairs
  ✅ @fakultasEkonomi_UnivX ← Faculty account
  ✅ @univx_official         ← (their own account — skip)
  ❌ @fashion_hits_jakarta   ← (random follow — low confidence)
  ❌ @klinik_pratama_univx   ← (subsidiary — penalize)
```

---

## Confidence Scoring

```
base_score = 0.5

+0.20  username contains university name (e.g. "bem_universitasx")
+0.15  full_name contains university name
+0.15  matches BEM/humas/pmb keyword
+0.10  is_verified = true
-0.20  matches department keywords (fakultas, ft, fisip)
-0.35  matches subsidiary keywords (klinik, rumah sakit, lab)
```

**Minimum to save: 0.40**

---

## Stop Mechanism

```python
for uni in universities:
    if is_paused():           # ← Checked every iteration
        log.info("[Agent4-BEM] Bot paused during batch, stopping early")
        break
    try:
        detail = await _discover_bem_for_uni(uni, loop)
        ...
```

---

## Delay

```python
await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)  # 5 seconds
```
Applied between each university.

---

## Why Discover Related Accounts?

Main university IG accounts post about:
- Events, announcements, news
- **Rarely**: personal contact numbers

BEM and humas accounts post about:
- Event organizers with contact persons
- **Contact person embedded in flyer images**
- WhatsApp group links
- Personal phone numbers for registration

Agent 4 unlocks Agent 2 to scrape these related accounts → more posts → more phone extractions.

---

## Database Schema

```sql
-- Related IG accounts
CREATE TABLE related_igs (
  id INTEGER PRIMARY KEY,
  university_id INTEGER,
  ig_handle TEXT,
  relation_type TEXT,  -- bem, humas, pmb, kemahasiswaan, alumni, dll
  source TEXT,         -- official_following, web_search
  confidence REAL,
  scraped BOOLEAN DEFAULT 0,
  FOREIGN KEY (university_id) REFERENCES universities(id)
);

-- University gets bem_handle column
ALTER TABLE universities ADD COLUMN bem_handle TEXT;
```

---

## Key Functions

| Function | Purpose |
|----------|---------|
| `run_bem_discovery_batch(limit)` | Batch run for scheduler |
| `run_bem_discovery_for_universities(ids)` | Targeted run |
| `_discover_bem_for_uni()` | Core logic: following list + classification |
| `get_ig_following()` | Playwright: scrape following list from IG profile |
| `find_related_accounts_from_following()` | Classification scoring |
| `search_related_accounts_via_search()` | Web search fallback |

---

## Difference from Agent 1

| | Agent 1: IG Handle Finder | Agent 4: BEM Discovery |
|-|--------------------------|------------------------|
| Finds | **Main university IG** | **Related sub-accounts** |
| Source | Website, IG search, Google | Official IG's following list |
| Target | `@universitasx_official` | `@bem_universitasx`, `@humas_...` |
| Confidence | 0.55 minimum | 0.40 minimum |
| Funnel step | `pending` → `ig_found` | `ig_found` → `bem_discovered` |
