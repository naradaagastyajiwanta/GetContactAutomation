import { apiClient } from './client'
import type { ControlStatus } from '../lib/types'

export async function getControlStatus(): Promise<ControlStatus> {
  const { data } = await apiClient.get<ControlStatus>('/control/status')
  return data
}

export async function pauseBot(): Promise<{ paused: boolean }> {
  const { data } = await apiClient.post<{ paused: boolean }>('/control/pause')
  return data
}

export async function resumeBot(): Promise<{ paused: boolean }> {
  const { data } = await apiClient.post<{ paused: boolean }>('/control/resume')
  return data
}

export async function toggleChatbot(
  type: 'agent' | 'audiensi' | 'research_multi_agent',
  enabled: boolean,
): Promise<Record<string, boolean>> {
  const { data } = await apiClient.post<Record<string, boolean>>(
    `/control/chatbot/${type}`,
    { enabled },
  )
  return data
}
