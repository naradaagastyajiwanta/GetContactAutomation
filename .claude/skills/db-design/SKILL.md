---
name: db-design
description: >
  Panduan merancang skema database dari nol untuk greenfield
  project. Gunakan saat perlu membuat ERD, mendefinisikan tabel,
  relasi, indexes, dan dokumentasi skema lengkap sebelum coding.
  Mendukung MySQL, PostgreSQL, dan SQLite.
---

# Database Design Skill

## Langkah Pertama — Konfirmasi Engine
Sebelum menggunakan panduan ini, pastikan database engine
sudah diketahui dari brief atau konfirmasi programmer.
Pilih section tipe data yang sesuai di bawah.

---

## Prinsip Utama (Berlaku untuk Semua Engine)

### Naming Convention
```
Tabel     : snake_case, plural          → users, order_items
Kolom     : snake_case, singular        → first_name, created_at
PK        : id                          → selalu pakai ini
FK        : {singular_table}_id         → user_id, product_id
Pivot     : {table1}_{table2}           → product_tag (alphabetical)
Boolean   : is_ atau has_               → is_active, has_discount
Timestamp : _at suffix                  → created_at, deleted_at
```

### Kolom Standar yang Selalu Ada
Setiap tabel wajib punya kolom berikut
(sintaks disesuaikan dengan engine yang digunakan):
```
id          → primary key, auto increment
created_at  → timestamp kapan data dibuat
updated_at  → timestamp kapan data terakhir diubah
```

Tabel yang datanya penting (tidak boleh benar-benar dihapus):
```
deleted_at  → timestamp soft delete, nullable
```

---

## Tipe Data per Database Engine

### MySQL
```
-- String
VARCHAR(255)       → nama, email, judul, slug
VARCHAR(100)       → kode, nomor telepon
TEXT               → deskripsi panjang
LONGTEXT           → konten sangat panjang, JSON besar
CHAR(2)            → kode negara, status fixed length

-- Number
TINYINT(1)         → boolean (0/1)
INT UNSIGNED       → angka positif sedang
BIGINT UNSIGNED    → ID, FK, angka besar (gunakan ini)
DECIMAL(10,2)      → harga, nilai uang (hindari FLOAT!)
DECIMAL(8,4)       → koordinat GPS, persentase presisi

-- Date & Time
DATE               → tanggal saja
TIME               → waktu saja
DATETIME           → tanggal + waktu tanpa timezone
TIMESTAMP          → tanggal + waktu dengan timezone
YEAR               → tahun saja

-- Lainnya
JSON               → data fleksibel, config, metadata
ENUM(...)          → nilai terbatas yang jarang berubah

-- Primary Key
id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY
```

---

### PostgreSQL
```
-- String
VARCHAR(255)       → nama, email, judul, slug
VARCHAR(100)       → kode, nomor telepon
TEXT               → deskripsi panjang (tidak perlu LONGTEXT)
CHAR(2)            → kode negara, status fixed length

-- Number
BOOLEAN            → true/false (bukan TINYINT)
INTEGER            → angka sedang
BIGINT             → ID, FK, angka besar (gunakan ini)
NUMERIC(10,2)      → harga, nilai uang (hindari FLOAT!)
NUMERIC(8,4)       → koordinat GPS, persentase presisi

-- Date & Time
DATE               → tanggal saja
TIME               → waktu saja
TIMESTAMP          → tanggal + waktu tanpa timezone
TIMESTAMPTZ        → tanggal + waktu dengan timezone (gunakan ini)

-- Lainnya
JSONB              → data fleksibel (lebih cepat dari JSON)
JSON               → data JSON tanpa indexing
TEXT CHECK(...)    → enum alternatif yang lebih fleksibel
-- atau gunakan CREATE TYPE untuk enum:
-- CREATE TYPE status AS ENUM ('pending','paid','cancelled')

-- Primary Key (pilih salah satu)
id BIGSERIAL PRIMARY KEY              -- auto increment klasik
id UUID DEFAULT gen_random_uuid()     -- UUID jika butuh distributed
```

---

### SQLite
```
-- String
TEXT               → semua jenis string (SQLite tidak punya VARCHAR)

-- Number
INTEGER            → semua angka bulat termasuk boolean (0/1)
REAL               → angka desimal
NUMERIC            → harga, nilai uang

-- Date & Time
TEXT               → simpan sebagai ISO 8601: '2024-01-15 10:30:00'
INTEGER            → simpan sebagai Unix timestamp
REAL               → simpan sebagai Julian day

-- Lainnya
BLOB               → binary data
-- SQLite tidak punya tipe JSON native, simpan sebagai TEXT

-- Primary Key
id INTEGER PRIMARY KEY AUTOINCREMENT
```

