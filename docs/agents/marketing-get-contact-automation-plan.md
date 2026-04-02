# Plan: Marketing - Get Contact Automation

**Date:** 2026-04-01
**Status:** Proposed MVP Plan
**Feature Order Name:** Marketing - Get Contac Automation
**Station:** Searching Data

## Brief Translation

### Before

- Sistem masih berpusat pada domain universitas.
- Import list masih diarahkan ke data universitas.
- Belum ada modul marketing untuk organisasi umum seperti lembaga negara, kementrian, BUMN, asosiasi, LPK, LKP, atau perusahaan swasta besar.
- Belum ada flow review hasil scraping yang khusus untuk tim marketing sebelum data diteruskan ke blast.

### After

- Marketing dapat membuat group pencarian baru secara dinamis.
- Marketing wajib memilih tipe client saat membuat group.
- Marketing dapat upload file Excel atau CSV berisi daftar client yang akan dicari.
- Sistem menjalankan get contact automation berdasarkan list yang di-upload.
- Sistem mencari website, Instagram, email, dan nomor telepon kandidat WA.
- Hasil scraping dapat dilihat, diedit, direview, lalu dipilih untuk masuk ke data siap di blast.
- Hasil approved dapat diteruskan ke WA Blast, Email Blast, atau keduanya.

## Objectives

1. Menyediakan modul marketing yang terpisah dari domain universitas.
2. Mendukung input list client secara dinamis melalui upload file.
3. Menyediakan dropdown tipe client sesuai brief.
4. Menjalankan proses scraping berbasis website, Instagram, lalu web search.
5. Menyimpan seluruh kandidat hasil scraping agar bisa direview dan diedit.
6. Menyediakan jalur handoff ke WA Blast dan Email Blast tanpa merusak contract existing.

## Locked Decisions

1. Modul ini dibangun sebagai domain baru dan tidak digabung ke tabel `universities`.
2. Upload MVP mendukung `name` sebagai field wajib dan `website` sebagai field opsional.
3. Sumber pencarian MVP mengikuti urutan: website -> Instagram -> web search.
4. Semua kandidat hasil scraping harus bisa dilihat dan diedit, bukan hanya kontak final.
5. Hasil approved harus muncul di staging "ready to blast" dan juga bisa ditambahkan ke campaign existing.
6. Tipe client menggunakan fixed options pada backend dan frontend, bukan master table lookup terpisah.
7. Nama group tidak unique; pembeda operasional menggunakan timestamp.

## Client Type Options

Dropdown tipe client pada MVP:

- `Lembaga Negara`
- `Kementrian`
- `BUMN`
- `Perusahaan Swasta Besar`
- `Asosiasi`
- `LPK`
- `LKP`

## Expected User Workflow

1. Marketing membuka modul Marketing Get Contact Automation.
2. Marketing membuat group baru.
3. Marketing memilih satu tipe client pada group tersebut.
4. Marketing upload file `.xlsx` atau `.csv` yang berisi daftar client.
5. Sistem menampilkan preview import: valid rows, invalid rows, dan duplicate rows.
6. Marketing melakukan commit import.
7. Sistem menyimpan semua client ke group yang dipilih.
8. Marketing menekan tombol `Run Search` untuk group tersebut.
9. Sistem memproses setiap client dengan urutan website -> Instagram -> web search.
10. Sistem menyimpan semua kandidat email, nomor telepon, website, dan akun Instagram yang ditemukan.
11. Marketing membuka detail group lalu memilih salah satu client.
12. Marketing melihat seluruh kandidat hasil scraping, termasuk source URL dan confidence.
13. Marketing mengedit data yang perlu disesuaikan.
14. Marketing menandai hasil sebagai reviewed, rejected, approved to WA, approved to Email, atau approved to both.
15. Sistem menempatkan hasil approved ke staging `ready to blast`.
16. Marketing memilih data approved lalu mengirimkannya ke campaign WA, Email, atau keduanya.

## Success Criteria Mapping

### Business Criteria

1. User dapat memilih group tanpa bergantung pada domain universitas.
2. User dapat upload Excel list group untuk diproses scraping.
3. Sistem menghasilkan email dan nomor WA candidate, dengan email tetap dianggap penting.
4. Saat user memilih tipe client, dropdown menampilkan daftar tipe client yang sudah ditentukan.
5. Saat user klik list yang dipilih, detail kontak dari list tersebut tampil.
6. Setiap group yang dibuat memiliki timestamp, sehingga nama group yang sama tetap aman.
7. Sistem berhasil mendapatkan kontak hasil scraping yang bisa direview, diedit, dan diteruskan ke blast.

### Technical Translation

