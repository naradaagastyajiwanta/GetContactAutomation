import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getConversations, getConversation, startTestConversation } from '../api/conversations'
import { queryKeys } from '../lib/queryKeys'
import { useWebSocketContext } from '../context/WebSocketContext'

export function useConversations(params: Record<string, unknown> = {}) {
  const { connected } = useWebSocketContext()
  return useQuery({
    queryKey: queryKeys.conversations.list(params),
    queryFn: () =>
      getConversations(params as { state?: string; is_test?: boolean; limit?: number; offset?: number }),
    refetchInterval: connected ? false : 3_000,
  })
}

export function useConversation(id: number) {
  const { connected } = useWebSocketContext()
  return useQuery({
    queryKey: queryKeys.conversations.detail(id),
    queryFn: () => getConversation(id),
    enabled: id > 0,
    refetchInterval: connected ? false : 3_000,
  })
}

export function useStartTestConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ phone, universityName, force }: { phone: string; universityName?: string; force?: boolean }) =>
      startTestConversation(phone, universityName, force),
    onSuccess: (data) => {
      toast.success(`Test conversation started (ID: ${data.id})`)
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.all })
    },
    onError: (error: any) => {
      // Let the component handle 409 (conflict) for custom UX
      if (error?.response?.status === 409) throw error
      const detail = error?.response?.data?.detail
      toast.error(detail || 'Failed to start test conversation')
    },
  })
}
