# OSINT Agentic AI — Implementation Plan

## 1. Overview

Fitur **OSINT (Open Source Intelligence) Agent** — agentic system dengan dua kapabilitas utama:

1. **University Intelligence** — Profiling universitas secara otomatis (website, social media, key people, berita)
2. **PIC Profiling (Customer Relation)** — Deep profiling individu kontak kampus (PIC) untuk kebutuhan CRM/customer relation

### 1.1 Use Case Utama: Request Automation Customer Relation

PIC Marketing mem-request data client (PIC Kampus) melalui menu khusus. OSINT Agent secara otomatis mengumpulkan data berikut dari sumber publik:

**Identitas & Profesional**
- Nama PIC (input user)
- Jabatan (input user)
- Mengajar Mata Kuliah
- Sudah berapa lama di kampus tersebut
- Tanggal lahir, Umur, Asal daerah

**Keluarga**
- Status (menikah / belum)
- Suami / Istri
- Jumlah anak
- Keluarga tinggal di

**Kondisi & Perspektif Kampus**
- Problem yang sedang dihadapi kampus
- Kekhawatiran terkait mahasiswa / program
- Harapan terhadap pengembangan mahasiswa

**Personal Interest**
- Hobi / kesukaan
- Makanan favorit
- Kesibukan di luar kampus

**Sosial & Kontak**
- Social media (LinkedIn / IG / dll)
- Alamat rumah / domisili

> **Catatan:** Sebagian data bersifat personal dan **tidak bisa didapat 100% dari OSINT**. Strategi: OSINT agent mengisi apa yang bisa ditemukan dari sumber publik, sisanya di-flag sebagai "needs manual input" atau "needs conversation" (didapat saat follow-up WA/meeting).

## 2. Arsitektur Existing & Data yang Sudah Ada

### 2.1 Pipeline Agent Existing

| Agent | File | Fungsi |
|-------|------|--------|
| Agent 1 | `orchestrator/agents/ig_handle_finder.py` | Cari IG handle universitas |
| Agent 2 | `orchestrator/agents/ig_post_scraper.py` | Scrape post IG |
| Agent 3 | `orchestrator/agents/ig_phone_extractor.py` | Ekstrak nomor + nama (GPT Vision OCR) |
| Agent 4 | `orchestrator/agents/bem_finder.py` | Cari akun BEM & related IG |
| Agent 5 | `orchestrator/agents/rector_finder.py` | Cari nama rektor |
| Research | `orchestrator/research_agents/graph.py` | LangGraph pipeline riset audiensi |
| ReAct | `orchestrator/agent/react_agent.py` | ReAct agent untuk WA conversation |

Tools yang sudah ada dan bisa di-reuse:
- `duckduckgo_client.py` — search tanpa API key
- `instagram.py` — IG scraping (web API + Playwright + Apify)
- `apify_client.py` — backup scraper
- `scrapingbot_client.py` — backup scraper
- `playwright_ig.py` — browser automation

### 2.2 Data yang SUDAH Tersedia di DB (jangan dicari ulang)

OSINT Agent **WAJIB** query data existing terlebih dahulu sebelum mulai scraping/searching. Data berikut sudah ada:

#### Tabel `universities`
| Column | Contoh | Catatan |
|--------|--------|--------|
| `name` | Universitas Brawijaya | Nama lengkap ✓ |
| `pddikti_id` | abc-123 | ID PDDIKTI ✓ |
| `province` | Jawa Timur | Provinsi ✓ |
| `website` | https://ub.ac.id | Website resmi ✓ |
| `ig_handle` | @universitasbrawijaya | IG handle utama ✓ |
| `rector_name` | Prof. Dr. Widodo | Nama rektor ✓ (jika sudah di-fill) |
| `student_count` | 35000 | Jumlah mahasiswa ✓ |
| `secretariat_phone` | 0341-xxx | Telp sekretariat ✓ (jika sudah didapat) |
| `bem_ig_handle` | @bem_ub | IG BEM ✓ (jika sudah di-discover) |

#### Tabel `university_related_igs`
| Column | Contoh | Catatan |
|--------|--------|--------|
| `ig_handle` | @bemftub | IG handle terkait ✓ |
| `relation_type` | bem / fakultas | Tipe relasi ✓ |
| `confidence` | 0.85 | Score confidence ✓ |

#### Tabel `ig_contacts`
| Column | Contoh | Catatan |
|--------|--------|--------|
| `phone_number` | 6281234567890 | Nomor HP ✓ |
| `contact_name` | Bu Ratna | Nama kontak ✓ |
| `source_post_url` | https://ig/p/xxx | Sumber ✓ |

#### Tabel `conversations`
| Column | Contoh | Catatan |
|--------|--------|--------|
| `extracted_number` | 6281234567890 | Nomor sekretariat ✓ |
| `extracted_contact_name` | Bu Sari | Nama kontak ✓ |
| `extracted_contact_role` | Bag. Akademik | Role/jabatan ✓ |
| `message_history` | [...] | History chat WA ✓ |

#### Tabel `audiensi_conversations`
| Column | Contoh | Catatan |
|--------|--------|--------|
| `rector_name` | Prof. Dr. Widodo | Nama rektor ✓ (from research pipeline) |
| `contact_role` | Sekretaris | Role kontak ✓ |

#### Research Pipeline State (LangGraph — `research_agents/`)
| Field | Contoh | Catatan |
|-------|--------|--------|
| `rector_name` | Prof. Dr. Widodo, S.T., M.T. | Nama lengkap + gelar ✓ |
| `rector_birth_year` | 1970 | Tahun lahir ✓ |
| `rector_birth_city` | Malang | Kota lahir ✓ |
| `university_city` | Malang | Kota universitas ✓ |
| `tourism_*` | 3 variants | Data wisata ✓ |
| `food_*` | 2 variants | Data kuliner ✓ |
| `psychographics` | ... | Profil psikografis ✓ |

### 2.3 Prinsip: "Check Before Search"

```
Setiap OSINT agent HARUS:
1. Query DB dulu → load semua data existing untuk university_id
2. Check freshness → jika data < OSINT_REFRESH_DAYS, SKIP
3. Hanya cari data yang BELUM ADA atau EXPIRED
4. Jika data existing confidence tinggi → SKIP, jangan overwrite
5. Jika data existing confidence rendah → boleh re-search untuk upgrade
```

**Contoh flow:**
```
University OSINT dipanggil untuk "Universitas Brawijaya":
  → Query DB: website=ub.ac.id ✓, ig_handle=@universitasbrawijaya ✓, rector_name=Prof. Dr. Widodo ✓
  → Web Profiler: SKIP website scraping (sudah ada), fokus hanya data BARU (alamat, fax, fakultas)
  → Social Intel: SKIP IG (sudah ada), cari Facebook/YouTube/LinkedIn/TikTok saja
  → Key People: SKIP rektor (sudah ada), fokus dekan/kabag/humas
  → News Scanner: SELALU RUN (berita selalu berubah)
  → Contact Enricher: Gabung data baru + existing contacts dari ig_contacts
```

## 3. OSINT Pipeline Architecture

Sistem terdiri dari **2 pipeline** yang saling terhubung:

### 3A. University OSINT Pipeline (otomatis)

```
┌─────────────────────────────────────────────────────────────┐
│                University OSINT Orchestrator                 │
│                  (LangGraph StateGraph)                      │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Web Profiler │  │ Social Intel │  │ Key People Finder │  │
│  │   Agent      │  │   Agent      │  │     Agent         │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────────┘  │
│         │                 │                  │               │
│         └─────────┬───────┘──────────────────┘               │
│                   ▼                                          │
│          ┌────────────────┐                                  │
│          │ News & Event   │                                  │
│          │   Scanner      │                                  │
│          └───────┬────────┘                                  │
│                  ▼                                           │
│          ┌────────────────┐                                  │
│          │ Contact        │                                  │
│          │ Enricher       │                                  │
│          └───────┬────────┘                                  │
│                  ▼                                           │
│          ┌────────────────┐                                  │
│          │ Reviewer       │                                  │
│          │ (QA Gate)      │                                  │
│          └────────────────┘                                  │
└─────────────────────────────────────────────────────────────┘
```

### 3B. PIC Profiling Pipeline (triggered by CRM request)

