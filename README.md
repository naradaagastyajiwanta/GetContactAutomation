# GetContactAI Agent

**AI-Powered Outreach & Intelligence Platform for Indonesian Universities**

Automated WhatsApp outreach with AI-driven conversations to collect university contact information, enriched with OSINT intelligence, CRM profiles, audiensi scheduling, and DMS integration.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-20+-339933?style=flat&logo=node.js&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?style=flat&logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## What It Does

GetContactAI automates outreach to Indonesian universities through a multi-channel, AI-driven pipeline:

| Channel | Description |
|---------|-------------|
| **Contact Collection** | PDDIKTI → IG Handle Discovery → IG Post Scraping → Phone Extraction → WhatsApp Outreach |
| **Audiensi** | Auto-queue from successful contact → PDF Invitation → Zoom Scheduling |
| **OSINT** | Web Profiling → Social Intel → Key People → News → Contact Enrichment (LangGraph) |
| **CRM** | Identity Resolution → Academic Profiler → Social Profiler → Personal/Family Info (LangGraph) |
| **Blast** | Bulk WhatsApp messaging with templates, human-like delays |
| **Email Blast** | SMTP (SOCKS5 proxy) + IMAP reply tracking, letter numbering |
| **DMS MySQL** | Sync schedules, contacts, approvals with external DMS system |

---

## Architecture

Three independent services communicate via HTTP and WebSocket:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React + Vite)                             │
│                         Port 5173 · TanStack Query + WS                      │
│  Dashboard · Universities · Pipeline · Conversations · Audiensi · CRM          │
│  Blast · Email Blast · DMS Schedules · Settings                              │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │ HTTP / WebSocket
┌────────────────────────────────▼─────────────────────────────────────────────┐
│                        ORCHESTRATOR (Python FastAPI)                          │
│                              Port 8000                                        │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  Endpoints: /universities /conversations /pipeline /audiensi /osint    │ │
│  │            /crm /dms /blast /email-blast /wa /config /learning        │ │
│  │            /ig-accounts /knowledge-items /api-logs                     │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌──────────────────┐  ┌───────────────────┐  ┌──────────────────────────┐  │
│  │  MessageQueue     │  │  Scheduler        │  │  State Machines         │  │
│  │  AI Semaphore     │  │  APScheduler      │  │  Contact + Audiensi      │  │
│  │  + WA Send Queue  │  │  (Outreach+Follow)│  │  ReAct Agent            │  │
│  └──────────────────┘  └───────────────────┘  └──────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────┐  ┌──────────────────────────────────────────┐  │
│  │  LangGraph Pipelines     │  │  IG Agents (3-tier search)               │  │
│  │  OSINT · CRM · Research  │  │  Find Handles · Scrape · Extract Phones │  │
│  └──────────────────────────┘  └──────────────────────────────────────────┘  │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │ HTTP POST /send · /send-document
┌────────────────────────────────▼─────────────────────────────────────────────┐
│                      WHATSAPP SERVICE (Node.js + Express)                    │
│                             Port 3100                                        │
│                                                                              │
│  ┌──────────────────────────┐  ┌──────────────────────────────────────────┐  │
│  │  DeviceManager             │  │  MessageQueue (SQLite-backed, persistent) │  │
│  │  Multi-device (≤5)        │  │  pending → sending → sent/failed        │  │
│  │  Baileys WASocket         │  │  Retry logic + deduplication            │  │
│  │  QR auth · Auto-reconnect │  │  Rate limiting                          │  │
│  └──────────────────────────┘  └──────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ WhatsApp Protocol
                                 ▼
                            📱 WhatsApp Cloud
