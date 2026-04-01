# Task Breakdown: Marketing - Get Contact Automation

**Date:** 2026-04-01
**Brief:** `docs/marketing-get-contact-automation-plan.md`

## Summary

- **Total Tasks:** 38
- **Database:** 6 tasks
- **Backend:** 16 tasks
- **Frontend:** 13 tasks
- **Integration:** 3 tasks
- **Estimated Time:** 6-8 working days for MVP

## Database Tasks

### TASK-DB-001: Add Marketing Groups Table
**File:** `orchestrator/db.py`

**Description:**
- Tambahkan tabel `marketing_groups`.
- Simpan metadata group: `name`, `client_type`, `status`, `imported_file_name`, `source_kind`, `created_at`, `updated_at`.
- Tambahkan fields summary dasar bila ingin dipersist: `items_count`, `results_count`, `approved_results_count`.

**Acceptance Criteria:**
- [ ] Tabel baru terbentuk saat `init_db()` dijalankan.
- [ ] Group tidak bergantung pada `universities`.
- [ ] Nama group yang sama tetap valid.
- [ ] Timestamp otomatis terisi.

**Dependencies:** None

**Estimated:** 20-30 min

**Notes:**
Status minimum: `draft`, `imported`, `searching`, `reviewing`, `ready`, `completed`.

---

### TASK-DB-002: Add Marketing Clients Table
**File:** `orchestrator/db.py`

**Description:**
- Tambahkan tabel `marketing_clients`.
- Simpan `group_id`, `client_name`, `client_type`, `website_input`, `website_normalized`, `instagram_handle`, `search_status`, `search_started_at`, `search_completed_at`, `last_error`, `created_at`, `updated_at`.

**Acceptance Criteria:**
- [ ] Satu group dapat memiliki banyak client.
- [ ] `client_type` tersimpan di item untuk snapshot operasional.
- [ ] `website_input` dan `website_normalized` terpisah.
- [ ] Status pencarian dapat dilacak per client.

**Dependencies:** `TASK-DB-001`

**Estimated:** 20-30 min

**Notes:**
Dedup import akan bergantung pada tabel ini.

---

### TASK-DB-003: Add Marketing Contact Results Table
**File:** `orchestrator/db.py`

**Description:**
- Tambahkan tabel `marketing_contact_results`.
- Simpan semua kandidat hasil scraping untuk satu client.
- Field minimal: `marketing_client_id`, `contact_type`, `contact_value`, `contact_name`, `contact_role`, `source`, `source_url`, `confidence`, `is_primary`, `review_state`, `edited_manually`, `manual_note`, `created_at`, `updated_at`.

**Acceptance Criteria:**
- [ ] Email dan nomor bisa sama-sama tersimpan untuk satu client.
- [ ] `contact_type` dapat membedakan `wa_phone` dan `other_phone`.
- [ ] Source URL dan confidence tetap tersimpan.
- [ ] Hasil edit manual bisa dilacak.

**Dependencies:** `TASK-DB-002`

**Estimated:** 25-35 min

**Notes:**
Review states minimum: `new`, `reviewed`, `approved_for_blast`, `rejected`.

---

### TASK-DB-004: Add Marketing Handoff Audit Table
**File:** `orchestrator/db.py`

**Description:**
- Tambahkan tabel `marketing_contact_handoffs`.
- Simpan `contact_result_id`, `channel`, `handoff_status`, `target_campaign_id`, `payload_snapshot`, `approved_at`, `created_at`.

**Acceptance Criteria:**
- [ ] Satu hasil dapat diarahkan ke channel `wa`, `email`, atau keduanya.
- [ ] `payload_snapshot` tersimpan sebagai jejak final review.
- [ ] Terdapat relasi ke contact result yang valid.

**Dependencies:** `TASK-DB-003`

**Estimated:** 15-25 min

**Notes:**
`payload_snapshot` direkomendasikan bertipe JSON string.

---

### TASK-DB-005: Add Indexes And Uniqueness Guards
**File:** `orchestrator/db.py`

