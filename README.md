<div align="center">

# 🎓 GetContactAI Agent

### AI-Powered Outreach & Intelligence Platform for Indonesian Universities

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-20+-339933?style=flat&logo=node.js&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**Automated WhatsApp outreach with AI-driven conversations to collect university contact information, enriched with OSINT intelligence and CRM profiles.**

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [API Reference](#-api-reference) • [Deployment](#-deployment)

</div>

---

## 📖 Overview

**GetContactAI Agent** is an intelligent automation platform designed to streamline outreach to Indonesian universities through multiple channels:

1. **WhatsApp Outreach** - AI-powered conversational outreach to collect contact information
2. **OSINT Pipeline** - Automated intelligence gathering about universities and key personnel
3. **CRM System** - Detailed profiling of Point of Contact (PIC) individuals
4. **Audiensi Scheduling** - Zoom meeting scheduling with university leadership
5. **DMS Integration** - Daily Management System for research and scheduling workflows

### What It Does

| Pipeline | Description |
|----------|-------------|
| **Contact Collection** | Discovers universities → Finds IG → Extracts phones → WhatsApp outreach |
| **OSINT Enrichment** | Web profiling → Social intelligence → Key people → News scanning |
| **CRM Profiling** | Identity resolution → Academic background → Social profiles → Personal interests |
| **Audiensi** | Meeting scheduling → PDF invitations → Zoom link generation |
| **Blast Campaigns** | Bulk messaging with templates and recipient management |

---

## ✨ Features

### 🤖 AI-Powered Pipeline

- **GPT-4o Vision** - Phone number extraction from Instagram post images
- **GPT-4o-mini** - Intelligent conversation management and reply analysis
- **LangGraph Orchestration** - Multi-agent workflows for OSINT and CRM pipelines
- **Dynamic Message Generation** - Context-aware personalized messages

### 💬 Human-Like WhatsApp Behavior

- **Typing indicators** and **read receipts** for natural conversation feel
- **Configurable delays** between messages
- **Multi-device support** via DeviceManager
- **Message queuing** with rate limiting

### 🔍 OSINT Intelligence Pipeline

- **Web Profiler** - Extracts address, contact info, org structure
- **Social Intel** - Discovers official social media accounts
- **Key People Finder** - Identifies rectors, secretaries, BEM contacts
- **News Scanner** - Monitors recent news and events
- **Contact Enricher** - Aggregates contacts from multiple sources

### 👤 CRM Profiling System

- **Identity Resolver** - PDDIKTI-based identity verification
- **Academic Profiler** - Education history, publications, research topics
- **Social Profiler** - LinkedIn, Instagram, Facebook presence
- **Personal Interest Agent** - Hobbies, personality traits (best-effort)
- **Family Info Agent** - Marital status, family details (best-effort)
- **Profile Compiler** - Aggregates all data into unified profile

### 📅 Audiensi (Meeting) System

- **Automated Zoom scheduling** with university rectors
- **PDF invitation generation** with university branding
- **Template management** for personalized outreach
- **State tracking** through the scheduling funnel

### 📊 Real-Time Dashboard

- **Live conversation monitoring** with WebSocket updates
- **Pipeline funnel visualization**
- **Stats cards** - universities contacted, success rates, etc.
- **Export capabilities** - CSV/Excel download

### ⚙️ Advanced Configuration

- **Dynamic config** via database (no restart needed)
- **Respectful outreach hours** (WIB timezone)
- **Daily quota limits** to prevent spam
- **Per-university enable/disable** controls

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (React + Vite)                         │
│                             localhost:5173                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │  Dashboard  │  │ Universities │  │ Conversations│  │ Audiensi   │      │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │  OSINT      │  │    CRM      │  │    DMS      │  │   Blast    │      │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ HTTP + WebSocket
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Orchestrator (FastAPI)                              │
│                           localhost:8000                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         API Endpoints                                │   │
│  │  /universities  /pipeline  /conversations  /audiensi  /osint       │   │
│  │  /crm  /dms  /blast  /config  /learning  /wa  /ig-accounts       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │   Agent Layer    │  │   Scheduler      │  │   State Machines     │   │
│  │  • IG Finders    │  │  • APScheduler   │  │  • Conversations    │   │
│  │  • Post Scraper  │  │  • Daily loops   │  │  • Audiensi States   │   │
│  │  • Phone Extract │  │  • Follow-ups     │  │                      │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐       │
│  │  OSINT Pipeline  │  │  CRM Pipeline   │  │   Message Queue     │       │
│  │  (LangGraph)     │  │  (LangGraph)    │  │   + Semaphore       │       │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘       │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ HTTP / Webhook
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     WhatsApp Service (Node.js)                             │
│                           localhost:3100                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              @whiskeysockets/baileys                                 │   │
│  │  • QR Code Auth  • Multi-device  • Message Queue  • Rate Limiter   │   │
│  │  • Typing Indicators  • Read Receipts  • Media Handling           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
                              📱 WhatsApp
```

### Data Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PDDIKTI   │────▶│  Universities │────▶│   Agents    │────▶│ WhatsApp   │
│   (Source)  │     │     DB       │     │  (Pipeline) │     │  Outreach  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                            │                    │
                                            ▼                    ▼
                                     ┌─────────────┐     ┌─────────────┐
                                     │    OSINT    │     │   Audiensi  │
                                     │  Enrichment │     │  Scheduling │
                                     └─────────────┘     └─────────────┘
                                            │
                                            ▼
                                     ┌─────────────┐
                                     │     CRM     │
                                     │  Profiling  │
                                     └─────────────┘
```

---

## 🛠️ Tech Stack

### Backend (Orchestrator)

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | FastAPI | High-performance async API |
| **Database** | SQLite (aiosqlite) | Persistent storage |
| **AI/ML** | OpenAI GPT-4o, GPT-4o-mini | Vision OCR & Chat |
| **Orchestration** | LangGraph | OSINT & CRM pipelines |
| **Scheduler** | APScheduler | Daily jobs & follow-ups |
| **HTTP Client** | httpx | Async HTTP requests |
| **Web Scraping** | Serper.dev, Playwright | Search & IG scraping |

### WhatsApp Service

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Runtime** | Node.js 20+ | JavaScript runtime |
| **Framework** | Express.js | HTTP server |
| **WhatsApp** | @whiskeysockets/baileys | WA protocol implementation |
| **Logging** | pino | Structured logging |
| **Metrics** | prom-client | Observability |

### Frontend

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | React 18 + Vite | UI framework |
| **Routing** | React Router 6 | SPA navigation |
| **State** | TanStack React Query 5 | Server state management |
| **Styling** | Tailwind CSS 3 | Utility-first CSS |
| **Icons** | Lucide React | Icon library |
| **Real-time** | WebSocket | Live updates |

---

## 📋 Prerequisites

### Required Software

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **Node.js 20+** - [Download](https://nodejs.org/)
- **Git** - [Download](https://git-scm.com/downloads)

### Required API Keys

| Service | Purpose | Get It |
|---------|---------|--------|
| **OpenAI API Key** | GPT-4o Vision & Chat | [openai.com](https://openai.com/) |
| **Serper API Key** | Google Search results | [serper.dev](https://serper.dev/) |

### Optional API Keys

| Service | Purpose |
|---------|---------|
| **Instagram Credentials** | Direct IG scraping via Playwright |
| **Apify API Key** | Alternative IG data extraction |
| **Google Sheets API** | Data export to Sheets |

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
# Clone repository
git clone https://github.com/your-org/GetContactAI.git
cd GetContactAI

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies
cd whatsapp-service && npm install && cd ..
cd frontend && npm install && cd ..
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your API keys
# Required: OPENAI_API_KEY, SERPER_API_KEY
```

### 3. Initialize Database

```bash
python scripts/setup_db.py
```

### 4. Start Services

```bash
# Terminal 1: WhatsApp Service
cd whatsapp-service && npm run dev

# Terminal 2: Orchestrator
uvicorn orchestrator.main:app --port 8000 --reload

# Terminal 3: Frontend
cd frontend && npm run dev
```

### 5. Access Application

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:5173 |
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **API Docs (ReDoc)** | http://localhost:8000/redoc |
| **Health Check** | http://localhost:8000/health |

---

## ⚙️ Configuration

### Environment Variables

```bash
# ═══════════════════════════════════════════════════════
# REQUIRED
# ═══════════════════════════════════════════════════════
OPENAI_API_KEY=sk-...              # OpenAI API key
SERPER_API_KEY=...                 # Serper.dev API key

# ═══════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════
DATABASE_PATH=data/getcontact.db    # SQLite path

# ═══════════════════════════════════════════════════════
# WHATSAPP SERVICE
# ═══════════════════════════════════════════════════════
WA_SERVICE_URL=http://localhost:3100
WEBHOOK_URL=http://localhost:8000/webhook/incoming

# ═══════════════════════════════════════════════════════
# OUTREACH SETTINGS (WIB = UTC+7)
# ═══════════════════════════════════════════════════════
OUTREACH_START_HOUR=7
OUTREACH_END_HOUR=22
MAX_DAILY_CONVERSATIONS=50
MIN_MESSAGE_GAP_SECONDS=30

# ═══════════════════════════════════════════════════════
# AI SETTINGS
# ═══════════════════════════════════════════════════════
AGENT_MODEL=gpt-4o-mini
VISION_MODEL=gpt-4o-mini

# ═══════════════════════════════════════════════════════
# OPTIONAL
# ═══════════════════════════════════════════════════════
IG_USERNAME=...                    # Instagram credentials
IG_PASSWORD=...
APIFY_API_KEY=...
```

### Dynamic Configuration

Many settings can be adjusted via the **Settings** page** or API:

```bash
# Get all config
GET /config

# Update config
PATCH /config
{
  "key": "MAX_DAILY_CONVERSATIONS",
  "value": "100"
}
```

---

## 📖 Usage Guide

### 1. Collect Universities

Navigate to **Dashboard** → Click **"Collect Universities"**

The system will fetch university data from PDDIKTI based on selected provinces.

### 2. Run Contact Pipeline

Go to **Pipeline** page and run agents in sequence:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Find IG Handles │───▶│  Scrape IG Posts │───▶│  Extract Phones  │
│  (Serper + IG)  │    │  (Playwright)   │    │  (GPT-4o Vision) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 3. Start WhatsApp Outreach

1. **Connect WhatsApp** - Scan QR code from WhatsApp page
2. **Enable Chatbot** - Turn on contact finder chatbot
3. **Start Outreach** - Click "Start Outreach" or wait for scheduled run
4. **Monitor** - Watch conversations in real-time

### 4. Run OSINT Enrichment

Go to **University Detail** → Click **"Run OSINT"**

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ Web Profiler │──▶│ Social Intel │──▶│  Key People  │──▶│ News Scanner │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
        │                                                    │
        └─────────────────▶ Contact Enricher ◀──────────────┘
                                   │
                                   ▼
                            Reviewer Agent
                                   │
                                   ▼
                          OSINT Profile Stored
```

### 5. CRM Profiling

Go to **CRM** → Create new profile request

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Identity   │──▶│   Academic    │──▶│    Social    │
│   Resolver   │   │   Profiler   │   │   Profiler   │
└──────────────┘   └──────────────┘   └──────────────┘
        │                │                   │
        └────────────────┴───────────────────┘
                         │
                         ▼
                ┌──────────────┐   ┌──────────────┐
                │   Personal   │   │    Family    │
                │   Interest   │   │    Info      │
                └──────────────┘   └──────────────┘
                         │
                         ▼
                Profile Compiler
                         │
                         ▼
                   Unified Profile
```

### 6. Schedule Audiensi

1. Navigate to **Audiensi** page
2. Select approved conversation
3. Generate PDF invitation
4. Send to rector via WhatsApp
5. Schedule Zoom meeting

---

## 📂 Project Structure

```
GetContactAI/
├── orchestrator/                    # Python FastAPI backend
│   ├── main.py                      # FastAPI app & endpoints
│   ├── config.py                    # Configuration & logging
│   ├── db.py                        # Database schema & queries
│   ├── conversation.py              # WhatsApp state machine
│   ├── message_queue.py             # AI semaphore + WA queue
│   ├── scheduler.py                # APScheduler jobs
│   │
│   ├── agents/                      # Contact discovery agents
│   │   ├── ig_handle_finder.py      # Find IG from website
│   │   ├── ig_post_scraper.py       # Scrape IG posts
│   │   ├── ig_phone_extractor.py   # Vision OCR extraction
│   │   ├── bem_finder.py            # Find BEM contacts
│   │   └── rector_finder.py        # Find rector contacts
│   │
│   ├── osint/                       # OSINT pipeline (LangGraph)
│   │   ├── state.py                 # State definitions
│   │   ├── graph.py                 # LangGraph workflow
│   │   ├── web_profiler.py          # University web profiling
│   │   ├── social_intel.py          # Social media discovery
│   │   ├── key_people.py           # Key personnel finder
│   │   ├── news_scanner.py          # News monitoring
│   │   ├── contact_enricher.py     # Contact aggregation
│   │   └── reviewer.py             # Quality review agent
│   │
│   ├── crm/                         # CRM pipeline (LangGraph)
│   │   ├── state.py                 # State definitions
│   │   ├── graph.py                 # LangGraph workflow
│   │   ├── identity_resolver.py    # PDDIKTI identity lookup
│   │   ├── academic_profiler.py    # Academic background
│   │   ├── social_profiler.py      # Social media profiles
│   │   ├── personal_interest.py    # Personal interests
│   │   ├── family_info.py          # Family details
│   │   └── profile_compiler.py     # Profile aggregation
│   │
│   ├── audiensi/                    # Audiensi scheduling
│   │   ├── conversation.py          # Audiensi state machine
│   │   ├── pdf_generator.py        # PDF invitation generator
│   │   └── auto_queue.py           # Auto-queue management
│   │
│   ├── agent/                       # Core AI agent system
│   │   ├── react_agent.py          # ReAct agent
│   │   ├── learning.py             # Learning system
│   │   ├── situation_detector.py   # Reply classification
│   │   └── prompts.py              # AI prompts
│   │
│   └── research_agents/             # Research & DMS agents
│       ├── gemini_caller.py        # Gemini API caller
│       └── graph.py                # Research workflow
│
├── whatsapp-service/               # Node.js WhatsApp bridge
│   ├── src/
│   │   ├── index.ts               # Express server & handlers
│   │   ├── deviceManager.ts      # Multi-device management
│   │   ├── messageQueue.ts       # Message queue & rate limit
│   │   ├── rateLimiter.ts        # Rate limiting
│   │   └── metrics.ts            # Prometheus metrics
│   └── package.json
│
├── frontend/                      # React dashboard
│   ├── src/
│   │   ├── components/           # Reusable UI components
│   │   │   ├── ui/              # Base components (Button, Card, etc.)
│   │   │   ├── layout/          # AppShell, Sidebar, TopBar
│   │   │   ├── dashboard/       # Dashboard widgets
│   │   │   ├── universities/    # University management
│   │   │   ├── conversations/   # Chat components
│   │   │   ├── audiensi/        # Audiensi components
│   │   │   ├── dms/             # DMS components
│   │   │   └── ...
│   │   ├── pages/               # Page components
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── UniversitiesPage.tsx
│   │   │   ├── PipelinePage.tsx
│   │   │   ├── ConversationsPage.tsx
│   │   │   ├── AudiensiQueuePage.tsx
│   │   │   ├── DmsSchedulesPage.tsx
│   │   │   └── ...
│   │   ├── api/                 # API client layer
│   │   ├── context/             # React contexts
│   │   └── App.tsx             # Router setup
│   └── package.json
│
├── scripts/                       # Utility scripts
│   ├── setup_db.py              # Database initialization
│   ├── collect_universities.py  # PDDIKTI scraper
│   └── ...
│
├── data/                         # Runtime data (gitignored)
│   ├── getcontact.db           # SQLite database
│   ├── audiensi_docs/          # Generated PDFs
│   ├── templates/              # Email templates
│   └── pw_sessions/           # Playwright sessions
│
├── docker-compose.yml           # Docker orchestration
├── Dockerfile.orchestrator     # Orchestrator image
├── Dockerfile.whatsapp         # WhatsApp service image
├── Dockerfile.frontend         # Frontend image
└── README.md                   # This file
```

---

## 📚 Database Schema

### Core Tables

| Table | Description |
|-------|-------------|
| `universities` | University records from PDDIKTI |
| `ig_contacts` | Extracted phone numbers from IG |
| `ig_posts` | Scraped Instagram posts |
| `conversations` | WhatsApp conversation state |
| `audiensi_conversations` | Audiensi scheduling state |
| `daily_quota` | Daily outreach limits |

### OSINT Tables

| Table | Description |
|-------|-------------|
| `osint_profiles` | OSINT enrichment results |
| `osint_contacts` | Aggregated contacts |
| `osint_social_media` | Social media accounts |
| `osint_news` | News items |
| `osint_runs` | Run history |

### CRM Tables

| Table | Description |
|-------|-------------|
| `crm_requests` | Profile requests |
| `crm_pic_profiles` | PIC profiles |
| `crm_profile_runs` | Run history |
| `crm_profile_sources` | Data sources |

### Other Tables

| Table | Description |
|-------|-------------|
| `blast_campaigns` | Bulk messaging campaigns |
| `blast_recipients` | Campaign recipients |
| `knowledge_items` | Chatbot knowledge base |
| `config` | Dynamic configuration |
| `api_call_logs` | API usage logs |
| `pipeline_logs` | Pipeline execution logs |

---

## 🔌 API Reference

### Core Endpoints

```http
# Health Check
GET /health

# Dashboard
GET /dashboard

# Universities
GET    /universities
POST   /universities
GET    /universities/{id}
PATCH  /universities/{id}/toggle-enabled
GET    /universities/export-excel

# Pipeline
POST /pipeline/find-ig-handles
POST /pipeline/scrape-ig-posts
POST /pipeline/extract-phones
POST /pipeline/discover-bem
POST /pipeline/find-rectors

# Conversations
GET  /conversations
GET  /conversations/{id}
POST /conversations/test

# Audiensi
GET  /audiensi
GET  /audiensi/queue
POST /audiensi/{id}/approve
POST /audiensi/{id}/send-zoom

# OSINT
POST /osint/run/{university_id}
POST /osint/run-batch
GET  /osint/profile/{university_id}

# CRM
POST   /crm/requests
GET    /crm/requests
POST   /crm/requests/{id}/run
GET    /crm/profiles/{id}

# DMS
GET /dms/schedules
GET /dms/schedules/today
POST /dms/sync/contacts
POST /dms/research/run-tomorrow

# Blast
POST /blast/campaigns
GET  /blast/campaigns/{id}
POST /blast/campaigns/{id}/start

# Control
POST /control/pause
POST /control/resume
GET  /control/status

# WhatsApp
GET /wa/qr
GET /wa/status
POST /wa/bulk-send

# Config
GET /config
PATCH /config

# Learning
GET /learning/lessons
GET /learning/analyses
```

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🗺️ Conversation States

### Contact Outreach

```
PENDING
    │
    ▼
INITIAL_SENT
    │
    ▼
WAITING_REPLY
    │
    ├───────────▶ GOT_NUMBER      ✅ Success
    ├───────────▶ REFUSED         ❌ Contact refused
    ├───────────▶ NEED_MORE       🔄 Need follow-up
    ├───────────▶ NO_REPLY       ⏰ No response
    ├───────────▶ ABANDONED      ⏹️ Max attempts reached
    └───────────▶ UNDELIVERED    📵 Message failed
```

### Audiensi Flow

```
QUEUED
    │
    ▼
MESSAGE_SENT
    │
    ▼
WAITING_REPLY
    │
    ├───────────▶ APPROVED       ✅ Rector agreed
    ├───────────▶ REFUSED        ❌ Rector declined
    └───────────▶ ZOOM_SENT      📅 Zoom link sent
```

---

## 🐳 Deployment

### Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Manual Deployment

```bash
# Build images
docker build -f Dockerfile.orchestrator -t getcontact-orchestrator .
docker build -f Dockerfile.whatsapp -t getcontact-whatsapp .
docker build -f Dockerfile.frontend -t getcontact-frontend .

# Run containers
docker run -p 8000:8000 --env-file .env getcontact-orchestrator
docker run -p 3100:3100 getcontact-whatsapp
docker run -p 5173:5173 getcontact-frontend
```

### Production Environment Variables

See `.env.production.example` for production-ready configuration.

---

## 🔧 Development

### Running Tests

```bash
# Python (pytest)
pytest orchestrator/tests/

# Node.js
npm test --prefix whatsapp-service
```

### Code Style

- **Python**: Follow PEP 8, use `black` formatter
- **TypeScript**: Strict mode enabled
- **React**: Functional components with hooks

### Adding New Agents

1. Create agent file in `orchestrator/agents/`
2. Define state in `orchestrator/osint/state.py` or `orchestrator/crm/state.py`
3. Add to LangGraph workflow
4. Register endpoint in `orchestrator/main.py`

---

## 📊 Monitoring

### Health Checks

```bash
# Orchestrator
curl http://localhost:8000/health

# WhatsApp Service
curl http://localhost:3100/health

# Database
sqlite3 data/getcontact.db "SELECT COUNT(*) FROM universities;"
```

### Logs

```bash
# Orchestrator logs
tail -f logs/orchestrator.log

# WhatsApp service logs
docker logs getcontact-whatsapp
```

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Follow code style guidelines
4. Add tests for new features
5. Update documentation
6. Submit a pull request

---

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **OpenAI** - GPT-4o and GPT-4o-mini APIs
- **Baileys** - WhatsApp library
- **FastAPI** - Python web framework
- **PDDIKTI** - Indonesian higher education database
- **LangChain** - LangGraph orchestration

---

## 📧 Support

- **Issues**: Open an issue on GitHub
- **Discussions**: Use GitHub Discussions
- **Email**: [your-email@example.com]

---

<div align="center">

**Built with ❤️ for Indonesian Universities**

[⬆ Back to Top](#-getcontactai-agent)

</div>