```

---

## Tech Stack

### Orchestrator (Python)
| Component | Technology | Purpose |
|-----------|-------------|---------|
| Framework | FastAPI + Uvicorn | Async HTTP API |
| Database | SQLite (aiosqlite) + WAL mode | Persistent storage |
| AI | OpenAI GPT-4o-mini, GPT-4o | Vision OCR, Chat, Reasoning |
| Orchestration | LangGraph | OSINT, CRM, Research pipelines |
| Scheduler | APScheduler | Outreach loops, follow-ups, agent cron |
| IG Scraping | Playwright, Apify, ScrapingBot, Serper | Instagram data collection |
| External DB | aiomysql | DMS MySQL integration |
| Phone Parsing | phonenumbers (libphonenumber) | Indonesian number validation |

### WhatsApp Service (Node.js)
| Component | Technology | Purpose |
|-----------|------------|---------|
| Runtime | Node.js 20+ | JS runtime |
| Framework | Express.js | HTTP server |
| WhatsApp | @whiskeysockets/baileys | WA protocol |
| Queue DB | better-sqlite3 | Persistent message queue |
| Logging | pino | Structured logging |
| Metrics | prom-client | Prometheus metrics |

### Frontend (React)
| Component | Technology | Purpose |
|-----------|------------|---------|
| Framework | React 18 + Vite | UI |
| Routing | React Router 6 | SPA navigation |
| State | TanStack React Query 5 | Server state + caching |
| Styling | Tailwind CSS 3 | Utility-first CSS |
| Icons | Lucide React | Icon library |
| HTTP | axios | API client |

---

## Prerequisites

### Software
- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **Node.js 20+** — [nodejs.org](https://nodejs.org/)
- **Git** — [git-scm.com](https://git-scm.com/downloads)

### Required API Keys
| Service | Purpose | Get It |
|---------|---------|--------|
| `OPENAI_API_KEY` | GPT-4o Vision & Chat | [platform.openai.com](https://platform.openai.com) |
| `SERPER_API_KEY` | Google search for IG handle discovery | [serper.dev](https://serper.dev) |

### Optional API Keys
| Service | Purpose |
|---------|---------|
| `IG_USERNAME` / `IG_PASSWORD` | Direct IG scraping via Playwright |
| `APIFY_API_KEY` | Fallback IG data extraction |
| `GEMINI_API_KEY` | Gap-filler in CRM pipeline |
| `TAVILY_API_KEY` | OSINT research enhancement |
| `DMS_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | External DMS MySQL sync |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/your-org/GetContactAI.git
cd GetContactAI

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Node.js dependencies
cd whatsapp-service && npm install && cd ..
cd frontend && npm install && cd ..

# 4. Configure environment
cp .env.example .env
# Edit .env: fill in OPENAI_API_KEY and SERPER_API_KEY

# 5. Initialize database (auto-created on first run too)
python scripts/setup_db.py

# 6. Start all three services
# Terminal 1 — WhatsApp Service
cd whatsapp-service && npm run dev

# Terminal 2 — Orchestrator
python -m uvicorn orchestrator.main:app --port 8000 --reload

# Terminal 3 — Frontend
cd frontend && npm run dev
```

### Access Points

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health Check | http://localhost:8000/health |

---

## Configuration

### Environment Variables

```bash
# ═══════════════════════════════════════════════════
# REQUIRED
# ═══════════════════════════════════════════════════
OPENAI_API_KEY=sk-...          # OpenAI API key
SERPER_API_KEY=...              # Serper.dev API key

# ═══════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════
DATABASE_PATH=data/getcontact.db   # SQLite database path

# ═══════════════════════════════════════════════════
# WHATSAPP SERVICE
# ═══════════════════════════════════════════════════
WA_SERVICE_URL=http://localhost:3100
WEBHOOK_URL=http://localhost:8000/webhook/incoming

# ═══════════════════════════════════════════════════
# OUTREACH (WIB = UTC+7)
# ═══════════════════════════════════════════════════
OUTREACH_START_HOUR=7           # Start sending at 07:00 WIB
OUTREACH_END_HOUR=22            # Stop sending at 22:00 WIB
MAX_DAILY_CONVERSATIONS=20      # Daily conversation quota
MIN_MESSAGE_GAP_SECONDS=30      # Min gap between messages

# ═══════════════════════════════════════════════════
# AI SETTINGS
# ═══════════════════════════════════════════════════
AGENT_MODEL=gpt-4o-mini         # Chat model
VISION_MODEL=gpt-4o-mini         # Vision OCR model
MAX_AI_CONCURRENT=3              # Max parallel AI calls

# ═══════════════════════════════════════════════════
# OPTIONAL: IG SCRAPING
# ═══════════════════════════════════════════════════
IG_USERNAME=...
IG_PASSWORD=...
APIFY_API_KEY=...

# ═══════════════════════════════════════════════════
# OPTIONAL: DMS MYSQL
# ═══════════════════════════════════════════════════
DMS_MYSQL_HOST=...
DMS_MYSQL_PORT=3306
DMS_MYSQL_USER=...
DMS_MYSQL_PASSWORD=...
DMS_MYSQL_DATABASE=...

