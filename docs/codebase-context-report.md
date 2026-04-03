# GetContactAI Codebase Context Report

**Last updated:** 2026-04-03
**Branch:** `feature/getcontactcorporate` (merged into `develop`)

---

## 1. Project Overview

GetContactAI adalah multi-service aplikasi yang mengautomasi outreach via WhatsApp ke universitas-universitas di Indonesia untuk collect informasi kontak secretariat.

**Workflow lengkap:**
1. Scrape data universitas dari PDDIKTI API
2. Cari IG handle universitas via website → IG Web → Google (Serper/DuckDuckGo)
3. Scrape IG posts (Playwright → Apify fallback)
4. Extract nomor telepon dari gambar post via GPT-4o Vision
5. Outreach WhatsApp via chatbot AI (state machine)
6. Follow-up dan scheduling audiensi
7. Blast campaigns (WA + Email) ke kontak yang sudah dikumpulkan
8. CRM + DMS scheduling

---

## 2. Struktur Direktori

```
GetContactAI/
├── orchestrator/          # Python FastAPI backend (port 8000)
│   ├── main.py            # ~7000 lines — semua REST API endpoints
│   ├── db.py              # ~5000+ lines — schema + semua query functions
│   ├── conversation.py    # WA chatbot state machine
│   ├── message_queue.py   # Semaphore + serial WA send queue
│   ├── scheduler.py       # APScheduler jobs
│   ├── instagram.py       # IG scraping + phone extraction (4-tier fallback)
│   ├── blast_service.py   # WA blast campaign engine (~1500 lines)
│   ├── email_blast.py    # SMTP email blast (~4000 lines)
│   ├── config.py          # ~400 lines — env vars + ConfigManager
│   ├── config_registry.py # ~700 lines — 60+ settings definitions
│   ├── playwright_ig.py  # ~4000 lines — Playwright stealth browser IG scraping
│   ├── agents/           # Pipeline agents
│   │   ├── ig_handle_finder.py
│   │   ├── ig_post_scraper.py
│   │   ├── ig_phone_extractor.py
│   │   ├── bem_finder.py
│   │   └── rector_finder.py
│   ├── marketing/        # Marketing module (groups, search, importer, handoff)
│   ├── audiensi/          # Audiensi chatbot module
│   ├── crm/              # CRM module
│   ├── osint/            # OSINT module
│   ├── auth/             # JWT auth (users, sessions, RBAC)
│   ├── research_agents/  # Experimental LangGraph agents
│   └── websocket.py      # WebSocket broadcast manager
├── whatsapp-service/     # Node.js/TypeScript (port 3100)
│   ├── src/
│   │   ├── index.ts      # Express server + Baileys socket setup
│   │   ├── deviceManager.ts  # Multi-device WA session mgmt
│   │   ├── messageQueue.ts    # In-memory WA message queue
│   │   ├── antiBan.ts        # Anti-ban rate limiting
│   │   ├── rateLimiter.ts    # Per-device rate limiter
│   │   ├── metrics.ts        # Health metrics
│   │   └── healthAndMetrics.ts
│   └── auth_store_device_*   # Per-device Baileys auth state
├── frontend/             # React 18 + Vite + TypeScript (port 5173)
│   └── src/
│       ├── App.tsx       # React Router + TanStack Query + Auth
│       ├── pages/        # 30+ page components
│       ├── components/   # Shared UI + domain components
│       ├── api/          # Axios API client
│       ├── hooks/        # Custom hooks
│       └── context/      # Theme, Toast, Auth providers
├── scripts/             # Utility scripts (setup_db, collect_universities, etc.)
├── docker-compose.yml   # All 3 services + MySQL
└── data/                # SQLite DB + WA message queue DB
```

---

## 3. Tech Stack

