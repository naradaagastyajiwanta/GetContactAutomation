# Plan: Marketing Get Contact Automation

## Overview

Bangun modul marketing baru yang terpisah dari domain universitas untuk mendukung flow:

1. pilih tipe client
2. upload daftar client
3. jalankan get contact automation
4. review hasil
5. edit hasil
6. handoff ke WA Blast dan Email Blast

Before:

- sistem masih university-centric
- import hanya ke `universities`
- belum ada review-handoff khusus marketing

After:

- marketing bisa mengelola group client dinamis
- marketing bisa mencari email dan nomor WA secara otomatis
- marketing bisa melihat detail hasil dan mengedit hasil
- marketing bisa memasukkan hasil approved ke data siap di-blast

## Summary

- Total Tasks: 20
- Database: 5 tasks
- Backend: 8 tasks
- Frontend: 5 tasks
- Integration: 2 tasks
- Estimated Time: 4-6 working days for MVP

## Product Decisions

- Modul dipisah total dari universitas.
- Edit hasil dilakukan di halaman detail client.
- Handoff mencakup WA Blast dan Email Blast.
- Format upload minimal: nama client, website opsional.
- Dropdown tipe client:
  - `Lembaga Negara`
  - `Kementrian`
  - `BUMN`
  - `Perusahaan Swasta Besar`
  - `Asosiasi`
  - `LPK`
  - `LKP`
- Group name tidak unique; pembeda operasional memakai timestamp.

## Expected Workflow

1. Marketing membuat group baru.
2. Marketing memilih tipe client.
3. Marketing upload file Excel/CSV berisi list client.
4. Sistem mem-parsing file dan menampilkan preview import.
5. Sistem menyimpan item client ke group marketing.
6. Marketing menjalankan search automation.
7. Sistem mencari website, Instagram, email, dan nomor telepon.
8. Sistem memisahkan hasil email, kandidat WA, dan nomor non-WA.
9. Marketing membuka detail group dan detail client.
10. Marketing mengedit hasil kontak bila perlu.
11. Marketing me-review dan approve hasil.
12. Sistem mendorong hasil approved ke WA Blast, Email Blast, atau keduanya.

## Success Criteria Mapping

1. User dapat memilih group tanpa bergantung lagi pada domain universitas.
2. User dapat upload Excel list group untuk diproses scraping.
3. Sistem menghasilkan email dan nomor WA, dengan email tetap dianggap penting.
4. Saat user memilih tipe client, dropdown menampilkan daftar tipe yang sudah ditentukan.
5. Saat user klik list/group, detail kontak dari list yang dipilih tampil.
6. Setiap group yang dibuat memiliki timestamp, sehingga nama group yang sama tetap aman.
7. Sistem berhasil menyimpan hasil scraping yang bisa direview dan diedit.

## Architecture Direction

### Why New Domain

Codebase saat ini masih sangat terikat ke domain universitas:

- schema utama berpusat pada `universities`
- OSINT flow banyak memakai `university_id`
- import existing hanya mengisi `universities`
- grouping existing adalah `university_groups`

Karena kebutuhan baru menargetkan organisasi umum seperti kementrian, BUMN, asosiasi, LPK, dan perusahaan, modul baru perlu dipisah agar tidak mencampur domain dan tidak memaksa schema lama dipakai di luar konteksnya.

### Reusable Existing Infrastructure

Tetap reuse komponen yang sudah matang:

- pola import file dari endpoint universitas
- pola group management dari `university_groups.py`
- util ekstraksi email dan telepon dari `orchestrator/osint/tools.py`
- pola recipient handoff dari `blast_service.py`
- pola email recipient handoff dari `email_blast.py`
- pola UI list-detail dari `UniversityGroupsPage`
- pola review action dari `BlastCampaignDetailPage`

## Database Tasks

### TASK-DB-001: Create Marketing Groups Table

**File:** `orchestrator/db.py`

**Description:**

- Tambahkan tabel group marketing sebagai header batch kerja marketing.
- Field minimal:
  - `id`
  - `name`
  - `client_type`
  - `status`
  - `imported_file_name`
  - `source_kind`
  - `created_at`
  - `updated_at`
- Status group minimal:
  - `draft`
  - `imported`
  - `searching`
  - `reviewing`
  - `ready`

**Acceptance Criteria:**

