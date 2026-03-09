import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getDmsStats,
  getDmsSchedules,
  getDmsSchedulesToday,
  getDmsScheduleDetail,
  getDmsFollowups,
  getDmsFollowupsByUniversity,
  getDmsMeetings,
  getDmsApprovals,
  getDmsHealth,
  triggerContactSync,
  triggerScheduleSync,
  getDmsResearchResults,
  getDmsResearchBySchedule,
  triggerResearchForSchedule,
} from '../api/dms'

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const dmsKeys = {
  all: ['dms'] as const,
  health: ['dms', 'health'] as const,
  stats: ['dms', 'stats'] as const,
  schedules: (daysAhead: number, pastDays: number) =>
    ['dms', 'schedules', { daysAhead, pastDays }] as const,
  schedulesToday: ['dms', 'schedules', 'today'] as const,
  scheduleDetail: (id: number, source?: string) =>
    ['dms', 'schedules', 'detail', id, source] as const,
  followups: (limit: number) => ['dms', 'followups', { limit }] as const,
  followupsByUniv: (idUniv: number) => ['dms', 'followups', 'univ', idUniv] as const,
  meetings: (daysAhead: number) => ['dms', 'meetings', { daysAhead }] as const,
  approvals: (status?: string) => ['dms', 'approvals', { status }] as const,
  research: ['dms', 'research'] as const,
  researchBySchedule: (id: number) => ['dms', 'research', 'schedule', id] as const,
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useDmsHealth() {
  return useQuery({
    queryKey: dmsKeys.health,
    queryFn: getDmsHealth,
    refetchInterval: 60_000,
    retry: 1,
  })
}

export function useDmsStats() {
  return useQuery({
    queryKey: dmsKeys.stats,
    queryFn: getDmsStats,
    refetchInterval: 300_000, // 5 min
  })
}

export function useDmsSchedules(daysAhead: number = 90, includePastDays: number = 30) {
  return useQuery({
    queryKey: dmsKeys.schedules(daysAhead, includePastDays),
    queryFn: () => getDmsSchedules(daysAhead, includePastDays),
    refetchInterval: 300_000,
  })
}

export function useDmsSchedulesToday() {
  return useQuery({
    queryKey: dmsKeys.schedulesToday,
    queryFn: getDmsSchedulesToday,
    refetchInterval: 120_000, // 2 min
  })
}

export function useDmsScheduleDetail(id: number, source: string = 'schedule_follow_up') {
  return useQuery({
    queryKey: dmsKeys.scheduleDetail(id, source),
    queryFn: () => getDmsScheduleDetail(id, source),
    enabled: id > 0,
    refetchInterval: 60_000,
  })
}

export function useDmsFollowups(limit: number = 50) {
  return useQuery({
    queryKey: dmsKeys.followups(limit),
    queryFn: () => getDmsFollowups(limit),
    refetchInterval: 300_000,
  })
}

export function useDmsFollowupsByUniversity(idUniv: number, limit: number = 20) {
  return useQuery({
    queryKey: dmsKeys.followupsByUniv(idUniv),
    queryFn: () => getDmsFollowupsByUniversity(idUniv, limit),
    enabled: idUniv > 0,
  })
}

export function useDmsMeetings(daysAhead: number = 14) {
  return useQuery({
    queryKey: dmsKeys.meetings(daysAhead),
    queryFn: () => getDmsMeetings(daysAhead),
    refetchInterval: 300_000,
  })
}

export function useDmsApprovals(status?: string) {
  return useQuery({
    queryKey: dmsKeys.approvals(status),
    queryFn: () => getDmsApprovals(status),
    refetchInterval: 300_000,
  })
}

export function useTriggerScheduleSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: triggerScheduleSync,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: dmsKeys.all })
    },
  })
}

export function useTriggerContactSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: triggerContactSync,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: dmsKeys.all })
    },
  })
}

export function useDmsResearchResults(limit: number = 500) {
  return useQuery({
    queryKey: [...dmsKeys.research, { limit }],
    queryFn: () => getDmsResearchResults(limit),
    refetchInterval: 60_000,
  })
}

export function useDmsResearchBySchedule(scheduleId: number) {
  return useQuery({
    queryKey: dmsKeys.researchBySchedule(scheduleId),
    queryFn: () => getDmsResearchBySchedule(scheduleId),
    enabled: scheduleId > 0,
    refetchInterval: 30_000,
  })
}

export function useTriggerResearch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, source }: { id: number; source: string }) =>
      triggerResearchForSchedule(id, source),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: dmsKeys.research })
      qc.invalidateQueries({ queryKey: dmsKeys.researchBySchedule(id) })
    },
  })
}
