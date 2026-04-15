# GetContact AI — Dokumentasi Teknis Lengkap

> Versi dokumen: April 2026  
> Dibuat dari analisis langsung source code

---

## Daftar Isi

1. [Gambaran Umum Project](#1-gambaran-umum-project)
2. [Arsitektur Sistem](#2-arsitektur-sistem)
3. [Alur Data Utama](#3-alur-data-utama)
4. [Orchestrator (Python FastAPI)](#4-orchestrator-python-fastapi)
   - 4.1 Startup & Lifespan
   - 4.2 Middleware
   - 4.3 Semua API Endpoint (213 endpoint)
5. [Conversation State Machine](#5-conversation-state-machine)
6. [Scheduler & Background Jobs](#6-scheduler--background-jobs)
7. [LLM Access Layer](#7-llm-access-layer)
8. [Instagram Scraping Pipeline](#8-instagram-scraping-pipeline)
9. [Marketing Module](#9-marketing-module)
10. [OSINT Module](#10-osint-module)
11. [CRM Module](#11-crm-module)
12. [Audiensi Module](#12-audiensi-module)
13. [WhatsApp Service (Node.js)](#13-whatsapp-service-nodejs)
    - 13.1 Semua REST Endpoint WA Service
    - 13.2 Device Manager
    - 13.3 Anti-Ban System
14. [Blast Campaign (WhatsApp)](#14-blast-campaign-whatsapp)
15. [Email Blast](#15-email-blast)
16. [Autentikasi & RBAC](#16-autentikasi--rbac)
17. [Frontend (React)](#17-frontend-react)
18. [Database Schema Lengkap (49 tabel)](#18-database-schema-lengkap)
19. [Config Registry (Semua Setting)](#19-config-registry-semua-setting)
20. [Environment Variables](#20-environment-variables)
21. [Docker & Deployment](#21-docker--deployment)
22. [CI/CD Pipeline](#22-cicd-pipeline)
23. [Observability & Error Tracking](#23-observability--error-tracking)

---

## 1. Gambaran Umum Project

**GetContact AI Agent** adalah sistem otomasi outreach multi-layanan untuk universitas, instansi pemerintah, dan target marketing di Indonesia. Sistem ini mengerjakan seluruh funnel dari pencarian prospek hingga penjadwalan audiensi formal secara otomatis.

### Fungsi Utama

| Fase | Apa yang dilakukan |
|------|-------------------|
| **Discovery** | Scraping data universitas dari PDDIKTI API, mencari akun Instagram lewat web search |
| **Scraping** | Scraping post IG untuk mendapatkan nomor telepon sekretariat via GPT-4o Vision OCR |
| **Outreach** | Mengirim pesan WhatsApp pertama ke kontak, lanjut follow-up otomatis |
| **Conversation** | AI (ReAct agent) menjawab balasan, mengekstrak nomor sekretariat yang valid |
| **Audiensi** | Otomatis mengantre permintaan audiensi formal, generate surat PDF, kirim ke rektor |
| **Marketing** | Multi-agent discovery kontak marketing dari laporan tahunan, BNSP, JDIH, asosiasi, dll |
| **OSINT / CRM** | Riset profil mendalam rektor/PIC: media sosial, riwayat pendidikan, kepribadian |
| **Email Blast** | Kirim email massal dengan rotasi akun SMTP, tracking reply via IMAP |

### Target Pengguna Sistem

- Tim BD (Business Development) yang melakukan pendekatan ke kampus
- Staf yang mengoperasikan pipeline outreach harian
- Admin yang mengelola konfigurasi, akun, dan kampanye

---

## 2. Arsitektur Sistem

### Tiga Layanan Independen

```
┌─────────────────────────────────────────────────────────────┐
│                        Host / Docker Network                 │
│                                                             │
│  ┌──────────────────┐    HTTP     ┌──────────────────────┐  │
│  │   Orchestrator   │ ─────────▶  │  WhatsApp Service    │  │
│  │  Python FastAPI  │ ◀─webhook─  │  Node.js / Baileys   │  │
│  │  Port 8000       │             │  Internal Port 3100  │  │
│  └──────────────────┘             └──────────────────────┘  │
│           │                                                  │
│      WebSocket                                               │
│           │                                                  │
│  ┌──────────────────┐                                       │
│  │    Frontend      │    SOCKS5    ┌──────────────────────┐ │
│  │  React + Vite    │    Proxy     │  Cloudflare WARP ×2  │ │
│  │  Dev: Port 5173  │             │  Ports 1080 / 1081   │ │
│  │  Docker: 3010    │             └──────────────────────┘ │
│  └──────────────────┘                                       │
│                            HTTP    ┌──────────────────────┐ │
│                                    │  PinchTab            │ │
│                                    │  Headless Browser    │ │
│                                    │  Port 9867           │ │
│                                    └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Port Mapping

| Service | Dev (local) | Docker (host) | Docker (internal) |
|---------|-------------|---------------|-------------------|
| Orchestrator | 8000 | 8000 (dev) / 8010 (prod) | 8000 |
| WhatsApp Service | 3100 | 3110 | 3100 |
| Frontend | 5173 | 3010 | 3010 |
| WARP Proxy 1 | — | — | 1080 |
| WARP Proxy 2 | — | 1081 | 1080 |
| PinchTab | 9867 | 9867 | 9867 |
| OAuth Callback | 1455 | 127.0.0.1:1455 (prod) | — |

### Komunikasi Antar Layanan

- **Orchestrator → WhatsApp Service**: HTTP REST (`WA_SERVICE_URL`)
- **WhatsApp Service → Orchestrator**: HTTP webhook push (`WEBHOOK_URL`) saat ada pesan masuk
- **Orchestrator → Frontend**: WebSocket real-time events di `/ws`
- **Orchestrator → WARP Proxy**: SOCKS5 untuk scraping dan SMTP
- **Orchestrator → PinchTab**: HTTP untuk browser automation
- **Frontend → Orchestrator**: Axios HTTP dengan session cookie

---

## 3. Alur Data Utama

### Pipeline Scraping → Outreach

```
PDDIKTI API
    │
    ▼
[collect_universities] ──────────── universities (status=pending)
    │
    ▼
[Agent 1: ig_handle_finder]
    - Website → IG handle lewat web (DDG/Serper)
    - Simpan universities.ig_handle
    - Status: pending → ig_found
    │
    ▼
[Agent 2: ig_post_scraper]
    - Scrape post IG terbaru (Playwright → Instaloader → Apify → ScrapingBot)
    - Simpan ke ig_posts
    - Status: ig_found → ig_scraped
    │
    ▼
[Agent 3: ig_phone_extractor]
    - GPT-4o Vision OCR setiap gambar post
    - Ekstrak nomor telepon dari flyer/poster
    - Simpan ke ig_contacts
    - Status: ig_scraped → contacted (jika sudah ada kontak)
    │
    ▼
[Scheduler: daily_outreach_loop]
    - Pilih universitas dengan status ig_scraped
    - Ambil kontak pertama yang belum dihubungi
    - Generate pesan awal (template/ReAct agent)
    - Enqueue ke message_queue → kirim via WA Service
    - Buat conversations record (status=INITIAL_SENT)
    │
    ▼
[Webhook incoming]
    - Terima balasan dari WA Service
    - Acquire per-phone lock
    - ReAct agent menganalisis balasan
    - Transisi state conversation
    │
    ├── GOT_NUMBER → Ekstrak nomor sekretariat
    │                → Auto-antre audiensi
    ├── NEED_MORE   → Generate follow-up question
    ├── REFUSED     → Kirim penutup sopan
    └── FOLLOWUP    → Scheduler kirim follow-up berkala
```

### Pipeline Marketing

```
[User buat Marketing Group]
    │
    ▼
[Marketing Orchestrator Agent]
    - Planning stage: tentukan strategi pencarian
    - Sub-agents paralel:
      ├── Web search (DDG/Serper)
      ├── Instagram discovery
      ├── Annual report scraper
      ├── BNSP/JDIH/LKIP document scraper
      └── Asosiasi profiler
    - Gemini gap-fill stage
    - Hasilkan marketing_contact_results
    │
    ▼
[User review & approve]
    │
    ▼
[Handoff ke Blast Campaign atau Outreach manual]
```

---

## 4. Orchestrator (Python FastAPI)

### 4.1 Startup & Lifespan

Urutan inisialisasi saat server start (via `@asynccontextmanager` lifespan):

1. **Sentry** — `init_sentry()` dari `observability.py` (no-op jika `SENTRY_DSN` kosong)
2. **Database** — `init_db()` membuat semua tabel + inline migration
3. **Marketing Recovery** — memulihkan state yang terganggu saat restart
4. **Log Broadcaster** — register event loop untuk log stream ke frontend
5. **APScheduler** — `setup_scheduler()` mendaftarkan semua cron job
6. **Background Tasks** — start IG health check loop (interval 5 menit), SMTP health check loop (interval 5 menit), message queue worker
7. **Codex Auth** — auto-import `~/.codex/auth.json` jika ada
8. **Webhook Registration** — daftar webhook URL ke WA Service (retry 3x)

**Shutdown sequence:**
- Cancel semua background tasks
- Shutdown scheduler
- Tutup DMS MySQL connection pool

### 4.2 Middleware

**CORS** — allow all origins, methods, headers (untuk dev)

**Auth Middleware** (`@app.middleware("http")`) — validasi session cookie di semua path kecuali:
- `/auth/*`
- `/health`
- `/docs`, `/openapi.json`, `/redoc`
- `/webhook/incoming`

Return 401 jika tidak ada session, 403 jika permission tidak cukup.

**Exception Handler** — `httpx.ConnectError` → return 503 saat WA service unreachable.

**Thread Pool** — `ThreadPoolExecutor(max_workers=2)` untuk agent jobs (agar tidak blocking event loop).

### 4.3 Semua API Endpoint

#### Autentikasi (24 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/auth/bootstrap-status` | Cek apakah setup admin pertama kali masih diperlukan |
| POST | `/auth/setup` | Buat admin pertama (harus dilakukan saat pertama deploy) |
| POST | `/auth/login` | Login dengan email/password DMS, set session cookie |
| POST | `/auth/logout` | Hapus session cookie aktif |
| GET | `/auth/me` | Ambil data user dari session cookie aktif |
| GET | `/auth/roles` | Daftar role yang tersedia (admin/operator/viewer) |
| GET | `/auth/access` | Daftar semua assignment role saat ini |
| GET | `/auth/audit-logs` | Log audit auth (paginasi) |
| GET | `/auth/role-requests/me` | Request upgrade role milik user sendiri |
| POST | `/auth/role-requests` | Ajukan request upgrade role |
| GET | `/auth/role-requests` | Semua request upgrade role (admin) |
| POST | `/auth/role-requests/{id}/approve` | Setujui request upgrade role |
| POST | `/auth/role-requests/{id}/reject` | Tolak request upgrade role |
| POST | `/auth/access/grant` | Grant role ke user |
| POST | `/auth/access/revoke` | Cabut role dari user |
| POST | `/auth/codex/start` | Mulai OAuth flow ChatGPT (buka browser) |
| GET | `/auth/callback` | OAuth callback dari OpenAI |
| GET | `/auth/codex-callback` | Codex OAuth callback handler |
| POST | `/auth/codex/manual` | Input token manual (headless server) |
| POST | `/auth/codex/cancel` | Batalkan proses login Codex |
| POST | `/auth/codex/logout` | Logout dari Codex OAuth |
| POST | `/auth/codex/refresh` | Refresh token Codex secara manual |
| POST | `/auth/codex/import-external` | Import `~/.codex/auth.json` |

#### Health & Monitoring (6 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/health` | Health check dasar (status services) |
| GET | `/health/llm-metrics` | Metrik penggunaan LLM (Codex vs API calls, cooldown status) |
| GET | `/health/codex-oauth` | Status token Codex OAuth (valid/expired, expiry time) |
| GET | `/health/sentry-status` | Status Sentry (aktif/nonaktif, environment) |
| GET | `/health/sentry-debug` | Debug Sentry (hanya jika `SENTRY_DEBUG_ENABLED=true`) |
| GET | `/dashboard` | Statistik ringkasan seluruh sistem |

#### Universitas (14 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/universities` | Daftar universitas (filter: status, province, search; paginasi) |
| POST | `/universities` | Tambah universitas baru secara manual |
| POST | `/universities/import` | Import dari file Excel/CSV |
| GET | `/universities/export-excel` | Export data ke file .xlsx |
| POST | `/universities/match-names` | Cocokkan nama universitas ke record yang ada |
| GET | `/universities/provinces` | Daftar provinsi unik untuk filter dropdown |
| GET | `/universities/with-emails` | Universitas yang punya email (untuk email blast) |
| GET | `/universities/{id}` | Detail satu universitas |
| PATCH | `/universities/{id}/toggle-enabled` | Aktifkan/nonaktifkan universitas dari pipeline |
| PATCH | `/universities/bulk-toggle` | Aktifkan/nonaktifkan banyak universitas sekaligus |
| DELETE | `/universities/{id}/ig-handle` | Hapus IG handle universitas |
| GET | `/universities/{id}/contacts` | Kontak yang ditemukan untuk universitas ini |
| GET | `/universities/{id}/posts` | Post IG yang sudah di-scrape |
| GET | `/universities/{id}/related-igs` | Akun IG terkait (BEM, dll) |

#### Kontak & Nomor Telepon (5 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/phone-numbers` | Daftar nomor telepon yang diekstrak (filter: university, status) |
| GET | `/phone-numbers/stats` | Statistik nomor telepon |
| PATCH | `/contacts/{id}/toggle-contacted` | Toggle status "sudah dihubungi" |
| POST | `/contacts/bulk-match` | Bulk matching kontak |
| POST | `/contacts/bulk-update-status` | Update status banyak kontak sekaligus |

#### Grup Universitas (8 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/university-groups` | Daftar semua grup |
| POST | `/university-groups` | Buat grup baru |
| GET | `/university-groups/{id}` | Detail grup |
| PUT | `/university-groups/{id}` | Update grup |
| DELETE | `/university-groups/{id}` | Hapus grup |
| POST | `/university-groups/{id}/universities/add` | Tambah universitas ke grup |
| POST | `/university-groups/{id}/universities/remove` | Hapus universitas dari grup |
| GET | `/university-groups/{id}/university-ids` | Daftar ID universitas dalam grup |

#### Percakapan (3 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/conversations` | Daftar percakapan (filter: state, university_id) |
| GET | `/conversations/{id}` | Detail percakapan + riwayat pesan |
| POST | `/conversations/test` | Test alur conversation (tidak mengirim pesan nyata) |

#### Pipeline Agent (11 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| POST | `/pipeline/collect-universities` | Scraping universitas dari PDDIKTI |
| POST | `/pipeline/find-ig-handles` | Agent 1: cari IG handle |
| POST | `/pipeline/scrape-ig-posts` | Agent 2: scrape post IG |
| POST | `/pipeline/extract-phones` | Agent 3: ekstrak nomor dari gambar |
| POST | `/pipeline/discover-bem` | Agent 4: temukan akun BEM |
| POST | `/pipeline/find-rectors` | Agent 5: riset nama rektor |
| POST | `/pipeline/run-agent-targeted` | Jalankan agent pada universitas tertentu |
| GET | `/pipeline/status` | Status setiap tahap pipeline |
| GET | `/pipeline/logs` | Log aktivitas pipeline (paginasi) |
| GET | `/pipeline/logs/{id}` | Detail satu log pipeline |
| GET | `/pddikti/provinces` | Daftar provinsi dari PDDIKTI |

#### Outreach & Kontrol (6 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| POST | `/outreach/start` | Trigger manual outreach loop |
| POST | `/outreach/process-followups` | Trigger manual proses follow-up |
| POST | `/control/pause` | Pause semua outreach & auto-reply |
| POST | `/control/resume` | Resume outreach & auto-reply |
| GET | `/control/status` | Status pause dan toggle chatbot |
| POST | `/control/chatbot/{type}` | Toggle chatbot (`agent` atau `audiensi`) |

#### WhatsApp Management (26 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/wa/devices` | Daftar semua WA device |
| POST | `/wa/me/device` | Buat/set device untuk user saat ini |
| GET | `/wa/me/device` | Ambil device user saat ini |
| DELETE | `/wa/me/device/{id}` | Hapus device user |
| PATCH | `/wa/me/device/{id}/label` | Update label device |
| GET | `/wa/devices/{id}/status` | Status satu device |
| GET | `/wa/devices/{id}/qr` | QR code untuk device |
| POST | `/wa/devices/{id}/connect` | Hubungkan device |
| POST | `/wa/devices/{id}/disconnect` | Putuskan device |
| POST | `/wa/devices/{id}/recover` | Paksa recovery koneksi device |
| GET | `/wa/devices/{id}/antiban` | Status anti-ban device |
| POST | `/wa/devices/{id}/antiban/pause` | Pause anti-ban |
| POST | `/wa/devices/{id}/antiban/resume` | Resume anti-ban |
| POST | `/wa/devices/{id}/antiban/reset` | Reset state anti-ban |
| GET | `/wa/qr` | QR code device default |
| GET | `/wa/status` | Status koneksi WA |
| POST | `/wa/send-test` | Kirim pesan WA test |
| POST | `/wa/logout` | Logout WA |
| POST | `/wa/restart` | Restart koneksi WA |
| POST | `/wa/bulk-send` | Kirim pesan WA massal |
| POST | `/wa/bulk-send-document` | Kirim dokumen WA massal |

#### Konfigurasi (6 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/config` | Semua nilai konfigurasi (nilai sensitif di-mask) |
| PATCH | `/config` | Update satu atau beberapa setting |
| PATCH | `/config/instagram` | Update setting Instagram khusus |
| GET | `/config/{key}` | Satu nilai config |
| DELETE | `/config/{key}` | Reset key ke default |
| GET | `/config/models` | Daftar model LLM yang tersedia |

#### Akun Email SMTP (6 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/email-smtp-accounts` | Daftar akun SMTP |
| POST | `/email-smtp-accounts` | Tambah akun SMTP |
| PUT | `/email-smtp-accounts/{id}` | Update akun SMTP |
| DELETE | `/email-smtp-accounts/{id}` | Hapus akun SMTP |
| POST | `/email-smtp-accounts/{id}/test` | Test koneksi SMTP |
| POST | `/email-smtp-accounts/check-all` | Cek health semua akun SMTP |

#### Akun Instagram (12 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/ig-accounts` | Daftar akun IG |
| GET | `/ig-accounts/health` | Status health semua akun IG |
| POST | `/ig-accounts` | Tambah akun IG |
| PUT | `/ig-accounts/{id}` | Update akun IG |
| DELETE | `/ig-accounts/{id}` | Hapus akun IG |
| POST | `/ig-accounts/{id}/login` | Login ke akun IG |
| POST | `/ig-accounts/{id}/login/challenge` | Handle login challenge (2FA) |
| POST | `/ig-accounts/{id}/test-login` | Test login akun IG |
| GET | `/ig-accounts/{id}/test-login-live` | Test login live (SSE stream) |
| GET | `/ig-accounts/{id}/session/export` | Export session cookies |
| POST | `/ig-accounts/{id}/session/import` | Import session cookies |
| POST | `/ig-accounts/{id}/session/import-cookies` | Import dari format cookies browser |

#### Knowledge Base (5 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/knowledge-items` | Daftar knowledge items |
| POST | `/knowledge-items` | Tambah knowledge item |
| PATCH | `/knowledge-items/{id}` | Update knowledge item |
| DELETE | `/knowledge-items/{id}` | Hapus knowledge item |
| POST | `/knowledge-items/upload` | Upload file sebagai knowledge item |

#### Learning System (4 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/learning/lessons` | Daftar lessons aktif yang diekstrak dari percakapan |
| GET | `/learning/analyses` | Analisis yang belum diproses |
| GET | `/learning/stats` | Statistik sistem learning |
| POST | `/learning/trigger-reflection` | Trigger refleksi manual di background |

#### Audiensi (15 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/audiensi` | Daftar audiensi (filter: state, university) |
| GET | `/audiensi/queue` | Antrian audiensi |
| GET | `/audiensi/stats` | Statistik audiensi |
| GET | `/audiensi/{id}` | Detail satu audiensi |
| PUT | `/audiensi/{id}/rector-name` | Update nama rektor |
| PUT | `/audiensi/{id}/initial-message` | Update draft pesan awal |
| POST | `/audiensi/{id}/regenerate-pdf` | Generate ulang surat audiensi PDF |
| GET | `/audiensi/{id}/pdf` | Download surat audiensi PDF |
| POST | `/audiensi/{id}/approve` | Setujui audiensi (kirim pesan ke kontak) |
| POST | `/audiensi/{id}/reject` | Tolak audiensi |
| POST | `/audiensi/{id}/send-zoom` | Kirim link Zoom meeting |
| POST | `/audiensi/template/upload` | Upload template surat (.docx) |
| GET | `/audiensi/template/placeholders` | Placeholder yang tersedia di template |

#### DMS Integration (21 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/dms/health` | Status koneksi DMS MySQL |
| GET | `/dms/stats` | Statistik data DMS |
| GET | `/dms/schedules` | Daftar jadwal audiensi dari DMS |
| GET | `/dms/schedules/today` | Jadwal hari ini |
| GET | `/dms/schedules/{id}` | Detail jadwal |
| GET | `/dms/followups` | Daftar follow-up DMS |
| GET | `/dms/followups/{id_univ}` | Follow-up per universitas |
| GET | `/dms/meetings` | Daftar meeting DMS |
| GET | `/dms/pics/search` | Cari PIC di DMS |
| GET | `/dms/universities/search` | Cari universitas di DMS |
| GET | `/dms/universities/{id}` | Detail universitas DMS |
| GET | `/dms/approvals` | Daftar approval DMS |
| POST | `/dms/sync/contacts` | Sync kontak ke DMS MySQL |
| POST | `/dms/sync/schedules` | Sync jadwal dari DMS |
| POST | `/dms/research/run-tomorrow` | Jalankan riset untuk jadwal besok |
| POST | `/dms/research/schedule/{id}` | Riset untuk satu jadwal |
| POST | `/dms/research/test` | Test riset DMS |
| GET | `/dms/research/results` | Hasil riset DMS |
| GET | `/dms/research/results/{id}` | Hasil riset per jadwal |

#### OSINT (5 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| POST | `/osint/run/{university_id}` | Jalankan OSINT untuk satu universitas |
| POST | `/osint/run-batch` | OSINT batch untuk banyak universitas |
| GET | `/osint/profile/{university_id}` | Profil OSINT universitas |
| GET | `/osint/runs` | Daftar run OSINT |
| GET | `/osint/runs/{id}` | Detail satu run OSINT |

#### CRM (7 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| POST | `/crm/requests` | Buat request profiling CRM |
| GET | `/crm/requests` | Daftar request CRM |
| GET | `/crm/requests/{id}` | Detail request CRM |
| POST | `/crm/requests/{id}/run` | Jalankan profiling CRM |
| GET | `/crm/profiles/{id}` | Profil CRM hasil profiling |
| PATCH | `/crm/profiles/{id}` | Update profil CRM secara manual |
| GET | `/crm/stats` | Statistik CRM |

#### Blast Campaign WA (17 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/blast/contacts` | Kontak yang bisa di-blast |
| POST | `/blast/check-previously-blasted` | Cek kontak yang sudah pernah di-blast |
| POST | `/blast/campaigns` | Buat campaign blast baru |
| GET | `/blast/campaigns` | Daftar campaign blast |
| GET | `/blast/campaigns/{id}` | Detail campaign |
| PUT | `/blast/campaigns/{id}` | Update campaign |
| DELETE | `/blast/campaigns/{id}` | Hapus campaign |
| POST | `/blast/campaigns/{id}/recipients` | Tambah penerima ke campaign |
| GET | `/blast/campaigns/{id}/recipients` | Daftar penerima campaign |
| DELETE | `/blast/campaigns/{id}/recipients/{rid}` | Hapus satu penerima |
| DELETE | `/blast/campaigns/{id}/recipients` | Hapus semua penerima |
| GET | `/blast/campaigns/{id}/preview` | Preview pesan campaign |
| POST | `/blast/campaigns/{id}/start` | Mulai campaign |
| POST | `/blast/campaigns/{id}/pause` | Pause campaign |
| POST | `/blast/campaigns/{id}/cancel` | Batalkan campaign |
| POST | `/blast/campaigns/{id}/force-resume` | Force resume (bypass anti-ban) |

#### Email Blast (32 endpoint)

| Method | Path | Deskripsi |
|--------|------|-----------|
| POST | `/email-blast/campaigns` | Buat campaign email baru |
| GET | `/email-blast/campaigns` | Daftar campaign email |
| GET | `/email-blast/campaigns/{id}` | Detail campaign |
| PATCH | `/email-blast/campaigns/{id}` | Update campaign |
| POST | `/email-blast/campaigns/{id}/recipients/add-all` | Tambah semua universitas yang punya email |
| POST | `/email-blast/campaigns/{id}/recipients/add` | Tambah penerima spesifik |
| POST | `/email-blast/campaigns/{id}/recipients/upload` | Upload file penerima |
| POST | `/email-blast/campaigns/{id}/recipients/import` | Import penerima dari DB |
| GET | `/email-blast/campaigns/{id}/recipients` | Daftar penerima |
| DELETE | `/email-blast/campaigns/{id}/recipients/{rid}` | Hapus penerima |
| POST | `/email-blast/campaigns/{id}/start` | Mulai kampanye email |
| POST | `/email-blast/campaigns/{id}/pause` | Pause kampanye |
| POST | `/email-blast/campaigns/{id}/cancel` | Batalkan kampanye |
| POST | `/email-blast/campaigns/{id}/retry-failed` | Retry email yang gagal |
| POST | `/email-blast/campaigns/{id}/sync-counters` | Sinkronkan counter dari tabel penerima |
| POST | `/email-blast/campaigns/{id}/test-email` | Kirim email test |
| GET | `/email-blast/campaigns/{id}/sent-emails` | Email yang sudah terkirim |
| GET | `/email-blast/campaigns/{id}/sent-emails/{eid}` | Detail satu email |
| GET | `/email-blast/campaigns/{id}/inbox` | Inbox reply campaign |
| GET | `/email-blast/campaigns/{id}/attachment` | Download attachment campaign |
| POST | `/email-blast/campaigns/{id}/attachment` | Upload attachment campaign |
| GET | `/email-blast/inbox` | Inbox user |
| GET | `/email-blast/sent-emails` | Email terkirim |
| GET | `/email-blast/sent-folder` | Folder sent |
| POST | `/email-blast/test-smtp` | Test konfigurasi SMTP |
| POST | `/email-blast/test-imap` | Test konfigurasi IMAP |
| GET | `/email-blast/test-inbox` | Test baca inbox |
| GET | `/email-blast/quota` | Status quota email harian |
| GET | `/email-blast/debug-campaign-replies/{id}` | Debug reply matching campaign |
| GET | `/email-blast/letter-config` | Konfigurasi format nomor surat |
| POST | `/email-blast/letter-config` | Buat/update konfigurasi surat |
| GET | `/email-blast/letter-history` | Riwayat penomoran surat |

#### Lainnya

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/export/csv` | Export data ke CSV |
| GET | `/api-logs` | Log semua API call (paginasi, filter) |
| GET | `/api-logs/{id}` | Detail satu log |
| GET | `/instagram/session-status` | Status session IG aktif |
| POST | `/instagram/reset-sessions` | Reset semua session IG |
| GET | `/api/v1/proxy-image` | Proxy gambar (hindari CORS) |
| GET | `/api/v1/instagram-image` | Ambil gambar dari CDN Instagram |
| GET | `/migration/dms/status` | Status migrasi DMS |
| POST | `/migration/dms/run` | Jalankan migrasi DMS |
| POST | `/webhook/incoming` | Terima pesan masuk dari WA Service |
| GET `/ws` | WebSocket | Stream real-time events ke frontend |

---

## 5. Conversation State Machine

### Status Percakapan

```
PENDING
  │
  ├──[scheduler: daily_outreach_loop]──▶ INITIAL_SENT
  │
  └─────────────────────────────────────────────────────┐
                                                         │
INITIAL_SENT / FOLLOWUP_SENT / NEED_MORE / WAITING_REPLY│
  │                                                      │
  ├──[webhook: pesan masuk]──▶ ANALYZING                 │
  │         │                      │                     │
  │         │              [ReAct Agent analisis]        │
  │         │                      │                     │
  │         │         ┌────────────┼─────────────┐       │
  │         │         ▼            ▼             ▼       │
  │         │    GOT_NUMBER    REFUSED      NEED_MORE    │
  │         │    (terminal)   (terminal)        │        │
  │         │                              WAITING_REPLY │
  │         │                                            │
  └─────────┘                                            │
                                                         │
[scheduler: process_followups] ──────────────────────────┘
  │
  ├── followup_count < MAX → FOLLOWUP_SENT
  └── followup_count >= MAX → ABANDONED (terminal)

UNDELIVERED (terminal) — jika WA Service return error kirim
```

### Trigger per Transisi

| Dari | Ke | Trigger |
|------|----|---------|
| PENDING | INITIAL_SENT | `daily_outreach_loop` di scheduler (tiap 30 menit) |
| INITIAL_SENT | ANALYZING | Webhook `POST /webhook/incoming` |
| WAITING_REPLY | ANALYZING | Webhook `POST /webhook/incoming` |
| FOLLOWUP_SENT | ANALYZING | Webhook `POST /webhook/incoming` |
| ANALYZING | GOT_NUMBER | LLM ekstrak nomor telepon yang valid |
| ANALYZING | REFUSED | LLM deteksi penolakan |
| ANALYZING | NEED_MORE | LLM butuh klarifikasi |
| ANALYZING | WAITING_REPLY | Balasan ambigu, kirim pertanyaan lanjutan |
| * (aktif) | FOLLOWUP_SENT | `process_followups` (tiap jam) setelah `FOLLOWUP_N_AFTER_HOURS` |
| * (aktif) | ABANDONED | `process_followups` setelah `MAX_FOLLOWUP_ATTEMPTS` terlampaui |
| * | UNDELIVERED | WA Service error saat kirim |

### Setelah GOT_NUMBER

Ketika state transisi ke `GOT_NUMBER`:
1. Nomor sekretariat disimpan ke `conversations.extracted_number`
2. Status universitas diupdate
3. `create_audiensi_from_success()` dipanggil → membuat record di `audiensi_conversations` (state: QUEUED)
4. Jika `AUTO_APPROVE_AUDIENSI = true`, audiensi auto-approve setelah `AUTO_APPROVE_DELAY_MINUTES`

### Audiensi State Machine

```
QUEUED → APPROVED → INITIAL_SENT → WAITING_REPLY → SCHEDULING → SCHEDULED → ZOOM_SENT
                                 ↘ FOLLOWUP_SENT ↗
                                 
Terminal: ZOOM_SENT, REFUSED, ABANDONED
```

---

## 6. Scheduler & Background Jobs

Semua job berjalan di WIB (UTC+7) menggunakan APScheduler.

### Outreach Jobs

| Job | Jadwal | Deskripsi |
|-----|--------|-----------|
| `daily_outreach_loop` | Tiap 30 menit, jam `OUTREACH_START_HOUR`–`OUTREACH_END_HOUR` | Kirim pesan pertama ke kontak baru |
| `process_followups` | Tiap jam menit ke-15, jam outreach | Kirim follow-up ke percakapan aktif |
| `process_audiensi_followups` | Tiap jam menit ke-45, jam outreach | Follow-up percakapan audiensi |

### Pipeline Agent Jobs (thread pool, max 2 workers)

| Job | Interval Default | Config Key |
|-----|-----------------|------------|
| Agent 1: ig_handle_finder | Tiap 1 jam | `AGENT_HANDLE_FINDER_INTERVAL_HOURS` |
| Agent 2: ig_post_scraper | Tiap 2 jam, menit ke-10 | `AGENT_POST_SCRAPER_INTERVAL_HOURS` |
| Agent 3: phone_extractor | Tiap 15 menit, 24/7 | `AGENT_PHONE_EXTRACTOR_INTERVAL_MINUTES` |
| Agent 4: bem_discovery | Tiap 1 jam, menit ke-40 | `AGENT_BEM_DISCOVERY_INTERVAL_HOURS` |

### DMS Sync Jobs

| Job | Jadwal | Deskripsi |
|-----|--------|-----------|
| `dms_sync_audiensi_schedules` | Tiap `DMS_SYNC_INTERVAL_MINUTES` (default 30 menit) | Fetch jadwal dari DMS, kirim reminder WA |
| `dms_sync_contacts` | Tiap 2 jam menit ke-50, jam 8–20 | Sync nomor GOT_NUMBER ke DMS MySQL |
| `_run_audiensi_research` | Tiap hari jam `DMS_RESEARCH_HOUR` (default 18:00) | Riset Gemini untuk jadwal besok |
| `_run_audiensi_research_check` | Tiap 4 jam menit ke-30, jam 8–22 | Catch-up riset yang terlewat |

### Learning & Embedding Jobs

| Job | Jadwal | Deskripsi |
|-----|--------|-----------|
| `run_learning_reflection` | 08:45, 14:45, 20:45 WIB | Ekstrak lessons dari analisis percakapan |
| `run_build_missing_embeddings` | Tiap 6 jam menit ke-55 | Build vector embedding untuk knowledge & lessons |

### Audiensi & Marketing Jobs

| Job | Jadwal | Deskripsi |
|-----|--------|-----------|
| `auto_approve_queued_audiensi` | Tiap 15 menit | Auto-approve audiensi QUEUED setelah delay |
| `_threaded_audiensi_rector_finder` | Tiap 4 jam menit ke-20, jam 8–20 | Cari nama rektor untuk audiensi |
| `_run_marketing_search_queue` | Tiap jam menit ke-0 | Proses antrian pencarian marketing |
| `_check_codex_oauth_health` | Tiap 15 menit | Monitor status token Codex OAuth |

---

## 7. LLM Access Layer

Semua panggilan AI di orchestrator melewati `orchestrator/llm/gateway.py`.

### Routing Logic

```
gateway.chat_completions_create() / responses_create()
    │
    ├── CHATGPT_OAUTH_ENABLED = true
    │       │
    │       ├── Token valid? ──▶ CodexClient → chatgpt.com/backend-api/codex
    │       │                    (SSE stream, header: Bearer + chatgpt-account-id)
    │       │
    │       └── Rate limit 429 / Auth error / Connection error
    │               │
    │               └── Cooldown 15 menit, fallback ke →
    │
    └── CHATGPT_OAUTH_ENABLED = false (atau fallback)
            │
            └── AsyncOpenAI → api.openai.com
                (OPENAI_API_KEY)

gateway.embeddings_create()
    └── Selalu ke api.openai.com (Codex tidak expose /v1/embeddings)
```

### File-file LLM Layer

| File | Fungsi |
|------|--------|
| `gateway.py` | Entry point: `chat_completions_create`, `responses_create`, `embeddings_create` |
| `client_factory.py` | Lazy singleton: `get_real_client()` (AsyncOpenAI), `get_codex()` (CodexClient) |
| `codex_oauth.py` | PKCE flow, token exchange/refresh, JWT decode |
| `codex_token_store.py` | Simpan token ke `data/codex_auth/auth.json`, file-locked |
| `codex_login_server.py` | Server aiohttp sementara di `localhost:1455` saat login |
| `codex_client.py` | HTTP client dengan header injection, SSE collection |
| `codex_chat_translator.py` | Terjemah Chat Completions ↔ Responses API |
| `codex_transformer.py` | Normalisasi request body (force `store=false`) |
| `codex_sse.py` | Parse SSE events dari Codex backend |

### Header Codex Request

```http
Authorization: Bearer <token>
chatgpt-account-id: <JWT claim "accountId">
OpenAI-Beta: gizmo-3
originator: codex_cli_rs  (configurable via CHATGPT_OAUTH_ORIGINATOR)
```

### Metrik di `/health/llm-metrics`

- Total calls via Codex vs API
- Cooldown aktif (sisa waktu setelah 429)
- Token usage aggregate
- Error rate per provider

---

## 8. Instagram Scraping Pipeline

### Rantai Failover (Tier 0 → Tier 3)

```
Tier 0: Playwright (playlist_ig.py)
    - Browser Chromium headless via Playwright
    - Session IG dari IG_SESSION_ID (rotasi otomatis)
    - Proxy WARP SOCKS5 jika PROXY_POOL_ENABLED=true
    - Restart browser tiap PW_PROFILES_PER_SESSION (default: 15)
    - Limit: PW_DAILY_LIMIT (default: 100/hari)
    │
    ▼ (jika Playwright return alt-text / rate limit)
Tier 1: Instaloader (gratis, tanpa session)
    - Delay: INSTALOADER_REQUEST_DELAY (default: 2.0 detik)
    - Toggle: INSTALOADER_ENABLED
    │
    ▼ (jika semua scraper organik gagal)
Tier 2: Apify API (berbayar)
    - apify_client.py
    - Memerlukan APIFY_API_KEY
    │
    ▼
Tier 3: ScrapingBot (berbayar)
    - scrapingbot_client.py
    - Memerlukan SCRAPINGBOT_USERNAME + SCRAPINGBOT_API_KEY
    - Support rotasi akun (SCRAPINGBOT_ACCOUNTS JSON)
```

### Agent 3 — Phone Extraction

Setiap gambar post IG dikirim ke GPT-4o Vision OCR:
- Gambar di-cache ke S3/GCS/R2 via `bucket.py` (agar tidak re-download)
- Prompt menginstruksikan model untuk ekstrak nomor telepon Indonesia (format `08xx`, `+628xx`)
- Validasi nomor dengan library `phonenumbers`
- Hasil disimpan ke `ig_contacts` (UNIQUE per universitas + nomor)

### Agent 4 — BEM Discovery

Mencari akun BEM (Badan Eksekutif Mahasiswa) universitas:
1. Cari via web search "BEM [nama universitas] instagram"
2. Ikuti following list akun IG utama universitas
3. Filter akun dengan kata kunci BEM/Hima/UKM
4. Simpan ke `university_related_igs`
5. Scrape post BEM untuk nomor tambahan

---

## 9. Marketing Module

### Arsitektur Multi-Agent

```
mkt_orchestrator.py (ReAct Agent)
    │
    ├── Stage 1: Planning
    │   └── LLM buat strategi pencarian berdasarkan client_type
    │
    ├── Stage 2: Parallel Discovery (asyncio.Semaphore(20))
    │   ├── Web Search Agent (DDG/Serper)
    │   ├── Instagram Discovery Agent
    │   ├── Annual Report Scraper (discovery/annual_report.py)
    │   ├── BNSP Scraper (discovery/bnsp.py) — lembaga sertifikasi
    │   ├── JDIH Scraper (discovery/jdih.py) — hukum/regulasi
    │   ├── LKIP Scraper (discovery/lkip.py) — laporan kinerja pemerintah
    │   └── Asosiasi Profiler (discovery/asosiasi.py)
    │
    ├── Stage 3: Scoring & Dedup
    │   └── Score kandidat IG berdasarkan affinity, profile match
    │
    └── Stage 4: Gemini Gap-Fill (jika MARKETING_GEMINI_ENABLED)
        └── Gemini + Google Search grounding untuk data yang belum ditemukan
```

### Status Orchestration

| Status | Arti |
|--------|------|
| `idle` | Belum dijalankan |
| `queued` | Dalam antrian scheduler |
| `planning` | Agent sedang buat rencana |
| `searching` | Sub-agents aktif mencari |
| `scoring` | Scoring kandidat |
| `gap_filling` | Gemini gap-fill stage |
| `completed` | Selesai |
| `error` | Gagal (reset otomatis setelah 1 jam) |

---

## 10. OSINT Module

Mengumpulkan intelijen open-source tentang staf universitas.

### Agen OSINT

| File | Fungsi |
|------|--------|
| `social_profiler.py` | Profil dari Instagram, LinkedIn, Twitter |
| `academic_profiler.py` | Profil akademik dari Google Scholar, Sinta, Garuda |
| `web_profiler.py` | Profil dari website universitas dan berita |
| `identity_resolver.py` | Deduplikasi identitas lintas sumber |
| `contact_enricher.py` | Pengayaan email dan nomor telepon |
| `news_scanner.py` | Scan berita tentang individu |
| `personal_interest.py` | Hobi dan minat dari post media sosial |
| `graph.py` | Graph entitas dan relasi (LangGraph) |

### Tabel Output OSINT

- `osint_profiles` — profil universitas (alamat, kontak resmi)
- `osint_contacts` — kontak individual yang ditemukan
- `osint_social_media` — akun media sosial
- `osint_news` — berita terkait

---

## 11. CRM Module

Membuat profil mendalam personal untuk PIC (Person In Charge) / rektor.

### Data yang Dikumpulkan per Profil

| Kategori | Field |
|----------|-------|
| **Identitas** | Nama lengkap, jabatan, mata kuliah, masa jabatan |
| **Personal** | Tanggal lahir, usia, asal daerah |
| **Pendidikan** | Riwayat pendidikan (S1/S2/S3) |
| **Keluarga** | Status pernikahan, nama pasangan, jumlah anak, alamat rumah |
| **Kampus** | Masalah kampus, kekhawatiran, harapan |
| **Minat** | Hobi, makanan favorit, aktivitas di luar kampus |
| **Psikologi** | Ringkasan kepribadian, gaya komunikasi, wawasan perilaku sosial |
| **Topik Terkini** | Isu terbaru yang dibahas di media sosial |
| **Sosial Media** | LinkedIn, Instagram, Facebook, Twitter |
| **Kontak** | Nomor telepon, email |

### Confidence Scoring

Setiap field memiliki `_source` field yang menyimpan URL/platform sumber data. `overall_confidence` dihitung dari `fields_found / fields_total`.

---

## 12. Audiensi Module

Mengotomasi penjadwalan rapat formal (audiensi) dengan rektor.

### Alur Lengkap

1. **Trigger** — GOT_NUMBER dari outreach conversation
2. **QUEUED** — record dibuat, menunggu persetujuan
3. **Auto-approve** — jika `AUTO_APPROVE_AUDIENSI=true`, otomatis approve setelah `AUTO_APPROVE_DELAY_MINUTES`
4. **APPROVED** — ReAct agent generate draft pesan awal + surat audiensi PDF
5. **INITIAL_SENT** — Pesan dikirim ke kontak sekretariat
6. **WAITING_REPLY** — Menunggu respons
7. **SCHEDULING** — Negosiasi jadwal (agent extract tanggal/waktu)
8. **SCHEDULED** — Jadwal disepakati, disimpan ke DMS
9. **ZOOM_SENT** — Link Zoom dikirim, proses selesai

### Generate Surat Audiensi

- Template `.docx` di-upload lewat `/audiensi/template/upload`
- Placeholder: `{{RECTOR_NAME}}`, `{{UNIVERSITY_NAME}}`, `{{DATE}}`, `{{TIME}}`, `{{ZOOM_LINK}}`, dll
- Konversi ke PDF via LibreOffice (headless) atau `docx2pdf`
- Tersimpan di `data/audiensi_docs/`

### DMS Integration

- Jadwal audiensi yang sudah `SCHEDULED` di-sync ke DMS MySQL
- DMS mengirimkan reminder WhatsApp H-`DMS_REMINDER_HOURS_BEFORE` (default 24 jam)
- Gemini riset background untuk setiap jadwal H-1 s/d H-3 (jika `DMS_RESEARCH_ENABLED`)

---

## 13. WhatsApp Service (Node.js)

### Semua REST Endpoint WA Service

Service berjalan di port 3100 (internal) / 3110 (host Docker).

| Method | Path | Deskripsi |
|--------|------|-----------|
| POST | `/send` | Kirim pesan teks (human-like typing indicator, random delay) |
| POST | `/send-document` | Kirim dokumen/file (base64 + mimetype) |
| GET | `/qr` | QR code device (query: `device_id`) |
| POST | `/logout` | Logout device atau semua device |
| GET | `/status` | Status semua device + antiban + queue stats |
| GET | `/queue/status` | Statistik antrian per device |
| DELETE | `/queue/cleanup` | Hapus pesan lama dari antrian (query: `daysOld`, default 7) |
| POST | `/webhook/register` | Daftar URL webhook untuk event masuk |
| POST | `/restart` | Restart koneksi device |
| GET | `/devices` | Daftar semua device |
| POST | `/devices` | Buat device baru (idempotent) |
| POST | `/devices/:id/connect` | Hubungkan device |
| POST | `/devices/:id/disconnect` | Putuskan device |
| POST | `/devices/:id/recover` | Force recovery auth device |
| GET | `/devices/:id/qr` | QR code device spesifik |
| DELETE | `/devices/:id` | Hapus device permanen |
| GET | `/devices/:id/status` | Status device + antiban + queue |
| GET | `/devices/:id/messages` | Pesan device (filter: status) |
| GET | `/devices/:id/antiban` | Status anti-ban device |
| POST | `/devices/:id/antiban/pause` | Pause anti-ban |
| POST | `/devices/:id/antiban/resume` | Resume anti-ban |
| POST | `/devices/:id/antiban/reset` | Reset state anti-ban |

### 13.2 Device Manager

**Struktur Auth Store:**
```
whatsapp-service/
├── auth_store_device_1/    ← credentials + signal keys device 1
├── auth_store_device_2/
├── ...
└── auth_store_device_5/
```

> **JANGAN HAPUS** folder `auth_store_device_*` — berisi kredensial sesi WhatsApp aktif.

**Device State (TypeScript interface):**

```typescript
interface DeviceState {
  id: string
  name: string
  phoneNumber: string | null
  authStorePath: string
  connectionState: 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'ERROR'
  sock: WASocket | null         // Baileys WebSocket
  latestQr: string | null       // QR code sebagai data URL
  reconnectAttempt: number      // maks 15 sebelum berhenti
  userDisconnected: boolean     // cegah auto-reconnect jika user yang disconnect
  metrics: {
    messagesSent: number
    messagesFailed: number
    lastMessageAt: Date | null
  }
}
```

**Inisialisasi Device:**
1. Load dari SQLite saat startup
2. Legacy migration: seed `device_1` s/d `device_5` jika auth file ada di disk
3. Hanya device yang punya auth file yang auto-connect
4. Max reconnect attempts: 15

**Konstanta Penting:**
```
PENDING_MESSAGES_TTL_MS: 1,800,000 (30 menit)
CLEANUP_INTERVAL_MS: 300,000 (5 menit)
MAX_MESSAGE_RETRY_ATTEMPTS: 3
MAX_WEBHOOK_RETRY_ATTEMPTS: 5
TYPING_SPEED: 40-70 ms/karakter
TYPING_DURATION: 3.000-15.000 ms
```

### 13.3 Anti-Ban System

#### Batas Hard (Tidak Bisa Dibypass)

| Batas | Nilai Default |
|-------|--------------|
| Pesan per menit | 6 |
| Pesan per jam | 120 |
| Pesan per hari | 500 |
| Pesan identik dalam 6 jam | 2 |
| Delay minimum antar pesan | 2.500 ms |
| Delay maksimum antar pesan | 8.000 ms |
| Delay ke kontak baru | +5.000 ms |

#### Warm-Up Periode (Device Baru)

| Hari | Limit Harian |
|------|-------------|
| Hari 1 | 15 |
| Hari 2 | ~27 |
| Hari 3 | ~49 |
| Hari 4 | ~88 |
| Hari 5 | ~158 |
| Hari 6 | ~284 |
| Hari 7+ | 500 (batas normal) |

Jika device tidak aktif >72 jam, warm-up restart dari hari 1.

#### Risk Score & Level

Skor 0–100 dihitung dari:
- Error 403 disconnect: +40 per kejadian (maks +60)
- Error 401 logout: +60 per kejadian (maks +80)
- Disconnect >3x/jam: +15
- Disconnect >5x/jam: +30
- Pesan gagal >5x/jam: +20
- Timelock aktif (error 463): +25

| Level | Skor | Tindakan |
|-------|------|---------|
| `low` | 0–29 | Normal |
| `medium` | 30–59 | Kurangi kontak baru |
| `high` | 60–84 | Auto-pause, cooldown |
| `critical` | 85–100 | Hentikan semua outbound |

#### Error Code & Cooldown

| Error Code | Efek |
|-----------|------|
| `463` | Timelock 6 jam (blokir kirim ke kontak baru) |
| `403` | Cooldown 1 jam |
| `401` | Cooldown 15 menit (logged out) |
| `429` / "rate limit" | Cooldown 5 menit |

#### Persistensi State

State anti-ban disimpan ke `data/antiban-state.json`:
- Send events (window 6 jam + 1 hari)
- Failed/disconnect events (window 6 jam)
- Known chats (kontak yang sudah pernah dihubungi)
- Warm-up daily counts (30 hari)
- Timelock status

---

## 14. Blast Campaign (WhatsApp)

### Status Campaign

| Status | Arti |
|--------|------|
| `draft` | Dibuat, belum dijalankan |
| `sending` | Aktif mengirim |
| `paused` | Dijeda (bisa dilanjutkan) |
| `completed` | Semua penerima diproses |
| `cancelled` | Dibatalkan |

### Status Penerima

| Status | Arti |
|--------|------|
| `pending` | Belum terkirim |
| `sent` | Berhasil terkirim |
| `failed` | Gagal (error message tersimpan) |

### Pengaturan Rate Limit & Jadwal

```
active_hours_start: 8    (mulai jam 8 pagi)
active_hours_end: 21     (berhenti jam 9 malam)
lunch_break: 12:00-13:00 (tidak kirim saat makan siang)
peak_hours: 10:00-14:00  (1.15x lebih cepat)
weekend_factor: 0.5      (50% lebih lambat di hari Sabtu/Minggu)
min_delay: 1.000 ms      (tidak bisa lebih cepat dari 1 detik)
```

### Content Variation

Jika `content_variation_enabled=true`, zero-width characters disisipkan secara konsisten (seed: campaign_id + nomor) untuk menghindari deteksi pesan identik oleh WhatsApp. Setiap penerima mendapat pesan yang tampak unik.

### Anti-Ban Integration

Campaign otomatis pause jika WA Service mengembalikan anti-ban block. `auto_resume_enabled=true` akan set timer untuk resume otomatis. Override manual tersedia via `/blast/campaigns/{id}/force-resume`.

---

## 15. Email Blast

### Arsitektur

- **Multiple SMTP accounts** — simpan banyak akun di tabel `email_smtp_accounts` (atau JSON di env `SMTP_ACCOUNTS`)
- **Rotasi akun** — ganti akun setiap `ROTATE_AFTER_N_EMAILS` (default: 50) atau saat akun hit daily limit
- **Cooldown per akun** — minimum `SMTP_ACCOUNT_MIN_COOLDOWN_SECONDS` (default: 60 detik) antar email
- **SOCKS5 proxy** — email dikirim via WARP (`SMTP_SOCKS_ENABLED=true`) untuk rotasi IP
- **IMAP monitoring** — background job cek inbox tiap 30 detik untuk menangkap reply

### Status Penerima Email

| Status | Arti |
|--------|------|
| `pending` | Belum terkirim |
| `sent` | Berhasil terkirim |
| `failed` | Error SMTP |
| `invalid` | Email tidak valid (syntax/MX check gagal) |
| `skipped` | Dilewati |

### Sistem Penomoran Surat

Format nomor surat dikonfigurasi di `email_blast_letter_config`. Format default: `{{NUMBER}}/ASOSIASI/{{YEAR}}`. Setiap email yang dikirim mendapat nomor berurutan yang tersimpan di `email_blast_recipients.letter_number`.

### Quota

- Per-hari per-akun: `SMTP_ACCOUNT_DAILY_LIMIT` (default: 40)
- Global per-hari: `EMAIL_BLAST_DAILY_LIMIT` (default: 200)
- Tracking: `email_blast_daily_quota` table

---

## 16. Autentikasi & RBAC

### Tiga Role

| Role | Permission |
|------|-----------|
| **admin** | `*` (semua akses) |
| **operator** | 24 permission spesifik (lihat di bawah) |
| **viewer** | Read-only untuk semua modul |

### Permission Operator (Lengkap)

```
dashboard.view
pipeline.view, pipeline.manage, pipeline.run
universities.view, universities.manage
conversations.view
audiensi.view, audiensi.manage
whatsapp.view, whatsapp.manage
blast.view, blast.manage
marketing.view, marketing.manage
knowledge.view, knowledge.manage
learning.view, learning.manage
crm.view, crm.manage
logs.view
settings.instagram
```

### Alur Login

1. `POST /auth/login` dengan email + password
2. Validasi via DMS MySQL (`get_active_karyawan_by_email`, timeout 5 detik)
3. Fallback ke SQLite lokal jika MySQL tidak bisa direach (menggunakan `AUTH_FALLBACK_PASSWORD`)
4. Session token 48-byte URL-safe dibuat, di-hash SHA-256, disimpan ke `auth_sessions`
5. Cookie `dms_marketing_session` di-set (HTTP-only, TTL: `AUTH_SESSION_TTL_HOURS` = 12 jam)
6. Setiap request: middleware extract cookie → validate token → inject user ke request context

### Bootstrap Admin Pertama

```bash
# Cek apakah sudah bootstrap
GET /auth/bootstrap-status

# Jika belum, buat admin pertama
POST /auth/setup
Body: {"email": "admin@domain.com", "password": "..."}
```

### Role Request Flow

User dengan role `viewer` bisa request upgrade ke `operator`:
1. `POST /auth/role-requests` dengan `requested_role_key: "operator"`
2. Admin lihat di `GET /auth/role-requests`
3. Admin approve (`POST /auth/role-requests/{id}/approve`) atau reject

---

## 17. Frontend (React)

### Tech Stack

- React 18, React Router 6
- TanStack React Query 5 (state management + caching)
- Tailwind CSS 3
- Lucide Icons
- Axios (HTTP client)
- Driver.js (guided tour)
- WebSocket (real-time updates)

### 32 Halaman

| File | Fitur |
|------|-------|
| `DashboardPage.tsx` | Statistik ringkasan dan widget |
| `PipelinePage.tsx` | Kontrol pipeline agent, log aktivitas |
| `UniversitiesPage.tsx` | Tabel universitas, filter, bulk action |
| `UniversityDetailPage.tsx` | Detail, kontak, post IG per universitas |
| `UniversityGroupsPage.tsx` | Manajemen grup universitas |
| `ConversationsPage.tsx` | Daftar percakapan WhatsApp |
| `ConversationDetailPage.tsx` | Riwayat chat, state, reasoning agent |
| `WhatsAppPage.tsx` | Status device, QR code, anti-ban |
| `BlastCampaignsPage.tsx` | Daftar campaign blast WA |
| `BlastCampaignDetailPage.tsx` | Detail campaign, progress, penerima |
| `EmailBlastPage.tsx` | Dashboard email blast |
| `EmailBlastCampaignsPage.tsx` | Daftar campaign email |
| `EmailBlastCampaignDetailPage.tsx` | Detail campaign email, penerima, inbox |
| `AudiensiQueuePage.tsx` | Antrian audiensi |
| `AudiensiDetailPage.tsx` | Detail audiensi, approval, PDF |
| `DmsSchedulesPage.tsx` | Jadwal dari DMS |
| `DmsScheduleDetailPage.tsx` | Detail jadwal DMS, riset, follow-up |
| `MarketingClientsPage.tsx` | Daftar klien marketing |
| `MarketingClientPage.tsx` | Klien marketing dalam satu group |
| `MarketingClientDetailPage.tsx` | Detail klien, kandidat IG, kontak |
| `MarketingGetContactPage.tsx` | Aksi handoff ke blast/outreach |
| `CrmPage.tsx` | Daftar request profiling CRM |
| `CrmDetailPage.tsx` | Profil CRM lengkap |
| `LearningPage.tsx` | Lessons & analisis percakapan |
| `KnowledgeBasePage.tsx` | Manajemen knowledge items |
| `PhoneNumbersPage.tsx` | Semua nomor yang diekstrak |
| `SettingsPage.tsx` | Semua konfigurasi sistem |
| `LoginPage.tsx` | Form login |
| `OAuthCallbackPage.tsx` | Handle OAuth callback ChatGPT |
| `LogsPage.tsx` | Log aktivitas sistem |
| `ApiLogsPage.tsx` | Log API calls ke LLM |
| `DbMigrationPage.tsx` | Tools migrasi database |

### Pola Frontend (Konsistensi)

```
frontend/src/
├── pages/          ← Komponen halaman
├── hooks/          ← useMarketing, useBlast, useConversations, dll
├── api/            ← 26 modul API client (axios)
├── components/     ← UI components per fitur
├── tours/          ← Konfigurasi guided tour per halaman
└── lib/
    └── queryKeys.ts ← Centralized React Query cache keys
```

**Pattern axios:** Single instance dengan `baseURL: '/api'`, `withCredentials: true`. Response 401 broadcast event `app:unauthorized` → redirect ke login.

**Pattern React Query:**
- `useQuery` untuk reads (fallback polling 3 detik saat WebSocket disconnect)
- `useMutation` untuk writes, auto-invalidate cache pada success

### Tour System (Driver.js)

- **Global sidebar tour** (`useTour.ts`): jalankan sekali setelah wizard completion
- **Per-page tour** (`usePageTour.ts`): auto-start 800ms setelah kunjungan pertama

**Menambah tour ke halaman baru:**
1. Tambah `data-tour="pagename-element"` ke 3–5 elemen kunci
2. Buat `frontend/src/tours/pagename.tour.ts`
3. Panggil `usePageTour('pagename', STEPS)` di komponen halaman

**Re-show tour setelah UI berubah:** ganti version key di `usePageTour.ts` (`page_tour_v1_` → `page_tour_v2_`)

---

## 18. Database Schema Lengkap

Database: SQLite di `data/getcontact.db`. WAL mode diaktifkan. Schema auto-create saat startup via `init_db()`.

### Kelompok Tabel

#### Core Universities (1 tabel)

**`universities`**
```sql
id INTEGER PK AUTOINCREMENT
name TEXT NOT NULL
pddikti_id TEXT UNIQUE
province TEXT
website TEXT
ig_handle TEXT
ig_verified BOOLEAN DEFAULT 0
secretariat_phone TEXT
email_kampus TEXT
email_source TEXT
rector_name TEXT
student_count INTEGER
status TEXT DEFAULT 'pending'
  -- nilai: pending, ig_found, ig_scraped, contacted, failed
enabled BOOLEAN DEFAULT 1
dms_univ_id INTEGER
created_at TIMESTAMP
updated_at TIMESTAMP
last_ig_scraped_at TIMESTAMP
bem_ig_handle TEXT
bem_discovery_status TEXT DEFAULT 'pending'
bem_discovery_attempts INTEGER DEFAULT 0
```
Index: `status`, `enabled`, `dms_univ_id`

#### IG Scraping (4 tabel)

**`ig_contacts`**
```sql
id INTEGER PK AUTOINCREMENT
university_id INTEGER REFERENCES universities(id)
phone_number TEXT NOT NULL
contact_name TEXT
source_post_url TEXT
source_image_url TEXT
created_at TIMESTAMP
has_person_name BOOLEAN DEFAULT 1
manual_contacted BOOLEAN DEFAULT 0
UNIQUE(university_id, phone_number)
```

**`ig_posts`**
```sql
id INTEGER PK AUTOINCREMENT
university_id INTEGER NOT NULL
post_url TEXT NOT NULL
image_url TEXT
caption TEXT
post_timestamp TEXT
phone_extracted BOOLEAN DEFAULT 0
phones_found INTEGER DEFAULT 0
source_ig_handle TEXT
source_ig_type TEXT
created_at TIMESTAMP
image_data TEXT        -- base64 cache (legacy)
image_bucket_url TEXT  -- URL di S3/GCS/R2
UNIQUE(university_id, post_url)
```

**`ig_accounts`** — akun IG untuk login scraping
```sql
id, username (UNIQUE), password, enabled, notes,
login_status, last_login_test, created_at, updated_at
```

**`university_related_igs`** — akun BEM dan terkait
```sql
id, university_id, ig_handle, relation_type (DEFAULT 'bem'),
source, confidence, posts_scraped, discovered_at
UNIQUE(university_id, ig_handle)
```

#### Conversations & Outreach (4 tabel)

**`conversations`**
```sql
id, university_id, contact_phone NOT NULL,
state DEFAULT 'PENDING', message_history TEXT DEFAULT '[]',
extracted_number, extracted_contact_name, extracted_contact_role,
last_message_at, next_action_at, attempt_count DEFAULT 0,
followup_count DEFAULT 0, is_test DEFAULT 0,
created_at, agent_reasoning, last_response_id
```
Index: `contact_phone`

**`conversation_analyses`** — hasil analisis post-conversation
```sql
id, conversation_id, outcome, total_messages, total_attempts,
duration_hours, province, success_factors, failure_factors,
contact_personality, effective_strategies, recommended_improvements,
summary, source DEFAULT 'outreach', processed DEFAULT 0, created_at
```

**`audiensi_conversations`**
```sql
id, university_id, source_conversation_id, contact_phone,
contact_role, rector_name, state DEFAULT 'QUEUED',
message_history, pdf_path, initial_message_draft,
scheduled_datetime, zoom_link, agent_reasoning,
attempt_count, followup_count, last_message_at,
approved_at, approved_by, created_at, last_response_id
```

**`lessons`** — lessons yang diekstrak dari analisis
```sql
id, situation_type, insight, recommended_strategy,
province, success_rate, example_count, confidence DEFAULT 0.5,
is_active DEFAULT 1, source_analysis_ids,
created_at, updated_at, embedding BLOB
```

#### Auth & Sessions (4 tabel)

**`auth_user_roles`**
```sql
id, dms_user_id, user_email, user_name, role_key,
is_active DEFAULT 1, granted_by_email, created_at, updated_at
UNIQUE(dms_user_id, role_key)
```

**`auth_sessions`**
```sql
session_hash TEXT PK, dms_user_id, user_email, user_name,
dms_user_level, expires_at, created_at, last_seen_at,
revoked_at, user_agent, ip_address
```

**`auth_audit_logs`**
```sql
id, action, actor_dms_user_id, actor_email,
subject_dms_user_id, subject_email, role_key,
success DEFAULT 1, detail, ip_address, user_agent, created_at
```

**`auth_role_upgrade_requests`**
```sql
id, requester_dms_user_id, requester_email, requester_name,
current_role_key, requested_role_key, status DEFAULT 'pending',
request_note, reviewed_by_*, review_note, reviewed_at,
created_at, updated_at
```

#### Blast Campaigns (2 tabel)

**`blast_campaigns`**
```sql
id, name, template_message, device_id DEFAULT 'device_1',
delay_between_ms DEFAULT 5000,
human_delay_min_ms DEFAULT 2000, human_delay_max_ms DEFAULT 8000,
content_variation_enabled DEFAULT 1,
schedule_enabled DEFAULT 1, schedule_timezone DEFAULT 'Asia/Jakarta',
active_hours_start DEFAULT 8, active_hours_end DEFAULT 21,
peak_hours_start DEFAULT 10, peak_hours_end DEFAULT 14,
lunch_break_start DEFAULT 12, lunch_break_end DEFAULT 13,
weekend_factor REAL DEFAULT 0.5,
auto_resume_enabled DEFAULT 1, auto_resume_at, paused_reason,
status DEFAULT 'draft',
total_recipients, sent_count, failed_count,
created_by_*, started_by_*, timestamps, antiban_override DEFAULT 0
```

**`blast_recipients`**
```sql
id, campaign_id REFERENCES blast_campaigns CASCADE,
contact_id, university_id, phone_number, contact_name,
university_name, rendered_message, status DEFAULT 'pending',
error_message, sent_at, created_at
UNIQUE(campaign_id, phone_number)
```

#### Email Blast (7 tabel)

**`email_blast_campaigns`**, **`email_blast_recipients`**, **`email_blast_daily_quota`**, **`email_blast_letter_config`**, **`email_inbox_cache`**, **`email_sent_cache`**, **`email_outbox`**

#### OSINT (5 tabel)

**`osint_profiles`**, **`osint_contacts`**, **`osint_social_media`**, **`osint_news`**, **`osint_runs`**

#### CRM (4 tabel)

**`crm_requests`**, **`crm_pic_profiles`** (50+ field per profil), **`crm_profile_runs`**, **`crm_profile_sources`**

#### Marketing Module (8 tabel)

**`marketing_groups`**, **`marketing_clients`**, **`marketing_contact_results`**, **`marketing_contact_handoffs`**, **`marketing_ig_posts`**, **`marketing_ig_candidates`**, **`marketing_orchestration_runs`**, **`marketing_orchestration_evidence`**

#### Lainnya (6 tabel)

**`daily_quota`**, **`strategy_metrics`**, **`config`**, **`user_wa_devices`**, **`knowledge_items`**, **`api_call_logs`**, **`pipeline_logs`**, **`university_groups`**, **`university_group_members`**, **`contact_memory`**

### Menambah Kolom Baru (Pattern Inline Migration)

```python
# Di dalam init_db() di db.py:
cursor = await db.execute("PRAGMA table_info(nama_tabel)")
columns = {row[1] for row in await cursor.fetchall()}
if "nama_kolom_baru" not in columns:
    await db.execute(
        "ALTER TABLE nama_tabel ADD COLUMN nama_kolom_baru TEXT DEFAULT ''"
    )
```

Schema bersifat **append-only** — kolom tidak pernah di-drop.

---

## 19. Config Registry (Semua Setting)

Semua setting yang bisa diubah via UI Settings → dapat diakses via `GET/PATCH /config`.

### Group: Credentials

| Key | Type | Default | Deskripsi |
|-----|------|---------|-----------|
| `OPENAI_API_KEY` | STRING | — | OpenAI API key (wajib untuk embeddings + fallback) |
| `SERPER_API_KEY` | STRING | — | Legacy Google Search API (DDG lebih diutamakan) |
| `IG_SESSION_ID` | STRING | — | Session IG, pisah koma untuk rotasi |
| `BRAVE_API_KEY` | STRING | — | Brave Search API |
| `APIFY_API_KEY` | STRING | — | Apify.com scraper |
| `SCRAPINGBOT_USERNAME` | STRING | — | ScrapingBot username |
| `SCRAPINGBOT_API_KEY` | STRING | — | ScrapingBot API key |
| `SCRAPINGBOT_ACCOUNTS` | STRING | — | JSON array akun ScrapingBot untuk rotasi |

### Group: Rate Limiting

| Key | Type | Default | Range | Deskripsi |
|-----|------|---------|-------|-----------|
| `MAX_DAILY_CONVERSATIONS` | INT | 20 | 1–500 | Maks percakapan baru per hari |
| `MIN_MESSAGE_GAP_SECONDS` | INT | 300 | 10–3600 | Jeda minimum antar pesan outreach |

### Group: Instagram

| Key | Type | Default | Range | Deskripsi |
|-----|------|---------|-------|-----------|
| `MAX_IG_PROFILES_PER_DAY` | INT | 200 | 1–1000 | Maks scrape profil IG per hari |
| `IG_REQUEST_DELAY_SECONDS` | INT | 30 | 10–120 | Jeda antar request ke IG API |
| `TARGET_POSTS_PER_UNIVERSITY` | INT | 100 | 10–500 | Target post yang di-scrape per universitas |

### Group: Playwright Browser

| Key | Type | Default | Range | Deskripsi |
|-----|------|---------|-------|-----------|
| `PW_HEADLESS` | BOOL | true | — | Mode headless (true untuk production) |
| `PW_MIN_DELAY_SECONDS` | INT | 8 | 3–60 | Delay minimum antar aksi browser |
| `PW_MAX_DELAY_SECONDS` | INT | 20 | 5–120 | Delay maksimum antar aksi browser |
| `PW_PROFILES_PER_SESSION` | INT | 15 | 3–50 | Profil per session sebelum restart browser |
| `PW_DAILY_LIMIT` | INT | 100 | 10–500 | Maks scrape via Playwright per hari |
| `PW_ACCOUNT_COOLDOWN_MINUTES` | INT | 30 | 5–240 | Cooldown akun setelah rate limit |
| `INSTALOADER_ENABLED` | BOOL | true | — | Aktifkan Instaloader sebagai fallback |
| `INSTALOADER_REQUEST_DELAY` | FLOAT | 2.0 | 0.5–30 | Delay antar request Instaloader (detik) |
| `PROXY_POOL_ENABLED` | BOOL | false | — | Aktifkan rotasi proxy WARP |
| `PROXY_POOL_WARP_URLS` | STRING | — | — | SOCKS5 URLs (env-only) |

### Group: Outreach

| Key | Type | Default | Range | Deskripsi |
|-----|------|---------|-------|-----------|
| `OUTREACH_START_HOUR` | INT | 7 | 0–23 | Jam mulai outreach (WIB) |
| `OUTREACH_END_HOUR` | INT | 22 | 1–24 | Jam selesai outreach (WIB) |
| `CHATBOT_ENABLED` | BOOL | true | — | Aktifkan chatbot penjawab |

### Group: AI Agent

| Key | Type | Default | Deskripsi |
|-----|------|---------|-----------|
| `USE_AGENTIC_REPLIES` | BOOL | true | ReAct agent untuk membalas pesan masuk |
| `USE_AGENTIC_INITIAL` | BOOL | false | ReAct agent untuk pesan pertama |
| `USE_AGENTIC_FOLLOWUPS` | BOOL | true | ReAct agent untuk follow-up |
| `LEARNING_ENABLED` | BOOL | true | Analisis percakapan dan ekstrak lessons |
| `AGENT_MODEL` | STRING | gpt-5.4 | Model LLM untuk agent (model picker) |
| `AGENT_TEMPERATURE` | FLOAT | 0.4 | 0.0–2.0 — temperature model |
| `AGENT_MAX_TOKENS` | INT | 500 | 100–4000 — maks token per respons |
| `AGENT_MAX_TOOL_ITERATIONS` | INT | 10 | 1–20 — maks iterasi ReAct loop |
| `AGENT_PLANNING_ENABLED` | BOOL | true | Pre-compute strategi sebelum ReAct loop |
| `MARKETING_GEMINI_ENABLED` | BOOL | true | Gemini grounding untuk marketing gap-fill |
| `MARKETING_ORCHESTRATOR_MODEL` | STRING | gpt-5.4 | Model orchestrator marketing |
| `MARKETING_SUB_AGENT_MODEL` | STRING | gpt-5.4 | Model sub-agent marketing |
| `MARKETING_AGENT_MAX_TOOL_ITERATIONS` | INT | 15 | 1–50 — maks iterasi marketing agent |
| `CHATGPT_OAUTH_ENABLED` | BOOL | false | Aktifkan Codex OAuth (ChatGPT Plus) |
| `CHATGPT_OAUTH_FALLBACK_TO_API` | BOOL | true | Fallback ke API jika Codex error |
| `CHATGPT_OAUTH_RATE_LIMIT_COOLDOWN_SECONDS` | INT | 900 | 60–7200 — cooldown setelah 429 |
| `API_LOG_RETENTION_DAYS` | INT | 7 | 1–90 — berapa hari log API disimpan |

### Group: Message Queue

| Key | Type | Default | Range | Deskripsi |
|-----|------|---------|-------|-----------|
| `MAX_AI_CONCURRENT` | INT | 3 | 1–20 | Maks task AI concurrent (restart diperlukan) |
| `SEND_INTERVAL_MS` | INT | 3000 | 500–30000 | Interval kirim pesan WA (ms) |

### Group: Audiensi

| Key | Type | Default | Deskripsi |
|-----|------|---------|-----------|
| `AUDIENSI_ENABLED` | BOOL | false | Aktifkan fitur audiensi Phase 2 |
| `AUTO_APPROVE_AUDIENSI` | BOOL | false | Auto-approve audiensi yang masuk antrian |
| `AUTO_APPROVE_DELAY_MINUTES` | INT | 60 | 5–1440 — delay sebelum auto-approve |
| `AUDIENSI_FOLLOWUP_AFTER_HOURS` | INT | 48 | 1–168 — jam sebelum follow-up audiensi |
| `AUDIENSI_MAX_FOLLOWUPS` | INT | 3 | 1–10 — maks percobaan follow-up |
| `AUDIENSI_ZOOM_LINK_TEMPLATE` | STRING | — | Template link Zoom |
| `AUDIENSI_PDF_TEMPLATE_PATH` | STRING | — | Path template .docx kustom |

### Group: DMS Integration

| Key | Type | Default | Deskripsi |
|-----|------|---------|-----------|
| `DMS_MYSQL_HOST` | STRING | — | Host DMS MySQL (env-only) |
| `DMS_MYSQL_PORT` | INT | 3306 | Port DMS MySQL (env-only) |
| `DMS_MYSQL_USER` | STRING | — | Username DMS (env-only) |
| `DMS_MYSQL_PASSWORD` | STRING | — | Password DMS (env-only) |
| `DMS_MYSQL_DATABASE` | STRING | — | Nama DB DMS (env-only) |
| `DMS_SYNC_ENABLED` | BOOL | false | Aktifkan sinkronisasi DMS |
| `DMS_SYNC_INTERVAL_MINUTES` | INT | 30 | 5–1440 — interval sync |
| `DMS_CONTACT_SYNC_ENABLED` | BOOL | false | Auto-sync kontak ke DMS |
| `DMS_REMINDER_ENABLED` | BOOL | false | Kirim reminder WA dari DMS |
| `DMS_REMINDER_HOURS_BEFORE` | INT | 24 | 1–72 — jam sebelum reminder |
| `GEMINI_API_KEY` | STRING | — | API key Google Gemini |
| `DMS_RESEARCH_ENABLED` | BOOL | false | Auto-riset jadwal audiensi DMS |
| `DMS_RESEARCH_HOUR` | INT | 18 | 0–23 — jam riset harian (WIB) |

### Group: Pipeline Scheduler

| Key | Type | Default | Range | Deskripsi |
|-----|------|---------|-------|-----------|
| `AGENT_HANDLE_FINDER_INTERVAL_HOURS` | INT | 1 | 1–24 | Interval Agent 1 |
| `AGENT_POST_SCRAPER_INTERVAL_HOURS` | INT | 2 | 1–24 | Interval Agent 2 |
| `AGENT_PHONE_EXTRACTOR_INTERVAL_MINUTES` | INT | 15 | 5–120 | Interval Agent 3 |
| `AGENT_BEM_DISCOVERY_INTERVAL_HOURS` | INT | 1 | 1–24 | Interval Agent 4 |

### Group: General (Email Blast Settings)

| Key | Type | Default | Deskripsi |
|-----|------|---------|-----------|
| `SMTP_HOST` | STRING | — | SMTP server |
| `SMTP_PORT` | INT | 465 | Port (465=SSL, 587=TLS) |
| `SMTP_USERNAME` | STRING | — | Email pengirim |
| `SMTP_PASSWORD` | STRING | — | Password SMTP |
| `SMTP_USE_SSL` | BOOL | true | Aktifkan SSL |
| `SMTP_ACCOUNTS` | STRING | — | JSON array akun rotasi (env-only) |
| `ROTATE_AFTER_N_EMAILS` | INT | 50 | Ganti akun setelah N email |
| `SMTP_ACCOUNT_MIN_COOLDOWN_SECONDS` | INT | 60 | Cooldown antar email per akun |
| `SMTP_ACCOUNT_DAILY_LIMIT` | INT | 40 | Maks email per akun per hari |
| `EMAIL_BLAST_DELAY_JITTER_MS` | INT | 5000 | Jitter acak antar email (ms) |
| `VALIDATE_EMAIL_BEFORE_SEND` | BOOL | true | Validasi syntax + MX sebelum kirim |
| `IMAP_HOST` | STRING | — | IMAP server |
| `IMAP_PORT` | INT | 993 | Port IMAP (993=SSL, 143=TLS) |
| `IMAP_USERNAME` | STRING | — | Username IMAP |
| `IMAP_PASSWORD` | STRING | — | Password IMAP |
| `IMAP_USE_SSL` | BOOL | true | SSL untuk IMAP |
| `EMAIL_BLAST_DAILY_LIMIT` | INT | 200 | Maks email global per hari |
| `EMAIL_BLAST_INBOX_WATCH_ENABLED` | BOOL | true | IMAP polling tiap 30 detik |

---

## 20. Environment Variables

Copy `.env.example` → `.env` untuk development, `.env.production.example` → `.env.production` untuk Docker.

### Wajib

```env
OPENAI_API_KEY=sk-...          # Wajib untuk embeddings + fallback LLM
```

### ChatGPT OAuth (Opsional — untuk akses via ChatGPT Plus)

```env
CHATGPT_OAUTH_ENABLED=true
CHATGPT_OAUTH_FALLBACK_TO_API=true
CHATGPT_OAUTH_RATE_LIMIT_COOLDOWN_SECONDS=900
CHATGPT_OAUTH_ORIGINATOR=codex_cli_rs
OAUTH_CALLBACK_URL=http://localhost:1455/auth/callback
```

### Sentry Error Tracking (Opsional)

```env
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_RELEASE=           # Di-inject CI: $CI_COMMIT_SHORT_SHA
SENTRY_ENABLE_LOGS=false
SENTRY_DEBUG_ENABLED=false
```

### Internal Service URLs

```env
WA_SERVICE_URL=http://whatsapp:3100
WEBHOOK_URL=http://orchestrator:8000/webhook/incoming
DATABASE_PATH=data/getcontact.db
DDG_PROXY=socks5h://warp:1080
DDGS_PROXY=socks5h://warp:1080
PINCHTAB_URL=http://pinchtab:9867
```

### Instagram & Scraping

```env
IG_SESSION_ID=session1,session2,session3   # Rotasi otomatis
APIFY_API_KEY=apify_api_...
SCRAPINGBOT_USERNAME=...
SCRAPINGBOT_API_KEY=...
```

### Email (SMTP / IMAP)

```env
SMTP_HOST=mail.domain.com
SMTP_PORT=465
SMTP_USERNAME=user@domain.com
SMTP_PASSWORD=...
SMTP_USE_SSL=true
SMTP_SOCKS_ENABLED=true
SMTP_SOCKS_HOST=warp
SMTP_SOCKS_PORT=1080
IMAP_HOST=mail.domain.com
IMAP_PORT=993
IMAP_USERNAME=user@domain.com
IMAP_PASSWORD=...
IMAP_USE_SSL=true
```

### Object Storage (IG Image Cache)

```env
# Pilih salah satu: gcs, s3, r2 (default: none = simpan lokal)
STORAGE_BACKEND=gcs

# GCS
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
GCS_BUCKET_NAME=bucket-name

# AWS S3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=...
AWS_S3_REGION=ap-southeast-1

# Cloudflare R2
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=...
R2_ENDPOINT=https://...r2.cloudflarestorage.com
```

### DMS MySQL Integration (Opsional)

```env
DMS_MYSQL_HOST=...
DMS_MYSQL_PORT=3306
DMS_MYSQL_USER=...
DMS_MYSQL_PASSWORD=...
DMS_MYSQL_DATABASE=...
```

### Auth

```env
AUTH_COOKIE_NAME=dms_marketing_session
AUTH_SESSION_TTL_HOURS=12
AUTH_COOKIE_SECURE=false          # Set true jika pakai HTTPS
AUTH_DEFAULT_PASSWORD=...         # Password login dashboard
AUTH_DEFAULT_ROLE=viewer
AUTH_FALLBACK_PASSWORD=...        # Password fallback jika MySQL down
```

### Operasional

```env
MAX_DAILY_CONVERSATIONS=20
MIN_MESSAGE_GAP_SECONDS=300
OUTREACH_START_HOUR=7
OUTREACH_END_HOUR=22
```

---

## 21. Docker & Deployment

### Layanan Docker Compose

```yaml
Services:
  orchestrator      # Python FastAPI (Dockerfile.orchestrator)
  whatsapp          # Node.js Baileys (Dockerfile.whatsapp)
  frontend          # React static (Dockerfile.frontend)
  warp              # Cloudflare WARP proxy 1 (SOCKS5 port 1080)
  warp2             # Cloudflare WARP proxy 2 (SOCKS5 port 1081)
  pinchtab          # Headless browser (shm_size: 2GB)
  nginx             # Reverse proxy (production only)
```

### Menjalankan

```bash
# Development
docker-compose up -d

# Production (build dari source di server)
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
```

### Volume Penting

```yaml
volumes:
  ./data:/app/data              # SQLite DB, audiensi docs, sessions
  ./whatsapp-service/auth_store_device_*:/app/auth_store_device_*
  warp-data:/var/lib/cloudflare-warp
  pinchtab-data:/data
```

> **JANGAN** hapus volume `auth_store_device_*` — berisi sesi WhatsApp aktif.

### Persyaratan Host untuk WARP

WARP container memerlukan:
- `privileged: true` atau `cap_add: [NET_ADMIN, SYS_MODULE]`
- Device `/dev/net/tun` tersedia di host
- Cek: `ls /dev/net/tun` dan `modprobe tun` jika belum ada

### Dockerfile Highlights

**Orchestrator** (besar karena Playwright + LibreOffice):
- Base: `python:3.11-slim`
- Install: `ca-certificates`, `libreoffice-writer-nogui`, `fonts-dejavu-core`
- Install Playwright: `playwright install --with-deps chromium chromium-headless-shell`
- Size estimasi: ~2–3 GB

**WhatsApp** (ringan):
- Base: `node:20-alpine`
- Multi-stage build: deps → build → runtime
- Size estimasi: ~300 MB

**Frontend** (sangat ringan):
- Base: `node:20-alpine`
- Output: static files di-serve via `serve` package
- Size estimasi: ~150 MB

### OAuth Callback di Production

Untuk ChatGPT OAuth, port 1455 di-bind hanya ke localhost:
```yaml
ports:
  - "127.0.0.1:1455:8000"
```
Login via SSH tunnel: `ssh -L 1455:localhost:1455 user@server`

---

## 22. CI/CD Pipeline

GitLab CI di `.gitlab-ci.yml`. Deploy ke GCP.

### Stages

```
test ──────────────────────────────▶ deploy ──▶ verify
  │
  ├── python_smoke_test (hard gate)
  │   - scripts/test_llm_factory.py
  │   - scripts/test_llm_gateway.py
  │
  ├── frontend_typecheck (hard gate)
  │   - cd frontend && npx tsc --noEmit
  │
  └── whatsapp_test (soft gate, allow_failure: true)
      - cd whatsapp-service && npm test
      - 7 dari 29 test flaky (timer-based)
```

Deploy hanya berjalan jika kedua hard gate (`python_smoke_test` + `frontend_typecheck`) pass.

**Inject variabel saat deploy:**
```bash
SENTRY_RELEASE=$CI_COMMIT_SHORT_SHA
```

---

## 23. Observability & Error Tracking

### Sentry (`orchestrator/observability.py`)

**Aktivasi:** set `SENTRY_DSN` di environment. Tanpa DSN, `init_sentry()` adalah no-op.

**Integrasi otomatis:**
- FastAPI (request/response tracking)
- httpx (outgoing HTTP calls)
- asyncio
- Python logging

**PII Scrubber:**
- Exact-key match: `token`, `key`, `password`, `secret`, `credential` → dimasker
- Auto-mask: email (format `user@domain`) dan nomor telepon Indonesia (`08xx`, `+628xx`) di semua exception dan breadcrumb

**Explicit capture:**
```python
# Di gateway.py untuk Codex auth/upstream errors:
capture_exception(exc)
```

**Trace sampling:** `SENTRY_TRACES_SAMPLE_RATE=0.1` (10%) — hemat quota free tier.

### WebSocket Events (Real-time ke Frontend)

| Event | Kapan dikirim |
|-------|--------------|
| `conversation_changed` | State percakapan berubah |
| `audiensi_auto_approved` | Audiensi auto-approve berhasil |
| `blast_progress` | Update progress blast campaign |
| `email_recipient_updated` | Status penerima email berubah |
| `email_smtp_account_health` | Status health akun SMTP berubah |
| `agent_completed` | Agent pipeline selesai 1 batch |
| `codex_oauth_state` | Status login Codex berubah |

### API Call Logs

Semua panggilan ke LLM dicatat di `api_call_logs`:
- Model yang digunakan
- Prompt tokens, completion tokens, cached tokens
- Tool calls yang dibuat
- System prompt dan pesan yang dikirim
- Retention: `API_LOG_RETENTION_DAYS` hari (default: 7)
- Akses: `GET /api-logs`

### Pipeline Logs

Setiap eksekusi agent dicatat di `pipeline_logs`:
- `items_processed`, `items_success`, `items_failed`
- Duration
- Error jika ada
- Akses: `GET /pipeline/logs`

---

*Dokumentasi ini dibuat dari analisis source code langsung. Update terakhir: April 2026.*
