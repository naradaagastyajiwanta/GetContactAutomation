---
name: brief-analysis
description: >
  Panduan menganalisis document brief. Gunakan
  saat menginterpretasi requirements dan mendeteksi
  ambiguitas dalam brief.
---

## Checklist Analisis Brief

### Red Flags — Selalu Tanyakan Jika:
- Requirement menggunakan kata: "mudah", "cepat", "canggih",
  "seperti biasa", "standar" → tidak terukur, perlu definisi
- Disebutkan integrasi dengan sistem lain tanpa detail API
- Ada kata "semua", "setiap", "selalu" tanpa batasan jelas
- Tidak ada kriteria acceptance yang spesifik

### Kategori Ambiguitas:
1. **Functional ambiguity** — apa yang harus dilakukan sistem
2. **Data ambiguity** — data apa yang dibutuhkan, dari mana
3. **UI/UX ambiguity** — tampilan & behaviour yang diharapkan
4. **Integration ambiguity** — bagaimana koneksi dengan sistem lain
5. **Performance ambiguity** — seberapa cepat, berapa banyak data

### Format Pertanyaan Klarifikasi yang Baik:
"Pada requirement #X tentang [topik], apakah yang dimaksud
adalah [opsi A] atau [opsi B]? Ini berpengaruh pada [dampak teknis]."

## Contoh Analisis

### Requirements Ambiguus → Translation
```
Brief: "Sistem harus responsif dan cepat"
Interpretasi:
- Responsif → UI mobile-friendly (Tailwind responsive classes)
- Cepat → API response < 500ms, perlu index di database
```

```
Brief: "User bisa mengelola data universitas"
Interpretasi:
- Mengelola → CRUD (Create, Read, Update, Delete)
- Data universitas → nama, alamat, kontak, website, IG handle
```

## Questions untuk Programmer
Jika menemukan ambiguity, buat opsi spesifik:

❌ "Apa yang dimaksud dengan cepat?"
✅ "Untuk response time API, apakah targetnya:
   A) < 200ms (optimistic)
   B) < 500ms (reasonable)
   C) < 1000ms (acceptable)"

## Technical Translation Pattern
```
User Language → Technical Language
-------------------------------------------------
"Tampil data"    → GET /api/v1/resource dengan pagination
"Simpan data"    → POST /api/v1/resource dengan validasi
"Edit data"      → PUT /api/v1/resource/{id}
"Hapus data"     → DELETE /api/v1/resource/{id} dengan soft delete
"Cari data"      → GET /api/v1/resource?search=keyword
```
