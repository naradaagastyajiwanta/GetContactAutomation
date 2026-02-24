import { apiClient } from './client'
import type { HealthStatus } from '../lib/types'

export async function getHealth(): Promise<HealthStatus> {
  const { data } = await apiClient.get<HealthStatus>('/health')
  return data
}

export async function resetIgSessions(): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post('/instagram/reset-sessions')
  return data
}
