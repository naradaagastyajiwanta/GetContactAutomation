import { useQuery } from '@tanstack/react-query'
import { getDashboardStats } from '../api/dashboard'
import { queryKeys } from '../lib/queryKeys'
import { useWebSocketContext } from '../context/WebSocketContext'

export function useDashboard() {
  const { connected } = useWebSocketContext()
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: getDashboardStats,
    refetchInterval: connected ? false : 30_000,
  })
}
