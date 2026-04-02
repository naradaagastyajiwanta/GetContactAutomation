# Architecture

**Project:** GetContactAI
**Last Updated:** 2026-04-02

## Table of Contents

1. [Overview](#overview)
2. [System Topology](#system-topology)
3. [Core Runtime Services](#core-runtime-services)
4. [Primary Business Domains](#primary-business-domains)
5. [Core Contact Pipeline](#core-contact-pipeline)
6. [Message and Webhook Flow](#message-and-webhook-flow)
7. [Data and Persistence Model](#data-and-persistence-model)
8. [Frontend Architecture](#frontend-architecture)
9. [Deployment Modes](#deployment-modes)
10. [Representative API Surface](#representative-api-surface)
11. [Operational Characteristics](#operational-characteristics)
12. [Known Architectural Realities](#known-architectural-realities)

## Overview

GetContactAI is a multi-service operational platform centered on one main workflow: discovering university contact paths and converting them into WhatsApp conversations that can yield the correct contact person for follow-up.

That core workflow is extended by adjacent modules:

- audiensi scheduling and PDF invitation handling
- OSINT enrichment for institutions
- CRM profiling for people and PICs
- WhatsApp blast campaigns
- email blast campaigns with reply tracking
- DMS MySQL synchronization and research workflows
- dashboard auth and permission control

This is not a small chatbot app. It is a stateful operations system with background scheduling, external dependencies, real message delivery, and multiple downstream workflows.

## System Topology

### High-level runtime topology

```text
Browser
  |
  | HTTP + WebSocket
  v
Frontend (React + Vite)
  |
  | /api and /ws
  v
Orchestrator (FastAPI)
  |
  +--> SQLite
  |
  +--> OpenAI and search / scraping providers
  |
  +--> DMS MySQL, SMTP, IMAP, proxy paths
  |
  +--> WhatsApp Service (/send, /send-document, /webhook/register)
                |
                v
          WhatsApp network
                |
                v
      incoming replies forwarded back to orchestrator webhook
```

### Local ports

| Service | Local Port |
| --- | --- |
| Frontend | `5173` |
| Orchestrator | `8000` |
| WhatsApp Service | `3100` |

### Docker-exposed ports

| Service | Docker Port |
| --- | --- |
| Frontend | `3010` |
| Orchestrator | `8000` |
| WhatsApp Service | `3110` |
| PinchTab | `9867` |

## Core Runtime Services

### 1. Orchestrator

The orchestrator is the primary backend. It is responsible for:

- FastAPI API surface
- SQLite initialization and access
- webhook intake for incoming WhatsApp messages
- conversation state transitions
- scheduler jobs and follow-up execution
- AI-backed message generation and reply analysis
- OSINT, CRM, audiensi, blast, email, DMS, and auth modules
- WebSocket broadcasts for frontend live updates

Important files:

| File | Role |
| --- | --- |
| `orchestrator/main.py` | App entrypoint, lifecycle, endpoints, webhook handling |
| `orchestrator/db.py` | Schema and queries |
| `orchestrator/conversation.py` | Contact conversation state machine |
| `orchestrator/scheduler.py` | Scheduled jobs for pipeline work |
| `orchestrator/message_queue.py` | Serialized outbound send queue and AI semaphore |
| `orchestrator/websocket.py` | Frontend event broadcast support |

### 2. WhatsApp Service

The WhatsApp service is a dedicated Node.js bridge using Baileys. It is responsible for:

- device session lifecycle
- QR pairing and reconnection
- outbound text and document sends
- queue and anti-ban controls
- forwarding inbound messages to the orchestrator webhook
- exposing operational status to the orchestrator and dashboard

Important files:

| File | Role |
| --- | --- |
| `whatsapp-service/src/index.ts` | Express entrypoint, message flow, endpoints |
| `whatsapp-service/src/deviceManager.ts` | Multi-device state and socket lifecycle |
| `whatsapp-service/src/messageQueue.ts` | Persistent WhatsApp queue |
| `whatsapp-service/src/antiBan.ts` | Anti-ban state and send protection |

### 3. Frontend

The frontend is a React dashboard used to operate and inspect the system. It is responsible for:

- rendering the operational UI
- calling backend APIs through `/api`
- subscribing to backend WebSocket updates
- presenting pipeline, conversation, blast, DMS, CRM, audiensi, and settings surfaces
- enforcing route-level permission checks

Important files:

| File | Role |
| --- | --- |
| `frontend/src/App.tsx` | Route registration |
| `frontend/src/api/client.ts` | Shared API client |
| `frontend/src/hooks/useWebSocket.ts` | Live event subscription and cache updates |
| `frontend/src/pages/` | Domain pages for each feature area |

## Primary Business Domains

### Contact collection and outreach

The primary production flow in the repository.

### Audiensi

Triggered after a successful contact result. Handles follow-up toward Zoom scheduling and invitation documents.

### OSINT

Institution-level public information enrichment.

### CRM

Person-level profile enrichment for PICs and related stakeholders.

### WhatsApp Blast

Bulk messaging campaigns across eligible contacts.

### Email Blast

Outbound email campaigns plus inbox and sent-folder tracking.

### DMS Integration

Synchronization and research workflows around schedules, contacts, and approvals.

### Auth and permissions

Role-based access across the operational dashboard.

## Core Contact Pipeline

### Stage 1: University source

Universities can be collected from PDDIKTI or entered through import and manual flows.

Primary entity:

- `universities`

Typical base status:

- `pending`

### Stage 2: Instagram handle discovery

Agent 1 attempts to find a valid Instagram handle using a tiered strategy.

Typical approach:

1. web search or DuckDuckGo path
2. Instagram web search fallback
3. university website scraping

Successful outcome usually moves a university toward:

- `ig_found`

### Stage 3: Instagram post scraping

Agent 2 gathers relevant Instagram posts, potentially across main and related accounts.

Primary entities:

- `ig_posts`
- related IG references

Successful outcome usually moves a university toward:

- `ig_scraped`

### Stage 4: Phone extraction

Agent 3 extracts phone numbers and names from captions and images.

Primary entity:

- `ig_contacts`

### Stage 5: Outreach scheduling

The scheduler selects eligible contacts and creates conversation records.

Primary entity:

- `conversations`

### Stage 6: WhatsApp send

The orchestrator enqueues outbound sends and delegates the actual transport to the WhatsApp service.

### Stage 7: Incoming reply processing

Inbound WhatsApp messages return via webhook and are processed against the current phone context.

### Stage 8: Success transition

If the system obtains the correct number, the conversation can move to a success state and optionally create an audiensi follow-on workflow.

## Message and Webhook Flow

### Outbound flow

```text
Frontend or scheduler action
  -> orchestrator endpoint or internal scheduler job
  -> message_queue enqueue
  -> serialized send worker
  -> POST to WhatsApp service /send or /send-document
  -> WhatsApp service uses device manager to send through Baileys
```

### Inbound flow

```text
real WhatsApp reply
  -> WhatsApp service receives message from Baileys
  -> message normalized in Node service
  -> webhook forwarded to orchestrator /webhook/incoming
  -> orchestrator schedules background processing
  -> per-phone lock prevents duplicate concurrent handling
  -> message routed to audiensi handler or contact conversation handler
  -> optional response is enqueued back to WhatsApp service
```

### Why the webhook registration matters

At orchestrator startup, the backend attempts to register its webhook URL with the WhatsApp service. If the WhatsApp service is not ready or the URL is wrong, incoming replies will not flow correctly until registration succeeds.

## Data and Persistence Model

### Main storage model

The system is stateful and primarily backed by SQLite for the core operational database.

Key persisted areas include:

- universities and status funnel
- Instagram posts and extracted contacts
- contact conversations and message history
- runtime configuration
- auth sessions and role state
- blast and email campaign records
- learning and reflection artifacts

### Important tables

| Table | Role |
| --- | --- |
| `universities` | Base institution records and funnel status |
| `ig_posts` | Scraped posts and extraction targets |
| `ig_contacts` | Extracted contacts |
| `conversations` | Outreach state and message history |
| `daily_quota` | Daily usage tracking |
| `config` | DB-backed runtime configuration |
| `auth_user_roles`, `auth_sessions`, `auth_audit_logs` | Dashboard authorization model |
| `conversation_analyses`, `lessons` | Learning system state |
| `blast_*`, `email_*` | Campaign and delivery tracking |

### Other stateful runtime paths

| Path | Contents |
| --- | --- |
| `data/getcontact.db` | Main SQLite database |
| `whatsapp-service/auth_store*` | WhatsApp auth data |
| `whatsapp-service/data/` | WhatsApp queue and related runtime storage |
| `data/audiensi_docs/` | Generated documents |
| `data/email_attachments/` | Email assets |

## Frontend Architecture

### Main route surfaces

The frontend route tree includes:

- dashboard
- universities and university detail
- pipeline
- conversations and conversation detail
- WhatsApp
- audiensi
- CRM
- blast
- email blast
- DMS schedules
- settings
- login and protected layouts

### Data access pattern

The frontend uses:

- Axios for transport
- TanStack React Query for server state
- WebSocket events to reduce polling and push updates into caches

### Realtime pattern

When the WebSocket is connected, the frontend can reduce or disable polling for some views. When the socket is disconnected, hooks fall back to periodic refetch intervals.

## Deployment Modes

### Local development mode

Expected shape:

- frontend on `5173`
- orchestrator on `8000`
- WhatsApp service on `3100`

Best when:

- actively editing code
- reading detailed logs
- iterating on one service at a time

### Docker mode

Expected shape:

- frontend exposed on `3010`
- orchestrator exposed on `8000`
- WhatsApp service exposed on `3110`
- support services such as WARP and PinchTab available

Best when:

- testing more complete runtime topology
- using production-like service URLs and support services

## Representative API Surface

The backend API is broad. Representative paths include:

### Core operations

- `GET /health`
- `POST /webhook/incoming`
- `GET /conversations`
- `GET /conversations/{id}`
- `POST /conversations/test`

### Pipeline operations

- `POST /pipeline/collect-universities`
- `POST /pipeline/find-ig-handles`
- `POST /pipeline/scrape-ig-posts`
- `POST /pipeline/extract-phones`
- `POST /pipeline/discover-bem`
- `GET /pipeline/status`
- `GET /pipeline/logs`

### WhatsApp and control

- `GET /wa/status`
- `GET /wa/devices`
- `POST /wa/devices/{device_id}/connect`
- `POST /control/pause`
- `POST /control/resume`

### Higher-level domains

- `/audiensi/*`
- `/crm/*`
- `/osint/*`
- `/blast/*`
- `/email-blast/*`
- `/dms/*`
- `/config`
- `/knowledge-items`

### Frontend transport note

The frontend uses `/api` as its base URL and relies on proxying or reverse proxy configuration to reach the orchestrator.

## Operational Characteristics

### Stateful by design

This architecture depends on persisted runtime state. That means debugging is not just about code correctness. It also involves:

- current DB contents
- current config values in SQLite
- current WhatsApp device session validity
- scheduler timing and quotas
- external provider health

### Queue-driven delivery

Outbound sends are not always immediate fire-and-forget operations. The orchestrator has a serialized message queue, and the WhatsApp service has its own protections and queue behavior. This is intentional to reduce race conditions and operational risk.

### Scheduler-driven behavior

The system can keep working without a user clicking buttons in the UI. Scheduler jobs drive outreach, follow-up, reflection, sync, and some agent work.

### Permission-gated dashboard

The dashboard is not a purely open internal page set. Backend auth and frontend protected routes are in place.

## Known Architectural Realities

### The repository is broad

The codebase contains a lot more than the core contact funnel. New contributors should not assume every module is equally simple to run locally.

### Some modules are highly environment-dependent

The following areas depend heavily on real credentials, real sessions, or external systems:

- Instagram scraping quality
- DMS sync
- email blast delivery and inbox tracking
- OSINT and CRM enrichment quality

### The contact funnel is the best entry point

If you want to understand how the system behaves end-to-end, start with this path:

1. `orchestrator/main.py`
2. `orchestrator/conversation.py`
3. `orchestrator/scheduler.py`
4. `orchestrator/message_queue.py`
5. `orchestrator/agents/ig_handle_finder.py`
6. `orchestrator/agents/ig_post_scraper.py`
7. `orchestrator/agents/ig_phone_extractor.py`
8. `whatsapp-service/src/index.ts`
9. `frontend/src/App.tsx`
10. `frontend/src/pages/PipelinePage.tsx`

That path reflects the most central runtime architecture in the repository today.
