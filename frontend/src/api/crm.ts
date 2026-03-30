import { apiClient } from './client'

// ── Types ─────────────────────────────────────────────────────────────────

export interface CrmRequest {
  id: number
  university_id: number | null
  university_name: string | null
  pic_name: string
  pic_title: string | null
  requested_by: string | null
  priority: string
  notes: string | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  run_id: number | null
  created_at: string
  updated_at: string | null
}

export interface CrmProfile {
  id: number
  request_id: number
  university_id: number | null
  full_name: string | null
  title: string | null
  birth_date: string | null
  age: number | null
  origin_region: string | null
  education_history: string | null
  teaching_subjects: string | null
  tenure_years: number | null
  photo_url: string | null
  marital_status: string | null
  spouse_name: string | null
  children_count: number | null
  family_residence: string | null
  campus_problems: string | null
  campus_concerns: string | null
  campus_hopes: string | null
  hobbies: string | null
  favorite_food: string | null
  outside_activities: string | null
  linkedin_url: string | null
  instagram_handle: string | null
  facebook_url: string | null
  twitter_handle: string | null
  other_social: string | null
  home_address: string | null
  phone: string | null
  email: string | null
  overall_confidence: number | null
  fields_found: number | null
  fields_total: number | null
  fields_manual: number | null
  created_at: string
  last_updated: string | null
}

export interface CrmProfileSource {
  id: number
  profile_id: number
  field_name: string
  value: string
  source_type: string
  source_url: string | null
  confidence: number | null
  notes: string | null
  created_at: string
}

export interface CrmStats {
  total_requests: number
  completed: number
  processing: number
  pending: number
  avg_completion_confidence: number
}

export interface CrmRequestCreatePayload {
  pic_name: string
  university_id?: number | null
  university_name?: string | null
  pic_title?: string | null
  requested_by?: string | null
  priority?: string
  notes?: string | null
}

// ── API functions ─────────────────────────────────────────────────────────

export async function getCrmRequests(params?: {
  status?: string
  limit?: number
  offset?: number
}): Promise<{ requests: CrmRequest[]; total: number }> {
  const { data } = await apiClient.get('/crm/requests', { params })
  return data
}

export async function getCrmRequest(requestId: number): Promise<{
  request: CrmRequest
  profile: CrmProfile | null
}> {
  const { data } = await apiClient.get(`/crm/requests/${requestId}`)
  return data
}

export async function createCrmRequest(
  payload: CrmRequestCreatePayload,
): Promise<{ id: number; status: string }> {
  const { data } = await apiClient.post('/crm/requests', payload)
  return data
}

export async function runCrmProfiling(
  requestId: number,
): Promise<{ status: string; request_id: number }> {
  const { data } = await apiClient.post(`/crm/requests/${requestId}/run`)
  return data
}

export async function getCrmProfile(profileId: number): Promise<{
  profile: CrmProfile
  sources: CrmProfileSource[]
}> {
  const { data } = await apiClient.get(`/crm/profiles/${profileId}`)
  return data
}

export async function updateCrmProfile(
  profileId: number,
  fields: Record<string, unknown>,
): Promise<{ profile: CrmProfile }> {
  const { data } = await apiClient.patch(`/crm/profiles/${profileId}`, { fields })
  return data
}

export async function getCrmStats(): Promise<CrmStats> {
  const { data } = await apiClient.get('/crm/stats')
  return data
}
