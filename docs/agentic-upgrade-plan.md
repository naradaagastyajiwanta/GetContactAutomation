# Plan: Upgrade Chatbot Menjadi Truly Agentic

> **Tanggal dibuat:** 30 Maret 2026  
> **Tujuan:** Meningkatkan kemampuan `ReactAgent` dari chatbot rule-based menjadi agen AI yang benar-benar autonomous — bisa research, plan, ingat, dan escalate secara mandiri.

---

## Ringkasan Status Saat Ini

| Komponen | Status Sekarang | Gap |
|----------|----------------|-----|
| Situation detection | Regex/keyword matching | Tidak semantic |
| Knowledge retrieval | SQL `LIKE '%keyword%'` | Tidak semantic |
| Web research | ❌ Tidak ada | Tidak bisa cari info real-time |
| Strategy planning | ❌ Tidak ada pre-step | Langsung react tanpa plan |
| Human escalation | ❌ Tidak ada tool | Silent failure saat stuck |
| Contact memory | Hanya per-sesi | Tidak ada lintas sesi |
| Learning | Batch/scheduled | Tidak real-time |
| Tool iterations | Max 5 | Terlalu rendah untuk multi-step |

---

## Fase 1 — Quick Wins (Estimasi: 1-2 hari)

> Perubahan kecil, impact langsung terasa. Tidak merubah arsitektur.

---

### 1.1 Naikkan `AGENT_MAX_TOOL_ITERATIONS`

**File:** `orchestrator/config.py`

**Masalah:** Default `5` terlalu rendah. Percakapan kompleks butuh:
`lookup_university_info` → `check_conversation_history` → `get_relevant_lessons` → `search_web` → `validate_phone_number` → `save_extracted_number` = **6 langkah**.

**Perubahan:**
```python
# config.py — ubah default
AGENT_MAX_TOOL_ITERATIONS: int = field(default_factory=lambda: int(os.getenv("AGENT_MAX_TOOL_ITERATIONS", "10")))
```

**Impact:** Agent bisa menyelesaikan reasoning chain yang lebih panjang tanpa terpotong.

---

### 1.2 Perbaiki `search_similar_conversations` — Return Summary

**File:** `orchestrator/agent/tools.py`

**Masalah:** Tool ini call `search_conversations_for_learning()` yang hanya return metadata (state, attempt_count, dll) tanpa isi percakapan atau hasil analisis. Agent mendapat data tapi tidak bisa belajar dari konten aktual.

**Perubahan di `db.py`:** Join ke `conversation_analyses` table:
```python
async def search_conversations_for_learning(
    province: str | None = None,
    outcome: str | None = None,
    limit: int = 20,
) -> list[dict]:
    # Tambah JOIN ke conversation_analyses
    # Return: summary, effective_strategies, failure_factors dari analyses
```

**Perubahan di `tools.py`:** Format output tool include narasi:
```python
# Return format baru
{
    "similar_conversations": [
        {
            "university_name": "...",
            "province": "...",
            "outcome": "GOT_NUMBER",
            "summary": "Kontak awalnya ragu, tapi setelah dijelaskan prestasi kampus lain berhasil",
            "effective_strategies": ["social proof", "tawarkan info dulu"],
            "failure_factors": []
        }
    ]
}
```

**Impact:** Agent bisa genuinely belajar dari percakapan serupa sebelum membalas.

---

### 1.3 Tambah Tool `search_web`

**File:** `orchestrator/agent/tools.py`

**Masalah:** Agent tidak bisa research real-time. Tidak tahu siapa Rektor aktif, berita kampus terbaru, atau nomor resmi. Tapi `duckduckgo_client.py` (dan `DuckDuckGoClient`) **sudah ada** di codebase!

