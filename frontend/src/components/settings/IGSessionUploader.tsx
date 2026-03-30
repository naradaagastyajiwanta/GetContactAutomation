import { useState, useCallback, useEffect } from 'react'
import {
  Cookie,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  ShieldCheck,
  ShieldX,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Info,
} from 'lucide-react'
import { Card, CardHeader, CardTitle } from '../ui/Card'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { Modal } from '../ui/Modal'
import { apiClient } from '../../api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SessionStatus {
  ok: boolean
  total: number
  healthy: number
  error: string | null
  sessions: Array<{ label: string; ok: boolean; error: string | null }>
}

interface SessionItem {
  id: string
  value: string
  visible: boolean
}

// ---------------------------------------------------------------------------
// Add Session Modal
// ---------------------------------------------------------------------------

function AddSessionModal({
  isOpen,
  onClose,
  onAdd,
}: {
  isOpen: boolean
  onClose: () => void
  onAdd: (sessionId: string) => void
}) {
  const [value, setValue] = useState('')
  const [showValue, setShowValue] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed) {
      setError('Session ID cannot be empty')
      return
    }
    if (!trimmed.includes('%') && trimmed.length < 50) {
      setError('This does not look like a valid sessionid cookie value')
      return
    }
    onAdd(trimmed)
    setValue('')
    setError('')
    onClose()
  }

  if (!isOpen) return null

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add Instagram Session" size="sm">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex items-start gap-2.5 p-3 bg-blue-50 border border-blue-200 rounded-xl text-xs text-blue-800">
          <Info className="w-4 h-4 mt-0.5 flex-shrink-0 text-blue-500" />
          <p>
            Paste value dari cookie <strong>sessionid</strong> yang sudah di-export dari browser.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
            Session ID (sessionid cookie value)
          </label>
          <div className="relative">
            <input
              type={showValue ? 'text' : 'password'}
              value={value}
              onChange={(e) => {
                setValue(e.target.value)
                setError('')
              }}
              placeholder="5827398253%3AABCdefGHIjklMNOpqrSTUvwxYZ01234..."
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 pr-10 text-sm font-mono text-gray-900 focus:border-pink-500 focus:ring-pink-200 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 placeholder:text-gray-400 placeholder:font-sans"
              autoFocus
            />
            <button
              type="button"
              onClick={() => setShowValue(!showValue)}
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              {showValue ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {error && (
            <p className="mt-1 text-xs text-red-600 flex items-center gap-1">
              <AlertCircle className="h-3 w-3" />
              {error}
            </p>
          )}
        </div>

        <p className="text-xs text-gray-400">
          Tidak yakin?{' '}
          <a
            href="https://github.com/logcorner/articles/blob/master/instagram-cookies.md"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline"
          >
            Lihat tutorial cara dapat sessionid
          </a>
        </p>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={!value.trim()}>
            <Cookie className="h-4 w-4" />
            Add Session
          </Button>
        </div>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function IGSessionUploader() {
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [status, setStatus] = useState<SessionStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)

  // Load sessions from config + status
  const fetchSessions = useCallback(async () => {
    setError('')
    try {
      const [cfgRes, statusRes] = await Promise.all([
        apiClient.get('/config/IG_SESSION_ID'),
        apiClient.get('/instagram/session-status'),
      ])
      const raw = cfgRes.data?.value ?? ''
      const parts = raw.split(',').map((s: string) => s.trim()).filter(Boolean)
      setSessions(
        parts.map((v: string, i: number) => ({
          id: `${i}-${v.slice(0, 10)}`,
          value: v,
          visible: false,
        }))
      )
      setStatus(statusRes.data)
    } catch {
      setError('Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  const handleAddSession = async (sessionId: string) => {
    const newSessions = [...sessions.map((s) => ({ ...s, visible: false })), {
      id: `${Date.now()}-${sessionId.slice(0, 10)}`,
      value: sessionId,
      visible: false,
    }]
    await saveSessions(newSessions)
  }

  const handleRemoveSession = async (id: string) => {
    const newSessions = sessions.filter((s) => s.id !== id)
    await saveSessions(newSessions)
  }

  const saveSessions = async (newSessions: SessionItem[]) => {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const raw = newSessions.map((s) => s.value).join(', ')
      await apiClient.patch('/config', {
        settings: { IG_SESSION_ID: raw },
      })
      setSessions(newSessions.map((s) => ({ ...s, visible: false })))
      setSuccess('Sessions saved! Refresh status in a moment.')
      // Reset pool
      await apiClient.post('/instagram/reset-sessions')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Save failed'
      setError(msg)
    } finally {
      setSaving(false)
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await apiClient.post('/instagram/reset-sessions')
      await fetchSessions()
    } catch {
      setError('Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  const healthyCount = status?.sessions?.filter((s) => s.ok).length ?? 0
  const totalCount = sessions.length

  return (
    <>
      <AddSessionModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onAdd={handleAddSession}
      />

      <Card padding={false}>
        <CardHeader className="flex flex-row items-center justify-between px-5 pt-5">
          <div className="flex items-center gap-2">
            <Cookie className="h-5 w-5 text-pink-500" />
            <CardTitle>Instagram Sessions</CardTitle>
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
            ) : (
              <Badge
                variant={
                  healthyCount > 0
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
                    : totalCount > 0
                      ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
                      : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                }
              >
                {healthyCount > 0
                  ? `${healthyCount}/${totalCount} active`
                  : totalCount > 0
                    ? 'Failed'
                    : 'Not configured'}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleRefresh}
              disabled={refreshing || loading}
              className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300 disabled:opacity-40 transition-colors"
              title="Refresh status"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <Button size="sm" onClick={() => setShowAddModal(true)}>
              <Plus className="h-4 w-4" />
              Add Session
            </Button>
          </div>
        </CardHeader>

        <div className="px-5 pb-5 space-y-3">
          {/* Info */}
          <div className="flex items-start gap-2.5 p-3 bg-blue-50 border border-blue-200 rounded-xl text-xs text-blue-800">
            <Info className="w-4 h-4 mt-0.5 flex-shrink-0 text-blue-500" />
            <p>
              Tambahkan session cookie dari browser. Tidak perlu username/password.
              Multiple sessions membantu menghindari rate limit — sistem auto-rotates.
            </p>
          </div>

          {/* Success / error */}
          {error && (
            <div className="flex items-center gap-2 text-xs text-red-600 dark:text-red-400 p-2 rounded-lg bg-red-50 dark:bg-red-900/20">
              <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
              {error}
            </div>
          )}
          {success && (
            <div className="flex items-center gap-2 text-xs text-green-600 dark:text-green-400 p-2 rounded-lg bg-green-50 dark:bg-green-900/20">
              <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
              {success}
            </div>
          )}

          {/* Session list */}
          {loading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="rounded-xl border-2 border-dashed border-gray-200 p-6 text-center dark:border-gray-700">
              <Cookie className="mx-auto h-8 w-8 text-gray-300 dark:text-gray-600" />
              <p className="mt-2 text-sm font-medium text-gray-500 dark:text-gray-400">
                No sessions configured
              </p>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                Add your first Instagram session cookie to start scraping
              </p>
              <Button size="sm" className="mt-3" onClick={() => setShowAddModal(true)}>
                <Plus className="h-4 w-4" />
                Add First Session
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              {sessions.map((session, idx) => {
                const sessionStatus = status?.sessions?.[idx]
                const isHealthy = sessionStatus?.ok === true
                const isFailed = sessionStatus?.ok === false

                return (
                  <div
                    key={session.id}
                    className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors ${
                      isHealthy
                        ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/10'
                        : isFailed
                          ? 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/10'
                          : 'border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-700/30'
                    }`}
                  >
                    {/* Status icon */}
                    {isHealthy ? (
                      <ShieldCheck className="h-4 w-4 text-green-500 flex-shrink-0" />
                    ) : isFailed ? (
                      <ShieldX className="h-4 w-4 text-red-500 flex-shrink-0" />
                    ) : (
                      <Cookie className="h-4 w-4 text-gray-400 flex-shrink-0" />
                    )}

                    {/* Session value */}
                    <div className="flex-1 min-w-0">
                      <code className="text-xs font-mono text-gray-700 dark:text-gray-300 truncate block">
                        {session.visible
                          ? session.value
                          : session.value.slice(0, 20) + '...' + session.value.slice(-10)}
                      </code>
                      {isFailed && sessionStatus?.error && (
                        <p className="text-[10px] text-red-500 mt-0.5 truncate">
                          {sessionStatus.error}
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        type="button"
                        onClick={() =>
                          setSessions((prev) =>
                            prev.map((s) =>
                              s.id === session.id ? { ...s, visible: !s.visible } : s
                            )
                          )
                        }
                        className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                        title={session.visible ? 'Hide' : 'Show'}
                      >
                        {session.visible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRemoveSession(session.id)}
                        disabled={saving}
                        className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-40"
                        title="Remove"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Save indicator */}
          {saving && (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Saving...
            </div>
          )}

          {/* Hint */}
          {sessions.length > 0 && (
            <p className="text-[10px] text-gray-400 text-center">
              Sessions auto-rotate when one gets rate-limited or suspended.
              Add 2-3 sessions for best results.
            </p>
          )}
        </div>
      </Card>
    </>
  )
}
