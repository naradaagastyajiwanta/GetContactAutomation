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

export async function addSelectedRecipients(id: number, universityIds: number[]): Promise<{ success: boolean; recipients_added: number }> {
  const response = await apiClient.post(`/email-blast/campaigns/${id}/recipients/add`, { university_ids: universityIds })
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

export interface LetterConfig {
  format_template: string
  last_number: number
}

export async function getLetterConfig(): Promise<{ success: boolean } & LetterConfig> {
  const response = await apiClient.get('/email-blast/letter-config')
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
