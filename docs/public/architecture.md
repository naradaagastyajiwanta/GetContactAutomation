# Architecture - GetContact AI Agent

**Version:** 1.0.0
**Last Updated:** 2025-02-25

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Core Services](#core-services)
4. [Data Flow Pipeline](#data-flow-pipeline)
5. [Database Schema](#database-schema)
6. [Technology Stack](#technology-stack)
7. [Service Communication](#service-communication)
8. [Security Considerations](#security-considerations)
9. [Scalability Architecture](#scalability-architecture)

---

## System Overview

GetContact AI Agent is a distributed multi-service application that automates WhatsApp outreach to Indonesian universities. The system orchestrates a complex pipeline involving web scraping, AI-powered vision processing, and conversational AI to collect contact information for university secretariats.

### Key Characteristics

- **Microservices Architecture:** Three independent services communicating via HTTP/webhooks
- **Event-Driven:** Async processing with queues and schedulers
- **AI-Powered:** Uses GPT-4o for vision OCR and GPT-4o-mini for conversations
- **State Machine:** Conversation flow managed through states
- **Rate-Limited:** Respects platform limits and outreach hours

### Business Domain

**Target:** Indonesian universities (PDDIKTI database)
**Goal:** Collect secretariat contact numbers via WhatsApp
**Method:** Multi-stage pipeline from discovery → scraping → AI extraction → outreach → follow-up

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         GETCONTACT AI AGENT                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐      ┌──────────────────┐      ┌──────────────┐     │
│  │              │      │                  │      │              │     │
│  │  ORCHESTRATOR│◄────►│  WHATSAPP        │◄────►│   FRONTEND   │     │
│  │  (Python)    │      │  SERVICE (Node)  │      │   (React)    │     │
│  │  Port: 8000  │      │  Port: 3100      │      │  Port: 5173  │     │
│  │              │      │                  │      │              │     │
│  └──────┬───────┘      └──────────┬───────┘      └──────────────┘     │
│         │                        │                                     │
│         │ Webhook                │ Baileys                             │
│         │                        │                                     │
│         ▼                        │                                     │
│  ┌──────────────────┐            │                                     │
│  │   Database       │            │                                     │
│  │   (SQLite)       │            │                                     │
│  └──────────────────┘            │                                     │
│         ▲                        │                                     │
│         │                        │                                     │
│         │                        ▼                                     │
│  ┌──────────────────────────────────────────────────┐                 │
│  │              EXTERNAL SERVICES                   │                 │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │                 │
│  │  │ OpenAI   │  │ Serper   │  │ PDDIKTI API  │  │                 │
│  │  │ GPT-4o   │  │ Google   │  │ Instagram    │  │                 │
│  │  └──────────┘  └──────────┘  │ Apify/       │  │                 │
│  │                              │ ScrapingBot  │  │                 │
│  │                              └──────────────┘  │                 │
│  └──────────────────────────────────────────────────┘                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Services

### 1. Orchestrator Service (Python FastAPI)

**Port:** 8000
**Responsibilities:** Core business logic, pipeline coordination, state management

**Key Modules:**

- **`main.py`** - FastAPI application with REST endpoints and webhook handler
- **`db.py`** - Database schema and async queries (aiosqlite)
- **`conversation.py`** - Conversation state machine and OpenAI integration
- **`message_queue.py`** - AI concurrency control and serial WA message queue
- **`scheduler.py`** - APScheduler for automated pipeline execution
- **`instagram.py`** - Instagram scraping and phone extraction
- **`config.py`** - Environment configuration with dynamic ConfigManager
- **`agents/`** - Pipeline agent implementations

**API Endpoints:**

- `GET /` - Health check
- `POST /webhook/incoming` - Receive WhatsApp messages
- `GET /api/v1/dashboard/stats` - Dashboard statistics
- `GET /api/v1/universities` - List/universities with pagination
- `POST /api/v1/pipelines/find-handles` - Trigger Agent 1
- `POST /api/v1/pipelines/scrape-posts` - Trigger Agent 2
- `POST /api/v1/pipelines/extract-phones` - Trigger Agent 3
- `GET /api/v1/whatsapp/qr` - Get WhatsApp QR code
- `POST /api/v1/whatsapp/send` - Send WhatsApp message
- `GET /api/v1/conversations` - List conversations
- `GET /api/v1/config` - Get configuration
- `PUT /api/v1/config/{key}` - Update configuration

### 2. WhatsApp Service (Node.js + TypeScript)

**Port:** 3100
**Responsibilities:** WhatsApp bridge with human-like behavior

**Key Features:**

- **Baileys Library:** @whiskeysockets/baileys for WhatsApp Web API
- **Human-Like Behavior:**
  - Typing indicators (composing/paused)
  - Random delays (2-5 seconds before responding)
  - Typing duration proportional to message length
  - Read receipts for incoming messages
- **Message Debouncing:** Combines rapid messages within 5-second window
- **Auto-Reconnect:** Jittered exponential backoff (max 15 attempts)
- **Credential Backup:** Automatic backup/restore of auth store
- **LID Resolution:** Handles Linked Identity (encrypted phone numbers)

**API Endpoints:**

- `POST /send` - Send text message with human-like behavior
- `POST /send-document` - Send file (PDF, images, etc.)
- `GET /qr` - Get QR code for pairing
- `GET /status` - Connection status
- `POST /webhook/register` - Register webhook URL
- `POST /logout` - Logout and clear auth
- `POST /restart` - Restart connection

**Internal Behavior:**

```
Incoming Message → Debounce (5s) → Combine → Forward to Orchestrator
Outgoing Message → Read Receipt → Delay (2-5s) → Typing Indicator →
  Typing Delay → Send → Pause Indicator
```

### 3. Frontend Service (React + TypeScript)

**Port:** 5173 (Vite dev server)
**Responsibilities:** Monitoring dashboard and control panel

**Pages:**

- **Dashboard** - Overview stats, pipeline funnel, today's quota
- **Universities** - University list with filters, add/import modal
- **University Detail** - IG contacts, posts, related IGs
- **Pipeline** - Pipeline overview, agent triggers, activity log
- **Conversations** - Conversation list with state filters
- **Conversation Detail** - Chat history, state timeline
- **WhatsApp** - QR code display, connection status
- **Learning** - AI lessons from conversations
- **Knowledge Base** - Curated knowledge items
- **API Logs** - HTTP request/response logs
- **Settings** - Configuration, control panel, export

**Technology:**

- **React 18** - UI framework
- **React Router 6** - Client-side routing
- **TanStack React Query 5** - Server state management
- **Tailwind CSS 3** - Styling
- **Lucide Icons** - Icon set
- **Axios** - HTTP client

---

## Data Flow Pipeline

The GetContact pipeline consists of 10 phases, each progressing universities through different states:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DATA FLOW PIPELINE                               │
└────────────────────────────────────────────────────────────────────────┘

Phase 1: PDDIKTI Scraping
  └─> Source: PDDIKTI API (pddiktipy)
  └─> Action: Fetch Indonesian universities
  └─> Output: Universities with name, province, website
  └─> Status: pending

Phase 2: IG Handle Discovery (Agent 1)
  └─> Source: University websites, Google/Serper, IG Web API
  └─> Action: Find official Instagram handles
  └─> Methods (3-tier):
      1. Website scraping (most accurate)
      2. Instagram Web Search API
      3. Serper.dev Google search (fallback)
  └─> Verification: Bio keyword matching
  └─> Output: IG handle, confidence score
  └─> Status: pending → ig_found

Phase 3: IG Post Scraping (Agent 2)
  └─> Source: Instagram profiles
  └─> Action: Scrape recent posts (max 50 per profile)
  └─> Methods: Apify/ScrapingBot fallback
  └─> Output: Post URLs, image URLs, captions
  └─> Status: ig_found → ig_scraped

Phase 4: Phone Extraction (Agent 3)
  └─> Source: IG post images
  └─> Action: Extract phone numbers using GPT-4o vision OCR
  └─> Filtering: Contact keyword matching, Indonesian phone patterns
  └─> Output: Phone numbers, contact names, source URLs
  └─> Status: ig_scraped → ig_scraped (with contacts)

Phase 5: BEM Discovery (Agent 4)
  └─> Source: Instagram search
  └─> Action: Find BEM (Student Council) IG handles
  └─> Output: Related IG handles
  └─> Status: Adds to related_ig_contacts table

Phase 6: Initial Outreach
  └─> Source: IG contacts database
  └─> Action: Send initial WhatsApp message
  └─> Message: AI-generated (template or agentic)
  └─> Rate Limit: MAX_DAILY_CONVERSATIONS per day
  └─> Hours: OUTREACH_START_HOUR to OUTREACH_END_HOUR (WIB)
  └─> Status: ig_scraped → contacted

Phase 7: Reply Analysis
  └─> Source: Incoming WhatsApp messages
  └─> Action: Analyze reply using GPT-4o-mini
  └─> Actions:
      - got_number: Extract phone, mark GOT_NUMBER
      - refused: Polite close, mark REFUSED
      - need_followup: Generate follow-up
      - unclear: Ask for clarification
  └─> States: INITIAL_SENT → WAITING_REPLY → REPLIED → ANALYZING

Phase 8: Follow-up Sequence
  └─> Schedule: 24h, 48h after last message
  └─> Max Attempts: MAX_FOLLOWUP_ATTEMPTS (default 3)
  └─> Action: Generate follow-up messages
  └─> States: → FOLLOWUP_SENT → (repeat or ABANDONED)

Phase 9: Success Processing
  └─> Trigger: Phone number extracted
  └─> Action: Update university secretariat_phone
  └─> Status: GOT_NUMBER
  └─> Auto-Queue: Create audiensi conversation

Phase 10: Audiensi Outreach (Optional)
  └─> Separate pipeline for rector outreach
  └─> States: PENDING → INITIAL_SENT → WAITING_REPLY →
              REPLIED → ANALYZING → SCHEDULED →
              COMPLETED → CANCELLED → ABANDONED
```

### Conversation State Machine

```
                    ┌──────────────┐
                    │   PENDING    │
                    └──────┬───────┘
                           │ Send initial
                           ▼
                    ┌──────────────┐
                    │ INITIAL_SENT │
                    └──────┬───────┘
                           │ Receive reply
                           ▼
                    ┌──────────────┐
                    │ WAITING_REPLY│
                    └──────┬───────┘
                           │ Analyze
                           ▼
                    ┌──────────────┐
                    │   REPLIED    │
                    └──────┬───────┘
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
           ┌──────────────┐  ┌──────────────┐
           │  ANALYZING   │  │   REFUSED    │
           └──────┬───────┘  └──────────────┘
                  │
         ┌────────┴────────┐
         ▼                 ▼
  ┌──────────────┐  ┌──────────────┐
  │  GOT_NUMBER  │  │  NEED_MORE   │
  └──────────────┘  └──────┬───────┘
                          │ Follow-up
                          ▼
                   ┌──────────────┐
                   │ FOLLOWUP_SENT│
                   └──────┬───────┘
                          │
                 ┌────────┴────────┐
                 ▼                 ▼
          ┌──────────────┐  ┌──────────────┐
          │  GOT_NUMBER  │  │  ABANDONED   │
          └──────────────┘  └──────────────┘
```

---

## Database Schema

SQLite database at `data/getcontact.db` (auto-created on startup).

### Core Tables

#### `universities`
```sql
CREATE TABLE universities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pddikti_id TEXT UNIQUE,
    province TEXT,
    website TEXT,
    ig_handle TEXT,
    ig_verified BOOLEAN DEFAULT 0,
    secretariat_phone TEXT,
    status TEXT DEFAULT 'pending',
    enabled BOOLEAN DEFAULT 1,
    rector_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Status Flow:** `pending` → `ig_found` → `ig_scraped` → `contacted` → `got_number` / `failed`

#### `ig_contacts`
```sql
CREATE TABLE ig_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER REFERENCES universities(id),
    phone_number TEXT NOT NULL,
    contact_name TEXT,
    source_post_url TEXT,
    source_image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Extracted phone numbers from Instagram posts.

#### `ig_posts`
```sql
CREATE TABLE ig_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    post_url TEXT NOT NULL,
    image_url TEXT,
    caption TEXT,
    post_timestamp TEXT,
    phone_extracted BOOLEAN DEFAULT 0,
    phones_found INTEGER DEFAULT 0,
    source_ig_handle TEXT,
    source_ig_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(university_id, post_url)
);
```

Scraped Instagram posts for phone extraction.

#### `conversations`
```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER REFERENCES universities(id),
    contact_phone TEXT NOT NULL,
    state TEXT DEFAULT 'PENDING',
    message_history TEXT,
    last_message_at TIMESTAMP,
    attempt_count INTEGER DEFAULT 0,
    followup_count INTEGER DEFAULT 0,
    extracted_number TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

WhatsApp conversations with state tracking.

#### `daily_quota`
```sql
CREATE TABLE daily_quota (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    conversations_started INTEGER DEFAULT 0,
    messages_sent INTEGER DEFAULT 0,
    ig_profiles_scraped INTEGER DEFAULT 0
);
```

Rate limiting tracking per day.

### Supporting Tables

#### `related_ig_contacts` - Additional IG handles found (BEM, etc.)
#### `pipeline_logs` - Pipeline execution history
#### `lessons` - AI learning from conversations
#### `knowledge_items` - Curated knowledge base
#### `api_logs` - HTTP request/response logs
#### `audiensi_conversations` - Rector outreach conversations
#### `audiensi_messages` - Audiensi message history
#### `config` - Dynamic configuration storage

---

## Technology Stack

### Python (Orchestrator)

**Framework & API:**
- `FastAPI 0.115.6` - Modern async web framework
- `Uvicorn 0.34.0` - ASGI server
- `Pydantic` - Data validation

**Database:**
- `aiosqlite 0.20.0` - Async SQLite
- `phonenumbers 8.13.52` - Phone validation

**AI/ML:**
- `openai >=1.66.0` - GPT-4o vision, GPT-4o-mini chat
- `Pillow 11.1.0` - Image processing

**Scheduling:**
- `apscheduler 3.10.4` - Cron-like scheduler

**HTTP & Scraping:**
- `httpx 0.28.1` - Async HTTP client
- `pddiktipy 2.0.6` - PDDIKTI API wrapper

**Utilities:**
- `python-dotenv 1.0.1` - Environment variables
- `rapidfuzz 3.11.0` - Fuzzy matching
- `python-multipart 0.0.20` - Form data parsing
- `python-docx 1.1.2` - Word documents
- `PyPDF2 3.0.1` - PDF parsing
- `openpyxl 3.1.5` - Excel files
- `gspread 6.1.4` - Google Sheets

### Node.js (WhatsApp Service)

**Core:**
- `@whiskeysockets/baileys 7.0.0-rc.9` - WhatsApp Web API
- `Express 4.21.1` - Web server
- `TypeScript 5.7.2` - Type-safe JS

**Utilities:**
- `axios 1.7.9` - HTTP client
- `cors 2.8.5` - CORS middleware
- `pino 9.5.0` - Logging
- `qrcode 1.5.4` - QR code generation
- `@hapi/boom 10.0.1` - HTTP errors

### React (Frontend)

**Core:**
- `React 18.3.1` - UI framework
- `React Router 6.28.0` - Routing
- `TypeScript 5.7.2` - Type-safe JS
- `Vite 6.0.3` - Build tool

**State & Data:**
- `TanStack React Query 5.62.0` - Server state
- `axios 1.7.9` - HTTP client

**Styling:**
- `Tailwind CSS 3.4.17` - Utility-first CSS
- `@tailwindcss/forms 0.5.9` - Form styling
- `lucide-react 0.468.0` - Icons

**Utilities:**
- `clsx 2.1.1` - Class names
- `date-fns 4.1.0` - Date formatting
- `react-hot-toast 2.4.1` - Notifications

---

## Service Communication

### Orchestrator → WhatsApp Service

**Send Message:**
```http
POST http://localhost:3100/send
Content-Type: application/json

{
  "to": "628123456789",
  "message": "Hello, world!",
  "replyToMsgKey": {...},
  "allMsgKeys": [...]
}
```

**Response:**
```json
{
  "success": true,
  "messageId": "3EB0..."
}
```

**Send Document:**
```http
POST http://localhost:3100/send-document
Content-Type: application/json

{
  "to": "628123456789",
  "fileBase64": "base64encoded...",
  "fileName": "document.pdf",
  "mimetype": "application/pdf",
  "caption": "Please review this document"
}
```

### WhatsApp Service → Orchestrator (Webhook)

**Incoming Message:**
```http
POST http://localhost:8000/webhook/incoming
Content-Type: application/json

{
  "from": "628123456789",
  "message": "Yes, please send more info",
  "timestamp": 1737852000,
  "messageId": "3EB0...",
  "pushName": "John Doe",
  "msgKey": {
    "remoteJid": "628123456789@s.whatsapp.net",
    "id": "3EB0...",
    "fromMe": false
  },
  "allMsgKeys": [...]
}
```

### Frontend → Orchestrator

**REST API calls via Axios:**

```typescript
// Get universities
const { data } = await axios.get('/api/v1/universities', {
  params: { skip: 0, limit: 50, search: 'Indonesia' }
});

// Trigger pipeline
await axios.post('/api/v1/pipelines/find-handles');

// Send message
await axios.post('/api/v1/whatsapp/send', {
  to: '628123456789',
  message: 'Test message'
});
```

---

## Security Considerations

### API Keys & Secrets

**Required Environment Variables:**
- `OPENAI_API_KEY` - GPT-4o access
- `SERPER_API_KEY` - Google search (free tier: 2500 queries/month)

**Optional:**
- `IG_USERNAME` / `IG_PASSWORD` - Dedicated scraping account
- `APIFY_API_KEY` - Backup IG scraping

**Best Practices:**
- Never commit `.env` files
- Use separate API keys for dev/prod
- Rotate keys regularly
- Monitor usage for anomalies

### WhatsApp Authentication

**Auth Store Location:** `whatsapp-service/auth_store/`

**Security:**
- Files contain session credentials
- Automatic backup to `auth_store_backup/`
- Clear on logout
- Not committed to Git (in `.gitignore`)

### Rate Limiting

**Configurable Limits:**
- `MAX_DAILY_CONVERSATIONS` - Daily WhatsApp conversations (default: 20)
- `MIN_MESSAGE_GAP_SECONDS` - Minimum gap between messages (default: 300s)
- `MAX_IG_PROFILES_PER_DAY` - Daily IG scrapes (default: 200)
- `IG_REQUEST_DELAY_SECONDS` - Delay between IG requests (default: 7s)

**Purpose:**
- Respect WhatsApp ToS
- Avoid Instagram rate limits
- Prevent account suspension

### Outreach Hours

**Configurable:**
- `OUTREACH_START_HOUR` - Default: 7 (WIB)
- `OUTREACH_END_HOUR` - Default: 22 (WIB)

**Timezone:** Asia/Jakarta (UTC+7)

### Data Privacy

**Stored Data:**
- University public information
- Instagram posts (public)
- Phone numbers (business contacts)
- Conversation history

**Recommendations:**
- Add authentication for production
- Encrypt sensitive fields
- Implement data retention policies
- GDPR compliance for EU contacts

### Human-Like Behavior

**Purpose:** Avoid WhatsApp spam detection

**Techniques:**
- Random delays (2-5 seconds)
- Typing indicators
- Read receipts
- Proportional typing duration
- Message debouncing

---

## Scalability Architecture

### Current Design (Single-Instance)

**Concurrency Control:**

```
AI Processing:
  └─> Semaphore (MAX_AI_CONCURRENT = 3)
  └─> Limits parallel OpenAI calls

WhatsApp Sending:
  └─> Serial queue
  └─> Fixed interval (SEND_INTERVAL_MS)
  └─> One message at a time

Pipeline Agents:
  └─> Thread pool (2 workers)
  └─> Separate event loops
  └─> Non-blocking HTTP handling
```

### Bottlenecks

1. **WhatsApp Serial Queue:** Single message at a time
2. **AI Semaphore:** Only 3 parallel OpenAI calls
3. **SQLite:** Single-file database (no concurrent writes)
4. **Single WA Number:** One WhatsApp account

### Scaling Options

**Vertical Scaling:**
- Increase `MAX_AI_CONCURRENT`
- Reduce `SEND_INTERVAL_MS` (carefully)
- Optimize database queries

**Horizontal Scaling:**
- Multiple WhatsApp instances (different numbers)
- PostgreSQL instead of SQLite
- Redis for distributed locking
- Message queue (RabbitMQ/Redis)

**Service Partitioning:**
- Separate scraper service
- Separate conversation service
- Multiple frontend instances with load balancer

---

## Monitoring & Observability

### Logging

**Python (Orchestrator):**
```python
from orchestrator.config import log
log.info("Processing university: %s", uni_name)
log.error("Failed to scrape IG: %s", error)
```

**Node.js (WhatsApp Service):**
```javascript
logger.info({ messageId }, 'Message sent successfully');
logger.error({ err }, 'Connection failed');
```

### Pipeline Logs

**Table:** `pipeline_logs`

**Fields:**
- `agent` - Agent name
- `status` - running/completed/failed
- `summary` - JSON summary
- `details` - JSON details (first 100)
- `items_processed` - Count
- `items_success` - Count
- `items_failed` - Count
- `started_at` - Timestamp
- `completed_at` - Timestamp

### API Logs

**Table:** `api_logs`

**Fields:**
- `endpoint` - API path
- `method` - HTTP method
- `request_body` - JSON
- `response_body` - JSON
- `status_code` - HTTP status
- `duration_ms` - Response time
- `created_at` - Timestamp

---

## Error Handling

### Retry Logic

**WhatsApp Messages:**
- Max retries: 3
- Delays: 2s, 5s, 10s (exponential backoff)
- Conditions: "not connected" errors

**Pipeline Agents:**
- Logged on failure
- Continue with next item
- Summary includes failure count

### Graceful Degradation

**IG Scraping Fallback:**
1. Primary: Instagram Web API
2. Fallback 1: Apify
3. Fallback 2: ScrapingBot

**AI Processing Fallback:**
- Agentic reply failed → Use legacy state machine
- Initial message failed → Use fixed template

---

## Configuration Management

### Dynamic Configuration

**ConfigManager Pattern:**
```python
# Thread-safe, runtime-updatable
from orchestrator.config import cfg

# Read
max_daily = cfg.MAX_DAILY_CONVERSATIONS

# Update (persists to DB)
await upsert_config("MAX_DAILY_CONVERSATIONS", "50")
cfg.MAX_DAILY_CONVERSATIONS = 50  # In-memory
```

**Database Table:** `config`

**Precedence:** DB value > .env value > registry default

### Key Configuration Groups

**Rate Limiting:**
- `MAX_DAILY_CONVERSATIONS`
- `MIN_MESSAGE_GAP_SECONDS`
- `MAX_IG_PROFILES_PER_DAY`
- `IG_REQUEST_DELAY_SECONDS`

**Outreach Hours:**
- `OUTREACH_START_HOUR`
- `OUTREACH_END_HOUR`

**AI Settings:**
- `AGENT_MODEL` - Model name (default: gpt-4o-mini)
- `AGENT_TEMPERATURE` - 0.0-1.0
- `AGENT_MAX_TOKENS` - Max output tokens
- `USE_AGENTIC_REPLIES` - Enable/disable AI replies
- `USE_AGENTIC_INITIAL` - Enable/disable AI initial messages
- `USE_AGENTIC_FOLLOWUPS` - Enable/disable AI follow-ups

**Feature Flags:**
- `CHATBOT_ENABLED` - Contact finder chatbot
- `LEARNING_ENABLED` - AI learning system
- `AUDIENSI_ENABLED` - Rector outreach pipeline

---

## File Structure

```
GetContactAIAgent/
├── orchestrator/              # Python FastAPI backend
│   ├── agents/               # Pipeline agents
│   ├── agent/                # Agentic AI system
│   ├── audiensi/             # Rector outreach
│   ├── main.py              # FastAPI app
│   ├── db.py                # Database schema
│   ├── conversation.py      # State machine
│   ├── message_queue.py     # Queue management
│   ├── scheduler.py         # APScheduler
│   ├── config.py            # Configuration
│   └── instagram.py         # IG scraping
│
├── whatsapp-service/         # Node.js WhatsApp bridge
│   ├── src/
│   │   └── index.ts        # Main server
│   ├── auth_store/         # Session credentials
│   ├── auth_store_backup/  # Credential backups
│   └── package.json
│
├── frontend/                 # React dashboard
│   ├── src/
│   │   ├── components/     # UI components
│   │   ├── pages/          # Page components
│   │   ├── hooks/          # Custom hooks
│   │   ├── context/        # React context
│   │   └── main.tsx        # App entry
│   └── package.json
│
├── data/                     # Database directory
│   └── getcontact.db       # SQLite database
│
├── docs/                     # Documentation
│   ├── architecture.md
│   ├── developer-guide.md
│   ├── deployment.md
│   ├── user-guide.md
│   └── api-reference.md
│
├── scripts/                  # Utility scripts
│   ├── setup_db.py
│   ├── collect_universities.py
│   └── export_results.py
│
├── .env.example             # Environment template
├── .gitignore
├── docker-compose.yml       # Docker orchestration
├── CLAUDE.md               # Project overview
└── README.md               # General README
```

---

## Summary

GetContact AI Agent implements a sophisticated multi-stage pipeline for automated WhatsApp outreach to Indonesian universities. The architecture balances:

- **Automation vs. Human-Like Behavior:** Carefully crafted delays and indicators
- **Concurrency vs. Rate Limits:** Semaphores and serial queues
- **Flexibility vs. Reliability:** Fallback mechanisms and retry logic
- **Simplicity vs. Scalability:** Single-instance design with scaling options

The system successfully integrates multiple AI capabilities (vision OCR, conversational AI) with web scraping and WhatsApp automation to achieve a complex business objective.