**Description:**
- Tambahkan index untuk `group_id`, `client_type`, `search_status`, `review_state`, `channel`, dan kolom query lainnya.
- Tambahkan uniqueness guard yang relevan untuk dedup operasional.

**Acceptance Criteria:**
- [ ] Query group detail dan client detail tetap cepat.
- [ ] Dedup import dan dedup result dapat dilakukan konsisten.
- [ ] Tidak ada index yang dibuat sebelum tabelnya tersedia.

**Dependencies:** `TASK-DB-001`, `TASK-DB-002`, `TASK-DB-003`, `TASK-DB-004`

**Estimated:** 20-30 min

**Notes:**
Gunakan migration guard seperti pola existing di `orchestrator/db.py`.

---

### TASK-DB-006: Add Query Helpers For Group Summary
**File:** `orchestrator/db.py`

**Description:**
- Tambahkan helper query untuk:
  - list groups dengan summary counts,
  - list clients per group,
  - detail client,
  - ready-to-blast list,
  - counts per contact type dan per review state.

**Acceptance Criteria:**
- [ ] Group list mengembalikan counts yang dibutuhkan frontend.
- [ ] Client detail bisa mengambil semua candidate results.
- [ ] Ready-to-blast query tidak perlu hitung manual di frontend.

**Dependencies:** `TASK-DB-003`, `TASK-DB-004`, `TASK-DB-005`

**Estimated:** 30-45 min

---

## Backend Tasks

### TASK-BE-001: Create Marketing Module Skeleton
**File:** `orchestrator/marketing/__init__.py`, `orchestrator/marketing/constants.py`

**Description:**
- Buat package `orchestrator/marketing`.
- Tambahkan constants untuk fixed `client_type`, group statuses, search statuses, review states, dan contact types.
- Tambahkan helper validation untuk nilai enum tersebut.

**Acceptance Criteria:**
- [ ] Constants dapat diimport dari endpoint dan service.
- [ ] Backend punya satu sumber kebenaran untuk option dropdown dan status.
- [ ] Tidak ada magic string berulang di endpoint baru.

**Dependencies:** None

**Estimated:** 20-30 min

---

### TASK-BE-002: Create Marketing Groups Service
**File:** `orchestrator/marketing/groups.py`

**Description:**
- Implementasikan CRUD group marketing.
- Reuse pola dari `orchestrator/university_groups.py`.
- Tambahkan list group dan detail group dengan summary counts.

**Acceptance Criteria:**
- [ ] Group bisa dibuat, dilist, diupdate, dan dihapus.
- [ ] Group detail mengembalikan metadata dan progress summary.
- [ ] Service ini tidak menyentuh domain universitas.

**Dependencies:** `TASK-DB-001`, `TASK-DB-006`, `TASK-BE-001`

**Estimated:** 35-50 min

---

### TASK-BE-003: Create Marketing Import Parser
**File:** `orchestrator/marketing/importer.py`

**Description:**
- Buat parser preview `.csv` dan `.xlsx` untuk marketing.
- Support flexible header minimal `name` dan `website`.
- Kembalikan `valid_rows`, `invalid_rows`, `duplicate_rows`, dan hasil normalisasi.

**Acceptance Criteria:**
- [ ] File dengan kolom `name` saja tetap valid.
- [ ] File dengan `name + website` ikut terbaca.
- [ ] Preview tidak menulis apa pun ke database.

**Dependencies:** `TASK-BE-001`

**Estimated:** 35-50 min

**Notes:**
Reuse pendekatan parsing existing dari `POST /universities/import`.

---

### TASK-BE-004: Create Marketing Import Commit Service
**File:** `orchestrator/marketing/importer.py`

**Description:**
- Tambahkan logic commit import.
- Simpan rows valid ke `marketing_clients` pada group tertentu.
- Terapkan dedup dalam group.
- Update group status dan summary count setelah import berhasil.

**Acceptance Criteria:**
- [ ] Imported count, skipped count, dan invalid count terlapor.
- [ ] Duplicate dalam group tidak membuat row ganda.
- [ ] Group status berpindah ke `imported` setelah commit.

