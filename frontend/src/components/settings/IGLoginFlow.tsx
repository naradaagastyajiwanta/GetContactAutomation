import { useState, useCallback } from 'react'
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  LogIn,
  ShieldCheck,
  X,
  Eye,
  EyeOff,
  RefreshCw,
  CloudOff,
  Download,
  Upload,
  ArrowRight,
  Monitor,
  Server,
} from 'lucide-react'
import { loginIGAccount, type LoginResult, type ChallengeResult } from '../../api/igAccounts'
import { submitLoginChallenge } from '../../api/igAccounts'
import { useQueryClient } from '@tanstack/react-query'

interface Props {
  accountId: number
  username: string
  onClose: () => void
  onDone?: (status: 'success' | 'failed', message: string) => void
}

type FlowState = 'idle' | 'logging_in' | 'challenge' | 'submitting' | 'success' | 'failed' | 'ip_blocked'

export function IGLoginFlow({ accountId, username, onClose, onDone }: Props) {
  const [state, setState] = useState<FlowState>('idle')
  const [message, setMessage] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [showScreenshot, setShowScreenshot] = useState(false)
  const queryClient = useQueryClient()

  const handleLogin = useCallback(async () => {
    setState('logging_in')
    setMessage('Logging in to Instagram...')

    try {
      const result: LoginResult = await loginIGAccount(accountId)
      queryClient.invalidateQueries({ queryKey: ['ig-accounts'] })

      switch (result.status) {
        case 'success':
          setState('success')
          setMessage(result.message)
          onDone?.('success', result.message)
          break

        case 'challenge':
          setState('challenge')
          setMessage(result.message)
          setSessionId(result.session_id)
          setScreenshot(result.screenshot)
          break

        case 'ip_blocked':
          setState('ip_blocked')
          setMessage(result.message)
          setScreenshot(result.screenshot)
          break

        case 'failed':
          setState('failed')
          setMessage(result.message)
          setScreenshot(result.screenshot)
          onDone?.('failed', result.message)
          break

        default:
          setState('failed')
          setMessage('Unexpected response from server.')
      }
    } catch (err: unknown) {
      setState('failed')
      const errMsg = err instanceof Error ? err.message : 'Connection error'
      setMessage(errMsg)
      onDone?.('failed', errMsg)
    }
  }, [accountId, queryClient, onDone])

  const handleSubmitCode = useCallback(async () => {
    if (!sessionId || !code.trim()) return

    setState('submitting')
    setMessage('Submitting verification code...')

    try {
      const result: ChallengeResult = await submitLoginChallenge(accountId, sessionId, code.trim())
      queryClient.invalidateQueries({ queryKey: ['ig-accounts'] })

      if (result.status === 'success') {
        setState('success')
        setMessage(result.message)
        setScreenshot(null)
        onDone?.('success', result.message)
      } else {
        setState('challenge')
        setMessage(result.message)
        setCode('')
        if (result.screenshot) setScreenshot(result.screenshot)
      }
    } catch (err: unknown) {
      setState('failed')
      const errMsg = err instanceof Error ? err.message : 'Connection error'
      setMessage(errMsg)
    }
  }, [accountId, sessionId, code, queryClient, onDone])

  const handleRetry = useCallback(() => {
    setState('idle')
    setMessage('')
    setSessionId(null)
    setScreenshot(null)
    setCode('')
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b bg-gradient-to-r from-purple-500 via-pink-500 to-orange-400">
          <div className="flex items-center gap-2">
            <LogIn className="w-5 h-5 text-white" />
            <span className="text-white font-semibold">Login Instagram</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-full hover:bg-white/20 transition-colors"
            title="Close"
          >
            <X className="w-5 h-5 text-white" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Account info */}
          <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-400 to-pink-400 flex items-center justify-center">
              <span className="text-white font-bold text-lg">
                {username.charAt(0).toUpperCase()}
              </span>
            </div>
            <div>
              <p className="font-semibold text-gray-900">@{username}</p>
              <p className="text-xs text-gray-500">
                {state === 'idle' && 'Ready to login'}
                {state === 'logging_in' && 'Connecting...'}
                {state === 'challenge' && 'Verification required'}
                {state === 'submitting' && 'Verifying code...'}
                {state === 'success' && 'Connected'}
                {state === 'failed' && 'Login failed'}
                {state === 'ip_blocked' && 'Server IP blocked'}
              </p>
            </div>
          </div>

          {/* ---- IDLE STATE ---- */}
          {state === 'idle' && (
            <div className="text-center space-y-4">
              <p className="text-sm text-gray-600">
                Click the button below to login. The system will use your saved
                credentials to authenticate with Instagram.
              </p>
              <button
                onClick={handleLogin}
                className="w-full py-3 px-4 bg-gradient-to-r from-purple-500 via-pink-500 to-orange-400 text-white font-semibold rounded-xl hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
              >
                <LogIn className="w-5 h-5" />
                Login to Instagram
              </button>
            </div>
          )}

          {/* ---- LOGGING IN ---- */}
          {state === 'logging_in' && (
            <div className="text-center space-y-3 py-4">
              <Loader2 className="w-10 h-10 animate-spin text-pink-500 mx-auto" />
              <p className="text-sm text-gray-600">{message}</p>
              <p className="text-xs text-gray-400">This may take 10-30 seconds...</p>
            </div>
          )}

          {/* ---- CHALLENGE STATE ---- */}
          {state === 'challenge' && (
            <div className="space-y-4">
              <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <ShieldCheck className="w-5 h-5 text-amber-500 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-amber-800">
                  <p className="font-medium">Verification Required</p>
                  <p className="mt-1">{message}</p>
                </div>
              </div>

              {/* Screenshot toggle */}
              {screenshot && (
                <div>
                  <button
                    onClick={() => setShowScreenshot(!showScreenshot)}
                    className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
                  >
                    {showScreenshot ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    {showScreenshot ? 'Hide' : 'Show'} verification page screenshot
                  </button>
                  {showScreenshot && (
                    <div className="mt-2 rounded-lg overflow-hidden border border-gray-200">
                      <img
                        src={`data:image/jpeg;base64,${screenshot}`}
                        alt="Instagram verification page"
                        className="w-full"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* Code input */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Verification Code
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
                  placeholder="Enter 6-digit code"
                  className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:border-pink-400 focus:ring-2 focus:ring-pink-200 outline-none text-center text-2xl tracking-[0.5em] font-mono"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && code.length >= 6) handleSubmitCode()
                  }}
                />
              </div>

              <button
                onClick={handleSubmitCode}
                disabled={code.length < 6}
                className="w-full py-3 px-4 bg-gradient-to-r from-purple-500 via-pink-500 to-orange-400 text-white font-semibold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                <ShieldCheck className="w-5 h-5" />
                Submit Code
              </button>
            </div>
          )}

          {/* ---- SUBMITTING CODE ---- */}
          {state === 'submitting' && (
            <div className="text-center space-y-3 py-4">
              <Loader2 className="w-10 h-10 animate-spin text-pink-500 mx-auto" />
              <p className="text-sm text-gray-600">{message}</p>
            </div>
          )}

          {/* ---- SUCCESS ---- */}
          {state === 'success' && (
            <div className="text-center space-y-4 py-4">
              <CheckCircle2 className="w-14 h-14 text-green-500 mx-auto" />
              <div>
                <p className="font-semibold text-green-700">Login Successful!</p>
                <p className="text-sm text-gray-500 mt-1">{message}</p>
              </div>
              <button
                onClick={onClose}
                className="w-full py-3 px-4 bg-green-500 text-white font-semibold rounded-xl hover:bg-green-600 transition-colors"
              >
                Done
              </button>
            </div>
          )}

          {/* ---- IP BLOCKED STATE (datacenter/VPS) ---- */}
          {state === 'ip_blocked' && (
            <div className="space-y-4">
              <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-300 rounded-xl">
                <CloudOff className="w-6 h-6 text-amber-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-amber-800">Server IP Blocked by Instagram</p>
                  <p className="text-sm text-amber-700 mt-1">
                    Instagram blocks logins from cloud/VPS servers.
                    This is not a password issue — use <strong>Session Sync</strong> instead.
                  </p>
                </div>
              </div>

              {/* Step-by-step guide */}
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
                <p className="font-semibold text-blue-800 text-sm">How to fix with Session Sync:</p>
                <div className="space-y-2.5">
                  <div className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500 text-white text-xs font-bold flex items-center justify-center">1</span>
                    <div className="text-sm text-blue-800">
                      <div className="flex items-center gap-1.5">
                        <Monitor className="w-4 h-4" />
                        <span className="font-medium">Login on your local PC</span>
                      </div>
                      <p className="text-blue-600 mt-0.5">
                        Open this dashboard on <code className="bg-blue-100 px-1 rounded">localhost</code> and login to @{username} there.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500 text-white text-xs font-bold flex items-center justify-center">2</span>
                    <div className="text-sm text-blue-800">
                      <div className="flex items-center gap-1.5">
                        <Download className="w-4 h-4" />
                        <span className="font-medium">Export session from local</span>
                      </div>
                      <p className="text-blue-600 mt-0.5">
                        Click the <Download className="w-3.5 h-3.5 inline" /> download button in the Actions column.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center justify-center text-blue-400">
                    <ArrowRight className="w-4 h-4" />
                  </div>

                  <div className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500 text-white text-xs font-bold flex items-center justify-center">3</span>
                    <div className="text-sm text-blue-800">
                      <div className="flex items-center gap-1.5">
                        <Upload className="w-4 h-4" />
                        <span className="font-medium">Import session on this server</span>
                      </div>
                      <p className="text-blue-600 mt-0.5">
                        Click the <Upload className="w-3.5 h-3.5 inline" /> upload button in the Actions column to upload the exported file.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-green-500 text-white text-xs font-bold flex items-center justify-center">✓</span>
                    <div className="text-sm text-blue-800">
                      <div className="flex items-center gap-1.5">
                        <Server className="w-4 h-4" />
                        <span className="font-medium">Session auto-verified</span>
                      </div>
                      <p className="text-blue-600 mt-0.5">
                        The server will verify the imported session works without re-logging in.
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Diagnostic screenshot */}
              {screenshot && (
                <div>
                  <button
                    onClick={() => setShowScreenshot(!showScreenshot)}
                    className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
                  >
                    {showScreenshot ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    {showScreenshot ? 'Hide' : 'Show'} what Instagram showed
                  </button>
                  {showScreenshot && (
                    <div className="mt-2 rounded-lg overflow-hidden border border-gray-200">
                      <img
                        src={`data:image/jpeg;base64,${screenshot}`}
                        alt="Instagram page screenshot"
                        className="w-full"
                      />
                    </div>
                  )}
                </div>
              )}

              <button
                onClick={onClose}
                className="w-full py-3 px-4 bg-blue-500 text-white font-semibold rounded-xl hover:bg-blue-600 transition-colors"
              >
                Got it — I'll use Session Sync
              </button>
            </div>
          )}

          {/* ---- FAILED ---- */}
          {state === 'failed' && (
            <div className="space-y-4 py-4">
              <div className="text-center">
                <AlertCircle className="w-14 h-14 text-red-400 mx-auto" />
                <p className="font-semibold text-red-700 mt-2">Login Failed</p>
                <p className="text-sm text-gray-500 mt-1">{message}</p>
              </div>

              {/* Hint about session sync */}
              <div className="flex items-start gap-2 p-3 bg-gray-50 border border-gray-200 rounded-lg">
                <CloudOff className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-gray-500">
                  If the password is correct but login still fails, your server IP may be blocked.
                  Try using <strong>Session Sync</strong> (export from local, import here) via the table actions.
                </p>
              </div>

              {/* Diagnostic screenshot if available */}
              {screenshot && (
                <div>
                  <button
                    onClick={() => setShowScreenshot(!showScreenshot)}
                    className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1 mx-auto"
                  >
                    {showScreenshot ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    {showScreenshot ? 'Hide' : 'Show'} what Instagram showed
                  </button>
                  {showScreenshot && (
                    <div className="mt-2 rounded-lg overflow-hidden border border-gray-200">
                      <img
                        src={`data:image/jpeg;base64,${screenshot}`}
                        alt="Instagram page screenshot"
                        className="w-full"
                      />
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={handleRetry}
                  className="flex-1 py-3 px-4 bg-gray-100 text-gray-700 font-semibold rounded-xl hover:bg-gray-200 transition-colors flex items-center justify-center gap-2"
                >
                  <RefreshCw className="w-4 h-4" />
                  Retry
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
