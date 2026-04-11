import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Info,
  LogIn,
  LogOut,
  Clipboard,
  Download,
  X,
} from "lucide-react";
import {
  cancelCodexLogin,
  getCodexStatus,
  getLLMMetrics,
  importExternalCodexAuth,
  logoutCodex,
  refreshCodexToken,
  startCodexLogin,
  submitCodexManualCode,
  waitForCodexLogin,
  type CodexOAuthStatusResponse,
  type CodexStatus,
  type LLMMetricsResponse,
} from "../../api/chatgptOAuth";

/**
 * ChatGPT OAuth Panel — in-process flow (no Docker sidecar).
 *
 * Drives the orchestrator's /auth/codex/* endpoints:
 *   - Login button → POST /auth/codex/start, opens authorize URL,
 *     long-polls /auth/codex/wait
 *   - Manual code paste fallback for headless setups
 *   - Logout, refresh, status, metrics
 *
 * Config toggles (CHATGPT_OAUTH_ENABLED, FALLBACK_TO_API, ORIGINATOR)
 * are still edited via the Config tab's ConfigDisplay component.
 */

function statusBadge(status: CodexStatus | undefined) {
  switch (status) {
    case "logged_in":
      return {
        icon: CheckCircle2,
        label: "Logged in",
        color: "text-green-600 dark:text-green-400",
        bg: "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800",
      };
    case "logged_out":
      return {
        icon: XCircle,
        label: "Logged out",
        color: "text-amber-600 dark:text-amber-400",
        bg: "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800",
      };
    case "disabled":
      return {
        icon: Info,
        label: "Disabled",
        color: "text-gray-500 dark:text-gray-400",
        bg: "bg-gray-50 dark:bg-gray-900/30 border-gray-200 dark:border-gray-700",
      };
    case "error":
    default:
      return {
        icon: AlertTriangle,
        label: "Error",
        color: "text-red-600 dark:text-red-400",
        bg: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800",
      };
  }
}

