import axios from 'axios'
import { apiClient } from './client'
import type {
  AuthAccessAssignment,
  AuthAuditLog,
  AuthBootstrapStatus,
  AuthMeResponse,
  AuthRoleDefinition,
  AuthRoleKey,
  AuthRoleUpgradeRequest,
  AuthRoleUpgradeRequestStatus,
} from '../lib/types'

export interface LoginPayload {
  email: string
  password: string
}

export interface SetupPayload extends LoginPayload {
  role_key?: AuthRoleKey
}

export interface LoginResponse {
  status: string
  user: AuthMeResponse['user']
  bootstrap_completed?: boolean
}

export interface AuthAccessResponse {
  assignments: AuthAccessAssignment[]
  roles: AuthRoleDefinition[]
}

export interface AuthAuditLogsResponse {
  logs: AuthAuditLog[]
  total: number
}

export interface AuthRoleRequestsResponse {
  requests: AuthRoleUpgradeRequest[]
  total: number
}

export interface MyAuthRoleRequestsResponse {
  requests: AuthRoleUpgradeRequest[]
  available_roles: AuthRoleKey[]
}

export async function getCurrentUser(): Promise<AuthMeResponse | null> {
  try {
    const { data } = await apiClient.get<AuthMeResponse>('/auth/me')
    return data
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      return null
    }
    throw error
  }
}

export async function getBootstrapStatus(): Promise<AuthBootstrapStatus> {
  const { data } = await apiClient.get<AuthBootstrapStatus>('/auth/bootstrap-status')
  return data
}

export async function login(payload: LoginPayload): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/auth/login', payload)
  return data
}

export async function setupInitialAdmin(payload: SetupPayload): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/auth/setup', payload)
  return data
}

export async function logout(): Promise<{ status: string }> {
  const { data } = await apiClient.post<{ status: string }>('/auth/logout')
  return data
}

export async function getAuthAccess(): Promise<AuthAccessResponse> {
  const { data } = await apiClient.get<AuthAccessResponse>('/auth/access')
  return data
}

export async function getAuthAuditLogs(limit = 50, offset = 0): Promise<AuthAuditLogsResponse> {
  const { data } = await apiClient.get<AuthAuditLogsResponse>('/auth/audit-logs', { params: { limit, offset } })
  return data
}

export async function grantAuthRole(payload: { email: string; role_key: AuthRoleKey }): Promise<{ status: string }> {
  const { data } = await apiClient.post<{ status: string }>('/auth/access/grant', payload)
  return data
}

export async function revokeAuthRole(payload: { dms_user_id: number; role_key: AuthRoleKey }): Promise<{ status: string }> {
  const { data } = await apiClient.post<{ status: string }>('/auth/access/revoke', payload)
  return data
}

export async function getAuthRoleRequests(
  status: AuthRoleUpgradeRequestStatus | '' = 'pending',
  limit = 50,
  offset = 0,
): Promise<AuthRoleRequestsResponse> {
  const params: Record<string, string | number> = { limit, offset }
  if (status) params.status = status
  const { data } = await apiClient.get<AuthRoleRequestsResponse>('/auth/role-requests', { params })
  return data
}

export async function getMyAuthRoleRequests(limit = 20): Promise<MyAuthRoleRequestsResponse> {
  const { data } = await apiClient.get<MyAuthRoleRequestsResponse>('/auth/role-requests/me', { params: { limit } })
  return data
}

export async function createAuthRoleRequest(payload: {
  role_key: AuthRoleKey
  request_note?: string
}): Promise<{ status: string; request: AuthRoleUpgradeRequest }> {
  const { data } = await apiClient.post<{ status: string; request: AuthRoleUpgradeRequest }>('/auth/role-requests', payload)
  return data
}

export async function approveAuthRoleRequest(
  requestId: number,
  payload?: { review_note?: string },
): Promise<{ status: string }> {
  const { data } = await apiClient.post<{ status: string }>(`/auth/role-requests/${requestId}/approve`, payload ?? {})
  return data
}

export async function rejectAuthRoleRequest(
  requestId: number,
  payload?: { review_note?: string },
): Promise<{ status: string }> {
  const { data } = await apiClient.post<{ status: string }>(`/auth/role-requests/${requestId}/reject`, payload ?? {})
  return data
}