**Dependencies:** `TASK-DB-002`, `TASK-BE-003`

**Estimated:** 35-50 min

---

### TASK-BE-005: Add Marketing Group And Import APIs
**File:** `orchestrator/main.py`

**Description:**
- Tambahkan endpoint:
  - `GET /marketing/groups`
  - `POST /marketing/groups`
  - `GET /marketing/groups/{group_id}`
  - `PATCH /marketing/groups/{group_id}`
  - `DELETE /marketing/groups/{group_id}`
  - `POST /marketing/groups/{group_id}/import/preview`
  - `POST /marketing/groups/{group_id}/import/commit`

**Acceptance Criteria:**
- [ ] API create group mewajibkan `client_type`.
- [ ] Preview dan commit import dapat dipanggil dari frontend.
- [ ] Response sudah cukup untuk update UI tanpa request tambahan yang tidak perlu.

**Dependencies:** `TASK-BE-002`, `TASK-BE-004`

**Estimated:** 45-60 min

---

### TASK-BE-006: Implement Website Discovery And Fetch Helpers
**File:** `orchestrator/marketing/search.py`

**Description:**
- Buat helper untuk memilih website dari input atau hasil web search.
- Reuse `ddg_search()` dan fetch util dari `orchestrator/osint/tools.py`.
- Tambahkan normalisasi URL dan shortlist halaman contact-relevant.

**Acceptance Criteria:**
- [ ] Jika website input tersedia, sistem memprosesnya lebih dulu.
- [ ] Jika website kosong, sistem dapat mencoba menemukan domain resmi.
- [ ] Source URL kandidat website tersimpan.

**Dependencies:** `TASK-BE-001`, `TASK-BE-004`

**Estimated:** 35-50 min

---

### TASK-BE-007: Implement Website Contact Extraction
**File:** `orchestrator/marketing/search.py`

**Description:**
- Ekstrak email dan nomor telepon dari halaman website.
- Cari juga social links, contact page link, dan Instagram link bila ada.
- Simpan candidate results dengan confidence dasar.

**Acceptance Criteria:**
- [ ] Email yang ditemukan tersimpan sebagai `email`.
- [ ] Nomor telepon yang ditemukan tersimpan sebagai candidate result.
- [ ] Source URL dan source type tertulis jelas.

**Dependencies:** `TASK-BE-006`, `TASK-DB-003`

**Estimated:** 45-60 min

---

### TASK-BE-008: Implement Instagram Discovery For Generic Clients
**File:** `orchestrator/marketing/search.py`

**Description:**
- Temukan akun Instagram dari website atau web search.
- Ekstrak kandidat kontak dari bio atau public profile info yang bisa diakses.
- Simpan akun Instagram sebagai result type `instagram` dan kontak turunannya bila ada.

**Acceptance Criteria:**
- [ ] Instagram handle tersimpan jika ditemukan.
- [ ] Bio yang berisi email atau nomor telepon dapat menghasilkan candidate baru.
- [ ] Source kandidat tetap dapat ditelusuri.

**Dependencies:** `TASK-BE-007`

**Estimated:** 45-65 min

---

### TASK-BE-009: Implement Web Search Fallback
**File:** `orchestrator/marketing/search.py`

**Description:**
- Tambahkan fallback web search untuk client yang belum punya cukup hasil.
- Prioritaskan domain resmi, profile organisasi, dan contact page.
- Tambahkan confidence berbeda antara direct website hit dan web search hit.

**Acceptance Criteria:**
- [ ] Client tanpa website input tetap bisa dicari.
- [ ] Candidate dari search fallback memiliki source yang jelas.
- [ ] Search fallback tidak menggandakan hasil yang sama.

**Dependencies:** `TASK-BE-006`, `TASK-BE-007`

**Estimated:** 35-50 min

---

### TASK-BE-010: Add WA vs Non-WA Classification Rules
**File:** `orchestrator/marketing/search.py`

