---
name: read-docx
description: >
  Ekstrak dan baca isi file Word (.docx). Gunakan ketika
  perlu membaca document brief, spec, atau dokumen Word lainnya.
allowed-tools: Bash
---

Untuk membaca file .docx, gunakan pandoc:
```bash
pandoc --track-changes=all document.docx -o output.md
cat output.md
```

Jika pandoc tidak tersedia, ekstrak XML:
```bash
unzip -p document.docx word/document.xml | \
  sed 's/<[^>]*>//g' | sed '/^$/d'
```

Hasil ekstraksi akan berupa teks mentah — susun ulang
menjadi format yang terstruktur dan readable.