# ═══════════════════════════════════════════════════
# OPTIONAL: EMAIL BLAST SMTP (SOCKS5 proxy required)
# ═══════════════════════════════════════════════════
SMTP_HOST=mail.asosiasi.ai
SMTP_PORT=465
SMTP_USERNAME=sekretariat@asosiasi.ai
SMTP_PASSWORD=...
SMTP_USE_SSL=true
SMTP_SOCKS5_HOST=...
SMTP_SOCKS5_PORT=1080
```

### Dynamic Configuration

All settings are **runtime-adjustable** via the Settings page or API. Values persist in the SQLite `config` table (DB overrides .env).

```bash
# View all config
GET /config

# Update a setting (persists to DB, takes effect immediately)
PATCH /config
{"key": "MAX_DAILY_CONVERSATIONS", "value": "50"}
```

---

## Data Flow

### Contact Collection Pipeline

```
PDDIKTI API ──▶ Universities DB ──▶ Agent 1 (IG Handles)
                                          │
                                          ▼
                                   Agent 2 (IG Posts)
                                          │
                                          ▼
                                   Agent 3 (GPT-4o Vision OCR)
                                          │
                                          ▼
                              ig_contacts + universities.status='contacted'
                                          │
                                          ▼
                               Scheduler → MessageQueue → WhatsApp Service
                                          │
                                          ▼
                              WhatsApp ──▶ Reply ──▶ Orchestrator
                                          │            │
                                          │    ┌───────┴───────┐
                                          │    │               │
                                          │  got_number    refused
                                          │    │               │
                                          ▼    ▼               ▼
                                  auto-queue       polite close
                                  audiensi
```

### Audiensi Pipeline

```
GOT_NUMBER (contact) ──▶ auto_queue → audiensi_conversations
                                            │
                            ┌───────────────┼───────────────┐
                            │               │               │
                         PDF invite      Zoom link       follow-up
                            │               │               │
                            └───────────────┴───────────────┘
                                            │
                                            ▼
                              DMS MySQL ← sync_schedules
```

---

## Conversation States

### Contact Outreach (Chatbot 1)

```
PENDING
    │
    ▼ (first message sent)
INITIAL_SENT
    │
    ▼ (waiting for reply)
WAITING_REPLY
    │
    ├──────────▶ GOT_NUMBER      ✅ Success (terminal)
    ├──────────▶ REFUSED          ❌ Contact refused (terminal)
    ├──────────▶ NEED_MORE        🔄 Follow-up needed
    ├──────────▶ NO_REPLY         ⏰ No response (legacy)
    ├──────────▶ ABANDONED        ⏹️ Max attempts (terminal)
    └──────────▶ UNDELIVERED      📵 Message failed (terminal)
```

### Audiensi (Chatbot 2)

```
QUEUED ──▶ MESSAGE_SENT ──▶ WAITING_REPLY
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
           APPROVED               REFUSED            ZOOM_SENT
          ✅ (terminal)           ❌ (terminal)       📅 (terminal)
```

---

## LangGraph Pipelines

### OSINT Pipeline (`osint/graph.py`)

```
START → load_existing_data
             │
             ▼
    parallel_research (asyncio.gather)
    ├── web_profiler      → address, phone, email, faculty, org structure
    ├── social_intel      → official social media accounts
    ├── key_people        → rectors, secretaries, BEM contacts
    └── news_scanner      → recent news and events
             │
             ▼
    contact_enricher (needs key_people + web_profiler output)
             │
             ▼
    reviewer (QA gate)
             │
        ┌────┴────┐
      approved  retry → selective_retry → reviewer
        (loop)
        │
        ▼
    persist_results → osint_profiles, osint_contacts, osint_social_media
             │
             ▼
           END
```

### CRM Pipeline (`crm/graph.py`)

```
START → load_existing
             │
             ▼
    identity_resolver (PDDIKTI → DuckDuckGo/Brave search)
             │
             ▼
    parallel_phase_1 (asyncio.gather)
    ├── academic_profiler    → education, publications, research
    ├── social_profiler      → LinkedIn, Instagram, Facebook, email, phone
    └── campus_context       → campus problems, concerns, hopes
             │
             ▼
    parallel_phase_2 (uses phase_1 output)
    ├── personal_interest    → hobbies, food, activities, personality
    └── family_info          → marital status, spouse, children, residence
             │
             ▼
    profile_compiler (merge all → CompiledProfile)
             │
             ▼
    gap_filler (re-query missing fields via Gemini)
             │
             ▼
    persist_results → crm_pic_profiles, crm_profile_sources
             │
             ▼
           END
