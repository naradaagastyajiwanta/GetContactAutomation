---
name: project-setup
description: >
  Panduan menginisialisasi project untuk GetContactAIAgent.
  Focus pada Python FastAPI, React, dan Node.js setup.
allowed-tools: Bash
---

# Project Setup Skill — GetContactAIAgent

## ⚠️ Aturan Utama
Semua perintah dijalankan via `docker compose exec`.
TIDAK BOLEH langsung di host.

---

## Python / FastAPI (Orchestrator)

### Base Dependencies
```bash
docker compose exec orchestrator pip install \
  fastapi \
  uvicorn[standard] \
  python-dotenv \
  pydantic \
  pydantic-settings \
  aiosqlite \
  openai \
  apscheduler \
  httpx \
  phonenumbers \
  pddiktipy
```

### Development Dependencies
```bash
docker compose exec orchestrator pip install \
  pytest \
  pytest-asyncio \
  httpx \
  black \
  mypy
```

### Save to requirements
```bash
docker compose exec orchestrator pip freeze > requirements.txt
```

### Setup Folder Structure
```bash
mkdir -p \
  orchestrator/agents \
  orchestrator/migrations \
  data \
  scripts \
  tests
```

---

## Node.js / WhatsApp Service

### Init (if not already)
```bash
docker compose exec whatsapp-service npm init -y
```

### Dependencies
```bash
docker compose exec whatsapp-service npm install \
  @whiskeysockets/baileys \
  pino \
  express \
  dotenv \
  axios
```

### Dev Dependencies
```bash
docker compose exec whatsapp-service npm install -D \
  typescript \
  ts-node \
  @types/node \
  @types/express \
  nodemon
```

### TypeScript Config
```bash
docker compose exec whatsapp-service npx tsc --init
```

### Setup Folder Structure
```bash
mkdir -p \
  whatsapp-service/src \
  whatsapp-service/dist
```

---

## React / Frontend

### Init (if using Vite + React)
```bash
# If folder empty
docker compose exec frontend npm create vite@latest . -- --template react-ts
```

### Base Dependencies
```bash
docker compose exec frontend npm install \
  react-router-dom \
  @tanstack/react-query \
  axios \
  lucide-react \
  clsx \
  tailwind-merge
```

### Dev Dependencies
```bash
docker compose exec frontend npm install -D \
  @types/react \
  @types/react-dom \
  tailwindcss \
  postcss \
  autoprefixer \
  @vitejs/plugin-react
```

### Setup Tailwind
```bash
docker compose exec frontend npx tailwindcss init -p
```

### Setup Folder Structure
```bash
mkdir -p \
  frontend/src/pages \
  frontend/src/components \
  frontend/src/components/ui \
  frontend/src/hooks \
  frontend/src/services \
  frontend/src/types \
  frontend/src/utils
```

---

## Environment Setup

### Create .env.example
```bash
cat > .env.example << 'EOF'
# OpenAI
OPENAI_API_KEY=your_openai_api_key_here

# Serper (Google Search)
SERPER_API_KEY=your_serper_api_key_here

# Instagram (optional)
IG_USERNAME=
IG_PASSWORD=
APIFY_API_KEY=

# WhatsApp Service
WHATSAPP_SERVICE_URL=http://whatsapp-service:3100

# Database
DATABASE_PATH=data/getcontact.db

# Outreach Hours (WIB = UTC+7)
OUTREACH_START_HOUR=9
OUTREACH_END_HOUR=17

# Rate Limiting
MAX_CONCURRENT_CONVERSATIONS=3
MESSAGE_INTERVAL_MIN=30
MESSAGE_INTERVAL_MAX=60

# Frontend
VITE_API_URL=http://localhost:8000
EOF
```

### Create .env (actual)
```bash
cp .env.example .env
# Edit .env dengan actual values
```

---

## Git Setup

### .gitignore
```bash
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/
*.egg-info/
.pytest_cache/

# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*
dist/

# Environment
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Database (optional, if want to ignore DB)
# data/*.db

# Logs
*.log
logs/
EOF
```

### Init Git (if not already)
```bash
git init
git add .
git commit -m "chore: initial project setup"
git remote add origin https://gitlab.com/your-org/getcontact-ai-agent.git
git push -u origin main
```

---

## Verification Checklist

### Python
```bash
docker compose exec orchestrator python --version
docker compose exec orchestrator pip list | grep -E "fastapi|openai"
```

### Node.js
```bash
docker compose exec whatsapp-service node --version
docker compose exec whatsapp-service npm list --depth=0
```

### Frontend
```bash
docker compose exec frontend node --version
docker compose exec frontend npm list --depth=0 | grep react
```

### All Services
```bash
docker compose ps
```

All should show "Up" status.

---

## Common Issues

### Port already in use
```bash
# Windows
netstat -ano | findstr :8000
# Kill the PID if needed

# Or change port in docker-compose.yml
```

### Module not found
```bash
# Reinstall dependencies
docker compose exec orchestrator pip install -r requirements.txt
docker compose exec frontend npm install
```

### Permission issues (Linux/WSL)
```bash
sudo chown -R $USER:$USER .
```
