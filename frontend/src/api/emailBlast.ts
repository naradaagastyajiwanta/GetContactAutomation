import { apiClient } from './client'
import axios from 'axios'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EmailBlastCampaign {
  id: number
  name: string
  subject: string
  template_message: string
  from_email: string
  from_name: string
  delay_between_ms: number
  status: 'draft' | 'running' | 'paused' | 'completed' | 'cancelled'
  total_recipients: number
  sent_count: number
  failed_count: number
  invalid_count: number
  created_by_dms_user_id?: number | null
  created_by_email?: string | null
  created_by_name?: string | null
  started_by_dms_user_id?: number | null
  started_by_email?: string | null
  started_by_name?: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  revision?: string
}

export interface EmailBlastQuota {
  date: string
  sent_today: number
  daily_limit: number
  remaining: number
  is_exhausted: boolean
}

export interface ManagedSMTPAccount {
  id: number
  host: string
  port: number
  user: string
  password: string
  use_ssl: boolean
  from_name: string
  enabled: boolean
  notes: string
  health_status?: 'unknown' | 'healthy' | 'error' | 'checking'
  health_message?: string
  last_checked_at?: string | null
  last_healthy_at?: string | null
  last_error_at?: string | null
  is_current?: boolean
  connected?: boolean
  email_count?: number
  daily_sent_count?: number
  daily_limit?: number | null
  cooldown_remaining_seconds?: number
  skip_reason?: string | null
  created_at: string
  updated_at: string
}

export interface ManagedSMTPAccountPayload {
  host: string
  port: number
  user: string
  password: string
  use_ssl: boolean
  from_name: string
  enabled?: boolean
  notes?: string
}

export interface EmailBlastRecipient {
  id: number
  campaign_id: number
  university_id: number | null
  email: string
  university_name: string | null
  rendered_subject: string | null
  rendered_message: string | null
  status: 'pending' | 'sent' | 'failed' | 'invalid'
  error_message: string | null
  sent_at: string | null
  created_at: string
}

export interface UploadExternalRecipientsResponse {
  success: boolean
  recipients_added: number
  processed_rows: number
  duplicate_or_existing: number
  skipped_missing_email: number
  skipped_invalid_format: number
  columns: string[]
  message: string
}

export interface ExternalRecipientImportRow {
  email: string
  name?: string
}

export interface CreateEmailCampaignRequest {
  name: string
  subject: string
  template_message: string
  from_email?: string
  from_name?: string
  delay_between_ms?: number
}

export interface StartEmailCampaignRequest {
  campaign_id: number
  max_recipients?: number
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

export async function createEmailCampaign(data: CreateEmailCampaignRequest): Promise<{ success: boolean; campaign_id: number }> {
  const response = await apiClient.post('/email-blast/campaigns', data)
  return response.data
}

export async function listEmailCampaigns(status?: string): Promise<{ success: boolean; campaigns: EmailBlastCampaign[] }> {
  const params = status ? { status } : {}
  const response = await apiClient.get('/email-blast/campaigns', { params })
  return response.data
}

export async function getEmailCampaign(id: number): Promise<{ success: boolean; campaign: EmailBlastCampaign }> {
  const response = await apiClient.get(`/email-blast/campaigns/${id}`)
  return response.data
}

export async function addAllRecipientsToCampaign(id: number, provinces?: string[]): Promise<{ success: boolean; recipients_added: number }> {
  const response = await apiClient.post(`/email-blast/campaigns/${id}/recipients/add-all`, { provinces })
  return response.data
}

export async function addSelectedRecipients(
  id: number,
  universityIds: number[],
  groupIds?: number[]
): Promise<{ success: boolean; recipients_added: number }> {
  const body: Record<string, unknown> = { university_ids: universityIds }
  if (groupIds && groupIds.length > 0) {
    body.group_ids = groupIds
  }
  const response = await apiClient.post(`/email-blast/campaigns/${id}/recipients/add`, body)
  return response.data
}

export async function uploadExternalRecipients(
  campaignId: number,
  rows: ExternalRecipientImportRow[],
): Promise<UploadExternalRecipientsResponse> {
  const response = await apiClient.post(`/email-blast/campaigns/${campaignId}/recipients/import`, {
    rows,
  })
  return response.data
}

export async function startEmailCampaign(data: StartEmailCampaignRequest): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post(`/email-blast/campaigns/${data.campaign_id}/start`, data)
  return response.data
}

export async function pauseEmailCampaign(id: number): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post(`/email-blast/campaigns/${id}/pause`)
  return response.data
}

