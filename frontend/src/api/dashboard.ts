import { apiClient } from './client'
import type { DashboardStats } from '../lib/types'

export async function getDashboardStats(): Promise<DashboardStats> {
  const { data } = await apiClient.get<DashboardStats>('/dashboard')
  return data
}