**Description:**
- Tambahkan helper klasifikasi nomor Indonesia.
- Mobile candidate diklasifikasikan sebagai `wa_phone`.
- Landline dan `021` masuk `other_phone`.

**Acceptance Criteria:**
- [ ] Nomor `021` tidak pernah masuk `wa_phone`.
- [ ] Nomor `08` atau `628` diprioritaskan sebagai `wa_phone` bila valid.
- [ ] Klasifikasi konsisten dipakai untuk display dan handoff.

**Dependencies:** `TASK-BE-007`, `TASK-BE-009`

**Estimated:** 25-35 min

---

### TASK-BE-011: Build Marketing Search Orchestrator
**File:** `orchestrator/marketing/search.py`

**Description:**
- Orkestrasi proses search per client dan per group.
- Update `search_status`, timestamps, `last_error`, dan pipeline log.
- Tambahkan retry mekanisme untuk failed items.

**Acceptance Criteria:**
- [ ] Group bisa menjalankan pencarian untuk seluruh client.
- [ ] Status `pending`, `running`, `completed`, `failed` berubah sesuai proses.
- [ ] Error tersimpan per client tanpa mematikan seluruh run.

**Dependencies:** `TASK-BE-008`, `TASK-BE-009`, `TASK-BE-010`

**Estimated:** 50-75 min

---

### TASK-BE-012: Add Search Trigger And Progress APIs
**File:** `orchestrator/main.py`

**Description:**
- Tambahkan endpoint:
  - `POST /marketing/groups/{group_id}/run-search`
  - `POST /marketing/groups/{group_id}/retry-search`
  - `GET /marketing/groups/{group_id}/clients`
  - `GET /marketing/clients/{client_id}`

**Acceptance Criteria:**
- [ ] Frontend bisa memicu search satu group.
- [ ] Frontend bisa melihat progress per client.
- [ ] Frontend bisa retry item gagal.

**Dependencies:** `TASK-BE-011`

**Estimated:** 40-60 min

---

### TASK-BE-013: Build Review And Edit Results Service
**File:** `orchestrator/marketing/handoff.py`, `orchestrator/marketing/serializers.py`

**Description:**
- Buat service untuk update result, mark reviewed, reject, approve, bulk approve, dan set primary.
- Pastikan `edited_manually` berubah saat hasil diubah user.

**Acceptance Criteria:**
- [ ] Semua candidate result bisa diubah dari UI.
- [ ] Review state dapat diubah secara individual dan bulk.
- [ ] Primary result per type bisa diatur konsisten.

**Dependencies:** `TASK-DB-003`, `TASK-DB-006`, `TASK-BE-011`

**Estimated:** 40-60 min

---

### TASK-BE-014: Add Review And Result APIs
**File:** `orchestrator/main.py`

**Description:**
- Tambahkan endpoint:
  - `GET /marketing/clients/{client_id}/results`
  - `PATCH /marketing/results/{result_id}`
  - `POST /marketing/results/{result_id}/review`
  - `POST /marketing/results/{result_id}/approve`
  - `POST /marketing/results/{result_id}/reject`
  - `POST /marketing/results/bulk-approve`

**Acceptance Criteria:**
- [ ] Detail client dapat menampilkan semua hasil.
- [ ] Frontend dapat mengedit dan mengapprove data.
- [ ] Ready-to-blast state dapat dibentuk dari data approved.

**Dependencies:** `TASK-BE-013`

**Estimated:** 45-65 min

---

### TASK-BE-015: Add WA Blast Handoff Service
**File:** `orchestrator/marketing/handoff.py`

**Description:**
- Mapping approved results menjadi recipient payload untuk WA Blast.
- Reuse jalur bulk recipient existing dari `blast_service.py`.
- Simpan audit handoff ke `marketing_contact_handoffs`.

**Acceptance Criteria:**
- [ ] Result approved bertipe WA bisa menjadi recipient WA campaign.
- [ ] Nama kontak dan nomor hasil edit ikut terbawa.
- [ ] Snapshot payload tersimpan.

