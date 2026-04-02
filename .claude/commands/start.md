---
description: "Entry point utama — single command untuk semua operasi"
---

# /start — Single Entry Point

Kamu menerima input dari user dalam bentuk apapun. Tugasmu:
1. Classify apa yang user minta
2. Route ke orchestrator dengan mode yang benar

**User HANYA perlu ingat satu command: `/start`**
Semua command lain (`/qa-checklist`, `/review-and-fix`, `/retro`, dll) adalah internal tools
yang dipanggil orchestrator — bukan yang user perlu hafal.

---

## STEP 1: CLASSIFY INPUT

Analisis input user dan classify ke salah satu mode:

| Mode | Trigger Pattern | Contoh Input |
|------|----------------|--------------|
| **BUILD** | Brief file, feature description, greenfield | `/start briefs/spec.docx`, `/start Add user auth` |
| **FIX** | Bug report, error, fix request | `/start Bug: login fails`, `/start fix the checkout error` |
| **TEST** | Test file, test request, QA | `/start test briefs/tests.xlsx`, `/start run QA` |
| **REVIEW** | Review request, check code | `/start review this`, `/start check my code` |
| **SHIP** | PR/merge request | `/start ship it`, `/start create PR` |
| **RETRO** | Retrospective, analysis | `/start retro`, `/start what happened last sprint` |
| **RESUME** | Continue, lanjut | `/start resume`, `/start continue` |
| **CLEAN** | Save and exit | `/start clean up` |

### Classification Logic

```bash
INPUT="$ARGUMENTS"
INPUT_LOWER=$(echo "$INPUT" | tr '[:upper:]' '[:lower:]')

# 1. File detection (highest priority)
if echo "$INPUT" | grep -qE '\.(docx|pdf)$'; then
  MODE="BUILD"
  BRIEF_FILE=$(echo "$INPUT" | grep -oE '[^ ]*\.(docx|pdf)')
elif echo "$INPUT" | grep -qE '\.(xlsx|xls|csv)$'; then
  MODE="TEST"
  TEST_FILE=$(echo "$INPUT" | grep -oE '[^ ]*\.(xlsx|xls|csv)')
  # Check for --data flag or second file
  DATA_FILE=$(echo "$INPUT" | grep -oE '\-\-data [^ ]*' | cut -d' ' -f2)
  if [ -z "$DATA_FILE" ]; then
    # Check for second file path (Windows or Linux)
    DATA_FILE=$(echo "$INPUT" | grep -oE '([A-Z]:\\[^ ]*\.(xlsx|xls|csv)|/[^ ]*\.(xlsx|xls|csv))' | tail -1)
    [ "$DATA_FILE" = "$TEST_FILE" ] && DATA_FILE=""
  fi

# 2. Keyword detection
elif echo "$INPUT_LOWER" | grep -qE 'bug|error|fix|gagal|failed|broken|crash'; then
  MODE="FIX"
elif echo "$INPUT_LOWER" | grep -qE 'test|qa|checklist|run.*test|check.*quality'; then
  MODE="TEST"
elif echo "$INPUT_LOWER" | grep -qE 'review|check.*code|check.*pr|audit'; then
  MODE="REVIEW"
elif echo "$INPUT_LOWER" | grep -qE 'ship|merge|create.*pr|ready.*deploy'; then
  MODE="SHIP"
elif echo "$INPUT_LOWER" | grep -qE 'retro|retrospective|what.*happened|sprint.*review'; then
  MODE="RETRO"
elif echo "$INPUT_LOWER" | grep -qE 'resume|continue|lanjut|keep.*going'; then
  MODE="RESUME"
elif echo "$INPUT_LOWER" | grep -qE 'clean|save.*exit|stop.*save'; then
  MODE="CLEAN"
else
  MODE="BUILD"  # default: treat as feature request
fi

echo "Mode: $MODE"
```

---

## STEP 2: RESOLVE FILE PATHS

Jika input mengandung file paths:

```bash
# Resolve Windows paths to WSL (WAJIB — kita di WSL2)
resolve_path() {
  local P="$1"
  if echo "$P" | grep -qE '^[A-Z]:'; then
    echo "$P" | sed 's|^\([A-Z]\):|/mnt/\L\1|; s|\\\\|/|g; s|\\|/|g'
  else
    echo "$P"
  fi
}

# Resolve all detected file paths
[ -n "$BRIEF_FILE" ] && BRIEF_FILE=$(resolve_path "$BRIEF_FILE")
[ -n "$TEST_FILE" ] && TEST_FILE=$(resolve_path "$TEST_FILE")
[ -n "$DATA_FILE" ] && DATA_FILE=$(resolve_path "$DATA_FILE")

# Verify files exist
[ -n "$BRIEF_FILE" ] && ls "$BRIEF_FILE" 2>/dev/null && echo "Brief: OK" || echo "Brief: NOT FOUND"
[ -n "$TEST_FILE" ] && ls "$TEST_FILE" 2>/dev/null && echo "Test file: OK" || echo "Test file: NOT FOUND"
[ -n "$DATA_FILE" ] && ls "$DATA_FILE" 2>/dev/null && echo "Data file: OK" || echo "Data file: NOT FOUND"
```

