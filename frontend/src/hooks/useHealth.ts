import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../api/health'
import { queryKeys } from '../lib/queryKeys'

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    refetchInterval: 60_000,
  })
}