- Group tidak bergantung pada `universities`.
- Group dengan nama yang sama tetap valid.
- Timestamp tersimpan otomatis.

**Dependencies:** None

**Estimated:** 15-25 min

**Notes:**

- Nama group tidak perlu unique.
- Timestamp akan dipakai untuk membedakan display saat nama sama.

---

### TASK-DB-002: Create Marketing Client Items Table

**File:** `orchestrator/db.py`

**Description:**

- Tambahkan tabel item client per group.
- Field minimal:
  - `group_id`
  - `client_name`
  - `client_type`
  - `website_input`
  - `website_normalized`
  - `instagram_handle`
  - `search_status`
  - `search_started_at`
  - `search_completed_at`
  - `last_error`
  - `created_at`
  - `updated_at`
- Search status minimal:
  - `pending`
  - `running`
  - `completed`
  - `failed`

**Acceptance Criteria:**

- Satu group dapat memiliki banyak client.
- `client_type` tersimpan di item agar aman jika group berubah metadata.
- Website input dan hasil normalisasi tersimpan terpisah.

**Dependencies:** `TASK-DB-001`

**Estimated:** 20-30 min

**Notes:**

- Pertimbangkan dedup di level `(group_id, normalized client_name, normalized website)`.

---

### TASK-DB-003: Create Marketing Contact Results Table

**File:** `orchestrator/db.py`

**Description:**

- Tambahkan tabel hasil kontak scraping untuk setiap item client.
- Field minimal:
  - `marketing_client_id`
  - `contact_type`
  - `contact_value`
  - `contact_name`
  - `contact_role`
  - `source`
  - `source_url`
  - `confidence`
  - `is_primary`
  - `review_state`
  - `edited_manually`
  - `created_at`
  - `updated_at`
- Contact type minimal:
  - `email`
  - `wa_phone`
  - `other_phone`
  - `website`
  - `instagram`
- Review state minimal:
  - `new`
  - `reviewed`
  - `approved_for_blast`
  - `rejected`

**Acceptance Criteria:**

- Email dan WA bisa sama-sama tersimpan untuk satu client.
- Nomor non-WA bisa dibedakan dari kandidat WA.
- Hasil edit manual bisa dilacak.

**Dependencies:** `TASK-DB-002`

**Estimated:** 25-35 min

**Notes:**

- Dedup yang direkomendasikan: `(marketing_client_id, contact_type, normalized contact_value)`.

---

### TASK-DB-004: Create Marketing Handoff Audit Table

**File:** `orchestrator/db.py`

**Description:**

- Tambahkan tabel audit untuk hasil kontak yang disetujui menuju channel blast.
- Field minimal:
  - `contact_result_id`
  - `channel`
  - `handoff_status`
  - `target_campaign_id`
  - `payload_snapshot`
  - `approved_at`
  - `created_at`
- Channel minimal:
  - `wa`
  - `email`

**Acceptance Criteria:**

- Satu hasil kontak bisa diarahkan ke satu atau dua channel.
- Snapshot payload tersimpan sebagai jejak review final.
- Handoff dapat ditrace ke campaign target jika campaign dibuat.

**Dependencies:** `TASK-DB-003`

**Estimated:** 15-25 min

**Notes:**

- `payload_snapshot` sebaiknya JSON string.

---

### TASK-DB-005: Add Indexes And Idempotent Migration Guards

**File:** `orchestrator/db.py`

**Description:**

- Tambahkan index untuk:
  - `group_id`
  - `client_type`
  - `search_status`
  - `review_state`
  - `marketing_client_id`
  - `channel`
- Pastikan migration baru aman untuk database existing.
- Ikuti pola gotcha migration blast yang sudah ada.

**Acceptance Criteria:**

- Startup backend pada DB lama tidak gagal.
- Index dibuat setelah kolom dan tabel tersedia.
- Tidak ada duplicate migration side effect.

**Dependencies:** `TASK-DB-001`, `TASK-DB-002`, `TASK-DB-003`, `TASK-DB-004`

**Estimated:** 20-30 min

**Notes:**

- Referensi gotcha: migration blast harus menjaga urutan alter dan index.

---

## Backend Tasks

### TASK-BE-001: Create Marketing Groups Service Layer

**File:** `orchestrator/marketing_groups.py`

**Description:**

