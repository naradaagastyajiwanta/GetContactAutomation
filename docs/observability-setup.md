# Observability Setup — Sentry Error Tracking

This document walks through enabling **Sentry.io** for the orchestrator
to capture runtime errors, performance traces, and release health data.

## TL;DR

1. Sign up at [sentry.io](https://sentry.io/signup/) (free tier, no CC required)
2. Create a new project → Platform: **Python** → Framework: **FastAPI**
3. Copy the DSN (format: `https://<public-key>@oXXXXXX.ingest.sentry.io/YYYYYY`)
4. Paste into `.env.production` (local or via GitLab `ENV_PRODUCTION` CI var):
   ```bash
   SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/789
   SENTRY_ENVIRONMENT=production
   SENTRY_TRACES_SAMPLE_RATE=0.1
   ```
5. Redeploy (`docker compose up -d orchestrator` or push to `main`)
6. Trigger a test error: `curl -X POST http://localhost:8010/health/sentry-test` (if you add a test endpoint) OR wait for a real error

Sentry will appear in your dashboard at `https://<org>.sentry.io/issues/`
within seconds of the first error event.

---

## Phase 1 — Python Orchestrator (CURRENT)

This phase only instruments the orchestrator (FastAPI). WhatsApp service
and React frontend are covered by later phases.

### What gets captured

| Event | How | Captured? |
|---|---|---|
| Unhandled exception in FastAPI endpoint | `FastApiIntegration` | ✅ auto |
| `httpx.AsyncClient` 4xx/5xx or timeout | `HttpxIntegration` | ✅ auto |
| `log.error(...)` → breadcrumb (not event) | `LoggingIntegration` | ✅ auto |
| `asyncio.Task` unhandled error | `AsyncioIntegration` | ✅ auto |
| Codex OAuth auth error (handled, then fallback) | `capture_exception()` in `gateway.py` | ✅ explicit |
| Codex upstream 5xx (handled, then fallback) | `capture_exception()` in `gateway.py` | ✅ explicit |
| Codex rate limit 429 (expected behavior) | — (logged as warning only) | ❌ intentional |
| 10% of FastAPI endpoint performance traces | `traces_sample_rate=0.1` | ✅ sampled |

### What does NOT get captured (intentional)

- **Rate limit 429 responses** — these are expected operational behavior,
  would spam Sentry with noise, and already tracked in
  `/health/llm-metrics` counters.
- **Successful requests** (except for 10% performance sample).
- **DB queries** (SQLAlchemy integration not used — we use aiosqlite).
- **WA service errors** — covered in Phase 3.
- **React frontend errors** — covered in Phase 2.

### Privacy — what's scrubbed before events leave the process

See `orchestrator/observability.py::_SENSITIVE_KEYS` and `_before_send()`:

**Always redacted (dict keys)**:
- `password`, `api_key`, `access_token`, `refresh_token`, `id_token`
- `authorization`, `cookie`, `set-cookie`
- `openai_api_key`, `gemini_api_key`, `serper_api_key`, `apify_api_key`, `scrapingbot_api_key`
- `dms_mysql_password`, `smtp_password`, `imap_password`
- `sentry_dsn`, `sentry_auth_token`, `gcs_service_account_json`
- `chatgpt_account_id`, `ig_session_id`, `ig_password`
- `x-api-key`, `x-auth-token`

**PII masked in strings** (exception messages, breadcrumb messages):
- Email addresses → `[email-redacted]`
- Indonesian mobile numbers (`08xx...` or `+628xx...`) → `[phone-redacted]`

**NOT redacted** (by design, useful for debugging):
- `account_id` (ChatGPT JWT claim identifier, opaque UUID)
- `university_id`, `conversation_id` (internal numeric IDs)
- HTTP status codes, request paths, stack traces

---

## Setup Steps (detailed)

### Step 1 — Create Sentry account and project

1. Go to [sentry.io/signup](https://sentry.io/signup/)
2. Sign up (Google/GitHub auth works fine)
3. On the "Create Your First Project" screen:
   - Platform: **Python**
   - Framework: **FastAPI**
   - Alert frequency: "Alert me on every new issue" (recommended for active dev)
   - Team/Project name: `getcontact-ai` (or your preferred)
4. On the next screen, **copy the DSN**. It looks like:
   ```
   https://abc123def456@o0000000.ingest.sentry.io/1234567
   ```
5. Keep that DSN — you'll paste it into `.env.production` next.

### Step 2 — Configure env vars

**Local development** (`.env`):
```bash
# Optional for local dev — leave empty to disable Sentry locally
SENTRY_DSN=
```

Local dev usually leaves `SENTRY_DSN` empty — you don't want dev errors
polluting production dashboards.

**Production on VPS** (`.env.production`):
```bash
SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/789
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
# SENTRY_RELEASE is set automatically by GitLab CI — leave empty here
SENTRY_RELEASE=
```

**GitLab CI** (for secure distribution of `.env.production`):
- GitLab → your project → Settings → CI/CD → Variables
- Add/update the `ENV_PRODUCTION` variable (masked, protected) with the
  full `.env.production` content including `SENTRY_DSN`
- Save. Next deploy will propagate the new env to the VPS.

### Step 3 — Deploy

```bash
# Option A: trigger via git push to main
git add requirements.txt orchestrator/observability.py orchestrator/main.py \
        orchestrator/llm/gateway.py docker-compose.yml docker-compose.prod.yml \
        .env.example .gitlab-ci.yml docs/observability-setup.md
git commit -m "feat(observability): add Sentry error tracking for orchestrator

Env-var driven (SENTRY_DSN). No-op when unset. Integrates FastAPI, httpx,
asyncio, and logging. PII scrubber redacts tokens, keys, passwords, and
auto-masks emails + Indonesian phone numbers in event payloads. Explicit
capture_exception() in LLM gateway for Codex auth/upstream errors.
GitLab CI injects SENTRY_RELEASE=\$CI_COMMIT_SHORT_SHA on each deploy for
release-health tracking."
git push origin main

# Option B: manual deploy on the VPS
ssh ubuntu@vps "cd /var/www/get_contact_jiwan && \
  docker compose -f docker-compose.prod.yml build orchestrator && \
  docker compose -f docker-compose.prod.yml up -d orchestrator"
```

### Step 4 — Verify

Check orchestrator logs for the initialization message:

```bash
docker logs gc-orchestrator --tail 50 | grep -i sentry
# Expected:
#   [observability] Sentry initialized (env=production, release=e02ca69, traces=0.10)
#   Sentry error tracking enabled
```

Trigger a test error (optional) — the easiest way is to call a protected
endpoint without auth, which will raise `HTTPException(401)` and be
captured:

```bash
curl -v http://localhost:8010/config
# Returns 401 — check Sentry dashboard for "Authentication required" event
```

Then check your Sentry dashboard at `https://<your-org>.sentry.io/issues/`
— you should see events appearing within 10-30 seconds.

---

## Monitoring usage

Sentry free tier: **5,000 errors/month**, **10,000 performance units/month**.

Check your usage at:
`https://<your-org>.sentry.io/settings/billing/usage/`

Rule of thumb:
- If you approach 80% of the error quota → reduce `traces_sample_rate`
  to `0.05` or add explicit scrubbing of noisy error types
- If you consistently exceed the free tier → upgrade to **Team plan**
  ($26/month, 50,000 errors/month)

---

## Disabling Sentry temporarily

Just unset `SENTRY_DSN` in `.env.production` and redeploy orchestrator:

```bash
# On VPS
sed -i 's/^SENTRY_DSN=.*/SENTRY_DSN=/' /var/www/get_contact_jiwan/.env.production
docker compose -f docker-compose.prod.yml restart orchestrator
```

`init_sentry()` becomes a no-op with empty DSN. No code change needed.

---

## Troubleshooting

### "Sentry init failed (non-critical)" in logs

Orchestrator logs this warning if `init_sentry()` throws any exception
during startup. Check the accompanying error message — usually one of:

1. **Malformed DSN** — verify the DSN is valid URL format from Sentry
   dashboard → Settings → Client Keys.
2. **Network unreachable to `ingest.sentry.io`** — Sentry SDK tries a
   DNS resolve at init. Check VPS outbound DNS and HTTPS are working.
3. **sentry-sdk not installed** — rebuild the orchestrator image after
   updating `requirements.txt`. The no-op guard catches this and skips.

### Errors not showing up in Sentry dashboard

1. Verify `SENTRY_DSN` is set in the **container** env, not just the host:
   ```bash
   docker exec gc-orchestrator env | grep SENTRY
   ```
2. Check `send_default_pii` is false (it is, by default) — verify scrubber
   didn't accidentally drop the event. Look for `[observability]`
   messages in `docker logs`.
3. Verify environment matches what you're filtering by in Sentry UI —
   `SENTRY_ENVIRONMENT=production` means events appear under "production"
   filter, not "development".
4. Check quota hasn't been exceeded (look at `/settings/billing/usage/`).

### Too many events / hitting free tier cap

1. Check which issue types are most noisy in Sentry → Issues → Sort by "Events"
2. Add explicit filters in `orchestrator/observability.py::_before_send`:
   ```python
   # Drop all events from a specific exception type
   if event.get("exception", {}).get("values", [{}])[0].get("type") == "NoisyError":
       return None   # returning None drops the event
   ```
3. Reduce `SENTRY_TRACES_SAMPLE_RATE` from `0.1` to `0.01` (1% of traces)
4. Consider upgrading to Team plan ($26/mo = 50K errors)

---

## Future phases (not yet implemented)

### Phase 2 — React frontend

Add `@sentry/react` + `@sentry/vite-plugin` for browser error capture
with source-map-resolved stack traces.

### Phase 3 — WhatsApp service

Add `@sentry/node` for Baileys connection errors and message send
failures. Integrate with Express via `Sentry.setupExpressErrorHandler`.

### Phase 4 — GitLab release tracking via sentry-cli

Currently `SENTRY_RELEASE` is injected at deploy time but no release is
formally "created" in Sentry. Phase 4 adds `sentry-cli releases new`
+ `set-commits --auto` + `finalize` for full release health metrics and
regression detection.

### Phase 5 — Alerting + dashboards

Configure Slack integration, custom alert rules, and team dashboards in
Sentry UI. No code changes required.

See `PLAN: Sentry Integration` in the project notes for the full roadmap.
