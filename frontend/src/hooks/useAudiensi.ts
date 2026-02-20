import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  getAudiensiConversations,
  getAudiensiQueue,
  getAudiensiConversation,
  getAudiensiStats,
  approveAudiensi,
  rejectAudiensi,
  updateRectorName,
  updateInitialMessage,
  regeneratePdf,
  sendZoomLink,
} from '../api/audiensi'
import { queryKeys } from '../lib/queryKeys'

export function useAudiensiConversations(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: queryKeys.audiensi.list(params),
    queryFn: () =>
      getAudiensiConversations(params as { state?: string; limit?: number; offset?: number }),
  })
}

export function useAudiensiQueue() {
  return useQuery({
    queryKey: queryKeys.audiensi.queue,
    queryFn: getAudiensiQueue,
    refetchInterval: 10_000,
  })
}

export function useAudiensiConversation(id: number) {
  return useQuery({
    queryKey: queryKeys.audiensi.detail(id),
    queryFn: () => getAudiensiConversation(id),
    enabled: id > 0,
    refetchInterval: 3_000,
  })
}

export function useAudiensiStats() {
  return useQuery({
    queryKey: queryKeys.audiensi.stats,
    queryFn: getAudiensiStats,
    refetchInterval: 30_000,
  })
}

export function useApproveAudiensi() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => approveAudiensi(id),
    onSuccess: () => {
      toast.success('Audiensi approved and message sent')
      queryClient.invalidateQueries({ queryKey: queryKeys.audiensi.all })
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to approve audiensi')
    },
  })
}

export function useRejectAudiensi() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => rejectAudiensi(id),
    onSuccess: () => {
      toast.success('Audiensi rejected')
      queryClient.invalidateQueries({ queryKey: queryKeys.audiensi.all })
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to reject audiensi')
    },
  })
}

export function useUpdateRectorName() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, rectorName }: { id: number; rectorName: string }) =>
      updateRectorName(id, rectorName),
    onSuccess: (_data, variables) => {
      toast.success('Rector name updated')
      queryClient.invalidateQueries({ queryKey: queryKeys.audiensi.detail(variables.id) })
      queryClient.invalidateQueries({ queryKey: queryKeys.audiensi.queue })
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to update rector name')
    },
  })
}

export function useUpdateInitialMessage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, message }: { id: number; message: string }) =>
      updateInitialMessage(id, message),
    onSuccess: (_data, variables) => {
      toast.success('Initial message updated')
      queryClient.invalidateQueries({ queryKey: queryKeys.audiensi.detail(variables.id) })
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to update message')
    },
  })
}

export function useRegeneratePdf() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => regeneratePdf(id),
    onSuccess: (_data, id) => {
      toast.success('PDF regenerated')
      queryClient.invalidateQueries({ queryKey: queryKeys.audiensi.detail(id) })
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to regenerate PDF')
    },
  })
}

export function useSendZoomLink() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => sendZoomLink(id),
    onSuccess: (_data, id) => {
      toast.success('Zoom link sent')
      queryClient.invalidateQueries({ queryKey: queryKeys.audiensi.detail(id) })
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to send Zoom link')
    },
  })
}
