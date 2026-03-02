import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import toast from 'react-hot-toast'
import { getIGAccountsHealth, type IGAccountsHealthResponse } from '../api/igAccounts'
import { queryKeys } from '../lib/queryKeys'

/**
 * Polls IG account health every 60s.
 * Shows toast notifications when accounts go down or get banned.
 */
export function useIGAccountHealth() {
  const prevRef = useRef<IGAccountsHealthResponse | null>(null)

  const query = useQuery({
    queryKey: queryKeys.igAccountsHealth,
    queryFn: () => getIGAccountsHealth(),
    refetchInterval: 60_000, // poll every 60s
    staleTime: 30_000,
    retry: 1,
  })

  // Detect status transitions and fire toast notifications
  useEffect(() => {
    const current = query.data
    if (!current || current.total === 0) return

    const prev = prevRef.current
    prevRef.current = current

    // Skip first load — don't spam toasts on page open
    if (!prev) return

    // Compare each account's status
    const prevMap = new Map(prev.accounts.map((a) => [a.username, a.status]))

    for (const acct of current.accounts) {
      const oldStatus = prevMap.get(acct.username)
      if (!oldStatus) continue // new account, skip

      // Transition: was OK → now bad
      if (oldStatus === 'connected' && acct.status !== 'connected') {
        if (acct.status === 'banned') {
          toast.error(`⛔ @${acct.username} telah di-ban oleh Instagram`, {
            duration: 10_000,
            id: `ig-banned-${acct.username}`,
          })
        } else if (acct.status === 'disconnected') {
          toast.error(`🔌 @${acct.username} sesi terputus — perlu login ulang`, {
            duration: 8_000,
            id: `ig-disconnected-${acct.username}`,
          })
        } else if (acct.status === 'rate_limited') {
          toast(`⏳ @${acct.username} terkena rate limit`, {
            duration: 6_000,
            icon: '⚠️',
            id: `ig-ratelimit-${acct.username}`,
          })
        }
      }

      // Transition: was bad → now OK (recovery)
      if (oldStatus !== 'connected' && acct.status === 'connected') {
        toast.success(`✅ @${acct.username} kembali terhubung`, {
          duration: 5_000,
          id: `ig-recovered-${acct.username}`,
        })
      }
    }

    // Aggregated alert: all accounts down
    if (prev.connected > 0 && current.connected === 0 && current.total > 0) {
      toast.error('🚨 Semua akun Instagram terputus!', {
        duration: 15_000,
        id: 'ig-all-down',
      })
    }
  }, [query.data])

  return query
}