- Buat service CRUD group marketing mengikuti pola `university_groups.py`.
- Support:
  - create
  - list
  - detail
  - update metadata
  - delete
- Tambahkan summary count untuk jumlah item client dan jumlah hasil kontak.

**Acceptance Criteria:**

- Group list bisa dipakai oleh halaman utama feature.
- Group detail mengembalikan metadata dan ringkasan progres.
- Service tidak menyentuh domain universitas.

**Dependencies:** `TASK-DB-001`, `TASK-DB-002`, `TASK-DB-003`

**Estimated:** 30-45 min

---

### TASK-BE-002: Build Import Preview Parser For Marketing Clients

**File:** `orchestrator/main.py` dan helper import baru bila diperlukan

**Description:**

- Tambahkan parser preview `.csv` dan `.xlsx` khusus marketing.
- Header fleksibel minimal:
  - `client_name`
  - `website`
  - `client_type`
- Jika `client_type` tidak ada di file, gunakan nilai default dari request.
- Kembalikan row valid, row invalid, dan normalized values.

**Acceptance Criteria:**

- File dengan `client_name` saja tetap valid.
- File dengan `client_name + website` tersupport.
- Preview tidak menulis ke DB.

**Dependencies:** `TASK-BE-001`

**Estimated:** 35-50 min

**Notes:**

- Reuse parsing pattern dari `/universities/import`.

---

### TASK-BE-003: Create Marketing Import Commit Endpoint

**File:** `orchestrator/main.py`

**Description:**

- Tambahkan endpoint commit import setelah preview.
- Endpoint membuat group jika belum ada, lalu menyimpan item client ke tabel marketing.
- Return:
  - imported count
  - skipped count
  - invalid count
  - group detail singkat

**Acceptance Criteria:**

- Imported rows masuk ke group yang benar.
- Duplicate dalam satu group ditangani konsisten.
- Nama group yang sama tetap boleh dipakai untuk batch baru.

**Dependencies:** `TASK-BE-002`

**Estimated:** 30-45 min

---

### TASK-BE-004: Build Generic Marketing Search Pipeline

**File:** `orchestrator/marketing_search.py`

**Description:**

- Buat pipeline pencarian untuk client generic.
- Urutan sumber:
  - website input atau website discovered
  - Instagram discovery
  - web search enrichment
- Reuse util `extract_emails` dan `extract_phones_from_text` dari `orchestrator/osint/tools.py`.
- Simpan source URL dan confidence dasar.

**Acceptance Criteria:**

- Sistem bisa menemukan email dari halaman website bila tersedia.
- Sistem bisa menemukan kandidat nomor telepon dari halaman web.
- Sistem bisa menemukan jejak Instagram bila ada.

**Dependencies:** `TASK-BE-003`

**Estimated:** 45-75 min

**Notes:**

- Untuk MVP, fokus ke website, search, dan Instagram discovery dulu.

---

### TASK-BE-005: Add WA vs Non-WA Classification Helper

**File:** `orchestrator/marketing_search.py` atau helper shared baru

**Description:**

- Tambahkan helper klasifikasi nomor.
- Mobile Indonesia masuk `wa_phone`.
- Landline seperti `021` masuk `other_phone`.
- Email tetap prioritas tersimpan walau tidak ada WA.

**Acceptance Criteria:**

- Nomor `021` tidak pernah diberi type `wa_phone`.
- Nomor `08` dan `628` diprioritaskan sebagai WA candidate.
- Hasil klasifikasi konsisten untuk edit dan handoff.

**Dependencies:** `TASK-BE-004`

**Estimated:** 20-30 min

---

### TASK-BE-006: Persist Search Results And Review State

**File:** `orchestrator/marketing_search.py` dan `orchestrator/db.py`

**Description:**

- Simpan hasil pencarian ke marketing contact results.
- Lakukan dedup per client.
- Set `review_state = new` untuk hasil baru.
- Update item status menjadi completed atau failed.

**Acceptance Criteria:**

- Duplicate source tidak membuat row ganda.
- Source dan confidence tetap tersimpan.
- Search status item berubah sesuai hasil.

**Dependencies:** `TASK-BE-004`, `TASK-BE-005`

**Estimated:** 30-45 min

---

### TASK-BE-007: Create Review And Edit APIs

**File:** `orchestrator/main.py`

**Description:**