---

## STEP 3: ROUTE TO ORCHESTRATOR

Semua mode → orchestrator. Orchestrator yang menentukan agents mana yang dipanggil.

### MODE: BUILD
```
→ Orchestrator (full pipeline)
  input: $ARGUMENTS
  brief_file: $BRIEF_FILE (jika ada)
  mode: fresh
  pipeline: Phase 0 → 0B → 1 → APPROVE → 2 → 3 → 4 → Critic → PR
```

### MODE: FIX
```
→ Orchestrator (bug fix pipeline)
  input: $ARGUMENTS
  mode: fix
  pipeline: Phase 0 → Tracer → Fix Strategy → Implement → Test → PR
```

### MODE: TEST
```
→ Orchestrator (test-only pipeline)
  input: $ARGUMENTS
  test_file: $TEST_FILE (jika ada)
  data_file: $DATA_FILE (jika ada)
  mode: test
  pipeline:
    Jika test_file ada (.xlsx/.docx/.csv/.md):
      → read-xlsx/read-docx (convert) → qa-checklist-interpreter → qa-checklist-runner → report
    Jika tidak ada test_file:
      → qa-checklist-generator → qa-checklist-runner → report
    Jika ada findings yang perlu fix:
      → fix cycle (be/fe-developer) → re-test
```

### MODE: REVIEW
```
→ Orchestrator (review-only pipeline)
  input: $ARGUMENTS
  mode: review
  pipeline: code-reviewer → security-check → critic → fix cycle jika perlu
```

### MODE: SHIP
```
→ Orchestrator (ship pipeline)
  mode: ship
  pipeline: health check → PR creation (develop → main)
```

### MODE: RETRO
```
→ Orchestrator (retro pipeline)
  mode: retro
  pipeline: retro-agent → report → auto-apply improvements
```

### MODE: RESUME
```
→ Orchestrator (resume)
  mode: resume
  pipeline: baca wave-execution-state.md → lanjut dari file terakhir
```

### MODE: CLEAN
```
→ Save state → compact → notify → exit
```

---

## STEP 4: RESUME CHECK (sebelum route)

```bash
if [ "$MODE" = "RESUME" ] || [ -f "docs/wave-execution-state.md" ]; then
  if [ -f "docs/wave-execution-state.md" ]; then
    STATUS=$(grep "^- \*\*Status\*\*:" docs/wave-execution-state.md | head -1 | cut -d: -f2 | xargs)
    CURRENT_WAVE=$(grep "^- \*\*Current Wave\*\*:" docs/wave-execution-state.md | head -1 | cut -d: -f2 | xargs)
    COMPLETED=$(grep -c '\[x\]' docs/wave-execution-state.md)
    TOTAL=$(grep -c '\[ \]\|\[x\]' docs/wave-execution-state.md)

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔄 RESUME STATE DETECTED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Wave: $CURRENT_WAVE"
    echo "Files: $COMPLETED / $TOTAL completed"
    echo "Status: $STATUS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ "$MODE" != "RESUME" ]; then
      echo "⚠️ Previous pipeline state found. Starting fresh will overwrite it."
    fi
  fi
fi
```

---

## CHANNEL MODE AWARENESS

```bash
CHANNEL_MODE="custom"
if [ -f ".claude/telegram/channel-mode.env" ]; then
  source .claude/telegram/channel-mode.env
  [ "${CHANNEL_MODE:-}" = "native" ] && kill -0 "${SESSION_PID:-0}" 2>/dev/null && CHANNEL_MODE="native"
fi
```

Semua decision points via AskUserQuestion (channel handles relay otomatis).

---

## CONTOH PENGGUNAAN

```
# Build
/start briefs/feature-spec.docx
/start Add PDF export to reports page
/start Buat aplikasi e-commerce dengan React + Laravel

# Fix
/start Bug: checkout returns 500 on mobile
/start fix the login validation error
/start docs/user-simulation-report.md has issues that need fixing

# Test
/start test briefs/test-cases.xlsx
/start run tests from briefs/AI_Excel_Addins_Test_Brief.xlsx using C:\Users\me\Downloads\dataset.xlsx
/start test everything
/start run QA

# Review
/start review this code
/start check my PR

# Ship
/start ship it
/start create PR

# Other
/start resume
/start retro
/start clean up
```

## HANDOFF
Serahkan kontrol ke orchestrator setelah classification. Jangan micro-manage.