**Dependencies:** `TASK-DB-004`, `TASK-BE-013`

**Estimated:** 35-50 min

---

### TASK-BE-016: Extend Email Blast For Generic Recipients
**File:** `orchestrator/email_blast.py`, `orchestrator/main.py`, `orchestrator/marketing/handoff.py`

**Description:**
- Tambahkan jalur recipient bulk generic untuk email blast.
- Jangan bergantung pada `university_id` sebagai syarat wajib.
- Tambahkan handoff API untuk approved marketing email results.

**Acceptance Criteria:**
- [ ] Approved email results bisa masuk ke email campaign existing.
- [ ] Recipient generic tetap kompatibel dengan engine email blast existing.
- [ ] Handoff audit tetap tercatat.

**Dependencies:** `TASK-BE-013`, `TASK-BE-015`

**Estimated:** 45-70 min

---

## Frontend Tasks

### TASK-FE-001: Add Marketing Types And Query Keys
**File:** `frontend/src/lib/types.ts`, `frontend/src/lib/queryKeys.ts`

**Description:**
- Tambahkan types untuk `MarketingGroup`, `MarketingClient`, `MarketingContactResult`, dan `MarketingHandoff`.
- Tambahkan namespace query keys untuk marketing module.

**Acceptance Criteria:**
- [ ] Semua page dan hook marketing memiliki type yang jelas.
- [ ] Query key marketing terpisah dari universitas.
- [ ] Tidak ada `any` untuk contract utama marketing.

**Dependencies:** `TASK-BE-001`, `TASK-BE-005`

**Estimated:** 20-30 min

---

### TASK-FE-002: Add Marketing API Client And Hooks
**File:** `frontend/src/api/marketing.ts`, `frontend/src/hooks/useMarketing.ts`

**Description:**
- Tambahkan seluruh API wrapper dan React Query hooks untuk feature marketing.
- Cover list group, create group, import preview, import commit, run search, client detail, results, ready-to-blast, dan handoff.

**Acceptance Criteria:**
- [ ] Semua endpoint marketing bisa dipanggil dari frontend melalui satu API module.
- [ ] Mutation memiliki invalidation yang benar.
- [ ] Loading, success, dan error state mudah dipakai page layer.

**Dependencies:** `TASK-FE-001`, `TASK-BE-012`, `TASK-BE-014`, `TASK-BE-016`

**Estimated:** 35-50 min

---

### TASK-FE-003: Add Routes And Navigation
**File:** `frontend/src/App.tsx`, `frontend/src/components/layout/Sidebar.tsx`

**Description:**
- Tambahkan route utama feature marketing.
- Tambahkan route detail client.
- Tambahkan menu baru pada sidebar.

**Acceptance Criteria:**
- [ ] Feature dapat diakses dari UI utama.
- [ ] User dapat pindah dari list group ke detail client.
- [ ] Route lazy-load mengikuti pola page lain.

**Dependencies:** `TASK-FE-002`

**Estimated:** 20-30 min

---

### TASK-FE-004: Build Marketing Create Group Modal
**File:** `frontend/src/components/marketing/MarketingCreateGroupModal.tsx`

**Description:**
- Buat modal create group.
- Wajib menampilkan dropdown `client_type`.
- Input `group name` dan optional description bila dibutuhkan.

**Acceptance Criteria:**
- [ ] User tidak bisa submit tanpa `client_type`.
- [ ] Options dropdown sesuai brief.
- [ ] Success create group langsung merefresh list.

**Dependencies:** `TASK-FE-002`

**Estimated:** 25-35 min

---

### TASK-FE-005: Build Marketing Import Modal
**File:** `frontend/src/components/marketing/MarketingImportModal.tsx`

**Description:**
- Reuse pola dari `ImportModal.tsx`.
- Tambahkan preview valid, invalid, duplicate rows.
- Tampilkan format guide untuk `name` wajib dan `website` opsional.

**Acceptance Criteria:**
- [ ] `.csv` dan `.xlsx` bisa dipilih dan di-preview.
- [ ] User melihat valid dan invalid row sebelum commit.
- [ ] Commit import mengupdate detail group.

