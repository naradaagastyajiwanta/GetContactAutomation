# Startup Guide

Practical guide to run GetContactAI in local development or with Docker.

## What You Are Starting

GetContactAI has three primary runtime services:

| Service | Local Port | Purpose |
| --- | --- | --- |
| Orchestrator | `8000` | Main backend, API, scheduler, database access, AI orchestration |
| WhatsApp Service | `3100` | Baileys bridge for WhatsApp sessions and message delivery |
| Frontend | `5173` | React dashboard for operations and monitoring |

There is also a Docker topology that can include support services such as WARP and PinchTab.

## Choose a Mode

### Mode A: Local development

Use this when you want fast iteration on code and logs.

### Mode B: Docker deployment

Use this when you want a more production-like setup, including support services and container networking.

## Prerequisites

### Required

| Requirement | Notes |
| --- | --- |
| Python 3.11+ | For the orchestrator |
| Node.js 20+ | For frontend and WhatsApp service |
| npm | Standard Node package manager |
| OpenAI API key | Required for AI-assisted message generation and extraction |

### Common optional dependencies

| Dependency | Why it matters |
| --- | --- |
| Serper API key | Additional search fallback for Instagram handle discovery |
| Instagram account credentials | Useful for session-based scraping paths |
| DMS MySQL credentials | Needed for DMS sync and research features |
| SMTP and IMAP credentials | Needed for email blast workflows |
| Docker and Docker Compose | Needed for containerized mode |

## Environment Setup

Create a `.env` file from the example.

### PowerShell

```powershell
Copy-Item .env.example .env
```

### Bash

```bash
cp .env.example .env
```

### Minimum useful local values

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
```

### Common optional values

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

## Local Development Startup

### 1. Install dependencies

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

### 2. Start services in the correct order

The order matters.

1. Start `whatsapp-service`
2. Start `orchestrator`
3. Start `frontend`

The orchestrator tries to register its webhook into the WhatsApp service on startup. If WhatsApp starts later, incoming message routing may not be ready yet.

### Terminal 1 - WhatsApp Service

```bash
cd whatsapp-service
npm run dev
```

Expected outcome:

- the Express service boots on port `3100`
- status endpoint becomes available
- the QR endpoint becomes available for pairing

### Terminal 2 - Orchestrator

```bash
python -m uvicorn orchestrator.main:app --port 8000 --reload
```

Expected outcome:

- SQLite schema is initialized or reused
- DB-backed config is loaded
- webhook registration is attempted against the WhatsApp service
- background tasks and scheduler jobs start

### Terminal 3 - Frontend

```bash
cd frontend
npm run dev
```

Expected outcome:

- Vite runs on `http://localhost:5173`
- frontend can call backend APIs through `/api`
- WebSocket connection can be established to `/ws`

## First-Time WhatsApp Setup

1. Open the dashboard.
2. Navigate to the WhatsApp page.
3. Connect a device and scan the QR code.
4. Wait until the device state changes to connected.

Session data is persisted under the WhatsApp service auth store paths, so you usually do not need to rescan on every restart unless the session is invalidated.

## Verify the System

### Backend health

```bash
curl http://localhost:8000/health
```

### WhatsApp service health

```bash
curl http://localhost:3100/status
```

### Frontend

Open:

- `http://localhost:5173`

### What to confirm

| Check | What good looks like |
| --- | --- |
| Backend health | `status: ok` |
| WhatsApp service | running and device list accessible |
| Frontend | dashboard loads without API errors |
| Webhook path | backend logs do not show repeated registration failure |

## Useful First Actions in the UI

### If you want to test messaging safely

Use the test conversation flow from the dashboard so replies can be mapped into a real conversation record.

### If you want to inspect the pipeline

Open the Pipeline page and review:

- current funnel counts
- agent execution logs
- pause or resume state

### If you want to inspect real conversation state

Open the Conversations page and filter by state.

## Manual API Operations

### Pipeline triggers

```bash
curl -X POST http://localhost:8000/pipeline/collect-universities
curl -X POST http://localhost:8000/pipeline/find-ig-handles
curl -X POST http://localhost:8000/pipeline/scrape-ig-posts
curl -X POST http://localhost:8000/pipeline/extract-phones
curl -X POST http://localhost:8000/pipeline/discover-bem
curl -X POST http://localhost:8000/outreach/start
```

### Pause and resume

```bash
curl -X POST http://localhost:8000/control/pause
curl -X POST http://localhost:8000/control/resume
```

### Documentation

```text
http://localhost:8000/docs
http://localhost:8000/redoc
```

## Docker Startup

The Docker topology is broader than local dev. It can include the frontend, orchestrator, WhatsApp service, WARP proxy, and PinchTab.

### Main exposed ports in Docker mode

| Service | Exposed Port |
| --- | --- |
| Frontend | `3010` |
| Orchestrator | `8000` |
| WhatsApp Service | `3110` |
| PinchTab | `9867` |

### Start with Docker Compose

```bash
docker compose up -d --build
docker compose logs -f
```

### Stop Docker Compose

```bash
docker compose down
```

### Notes for Docker mode

1. The orchestrator container uses internal service URLs, not host localhost URLs.
2. The main compose file uses `.env.production` for the orchestrator container.
3. WARP and PinchTab are part of the runtime topology in Docker mode.

## Common Startup Problems

| Problem | Likely cause | Fix |
| --- | --- | --- |
| QR does not appear | WhatsApp service not healthy or no device session init | Check `http://localhost:3100/status` or container logs |
| Webhook registration fails | WhatsApp service started after backend or wrong `WA_SERVICE_URL` | Start WhatsApp first, verify env, restart orchestrator |
| Frontend loads but API fails | Backend not running or proxy mismatch | Verify `http://localhost:8000/health` and frontend proxy config |
| Bot does not respond | Pipeline paused, chatbot disabled, no matching conversation, or outside allowed hours | Check control state, config, and conversation records |
| Messages are sent too slowly or not at all | Queue backlog, anti-ban restrictions, device connectivity | Check WhatsApp status, queue stats, and backend logs |
| IG scraping is weak | IG session issue, proxy issue, or fallback provider issue | Check IG account health and provider config |
| Email blast features fail | SMTP, IMAP, or SOCKS proxy misconfigured | Validate mailbox and proxy environment values |

## Shutdown

### Local development

Stop each service with `Ctrl+C` in its terminal.

### Windows helper

```powershell
.\stop-all.bat
```

### Docker

```bash
docker compose down
```

## Recommended Reading Order

If you are onboarding into the codebase after the system is running, read these files next:

1. `README.md`
2. `orchestrator/main.py`
3. `orchestrator/conversation.py`
4. `orchestrator/scheduler.py`
5. `whatsapp-service/src/index.ts`
6. `frontend/src/App.tsx`
7. `frontend/src/pages/PipelinePage.tsx`
