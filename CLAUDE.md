# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GetContact AI Agent is a multi-service application that automates WhatsApp and email outreach to Indonesian universities, government agencies, and marketing targets. It scrapes Instagram for phone numbers, conducts AI-driven WhatsApp conversations to obtain secretariat contacts, runs bulk blast campaigns, and performs OSINT profiling on key decision-makers.

## Architecture

Three independent services communicate via HTTP/webhooks:

1. **Orchestrator** (`orchestrator/`, Python FastAPI, port 8000) — Core business logic: pipeline agents, conversation state machine, scheduling, database, marketing, OSINT, CRM, audiensi, email blast. Also hosts the **in-process Codex OAuth client** that talks directly to `chatgpt.com/backend-api/codex` when ChatGPT subscription mode is enabled (no sidecar).
2. **WhatsApp Service** (`whatsapp-service/`, Node.js/TypeScript, internal port 3100) — Baileys-based WhatsApp bridge managing up to 5 concurrent devices with anti-ban behavior
3. **Frontend** (`frontend/`, React + Vite, dev port 5173) — Dashboard covering all features: pipeline, blast, marketing, CRM, audiensi, email, DMS, settings (including ChatGPT OAuth login UI)

**Primary data flow:**
PDDIKTI university scraping → Agent 1 (find IG handles) → Agent 2 (scrape IG posts) → Agent 3 (extract phones via GPT-4o vision OCR, images cached to S3/GCS via `bucket.py`) → WhatsApp outreach via conversation state machine → Follow-ups

**Proxy/networking:** Two Cloudflare WARP containers (SOCKS5 ports 1080/1081) provide IP rotation and DPI bypass for scraping. A **Pinchtab** headless browser service (port 9867) handles browser automation tasks. Config is in `docker-compose.yml`.

**Docker port mapping (differs from dev):** In Docker, frontend runs on host port 3010, WhatsApp service on host port 3110 (internal 3100). The Codex OAuth callback server temporarily binds to `localhost:1455` only during interactive login flows.

**Real-time updates:** `websocket.py` broadcasts events to the frontend via WebSocket.

## Commands

### Orchestrator (Python)
```bash
pip install -r requirements.txt
uvicorn orchestrator.main:app --port 8000 --reload
```

### WhatsApp Service (Node.js)
```bash
cd whatsapp-service && npm install
npm run dev          # Development with ts-node
npm run build        # Compile TypeScript
npm start            # Run compiled dist/index.js
```

### Frontend (React)
```bash
cd frontend && npm install
npm run dev          # Vite dev server
npm run build        # tsc && vite build
```

### Full Stack (Docker)
```bash
docker-compose up -d                    # Start all services
docker-compose -f docker-compose.prod.yml up -d  # Production
```

### Utility Scripts
```bash
python scripts/setup_db.py                    # Initialize SQLite database
python scripts/setup_gcs_bucket.py            # Initialize GCS/S3 bucket for IG image cache
python scripts/collect_universities.py        # Scrape universities from PDDIKTI
python scripts/export_results.py              # Export collected data
python scripts/migrate_marketing.py           # Run marketing module DB migration
python scripts/migrate_ig_contacts_to_dms.py  # Sync IG contacts SQLite → DMS MySQL
python scripts/migrate_images_to_bucket.py    # Move stored images to S3/GCS
```

### Manual Test Scripts
Python tests are manual scripts (no pytest framework). WhatsApp service has a Jest suite.
```bash
# Python
python scripts/qa_full_pipeline.py      # End-to-end pipeline test
python scripts/test_auth_permissions.py # Auth & RBAC tests
python scripts/stress_test_blast.py     # Blast load test

# WhatsApp Service (Jest)
cd whatsapp-service && npm test         # Run all tests (errorHandling, memoryCleanup, messageQueue, rateLimiter, typeSafety)
```

## Key Orchestrator Modules