**Dependencies:** `TASK-FE-002`, `TASK-BE-005`

**Estimated:** 40-55 min

---

### TASK-FE-006: Build Marketing Group Card Component
**File:** `frontend/src/components/marketing/MarketingGroupCard.tsx`

**Description:**
- Buat card group untuk list di panel kiri.
- Tampilkan `name`, `client_type`, timestamp, status, item count, dan approved count.

**Acceptance Criteria:**
- [ ] Nama group yang sama bisa dibedakan dengan timestamp.
- [ ] Status dan counts mudah discan.
- [ ] Card terpilih memiliki visual state yang jelas.

**Dependencies:** `TASK-FE-002`

**Estimated:** 20-30 min

---

### TASK-FE-007: Build Marketing Main Page
**File:** `frontend/src/pages/MarketingGetContactPage.tsx`

**Description:**
- Bangun page utama list-detail mengikuti pola `UniversityGroupsPage`.
- Kiri: daftar group.
- Kanan: detail group, action import, action run search, dan summary counts.

**Acceptance Criteria:**
- [ ] Empty state dan loading state tersedia.
- [ ] Group list dan detail terhubung dengan benar.
- [ ] Action create group, import, dan run search tersedia pada flow utama.

**Dependencies:** `TASK-FE-003`, `TASK-FE-004`, `TASK-FE-005`, `TASK-FE-006`

**Estimated:** 45-65 min

---

### TASK-FE-008: Build Marketing Group Detail Client Table
**File:** `frontend/src/components/marketing/MarketingGroupDetail.tsx`

**Description:**
- Tampilkan tabel client dalam group.
- Tampilkan kolom: client name, website, search status, email count, WA count, updated time, action.
- Tambahkan filter status dan search by client name.

**Acceptance Criteria:**
- [ ] User dapat mencari client dalam group.
- [ ] Search status dan result counts tampil jelas.
- [ ] Klik row membuka detail client.

**Dependencies:** `TASK-FE-002`, `TASK-BE-012`

**Estimated:** 45-65 min

---

### TASK-FE-009: Build Client Result Review Table
**File:** `frontend/src/components/marketing/MarketingClientResultsTable.tsx`

**Description:**
- Tampilkan semua candidate results dengan kolom: type, value, contact name, source, source URL, confidence, review state, primary, edited flag.
- Sediakan action edit, review, reject, approve.

**Acceptance Criteria:**
- [ ] Semua candidate result bisa terlihat di satu tabel review.
- [ ] Source URL dan confidence dapat dibaca user.
- [ ] Hasil edit dapat disubmit ulang ke backend.

**Dependencies:** `TASK-FE-002`, `TASK-BE-014`

**Estimated:** 50-70 min

---

### TASK-FE-010: Build Marketing Client Detail Page
**File:** `frontend/src/pages/MarketingClientDetailPage.tsx`

**Description:**
- Tampilkan metadata client dan hasil review table.
- Tambahkan section source summary dan current search status.
- Tambahkan bulk action untuk approve selected results.

**Acceptance Criteria:**
- [ ] Detail client dapat diakses dari group detail.
- [ ] Semua hasil candidate dan status review dapat terlihat.
- [ ] User dapat melakukan approve dan reject langsung dari page ini.

**Dependencies:** `TASK-FE-009`

**Estimated:** 45-65 min

---

### TASK-FE-011: Build Ready-To-Blast Panel
**File:** `frontend/src/components/marketing/MarketingReadyToBlastPanel.tsx`

**Description:**
- Tampilkan semua hasil approved pada level group.
- Tambahkan multi-select dan filter channel.
- Siapkan tombol `Send to WA`, `Send to Email`, `Send to Both`.

**Acceptance Criteria:**
- [ ] Hanya hasil approved yang tampil di panel ini.
- [ ] User dapat memilih beberapa result sekaligus.
- [ ] User dapat membedakan email result dan WA result.

**Dependencies:** `TASK-FE-002`, `TASK-BE-014`

