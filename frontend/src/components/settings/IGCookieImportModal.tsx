import { useState, useCallback } from 'react'
import {
  X,
  Cookie,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Copy,
  Globe,
  ArrowRight,
  MonitorSmartphone,
  ClipboardPaste,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { importIGCookies, type CookieImportResult } from '../../api/igAccounts'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '../../lib/queryKeys'

interface Props {
  accountId: number
  username: string
  isOpen: boolean
  onClose: () => void
}

type Step = 'tutorial' | 'paste' | 'importing' | 'success' | 'error'

export function IGCookieImportModal({ accountId, username, isOpen, onClose }: Props) {
  const [step, setStep] = useState<Step>('tutorial')
  const [cookieJson, setCookieJson] = useState('')
  const [parseError, setParseError] = useState('')
  const [result, setResult] = useState<CookieImportResult | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [showDevTools, setShowDevTools] = useState(false)
  const queryClient = useQueryClient()

  const handleParseCookies = useCallback((): Array<Record<string, unknown>> | null => {
    const text = cookieJson.trim()
    if (!text) {
      setParseError('Paste your cookies JSON here first.')
      return null
    }

    try {
      const parsed = JSON.parse(text)

      // Accept array directly (Cookie-Editor format)
      if (Array.isArray(parsed)) {
        if (parsed.length === 0) {
          setParseError('Cookie array is empty.')
          return null
        }
        // Validate at least one has name + value
        const valid = parsed.filter((c: Record<string, unknown>) => c.name && c.value)
        if (valid.length === 0) {
          setParseError('No valid cookies found. Each cookie must have "name" and "value".')
          return null
        }
        setParseError('')
        return valid
      }

      // Accept single object (wrap in array)
      if (typeof parsed === 'object' && parsed.name && parsed.value) {
        setParseError('')
        return [parsed]
      }

      setParseError('Expected a JSON array of cookies. Example: [{"name":"sessionid","value":"...","domain":".instagram.com"}]')
      return null
    } catch {
      setParseError('Invalid JSON. Make sure you copied the full JSON text from the extension.')
      return null
    }
  }, [cookieJson])

  const handleImport = useCallback(async () => {
    const cookies = handleParseCookies()
    if (!cookies) return

    setStep('importing')
    setErrorMsg('')

    try {
      const res = await importIGCookies(accountId, cookies)
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccounts })
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccountsHealth })

      if (res.verify?.status === 'connected') {
        setResult(res)
        setStep('success')
      } else {
        setResult(res)
        setErrorMsg(
          (res.verify?.status === 'auth_limited'
            ? 'Cookies berhasil diimpor, tetapi sesi hanya punya akses profil publik. Following list belum bisa diakses.'
            : res.verify?.reason) ||
          'Cookies were imported but session verification failed. The cookies may be expired.',
        )
        setStep('error')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connection error'
      setErrorMsg(msg)
      setStep('error')
    }
  }, [accountId, handleParseCookies, queryClient])

  const handleReset = useCallback(() => {
    setStep('tutorial')
    setCookieJson('')
    setParseError('')
    setResult(null)
    setErrorMsg('')
  }, [])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b bg-gradient-to-r from-amber-500 to-orange-500 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Cookie className="w-5 h-5 text-white" />
            <span className="text-white font-semibold">Import Cookies — @{username}</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-full hover:bg-white/20 transition-colors"
            title="Close"
          >
            <X className="w-5 h-5 text-white" />
          </button>
        </div>

        <div className="p-5 space-y-4 overflow-y-auto flex-1">
          {/* ====================== TUTORIAL STEP ====================== */}
          {step === 'tutorial' && (
            <div className="space-y-4">
              <div className="flex items-start gap-3 p-3 bg-blue-50 border border-blue-200 rounded-xl">
                <MonitorSmartphone className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-blue-800">
                  Instagram blocks login from servers. Instead, copy your session cookies
                  from a normal browser and paste them here.
                </p>
              </div>

              {/* Step-by-step guide */}
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-900 text-sm">Tutorial:</h3>

                {/* Step 1 */}
                <div className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-7 h-7 rounded-full bg-orange-500 text-white text-xs font-bold flex items-center justify-center">1</span>
                  <div className="text-sm">
                    <p className="font-medium text-gray-900">Login ke Instagram di browser biasa</p>
                    <p className="text-gray-500 mt-0.5">
                      Buka{' '}
                      <a
                        href="https://www.instagram.com"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline inline-flex items-center gap-0.5"
                      >
                        instagram.com <ExternalLink className="w-3 h-3" />
                      </a>
                      {' '}di Chrome/Firefox dan login sebagai <strong>@{username}</strong>.
                    </p>
                  </div>
                </div>

                {/* Step 2 */}
                <div className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-7 h-7 rounded-full bg-orange-500 text-white text-xs font-bold flex items-center justify-center">2</span>
                  <div className="text-sm">
                    <p className="font-medium text-gray-900">Install extension "Cookie-Editor"</p>
                    <p className="text-gray-500 mt-0.5">
                      Install dari Chrome Web Store:
                    </p>
                    <a
                      href="https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-sm text-blue-600 hover:bg-blue-50 transition-colors"
                    >
                      <Globe className="w-4 h-4" />
                      Cookie-Editor — Chrome Web Store
                      <ExternalLink className="w-3 h-3" />
                    </a>
                    <p className="text-gray-400 mt-1 text-xs">
                      Juga tersedia untuk Firefox, Edge, dan Safari.
                    </p>
                  </div>
                </div>

                {/* Step 3 */}
                <div className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-7 h-7 rounded-full bg-orange-500 text-white text-xs font-bold flex items-center justify-center">3</span>
                  <div className="text-sm">
                    <p className="font-medium text-gray-900">Export cookies dari Instagram</p>
                    <p className="text-gray-500 mt-0.5">
                      Pastikan kamu di halaman instagram.com, lalu:
                    </p>
                    <ol className="mt-1 ml-4 list-decimal text-gray-500 space-y-0.5">
                      <li>Klik icon Cookie-Editor di toolbar</li>
                      <li>Klik tombol <strong>"Export"</strong> (icon panah ke bawah)</li>
                      <li>Pilih format <strong>"JSON"</strong></li>
                      <li>Cookies otomatis ter-copy ke clipboard</li>
                    </ol>
                  </div>
                </div>

                {/* Step 4 */}
                <div className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-7 h-7 rounded-full bg-orange-500 text-white text-xs font-bold flex items-center justify-center">4</span>
                  <div className="text-sm flex items-center gap-1.5">
                    <ClipboardPaste className="w-4 h-4 text-gray-700" />
                    <p className="font-medium text-gray-900">Paste di halaman berikutnya</p>
                  </div>
                </div>
              </div>

              {/* Alternative: DevTools method */}
              <div className="border border-gray-200 rounded-lg overflow-hidden">
                <button
                  onClick={() => setShowDevTools(!showDevTools)}
                  className="w-full flex items-center justify-between px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  <span>Alternatif: Tanpa extension (DevTools)</span>
                  {showDevTools ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
                {showDevTools && (
                  <div className="px-3 pb-3 text-xs text-gray-500 space-y-1 border-t">
                    <p className="mt-2">Di Chrome/Firefox, buka instagram.com lalu:</p>
                    <ol className="ml-4 list-decimal space-y-0.5">
                      <li>Tekan <kbd className="px-1 py-0.5 bg-gray-100 rounded text-[10px]">F12</kbd> untuk buka DevTools</li>
                      <li>Buka tab <strong>Application</strong> (Chrome) atau <strong>Storage</strong> (Firefox)</li>
                      <li>Di sidebar kiri, expand <strong>Cookies</strong> → klik <strong>https://www.instagram.com</strong></li>
                      <li>Minimal catat 3 cookie ini:</li>
                    </ol>
                    <div className="mt-1 ml-4 font-mono text-[10px] bg-gray-50 rounded p-2 space-y-0.5">
                      <p><strong>sessionid</strong> = (value panjang)</p>
                      <p><strong>ds_user_id</strong> = (angka)</p>
                      <p><strong>csrftoken</strong> = (value panjang)</p>
                    </div>
                    <p className="mt-1">Lalu paste manual dalam format JSON:</p>
                    <pre className="mt-1 bg-gray-50 rounded p-2 overflow-x-auto text-[10px] leading-relaxed">{`[
  {"name":"sessionid","value":"PASTE_HERE","domain":".instagram.com","path":"/"},
  {"name":"ds_user_id","value":"PASTE_HERE","domain":".instagram.com","path":"/"},
  {"name":"csrftoken","value":"PASTE_HERE","domain":".instagram.com","path":"/"}
]`}</pre>
                  </div>
                )}
              </div>

              {/* Continue */}
              <div className="flex gap-2 pt-2">
                <button
                  onClick={onClose}
                  className="flex-1 py-3 px-4 bg-gray-100 text-gray-700 font-semibold rounded-xl hover:bg-gray-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => setStep('paste')}
                  className="flex-1 py-3 px-4 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-semibold rounded-xl hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
                >
                  Sudah Copy Cookies
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* ====================== PASTE STEP ====================== */}
          {step === 'paste' && (
            <div className="space-y-4">
              <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <ClipboardPaste className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-amber-800">
                  <p className="font-medium">Paste Cookie JSON</p>
                  <p className="mt-0.5">
                    Paste hasil export dari Cookie-Editor (Ctrl+V) ke textarea di bawah.
                  </p>
                </div>
              </div>

              <div>
                <textarea
                  value={cookieJson}
                  onChange={(e) => {
                    setCookieJson(e.target.value)
                    setParseError('')
                  }}
                  placeholder={'[\n  {"name":"sessionid","value":"...","domain":".instagram.com","path":"/"},\n  {"name":"ds_user_id","value":"...","domain":".instagram.com","path":"/"},\n  ...\n]'}
                  className={`w-full h-48 px-3 py-2 border-2 rounded-xl font-mono text-xs resize-none focus:outline-none focus:ring-2 ${
                    parseError
                      ? 'border-red-300 focus:ring-red-200 focus:border-red-400'
                      : 'border-gray-200 focus:ring-amber-200 focus:border-amber-400'
                  }`}
                  autoFocus
                />
                {parseError && (
                  <p className="mt-1 text-xs text-red-600 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    {parseError}
                  </p>
                )}
              </div>

              {/* Cookie count preview */}
              {cookieJson.trim() && !parseError && (() => {
                try {
                  const arr = JSON.parse(cookieJson.trim())
                  if (Array.isArray(arr)) {
                    const names = arr.map((c: Record<string, unknown>) => c.name).filter(Boolean)
                    const hasSession = names.includes('sessionid')
                    const hasDsUser = names.includes('ds_user_id')
                    return (
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-gray-500">{arr.length} cookies detected</span>
                        {hasSession && <span className="px-1.5 py-0.5 bg-green-100 text-green-700 rounded">sessionid ✓</span>}
                        {hasDsUser && <span className="px-1.5 py-0.5 bg-green-100 text-green-700 rounded">ds_user_id ✓</span>}
                        {!hasSession && <span className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded">sessionid ✗</span>}
                        {!hasDsUser && <span className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded">ds_user_id ✗</span>}
                      </div>
                    )
                  }
                } catch { /* ignore */ }
                return null
              })()}

              <div className="flex gap-2">
                <button
                  onClick={() => setStep('tutorial')}
                  className="flex-1 py-3 px-4 bg-gray-100 text-gray-700 font-semibold rounded-xl hover:bg-gray-200 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={handleImport}
                  disabled={!cookieJson.trim()}
                  className="flex-1 py-3 px-4 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-semibold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <Copy className="w-4 h-4" />
                  Import Cookies
                </button>
              </div>
            </div>
          )}

          {/* ====================== IMPORTING ====================== */}
          {step === 'importing' && (
            <div className="text-center space-y-3 py-8">
              <Loader2 className="w-10 h-10 animate-spin text-amber-500 mx-auto" />
              <p className="text-sm text-gray-600">Importing cookies & verifying session...</p>
              <p className="text-xs text-gray-400">This may take 10-30 seconds</p>
            </div>
          )}

          {/* ====================== SUCCESS ====================== */}
          {step === 'success' && (
            <div className="text-center space-y-4 py-4">
              <CheckCircle2 className="w-14 h-14 text-green-500 mx-auto" />
              <div>
                <p className="font-semibold text-green-700">Session Imported Successfully!</p>
                <p className="text-sm text-gray-500 mt-1">
                  @{username} is now connected on this server.
                </p>
                {result?.verify?.username_verified && (
                  <p className="text-xs text-gray-400 mt-1">
                    Verified as: @{result.verify.username_verified}
                  </p>
                )}
              </div>
              <button
                onClick={onClose}
                className="w-full py-3 px-4 bg-green-500 text-white font-semibold rounded-xl hover:bg-green-600 transition-colors"
              >
                Done
              </button>
            </div>
          )}

          {/* ====================== ERROR ====================== */}
          {step === 'error' && (
            <div className="space-y-4 py-4">
              <div className="text-center">
                <AlertCircle className="w-14 h-14 text-red-400 mx-auto" />
                <p className="font-semibold text-red-700 mt-2">Import Failed</p>
                <p className="text-sm text-gray-500 mt-1">{errorMsg}</p>
              </div>

              {result && (
                <div className="text-xs text-gray-400 p-2 bg-gray-50 rounded-lg font-mono">
                  {result.import?.message && <p>Import: {result.import.message}</p>}
                  {result.verify?.reason && <p>Verify: {result.verify.reason}</p>}
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={handleReset}
                  className="flex-1 py-3 px-4 bg-gray-100 text-gray-700 font-semibold rounded-xl hover:bg-gray-200 transition-colors"
                >
                  Try Again
                </button>
                <button
                  onClick={onClose}
                  className="flex-1 py-3 px-4 bg-gray-100 text-gray-700 font-semibold rounded-xl hover:bg-gray-200 transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
