import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  getBlastContacts,
  listCampaigns,
  getCampaign,
  createCampaign,
  updateCampaign,
  deleteCampaign,
  addRecipients,
  getRecipients,
  removeRecipient,
  clearRecipients,
  previewMessages,
  startCampaign,
  pauseCampaign,
  cancelCampaign,
  type BlastContactsParams,
  type CreateCampaignPayload,
} from '../api/blast'

export const blastKeys = {
  all: ['blast'] as const,
  contacts: (params: BlastContactsParams) => ['blast', 'contacts', params] as const,
  campaigns: (params?: Record<string, unknown>) => ['blast', 'campaigns', params] as const,
  campaign: (id: number) => ['blast', 'campaigns', id] as const,
  recipients: (campaignId: number, params?: Record<string, unknown>) =>
    ['blast', 'campaigns', campaignId, 'recipients', params] as const,
  preview: (campaignId: number) => ['blast', 'campaigns', campaignId, 'preview'] as const,
}

// ---------------------------------------------------------------------------
// Contact selection
// ---------------------------------------------------------------------------

export function useBlastContacts(params: BlastContactsParams, enabled = true) {
  return useQuery({
    queryKey: blastKeys.contacts(params),
    queryFn: () => getBlastContacts(params),
    enabled,
  })
}

// ---------------------------------------------------------------------------
// Campaigns
// ---------------------------------------------------------------------------

export function useBlastCampaigns(params?: { status?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: blastKeys.campaigns(params),
    queryFn: () => listCampaigns(params),
    refetchInterval: 5_000, // auto-refresh for progress
  })
}

export function useBlastCampaign(id: number, enabled = true) {
  return useQuery({
    queryKey: blastKeys.campaign(id),
    queryFn: () => getCampaign(id),
    enabled,
    refetchInterval: (query) => {
      const campaign = query.state.data
      return campaign?.status === 'sending' ? 2_000 : 10_000
    },
  })
}

export function useCreateCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateCampaignPayload) => createCampaign(payload),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Campaign created')
        qc.invalidateQueries({ queryKey: blastKeys.campaigns() })
      }
    },
    onError: () => toast.error('Failed to create campaign'),
  })
}

export function useUpdateCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: Partial<CreateCampaignPayload> & { id: number }) =>
      updateCampaign(id, payload),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Campaign updated')
        qc.invalidateQueries({ queryKey: blastKeys.all })
      }
    },
    onError: () => toast.error('Failed to update campaign'),
  })
}

export function useDeleteCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteCampaign(id),
    onSuccess: () => {
      toast.success('Campaign deleted')
      qc.invalidateQueries({ queryKey: blastKeys.campaigns() })
    },
    onError: () => toast.error('Failed to delete campaign'),
  })
}

// ---------------------------------------------------------------------------
// Recipients
// ---------------------------------------------------------------------------

export function useAddRecipients() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      campaignId,
      contact_ids,
      university_ids,
      recipients,
    }: {
      campaignId: number
      contact_ids?: number[]
      university_ids?: number[]
      recipients?: Array<Record<string, unknown>>
    }) => addRecipients(campaignId, { contact_ids, university_ids, recipients }),
    onSuccess: (data) => {
      if (data.success) {
        toast.success(`Added ${data.added} recipients (${data.skipped} skipped)`)
        qc.invalidateQueries({ queryKey: blastKeys.all })
      }
    },
    onError: () => toast.error('Failed to add recipients'),
  })
}

export function useBlastRecipients(
  campaignId: number,
  params?: { status?: string; limit?: number; offset?: number },
  enabled = true
) {
  return useQuery({
    queryKey: blastKeys.recipients(campaignId, params),
    queryFn: () => getRecipients(campaignId, params),
    enabled,
    refetchInterval: 5_000,
  })
}

export function useRemoveRecipient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ campaignId, recipientId }: { campaignId: number; recipientId: number }) =>
      removeRecipient(campaignId, recipientId),
    onSuccess: () => {
      toast.success('Recipient removed')
      qc.invalidateQueries({ queryKey: blastKeys.all })
    },
    onError: () => toast.error('Failed to remove recipient'),
  })
}

export function useClearRecipients() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (campaignId: number) => clearRecipients(campaignId),
    onSuccess: (data) => {
      toast.success(`Removed ${data.removed} recipients`)
      qc.invalidateQueries({ queryKey: blastKeys.all })
    },
    onError: () => toast.error('Failed to clear recipients'),
  })
}

// ---------------------------------------------------------------------------
// Preview & Actions
// ---------------------------------------------------------------------------

export function useBlastPreview(campaignId: number, enabled = true) {
  return useQuery({
    queryKey: blastKeys.preview(campaignId),
    queryFn: () => previewMessages(campaignId, 5),
    enabled,
  })
}

export function useStartCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (campaignId: number) => startCampaign(campaignId),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Blast campaign started!')
        qc.invalidateQueries({ queryKey: blastKeys.all })
      } else {
        toast.error(data.error || 'Failed to start')
      }
    },
    onError: () => toast.error('Failed to start campaign'),
  })
}

export function usePauseCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (campaignId: number) => pauseCampaign(campaignId),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Campaign paused')
        qc.invalidateQueries({ queryKey: blastKeys.all })
      } else {
        toast.error(data.error || 'Failed to pause')
      }
    },
    onError: () => toast.error('Failed to pause campaign'),
  })
}

export function useCancelCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (campaignId: number) => cancelCampaign(campaignId),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Campaign cancelled')
        qc.invalidateQueries({ queryKey: blastKeys.all })
      } else {
        toast.error(data.error || 'Failed to cancel')
      }
    },
    onError: () => toast.error('Failed to cancel campaign'),
  })
}
