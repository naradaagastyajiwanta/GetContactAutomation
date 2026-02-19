import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getControlStatus, pauseBot, resumeBot } from '../api/control'
import { queryKeys } from '../lib/queryKeys'

export function useControlStatus() {
  return useQuery({
    queryKey: queryKeys.control,
    queryFn: getControlStatus,
    refetchInterval: 10_000,
  })
}

export function usePause() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: pauseBot,
    onSuccess: () => {
      toast.success('Bot paused')
      queryClient.invalidateQueries({ queryKey: queryKeys.control })
    },
    onError: () => {
      toast.error('Failed to pause bot')
    },
  })
}

export function useResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: resumeBot,
    onSuccess: () => {
      toast.success('Bot resumed')
      queryClient.invalidateQueries({ queryKey: queryKeys.control })
    },
    onError: () => {
      toast.error('Failed to resume bot')
    },
  })
}
