# GetContactAIAgent - Claude Code Subagent System

Framework subagent dan agent team untuk development GetContactAIAgent menggunakan Claude Code.

## 🚀 Quick Start

### Untuk Fitur Baru
```bash
# Jalankan orchestrator
/start "tambah fitur management universitas dengan CRUD dan pagination"

# Atau dari file brief
/start briefs/brief-003.docx
```

### Untuk Review & Fix
```bash
# Jalankan agent team
/review-and-fix
```

## 📁 Struktur

```
.claude/
├── agents/                    # Subagent definitions (11 agents)
│   ├── orchestrator-agent.md  # Main coordinator
│   ├── brief-reader.md        # Read & extract briefs
│   ├── brief-interpreter.md   # Translate to technical
│   ├── codebase-scout.md      # Analyze codebase
│   ├── technical-planner.md   # Create spec & tasks
│   ├── code-architect.md      # Create blueprint
│   ├── be-developer.md        # Python/FastAPI dev
│   ├── fe-developer.md        # React/TypeScript dev
│   ├── code-reviewer.md       # Code review
│   ├── technical-writer.md    # Documentation
│   └── pr-creator.md          # Create MR to GitLab
│
├── commands/                  # Command aliases
│   └── review-and-fix.md      # Agent team command
│
└── skills/                    # Reusable skills (10 skills)
    ├── brief-analysis/        # Brief interpretation guide
    ├── checkpoint-protocol/   # Checkpoint format
    ├── codebase-explorer/     # Codebase scanning
    ├── db-design/             # Database design (SQLite)
    ├── docker-env/            # Docker operations
    ├── git-operations/        # Git workflow
    ├── project-setup/         # Project initialization
    ├── python-conventions/    # FastAPI/Python patterns
    ├── react-conventions/     # React/TypeScript patterns
    └── task-breakdown/        # Task format guide
```

## 🤖 Agent Workflow

### New Feature Pipeline
```
1. @brief-reader          → Ekstrak brief
2. @brief-interpreter     → Translate ke teknis
   🛑 CP1: Review Interpretasi
3. @codebase-scout        → Analisis codebase
4. @technical-planner     → Buat spec + tasks
   🛑 CP2: Review Technical Plan
5. @code-architect        → Buat blueprint
   🛑 CP3: Review Blueprint
6. @be-developer          → Implement backend
7. @fe-developer          → Implement frontend
8. /review-and-fix        → Agent team review
9. @pr-creator            → Buat MR
```

### Agent Team (review-and-fix)
```
code-reviewer ──┐
user-simulator ──┤ (paralel)
                 │
        ┌────────┴────────┐
        ▼                 ▼
  be-developer      fe-developer  (paralel fix)
        │                 │
        └────────┬────────┘
                 ▼
           qa-tester
```

| Agent | Fungsi | Cara Panggil |
|-------|--------|--------------|
| `orchestrator-agent` | Koordinator utama | `/start [deskripsi]` |
| `brief-reader` | Baca brief | `@brief-reader` |
| `brief-interpreter` | Translate ke teknis | `@brief-interpreter` |
| `codebase-scout` | Analisis codebase | `@codebase-scout` |
| `technical-planner` | Buat spec & tasks | `@technical-planner` |
| `code-architect` | Buat blueprint | `@code-architect` |
| `be-developer` | Backend dev | `@be-developer` |
| `fe-developer` | Frontend dev | `@fe-developer` |
| `code-reviewer` | Code review | `@code-reviewer` |
| `technical-writer` | Buat dokumentasi | `@technical-writer` |
| `pr-creator` | Buat MR | `@pr-creator` |

## 📋 Menggunakan Agent

### Cara 1: Direct Call
```
@nama-agent
[instruksi task]
```

Contoh:
```
@brief-reader
Baca briefs/brief-003.docx dan ekstrak seluruh isinya.
```

### Cara 2: Via Orchestrator
```
/start [deskripsi singkat atau path ke brief]
```

### Cara 3: Agent Team
```
/review-and-fix
```

## 🛠️ Skills Reference

### python-conventions
FastAPI, aiosqlite, OpenAI patterns
```python
# Database query
async with aiosqlite.connect(db_path) as db:
    async with db.execute(
        "SELECT * FROM table WHERE id = ?", (id,)
    ) as cursor:
        row = await cursor.fetchone()
```

### react-conventions
React 18, TypeScript, TanStack Query
```tsx
export function Component({ id }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['resource', id],
    queryFn: () => fetchResource(id),
  });
}
```

### git-operations
Branch, commit, MR workflow
```bash
git checkout -b feat/003-university
git commit -m "feat(be): add university CRUD"
```

### task-breakdown
Standard task format
```markdown
### TASK-BE-001: Title
**File:** path/to/file.py
**Acceptance Criteria:**
- [ ] Criteria 1
- [ ] Criteria 2
```

## 📝 Output Documents

### Generate oleh Agents
- `docs/technical-spec.md` - Spesifikasi teknis
- `docs/task-breakdown.md` - Breakdown task
- `docs/architecture-blueprint.md` - Blueprint implementasi
- `docs/codebase-context-report.md` - Laporan codebase
- `docs/code-review-report.md` - Laporan code review
- `docs/user-simulation-report.md` - Laporan user testing

## 🎯 Tech Stack Project

### Backend
- Python 3.x, FastAPI
- aiosqlite (SQLite async)
- OpenAI GPT-4o / GPT-4o-mini
- APScheduler

### Frontend
- React 18, TypeScript
- Vite, React Router 6
- TanStack Query 5
- Tailwind CSS 3

### WhatsApp
- Node.js, Baileys
- Port 3100

## 🔄 Development Workflow

1. **Brief** → PM buat brief di `briefs/`
2. **Orchestrator** → Pilih pipeline otomatis
3. **Agents** → Eksekusi tahapan dengan checkpoint
4. **Review** → User approve di setiap checkpoint
5. **Dev** → be-developer + fe-developer implement
6. **Team Review** → code-reviewer + user-simulator
7. **Fix** → developer agents fix issues
8. **QA** → qa-tester verify
9. **MR** → pr-creator buat merge request

## 💡 Tips

- Selalu gunakan `/start` untuk pipeline otomatis
- Tunggu approval di setiap checkpoint
- Gunakan `/review-and-fix` setelah development selesai
- Baca `docs/` output untuk memahami context
- Skills di-load otomatis oleh agents

## 📚 Referensi

- [Claude Code Docs](https://claude.ai/code/docs)
- Repository asli: https://gitlab.com/airadms/claude-guide
