import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getPipelineStatus, triggerFindHandles, triggerScrapePosts, triggerExtractPhones, triggerDiscoverBem, triggerFindRectors, getProvinces, triggerCollectUniversities, getPipelineLogs, triggerAgentTargeted, pauseBot, resumeBot, type PipelineLogsParams, type TargetedAgentType } from '../api/pipeline'
import { queryKeys } from '../lib/queryKeys'
import { useWebSocketContext } from '../context/WebSocketContext'

export function usePipelineStatus() {
  const { connected } = useWebSocketContext()
  return useQuery({
    queryKey: queryKeys.pipeline.status,
    queryFn: getPipelineStatus,
    refetchInterval: connected ? false : 5_000,
  })
}

export function usePipelineLogs(params: PipelineLogsParams = {}) {
  const { connected } = useWebSocketContext()
  return useQuery({
    queryKey: queryKeys.pipeline.logs(params as Record<string, unknown>),
    queryFn: () => getPipelineLogs(params),
    refetchInterval: connected ? false : 10_000,
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

export function useTriggerDiscoverBem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (limit?: number) => triggerDiscoverBem(limit),
    onSuccess: (data) => {
      toast.success(data.message || 'BEM discovery started')
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
    },
    onError: () => {
      toast.error('Failed to start BEM discovery')
    },
  })
}

export function useTriggerFindRectors() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (limit?: number) => triggerFindRectors(limit),
    onSuccess: (data) => {
      toast.success(data.message || 'Rector name search started')
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
    },
    onError: () => {
      toast.error('Failed to start rector name search')
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

const AGENT_LABELS: Record<TargetedAgentType, string> = {
  find_handles: 'Find IG Handles',
  scrape_posts: 'Scrape IG Posts',
  extract_phones: 'Extract Phones',
  discover_bem: 'Discover BEM',
  find_rectors: 'Find Rectors',
}

export function useRunAgentTargeted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ agentType, universityIds }: { agentType: TargetedAgentType; universityIds: number[] }) =>
      triggerAgentTargeted(agentType, universityIds),
    onSuccess: (data, variables) => {
      toast.success(data.message || `${AGENT_LABELS[variables.agentType]} started`)
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
    },
    onError: (_err, variables) => {
      toast.error(`Failed to start ${AGENT_LABELS[variables.agentType]}`)
    },
  })
}

export function usePauseBot() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => pauseBot(),
    onSuccess: () => {
      toast.success('Pipeline stopped — agents will finish current item and stop')
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
    },
    onError: () => {
      toast.error('Failed to pause pipeline')
    },
  })
}

export function useResumeBot() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => resumeBot(),
    onSuccess: () => {
      toast.success('Pipeline resumed')
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
    },
    onError: () => {
      toast.error('Failed to resume pipeline')
    },
  })
}
