import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getPipelineStatus, triggerFindHandles, triggerScrapePosts, triggerExtractPhones, getProvinces, triggerCollectUniversities } from '../api/pipeline'
import { queryKeys } from '../lib/queryKeys'

export function usePipelineStatus() {
  return useQuery({
    queryKey: queryKeys.pipeline.status,
    queryFn: getPipelineStatus,
    refetchInterval: 15_000,
  })
}

export function useTriggerFindHandles() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (limit?: number) => triggerFindHandles(limit),
    onSuccess: (data) => {
      toast.success(data.message || 'Find IG handles started')
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
    },
    onError: () => {
      toast.error('Failed to start IG handle search')
    },
  })
}

export function useTriggerScrapePosts() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (limit?: number) => triggerScrapePosts(limit),
    onSuccess: (data) => {
      toast.success(data.message || 'Scrape IG posts started')
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
    },
    onError: () => {
      toast.error('Failed to start IG post scraping')
    },
  })
}

export function useTriggerExtractPhones() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (limit?: number) => triggerExtractPhones(limit),
    onSuccess: (data) => {
      toast.success(data.message || 'Phone extraction started')
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
    },
    onError: () => {
      toast.error('Failed to start phone extraction')
    },
  })
}

export function useProvinces() {
  return useQuery({
    queryKey: ['provinces'],
    queryFn: getProvinces,
    staleTime: Infinity,
  })
}

export function useTriggerCollectUniversities() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params?: { province?: string; limit?: number }) => triggerCollectUniversities(params),
    onSuccess: (data) => {
      toast.success(data.message || 'University collection started')
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
    },
    onError: () => {
      toast.error('Failed to start PDDIKTI collection')
    },
  })
}
