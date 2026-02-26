Buat agent team untuk review, fix, dan validation phase.

## Context
- Kode sudah dibuat di branch sesuai docs/architecture-blueprint.md
- docs/task-breakdown.md berisi semua tasks
- docs/technical-spec.md berisi requirements teknis
- Docker container sudah running

## Team Setup

Buat team dengan 5 teammates:

### 1. code-reviewer (Task tool, subagent_type: superpowers:code-reviewer)
Mulai PARALEL dengan user-simulator.

**Tugas:**
- Review SEMUA kode (backend + frontend) di branch ini
- Focus pada:
  - Code quality & conventions
  - Error handling
  - Type safety (frontend)
  - SQL injection risks (backend)
  - Security issues
- Buat `docs/code-review-report.md`
- Tunggu input dari user-simulator
- Setelah dapat user issues: finalize report, tentukan BE/FE
- Kirim Backend Issues ke be-developer
- Kirim Frontend Issues ke fe-developer

### 2. user-simulator (Task tool, subagent_type: general-purpose)
Mulai PARALEL dengan code-reviewer.

**Tugas:**
- Test semua user flows dari technical-spec
- Buka browser/manual test via frontend
- Cek:
  - All buttons work
  - Forms submit correctly
  - Data displays properly
  - Error messages show
- Buat `docs/user-simulation-report.md`
- Setelah selesai: kirim hasil ke code-reviewer

### 3. be-developer (Task tool, subagent_type: general-purpose)
Tunggu pesan dari code-reviewer.

**Tugas:**
- Terima Backend Issues dari code-reviewer
- Fix semua 🔴 Blocker dan 🟡 Major issues
- Gunakan docker exec untuk commands
- Commit setiap fix: `fix(scope): description`
- Setelah selesai: kirim pesan "backend fix done"

### 4. fe-developer (Task tool, subagent_type: general-purpose)
Tunggu pesan dari code-reviewer, paralel dengan be-developer.

**Tugas:**
- Terima Frontend Issues dari code-reviewer
- Fix semua 🔴 Blocker dan 🟡 Major issues
- Gunakan docker exec untuk commands
- Commit setiap fix: `fix(ui): description`
- Setelah selesai: kirim pesan "frontend fix done"

### 5. qa-tester (Task tool, subagent_type: general-purpose)
Tunggu BE dan FE keduanya done.

**Tugas:**
- Jalankan test suite (jika ada)
- Re-run user flows yang sebelumnya fail
- Verify semua Blocker dan Major issues fixed
- Buat final test report
- Jika ada fail: kirim pesan ke lead dengan detail error

## Alur Kerja

```
LEAD (koordinasi only)
  |
  ├─> code-reviewer ──────────────────┐
  │   (review code)                   │ PARALEL
  │                                    │
  ├─> user-simulator ──────────────────┘
  │   (test user flows)
  │           |
  │           └──> kirim temuan ke code-reviewer
  │                          |
  │               code-reviewer finalize
  │                      |
  │         ┌─────────────┴─────────────┐
  │         ▼                           ▼
  │   be-developer                 fe-developer   (PARALEL fix)
  │   (fix BE issues)              (fix FE issues)
  │         |                           |
  │         └─────────────┬─────────────┘
  │                       ▼
  │                 qa-tester
  │              (re-test + verify)
  │                       |
  └───────────────────────┘
              DONE
```

## Format Code Review Report

### docs/code-review-report.md
```markdown
# Code Review Report: [Nama Fitur]
**Date:** [tanggal]
**Branch:** feat/[xxx]-[yyy]
**Reviewer:** code-reviewer

## Summary
- **Total Issues:** [N]
- **Critical:** [N]
- **Major:** [N]
- **Minor:** [N]

## Backend Issues

### 🔴 CRITICAL-001: SQL Injection Risk
**File:** orchestrator/main.py:123
**Code:** `f"SELECT * FROM table WHERE name = '{name}'"`
**Issue:** String interpolation allows SQL injection
**Fix:** Use parameterized query
**Assigned:** be-developer

### 🟡 MAJOR-001: Missing Error Handling
**File:** orchestrator/service.py:45
**Issue:** No try-except for database operation
**Fix:** Add error handling with logging
**Assigned:** be-developer

[... more issues]

## Frontend Issues

### 🔴 CRITICAL-002: Type Unsafe
**File:** frontend/src/pages/Page.tsx:78
**Issue:** Using `any` type for props
**Fix:** Define proper interface
**Assigned:** fe-developer

[... more issues]

## User Issues (from user-simulator)

### 🔴 USER-001: Form Not Submitting
**Flow:** Create [Resource]
**Steps:** Open form → fill data → click submit
**Expected:** Data saved, success message
**Actual:** Nothing happens
**Root Cause:** Likely BE issue
**Assigned:** be-developer

[... more issues]
```

## Format User Simulation Report

### docs/user-simulation-report.md
```markdown
# User Simulation Report: [Nama Fitur]
**Date:** [tanggal]
**Tester:** user-simulator

## Environment
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Test Data: [sample data used]

## User Flows Tested

### Flow 1: Create [Resource]
**Status:** ✅ PASS / ❌ FAIL
**Steps:**
1. Navigate to /page
2. Click "Add New" button
3. Fill form:
   - Field 1: [value]
   - Field 2: [value]
4. Click Submit

**Expected:** Resource created, success toast, redirect to list
**Actual:** [what happened]

**Screenshots/Error:**
```
[Error message if any]
```

### Flow 2: View [Resource] Detail
[... same format]

## Summary
- **Total Flows:** [N]
- **Passed:** [N]
- **Failed:** [N]

## Failed Flows Detail
[List all failed flows with issues to report to code-reviewer]
```

## Final Test Report

### docs/final-test-report.md
```markdown
# Final Test Report: [Nama Fitur]
**Date:** [tanggal]
**Tester:** qa-tester

## Regression Tests
### Backend Tests
```
pytest tests/ -v
```
**Result:** ✅ PASS / ❌ FAIL

### Frontend Tests
```
npm test
```
**Result:** ✅ PASS / ❌ FAIL

## User Flows Re-test
[Re-test flows that failed in user-simulation]

### Flow 1: Create [Resource] (RE-TEST)
**Previous Status:** ❌ FAIL
**Current Status:** ✅ PASS
**Verification:** Issue fixed, flow works correctly

[... more re-tests]

## Final Summary
- **All Critical Issues:** Fixed ✅
- **All Major Issues:** Fixed ✅
- **Minor Issues:** [N] remaining (optional)
- **All User Flows:** Passing ✅

## Recommendation
✅ Ready for Merge Request / ❌ More work needed
```

## Lead Responsibilities
- Koordinasi team, JANGAN tulis kode
- Pantau progress semua 5 teammates
- Redirect jika ada yang stuck
- Verify reports selesai
- Sarankan next step: @pr-creator
