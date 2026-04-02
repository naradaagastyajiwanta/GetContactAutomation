# GetContactAI

AI-assisted outreach and intelligence platform for Indonesian universities.

GetContactAI is a multi-service monorepo that combines contact discovery, WhatsApp outreach, audiensi scheduling, OSINT enrichment, CRM profiling, blast operations, email campaigns, and DMS integration in one operational dashboard.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-20+-339933?style=flat&logo=node.js&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?style=flat&logo=typescript&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-runtime_storage-003B57?style=flat&logo=sqlite&logoColor=white)

## Table of Contents

1. [What This Project Is](#what-this-project-is)
2. [Current Project State](#current-project-state)
3. [System Overview](#system-overview)
4. [Main Product Flows](#main-product-flows)
5. [Repository Structure](#repository-structure)
6. [Technology Stack](#technology-stack)
7. [Runtime Data and Storage](#runtime-data-and-storage)
8. [Local Development](#local-development)
9. [Docker Deployment](#docker-deployment)
10. [Environment Variables](#environment-variables)
11. [How the Core Contact Pipeline Works](#how-the-core-contact-pipeline-works)
12. [Conversation and Scheduling Flows](#conversation-and-scheduling-flows)
13. [Frontend Surface Area](#frontend-surface-area)
14. [Operational Notes](#operational-notes)
15. [Common Commands](#common-commands)
16. [Troubleshooting](#troubleshooting)

## What This Project Is

This repository is not a single chatbot service. It is a working monorepo with three primary runtime services and several domain modules behind them:

| Service | Role | Default Local Port |
| --- | --- | --- |
| `orchestrator` | Main backend, state machines, scheduler, APIs, database access, AI orchestration | `8000` |
| `whatsapp-service` | Baileys-based WhatsApp bridge, multi-device session handling, outbound queueing, webhook forwarding | `3100` |
| `frontend` | React dashboard for monitoring, operating, and reviewing all workflows | `5173` |

On top of those services, the codebase contains multiple business domains:

| Domain | Purpose |
| --- | --- |
| Contact collection | Find university Instagram handles, scrape posts, extract phone numbers, run outreach |
| Audiensi | Continue successful outreach into scheduling and PDF invitation flow |
| OSINT | Build institutional intelligence from public web and social data |
| CRM | Build person-level profiles for PICs and contacts |
| WhatsApp Blast | Bulk outbound campaigns with queueing and anti-ban controls |
| Email Blast | SMTP and IMAP driven outbound email campaigns with reply tracking |
| DMS Integration | Synchronize contacts, schedules, approvals, and research with external MySQL-backed systems |
| Auth and permissions | Role-based access for dashboard users |

## Current Project State

The repo is broad and operationally ambitious. Not every module has the same maturity or infrastructure dependency profile.

### What is clearly implemented in code

| Area | State in Repo |
| --- | --- |
| Core contact funnel | Implemented end-to-end: university collection, IG search, post scraping, phone extraction, WhatsApp outreach, follow-up logic |
| Conversation engine | Implemented with state machine plus optional agentic reply path |
| WhatsApp bridge | Implemented with device management, message queue, webhook forwarding, anti-ban hooks, and multi-device support |
| Dashboard | Implemented with pages for universities, pipeline, conversations, WhatsApp, settings, blast, email blast, DMS, CRM, and audiensi |
| Dynamic runtime config | Implemented via SQLite-backed config table, with DB values overriding defaults |
| Auth and permission gates | Implemented in backend and frontend protected routes |

### Areas that exist but are more infrastructure-heavy

| Area | Notes |
| --- | --- |
| OSINT pipeline | Present in codebase and wired into API, but depends on external providers and real research conditions |
| CRM pipeline | Present in codebase and exposed in dashboard, but relies on high-quality search and enrichment inputs |
| Email blast | Present and substantial, but operational quality depends on SMTP, IMAP, proxy, and mailbox setup |
| DMS sync and research | Present and integrated, but requires real external MySQL connectivity and domain data |
| Instagram scraping | Works through multiple fallbacks, but is naturally sensitive to account health, cookies, proxying, and platform changes |

### Practical summary

If you want to understand the project quickly, treat it as:

1. A contact discovery and outreach system at its core.
2. An operations dashboard around that core.
3. Several adjacent automation modules that extend the workflow after contact acquisition.

## System Overview

### High-level architecture

```text
                                   Browser
                                      |
                                      | HTTP + WebSocket
                                      v
                    +---------------------------------------+
                    | Frontend (React + Vite)               |
                    | Dashboard, pipeline control, review   |
                    +------------------+--------------------+
                                       |
                                       | /api, /ws
                                       v
                    +---------------------------------------+
                    | Orchestrator (FastAPI)                |
                    | API surface, scheduler, state, AI     |
                    | SQLite, config, auth, DMS, email      |
                    +------------------+--------------------+
                                       |
                   +-------------------+-------------------+
                   |                                       |
                   | outbound send                         | webhook register / incoming replies
                   v                                       ^
          +------------------------+             +--------------------------+
          | WhatsApp Service       |             | WhatsApp network         |
          | Baileys + device mgr   |             | real conversations       |
          | queue + anti-ban       |             +--------------------------+
          +------------------------+
```

### Local ports vs Docker ports

The project supports both direct local development and containerized deployment. Ports differ between those modes.

| Service | Local Dev | Docker Compose |
| --- | --- | --- |
| Frontend | `5173` | `3010` |
| Orchestrator | `8000` | `8000` |
| WhatsApp Service | `3100` | `3110` exposed from container `3100` |
| PinchTab | optional | `9867` |
| WARP SOCKS proxy | optional | internal service |

## Main Product Flows

### 1. Contact discovery and WhatsApp outreach

```text
PDDIKTI or manual university input
  -> university records in SQLite
  -> Agent 1 finds Instagram handles
  -> Agent 2 scrapes Instagram posts and related accounts
  -> Agent 3 extracts phone numbers from captions and images
  -> scheduler picks eligible contacts
  -> outbound WhatsApp message is queued
  -> replies return through webhook
  -> conversation state machine decides next action
  -> success updates university secretariat phone
```

### 2. Audiensi continuation

```text
GOT_NUMBER from contact outreach
  -> auto-queue audiensi conversation
  -> send invitation context and follow-up
  -> generate or regenerate PDF invitation
  -> approve or reject flow
  -> send Zoom details
  -> sync schedules and related information into DMS
```

### 3. Intelligence and profiling

```text
University or PIC selected
  -> run OSINT workflow for institution-level enrichment
  -> run CRM workflow for person-level profiling
  -> store structured results for operations use
```

### 4. Campaign operations

```text
Existing contacts and universities
  -> WhatsApp blast campaigns
  -> Email blast campaigns
  -> progress tracking in dashboard and WebSocket updates
```

## Repository Structure

```text
GetContactAI/
|- orchestrator/            Python FastAPI backend and domain modules
|- whatsapp-service/        Node.js TypeScript WhatsApp bridge
|- frontend/                React dashboard
|- data/                    SQLite database, generated docs, runtime assets
|- docs/                    Architecture and public documentation
|- nginx/                   Reverse proxy configuration
|- scripts/                 Utility scripts for setup and maintenance
|- docker-compose.yml       Main production-like container topology
|- Dockerfile.orchestrator
|- Dockerfile.whatsapp
|- Dockerfile.frontend
|- start-all.bat            Windows helper for local startup
|- stop-all.bat             Windows helper for local stop
|- STARTUP.md               Short startup guide
```

### Backend structure

| Path | Responsibility |
| --- | --- |
| `orchestrator/main.py` | FastAPI app, lifespan, webhook handling, main API endpoints |
| `orchestrator/db.py` | SQLite schema and database queries |
| `orchestrator/conversation.py` | Contact outreach conversation state machine |
| `orchestrator/scheduler.py` | Scheduled jobs for outreach, follow-up, and agent batches |
| `orchestrator/message_queue.py` | Serialized outbound WhatsApp queue and AI concurrency gate |
| `orchestrator/agents/` | Instagram and rector discovery agents |
| `orchestrator/audiensi/` | Audiensi workflow and PDF generation |
| `orchestrator/osint/` | OSINT graph and tools |
| `orchestrator/crm/` | CRM graph and person profiling |
| `orchestrator/research_agents/` | Research flow for DMS and meeting prep |
| `orchestrator/email_blast.py` | Email sending, inbox watching, and campaign management |
| `orchestrator/blast_service.py` | WhatsApp bulk campaign execution |
| `orchestrator/auth/` | Session, role, and permission handling |

### WhatsApp service structure

| Path | Responsibility |
| --- | --- |
| `whatsapp-service/src/index.ts` | Express app, webhook forwarding, send endpoints, QR and status APIs |
| `whatsapp-service/src/deviceManager.ts` | Device lifecycle and Baileys socket management |
| `whatsapp-service/src/messageQueue.ts` | Persistent SQLite-backed queue for WhatsApp sends |
| `whatsapp-service/src/antiBan.ts` | Anti-ban and reachout timing logic |
| `whatsapp-service/src/rateLimiter.ts` | Request rate limiting |
| `whatsapp-service/src/metrics.ts` | Metrics and operational instrumentation |

### Frontend structure

| Path | Responsibility |
| --- | --- |
| `frontend/src/App.tsx` | Route registration and page composition |
| `frontend/src/api/` | API clients by domain |
| `frontend/src/hooks/` | React Query wrappers and WebSocket hooks |
| `frontend/src/context/` | Auth, theme, toast, and WebSocket providers |
| `frontend/src/pages/` | Main dashboard pages |
| `frontend/src/components/` | Domain components and UI primitives |

## Technology Stack

### Orchestrator

| Area | Technology |
| --- | --- |
| Web framework | FastAPI + Uvicorn |
| Storage | SQLite via `aiosqlite` |
| AI | OpenAI chat and vision models |
| Scheduling | APScheduler |
| Scraping and browsing | Playwright, DDGS, Serper, Apify, ScrapingBot |
| External integration | MySQL via `aiomysql`, SMTP, IMAP, SOCKS proxy |
| File processing | `openpyxl`, `python-docx`, PDF utilities |

### WhatsApp service

| Area | Technology |
| --- | --- |
| Runtime | Node.js |
| Framework | Express |
| WhatsApp | `@whiskeysockets/baileys` |
| Queue storage | `better-sqlite3` |
| Logging | `pino` |
| QR generation | `qrcode` |

### Frontend

| Area | Technology |
| --- | --- |
| UI | React 18 |
| Build tool | Vite |
| Routing | React Router 6 |
| Server state | TanStack React Query 5 |
| Styling | Tailwind CSS 3 |
| HTTP | Axios |

## Runtime Data and Storage

### Main runtime data

| Path | What lives there |
| --- | --- |
| `data/getcontact.db` | Main SQLite database |
| `whatsapp-service/auth_store*` | WhatsApp auth sessions, including per-device stores |
| `whatsapp-service/data/` | WhatsApp service queue and related runtime data |
| `data/audiensi_docs/` | Generated audiensi invitation files |
| `data/email_attachments/` | Email campaign attachments |
| `data/templates/` | Template assets |
| `data/pw_sessions/` | Playwright or browser session artifacts |

### Core database tables

The database is much larger than a simple outreach tracker. A few tables matter most when onboarding to the project.

| Table | Purpose |
| --- | --- |
| `universities` | Base institution records and status funnel |
| `ig_posts` | Scraped Instagram content |
| `ig_contacts` | Extracted phone numbers and contacts |
| `conversations` | Outreach message history and conversation state |
| `daily_quota` | Daily outbound usage tracking |
| `config` | Runtime configuration persisted in DB |
| `auth_*` | Dashboard user roles, sessions, audit logs, upgrade requests |
| `conversation_analyses`, `lessons` | Learning and reflection artifacts |
| `blast_*`, `email_*` | Campaign management and delivery data |

## Local Development

### Prerequisites

| Requirement | Notes |
| --- | --- |
| Python 3.11+ | Required for orchestrator |
| Node.js 20+ | Recommended for frontend and WhatsApp service |
| OpenAI API key | Required for meaningful AI behaviour |
| Serper API key | Optional fallback; DuckDuckGo path exists in codebase |
| Real WhatsApp number | Required if you want real message delivery |

### Recommended local startup order

The startup order matters because the orchestrator attempts to register its webhook into the WhatsApp service at boot.

1. Start `whatsapp-service`
2. Start `orchestrator`
3. Start `frontend`

### Install dependencies

#### PowerShell

```powershell
python -m pip install -r requirements.txt

Push-Location whatsapp-service
npm install
Pop-Location

Push-Location frontend
npm install
Pop-Location
```

#### Bash

```bash
pip install -r requirements.txt

cd whatsapp-service && npm install && cd ..
cd frontend && npm install && cd ..
```

### Prepare environment

Create a `.env` file from the example and fill the minimum keys.

#### PowerShell

```powershell
Copy-Item .env.example .env
```

#### Bash

```bash
cp .env.example .env
```

At minimum you normally need:

```env
OPENAI_API_KEY=...
WA_SERVICE_URL=http://localhost:3100
WEBHOOK_URL=http://localhost:8000/webhook/incoming
DATABASE_PATH=data/getcontact.db
```

### Run locally

#### Terminal 1 - WhatsApp service

```bash
cd whatsapp-service
npm run dev
```

#### Terminal 2 - Orchestrator

```bash
python -m uvicorn orchestrator.main:app --port 8000 --reload
```

#### Terminal 3 - Frontend

```bash
cd frontend
npm run dev
```

### Local access points

| Surface | URL |
| --- | --- |
| Frontend | `http://localhost:5173` |
| FastAPI Swagger | `http://localhost:8000/docs` |
| FastAPI ReDoc | `http://localhost:8000/redoc` |
| Health endpoint | `http://localhost:8000/health` |
| WhatsApp status | `http://localhost:3100/status` |

## Docker Deployment

The root `docker-compose.yml` is not a minimal demo stack. It includes support services for real operational conditions.

### Services in Docker Compose

| Service | Purpose |
| --- | --- |
| `whatsapp` | WhatsApp bridge |
| `orchestrator` | Main backend |
| `frontend` | Built frontend served by internal web server |
| `warp` | SOCKS5 proxy path used for scraping and email routing |
| `pinchtab` | Headless browser automation service |

### Start with Docker Compose

```bash
docker compose up -d --build
docker compose logs -f
```

### Docker access points

| Surface | URL |
| --- | --- |
| Frontend | `http://localhost:3010` |
| Orchestrator | `http://localhost:8000` |
| WhatsApp service | `http://localhost:3110` |
| PinchTab | `http://localhost:9867` |

### Important Docker notes

1. Compose uses `.env.production` for the orchestrator container by default.
2. The containerized orchestrator points `WA_SERVICE_URL` to the internal service name, not `localhost`.
3. The containerized orchestrator registers `WEBHOOK_URL` using the internal Docker hostname, not the host machine URL.

## Environment Variables

The project has many config keys, but you do not need everything on day one.

### Common minimum set

```env
OPENAI_API_KEY=...
DATABASE_PATH=data/getcontact.db
WA_SERVICE_URL=http://localhost:3100
WEBHOOK_URL=http://localhost:8000/webhook/incoming
OUTREACH_START_HOUR=7
OUTREACH_END_HOUR=22
MAX_DAILY_CONVERSATIONS=20
MIN_MESSAGE_GAP_SECONDS=30
AGENT_MODEL=gpt-4o-mini
VISION_MODEL=gpt-4o-mini
MAX_AI_CONCURRENT=3
```

### Frequently useful optional keys

```env
SERPER_API_KEY=...
IG_USERNAME=...
IG_PASSWORD=...
APIFY_API_KEY=...

DMS_MYSQL_HOST=...
DMS_MYSQL_PORT=3306
DMS_MYSQL_USER=...
DMS_MYSQL_PASSWORD=...
DMS_MYSQL_DATABASE=...

SMTP_HOST=...
SMTP_PORT=465
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_SOCKS_ENABLED=true
SMTP_SOCKS_HOST=...
SMTP_SOCKS_PORT=1080
```

### Config precedence

Many values are runtime-adjustable from the Settings UI or API and persisted into the SQLite `config` table. In practice that means DB-backed config can override your original environment defaults.

## How the Core Contact Pipeline Works

### Stage 1 - University source

Universities can come from PDDIKTI collection, import flows, or manual creation.

### Stage 2 - Instagram handle discovery

The orchestrator tries to find official Instagram handles through a tiered strategy:

1. Web search and DuckDuckGo driven discovery
2. Instagram web search fallback
3. University website scraping

Accepted results update the university row and move status toward `ig_found`.

### Stage 3 - Instagram post scraping

The scraper collects relevant posts from the main university Instagram and, where present, related accounts such as BEM or similar operational accounts.

### Stage 4 - Phone extraction

The extractor combines caption parsing with image-based OCR and saves normalized contacts into `ig_contacts`.

### Stage 5 - Outreach

The scheduler selects universities in the right state, chooses an eligible contact without an existing conversation, creates a conversation record, and enqueues a WhatsApp message through the orchestrator send queue.

### Stage 6 - Reply processing

Replies come back through the WhatsApp service webhook, are normalized by the orchestrator, then routed into the contact conversation manager or audiensi manager depending on the current phone context.

## Conversation and Scheduling Flows

### Contact conversation states

The core contact chatbot revolves around these states:

```text
PENDING
  -> INITIAL_SENT
  -> WAITING_REPLY / FOLLOWUP_SENT / NEED_MORE
  -> GOT_NUMBER | REFUSED | ABANDONED | UNDELIVERED
```

What matters operationally is:

1. `GOT_NUMBER` is success.
2. `REFUSED`, `ABANDONED`, and `UNDELIVERED` are terminal outcomes.
3. Follow-ups are scheduled based on elapsed time since the last outbound contact.

### Audiensi continuation

When a contact conversation successfully yields the right number, the system can auto-queue an audiensi workflow. That flow has its own conversation logic, document generation, and Zoom follow-up handling.

## Frontend Surface Area

The frontend is already much broader than a single dashboard page. Major pages include:

| Page | Purpose |
| --- | --- |
| Dashboard | Funnel overview, quotas, summary metrics |
| Universities | Search, filter, inspect, import, and group universities |
| University Detail | Inspect posts, contacts, related IGs |
| Pipeline | Trigger agents, inspect activity logs, control execution |
| Conversations | Review outreach states and message history |
| WhatsApp | Manage QR and connection state |
| Audiensi | Track scheduling workflow |
| CRM | Review and run person profiling requests |
| Blast | WhatsApp campaign operations |
| Email Blast | Email campaign creation and reply tracking |
| DMS Schedules | Review DMS-sourced schedules and research state |
| Settings | Config, access, exports, health, IG account management |

### Realtime behaviour

The frontend uses WebSocket updates from the orchestrator to avoid excessive polling when live events are available. Query hooks fall back to periodic refetch when the WebSocket is not connected.

## Operational Notes

### This project is stateful

You are not dealing with a stateless API demo. Runtime health depends on:

1. SQLite data integrity.
2. Valid WhatsApp auth sessions.
3. Valid IG sessions or fallback scraping methods.
4. External provider connectivity.
5. Correct config values persisted in DB.

### The webhook path matters

The orchestrator registers its webhook into the WhatsApp service at startup. If the WhatsApp service is not running first, incoming message handling will not be wired automatically until registration succeeds later.

### Scheduler behaviour matters

The project can perform work without manual button clicks. If you are debugging, always check whether scheduled jobs, pause state, quota limits, or time windows are affecting behaviour.

### Auth now exists

The dashboard is no longer just an open admin console. Protected routes and backend role checks are present, so some pages and operations depend on the active user session and permissions.

## Common Commands

### Local development

```bash
# Backend
python -m uvicorn orchestrator.main:app --port 8000 --reload

# Frontend
cd frontend && npm run dev

# WhatsApp service
cd whatsapp-service && npm run dev
```

### Basic operations

```bash
# Health
curl http://localhost:8000/health

# Trigger collection
curl -X POST http://localhost:8000/pipeline/collect-universities

# Trigger Agent 1
curl -X POST http://localhost:8000/pipeline/find-ig-handles

# Trigger Agent 2
curl -X POST http://localhost:8000/pipeline/scrape-ig-posts

# Trigger Agent 3
curl -X POST http://localhost:8000/pipeline/extract-phones

# Start outreach loop manually
curl -X POST http://localhost:8000/outreach/start

# Pause and resume
curl -X POST http://localhost:8000/control/pause
curl -X POST http://localhost:8000/control/resume
```

### Windows helpers

```powershell
.\start-all.bat
.\stop-all.bat
```

## Troubleshooting

| Problem | Likely Cause | What to Check |
| --- | --- | --- |
| QR does not appear | WhatsApp service not healthy | `http://localhost:3100/status` locally or container logs |
| Orchestrator says webhook not registered | WhatsApp service started late or unavailable | Start WhatsApp service first and restart orchestrator |
| Bot sends nothing | Pause state, quota, no eligible contacts, wrong time window | Check Settings, pipeline status, and `daily_quota` |
| Incoming messages are ignored | No conversation exists for that phone or chatbot disabled | Check conversation records and control state |
| IG scraping quality drops | Session health, proxy issues, platform changes | Check IG accounts, proxy path, fallback provider setup |
| Email blast is unreliable | SMTP, IMAP, or SOCKS proxy misconfiguration | Validate mailbox config and connectivity |
| Docker works but local dev does not | Port or env mismatch | Compare `WA_SERVICE_URL`, `WEBHOOK_URL`, and actual ports |

## Final Orientation

If you are new to this repository, the fastest way to build a correct mental model is:

1. Start with the core trio: `orchestrator/main.py`, `orchestrator/conversation.py`, and `whatsapp-service/src/index.ts`.
2. Then inspect `orchestrator/scheduler.py` and `orchestrator/agents/`.
3. Then move to `frontend/src/App.tsx`, `frontend/src/pages/PipelinePage.tsx`, and `frontend/src/pages/ConversationsPage.tsx`.
4. Only after that expand into `audiensi/`, `crm/`, `osint/`, `email_blast.py`, and DMS sync.

That order matches how the project behaves in real operation: discover contacts first, run outreach second, then layer intelligence and campaign workflows on top.