### Backend (Orchestrator)
- **Framework:** FastAPI + Uvicorn
- **Database:** SQLite via `aiosqlite` (single file `data/getcontact.db`)
- **AI:** OpenAI (GPT-4o Vision for phone OCR, GPT-4o-mini for chat)
- **Scheduler:** APScheduler (AsyncIOScheduler)
- **HTTP Client:** httpx (async)
- **Phone parsing:** `phonenumbers` library
- **Browser automation:** Playwright (stealth mode)
- **IG Scraping fallback:** Apify API, ScrapingBot.io API
- **Email:** SMTP via `smtplib` + SOCKS5 proxy (`socks` library), docx parsing
- **Auth:** JWT (PyJWT) with JTI-based session revocation

### WhatsApp Service
- **Framework:** Express.js + TypeScript (strict mode)
- **WA Library:** `@whiskeysockets/baileys` (multi-device)
- **Logger:** Pino
- **Rate limiting:** Custom per-device rate limiter
- **Multi-device:** Up to 5 simultaneous WA accounts via `DeviceManager`

### Frontend
- **Framework:** React 18 + Vite
- **Routing:** React Router v6
- **State:** TanStack React Query v5 (server state), Zustand-like contexts
- **Styling:** Tailwind CSS 3
- **Icons:** Lucide React
- **HTTP:** Axios
- **Auth:** JWT stored in localStorage, interceptor for auto-refresh

---

## 4. Database Schema (Key Tables)

All in one SQLite file. Schema auto-creates on startup via `db.py`.

| Table | Purpose |
|-------|---------|
| `universities` | PDDIKTI data + IG handles + extracted contacts |
| `ig_contacts` | Phone numbers extracted from IG posts |
| `ig_posts` | Scraped IG post URLs/images with extracted phones |
| `conversations` | WA outreach conversations (state machine) |
| `daily_quota` | Daily message/conversation counters |
| `conversation_analyses` | Post-mortem analysis of each conversation |
| `lessons` | Learned strategies from conversations |
| `knowledge_items` | RAG knowledge base for AI context |
| `blast_campaigns` | WA blast campaign definitions |
| `blast_recipients` | Per-campaign recipient list with status |
| `email_blast_campaigns` | Email blast campaigns |
| `email_blast_recipients` | Email recipient status tracking |
| `audiensi_conversations` | Audiensi scheduling chatbot state |
| `users` | Admin users |
| `user_sessions` | JWT sessions with JTI |
| `auth_role_assignments` | RBAC role assignments |
| `auth_role_upgrade_requests` | Pending role requests |
| `api_call_logs` | API audit log |
| `pipeline_logs` | Pipeline execution audit log |
| `config` | Dynamic key-value config store |
| `university_groups` | Grouping universities for blast targeting |
| `crm_clients` | CRM client records |
| `osint_results` | OSINT scan results |
| `dms_schedules` | DMS (scheduling) records |

---

## 5. WhatsApp Chatbot State Machine (conversation.py)

**ConvState enum:**
```
PENDING → INITIAL_SENT → WAITING_REPLY → REPLIED → ANALYZING
→ GOT_NUMBER | NEED_MORE | REFUSED | NO_REPLY | ABANDONED | UNDELIVERED | NEEDS_REVIEW
→ FOLLOWUP_SENT (from NEED_MORE)
```

**Initial message:** Template invitation untuk audiensi Zoom dari "Ali tim Asosiasi AI Indonesia", menyebut universitas lain yang sudah ikut (UI, UNAIR, UPH, Binus, dll).

**AI Analysis:** GPT-4o-mini analyzes incoming reply, extracts contact info or determines if refused/no-reply.

**Follow-up timing:** Configurable via `FOLLOWUP_1_AFTER_HOURS`, `FOLLOWUP_2_AFTER_HOURS`.

**React Agent mode:** Newer implementation uses OpenAI Responses API (gpt-4o-mini) with tool calling. Has 9 tools: save_extracted_number, mark_refused, need_more, send_whatsapp_message, send_followup_message, get_context, check_knowledge_base, update_university. Falls back to Chat Completions for GPT-5, then legacy GPT-3.5 ConversationManager.

