/**
 * EmailBlastCampaignsPage — Email blast campaigns management with university selector.
 * Improved UI/UX version.
 */

import { useState } from 'react'
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

function ProgressBar({ sent, failed, total }: { sent: number; failed: number; total: number }) {
  if (total === 0) return null
  const sentPct = (sent / total) * 100
  const failedPct = (failed / total) * 100

  return (
    <div className="w-full">
      <div className="flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400 mb-1">
        <span>{sent + failed}/{total}</span>
        <span>{Math.round(sentPct + failedPct)}%</span>
      </div>
      <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
        {sentPct > 0 && (
          <div className="bg-gradient-to-r from-green-500 to-green-400 h-full transition-all duration-500" style={{ width: `${sentPct}%` }} />
        )}
        {failedPct > 0 && (
          <div className="bg-gradient-to-r from-red-400 to-red-300 h-full transition-all duration-500" style={{ width: `${failedPct}%` }} />
        )}
        {sentPct === 0 && failedPct === 0 && (
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
}: {
  isOpen: boolean
  onClose: () => void
  onSelect: (universityIds: number[], selectAll: boolean) => void
}) {
  const [search, setSearch] = useState('')
  const [province, setProvince] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [selectAll, setSelectAll] = useState(false)

  const { data: provinces } = useProvinces()
  const { data, isLoading, refetch } = useUniversitiesWithEmails(province || undefined, search, 500, 0)

  const universities = data?.data || []

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
    if (selectAll) {
      onSelect([], true)
    } else {
      onSelect(Array.from(selectedIds), false)
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

        {/* Filters */}
        <div className="flex gap-2 mb-4">
          <div className="flex-1 relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cari universitas..."
              className="w-full pl-9 pr-3 py-2.5 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
            />
          </div>
          <select
            value={province}
            onChange={(e) => setProvince(e.target.value)}
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
            {universities.length} universitas
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
      { name: name.trim(), subject: '', template_message: '', delay_between_ms: 8000 },
      {
        onSuccess: (result) => {
          setName('')
          setShowCreate(false)
          if (result.success && result.campaign_id) {
            navigate(`/email-blast/${result.campaign_id}`)
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
    setShowSelector(true)
  }

  const handleUniversitySelect = (universityIds: number[], selectAll: boolean) => {
    const campaignId = Number(window.localStorage.getItem('emailBlastCampaignId'))
    if (selectAll) {
      addRecipientsMutation.mutate(campaignId)
    } else {
      addSelectedRecipientsMutation.mutate({ id: campaignId, universityIds })
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <Mail className="w-7 h-7 text-blue-600" />
            Email Blast
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Kirim email massal ke universitas
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleTestSmtp}
            className="px-4 py-2 text-sm bg-white dark:bg-gray-800 border dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg flex items-center gap-2 transition-colors"
            disabled={testSmtpMutation.isPending}
          >
            <RefreshCw className={cn("w-4 h-4", testSmtpMutation.isPending && "animate-spin")} />
            Test SMTP
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2 transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            Buat Campaign
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg w-fit">
        <button
          onClick={() => setActiveTab('campaigns')}
          className={cn(
            "px-4 py-2 text-sm font-medium rounded-md flex items-center gap-2 transition-all",
            activeTab === 'campaigns'
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Send className="w-4 h-4" />
          Campaigns
        </button>
        <button
          onClick={() => { setActiveTab('inbox'); refetchInbox(); }}
          className={cn(
            "px-4 py-2 text-sm font-medium rounded-md flex items-center gap-2 transition-all",
            activeTab === 'inbox'
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Inbox className="w-4 h-4" />
          Inbox
          {inboxEmails.length > 0 && (
            <span className="ml-1 px-2 py-0.5 bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400 rounded-full text-xs">
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
        onClose={() => setShowSelector(false)}
        onSelect={handleUniversitySelect}
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
              className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-4 hover:border-blue-300 dark:hover:border-blue-700 transition-all hover:shadow-md"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4 min-w-0">
                  <div className={cn(
                    "w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0",
                    campaign.status === 'running' ? "bg-blue-100 dark:bg-blue-900/40" :
                    campaign.status === 'completed' ? "bg-green-100 dark:bg-green-900/40" :
                    campaign.status === 'paused' ? "bg-amber-100 dark:bg-amber-900/40" :
                    campaign.status === 'cancelled' ? "bg-red-100 dark:bg-red-900/40" :
                    "bg-gray-100 dark:bg-gray-800"
                  )}>
                    <Mail className={cn(
                      "w-6 h-6",
                      campaign.status === 'running' ? "text-blue-600" :
                      campaign.status === 'completed' ? "text-green-600" :
                      campaign.status === 'paused' ? "text-amber-600" :
                      campaign.status === 'cancelled' ? "text-red-600" :
                      "text-gray-600 dark:text-gray-400"
                    )} />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-semibold text-lg">{campaign.name}</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                      {campaign.subject || 'Belum ada subjek'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-4 ml-4">
                  <div className="w-40">
                    <StatusBadge status={campaign.status} />
                    {campaign.total_recipients > 0 && (
                      <div className="mt-2">
                        <ProgressBar
                          sent={campaign.sent_count}
                          failed={campaign.failed_count}
                          total={campaign.total_recipients}
                        />
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5">
                    {campaign.status === 'draft' && (
                      <>
                        <button
                          onClick={() => handleSelectUniversities(campaign.id)}
                          className="px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-blue-600 flex items-center gap-1.5"
                          title="Pilih Universitas"
                        >
                          <Filter className="w-4 h-4" />
                          <span className="hidden sm:inline">Pilih</span>
                        </button>
                        <button
                          onClick={() => {
                            if (confirm('Tambah semua universitas ke campaign ini?')) {
                              addRecipientsMutation.mutate(campaign.id)
                            }
                          }}
                          className="px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg flex items-center gap-1.5"
                          title="Tambah Semua"
                        >
                          <Users className="w-4 h-4" />
                          <span className="hidden sm:inline">Add All</span>
                        </button>
                        <button
                          onClick={() => setShowStart(campaign.id)}
                          className="px-3 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-1.5 shadow-sm"
                          title="Mulai"
                        >
                          <Play className="w-4 h-4" />
                          <span className="hidden sm:inline">Mulai</span>
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
        <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl overflow-hidden">
          <div className="p-4 border-b dark:border-gray-800 flex items-center justify-between">
            <h3 className="font-semibold flex items-center gap-2">
              <Inbox className="w-5 h-5 text-blue-600" />
              Semua Email Masuk
              <span className="ml-2 px-2 py-0.5 bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400 rounded-full text-xs">
                {inboxEmails.length}
              </span>
            </h3>
            <button
              onClick={() => refetchInbox()}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
              title="Refresh"
            >
              <RefreshCw className="w-5 h-5" />
            </button>
          </div>

          {inboxLoading ? (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
            </div>
          ) : inboxEmails.length === 0 ? (
            <div className="text-center py-20">
              <Inbox className="w-16 h-16 mx-auto mb-4 text-gray-300" />
              <h3 className="text-lg font-medium mb-2">Belum Ada Email Masuk</h3>
              <p className="text-gray-500 dark:text-gray-400">
                Email balasan dari recipient akan muncul di sini
              </p>
            </div>
          ) : (
            <div className="divide-y dark:divide-gray-800 max-h-[600px] overflow-y-auto">
              {inboxEmails.map((email: any) => (
                <div
                  key={email.id}
                  onClick={() => setSelectedEmail(email)}
                  className="p-4 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <Mail className="w-4 h-4 text-blue-500" />
                        <span className="font-medium text-sm truncate">{email.subject || '(Tanpa Subjek)'}</span>
                      </div>
                      <div className="text-xs text-gray-500 truncate mb-1">
                        Dari: {email.from_name || email.from_email}
                      </div>
                      <div className="text-xs text-gray-400 line-clamp-2">
                        {email.body?.substring(0, 100)}...
                      </div>
                    </div>
                    <div className="text-xs text-gray-400 whitespace-nowrap flex-shrink-0">
                      {email.date ? new Date(email.date).toLocaleString('id-ID', {
                        day: 'numeric',
                        month: 'short',
                        hour: '2-digit',
                        minute: '2-digit'
                      }) : '-'}
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