### Core (top-level)
- `main.py` — FastAPI app with lifespan management, REST endpoints, webhook handler
- `config.py` — Environment variables via python-dotenv, logging setup
- `config_registry.py` — Dynamic runtime config system with typed constraints (INT/FLOAT/BOOL/STRING), groups (Rate Limiting, AI Agent, DMS Integration, etc.), and database persistence. UI model pickers are defined here.
- `db.py` — SQLite schema (auto-created), async queries via aiosqlite
- `conversation.py` — Conversation state machine (PENDING → INITIAL_SENT → WAITING_REPLY → REPLIED → ANALYZING → GOT_NUMBER etc.) + OpenAI GPT-4o-mini
- `message_queue.py` — AI concurrency semaphore (default 3) + serial WA message queue
- `scheduler.py` — APScheduler for daily outreach loops and follow-ups
- `blast_service.py` — WhatsApp blast campaign orchestration (templates, scheduling, timezone-aware delivery, rate limiting)
- `email_blast.py` — SMTP bulk email engine (proxy rotation, MIME multipart, quota tracking)
- `dms_mysql.py` — Two-way sync with external DMS MySQL database (audiensi schedules, Zoom links, contact sync)
- `websocket.py` — WebSocket manager for real-time frontend updates
- `proxy_pool.py` — Proxy management for WARP containers
- `bucket.py` — S3/GCS-compatible object storage for IG post image caching (supports GCS, Cloudflare R2, AWS S3)
- `audiensi_research.py` — Audiensi research table management (separate from core audiensi pipeline)
- `auth/service.py` — Role-based access control with DMS integration and SQLite fallback

### LLM Access Layer (`orchestrator/llm/`)
Central dispatch for all OpenAI SDK calls. When `CHATGPT_OAUTH_ENABLED=true`, chat/responses/vision calls route through an **in-process Codex OAuth client** (Python port of openclaw/pi-ai) that talks directly to `chatgpt.com/backend-api/codex`. Falls back automatically to `api.openai.com` via `OPENAI_API_KEY` on rate-limit/auth/connection errors.