---

## Format Dokumentasi Skema

### Format Tabel
```markdown
### tabel: nama_tabel
> Deskripsi singkat fungsi tabel ini

| Kolom | Type | Null | Default | Keterangan |
|-------|------|------|---------|------------|
| id | [sesuai engine] | No | auto | Primary key |
| user_id | [sesuai engine] | No | — | FK → users.id |
| name | varchar(255) / text | No | — | Nama item |
| description | text | Yes | NULL | Deskripsi opsional |
| price | decimal(10,2) / numeric(10,2) | No | 0.00 | Harga |
| is_active | tinyint(1) / boolean | No | true | Status aktif |
| created_at | timestamp / timestamptz | Yes | NULL | — |
| updated_at | timestamp / timestamptz | Yes | NULL | — |
| deleted_at | timestamp / timestamptz | Yes | NULL | Soft delete |

**Indexes:**
- PRIMARY: id
- INDEX: user_id
- UNIQUE: email (jika ada kolom unique)

**Relations:**
- belongsTo users (via user_id)
```

---

## Panduan Relasi (Berlaku Semua Engine)

### One-to-Many (paling umum)
```
users --< orders
Artinya: satu user punya banyak order

Di tabel orders:
- Tambah kolom: user_id [type sesuai engine] NOT NULL
- Tambah index: INDEX(user_id)
- Tambah FK: FOREIGN KEY (user_id) REFERENCES users(id)
```

### Many-to-Many (butuh pivot table)
```
products >--< tags
Artinya: satu product punya banyak tag,
         satu tag bisa di banyak product

Buat pivot table: product_tag
| Kolom | Type |
|-------|------|
| product_id | [type sesuai engine] |
| tag_id | [type sesuai engine] |

PRIMARY KEY: (product_id, tag_id)
Tidak perlu id, created_at, updated_at di pivot sederhana.
Tambah timestamps jika perlu tahu kapan relasi dibuat.
```

### One-to-One
```
users --1 user_profiles
Artinya: satu user punya tepat satu profile

Di tabel user_profiles:
- Tambah kolom: user_id [type sesuai engine] NOT NULL
- Tambah UNIQUE: UNIQUE(user_id) ← ini yang buat one-to-one
```

---

## Panduan Index (Berlaku Semua Engine)

```
✅ Semua foreign key columns          → user_id, product_id
✅ Kolom yang sering di-WHERE         → status, is_active, email
✅ Kolom yang sering di-ORDER BY      → created_at, name
✅ Kolom yang sering di-JOIN          → sama dengan FK
✅ Kolom unique                       → email, slug, code

❌ Kolom boolean saja (low cardinality)
❌ Text/longtext columns
❌ Kolom yang jarang di-query
```

### Composite Index
```sql
-- Jika sering query: WHERE user_id = ? AND status = ?
INDEX(user_id, status)   -- urutan: kolom paling selektif dulu
```

---

## Format ERD ASCII

```
Gunakan simbol ini:
1 ──< banyak (one-to-many)
1 ── 1 (one-to-one)
>──< banyak-ke-banyak (many-to-many via pivot)

Contoh:
[users] 1 ──< [orders] 1 ──< [order_items] >── 1 [products]
   │                                                  │
   └── 1 [user_profiles]              [categories] ──< ┘
                                           │
                                      [products] ──< [product_images]
```

---

## Checklist Sebelum Output Schema

- [ ] Database engine sudah dicantumkan di header file
- [ ] Tipe data konsisten dengan engine yang dipilih
- [ ] Setiap tabel punya id, created_at, updated_at
- [ ] Tabel penting punya deleted_at (soft delete)
- [ ] Semua FK punya index
- [ ] Tidak ada typo nama tabel / kolom
- [ ] Semua relasi sudah terdokumentasi dua arah
- [ ] Nama tabel konsisten (semua plural)
- [ ] Pivot table nama sudah alphabetical
- [ ] Tidak ada kolom yang redundan / duplikat antar tabel

---

## File Output

Simpan hasil rancangan ke:
```
docs/
└── database-schema.md
```

Format file:
```markdown
# Database Schema — [Nama Project]

## Database Engine: [MySQL / PostgreSQL / SQLite]

## ERD
[ASCII diagram]

## Tabel

### tabel: users
[definisi lengkap]

### tabel: orders
[definisi lengkap]

... dan seterusnya

## Ringkasan Relasi
[daftar semua relasi]

## Migration Order
Urutan migration yang harus dibuat (dependency order):
1. users
2. categories
3. products (butuh categories)
4. orders (butuh users)
5. order_items (butuh orders + products)
```
