---
name: checkpoint-protocol
description: >
  Protokol standar untuk agent pause dan meminta
  persetujuan user sebelum melanjutkan ke
  tahap berikutnya.
---

## Cara Melakukan Checkpoint

Saat kamu perlu persetujuan user, output format ini:

---
## 🛑 CHECKPOINT — Persetujuan Diperlukan

**Agent:** [nama agent kamu]
**Tahap:** [nama tahap saat ini]
**Next Step:** [apa yang akan dilakukan setelah disetujui]

### Yang Sudah Dikerjakan:
[ringkasan output yang sudah dibuat]

### Yang Perlu Diperiksa:
[file atau dokumen yang perlu di-review user]

### Pertanyaan (jika ada):
[pertanyaan spesifik untuk user]

**Untuk melanjutkan, ketik:**
- `APPROVE` — lanjut ke tahap berikutnya
- `REVISE: [catatan revisi]` — kembali dan perbaiki
- `STOP` — hentikan proses
---

Tunggu response user. Jangan lanjutkan sampai
ada salah satu dari ketiga response di atas.

## Checkpoint di Pipeline

### CP1: Setelah Brief Interpretation
```
@brief-interpreter selesai → CP1 → user APPROVE/REVISE
```

### CP2: Setelah Technical Planning
```
@technical-planner selesai → CP2 → user APPROVE/REVISE
```

### CP3: Setelah Architecture Blueprint
```
@code-architect selesai → CP3 → user APPROVE/REVISE
```

### CP4: Setelah Environment Setup (Greenfield only)
```
@env-configurator selesai → CP4 → user verify → APPROVE
```

## Response Handling

### Jika APPROVE
- Lanjut ke tahap berikutnya
- Tidak perlu output apa-apa kecuali next agent dipanggil

### Jika REVISE: [catatan]
- Baca catatan revisi
- Perbaiki sesuai catatan
- Tampilkan kembali hasil yang sudah direvisi
- Tunggu APPROVE/REVISE lagi

### Jika STOP
- Hentikan proses
- Simpan progress yang sudah ada
- Beritahu user bisa lanjut dengan memanggil agent yang sesuai

## Example Usage
```
=== 🛑 CHECKPOINT 1: REVIEW INTERPRETASI ===

Agent: brief-interpreter
Tahap: Technical Translation
Next: @codebase-scout akan menganalisis codebase

### Output:
- Technical Requirements: 5 requirements
- API Endpoints: 3 endpoints baru
- Database Changes: TIDAK ADA
- Frontend: 1 page baru + 2 components

### Pertanyaan Klarifikasi:
Q-001: Pagination limit → RECOMMENDED: 50 items per page

APPROVE untuk lanjut?
REVISE: [catatan]
```