```
┌──────────────────────────────────────────────────────────────────┐
│               PIC Profiling Orchestrator                          │
│                (LangGraph StateGraph)                             │
│                                                                  │
│  INPUT: nama PIC + jabatan + universitas (dari user)             │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ Identity         │  │ Social Media     │  │ Academic       │  │
│  │ Resolver Agent   │  │ Profiler Agent   │  │ Profiler Agent │  │
│  │                  │  │                  │  │                │  │
│  │ - Google name    │  │ - Find LinkedIn  │  │ - Mata kuliah  │  │
│  │ - Match to uni   │  │ - Find IG        │  │ - Lama kerja   │  │
│  │ - Birth info     │  │ - Find Twitter   │  │ - Publikasi    │  │
│  │ - Asal daerah    │  │ - Find Facebook  │  │ - Keahlian     │  │
│  └──────┬──────────┘  └──────┬───────────┘  └──────┬─────────┘  │
│         │                    │                      │            │
│         └────────────┬───────┘──────────────────────┘            │
│                      ▼                                           │
│         ┌────────────────────┐                                   │
│         │ Campus Context     │                                   │
│         │ Agent              │                                   │
│         │                    │                                   │
│         │ - Problem kampus   │                                   │
│         │ - Berita terkini   │                                   │
│         │ - Kekhawatiran     │                                   │
│         │ - Harapan          │                                   │
│         └────────┬───────────┘                                   │
│                  ▼                                               │
│         ┌────────────────────┐                                   │
│         │ Profile Compiler   │                                   │
│         │ & Reviewer         │                                   │
│         │                    │                                   │
│         │ - Gabung semua     │                                   │
│         │ - Confidence score │                                   │
│         │ - Flag "needs      │                                   │
│         │   manual input"    │                                   │
│         └────────────────────┘                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow — CRM Request

```
PIC Marketing buat request di menu "Customer Relation"
  → Input: Nama PIC, Jabatan, Universitas
  → PIC Profiling Pipeline start
    → Identity Resolver: Google "{nama} {universitas}" ─┐
    → Social Media Profiler: cari LinkedIn/IG/dll        ├─ parallel
    → Academic Profiler: cari mata kuliah, publikasi     ─┘
    → Campus Context: problem kampus, berita terkini
    → Profile Compiler: gabung, score, flag gaps
  → Profil tersimpan di DB
  → PIC Marketing review di dashboard
  → Data personal yang tidak ditemukan → flag "isi manual" / "tanyakan saat meeting"
```

## 4. Sub-Agents Detail

### Pipeline A — University OSINT

#### 4.1 Web Profiler Agent

**Tugas:** Scrape website resmi universitas untuk mengumpulkan informasi struktural.

**Existing data (SKIP jika sudah ada):**
- ~~Website URL~~ → sudah di `universities.website`
- ~~Provinsi~~ → sudah di `universities.province`
- ~~Jumlah mahasiswa~~ → sudah di `universities.student_count`

**Data BARU yang dikumpulkan (hanya ini):**
- Alamat lengkap kampus (bisa lebih dari 1 kampus)
- Nomor telepon, fax, email resmi (cross-check dgn `ig_contacts`)
- Daftar fakultas dan program studi
- Struktur organisasi (jika tersedia)
- Visi, misi (untuk bahan conversation)

**Sumber:** Website resmi universitas (`universities.website` → pakai URL dari DB), PDDIKTI

**Tools:** `httpx` + `BeautifulSoup` untuk scraping, GPT-4o-mini untuk extraction dari unstructured text

#### 4.2 Social Intel Agent

**Tugas:** Mapping semua social media presence universitas.

**Existing data (SKIP jika sudah ada):**
- ~~Instagram utama~~ → sudah di `universities.ig_handle`
- ~~IG BEM~~ → sudah di `universities.bem_ig_handle`
- ~~IG-IG terkait~~ → sudah di `university_related_igs` (BEM, fakultas, dll)
- ~~Website~~ → sudah di `universities.website`

**Data BARU yang dikumpulkan (hanya yang belum ada):**
- Facebook page
- Twitter / X
- YouTube channel
- LinkedIn page
- TikTok

**Sumber:** Google/DuckDuckGo search, website university, cross-reference dari social bio

**Tools:** `duckduckgo_client.py`, `httpx`, regex extraction

#### 4.3 Key People Finder Agent

**Tugas:** Identifikasi orang-orang kunci di universitas beserta kontak mereka.

**Existing data (SKIP jika sudah ada):**
- ~~Nama Rektor~~ → sudah di `universities.rector_name` dan research pipeline (`rector_info`)
- ~~Kontak-kontak IG~~ → sudah di `ig_contacts` (phone, nama, sumber)
- ~~Kontak dari WA conversations~~ → `conversations.extracted_contact_name` + `extracted_contact_role`
- ~~Telp sekretariat~~ → `universities.secretariat_phone`

**Data BARU yang dikumpulkan (hanya yang belum ada):**
- Wakil Rektor
- Dekan setiap fakultas
- Kabag Akademik / Kemahasiswaan
- Sekretaris universitas / fakultas
- Humas / PR contact
- Email (jika publik — belum ada di DB)

**Sumber:** Website universitas (halaman pimpinan/struktur), Google, berita

**Tools:** `duckduckgo_client.py`, `httpx`, GPT-4o-mini extraction

#### 4.4 News & Event Scanner Agent

**Tugas:** Cari berita terbaru dan event upcoming terkait universitas.

**Data yang dikumpulkan:**
- Berita terbaru (wisuda, MoU, prestasi, event)
- Event upcoming (seminar, dies natalis, wisuda)
- Prestasi dan penghargaan terbaru

**Kegunaan:** Bahan pembuka percakapan WhatsApp yang relevan & personal

**Sumber:** Google News, portal berita kampus, website resmi (section berita)

**Tools:** `duckduckgo_client.py` (news search), `httpx`, GPT-4o-mini summarization

#### 4.5 Contact Enricher Agent

**Tugas:** Agregasi dan validasi semua kontak — gabungkan data BARU dari OSINT + data EXISTING dari DB.

**Proses:**
1. Load existing: `ig_contacts` + `conversations` (extracted contacts) + `universities.secretariat_phone`
2. Kumpulkan kontak BARU dari agent 1-4
3. Merge & deduplicate (normalize nomor dgn `phonenumbers`, lowercase email)
4. Validasi format (nomor Indonesia, email valid)
5. Cross-reference: kontak yang muncul di >1 sumber = confidence lebih tinggi
6. Prioritas ranking: sekretariat > humas > dekan > generic
7. JANGAN overwrite data existing yang sudah `confirmed` — hanya tambahkan data baru

**Output:** Daftar kontak gabungan (existing + baru) terurut berdasarkan confidence & priority

#### 4.6 Reviewer Agent

**Tugas:** Quality assurance gate sebelum data di-commit ke DB.

**Checks:**
- Data consistency (alamat, kota sesuai universitas)
- Confidence scoring (high/medium/low per data point)
- Flag data yang perlu verifikasi manual
- Detect kemungkinan false positive (kontak orang salah, universitas salah)

---

### Pipeline B — PIC Profiling (Customer Relation)

#### 4.7 Identity Resolver Agent

**Tugas:** Resolusi identitas lengkap dari nama + jabatan + universitas yang di-input user.

**Check existing dulu:**
- Cek apakah PIC sudah pernah muncul di `conversations.extracted_contact_name`
- Cek apakah nama match dgn `universities.rector_name` → bisa langsung pakai data dari research pipeline (`rector_info.rector_birth_year`, `rector_birth_city`)
- Cek `ig_contacts.contact_name` → mungkin sudah ada phone number

**Data BARU yang dikumpulkan (hanya yang belum ada):**
- Full name verification (nama lengkap dengan gelar)
- Tanggal lahir, umur
- Asal daerah / kota kelahiran
- Alamat domisili (jika publik)
- Foto profil (jika tersedia)

**Strategi pencarian:**
1. Google: `"{nama}" "{universitas}" {jabatan}` 
2. Website universitas: halaman profil dosen / pimpinan
3. SINTA (portal dosen Indonesia): `sinta.kemdikbud.go.id`
4. Google Scholar: profil akademik
5. Portal berita lokal: wawancara / liputan

**OSINT-able:** Nama lengkap (✓), tanggal lahir (mungkin dari SINTA/berita), asal daerah (mungkin), domisili (kemungkinan rendah)

**Needs manual:** Tanggal lahir (jika tidak publik), domisili spesifik

#### 4.8 Social Media Profiler Agent

**Tugas:** Temukan semua akun social media personal PIC.

**Data yang dikumpulkan:**
- LinkedIn profile URL + headline
- Instagram personal
- Facebook personal
- Twitter / X
- TikTok (jika ada)

**Strategi pencarian:**
1. LinkedIn search: `"{nama}" "{universitas}"`
2. Google: `site:linkedin.com "{nama}" "{universitas}"`
3. Google: `site:instagram.com "{nama}"` + cross-reference bio
4. Facebook search: nama + universitas
5. Cross-reference: dari halaman universitas → link ke personal socmed

**OSINT-able:** LinkedIn (✓ tinggi), IG (✓ sedang), Facebook (✓ sedang)

#### 4.9 Academic Profiler Agent

**Tugas:** Profiling karir akademik dan keahlian PIC.

**Data yang dikumpulkan:**
- Mata kuliah yang diajar
- Keahlian / bidang riset
- Berapa lama di kampus tersebut (tenure)
- Riwayat pendidikan
- Publikasi ilmiah
- Jabatan fungsional (Lektor, Guru Besar, dll)

**Strategi pencarian:**
1. SINTA Kemdikbud: profil dosen lengkap (publikasi, sinta score)
2. Google Scholar: `"{nama}" "{universitas}"`
3. Website universitas: halaman profil dosen
4. Portal akademik: jurnal, prosiding
5. PDDIKTI: data dosen terdaftar

**OSINT-able:** Mata kuliah (✓), lama kerja (✓ dari SINTA), publikasi (✓), keahlian (✓)

#### 4.10 Campus Context Agent

**Tugas:** Kumpulkan konteks kampus yang relevan untuk conversation — problem, kekhawatiran, harapan.

**Check existing dulu:**
- Cek apakah research pipeline sudah pernah jalan untuk universitas ini → ambil `psychographics`, `tourism_*`, `food_*` dari cache
- Cek `audiensi_conversations.agent_reasoning` → mungkin ada insight dari audiensi sebelumnya
- Cek `conversations.message_history` → extract insights dari percakapan WA sebelumnya

**Data BARU yang dikumpulkan:**
- Problem yang sedang dihadapi kampus (akreditasi, penurunan mahasiswa, dll)
- Kekhawatiran terkait mahasiswa / program
- Harapan terhadap pengembangan mahasiswa
- Berita terkini tentang kampus + PIC
- Isu-isu pendidikan tinggi nasional yang relevan

**Strategi:**
1. Google News: `"{universitas}" masalah|tantangan|akreditasi|mahasiswa`
2. Portal berita kampus: section berita terbaru
3. Laporan PDDIKTI: data mahasiswa, akreditasi prodi
4. GPT inference: dari berita + data existing → generate insight tentang kemungkinan problem & harapan

**OSINT-able:** Problem kampus (✓ dari berita), kekhawatiran (⚠ inferensi GPT), harapan (⚠ inferensi GPT)

**Note:** Bagian "perspektif kampus" banyak yang bersifat opini personal — OSINT agent akan memberikan **educated guess** berdasarkan data publik, di-flag sebagai `confidence: inferred`

#### 4.11 Personal Interest Agent (best-effort)

**Tugas:** Cari informasi personal interest PIC dari sumber publik.

**Data yang dikumpulkan:**
- Hobi / kesukaan
- Makanan favorit
- Kesibukan di luar kampus

**Strategi:**
1. LinkedIn: posts, articles, interest sections
2. Instagram: bio, hashtags, post patterns
3. Facebook: about section, interest, groups
4. Wawancara / profil di media: `"{nama}" hobi|kesukaan|wawancara`
5. GPT inference dari social media activity patterns

**OSINT-able:** Sangat terbatas — hobi (⚠ jika ada di bio/posts), makanan favorit (✗ hampir mustahil), kesibukan (⚠ jika aktif di socmed)

**Needs manual:** Kebanyakan data ini perlu didapat dari conversation langsung

#### 4.12 Family Info Agent (best-effort)

**Tugas:** Cari informasi keluarga PIC dari sumber publik.

**Data yang dikumpulkan:**
- Status pernikahan
- Nama suami / istri
- Jumlah anak
- Keluarga tinggal di

**Strategi:**
1. Facebook: relationship status, family members, location
2. LinkedIn: posts tentang keluarga (anniversary, graduation anak)
3. Berita lokal: liputan acara keluarga
4. Social media cross-reference

**OSINT-able:** Sangat terbatas dan sensitif. Status pernikahan (⚠ mungkin dari Facebook), detail lainnya (✗ butuh conversation)

**⚠ Privacy note:** Data keluarga sangat sensitif. Agent akan HANYA mengumpulkan dari sumber yang secara **eksplisit publik** (public FB profile, public posts). Tidak akan melakukan intrusive scraping.

#### 4.13 Profile Compiler & Reviewer

**Tugas:** Gabungkan semua data dari agent 4.7-4.12, scoring, dan flag gaps.

**Output per field:**

| Field | Source | Status |
|-------|--------|--------|
| Nama PIC | User input | `confirmed` |
| Jabatan | User input + OSINT verification | `confirmed` / `updated` |
| Mata Kuliah | SINTA / website universitas | `found` / `not_found` |
| Lama di kampus | SINTA / website | `found` / `not_found` |
| Tanggal lahir | Berita / SINTA | `found` / `not_found` |
| Umur | Computed dari tanggal lahir | `computed` / `not_found` |
| Asal daerah | Berita / profil | `found` / `not_found` |
| Status menikah | Facebook / social | `found` / `needs_confirmation` |
| Suami/Istri | Facebook | `found` / `needs_manual` |
| Jumlah anak | — | `needs_manual` |
| Keluarga tinggal di | — | `needs_manual` |
| Problem kampus | Berita / inferensi | `inferred` |
| Kekhawatiran | Inferensi GPT | `inferred` |
| Harapan | Inferensi GPT | `inferred` |
| Hobi | Social media | `found` / `needs_manual` |
| Makanan favorit | — | `needs_manual` |
| Kesibukan luar kampus | Social / berita | `found` / `needs_manual` |
| Social media | LinkedIn/IG/dll | `found` |
| Alamat domisili | — | `needs_manual` |

## 5. Database Schema

### Tabel Baru — University OSINT

```sql
-- Profil utama hasil OSINT per universitas
CREATE TABLE IF NOT EXISTS osint_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    address TEXT,
    city TEXT,
    province TEXT,
    postal_code TEXT,
    phone_official TEXT,
    fax TEXT,
    email_official TEXT,
    website_verified TEXT,
    vision_mission TEXT,
    faculty_count INTEGER,
    faculty_list TEXT,             -- JSON array
    org_structure TEXT,            -- JSON
    confidence REAL DEFAULT 0.0,
    last_run_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(university_id)
);

