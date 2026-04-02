---
name: codebase-explorer
description: >
  Eksplorasi dan analisa struktur codebase existing di repository. Gunakan saat perlu memahami arsitektur project, menemukan file yang relevan, mengidentifikasi pattern yang dipakai, atau memetakan area yang akan terdampak oleh perubahan baru. Digunakan oleh codebase-scout agent.
allowed-tools: Bash, Read, Glob, Grep
---

## Codebase Explorer Skill
Skill ini memandu cara membaca dan memahami codebase existing
secara sistematis — tanpa mengubah apapun.

⚠️ **Aturan Utama**: Ini adalah READ ONLY mission.
JANGAN create, edit, atau delete file apapun selama eksplorasi. Fokus hanya pada pemahaman struktur, pola, dan dependensi kode yang sudah ada.

## Langkah Eksplorasi (Urutan Wajib)
# Langkah 1 — Gambaran Umum Struktur Project
```bash
# Lihat struktur top-level (2 level dalam)
find . -maxdepth 2 -not -path '*/\.*' \
       -not -path '*/node_modules/*' \
       -not -path '*/vendor/*' \
       -not -path '*/__pycache__/*' \
       -not -path '*/storage/*' \
       | sort

# Atau gunakan tree jika tersedia
tree -L 2 -I 'node_modules|vendor|.git|storage|__pycache__'
```
Dari output ini, identifikasi:

- Ini monorepo atau single project?
- Folder utama untuk backend, frontend, config
- Ada berapa sub-project / service?

# Langkah 2 — Deteksi Stack & Framework
```bash
# PHP / Laravel
cat composer.json 2>/dev/null | grep -E '"laravel|"require' | head -20

# Node.js / Express
cat package.json 2>/dev/null | grep -E '"dependencies|"express|"next' | head -20

# Python
cat requirements.txt 2>/dev/null | head -20
cat pyproject.toml 2>/dev/null | head -20
cat setup.py 2>/dev/null | head -10

# React / Next.js
cat package.json 2>/dev/null | grep -E '"react|"next' | head -10  
```

Catat versi framework yang digunakan — ini penting untuk
memastikan kode baru kompatibel.

# Langkah 3 — Pahami Arsitektur & Pattern

# Untuk Laravel / PHP
```bash
# Lihat struktur MVC
ls app/Models/
ls app/Http/Controllers/
ls app/Services/ 2>/dev/null || echo "No Services layer"
ls app/Repositories/ 2>/dev/null || echo "No Repository layer"

# Lihat routes
cat routes/web.php | head -50
cat routes/api.php | head -50

# Lihat migrations (pahami skema DB)
ls database/migrations/ | sort

# Lihat contoh Controller untuk pahami pattern
ls app/Http/Controllers/ | head -5
# Baca satu controller sebagai referensi pattern
```

# Untuk Node.js / Express
```bash
# Entry point
cat server.js 2>/dev/null || cat app.js 2>/dev/null || cat index.js 2>/dev/null | head -50

# Struktur routes & controllers
ls src/routes/ 2>/dev/null || ls routes/ 2>/dev/null
ls src/controllers/ 2>/dev/null || ls controllers/ 2>/dev/null
ls src/services/ 2>/dev/null || ls services/ 2>/dev/null
ls src/models/ 2>/dev/null || ls models/ 2>/dev/null

# Middleware yang dipakai
ls src/middleware/ 2>/dev/null || ls middleware/ 2>/dev/null
```
# Untuk Python
```bash
# Deteksi framework (Flask/FastAPI/Django)
grep -r "from flask\|import flask\|from fastapi\|import django" \
     --include="*.py" -l | head -5

# Struktur utama
ls app/ 2>/dev/null || ls src/ 2>/dev/null
find . -name "*.py" -not -path '*/\.*' \
       -not -path '*/__pycache__/*' \
       -not -path '*/.venv/*' \
       | head -30 
```

# Untuk React / Next.js
```bash
# Deteksi apakah Next.js atau pure React
cat next.config.js 2>/dev/null && echo ">> Next.js project"
cat vite.config.js 2>/dev/null && echo ">> Vite/React project"

# Struktur halaman & komponen
ls src/pages/ 2>/dev/null || ls app/ 2>/dev/null   # Next.js app router
ls src/components/ 2>/dev/null || ls components/ 2>/dev/null
ls src/hooks/ 2>/dev/null
ls src/store/ 2>/dev/null || ls src/context/ 2>/dev/null

# State management
grep -r "redux\|zustand\|jotai\|recoil\|context" \
     package.json | head -5
```

