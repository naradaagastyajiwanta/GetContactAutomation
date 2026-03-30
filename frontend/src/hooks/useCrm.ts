import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getCrmRequests,
  getCrmRequest,
  getCrmProfile,
  createCrmRequest,
  runCrmProfiling,
  getCrmStats,
  type CrmRequestCreatePayload,
} from '../api/crm'

const crmKeys = {
  all: ['crm'] as const,
  requests: (params: Record<string, unknown>) => ['crm', 'requests', params] as const,
  detail: (id: number) => ['crm', 'detail', id] as const,
  profile: (id: number) => ['crm', 'profile', id] as const,
  stats: ['crm', 'stats'] as const,
}

export function useCrmRequests(params?: { status?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: crmKeys.requests(params ?? {}),
    queryFn: () => getCrmRequests(params),
    refetchInterval: 10_000,
  })
}

export function useCrmRequestDetail(requestId: number) {
  return useQuery({
    queryKey: crmKeys.detail(requestId),
    queryFn: () => getCrmRequest(requestId),
    refetchInterval: 5_000,
  })
}

export function useCrmProfileSources(profileId: number | null | undefined) {
  return useQuery({
    queryKey: crmKeys.profile(profileId ?? 0),
    queryFn: () => getCrmProfile(profileId!),
    enabled: !!profileId,
  })
}

export function useCrmStats() {
  return useQuery({
    queryKey: crmKeys.stats,
    queryFn: getCrmStats,
    refetchInterval: 15_000,
  })
}

export function useCreateCrmRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CrmRequestCreatePayload) => createCrmRequest(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: crmKeys.all })
    },
  })
}

export function useRunCrmProfiling() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (requestId: number) => runCrmProfiling(requestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: crmKeys.all })
    },
  })
}
