import { useQuery } from '@tanstack/react-query'
import { getApiLogs, getApiLog, type ApiLogsParams } from '../api/apiLogs'
import { queryKeys } from '../lib/queryKeys'

export function useApiLogs(params: ApiLogsParams = {}) {
  return useQuery({
    queryKey: queryKeys.apiLogs.list(params as Record<string, unknown>),
    queryFn: () => getApiLogs(params),
  })
}

export function useApiLog(id: number) {
  return useQuery({
    queryKey: queryKeys.apiLogs.detail(id),
    queryFn: () => getApiLog(id),
    enabled: id > 0,
  })
}
