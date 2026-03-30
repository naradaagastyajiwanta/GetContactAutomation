# Email Blast Deliverability Plan

## Problem Statement

Webmail `sekretariat@asosiasi.ai` via `mail.asosiasi.ai` sering di-ban/flag oleh mail server target. Root causes:

1. Semua email blast keluar dari 1 akun SMTP
2. Bounce rate tinggi dari invalid addresses
3. Tidak ada warmup schedule
4. Content triggering spam filters
5. Domain belum ter-authenticate dengan benar

## Solution Layers

### Layer 1: Multi-Account SMTP Rotation ✅ (Priority 1 — Start Here)
**Goal:** Distribute email load across multiple SMTP accounts to avoid single-account rate limits and bans.

**Changes:**
- Add `SMTP_ACCOUNTS` config (JSON array): `[{host, port, user, password, use_ssl, rotate_after}]`
- `rotate_after_n_emails` config: rotate to next account after N emails (default: 50)
- `SMTPClient` class rotates accounts when quota/limit reached
- Fallback to next account if one gets auth error or flagged
- Track active account index in-memory

**Files changed:**
- `orchestrator/config_registry.py` — add SMTP_ACCOUNTS, ROTATE_AFTER_N config
- `orchestrator/email_blast.py` — SMTPClient rotation logic
- `.env.example`, `.env.production.example` — new config vars

---

### Layer 2: Pre-Send Email Validation
**Goal:** Reduce bounce rate by validating emails before sending.

**Changes:**
- Install `email-validator` package
- Add `VALIDATE_EMAIL_BEFORE_SEND` config (bool, default: true)
- Before sending: check MX record, syntax, disposable domain
- If invalid: mark as `invalid` (not `failed`) and skip sending
- Track `invalid_count` per campaign

**Files changed:**
- `requirements.txt` — add `email-validator`
- `orchestrator/email_blast.py` — validation logic
- `orchestrator/db.py` — add `invalid` status + `invalid_count` column
- `orchestrator/config_registry.py` — add VALIDATE_EMAIL_BEFORE_SEND config

---

### Layer 3: Adaptive Delay & Warmup Mode
**Goal:** Prevent spam flags by starting slow and ramping up over time.

**Changes:**
- Add `WARMUP_ENABLED` config (bool, default: true)
- Add `WARMUP_SCHEDULE` config: JSON object mapping day → max_emails `{ "1": 5, "3": 15, "7": 50, "14": 100, "30": 200 }`
- Add `AUTO_INCREASE_DELAY_ON_ERROR` config (bool, default: true)
- If SMTP error: double current delay, log warning
- Warmup mode: obey daily cap based on warmup schedule
- After warmup days elapsed: full speed (respecting daily 200 limit)

**Files changed:**
- `orchestrator/config_registry.py` — add warmup configs
- `orchestrator/email_blast.py` — warmup + adaptive delay logic
- `orchestrator/scheduler.py` — reset adaptive delay daily

---

### Layer 4: Improved Email Content
**Goal:** Reduce spam filter triggers through better email content and RFC compliance.

**Changes:**
- Add `ENABLE_UNSUBSCRIBE_HEADER` config (bool, default: true)
- Add List-Unsubscribe header (RFC 8058) to every email
- Generate text/plain version alongside HTML
- Avoid spam trigger phrases (configurable word list)
- Proper encoding and multipart/alternative MIME type
- Track spam_score per campaign (future enhancement)

**Files changed:**
- `orchestrator/email_blast.py` — multipart email, unsubscribe header
- `orchestrator/config_registry.py` — add ENABLE_UNSUBSCRIBE_HEADER config

---

### Layer 5: Monitoring & Auto-Recovery
**Goal:** Detect account bans early and auto-recover without manual intervention.

**Changes:**
- Add `SMTP_HEALTH_CHECK_INTERVAL` config (default: 30 emails)
- After every N emails: send test ping to itself
- If ping fails: mark account as `degraded` and skip to next
- Add `account_health` table in DB: `{account_key, status, fail_count, last_success}`
- API endpoint `GET /email-blast/smtp-health` — returns per-account status
- Frontend: show SMTP account health in Settings page
- Auto-recovery: after 1 hour, attempt to use degraded account again

**Files changed:**
- `orchestrator/db.py` — add `smtp_account_health` table
- `orchestrator/email_blast.py` — health check + auto-recovery logic
- `orchestrator/main.py` — add `/email-blast/smtp-health` endpoint
- `frontend/src/api/emailBlast.ts` — add health check API client
- `frontend/src/pages/SettingsPage.tsx` — add SMTP health display

---

## Database Schema Changes

### New column in `email_blast_campaigns`
```sql
ALTER TABLE email_blast_campaigns ADD COLUMN invalid_count INTEGER DEFAULT 0;
```

### New table `smtp_account_health`
```sql
CREATE TABLE IF NOT EXISTS smtp_account_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key TEXT UNIQUE NOT NULL,  -- hash of account credentials
    email_address TEXT NOT NULL,
    status TEXT DEFAULT 'active',       -- active | degraded | banned
    fail_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    last_error TEXT,
    last_success_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Config Variables Summary

### Layer 1
```
SMTP_ACCOUNTS=[{"host":"mail.asosiasi.ai","port":465,"user":"sekretariat@asosiasi.ai","password":"xxx","use_ssl":true}]
ROTATE_AFTER_N_EMAILS=50
```

### Layer 2
```
VALIDATE_EMAIL_BEFORE_SEND=true
```

### Layer 3
```
WARMUP_ENABLED=true
WARMUP_SCHEDULE={"1":5,"3":15,"7":50,"14":100,"30":200}
AUTO_INCREASE_DELAY_ON_ERROR=true
```

### Layer 4
```
ENABLE_UNSUBSCRIBE_HEADER=true
```

### Layer 5
```
SMTP_HEALTH_CHECK_INTERVAL=30
```

---

## Testing Plan

1. Create test campaign with 5 recipients
2. Verify rotation works (check from_address in sent emails)
3. Verify warmup respects daily cap
4. Verify validation skips invalid emails
5. Verify multipart email format
6. Verify auto-recovery after simulated ban

---

## Rollout Order

1. Layer 1 (Multi-Account Rotation) — **FIRST**
2. Layer 3 (Warmup + Adaptive Delay) — **SECOND**
3. Layer 2 (Pre-Send Validation) — **THIRD**
4. Layer 4 (Email Content) — **FOURTH**
5. Layer 5 (Monitoring) — **FIFTH**
