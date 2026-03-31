import { apiClient } from './client'

export interface IGAccount {
  id: number
  username: string
  password: string // masked in responses
  enabled: boolean
  notes: string
  login_status: 'untested' | 'success' | 'failed' | 'challenge' | 'banned' | 'rate_limited' | 'auth_limited'
  last_login_test: string | null
  created_at: string
  updated_at: string
}

export interface IGAccountPoolStatus {
  username: string
  healthy: boolean
  login_ok: boolean
  profiles_today: number
  cooldown_remaining_s: number
  last_error: string | null
}

export interface IGAccountsResponse {
  accounts: IGAccount[]
  pool_status: IGAccountPoolStatus[]
}

export async function getIGAccounts(): Promise<IGAccountsResponse> {
  const { data } = await apiClient.get<IGAccountsResponse>('/ig-accounts')
  return data
}

export async function createIGAccount(payload: {
  username: string
  password: string
  notes?: string
}): Promise<{ status: string; account: IGAccount }> {
  const { data } = await apiClient.post<{ status: string; account: IGAccount }>(
    '/ig-accounts',
    payload,
  )
  return data
}

export async function updateIGAccount(
  id: number,
  payload: {
    username?: string
    password?: string
    enabled?: boolean
    notes?: string
  },
): Promise<{ status: string; account: IGAccount }> {
  const { data } = await apiClient.put<{ status: string; account: IGAccount }>(
    `/ig-accounts/${id}`,
    payload,
  )
  return data
}

export async function deleteIGAccount(
  id: number,
): Promise<{ status: string }> {
  const { data } = await apiClient.delete<{ status: string }>(`/ig-accounts/${id}`)
  return data
}

export interface TestLoginDetails {
  cookies: Record<string, string>
  final_url: string
  profile_nuked: boolean
}

export interface TestLoginResult {
  status: string
  result: { success: boolean; message: string; details?: TestLoginDetails }
  login_status: string
}

export async function testIGAccountLogin(
  id: number,
): Promise<TestLoginResult> {
  const { data } = await apiClient.post<TestLoginResult>(
    `/ig-accounts/${id}/test-login`,
  )
  return data
}

/** SSE event types emitted by the live login endpoint */
export interface TestLoginSSEEvent {
  type: 'status' | 'screenshot' | 'done' | 'result'
  ts?: number
  message?: string
  step?: string
  screenshot?: string // base64 JPEG
  result?: { success: boolean; message: string; details?: TestLoginDetails }
  login_status?: string
}

/**
 * Connect to the live test-login SSE endpoint.
 * Returns an EventSource — caller must close it when done.
 */
export function connectTestLoginLive(
  id: number,
  onEvent: (evt: TestLoginSSEEvent) => void,
  onError?: (err: Event) => void,
): EventSource {
  const es = new EventSource(`/api/ig-accounts/${id}/test-login-live`)
  es.onmessage = (msg) => {
    try {
      const data: TestLoginSSEEvent = JSON.parse(msg.data)
      onEvent(data)
    } catch {
      // ignore parse errors
    }
  }
  es.onerror = (err) => {
    onError?.(err)
    es.close()
  }
  return es
}

// ---------------------------------------------------------------------------
// New headless login flow (simple REST, no SSE)
// ---------------------------------------------------------------------------

export interface LoginResult {
  status: 'success' | 'challenge' | 'failed' | 'ip_blocked'
  message: string
  session_id: string | null
  screenshot: string | null // base64 JPEG (challenge page)
  details: {
    cookies: Record<string, string>
    final_url: string
    profile_nuked?: boolean
    reason?: string       // e.g. "datacenter_ip_block"
    in_docker?: boolean
  }
}

export async function loginIGAccount(id: number): Promise<LoginResult> {
  const { data } = await apiClient.post<LoginResult>(`/ig-accounts/${id}/login`)
  return data
}

export interface ChallengeResult {
  status: 'success' | 'failed'
  message: string
  screenshot: string | null
  details: {
    cookies: Record<string, string>
    final_url: string
  }
}

export async function submitLoginChallenge(
  id: number,
  sessionId: string,
  code: string,
): Promise<ChallengeResult> {
  const { data } = await apiClient.post<ChallengeResult>(
    `/ig-accounts/${id}/login/challenge`,
    { session_id: sessionId, code },
  )
  return data
}

// ---------------------------------------------------------------------------
// IG Account Health Check
// ---------------------------------------------------------------------------

export interface IGAccountHealthItem {
  username: string
  status: 'connected' | 'disconnected' | 'banned' | 'rate_limited' | 'error' | 'auth_limited'
  reason: string | null
  username_verified: string | null
}

export interface IGAccountsHealthResponse {
  total: number
  connected: number
  all_ok: boolean
  accounts: IGAccountHealthItem[]
  checked_at: string
}

export async function getIGAccountsHealth(
  force = false,
): Promise<IGAccountsHealthResponse> {
  const { data } = await apiClient.get<IGAccountsHealthResponse>(
    '/ig-accounts/health',
    { params: force ? { force: true } : undefined },
  )
  return data
}

// ---------------------------------------------------------------------------
// Session Export / Import (for syncing sessions between local ↔ server)
// ---------------------------------------------------------------------------

/**
 * Download the Playwright session profile for an account as a tar.gz blob.
 * Returns the Blob directly for the caller to trigger a download.
 */
export async function exportIGSession(id: number, username: string): Promise<void> {
  const resp = await apiClient.get(`/ig-accounts/${id}/session/export`, {
    responseType: 'blob',
  })
  const blob = new Blob([resp.data], { type: 'application/gzip' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `ig_session_${username}.tar.gz`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export interface SessionImportResult {
  status: string
  import: { success: boolean; message: string; members: number }
  verify: {
    status: string
    reason: string | null
    username_verified: string | null
  }
}

/**
 * Upload a tar.gz session profile archive for an account.
 */
export async function importIGSession(
  id: number,
  file: File,
): Promise<SessionImportResult> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await apiClient.post<SessionImportResult>(
    `/ig-accounts/${id}/session/import`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 },
  )
  return data
}

// ---------------------------------------------------------------------------
// Cookie Import (browser extension → server session)
// ---------------------------------------------------------------------------

export interface CookieImportResult {
  status: string
  import: {
    success: boolean
    message: string
    cookies_count: number
    has_sessionid: boolean
    has_ds_user_id: boolean
    has_csrftoken: boolean
  }
  verify: {
    status: string
    reason: string | null
    username_verified: string | null
  }
}

/**
 * Import raw browser cookies (JSON array) into the server's Playwright profile.
 * The cookies are typically exported from a browser extension like Cookie-Editor.
 */
export async function importIGCookies(
  id: number,
  cookies: Array<Record<string, unknown>>,
): Promise<CookieImportResult> {
  const { data } = await apiClient.post<CookieImportResult>(
    `/ig-accounts/${id}/session/import-cookies`,
    { cookies },
    { timeout: 120_000 },
  )
  return data
}
