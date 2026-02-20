import { apiClient } from './client'
import type { AudiensiConversation, AudiensiStats, Message } from '../lib/types'

interface AudiensiParams {
  state?: string
  limit?: number
  offset?: number
}

interface RawAudiensiConversation extends Omit<AudiensiConversation, 'message_history'> {
  message_history: string | Message[]
}

function parseAudiensi(data: RawAudiensiConversation): AudiensiConversation {
  return {
    ...data,
    message_history:
      typeof data.message_history === 'string'
        ? JSON.parse(data.message_history)
        : data.message_history,
  }
}

export async function getAudiensiConversations(params?: AudiensiParams): Promise<AudiensiConversation[]> {
  const { data } = await apiClient.get<RawAudiensiConversation[]>('/audiensi', { params })
  return data.map(parseAudiensi)
}

export async function getAudiensiQueue(): Promise<AudiensiConversation[]> {
  const { data } = await apiClient.get<RawAudiensiConversation[]>('/audiensi/queue')
  return data.map(parseAudiensi)
}

export async function getAudiensiConversation(id: number): Promise<AudiensiConversation> {
  const { data } = await apiClient.get<RawAudiensiConversation>(`/audiensi/${id}`)
  return parseAudiensi(data)
}

export async function getAudiensiStats(): Promise<AudiensiStats> {
  const { data } = await apiClient.get<AudiensiStats>('/audiensi/stats')
  return data
}

export async function approveAudiensi(id: number): Promise<void> {
  await apiClient.post(`/audiensi/${id}/approve`)
}

export async function rejectAudiensi(id: number): Promise<void> {
  await apiClient.post(`/audiensi/${id}/reject`)
}

export async function updateRectorName(id: number, rectorName: string): Promise<void> {
  await apiClient.put(`/audiensi/${id}/rector-name`, { rector_name: rectorName })
}

export async function updateInitialMessage(id: number, message: string): Promise<void> {
  await apiClient.put(`/audiensi/${id}/initial-message`, { message })
}

export async function regeneratePdf(id: number): Promise<void> {
  await apiClient.post(`/audiensi/${id}/regenerate-pdf`)
}

export async function sendZoomLink(id: number): Promise<void> {
  await apiClient.post(`/audiensi/${id}/send-zoom`)
}

export async function uploadTemplate(file: File): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  await apiClient.post('/audiensi/template/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export async function getTemplatePlaceholders(): Promise<{ placeholders: Array<{ key: string; description: string }> }> {
  const { data } = await apiClient.get('/audiensi/template/placeholders')
  return data
}
