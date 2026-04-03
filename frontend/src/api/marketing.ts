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

export type ContactType = 'website' | 'wa_phone' | 'email' | 'office_phone' | 'pic_name' | 'pic_title'

export type ClientSearchStatus = 'pending' | 'searching' | 'found' | 'not_found' | 'error'
export type InstagramPostScrapeStatus = 'scraping' | 'success' | 'empty' | 'failed' | 'skipped' | 'audit_only' | 'not_found'

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
  error_message?: string | null
  ig_handle?: string | null
  ig_profile_url?: string | null
  ig_last_scraped_at?: string | null
  ig_post_scrape_status?: InstagramPostScrapeStatus | null
  ig_post_scrape_error?: string | null
  ig_post_scrape_last_attempt_at?: string | null
  created_at: string
  ig_candidates: MarketingInstagramCandidate[]
  ig_posts: MarketingInstagramPost[]
  contacts: MarketingContact[]
}

export interface RetryInstagramScrapeResult {
  success: boolean
  client_id: number
  status: InstagramPostScrapeStatus
  handles: string[]
  posts: number
  contacts_added: number
  message: string
}

export interface RetryInstagramContactExtractionResult {
  success: boolean
  client_id: number
  posts: number
  contacts_added: number
  message: string
}

export interface RetryMarketingSearchResult {
  success: boolean
  client_id: number
  group_id: number
  status: 'queued'
  message: string
}

export interface MarketingInstagramCandidate {
  id: number
  client_id: number
  handle: string
  profile_url: string | null
  source: string | null
  title: string | null
  snippet: string | null
  full_name: string | null
  bio: string | null
  external_url: string | null
  external_domain: string | null
  is_verified: boolean
  base_score: number
  affinity_score: number
  profile_score: number
  final_score: number
  llm_is_correct: boolean | null
  llm_confidence: number
  llm_reason: string | null
  rank_order: number | null
  is_primary: boolean
  is_selected: boolean
  created_at: string
}

export interface MarketingInstagramPost {
  id: number
  client_id: number
  ig_handle: string | null
  post_url: string
  image_url: string | null
  caption: string | null
  post_timestamp: string | null
  source: string | null
  phone_extracted: boolean
  phones_found: number
  created_at: string
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
  error_count: number
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
  // Backend returns {success, groups, total} — strip success wrapper
  return { groups: data.groups, total: data.total }
}

export async function getMarketingGroup(
  groupId: number
): Promise<{ group: MarketingGroup; stats: GroupStats }> {
  const { data } = await apiClient.get(`/marketing/groups/${groupId}`)
  // Backend returns {success, group, stats} — strip success wrapper
  return { group: data.group, stats: data.stats }
}

export async function createMarketingGroup(payload: {
  name: string
  client_type: ClientType
}): Promise<{ id: number }> {
  const { data } = await apiClient.post('/marketing/groups', payload)
  // Backend returns {success, group: {id, name, ...}} — extract id
  return { id: data.group.id }
}

export async function deleteMarketingGroup(groupId: number): Promise<void> {
  await apiClient.delete(`/marketing/groups/${groupId}`)
}

// ── Client API ─────────────────────────────────────────────────────────────

export async function getMarketingClients(
  groupId: number
): Promise<{ clients: MarketingClient[] }> {
  const { data } = await apiClient.get(`/marketing/groups/${groupId}/clients`)
  // Backend returns {success, clients} — strip success wrapper
  return { clients: data.clients }
}

export async function addMarketingClient(
  groupId: number,
  payload: { name: string }
): Promise<{ id: number }> {
  const { data } = await apiClient.post(`/marketing/groups/${groupId}/clients`, payload)
  // Backend returns {success, client: {id, ...}} — extract id
  return { id: data.client.id }
}

export async function deleteMarketingClient(clientId: number): Promise<void> {
  await apiClient.delete(`/marketing/clients/${clientId}`)
}

export async function retryMarketingClientInstagramScrape(
  clientId: number
): Promise<RetryInstagramScrapeResult> {
  const { data } = await apiClient.post(`/marketing/clients/${clientId}/instagram/retry`)
  return data
}

export async function retryMarketingClientInstagramContactExtraction(
  clientId: number
): Promise<RetryInstagramContactExtractionResult> {
  const { data } = await apiClient.post(`/marketing/clients/${clientId}/instagram/contacts/retry`)
  return data
}

export async function retryMarketingClientSearch(
  clientId: number
): Promise<RetryMarketingSearchResult> {
  const { data } = await apiClient.post(`/marketing/clients/${clientId}/search/retry`)
  return data
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
  // Backend returns {success} only — fetch updated contact after patch
  await apiClient.patch(`/marketing/contacts/${contactId}`, payload)
  // Return payload as optimistic contact (id is known)
  return { contact: { id: contactId, ...payload } as unknown as MarketingContact }
}

export async function bulkApproveGroupContacts(
  groupId: number
): Promise<{ approved: number }> {
  const { data } = await apiClient.post(`/marketing/groups/${groupId}/approve-all`)
  // Backend returns {success, approved} — strip success wrapper
  return { approved: data.approved }
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
  // Backend returns {detected_columns, preview, total_rows, duplicates}
  // Map to frontend's ImportPreview interface {columns, rows, total_rows, duplicates}
  return {
    columns: data.detected_columns ?? [],
    rows: data.preview ?? [],
    total_rows: data.total_rows ?? 0,
    duplicates: data.duplicates ?? 0,
  }
}

export async function importCommit(
  groupId: number,
  file: File
): Promise<ImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post(
    `/marketing/groups/${groupId}/import/commit`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
  // Backend returns {success, inserted, skipped_empty, duplicates}
  // Map skipped_empty → skipped for frontend interface
  return {
    inserted: data.inserted,
    skipped: data.skipped_empty,
    duplicates: data.duplicates,
  }
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
  pending: number
  searching: number
  error_message?: string
}

export async function startGroupSearch(groupId: number): Promise<void> {
  await apiClient.post(`/marketing/groups/${groupId}/search/start`)
}

export async function getSearchStatus(groupId: number): Promise<SearchStatus> {
  const { data } = await apiClient.get(`/marketing/groups/${groupId}/search/status`)
  const stats = data.stats
  // Backend returns {success, stats: {total, pending, searching, found, not_found, error_count, approved, errors}}
  // Map to frontend SearchStatus interface
  return {
    status: (stats.found + stats.not_found + stats.error_count > 0 && stats.pending + stats.searching === 0)
      ? 'done' as GroupStatus
      : 'searching' as GroupStatus,
    progress: (stats.total ?? 0) - (stats.pending ?? 0) - (stats.searching ?? 0),
    total: stats.total ?? 0,
    found: stats.found ?? 0,
    not_found: stats.not_found ?? 0,
    pending: stats.pending ?? 0,
    searching: stats.searching ?? 0,
    error_message: (stats.errors ?? [])[0]?.message,
  }
}

// ── Handoff API ─────────────────────────────────────────────────────────────

export async function handoffGroup(
  groupId: number,
  handoffType: 'wa_blast' | 'email_blast'
): Promise<HandoffResult> {
  const { data } = await apiClient.post(`/marketing/groups/${groupId}/handoff`, {
    handoff_type: handoffType,
  })
  // Backend returns {success, campaign_id, wa_count, email_count, handoff_id, message}
  // Map to HandoffResult interface
  return {
    success: data.success,
    campaign_id: data.campaign_id,
    campaign_type: handoffType,
    message: data.message,
  }
}
