import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query'
import { useWebSocketContext } from '../context/WebSocketContext'
import {
  createEmailCampaign,
  listEmailCampaigns,
  getEmailBlastQuota,
  type EmailBlastQuota,
  getEmailCampaign,
  addAllRecipientsToCampaign,
  addSelectedRecipients,
  startEmailCampaign,
  pauseEmailCampaign,
  cancelEmailCampaign,
  getEmailRecipients,
  deleteEmailRecipient,
  testSmtpConnection,
  updateEmailCampaign,
  uploadAttachment,
  getAttachment,
  getLetterConfig,
  updateLetterConfig,
  getSentEmails,
  getSentEmail,
  getInboxEmails,
  getAllInboxEmails,
  getAllSentEmails,
  getSentFolderEmails,
  sendTestEmail,
  getLetterHistory,
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
    staleTime: 30_000,
  })
}

export function useEmailBlastCampaign(id: number) {
  const { connected } = useWebSocketContext()

  return useQuery<{ success: boolean; campaign: EmailBlastCampaign }>({
    queryKey: ['email-blast-campaign', id],
    queryFn: () => getEmailCampaign(id),
    enabled: !!id,
    refetchInterval: (query) => {
      if (connected) {
        return false
      }

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
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaign'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-recipients'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-quota'] })
    },
  })
}

export function usePauseEmailCampaign() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => pauseEmailCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaign'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-recipients'] })
    },
  })
}

export function useCancelEmailCampaign() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => cancelEmailCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaign'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-recipients'] })
    },
  })
}

export function useAddAllRecipients() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => addAllRecipientsToCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaign'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-recipients'] })
    },
  })
}

export function useAddSelectedRecipients() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, universityIds, groupIds }: { id: number; universityIds: number[]; groupIds?: number[] }) =>
      addSelectedRecipients(id, universityIds, groupIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaign'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-recipients'] })
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
      queryClient.invalidateQueries({ queryKey: ['email-blast-attachment'] })
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

export function useSentEmails(campaignId: number, status?: string) {
  const { connected } = useWebSocketContext()

  return useQuery<{ success: boolean; emails: any[]; total: number }>({
    queryKey: ['email-blast-sent-emails', campaignId, status],
    queryFn: () => getSentEmails(campaignId, status),
    enabled: !!campaignId,
    staleTime: 30_000,
    refetchInterval: connected ? false : 60_000,
  })
}

export function useSentEmail(campaignId: number, emailId: number) {
  return useQuery<{ success: boolean; email: any }>({
    queryKey: ['email-blast-sent-email', campaignId, emailId],
    queryFn: () => getSentEmail(campaignId, emailId),
    enabled: !!campaignId && !!emailId,
  })
}

export function useInboxEmails(campaignId: number, limit?: number) {
  const { connected } = useWebSocketContext()

  return useQuery<{ success: boolean; emails: any[]; total: number }>({
    queryKey: ['email-blast-inbox', campaignId, limit],
    queryFn: () => getInboxEmails(campaignId, limit),
    enabled: !!campaignId,
    staleTime: 30_000,
    refetchInterval: connected ? false : 60_000,
  })
}

export function useLetterConfig() {
  return useQuery({
    queryKey: ['email-blast-letter-config'],
    queryFn: () => getLetterConfig(),
  })
}

export function useAllInboxEmails(limit?: number, enabled?: boolean) {
  const { connected } = useWebSocketContext()

  return useQuery<{ success: boolean; emails: any[]; total: number; offset: number; limit: number }>({
    queryKey: ['email-blast-all-inbox', limit],
    queryFn: () => getAllInboxEmails(limit),
    enabled: enabled !== false,
    staleTime: 30_000,
    refetchInterval: enabled !== false && !connected ? 60_000 : false,
  })
}

export function useAllInboxEmailsPaginated(pageSize: number = 50, enabled: boolean = true) {
  const { connected } = useWebSocketContext()

  return useInfiniteQuery({
    queryKey: ['email-blast-all-inbox-paginated'],
    queryFn: async ({ pageParam = 0 }: { pageParam?: number }) => {
      return getAllInboxEmails(pageSize, pageParam ?? 0)
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage: { offset?: number; limit?: number; total?: number }) => {
      const currentOffset = lastPage.offset ?? 0
      const nextOffset = currentOffset + pageSize
      if (nextOffset >= (lastPage.total || 0)) return undefined
      return nextOffset
    },
    enabled,
    staleTime: 30_000,
    refetchInterval: enabled && !connected ? 60_000 : false,
  })
}

export function useAllSentEmailsPaginated(pageSize: number = 50, enabled: boolean = true) {
  const { connected } = useWebSocketContext()

  return useInfiniteQuery({
    queryKey: ['email-blast-all-sent-paginated'],
    queryFn: async ({ pageParam = 0 }: { pageParam?: number }) => {
      return getAllSentEmails(pageSize, pageParam ?? 0)
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage: { offset?: number; limit?: number; total?: number }) => {
      const currentOffset = lastPage.offset ?? 0
      const nextOffset = currentOffset + pageSize
      if (nextOffset >= (lastPage.total || 0)) return undefined
      return nextOffset
    },
    enabled,
    staleTime: 30_000,
    refetchInterval: enabled && !connected ? 60_000 : false,
  })
}

export function useSentFolderEmailsPaginated(pageSize: number = 50, enabled: boolean = true) {
  const { connected } = useWebSocketContext()

  return useInfiniteQuery({
    queryKey: ['email-blast-sent-folder-paginated'],
    queryFn: async ({ pageParam = 0 }: { pageParam?: number }) => {
      return getSentFolderEmails(pageSize, pageParam ?? 0)
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage: { offset?: number; limit?: number; total?: number }) => {
      const currentOffset = lastPage.offset ?? 0
      const nextOffset = currentOffset + pageSize
      if (nextOffset >= (lastPage.total || 0)) return undefined
      return nextOffset
    },
    enabled,
    staleTime: 30_000,
    refetchInterval: enabled && !connected ? 60_000 : false,
  })
}

export function useUpdateLetterConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ format_template, last_number }: { format_template?: string; last_number?: number }) =>
      updateLetterConfig(format_template, last_number),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-letter-config'] })
    },
  })
}

export function useDeleteEmailRecipient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ campaignId, recipientId }: { campaignId: number; recipientId: number }) =>
      deleteEmailRecipient(campaignId, recipientId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-blast-recipients'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaign'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
    },
  })
}

export function useSendTestEmail() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      campaignId,
      toEmail,
      options,
    }: {
      campaignId: number
      toEmail: string
      options?: Parameters<typeof sendTestEmail>[2]
    }) => sendTestEmail(campaignId, toEmail, options),
    onSuccess: () => {
      // Invalidate sent folder cache so new sent email appears
      queryClient.invalidateQueries({ queryKey: ['email-blast-all-sent-paginated'] })
      queryClient.invalidateQueries({ queryKey: ['email-blast-sent-emails'] })
    },
  })
}

export function useLetterHistory(params?: {
  campaign_id?: number
  duplicate_only?: boolean
  search?: string
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ['email-blast-letter-history', params],
    queryFn: () => getLetterHistory(params),
    staleTime: 30_000,
  })
}

export function useEmailBlastQuota() {
  const { connected } = useWebSocketContext()

  return useQuery<EmailBlastQuota>({
    queryKey: ['email-blast-quota'],
    queryFn: getEmailBlastQuota,
    staleTime: 30_000,
    refetchInterval: connected ? false : 60_000,
  })
}
