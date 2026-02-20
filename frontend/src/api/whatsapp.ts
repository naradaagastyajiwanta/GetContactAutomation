import { apiClient } from './client'

export interface WaQrResponse {
  qr: string | null
  dataUrl: string | null
  connected: boolean
  phoneNumber: string | null
}

export interface WaStatusResponse {
  connected: boolean
  phoneNumber: string | null
  reconnectAttempt: number
  maxReconnectAttempts: number
}

export async function getWaQr(): Promise<WaQrResponse> {
  const { data } = await apiClient.get<WaQrResponse>('/wa/qr')
  return data
}

export async function getWaStatus(): Promise<WaStatusResponse> {
  const { data } = await apiClient.get<WaStatusResponse>('/wa/status')
  return data
}

export async function sendTestMessage(to: string, message: string) {
  const { data } = await apiClient.post('/wa/send-test', { to, message })
  return data as { success: boolean; messageId?: string; error?: string }
}

export async function waLogout() {
  const { data } = await apiClient.post('/wa/logout')
  return data as { success: boolean; message?: string; error?: string }
}

export async function waRestart() {
  const { data } = await apiClient.post('/wa/restart')
  return data as { success: boolean; message?: string; error?: string }
}
