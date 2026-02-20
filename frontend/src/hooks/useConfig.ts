import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getConfig, updateConfig, resetConfig, getModels } from '../api/config'
import { queryKeys } from '../lib/queryKeys'

export function useConfig() {
  return useQuery({
    queryKey: queryKeys.config,
    queryFn: getConfig,
  })
}

export function useUpdateConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: updateConfig,
    onSuccess: (data) => {
      toast.success(`Updated ${data.updated.length} setting(s)`)
      queryClient.invalidateQueries({ queryKey: queryKeys.config })
    },
    onError: (error: any) => {
      const errors = error?.response?.data?.errors
      if (errors) {
        const msgs = Object.values(errors).join(', ')
        toast.error(`Validation failed: ${msgs}`)
      } else {
        toast.error('Failed to update config')
      }
    },
  })
}

export function useModels() {
  return useQuery({
    queryKey: queryKeys.models,
    queryFn: getModels,
    staleTime: 5 * 60 * 1000, // cache for 5 minutes
  })
}

export function useResetConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: resetConfig,
    onSuccess: (data) => {
      toast.success(`Reset ${data.key} to default`)
      queryClient.invalidateQueries({ queryKey: queryKeys.config })
    },
    onError: () => {
      toast.error('Failed to reset config')
    },
  })
}
