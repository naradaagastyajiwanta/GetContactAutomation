---
name: task-breakdown
description: >
  Format standar untuk memecah fitur menjadi tasks
  yang bisa dikerjakan. Gunakan saat membuat
  task breakdown dari technical spec.
---

## Format Task

Setiap task harus memiliki:
- **ID:** TASK-001, TASK-002, dst
- **Judul:** singkat, dimulai kata kerja (Buat, Tambah, Ubah)
- **Tipe:** Backend / Frontend / Database / DevOps / Test
- **Deskripsi:** apa yang perlu dilakukan (2-3 kalimat)
- **Acceptance Criteria:** kondisi yang membuat task "done"
- **Depends On:** ID task yang harus selesai duluan (jika ada)
- **Estimasi:** S (< 2 jam) / M (2-4 jam) / L (4-8 jam)

## Urutan Wajib:
1. Database migrations selalu pertama
2. Backend models & repositories
3. Backend service layer & business logic
4. Backend API endpoints / controllers
5. Frontend services / API calls
6. Frontend components & pages
7. Integration tests
8. Unit tests

## Contoh:

**TASK-001**

* **Judul** : Buat tabel users_addresses di database
* **Tipe**: Database
* **Deskripsi** : Tambah migration baru untuk tabel
users_addresses dengan fields: id, user_id, address,
city, province, postal_code, is_primary, timestamps
* **Acceptance Criteria** :

    * Migration berhasil dijalankan tanpa error
    * Rollback migration juga berfungsi


* **Depends On**: -
* **Estimasi** : 1 hour