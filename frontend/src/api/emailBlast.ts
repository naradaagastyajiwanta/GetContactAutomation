import { apiClient } from './client'

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
  created_at: string
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
}

export interface EmailBlastRecipient {
  id: number
  campaign_id: number
  university_id: number | null
  email: string
  university_name: string | null
  rendered_subject: string | null
  rendered_message: string | null
  status: 'pending' | 'sent' | 'failed'
  error_message: string | null
  sent_at: string | null
  created_at: string
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

export interface UpdateEmailCampaignRequest {
  subject?: string
  template_message?: string
  delay_between_ms?: number
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

  const response = await apiClient.post(`/email-blast/campaigns/${campaignId}/attachment`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
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
  subject: string | null
  body: string | null
  status: string
  sent_at: string | null
  error_message: string | null
  campaign_name?: string | null
  source?: string  // 'campaign' or 'test'
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
export interface InboundEmail {
  id: number
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
  id: number
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
