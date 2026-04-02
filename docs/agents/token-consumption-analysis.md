# Token Consumption Analysis — Claude Team Agents

> Generated: 2026-03-25
> Purpose: Map token usage per pipeline scenario, identify waste, propose optimizations

---

## Token Estimation Rules

- **1 token ≈ 4 characters** (English text/markdown)
- **1 token ≈ 3.5 characters** (code-heavy content)
- Each **agent spawn = new context window** (fresh token budget)
- Base overhead per agent context: ~8K tokens (system prompt + tool definitions + global CLAUDE.md)

---

## Per-Agent Token Cost Breakdown

### Fixed Costs (every agent pays this)

| Component | Bytes | Est. Tokens | Notes |
|-----------|-------|-------------|-------|
| System prompt + tool defs | ~30KB | ~7,500 | Claude Code runtime overhead |
| Global CLAUDE.md | 2.4KB | ~600 | User's global instructions |
| **Subtotal (base)** | | **~8,100** | **Every agent starts here** |

### Variable Costs (per agent type)

| Agent | Definition | Skills Loaded | Docs Read | Working Context | **Total per Spawn** |
|-------|-----------|---------------|-----------|-----------------|---------------------|
| **orchestrator** | 25.7KB (6,400t) | wave-execution 3.2KB + context-resilience 1.9KB + git-ops 6.1KB = 11.2KB (2,800t) | pipeline-state + wave-plan + signal ≈ 5KB (1,250t) | Heavy coordination ~20K tokens | **~38,500** |
| **be-developer** | 7.0KB (1,750t) | stack-conventions 13.5KB + docker-env 2.1KB + git-ops 6.1KB = 21.7KB (5,400t) | agent-context + wave-plan + blueprint + lessons ≈ 15KB (3,750t) | Implementation ~40K tokens | **~59,000** |
| **fe-developer** | 7.0KB (1,750t) | react-conventions 12.9KB + design-philosophy 5.4KB + frontend-craft 6.7KB + docker-env 2.1KB + git-ops 6.1KB = 33.2KB (8,300t) | agent-context + design-direction + wave-plan + blueprint + lessons ≈ 18KB (4,500t) | Implementation ~40K tokens | **~62,650** |
| **wave-planner** | 4.5KB (1,125t) | task-breakdown 1.3KB (325t) | signal + conventions + pipeline-intelligence ≈ 8KB (2,000t) | Planning ~15K tokens | **~26,550** |
| **code-reviewer** | 6.3KB (1,575t) | git-ops 6.1KB (1,525t) | git diff + lessons ≈ 10KB (2,500t) | Review ~20K tokens | **~33,700** |
| **qa-tester** | 7.3KB (1,825t) | qa 13.8KB (3,450t) | checklist + acceptance-criteria + diff ≈ 10KB (2,500t) | Testing ~15K tokens | **~30,875** |
| **codebase-scout** | 6.1KB (1,525t) | codebase-explorer 7.4KB (1,850t) | codebase files ≈ 20KB (5,000t) | Exploration ~15K tokens | **~31,475** |
| **brief-reader** | 2.1KB (525t) | read-docx 0.5KB (125t) | brief file ≈ 5KB (1,250t) | Extraction ~5K tokens | **~15,000** |
| **brief-interpreter** | 3.3KB (825t) | brief-analysis 1.1KB (275t) | reader output ≈ 5KB (1,250t) | Analysis ~8K tokens | **~18,450** |
| **pm-agent** | 5.0KB (1,250t) | none | brief ≈ 5KB (1,250t) | Validation ~8K tokens | **~18,600** |
| **technical-planner** | 5.5KB (1,375t) | task-breakdown 1.3KB (325t) | codebase-report + context ≈ 12KB (3,000t) | Planning ~15K tokens | **~27,800** |
| **code-architect** | 4.2KB (1,050t) | none | tech-spec + lessons ≈ 8KB (2,000t) | Blueprint ~12K tokens | **~23,150** |
| **env-configurator** | 13.3KB (3,325t) | docker-env 2.1KB (525t) | assessment + .env ≈ 4KB (1,000t) | Setup ~10K tokens | **~22,950** |
| **project-initializer** | 6.2KB (1,550t) | project-setup 6.9KB (1,725t) | docker-compose + blueprint ≈ 5KB (1,250t) | Init ~10K tokens | **~22,625** |
| **db-designer** | 3.2KB (800t) | db-design 8.6KB (2,150t) | brief + schema ≈ 5KB (1,250t) | Design ~10K tokens | **~22,300** |
| **git-manager** | 7.5KB (1,875t) | none | pipeline-state ≈ 2KB (500t) | Git ops ~5K tokens | **~15,475** |
| **pr-creator** | 5.5KB (1,375t) | none | wave-plan + git log ≈ 8KB (2,000t) | PR creation ~5K tokens | **~16,475** |
| **security-check** | 5.1KB (1,275t) | none | config files ≈ 5KB (1,250t) | Audit ~5K tokens | **~15,625** |
| **convention-scout** | 2.5KB (625t) | convention-research 1.8KB (450t) | signal ≈ 2KB (500t) | Web search ~10K tokens | **~19,675** |
| **design-director** | 3.4KB (850t) | design-philosophy 5.4KB + frontend-craft 6.7KB = 12.1KB (3,025t) | brief ≈ 3KB (750t) | Design ~10K tokens | **~22,725** |
| **docker-manager** | 4.5KB (1,125t) | none | docker-compose + .env ≈ 3KB (750t) | Health check ~5K tokens | **~14,975** |
| **user-simulator** | 11.0KB (2,750t) | none | simulation-config ≈ 5KB (1,250t) | Browser flows ~15K tokens | **~27,100** |
| **doc-updater** | 11.5KB (2,875t) | none | all docs ≈ 20KB (5,000t) | Update ~10K tokens | **~25,975** |
| **retro-agent** | 5.3KB (1,325t) | retro 20.2KB (5,050t) | pipeline-intelligence + fix-ledger + lessons ≈ 10KB (2,500t) | Analysis ~10K tokens | **~26,975** |

