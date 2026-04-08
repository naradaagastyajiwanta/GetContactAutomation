# Project Conventions

Dibaca oleh wave-planner sebelum merencanakan implementasi fitur baru.

---

## Frontend: Onboarding Tour System

Setiap halaman baru yang ditambahkan ke frontend **wajib** disertai tour kontekstual.

### 3 langkah wajib saat membuat halaman baru:

1. **Tambah `data-tour` attributes** ke 3–5 elemen kunci di page component
   - Naming convention: `data-tour="namahalaman-elemen"` (e.g. `data-tour="pipeline-stage-stats"`)
   - Target: page header/actions, filter panel, tabel/list utama, tombol aksi utama

2. **Buat file config** di `frontend/src/tours/namahalaman.tour.ts`
   - Array of `PageTourStep` (extends `DriveStep` dari driver.js)
   - Tambah field `permission?: string` untuk steps yang butuh role tertentu

3. **Panggil hook** di dalam page component:
   ```tsx
   import { usePageTour } from '../hooks/usePageTour'
   import { NAMA_TOUR_STEPS } from '../tours/namahalaman.tour'

   export default function NamaPage() {
     usePageTour('namahalaman', NAMA_TOUR_STEPS)
     // ...
   }
   ```

### Storage
- Global tour (sidebar): `onboarding_v1_{userId}` — selesai setelah wizard wizard
- Per-page tour: `page_tour_v1_{pageId}_{userId}` — auto-start sekali per halaman per user

### Bumping versi (re-show setelah major UI change)
- Semua halaman: ganti prefix `page_tour_v1_` → `page_tour_v2_` di `usePageTour.ts`
- Satu halaman saja: ubah `pageId` string (e.g. `'pipeline'` → `'pipeline_v2'`)

### Role filtering
- Steps admin-only di global tour: bungkus dengan `hasPermission('settings.manage')` di `useTour.ts`
- Steps operator-only di page tour: tambah `permission: 'feature.manage'` di step config

### File locations
- Hook: `frontend/src/hooks/usePageTour.ts`
- Global tour: `frontend/src/hooks/useTour.ts`
- Tour configs: `frontend/src/tours/*.tour.ts`
- Driver.js CSS: di-import di `frontend/src/main.tsx`

---

## Frontend: Auth & Permission Pattern

Setiap fitur baru yang punya permission boundary:
- Gunakan `useAuth().hasPermission('feature.action')` untuk conditional render
- Gunakan `<PermissionGuard permission="feature.view">` untuk route-level guard
- Role yang ada: `admin` (all), `operator` (view+manage), `viewer` (view only)
- Permission yang hanya admin: `settings.manage`

---

## Frontend: Page Structure Convention

Setiap halaman baru mengikuti pola:
- Page file: `frontend/src/pages/NamaPage.tsx`
- Hook: `frontend/src/hooks/useNama.ts` (panggil API, handle state)
- API client: `frontend/src/api/nama.ts` (axios calls ke orchestrator)
- Components: `frontend/src/components/nama/` (sub-components)
- Route: tambah di `frontend/src/App.tsx` dengan `<PermissionGuard>`
