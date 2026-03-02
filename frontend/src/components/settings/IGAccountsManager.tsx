import { useState, useRef } from 'react'
import {
  Plus,
  Trash2,
  Eye,
  EyeOff,
  ToggleLeft,
  ToggleRight,
  Timer,
  Instagram,
  RefreshCw,
  ShieldCheck,
  ShieldX,
  ShieldQuestion,
  ShieldAlert,
  Loader2,
  Play,
  AlertCircle,
  X,
  CheckCircle2,
  Download,
  Upload,
} from 'lucide-react'
import { Card, CardHeader, CardTitle } from '../ui/Card'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { Modal } from '../ui/Modal'
import { Spinner } from '../ui/Spinner'
import {
  useIGAccounts,
  useCreateIGAccount,
  useUpdateIGAccount,
  useDeleteIGAccount,
} from '../../hooks/useIGAccounts'
import type { IGAccount, IGAccountPoolStatus } from '../../api/igAccounts'
import { exportIGSession, importIGSession } from '../../api/igAccounts'
import { IGLoginFlow } from './IGLoginFlow'

// ---------------------------------------------------------------------------
// Add / Edit form modal
// ---------------------------------------------------------------------------

function AccountFormModal({
  isOpen,
  onClose,
  onCreated,
  initial,
}: {
  isOpen: boolean
  onClose: () => void
  onCreated?: (accountId: number) => void
  initial?: IGAccount
}) {
  const [username, setUsername] = useState(initial?.username ?? '')
  const [password, setPassword] = useState('')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [showPw, setShowPw] = useState(false)

  const createMut = useCreateIGAccount()
  const updateMut = useUpdateIGAccount()
  const isLoading = createMut.isPending || updateMut.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (initial) {
      // Update — only send fields that changed
      const payload: Record<string, unknown> = { id: initial.id }
      if (username && username !== initial.username) payload.username = username
      if (password) payload.password = password
      if (notes !== initial.notes) payload.notes = notes
      updateMut.mutate(payload as any, { onSuccess: () => onClose() })
    } else {
      createMut.mutate(
        { username: username.trim(), password, notes },
        {
          onSuccess: (data) => {
            onClose()
            // Auto-trigger login test for newly created account
            if (onCreated && data.account?.id) {
              onCreated(data.account.id)
            }
          },
        },
      )
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={initial ? 'Edit IG Account' : 'Add IG Account'} size="sm">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Username
          </label>
          <div className="flex items-center">
            <span className="inline-flex items-center rounded-l-md border border-r-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-400">
              @
            </span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value.replace(/^@/, ''))}
              placeholder="instagram_username"
              required={!initial}
              className="block w-full rounded-r-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Password {initial && <span className="text-gray-400">(leave blank to keep current)</span>}
          </label>
          <div className="relative">
            <input
              type={showPw ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={initial ? '••••••••' : 'Enter password'}
              required={!initial}
              className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 pr-10 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
            <button
              type="button"
              onClick={() => setShowPw(!showPw)}
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Notes <span className="text-gray-400">(optional)</span>
          </label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. alt account, main account..."
            className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" loading={isLoading}>
            {initial ? 'Save Changes' : 'Add Account'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Status badge for pool runtime state
// ---------------------------------------------------------------------------

function PoolStatusBadge({ poolInfo }: { poolInfo?: IGAccountPoolStatus }) {
  if (!poolInfo) {
    return (
      <Badge variant="bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400">
        Not in pool
      </Badge>
    )
  }
  if (!poolInfo.login_ok) {
    return (
      <Badge variant="bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">
        Login Failed
      </Badge>
    )
  }
  if (poolInfo.cooldown_remaining_s > 0) {
    const mins = Math.ceil(poolInfo.cooldown_remaining_s / 60)
    return (
      <Badge variant="bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400">
        <Timer className="mr-1 h-3 w-3 inline" />
        Cooldown {mins}m
      </Badge>
    )
  }
  return (
    <Badge variant="bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400">
      Healthy
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Login verification status badge
// ---------------------------------------------------------------------------

function LoginStatusBadge({ acct, isTesting }: { acct: IGAccount; isTesting: boolean }) {
  if (isTesting) {
    return (
      <Badge variant="bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400">
        <Loader2 className="mr-1 h-3 w-3 inline animate-spin" />
        Testing...
      </Badge>
    )
  }

  const status = acct.login_status || 'untested'
  const lastTest = acct.last_login_test
    ? new Date(acct.last_login_test).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' })
    : null

  if (status === 'success') {
    return (
      <div className="flex flex-col gap-0.5">
        <Badge variant="bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400">
          <ShieldCheck className="mr-1 h-3 w-3 inline" />
          Verified
        </Badge>
        {lastTest && <span className="text-[10px] text-gray-400">{lastTest}</span>}
      </div>
    )
  }
  if (status === 'failed') {
    return (
      <div className="flex flex-col gap-0.5">
        <Badge variant="bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">
          <ShieldX className="mr-1 h-3 w-3 inline" />
          Failed
        </Badge>
        {lastTest && <span className="text-[10px] text-gray-400">{lastTest}</span>}
      </div>
    )
  }
  if (status === 'challenge') {
    return (
      <div className="flex flex-col gap-0.5">
        <Badge variant="bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400">
          <ShieldQuestion className="mr-1 h-3 w-3 inline" />
          Needs Verify
        </Badge>
        {lastTest && <span className="text-[10px] text-gray-400">{lastTest}</span>}
      </div>
    )
  }
  if (status === 'banned') {
    return (
      <div className="flex flex-col gap-0.5">
        <Badge variant="bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">
          <ShieldAlert className="mr-1 h-3 w-3 inline" />
          Banned
        </Badge>
        {lastTest && <span className="text-[10px] text-gray-400">{lastTest}</span>}
      </div>
    )
  }
  return (
    <Badge variant="bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
      <ShieldQuestion className="mr-1 h-3 w-3 inline" />
      Untested
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function IGAccountsManager() {
  const { data, isLoading, refetch } = useIGAccounts()
  const deleteMut = useDeleteIGAccount()
  const updateMut = useUpdateIGAccount()

  const [showAddModal, setShowAddModal] = useState(false)
  const [editAccount, setEditAccount] = useState<IGAccount | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [testingAccountId, setTestingAccountId] = useState<number | null>(null)
  const [lastTestResult, setLastTestResult] = useState<{
    accountId: number
    success: boolean
    message: string
  } | null>(null)
  const [loginFlowAccount, setLoginFlowAccount] = useState<{ id: number; username: string } | null>(null)
  const [syncingAccountId, setSyncingAccountId] = useState<number | null>(null)
  const importFileRef = useRef<HTMLInputElement>(null)
  const [importTargetAccount, setImportTargetAccount] = useState<{ id: number; username: string } | null>(null)

  const accounts = data?.accounts ?? []
  const poolStatus = data?.pool_status ?? []

  const poolMap = new Map<string, IGAccountPoolStatus>()
  for (const ps of poolStatus) {
    poolMap.set(ps.username, ps)
  }

  const handleToggleEnabled = (acct: IGAccount) => {
    updateMut.mutate({ id: acct.id, enabled: !acct.enabled })
  }

  const handleTestLogin = (acct: IGAccount) => {
    setLastTestResult(null)
    setLoginFlowAccount({ id: acct.id, username: acct.username })
    setTestingAccountId(acct.id)
  }

  const handleLoginDone = (status: 'success' | 'failed', message: string) => {
    setTestingAccountId(null)
    setLastTestResult({
      accountId: loginFlowAccount?.id ?? 0,
      success: status === 'success',
      message,
    })
  }

  const handleAccountCreated = (accountId: number) => {
    // Auto-test login after creating a new account — find the account
    const acct = accounts.find((a) => a.id === accountId)
    if (acct) {
      handleTestLogin(acct)
    } else {
      // Refetch first, then test
      refetch().then((res) => {
        const freshAcct = res.data?.accounts?.find((a: IGAccount) => a.id === accountId)
        if (freshAcct) handleTestLogin(freshAcct)
      })
    }
  }

  const handleDelete = (id: number) => {
    deleteMut.mutate(id, { onSuccess: () => setConfirmDeleteId(null) })
  }

  const handleExportSession = async (acct: IGAccount) => {
    setSyncingAccountId(acct.id)
    try {
      await exportIGSession(acct.id, acct.username)
      setLastTestResult({ accountId: acct.id, success: true, message: `Session exported for @${acct.username}` })
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Export failed'
      setLastTestResult({ accountId: acct.id, success: false, message: msg })
    } finally {
      setSyncingAccountId(null)
    }
  }

  const handleImportSession = (acct: IGAccount) => {
    setImportTargetAccount({ id: acct.id, username: acct.username })
    importFileRef.current?.click()
  }

  const handleImportFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !importTargetAccount) return
    e.target.value = '' // reset so same file can be re-selected

    setSyncingAccountId(importTargetAccount.id)
    try {
      const result = await importIGSession(importTargetAccount.id, file)
      const verified = result.verify?.status === 'connected'
      setLastTestResult({
        accountId: importTargetAccount.id,
        success: verified,
        message: verified
          ? `Session imported & verified for @${importTargetAccount.username}!`
          : `Session imported but verification ${result.verify?.status}: ${result.verify?.reason || 'unknown'}`,
      })
      refetch()
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Import failed'
      setLastTestResult({ accountId: importTargetAccount.id, success: false, message: msg })
    } finally {
      setSyncingAccountId(null)
      setImportTargetAccount(null)
    }
  }

  const healthyCount = poolStatus.filter((p) => p.healthy).length

  return (
    <>
      {/* Hidden file input for session import */}
      <input
        ref={importFileRef}
        type="file"
        accept=".tar.gz,.tgz"
        className="hidden"
        onChange={handleImportFileSelected}
      />      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-2">
            <Instagram className="h-5 w-5 text-pink-500" />
            <CardTitle>Instagram Accounts</CardTitle>
            {accounts.length > 0 && (
              <Badge variant="bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-400">
                {healthyCount}/{accounts.length} active
              </Badge>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              title="Refresh"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button size="sm" onClick={() => setShowAddModal(true)}>
              <Plus className="h-4 w-4" />
              Add Account
            </Button>
          </div>
        </CardHeader>



        {lastTestResult && (
          <div className={`mx-4 mb-2 rounded-md border px-3 py-2 text-xs ${
            lastTestResult.success
              ? 'border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400'
              : 'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400'
          }`}>
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-2">
                {lastTestResult.success ? (
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                ) : (
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                )}
                <p className="font-medium">{lastTestResult.message}</p>
              </div>
              <button
                onClick={() => setLastTestResult(null)}
                className="ml-2 flex-shrink-0 rounded p-0.5 hover:bg-black/10 dark:hover:bg-white/10"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : accounts.length === 0 ? (
          <div className="rounded-lg border-2 border-dashed border-gray-200 p-8 text-center dark:border-gray-700">
            <Instagram className="mx-auto h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="mt-2 text-sm font-medium text-gray-600 dark:text-gray-400">
              No Instagram accounts configured
            </p>
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Add accounts to enable multi-account rotation for IG scraping.
              Multiple accounts help avoid rate limits.
            </p>
            <Button size="sm" className="mt-4" onClick={() => setShowAddModal(true)}>
              <Plus className="h-4 w-4" />
              Add First Account
            </Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr className="text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  <th className="px-3 py-2">Username</th>
                  <th className="px-3 py-2">Password</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Login</th>
                  <th className="px-3 py-2">Pool</th>
                  <th className="px-3 py-2">Notes</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                {accounts.map((acct) => {
                  const pool = poolMap.get(acct.username)
                  const isTesting = testingAccountId === acct.id
                  return (
                    <tr key={acct.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                      <td className="whitespace-nowrap px-3 py-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                        @{acct.username}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-sm text-gray-500 dark:text-gray-400 font-mono">
                        {acct.password}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-sm">
                        {acct.enabled ? (
                          <Badge variant="bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400">
                            Enabled
                          </Badge>
                        ) : (
                          <Badge variant="bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                            Disabled
                          </Badge>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-sm">
                        <div className="flex items-center gap-1.5">
                          <LoginStatusBadge acct={acct} isTesting={isTesting} />
                          <button
                            onClick={() => handleTestLogin(acct)}
                            disabled={isTesting || testingAccountId !== null}
                            className="rounded p-1 text-gray-400 hover:bg-indigo-50 hover:text-indigo-600 dark:hover:bg-indigo-900/30 dark:hover:text-indigo-400 disabled:opacity-40 disabled:cursor-not-allowed"
                            title="Login to Instagram"
                          >
                            {isTesting ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Play className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-sm">
                        <PoolStatusBadge poolInfo={pool} />
                        {pool && pool.profiles_today > 0 && (
                          <span className="ml-1 text-xs text-gray-400">
                            {pool.profiles_today} today
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400 max-w-[200px] truncate">
                        {acct.notes || '—'}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleExportSession(acct)}
                            disabled={syncingAccountId !== null}
                            className="rounded p-1 text-gray-400 hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-900/30 dark:hover:text-blue-400 disabled:opacity-40 disabled:cursor-not-allowed"
                            title="Export Session (download)"
                          >
                            {syncingAccountId === acct.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Download className="h-4 w-4" />
                            )}
                          </button>
                          <button
                            onClick={() => handleImportSession(acct)}
                            disabled={syncingAccountId !== null}
                            className="rounded p-1 text-gray-400 hover:bg-emerald-50 hover:text-emerald-600 dark:hover:bg-emerald-900/30 dark:hover:text-emerald-400 disabled:opacity-40 disabled:cursor-not-allowed"
                            title="Import Session (upload .tar.gz)"
                          >
                            <Upload className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleToggleEnabled(acct)}
                            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
                            title={acct.enabled ? 'Disable' : 'Enable'}
                          >
                            {acct.enabled ? (
                              <ToggleRight className="h-4 w-4 text-green-500" />
                            ) : (
                              <ToggleLeft className="h-4 w-4" />
                            )}
                          </button>
                          <button
                            onClick={() => setEditAccount(acct)}
                            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-indigo-600 dark:hover:bg-gray-700 dark:hover:text-indigo-400"
                            title="Edit"
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => setConfirmDeleteId(acct.id)}
                            className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                            title="Delete"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Login flow modal */}
      {loginFlowAccount && (
        <IGLoginFlow
          accountId={loginFlowAccount.id}
          username={loginFlowAccount.username}
          onClose={() => {
            setLoginFlowAccount(null)
            setTestingAccountId(null)
          }}
          onDone={handleLoginDone}
        />
      )}

      {/* Add modal */}
      {showAddModal && (
        <AccountFormModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onCreated={handleAccountCreated}
        />
      )}

      {/* Edit modal */}
      {editAccount && (
        <AccountFormModal
          isOpen={!!editAccount}
          onClose={() => setEditAccount(null)}
          initial={editAccount}
        />
      )}

      {/* Delete confirmation */}
      {confirmDeleteId !== null && (
        <Modal
          isOpen
          onClose={() => setConfirmDeleteId(null)}
          title="Delete Account"
          size="sm"
        >
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Are you sure you want to remove this account? The browser profile data will remain on disk.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setConfirmDeleteId(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={deleteMut.isPending}
              onClick={() => handleDelete(confirmDeleteId)}
            >
              Delete
            </Button>
          </div>
        </Modal>
      )}
    </>
  )
}
