import { apiClient } from './client'

export interface ConfigSetting {
  key: string
  value: string | number | boolean
  default: string | number | boolean
  type: 'int' | 'float' | 'bool' | 'string'
  group: string
  label: string
  description: string
  min_value: number | null
  max_value: number | null
  sensitive?: boolean
  has_value?: boolean | null
}

export interface ConfigResponse {
  settings: ConfigSetting[]
}

export async function getConfig(): Promise<ConfigResponse> {
  const { data } = await apiClient.get<ConfigResponse>('/config')
  return data
}

export async function updateConfig(
  settings: Record<string, string | number | boolean>,
): Promise<{ status: string; updated: string[] }> {
  const { data } = await apiClient.patch<{ status: string; updated: string[] }>(
    '/config',
    { settings },
  )
  return data
}

export async function resetConfig(
  key: string,
): Promise<{ status: string; key: string; value: string | number | boolean }> {
  const { data } = await apiClient.delete<{
    status: string
    key: string
    value: string | number | boolean
  }>(`/config/${key}`)
  return data
}

export async function getModels(): Promise<{ models: string[]; error?: string }> {
  const { data } = await apiClient.get<{ models: string[]; error?: string }>('/config/models')
  return data
}
