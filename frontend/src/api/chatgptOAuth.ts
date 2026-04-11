import { apiClient } from "./client";

/**
 * API client for the in-process Codex OAuth subsystem.
 *
 * Talks to the orchestrator's /auth/codex/* endpoints. There is NO
 * sidecar container — the OAuth flow runs entirely inside the
 * orchestrator's Python process. The callback server only binds
 * to localhost:1455 while a login is actively in progress.
 */

export type CodexStatus = "logged_in" | "logged_out" | "disabled" | "error";

export interface CodexOAuthStatusResponse {
  status: CodexStatus;
  message?: string;
  account_id?: string | null;
  expires_at?: number;
  expires_in_seconds?: number;
  source?: "cache" | "disk" | "none";
}

export interface LLMMetricsResponse {
  codex_chat_calls: number;
  codex_responses_calls: number;
  codex_errors: number;
  codex_rate_limits: number;
  codex_auth_errors: number;
  fallback_chat_calls: number;
  fallback_responses_calls: number;
  direct_chat_calls: number;
  direct_responses_calls: number;
  direct_embeddings_calls: number;
  cooldown_remaining_seconds: number;
  oauth_enabled: boolean;
  fallback_enabled: boolean;
}

export interface StartLoginResponse {
  authorize_url: string;
  state: string;
  callback_host: string;
  callback_port: number;
}

export interface LoginResultResponse {
  status: "logged_in";
  account_id?: string | null;
  expires_at: number;
}

export async function getCodexStatus(): Promise<CodexOAuthStatusResponse> {
  const { data } = await apiClient.get<CodexOAuthStatusResponse>(
    "/health/codex-oauth",
  );
  return data;
}

export async function getLLMMetrics(): Promise<LLMMetricsResponse> {
  const { data } = await apiClient.get<LLMMetricsResponse>(
    "/health/llm-metrics",
  );
  return data;
}

export async function startCodexLogin(): Promise<StartLoginResponse> {
  const { data } =
    await apiClient.post<StartLoginResponse>("/auth/codex/start");
  return data;
}

/**
 * Long-poll the orchestrator until the OAuth callback is captured and
 * the token exchange completes. Resolves with the logged-in status.
 *
 * Pass `timeoutSeconds` to control how long the orchestrator will
 * wait for the user to complete the browser flow before giving up.
 */
export async function waitForCodexLogin(
  timeoutSeconds: number = 300,
): Promise<LoginResultResponse> {
  const { data } = await apiClient.post<LoginResultResponse>(
    "/auth/codex/wait",
    null,
    {
      params: { timeout_seconds: timeoutSeconds },
      timeout: (timeoutSeconds + 30) * 1000,
    },
  );
  return data;
}

export async function submitCodexManualCode(
  input: string,
): Promise<LoginResultResponse> {
  const { data } = await apiClient.post<LoginResultResponse>(
    "/auth/codex/manual",
    {
      input,
    },
  );
  return data;
}

export async function cancelCodexLogin(): Promise<void> {
  await apiClient.post("/auth/codex/cancel");
}

export async function logoutCodex(): Promise<void> {
  await apiClient.post("/auth/codex/logout");
}

export async function refreshCodexToken(): Promise<LoginResultResponse> {
  const { data } = await apiClient.post<LoginResultResponse>(
    "/auth/codex/refresh",
  );
  return data;
}

export async function importExternalCodexAuth(): Promise<{ ok: boolean }> {
  const { data } = await apiClient.post<{ ok: boolean }>(
    "/auth/codex/import-external",
  );
  return data;
}