- Tambahkan endpoint:
  - list group
  - detail group
  - detail client
  - list results
  - update result
  - mark reviewed
  - reject result
  - approve result
  - bulk approve
- Edit fokus pada hasil kontak, bukan item client mentah.

**Acceptance Criteria:**

- Detail client menampilkan semua hasil kontak yang ditemukan.
- Marketing dapat mengedit nomor atau email.
- Flag `edited_manually` berubah saat user mengedit hasil.

**Dependencies:** `TASK-BE-006`

**Estimated:** 45-70 min

---

### TASK-BE-008: Create Handoff APIs To WA Blast And Email Blast

**File:** `orchestrator/main.py`

**Description:**

- Tambahkan endpoint handoff ke WA Blast dan Email Blast.
- Map hasil approved menjadi payload yang kompatibel dengan `blast_service` dan `email_blast`.
- Simpan audit ke tabel handoff.

**Acceptance Criteria:**

- Handoff ke WA dan email dapat dijalankan terpisah atau bersamaan.
- Payload snapshot tersimpan.
- Contract existing blast tidak berubah.

**Dependencies:** `TASK-BE-007`, `TASK-DB-004`

**Estimated:** 40-60 min

---

## Frontend Tasks

### TASK-FE-001: Add Routes And Sidebar Navigation

**File:** `frontend/src/App.tsx` and `frontend/src/components/layout/Sidebar.tsx`

**Description:**

- Tambahkan route utama feature marketing.
- Tambahkan route detail group dan detail client.
- Tambahkan menu baru di sidebar.

**Acceptance Criteria:**

- Feature dapat diakses dari UI utama.
- User dapat pindah dari list group ke detail group lalu detail client.

**Dependencies:** None

**Estimated:** 15-25 min

---

### TASK-FE-002: Build Marketing Groups Page

**File:** `frontend/src/pages/MarketingGetContactPage.tsx`

**Description:**

- Buat page list-detail dua kolom meniru pola `UniversityGroupsPage`.
- Panel kiri: daftar group.
- Panel kanan: detail ringkas group, action import, action run search.
- Tampilkan:
  - `client_type`
  - status
  - item count
  - result count
  - `created_at`

**Acceptance Criteria:**

- Group dengan nama sama tetap bisa dibedakan dari timestamp.
- Empty state dan loading state tersedia.
- Summary group terlihat tanpa membuka detail penuh.

**Dependencies:** `TASK-BE-001`, `TASK-BE-007`

**Estimated:** 40-60 min

---

### TASK-FE-003: Build Create Group And Import Flow

**File:** `frontend/src/components/marketing/MarketingImportModal.tsx` dan related hooks/api modules

**Description:**

- Buat modal create group dengan dropdown `client_type`.
- Buat upload modal dengan preview import.
- Reuse pola `ImportModal.tsx`, tetapi ubah format guide menjadi marketing client list.

**Acceptance Criteria:**

- User wajib memilih `client_type` saat create group.
- User bisa upload `.csv` atau `.xlsx`.
- Preview valid dan invalid rows tampil sebelum commit.

**Dependencies:** `TASK-BE-002`, `TASK-BE-003`

**Estimated:** 45-70 min

---

### TASK-FE-004: Build Group Detail Table And Search Controls

**File:** `frontend/src/components/marketing/MarketingGroupDetail.tsx`

**Description:**

- Tampilkan tabel item client dalam group.
- Field minimal:
  - client name
  - website
  - status pencarian
  - email count
  - WA count
  - updated time
- Tambahkan filter status, search by name, dan tombol retry untuk item failed.

**Acceptance Criteria:**

- Saat klik row, user masuk ke detail client.
- Search status dan result counts tampil jelas.
- Retry item gagal tersedia.

**Dependencies:** `TASK-BE-006`, `TASK-BE-007`

**Estimated:** 45-70 min

---

### TASK-FE-005: Build Client Detail Review Page

**File:** `frontend/src/pages/MarketingClientDetailPage.tsx`

**Description:**

- Tampilkan metadata client, website, Instagram, source list, dan semua hasil kontak.
- Sediakan form edit untuk hasil kontak.
- Tambahkan action:
  - `Reviewed`
  - `Reject`
  - `Approve To Blast`
  - `Approve To Email`
  - `Approve Both`

**Acceptance Criteria:**