**Estimated:** 35-50 min

---

### TASK-FE-012: Build Marketing Handoff Modal
**File:** `frontend/src/components/marketing/MarketingHandoffModal.tsx`

**Description:**
- Buat modal handoff untuk WA Blast, Email Blast, atau keduanya.
- Reuse pola UX dari `AddToBlastModal.tsx`, tetapi source datanya dari approved marketing results.
- Dukung pilih campaign existing.

**Acceptance Criteria:**
- [ ] User bisa memilih channel handoff.
- [ ] User bisa memilih campaign target existing.
- [ ] Success handoff mengupdate audit state di UI.

**Dependencies:** `TASK-FE-011`, `TASK-BE-015`, `TASK-BE-016`

**Estimated:** 45-65 min

---

### TASK-FE-013: Add Progress And Status Badges
**File:** `frontend/src/components/marketing/*`

**Description:**
- Tambahkan badge dan progress state untuk group dan client.
- Reuse pattern existing badge dan spinner.
- Tampilkan summary pending, running, completed, failed, approved.

**Acceptance Criteria:**
- [ ] Group state mudah dibaca dari list.
- [ ] Client state mudah dibaca dari detail group.
- [ ] Running state terlihat saat search aktif.

**Dependencies:** `TASK-FE-007`, `TASK-FE-008`, `TASK-BE-012`

**Estimated:** 20-30 min

---

## Integration Tasks

### TASK-INT-001: Verify Import And Search End-To-End
**Description:**
- Uji flow create group -> upload preview -> commit import -> run search.
- Gunakan sample kecil 5-10 client dengan kombinasi website ada dan tidak ada.

**Test Steps:**
1. Create group baru dengan `client_type` valid.
2. Upload file `.xlsx` sample.
3. Verifikasi preview import.
4. Commit import.
5. Run search.
6. Buka detail beberapa client.

**Acceptance Criteria:**
- [ ] Import berhasil tanpa merusak data existing.
- [ ] Search status berubah sesuai proses.
- [ ] Ada hasil candidate pada client yang memiliki jejak publik.

**Dependencies:** `TASK-BE-012`, `TASK-FE-010`

**Estimated:** 30-45 min

---

### TASK-INT-002: Verify Result Classification And Review Workflow
**Description:**
- Uji bahwa email tetap disimpan dan `021` tidak menjadi WA candidate.
- Uji edit manual, approve, reject, dan ready-to-blast flow.

**Test Steps:**
1. Ambil satu client dengan beberapa candidate results.
2. Edit satu email dan satu nomor telepon.
3. Approve beberapa result.
4. Reject satu result.
5. Cek panel ready-to-blast.

**Acceptance Criteria:**
- [ ] Nomor `021` tidak masuk `wa_phone`.
- [ ] Edit manual tersimpan dan `edited_manually` berubah.
- [ ] Ready-to-blast hanya memuat data approved.

**Dependencies:** `TASK-BE-014`, `TASK-FE-011`

**Estimated:** 25-35 min

---

### TASK-INT-003: Verify WA And Email Handoff Compatibility
**Description:**
- Uji handoff approved results ke campaign WA dan email existing.
- Pastikan payload generic marketing tetap kompatibel.

**Test Steps:**
1. Approve satu WA result dan satu email result.
2. Open handoff modal.
3. Pilih campaign WA existing.
4. Pilih campaign email existing.
5. Submit handoff.
6. Verifikasi recipient list dan audit table.

**Acceptance Criteria:**
- [ ] WA recipient masuk ke campaign tanpa error contract.
- [ ] Email recipient masuk ke campaign tanpa butuh `university_id`.
- [ ] `payload_snapshot` tersimpan pada audit.

**Dependencies:** `TASK-BE-015`, `TASK-BE-016`, `TASK-FE-012`

**Estimated:** 30-45 min

---

## Task Dependency Graph