```

### Research Pipeline (`research_agents/graph.py`) — DMS Audiensi Research

```
START → rector_agent (Who is the rector?)
             │
             ▼
    rector gate
      │ found + city       │ not found (retry ≤ 1)  │ not found (retry > 1)
      ▼                     ▼                        ▼
  birth_city_lookup    rector_agent (loop)      finalize (partial)
      │
      ▼
    research_topics (6 agents in parallel via asyncio.gather)
    tourism × 3 agents · food × 2 agents · psychographics × 1 agent
      │
      ▼
    finalize → research results stored → DMS MySQL sync
```

---

## Project Structure

```
GetContactAI/
├── orchestrator/                    # Python FastAPI backend
│   ├── main.py                     # FastAPI app · 150+ endpoints
│   ├── config.py                   # ConfigManager (DB-precedent) · logging
│   ├── config_registry.py          # All dynamic config keys + defaults
│   ├── db.py                       # SQLite schema (20+ tables) · aiosqlite
│   ├── conversation.py             # Chatbot 1 state machine + GPT-4o-mini
│   ├── message_queue.py            # AI semaphore + serial WA send queue
│   ├── scheduler.py                # APScheduler jobs · ThreadPoolExecutor
│   ├── instagram.py                # IG search + phone extraction + verification
│   ├── playwright_ig.py            # IG account pool (Playwright WASocket)
│   ├── websocket.py                # WebSocket broadcast manager
│   ├── blast_service.py            # WA blast worker
│   ├── email_blast.py              # SMTP (SOCKS5) + IMAP reply tracking
│   ├── dms_mysql.py               # DMS MySQL pool + tables
│   ├── university_groups.py        # University group management
│   ├── audiensi_research.py       # Research result DB + table
│   │
│   ├── agents/                     # IG contact discovery agents
│   │   ├── ig_handle_finder.py    # 3-tier: website → IG Web → Serper
│   │   ├── ig_post_scraper.py     # Playwright IG scraping
│   │   ├── ig_phone_extractor.py  # GPT-4o Vision OCR on images
│   │   ├── bem_finder.py          # BEM/relevant IG discovery
│   │   └── rector_finder.py       # Rector name from website + PDDIKTI
│   │
│   ├── agent/                      # Core AI + learning system
│   │   ├── react_agent.py         # ReAct loop for AI replies
│   │   ├── learning.py            # Conversation analysis + lesson generation
│   │   ├── situation_detector.py  # Reply classification
│   │   ├── tools.py               # Shared agent tools
│   │   └── prompts.py             # System prompts
│   │
│   ├── osint/                     # OSINT LangGraph pipeline
│   │   ├── state.py              # State definition
│   │   ├── graph.py              # LangGraph StateGraph workflow
│   │   ├── web_profiler.py       # University web scraping
│   │   ├── social_intel.py       # Social media discovery
│   │   ├── key_people.py         # Key personnel finder
│   │   ├── news_scanner.py       # News monitoring
│   │   ├── contact_enricher.py   # Contact aggregation
│   │   ├── reviewer.py           # QA review agent
│   │   └── tools.py              # Shared OSINT tools
│   │
│   ├── crm/                       # CRM LangGraph pipeline
│   │   ├── state.py             # State definition
│   │   ├── graph.py             # LangGraph workflow
│   │   ├── identity_resolver.py # PDDIKTI + search identity
│   │   ├── academic_profiler.py # Education + publications
│   │   ├── social_profiler.py   # LinkedIn · Instagram · Facebook
│   │   ├── campus_context.py    # Campus problems / concerns / hopes
│   │   ├── personal_interest.py # Hobbies · food · personality
│   │   ├── family_info.py      # Marital status · family
│   │   ├── profile_compiler.py # Merge all → CompiledProfile
│   │   └── tools.py             # Shared CRM tools
│   │
│   ├── audiensi/                  # Audiensi scheduling
│   │   ├── conversation.py       # Chatbot 2 state machine
│   │   ├── states.py            # AudiensiState enum
│   │   ├── auto_queue.py       # Auto-queue from GOT_NUMBER
│   │   ├── pdf_generator.py    # PDF invitation generation
│   │   ├── prompts.py           # Audiensi system prompts
│   │   ├── react_agent.py      # Audiensi ReAct agent
│   │   └── tools.py            # Audiensi tools
│   │
│   ├── research_agents/           # DMS research LangGraph
│   │   ├── state.py            # ResearchState
│   │   ├── graph.py            # Research LangGraph
│   │   ├── reviewer.py         # Research QA
│   │   ├── gemini_caller.py    # Gemini API caller
│   │   └── agents/
│   │       ├── rector_agent.py
│   │       ├── birth_city_lookup.py
│   │       ├── psychographics_agent.py
│   │       └── topic_agents.py  # tourism × 3, food × 2
│   │
│   └── osint/                    # OSINT tools + clients
│       ├── state.py
│       ├── graph.py
│       ├── tavily_client.py    # Tavily search
│       ├── pinchtab_client.py  # Email enrichment
│       ├── pw_auth_client.py   # Password auth
│       └── ...
│
├── whatsapp-service/              # Node.js WhatsApp bridge
│   ├── src/
│   │   ├── index.ts            # Express server · webhook · message handling
│   │   ├── deviceManager.ts    # Multi-device WASocket management
│   │   ├── messageQueue.ts     # SQLite-backed persistent queue
│   │   ├── rateLimiter.ts      # Token bucket rate limiter
│   │   ├── healthAndMetrics.ts # Health endpoints
│   │   └── metrics.ts          # Prometheus metrics
│   ├── data/
│   │   └── message_queue.db   # Persistent message queue
│   └── package.json
│
├── frontend/                      # React dashboard
│   ├── src/
│   │   ├── App.tsx            # Router setup (15 routes)
│   │   ├── api/
│   │   │   └── client.ts      # axios + interceptors
│   │   ├── context/
│   │   │   └── WebSocketContext.tsx  # Real-time updates
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── UniversitiesPage.tsx
│   │   │   ├── UniversityDetailPage.tsx
│   │   │   ├── PipelinePage.tsx
│   │   │   ├── ConversationsPage.tsx
│   │   │   ├── ConversationDetailPage.tsx
│   │   │   ├── LearningPage.tsx
│   │   │   ├── WhatsAppPage.tsx
│   │   │   ├── AudiensiQueuePage.tsx
│   │   │   ├── AudiensiDetailPage.tsx
│   │   │   ├── KnowledgeBasePage.tsx
│   │   │   ├── ApiLogsPage.tsx
│   │   │   ├── BlastCampaignsPage.tsx
│   │   │   ├── BlastCampaignDetailPage.tsx
│   │   │   ├── EmailBlastPage.tsx
│   │   │   ├── EmailBlastCampaignsPage.tsx
│   │   │   ├── EmailBlastCampaignDetailPage.tsx
│   │   │   ├── DmsSchedulesPage.tsx
│   │   │   ├── DmsScheduleDetailPage.tsx
│   │   │   ├── CrmPage.tsx
│   │   │   ├── CrmDetailPage.tsx
│   │   │   ├── UniversityGroupsPage.tsx
│   │   │   └── SettingsPage.tsx
│   │   └── components/
│   │       ├── layout/AppShell.tsx   # Sidebar + main layout
│   │       └── ui/                    # Base UI components
│   └── package.json
│
├── scripts/
│   ├── setup_db.py               # DB initialization
│   └── ...
│
├── data/                          # Runtime data (gitignored)
│   ├── getcontact.db            # SQLite database
│   ├── auth_store/              # WhatsApp session auth (per device)
│   ├── auth_store_backup/       # Auth backup
│   ├── audiensi_docs/          # Generated PDFs
│   └── templates/              # Email blast templates
│
├── docker-compose.yml
├── Dockerfile.orchestrator
├── Dockerfile.whatsapp
├── Dockerfile.frontend
└── README.md
```

---

## Database Schema

SQLite database at `data/getcontact.db` — schema auto-created on startup. WAL mode enabled for concurrent read/write.

### Core Tables

| Table | Description |
|-------|-------------|
| `universities` | PDDIKTI-sourced universities, IG handles, status funnel |
| `ig_contacts` | Phone numbers extracted via GPT-4o Vision from IG posts |
| `ig_posts` | Scraped IG posts with captions and image URLs |
| `ig_accounts` | Managed IG account pool for scraping (username, password, login status) |
| `conversations` | Contact outreach state machine, message_history (JSON), extracted_number |
| `daily_quota` | `date TEXT PRIMARY KEY` → messages_sent, conversations_started |

### Audiensi Tables

| Table | Description |
|-------|-------------|
| `audiensi_conversations` | Phase-2 Zoom scheduling conversations |
| `university_related_igs` | BEM, humas, PMB IG accounts discovered per university |

### Agent + Learning Tables

| Table | Description |
|-------|-------------|
| `conversation_analyses` | Post-mortem of completed conversations |
| `lessons` | Learned strategies keyed by situation_type + province |
| `strategy_metrics` | Per-conversation strategy tracking |
| `pipeline_logs` | Agent execution logs (find_handles, scrape_posts, extract_phones) |

### OSINT Tables

| Table | Description |
|-------|-------------|
| `osint_profiles` | University web profiling results |
| `osint_contacts` | Aggregated contacts from multiple sources |
| `osint_social_media` | Social media accounts per university |
| `osint_news` | News items per university |
| `osint_runs` | OSINT pipeline execution history |

### CRM Tables

| Table | Description |
|-------|-------------|
| `crm_requests` | Profile requests (PIC name, university, priority) |
| `crm_pic_profiles` | Full PIC profiles (identity, academic, social, personal, family) |
| `crm_profile_runs` | CRM pipeline execution history |
| `crm_profile_sources` | Per-field data source tracking with confidence |

### Blast Tables

| Table | Description |
|-------|-------------|
| `blast_campaigns` | WA bulk messaging campaigns |
| `blast_recipients` | Campaign recipients with rendered message |
| `email_blast_campaigns` | Email campaigns with template + attachment |
| `email_blast_recipients` | Email recipients with rendered content |
| `email_inbox_cache` | IMAP inbox cache (reply tracking) |
| `email_sent_cache` | IMAP sent folder cache |
| `email_outbox` | All outgoing emails (campaign + test) |
| `email_blast_letter_config` | Letter numbering (auto-increment per year) |

### Support Tables

| Table | Description |
|-------|-------------|
| `university_groups` | Named groups of universities |
| `university_group_members` | Group membership |
| `knowledge_items` | Chatbot knowledge base with trigger keywords |
| `api_call_logs` | Per-conversation API call audit (prompt_tokens, completion_tokens) |
| `config` | Dynamic runtime configuration (DB-persisted) |

---

## API Reference

### Key Endpoints

```http
# ── Health ──────────────────────────────────────────────────────────
GET  /health                        # Full health check (IG, WA, DMS)
GET  /dashboard                     # System statistics

