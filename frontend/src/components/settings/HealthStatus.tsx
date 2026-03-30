import { useState } from 'react'
import { Activity, ChevronDown, ChevronUp, ExternalLink, Wifi, WifiOff, Instagram, Server, Key } from 'lucide-react'
import { useHealth } from '../../hooks/useHealth'
import { Card, CardContent } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { cn } from '../../lib/utils'
import type { ApiKeyInfo } from '../../lib/types'

// ---------------------------------------------------------------------------
// Step-by-step guides for each free-tier API key
// ---------------------------------------------------------------------------

const TEMP_MAIL_URL = 'https://temp-mail.org/'

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
      'Buka temp-mail.org → salin alamat email sementara yang sudah dibuat otomatis.',
      'Buka serper.dev dan klik "Sign Up" → gunakan email dari temp-mail tadi.',
      'Buka kembali temp-mail.org → klik email verifikasi dari Serper → klik link konfirmasi.',
      'Login ke dashboard Serper.',
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
      'Buka temp-mail.org → salin alamat email sementara yang sudah dibuat otomatis.',
      'Buka apify.com dan klik "Sign up for free" → gunakan email dari temp-mail tadi.',
      'Buka kembali temp-mail.org → klik email verifikasi dari Apify → konfirmasi akun.',
      'Login ke Apify Console.',
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
      'Buka temp-mail.org → salin alamat email sementara yang sudah dibuat otomatis.',
      'Buka scraping-bot.io dan klik "Start for Free" → gunakan email dari temp-mail tadi.',
      'Buka kembali temp-mail.org → klik email verifikasi dari ScrapingBot → konfirmasi akun.',
      'Login ke dashboard ScrapingBot.',
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
              href={TEMP_MAIL_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded bg-sky-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-sky-700 dark:bg-sky-700 dark:hover:bg-sky-600"
            >
              <ExternalLink className="h-3 w-3" />
              Buka Temp Mail
            </a>
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
  let badgeClass = 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'

  if (configured && ok) {
    dotColor = 'bg-green-400 dark:bg-green-500'
    statusText = 'OK'
    badgeClass = 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
  } else if (hasError) {
    dotColor = 'bg-red-400 dark:bg-red-500'
    statusText = 'Quota Habis'
    badgeClass = 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
  }

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50/50 px-3 py-2.5 dark:border-gray-700 dark:bg-gray-800/30">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
        <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium', badgeClass)}>
          <span className={cn('h-1.5 w-1.5 rounded-full', dotColor)} />
          {statusText}
        </span>
      </div>

      {!configured && (
        <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
          Opsional — tambahkan di Config untuk scraping tanpa IG session.
        </p>
      )}

      {hasError && (
        <div className="mt-1.5">
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
// Status pill for the top bar
// ---------------------------------------------------------------------------

function StatusPill({
  icon,
  label,
  ok,
  detail,
}: {
  icon: React.ReactNode
  label: string
  ok: boolean
  detail?: string
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-lg border px-3 py-2 text-sm',
        ok
          ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20'
          : 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/20',
      )}
    >
      <div className={cn('flex-shrink-0', ok ? 'text-green-500' : 'text-red-500')}>
        {icon}
      </div>
      <div className="min-w-0">
        <span className={cn('font-medium', ok ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400')}>
          {label}
        </span>
        {detail && (
          <span className={cn('ml-1.5 text-xs', ok ? 'text-green-600/70 dark:text-green-500/70' : 'text-red-600/70 dark:text-red-500/70')}>
            {detail}
          </span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

export function HealthStatus() {
  const { data: health, isLoading } = useHealth()
  const [showDetails, setShowDetails] = useState(false)

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

  const apiOk = health?.status === 'ok'

  // Count how many API keys have issues
  const apiKeyIssues = [apiKeys?.serper, apiKeys?.apify, apiKeys?.scrapingbot].filter(
    (k) => k && k.configured && !k.ok,
  ).length

  return (
    <Card padding={false} className="overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-gray-500 dark:text-gray-400" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">System Health</h3>
        </div>
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
        >
          {showDetails ? 'Less' : 'Details'}
          {showDetails ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      <CardContent className="p-5">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Compact status pills */}
            <div className="grid grid-cols-3 gap-2">
              <StatusPill
                icon={<Server className="h-4 w-4" />}
                label="API"
                ok={apiOk}
                detail={apiOk ? 'OK' : 'Error'}
              />
              <StatusPill
                icon={waConnected ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
                label="WA"
                ok={waConnected}
              />
              <StatusPill
                icon={<Instagram className="h-4 w-4" />}
                label="IG"
                ok={igOk}
                detail={
                  igTotal === 0
                    ? 'N/A'
                    : igOk
                      ? `${igHealthy}/${igTotal}`
                      : (igError ? igLabel[igError] || igError : 'Error')
                }
              />
            </div>

            {/* Expandable details */}
            {showDetails && (
              <div className="space-y-3 pt-1">
                {/* IG session breakdown */}
                {igSessions.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                      Instagram Sessions
                    </p>
                    {igSessions.map((s, i) => (
                      <div key={i} className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-1.5 text-xs dark:bg-gray-800/50">
                        <span className="font-mono text-gray-600 dark:text-gray-400">{s.label}</span>
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
                  <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-3">
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

                {/* API Keys */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Key className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                    <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                      API Keys
                      {apiKeyIssues > 0 && (
                        <span className="ml-1.5 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700 dark:bg-red-900/40 dark:text-red-400">
                          {apiKeyIssues} issue{apiKeyIssues > 1 ? 's' : ''}
                        </span>
                      )}
                    </p>
                  </div>

                  <ApiKeyRow
                    label="Serper (Google Search)"
                    info={apiKeys?.serper}
                    serviceKey="serper"
                  />

                  {fallbacks && (
                    <>
                      <ApiKeyRow
                        label="Apify (IG Scraper Tier 2)"
                        info={apiKeys?.apify ?? (fallbacks.apify ? { configured: fallbacks.apify.configured, ok: true, error: null } : undefined)}
                        serviceKey="apify"
                      />
                      <ApiKeyRow
                        label="ScrapingBot (IG Scraper Tier 3)"
                        info={apiKeys?.scrapingbot ?? (fallbacks.scrapingbot ? { configured: fallbacks.scrapingbot.configured, ok: true, error: null } : undefined)}
                        serviceKey="scrapingbot"
                      />
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
