import { apiClient } from './client'

// ── Types ─────────────────────────────────────────────────────────────────

export type ClientType =
  | 'lembaga_negara'
  | 'kementerian'
  | 'bumn'
  | 'swasta_besar'
  | 'asosiasi'
  | 'lpk'
  | 'lkp'

export const CLIENT_TYPE_LABELS: Record<ClientType, string> = {
  lembaga_negara: 'Lembaga Negara',
  kementerian: 'Kementerian',
  bumn: 'BUMN',
  swasta_besar: 'Perusahaan Swasta Besar',
  asosiasi: 'Asosiasi',
  lpk: 'LPK',
  lkp: 'LKP',
}

export type GroupStatus = 'draft' | 'searching' | 'done'

export type ContactType = 'wa_phone' | 'email' | 'office_phone' | 'pic_name' | 'pic_title'

export type ClientSearchStatus = 'pending' | 'searching' | 'found' | 'not_found' | 'error'

export interface MarketingGroup {
  id: number
  name: string
  client_type: ClientType
  total_clients: number
  found_count: number
  not_found_count: number
  pending_count: number
  status: GroupStatus
  created_at: string
  updated_at: string | null
}

export interface MarketingClient {
  id: number
  group_id: number
  name: string
  search_status: ClientSearchStatus
  created_at: string
  contacts: MarketingContact[]
}

export interface MarketingContact {
  id: number
  client_id: number
  contact_type: ContactType
  value: string | null
  source_url: string | null
  source_type: string | null
  confidence: number | null
  is_approved: boolean
  is_selected: boolean
  edited_value: string | null
  created_at: string
}

export interface GroupStats {
  total: number
  found: number
  not_found: number
  pending: number
  approved: number
}

export interface ImportPreview {
  columns: string[]
  rows: Record<string, string>[]
  total_rows: number
  duplicates: number
}

export interface ImportResult {
  inserted: number
  skipped: number
  duplicates: number
}

export interface HandoffResult {
  success: boolean
  campaign_id?: number
  campaign_type?: 'wa_blast' | 'email_blast'
  message?: string
}

// ── Group API ──────────────────────────────────────────────────────────────

export async function getMarketingGroups(params?: {
  client_type?: ClientType | ''
}): Promise<{ groups: MarketingGroup[]; total: number }> {
  const { data } = await apiClient.get('/marketing/groups', { params })
  return data
}

export async function getMarketingGroup(
  groupId: number
): Promise<{ group: MarketingGroup; stats: GroupStats }> {
  const { data } = await apiClient.get(`/marketing/groups/${groupId}`)
  return data
}

export async function createMarketingGroup(payload: {
  name: string
  client_type: ClientType
}): Promise<{ id: number }> {
  const { data } = await apiClient.post('/marketing/groups', payload)
  return data
}

export async function deleteMarketingGroup(groupId: number): Promise<void> {
  await apiClient.delete(`/marketing/groups/${groupId}`)
}

// ── Client API ─────────────────────────────────────────────────────────────

export async function getMarketingClients(
  groupId: number
): Promise<{ clients: MarketingClient[] }> {
  const { data } = await apiClient.get(`/marketing/groups/${groupId}/clients`)
  return data
}

export async function addMarketingClient(
  groupId: number,
  payload: { name: string }
): Promise<{ id: number }> {
  const { data } = await apiClient.post(`/marketing/groups/${groupId}/clients`, payload)
  return data
}

export async function deleteMarketingClient(clientId: number): Promise<void> {
  await apiClient.delete(`/marketing/clients/${clientId}`)
}

// ── Contact API ────────────────────────────────────────────────────────────

export async function updateMarketingContact(
  contactId: number,
  payload: {
    is_approved?: boolean
    is_selected?: boolean
    edited_value?: string
  }
): Promise<{ contact: MarketingContact }> {
  const { data } = await apiClient.patch(`/marketing/contacts/${contactId}`, payload)
  return data
}

export async function bulkApproveGroupContacts(
  groupId: number
): Promise<{ approved: number }> {
  const { data } = await apiClient.post(`/marketing/groups/${groupId}/approve-all`)
  return data
}

// ── Import / Export API ────────────────────────────────────────────────────

export async function importPreview(
  groupId: number,
  file: File
): Promise<ImportPreview> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post(
    `/marketing/groups/${groupId}/import/preview`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
  return data
}

export async function importCommit(
  groupId: number
): Promise<ImportResult> {
  const { data } = await apiClient.post(`/marketing/groups/${groupId}/import/commit`)
  return data
}

export async function exportGroupClients(groupId: number): Promise<Blob> {
  const { data } = await apiClient.get(`/marketing/groups/${groupId}/export`, {
    responseType: 'blob',
  })
  return data
}

// ── Search API ─────────────────────────────────────────────────────────────

export interface SearchStatus {
  status: GroupStatus
  progress: number
  total: number
  found: number
  not_found: number
  error_message?: string
}

export async function startGroupSearch(groupId: number): Promise<void> {
  await apiClient.post(`/marketing/groups/${groupId}/search/start`)
}

export async function getSearchStatus(groupId: number): Promise<SearchStatus> {
  const { data } = await apiClient.get(`/marketing/groups/${groupId}/search/status`)
  return data
}

// ── Handoff API ─────────────────────────────────────────────────────────────

export async function handoffGroup(
  groupId: number,
  handoffType: 'wa_blast' | 'email_blast'
): Promise<HandoffResult> {
  const { data } = await apiClient.post(`/marketing/groups/${groupId}/handoff`, {
    handoff_type: handoffType,
  })
  return data
}