# ── Universities ──────────────────────────────────────────────────────
GET    /universities                # List with filters (status, province, search...)
POST   /universities                # Create university (single or bulk)
POST   /universities/import         # Import from CSV/Excel
GET    /universities/export-excel    # Export contacts as .xlsx
GET    /universities/{id}           # University detail
DELETE /universities/{id}/ig-handle  # Reset IG handle (force re-search)
GET    /universities/{id}/contacts   # IG contacts for university
GET    /universities/{id}/posts      # IG posts for university
GET    /universities/{id}/related-igs # BEM/humas/pmb IG accounts
GET    /universities/with-emails     # Universities with email_kampus
GET    /universities/provinces       # Distinct province list
PATCH  /universities/{id}/toggle-enabled
PATCH  /universities/bulk-toggle

# ── Pipeline ──────────────────────────────────────────────────────────
POST /pipeline/collect-universities  # Fetch from PDDIKTI API
POST /pipeline/find-ig-handles       # Agent 1: IG handle discovery
POST /pipeline/scrape-ig-posts       # Agent 2: scrape IG posts
POST /pipeline/extract-phones        # Agent 3: GPT-4o Vision OCR
POST /pipeline/discover-bem           # Agent 4: BEM IG discovery
POST /pipeline/find-rectors          # Agent 5: rector name finder
POST /pipeline/run-agent-targeted     # Targeted agent run
GET  /pipeline/status
GET  /pipeline/logs