---

## Pipeline Scenario Simulations

### Scenario 1: GREENFIELD (New Project — e.g., Laravel + React)

```
Total agents spawned: 22-28 (depending on wave count)
Estimated total tokens: ~650K-850K
```

| Step | Agents Spawned | Tokens per Agent | Parallel? | Step Total |
|------|---------------|-----------------|-----------|------------|
| **0a. Brief parsing** | brief-reader + brief-interpreter + pm-agent | 15K + 18.5K + 18.6K | ✅ 3 parallel | **~52,100** |
| **0b. Context analysis** | codebase-scout + convention-scout + design-director | 31.5K + 19.7K + 22.7K | ✅ 3 parallel | **~73,900** |
| **1a. Wave planning** | wave-planner | 26.6K | sequential | **~26,600** |
| **1b. Architecture** | code-architect | 23.2K | sequential | **~23,200** |
| **2a. Environment** | env-configurator | 23K | sequential | **~23,000** |
| **2b. Project init** | project-initializer | 22.6K | sequential | **~22,600** |
| **2c. DB design** | db-designer | 22.3K | sequential | **~22,300** |
| **2d. Docker check** | docker-manager | 15K | sequential | **~15,000** |
| **3a. Wave 1** (2 features) | git-manager + 2x be-developer + 2x fe-developer + git-manager | 15.5K + (59K×2) + (62.7K×2) + 15.5K | ✅ 4 dev parallel | **~274,400** |
| **3b. Wave 2** (2 features) | git-manager + 2x be-developer + 2x fe-developer + git-manager | same | ✅ 4 dev parallel | **~274,400** |
| **4a. Review** | code-reviewer + security-check + qa-tester + user-simulator | 33.7K + 15.6K + 30.9K + 27.1K | ✅ 4 parallel | **~107,300** |
| **4b. Fix cycle** (if issues) | be-developer + fe-developer | 59K + 62.7K | ✅ 2 parallel | **~121,700** |
| **5. PR creation** | pr-creator | 16.5K | sequential | **~16,500** |
| **5b. Doc update** | doc-updater | 26K | sequential | **~26,000** |
| **Orchestrator** | orchestrator (lives entire pipeline) | 38.5K + ongoing coordination ~30K | continuous | **~68,500** |
| | | | **TOTAL** | **~1,147,500** |

> **With 2 waves, 2 features each: ~1.1M tokens**
> **With 3 waves: add ~274K per wave = ~1.4M tokens**

---

### Scenario 2: NEW FEATURE (1 feature added to existing project)

```
Total agents spawned: 12-15
Estimated total tokens: ~350K-450K
```

