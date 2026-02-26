# Developer Guide - GetContact AI Agent

**Version:** 1.0.0
**Last Updated:** 2025-02-25

---

## Table of Contents

1. [Local Development Setup](#local-development-setup)
2. [Project Structure](#project-structure)
3. [Coding Standards](#coding-standards)
4. [Development Workflows](#development-workflows)
5. [Testing Guidelines](#testing-guidelines)
6. [Debugging](#debugging)
7. [Common Tasks](#common-tasks)
8. [Troubleshooting](#troubleshooting)
9. [Contributing](#contributing)

---

## Local Development Setup

### Prerequisites

**Required Software:**
- Python 3.10+
- Node.js 18+
- Git
- SQLite3 (usually bundled with Python)

**Required Accounts:**
- OpenAI API account (for GPT-4o and GPT-4o-mini)
- Serper.dev account (free tier: 2500 queries/month)
- WhatsApp account (dedicated recommended)

**Optional Services:**
- Apify account (backup IG scraping)
- Google account (for Sheets export)

### Installation Steps

#### 1. Clone Repository

```bash
git clone <repository-url>
cd GetContactAIAgent
```

#### 2. Orchestrator Setup (Python)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create data directory
mkdir -p data
```

#### 3. WhatsApp Service Setup (Node.js)

```bash
cd whatsapp-service

# Install dependencies
npm install

# Build TypeScript (optional for dev)
npm run build

cd ..
```

#### 4. Frontend Setup (React)

```bash
cd frontend

# Install dependencies
npm install

cd ..
```

#### 5. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your API keys
# Required:
# - OPENAI_API_KEY=sk-...
# - SERPER_API_KEY=...
# Optional:
# - IG_USERNAME=your_ig_username
# - IG_PASSWORD=your_ig_password
# - APIFY_API_KEY=...
```

#### 6. Initialize Database

```bash
# Database auto-creates on first run, or run:
python scripts/setup_db.py
```

### Starting Services

#### Development Mode (3 Terminals)

**Terminal 1 - Orchestrator:**
```bash
# Activate virtual environment
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Start FastAPI with auto-reload
uvicorn orchestrator.main:app --port 8000 --reload
```

**Terminal 2 - WhatsApp Service:**
```bash
cd whatsapp-service
npm run dev
```

**Terminal 3 - Frontend:**
```bash
cd frontend
npm run dev
```

#### Verify Services

1. **Orchestrator:** http://localhost:8000
   - API docs: http://localhost:8000/docs
   - Health check: `curl http://localhost:8000/`

2. **WhatsApp Service:** http://localhost:3100
   - Status: `curl http://localhost:3100/status`

3. **Frontend:** http://localhost:5173

---

## Project Structure

### Orchestrator (Python)

```
orchestrator/
├── main.py                    # FastAPI app, routes, lifespan
├── config.py                  # Environment, ConfigManager, logging
├── db.py                      # Database schema, queries
├── conversation.py            # State machine, OpenAI integration
├── message_queue.py           # AI semaphore, WA queue
├── scheduler.py               # APScheduler setup, jobs
├── instagram.py               # IG scraping logic
├── apify_client.py           # Apify client wrapper
├── scrapingbot_client.py     # ScrapingBot client wrapper
├── config_registry.py        # Dynamic config definitions
│
├── agents/                    # Pipeline agents
│   ├── __init__.py
│   ├── ig_handle_finder.py   # Agent 1: Find IG handles
│   ├── ig_post_scraper.py    # Agent 2: Scrape IG posts
│   ├── ig_phone_extractor.py # Agent 3: Extract phones
│   ├── bem_finder.py         # Agent 4: Find BEM accounts
│   └── rector_finder.py      # Agent: Find rector contacts
│
├── agent/                     # Agentic AI system
│   ├── react_agent.py        # Main ReAct agent
│   ├── tools.py              # Tool definitions
│   ├── prompts.py            # System prompts
│   └── learning.py           # Learning system
│
└── audiensi/                  # Rector outreach pipeline
    ├── react_agent.py        # Audiensi-specific agent
    └── states.py             # Audiensi state definitions
```

**Key Modules Explained:**

**`main.py`** - FastAPI application
- Lifespan management (startup/shutdown)
- REST API endpoints
- Webhook handler for incoming WhatsApp messages
- CORS middleware

**`db.py`** - Database layer
- Schema DDL (auto-executed on startup)
- Async query functions (aiosqlite)
- CRUD operations for all tables
- Transaction support

**`conversation.py`** - Conversation logic
- `ConvState` enum (state definitions)
- `ConversationManager` class
- OpenAI integration (GPT-4o-mini)
- Message generation (initial, follow-up)
- Reply analysis

**`scheduler.py`** - Background jobs
- APScheduler configuration
- Outreach loop (every 30 min)
- Follow-up processing (every hour)
- Agent batch jobs (threaded)
- Learning reflection (3x daily)

**`message_queue.py`** - Queue management
- AI concurrency semaphore (max 3 parallel)
- WhatsApp send queue (serial)
- Retry logic with exponential backoff
- Document sending support

### WhatsApp Service (Node.js/TypeScript)

```
whatsapp-service/
├── src/
│   └── index.ts              # Main server
├── auth_store/               # Session credentials (gitignored)
├── auth_store_backup/        # Credential backups (gitignored)
├── dist/                     # Compiled JavaScript
├── package.json
└── tsconfig.json
```

**Key Features in `index.ts`:**

- **Connection Management:** Auto-reconnect with backoff
- **QR Code Generation:** For WhatsApp pairing
- **Message Debouncing:** Combine rapid messages (5s window)
- **Human-Like Behavior:** Typing indicators, delays
- **Credential Backup:** Automatic backup/restore
- **LID Resolution:** Handle encrypted phone numbers

### Frontend (React/TypeScript)

```
frontend/
├── src/
│   ├── main.tsx              # App entry
│   ├── App.tsx               # Router setup
│   ├── pages/                # Page components
│   │   ├── DashboardPage.tsx
│   │   ├── UniversitiesPage.tsx
│   │   ├── UniversityDetailPage.tsx
│   │   ├── PipelinePage.tsx
│   │   ├── ConversationsPage.tsx
│   │   ├── ConversationDetailPage.tsx
│   │   ├── LearningPage.tsx
│   │   ├── WhatsAppPage.tsx
│   │   ├── AudiensiQueuePage.tsx
│   │   ├── AudiensiDetailPage.tsx
│   │   ├── KnowledgeBasePage.tsx
│   │   ├── ApiLogsPage.tsx
│   │   └── SettingsPage.tsx
│   ├── components/           # Reusable components
│   │   ├── ui/              # UI components (Button, Card, etc.)
│   │   ├── layout/          # Layout (Sidebar, TopBar, etc.)
│   │   ├── dashboard/       # Dashboard-specific
│   │   ├── universities/    # University-specific
│   │   ├── conversations/   # Conversation-specific
│   │   ├── pipeline/        # Pipeline-specific
│   │   └── settings/        # Settings-specific
│   ├── hooks/               # Custom React hooks
│   │   └── useUniversities.ts
│   ├── context/             # React context providers
│   │   ├── ThemeContext.tsx
│   │   └── ToastContext.tsx
│   └── lib/                 # Utilities
│       └── api.ts           # API client
├── public/                  # Static assets
├── index.html
├── package.json
├── vite.config.ts
└── tailwind.config.js
```

---

## Coding Standards

### Python (Orchestrator)

**Style Guide:** PEP 8

**Code Formatting:**
```python
# Use type hints
async def process_message(phone: str, message: str) -> dict:
    """Process incoming WhatsApp message."""
    result = await analyze_message(message)
    return result

# Use f-strings for formatting
log.info(f"Processing {phone}: {message}")

# Use context managers
async with aiosqlite.connect(DATABASE_PATH) as db:
    await db.execute("INSERT INTO ...")
```

**Error Handling:**
```python
# Always log exceptions
try:
    result = await risky_operation()
except Exception as e:
    log.error("Operation failed: %s", e, exc_info=True)
    raise

# Use specific exceptions
raise ValueError("Invalid phone number")
```

**Async/Await:**
```python
# Use async/await consistently
async def process_batch():
    tasks = [process_item(item) for item in items]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

**Imports:**
```python
# Standard library first
import asyncio
from datetime import datetime

# Third-party second
from fastapi import FastAPI
from openai import AsyncOpenAI

# Local imports last
from orchestrator.config import log, cfg
from orchestrator.db import get_university_by_id
```

### TypeScript (WhatsApp Service & Frontend)

**Style:** ESLint + Prettier (if configured)

**Code Formatting:**
```typescript
// Use interfaces for types
interface Message {
  to: string;
  message: string;
  replyToMsgKey?: MsgKey;
}

// Use async/await
async function sendMessage(msg: Message): Promise<void> {
  await sock.sendMessage(jid, { text: msg.message });
}

// Use const/let, never var
const result = await fetchData();
let count = 0;
```

**Error Handling:**
```typescript
// Try-catch with logging
try {
  await sock.sendMessage(jid, { text: message });
} catch (err) {
  logger.error({ err }, 'Failed to send message');
}
```

**React Best Practices:**
```typescript
// Use functional components with hooks
function UniversitiesPage() {
  const [universities, setUniversities] = useState<University[]>([]);
  const { data, isLoading, error } = useUniversities();

  useEffect(() => {
    document.title = 'Universities - GetContact';
  }, []);

  if (isLoading) return <Spinner />;
  if (error) return <ErrorMessage error={error} />;

  return <UniversityTable universities={universities} />;
}

// Custom hooks for data fetching
function useUniversities() {
  return useQuery({
    queryKey: ['universities'],
    queryFn: async () => {
      const { data } = await axios.get('/api/v1/universities');
      return data;
    }
  });
}
```

---

## Development Workflows

### Adding a New API Endpoint

**1. Define Route (Orchestrator):**

```python
# In orchestrator/main.py

from fastapi import HTTPException
from pydantic import BaseModel

class UniversityCreate(BaseModel):
    name: str
    province: str | None = None
    website: str | None = None

@app.post("/api/v1/universities")
async def create_university(uni: UniversityCreate):
    """Create a new university."""
    try:
        uni_id = await add_university(
            name=uni.name,
            province=uni.province,
            website=uni.website
        )
        return {"id": uni_id, "name": uni.name}
    except Exception as e:
        log.error("Failed to create university: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
```

**2. Add Database Function (if needed):**

```python
# In orchestrator/db.py

async def add_university(name: str, province: str = None, website: str = None) -> int:
    """Add a new university and return its ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO universities (name, province, website) VALUES (?, ?, ?)",
            (name, province, website)
        )
        await db.commit()
        return cursor.lastrowid
```

**3. Add Frontend Integration:**

```typescript
// In frontend/src/lib/api.ts

export async function createUniversity(data: UniversityCreate): Promise<University> {
  const response = await axios.post('/api/v1/universities', data);
  return response.data;
}

// In component
const handleSubmit = async (data: UniversityCreate) => {
  try {
    const uni = await createUniversity(data);
    toast.success('University created');
    queryClient.invalidateQueries(['universities']);
  } catch (error) {
    toast.error('Failed to create university');
  }
};
```

### Adding a New Pipeline Agent

**1. Create Agent Module:**

```python
# orchestrator/agents/new_agent.py

import asyncio
from orchestrator.config import log, cfg

async def process_university(uni: dict) -> dict | None:
    """Process a single university."""
    log.info("Processing %s", uni["name"])
    # Your logic here
    return {"university": uni["name"], "result": "success"}

async def run_new_agent_batch(limit: int = 50) -> dict:
    """Run agent batch job."""
    from orchestrator.db import get_universities_by_status

    universities = await get_universities_by_status("pending", limit=limit)
    results = []

    for uni in universities:
        try:
            result = await process_university(uni)
            if result:
                results.append(result)
            await asyncio.sleep(cfg.IG_REQUEST_DELAY_SECONDS)
        except Exception as e:
            log.error("Error processing %s: %s", uni["name"], e)

    return {"processed": len(universities), "success": len(results), "details": results}
```

**2. Add Scheduler Job:**

```python
# In orchestrator/scheduler.py

async def _threaded_new_agent():
    """Run new agent in thread pool."""
    from orchestrator.agents.new_agent import run_new_agent_batch
    return await run_agent_in_thread(run_new_agent_batch)

def setup_scheduler():
    # ... existing jobs ...

    scheduler.add_job(
        _threaded_new_agent,
        "cron",
        hour="8-20/2",  # Every 2 hours
        minute="0",
        timezone=WIB,
        id="new_agent",
        replace_existing=True,
        max_instances=1,
    )
```

**3. Add API Endpoint:**

```python
# In orchestrator/main.py

@app.post("/api/v1/pipelines/new-agent")
async def trigger_new_agent(background_tasks: BackgroundTasks):
    """Manually trigger new agent."""
    from orchestrator.agents.new_agent import run_new_agent_batch

    background_tasks.add_task(run_new_agent_batch)
    return {"status": "started"}
```

**4. Add Frontend Trigger:**

```typescript
// In frontend/src/pages/PipelinePage.tsx

const triggerNewAgent = async () => {
  await axios.post('/api/v1/pipelines/new-agent');
  toast.success('New agent started');
};

// In JSX
<Button onClick={triggerNewAgent}>Run New Agent</Button>
```

### Database Migration

**1. Modify Schema:**

```python
# In orchestrator/db.py

_DDL = """
-- Existing tables...

CREATE TABLE IF NOT EXISTS new_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
```

**2. Add Migration Script (optional):**

```python
# scripts/migrate_add_new_table.py

import asyncio
import aiosqlite
from orchestrator.config import DATABASE_PATH

async def migrate():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            ALTER TABLE universities ADD COLUMN new_field TEXT
        """)
        await db.commit()
        print("Migration complete")

if __name__ == "__main__":
    asyncio.run(migrate())
```

**3. Run Migration:**

```bash
python scripts/migrate_add_new_table.py
```

---

## Testing Guidelines

### Python Testing (pytest)

**Setup:**

```bash
# Install pytest
pip install pytest pytest-asyncio pytest-cov

# Run tests
pytest tests/

# With coverage
pytest --cov=orchestrator tests/
```

**Example Test:**

```python
# tests/test_conversation.py

import pytest
from orchestrator.conversation import conversation_manager, ConvState

@pytest.mark.asyncio
async def test_generate_initial_message():
    """Test initial message generation."""
    message = await conversation_manager.generate_initial_message(
        university_name="Universitas Indonesia"
    )
    assert "Universitas Indonesia" in message
    assert "Asosiasi Artificial Intelligence" in message

@pytest.mark.asyncio
async def test_analyze_reply_got_number():
    """Test reply analysis when phone number is provided."""
    history = []
    analysis = await conversation_manager.analyze_reply(
        conversation_history=history,
        latest_reply="Hubungi 08123456789",
        push_name="Budi",
        uni_name="Universitas Indonesia"
    )
    assert analysis["action"] == "got_number"
    assert analysis["extracted_number"] is not None
```

### Frontend Testing (Vitest)

**Setup:**

```bash
# Install vitest
npm install -D vitest @testing-library/react @testing-library/jest-dom

# Run tests
npm run test
```

**Example Test:**

```typescript
// frontend/src/components/__tests__/Button.test.tsx

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Button } from '../ui/Button';

describe('Button', () => {
  it('renders children', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('applies variant classes', () => {
    render(<Button variant="danger">Delete</Button>);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('bg-red-600');
  });
});
```

### Manual Testing Checklist

**Orchestrator:**
- [ ] Health check endpoint returns 200
- [ ] Database initialization works
- [ ] Scheduler jobs trigger correctly
- [ ] Webhook receives messages
- [ ] Configuration updates persist

**WhatsApp Service:**
- [ ] QR code generates
- [ ] Connection establishes
- [ ] Messages send with typing indicators
- [ ] Webhook forwards messages
- [ ] Reconnection works on disconnect

**Frontend:**
- [ ] Pages load without errors
- [ ] API calls succeed
- [ ] Pagination works
- [ ] Filters apply correctly
- [ ] Real-time updates (polling)

---

## Debugging

### Python Debugging (VS Code)

**Launch Configuration:**

```json
// .vscode/launch.json
{
  "version": "0.1.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["orchestrator.main:app", "--port", "8000", "--reload"],
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env"
    }
  ]
}
```

**Logging:**

```python
# Use logger for debugging
from orchestrator.config import log

log.debug("Variable value: %s", variable)
log.info("Processing item: %s", item)
log.warning("Unexpected state: %s", state)
log.error("Failed to process: %s", error, exc_info=True)
```

**Database Inspection:**

```bash
# Open database
sqlite3 data/getcontact.db

# Query
SELECT * FROM universities LIMIT 10;

# Check schema
.schema universities
```

### Node.js Debugging (VS Code)

**Launch Configuration:**

```json
// .vscode/launch.json
{
  "version": "0.1.0",
  "configurations": [
    {
      "name": "Node.js: WhatsApp Service",
      "type": "node",
      "request": "launch",
      "runtimeExecutable": "npm",
      "runtimeArgs": ["run", "dev"],
      "cwd": "${workspaceFolder}/whatsapp-service",
      "console": "integratedTerminal"
    }
  ]
}
```

**Logging:**

```typescript
// Use pino logger
logger.info({ messageId }, 'Message sent');
logger.error({ err }, 'Connection failed');

// Debug level
logger.debug({ state }, 'Current state');
```

### Frontend Debugging

**React DevTools:**
- Install browser extension
- Inspect component tree
- View props and state
- Profile performance

**Network Tab:**
- Inspect API requests
- Check response payloads
- Verify status codes

**Console:**
```typescript
// Debug logging
console.log('Universities:', universities);
console.error('API Error:', error);
console.warn('Unexpected state:', state);
```

---

## Common Tasks

### Running Tests

```bash
# Python tests
pytest tests/ -v

# Frontend tests
cd frontend && npm run test

# With coverage
pytest --cov=orchestrator tests/
```

### Database Management

```bash
# Initialize database
python scripts/setup_db.py

# Export data
python scripts/export_results.py

# Backup database
cp data/getcontact.db data/getcontact.db.backup

# Restore database
cp data/getcontact.db.backup data/getcontact.db
```

### Collecting Universities

```bash
# Scrape from PDDIKTI
python scripts/collect_universities.py --province "DKI Jakarta" --limit 10
```

### Manual Pipeline Triggers

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/pipelines/find-handles
curl -X POST http://localhost:8000/api/v1/pipelines/scrape-posts
curl -X POST http://localhost:8000/api/v1/pipelines/extract-phones

# Via frontend
# Navigate to Pipeline page → Click agent trigger buttons
```

### Sending Test Message

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/whatsapp/send \
  -H "Content-Type: application/json" \
  -d '{"to": "628123456789", "message": "Test message"}'
```

### Viewing Logs

**Python (Orchestrator):**
```bash
# Logs output to console
# Check for:
# - [INFO] Normal operations
# - [WARNING] Non-critical issues
# - [ERROR] Failures
# - [CRITICAL] Severe failures
```

**Node.js (WhatsApp Service):**
```bash
# Logs output to console
# Pino logger format
```

**Frontend:**
```bash
# Browser console
# Network tab for API calls
```

---

## Troubleshooting

### Common Issues

**1. WhatsApp Service Not Connecting**

**Symptoms:** QR code keeps generating, connection fails

**Solutions:**
- Check internet connection
- Clear `auth_store/` and `auth_store_backup/`
- Restart service
- Check WhatsApp service is reachable: `curl http://localhost:3100/status`

**2. OpenAI API Errors**

**Symptoms:** "Rate limit exceeded", "Invalid API key"

**Solutions:**
- Verify `OPENAI_API_KEY` in `.env`
- Check API key has credits
- Reduce `MAX_AI_CONCURRENT` to avoid rate limits
- Check OpenAI status page

**3. Database Locked**

**Symptoms:** "database is locked" errors

**Solutions:**
- Close all connections
- Check for long-running transactions
- Use WAL mode (configured in `db.py`)
- Restart orchestrator

**4. Instagram Scraping Fails**

**Symptoms:** No IG handles found, high failure rate

**Solutions:**
- Check `IG_USERNAME` and `IG_PASSWORD`
- Verify account is not blocked
- Increase `IG_REQUEST_DELAY_SECONDS`
- Check Apify/ScrapingBot quota
- Verify Serper API key

**5. Messages Not Sending**

**Symptoms:** Queue fills, messages stuck

**Solutions:**
- Check WhatsApp service status
- Verify webhook registration: `curl http://localhost:3100/status`
- Check `SEND_INTERVAL_MS` configuration
- Review logs for send errors

**6. Frontend API Errors**

**Symptoms:** 500 errors, connection refused

**Solutions:**
- Verify orchestrator is running
- Check CORS configuration
- Verify API base URL in frontend
- Check browser console for errors

### Debug Mode

**Enable Debug Logging:**

```python
# In orchestrator/config.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

```typescript
// In whatsapp-service/src/index.ts
const logger = pino({ level: 'debug' });
```

### Getting Help

**Check:**
1. Logs for error messages
2. API documentation: http://localhost:8000/docs
3. Database schema and queries
4. GitHub issues (if available)

---

## Contributing

### Code Review Process

1. Create feature branch
2. Make changes following coding standards
3. Test thoroughly
4. Update documentation
5. Submit pull request

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes
git add .
git commit -m "feat: add new feature"

# Push to remote
git push origin feature/new-feature

# Create pull request
```

### Commit Message Convention

```
feat: add new pipeline agent
fix: resolve WhatsApp connection issue
docs: update architecture documentation
refactor: improve database query performance
test: add conversation state machine tests
chore: update dependencies
```

---

## Summary

This developer guide provides the essential information for working with the GetContact AI Agent codebase. Key points:

- **Three services:** Orchestrator (Python), WhatsApp Service (Node.js), Frontend (React)
- **Async/await:** Used throughout Python and TypeScript
- **Type safety:** Python type hints + TypeScript strict mode
- **Testing:** pytest for Python, Vitest for frontend
- **Debugging:** VS Code launch configurations, logging
- **Common tasks:** Database management, pipeline triggers, testing

For system architecture details, see [architecture.md](architecture.md).
For deployment instructions, see [deployment.md](deployment.md).
For end-user documentation, see [user-guide.md](user-guide.md).