**Implementasi:**
```python
# tools.py — tambah tool baru
async def _search_web(query: str, max_results: int = 3) -> dict:
    """Search web for real-time information about a university."""
    try:
        from orchestrator.duckduckgo_client import DuckDuckGoClient
        client = DuckDuckGoClient()
        results = await client.search(query)
        return {
            "results": [
                {"title": r.get("title"), "snippet": r.get("body"), "url": r.get("href")}
                for r in results[:max_results]
            ]
        }
    except Exception as e:
        return {"error": str(e), "results": []}

SEARCH_WEB_SCHEMA = {
    "name": "search_web",
    "description": "Cari informasi real-time di internet. Gunakan untuk mencari nama rektor aktif, nomor resmi kampus, berita terbaru, atau info yang tidak ada di database.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query pencarian. Contoh: 'rektor Universitas XYZ 2025', 'nomor sekretariat Universitas XYZ'"
            },
            "max_results": {
                "type": "integer",
                "description": "Jumlah hasil maksimal (default: 3)",
                "default": 3
            }
        },
        "required": ["query"]
    }
}
```

**Tambahkan ke registri:**
```python
TOOL_SCHEMAS.append(SEARCH_WEB_SCHEMA)
TOOL_IMPLEMENTATIONS["search_web"] = _search_web
```

**Impact:** Agent bisa autonomous research — cari nama rektor, nomor resmi kampus, atau konteks kampus sebelum membalas.

---

## Fase 2 — Agentic Core Upgrades (Estimasi: 2-4 hari)

> Perubahan arsitektur ringan yang meningkatkan autonomy secara signifikan.

---

### 2.1 Tambah Tool `escalate_to_human`

**File:** `orchestrator/agent/tools.py` + `orchestrator/db.py`

**Masalah:** Saat agent stuck atau tidak yakin, dia terus mencoba sampai iteration limit habis, lalu kirim error message hardcoded dalam Bahasa Indonesia. Tidak ada mekanisme serah terima ke manusia.

**Implementasi:**

```python
# tools.py
async def _escalate_to_human(
    reason: str,
    suggested_action: str,
    conv_id: int,
    chatbot_type: str
) -> dict:
    """
    Escalate conversation ke tim manusia saat agent tidak yakin atau stuck.
    Tandai conversation sebagai NEEDS_REVIEW dan kirim notifikasi via WebSocket.
    """
    from orchestrator.db import update_conversation_state
    from orchestrator.websocket import ws_manager

    await update_conversation_state(conv_id, "NEEDS_REVIEW", agent_reasoning=f"Eskalasi: {reason}")
    await ws_manager.broadcast_type(
        "escalation_needed",
        conv_id=conv_id,
        reason=reason,
        suggested_action=suggested_action,
        chatbot_type=chatbot_type
    )
    return {
        "escalated": True,
        "message": "Percakapan ini sudah ditandai untuk direview tim. Jangan kirim balasan otomatis."
    }
```

**Database:** Tambah state `NEEDS_REVIEW` ke conversation state machine di `conversation.py` dan `db.py`.

**Frontend:** Tambah badge/notifikasi di Conversations page saat ada state `NEEDS_REVIEW`.

**Tools schema:**
```python
ESCALATE_SCHEMA = {
    "name": "escalate_to_human",
    "description": "Eskalasi percakapan ke tim manusia. Gunakan HANYA ketika: kontak mengajukan pertanyaan legal/compliance yang tidak bisa kamu jawab, situasi sangat tidak biasa, atau kamu sudah mencoba semua pendekatan dan gagal.",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Alasan eskalasi"},
            "suggested_action": {"type": "string", "description": "Saran tindakan untuk tim manusia"}
        },
        "required": ["reason", "suggested_action"]
    }
}
```

**Jadikan terminal tool:**
```python
TERMINAL_TOOLS = {
    "save_extracted_number",
    "mark_conversation_refused",
    "confirm_and_send_zoom",
    "escalate_to_human",  # tambah ini
}
```

**Impact:** Tidak ada lagi silent failure. Dashboard bisa tracking conversation mana yang butuh intervensi manusia.

---

### 2.2 Strategy Planning Pre-Step

**File:** `orchestrator/agent/react_agent.py` + `orchestrator/agent/prompts.py`