-- Semua kontak universitas yang ditemukan
CREATE TABLE IF NOT EXISTS osint_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    name TEXT,
    title TEXT,
    department TEXT,
    phone TEXT,
    email TEXT,
    source TEXT,
    source_url TEXT,
    confidence REAL DEFAULT 0.0,
    priority INTEGER DEFAULT 0,
    verified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(university_id, phone, name)
);

-- Semua akun social media universitas
CREATE TABLE IF NOT EXISTS osint_social_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    platform TEXT NOT NULL,
    handle TEXT,
    url TEXT,
    followers INTEGER,
    verified INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.0,
    source TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(university_id, platform, handle)
);

-- Berita dan event terkait
CREATE TABLE IF NOT EXISTS osint_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    source TEXT,
    published_date TEXT,
    category TEXT,
    relevance_score REAL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Log OSINT runs
CREATE TABLE IF NOT EXISTS osint_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    status TEXT DEFAULT 'running',
    trigger_type TEXT DEFAULT 'manual',
    agents_completed TEXT,
    agents_failed TEXT,
    contacts_found INTEGER DEFAULT 0,
    social_media_found INTEGER DEFAULT 0,
    news_found INTEGER DEFAULT 0,
    duration_seconds REAL,
    error TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);
```

### Tabel Baru — PIC Profiling (Customer Relation)

```sql
-- Request profiling dari PIC Marketing
CREATE TABLE IF NOT EXISTS crm_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER REFERENCES universities(id),
    university_name TEXT,          -- denormalized untuk display
    requested_by TEXT,             -- nama PIC Marketing yang request
    status TEXT DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'partial', 'failed'
    pic_name TEXT NOT NULL,        -- nama PIC kampus (INPUT USER)
    pic_title TEXT,                -- jabatan (INPUT USER)
    priority TEXT DEFAULT 'normal', -- 'high', 'normal', 'low'
    notes TEXT,                    -- catatan dari requester
    run_id INTEGER,                -- link ke crm_profile_runs
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Profil lengkap PIC Kampus (hasil OSINT + manual input)
CREATE TABLE IF NOT EXISTS crm_pic_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES crm_requests(id),
    university_id INTEGER REFERENCES universities(id),

    -- Identitas & Profesional
    full_name TEXT,
    full_name_source TEXT,         -- 'user_input', 'osint', 'manual'
    title TEXT,                    -- jabatan
    title_source TEXT,
    teaching_subjects TEXT,        -- mata kuliah (JSON array)
    teaching_subjects_source TEXT,
    tenure_years INTEGER,          -- lama di kampus
    tenure_years_source TEXT,
    birth_date TEXT,
    birth_date_source TEXT,
    age INTEGER,
    origin_region TEXT,            -- asal daerah
    origin_region_source TEXT,
    education_history TEXT,        -- JSON: riwayat pendidikan
    education_history_source TEXT,
    photo_url TEXT,

    -- Keluarga
    marital_status TEXT,           -- 'menikah', 'belum_menikah', 'unknown'
    marital_status_source TEXT,
    spouse_name TEXT,
    spouse_name_source TEXT,
    children_count INTEGER,
    children_count_source TEXT,
    family_residence TEXT,         -- keluarga tinggal di
    family_residence_source TEXT,

    -- Kondisi & Perspektif Kampus
    campus_problems TEXT,          -- JSON array of identified problems
    campus_problems_source TEXT,
    campus_concerns TEXT,          -- kekhawatiran terkait mahasiswa/program
    campus_concerns_source TEXT,
    campus_hopes TEXT,             -- harapan pengembangan mahasiswa
    campus_hopes_source TEXT,

    -- Personal Interest
    hobbies TEXT,                  -- JSON array
    hobbies_source TEXT,
    favorite_food TEXT,
    favorite_food_source TEXT,
    outside_activities TEXT,       -- kesibukan di luar kampus
    outside_activities_source TEXT,

    -- Sosial & Kontak
    linkedin_url TEXT,
    instagram_handle TEXT,
    facebook_url TEXT,
    twitter_handle TEXT,
    other_social TEXT,             -- JSON: platform lain
    home_address TEXT,
    home_address_source TEXT,
    phone TEXT,
    email TEXT,

    -- Meta
    overall_confidence REAL DEFAULT 0.0,
    fields_found INTEGER DEFAULT 0,    -- berapa field yang berhasil diisi OSINT
    fields_total INTEGER DEFAULT 0,    -- total field yang diminta
    fields_manual INTEGER DEFAULT 0,   -- berapa field yang butuh manual input
    last_updated TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now'))
);

