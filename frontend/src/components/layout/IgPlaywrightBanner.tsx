import { useState } from 'react'
import { AlertTriangle, X, RefreshCw, ExternalLink, ShieldAlert, WifiOff } from 'lucide-react'
import { useIGAccountHealth } from '../../hooks/useIGAccountHealth'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '../../lib/queryKeys'
import { getIGAccountsHealth } from '../../api/igAccounts'
import toast from 'react-hot-toast'

/**
 * Global banner for Playwright-based IG account health.
 * Shown when any IG account's session is disconnected or banned.
 * Rendered in AppShell alongside the existing IgSessionBanner.
 */
export function IgPlaywrightBanner() {
  const { data: health, isLoading } = useIGAccountHealth()
  const queryClient = useQueryClient()
  const [dismissed, setDismissed] = useState(false)
  const [checking, setChecking] = useState(false)

  if (isLoading || !health || health.total === 0 || health.all_ok || dismissed) {
    return null
  }

  const disconnected = health.accounts.filter((a) => a.status === 'disconnected')
  const banned = health.accounts.filter((a) => a.status === 'banned')
  const rateLimited = health.accounts.filter((a) => a.status === 'rate_limited')
  const errored = health.accounts.filter((a) => a.status === 'error')

  const allDown = health.connected === 0
  const hasBanned = banned.length > 0

  const title = allDown
    ? health.total === 1
      ? 'Koneksi Instagram terputus'
      : `Semua ${health.total} akun Instagram bermasalah`
    : `${health.total - health.connected} dari ${health.total} akun IG bermasalah`

  const handleForceCheck = async () => {
    setChecking(true)
    try {
      const fresh = await getIGAccountsHealth(true)
      queryClient.setQueryData(queryKeys.igAccountsHealth, fresh)
      if (fresh.all_ok) {
        toast.success('Semua akun IG terhubung!')
        setDismissed(true)
      } else {
        toast.error(`${fresh.total - fresh.connected} akun masih bermasalah`)
      }
    } catch {
      toast.error('Gagal memeriksa status akun')
    } finally {
      setChecking(false)
    }
  }

  const borderColor = hasBanned || allDown
    ? 'border-red-300 dark:border-red-700'
    : 'border-amber-300 dark:border-amber-700'
  const bgColor = hasBanned || allDown
    ? 'bg-red-50 dark:bg-red-950/40'
    : 'bg-amber-50 dark:bg-amber-950/40'
  const iconColor = hasBanned || allDown
    ? 'text-red-600 dark:text-red-400'
    : 'text-amber-600 dark:text-amber-400'
  const titleColor = hasBanned || allDown
    ? 'text-red-800 dark:text-red-200'
    : 'text-amber-800 dark:text-amber-200'
  const textColor = hasBanned || allDown
    ? 'text-red-700 dark:text-red-300'
    : 'text-amber-700 dark:text-amber-300'

  return (
    <div className={`relative mb-4 rounded-lg border px-4 py-3 ${borderColor} ${bgColor}`}>
      <div className="flex items-start gap-3">
        {hasBanned ? (
          <ShieldAlert className={`mt-0.5 h-5 w-5 shrink-0 ${iconColor}`} />
        ) : allDown ? (
          <WifiOff className={`mt-0.5 h-5 w-5 shrink-0 ${iconColor}`} />
        ) : (
          <AlertTriangle className={`mt-0.5 h-5 w-5 shrink-0 ${iconColor}`} />
        )}

        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold ${titleColor}`}>{title}</p>

          {/* Per-account status pills */}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {health.accounts.map((a) => {
              const statusConfig = {
                connected: {
                  bg: 'bg-green-100 dark:bg-green-900/30',
                  text: 'text-green-700 dark:text-green-400',
                  dot: 'bg-green-500',
                  label: 'Terhubung',
                },
                disconnected: {
                  bg: 'bg-red-100 dark:bg-red-900/30',
                  text: 'text-red-700 dark:text-red-400',
                  dot: 'bg-red-500',
                  label: 'Terputus',
                },
                banned: {
                  bg: 'bg-red-100 dark:bg-red-900/30',
                  text: 'text-red-700 dark:text-red-400',
                  dot: 'bg-red-500',
                  label: 'Banned',
                },
                rate_limited: {
                  bg: 'bg-amber-100 dark:bg-amber-900/30',
                  text: 'text-amber-700 dark:text-amber-400',
                  dot: 'bg-amber-500',
                  label: 'Rate Limited',
                },
                error: {
                  bg: 'bg-gray-100 dark:bg-gray-800',
                  text: 'text-gray-700 dark:text-gray-400',
                  dot: 'bg-gray-500',
                  label: 'Error',
                },
              }[a.status] ?? {
                bg: 'bg-gray-100 dark:bg-gray-800',
                text: 'text-gray-600 dark:text-gray-400',
                dot: 'bg-gray-400',
                label: a.status,
              }

              return (
                <span
                  key={a.username}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${statusConfig.bg} ${statusConfig.text}`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${statusConfig.dot}`} />
                  @{a.username}
                  <span className="opacity-70">({statusConfig.label})</span>
                </span>
              )
            })}
          </div>

          {/* Action row */}
          <div className={`mt-2 flex items-center gap-3 text-xs ${textColor}`}>
            {disconnected.length > 0 && (
              <span>
                <strong>Fix:</strong> Buka{' '}
                <a
                  href="/settings"
                  className="inline-flex items-center gap-0.5 font-medium underline hover:opacity-80"
                >
                  Settings <ExternalLink className="h-3 w-3" />
                </a>{' '}
                → Login ulang akun yang terputus
              </span>
            )}
            {hasBanned && (
              <span>
                <strong>Perhatian:</strong> Akun yang di-ban perlu diganti dengan akun baru
              </span>
            )}
            <button
              onClick={handleForceCheck}
              disabled={checking}
              className="inline-flex items-center gap-1 rounded-md border border-current px-2 py-0.5 font-medium hover:opacity-80 disabled:opacity-50 ml-auto"
            >
              <RefreshCw className={`h-3 w-3 ${checking ? 'animate-spin' : ''}`} />
              Cek Ulang
            </button>
          </div>
        </div>

        <button
          onClick={() => setDismissed(true)}
          className={`shrink-0 rounded p-1 hover:opacity-80 ${iconColor}`}
          title="Dismiss (akan muncul lagi jika masih bermasalah)"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
