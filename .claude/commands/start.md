Analisis request ini dan jalankan pipeline yang tepat.

Sumber request bisa berupa:
- Nama file brief (contoh: briefs/brief-002.docx)
- Deskripsi teks langsung dari programmer
- Nama report yang perlu ditindaklanjuti
  (contoh: docs/user-simulation-report.md)

Langkah yang harus dilakukan:
1. Identifikasi sumber dan tipe pekerjaan
   (GREENFIELD / NEW FEATURE / BUG FIX / SMALL EDIT)
2. Tampilkan execution plan lengkap
3. Tunggu APPROVE dari programmer (approval HANYA untuk plan)
4. Setelah APPROVE, eksekusi pipeline TANPA meminta
   approval lagi di setiap tahap — kecuali security-agent
   yang memutuskan suatu operasi perlu di-flag
5. Di akhir, tampilkan instruksi untuk jalankan /review-and-fix

## Approval Flow

```
PROGRAMMER APPROVE: hanya untuk execution plan (sekali di awal)

SECURITY-AGENT APPROVE: otomatis aktif selama eksekusi untuk:
  - Operasi database destructive (DELETE, DROP, TRUNCATE,
    UPDATE tanpa WHERE)
  - Operasi credentials (.env read/write, secrets)
  - Git push ke branch manapun selain feat/* sendiri

Semua operasi lain: berjalan otomatis tanpa interupsi
```

## Cara Orchestrator Berkomunikasi dengan Security-Agent

Sebelum setiap operasi yang berpotensi masuk kategori
di atas, kirim request ke security-agent dengan format:

```
SECURITY CHECK:
Agent   : [nama agent yang akan menjalankan]
Operasi : [command lengkap yang akan dijalankan]
Konteks : [kenapa operasi ini dibutuhkan]
```

Tunggu respons security-agent sebelum melanjutkan.
Jika security-agent BLOCK → hentikan pipeline dan
laporkan ke programmer.
