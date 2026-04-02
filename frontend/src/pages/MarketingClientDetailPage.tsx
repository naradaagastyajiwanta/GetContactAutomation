import { useState, useEffect } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Play,
  Download,
  Upload,
  CheckCircle2,
  Plus,
  Loader2,
  Users,
  Wifi,
  Mail,
  Phone,
  User,
  Briefcase,
  XCircle,
} from 'lucide-react'
import { cn } from '../lib/utils'
import {
  useMarketingGroupDetail,
  useMarketingClients,
  useStartGroupSearch,
  useSearchStatus,
  useBulkApproveGroupContacts,
  useExportGroupClients,
  useAddMarketingClient,
} from '../hooks/useMarketing'
import { Card, CardHeader, CardTitle } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { Badge } from '../components/ui/Badge'
import { Modal } from '../components/ui/Modal'
import { MarketingImportModal } from '../components/marketing/MarketingImportModal'
import { MarketingClientResultsTable } from '../components/marketing/MarketingClientResultsTable'
import { MarketingReadyToBlastPanel } from '../components/marketing/MarketingReadyToBlastPanel'
import { useAuth } from '../context/AuthContext'
import toast from 'react-hot-toast'
import type { GroupStatus } from '../api/marketing'

const statusConfig: Record<
  GroupStatus,
  { label: string; color: string; bg: string; icon: React.ElementType }
> = {
  draft: {
    label: 'Draft',
    color: 'text-gray-600 dark:text-gray-400',
    bg: 'bg-gray-100 dark:bg-gray-800',
    icon: XCircle,
  },
  searching: {
    label: 'Searching',
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-900/30',
    icon: Loader2,
  },
  done: {
    label: 'Done',
    color: 'text-green-600 dark:text-green-400',
    bg: 'bg-green-50 dark:bg-green-900/30',
    icon: CheckCircle2,
  },
}

function SearchProgressBar({ status, progress, total, found, not_found }: {
  status: GroupStatus
  progress: number
  total: number
  found: number
  not_found: number
}) {
  if (status !== 'searching') return null
  const pct = total > 0 ? Math.round((progress / total) * 100) : 0
  const foundPct = total > 0 ? (found / total) * 100 : 0
  const notFoundPct = total > 0 ? (not_found / total) * 100 : 0

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>{progress}/{total} diproses</span>
        <span>{pct}%</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
        <div className="flex h-full">
          {foundPct > 0 && (
            <div
              className="h-full bg-green-500 transition-all duration-500"
              style={{ width: `${foundPct}%` }}
            />
          )}
          {notFoundPct > 0 && (
            <div
              className="h-full bg-red-400 transition-all duration-500"
              style={{ width: `${notFoundPct}%` }}
            />
          )}
          {pct < 100 && (
            <div
              className="h-full bg-blue-400 animate-pulse"
              style={{ width: `${Math.max(0, 100 - foundPct - notFoundPct)}%` }}
            />
          )}
        </div>
      </div>
      <div className="flex gap-4 text-xs">
        <span className="text-green-600 dark:text-green-400">
          {found} ditemukan
        </span>
        <span className="text-red-500">
          {not_found} tidak ditemukan
        </span>
      </div>
    </div>
  )
}

function AddClientInlineForm({
  groupId,
  onClose,
}: {
  groupId: number
  onClose: () => void
}) {
  const [name, setName] = useState('')
  const addClient = useAddMarketingClient()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await addClient.mutateAsync({ groupId, name: name.trim() })
      toast.success('Client ditambahkan')
      setName('')
      onClose()
    } catch {
      toast.error('Gagal menambahkan client')
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Nama client..."
        className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm
          focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
          dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
      />
      <Button type="submit" size="sm" loading={addClient.isPending} disabled={!name.trim()}>
        Tambah
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={onClose}>
        Batal
      </Button>
    </form>
  )
}