1. `client_type` harus menjadi field wajib saat create group.
2. Import file harus mendukung `.csv` dan `.xlsx` dengan header fleksibel.
3. Search pipeline harus mampu menyimpan banyak kandidat hasil untuk satu client.
4. Nomor `021` tidak boleh diklasifikasikan sebagai `wa_phone`.
5. Email harus tetap disimpan walaupun tidak ditemukan WA candidate.
6. Handoff ke WA Blast harus menggunakan payload generic dan tidak bergantung pada `university_id`.
7. Handoff ke Email Blast harus mendukung recipient source baru dari domain marketing.

## Scope

### Included in MVP

- Modul group marketing baru.
- Dropdown tipe client.
- Upload list client.
- Preview import sebelum commit.
- Search automation per group.
- Penyimpanan semua kandidat hasil scraping.
- Detail client untuk review dan edit.
- Staging ready to blast.
- Handoff ke WA Blast dan Email Blast.
- Status summary dan progress dasar.

### Excluded from MVP

- Multi-user approval workflow.
- Scheduler otomatis harian khusus modul marketing.
- Generic universal entity graph lintas semua domain repo.
- Integrasi CRM enrichment non-kontak.
- Ranking AI yang terlalu kompleks untuk prioritas blast.

## Architecture Direction

### Why New Domain

Codebase saat ini masih sangat terikat ke domain universitas:

- Schema utama berpusat pada `universities`.
- Grouping existing menggunakan `university_groups`.
- Import existing menulis ke `universities`.
- Flow hasil kontak dan blast banyak bergantung pada `university_id`.

Karena feature baru menargetkan organisasi umum, modul baru harus dipisah agar:

- tidak mencampur semantik data universitas dengan organisasi non-universitas,
- tidak memaksa query existing untuk menerima entity yang bentuk datanya berbeda,
- lebih mudah dikembangkan untuk kategori client lain di masa depan.

### Infrastructure To Reuse

Komponen existing yang direkomendasikan untuk reuse:

- parser import file dari endpoint universitas di `orchestrator/main.py`,
- pola CRUD group dari `orchestrator/university_groups.py`,
- util fetch dan search dari `orchestrator/osint/tools.py`,
- pola recipient handoff dari `orchestrator/blast_service.py`,
- engine email campaign dari `orchestrator/email_blast.py`,
- pola page list-detail dari `frontend/src/pages/UniversityGroupsPage.tsx`,
- pola review hasil dari `frontend/src/components/universities/ContactsPanel.tsx`,
- pola add-to-blast dari `frontend/src/components/blast/AddToBlastModal.tsx`.

## Proposed File Map

### Backend

- `orchestrator/db.py`
- `orchestrator/marketing/__init__.py`
- `orchestrator/marketing/constants.py`
- `orchestrator/marketing/groups.py`
- `orchestrator/marketing/importer.py`
- `orchestrator/marketing/search.py`
- `orchestrator/marketing/handoff.py`
- `orchestrator/marketing/serializers.py`
- `orchestrator/main.py`

### Frontend

- `frontend/src/lib/types.ts`
- `frontend/src/lib/queryKeys.ts`
- `frontend/src/api/marketing.ts`
- `frontend/src/hooks/useMarketing.ts`
- `frontend/src/pages/MarketingGetContactPage.tsx`
- `frontend/src/pages/MarketingClientDetailPage.tsx`
- `frontend/src/components/marketing/MarketingGroupCard.tsx`
- `frontend/src/components/marketing/MarketingCreateGroupModal.tsx`
- `frontend/src/components/marketing/MarketingImportModal.tsx`
- `frontend/src/components/marketing/MarketingGroupDetail.tsx`
- `frontend/src/components/marketing/MarketingClientResultsTable.tsx`
- `frontend/src/components/marketing/MarketingReadyToBlastPanel.tsx`
- `frontend/src/components/marketing/MarketingHandoffModal.tsx`

## Proposed Data Model

### Table: `marketing_groups`

Purpose:
Header batch kerja marketing.

Minimum fields:

- `id`
- `name`
- `client_type`
- `status`
- `imported_file_name`
- `source_kind`
- `items_count`
- `results_count`
- `approved_results_count`
- `created_at`
- `updated_at`

Recommended statuses:

- `draft`
- `imported`
- `searching`
- `reviewing`
- `ready`
- `completed`

### Table: `marketing_clients`

Purpose:
List client yang berada di dalam satu group.

Minimum fields:

- `id`
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

Recommended search statuses:

- `pending`
- `running`
- `completed`
- `failed`

### Table: `marketing_contact_results`

Purpose:
Menyimpan semua kandidat hasil scraping untuk satu client.

Minimum fields:

- `id`
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
- `manual_note`
- `created_at`
- `updated_at`

Recommended contact types:

- `email`
- `wa_phone`
- `other_phone`
- `website`
- `instagram`

Recommended review states:

- `new`
- `reviewed`
- `approved_for_blast`
- `rejected`

