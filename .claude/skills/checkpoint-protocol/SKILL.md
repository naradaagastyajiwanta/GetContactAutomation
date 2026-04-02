---
name: checkpoint-protocol
description: >
  Protokol standar untuk agent pause dan meminta
  persetujuan programmer sebelum melanjutkan ke
  tahap berikutnya.
---

## Cara Melakukan Checkpoint

Saat kamu perlu persetujuan programmer, output format ini:

---
## 🛑 CHECKPOINT — Persetujuan Diperlukan

**Agent:** [nama agent kamu]
**Tahap:** [nama tahap saat ini]
**Next Step:** [apa yang akan dilakukan setelah disetujui]

### Yang Sudah Dikerjakan:
[ringkasan output yang sudah dibuat]

### Yang Perlu Diperiksa:
[file atau dokumen yang perlu di-review programmer]

### Pertanyaan (jika ada):
[pertanyaan spesifik untuk programmer]

**Untuk melanjutkan, ketik:**
- `APPROVE` — lanjut ke tahap berikutnya
- `REVISE: [catatan revisi]` — kembali dan perbaiki
- `STOP` — hentikan proses
---

Tunggu response programmer. Jangan lanjutkan sampai
ada salah satu dari ketiga response di atas.