export async function cancelEmailCampaign(id: number): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post(`/email-blast/campaigns/${id}/cancel`)
  return response.data
}

export async function getEmailRecipients(id: number, status?: string): Promise<{ success: boolean; recipients: EmailBlastRecipient[] }> {
  const params = status ? { status } : {}
  const response = await apiClient.get(`/email-blast/campaigns/${id}/recipients`, { params })
  return response.data
}

export async function deleteEmailRecipient(campaignId: number, recipientId: number): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.delete(`/email-blast/campaigns/${campaignId}/recipients/${recipientId}`)
  return response.data
}

export async function testSmtpConnection(): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post('/email-blast/test-smtp')
  return response.data
}

export async function getManagedSMTPAccounts(): Promise<{ accounts: ManagedSMTPAccount[] }> {
  const response = await apiClient.get('/email-smtp-accounts')
  return response.data
}

export async function createManagedSMTPAccount(payload: ManagedSMTPAccountPayload): Promise<{ status: string; account: ManagedSMTPAccount }> {
  const response = await apiClient.post('/email-smtp-accounts', payload)
  return response.data
}

export async function updateManagedSMTPAccount(
  id: number,
  payload: Partial<ManagedSMTPAccountPayload> & { enabled?: boolean; notes?: string }
): Promise<{ status: string; account: ManagedSMTPAccount }> {
  const response = await apiClient.put(`/email-smtp-accounts/${id}`, payload)
  return response.data
}

export async function deleteManagedSMTPAccount(id: number): Promise<{ status: string }> {
  const response = await apiClient.delete(`/email-smtp-accounts/${id}`)
  return response.data
}

export async function testManagedSMTPAccount(id: number): Promise<{ success: boolean; message: string; account?: ManagedSMTPAccount | null }> {
  const response = await apiClient.post(`/email-smtp-accounts/${id}/test`)
  return response.data
}

export async function checkAllManagedSMTPAccounts(): Promise<{ success: boolean; checked: number; healthy: number; failed: number }> {
  const response = await apiClient.post('/email-smtp-accounts/check-all')
  return response.data
}

export interface UpdateEmailCampaignRequest {
  name?: string
  subject?: string
  template_message?: string
  delay_between_ms?: number
  expected_revision?: string
}

export async function updateEmailCampaign(id: number, data: UpdateEmailCampaignRequest): Promise<{ success: boolean; campaign: EmailBlastCampaign }> {
  const response = await apiClient.patch(`/email-blast/campaigns/${id}`, data)
  return response.data
}

export interface AttachmentInfo {
  filename: string | null
  variables: Record<string, string>
  detected_variables?: string[]
}

export async function uploadAttachment(
  campaignId: number,
  file: File,
  variables: Record<string, string> = {}
): Promise<{ success: boolean; filename: string; variables: Record<string, string> }> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('variables', JSON.stringify(variables))

  // Use fresh axios instance without default Content-Type.
  // apiClient defaults to Content-Type: application/json which breaks multipart parsing.
  const uploadClient = axios.create({ baseURL: '/api' })
  const response = await uploadClient.post(`/email-blast/campaigns/${campaignId}/attachment`, formData)
  return response.data
}

export async function getAttachment(campaignId: number): Promise<{ success: boolean } & AttachmentInfo> {
  const response = await apiClient.get(`/email-blast/campaigns/${campaignId}/attachment`)
  return response.data
}

// Sent Emails (Inbox)
export interface SentEmail {
  id: number
  email: string
  university_name: string | null
  from_email?: string | null
  from_name?: string | null
  subject: string | null
  body: string | null
  status: string
  sent_at: string | null
  error_message: string | null
  campaign_name?: string | null
  source?: string  // 'campaign' or 'test'
  started_by_email?: string | null
  started_by_name?: string | null
  created_by_email?: string | null
  created_by_name?: string | null
}

export async function getSentEmails(campaignId: number, status?: string): Promise<{ success: boolean; emails: SentEmail[]; total: number }> {
  const params = status ? `?status=${status}` : ''
  const response = await apiClient.get(`/email-blast/campaigns/${campaignId}/sent-emails${params}`)
  return response.data
}

export async function getSentEmail(campaignId: number, emailId: number): Promise<{ success: boolean; email: SentEmail }> {
  const response = await apiClient.get(`/email-blast/campaigns/${campaignId}/sent-emails/${emailId}`)
  return response.data
}

// Inbound Emails (Replies)
export type EmailCacheRowId = string

