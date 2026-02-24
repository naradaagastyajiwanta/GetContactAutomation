import { useState } from 'react'
import { AlertTriangle, X, ExternalLink, RefreshCw } from 'lucide-react'
import { useHealth } from '../../hooks/useHealth'
import { resetIgSessions } from '../../api/health'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '../../lib/queryKeys'
import toast from 'react-hot-toast'

/**
 * Global banner shown when Instagram sessions are expired or suspended.
 * Rendered in AppShell so it appears on every page.
 * Supports the multi-session pool — shows how many sessions are down.
 */
export function IgSessionBanner() {
  const { data: health } = useHealth()
  const queryClient = useQueryClient()
  const [dismissed, setDismissed] = useState(false)
  const [resetting, setResetting] = useState(false)

  const ig = health?.instagram
  const igOk = ig?.ok ?? true
  const total = ig?.total ?? 0
  const healthy = ig?.healthy ?? 0
  const sessions = ig?.sessions ?? []
  const fallbacks = ig?.fallbacks

  // Count configured fallback providers
  const fbApify = fallbacks?.apify?.configured ?? false
  const fbSbot = fallbacks?.scrapingbot?.configured ?? false
  const fbCount = (fbApify ? 1 : 0) + (fbSbot ? 1 : 0)

  if (igOk || dismissed || total === 0) return null

  const allDown = healthy === 0
  const title = allDown
    ? total === 1
      ? 'Instagram session expired'
      : `All ${total} Instagram sessions are down`
    : `${total - healthy} of ${total} IG sessions down`

  const fallbackNote = allDown && fbCount > 0
    ? ` Fallback provider${fbCount > 1 ? 's' : ''} (${[fbApify && 'Apify', fbSbot && 'ScrapingBot'].filter(Boolean).join(', ')}) will be used automatically.`
    : ''
  const description = allDown
    ? `All IG sessions are expired or suspended.${fbCount > 0 ? fallbackNote : ' Scraping agents will return empty results until you update the session IDs.'}`
    : `${healthy} session(s) still active — rotation is working, but you should replace the failed session(s) soon.`

  const handleReset = async () => {
    setResetting(true)
    try {
      await resetIgSessions()
      queryClient.invalidateQueries({ queryKey: queryKeys.health })
      toast.success('IG sessions reset — will be re-checked on next request')
    } catch {
      toast.error('Failed to reset IG sessions')
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className={`relative mb-4 rounded-lg border px-4 py-3 ${
      allDown
        ? 'border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-950/40'
        : 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/40'
    }`}>
      <div className="flex items-start gap-3">
        <AlertTriangle className={`mt-0.5 h-5 w-5 shrink-0 ${
          allDown
            ? 'text-red-600 dark:text-red-400'
            : 'text-amber-600 dark:text-amber-400'
        }`} />
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold ${
            allDown
              ? 'text-red-800 dark:text-red-200'
              : 'text-amber-800 dark:text-amber-200'
          }`}>
            {title}
          </p>
          <p className={`mt-0.5 text-sm ${
            allDown
              ? 'text-red-700 dark:text-red-300'
              : 'text-amber-700 dark:text-amber-300'
          }`}>
            {description}
          </p>

          {/* Per-session status pills */}
          {sessions.length > 1 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {sessions.map((s, i) => (
                <span
                  key={i}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    s.ok
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  }`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${s.ok ? 'bg-green-500' : 'bg-red-500'}`} />
                  {s.label}
                  {!s.ok && s.error && ` (${s.error === 'login_required' ? 'expired' : s.error})`}
                </span>
              ))}
            </div>
          )}

          {/* Fallback provider pills */}
          {fbCount > 0 && allDown && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {fbApify && (
                <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                  Apify fallback active
                </span>
              )}
              {fbSbot && (
                <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-purple-500" />
                  ScrapingBot fallback active
                </span>
              )}
            </div>
          )}

          <div className={`mt-2 flex items-center gap-3 text-xs ${
            allDown
              ? 'text-red-600 dark:text-red-400'
              : 'text-amber-600 dark:text-amber-400'
          }`}>
            <span>
              <strong>Fix:</strong> Get sessionid from browser (F12 → Cookies → instagram.com) →{' '}
              <a
                href="/settings"
                className="inline-flex items-center gap-0.5 font-medium underline hover:opacity-80"
              >
                Settings <ExternalLink className="h-3 w-3" />
              </a>
              {' '}→ IG Session ID(s). Use commas for multiple sessions.
            </span>
            <button
              onClick={handleReset}
              disabled={resetting}
              className="inline-flex items-center gap-1 rounded-md border border-current px-2 py-0.5 font-medium hover:opacity-80 disabled:opacity-50"
            >
              <RefreshCw className={`h-3 w-3 ${resetting ? 'animate-spin' : ''}`} />
              Reset
            </button>
          </div>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className={`shrink-0 rounded p-1 hover:opacity-80 ${
            allDown
              ? 'text-red-600 dark:text-red-400'
              : 'text-amber-600 dark:text-amber-400'
          }`}
          title="Dismiss (will reappear on page refresh)"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
