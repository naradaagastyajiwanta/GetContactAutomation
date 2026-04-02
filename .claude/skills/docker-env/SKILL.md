---
name: docker-env
description: >
  Panduan operasi Docker untuk project content_automation.
  Gunakan setiap kali perlu menjalankan perintah install,
  run, test, atau migrate di dalam environment yang terisolasi.
  WAJIB digunakan oleh be-developer, fe-developer, qa-tester.
allowed-tools: Bash
---

# Docker Environment — content_automation

## Aturan Utama
JANGAN pernah jalankan pip, npm, composer, atau python
langsung di WSL host. Selalu jalankan di dalam container.

## Cek Status Container
```bash
docker compose ps
```

## Menjalankan Perintah di Container

### PHP / Laravel
```bash
# Install packages
docker compose exec php composer require package-name

# Artisan commands
docker compose exec php php artisan migrate
docker compose exec php php artisan make:model NamaModel

# Jalankan server (jika belum running)
docker compose up -d php
```

### Node.js / Express
```bash
# Install packages
docker compose exec node pnpm add package-name

# Jalankan server
docker compose up -d node
```

### Python
```bash
# Install packages (venv sudah aktif di dalam container)
docker compose exec python pip install package-name

# Update requirements.txt setelah install
docker compose exec python pip freeze > requirements.txt

# Jalankan script
docker compose exec python python script.py
```

### React / Next.js
```bash
# Install packages
docker compose exec frontend pnpm add package-name

# Build
docker compose exec frontend pnpm build
```

## Start / Stop Semua Services
```bash
# Start semua
docker compose up -d

# Stop semua
docker compose down

# Rebuild jika Dockerfile berubah
docker compose up -d --build
```

## Cek Logs
```bash
docker compose logs -f php
docker compose logs -f node
docker compose logs -f python
docker compose logs -f frontend
```

## Troubleshooting
Jika container tidak bisa start:
1. `docker compose logs <service>` — baca error
2. `docker compose down && docker compose up -d --build`
3. Jika volume corrupt: `docker compose down -v` (hati-hati: hapus data DB)