# Langkah 4 — Identifikasi Konvensi Tim

```bash
# Naming convention — lihat contoh file yang ada
ls app/Models/ | head -10          # PascalCase? snake_case?
ls app/Http/Controllers/ | head -10

# Code style config
cat .eslintrc* 2>/dev/null | head -30
cat .prettierrc* 2>/dev/null | head -20
cat phpcs.xml 2>/dev/null | head -20
cat .flake8 2>/dev/null | head -20

# Git hooks / pre-commit
cat .husky/pre-commit 2>/dev/null | head -20
cat .pre-commit-config.yaml 2>/dev/null | head -20

# Environment variables yang digunakan
cat .env.example 2>/dev/null || cat .env.sample 2>/dev/null
```
# Langkah 5 — Identifikasi Touch Points
Berdasarkan requirement dari brief, cari file/area yang
akan terdampak:
```bash
# Cari berdasarkan keyword dari brief
grep -r "KEYWORD_DARI_BRIEF" \
     --include="*.php" --include="*.js" \
     --include="*.ts" --include="*.py" \
     -l | head -20

# Cari model / tabel yang relevan
grep -r "NAMA_ENTITAS" \
     --include="*.php" --include="*.py" \
     -l | head -10

# Cari route yang relevan
grep -r "NAMA_ROUTE_ATAU_ENDPOINT" \
     routes/ src/routes/ --include="*.php" \
     --include="*.js" --include="*.ts" | head -10
```
Ganti `KEYWORD_DARI_BRIEF` dengan kata kunci spesifik
dari requirement yang sedang dianalisa.

# Langkah 6 — Catat Technical Debt yang Relevan
Perhatikan hal-hal ini saat membaca kode:
```bash
# Cari TODO / FIXME / HACK yang relevan dengan area yang akan diubah
grep -r "TODO\|FIXME\|HACK\|XXX" \
     --include="*.php" --include="*.js" \
     --include="*.ts" --include="*.py" \
     -n | grep -i "KEYWORD" | head -20

# Cari deprecated usage
grep -r "deprecated\|@deprecated" \
     --include="*.php" --include="*.js" \
     --include="*.ts" -n | head -10
```

**Format Output Codebase Report**
Setelah eksplorasi selesai, buat laporan dengan format ini:
```markdown
## Codebase Context Report

### 1. Stack & Versi
- Backend: Laravel X.X / Node.js vX.X / Python X.X
- Frontend: React X.X / Next.js X.X
- Database: MySQL / PostgreSQL
- State Management: Redux / Zustand / Context API

### 2. Arsitektur
- Pattern: MVC / Service-Repository / dll
- Folder struktur utama: [deskripsi singkat]
- API style: REST / GraphQL

### 3. Konvensi yang Dipakai
- Naming: PascalCase untuk Model, camelCase untuk method, dll
- Branch naming: feat/xxx, fix/xxx
- Commit style: conventional commits / lainnya

### 4. Touch Points yang Terdampak
- File A — alasan terdampak
- File B — alasan terdampak
- Tabel X — perlu migration baru / perubahan

### 5. Dependencies Relevan yang Sudah Ada
- Package A (vX.X) — bisa dipakai untuk requirement Y
- Package B (vX.X) — bisa dipakai untuk requirement Z

### 6. Technical Debt yang Perlu Diperhatikan
- TODO di file X baris Y — relevan karena...
- Pattern lama di module Z — perlu disesuaikan

### 7. Hal yang Perlu Dikonfirmasi ke Programmer
- Pertanyaan 1
- Pertanyaan 2
```

Tips Eksplorasi Efisien
Baca file dalam urutan ini untuk memahami paling cepat:

1. README.md — gambaran umum project
2. .env.example — pahami semua config yang dibutuhkan
3. routes/api.php atau src/routes/ — peta semua endpoint
4. Satu Model + Migration sebagai referensi pattern
5. Satu Controller/Service sebagai referensi pattern
6. Satu komponen frontend sebagai referensi pattern UI

Jangan baca semua file — cukup yang representatif
untuk memahami pattern, sisanya bisa di-grep saat dibutuhkan.