---

## 6. Pipeline Agents (5 Agents)

All run via `scheduler.py` using `ThreadPoolExecutor` to avoid blocking FastAPI event loop.

| Agent | Input | Output | Strategy |
|-------|-------|--------|---------|
| **IG Handle Finder** | university website URL | IG handle | Website scrape → IG Web search → Serper Google search |
| **IG Post Scraper** | IG handle | IG post URLs + images | Playwright stealth → Apify → ScrapingBot fallback |
| **Phone Extractor** | IG post images | Phone numbers | GPT-4o Vision OCR |
| **BEM Finder** | IG handle | BEM account handles | Scrape IG following list, filter by BEM keywords |
| **Rector Finder** | university name | Rector name + contacts | Web search + GPT extraction |

**IG Scraping 4-tier fallback** (instagram.py):
1. Playwright Stealth Browser (free, primary)
2. Direct IG Web API with cookie sessions (free)
3. Apify Instagram Scraper API (paid)
4. ScrapingBot.io (paid, last resort)

---

## 7. Blast Services

### WA Blast (blast_service.py, ~1500 lines)
- Campaign with template messages + placeholder substitution
- Per-recipient randomization (names, greeting time based on timezone)
- Queue-based sending with configurable intervals
- Anti-ban awareness (pauses when blocked)
- Peak hour speed boost
- Template variables: `{{nama}}`, `{{universitas}}`, `{{no_wa}}`, `{{datetime}}`

### Email Blast (email_blast.py, ~4000 lines)
- SMTP via TLS or SOCKS5 proxy (VPS blocks port 465/587)
- Template rendering from docx files
- Per-campaign tracking: sent_count, failed_count, pending_count
- Counter sync on demand
- IMAP sent folder tracking

### Marketing Module (orchestrator/marketing/)
- Groups: university grouping untuk blast targeting
- Search: Mencari kontak berdasarkan criteria
- Importer: Import kontak dari CSV/external sources
- Handoff: Transfer kontak ke blast pipeline

---

## 8. WhatsApp Service Architecture

Multi-device WA bridge menggunakan Baileys library:

- **DeviceManager:** Manages multiple WA devices (device_1 ... device_N)
- **MessageQueue:** In-memory queue per device, serial sending with configurable interval
- **AntiBan:** Tracks send failures, adjusts rate dynamically
- **RateLimiter:** Per-device rate limiting (messages per minute/hour)
- **Webhook:** POSTs incoming messages to Orchestrator at `WEBHOOK_URL/incoming`
- **Metrics:** Tracks message counts, delivery rates, anti-ban events

**API endpoints:**
- `POST /send` — Send text message
- `POST /send-document` — Send document
- `POST /webhook/register` — Register webhook URL
- `GET /health` — Connection + metrics status
- `GET /metrics` — Detailed metrics

---

## 9. Config System (config_registry.py)

**60+ dynamic settings** stored in `config` table, with DB value > .env > registry default priority.

Key config areas:
- Outreach hours (WIB timezone)
- Daily message limits
- Follow-up timing
- IG scraping limits
- AI model selection
- Anti-ban thresholds
- Blast timing/speed
- Email SMTP settings

`ConfigManager` class provides `cfg.KEYNAME` access with hot-reload capability.

---

## 10. Frontend Pages (30+ pages)

Key pages:
- **DashboardPage** — Stats overview, recent activity
- **UniversitiesPage** — Table dengan filter/search, bulk actions
- **UniversityDetailPage** — Detail + pipeline trigger buttons
- **PipelinePage** — Run/monitor 5 pipeline agents
- **ConversationsPage** — All WA conversations with state filters
- **ConversationDetailPage** — Message history + AI analysis
- **WhatsAppPage** — WA service status, device management
- **AudiensiQueuePage** — Audiensi chatbot queue
- **KnowledgeBasePage** — RAG knowledge items editor
- **BlastCampaignsPage** — WA blast campaign CRUD
- **EmailBlastPage** — Email campaign management
- **CrmPage / CrmDetailPage** — CRM client management
- **UniversityGroupsPage** — Group management for blast targeting
- **MarketingGetContactPage** — Marketing module dashboard
- **MarketingClientDetailPage** — Client detail dengan IG/contact data
- **SettingsPage** — Dynamic config editor
- **LoginPage** — JWT auth

