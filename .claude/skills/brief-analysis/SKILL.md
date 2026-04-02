---
name: brief-analysis
description: >
  Panduan menganalisis document brief dari PM. Gunakan
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