-- Log setiap run PIC profiling
CREATE TABLE IF NOT EXISTS crm_profile_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES crm_requests(id),
    status TEXT DEFAULT 'running',
    agents_completed TEXT,         -- JSON array
    agents_failed TEXT,            -- JSON array
    duration_seconds REAL,
    error TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

-- Sumber data per field (audit trail)
CREATE TABLE IF NOT EXISTS crm_profile_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES crm_pic_profiles(id),
    field_name TEXT NOT NULL,      -- 'birth_date', 'hobbies', etc.
    value TEXT,
    source_type TEXT,              -- 'osint', 'manual', 'inferred', 'conversation'
    source_url TEXT,
    confidence REAL DEFAULT 0.0,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

## 6. Backend Structure

### File Map

```
orchestrator/osint/
├── __init__.py              # exports: run_osint_pipeline, run_osint_batch
├── graph.py                 # LangGraph StateGraph — university OSINT
├── state.py                 # TypedDict state + Pydantic output models
├── web_profiler.py          # Agent: website scraping & info extraction
├── social_intel.py          # Agent: social media discovery
├── key_people.py            # Agent: key people identification
├── news_scanner.py          # Agent: news & events
├── contact_enricher.py      # Agent: contact aggregation & validation
├── reviewer.py              # Agent: QA gate
└── tools.py                 # Shared tools: search, scrape, extract

orchestrator/crm/
├── __init__.py              # exports: run_pic_profiling, create_crm_request
├── graph.py                 # LangGraph StateGraph — PIC profiling pipeline
├── state.py                 # TypedDict state + Pydantic models for PIC profile
├── identity_resolver.py     # Agent: Google/SINTA identity resolution
├── social_profiler.py       # Agent: find personal social media
├── academic_profiler.py     # Agent: SINTA, Scholar, teaching info
├── campus_context.py        # Agent: campus problems, concerns, hopes
├── personal_interest.py     # Agent: hobbies, food, activities (best-effort)
├── family_info.py           # Agent: marital status, family (best-effort)
├── profile_compiler.py      # Agent: compile all + confidence scoring + gap flagging
└── tools.py                 # Shared: SINTA scraper, LinkedIn scraper, etc.
```

### API Endpoints

```python
# ==================== University OSINT ====================

POST /osint/run/{university_id}
→ { "run_id": 123, "status": "started" }

POST /osint/run-batch
Body: { "university_ids": [1,2,3], "limit": 20, "filter_status": "ig_found" }
→ { "runs": [...], "total": 3 }

GET /osint/profile/{university_id}
→ { "profile": {...}, "contacts": [...], "social_media": [...], "news": [...] }

GET /osint/runs?page=1&limit=20
→ { "runs": [...], "total": 50 }

GET /osint/runs/{run_id}
→ { "run_id": 123, "status": "running", "agents_completed": [...] }

# ==================== CRM / PIC Profiling ====================

# Buat request profiling baru
POST /crm/requests
Body: {
    "university_id": 42,
    "pic_name": "Dr. Ahmad Fauzi, M.Pd.",
    "pic_title": "Wakil Rektor I",
    "requested_by": "Budi Marketing",
    "priority": "high",
    "notes": "Meeting minggu depan"
}
→ { "request_id": 1, "status": "pending" }

# List semua CRM requests
GET /crm/requests?status=pending&page=1&limit=20
→ { "requests": [...], "total": 15 }

# Detail request + profil PIC
GET /crm/requests/{request_id}
→ { "request": {...}, "profile": {...}, "sources": [...] }

# Trigger OSINT profiling untuk request
POST /crm/requests/{request_id}/run
→ { "run_id": 1, "status": "processing" }

# Update profil secara manual (isi field yang tidak ketemu OSINT)
PATCH /crm/profiles/{profile_id}
Body: {
    "marital_status": "menikah",
    "spouse_name": "Dr. Siti Aminah",
    "children_count": 2,
    "favorite_food": "Nasi Goreng Kambing",
    "source_type": "manual"      -- atau "conversation"
}
→ { "status": "updated", "fields_updated": [...] }

# Lihat profil PIC lengkap (gabungan OSINT + manual)
GET /crm/profiles/{profile_id}
→ { "profile": {...}, "completion_rate": 0.72, "gaps": [...] }

# Export profil ke format yang readable
GET /crm/profiles/{profile_id}/export?format=pdf
→ PDF / JSON report

# Dashboard stats
GET /crm/stats
→ { "total_requests": 50, "completed": 35, "avg_completion_rate": 0.68 }
```

## 7. Frontend

### Halaman Baru 1: OSINT Dashboard (`/osint`)

**Komponen utama:**
- **University OSINT Table** — list universitas dengan status OSINT (not started, in progress, completed)
- **OSINT Profile Card** — profil lengkap universitas setelah OSINT selesai
- **Run History** — log semua OSINT runs dengan status dan durasi
- **Batch Actions** — trigger OSINT untuk batch universitas

### Halaman Baru 2: Customer Relation (`/crm`)

**Menu utama di sidebar — "Customer Relation"**

**Sub-pages:**

#### `/crm` — Request List (Landing)
- Table semua CRM requests dengan kolom: PIC, Universitas, Status, Completion %, Requester, Tanggal
- Filter: status (pending/processing/completed), priority, universitas
- Tombol "+ New Request"
- Bulk trigger OSINT

#### `/crm/new` — Form Request Baru
- Form input:
  - Universitas (autocomplete dari DB)
  - Nama PIC Kampus (text input) — **REQUIRED**
  - Jabatan (text input) — **REQUIRED**
  - Priority (dropdown: high/normal/low)
  - Notes (textarea)
- Tombol "Submit & Run OSINT" (langsung trigger) atau "Save Draft"

#### `/crm/requests/:id` — Detail Request + Profil PIC
- **Header:** Nama PIC, Jabatan, Universitas, Status, Completion Rate (progress bar)
- **Profil Card** dengan semua kategori:

  **Identitas & Profesional**
  | Field | Nilai | Source | Status |
  |-------|-------|--------|--------|
  | Nama | Dr. Ahmad Fauzi, M.Pd. | user_input | ✅ confirmed |
  | Jabatan | Wakil Rektor I | osint | ✅ found |
  | Mata Kuliah | Matematika, Statistik | osint (SINTA) | ✅ found |
  | Lama di Kampus | 12 tahun | osint (SINTA) | ✅ found |
  | Tanggal Lahir | — | — | ⚠️ needs manual |
  | Umur | — | — | ⚠️ needs manual |
  | Asal Daerah | Padang | osint (berita) | 🔍 found |

  **Keluarga**
  | Field | Nilai | Source | Status |
  |-------|-------|--------|--------|
  | Status | Menikah | osint (Facebook) | 🔍 needs confirmation |
  | Suami/Istri | — | — | ⚠️ needs manual |
  | Jumlah Anak | — | — | ⚠️ needs manual |
  | Tinggal di | — | — | ⚠️ needs manual |

  (dst untuk semua kategori...)

- **Setiap field** bisa di-edit manual (inline edit / modal)
- **Source trail:** klik source → lihat URL sumber
- **Action buttons:**
  - "Re-run OSINT" — jalankan ulang pipeline
  - "Export PDF" — export profil
  - "Mark Complete" — tandai sudah lengkap

#### `/crm/stats` — Dashboard Statistik
- Total requests, completion rate avg, top requesters
- Chart: requests per week, completion trend
- Leaderboard: universitas dengan profil terlengkap

### Integrasi di University Detail Page

- Tab baru **"Intelligence"** di `UniversityDetailPage.tsx`
- Menampilkan: profil OSINT universitas + list PIC yang sudah di-profile
- Link ke CRM request untuk PIC baru

## 8. Scheduler Integration

```python
# Di scheduler.py, tambahkan:

# Auto-run OSINT sebelum outreach (opsional, configurable)
scheduler.add_job(
    _threaded_osint_enrichment,
    "interval", hours=6,
    id="osint_enrichment",
    name="OSINT Enrichment"
)

# OSINT dijalankan untuk universitas yang:
# 1. Status 'ig_found' atau 'ig_scraped'
# 2. Belum punya osint_profile
# 3. Atau osint_profile sudah >7 hari (refresh)
```

## 9. WhatsApp Agent Integration

Data OSINT diinject ke conversation agent sebagai context:

