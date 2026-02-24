import { useState } from 'react'
import { Activity, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { useHealth } from '../../hooks/useHealth'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { cn } from '../../lib/utils'
import type { ApiKeyInfo } from '../../lib/types'

// ---------------------------------------------------------------------------
// Step-by-step guides for each free-tier API key
// ---------------------------------------------------------------------------

const API_GUIDES: Record<string, {
  name: string
  url: string
  configKey: string | string[]
  steps: string[]
}> = {
  serper: {
    name: 'Serper (Google Search API)',
    url: 'https://serper.dev',
    configKey: 'SERPER_API_KEY',
    steps: [
      'Buka serper.dev dan klik "Sign Up" — gunakan email baru (Gmail/Outlook).',
      'Verifikasi email, lalu login ke dashboard.',
      'Di dashboard, salin API Key yang muncul di halaman utama.',
      'Di aplikasi ini, buka Settings → Config → cari SERPER_API_KEY.',
      'Klik Edit, tempel API Key baru, lalu klik Confirm.',
      'Refresh halaman — status Serper akan berubah menjadi hijau.',
    ],
  },
  apify: {
    name: 'Apify (Instagram Scraper Tier 2)',
    url: 'https://apify.com',
    configKey: 'APIFY_API_KEY',
    steps: [
      'Buka apify.com dan klik "Sign up for free" — gunakan email baru.',
      'Verifikasi email, lalu login ke Apify Console.',
      'Di sidebar kiri, klik nama akun → Settings → Integrations.',
      'Di bagian "Personal API tokens", klik "Create new token".',
      'Beri nama token (misal: "getcontact"), lalu klik Create — salin tokennya.',
      'Di aplikasi ini, buka Settings → Config → cari APIFY_API_KEY.',
      'Klik Edit, tempel token baru, lalu klik Confirm.',
    ],
  },
  scrapingbot: {
    name: 'ScrapingBot (Instagram Scraper Tier 3)',
    url: 'https://www.scraping-bot.io',
    configKey: ['SCRAPINGBOT_USERNAME', 'SCRAPINGBOT_API_KEY'],
    steps: [
      'Buka scraping-bot.io dan klik "Start for Free" — gunakan email baru.',
      'Verifikasi email, lalu login ke dashboard ScrapingBot.',
      'Di dashboard, temukan bagian "API Credentials" atau "API Keys".',
      'Salin Username dan API Key yang tertera.',
      'Di aplikasi ini, buka Settings → Config.',
      'Update SCRAPINGBOT_USERNAME dengan username yang disalin.',
      'Update SCRAPINGBOT_API_KEY dengan API Key yang disalin.',
      'Klik Confirm pada masing-masing field.',
    ],
  },
}

function ApiKeyGuide({ serviceKey }: { serviceKey: string }) {
  const [open, setOpen] = useState(false)
  const guide = API_GUIDES[serviceKey]
  if (!guide) return null

  const configKeys = Array.isArray(guide.configKey) ? guide.configKey : [guide.configKey]

  return (
    <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <span className="text-xs font-semibold text-amber-800 dark:text-amber-300">
          Cara buat akun baru {guide.name}
        </span>
        {open
          ? <ChevronUp className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 flex-shrink-0" />
          : <ChevronDown className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 flex-shrink-0" />
        }
      </button>

      {open && (
        <div className="border-t border-amber-200 dark:border-amber-800 px-3 pb-3 pt-2 space-y-2">
          <ol className="space-y-1.5">
            {guide.steps.map((step, i) => (
              <li key={i} className="flex gap-2 text-xs text-amber-900 dark:text-amber-200">
                <span className="flex-shrink-0 font-bold text-amber-600 dark:text-amber-400">
                  {i + 1}.
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <a
              href={guide.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-700 dark:bg-amber-700 dark:hover:bg-amber-600"
            >
              <ExternalLink className="h-3 w-3" />
              Buka {guide.url.replace('https://', '').replace('http://', '')}
            </a>
            <span className="text-xs text-amber-700 dark:text-amber-400">
              Config key:{' '}
              {configKeys.map((k, i) => (
                <span key={k}>
                  <span className="font-mono font-semibold">{k}</span>
                  {i < configKeys.length - 1 && ', '}
                </span>
              ))}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function ApiKeyRow({
  label,
  info,
  serviceKey,
}: {
  label: string
  info: ApiKeyInfo | undefined
  serviceKey: string
}) {
  const configured = info?.configured ?? false
  const ok = info?.ok ?? true
  const hasError = configured && !ok

  let dotColor = 'bg-gray-300 dark:bg-gray-600'
  let statusText = 'Not Set'

  if (configured && ok) {
    dotColor = 'bg-green-400 dark:bg-green-500'
    statusText = 'OK'
  } else if (hasError) {
    dotColor = 'bg-red-400 dark:bg-red-500'
    statusText = 'Quota Habis'
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
        <div className="flex items-center gap-2">
          <span className={cn('h-2.5 w-2.5 rounded-full', dotColor)} />
          <span className={cn(
            'text-sm font-medium',
            hasError ? 'text-red-600 dark:text-red-400' : 'text-gray-900 dark:text-gray-100',
          )}>
            {statusText}
          </span>
        </div>
      </div>

      {/* Not configured hint */}
      {!configured && (
        <p className="mt-1 ml-0.5 text-xs text-gray-400 dark:text-gray-500">
          Opsional — tambahkan di Config untuk scraping tanpa IG session.
        </p>
      )}

      {/* Quota exhausted alert + guide */}
      {hasError && (
        <div className="mt-1">
          <p className="text-xs text-red-600 dark:text-red-400">
            API key tidak valid atau kuota free tier habis. Buat akun baru dengan email baru.
          </p>
          <ApiKeyGuide serviceKey={serviceKey} />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------

export function HealthStatus() {
  const { data: health, isLoading } = useHealth()

  const waConnected = health?.whatsapp?.connected ?? false
  const ig = health?.instagram
  const igOk = ig?.ok ?? true
  const igTotal = ig?.total ?? 0
  const igHealthy = ig?.healthy ?? 0
  const igSessions = ig?.sessions ?? []
  const igError = ig?.error
  const fallbacks = ig?.fallbacks
  const apiKeys = health?.api_keys

  const igLabel: Record<string, string> = {
    suspended: 'Suspended',
    login_required: 'Session Expired',
    no_sessions: 'Not Configured',
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-gray-500 dark:text-gray-400" />
          <CardTitle>System Health</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500 dark:text-gray-400">API Status</span>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'h-2.5 w-2.5 rounded-full',
                    health?.status === 'ok'
                      ? 'bg-green-400 dark:bg-green-500'
                      : 'bg-red-400 dark:bg-red-500',
                  )}
                />
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {health?.status === 'ok' ? 'Healthy' : 'Error'}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500 dark:text-gray-400">WhatsApp</span>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'h-2.5 w-2.5 rounded-full',
                    waConnected
                      ? 'bg-green-400 dark:bg-green-500'
                      : 'bg-red-400 dark:bg-red-500',
                  )}
                />
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {waConnected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500 dark:text-gray-400">Instagram Sessions</span>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'h-2.5 w-2.5 rounded-full',
                    igOk
                      ? 'bg-green-400 dark:bg-green-500'
                      : 'bg-red-400 dark:bg-red-500',
                  )}
                />
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {igTotal === 0
                    ? 'Not Configured'
                    : igOk
                      ? `${igHealthy}/${igTotal} Active`
                      : (igError ? igLabel[igError] || igError : 'Error')}
                </span>
              </div>
            </div>

            {/* Per-session breakdown */}
            {igSessions.length > 1 && (
              <div className="ml-4 space-y-1">
                {igSessions.map((s, i) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <span className="font-mono text-gray-500 dark:text-gray-400">{s.label}</span>
                    <span className={cn(
                      'font-medium',
                      s.ok
                        ? 'text-green-600 dark:text-green-400'
                        : 'text-red-600 dark:text-red-400',
                    )}>
                      {s.ok ? 'Active' : (s.error === 'login_required' ? 'Expired' : s.error || 'Error')}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {!igOk && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3 mt-1">
                <p className="text-xs text-red-700 dark:text-red-400">
                  {igTotal === 0
                    ? <>No IG sessions configured. Add <span className="font-mono font-semibold">IG_SESSION_ID</span> in Config below.</>
                    : <>
                        {igHealthy === 0 ? 'All' : 'Some'} IG sessions are down.
                        Update <span className="font-mono font-semibold">IG_SESSION_ID</span> in
                        Config below. Use commas to add multiple sessions for automatic rotation.
                      </>
                  }
                </p>
              </div>
            )}

            {/* ----------------------------------------------------------------
                Search & Scraping API Keys
            ---------------------------------------------------------------- */}
            <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
              <span className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                Search & Scraping API Keys
              </span>
            </div>

            {/* Serper */}
            <ApiKeyRow
              label="Serper (Google Search)"
              info={apiKeys?.serper}
              serviceKey="serper"
            />

            {/* Fallback Providers */}
            {fallbacks && (
              <>
                <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
                  <span className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                    Fallback Scraping Providers
                  </span>
                </div>

                {/* Apify */}
                <ApiKeyRow
                  label="Apify (IG Scraper Tier 2)"
                  info={apiKeys?.apify ?? (fallbacks.apify ? { configured: fallbacks.apify.configured, ok: true, error: null } : undefined)}
                  serviceKey="apify"
                />

                {/* ScrapingBot */}
                <ApiKeyRow
                  label="ScrapingBot (IG Scraper Tier 3)"
                  info={apiKeys?.scrapingbot ?? (fallbacks.scrapingbot ? { configured: fallbacks.scrapingbot.configured, ok: true, error: null } : undefined)}
                  serviceKey="scrapingbot"
                />
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
