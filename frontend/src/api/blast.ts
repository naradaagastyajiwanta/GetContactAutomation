import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BlastCampaign {
  id: number;
  name: string;
  template_message: string;
  device_id: string;
  delay_between_ms: number;
  human_delay_min_ms: number;
  human_delay_max_ms: number;
  content_variation_enabled: boolean | number;
  schedule_enabled: boolean | number;
  schedule_timezone: string;
  active_hours_start: number;
  active_hours_end: number;
  peak_hours_start: number;
  peak_hours_end: number;
  lunch_break_start: number;
  lunch_break_end: number;
  weekend_factor: number;
  auto_resume_enabled: boolean | number;
  auto_resume_at: string | null;
  paused_reason: string | null;
  antiban_override: boolean | number | null;
  status: "draft" | "sending" | "paused" | "completed" | "cancelled";
  total_recipients: number;
  sent_count: number;
  failed_count: number;
  created_by_dms_user_id?: number | null;
  created_by_email?: string | null;
  created_by_name?: string | null;
  started_by_dms_user_id?: number | null;
  started_by_email?: string | null;
  started_by_name?: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  paused_at: string | null;
}

export interface BlastRecipient {
  id: number;
  campaign_id: number;
  contact_id: number | null;
  university_id: number | null;
  phone_number: string;
  contact_name: string | null;
  university_name: string | null;
  rendered_message: string | null;
  status: "pending" | "sent" | "failed" | "skipped";
  error_message: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface BlastContact {
  contact_id: number;
  phone_number: string;
  contact_name: string | null;
  has_person_name: boolean | number;
  manual_contacted: boolean | number;
  university_id: number;
  university_name: string | null;
  province: string | null;
  conversation_state: string | null;
}

export interface BlastPreview {
  phone_number: string;
  contact_name: string | null;
  university_name: string | null;
  rendered_message: string;
}

// ---------------------------------------------------------------------------
// Contacts for selection
// ---------------------------------------------------------------------------

export interface BlastContactsParams {
  university_ids?: string;
  search?: string;
  province?: string;
  has_name?: boolean;
  contacted?: boolean;
  has_conversation?: boolean;
  limit?: number;
  offset?: number;
}

export async function getBlastContacts(
  params?: BlastContactsParams,
): Promise<{ data: BlastContact[]; total: number }> {
  const { data } = await apiClient.get("/blast/contacts", { params });
  return data;
}

// ---------------------------------------------------------------------------
// Campaigns CRUD
// ---------------------------------------------------------------------------

export interface PreviouslyBlastedContact {
  contact_id: number;
  phone_number: string;
  contact_name: string | null;
  university_name: string | null;
  campaign_name: string;
  sent_at: string | null;
}

export async function checkPreviouslyBlasted(params: {
  contact_ids?: number[];
  university_ids?: number[];
}): Promise<{
  previously_blasted: PreviouslyBlastedContact[];
  total_contacts: number;
  all_contact_ids: number[];
}> {
  const { data } = await apiClient.post(
    "/blast/check-previously-blasted",
    params,
  );
  return data;
}

export interface CreateCampaignPayload {
  name: string;
  template_message?: string;
  device_id?: string;
  delay_between_ms?: number;
  human_delay_min_ms?: number;
  human_delay_max_ms?: number;
  content_variation_enabled?: boolean;
  schedule_enabled?: boolean;
  schedule_timezone?: string;
  active_hours_start?: number;
  active_hours_end?: number;
  peak_hours_start?: number;
  peak_hours_end?: number;
  lunch_break_start?: number;
  lunch_break_end?: number;
  weekend_factor?: number;
  auto_resume_enabled?: boolean;
}

export async function createCampaign(
  payload: CreateCampaignPayload,
): Promise<{ success: boolean; campaign: BlastCampaign }> {
  const { data } = await apiClient.post("/blast/campaigns", payload);
  return data;
}

export async function listCampaigns(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<{ data: BlastCampaign[]; total: number }> {
  const { data } = await apiClient.get("/blast/campaigns", { params });
  return data;
}

export async function getCampaign(id: number): Promise<BlastCampaign> {
  const { data } = await apiClient.get(`/blast/campaigns/${id}`);
  return data;
}

export async function updateCampaign(
  id: number,
  payload: Partial<CreateCampaignPayload>,
): Promise<{ success: boolean; campaign: BlastCampaign }> {
  const { data } = await apiClient.put(`/blast/campaigns/${id}`, payload);
  return data;
}

export async function deleteCampaign(
  id: number,
): Promise<{ success: boolean }> {
  const { data } = await apiClient.delete(`/blast/campaigns/${id}`);
  return data;
}

// ---------------------------------------------------------------------------
// Recipients
// ---------------------------------------------------------------------------

export async function addRecipients(
  campaignId: number,
  payload: {
    contact_ids?: number[];
    university_ids?: number[];
    recipients?: Array<Record<string, unknown>>;
    group_ids?: number[];
  },
): Promise<{
  success: boolean;
  added: number;
  skipped: number;
  total: number;
}> {
  const { data } = await apiClient.post(
    `/blast/campaigns/${campaignId}/recipients`,
    payload,
  );
  return data;
}

export async function getRecipients(
  campaignId: number,
  params?: { status?: string; limit?: number; offset?: number },
): Promise<{ data: BlastRecipient[]; total: number }> {
  const { data } = await apiClient.get(
    `/blast/campaigns/${campaignId}/recipients`,
    { params },
  );
  return data;
}

export async function removeRecipient(
  campaignId: number,
  recipientId: number,
): Promise<{ success: boolean }> {
  const { data } = await apiClient.delete(
    `/blast/campaigns/${campaignId}/recipients/${recipientId}`,
  );
  return data;
}

export async function clearRecipients(
  campaignId: number,
): Promise<{ success: boolean; removed: number }> {
  const { data } = await apiClient.delete(
    `/blast/campaigns/${campaignId}/recipients`,
  );
  return data;
}

// ---------------------------------------------------------------------------
// Preview & Actions
// ---------------------------------------------------------------------------

export async function previewMessages(
  campaignId: number,
  limit?: number,
): Promise<{ previews: BlastPreview[] }> {
  const { data } = await apiClient.get(
    `/blast/campaigns/${campaignId}/preview`,
    {
      params: { limit },
    },
  );
  return data;
}

export async function startCampaign(
  campaignId: number,
): Promise<{ success: boolean; error?: string }> {
  const { data } = await apiClient.post(`/blast/campaigns/${campaignId}/start`);
  return data;
}

export async function pauseCampaign(
  campaignId: number,
): Promise<{ success: boolean; error?: string }> {
  const { data } = await apiClient.post(`/blast/campaigns/${campaignId}/pause`);
  return data;
}

export async function cancelCampaign(
  campaignId: number,
): Promise<{ success: boolean; error?: string }> {
  const { data } = await apiClient.post(
    `/blast/campaigns/${campaignId}/cancel`,
  );
  return data;
}

export async function forceResumeCampaign(
  campaignId: number,
): Promise<{ success: boolean; antiban_override?: boolean; error?: string }> {
  const { data } = await apiClient.post(
    `/blast/campaigns/${campaignId}/force-resume`,
  );
  return data;
}