function formatExpiry(expiresInSeconds: number | undefined): string {
  if (expiresInSeconds === undefined) return "—";
  if (expiresInSeconds <= 0) return "expired";
  const hours = Math.floor(expiresInSeconds / 3600);
  const minutes = Math.floor((expiresInSeconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function ChatGPTOAuthPanel() {
  const [status, setStatus] = useState<CodexOAuthStatusResponse | null>(null);
  const [metrics, setMetrics] = useState<LLMMetricsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loginInProgress, setLoginInProgress] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showSetup, setShowSetup] = useState(false);
  const [showManual, setShowManual] = useState(false);
  const [manualInput, setManualInput] = useState("");
  const [manualSubmitting, setManualSubmitting] = useState(false);

  // Auto-dismiss success banner after 6 seconds
  const successTimerRef = useRef<number | null>(null);
  const showSuccess = (message: string) => {
    setError(null);
    setSuccess(message);
    if (successTimerRef.current !== null) {
      window.clearTimeout(successTimerRef.current);
    }
    successTimerRef.current = window.setTimeout(() => {
      setSuccess(null);
      successTimerRef.current = null;
    }, 6000);
  };

  // Monotonic counter for login attempts — used to silently discard
  // stale results when the user starts a fresh login before the
  // previous one has resolved (e.g. closed browser tab mid-OAuth).
  const loginAttemptRef = useRef(0);

  useEffect(() => {
    return () => {
      if (successTimerRef.current !== null) {
        window.clearTimeout(successTimerRef.current);
      }
    };
  }, []);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, m] = await Promise.all([getCodexStatus(), getLLMMetrics()]);
      setStatus(s);
      setMetrics(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30_000);
    return () => clearInterval(interval);
  }, []);

  const handleLogin = async () => {
    // Bump the attempt counter and capture our own ID. Any previous
    // handleLogin invocation that is still awaiting a long-poll will
    // notice (on resume) that its ID no longer matches the latest and
    // silently discard its result — no flicker error toasts when the
    // user retries after closing a stale browser tab.
    const myAttempt = ++loginAttemptRef.current;
    const isStale = () => loginAttemptRef.current !== myAttempt;

    setError(null);
    setSuccess(null);
    setLoginInProgress(true);
    try {
      // Proactively tell the backend to tear down any leftover in-flight
      // session from a previous click. The backend's begin_login() also
      // auto-supersedes stale sessions, so this is belt-and-suspenders —
      // if the first call here fails (no active session), that's fine.
      try {
        await cancelCodexLogin();
      } catch {
        /* no active flow — nothing to cancel */
      }

      if (isStale()) return;

      const start = await startCodexLogin();
      if (isStale()) return;

      // Open the authorize URL in a new tab so the user can complete OAuth
      window.open(start.authorize_url, "_blank", "noopener,noreferrer");

      // Long-poll the orchestrator until the callback fires
      const result = await waitForCodexLogin(300);

      // A newer handleLogin call started and already superseded this one
      if (isStale()) return;

      // Server-side supersede marker: another /auth/codex/start call
      // replaced this session (e.g. user clicked Login twice). Silently
      // discard — the newer attempt handler will take over.
      if (result.status === "superseded") {
        console.log("[codex-login] superseded by newer attempt, discarding");
        return;
      }

      await refresh();
      const accountSnippet = result.account_id
        ? ` (account: ${result.account_id.slice(0, 8)}…)`
        : "";
      showSuccess(
        `Login successful${accountSnippet}. Tokens stored and ready to use.`,
      );
      console.log("Codex login complete:", result);
    } catch (e: unknown) {
      // If a newer attempt has already taken over, silently drop this
      // error — the user already moved on.
      if (isStale()) return;

      const message =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? (e instanceof Error ? e.message : "Login failed");
      setError(String(message));
      // Best-effort cleanup of the in-flight server
      try {
        await cancelCodexLogin();
      } catch {
        /* ignore */
      }
    } finally {
      // Only clear the spinner if we are the latest attempt. Otherwise
      // a newer attempt is still running and should keep the spinner on.
      if (!isStale()) {
        setLoginInProgress(false);
      }
    }
  };

  const handleManualSubmit = async () => {
    if (!manualInput.trim()) {
      setError("Paste the redirect URL or auth code first");
      return;
    }
    setManualSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      // Make sure a flow is in progress so the PKCE verifier exists in
      // memory. If user clicked Login earlier the start call already
      // happened; if not, this will start a fresh one.
      if (!loginInProgress) {
        try {
          await startCodexLogin();
        } catch {
          // 409 Conflict is fine — there's already an active flow
        }
      }
      const result = await submitCodexManualCode(manualInput.trim());
      setManualInput("");
      setShowManual(false);
      await refresh();
      const accountSnippet = result.account_id
        ? ` (account: ${result.account_id.slice(0, 8)}…)`
        : "";
      showSuccess(
        `Manual login successful${accountSnippet}. Tokens stored and ready to use.`,
      );
    } catch (e: unknown) {
      const message =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? (e instanceof Error ? e.message : "Manual login failed");
      setError(String(message));
    } finally {
      setManualSubmitting(false);
    }
  };

  const handleLogout = async () => {
    if (!confirm("Logout from Codex OAuth and clear stored tokens?")) return;
    setError(null);
    setSuccess(null);
    try {
      await logoutCodex();
      await refresh();
      showSuccess("Logged out. Stored tokens cleared.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Logout failed");
    }
  };

  const handleRefreshToken = async () => {
    setError(null);
    setSuccess(null);
    try {
      const result = await refreshCodexToken();
      await refresh();
      const expiresIn = Math.max(
        0,
        Math.round((result.expires_at - Date.now() / 1000) / 60),
      );
      showSuccess(`Token refreshed. Valid for ~${expiresIn} more minutes.`);
    } catch (e: unknown) {
      const message =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? (e instanceof Error ? e.message : "Refresh failed");
      setError(String(message));
    }
  };

  const handleImportExternal = async () => {
    setError(null);
    setSuccess(null);
    try {
      await importExternalCodexAuth();
      await refresh();
      showSuccess(
        "Imported credentials from ~/.codex/auth.json. Tokens ready to use.",
      );
    } catch (e: unknown) {
      const message =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? (e instanceof Error ? e.message : "Import failed");
      setError(String(message));
    }
  };

  const codexTotal =
    (metrics?.codex_chat_calls ?? 0) + (metrics?.codex_responses_calls ?? 0);
  const fallbackTotal =
    (metrics?.fallback_chat_calls ?? 0) +
    (metrics?.fallback_responses_calls ?? 0);
  const directTotal =
    (metrics?.direct_chat_calls ?? 0) + (metrics?.direct_responses_calls ?? 0);
  const grandTotal = codexTotal + fallbackTotal + directTotal;
  const codexPct = grandTotal ? (codexTotal / grandTotal) * 100 : 0;

  const isLoggedIn = status?.status === "logged_in";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            ChatGPT OAuth (In-Process)
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-2xl">
            Routes OpenAI chat / responses / vision calls through a ChatGPT Plus
            subscription via the in-process Codex OAuth flow. No sidecar
            container — the orchestrator talks directly to{" "}
            <code>chatgpt.com/backend-api/codex</code>. Embeddings still use{" "}
            <code>OPENAI_API_KEY</code>.
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
          />
          Refresh
        </button>
      </div>

      {success && (
        <div className="flex items-start gap-2 rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 p-3 text-xs text-green-800 dark:text-green-300">
          <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 font-medium">{success}</div>
          <button
            onClick={() => setSuccess(null)}
            className="flex-shrink-0 text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-200"
            aria-label="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-3 text-xs text-red-700 dark:text-red-300">
          <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 font-medium">{error}</div>
          <button
            onClick={() => setError(null)}
            className="flex-shrink-0 text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-200"
            aria-label="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Status card */}
      {status &&
        (() => {
          const badge = statusBadge(status.status);
          const BadgeIcon = badge.icon;
          return (
            <div className={`rounded-lg border ${badge.bg} p-4`}>
              <div className="flex items-start gap-3">
                <BadgeIcon
                  className={`h-5 w-5 ${badge.color} flex-shrink-0 mt-0.5`}
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-semibold ${badge.color}`}>
                      {badge.label}
                    </span>
                    {metrics?.oauth_enabled === false && (
                      <span className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 font-medium">
                        CHATGPT_OAUTH_ENABLED=false
                      </span>
                    )}
                  </div>
                  {status.status === "logged_in" && (
                    <div className="mt-2 grid gap-1 text-xs text-gray-700 dark:text-gray-300">
                      {status.account_id && (
                        <div>
                          <span className="text-gray-500 dark:text-gray-400">
                            Account:{" "}
                          </span>
                          <code className="font-mono">{status.account_id}</code>
                        </div>
                      )}
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">
                          Token expires in:{" "}
                        </span>
                        <span className="font-medium">
                          {formatExpiry(status.expires_in_seconds)}
                        </span>
                      </div>
                    </div>
                  )}
                  {status.message && status.status !== "logged_in" && (
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                      {status.message}
                    </p>
                  )}
                </div>
              </div>

              {/* Action buttons */}
              <div className="mt-4 flex flex-wrap gap-2">
                {!isLoggedIn && (
                  <>
                    <button
                      onClick={handleLogin}
                      disabled={loginInProgress}
                      className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
                    >
                      <LogIn className="h-3.5 w-3.5" />
                      {loginInProgress
                        ? "Waiting for browser…"
                        : "Login with ChatGPT"}
                    </button>
                    <button
                      onClick={() => setShowManual((v) => !v)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                      <Clipboard className="h-3.5 w-3.5" />
                      Manual paste (headless)
                    </button>
                    <button
                      onClick={handleImportExternal}
                      className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Import ~/.codex/auth.json
                    </button>
                  </>
                )}
                {isLoggedIn && (
                  <>
                    <button
                      onClick={handleRefreshToken}
                      className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Refresh token
                    </button>
                    <button
                      onClick={handleLogout}
                      className="inline-flex items-center gap-1.5 rounded-md border border-red-300 dark:border-red-700 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                    >
                      <LogOut className="h-3.5 w-3.5" />
                      Logout
                    </button>
                  </>
                )}
              </div>

              {/* Manual paste form */}
              {showManual && (
                <div className="mt-4 space-y-2 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/50 p-3">
                  <p className="text-xs text-gray-600 dark:text-gray-400">
                    Paste the full redirect URL (or just the <code>code=</code>{" "}
                    parameter) from your browser after completing the OAuth flow
                    on a different machine.
                  </p>
                  <input
                    type="text"
                    value={manualInput}
                    onChange={(e) => setManualInput(e.target.value)}
                    placeholder="http://localhost:1455/auth/callback?code=...&state=..."
                    className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs font-mono"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={handleManualSubmit}
                      disabled={manualSubmitting}
                      className="rounded bg-indigo-600 hover:bg-indigo-700 px-3 py-1 text-xs font-medium text-white disabled:opacity-60"
                    >
                      {manualSubmitting ? "Submitting…" : "Submit"}
                    </button>
                    <button
                      onClick={() => {
                        setShowManual(false);
                        setManualInput("");
                      }}
                      className="rounded border border-gray-300 dark:border-gray-600 px-3 py-1 text-xs text-gray-700 dark:text-gray-300"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })()}

      {/* Metrics card */}
      {metrics && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              LLM Routing Metrics
            </h3>
            {metrics.cooldown_remaining_seconds > 0 && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 font-medium">
                Cooldown: {Math.round(metrics.cooldown_remaining_seconds)}s
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <Stat label="Codex (chat)" value={metrics.codex_chat_calls} />
            <Stat label="Codex (resp)" value={metrics.codex_responses_calls} />
            <Stat
              label="Codex 429"
              value={metrics.codex_rate_limits}
              warning={metrics.codex_rate_limits > 0}
            />
            <Stat
              label="Codex 401"
              value={metrics.codex_auth_errors}
              warning={metrics.codex_auth_errors > 0}
            />
            <Stat label="Fallback (chat)" value={metrics.fallback_chat_calls} />
            <Stat
              label="Fallback (resp)"
              value={metrics.fallback_responses_calls}
            />
            <Stat label="Direct API" value={directTotal} />
            <Stat label="Embeddings" value={metrics.direct_embeddings_calls} />
          </div>

          {grandTotal > 0 && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400 mb-1">
                <span>Codex hit rate</span>
                <span>{codexPct.toFixed(1)}%</span>
              </div>
              <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 to-purple-500"
                  style={{ width: `${codexPct}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Setup instructions (collapsible) */}
      <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <button
          onClick={() => setShowSetup((s) => !s)}
          className="w-full px-4 py-3 text-left text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center justify-between"
        >
          <span>How it works</span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {showSetup ? "Hide" : "Show"}
          </span>
        </button>
        {showSetup && (
          <div className="px-4 pb-4 text-xs text-gray-600 dark:text-gray-400 space-y-2 border-t border-gray-200 dark:border-gray-700 pt-3">
            <ol className="list-decimal list-inside space-y-2">
              <li>
                Click <strong>Login with ChatGPT</strong>. The orchestrator
                generates a PKCE verifier, spawns a temporary callback server on{" "}
                <code>localhost:1455</code>, and opens the OpenAI authorize URL
                in a new tab.
              </li>
              <li>
                Sign in with your ChatGPT Plus / Pro account. OpenAI redirects
                back to the callback server, which captures the authorization
                code and exchanges it for an access + refresh token.
              </li>
              <li>
                Tokens are stored at <code>data/codex_auth/auth.json</code>{" "}
                (gitignored). The store auto-refreshes the access token before
                expiry on every API call.
              </li>
              <li>
                For headless servers without browser access, use{" "}
                <strong>Manual paste</strong>: open the authorize URL on a
                machine with a browser, complete OAuth, then paste the redirect
                URL back here.
              </li>
              <li>
                Or click <strong>Import ~/.codex/auth.json</strong> if you
                already ran <code>codex login</code> on this host with the
                official Codex CLI — the orchestrator can mirror those
                credentials.
              </li>
              <li>
                Once logged in, set <code>CHATGPT_OAUTH_ENABLED=true</code> in
                the Config tab to start routing traffic through Codex.
              </li>
            </ol>
          </div>
        )}
      </div>

      {/* ToS notice */}
      <div className="rounded-lg border border-amber-200 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/10 p-3">
        <div className="flex items-start gap-2 text-xs">
          <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-amber-800 dark:text-amber-300">
            <p className="font-medium mb-1">Terms of Service Notice</p>
            <p className="leading-relaxed">
              Uses the official Codex CLI OAuth flow (same{" "}
              <code>client_id</code> as <code>codex login</code>). Intended for
              personal / small-team use with a dedicated ChatGPT account. Keep{" "}
              <code>CHATGPT_OAUTH_FALLBACK_TO_API</code> enabled so the real API
              takes over if access is ever revoked.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  warning = false,
}: {
  label: string;
  value: number;
  warning?: boolean;
}) {
  return (
    <div className="rounded-md bg-gray-50 dark:bg-gray-900/50 p-2.5">
      <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p
        className={`text-lg font-semibold mt-0.5 ${
          warning
            ? "text-amber-600 dark:text-amber-400"
            : "text-gray-900 dark:text-gray-100"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
