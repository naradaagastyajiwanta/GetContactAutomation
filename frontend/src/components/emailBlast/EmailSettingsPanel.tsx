/**
 * EmailSettingsPanel — SMTP config, letter numbering, IMAP settings.
 */

import { useState, useEffect } from 'react'
import {
  Settings,
  Mail,
  Hash,
  Plus,
  Pencil,
  Trash2,
  Eye,
  EyeOff,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Save,
} from 'lucide-react'
import {
  useLetterConfig,
  useUpdateLetterConfig,
  useTestSmtp,
  useManagedSMTPAccounts,
  useCreateManagedSMTPAccount,
  useCheckAllManagedSMTPAccounts,
  useUpdateManagedSMTPAccount,
  useDeleteManagedSMTPAccount,
  useTestManagedSMTPAccount,
} from '../../hooks/useEmailBlast'
import { useConfig, useUpdateConfig } from '../../hooks/useConfig'
import { Spinner } from '../ui/Spinner'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { toast } from 'react-hot-toast'
import type { ManagedSMTPAccount } from '../../api/emailBlast'

function getHealthBadge(account: ManagedSMTPAccount) {
  if (!account.enabled) {
    return {
      label: 'Disabled',
      className: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
    }
  }

  switch (account.health_status) {
    case 'healthy':
      return {
        label: 'Healthy',
        className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
      }
    case 'error':
      return {
        label: 'Unreachable',
        className: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
      }
    case 'checking':
      return {
        label: 'Checking',
        className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
      }
    default:
      return {
        label: 'Unknown',
        className: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
      }
  }
}

