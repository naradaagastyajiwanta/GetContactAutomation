import { apiClient } from './client'

export interface IGAccount {
  id: number
  username: string
  password: string // masked in responses
  enabled: boolean
  notes: string
  login_status: 'untested' | 'success' | 'failed' | 'challenge' | 'banned'
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
  status: 'success' | 'challenge' | 'failed'
  message: string
  session_id: string | null
  screenshot: string | null // base64 JPEG (challenge page)
  details: {
    cookies: Record<string, string>
    final_url: string
    profile_nuked?: boolean
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
  status: 'connected' | 'disconnected' | 'banned' | 'rate_limited' | 'error'
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
