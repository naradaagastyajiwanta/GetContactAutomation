import { apiClient } from './client'
import type { PipelineStatus, PipelineLog } from '../lib/types'

export async function getPipelineStatus(): Promise<PipelineStatus> {
  const { data } = await apiClient.get<PipelineStatus>('/pipeline/status')
  return data
}

export interface PipelineLogsParams {
  agent_type?: string
  status?: string
  limit?: number
  offset?: number
}

export interface PipelineLogsResponse {
  items: PipelineLog[]
  total: number
}

export async function getPipelineLogs(params?: PipelineLogsParams): Promise<PipelineLogsResponse> {
  const { data } = await apiClient.get<PipelineLogsResponse>('/pipeline/logs', { params })
  return data
}

export async function getPipelineLogDetail(id: number): Promise<PipelineLog> {
  const { data } = await apiClient.get<PipelineLog>(`/pipeline/logs/${id}`)
  return data
}

export async function getProvinces(): Promise<string[]> {
  const { data } = await apiClient.get<{ provinces: string[] }>('/pddikti/provinces')
  return data.provinces
}

export async function triggerCollectUniversities(params?: { province?: string; limit?: number }): Promise<{ status: string; message: string }> {
  const queryParams: Record<string, string | number> = {}
  if (params?.province) queryParams.province = params.province
  if (params?.limit != null) queryParams.limit = params.limit
  const { data } = await apiClient.post<{ status: string; message: string }>('/pipeline/collect-universities', null, {
    params: Object.keys(queryParams).length > 0 ? queryParams : undefined,
  })
  return data
}

export async function triggerFindHandles(limit?: number): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post<{ status: string; message: string }>('/pipeline/find-ig-handles', null, {
    params: limit != null ? { limit } : undefined,
  })
  return data
}

export async function triggerScrapePosts(limit?: number): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post<{ status: string; message: string }>('/pipeline/scrape-ig-posts', null, {
    params: limit != null ? { limit } : undefined,
  })
  return data
}

export async function triggerExtractPhones(limit?: number): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post<{ status: string; message: string }>('/pipeline/extract-phones', null, {
    params: limit != null ? { limit } : undefined,
  })
  return data
}

export async function triggerDiscoverBem(limit?: number): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post<{ status: string; message: string }>('/pipeline/discover-bem', null, {
    params: limit != null ? { limit } : undefined,
  })
  return data
}

export async function triggerFindRectors(limit?: number): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post<{ status: string; message: string }>('/pipeline/find-rectors', null, {
    params: limit != null ? { limit } : undefined,
  })
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

export type TargetedAgentType = 'find_handles' | 'scrape_posts' | 'extract_phones' | 'discover_bem' | 'find_rectors'

export async function triggerAgentTargeted(
  agentType: TargetedAgentType,
  universityIds: number[],
): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post<{ status: string; message: string }>(
    '/pipeline/run-agent-targeted',
    { agent_type: agentType, university_ids: universityIds },
  )
  return data
}
