/**
 * EmailBlastCampaignsPage — Email blast campaigns management with university selector.
 * Improved UI/UX version.
 */

import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Mail,
  Plus,
  Play,
  Pause,
  XCircle,
  Clock,
  CheckCircle2,
  Send,
  RefreshCw,
  ChevronRight,
  Search,
  Filter,
  Check,
  Square,
  AlertTriangle,
  Users,
  FileText,
  Inbox,
  Eye,
} from 'lucide-react'
import { cn } from '../lib/utils'
import {
  useEmailBlastCampaigns,
  useCreateEmailCampaign,
  useStartEmailCampaign,
  usePauseEmailCampaign,
  useCancelEmailCampaign,
  useTestSmtp,
  useAddAllRecipients,
  useAddSelectedRecipients,
} from '../hooks/useEmailBlast'
import { getAllInboxEmails } from '../api/emailBlast'
import { useQuery } from '@tanstack/react-query'
import { useUniversitiesWithEmails, useProvinces } from '../hooks/useUniversities'
import { useUniversityGroups } from '../hooks/useUniversityGroups'
import { QuickSelectGroups } from '../components/universityGroups/QuickSelectGroups'
import type { EmailBlastCampaign } from '../api/emailBlast'

const statusConfig: Record<string, { label: string; color: string; bg: string; border: string; icon: React.ElementType }> = {
  draft: { label: 'Draft', color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-50 dark:bg-gray-800', border: 'border-gray-200 dark:border-gray-700', icon: FileText },
  running: { label: 'Sedang Berjalan', color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20', border: 'border-blue-200 dark:border-blue-800', icon: Send },
  paused: { label: 'Dijeda', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-200 dark:border-amber-800', icon: Pause },
  completed: { label: 'Selesai', color: 'text-green-600 dark:text-green-400', bg: 'bg-green-50 dark:bg-green-900/20', border: 'border-green-200 dark:border-green-800', icon: CheckCircle2 },
  cancelled: { label: 'Dibatalkan', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20', border: 'border-red-200 dark:border-red-800', icon: XCircle },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = statusConfig[status] || statusConfig.draft
  const Icon = cfg.icon
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border', cfg.bg, cfg.color, cfg.border)}>
      <Icon className="w-3.5 h-3.5" />
      {cfg.label}
    </span>
  )
}

function ProgressBar({ sent, failed, invalid = 0, total }: { sent: number; failed: number; invalid?: number; total: number }) {
  if (total === 0) return null
  const sentPct = (sent / total) * 100
  const failedPct = (failed / total) * 100
  const invalidPct = (invalid / total) * 100

  return (
    <div className="w-full">
      <div className="flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400 mb-1">
        <span>{sent + failed + invalid}/{total}</span>
        <span>{Math.round(sentPct + failedPct + invalidPct)}%</span>
      </div>
      <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
        {sentPct > 0 && (
          <div className="bg-gradient-to-r from-green-500 to-green-400 h-full transition-all duration-500" style={{ width: `${sentPct}%` }} />
        )}
        {failedPct > 0 && (
          <div className="bg-gradient-to-r from-red-400 to-red-300 h-full transition-all duration-500" style={{ width: `${failedPct}%` }} />
        )}
        {invalidPct > 0 && (
          <div className="bg-gradient-to-r from-yellow-400 to-yellow-300 h-full transition-all duration-500" style={{ width: `${invalidPct}%` }} />
        )}
        {sentPct === 0 && failedPct === 0 && invalidPct === 0 && (
          <div className="h-full bg-gray-200 dark:bg-gray-600 w-full" />
        )}
      </div>
    </div>
  )
}

// University Selector Modal
function UniversitySelector({
  isOpen,
  onClose,
  onSelect,
  selectedGroupIds,
  onGroupToggle,
}: {
  isOpen: boolean
  onClose: () => void
  onSelect: (universityIds: number[], selectAll: boolean, groupIds?: number[]) => void
  selectedGroupIds: Set<number>
  onGroupToggle: (groupId: number) => void
}) {
  const [search, setSearch] = useState('')
  const [province, setProvince] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [selectAll, setSelectAll] = useState(false)
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 50

  // Reset page when modal opens
  useEffect(() => {
    if (isOpen) setPage(0)
  }, [isOpen])

  const { data: groupsData } = useUniversityGroups()
  const { data: provinces } = useProvinces()
  const { data, isLoading, refetch } = useUniversitiesWithEmails(province || undefined, search, PAGE_SIZE, page * PAGE_SIZE)

  const universities = data?.data || []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const handleToggle = (id: number) => {
    const newSet = new Set(selectedIds)
    if (newSet.has(id)) {
      newSet.delete(id)
    } else {
      newSet.add(id)
    }
    setSelectedIds(newSet)
    setSelectAll(false)
  }

  const handleSelectAll = () => {
    if (selectAll) {
      setSelectedIds(new Set())
      setSelectAll(false)
    } else {
      setSelectedIds(new Set(universities.map(u => u.id)))
      setSelectAll(true)
    }
  }

  const handleConfirm = () => {
    const groupIds = selectedGroupIds.size > 0 ? Array.from(selectedGroupIds) : undefined
    if (selectAll) {
      onSelect([], true, groupIds)
    } else {
      onSelect(Array.from(selectedIds), false, groupIds)
    }
    setSelectedIds(new Set())
    setSelectAll(false)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-3xl max-h-[80vh] flex flex-col shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-semibold">Pilih Universitas</h2>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        {/* Group Quick Select */}
        {groupsData && groupsData.groups.length > 0 && (
          <div className="mb-4">
            <QuickSelectGroups
              groups={groupsData.groups}
              selectedGroupIds={selectedGroupIds}
              onToggle={onGroupToggle}
            />
          </div>
        )}

        {/* Filters */}
        <div className="flex gap-2 mb-4">
          <div className="flex-1 relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0); }}
              placeholder="Cari universitas..."
              className="w-full pl-9 pr-3 py-2.5 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
            />
          </div>
          <select
            value={province}
            onChange={(e) => { setProvince(e.target.value); setPage(0); }}
            className="px-3 py-2.5 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
          >
            <option value="">Semua Provinsi</option>
            {provinces?.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <button
            onClick={() => refetch()}
            className="p-2.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg border dark:border-gray-700"
          >
            <RefreshCw className={cn("w-4 h-4", isLoading && "animate-spin")} />
          </button>
        </div>

        {/* Select All */}
        <div className="flex items-center gap-3 mb-3 pb-3 border-b dark:border-gray-700">
          <button
            onClick={handleSelectAll}
            className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700 font-medium"
          >
            {selectAll ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
            {selectAll ? 'Deselect All' : 'Select All'}
          </button>
          {selectedIds.size > 0 && (
            <span className="text-sm text-blue-600 font-medium">
              {selectedIds.size} dipilih
            </span>
          )}
          <span className="text-sm text-gray-500 ml-auto">
            {universities.length} universitas{total > PAGE_SIZE ? ` dari ${total}` : ''}
          </span>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto -mx-6 px-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
            </div>
          ) : universities.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Search className="w-10 h-10 mx-auto mb-3 opacity-50" />
              <p>Tidak ada universitas ditemukan</p>
            </div>
          ) : (
            <div className="space-y-1">
              {universities.map((uni) => (
                <label
                  key={uni.id}
                  className={cn(
                    "flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors",
                    selectedIds.has(uni.id)
                      ? "bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800"
                      : "hover:bg-gray-50 dark:hover:bg-gray-800 border border-transparent"
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(uni.id) || (selectAll && !selectedIds.has(uni.id))}
                    onChange={() => handleToggle(uni.id)}
                    className="w-4 h-4 rounded border-gray-300 text-blue-600"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{uni.name}</div>
                    <div className="text-sm text-gray-500 truncate">{uni.email}</div>
                  </div>
                  {uni.province && (
                    <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded-full">
                      {uni.province}
                    </span>
                  )}
                </label>
              ))}
            </div>
          )}

          {/* Pagination */}
          {total > PAGE_SIZE && (
            <div className="sticky bottom-0 flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-gray-800/50 border-t dark:border-gray-700 mt-0">
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} dari {total}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="px-2 py-1 text-xs bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  ←
                </button>
                <span className="px-2 py-1 text-xs font-medium text-gray-600 dark:text-gray-300">
                  {page + 1}/{totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="px-2 py-1 text-xs bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  →
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-between items-center mt-4 pt-4 border-t dark:border-gray-700">
          <div className="text-sm text-gray-500">
            {selectAll ? `${universities.length} universitas` : `${selectedIds.size} dipilih`}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700"
            >
              Batal
            </button>
            <button
              onClick={handleConfirm}
              disabled={selectedIds.size === 0 && !selectAll}
              className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 flex items-center gap-2"
            >
              <Check className="w-4 h-4" />
              Tambah ke Campaign
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function CheckSquare({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  )
}

export default function EmailBlastCampaignsPage() {
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [showStart, setShowStart] = useState<number | null>(null)
  const [showSelector, setShowSelector] = useState(false)
  const [activeTab, setActiveTab] = useState<'campaigns' | 'inbox'>('campaigns')
  const [selectedEmail, setSelectedEmail] = useState<any>(null)
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<number>>(new Set())

  // Form state
  const [name, setName] = useState('')

  const { data, isLoading } = useEmailBlastCampaigns()
  const createMutation = useCreateEmailCampaign()
  const startMutation = useStartEmailCampaign()
  const pauseMutation = usePauseEmailCampaign()
  const cancelMutation = useCancelEmailCampaign()
  const addRecipientsMutation = useAddAllRecipients()
  const addSelectedRecipientsMutation = useAddSelectedRecipients()
  const testSmtpMutation = useTestSmtp()

  // All inbox emails query
  const { data: inboxData, isLoading: inboxLoading, refetch: refetchInbox } = useQuery({
    queryKey: ['email-blast-all-inbox'],
    queryFn: () => getAllInboxEmails(50),
    enabled: activeTab === 'inbox',
    refetchInterval: 30000,
  })

  const campaigns = data?.campaigns || []
  const inboxEmails = inboxData?.emails || []

  const handleCreate = () => {
    if (!name.trim()) return
    createMutation.mutate(
      { name: name.trim(), subject: '', template_message: '', delay_between_ms: 20_000 },
      {
        onSuccess: (result) => {
          setName('')
          setShowCreate(false)
          if (result.success && result.campaign_id) {
            navigate(`/email-blast/campaigns/${result.campaign_id}`)
          }
        },
      }
    )
  }

  const handleStart = (campaignId: number) => {
    startMutation.mutate({ campaign_id: campaignId, max_recipients: undefined })
    setShowStart(null)
  }

  const handleTestSmtp = () => {
    testSmtpMutation.mutate(undefined, {
      onSuccess: (result) => {
        alert(result.message)
      },
    })
  }

  const handleSelectUniversities = (campaignId: number) => {
    window.localStorage.setItem('emailBlastCampaignId', String(campaignId))
    setSelectedGroupIds(new Set())
    setShowSelector(true)
  }

  const handleUniversitySelect = (universityIds: number[], selectAll: boolean, groupIds?: number[]) => {
    const campaignId = Number(window.localStorage.getItem('emailBlastCampaignId'))
    if (selectAll) {
      addRecipientsMutation.mutate(campaignId)
    } else {
      addSelectedRecipientsMutation.mutate({
        id: campaignId,
        universityIds,
        groupIds: groupIds && groupIds.length > 0 ? groupIds : undefined,
      })
    }
  }

  const handleGroupToggle = (groupId: number) => {
    setSelectedGroupIds((prev) => {
      const next = new Set(prev)
      if (next.has(groupId)) {
        next.delete(groupId)
      } else {
        next.add(groupId)
      }
      return next
    })
  }

  // Calculate stats
  const totalCampaigns = campaigns.length
  const completedCampaigns = campaigns.filter(c => c.status === 'completed').length
  const totalSent = campaigns.reduce((sum, c) => sum + c.sent_count, 0)
  const totalRecipients = campaigns.reduce((sum, c) => sum + c.total_recipients, 0)

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl shadow-lg shadow-blue-500/20">
              <Mail className="w-6 h-6 text-white" />
            </div>
            <span className="bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
              Email Blast
            </span>
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 ml-14">
            Kirim email massal ke universitas
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleTestSmtp}
            className="px-4 py-2.5 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-xl flex items-center gap-2 transition-all hover:shadow-md"
            disabled={testSmtpMutation.isPending}
          >
            <RefreshCw className={cn("w-4 h-4 text-gray-600", testSmtpMutation.isPending && "animate-spin")} />
            <span className="text-gray-700 dark:text-gray-300">Test SMTP</span>
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="px-5 py-2.5 text-sm bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-700 hover:to-blue-600 text-white rounded-xl flex items-center gap-2 transition-all shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40"
          >
            <Plus className="w-4 h-4" />
            Buat Campaign
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-white dark:bg-gray-900 rounded-2xl p-5 border border-gray-100 dark:border-gray-800 shadow-sm hover:shadow-md transition-all">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-50 dark:bg-blue-900/30 rounded-xl">
              <Send className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{totalCampaigns}</p>
              <p className="text-xs text-gray-500">Total Campaigns</p>
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-2xl p-5 border border-gray-100 dark:border-gray-800 shadow-sm hover:shadow-md transition-all">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-green-50 dark:bg-green-900/30 rounded-xl">
              <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{completedCampaigns}</p>
              <p className="text-xs text-gray-500">Completed</p>
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-2xl p-5 border border-gray-100 dark:border-gray-800 shadow-sm hover:shadow-md transition-all">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-purple-50 dark:bg-purple-900/30 rounded-xl">
              <Mail className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{totalSent}</p>
              <p className="text-xs text-gray-500">Emails Sent</p>
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-2xl p-5 border border-gray-100 dark:border-gray-800 shadow-sm hover:shadow-md transition-all">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-amber-50 dark:bg-amber-900/30 rounded-xl">
              <Inbox className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{inboxEmails.length}</p>
              <p className="text-xs text-gray-500">Replies</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-6 bg-gray-100/50 dark:bg-gray-800/50 p-1.5 rounded-2xl backdrop-blur-sm">
        <button
          onClick={() => setActiveTab('campaigns')}
          className={cn(
            "px-5 py-2.5 text-sm font-semibold rounded-xl flex items-center gap-2.5 transition-all duration-300",
            activeTab === 'campaigns'
              ? "bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-lg shadow-blue-500/10"
              : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-white/50 dark:hover:bg-gray-700/50"
          )}
        >
          <Send className="w-4 h-4" />
          Campaigns
        </button>
        <button
          onClick={() => { setActiveTab('inbox'); refetchInbox(); }}
          className={cn(
            "px-5 py-2.5 text-sm font-semibold rounded-xl flex items-center gap-2.5 transition-all duration-300",
            activeTab === 'inbox'
              ? "bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-lg shadow-blue-500/10"
              : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-white/50 dark:hover:bg-gray-700/50"
          )}
        >
          <Inbox className="w-4 h-4" />
          Inbox
          {inboxEmails.length > 0 && (
            <span className="ml-1 px-2.5 py-0.5 bg-gradient-to-r from-green-500 to-emerald-500 text-white text-xs font-bold rounded-full shadow-lg shadow-green-500/30">
              {inboxEmails.length}
            </span>
          )}
        </button>
      </div>

      {/* Campaign List */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-md shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
                <Mail className="w-5 h-5 text-blue-600" />
              </div>
              <h2 className="text-lg font-semibold">Buat Campaign Baru</h2>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1.5">Nama Campaign</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2.5 border rounded-lg dark:bg-gray-800 dark:border-gray-700 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Contoh: Kerja Sama AI 2026"
                  autoFocus
                />
              </div>

              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  💡 Subject dan template email bisa diisi di halaman detail campaign setelah dibuat.
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700"
              >
                Batal
              </button>
              <button
                onClick={handleCreate}
                disabled={createMutation.isPending || !name.trim()}
                className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                {createMutation.isPending ? 'Membuat...' : 'Buat Campaign'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Start Modal */}
      {showStart && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-md shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-lg">
                <Play className="w-5 h-5 text-green-600" />
              </div>
              <h2 className="text-lg font-semibold">Mulai Kirim Email</h2>
            </div>

            <div className="py-4">
              <p className="text-gray-600 dark:text-gray-400">
                Email akan dikirim ke semua penerima yang sudah ditambahkan ke campaign ini.
              </p>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowStart(null)}
                className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700"
              >
                Batal
              </button>
              <button
                onClick={() => handleStart(showStart)}
                disabled={startMutation.isPending}
                className="px-4 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-50 flex items-center gap-2"
              >
                <Send className="w-4 h-4" />
                {startMutation.isPending ? 'Memulai...' : 'Mulai Kirim'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* University Selector Modal */}
      <UniversitySelector
        isOpen={showSelector}
        onClose={() => {
          setShowSelector(false)
          setSelectedGroupIds(new Set())
        }}
        onSelect={handleUniversitySelect}
        selectedGroupIds={selectedGroupIds}
        onGroupToggle={handleGroupToggle}
      />

      {activeTab === 'campaigns' && isLoading && (
        <div className="flex items-center justify-center py-20">
          <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      )}

      {activeTab === 'campaigns' && !isLoading && campaigns.length === 0 && (
        <div className="text-center py-20">
          <div className="w-16 h-16 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-4">
            <Mail className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-medium mb-2">Belum Ada Campaign</h3>
          <p className="text-gray-500 dark:text-gray-400 mb-6 max-w-sm mx-auto">
            Buat campaign pertama Anda untuk mulai mengirim email massal ke universitas
          </p>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg inline-flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Buat Campaign Pertama
          </button>
        </div>
      )}

      {activeTab === 'campaigns' && !isLoading && campaigns.length > 0 && (
        <div className="grid gap-3">
          {campaigns.map((campaign: EmailBlastCampaign) => (
            <div
              key={campaign.id}
              className="group bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 rounded-2xl p-5 hover:border-blue-200 dark:hover:border-blue-700 hover:shadow-xl hover:shadow-blue-500/5 transition-all duration-300"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-5 min-w-0">
                  <div className={cn(
                    "w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-lg",
                    campaign.status === 'running' ? "bg-gradient-to-br from-blue-400 to-blue-600 shadow-blue-500/25" :
                    campaign.status === 'completed' ? "bg-gradient-to-br from-green-400 to-green-600 shadow-green-500/25" :
                    campaign.status === 'paused' ? "bg-gradient-to-br from-amber-400 to-amber-600 shadow-amber-500/25" :
                    campaign.status === 'cancelled' ? "bg-gradient-to-br from-red-400 to-red-600 shadow-red-500/25" :
                    "bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-800 shadow-gray-500/10"
                  )}>
                    <Mail className={cn(
                      "w-7 h-7",
                      campaign.status === 'running' ? "text-white" :
                      campaign.status === 'completed' ? "text-white" :
                      campaign.status === 'paused' ? "text-white" :
                      campaign.status === 'cancelled' ? "text-white" :
                      "text-gray-500 dark:text-gray-400"
                    )} />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-bold text-lg text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                      {campaign.name}
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 truncate mt-0.5">
                      {campaign.subject || 'Belum ada subjek'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-6 ml-4">
                  <div className="w-48">
                    <StatusBadge status={campaign.status} />
                    {campaign.total_recipients > 0 && (
                      <div className="mt-3">
                        <ProgressBar
                          sent={campaign.sent_count}
                          failed={campaign.failed_count}
                          invalid={campaign.invalid_count}
                          total={campaign.total_recipients}
                        />
                        <div className="flex justify-between mt-1.5 text-[11px] text-gray-400">
                          <span>{campaign.sent_count} terkirim</span>
                          <span>{campaign.total_recipients - campaign.sent_count} tersisa</span>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {campaign.status === 'draft' && (
                      <>
                        <button
                          onClick={() => handleSelectUniversities(campaign.id)}
                          className="px-4 py-2.5 text-sm bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 dark:hover:bg-blue-900/40 text-blue-600 dark:text-blue-400 rounded-xl flex items-center gap-2 transition-all hover:shadow-lg hover:shadow-blue-500/10"
                          title="Pilih Universitas"
                        >
                          <Filter className="w-4 h-4" />
                          <span>Pilih</span>
                        </button>
                        <button
                          onClick={() => setShowStart(campaign.id)}
                          className="px-4 py-2.5 text-sm bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-500 text-white rounded-xl flex items-center gap-2 shadow-lg shadow-green-500/25 hover:shadow-green-500/40 transition-all"
                          title="Mulai"
                        >
                          <Play className="w-4 h-4" />
                          <span>Mulai</span>
                        </button>
                      </>
                    )}
                    {campaign.status === 'running' && (
                      <button
                        onClick={() => pauseMutation.mutate(campaign.id)}
                        className="px-3 py-2 text-sm bg-amber-600 hover:bg-amber-700 text-white rounded-lg flex items-center gap-1.5 shadow-sm"
                        title="Jeda"
                      >
                        <Pause className="w-4 h-4" />
                        <span className="hidden sm:inline">Jeda</span>
                      </button>
                    )}
                    {campaign.status === 'paused' && (
                      <>
                        <button
                          onClick={() => startMutation.mutate({ campaign_id: campaign.id, max_recipients: 100 })}
                          className="px-3 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-1.5 shadow-sm"
                          title="Lanjutkan"
                        >
                          <Play className="w-4 h-4" />
                          <span className="hidden sm:inline">Lanjutkan</span>
                        </button>
                        <button
                          onClick={() => handleSelectUniversities(campaign.id)}
                          className="px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-blue-600 flex items-center gap-1.5"
                          title="Tambah Recipient"
                        >
                          <Users className="w-4 h-4" />
                          <span className="hidden sm:inline">Tambah</span>
                        </button>
                      </>
                    )}
                    {(campaign.status === 'draft' || campaign.status === 'paused') && (
                      <button
                        onClick={() => {
                          if (confirm('Batalkan campaign ini?')) {
                            cancelMutation.mutate(campaign.id)
                          }
                        }}
                        className="px-3 py-2 text-sm hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg text-red-600 flex items-center gap-1.5"
                        title="Batalkan"
                      >
                        <XCircle className="w-4 h-4" />
                      </button>
                    )}
                    <Link
                      to={`/email-blast/${campaign.id}`}
                      className="px-3 py-2 text-sm bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg flex items-center gap-1.5"
                    >
                      Detail
                      <ChevronRight className="w-4 h-4" />
                    </Link>
                  </div>
                </div>
              </div>

              {/* Stats Row */}
              <div className="mt-3 pt-3 border-t dark:border-gray-800 flex items-center gap-4 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                  <Users className="w-3.5 h-3.5" />
                  {campaign.total_recipients} penerima
                </span>
                <span className="flex items-center gap-1 text-green-600">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {campaign.sent_count} terkirim
                </span>
                {campaign.failed_count > 0 && (
                  <span className="flex items-center gap-1 text-red-600">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    {campaign.failed_count} gagal
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'inbox' && (
        <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 rounded-2xl overflow-hidden shadow-lg shadow-gray-500/5">
          <div className="p-5 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between bg-gradient-to-r from-gray-50 to-white dark:from-gray-800 dark:to-gray-900">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl shadow-lg shadow-blue-500/25">
                <Inbox className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="font-bold text-gray-900 dark:text-white">Semua Email Masuk</h3>
                <p className="text-xs text-gray-500">Email balasan dari recipient</p>
              </div>
              <span className="ml-2 px-3 py-1 bg-gradient-to-r from-green-500 to-emerald-500 text-white text-xs font-bold rounded-full shadow-lg shadow-green-500/30">
                {inboxEmails.length}
              </span>
            </div>
            <button
              onClick={() => refetchInbox()}
              className="p-2.5 hover:bg-white dark:hover:bg-gray-700 rounded-xl border border-gray-200 dark:border-gray-700 transition-all hover:shadow-md"
              title="Refresh"
            >
              <RefreshCw className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </button>
          </div>

          {inboxLoading ? (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
            </div>
          ) : inboxEmails.length === 0 ? (
            <div className="text-center py-20 px-5">
              <div className="w-20 h-20 bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-700 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg">
                <Inbox className="w-10 h-10 text-gray-300" />
              </div>
              <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">Belum Ada Email Masuk</h3>
              <p className="text-gray-500 dark:text-gray-400 max-w-sm mx-auto">
                Email balasan dari recipient akan muncul di sini
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800 max-h-[600px] overflow-y-auto">
              {inboxEmails.map((email: any) => (
                <div
                  key={email.id}
                  onClick={() => setSelectedEmail(email)}
                  className="p-5 hover:bg-gradient-to-r hover:from-blue-50 hover:to-transparent dark:hover:from-blue-900/20 dark:hover:to-transparent cursor-pointer transition-all duration-200 group"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-10 h-10 bg-gradient-to-br from-blue-100 to-blue-200 dark:from-blue-900/40 dark:to-blue-800/30 rounded-full flex items-center justify-center shadow-sm">
                          <Mail className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div className="min-w-0">
                          <span className="font-semibold text-sm text-gray-900 dark:text-white truncate block">
                            {email.from_name || email.from_email}
                          </span>
                          <span className="text-xs text-gray-400">{email.from_email}</span>
                        </div>
                      </div>
                      <div className="ml-13">
                        <p className="font-medium text-sm text-gray-800 dark:text-gray-200 mb-1">{email.subject || '(Tanpa Subjek)'}</p>
                        <p className="text-xs text-gray-500 line-clamp-2">{email.body?.substring(0, 120)}...</p>
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <span className="text-xs text-gray-400 font-medium">
                        {email.date ? new Date(email.date).toLocaleString('id-ID', {
                          day: 'numeric',
                          month: 'short',
                          hour: '2-digit',
                          minute: '2-digit'
                        }) : '-'}
                      </span>
                      <div className="mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg shadow-lg shadow-blue-500/30">
                          <Eye className="w-3 h-3" />
                          Lihat
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Email Detail Modal */}
      {selectedEmail && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between mb-4 pb-4 border-b dark:border-gray-800">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Mail className="w-5 h-5 text-blue-500" />
                Detail Email
              </h2>
              <button onClick={() => setSelectedEmail(null)} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4">
              {/* Type indicator */}
              <div className="flex items-center gap-2">
                <Mail className="w-4 h-4 text-blue-500" />
                <span className="text-blue-600 dark:text-blue-400">Email Masuk</span>
              </div>

              {/* Subject */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">Subjek</label>
                <div className="font-medium">{selectedEmail.subject || '(Tanpa Subjek)'}</div>
              </div>

              {/* From */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">Dari</label>
                <div className="font-medium">{selectedEmail.from_name || '-'}</div>
                <div className="text-sm text-gray-500">{selectedEmail.from_email}</div>
              </div>

              {/* To */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">Kepada</label>
                <div className="text-sm text-gray-500">{selectedEmail.to_email}</div>
              </div>

              {/* Body */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">Isi Email</label>
                <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm whitespace-pre-wrap max-h-60 overflow-y-auto">
                  {selectedEmail.body || '(Tidak ada isi email)'}
                </div>
              </div>

              {/* Timestamp */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">Waktu Diterima</label>
                <div className="text-sm text-gray-500">
                  {selectedEmail.date ? new Date(selectedEmail.date).toLocaleString('id-ID', {
                    day: 'numeric',
                    month: 'long',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                  }) : '-'}
                </div>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t dark:border-gray-800 flex justify-end">
              <button
                onClick={() => setSelectedEmail(null)}
                className="px-4 py-2 bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
