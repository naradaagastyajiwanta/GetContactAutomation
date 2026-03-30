# Pipeline Flow Documentation

Detailed documentation for every agent in the GetContactAI autonomous outreach pipeline.

## Table of Contents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 1 | [IG Handle Finder](./agent-01-ig-handle-finder.md) | `orchestrator/agents/ig_handle_finder.py` | Find Instagram handle for each university |
| 2 | [IG Post Scraper](./agent-02-ig-post-scraper.md) | `orchestrator/agents/ig_post_scraper.py` | Scrape posts from university IG accounts |
| 3 | [Phone Extractor](./agent-03-phone-extractor.md) | `orchestrator/agents/ig_phone_extractor.py` | Extract phone numbers via GPT Vision OCR |
| 4 | [BEM Discovery](./agent-04-bem-discovery.md) | `orchestrator/agents/bem_finder.py` | Discover related IG accounts (BEM, humas, PMB) |
| 5 | [Rector Finder](./agent-05-rector-finder.md) | `orchestrator/agents/rector_finder.py` | Find rector's name for formal outreach |

## Pipeline Funnel

```
pending
  │
  │  Agent 1: Find IG Handle
  ▼
ig_found
  │
  │  Agent 4: Discover BEM & Related Accounts
  ▼
bem_discovered
  │
  │  Agent 2: Scrape IG Posts (main + related accounts)
  ▼
ig_scraped
  │
  │  Agent 3: Extract Phone Numbers (GPT Vision OCR)
  ▼
contacts_found
  │
  │  WhatsApp Outreach: AI Chatbot
  ▼
contacted
  │
  │  Follow-up, Audiensi Scheduling
  ▼
got_number
```

## Stop Mechanism

All agents respect the global `is_paused()` flag. When an operator clicks **Stop Pipeline** in the frontend:

1. Frontend calls `POST /control/pause`
2. Backend sets `set_paused(True)`
3. Each agent checks `is_paused()` at the top of every loop iteration
4. Agent finishes the **current university** then breaks out of the loop
5. Rolling position is saved so the next run continues from where it left off

See: `orchestrator/config.py` → `is_paused()` / `set_paused()`

## Rolling Mechanism

All batch agents use `AGENT_LAST_PROCESSED_UNIV_ID` in the `config` DB table to track position. This prevents reprocessing the same universities across scheduler runs.

```
Batch 1: universities id 1-50  → saved last_id = 50
Batch 2: universities id 51-100 → saved last_id = 100
...
After all processed: last_id reset to 0
```

## Scheduler Configuration

Agents run automatically via APScheduler (times in WIB / UTC+7):

| Agent | Schedule | Config Key |
|-------|----------|------------|
| Agent 1: Find IG Handles | Every 2 hours | `HANDLE_FINDER_CRON` |
| Agent 2: Scrape IG Posts | Every 3 hours | `POST_SCRAPER_CRON` |
| Agent 3: Extract Phones | Every 1 hour | `PHONE_EXTRACTOR_CRON` |
| Agent 4: Discover BEM | Every 4 hours | `BEM_DISCOVERY_CRON` |
| Agent 5: Find Rectors | 17:00 daily | `RECTOR_FINDER_CRON` |

## Rate Limiting

| Setting | Default | Purpose |
|---------|---------|---------|
| `IG_REQUEST_DELAY_SECONDS` | 5s | Delay between university/IG requests |
| Vision API sleep | 1s | Delay between GPT Vision calls |
| `MAX_CONCURRENT_CHATS` | 3 | Max simultaneous WhatsApp AI conversations |