Auth: Role-based with permissions: `dashboard.view`, `universities.view`, `pipeline.view`, `conversations.view`, `learning.view`, `whatsapp.view`, `audiensi.view`, `knowledge.view`, `blast.view`, `crm.view`, `settings.manage`

---

## 11. Common Patterns

### Backend API Pattern (main.py)
```python
@router.get("/api/v1/resource")
async def get_resource(skip: int = 0, limit: int = 100):
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT * FROM table LIMIT ? OFFSET ?", (limit, skip)
            ) as cursor:
                rows = await cursor.fetchall()
                return {"status": "success", "data": [dict(row) for row in rows]}
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### DB Query Pattern (db.py)
- All queries use `?` placeholders (no f-string SQL injection)
- All DB operations are `async` with `aiosqlite`
- WebSocket broadcast after mutations via `ws_manager.broadcast()`

### Frontend Service Pattern (frontend/src/api/)
```typescript
const API_URL = import.meta.env.VITE_API_URL;
export const service = {
  getAll: async () => {
    const { data } = await axios.get(`${API_URL}/api/v1/resource`);
    return data.data;
  },
  create: async (payload: CreateData) => {
    const { data } = await axios.post(`${API_URL}/api/v1/resource`, payload);
    return data.data;
  },
};
```

### React Component Pattern
```typescript
export function Component({ id }: ComponentProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['resource', id],
    queryFn: () => fetchResource(id),
  });
  if (isLoading) return <Spinner />;
  if (error) return <div>Error: {error.message}</div>;
  return <div>{data?.name}</div>;
}
```

---

## 12. Gotchas & Important Notes

1. **JWT_SECRET random generation** — If `JWT_SECRET` env var not set, a random one is generated on startup, invalidating ALL existing sessions. Must be persisted in `.env`.

2. **IG session cookies expire** — Playwright IG sessions need periodic re-authentication. Apify is the automatic fallback.

3. **SOCKS5 proxy for email** — VPS firewall blocks SMTP ports (465/587). Email blast uses SOCKS5 proxy (`EMAILS_SOCKS5_PROXY` env var).

4. **Multi-device WA auth state** — Each device has its own `auth_store_device_N` directory. Deleting these resets the WA session.

5. **ThreadPoolExecutor for agents** — Pipeline agents run in a thread pool to avoid blocking FastAPI's async event loop. Don't use `async` DB calls inside agent batch functions directly — use `_run_async_in_new_loop()` pattern.

6. **aiosqlite auto-commit gotcha** — When using `async with db.execute()` followed by `async with db.execute()` then `await db.commit()` — make sure all statements are inside the same `async with aiosqlite.connect()` block.

7. **Serper API quota** — Serper has monthly limits. DuckDuckGo is the free fallback for IG handle search.

8. **WIB timezone** — All scheduling uses WIB (UTC+7). `WIB = timezone(timedelta(hours=7))`.

9. **WhatsApp Service runs separately** — Orchestrator communicates with WA Service via HTTP (`WA_SERVICE_URL` env var). They are independent processes.

10. **Config hot-reload** — Config values can be changed via API at runtime without restart. Use `cfg.reload()` if needed.

11. **main.py is huge** (~7000 lines) — All endpoints are in one file. Future refactor should split into routers.

12. **Current branch is `feature/getcontactcorporate`** — This branch adds corporate/GetContact client management to the marketing module (IG integration for marketing clients, not just universities).