# ── Outreach ──────────────────────────────────────────────────────────
POST /outreach/start                 # Trigger daily outreach loop
POST /outreach/process-followups     # Manual follow-up processing

# ── Conversations ────────────────────────────────────────────────────
GET  /conversations                  # List (state, university_id filters)
GET  /conversations/{id}             # Detail with full message history
POST /conversations/test             # Test conversation (real WA delivery)

# ── Control ───────────────────────────────────────────────────────────
POST /control/pause
POST /control/resume
GET  /control/status
POST /control/chatbot/{chatbot_type}  # Enable/disable chatbot type

# ── Audiensi ──────────────────────────────────────────────────────────
GET  /audiensi                       # All audiensi conversations
GET  /audiensi/queue                 # Queue (state=QUEUED)
GET  /audiensi/{id}
POST /audiensi/{id}/approve         # Approve + schedule Zoom
POST /audiensi/{id}/reject
POST /audiensi/{id}/send-zoom
GET  /audiensi/{id}/pdf             # Download generated PDF
POST /audiensi/{id}/regenerate-pdf
POST /audiensi/template/upload

# ── WhatsApp ─────────────────────────────────────────────────────────
GET  /wa/qr                          # QR code for device_1
GET  /wa/status                      # WA connection status
GET  /wa/devices                     # All devices
GET  /wa/devices/{id}/qr
POST /wa/devices/{id}/connect
POST /wa/devices/{id}/disconnect
POST /wa/devices/{id}/reset
POST /wa/bulk-send                  # Bulk text message
POST /wa/bulk-send-document         # Bulk document + caption

