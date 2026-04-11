# ChatGPT OAuth Proxy — Terms of Service Notice

**Read this before enabling `CHATGPT_OAUTH_ENABLED=true` in production.**

## What You Are Using

The `chatgpt-proxy` sidecar runs an unofficial, community-maintained
npm package — [`EvanZhouDev/openai-oauth`](https://github.com/EvanZhouDev/openai-oauth) —
which implements the **official** OpenAI Codex CLI OAuth flow
(`https://auth.openai.com/oauth/authorize` with the Codex CLI client ID
`app_EMoamEEZ73f0CkXaXp7hrann`) to obtain a session token, then uses that
token to call `https://chatgpt.com/backend-api/codex/*` endpoints as if
it were the official Codex CLI.

**The OAuth flow itself is legitimate** — it's the same flow the
`@openai/codex` CLI uses. What's not officially sanctioned is using
that token from a custom application (this project) rather than the
Codex CLI itself.

From the reference repo's own legal notice:

> This is an unofficial, community-maintained project and is not
> affiliated with, endorsed by, or sponsored by OpenAI, Inc.
>
> It uses your local Codex/ChatGPT authentication cache
> (`auth.json`, e.g. `~/.codex/auth.json`) and should be treated
> like password-equivalent credentials.
>
> Use only for personal, local experimentation on trusted machines;
> do not run as a hosted service, do not share access, and do not
> pool or redistribute tokens.
>
> You are solely responsible for complying with OpenAI's Terms,
> policies, and any applicable agreements; misuse may result in
> rate limits, suspension, or termination.

## Risks You Accept by Enabling This

### 1. Account Suspension / Termination

OpenAI reserves the right to limit, suspend, or terminate any account
that uses Codex access outside the intended scope (personal coding
assistance). Automating marketing outreach or WhatsApp conversations
is **clearly outside** that scope. Use at your own risk.

### 2. Client ID Revocation

OpenAI could invalidate the Codex CLI client ID or tighten token
scoping at any time. If that happens, this integration breaks without
warning. The gateway's fallback-to-API-key logic is the safety net.

### 3. Rate Limit Enforcement

ChatGPT subscriptions have hard daily/hourly caps enforced at the
backend. Automated burst workloads (marketing pipelines, mass blasts)
will hit these caps quickly and trigger 429 responses. There is no
"upgrade" path beyond switching to the paid API.

### 4. Token Theft = Account Takeover

The contents of `data/codex_auth/auth.json` grant full access to the
ChatGPT account they belong to. Treat it like a password:

- Never commit it to git (`.gitignore` already excludes `data/codex_auth/`)
- Never log it or include it in error messages
- Never expose port `10531` outside `127.0.0.1` (docker-compose.yml
  already binds to localhost only — do not change this)
- Never share the file or check it into shared secrets managers
  without equivalent protections

### 5. Silent Upstream Breakage

The community tooling tracks a private OpenAI backend. If OpenAI
changes the `chatgpt.com/backend-api/codex/*` API shape or request
format, calls will start failing. The fallback-to-API-key logic keeps
the pipeline running while you wait for an upstream fix.

## Hard Rules for Safe Use

1. **Use a dedicated ChatGPT account.** Don't use your personal
   account. If OpenAI suspends it, you lose automation capability but
   not your personal access.
2. **Keep `CHATGPT_OAUTH_FALLBACK_TO_API=true`.** Disabling fallback
   makes your pipeline brittle to any proxy issue.
3. **Keep `OPENAI_API_KEY` funded** even if you expect the proxy to
   handle most traffic. Embeddings always hit the real API, and the
   fallback path needs a valid key.
4. **Do not expose the proxy port publicly.** The docker-compose
   binding is `127.0.0.1:10531:10531` — leave it that way.
5. **Do not run the proxy as a multi-tenant service.** Reference
   tool explicitly warns against pooling or redistributing tokens.
6. **Monitor `/health/llm-metrics`.** A sudden spike in
   `proxy_auth_errors` means a token problem; a spike in
   `proxy_rate_limits` means you're hitting the subscription caps.

## If OpenAI Revokes Access

If you see sustained `401` errors from the proxy even after
`codex login` and you cannot re-authenticate:

1. Immediately set `CHATGPT_OAUTH_ENABLED=false` via the FE Settings
   or the config API. All traffic will route to the real OpenAI API.
2. Stop the sidecar: `docker-compose stop chatgpt-proxy`.
3. Do not attempt to re-login with the same account from multiple
   machines or automated scripts — this can trigger anti-abuse
   flagging.
4. If you're affected by a policy change (not a one-off token issue),
   switch to a paid API-only setup: keep `OPENAI_API_KEY` funded and
   `CHATGPT_OAUTH_ENABLED=false` permanently.

## When Not to Use This

**Do not enable OAuth mode if:**

- You're running this as a commercial SaaS that other people use
- You need consistent, contractual SLAs on LLM availability
- Your workload regularly exceeds ChatGPT Plus rate limits
- You cannot tolerate the pipeline suddenly stopping if OpenAI
  changes their client policies

In those cases, the pay-per-token API is the correct solution. The
proxy is a cost-saving convenience for personal / small-team use
cases where brief outages are acceptable.

## Related Documents

- [Setup guide](./chatgpt-oauth-setup.md)
- [Architecture deep-dive](./chatgpt-oauth-architecture.md)