```python
# Di agent/tools.py, tambahkan tool baru:
# get_osint_profile(university_name) → returns OSINT data

# Di agent/prompts.py, inject OSINT data ke system prompt:
# "Informasi tambahan tentang {university}:
#  - Rektor: {rector_name}
#  - Berita terbaru: {latest_news}
#  - Event: {upcoming_events}"
```

## 10. Implementation Phases

### Phase 1 — Foundation: DB + CRM Request Flow
- [ ] Buat semua tabel database (`osint_*` + `crm_*`)
- [ ] API: `POST /crm/requests`, `GET /crm/requests`, `GET /crm/requests/:id`
- [ ] API: `PATCH /crm/profiles/:id` (manual edit)
- [ ] Frontend: Halaman CRM Request List + Form New Request
- [ ] Frontend: Halaman Detail Request (tampilan profil kosong, manual edit only)
- [ ] Test: bisa create request, edit manual, list/filter

### Phase 2 — OSINT Core: University Intelligence
- [ ] Buat `orchestrator/osint/state.py` + `tools.py`
- [ ] Implement `web_profiler.py` + `contact_enricher.py`
- [ ] Implement `social_intel.py` + `key_people.py`
- [ ] Buat `orchestrator/osint/graph.py` (LangGraph pipeline)
- [ ] API: `POST /osint/run/{id}`, `GET /osint/profile/{id}`
- [ ] Frontend: OSINT Dashboard + University Detail tab "Intelligence"
- [ ] Test: run OSINT untuk 5 universitas

### Phase 3 — PIC Profiling Pipeline
- [ ] Buat `orchestrator/crm/state.py` + `tools.py`
- [ ] Implement `identity_resolver.py` (Google + SINTA + website)
- [ ] Implement `academic_profiler.py` (SINTA, Scholar, website)
- [ ] Implement `social_profiler.py` (LinkedIn, IG, Facebook)
- [ ] Implement `campus_context.py` (berita + GPT inference)
- [ ] Implement `personal_interest.py` + `family_info.py` (best-effort)
- [ ] Implement `profile_compiler.py` (gabung + score + flag gaps)
- [ ] Buat `orchestrator/crm/graph.py` (LangGraph pipeline)
- [ ] API: `POST /crm/requests/:id/run`
- [ ] Test: end-to-end CRM request → OSINT → profil

### Phase 4 — Full Frontend
- [ ] CRM Detail page: profil lengkap dengan semua kategori
- [ ] Inline edit per field + source trail
- [ ] Status badges (confirmed/found/inferred/needs_manual)
- [ ] Re-run OSINT button
- [ ] CRM Stats dashboard
- [ ] Real-time progress via WebSocket

### Phase 5 — News + Reviewer + Polish
- [ ] Implement `news_scanner.py` (university + PIC news)
- [ ] Implement `reviewer.py` (QA gate untuk kedua pipeline)
- [ ] Scheduler integration: auto-OSINT sebelum outreach
- [ ] WA Agent integration: inject OSINT/CRM data ke conversation context
- [ ] Export profil ke PDF
- [ ] Retry mechanism + partial results fallback

## 11. Config Keys (di Settings page)

| Key | Default | Deskripsi |
|-----|---------|-----------|
| `OSINT_ENABLED` | `true` | Enable/disable OSINT pipeline |
| `OSINT_AUTO_RUN` | `false` | Auto-run sebelum outreach |
| `OSINT_REFRESH_DAYS` | `7` | Refresh OSINT data setelah N hari |
| `OSINT_MAX_CONCURRENT` | `3` | Max concurrent OSINT runs |
| `OSINT_NEWS_MAX_AGE_DAYS` | `90` | Ambil berita max N hari ke belakang |
| `OSINT_MIN_CONFIDENCE` | `0.5` | Min confidence untuk simpan data |
| `CRM_AUTO_RUN_ON_CREATE` | `true` | Auto-trigger OSINT saat CRM request dibuat |
| `CRM_SINTA_ENABLED` | `true` | Enable SINTA scraping untuk profil dosen |
| `CRM_LINKEDIN_ENABLED` | `true` | Enable LinkedIn search |
| `CRM_FAMILY_AGENT_ENABLED` | `false` | Enable family info agent (sensitive, off by default) |

## 12. Data Source Directory — Panduan Lengkap untuk Agent

Agar setiap OSINT agent tahu **dimana harus mencari**, berikut katalog lengkap semua sumber data.

### 12.1 Sumber Data yang SUDAH ADA di Codebase

#### A. DuckDuckGo Search (FREE — Primary Web Search)
- **Module:** `duckduckgo_client.py`
- **Fungsi:** `async_search_text(query, max_results, region)`
- **Rate limit:** 2.5s gap antar query, auto retry 10s on 429
- **Region:** `id-id` (Indonesia)
- **Output:** `[{title, link, snippet}]`
- **Cocok untuk:**
  - Cari profil orang: `"{nama}" "{universitas}" dosen|rektor|dekan`
  - Cari social media: `site:linkedin.com "{nama}" "{universitas}"`
  - Cari berita: `"{universitas}" berita|akreditasi|mahasiswa 2025 2026`
  - Cari website kampus: `"{universitas}" website resmi`

#### B. Google Gemini + Google Search Grounding (PAID — Deep Research)
- **Module:** `research_agents/gemini_caller.py`
- **Model:** `gemini-3.1-pro-preview`
- **Fitur utama:** Google Search grounding bawaan — Gemini otomatis cari Google dan lampirkan URL sumber
- **Auth:** `GEMINI_API_KEY`
- **Cocok untuk:**
  - Riset mendalam yang butuh reasoning + search sekaligus
  - "Siapa rektor [univ] saat ini? Kapan lahir? Dari mana?"
  - "Apa masalah utama [univ] tahun 2025-2026?"
  - Topic research dengan auto-grounding URL

#### C. Serper.dev Google Search (PAID — Fallback)
- **Module:** `instagram.py`, `rector_finder.py`
- **Endpoint:** `POST https://google.serper.dev/search`
- **Auth:** `X-API-KEY` header, key dari `SERPER_API_KEY`
- **Status:** Legacy fallback (DDG adalah primary)
- **Cocok untuk:** Backup jika DDG down/rate-limited

#### D. Instagram Scraping (4-Tier)

| Tier | Module | Cost | Capability |
|------|--------|------|------------|
| 0 (primary) | `playwright_ig.py` | Free | Profile, posts, following list, search |
| 1 | `instagram.py` direct API | Free | Profile, posts (butuh session cookie) |
| 2 | `apify_client.py` | Paid | Profile, posts, profile search |
| 3 | `scrapingbot_client.py` | Paid | Profile, posts |

- **Data bisa didapat:** bio, full_name, follower count, following list, external_url, posts (caption + image + timestamp)
- **Cocok untuk:**
  - Cari akun IG personal PIC dari bio universitas
  - Analisis posts untuk hobi/interest (dari caption & hashtags)
  - Follow list kampus → discover related accounts

#### E. PDDIKTI API (FREE — Data Resmi Kampus + Dosen) ⭐⭐ GOLDMINE
- **Library:** `pddiktipy` (sudah installed)
- **Endpoint:** `https://api-pddikti.kemdiktisaintek.go.id/`
- **Sudah dipakai di:** `instagram.py` (website lookup), `scripts/collect_universities.py`

**E1. Data Perguruan Tinggi:**

| Method pddiktipy | Data | Catatan |
|---|---|---|
| `search_pt(nama)` | id, nama, kode, nama_singkat | Cari kampus |
| `get_jumlah_dosen_pt(pt_id)` | Total dosen aktif | e.g. UB = 2,509 |
| `get_jumlah_mahasiswa_pt(pt_id)` | Total mahasiswa | |
| `get_prodi_pt(pt_id, tahun)` | List prodi + akreditasi + jumlah dosen + jumlah mahasiswa + rasio | Sangat lengkap! |
| `get_rasio_pt(pt_id)` | Rasio dosen:mahasiswa | e.g. "1:13" |
| `get_data_pt_akreditasi()` | Distribusi akreditasi nasional | |
| `get_graduation_rate_pt(pt_id)` | Tingkat kelulusan | |
| `get_waktu_studi_pt(pt_id)` | Rata-rata waktu studi | |
| `get_mahasiswa_pt(pt_id)` | Daftar mahasiswa | |

**E2. Data Dosen (BARU — Belum dipakai!)** ⭐

