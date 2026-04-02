---
name: project-setup
description: >
  Panduan menginisialisasi project baru dari nol untuk setiap
  framework dalam stack. Gunakan saat project-initializer perlu
  menjalankan perintah init, install base dependencies, dan
  setup struktur folder awal. Semua perintah via Docker exec.
allowed-tools: Bash
---

# Project Setup Skill

## ⚠️ Aturan Utama
Semua perintah dijalankan via `docker compose exec`.
TIDAK BOLEH langsung di WSL host.

---

## Laravel / PHP

### Inisialisasi Project Baru
```bash
# Jika folder masih kosong
docker compose exec php composer create-project \
  laravel/laravel . --prefer-dist

# Generate app key
docker compose exec php php artisan key:generate
```

### Base Dependencies Umum
```bash
# Autentikasi API (Sanctum)
docker compose exec php composer require laravel/sanctum
docker compose exec php php artisan vendor:publish \
  --provider="Laravel\Sanctum\SanctumServiceProvider"

# Query builder helper
docker compose exec php composer require spatie/laravel-query-builder

# Media / file upload
docker compose exec php composer require spatie/laravel-medialibrary

# Role & permission
docker compose exec php composer require spatie/laravel-permission

# Dev tools
docker compose exec php composer require --dev \
  laravel/telescope \
  barryvdh/laravel-debugbar
```

### Setup Folder Tambahan (jika pakai Service-Repository pattern)
```bash
docker compose exec php mkdir -p \
  app/Services \
  app/Repositories \
  app/Interfaces \
  app/DTOs \
  app/Enums \
  app/Traits \
  app/Exceptions
```

### Verifikasi
```bash
docker compose exec php php artisan --version
docker compose exec php php artisan migrate:status
```

---

## Node.js / Express

### Inisialisasi Project Baru
```bash
# Init package.json
docker compose exec node pnpm init

# Install Express & core dependencies
docker compose exec node pnpm add \
  express \
  dotenv \
  cors \
  helmet \
  morgan \
  express-validator
```

### Jika Pakai TypeScript
```bash
docker compose exec node pnpm add -D \
  typescript \
  ts-node \
  @types/node \
  @types/express \
  nodemon

# Init tsconfig
docker compose exec node npx tsc --init
```

### ORM & Database
```bash
# Prisma (recommended)
docker compose exec node pnpm add prisma @prisma/client
docker compose exec node npx prisma init

# Atau Sequelize
docker compose exec node pnpm add sequelize mysql2
docker compose exec node pnpm add -D sequelize-cli
```

### Setup Folder Structure
```bash
docker compose exec node mkdir -p \
  src/routes \
  src/controllers \
  src/services \
  src/repositories \
  src/middleware \
  src/models \
  src/utils \
  src/types \
  src/config
```

### Verifikasi
```bash
docker compose exec node node --version
docker compose exec node pnpm --version
```

---

## Python (FastAPI / Flask)

### FastAPI (Recommended untuk API)
```bash
# Install FastAPI + server
docker compose exec python pip install \
  fastapi \
  uvicorn[standard] \
  python-dotenv \
  pydantic \
  pydantic-settings

# ORM
docker compose exec python pip install \
  sqlalchemy \
  alembic \
  pymysql

# Auth
docker compose exec python pip install \
  python-jose[cryptography] \
  passlib[bcrypt] \
  python-multipart

# Simpan ke requirements
docker compose exec python pip freeze > requirements.txt
```

### Flask (Jika sudah familiar)
```bash
docker compose exec python pip install \
  flask \
  flask-sqlalchemy \
  flask-migrate \
  flask-jwt-extended \
  python-dotenv \
  marshmallow

docker compose exec python pip freeze > requirements.txt
```

### Setup Folder Structure (FastAPI)
```bash
mkdir -p \
  app/api/v1/endpoints \
  app/core \
  app/db \
  app/models \
  app/schemas \
  app/services \
  app/repositories \
  app/utils
touch app/__init__.py app/main.py app/core/config.py
```

### Verifikasi
```bash
docker compose exec python python --version
docker compose exec python pip list | grep -E "fastapi|flask"
```

---

## React / Next.js

### Next.js (Recommended — App Router)
```bash
# Jika folder masih kosong
docker compose exec frontend pnpm create next-app . \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir \
  --import-alias "@/*"
```

### Base Dependencies Umum
```bash
# State management
docker compose exec frontend pnpm add zustand

# Data fetching
docker compose exec frontend pnpm add @tanstack/react-query

# Form handling
docker compose exec frontend pnpm add \
  react-hook-form \
  @hookform/resolvers \
  zod

# UI Components (pilih salah satu)
docker compose exec frontend pnpm add \
  @radix-ui/react-dialog \
  @radix-ui/react-dropdown-menu \
  class-variance-authority \
  clsx \
  tailwind-merge

# HTTP client
docker compose exec frontend pnpm add axios

# Icons
docker compose exec frontend pnpm add lucide-react
```

### Setup Folder Structure (Next.js App Router)
```bash
mkdir -p \
  src/components/ui \
  src/components/layout \
  src/components/features \
  src/hooks \
  src/lib \
  src/services \
  src/stores \
  src/types \
  src/utils
```

### Verifikasi
```bash
docker compose exec frontend node --version
docker compose exec frontend pnpm --version
docker compose exec frontend pnpm build 2>&1 | tail -5
```

---

## Git Setup (Setelah Semua Framework Diinit)

### Init Repository
```bash
# Di WSL host (bukan di container)
git init
git add .
git commit -m "chore: initial project setup"

# Hubungkan ke GitLab remote
git remote add origin https://gitlab.com/org/nama-repo.git
git push -u origin main
```

### Setup `.gitignore` Lengkap
```bash
# Download gitignore yang sesuai stack
# Laravel
curl -o .gitignore https://raw.githubusercontent.com/github/gitignore/main/Laravel.gitignore

# Node.js
curl -o backend/.gitignore https://raw.githubusercontent.com/github/gitignore/main/Node.gitignore

# Python
curl -o python/.gitignore https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore

# Next.js / React
curl -o frontend/.gitignore https://raw.githubusercontent.com/github/gitignore/main/Node.gitignore
```

### Tambahkan ke `.gitignore`
```
# Environment
.env
.env.local
.env.*.local

# Docker volumes (jangan commit data)
docker/data/

# OS
.DS_Store
Thumbs.db
```

---

## Checklist Verifikasi Akhir

Sebelum laporkan ke programmer (Checkpoint 4):

- [ ] Semua Docker container status `Up`
- [ ] `docker compose logs` tidak ada error
- [ ] Framework berhasil terinstall di container
- [ ] Struktur folder sesuai `architecture-blueprint.md`
- [ ] `.env.example` sudah dibuat
- [ ] `.gitignore` sudah benar (tidak ada `.env` ter-commit)
- [ ] Initial commit sudah di-push ke GitLab
- [ ] Database migration bisa berjalan tanpa error
