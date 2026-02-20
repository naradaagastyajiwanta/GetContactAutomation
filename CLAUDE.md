# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GetContact AI Agent is a multi-service application that automates WhatsApp outreach to Indonesian universities to collect contact information. It scrapes Instagram for phone numbers, then conducts AI-driven WhatsApp conversations to obtain secretariat contacts.

## Architecture

Three independent services communicate via HTTP/webhooks:

1. **Orchestrator** (`orchestrator/`, Python FastAPI, port 8000) — Core business logic: pipeline agents, conversation state machine, scheduling, database
2. **WhatsApp Service** (`whatsapp-service/`, Node.js/TypeScript, port 3100) — Baileys-based WhatsApp bridge with human-like behavior (typing indicators, delays, read receipts)
3. **Frontend** (`frontend/`, React + Vite, port 5173) — Dashboard for monitoring and controlling the system

**Data flow pipeline:**
PDDIKTI university scraping → Agent 1 (find IG handles) → Agent 2 (scrape IG posts) → Agent 3 (extract phones via GPT-4o vision OCR) → WhatsApp outreach via conversation state machine → Follow-ups

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
npm run preview      # Preview production build
```

### Utility Scripts
```bash
python scripts/setup_db.py            # Initialize SQLite database
python scripts/collect_universities.py # Scrape universities from PDDIKTI
python scripts/export_results.py       # Export collected data
```

## Key Orchestrator Modules

- `main.py` — FastAPI app with lifespan management, REST endpoints, webhook handler
- `config.py` — Environment variables via python-dotenv, logging setup
- `db.py` — SQLite schema (auto-created), async queries via aiosqlite
- `conversation.py` — Conversation state machine (PENDING → INITIAL_SENT → WAITING_REPLY → REPLIED → ANALYZING → GOT_NUMBER etc.) + OpenAI GPT-4o-mini integration
- `message_queue.py` — AI concurrency semaphore (default 3) + serial WA message queue (configurable interval)
- `scheduler.py` — APScheduler for daily outreach loops and follow-ups
- `instagram.py` — IG scraping and phone number extraction
- `agents/ig_handle_finder.py` — Agent 1: website → IG Web → Serper Google search
- `agents/ig_post_scraper.py` — Agent 2: scrape recent IG posts
- `agents/ig_phone_extractor.py` — Agent 3: GPT-4o vision OCR on post images

## Database

SQLite at `data/getcontact.db` (path configurable via `DATABASE_PATH` env var). Schema auto-creates on startup via `db.py`. Key tables: `universities`, `ig_contacts`, `ig_posts`, `conversations`, `daily_quota`. Message history stored as JSON strings in the `conversations` table.

## Environment

Copy `.env.example` to `.env`. Required keys: `OPENAI_API_KEY`, `SERPER_API_KEY`. Optional: `IG_USERNAME`/`IG_PASSWORD`, `APIFY_API_KEY`. Rate limiting and outreach hours are configurable (WIB timezone = UTC+7).

## Tech Stack Details

- **Python:** FastAPI, aiosqlite, openai (GPT-4o for vision, GPT-4o-mini for chat), apscheduler, httpx, phonenumbers, pddiktipy
- **WhatsApp Service:** @whiskeysockets/baileys, Express, TypeScript strict mode, pino logger
- **Frontend:** React 18, React Router 6, TanStack React Query 5, Tailwind CSS 3, Lucide icons, axios