# ── IG Accounts ──────────────────────────────────────────────────────
GET  /ig-accounts                    # List managed IG accounts
POST /ig-accounts                    # Add IG account
PUT  /ig-accounts/{id}
DELETE /ig-accounts/{id}
POST /ig-accounts/{id}/login         # Initiate login
POST /ig-accounts/{id}/login/challenge  # OTP verification
POST /ig-accounts/{id}/test-login   # Test session validity
GET  /ig-accounts/{id}/test-login-live  # Live connection check
GET  /ig-accounts/{id}/session/export  # Export session cookies
POST /ig-accounts/{id}/session/import-cookies  # Import session
GET  /ig-accounts/health             # Pool health status

# ── OSINT ─────────────────────────────────────────────────────────────
POST /osint/run/{university_id}      # Run OSINT for one university
POST /osint/run-batch               # Run OSINT for batch
GET  /osint/profile/{university_id}
GET  /osint/runs
GET  /osint/runs/{run_id}

# ── CRM ───────────────────────────────────────────────────────────────
POST /crm/requests                   # Create profile request
GET  /crm/requests
GET  /crm/requests/{id}
POST /crm/requests/{id}/run          # Execute CRM pipeline
GET  /crm/profiles/{id}
PATCH /crm/profiles/{id}            # Update profile fields
GET  /crm/stats

# ── DMS ───────────────────────────────────────────────────────────────
GET  /dms/health
GET  /dms/stats
GET  /dms/schedules                  # All schedules
GET  /dms/schedules/today
GET  /dms/schedules/{id}
GET  /dms/followups
GET  /dms/approvals
GET  /dms/meetings
GET  /dms/pics/search
GET  /dms/universities/search
POST /dms/sync/contacts             # Sync extracted contacts to DMS
POST /dms/sync/schedules            # Sync schedules from DMS
POST /dms/research/run-tomorrow     # Research H-1 audiensi schedules
POST /dms/research/schedule/{id}    # Research specific schedule
GET  /dms/research/results
GET  /dms/research/results/{schedule_id}

# ── Blast ─────────────────────────────────────────────────────────────
GET  /blast/contacts                 # Blast-eligible contacts
POST /blast/check-previously-blasted
POST /blast/campaigns               # Create campaign
GET  /blast/campaigns
GET  /blast/campaigns/{id}
PUT  /blast/campaigns/{id}
DELETE /blast/campaigns/{id}
POST /blast/campaigns/{id}/recipients/add-all
POST /blast/campaigns/{id}/recipients
GET  /blast/campaigns/{id}/recipients
POST /blast/campaigns/{id}/start
POST /blast/campaigns/{id}/pause
POST /blast/campaigns/{id}/cancel

# ── Email Blast ───────────────────────────────────────────────────────
POST /email-blast/campaigns
GET  /email-blast/campaigns
GET  /email-blast/campaigns/{id}
PATCH /email-blast/campaigns/{id}
POST /email-blast/campaigns/{id}/start
POST /email-blast/campaigns/{id}/pause
POST /email-blast/campaigns/{id}/cancel
POST /email-blast/campaigns/{id}/retry-failed
GET  /email-blast/campaigns/{id}/recipients
GET  /email-blast/campaigns/{id}/sent-emails
GET  /email-blast/campaigns/{id}/inbox
POST /email-blast/campaigns/{id}/attachment
GET  /email-blast/campaigns/{id}/attachment
GET  /email-blast/inbox             # IMAP inbox view
GET  /email-blast/sent-emails      # IMAP sent folder view
GET  /email-blast/letter-config
POST /email-blast/letter-config
POST /email-blast/test-smtp
POST /email-blast/test-imap
GET  /email-blast/debug-campaign-replies/{id}

# ── Knowledge ──────────────────────────────────────────────────────────
GET  /knowledge-items
POST /knowledge-items
PATCH /knowledge-items/{id}
DELETE /knowledge-items/{id}
POST /knowledge-items/upload         # Upload CSV/JSON

# ── Learning ──────────────────────────────────────────────────────────
GET  /learning/lessons               # Active lessons
GET  /learning/analyses              # Unprocessed conversation analyses
GET  /learning/stats
POST /learning/trigger-reflection    # Run learning reflection manually