| Step | Agents Spawned | Tokens per Agent | Parallel? | Step Total |
|------|---------------|-----------------|-----------|------------|
| **0a. Brief parsing** | brief-reader + brief-interpreter | 15K + 18.5K | ✅ 2 parallel | **~33,500** |
| **0b. Context** | context-loader + codebase-scout | 20K + 31.5K | ✅ 2 parallel | **~51,500** |
| **1. Planning** | technical-planner + wave-planner + code-architect | 27.8K + 26.6K + 23.2K | sequential | **~77,600** |
| **2. Wave 1** (1 feature) | git-manager + be-developer + fe-developer + git-manager | 15.5K + 59K + 62.7K + 15.5K | ✅ 2 dev parallel | **~152,700** |
| **3. Review** | code-reviewer + qa-tester | 33.7K + 30.9K | ✅ 2 parallel | **~64,600** |
| **3b. Fix cycle** (if needed) | be-developer + fe-developer | 59K + 62.7K | ✅ 2 parallel | **~121,700** |
| **4. PR** | pr-creator | 16.5K | sequential | **~16,500** |
| **Orchestrator** | continuous | 38.5K + ~15K coordination | continuous | **~53,500** |
| | | | **TOTAL** | **~571,600** |

> **Without fix cycle: ~450K tokens**
> **With fix cycle: ~572K tokens**

---

### Scenario 3: BUG FIX

```
Total agents spawned: 6-8
Estimated total tokens: ~180K-250K
```

| Step | Agents Spawned | Tokens per Agent | Parallel? | Step Total |
|------|---------------|-----------------|-----------|------------|
| **0. Analysis** | codebase-scout | 31.5K | sequential | **~31,500** |
| **1. Fix** | git-manager + be-developer OR fe-developer + git-manager | 15.5K + 59K + 15.5K | sequential | **~90,000** |
| **2. Review** | code-reviewer + qa-tester | 33.7K + 30.9K | ✅ 2 parallel | **~64,600** |
| **3. PR** | pr-creator | 16.5K | sequential | **~16,500** |
| **Orchestrator** | continuous | 38.5K + ~10K | continuous | **~48,500** |
| | | | **TOTAL** | **~251,100** |

> **Simple bug: ~180K tokens** (skip qa-tester)
> **Complex bug with fix cycle: ~310K tokens**

---

### Scenario 4: SMALL EDIT (typo, config change)

```
Total agents spawned: 3-4
Estimated total tokens: ~100K-130K
```

| Step | Agents Spawned | Tokens per Agent | Parallel? | Step Total |
|------|---------------|-----------------|-----------|------------|
| **1. Direct fix** | be-developer OR fe-developer | 59-63K | sequential | **~61,000** |
| **2. Review** | code-reviewer (scope-aware) | 33.7K | sequential | **~33,700** |
| **3. PR** | pr-creator | 16.5K | sequential | **~16,500** |
| **Orchestrator** | lightweight | 38.5K | continuous | **~38,500** |
| | | | **TOTAL** | **~149,700** |

---

## Token Waste Hotspots

### 1. Developer Agents: Skills Overload (~5,400-8,300 tokens wasted per spawn)

**Problem**: be-developer loads full `nodejs-conventions` (13.5KB / 3,375t) even for a 5-line fix. fe-developer loads 5 skills totaling 33.2KB (8,300t).

**Impact**: With 4 developers per wave × 2 waves = 8 spawns × ~6,850t avg wasted = **~54,800 tokens wasted**

**Fix**: Lazy skill loading — only load conventions if agent needs to create new files. For edits to existing files, conventions are already in the code.

### 2. Orchestrator: Oversized Definition (6,400 tokens)

**Problem**: 25.7KB agent definition loaded even for SMALL EDIT pipeline.

**Impact**: ~6,400 tokens on definition alone, even when 80% of the content is GREENFIELD-specific.

**Fix**: Split into `orchestrator-core.md` (8KB, routing + state) and `orchestrator-greenfield.md` (17KB, loaded only for GREENFIELD).

### 3. Base Overhead × Agent Count (8,100 tokens × N agents)

**Problem**: Every agent pays ~8,100 tokens for system prompt + tool defs + global CLAUDE.md. A GREENFIELD pipeline spawns 22-28 agents.

**Impact**: 8,100 × 25 = **~202,500 tokens** just on base overhead (17% of total)

**Fix**: Use `model: "haiku"` for lightweight agents that don't need Opus/Sonnet reasoning:
- git-manager (bash git commands only)
- docker-manager (health checks only)
- brief-reader (extraction only)
- pr-creator (API calls only)

