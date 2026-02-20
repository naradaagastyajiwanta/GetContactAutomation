# Panduan Startup - GetContact AI Agent

Sistem ini terdiri dari 3 service yang harus dijalankan bersamaan:

| Service | Port | Teknologi |
|---------|------|-----------|
| Orchestrator | 8000 | Python FastAPI |
| WhatsApp Service | 3100 | Node.js / TypeScript (Baileys) |
| Frontend | 5173 | React + Vite |

---

## 1. Prasyarat

- **Python 3.11+**
- **Node.js 18+** dan npm
- **OpenAI API Key** (wajib)
- **Serper API Key** (wajib untuk pencarian IG)

---

## 2. Setup Environment

Salin `.env.example` ke `.env` di root project, lalu isi:

```bash
cp .env.example .env
```

Isi minimal yang wajib:

```env
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
```

Opsional:

```env
IG_USERNAME=...
IG_PASSWORD=...
APIFY_API_KEY=...
```

Setting lain bisa dibiarkan default (atau diubah via dashboard Settings nanti).

---

## 3. Install Dependencies

Buka **3 terminal terpisah**. Di masing-masing:

### Terminal 1 - Orchestrator (Python)

```bash
pip install -r requirements.txt
```

### Terminal 2 - WhatsApp Service (Node.js)

```bash
cd whatsapp-service
npm install
```

### Terminal 3 - Frontend (React)

```bash
cd frontend
npm install
```

---

## 4. Jalankan Semua Service

Urutan start **penting** — WhatsApp Service harus jalan duluan sebelum Orchestrator, supaya webhook bisa teregister.

### Terminal 1 - WhatsApp Service (start duluan)

```bash
cd whatsapp-service
npm run dev
```

Tunggu sampai muncul: `WhatsApp service listening on port 3100`

### Terminal 2 - Orchestrator

```bash
python -m uvicorn orchestrator.main:app --port 8000 --reload
```

Tunggu sampai muncul:
```
Database initialized
Webhook registered: http://localhost:8000/webhook/incoming
Orchestrator started on port 8000
```

### Terminal 3 - Frontend

```bash
cd frontend
npm run dev
```

Buka browser: **http://localhost:5173**

---

## 5. Koneksi WhatsApp

1. Buka halaman **WhatsApp** di dashboard (sidebar kiri)
2. Scan **QR Code** yang muncul pakai WhatsApp di HP
3. Tunggu status berubah ke **Connected**
4. QR code akan hilang dan menampilkan nomor telepon yang terkoneksi

> **Catatan:** Session tersimpan di `whatsapp-service/auth_store/`. Selama folder ini ada, tidak perlu scan ulang setelah restart.

---

## 6. Verifikasi Sistem Berjalan

Cek health endpoint:

```bash
curl http://localhost:8000/health
```

Response yang benar:

```json
{
  "status": "ok",
  "whatsapp": { "connected": true, "phoneNumber": "628..." }
}
```

Atau langsung cek dari dashboard — halaman utama menampilkan status semua komponen.

---

## 7. Test Percakapan (Opsional)

Untuk test alur AI end-to-end tanpa menghubungi universitas asli:

1. Buka halaman **WhatsApp** di dashboard
2. Scroll ke card **Test Conversation**
3. Masukkan nomor WA pribadi kamu
4. Klik **Start Test Conversation**
5. Kamu akan menerima pesan WA dari bot
6. Balas pesan tersebut — bot akan memproses dan merespons otomatis
7. Lihat percakapan lengkap di halaman **Conversations** (ada badge "Test")

---

## 8. Menjalankan Pipeline

Pipeline bisa dijalankan otomatis (via scheduler) atau manual dari dashboard:

### Otomatis
Scheduler sudah aktif saat Orchestrator start:
- **Outreach** setiap 30 menit saat jam aktif (default 07:00-22:00 WIB)
- **Follow-up** setiap jam
- **Agent 1** (cari IG handle) setiap 2 jam
- **Agent 2** (scrape post) setiap 3 jam
- **Agent 3** (extract nomor telepon) setiap jam

### Manual (via Dashboard)
Halaman **Pipeline** menyediakan tombol trigger untuk masing-masing agent.

### Manual (via API)

```bash
# Kumpulkan universitas dari PDDIKTI
curl -X POST http://localhost:8000/pipeline/collect-universities

# Agent 1: Cari IG handle
curl -X POST http://localhost:8000/pipeline/find-ig-handles

# Agent 2: Scrape post IG
curl -X POST http://localhost:8000/pipeline/scrape-ig-posts

# Agent 3: Extract nomor telepon dari gambar
curl -X POST http://localhost:8000/pipeline/extract-phones

# Mulai outreach WA
curl -X POST http://localhost:8000/outreach/start
```

---

## 9. Pause / Resume

Bot bisa di-pause kapan saja (menghentikan outreach otomatis dan auto-reply):

```bash
curl -X POST http://localhost:8000/control/pause
curl -X POST http://localhost:8000/control/resume
```

Atau lewat tombol di dashboard.

---

## 10. Stop Semua Service

Tekan `Ctrl+C` di masing-masing terminal (urutan tidak penting).

---

## Troubleshooting

| Masalah | Solusi |
|---------|--------|
| QR code tidak muncul | Restart WhatsApp Service, pastikan port 3100 tidak dipakai |
| Webhook not registered | Pastikan WA Service sudah running sebelum Orchestrator start |
| Bot tidak membalas pesan | Cek apakah bot di-pause (`GET /control/status`). Cek log Orchestrator |
| "Unknown number, ignoring" | Nomor pengirim tidak punya conversation record. Gunakan Test Conversation untuk testing |
| Database error saat start | Hapus `data/getcontact.db` dan restart — schema akan dibuat ulang (data hilang) |
| WhatsApp minta scan ulang | Session expired. Hapus `whatsapp-service/auth_store/` lalu scan QR baru |