- Edit hasil dilakukan di page detail, bukan inline di list.
- Marketing dapat melihat source URL dan confidence.
- Action approve hanya tersedia untuk data valid.

**Dependencies:** `TASK-BE-007`, `TASK-BE-008`

**Estimated:** 60-90 min

---

## Integration Tasks

### TASK-INT-001: Verify WA Blast Handoff Compatibility

**Description:**

- Test bahwa hasil approved bertipe WA dapat diubah menjadi recipient payload yang cocok untuk blast service.
- Verifikasi preview recipient di campaign tetap benar.

**Test Steps:**

1. Create group marketing.
2. Import sample clients.
3. Run search pada sample kecil.
4. Approve satu WA result.
5. Trigger handoff ke WA blast.
6. Buka blast recipient list dan verifikasi payload.

**Acceptance Criteria:**

- Recipient masuk ke flow WA blast tanpa error contract.
- Nomor dan nama kontak yang sudah diedit ikut terbawa.

**Dependencies:** `TASK-BE-008`, `TASK-FE-005`

**Estimated:** 20-30 min

---

### TASK-INT-002: Verify Email Blast Handoff Compatibility

**Description:**

- Test bahwa hasil approved bertipe email dapat diubah menjadi recipient payload yang cocok untuk email blast.
- Verifikasi bahwa email invalid atau kosong tidak ikut masuk.

**Test Steps:**

1. Create group marketing.
2. Import sample clients.
3. Run search pada sample kecil.
4. Approve satu email result.
5. Trigger handoff ke email blast.
6. Buka email blast recipient list dan verifikasi payload.

**Acceptance Criteria:**

- Recipient masuk ke flow email blast tanpa memecah contract existing.
- Payload snapshot tersimpan pada audit handoff.

**Dependencies:** `TASK-BE-008`, `TASK-FE-005`

**Estimated:** 20-30 min

---

## Execution Order

### Phase 1: Database Foundation

1. `TASK-DB-001`
2. `TASK-DB-002`
3. `TASK-DB-003`
4. `TASK-DB-004`
5. `TASK-DB-005`

### Phase 2: Backend Foundation

6. `TASK-BE-001`
7. `TASK-BE-002`
8. `TASK-BE-003`
9. `TASK-BE-004`
10. `TASK-BE-005`
11. `TASK-BE-006`
12. `TASK-BE-007`
13. `TASK-BE-008`

### Phase 3: Frontend

14. `TASK-FE-001`
15. `TASK-FE-002`
16. `TASK-FE-003`
17. `TASK-FE-004`
18. `TASK-FE-005`

### Phase 4: Integration

19. `TASK-INT-001`
20. `TASK-INT-002`

## Relevant Files

- `orchestrator/db.py`
- `orchestrator/main.py`
- `orchestrator/university_groups.py`
- `orchestrator/blast_service.py`
- `orchestrator/email_blast.py`
- `orchestrator/osint/tools.py`
- `frontend/src/App.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/universities/ImportModal.tsx`
- `frontend/src/pages/UniversityGroupsPage.tsx`
- `frontend/src/pages/BlastCampaignDetailPage.tsx`

## Verification

1. Migration berjalan aman di database existing.
2. Import `.csv` dan `.xlsx` dengan `client_name` dan website opsional berhasil diparse.
3. Search pada sample kecil menghasilkan email dan WA candidate yang terklasifikasi benar.
4. Nomor landline seperti `021` tidak masuk jalur WA candidate.
5. Detail client bisa diedit dan perubahan persist setelah refresh.
6. Bulk approve ke WA dan email menghasilkan handoff record dan payload snapshot.
7. Data approved benar-benar bisa dipakai di flow blast existing.
8. Group dengan nama sama tetap terlihat unik lewat timestamp.

## Risks

1. Reuse pipeline universitas secara langsung akan menghasilkan coupling schema yang buruk.
2. Discovery Instagram untuk entity generic bisa lebih noisy daripada universitas.
3. Jika import preview tidak dibuat, risiko salah mapping file akan tinggi untuk user marketing.
4. Handoff ke dua channel butuh snapshot payload agar hasil review tidak berubah diam-diam.

## Scope Boundaries

Included:

- group/list management
- upload
- search automation
- result review-edit
- ready-to-blast handoff
- status UI

Excluded from MVP:

- multi-user approval
- scheduler blast dari page marketing
- generalized universal entity graph untuk semua domain repo