import { useQuery } from '@tanstack/react-query'
import { getConversations, getConversation } from '../api/conversations'
import { queryKeys } from '../lib/queryKeys'

export function useConversations(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: queryKeys.conversations.list(params),
    queryFn: () =>
      getConversations(params as { state?: string; limit?: number; offset?: number }),
  })
}

export function useConversation(id: number) {
  return useQuery({
    queryKey: queryKeys.conversations.detail(id),
    queryFn: () => getConversation(id),
    enabled: id > 0,
  })
}