| Method pddiktipy | Data yang Didapat | Fields |
|---|---|---|
| `search_dosen(nama)` | Cari dosen by nama | `id, nama, nidn, nuptk, nama_pt, singkatan_pt, nama_prodi` |
| `get_dosen_profile(dosen_id)` | Profil lengkap | `nama_dosen, nama_pt, nama_prodi, jenis_kelamin, jabatan_akademik, pendidikan_tertinggi, status_ikatan_kerja, status_aktivitas` |
| `get_dosen_study_history(dosen_id)` | Riwayat pendidikan | `tahun_masuk, tahun_lulus, nama_prodi, jenjang, nama_pt, gelar_akademik, singkatan_gelar` |
| `get_dosen_teaching_history(dosen_id)` | Mata kuliah yg diajar | `nama_semester, kode_matkul, nama_matkul, nama_kelas, nama_pt` |
| `get_dosen_penelitian(dosen_id)` | Riset/penelitian | `judul_kegiatan, tahun_kegiatan, jenis_kegiatan` |
| `get_dosen_pengabdian(dosen_id)` | Pengabdian masyarakat | `judul_kegiatan, tahun_kegiatan` |
| `get_dosen_karya(dosen_id)` | Karya ilmiah/prosiding | `judul_kegiatan, tahun_kegiatan, jenis_kegiatan` |
| `get_dosen_paten(dosen_id)` | Paten/HKI | `judul_kegiatan, tahun_kegiatan, jenis_kegiatan` |

**Contoh data dosen dari PDDIKTI:**
```
search_dosen("Widodo") →
  nama: WIDODO SETIYO WIBOWO
  nidn: 0025028602
  nama_pt: UNIVERSITAS NEGERI YOGYAKARTA
  nama_prodi: Pendidikan Ilmu Pengetahuan Alam

get_dosen_profile(id) →
  jabatan_akademik: Lektor
  pendidikan_tertinggi: S2
  status_ikatan_kerja: Dosen Tetap
  status_aktivitas: Aktif

get_dosen_study_history(id) →
  S1: Pendidikan Fisika @ UNY (2004-2008) → S.Pd
  S2: Pendidikan Sains @ UNY (2009-2011) → M.Pd
  → Bisa hitung: sudah di UNY sejak 2004 = 22 tahun!
  → Bisa infer: asal mungkin Yogyakarta/Jawa Tengah

get_dosen_teaching_history(id) →
  Videografi, Media Pembelajaran Berbasis Komputer (2025/2026)
  → Bisa tahu mata kuliah yang diajar!
```

**Mapping PDDIKTI Dosen → PIC Profile Fields:**

| PIC Field | PDDIKTI Source | Confidence |
|-----------|---------------|------------|
| Nama lengkap + gelar | `search_dosen` + `study_history` | ✅ 100% |
| Jabatan akademik | `get_dosen_profile.jabatan_akademik` | ✅ 100% |
| Mata kuliah | `get_dosen_teaching_history` | ✅ 100% |
| Lama di kampus | `get_dosen_study_history.tahun_masuk` (S1) → hitung | ✅ 90% |
| NIDN | `search_dosen.nidn` | ✅ 100% |
| Pendidikan | `get_dosen_study_history` (semua jenjang) | ✅ 100% |
| Bidang riset | `get_dosen_penelitian` → GPT summarize | ✅ 85% |
| Publikasi | `get_dosen_karya` + `get_dosen_penelitian` | ✅ 90% |
| Asal daerah | Infer dari lokasi S1/S2 + DDG fallback | ⚠️ 40% |
| Jenis kelamin | `get_dosen_profile.jenis_kelamin` | ✅ 100% |

**PDDIKTI adalah sumber #1 untuk profiling dosen/PIC kampus — WAJIB dicek pertama sebelum search engine!**

#### F. OpenAI GPT-4o Vision (PAID — OCR & Image Analysis)
- **Module:** `instagram.py`
- **Cocok untuk:** Extract text dari gambar (phone numbers, flyer, poster)

#### G. OpenAI GPT-4o-mini (PAID — Text Processing)
- **Module:** `instagram.py`, `rector_finder.py`, `conversation.py`
- **Cocok untuk:**
  - Extract structured data dari unstructured text
  - Inference/reasoning dari kumpulan data
  - Summarization berita

#### H. DMS MySQL (INTERNAL — Data Audiensi)
- **Module:** `dms_mysql.py`
- **Tables:** `schedule_follow_up`, `meeting_audiensi`, `universitas`, `kontak_universitas`, `kontak_auto`
- **Data:** Jadwal audiensi, kontak yang sudah dihubungi, hasil meeting

#### I. University Website Scraping (FREE — Direct HTTP)
- **Module:** `instagram.py`, `rector_finder.py`
- **Path patterns yang di-scrape:**
  - `/profil`, `/pimpinan`, `/tentang/pimpinan` — mencari nama rektor/pimpinan
  - Homepage — mencari link social media di header/footer
- **Tools:** `httpx` + regex/BeautifulSoup

---

### 12.2 Sumber Data BARU yang Perlu Diintegrasikan

#### J. SINTA Kemdikbud (FREE — Profil Dosen Indonesia) ⭐ PRIORITAS TINGGI
- **URL:** `https://sinta.kemdikbud.go.id`
- **Search:** `https://sinta.kemdikbud.go.id/authors?q={nama}`
- **Profile:** `https://sinta.kemdikbud.go.id/authors/profile/{sinta_id}`
- **Akses:** Web scraping (HTML) — belum ada API resmi
- **Data yang bisa didapat:**
  - ✅ Nama lengkap + gelar
  - ✅ NIDN (Nomor Induk Dosen Nasional) — bisa cross-reference dgn PDDIKTI
  - ✅ Universitas afiliasi (verification)
  - ✅ Bidang keahlian / mata kuliah
  - ✅ Sinta Score (S1-S6)
  - ✅ Jumlah publikasi + h-index
  - ✅ Google Scholar ID (link) → bisa langsung akses Scholar
  - ⚠️ Kadang ada: tahun pertama afiliasi → bisa hitung lama di kampus
  - ✅ Foto profil (kadang ada)
- **Strategi:** Cari di PDDIKTI dulu (dapat NIDN) → gunakan NIDN untuk search di SINTA
- **Untuk agent:** Identity Resolver, Academic Profiler
- **Implementation:** `httpx` + `BeautifulSoup` + cache result

#### K. Google Scholar (FREE — Profil Akademik)
- **URL:** `https://scholar.google.com/citations?user={scholar_id}`
- **Search:** `https://scholar.google.com/scholar?q=author:"{nama}"+{universitas}`
- **Data yang bisa didapat:**
  - ✅ Interests/bidang riset
  - ✅ Publikasi + citation count
  - ✅ Co-author (kolega — bisa jadi leads kontak lain)
  - ✅ Foto profil (kadang)
  - ⚠️ Affiliasi + homepage link
- **Untuk agent:** Academic Profiler
- **Rate limit:** Agresif — butuh random delay 5-15s

#### L. LinkedIn Search (FREE/LIMITED — Profil Profesional)
- **Method 1 — Via DuckDuckGo/Google:**
  - Query: `site:linkedin.com/in "{nama}" "{universitas}"`
  - Data: nama, headline, lokasi (dari snippet)
- **Method 2 — Via LinkedIn Public Profile:**
  - URL: `https://www.linkedin.com/in/{username}`
  - Scraping: sangat limited tanpa login, tapi headline + lokasi + bio biasanya visible
- **Data yang bisa didapat:**
  - ✅ Headline (jabatan current)
  - ✅ Lokasi (kota)
  - ⚠️ Pengalaman kerja → lama di kampus
  - ⚠️ Pendidikan terakhir
  - ⚠️ Skills & interests
  - ❌ Detail lebih dalam butuh LinkedIn login
- **Untuk agent:** Social Media Profiler, Identity Resolver
- **Note:** Jangan scrape agresif — cukup dari search snippet + public page

#### M. Facebook Search (FREE/LIMITED — Data Personal)
- **Method — Via DuckDuckGo/Google:**
  - Query: `site:facebook.com "{nama}" "{kota universitas}"`
  - Query: `site:facebook.com "{nama}" dosen|universitas`
- **Data yang bisa didapat (jika profil publik):**
  - ⚠️ Status relationship
  - ⚠️ Family members
  - ⚠️ Lokasi tinggal
  - ⚠️ Interests, groups
  - ⚠️ Posts publik tentang hobi/keluarga
- **Untuk agent:** Family Info Agent, Personal Interest Agent
- **Note:** Sangat bergantung pada privacy setting user — success rate rendah

#### N. Google News Search (FREE — Berita Terkini)
- **Method 1 — Via DuckDuckGo:**
  - Query: `"{universitas}" berita 2025 2026`
  - Query: `"{nama}" "{universitas}" wawancara|profil|berita`
- **Method 2 — Via Gemini + Google Search grounding:**
  - Prompt: "Cari berita terbaru tentang {universitas} dalam 3 bulan terakhir"
  - Bonus: otomatis dapat grounding URLs
- **Data yang bisa didapat:**
  - ✅ Problem kampus (akreditasi, penurunan, bencana)
  - ✅ Prestasi & penghargaan
  - ✅ Event (wisuda, seminar, dies natalis)
  - ✅ MoU / kerjasama baru
  - ⚠️ Profil orang (dari wawancara media)
  - ⚠️ Asal daerah (dari berita pelantikan/inauguration)
- **Untuk agent:** News Scanner, Campus Context, Identity Resolver

#### O. Portal Berita Pendidikan (FREE — Sektor-Specific)
- **Sumber:**
  - `https://www.kompas.com/edu/`
  - `https://edukasi.sindonews.com/`
  - `https://www.republika.co.id/pendidikan`
  - `https://www.kemdikbud.go.id/main/` — portal resmi
  - `https://dikti.kemdikbud.go.id/` — portal dikti
  - `https://lldikti{region}.kemdikbud.go.id/` — per region
