---
name: db-design
description: >
  Panduan merancang skema database untuk GetContactAIAgent.
  Fokus pada SQLite dengan aiosqlite.
---

# Database Design Skill - GetContactAIAgent

## Database Engine: SQLite

GetContactAIAgent menggunakan **SQLite** dengan **aiosqlite** (async).

---

## Prinsip Utama

### Naming Convention
```
Tabel     : snake_case, plural          → universities, ig_contacts
Kolom     : snake_case, singular        → ig_handle, created_at
PK        : id (TEXT/UUID)              → selalu pakai ini
FK        : {singular_table}_id         → university_id, contact_id
Boolean   : is_ atau has_               → is_active, has_verified
Timestamp : _at suffix                  → created_at, updated_at
```

### Kolom Standar (SQLite)
```sql
id          TEXT PRIMARY KEY  -- UUID, bukan auto increment
created_at  TEXT NOT NULL     -- ISO 8601 timestamp
updated_at  TEXT              -- ISO 8601 timestamp
```

---

## Tipe Data SQLite

```
String     → TEXT                    -- semua string
Number     → INTEGER                 -- semua angka bulat
Decimal    → REAL or NUMERIC         -- harga, koordinat
Boolean    → INTEGER (0/1)           -- true = 1, false = 0
DateTime   → TEXT (ISO 8601)         -- '2024-01-15 10:30:00'
JSON       → TEXT                    -- simpan sebagai JSON string
Blob       → BLOB                    -- binary data
```

### Examples
```sql
-- String
name TEXT NOT NULL
email TEXT NOT NULL
description TEXT

-- Number
status INTEGER DEFAULT 0
priority INTEGER DEFAULT 1

-- Boolean
is_active INTEGER DEFAULT 1  -- 1 = true, 0 = false
is_verified INTEGER DEFAULT 0

-- DateTime
created_at TEXT NOT NULL DEFAULT (datetime('now'))
updated_at TEXT
last_sync_at TEXT

-- JSON
metadata TEXT  -- '{"key": "value"}'
message_history TEXT  -- JSON array of messages
```

---

## Format Dokumentasi Skema

### Format Tabel
```markdown
### tabel: universities
> Data universitas yang akan dihubungi

| Kolom | Type | Null | Default | Keterangan |
|-------|------|------|---------|------------|
| id | TEXT | No | — | Primary key (UUID) |
| name | TEXT | No | — | Nama universitas |
| code | TEXT | No | — | Kode PDDIKTI |
| province | TEXT | Yes | NULL | Provinsi |
| ig_handle | TEXT | Yes | NULL | Instagram handle |
| created_at | TEXT | No | — | Timestamp dibuat |
| updated_at | TEXT | Yes | NULL | — |

**Indexes:**
- PRIMARY: id
- INDEX: code (UNIQUE)
- INDEX: province
- INDEX: ig_handle

**Relations:**
- hasMany ig_contacts (via university_id)
```

---

## Panduan Relasi (SQLite)

### One-to-Many
```sql
-- universities (1) ← (N) ig_contacts
-- Di tabel ig_contacts:
university_id TEXT NOT NULL
FOREIGN KEY (university_id) REFERENCES universities(id)
```

### Many-to-Many (pivot table)
```sql
-- Pivot untuk relasi many-to-many
CREATE TABLE university_tags (
    university_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    PRIMARY KEY (university_id, tag_id),
    FOREIGN KEY (university_id) REFERENCES universities(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
);
```

---

## Panduan Index

```
✅ Semua foreign key columns
✅ Kolom yang sering di-WHERE → status, is_active, province
✅ Kolom yang sering di-ORDER BY → created_at, name
✅ Kolom unique → code, email, slug

❌ Kolom boolean saja (low cardinality)
❌ TEXT columns yang sangat panjang
```

### Composite Index
```sql
-- Jika sering query: WHERE university_id = ? AND status = ?
CREATE INDEX idx_univ_status ON ig_contacts(university_id, status);
```

---

## Format ERD ASCII

```
[universities] 1 ──< [ig_contacts] 1 ──< [ig_posts]
                                    │
                             [conversations] ──< [messages]
```

---

## Schema Example (Existing in Project)

```markdown
### tabel: universities
> Master data universitas Indonesia

| Kolom | Type | Null | Default |
|-------|------|------|----------|
| id | TEXT | No | — |
| name | TEXT | No | — |
| code | TEXT | No | — |
| province | TEXT | Yes | NULL |
| website | TEXT | Yes | NULL |
| ig_handle | TEXT | Yes | NULL |
| created_at | TEXT | No | — |
| updated_at | TEXT | Yes | NULL |

### tabel: ig_contacts
> Kontak Instagram yang berhasil diekstrak

| Kolom | Type | Null | Default |
|-------|------|------|----------|
| id | TEXT | No | — |
| university_id | TEXT | Yes | NULL |
| ig_handle | TEXT | No | — |
| phone_number | TEXT | Yes | NULL |
| source_post_id | TEXT | Yes | NULL |
| created_at | TEXT | No | — |

### tabel: conversations
> Data percakapan WhatsApp dengan kontak

| Kolom | Type | Null | Default |
|-------|------|------|----------|
| id | TEXT | No | — |
| contact_id | TEXT | No | — |
| status | TEXT | No | 'PENDING' |
| current_state | TEXT | No | — |
| message_history | TEXT | Yes | NULL |
| created_at | TEXT | No | — |
| updated_at | TEXT | Yes | NULL |
```

---

## File Output

Simpan ke: `docs/database-schema.md`

```markdown
# Database Schema — GetContactAIAgent

## Database Engine: SQLite

## Existing Tables
[daftar tabel yang sudah ada]

## New Tables for [Feature Name]
[tabel baru untuk fitur ini]

## Migration Order
1. [tabel pertama]
2. [tabel yang bergantung pada tabel pertama]
3. [dst]
```
