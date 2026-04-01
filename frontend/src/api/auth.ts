import axios from 'axios'
import { apiClient } from './client'
import type {
  AuthAccessAssignment,
  AuthAuditLog,
  AuthBootstrapStatus,
  AuthMeResponse,
  AuthRoleDefinition,
  AuthRoleKey,
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