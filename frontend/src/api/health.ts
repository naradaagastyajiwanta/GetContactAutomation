import { apiClient } from './client'
import type { HealthStatus } from '../lib/types'

export async function getHealth(): Promise<HealthStatus> {
  const { data } = await apiClient.get<HealthStatus>('/health')
  return data
}
