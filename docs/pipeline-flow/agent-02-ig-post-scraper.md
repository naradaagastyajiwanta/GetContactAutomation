# Agent 2: IG Post Scraper

**File:** `orchestrator/agents/ig_post_scraper.py`
**Trigger:** Scheduler (every 3 hours) / Manual via PipelinePage
**Target:** Universities with `status = "ig_found"` (IG handle known)

## Purpose

Scrape Instagram posts from university IG accounts and their related accounts (BEM, humas, PMB, etc.) to collect content that may contain phone numbers and contact names.

---

## Entry Criteria

- University `status = "ig_found"` (IG handle already found by Agent 1)
- University has an `ig_handle` set
- Rolling offset: picks up from `AGENT_LAST_PROCESSED_UNIV_ID`
- Target: **100 posts per university** (configurable via `TARGET_POSTS_PER_UNIVERSITY`)

---

## Flow per University

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Check current post count
│  ─────────────────────────────────────────────────────────
│  count = get_post_count_for_university(university_id)
│
│  If count >= 100 (TARGET_POSTS_PER_UNIVERSITY):
│    → status = "ig_scraped"
│    → SKIP this university
│  Else:
│    → Proceed to scrape
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: Scrape MAIN IG Account (Tiered Fallback)
│  ─────────────────────────────────────────────────────────
│  scrape_ig_posts_with_fallback(handle)
│
│  ├─ TIER 0: Playwright Stealth Browser (free)
│  │           → Headless Chromium, login via stored credentials
│  │           → Navigate to instagram.com/{handle}
│  │           → Scroll to load posts
│  │           → Extract: post_url, image_url, caption, timestamp
│  │
│  ├─ TIER 1: IG Web API (IG_SESSION_ID cookie)
│  │           → Direct GraphQL API call, no browser needed
│  │           → Much faster, lower rate limit risk
│  │
│  ├─ TIER 2: Apify (DISABLED)
│  │
│  └─ TIER 3: ScrapingBot.io (DISABLED)
│
│  On success: save posts to ig_posts table (source_ig_type = "main")
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Check if Target Reached (≥ 100 posts)
│  ─────────────────────────────────────────────────────────
│  If current_count >= 100:
│    → status = "ig_scraped"
│    → DONE
│  Else:
│    → Proceed to scrape related IG accounts
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Scrape RELATED IG Accounts (BEM, Humaskes, PMB, ...)
│  ─────────────────────────────────────────────────────────
│  related_igs = get_related_igs_for_university(university_id)
│
│  For each related IG (discovered by Agent 4):
│    If current_count >= 100 → BREAK
│
│    scrape_ig_posts_with_fallback(related_handle)
│      → Same 4-tier fallback as main IG
│      → Save to ig_posts (source_ig_type = relation_type)
│
│    relation_type values:
│      - "bem"         → BEM account
│      - "humas"       → Public relations
│      - "pmb"         → Admissions / PMB
│      - "kemahasiswaan" → Student affairs
│      - "alumni"      → Alumni
│      - other         → Generic related account
│
│    Delay: IG_REQUEST_DELAY_SECONDS (5s default)
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: Final Status Update
│  ─────────────────────────────────────────────────────────
│  If posts found (total > 0):
│    → status = "ig_scraped"
│
│  If 0 posts found (all tiers failed):
│    → status remains "ig_found" (will retry on next cycle)
│    → Reason: account may be private, deleted, or renamed
└─────────────────────────────────────────────────────────────┘
```

---

## What Gets Scraped from Each Post

| Field | Source | Description |
|-------|--------|-------------|
| `post_url` | IG API / page | Full URL to the post |
| `image_url` | IG API / page | URL to the post image (for GPT Vision OCR) |
| `caption` | IG API / page | Post text/caption (can contain phone numbers) |
| `post_timestamp` | IG API / page | When the post was published |
| `source_ig_handle` | From loop | Which IG account this came from |
| `source_ig_type` | From loop | "main", "related_bem", "related_humas", etc. |

---

## Smart Deeper Mode

When running targeted (for specific universities), Agent 2 uses "deeper" mode if posts already exist:

```python
if known_urls:  # University already has posts from previous scrape
    scrape_fn = partial(scrape_ig_posts_with_fallback, handle, deeper=True)
    # deeper=True: paginates further back to find OLDER posts
    # Excludes posts already in known_urls
```

This helps universities with many posts find ones that weren't covered in the initial scrape.

---

## Stop Mechanism

```python
for uni in universities:
    if is_paused():           # ← Checked every iteration
        log.info("[Agent2] Bot paused during batch, stopping early")
        break
    uni_id = uni["id"]
    # ... scrape ...
    # Finishes current university + all its related IGs before stopping
```

Agent completes the current university (including all related IG scraping) before exiting.

---

## Delay

```python
await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)  # 5s
```
Applied:
1. Between each university in the main loop
2. Between each related IG scrape

```python
await asyncio.sleep(1)  # Vision API rate limit (Agent 3)
```
Only in Agent 3, not here.

---

## Rolling Mechanism

Same as other agents:
```
last_id saved to config table after each batch
next batch picks up from last_id + 1
```

---

## Why 100 Posts?

Indonesian university IG accounts typically have:
- **Main account**: 50-200 posts (most recent)
- **BEM account**: 20-100 posts
- **Humas/PMB**: 10-50 posts

100 is a reasonable target that captures most content without over-scraping rate-limited accounts.

---

## Known Issues

- **All tiers broken**: IG sessions expired (`hasetar955`, `kefey90592`), `IG_SESSION_ID` not set, Apify/ScrapingBot disabled.
- **Result: 0 posts for ALL universities** — systemic failure, not per-university.
- **Fix**: User must re-login to IG accounts and export fresh `sessionid` cookies.

---

## Key Functions

| Function | Purpose |
|----------|---------|
| `run_post_scrape_batch(limit)` | Batch run for scheduler/manual |
| `run_post_scrape_for_universities(ids)` | Targeted run |
| `_save_posts()` | Save posts to `ig_posts` table |
| `scrape_ig_posts_with_fallback()` | 4-tier scraping (in `instagram.py`) |
