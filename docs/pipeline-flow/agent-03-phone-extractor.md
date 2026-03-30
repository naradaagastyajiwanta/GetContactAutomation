# Agent 3: Phone Extractor

**File:** `orchestrator/agents/ig_phone_extractor.py`
**Trigger:** Scheduler (every 1 hour) / Manual via PipelinePage
**Target:** Posts in `ig_posts` table where `phone_extracted = 0`

## Purpose

Extract phone numbers and contact names from scraped Instagram posts using GPT-4o Vision OCR on images and GPT text analysis on captions. This is the most AI-intensive agent — it uses OpenAI's vision model to "read" post images.

---

## Entry Criteria

- Post has `phone_extracted = 0` (not yet processed)
- Post has either:
  - An `image_url` (most posts) → **Vision OCR** on the image
  - Only a `caption` → **Text extraction** from caption only

---

## Flow per Post

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Fetch Post Data
│  ─────────────────────────────────────────────────────────
│  posts = get_unextracted_posts(limit=50)
│
│  For each post:
│    caption = post.caption or ""
│    image_url = post.image_url
│    university_id = post.university_id
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2A: Image Post — GPT Vision OCR
│  ─────────────────────────────────────────────────────────
│  contacts = extract_phone_from_image(image_url, caption)
│
│  Sends to GPT-4o:
│    - The image (post image, e.g. poster/event flyer)
│    - The caption text as context
│
│  GPT-4o analyzes the image visually:
│    - Reads phone numbers from flyers, banners, event posters
│    - Reads contact names mentioned in the image
│    - Returns structured: [{"phone": "...", "name": "..."}]
│
│  Failure handling:
│    If vision API fails → log warning → skip to next post
│    (caption is NOT re-processed in this fallback)
└─────────────────────────────────────────────────────────────┘
                              │
                              │  (no image)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2B: Caption-Only Post — Text Extraction
│  ─────────────────────────────────────────────────────────
│  contacts = extract_named_contacts_from_text(caption)
│
│  Uses regex + GPT to find:
│    - Phone numbers in caption text
│    - Names next to phone numbers (e.g. "Bpk. Ahmad: 0812-xxx")
│    - Contact person mentions
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Deduplication (Per University)
│  ─────────────────────────────────────────────────────────
│  saved_names = get_contacts_for_university(university_id)
│
│  For each contact found:
│    norm_name = _normalize_name(name)
│
│    if norm_name in saved_names:
│      → SKIP (already have this contact for this university)
│    else:
│      → add_ig_contact(...) → save to DB
│      → saved_names.add(norm_name)
│
│  _normalize_name() removes:
│    - Titles: dr, prof, ir, s.psi, s.pd, m.m, dll
│    - Punctuation: commas, dots, dashes
│    - Case differences
│
│  Example: "Dr. Anindya, S.Psi, K." → "anindya"
│           Matches "dr. Anindya" from previous save
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Save to Database
│  ─────────────────────────────────────────────────────────
│  INSERT INTO ig_contacts:
│    university_id    → parent university
│    phone_number     → extracted phone
│    contact_name     → name (if found) or NULL
│    has_person_name  → bool (was a real person name found?)
│    source_post_url  → which post this came from
│    source_image_url → image URL (for audit)
│
│  UPDATE ig_posts SET phone_extracted = 1 WHERE id = X
└─────────────────────────────────────────────────────────────┘
```

---

## What Is a "Named Contact"?

Agent 3 specifically looks for contacts that have a **person's name**, not just a phone number. This is critical for meaningful WhatsApp outreach.

| Scenario | `has_person_name` | Example |
|----------|-------------------|---------|
| Phone + person's name | `true` | `"Bpk. Herman: 0812-3456-7890"` |
| Phone only (generic poster) | `false` | `"Hubungi: 021-xxx"` (no name) |
| Contact name found in image | `true` | GPT reads name from event flyer |
| No name in image | `false` | GPT only reads phone number |

Contacts with `has_person_name = false` are still saved (useful for reference) but the WhatsApp chatbot prioritizes contacts with `has_person_name = true`.

---

## GPT Vision Prompt (simplified)

```
You are an OCR assistant analyzing an Indonesian university Instagram post.

From the image, extract ALL phone numbers with their associated contact names.

Rules:
- Only extract if you can see a person's name (not just a phone number)
- Phone formats: 08xx, +62, (021), etc.
- Names should be Indonesian person's names (capitalized)
- Ignore generic numbers like "hotline", "call center"

Return as JSON array:
[
  {"phone": "0812-3456-7890", "name": "Bpk. Herman"},
  {"phone": "0813-9876-5432", "name": "Ibu Siti"}
]

If no phone numbers with names found, return: []
```

---

## Deduplication Logic

Agent 3 deduplicates in two ways:

### 1. Name Deduplication (in-memory set)
```python
saved_names = {_normalize_name(c["contact_name"]) for c in existing_contacts}
if _normalize_name(new_name) in saved_names:
    skip  # Don't add duplicate
```

### 2. Phone Deduplication (SQLite UNIQUE constraint)
```sql
INSERT OR IGNORE INTO ig_contacts (university_id, phone_number, ...)
VALUES (?, ?, ...)
```
If same phone already exists for this university → silently ignored.

---

## Normalization Examples

| Raw Input | Normalized |
|-----------|------------|
| `Dr. Anindya, S.Psi, K.` | `anindya` |
| `dr. Anindya, S.Psi` | `anindya` |
| `Prof. Dr. Budi Santoso, M.Si.` | `budi santoso` |
| `IR. Ahmad` | `ahmad` |
| `Bpk. Herman` | `herman` |

This ensures `Dr. Anindya` and `dr. Anindya` are treated as the same person.

---

## Stop Mechanism

```python
for post in posts:
    if is_paused():           # ← Checked every iteration
        log.info("[Agent3] Bot paused during batch, stopping early")
        break
    try:
        contacts = await extract_phone_from_image(image_url, caption)
        ...
```

Already implemented before this session (Agent 3 had it from the start).

---

## Delay

```python
await asyncio.sleep(1)  # 1 second between posts
```
Required to avoid OpenAI API rate limits. 50 posts = ~50 seconds minimum.

---

## Batch Limit

Default: **50 posts per batch** (controlled by `limit` parameter).

50 posts × 1s sleep = ~1 minute per batch.
100 posts × 1s = ~1.7 minutes with limit=100.

---

## Key Functions

| Function | Purpose |
|----------|---------|
| `run_phone_extraction_batch(limit)` | Batch run for scheduler |
| `run_phone_extraction_for_universities(ids)` | Targeted run |
| `_normalize_name(name)` | Strip titles/punctuation for dedup |
| `extract_phone_from_image()` | GPT-4o Vision OCR (in `instagram.py`) |
| `extract_named_contacts_from_text()` | Text-only extraction (in `instagram.py`) |

---

## Why Vision OCR?

Many Indonesian universities post:
- **Event flyers** with contact person's photo + phone
- **Banners** with WhatsApp numbers
- **Poster images** where phone number is embedded in the image (not in caption)

These cannot be extracted from caption text alone — GPT Vision reads the image directly.

Example:
```
Caption: " Kegiatan Jumat Sehat  📅 Jumat, 10 Jan 2025"
Image: [Banner with "Hubungi: Bpk. Herman 0812-3456-7890"]
```
Caption has no phone → only Vision OCR can extract it.
