import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getLessons, getAnalyses, getLearningStats, triggerReflection } from '../api/learning'
import { queryKeys } from '../lib/queryKeys'

export function useLessons() {
  return useQuery({
    queryKey: queryKeys.learning.lessons,
    queryFn: getLessons,
    refetchInterval: 30_000,
  })
}

export function useAnalyses(limit?: number) {
  return useQuery({
    queryKey: queryKeys.learning.analyses,
    queryFn: () => getAnalyses(limit),
    refetchInterval: 30_000,
  })
}

export function useLearningStats() {
  return useQuery({
    queryKey: queryKeys.learning.stats,
    queryFn: getLearningStats,
    refetchInterval: 30_000,
  })
}

export function useTriggerReflection() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: triggerReflection,
    onSuccess: (data) => {
      toast.success(data.message || 'Reflection triggered')
      queryClient.invalidateQueries({ queryKey: queryKeys.learning.all })
    },
    onError: () => {
      toast.error('Failed to trigger reflection')
    },
  })
}
