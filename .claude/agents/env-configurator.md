---
name: env-configurator
description: >
  Gunakan setelah project-initializer selesai. Agent ini
  setup semua file konfigurasi — .env, docker-compose,
  dan config files yang dibutuhkan project baru.
tools: Read, Write, Bash
---

Tugasmu setup environment yang siap jalan.

Yang perlu dibuat/dikonfigurasi:
1. .env.example — template environment variables
2. .env — local development config
3. docker-compose.yml — jika belum ada
4. Config database connection
5. Config mail, queue, storage jika dibutuhkan brief

Setelah selesai, verifikasi:
docker compose up -d
docker compose exec php php artisan migrate  # atau stack lain
docker compose ps  # semua harus status "Up"

Jika semua Up → laporkan ke programmer untuk CP 4.
```

---

## Skill Tambahan yang Dibutuhkan Greenfield

| Skill | Dipakai oleh | Keterangan |
|-------|-------------|------------|
| `db-design` | `db-designer` | Panduan ERD & schema design |
| `project-setup` | `project-initializer` | Panduan init per framework |

Skill `codebase-explorer` dan `git-operations` untuk clone **tidak dipakai** di greenfield — diganti dengan `git init` fresh oleh `project-initializer`.

---

## Summary: Greenfield vs New Feature
```
Greenfield  (12 agent, 4 checkpoint):
brief-reader → brief-interpreter → 🛑CP1
→ db-designer → technical-planner → 🛑CP2
→ code-architect → 🛑CP3
→ project-initializer → env-configurator → 🛑CP4
→ be-developer + fe-developer (paralel)
→ qa-tester → pr-creator → 👁️PR Review

New Feature (9 agent, 3 checkpoint):
brief-reader → brief-interpreter → 🛑CP1
→ codebase-scout → technical-planner → 🛑CP2
→ code-architect → 🛑CP3
→ be-developer + fe-developer (paralel)
→ qa-tester → pr-creator → 👁️PR Review