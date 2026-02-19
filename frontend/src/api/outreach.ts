import { apiClient } from './client'

export async function startOutreach(): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post<{ status: string; message: string }>('/outreach/start')
  return data
}

export async function processFollowups(): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post<{ status: string; message: string }>('/outreach/process-followups')
  return data
}