**Masalah:** Agent langsung `_run_react_loop()` tanpa berpikir dulu strategi yang tepat untuk konteks spesifik ini. Tidak ada "inner planning" sebelum action.

**Implementasi — fungsi baru di `react_agent.py`:**

```python
async def _plan_approach(
    self,
    conv: dict,
    uni_info: dict,
    message_history: list[dict],
    situation_tags: list[str],
) -> dict:
    """
    Lightweight planning step sebelum _run_react_loop.
    Menghasilkan strategy plan yang diinjeksi ke system prompt.
    """
    planning_prompt = f"""
    Kamu sedang mempersiapkan balasan WhatsApp ke sekretariat {uni_info.get('name')} ({uni_info.get('province')}).
    
    Situasi terdeteksi: {', '.join(situation_tags)}
    Percobaan ke-{conv.get('attempt_count', 1)}
    
    Pesan terakhir dari kontak:
    {message_history[-1]['content'] if message_history else 'Belum ada'}
    
    Dalam 3-5 kalimat, rencanakan pendekatan terbaik:
    1. Tone apa yang tepat?
    2. Apa tantangan utama yang harus diatasi?
    3. Langkah konkret apa yang akan kamu ambil?
    
    Jawab dalam JSON:
    {{"tone": "...", "main_challenge": "...", "steps": ["step1", "step2", ...], "avoid": ["hal yang harus dihindari"]}}
    """
    
    try:
        response = await self.client.chat.completions.create(
            model=cfg.AGENT_MODEL,
            messages=[{"role": "user", "content": planning_prompt}],
            response_format={"type": "json_object"},
            max_tokens=300,
        )
        plan = json.loads(response.choices[0].message.content)
        return plan
    except Exception:
        return {}  # Planning gagal tidak boleh block main flow
```

**Inject plan ke system prompt:**

```python
# prompts.py — build_agent_system_prompt()
if strategy_plan:
    prompt += f"\n\n## RENCANA STRATEGI KAMU\n"
    prompt += f"- Tone: {strategy_plan.get('tone', 'semi-formal')}\n"
    prompt += f"- Tantangan utama: {strategy_plan.get('main_challenge', '')}\n"
    prompt += f"- Langkah: {'; '.join(strategy_plan.get('steps', []))}\n"
    prompt += f"- Hindari: {'; '.join(strategy_plan.get('avoid', []))}\n"
```

**Simpan ke DB:**
```python
# Setelah planning, simpan ke agent_reasoning
await db.update_agent_reasoning(conv_id, json.dumps(strategy_plan))
```

**Impact:** Agent punya "pikiran" sebelum bertindak. Reasoning bisa di-inspect di dashboard via kolom `agent_reasoning`.

---

### 2.3 Real-time Learning — Trigger Analysis Langsung Saat Terminal

**File:** `orchestrator/conversation.py` + `orchestrator/agent/learning.py`

**Masalah:** `analyze_completed_conversation()` dan `run_reflection()` hanya dipanggil dari scheduler (batch, periodik). Pola kegagalan/keberhasilan baru tidak langsung tersedia untuk percakapan lain yang sedang berjalan.

**Perubahan di `conversation.py`:**

```python
# Saat state mencapai terminal (GOT_NUMBER, REFUSED, ABANDONED)
# Tambahkan background task untuk immediate analysis
async def _transition_to_terminal(self, conv: dict, new_state: str):
    await db.update_conversation_state(conv["id"], new_state)
    
    # Fire-and-forget analysis — jangan tunggu selesai
    asyncio.create_task(
        self._run_immediate_analysis(conv["id"], new_state)
    )

async def _run_immediate_analysis(self, conv_id: int, outcome: str):
    """Jalankan conversation analysis langsung setelah terminal state."""
    try:
        from orchestrator.agent.learning import analyze_completed_conversation
        await analyze_completed_conversation(conv_id, source="outreach")
        # Jika cukup data terkumpul, trigger mini-reflection
        # (hanya jika unprocessed_analyses >= 5, bukan batch penuh)
    except Exception as e:
        log.warning("Immediate analysis failed for conv %d: %s", conv_id, e)
```