export interface InboundEmail {
  id: EmailCacheRowId
  mailbox_email?: string
  uid?: number
  message_id: string
  in_reply_to: string
  from_email: string
  from_name: string
  to_email: string
  subject: string
  body: string
  date: string
  campaign_id?: number
}

export async function getInboxEmails(campaignId: number, limit?: number): Promise<{ success: boolean; emails: InboundEmail[]; total: number }> {
  const params = limit ? `?limit=${limit}` : ''
  const response = await apiClient.get(`/email-blast/campaigns/${campaignId}/inbox${params}`)
  return response.data
}

export async function getAllInboxEmails(
  limit?: number,
  offset?: number
): Promise<{ success: boolean; emails: InboundEmail[]; total: number; offset: number; limit: number }> {
  const params = new URLSearchParams()
  if (limit !== undefined) params.set('limit', String(limit))
  if (offset !== undefined) params.set('offset', String(offset))
  const qs = params.toString() ? `?${params.toString()}` : ''
  const response = await apiClient.get(`/email-blast/inbox${qs}`)
  return response.data
}

export async function getAllSentEmails(
  limit?: number,
  offset?: number,
  status?: string
): Promise<{ success: boolean; emails: SentEmail[]; total: number; offset: number; limit: number }> {
  const params = new URLSearchParams()
  if (limit !== undefined) params.set('limit', String(limit))
  if (offset !== undefined) params.set('offset', String(offset))
  if (status) params.set('status', status)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const response = await apiClient.get(`/email-blast/sent-emails${qs}`)
  return response.data
}

export interface SentFolderEmail {
  id: EmailCacheRowId
  mailbox_email?: string
  uid?: number
  message_id: string
  from_email: string
  from_name: string
  to_email: string
  subject: string
  body: string
  date: string
}

export async function getSentFolderEmails(
  limit?: number,
  offset?: number
): Promise<{ success: boolean; emails: SentFolderEmail[]; total: number; offset: number; limit: number }> {
  const params = new URLSearchParams()
  if (limit !== undefined) params.set('limit', String(limit))
  if (offset !== undefined) params.set('offset', String(offset))
  const qs = params.toString() ? `?${params.toString()}` : ''
  const response = await apiClient.get(`/email-blast/sent-folder${qs}`)
  return response.data
}

export interface LetterConfig {
  format_template: string
  last_number: number
}

export async function getLetterConfig(): Promise<{ success: boolean } & LetterConfig> {
  const response = await apiClient.get('/email-blast/letter-config')
  return response.data
}

export async function sendTestEmail(
  campaignId: number,
  toEmail: string,
  options?: {
    subject?: string
    body?: string
    fromEmail?: string
    fromName?: string
    attachmentFilename?: string | null
    customVars?: Record<string, string>
  }
): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post(`/email-blast/campaigns/${campaignId}/test-email`, {
    to_email: toEmail,
    subject: options?.subject,
    body: options?.body,
    from_email: options?.fromEmail,
    from_name: options?.fromName,
    attachment_filename: options?.attachmentFilename,
    custom_vars: options?.customVars,
  })
  return response.data
}

export async function updateLetterConfig(
  format_template?: string,
  last_number?: number
): Promise<{ success: boolean } & LetterConfig> {
  const response = await apiClient.post('/email-blast/letter-config', {
    format_template,
    last_number,
  })
  return response.data
}

// Letter History
export interface LetterHistoryItem {
  id: number
  campaign_id: number
  campaign_name: string
  letter_number: string
  university_name: string | null
  email: string
  sent_at: string | null
  started_by_email?: string | null
  started_by_name?: string | null
  created_by_email?: string | null
  created_by_name?: string | null
  is_duplicate: boolean
}

export interface LetterHistoryResponse {
  success: boolean
  items: LetterHistoryItem[]
  total: number
  duplicate_count: number
  limit: number
  offset: number
}

export async function getLetterHistory(params?: {
  campaign_id?: number
  duplicate_only?: boolean
  search?: string
  limit?: number
  offset?: number
}): Promise<LetterHistoryResponse> {
  const searchParams = new URLSearchParams()
  if (params?.campaign_id) searchParams.set('campaign_id', String(params.campaign_id))
  if (params?.duplicate_only) searchParams.set('duplicate_only', 'true')
  if (params?.search) searchParams.set('search', params.search)
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset))
  const qs = searchParams.toString() ? `?${searchParams.toString()}` : ''
  const response = await apiClient.get(`/email-blast/letter-history${qs}`)
  return response.data
}

export async function getEmailBlastQuota(): Promise<EmailBlastQuota> {
  const response = await apiClient.get('/email-blast/quota')
  return response.data
}
