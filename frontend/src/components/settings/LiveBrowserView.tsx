import { useEffect, useRef, useState, useCallback } from 'react'
import { Monitor, X, Loader2, CheckCircle2, AlertCircle, Camera, Maximize2, Minimize2, Hand } from 'lucide-react'
import { connectTestLoginLive, type TestLoginSSEEvent, type TestLoginDetails } from '../../api/igAccounts'
import { useQueryClient } from '@tanstack/react-query'

interface Props {
  accountId: number
  username: string
  onClose: () => void
  onDone?: (result: { success: boolean; message: string; details?: TestLoginDetails }, loginStatus: string) => void
}

interface Screenshot {
  step: string
  base64: string
  message: string
  ts: number
}

export function LiveBrowserView({ accountId, username, onClose, onDone }: Props) {
  const [status, setStatus] = useState('Connecting...')
  const [screenshots, setScreenshots] = useState<Screenshot[]>([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const [finalResult, setFinalResult] = useState<{
    success: boolean
    message: string
    details?: TestLoginDetails
  } | null>(null)
  const [isFinished, setIsFinished] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const queryClient = useQueryClient()

  const handleEvent = useCallback((evt: TestLoginSSEEvent) => {
    switch (evt.type) {
      case 'status':
        setStatus(evt.message ?? '')
        break
      case 'screenshot':
        if (evt.screenshot) {
          setScreenshots((prev) => {
            const next = [...prev, {
              step: evt.step ?? '',
              base64: evt.screenshot!,
              message: evt.message ?? '',
              ts: evt.ts ?? Date.now() / 1000,
            }]
            setCurrentIdx(next.length - 1) // auto-advance to newest
            return next
          })
          setStatus(evt.message ?? '')
        }
        break
      case 'done':
        if (evt.result) {
          setFinalResult(evt.result)
          setStatus(evt.result.success ? 'Login verified!' : 'Login failed')
        }
        break
      case 'result':
        setIsFinished(true)
        // Invalidate accounts cache so the table refreshes
        queryClient.invalidateQueries({ queryKey: ['ig-accounts'] })
        if (evt.result && onDone) {
          onDone(evt.result, evt.login_status ?? 'failed')
        }
        esRef.current?.close()
        break
    }
  }, [onDone, queryClient])

  useEffect(() => {
    const es = connectTestLoginLive(accountId, handleEvent, () => {
      setIsFinished(true)
      setStatus('Connection lost')
    })
    esRef.current = es
    return () => {
      es.close()
    }
  }, [accountId, handleEvent])

  const currentShot = screenshots[currentIdx]

  return (
    <div className={`rounded-xl border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800 overflow-hidden ${
      expanded ? 'fixed inset-4 z-50' : ''
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-4 py-2.5 dark:border-gray-700 dark:bg-gray-900/60">
        <div className="flex items-center gap-2">
          <Monitor className="h-4 w-4 text-indigo-500" />
          <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
            Manual Login — @{username}
          </span>
          {!isFinished && (
            <span className="flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-medium text-red-700 dark:bg-red-900/40 dark:text-red-400">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
              LIVE
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded(!expanded)}
            className="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
            title={expanded ? 'Minimize' : 'Maximize'}
          >
            {expanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={() => { esRef.current?.close(); onClose() }}
            className="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
            title="Close"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-2 border-b border-gray-100 bg-gray-50/50 px-4 py-1.5 dark:border-gray-700/50 dark:bg-gray-900/30">
        {!isFinished ? (
          <Loader2 className="h-3 w-3 animate-spin text-indigo-500" />
        ) : finalResult?.success ? (
          <CheckCircle2 className="h-3 w-3 text-green-500" />
        ) : (
          <AlertCircle className="h-3 w-3 text-red-500" />
        )}
        <span className="text-xs text-gray-600 dark:text-gray-400">{status}</span>
      </div>

      {/* Screenshot viewport */}
      <div className={`relative bg-gray-900 ${expanded ? 'flex-1' : ''}`} style={{ minHeight: expanded ? 'calc(100vh - 200px)' : '360px' }}>
        {currentShot ? (
          <img
            src={`data:image/jpeg;base64,${currentShot.base64}`}
            alt={currentShot.step}
            className="mx-auto h-full w-full object-contain"
            style={{ maxHeight: expanded ? 'calc(100vh - 200px)' : '360px' }}
          />
        ) : (
          <div className="flex h-full min-h-[360px] items-center justify-center">
            <div className="text-center text-gray-400">
              <Monitor className="mx-auto h-10 w-10 opacity-40" />
              <p className="mt-3 text-sm font-medium">Opening browser on your desktop...</p>
              <p className="mt-1 text-xs opacity-70">You will log in manually in the Chromium window</p>
            </div>
          </div>
        )}

        {/* Manual login instruction overlay — shown while waiting and not finished */}
        {!isFinished && !finalResult && (
          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 via-black/50 to-transparent px-4 py-4">
            <div className="flex items-start gap-3">
              <Hand className="mt-0.5 h-5 w-5 flex-shrink-0 text-yellow-400 animate-bounce" />
              <div>
                <p className="text-sm font-semibold text-white">
                  Log in manually in the browser window
                </p>
                <p className="mt-0.5 text-xs text-gray-300">
                  A Chromium browser has opened on your desktop. Please type your Instagram credentials there and complete any verification.
                  The system is watching and will detect your login automatically.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Screenshot timeline */}
      {screenshots.length > 1 && (
        <div className="flex items-center gap-1 overflow-x-auto border-t border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-900/40">
          {screenshots.map((shot, idx) => (
            <button
              key={idx}
              onClick={() => setCurrentIdx(idx)}
              className={`flex-shrink-0 rounded border-2 transition-all ${
                idx === currentIdx
                  ? 'border-indigo-500 ring-1 ring-indigo-300'
                  : 'border-transparent opacity-60 hover:opacity-90'
              }`}
              title={shot.message || shot.step}
            >
              <img
                src={`data:image/jpeg;base64,${shot.base64}`}
                alt={shot.step}
                className="h-10 w-16 rounded object-cover"
              />
            </button>
          ))}
        </div>
      )}

      {/* Final result panel */}
      {finalResult && (
        <div className={`border-t px-4 py-3 text-sm ${
          finalResult.success
            ? 'border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400'
            : 'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400'
        }`}>
          <div className="flex items-start gap-2">
            {finalResult.success ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0" />
            ) : (
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            )}
            <div className="space-y-1">
              <p className="font-medium">{finalResult.message}</p>
              {finalResult.details && (
                <div className="mt-1 space-y-0.5 text-[11px] opacity-80 font-mono">
                  <p>
                    Cookies:{' '}
                    {Object.keys(finalResult.details.cookies).length > 0
                      ? Object.entries(finalResult.details.cookies)
                          .map(([k, v]) => `${k}=${String(v).slice(0, 6)}...`)
                          .join(', ')
                      : 'none'}
                  </p>
                  <p>Final URL: {finalResult.details.final_url || 'n/a'}</p>
                  {finalResult.details.profile_nuked && (
                    <p className="text-orange-600 dark:text-orange-400">
                      ⚠ Browser profile was wiped for fresh retry
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