**Impact:** Lessons database terupdate lebih cepat. Percakapan yang berlangsung malam hari sudah punya lessons baru dari percakapan sore hari.

---

## Fase 3 — Semantic Intelligence (Estimasi: 3-5 hari)

> Perubahan arsitektur terbesar. Memberikan lompatan kualitas paling signifikan.

---

### 3.1 Semantic Embeddings untuk Knowledge Retrieval

**File:** `orchestrator/db.py`, `orchestrator/agent/situation_detector.py`, `orchestrator/agent/tools.py`

**Masalah:** Semua knowledge retrieval masih keyword-based. Kontak yang bilang "lagi banyak kerjaan" tidak akan match dengan lesson tentang "kontaknya sibuk" karena kata kuncinya berbeda.

**Stack:** `text-embedding-3-small` (OpenAI, murah — ~$0.02 per 1M token) + numpy cosine similarity (tidak perlu vector DB eksternal, cukup simpan di SQLite sebagai BLOB).

#### 3.1.1 Schema Tambahan

```sql
-- db.py: tambah kolom ke tabel yang ada
ALTER TABLE knowledge_items ADD COLUMN embedding BLOB;
ALTER TABLE lessons ADD COLUMN embedding BLOB;

-- Tabel baru untuk conversation summaries yang siap diambil
CREATE TABLE IF NOT EXISTS conversation_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    content TEXT NOT NULL,  -- ringkasan yang di-embed
    embedding BLOB NOT NULL,
    outcome TEXT,
    province TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_emb_outcome ON conversation_embeddings(outcome);
CREATE INDEX IF NOT EXISTS idx_conv_emb_province ON conversation_embeddings(province);
```

#### 3.1.2 Embedding Helper

```python
# orchestrator/agent/embeddings.py (file baru)
import numpy as np
from openai import AsyncOpenAI
import struct

_client = AsyncOpenAI()
_EMBEDDING_MODEL = "text-embedding-3-small"

async def get_embedding(text: str) -> list[float]:
    """Dapatkan embedding vector untuk teks."""
    response = await _client.embeddings.create(
        model=_EMBEDDING_MODEL,
        input=text[:8000],  # batas token
    )
    return response.data[0].embedding

def encode_embedding(vector: list[float]) -> bytes:
    """Encode float list ke BLOB untuk SQLite."""
    return struct.pack(f"{len(vector)}f", *vector)

def decode_embedding(blob: bytes) -> np.ndarray:
    """Decode BLOB dari SQLite ke numpy array."""
    n = len(blob) // 4
    return np.array(struct.unpack(f"{n}f", blob))

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Hitung cosine similarity antara dua vector."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
```

#### 3.1.3 Semantic Knowledge Retrieval

```python
# db.py — fungsi baru pengganti match_knowledge_items_by_message()
async def match_knowledge_items_semantic(
    chatbot_type: str,
    query_embedding: bytes,
    top_k: int = 5,
    min_similarity: float = 0.6,
) -> list[dict]:
    """Retrieve knowledge items berdasarkan cosine similarity."""
    from orchestrator.agent.embeddings import decode_embedding, cosine_similarity
    import numpy as np

    query_vec = decode_embedding(query_embedding)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM knowledge_items WHERE chatbot_type = ? AND is_active = 1 AND embedding IS NOT NULL",
            (chatbot_type,),
        )
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        item = _row_to_dict(row)
        item_vec = decode_embedding(item["embedding"])
        sim = cosine_similarity(query_vec, item_vec)
        if sim >= min_similarity:
            item["similarity"] = sim
            results.append(item)

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]
```

#### 3.1.4 Background Job: Build Embeddings

