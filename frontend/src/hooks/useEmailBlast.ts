import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createEmailCampaign,
  listEmailCampaigns,
  getEmailCampaign,
  addAllRecipientsToCampaign,
  addSelectedRecipients,
  startEmailCampaign,
  pauseEmailCampaign,
  cancelEmailCampaign,
  getEmailRecipients,
  testSmtpConnection,
  updateEmailCampaign,
  uploadAttachment,
  getAttachment,
  type EmailBlastCampaign,
  type EmailBlastRecipient,
  type CreateEmailCampaignRequest,
  type StartEmailCampaignRequest,
  type UpdateEmailCampaignRequest,
} from '../api/emailBlast'

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useEmailBlastCampaigns(status?: string) {
  return useQuery<{ success: boolean; campaigns: EmailBlastCampaign[] }>({
    queryKey: ['email-blast-campaigns', status],
    queryFn: () => listEmailCampaigns(status),
    refetchInterval: 5_000,
  })
}

export function useEmailBlastCampaign(id: number) {
  return useQuery<{ success: boolean; campaign: EmailBlastCampaign }>({
    queryKey: ['email-blast-campaign', id],
    queryFn: () => getEmailCampaign(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const campaign = query.state.data
      return campaign?.campaign?.status === 'running' ? 2_000 : 10_000
    },
  })
}

export function useEmailBlastRecipients(id: number, status?: string) {
  return useQuery<{ success: boolean; recipients: EmailBlastRecipient[] }>({
    queryKey: ['email-blast-recipients', id, status],
    queryFn: () => getEmailRecipients(id, status),
    enabled: !!id,
  })
}

export function useCreateEmailCampaign() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateEmailCampaignRequest) => createEmailCampaign(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
    },
  })
}

export function useStartEmailCampaign() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: StartEmailCampaignRequest) => startEmailCampaign(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-recipients'] })
    },
  })
}

export function usePauseEmailCampaign() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => pauseEmailCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
    },
  })
}

export function useCancelEmailCampaign() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => cancelEmailCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
    },
  })
}

export function useAddAllRecipients() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => addAllRecipientsToCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
    },
  })
}

export function useAddSelectedRecipients() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, universityIds }: { id: number; universityIds: number[] }) =>
      addSelectedRecipients(id, universityIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
    },
  })
}

export function useTestSmtp() {
  return useMutation({
    mutationFn: () => testSmtpConnection(),
  })
}

export function useUpdateEmailCampaign() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateEmailCampaignRequest }) =>
      updateEmailCampaign(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaign'] })
    },
  })
}

export function useUploadAttachment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ campaignId, file, variables }: { campaignId: number; file: File; variables: Record<string, string> }) =>
      uploadAttachment(campaignId, file, variables),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaign'] })
    },
  })
}

export function useCampaignAttachment(campaignId: number) {
  return useQuery({
    queryKey: ['email-blast-attachment', campaignId],
    queryFn: () => getAttachment(campaignId),
    enabled: !!campaignId,
  })
}
