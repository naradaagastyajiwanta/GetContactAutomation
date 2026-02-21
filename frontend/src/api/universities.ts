import { apiClient } from './client'
import type { University, IgContact, IgPost } from '../lib/types'

interface UniversityParams {
  status?: string
  search?: string
  limit?: number
  offset?: number
}

export async function getUniversities(params?: UniversityParams): Promise<University[]> {
  const { data } = await apiClient.get<University[]>('/universities', { params })
  return data
}

export async function getUniversity(id: number): Promise<University> {
  const { data } = await apiClient.get<University>(`/universities/${id}`)
  return data
}

export async function getUniversityContacts(id: number): Promise<IgContact[]> {
  const { data } = await apiClient.get<IgContact[]>(`/universities/${id}/contacts`)
  return data
}

export async function getUniversityPosts(id: number): Promise<IgPost[]> {
  const { data } = await apiClient.get<IgPost[]>(`/universities/${id}/posts`)
  return data
}

export async function importUniversities(file: File): Promise<{ imported: number; skipped: number }> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post<{ imported: number; skipped: number }>('/universities/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function createUniversities(
  universities: Array<{ name: string; province?: string; website?: string }>
): Promise<{ added: number; skipped: number }> {
  const { data } = await apiClient.post<{ added: number; skipped: number }>('/universities', { universities })
  return data
}