```python
# orchestrator/scheduler.py — tambah job
async def build_missing_embeddings():
    """Build embeddings untuk knowledge_items dan lessons yang belum punya."""
    from orchestrator.agent.embeddings import get_embedding, encode_embedding

    # Knowledge items
    items = await db.get_knowledge_items(active_only=True)
    for item in items:
        if not item.get("embedding"):
            text = f"{item['title']}\n{item['content']}"
            vec = await get_embedding(text)
            await db.update_knowledge_item_embedding(item["id"], encode_embedding(vec))
            await asyncio.sleep(0.1)  # rate limit

    # Lessons
    lessons = await db.get_all_active_lessons()
    for lesson in lessons:
        if not lesson.get("embedding"):
            text = f"{lesson['situation_type']}\n{lesson['insight']}\n{lesson['recommended_strategy']}"
            vec = await get_embedding(text)
            await db.update_lesson_embedding(lesson["id"], encode_embedding(vec))
            await asyncio.sleep(0.1)

# Run sekali saat startup + setiap 6 jam
scheduler.add_job(build_missing_embeddings, "interval", hours=6, id="build_embeddings")
```

#### 3.1.5 Update `situation_detector.py`

Ganti dari pure keyword matching menjadi **hybrid**: keyword untuk speed (deteksi cepat), semantic untuk quality (deteksi akurat saat keyword tidak match).

```python
# situation_detector.py — fungsi baru
async def detect_situation_tags_semantic(
    message: str,
    message_history: list[dict],
) -> list[str]:
    """Hybrid: keyword tags + semantic similarity untuk coverage penuh."""
    # Step 1: keyword tags tradisional (tetap ada, cepat)
    tags = detect_situation_tags(message, message_history)
    
    # Step 2: semantic tambahan jika keyword miss
    from orchestrator.agent.embeddings import get_embedding, encode_embedding
    query_vec = encode_embedding(await get_embedding(message))
    
    semantic_items = await db.match_knowledge_items_semantic(
        chatbot_type="outreach",
        query_embedding=query_vec,
        top_k=3,
        min_similarity=0.65,
    )
    
    # Extract situation_tags dari hasil semantic
    for item in semantic_items:
        for tag in item.get("situation_tags", "").split(","):
            tag = tag.strip()
            if tag and tag not in tags:
                tags.append(tag)
    
    return tags
```

**Impact:** Agent bisa match situasi yang sebelumnya miss — "saya lagi di luar kota" bisa match ke tag `sibuk` meski tidak ada kata kunci "sibuk" atau "lagi" yang terdaftar.

---

### 3.2 Persistent Contact Memory

**File:** `orchestrator/db.py`, `orchestrator/agent/tools.py`

**Masalah:** Agent tidak ingat apa pun tentang kontak atau kampus dari percakapan sebelumnya. Setiap percakapan mulai dari nol.

#### Schema Baru

```sql
-- db.py
CREATE TABLE IF NOT EXISTS contact_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_phone TEXT NOT NULL,
    university_id INTEGER REFERENCES universities(id),
    note_type TEXT NOT NULL,  -- 'personality', 'preference', 'context', 'warning'
    content TEXT NOT NULL,
    confidence REAL DEFAULT 0.7,
    source_conversation_id INTEGER REFERENCES conversations(id),
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_contact_memory_phone ON contact_memory(contact_phone);
```

#### Tool Baru: `remember_about_contact`

```python
# tools.py
async def _remember_about_contact(
    note_type: str,
    content: str,
    conv_id: int,
    contact_phone: str,
    university_id: int,
) -> dict:
    """Simpan observasi penting tentang kontak untuk digunakan di percakapan mendatang."""
    await db.add_contact_memory(
        contact_phone=contact_phone,
        university_id=university_id,
        note_type=note_type,
        content=content,
        source_conversation_id=conv_id,
    )
    return {"saved": True, "note": content}

REMEMBER_SCHEMA = {
    "name": "remember_about_contact",
    "description": "Simpan catatan penting tentang kontak ini. Gunakan untuk personalities, preferensi komunikasi, konteks khusus, atau warning. Catatan akan muncul di percakapan berikutnya.",
    "parameters": {
        "type": "object",
        "properties": {
            "note_type": {
                "type": "string",
                "enum": ["personality", "preference", "context", "warning"],
                "description": "Tipe catatan"
            },
            "content": {
                "type": "string",
                "description": "Isi catatan. Tulis singkat dan informatif."
            }
        },
        "required": ["note_type", "content"]
    }
}
```