- `client_factory.py` — Lazy singletons: `get_real_client()` (AsyncOpenAI for `api.openai.com`) and `get_codex()` (Python `CodexClient`).
- `gateway.py` — High-level `chat_completions_create` / `responses_create` / `embeddings_create` wrappers. Routing, 15-min cooldown after 429, metrics at `/health/llm-metrics`. Embeddings always go direct (Codex backend doesn't expose `/v1/embeddings`).
- `codex_oauth.py` — PKCE flow, token exchange/refresh, JWT decode. Same OAuth client_id as the official Codex CLI; openclaw-style scopes (`model.request`, `api.responses.write`).
- `codex_token_store.py` — File-locked persistence at `data/codex_auth/auth.json`, transparent token refresh, optional import from `~/.codex/auth.json`.
- `codex_login_server.py` — Temporary aiohttp server bound to `localhost:1455` only during interactive login.
- `codex_client.py` — `CodexClient` HTTP client with header injection (Bearer, chatgpt-account-id, OpenAI-Beta, originator) and SSE response collection.
- `codex_chat_translator.py` — Bidirectional Chat Completions ↔ Responses translation (lets existing `gateway.chat_completions_create()` callers work transparently against the Responses-only Codex backend).
- `codex_transformer.py` / `codex_sse.py` — Body normalization (force `store=false`, strip `previous_response_id`) and SSE event parsing.
- Call-sites that previously held their own `_get_openai()` singleton now import from `orchestrator.llm.gateway`. Files that track `last_response_id` (react_agent.py, audiensi/react_agent.py, mkt_orchestrator.py) guard persistence with a `_persist_response_id()` check — Codex-generated IDs are invalid for the real API and must not be cached when OAuth is on.

**Login flow:** Settings → ChatGPT tab → click "Login with ChatGPT" (opens browser to OpenAI) OR "Manual paste" for headless OR "Import ~/.codex/auth.json" for hosts with the official Codex CLI. See `docs/chatgpt-oauth-setup.md`.

### Instagram Scraping
- `instagram.py` — IG scraping and phone number extraction
- `apify_client.py` — Web scraping via Apify API
- `scrapingbot_client.py` — Alternative scraping service
- `playlist_ig.py` — Playwright-based Instagram scraping (browser automation)
- `mcp_browser_client.py` — MCP browser integration
- `agents/ig_handle_finder.py` — Agent 1: website → IG Web → Serper Google search
- `agents/ig_post_scraper.py` — Agent 2: scrape recent IG posts
- `agents/ig_phone_extractor.py` — Agent 3: GPT-4o vision OCR on post images
- `agents/bem_finder.py` — Discovers BEM (student executive board) contacts for universities
- `agents/rector_finder.py` — Researches and enriches rector data for universities

### Marketing (`orchestrator/marketing/`)
Multi-agent system for discovering and reaching marketing contacts.
- `mkt_orchestrator.py` — Main orchestration engine coordinating sub-agents
- `search.py` — Marketing contact search & discovery
- `mkt_sub_agents.py` — Sub-agent implementations (specialized roles)
- `generator.py` — Message/content generation
- `mkt_prompts.py` — LLM prompts
- `groups.py` — Marketing group management
- `mkt_memory.py` — Marketing context memory across sessions
- `discovery/` — Industry-specific discovery agents (annual reports, BNSP, JDIH, LKIP, asosiasi)

### OSINT (`orchestrator/osint/`)
Open-source intelligence gathering on university staff and key people.
- `graph.py` — Graph-based entity relationship mapping
- `social_profiler.py`, `academic_profiler.py`, `web_profiler.py` — Profile building from multiple sources
- `identity_resolver.py` — Cross-source identity deduplication
- `contact_enricher.py`, `news_scanner.py`, `personal_interest.py` — Enrichment layers
- `tools.py` — OSINT tool implementations

### CRM (`orchestrator/crm/`)
Profile compilation and knowledge graph for contacts.
- `graph.py` — CRM knowledge graph
- `profile_compiler.py` — Aggregates OSINT data into structured profiles
- `social_post_analyzer.py` — Analyzes social media posts for insights
- `state.py` — CRM operation state management
- `campus_context.py`, `family_info.py` — Enrichment layers for campus environment and personal background data

### Audiensi (`orchestrator/audiensi/`)
Automates scheduling formal university meetings (audiensi).
- `react_agent.py` — ReAct agent for planning and scheduling audiensi
- `auto_queue.py` — Queue management for audiensi requests
- `pdf_generator.py` — Generates formal surat audiensi (meeting request letters) as PDF
- `conversation.py` — Audiensi-specific conversation handling

### Research Agents (`orchestrator/research_agents/`)
- `gemini_caller.py` — Google Gemini LLM integration
- `agents/` — Specialized agents: topic, psychographics, birth city lookup, rector research

### Base Agent Framework (`orchestrator/agent/`)
- `react_agent.py` — ReAct (Reasoning + Acting) pattern base class
- `learning.py` — Agent learning/memory system
- `tools.py` — Shared tool implementations
- `embeddings.py` — Vector embeddings for semantic search

## Database

SQLite at `data/getcontact.db` (configurable via `DATABASE_PATH`). Schema auto-creates on startup via `db.py`. Key tables: `universities`, `ig_contacts`, `ig_posts`, `conversations`, `daily_quota`. Message history stored as JSON strings in `conversations`. Marketing, blast, email, CRM, and audiensi each add their own tables — see `db.py` and `scripts/migrate_marketing.py` for full schema.

Dynamic config values are stored in a `config_registry` table managed by `config_registry.py`.

## Frontend Structure

Pages and hooks are organized by feature domain. Each feature has:
- A page component in `frontend/src/pages/`
- A custom hook in `frontend/src/hooks/` (e.g., `useMarketing.ts`, `useBlast.ts`)
- An API client in `frontend/src/api/` that calls the orchestrator REST endpoints
- UI components in `frontend/src/components/<feature>/`

Major feature domains: pipeline, blast (WA), email-blast, marketing, CRM, audiensi, DMS schedules, conversations, university groups, settings/config, logs, auth.

## Frontend Onboarding Tour System

Guided spotlight tour built with **Driver.js**. Two layers:

**1. Global sidebar tour** (`hooks/useTour.ts`) — runs once after wizard completion. Steps are filtered by `hasPermission` — admin-only steps (System, Settings) are excluded for operator/viewer.

**2. Per-page contextual tour** (`hooks/usePageTour.ts` + `tours/`) — auto-starts 800ms after first visit to each page, tracked per-user in localStorage (`page_tour_v1_{pageId}_{userId}`). Tour steps with a `permission` field are skipped if the user lacks that permission.

**Adding a tour to a new page — 3 steps:**
1. Add `data-tour="pagename-element"` attributes to 3–5 key elements in the page component
2. Create `frontend/src/tours/pagename.tour.ts` with the step config array
3. Call `usePageTour('pagename', STEPS)` inside the page component

**Bumping tour version (re-show after major UI change):**
- Increment key prefix in `usePageTour.ts`: `page_tour_v1_` → `page_tour_v2_` (re-shows all tours)
- To re-show only one page, change only that page's `pageId` string (e.g. `'pipeline_v2'`)

**Tour configs:** `frontend/src/tours/` — one file per page (dashboard, pipeline, universities, conversations, audiensi, whatsapp, blast, marketing, crm, learning, knowledge).

## WhatsApp Service

- `index.ts` — Main Express server with all REST routes and Baileys integration
- `deviceManager.ts` — Manages up to 5 concurrent WhatsApp devices; each device has its own auth store (`auth_store_u<id>/`)
- `antiBan.ts` — Anti-ban logic: human-like typing indicators, read receipts, random delays
- `messageQueue.ts` — Scheduled message delivery queue
- `rateLimiter.ts` — Per-device rate limiting
- `healthAndMetrics.ts`, `metrics.ts` — Health check endpoints and Prometheus-style metrics

Auth stores are persisted in `whatsapp-service/auth_store_u<id>/` — do not delete these; they contain active session credentials.

Tests live in `whatsapp-service/tests/` and cover: error handling, memory cleanup, message queue, rate limiter, and type safety.

## Environment

Copy `.env.example` to `.env` (or `.env.production.example` for Docker/production). Required: `OPENAI_API_KEY` (still required for embeddings and as fallback when ChatGPT OAuth is enabled), `SERPER_API_KEY`. Optional: `IG_SESSION_ID`, `APIFY_API_KEY`, `SCRAPINGBOT_*`, `DMS_MYSQL_*` (for DMS sync), `SMTP_*`/`IMAP_*` (for email blast), `GEMINI_API_KEY`. Object storage: set `STORAGE_BACKEND` to `gcs`, `s3`, or `r2` plus the corresponding credentials. All timezone-sensitive logic uses WIB (UTC+7).

**ChatGPT OAuth mode:** when `CHATGPT_OAUTH_ENABLED=true`, chat/responses/vision calls route through an **in-process Python Codex OAuth client** that talks directly to `chatgpt.com/backend-api/codex` using a ChatGPT Plus/Pro subscription. No sidecar container. Login via the FE Settings → ChatGPT tab (browser callback OR manual paste OR import existing `~/.codex/auth.json`). Full guide in `docs/chatgpt-oauth-setup.md`. `OPENAI_API_KEY` is still required for embeddings (Codex backend doesn't expose `/v1/embeddings`) and as the automatic fallback on rate-limit / auth-error.

## CI/CD

GitLab CI/CD pipeline defined in `.gitlab-ci.yml`. Deploys to GCP. Production Docker config is in `docker-compose.prod.yml`.

Pipeline stages: `test` → `deploy` → `verify`. The `test` stage runs in parallel:
- `python_smoke_test` (hard gate) — `scripts/test_llm_factory.py` + `test_llm_gateway.py`
- `frontend_typecheck` (hard gate) — `npx tsc --noEmit`
- `whatsapp_test` (soft gate, `allow_failure: true`) — existing Jest suite, 7/29 timer-based tests currently flaky

Deploy only proceeds if hard-gate tests pass.

## Observability

Sentry error tracking for the orchestrator is wired via `orchestrator/observability.py`. Activation is env-var driven (`SENTRY_DSN`) — when unset, `init_sentry()` is a silent no-op. Integrations: FastAPI, httpx, asyncio, logging. PII scrubber redacts tokens/keys/passwords (exact-key match) and auto-masks emails + Indonesian phone numbers in exception/breadcrumb strings. Release tracking via `SENTRY_RELEASE=$CI_COMMIT_SHORT_SHA` injected by GitLab CI during deploy. Explicit `capture_exception()` calls in `orchestrator/llm/gateway.py` for Codex auth/upstream errors. See `docs/observability-setup.md` for full setup guide.

## Tech Stack

- **Python:** FastAPI, aiosqlite, openai SDK (default model `gpt-5.4`), in-process Codex OAuth client (`orchestrator/llm/codex_*.py` — Python port of openclaw / pi-ai), google-generativeai (Gemini, Google Search grounding for audiensi research and gap-fill), apscheduler, httpx, playwright, phonenumbers, pddiktipy, aiohttp (used only for the temporary OAuth callback server)
- **WhatsApp Service:** @whiskeysockets/baileys, Express, TypeScript strict mode, pino logger
- **Frontend:** React 18, React Router 6, TanStack React Query 5, Tailwind CSS 3, Lucide icons, axios
- **Infrastructure:** Docker Compose (3 services + 2 WARP proxies + pinchtab), Nginx reverse proxy, Cloudflare WARP (×2) for proxy rotation, ChatGPT Plus subscription access via in-process Python OAuth (no sidecar), PostgreSQL (production), Redis