```text
TASK-DB-001 -> TASK-DB-002 -> TASK-DB-003 -> TASK-DB-004 -> TASK-DB-005 -> TASK-DB-006

TASK-BE-001 -> TASK-BE-002 -> TASK-BE-005
TASK-BE-001 -> TASK-BE-003 -> TASK-BE-004 -> TASK-BE-005

TASK-BE-004 -> TASK-BE-006 -> TASK-BE-007 -> TASK-BE-008
TASK-BE-006 -> TASK-BE-009
TASK-BE-007 + TASK-BE-008 + TASK-BE-009 -> TASK-BE-010 -> TASK-BE-011 -> TASK-BE-012

TASK-BE-011 -> TASK-BE-013 -> TASK-BE-014 -> TASK-BE-015 -> TASK-BE-016

TASK-FE-001 -> TASK-FE-002 -> TASK-FE-003
TASK-FE-002 -> TASK-FE-004 -> TASK-FE-007
TASK-FE-002 -> TASK-FE-005 -> TASK-FE-007
TASK-FE-002 -> TASK-FE-006 -> TASK-FE-007
TASK-FE-002 -> TASK-FE-008 -> TASK-FE-013
TASK-FE-002 -> TASK-FE-009 -> TASK-FE-010
TASK-FE-010 -> TASK-FE-011 -> TASK-FE-012

TASK-INT-001 depends on TASK-BE-012 + TASK-FE-010
TASK-INT-002 depends on TASK-BE-014 + TASK-FE-011
TASK-INT-003 depends on TASK-BE-015 + TASK-BE-016 + TASK-FE-012
```

## Execution Order

### Phase 1: Database Foundation
1. `TASK-DB-001`
2. `TASK-DB-002`
3. `TASK-DB-003`
4. `TASK-DB-004`
5. `TASK-DB-005`
6. `TASK-DB-006`

### Phase 2: Backend Foundation
7. `TASK-BE-001`
8. `TASK-BE-002`
9. `TASK-BE-003`
10. `TASK-BE-004`
11. `TASK-BE-005`

### Phase 3: Search Engine
12. `TASK-BE-006`
13. `TASK-BE-007`
14. `TASK-BE-008`
15. `TASK-BE-009`
16. `TASK-BE-010`
17. `TASK-BE-011`
18. `TASK-BE-012`

### Phase 4: Review And Handoff Backend
19. `TASK-BE-013`
20. `TASK-BE-014`
21. `TASK-BE-015`
22. `TASK-BE-016`

### Phase 5: Frontend Foundation
23. `TASK-FE-001`
24. `TASK-FE-002`
25. `TASK-FE-003`
26. `TASK-FE-004`
27. `TASK-FE-005`
28. `TASK-FE-006`

### Phase 6: Frontend Main UX
29. `TASK-FE-007`
30. `TASK-FE-008`
31. `TASK-FE-009`
32. `TASK-FE-010`
33. `TASK-FE-011`
34. `TASK-FE-012`
35. `TASK-FE-013`

### Phase 7: Integration And QA
36. `TASK-INT-001`
37. `TASK-INT-002`
38. `TASK-INT-003`

## Risks

### Risk 1: Email Blast Extension Is Late
- If email generic recipients are postponed, the feature will appear half-finished because ready-to-blast only works for WA.
- Mitigation: implement `TASK-BE-016` in the same phase as WA handoff.

### Risk 2: Search Coverage Is Noisy
- Generic client categories will produce noisier search results than universities.
- Mitigation: preserve source URL, confidence, and manual review for all candidate results.

### Risk 3: Import Format Variations
- Marketing may change spreadsheet headers over time.
- Mitigation: preview parser with flexible aliases and invalid row feedback.

### Risk 4: Group Names Repeat
- Repeated group names can confuse user selection.
- Mitigation: show timestamp prominently on group cards and detail header.

## Notes

### Implementation Strategy
- Reuse infra, not schema.
- Reuse UX patterns, not domain assumptions.
- Keep MVP focused on import -> search -> review -> ready-to-blast -> handoff.

### QA Focus
- Import parser correctness.
- Search result classification correctness.
- Edit persistence correctness.
- Blast handoff contract compatibility.