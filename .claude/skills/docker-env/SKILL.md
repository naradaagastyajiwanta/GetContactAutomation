---
name: docker-env
description: >
  Panduan operasi Docker untuk GetContactAIAgent.
  Gunakan setiap kali perlu menjalankan perintah install,
  run, test, atau migrate di dalam environment yang terisolasi.
allowed-tools: Bash
---

# Docker Environment — GetContactAIAgent

## Services
- **orchestrator** - Python FastAPI (port 8000)
- **whatsapp-service** - Node.js Baileys (port 3100)
- **frontend** - React + Vite (port 5173)
- **postgres** - PostgreSQL (optional, jika migrate dari SQLite)

## Aturan Utama
JANGAN pernah jalankan pip, npm, atau python langsung di host.
Selalu jalankan di dalam container dengan `docker compose exec`.

---

## Cek Status Container

```bash
docker compose ps
```

Expected output:
```
NAME                    STATUS          PORTS
getcontact-orchestrator   Up             0.0.0.0:8000->8000/tcp
getcontact-whatsapp       Up             0.0.0.0:3100->3100/tcp
getcontact-frontend       Up             0.0.0.0:5173->5173/tcp
```

---

## Python / Orchestrator

### Install packages
```bash
docker compose exec orchestrator pip install package-name

# Update requirements.txt
docker compose exec orchestrator pip freeze > requirements.txt
```

### Run Python script
```bash
docker compose exec orchestrator python scripts/script_name.py
```

### Database operations
```bash
# Run migration
docker compose exec orchestrator python scripts/setup_db.py

# Export data
docker compose exec orchestrator python scripts/export_results.py
```

### Run tests
```bash
docker compose exec orchestrator python -m pytest tests/ -v
```

---

## Node.js / WhatsApp Service

### Install packages
```bash
docker compose exec whatsapp-service npm install package-name

# Or with pnpm (if using)
docker compose exec whatsapp-service pnpm add package-name
```

### Run TypeScript
```bash
docker compose exec whatsapp-service npx ts-node src/index.ts
```

### Build
```bash
docker compose exec whatsapp-service npm run build
```

---

## React / Frontend

### Install packages
```bash
docker compose exec frontend npm install package-name

# Or with pnpm
docker compose exec frontend pnpm add package-name
```

### Run dev server (usually auto-running)
```bash
docker compose exec frontend npm run dev
```

### Build for production
```bash
docker compose exec frontend npm run build
```

### Run tests
```bash
docker compose exec frontend npm test
```

---

## Start / Stop Services

```bash
# Start semua services
docker compose up -d

# Stop semua services
docker compose down

# Restart specific service
docker compose restart orchestrator

# Rebuild jika Dockerfile berubah
docker compose up -d --build
```

---

## Cek Logs

```bash
# Stream logs (real-time)
docker compose logs -f orchestrator
docker compose logs -f whatsapp-service
docker compose logs -f frontend

# All logs
docker compose logs -f

# Last 50 lines
docker compose logs --tail=50 orchestrator
```

---

## Database Access (SQLite)

### Check database
```bash
docker compose exec orchestrator sqlite3 data/getcontact.db
```

### SQLite commands
```sql
.tables          -- List semua tabel
.schema          -- Lihat schema
.schema table    -- Lihat schema tabel spesifik
SELECT * FROM table LIMIT 10;
.quit            -- Keluar
```

---

## Troubleshooting

### Container tidak bisa start
```bash
# 1. Cek logs
docker compose logs orchestrator

# 2. Rebuild
docker compose down
docker compose up -d --build

# 3. Cek port conflict
netstat -ano | findstr :8000
```

### Database locked
```bash
# Pastikan tidak ada process yang hold DB connection
docker compose ps
docker compose restart orchestrator
```

### Volume corrupt (hapus semua data)
```bash
# HATI-HATI: Ini akan hapus database!
docker compose down -v
docker compose up -d
```

---

## Environment Variables

### Check env di container
```bash
docker compose exec orchestrator env | grep API_KEY
docker compose exec orchestrator cat .env
```

### Restart after env change
```bash
docker compose down
docker compose up -d
```