#### Inject ke Prompt

```python
# prompts.py — build_agent_system_prompt()
if contact_memories:
    prompt += "\n\n## CATATAN TENTANG KONTAK INI\n"
    for mem in contact_memories:
        prompt += f"- [{mem['note_type'].upper()}] {mem['content']}\n"
```

**Impact:** Agent ingat bahwa kontak tertentu lebih responsif malam hari, atau bahwa kampus ini sudah pernah menolak 2x tapi dengan alasan yang bisa diatasi.

---

## Fase 4 — Unified Agent Flow (Estimasi: 2-3 hari)

> Hilangkan friction antara outreach agent dan audiensi agent.

---

### 4.1 Optionalize Admin Approval Gate

**File:** `orchestrator/config.py`, `orchestrator/conversation.py`

**Masalah:** Setiap kali `save_extracted_number` dipanggil, audiensi conversation masuk ke state `QUEUED` dan menunggu admin approval. Jika admin tidak approve dalam beberapa jam, momentum percakapan hilang.

**Perubahan:**
```python
# config.py — tambah setting baru
AUTO_APPROVE_AUDIENSI: bool = field(default_factory=lambda: os.getenv("AUTO_APPROVE_AUDIENSI", "false").lower() == "true")
AUTO_APPROVE_DELAY_MINUTES: int = field(default_factory=lambda: int(os.getenv("AUTO_APPROVE_DELAY_MINUTES", "60")))
```

```python
# scheduler.py — job baru
async def auto_approve_queued_audiensi():
    """Auto-approve audiensi conversations yang sudah menunggu > N menit."""
    if not cfg.AUTO_APPROVE_AUDIENSI:
        return
    
    threshold_minutes = cfg.AUTO_APPROVE_DELAY_MINUTES
    queued = await db.get_queued_audiensi()
    
    for aud in queued:
        created_at = datetime.fromisoformat(aud["created_at"])
        age_minutes = (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
        
        if age_minutes >= threshold_minutes:
            await db.update_audiensi_state(aud["id"], "APPROVED",
                approved_by="system_auto",
                approved_at=_utcnow()
            )
            log.info("Auto-approved audiensi %d (waited %.1f minutes)", aud["id"], age_minutes)

# Jalankan setiap 15 menit
scheduler.add_job(auto_approve_queued_audiensi, "interval", minutes=15, id="auto_approve_audiensi")
```

**Impact:** Dengan `AUTO_APPROVE_AUDIENSI=true`, agent bisa autonomously mengatur meeting tanpa intervensi admin. Tetap opsional untuk keamanan.

---

## Checklist Implementasi

### Fase 1 — Quick Wins
- [ ] **1.1** Naikkan `AGENT_MAX_TOOL_ITERATIONS` default dari 5 ke 10 di `config.py`
- [ ] **1.2** Update `search_conversations_for_learning()` di `db.py` untuk JOIN `conversation_analyses`
- [ ] **1.2** Update tool `search_similar_conversations` di `tools.py` untuk return `summary` + `effective_strategies`
- [ ] **1.3** Buat fungsi `_search_web()` di `tools.py` menggunakan `duckduckgo_client.py`
- [ ] **1.3** Tambah `SEARCH_WEB_SCHEMA` dan register di `TOOL_IMPLEMENTATIONS`

### Fase 2 — Agentic Core
- [ ] **2.1** Buat fungsi `_escalate_to_human()` di `tools.py`
- [ ] **2.1** Tambah state `NEEDS_REVIEW` ke state machine di `conversation.py` dan `db.py`
- [ ] **2.1** Tambah `escalate_to_human` ke `TERMINAL_TOOLS` set
- [ ] **2.1** Tambah WebSocket broadcast `escalation_needed` event
- [ ] **2.1** Update frontend untuk tampilkan badge di conversations dengan state `NEEDS_REVIEW`
- [ ] **2.2** Buat fungsi `_plan_approach()` di `react_agent.py`
- [ ] **2.2** Update `build_agent_system_prompt()` di `prompts.py` untuk terima dan inject `strategy_plan`
- [ ] **2.2** Update `process_incoming_message()` untuk call `_plan_approach()` sebelum `_run_react_loop()`
- [ ] **2.3** Tambah `_transition_to_terminal()` dengan fire-and-forget analysis di `conversation.py`
- [ ] **2.3** Update `analyze_completed_conversation()` di `learning.py` untuk support immediate mode

