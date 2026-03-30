import { apiClient } from './client'
import type { University, IgContact, IgPost, RelatedIg } from '../lib/types'

interface UniversityParams {
  status?: string
  search?: string
  province?: string
  has_ig?: boolean
  enabled?: boolean
  limit?: number
  offset?: number
  sort_by?: string
  order?: string
}

export interface PaginatedUniversities {
  data: University[]
  total: number
}

export async function getUniversities(params?: UniversityParams): Promise<PaginatedUniversities> {
  const { data } = await apiClient.get<PaginatedUniversities>('/universities', { params })
  return data
}

export interface UniversityWithEmail {
  id: number
  name: string
  province: string | null
  email: string
  website: string | null
}

export interface PaginatedUniversitiesWithEmail {
  data: UniversityWithEmail[]
  total: number
  limit: number
  offset: number
}

export async function getUniversitiesWithEmails(
  province?: string,
  search?: string,
  limit: number = 100,
  offset: number = 0
): Promise<PaginatedUniversitiesWithEmail> {
  const params: Record<string, string | number> = { limit, offset }
  if (province) params.province = province
  if (search) params.search = search
  const { data } = await apiClient.get<PaginatedUniversitiesWithEmail>('/universities/with-emails', { params })
  return data
}

export async function getProvinces(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>('/universities/provinces')
  return data
}

export async function toggleUniversityEnabled(
  id: number,
  enabled: boolean
): Promise<{ id: number; enabled: boolean }> {
  const { data } = await apiClient.patch<{ id: number; enabled: boolean }>(
    `/universities/${id}/toggle-enabled`,
    null,
    { params: { enabled } }
  )
  return data
}

export async function bulkToggleUniversities(
  ids: number[],
  enabled: boolean
): Promise<{ updated: number; enabled: boolean }> {
  const { data } = await apiClient.patch<{ updated: number; enabled: boolean }>(
    '/universities/bulk-toggle',
    { ids, enabled }
  )
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

export async function getUniversityRelatedIgs(id: number): Promise<RelatedIg[]> {
  const { data } = await apiClient.get<RelatedIg[]>(`/universities/${id}/related-igs`)
  return data
}

export async function toggleContactContacted(
  contactId: number,
  contacted: boolean
): Promise<{ success: boolean; id: number; manual_contacted: boolean }> {
  const { data } = await apiClient.patch<{ success: boolean; id: number; manual_contacted: boolean }>(
    `/contacts/${contactId}/toggle-contacted`,
    null,
    { params: { contacted } }
  )
  return data
}

export interface BulkMatchedContact {
  id: number
  university_id: number
  phone_number: string
  contact_name: string | null
  has_person_name: boolean
  manual_contacted: boolean
  conversation_state: string | null
  conversation_id: number | null
  university_name: string | null
  created_at: string
}

export async function bulkMatchContacts(
  phoneNumbers: string[]
): Promise<{ matched: BulkMatchedContact[]; not_matched: string[] }> {
  const { data } = await apiClient.post('/contacts/bulk-match', { phone_numbers: phoneNumbers })
  return data
}

export async function bulkUpdateContactStatus(
  contactIds: number[],
  contacted: boolean
): Promise<{ success: boolean; updated: number }> {
  const { data } = await apiClient.post('/contacts/bulk-update-status', {
    contact_ids: contactIds,
    contacted,
  })
  return data
}

export async function resetUniversityIgHandle(
  id: number
): Promise<{ success: boolean; id: number; status: string }> {
  const { data } = await apiClient.delete<{ success: boolean; id: number; status: string }>(
    `/universities/${id}/ig-handle`
  )
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

export function exportUniversitiesExcel(params?: UniversityParams & { ids?: number[] }): void {
  /**
   * Export contacts (university name, contact name, phone) to Excel.
   * Pass ids to export specific universities, or use filters to export by criteria.
   */
  const query = new URLSearchParams()
  if (params?.ids && params.ids.length > 0) {
    query.set('ids', params.ids.join(','))
  } else {
    if (params?.search) query.set('search', params.search)
    if (params?.status) query.set('status', params.status)
    if (params?.province) query.set('province', params.province)
    if (params?.has_ig !== undefined) query.set('has_ig', String(params.has_ig))
    if (params?.enabled !== undefined) query.set('enabled', String(params.enabled))
  }
  const qs = query.toString()
  window.open(`/api/universities/export-excel${qs ? '?' + qs : ''}`, '_blank')
}

export interface MatchedUniversity {
  id: number
  name: string
  province: string | null
  status: string
  ig_handle: string | null
  matched_query: string
  match_type: 'exact' | 'partial'
}

export async function matchUniversityNames(names: string[]): Promise<{
  matches: MatchedUniversity[]
  total_queries: number
  total_matched: number
}> {
  const { data } = await apiClient.post('/universities/match-names', { names })
  return data
}
