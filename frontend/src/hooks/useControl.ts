import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getControlStatus, pauseBot, resumeBot, toggleChatbot } from '../api/control'
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

export function useToggleChatbot() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ type, enabled }: { type: 'agent' | 'audiensi' | 'research_multi_agent'; enabled: boolean }) =>
      toggleChatbot(type, enabled),
    onSuccess: (_, variables) => {
      const label =
        variables.type === 'agent'
          ? 'Contact Finder'
          : variables.type === 'audiensi'
            ? 'Audiensi'
            : 'Multi-Agent Research'
      toast.success(`${label} ${variables.enabled ? 'enabled' : 'disabled'}`)
      queryClient.invalidateQueries({ queryKey: queryKeys.control })
      queryClient.invalidateQueries({ queryKey: queryKeys.config })
    },
    onError: () => {
      toast.error('Failed to toggle chatbot')
    },
  })
}