- **Akses:** Direct scraping / Google search `site:kompas.com/edu "{universitas}"`
- **Untuk agent:** Campus Context, News Scanner

#### P. BAN-PT / Akreditasi (FREE — Data Akreditasi)
- **URL:** `https://www.banpt.or.id/`
- **Data:**
  - ✅ Status akreditasi institusi (A/B/C/Unggul/Baik Sekali/Baik)
  - ✅ Status akreditasi per prodi
  - ✅ Tanggal expired akreditasi
- **Note:** PDDIKTI `get_prodi_pt()` sudah punya data akreditasi per prodi — bisa dipakai duluan
- **Untuk agent:** Campus Context (apakah kampus sedang was-was soal reakreditasi?)

#### Q. Garuda (Kemdikbud) — Portal Jurnal Indonesia (FREE)
- **URL:** `https://garuda.kemdikbud.go.id`
- **Search:** `https://garuda.kemdikbud.go.id/author?q={nama}`
- **Data:**
  - ✅ Daftar publikasi lengkap di jurnal Indonesia
  - ✅ Nama jurnal + tahun + DOI
  - ✅ Co-author (bisa jadi kontak tambahan)
  - ✅ Bidang penelitian (dari keyword artikel)
- **Untuk agent:** Academic Profiler
- **Relasi:** Pelengkap `get_dosen_karya()` PDDIKTI + SINTA

#### R. Repositori Kampus (FREE — Skripsi/Tesis/Disertasi)
- **Pattern URL:** `http://repository.{domain}/` atau `http://eprints.{domain}/`
- **Search:** DDG `site:repository.{domain} "{nama dosen}" pembimbing|penguji`
- **Data:**
  - ✅ Daftar mahasiswa yang dibimbing → aktif sebagai pembimbing
  - ✅ Topik bimbingan → bidang keahlian spesifik
  - ✅ Tahun bimbingan → konfirmasi masih aktif
- **Untuk agent:** Academic Profiler
- **Note:** Tidak semua kampus punya repositori publik

#### S. Scopus / Web of Science (FREE search / PAID full)
- **Scopus search:** `https://www.scopus.com/freelookup/form/author.uri`
- **Via DDG:** `site:scopus.com "{nama}" "{universitas}"`
- **Data:** h-index internasional, publikasi Q1-Q4, co-authors global
- **Untuk agent:** Academic Profiler (high-profile dosen)
- **Note:** Hanya relevan untuk dosen yang produktif riset

#### T. ResearchGate (FREE — Profil Peneliti)
- **Via DDG:** `site:researchgate.net "{nama}" "{universitas}"`
- **Data:**
  - ✅ Profil foto
  - ✅ Research interest
  - ✅ Publikasi + citation
  - ✅ Network/co-authors
  - ⚠️ Questions & answers (menunjukkan expertise area)
- **Untuk agent:** Academic Profiler, Identity Resolver

#### U. Portal Berita Daerah (FREE — Berita Lokal)
- **Sumber per region:**
  - Jawa Timur: `jatimtimes.com`, `malangtimes.com`, `surabayaonline.co`
  - Jawa Barat: `jabar.tribunnews.com`, `pikiran-rakyat.com`
  - Jawa Tengah: `jateng.tribunnews.com`, `solopos.com`
  - Sumatra: `sumut.tribunnews.com`, `goriau.com`, `palembang.tribunnews.com`
  - Kalimantan: `kaltim.tribunnews.com`, `banjarmasin.tribunnews.com`
  - Sulawesi: `makassar.tribunnews.com`, `sulsel.tribunnews.com`
  - Bali & NTT: `bali.tribunnews.com`, `kupang.tribunnews.com`
  - dll — banyak cabang tribunnews.com per region
- **Via DDG:** `site:tribunnews.com "{universitas}" "{nama}"`
- **Data:** Berita kampus lokal, profil rektor/dekan, event, problem kampus
- **Untuk agent:** News Scanner, Campus Context, Identity Resolver
- **Keunggulan:** Berita daerah sering punya detail personal (asal, keluarga, hobi) yang tidak muncul di media nasional

#### V. WhatsApp Business Profile (FREE — Kontak Kampus)
- **Via:** WhatsApp Service (`whatsapp-service` sudah ada)
- **Method:** Check WA Business profile dari nomor yang sudah ada di `ig_contacts` / `conversations`
- **Data:**
  - ✅ Nama bisnis (konfirmasi organisasi)
  - ✅ Bio / deskripsi
  - ✅ Alamat (kadang)
  - ✅ Email (kadang)
  - ✅ Website (kadang)
  - ✅ Jam operasional
- **Untuk agent:** Contact Enricher
- **Note:** Hanya jika nomor sudah ada di DB — bukan untuk search baru

#### W. YouTube (FREE — Channel Kampus & Wawancara)
- **Via DDG:** `site:youtube.com "{universitas}" official|resmi`
- **Via DDG:** `site:youtube.com "{nama}" "{universitas}" wawancara|kuliah|orasi`
- **Data:**
  - ✅ Channel resmi kampus
  - ⚠️ Video wawancara/orasi PIC → personality insight
  - ⚠️ Kuliah umum → bidang expertise
  - ⚠️ Video dies natalis/wisuda → sekilas personal style
- **Untuk agent:** Social Intel, Personal Interest (jika ada orasi/wawancara)

---

### 12.3 Search Query Templates per Agent

Agar agent tahu query pattern yang optimal:

#### Web Profiler Agent
```
PDDIKTI: search_pt("{universitas}") → pt_id
PDDIKTI: get_prodi_pt(pt_id, "20251") → daftar prodi + akreditasi + jumlah dosen/mhs
PDDIKTI: get_jumlah_dosen_pt(pt_id) → total dosen
PDDIKTI: get_rasio_pt(pt_id) → rasio dosen:mahasiswa
PDDIKTI: get_graduation_rate_pt(pt_id) → tingkat kelulusan
DDG: "{universitas}" alamat kampus fakultas
DDG: site:{website_url} fakultas|prodi|program studi
DDG: "{universitas}" visi misi
HTTP: GET {website_url}/profil
HTTP: GET {website_url}/akademik/fakultas
```

#### Social Intel Agent
```
DDG: "{universitas}" facebook page official
DDG: "{universitas}" youtube channel resmi
DDG: site:linkedin.com/company "{universitas}"
DDG: "{universitas}" twitter OR x.com official
DDG: "{universitas}" tiktok official
HTTP: GET {website_url} → parse footer/header social links
```

#### Key People Finder Agent
```
PDDIKTI: search_dosen("{nama rektor}") → verifikasi + dapatkan dosen_id
PDDIKTI: get_dosen_profile(dosen_id) → jabatan, status
DDG: "wakil rektor {universitas}" 2025 2026
DDG: "dekan {nama_fakultas} {universitas}" 2025
DDG: "{universitas}" struktur organisasi pimpinan
DDG: "{universitas}" humas|public relation kontak email
HTTP: GET {website_url}/pimpinan
HTTP: GET {website_url}/tentang/struktur-organisasi
```

#### News & Event Scanner Agent
```
DDG: "{universitas}" berita terbaru 2025 2026
DDG: "{universitas}" wisuda|seminar|dies natalis|MoU 2025
DDG: "{universitas}" akreditasi|prestasi|penghargaan
DDG: "{universitas}" masalah|kendala|tantangan
DDG: site:tribunnews.com "{universitas}"
DDG: site:kompas.com/edu "{universitas}"
GEMINI: "Cari 5 berita terbaru tentang {universitas} dalam 3 bulan terakhir"
```

#### Identity Resolver Agent (PIC Profiling)
```
① PDDIKTI: search_dosen("{nama}") → match nama_pt == universitas
   → JIKA MATCH: langsung dapat nama, nidn, prodi, pt
② PDDIKTI: get_dosen_profile(dosen_id) → jabatan_akademik, jenis_kelamin, pendidikan_tertinggi
③ PDDIKTI: get_dosen_study_history(dosen_id) → riwayat pendidikan + tahun + gelar
   → Infer: asal daerah dari lokasi S1 pertama, lama di kampus dari tahun pertama
④ SINTA: search by NIDN (dari step 1) → sinta ID, score, foto
⑤ DDG: "{nama lengkap}" "{universitas}" profil|dosen|lahir
⑥ DDG: "{nama lengkap}" wawancara|profil personal → asal, tanggal lahir
⑦ HTTP: GET {website_url}/profil-dosen/{nama_slug}
```

#### Social Media Profiler Agent (PIC Profiling)
```
DDG: site:linkedin.com/in "{nama}" "{universitas}"
DDG: site:researchgate.net "{nama}" "{universitas}"
DDG: site:instagram.com "{nama}"  → verify di bio
DDG: site:facebook.com "{nama}" "{kota universitas}"
DDG: site:twitter.com "{nama}" dosen|professor
DDG: site:youtube.com "{nama}" "{universitas}" wawancara|orasi
DDG: "{nama}" "{universitas}" social media|kontak
SCHOLAR: get scholar_id dari SINTA → cek Google Scholar profile
```