### Table: `marketing_contact_handoffs`

Purpose:
Audit trail untuk hasil approved yang dikirim ke channel blast.

Minimum fields:

- `id`
- `contact_result_id`
- `channel`
- `handoff_status`
- `target_campaign_id`
- `payload_snapshot`
- `approved_at`
- `created_at`

Recommended channels:

- `wa`
- `email`

## Query And Dedup Rules

1. Dedup import minimal pada level `(group_id, normalized client_name, normalized website)`.
2. Dedup contact results minimal pada level `(marketing_client_id, contact_type, normalized contact_value)`.
3. Email disimpan dalam lowercase normalized form.
4. Nomor telepon dinormalisasi ke bentuk yang konsisten untuk Indonesia.
5. `021` dan landline tidak masuk `wa_phone`; tetap dapat disimpan sebagai `other_phone` bila relevan.

## Search Pipeline Design

### Stage 1: Website Input Or Discovery

1. Jika file upload sudah memiliki website, gunakan website tersebut lebih dulu.
2. Jika website tidak ada, lakukan pencarian web untuk mencari website resmi.
3. Fetch halaman website utama dan halaman yang berpotensi berisi kontak.

Target extraction:

- email,
- nomor telepon,
- link ke halaman kontak,
- social links,
- akun Instagram,
- halaman profil perusahaan atau organisasi.

### Stage 2: Instagram Discovery

1. Gunakan link Instagram dari website jika tersedia.
2. Jika tidak ada, cari kandidat Instagram lewat web search.
3. Simpan akun Instagram yang berhasil ditemukan sebagai hasil candidate.

Target extraction:

- handle Instagram,
- bio yang mengandung email,
- bio yang mengandung nomor telepon,
- petunjuk ke contact page atau WhatsApp link.

### Stage 3: Web Search Fallback

1. Jalankan web search menggunakan nama client.
2. Prioritaskan hasil yang mengarah ke domain resmi, profil organisasi, dan contact page.
3. Simpan source URL dan confidence.

### Stage 4: Classification

1. Classify email sebagai `email`.
2. Classify mobile candidate sebagai `wa_phone`.
3. Classify landline atau non-mobile sebagai `other_phone`.
4. Simpan website dan Instagram sebagai candidate non-contact untuk membantu review.

## Review And Ready-To-Blast Design

### Review Rules

1. Semua kandidat hasil harus terlihat di detail client.
2. Marketing dapat mengedit nilai hasil, nama kontak, dan catatan manual.
3. Setiap edit mengubah `edited_manually = 1`.
4. User dapat memilih salah satu hasil sebagai primary.
5. User dapat menandai hasil sebagai `reviewed`, `rejected`, atau `approved_for_blast`.

### Ready-To-Blast Rules

1. Data siap di blast berasal dari hasil dengan `review_state = approved_for_blast`.
2. Ready-to-blast ditampilkan di level group dan dapat difilter per channel.
3. Handoff ke WA dan email ditrigger dari data approved, bukan dari hasil mentah.

## Handoff Design

### WA Blast

Reuse yang direkomendasikan:

- endpoint recipient payload generic di `orchestrator/main.py`,
- bulk insert recipient di `orchestrator/blast_service.py`,
- modal existing di `frontend/src/components/blast/AddToBlastModal.tsx` sebagai referensi UX.

WA payload yang diperlukan:

- `phone_number`
- `contact_name`
- `source marketing metadata`
- `optional label/group info`

### Email Blast

Gap existing:

- flow current masih mengasumsikan source recipient dari universitas,
- belum ada jalur add recipient by generic marketing contacts.

Perubahan yang direkomendasikan:

1. tambahkan service bulk recipient baru untuk email blast,
2. tambahkan endpoint marketing handoff ke email campaign,
3. gunakan payload email generic tanpa `university_id` sebagai syarat wajib.

## API Surface Recommendation

### Group APIs

- `GET /marketing/groups`
- `POST /marketing/groups`
- `GET /marketing/groups/{group_id}`
- `PATCH /marketing/groups/{group_id}`
- `DELETE /marketing/groups/{group_id}`

### Import APIs

- `POST /marketing/groups/{group_id}/import/preview`
- `POST /marketing/groups/{group_id}/import/commit`

### Search APIs

- `POST /marketing/groups/{group_id}/run-search`
- `POST /marketing/groups/{group_id}/retry-search`
- `GET /marketing/groups/{group_id}/clients`
- `GET /marketing/clients/{client_id}`

### Result Review APIs

- `GET /marketing/clients/{client_id}/results`
- `PATCH /marketing/results/{result_id}`
- `POST /marketing/results/{result_id}/review`
- `POST /marketing/results/{result_id}/approve`
- `POST /marketing/results/{result_id}/reject`
- `POST /marketing/results/bulk-approve`

### Ready-To-Blast And Handoff APIs

