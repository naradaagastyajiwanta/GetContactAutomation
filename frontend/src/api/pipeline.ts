import { apiClient } from './client'
import type { PipelineStatus } from '../lib/types'

export async function getPipelineStatus(): Promise<PipelineStatus> {
  const { data } = await apiClient.get<PipelineStatus>('/pipeline/status')
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