#### Academic Profiler Agent (PIC Profiling)
```
① PDDIKTI: get_dosen_teaching_history(dosen_id) → mata kuliah aktif
② PDDIKTI: get_dosen_penelitian(dosen_id) → riset + tahun
③ PDDIKTI: get_dosen_pengabdian(dosen_id) → pengabdian masyarakat
④ PDDIKTI: get_dosen_karya(dosen_id) → prosiding + publikasi
⑤ PDDIKTI: get_dosen_paten(dosen_id) → HKI + paten
⑥ SINTA: profile page → sinta score, h-index, bidang keahlian
⑦ SCHOLAR: citations page → interests, top publications
⑧ DDG: site:garuda.kemdikbud.go.id "{nama}" → publikasi jurnal nasional
⑨ DDG: site:scopus.com "{nama}" "{universitas}" → publikasi internasional
⑩ DDG: site:repository.{domain} "{nama}" pembimbing → bimbingan skripsi
```

#### Campus Context Agent (PIC Profiling)
```
PDDIKTI: get_prodi_pt(pt_id, tahun) → akreditasi per prodi (ada yang expired?)
PDDIKTI: get_rasio_pt(pt_id) → rasio dosen:mhs (overloaded?)
DDG: "{universitas}" masalah|tantangan|kendala 2025 2026
DDG: "{universitas}" akreditasi expired|turun|naik
DDG: "{universitas}" mahasiswa|pendaftar|PMB trend
DDG: site:tribunnews.com "{universitas}" 2025 2026
DDG: "{universitas}" "{nama PIC}" program|inisiatif|harapan
GEMINI: "Analisis tantangan utama {universitas} berdasarkan berita terkini"
```

#### Personal Interest & Family Agent (PIC Profiling)
```
DDG: "{nama}" hobi|kesukaan|wawancara personal
DDG: site:facebook.com "{nama}" "{kota}"  → public posts
DDG: "{nama}" "{universitas}" profil lengkap|wawancara
DDG: site:youtube.com "{nama}" "{universitas}" wawancara
DDG: site:tribunnews.com "{nama}" "{universitas}" profil
LINKEDIN: check posts/articles by person
IG: check personal account → bio, post patterns
```

---

### 12.4 PIC Profiling — Field × Source Matrix (Updated with PDDIKTI Dosen)

**Urutan prioritas pencarian: PDDIKTI → SINTA → DDG/Gemini → Social Media**

| Field | Source 1 (Primary) | Source 2 | Source 3 | Source 4 | Success Rate | Fallback |
|-------|-------------------|----------|----------|----------|-------------|----------|
| **Nama lengkap + gelar** | PDDIKTI `search_dosen` ✅ | PDDIKTI `study_history` (gelar) ✅ | SINTA ✅ | DDG | 100% | user input |
| **NIDN** | PDDIKTI `search_dosen` ✅ | — | — | — | 100% | — |
| **Jenis kelamin** | PDDIKTI `get_dosen_profile` ✅ | — | — | — | 100% | — |
| **Jabatan akademik** | PDDIKTI `get_dosen_profile` ✅ | SINTA ✅ | Website univ | — | 100% | user input |
| **Mata kuliah** | PDDIKTI `teaching_history` ✅ | SINTA ⚠️ | Website univ | DDG | 95% | needs manual |
| **Riwayat pendidikan** | PDDIKTI `study_history` ✅ | SINTA ✅ | DDG | — | 100% | — |
| **Lama di kampus** | PDDIKTI `study_history.tahun_masuk` ✅ | LinkedIn ⚠️ | SINTA | — | 90% | needs manual |
| **Bidang riset** | PDDIKTI `penelitian` ✅ | SINTA ✅ | Scholar ✅ | Garuda | 95% | — |
| **Publikasi** | PDDIKTI `karya` + `penelitian` ✅ | SINTA ✅ | Scholar | Scopus | 95% | — |
| **HKI / Paten** | PDDIKTI `paten` ✅ | DDG | — | — | 90% | — |
| **Pengabdian masy.** | PDDIKTI `pengabdian` ✅ | — | — | — | 90% | — |
| **Asal daerah** | PDDIKTI study S1 lokasi ⚠️ | Berita lokal ⚠️ | DDG wawancara | — | 50% | needs manual |
| **Tanggal lahir** | Berita ⚠️ | SINTA ⚠️ | DDG | — | 20% | needs manual |
| **Umur** | Computed dari tgl lahir | — | — | — | 20% | needs manual |
| **Status menikah** | Facebook ⚠️ | DDG berita personal | — | — | 15% | needs conversation |
| **Suami/Istri** | Facebook ❌ | Berita ❌ | — | — | 5% | needs conversation |
| **Jumlah anak** | — | — | — | — | <5% | needs conversation |
| **Tinggal di** | — | — | — | — | <5% | needs conversation |
| **Problem kampus** | PDDIKTI prodi akreditasi ✅ | Google News ✅ | Gemini ✅ | Tribunnews | 70% (inferred) | needs conversation |
| **Kekhawatiran** | GPT inference ⚠️ | Berita ⚠️ | PDDIKTI rasio ⚠️ | — | 45% (inferred) | needs conversation |
| **Harapan** | GPT inference ⚠️ | Berita ⚠️ | — | — | 40% (inferred) | needs conversation |
| **Hobi** | Socmed bio ⚠️ | Wawancara media ⚠️ | YouTube ⚠️ | — | 20% | needs conversation |
| **Makanan favorit** | — | — | — | — | <5% | needs conversation |
| **Kesibukan luar** | Socmed/berita ⚠️ | LinkedIn ⚠️ | PDDIKTI pengabdian ⚠️ | — | 20% | needs conversation |
| **Social media** | DDG search ✅ | ResearchGate ✅ | IG/FB search ⚠️ | LinkedIn ✅ | 75% | — |
| **Alamat domisili** | — | — | — | — | <5% | needs conversation |

Legend: ✅ reliable | ⚠️ mungkin ada | ❌ sangat rendah

**Expected overall completion dari OSINT (post-PDDIKTI update): ~50-60%** ⬆️
Dengan PDDIKTI Dosen sebagai sumber utama, success rate naik signifikan terutama untuk:
- Akademik fields: 90-100% (dari 70%)
- Identitas profesional: 100% (dari 95%)
- Campus context: 70% (dari 60%)

Sisanya: manual input PIC Marketing, atau didapat dari conversation WA/meeting.

---

### 12.5 Cost & Rate Limit Summary

| Source | Cost | Rate Limit | Daily Budget Estimate |
|--------|------|------------|----------------------|
| **PDDIKTI API** | Free | Tidak terdokumentasi, 0.3s delay | ~300 queries/day safe |
| DuckDuckGo | Free | 2.5s/query, 429 backoff | ~500 queries/day safe |
| SINTA scraping | Free | Butuh delay 3-5s | ~200 pages/day safe |
| Google Scholar | Free | Agresif anti-bot, 5-15s delay | ~50 profiles/day |
| Garuda Kemdikbud | Free | Unknown, 3s delay | ~100 pages/day safe |
| ResearchGate (via DDG) | Free | DDG rate limit | N/A (via DDG) |
| LinkedIn (via DDG) | Free | DDG rate limit | N/A (via DDG) |
| Facebook (via DDG) | Free | DDG rate limit | N/A (via DDG) |
| Tribunnews (via DDG) | Free | DDG rate limit | N/A (via DDG) |
| University websites | Free | 2s delay between pages | Depends on target |
| Gemini + Google Search | ~$0.01/call | 15 RPM (free tier) | ~50-100 calls/day |
| OpenAI GPT-4o-mini | ~$0.002/call | 500 RPM | Budget-dependent |
| OpenAI GPT-4o Vision | ~$0.01/image | 500 RPM | Budget-dependent |
| Serper.dev | ~$0.004/query | 2500/month (free) | Fallback only |
| Apify IG | ~$0.01/profile | Depends on plan | Fallback only |
| Scraping-Bot | ~$0.005/call | Depends on plan | Last resort only |

**Estimated cost per university OSINT:** ~$0.03-0.10 (turun karena PDDIKTI free)
**Estimated cost per PIC profile:** ~$0.05-0.20 (turun karena PDDIKTI Dosen free)

## 13. Estimasi Dependency

Dependency baru yang dibutuhkan:
- `beautifulsoup4` — HTML parsing (kemungkinan sudah ada)
- `langgraph` — sudah ada di `research_agents`
- Tidak perlu dependency baru yang signifikan

## 13. Risiko & Mitigasi

| Risiko | Mitigasi |
|--------|----------|
| Rate limiting di Google/DDG | Delay antar request, concurrent limit, queue |
| Website universitas susah di-scrape (JS-heavy) | Playwright fallback (sudah ada) |
| Data inaccurate | Reviewer agent + confidence scoring + manual verification flag |
| GPT cost tinggi | Pakai GPT-4o-mini, cache results, batch extraction |
| Pipeline lambat | Parallel execution, timeout per agent, partial results OK |