### 4. Review + Fix Cycle Duplication (~121K tokens)

**Problem**: If code-reviewer finds issues → spawns new be-developer + fe-developer with FULL context reload. Same skills, same docs, different conversation.

**Impact**: ~121,700 tokens per fix cycle. Some pipelines iterate 2-3 times = **~243-365K tokens**

**Fix**:
- code-reviewer should output precise, actionable fixes (file:line → exact change)
- Use `Edit` tool directly from orchestrator for simple fixes instead of spawning full developer agents
- Threshold: <10 lines changed → orchestrator fixes directly; >10 lines → spawn developer

### 5. Parallel Agent Redundancy (docs re-read)

**Problem**: When 4 developers spawn in parallel, each independently reads the same docs (wave-plan, blueprint, conventions, lessons). That's 4× the read cost.

**Impact**: ~15KB docs × 4 agents = 60KB (15,000 tokens) of duplicate reads.

**Fix**: Pre-compile a per-wave `agent-context-wave-N.md` that bundles only what that wave's developers need. Each developer reads 1 file instead of 5-6.

### 6. fe-developer Skills Bloat (8,300 skill tokens)

**Problem**: fe-developer loads 5 skills (33.2KB). `design-philosophy` (5.4KB) and `frontend-craft` (6.7KB) overlap conceptually.

**Impact**: ~8,300 tokens per fe-developer spawn. With 4 FE developers across waves = **~33,200 tokens**

**Fix**: Merge `design-philosophy` + `frontend-craft` into single `frontend-standards.md` (~8KB instead of 12.1KB). Cut 4,100 tokens per FE spawn.

---

## Optimization Summary: Projected Savings

| Optimization | Current Cost | After Fix | Savings | Effort |
|-------------|-------------|-----------|---------|--------|
| **Haiku for simple agents** (git-manager, docker-manager, brief-reader, pr-creator) | 8,100t base × 6 agents = 48.6K | ~3,000t base × 6 = 18K | **~30,600t** (saved on base overhead) | Low — add `model: haiku` to agent defs |
| **Lazy skill loading** for developers | 5,400-8,300t × 8 spawns = ~54.8K | ~1,000t × 8 = 8K | **~46,800t** | Medium — conditional skill loading |
| **Split orchestrator** definition | 6,400t always | 2,000t (core) + 4,400t (greenfield-only) | **~4,400t** per non-greenfield run | Low — split file |
| **Merge FE skills** | 8,300t × 4 FE spawns = 33.2K | 5,250t × 4 = 21K | **~12,200t** | Low — merge 2 files |
| **Pre-compiled wave context** | 15K docs × 4 devs = 60K | 5K × 4 = 20K | **~40,000t** | Medium — generate context file per wave |
| **Direct fix for <10 lines** | 121.7K per fix cycle | 5K (orchestrator edit) | **~116,700t** per avoided cycle | Medium — add threshold logic |
| **TOTAL POTENTIAL SAVINGS** | | | **~250,700t per GREENFIELD run** | |

> **That's ~22% reduction on a typical GREENFIELD pipeline (1.1M → ~860K tokens)**

---

## Recommended Priority Actions

### Quick Wins (< 1 hour each)

1. **Add `model: "haiku"` to simple agents**: git-manager, docker-manager, brief-reader, pr-creator
   - Saves: ~30K tokens per pipeline
   - Risk: None — these agents do deterministic operations

2. **Merge `design-philosophy` + `frontend-craft`** into `frontend-standards.md`
   - Saves: ~12K tokens per pipeline
   - Risk: None — content overlap already exists

3. **Split `orchestrator.md`** into core + greenfield-specific sections
   - Saves: ~4.4K per non-greenfield run
   - Risk: Low — modular improvement

### Medium Effort (2-4 hours)

4. **Pre-compiled wave context file**: Orchestrator generates `docs/agent-context-wave-N.md` before spawning teams
   - Saves: ~40K tokens per pipeline
   - Risk: Low — already partially implemented as `agent-context.md`

5. **Direct fix threshold**: Orchestrator handles <10 line fixes without spawning developer agents
   - Saves: ~117K tokens per fix cycle avoided
   - Risk: Medium — needs good judgment on fix complexity

### Longer Term

6. **Lazy skill loading**: Skills only loaded when agent needs to create new files (not edit existing)
   - Saves: ~47K tokens per pipeline
   - Risk: Medium — needs skill loading refactor in agent definitions
