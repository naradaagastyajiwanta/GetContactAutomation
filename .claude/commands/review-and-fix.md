---
description: "Review code + fix issues dengan Agent Team"
---

# /review-and-fix — Agent Team Review Pipeline

## LANGKAH 0: MODE DETECTION
1. `git diff --name-only develop...HEAD` → count files changed
2. ≤20 files = scope-aware mode, >20 files = full mode
3. Baca `docs/change-context.md` untuk konfirmasi scope

## LANGKAH 1: SPAWN REVIEW TEAM (Agent Team, parallel)
Spawn Agent Team dengan teammates:
- **code-reviewer**: review logic, architecture, bugs. (Lint/format sudah dihandle hooks)
- **user-simulator**: browser testing via GStack

Setiap teammate bekerja paralel di worktree terpisah.

## LANGKAH 2: COLLECT FINDINGS
- code-reviewer → `docs/code-review-report.md`
- user-simulator → `docs/user-simulation-report.md`
- Merge findings, prioritize: CRITICAL → HIGH → MEDIUM → LOW

## LANGKAH 3: FIX LOOP (with fix-strategist)
Untuk setiap finding:
1. **fix-strategist** membaca `docs/fix-ledger.md` → tentukan strategi baru
2. **fix-strategist** update ledger dengan strategi yang akan dicoba
3. **be-developer** / **fe-developer** execute fix (parallel jika independent)
4. Jika fix gagal → kembali ke fix-strategist (max 3 attempts per issue)

## LANGKAH 4: RE-TEST
- qa-tester + qa-checklist-runner (parallel)
- Hanya test yang relevan dengan fix yang dibuat

## LANGKAH 5: HEALTH CHECK
- docker-manager: verify semua containers healthy
- Endpoint smoke test

## LANGKAH 6: PR
- pr-creator: buat PR develop → main
- Include changelog dari semua fixes