### Fase 3 — Semantic Intelligence
- [ ] **3.1** Buat file `orchestrator/agent/embeddings.py`
- [ ] **3.1** Tambah kolom `embedding BLOB` ke `knowledge_items` dan `lessons` di `db.py` (migration)
- [ ] **3.1** Buat tabel `conversation_embeddings` di `db.py`
- [ ] **3.1** Buat fungsi `match_knowledge_items_semantic()` di `db.py`
- [ ] **3.1** Update `db.py` untuk add `update_knowledge_item_embedding()` dan `update_lesson_embedding()`
- [ ] **3.1** Buat job `build_missing_embeddings()` di `scheduler.py`
- [ ] **3.1** Update `situation_detector.py` dengan `detect_situation_tags_semantic()`
- [ ] **3.2** Tambah tabel `contact_memory` di `db.py` (migration)
- [ ] **3.2** Buat fungsi `add_contact_memory()` dan `get_contact_memories()` di `db.py`
- [ ] **3.2** Buat tool `remember_about_contact` di `tools.py`
- [ ] **3.2** Update `build_agent_system_prompt()` untuk inject `contact_memories`

### Fase 4 — Unified Flow
- [ ] **4.1** Tambah `AUTO_APPROVE_AUDIENSI` dan `AUTO_APPROVE_DELAY_MINUTES` ke `config.py`
- [ ] **4.1** Tambah job `auto_approve_queued_audiensi()` di `scheduler.py`
- [ ] **4.1** Update `.env.example` dengan variable baru

---

## File yang Dimodifikasi

| File | Fase | Jenis Perubahan |
|------|------|-----------------|
| `orchestrator/config.py` | 1, 4 | Tambah config keys baru |
| `orchestrator/db.py` | 1, 2, 3 | Tambah fungsi query baru + schema migration |
| `orchestrator/agent/tools.py` | 1, 2, 3 | Tambah 3 tools baru, update 1 tool |
| `orchestrator/agent/react_agent.py` | 2 | Tambah `_plan_approach()`, update main flow |
| `orchestrator/agent/prompts.py` | 2, 3 | Update `build_agent_system_prompt()` |
| `orchestrator/agent/situation_detector.py` | 3 | Tambah semantic detection |
| `orchestrator/agent/embeddings.py` | 3 | **File baru** |
| `orchestrator/agent/learning.py` | 2 | Update untuk support immediate analysis |
| `orchestrator/conversation.py` | 2 | Tambah `_transition_to_terminal()` |
| `orchestrator/scheduler.py` | 3, 4 | Tambah 2 jobs baru |
| `frontend/src/...` | 2 | Badge `NEEDS_REVIEW` di conversations |
| `.env.example` | 4 | Dokumentasi variable baru |

---

## Catatan Risiko

| Risiko | Mitigasi |
|--------|----------|
| Biaya embedding OpenAI meningkat | `text-embedding-3-small` sangat murah, batasi re-embed hanya untuk item baru |
| `search_web` lambat → delay reply | Beri timeout 5 detik, jika timeout skip dan lanjut tanpa web result |
| `_plan_approach()` failure blocking main flow | Wrap di try/except, planning gagal tidak boleh stop main agent |
| Auto-approve audiensi kirim ke kontak yang salah | Default `AUTO_APPROVE_AUDIENSI=false`, opt-in via env var |
| Semantic retrieval false positive | Atur `min_similarity=0.65`, kombinasikan dengan keyword matching (hybrid approach) |