- `GET /marketing/groups/{group_id}/ready-to-blast`
- `POST /marketing/handoff/wa`
- `POST /marketing/handoff/email`
- `POST /marketing/handoff/both`
- `GET /marketing/handoffs`

## Frontend UX Recommendation

### Main Page

Layout recommendation:

- kiri: daftar group,
- kanan: summary group dan tabel client dalam group,
- panel kanan harus tetap usable untuk empty state, loading state, dan running state.

### Group Card

Setiap group card sebaiknya menampilkan:

- `group name`
- `client type`
- `created_at` atau timestamp label
- `items count`
- `approved results count`
- status badge

### Group Detail

Tabel client minimal menampilkan:

- client name
- website
- search status
- email count
- WA count
- updated time
- action: open detail

### Client Detail Page

Harus menampilkan:

- metadata client,
- website normalized,
- Instagram handle,
- daftar source yang dipakai,
- semua hasil kontak,
- source URL,
- confidence,
- form edit,
- action review dan approve.

## Delivery Phases

### Phase 1: Foundation

- schema domain marketing,
- constants tipe client dan statuses,
- base service layer,
- base API list and detail.

### Phase 2: Import

- create group,
- import preview,
- import commit,
- dedup import,
- group summary update.

### Phase 3: Search Engine

- website discovery,
- website extraction,
- Instagram discovery,
- web search fallback,
- result persistence,
- status update and retry.

### Phase 4: Review UI

- routes and navigation,
- group page,
- import modal,
- group detail table,
- client detail review page,
- ready-to-blast panel.

### Phase 5: Handoff

- WA handoff,
- email handoff,
- payload audit,
- ready-to-blast actions.

### Phase 6: QA And Hardening

- import validation,
- classification validation,
- end-to-end smoke test,
- handoff verification,
- retry and progress behavior.

## Risks And Mitigations

### Risk 1: Domain Coupling

Risk:
Jika modul ini dipaksa reuse langsung tabel `universities`, codebase akan makin sulit dipelihara.

Mitigation:
Bangun domain `marketing` terpisah dan reuse hanya level util, UI pattern, dan blast engine.

### Risk 2: Noisy Search Results

Risk:
Entity generic lebih noisy dibanding universitas, terutama untuk Instagram dan web search.

Mitigation:
Simpan semua candidate beserta source URL dan confidence, lalu wajibkan review manual sebelum handoff.

### Risk 3: Email Blast Source Limitation

Risk:
Email blast current flow masih university-centric.

Mitigation:
Tambahkan jalur recipient bulk generic sejak awal implementasi backend, jangan ditunda ke tahap terakhir.

### Risk 4: Import Mapping Error

Risk:
Marketing dapat upload file dengan header yang berubah-ubah.

Mitigation:
Sediakan preview import dan flexible header detection sebelum commit.

## Acceptance Checklist

1. User dapat membuat group marketing baru dan memilih tipe client.
2. User dapat membuat dua group dengan nama yang sama pada waktu berbeda.
3. User dapat upload `.csv` dan `.xlsx` dengan format `name` wajib dan `website` opsional.
4. User melihat preview import sebelum commit.
5. Group detail menampilkan list client yang berhasil diimport.
6. User dapat menjalankan search automation untuk satu group.
7. Sistem dapat menemukan email dari website bila tersedia.
8. Sistem dapat menemukan WA candidate bila tersedia.
9. Sistem tidak mengklasifikasikan `021` sebagai `wa_phone`.
10. User dapat membuka detail client dan melihat semua kandidat hasil scraping.
11. User dapat mengedit hasil email atau nomor telepon.
12. User dapat approve hasil ke staging ready to blast.
13. User dapat handoff hasil approved ke WA Blast.
14. User dapat handoff hasil approved ke Email Blast.
15. Audit handoff tersimpan dengan payload snapshot.

## Relevant Files

- `orchestrator/db.py`
- `orchestrator/main.py`
- `orchestrator/university_groups.py`
- `orchestrator/blast_service.py`
- `orchestrator/email_blast.py`
- `orchestrator/osint/tools.py`
- `frontend/src/App.tsx`
- `frontend/src/lib/queryKeys.ts`
- `frontend/src/lib/types.ts`
- `frontend/src/pages/UniversityGroupsPage.tsx`
- `frontend/src/components/universityGroups/GroupUniversitiesPanel.tsx`
- `frontend/src/components/universities/ImportModal.tsx`
- `frontend/src/components/universities/ContactsPanel.tsx`
- `frontend/src/components/blast/AddToBlastModal.tsx`
- `frontend/src/api/emailBlast.ts`
- `frontend/src/hooks/useEmailBlast.ts`

## Related Execution Doc

Task breakdown detail untuk implementasi feature ini disimpan di:

- `docs/task-breakdown.md`