# ── Config ────────────────────────────────────────────────────────────
GET  /config                         # All config values
PATCH /config                       # Update a config key
DELETE /config/{key}
GET  /config/models                  # Available AI models

# ── University Groups ────────────────────────────────────────────────
GET  /university-groups
POST /university-groups
GET  /university-groups/{id}
PUT  /university-groups/{id}
DELETE /university-groups/{id}
POST /university-groups/{id}/universities/add
POST /university-groups/{id}/universities/remove
GET  /university-groups/{id}/university-ids

# ── API Logs ─────────────────────────────────────────────────────────
GET  /api-logs
GET  /api-logs/{id}

# ── Export ────────────────────────────────────────────────────────────
GET  /export/csv
```

Full interactive documentation: **http://localhost:8000/docs**

---

## Scheduler Jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| `daily_outreach` | Every 30 min (7–22 WIB) | Send initial WA messages to `ig_scraped` universities |
| `process_followups` | Every hour (7–22 WIB) | Follow-up at 24h / 48h; mark `ABANDONED` at max attempts |
| `agent_handle_finder` | Every 2 hours (8–20 WIB) | Agent 1: find IG handles for pending universities |
| `agent_post_scraper` | Every 3 hours (8–20 WIB) | Agent 2: scrape IG posts |
| `agent_phone_extractor` | Every hour (8–21 WIB) | Agent 3: GPT-4o Vision OCR on post images |
| `agent_bem_discovery` | Every 4 hours (9–19 WIB) | Agent 4: discover BEM/relevant IG accounts |
| `agent_rector_finder` | Every 4 hours (8–20 WIB) | Agent 5: find rector names |
| `learning_reflection` | 08:00, 14:00, 20:00 WIB | Analyze completed conversations, generate lessons |
| `dms_sync_schedules` | Every 30 min | Sync audiensi schedules from DMS MySQL |
| `dms_contact_sync` | Every 2 hours (8–20 WIB) | Sync extracted contacts to DMS |
| `dms_research_run_tomorrow` | Daily 18:00 WIB | Research H-1 audiensi schedules |
| `dms_research_safety_check` | Every 4 hours (8–22 WIB) | Catch unresearched upcoming schedules |
| `ig_health_check` | Every 5 min | Log unhealthy IG account pool members |
| `periodic_ig_health_check` | Every 5 min | Periodic IG session health log |

---

## Deployment

### Docker Compose (Recommended)

```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

### Manual Build

```bash
docker build -f Dockerfile.orchestrator -t getcontact-orchestrator .
docker build -f Dockerfile.whatsapp    -t getcontact-whatsapp .
docker build -f Dockerfile.frontend    -t getcontact-frontend .

docker run -p 8000:8000 --env-file .env getcontact-orchestrator
docker run -p 3100:3100              getcontact-whatsapp
docker run -p 5173:80                 getcontact-frontend
```

### WhatsApp Device Setup

1. Navigate to **WhatsApp** page (port 5173)
2. Select device → click **Connect**
3. Scan QR code with WhatsApp app
4. Wait for "connected" status
5. Up to **5 devices** supported

---

## Development

### Code Conventions

| Language | Style |
|----------|-------|
| Python | PEP 8 · `black` formatter · strict type hints |
| TypeScript | Strict mode · functional components + hooks |
| React | React 18 · TanStack Query patterns |

### Running Tests

```bash
# Python (pytest)
pytest orchestrator/tests/

# Node.js
npm test --prefix whatsapp-service
```

### Key Design Patterns

- **LRU Phone Lock** (`main.py`): Prevents concurrent processing of same phone number across debounce windows
- **AI Semaphore** (`message_queue.py`): `Semaphore(MAX_AI_CONCURRENT)` gates all AI calls to prevent rate limits
- **Serial WA Queue** (`message_queue.py`): Background worker drains queue with `SEND_INTERVAL_MS` gap for human-like sending cadence
- **Agent ThreadPool** (`scheduler.py`): Heavy Playwright/IG ops run in `ThreadPoolExecutor` so FastAPI event loop stays responsive
- **Config Precedence** (`config.py`): DB value > .env > registry default — runtime changes without restart
- **Dual-mode Chatbot** (`conversation.py`): Falls back from ReAct agent to legacy state machine on error
- **SQLite WAL Mode** (`db.py`): Concurrent read/write from multiple threads via `PRAGMA journal_mode=WAL`

---

## License

MIT License — see [LICENSE](LICENSE) file.

---

*Built for Indonesian Universities* 🇮🇩

