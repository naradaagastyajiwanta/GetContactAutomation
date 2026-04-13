import { useQuery } from '@tanstack/react-query'
import { getPhoneNumbers, getPhoneNumberStats, type PhoneNumberParams, type PaginatedPhoneNumbers, type PhoneNumberStats } from '../api/phoneNumbers'
import { queryKeys } from '../lib/queryKeys'

export function usePhoneNumbers(params: Record<string, unknown> = {}, autoRefresh = true) {
  return useQuery<PaginatedPhoneNumbers>({
    queryKey: queryKeys.phoneNumbers.list(params),
    queryFn: () =>
      getPhoneNumbers(params as PhoneNumberParams),
    placeholderData: (prev) => prev,
    refetchInterval: autoRefresh ? 30000 : false, // Auto-refresh every 30 seconds
  })
}

export function usePhoneNumberStats() {
  return useQuery<PhoneNumberStats>({
    queryKey: ['phone-numbers', 'stats'],
    queryFn: getPhoneNumberStats,
    refetchInterval: 30000, // Refresh every 30 seconds
  })
}