export default function MarketingClientDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const groupId = Number(id)

  const [importOpen, setImportOpen] = useState(false)
  const [addClientOpen, setAddClientOpen] = useState(false)

  const { data, isLoading, error } = useMarketingGroupDetail(groupId)
  const { data: clientsData } = useMarketingClients(groupId)
  const canManage = hasPermission('marketing.manage') || hasPermission('blast.manage')

  const group = data?.group
  const stats = data?.stats
  const clients = clientsData?.clients ?? []

  // Poll search status while searching
  const searchStatusEnabled = group?.status === 'searching'
  const { data: searchStatus } = useSearchStatus(groupId, searchStatusEnabled)

  const startSearchMutation = useStartGroupSearch()
  const bulkApproveMutation = useBulkApproveGroupContacts()
  const exportMutation = useExportGroupClients()

  const statusCfg = statusConfig[group?.status ?? 'draft']

  async function handleStartSearch() {
    try {
      await startSearchMutation.mutateAsync(groupId)
      toast.success('Scraping dimulai')
    } catch {
      toast.error('Gagal memulai scraping')
    }
  }

  async function handleBulkApprove() {
    if (!window.confirm('Approve semua kontak yang ditemukan?')) return
    try {
      const result = await bulkApproveMutation.mutateAsync(groupId)
      toast.success(`${result.approved} kontak di-approve`)
    } catch {
      toast.error('Gagal bulk approve')
    }
  }

  async function handleExport() {
    try {
      const blob = await exportMutation.mutateAsync(groupId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${group?.name ?? 'marketing-group'}-export.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Gagal export data')
    }
  }

  const isSearching = group?.status === 'searching'

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error || !group) {
    return (
      <div className="space-y-4">
        <Link
          to="/marketing"
          className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
        >
          <ArrowLeft className="h-4 w-4" /> Kembali
        </Link>
        <Card className="border-red-200 dark:border-red-800 py-8 text-center">
          <p className="text-red-600 dark:text-red-400">
            Gagal memuat data group: {(error as Error)?.message ?? 'Unknown error'}
          </p>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/marketing"
            className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                {group.name}
              </h1>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                {group.client_type}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <span
                className={cn(
                  'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold',
                  statusCfg.bg,
                  statusCfg.color
                )}
              >
                <statusCfg.icon
                  className={cn('h-3 w-3', isSearching && 'animate-spin')}
                />
                {statusCfg.label}
              </span>
              <span className="text-xs text-gray-400">
                {formatDate(group.created_at)}
              </span>
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {canManage && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleBulkApprove}
                loading={bulkApproveMutation.isPending}
                disabled={clients.flatMap((c) => c.contacts).length === 0}
              >
                <CheckCircle2 className="h-4 w-4" />
                Approve Semua
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleExport}
                loading={exportMutation.isPending}
                disabled={clients.length === 0}
              >
                <Download className="h-4 w-4" />
                Export Excel
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setImportOpen(true)}
              >
                <Upload className="h-4 w-4" />
                Upload Excel
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAddClientOpen(true)}
              >
                <Plus className="h-4 w-4" />
                Tambah Client
              </Button>
              {group.status !== 'searching' && (
                <Button
                  size="sm"
                  onClick={handleStartSearch}
                  loading={startSearchMutation.isPending}
                >
                  <Play className="h-4 w-4" />
                  Mulai Scraping
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          {[
            { label: 'Total', value: stats.total, color: 'text-gray-900 dark:text-gray-100' },
            { label: 'Ditemukan', value: stats.found, color: 'text-green-600 dark:text-green-400' },
            { label: 'Tidak Ditemukan', value: stats.not_found, color: 'text-red-500' },
            { label: 'Pending', value: stats.pending, color: 'text-blue-600 dark:text-blue-400' },
            { label: 'Approved', value: stats.approved, color: 'text-indigo-600 dark:text-indigo-400' },
          ].map((s) => (
            <Card key={s.label} padding={false}>
              <div className="p-4">
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{s.label}</p>
                <p className={cn('mt-1 text-2xl font-bold', s.color)}>{s.value}</p>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Search progress */}
      {isSearching && searchStatus && (
        <Card>
          <CardHeader>
            <CardTitle>Progress Scraping</CardTitle>
          </CardHeader>
          <SearchProgressBar
            status={searchStatus.status}
            progress={searchStatus.progress}
            total={searchStatus.total}
            found={searchStatus.found}
            not_found={searchStatus.not_found}
          />
          {searchStatus.error_message && (
            <p className="mt-2 text-xs text-red-500">{searchStatus.error_message}</p>
          )}
        </Card>
      )}

      {/* Ready to blast panel */}
      <MarketingReadyToBlastPanel clients={clients} groupId={groupId} />

      {/* Add client inline form */}
      {addClientOpen && (
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-gray-700 dark:text-gray-300">
            Tambah Client Baru
          </h3>
          <AddClientInlineForm
            groupId={groupId}
            onClose={() => setAddClientOpen(false)}
          />
        </Card>
      )}

      {/* Clients list */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Daftar Client ({clients.length})
          </h2>
        </div>
        <MarketingClientResultsTable
          clients={clients}
          groupId={groupId}
          canManage={canManage}
        />
      </div>

      {/* Import modal */}
      {importOpen && (
        <MarketingImportModal
          groupId={groupId}
          onClose={() => setImportOpen(false)}
        />
      )}
    </div>
  )
}

function formatDate(date: string | null): string {
  if (!date) return '-'
  return new Intl.DateTimeFormat('id-ID', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(date))
}