function formatHealthTimestamp(value?: string | null) {
  if (!value) {
    return 'Belum pernah'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function formatCooldown(seconds?: number) {
  if (!seconds || seconds <= 0) {
    return 'Ready'
  }

  if (seconds < 60) {
    return `${seconds.toFixed(0)} detik`
  }

  const minutes = Math.floor(seconds / 60)
  const remainder = Math.round(seconds % 60)
  return remainder > 0 ? `${minutes}m ${remainder}d` : `${minutes} menit`
}

function describeSkipReason(reason?: string | null) {
  if (!reason) {
    return 'Eligible'
  }

  if (reason === 'disabled') return 'Disabled'
  if (reason === 'degraded') return 'SMTP error/auth issue'
  if (reason === 'daily_limit') return 'Daily mailbox cap reached'
  if (reason.startsWith('cooldown:')) {
    const [, rawSeconds] = reason.split(':')
    const seconds = Number.parseFloat(rawSeconds)
    return `Cooling down ${formatCooldown(seconds)}`
  }

  return reason
}

function SMTPAccountFormModal({
  isOpen,
  onClose,
  initial,
}: {
  isOpen: boolean
  onClose: () => void
  initial?: ManagedSMTPAccount | null
}) {
  const createMutation = useCreateManagedSMTPAccount()
  const updateMutation = useUpdateManagedSMTPAccount()
  const [host, setHost] = useState('mail.asosiasi.ai')
  const [port, setPort] = useState('465')
  const [user, setUser] = useState('')
  const [password, setPassword] = useState('')
  const [useSsl, setUseSsl] = useState(true)
  const [fromName, setFromName] = useState('Sekretariat Asosiasi AI')
  const [enabled, setEnabled] = useState(true)
  const [notes, setNotes] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  useEffect(() => {
    if (!isOpen) {
      return
    }

    setHost(initial?.host ?? 'mail.asosiasi.ai')
    setPort(String(initial?.port ?? 465))
    setUser(initial?.user ?? '')
    setPassword('')
    setUseSsl(initial?.use_ssl ?? true)
    setFromName(initial?.from_name ?? 'Sekretariat Asosiasi AI')
    setEnabled(initial?.enabled ?? true)
    setNotes(initial?.notes ?? '')
    setShowPassword(false)
  }, [initial, isOpen])

  const isLoading = createMutation.isPending || updateMutation.isPending

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const payload = {
      host: host.trim(),
      port: Number.parseInt(port, 10) || 465,
      user: user.trim(),
      password,
      use_ssl: useSsl,
      from_name: fromName.trim(),
      enabled,
      notes: notes.trim(),
    }

    if (initial) {
      const patch: Record<string, unknown> = {
        host: payload.host,
        port: payload.port,
        user: payload.user,
        use_ssl: payload.use_ssl,
        from_name: payload.from_name,
        enabled: payload.enabled,
        notes: payload.notes,
      }
      if (payload.password.trim()) {
        patch.password = payload.password
      }
      updateMutation.mutate({ id: initial.id, ...patch }, { onSuccess: () => onClose() })
      return
    }

    createMutation.mutate(payload, { onSuccess: () => onClose() })
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={initial ? 'Edit SMTP Account' : 'Add SMTP Account'} size="md">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Host</label>
            <input
              type="text"
              value={host}
              onChange={(event) => setHost(event.target.value)}
              placeholder="mail.asosiasi.ai"
              required
              className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Port</label>
            <input
              type="number"
              min={1}
              max={65535}
              value={port}
              onChange={(event) => setPort(event.target.value)}
              required
              className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Email / Username</label>
          <input
            type="email"
            value={user}
            onChange={(event) => setUser(event.target.value)}
            placeholder="sekretariat1@asosiasi.ai"
            required
            className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Password {initial ? <span className="text-gray-400">(leave blank to keep current)</span> : null}
          </label>
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required={!initial}
              className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 pr-10 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">From Name</label>
            <input
              type="text"
              value={fromName}
              onChange={(event) => setFromName(event.target.value)}
              placeholder="Sekretariat Asosiasi AI"
              className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
          </div>
          <label className="mt-6 flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input type="checkbox" checked={useSsl} onChange={(event) => setUseSsl(event.target.checked)} />
            Use SSL
          </label>
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
          Enable this account for rotation
        </label>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Notes</label>
          <input
            type="text"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Optional note"
            className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" loading={isLoading}>{initial ? 'Save Changes' : 'Add Account'}</Button>
        </div>
      </form>
    </Modal>
  )
}

export function EmailSettingsPanel({ canManage }: { canManage: boolean }) {
  const [smtpStatus, setSmtpStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle')
  const [letterFormat, setLetterFormat] = useState('')
  const [letterNumber, setLetterNumber] = useState('')
  const [rotateAfterEmails, setRotateAfterEmails] = useState('50')
  const [mailboxCooldownSeconds, setMailboxCooldownSeconds] = useState('60')
  const [mailboxDailyLimit, setMailboxDailyLimit] = useState('40')
  const [delayJitterMs, setDelayJitterMs] = useState('5000')
  const [showAccountModal, setShowAccountModal] = useState(false)
  const [editingAccount, setEditingAccount] = useState<ManagedSMTPAccount | null>(null)
  const [testingAccountId, setTestingAccountId] = useState<number | null>(null)

  const { data: letterConfig, isLoading: letterLoading } = useLetterConfig()
  const { data: configData, isLoading: configLoading } = useConfig()
  const { data: smtpAccountsData, isLoading: smtpAccountsLoading } = useManagedSMTPAccounts()
  const updateLetterMutation = useUpdateLetterConfig()
  const updateConfigMutation = useUpdateConfig()
  const testSmtpMutation = useTestSmtp()
  const deleteSMTPAccountMutation = useDeleteManagedSMTPAccount()
  const testManagedSMTPAccountMutation = useTestManagedSMTPAccount()
  const checkAllManagedSMTPAccountsMutation = useCheckAllManagedSMTPAccounts()

  const smtpAccounts = smtpAccountsData?.accounts ?? []

  useEffect(() => {
    if (letterConfig) {
      setLetterFormat(letterConfig.format_template)
      setLetterNumber(String(letterConfig.last_number))
    }
  }, [letterConfig])

  useEffect(() => {
    if (!configData?.settings) {
      return
    }

    const settingsMap = new Map(configData.settings.map((setting) => [setting.key, setting.value]))
    setRotateAfterEmails(String(settingsMap.get('ROTATE_AFTER_N_EMAILS') ?? 50))
    setMailboxCooldownSeconds(String(settingsMap.get('SMTP_ACCOUNT_MIN_COOLDOWN_SECONDS') ?? 60))
    setMailboxDailyLimit(String(settingsMap.get('SMTP_ACCOUNT_DAILY_LIMIT') ?? 40))
    setDelayJitterMs(String(settingsMap.get('EMAIL_BLAST_DELAY_JITTER_MS') ?? 5000))
  }, [configData])

  async function handleTestSmtp() {
    setSmtpStatus('testing')
    try {
      const result = await testSmtpMutation.mutateAsync()
      if (result.success) {
        setSmtpStatus('ok')
        toast.success('SMTP connection successful')
      } else {
        setSmtpStatus('error')
        toast.error(result.message || 'SMTP connection failed')
      }
    } catch {
      setSmtpStatus('error')
      toast.error('SMTP connection failed')
    }
  }

  async function handleSaveLetter() {
    try {
      await updateLetterMutation.mutateAsync({
        format_template: letterFormat,
        last_number: parseInt(letterNumber) || 0,
      })
      toast.success('Letter config saved')
    } catch {
      toast.error('Failed to save')
    }
  }

  async function handleSaveAntiBanConfig() {
    try {
      await updateConfigMutation.mutateAsync({
        ROTATE_AFTER_N_EMAILS: Number.parseInt(rotateAfterEmails, 10) || 0,
        SMTP_ACCOUNT_MIN_COOLDOWN_SECONDS: Number.parseInt(mailboxCooldownSeconds, 10) || 0,
        SMTP_ACCOUNT_DAILY_LIMIT: Number.parseInt(mailboxDailyLimit, 10) || 0,
        EMAIL_BLAST_DELAY_JITTER_MS: Number.parseInt(delayJitterMs, 10) || 0,
      })
      toast.success('Anti-ban config saved')
    } catch {
      // toast handled by mutation
    }
  }

  async function handleTestManagedAccount(accountId: number) {
    setTestingAccountId(accountId)
    try {
      const result = await testManagedSMTPAccountMutation.mutateAsync(accountId)
      if (result.success) {
        toast.success(result.message || 'SMTP account connected')
      } else {
        toast.error(result.message || 'SMTP account failed')
      }
    } catch {
      toast.error('SMTP account test failed')
    } finally {
      setTestingAccountId(null)
    }
  }

  async function handleCheckAllManagedAccounts() {
    try {
      const result = await checkAllManagedSMTPAccountsMutation.mutateAsync()
      toast.success(`Health check selesai: ${result.healthy} healthy, ${result.failed} gagal, ${result.checked} dicek`)
    } catch {
      toast.error('Bulk SMTP health check failed')
    }
  }

  function handleAddAccount() {
    setEditingAccount(null)
    setShowAccountModal(true)
  }

  function handleEditAccount(account: ManagedSMTPAccount) {
    setEditingAccount(account)
    setShowAccountModal(true)
  }

  async function handleDeleteAccount(account: ManagedSMTPAccount) {
    if (!window.confirm(`Delete SMTP account ${account.user}?`)) {
      return
    }

    deleteSMTPAccountMutation.mutate(account.id)
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <Settings className="h-4 w-4" />
          <span>Email Settings</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="max-w-4xl space-y-8">
          {/* SMTP Test */}
          <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
              <Mail className="h-4 w-4 text-gray-400" />
              SMTP Connection
            </h3>
            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
              <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                Test the currently active SMTP rotation config to ensure emails can be sent.
              </p>
              <Button
                size="sm"
                variant="secondary"
                onClick={handleTestSmtp}
                disabled={!canManage}
                loading={testSmtpMutation.isPending}
              >
                {smtpStatus === 'testing' ? (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    Testing...
                  </>
                ) : smtpStatus === 'ok' ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                    Connected
                  </>
                ) : smtpStatus === 'error' ? (
                  <>
                    <XCircle className="h-3.5 w-3.5 text-red-500" />
                    Failed — Retry
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-3.5 w-3.5" />
                    Test Connection
                  </>
                )}
              </Button>
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
              <Mail className="h-4 w-4 text-gray-400" />
              Anti-Ban Rotation
            </h3>
            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 space-y-4">
              {configLoading ? (
                <div className="flex items-center justify-center py-4"><Spinner /></div>
              ) : (
                <>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-600 dark:text-gray-400">
                        Rotate After N Emails
                      </label>
                      <input
                        type="number"
                        min={1}
                        value={rotateAfterEmails}
                        onChange={(event) => setRotateAfterEmails(event.target.value)}
                        disabled={!canManage}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                      />
                      <p className="mt-1 text-[10px] text-gray-400">Mailbox pindah setelah jumlah kirim ini tercapai.</p>
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-600 dark:text-gray-400">
                        Mailbox Cooldown (seconds)
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={mailboxCooldownSeconds}
                        onChange={(event) => setMailboxCooldownSeconds(event.target.value)}
                        disabled={!canManage}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                      />
                      <p className="mt-1 text-[10px] text-gray-400">Jeda minimum sebelum mailbox yang sama boleh dipakai lagi.</p>
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-600 dark:text-gray-400">
                        Daily Limit Per Mailbox
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={mailboxDailyLimit}
                        onChange={(event) => setMailboxDailyLimit(event.target.value)}
                        disabled={!canManage}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                      />
                      <p className="mt-1 text-[10px] text-gray-400">0 berarti unlimited, selain itu mailbox akan di-skip setelah cap harian tercapai.</p>
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-600 dark:text-gray-400">
                        Delay Jitter (ms)
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={delayJitterMs}
                        onChange={(event) => setDelayJitterMs(event.target.value)}
                        disabled={!canManage}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                      />
                      <p className="mt-1 text-[10px] text-gray-400">Random delay tambahan setelah tiap email agar pola kirim tidak terlalu mekanis.</p>
                    </div>
                  </div>

                  <Button
                    size="sm"
                    onClick={handleSaveAntiBanConfig}
                    disabled={!canManage}
                    loading={updateConfigMutation.isPending}
                  >
                    <Save className="h-3.5 w-3.5" />
                    Save Anti-Ban Config
                  </Button>
                </>
              )}
            </div>
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
                <Mail className="h-4 w-4 text-gray-400" />
                SMTP Rotation Accounts
              </h3>
              {canManage ? (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleCheckAllManagedAccounts}
                    loading={checkAllManagedSMTPAccountsMutation.isPending}
                    disabled={smtpAccounts.length === 0}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Check All Now
                  </Button>
                  <Button size="sm" onClick={handleAddAccount}>
                    <Plus className="h-3.5 w-3.5" />
                    Add Account
                  </Button>
                </div>
              ) : null}
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
              <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">
                Admin can manage multiple mailbox identities here. When multiple enabled accounts exist, backend SMTP rotation will cycle them automatically.
              </p>
              <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">
                Health check otomatis berjalan tiap menit di backend dan statusnya dipush realtime ke halaman ini saat WebSocket aktif.
              </p>

              {smtpAccountsLoading ? (
                <div className="flex items-center justify-center py-6"><Spinner /></div>
              ) : smtpAccounts.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-300 px-4 py-6 text-sm text-gray-500 dark:border-gray-600 dark:text-gray-400">
                  No managed SMTP accounts yet. Add accounts here to enable FE-managed rotation.
                </div>
              ) : (
                <div className="space-y-3">
                  {smtpAccounts.map((account) => {
                    const isTesting = testingAccountId === account.id && testManagedSMTPAccountMutation.isPending
                    const healthBadge = getHealthBadge(account)
                    return (
                      <div key={account.id} className="rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-sm font-semibold text-gray-900 dark:text-white">{account.user}</p>
                              <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${account.enabled ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
                                {account.enabled ? 'Enabled' : 'Disabled'}
                              </span>
                              <span className="rounded bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                                {account.use_ssl ? 'SSL' : 'TLS/Plain'}
                              </span>
                              <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${healthBadge.className}`}>
                                {healthBadge.label}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              {account.host}:{account.port} • From name: {account.from_name}
                            </p>
                            <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                              <div className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-900/60">
                                <p className="text-[10px] uppercase tracking-wide text-gray-400">Today Sent</p>
                                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">
                                  {account.daily_sent_count ?? 0}
                                  {account.daily_limit ? <span className="text-xs font-normal text-gray-400"> / {account.daily_limit}</span> : null}
                                </p>
                              </div>
                              <div className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-900/60">
                                <p className="text-[10px] uppercase tracking-wide text-gray-400">Session Count</p>
                                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">{account.email_count ?? 0}</p>
                              </div>
                              <div className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-900/60">
                                <p className="text-[10px] uppercase tracking-wide text-gray-400">Cooldown</p>
                                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">{formatCooldown(account.cooldown_remaining_seconds)}</p>
                              </div>
                              <div className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-900/60">
                                <p className="text-[10px] uppercase tracking-wide text-gray-400">Rotation State</p>
                                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">
                                  {account.is_current ? 'Current mailbox' : describeSkipReason(account.skip_reason)}
                                </p>
                              </div>
                            </div>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              Last checked: {formatHealthTimestamp(account.last_checked_at)}
                            </p>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              Runtime: {account.connected ? 'Connected' : 'Idle'}
                            </p>
                            {account.health_message ? (
                              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Health: {account.health_message}</p>
                            ) : null}
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              Password: {account.password || '(hidden)'}
                            </p>
                            {account.notes ? (
                              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Notes: {account.notes}</p>
                            ) : null}
                          </div>

                          <div className="flex items-center gap-2">
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => handleTestManagedAccount(account.id)}
                              loading={isTesting}
                              disabled={!canManage}
                            >
                              <RefreshCw className="h-3.5 w-3.5" />
                              Test
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => handleEditAccount(account)} disabled={!canManage}>
                              <Pencil className="h-3.5 w-3.5" />
                              Edit
                            </Button>
                            <Button size="sm" variant="danger" onClick={() => handleDeleteAccount(account)} disabled={!canManage || deleteSMTPAccountMutation.isPending}>
                              <Trash2 className="h-3.5 w-3.5" />
                              Delete
                            </Button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </section>

          {/* Letter Numbering */}
          <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
              <Hash className="h-4 w-4 text-gray-400" />
              Letter Numbering
            </h3>
            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 space-y-4">
              {letterLoading ? (
                <div className="flex items-center justify-center py-4"><Spinner /></div>
              ) : (
                <>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-gray-600 dark:text-gray-400">
                      Format Template
                    </label>
                    <input
                      type="text"
                      value={letterFormat}
                      onChange={(e) => setLetterFormat(e.target.value)}
                      disabled={!canManage}
                      placeholder="{{NUMBER}}/ASOSIASI/{{YEAR}}"
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-mono text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
                    />
                    <p className="mt-1 text-[10px] text-gray-400">
                      Variables: {"{{NUMBER}}"} (zero-padded), {"{{YEAR}}"}, {"{{MONTH}}"}, {"{{MONTH_NAME}}"}
                    </p>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-gray-600 dark:text-gray-400">
                      Last Number
                    </label>
                    <input
                      type="number"
                      value={letterNumber}
                      onChange={(e) => setLetterNumber(e.target.value)}
                      disabled={!canManage}
                      min={0}
                      className="w-32 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                    />
                  </div>

                  <Button
                    size="sm"
                    onClick={handleSaveLetter}
                    disabled={!canManage}
                    loading={updateLetterMutation.isPending}
                  >
                    <Save className="h-3.5 w-3.5" />
                    Save
                  </Button>
                </>
              )}
            </div>
          </section>
        </div>
      </div>

      <SMTPAccountFormModal
        isOpen={showAccountModal}
        onClose={() => {
          setShowAccountModal(false)
          setEditingAccount(null)
        }}
        initial={editingAccount}
      />
    </div>
  )
}
