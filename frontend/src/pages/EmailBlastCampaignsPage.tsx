/**
 * EmailBlastCampaignsPage — Email blast campaigns management with university selector.
 */

import { useState, useMemo } from 'react'
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
import { useUniversitiesWithEmails, useProvinces } from '../hooks/useUniversities'
import type { EmailBlastCampaign } from '../api/emailBlast'
import { useQuery } from '@tanstack/react-query'

const statusConfig: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  draft: { label: 'Draft', color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-100 dark:bg-gray-800', icon: Clock },
  running: { label: 'Sending', color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/30', icon: Send },
  paused: { label: 'Paused', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/30', icon: Pause },
  completed: { label: 'Completed', color: 'text-green-600 dark:text-green-400', bg: 'bg-green-50 dark:bg-green-900/30', icon: CheckCircle2 },
  cancelled: { label: 'Cancelled', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/30', icon: XCircle },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = statusConfig[status] || statusConfig.draft
  const Icon = cfg.icon
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold', cfg.bg, cfg.color)}>
      <Icon className="w-3 h-3" />
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
      <div className="h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
        {sentPct > 0 && (
          <div className="bg-green-500 h-full transition-all duration-500" style={{ width: `${sentPct}%` }} />
        )}
        {failedPct > 0 && (
          <div className="bg-red-400 h-full transition-all duration-500" style={{ width: `${failedPct}%` }} />
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
  const [loading, setLoading] = useState(false)

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
      onSelect([], true) // Empty array means all filtered
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
      <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-3xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Select Universities</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
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
              placeholder="Search universities..."
              className="w-full pl-9 pr-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
            />
          </div>
          <select
            value={province}
            onChange={(e) => setProvince(e.target.value)}
            className="px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
          >
            <option value="">All Provinces</option>
            {provinces?.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <button
            onClick={() => refetch()}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
          >
            <RefreshCw className={cn("w-4 h-4", isLoading && "animate-spin")} />
          </button>
        </div>

        {/* Select All */}
        <div className="flex items-center gap-2 mb-2 pb-2 border-b dark:border-gray-800">
          <button
            onClick={handleSelectAll}
            className="flex items-center gap-2 text-sm"
          >
            {selectAll ? <Check className="w-4 h-4" /> : <Square className="w-4 h-4" />}
            Select All ({universities.length} universities)
          </button>
          {selectedIds.size > 0 && (
            <span className="text-sm text-blue-600">
              {selectedIds.size} selected
            </span>
          )}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : universities.length === 0 ? (
            <div className="text-center py-8 text-gray-500">No universities found</div>
          ) : (
            <div className="divide-y dark:divide-gray-800">
              {universities.map((uni) => (
                <div
                  key={uni.id}
                  onClick={() => handleToggle(uni.id)}
                  className={cn(
                    "flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800",
                    selectedIds.has(uni.id) && "bg-blue-50 dark:bg-blue-900/20"
                  )}
                >
                  {selectedIds.has(uni.id) || (selectAll && !selectedIds.has(uni.id)) ? (
                    <Check className="w-4 h-4 text-blue-600" />
                  ) : (
                    <Square className="w-4 h-4 text-gray-400" />
                  )}
                  <div className="flex-1">
                    <div className="font-medium">{uni.name}</div>
                    <div className="text-sm text-gray-500">{uni.province}</div>
                  </div>
                  <div className="text-sm text-gray-500">{uni.email}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-between items-center mt-4 pt-4 border-t dark:border-gray-800">
          <div className="text-sm text-gray-500">
            {selectAll ? `All ${universities.length} universities` : `${selectedIds.size} selected`}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={selectedIds.size === 0 && !selectAll}
              className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
            >
              Add to Campaign
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function EmailBlastCampaignsPage() {
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [showStart, setShowStart] = useState<number | null>(null)
  const [showSelector, setShowSelector] = useState(false)
  const [maxRecipients, setMaxRecipients] = useState(100)

  // Form state
  const [name, setName] = useState('')
  const [subject, setSubject] = useState('')
  const [template, setTemplate] = useState('')
  const [delayMs, setDelayMs] = useState(8000)

  const { data, isLoading } = useEmailBlastCampaigns()
  const createMutation = useCreateEmailCampaign()
  const startMutation = useStartEmailCampaign()
  const pauseMutation = usePauseEmailCampaign()
  const cancelMutation = useCancelEmailCampaign()
  const addRecipientsMutation = useAddAllRecipients()
  const addSelectedRecipientsMutation = useAddSelectedRecipients()
  const testSmtpMutation = useTestSmtp()

  const campaigns = data?.campaigns || []

  const handleCreate = () => {
    if (!name.trim()) return
    createMutation.mutate(
      { name: name.trim(), subject: '', template_message: '', delay_between_ms: 8000 },
      {
        onSuccess: (result) => {
          setName('')
          setSubject('')
          setTemplate('')
          setShowCreate(false)
          if (result.success && result.campaign_id) {
            navigate(`/email-blast/${result.campaign_id}`)
          }
        },
      }
    )
  }

  const handleStart = (campaignId: number) => {
    startMutation.mutate({ campaign_id: campaignId, max_recipients: maxRecipients })
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
    // Store campaign ID and open selector
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
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Mail className="w-6 h-6" />
            Email Blast
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Kirim email massal ke universitas
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleTestSmtp}
            className="px-3 py-2 text-sm bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg flex items-center gap-2"
            disabled={testSmtpMutation.isPending}
          >
            <RefreshCw className={cn("w-4 h-4", testSmtpMutation.isPending && "animate-spin")} />
            Test SMTP
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="px-3 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            New Campaign
          </button>
        </div>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-md">
            <h2 className="text-lg font-semibold mb-4">New Email Campaign</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Campaign Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
                  placeholder="Kerja Sama AI"
                  autoFocus
                />
              </div>

              <p className="text-sm text-gray-500">
                Subject dan template bisa diisi di halaman detail campaign.
              </p>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={createMutation.isPending || !name.trim()}
                className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
              >
                {createMutation.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Start Modal */}
      {showStart && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-md">
            <h2 className="text-lg font-semibold mb-4">Start Campaign</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Max Recipients</label>
                <input
                  type="number"
                  value={maxRecipients}
                  onChange={(e) => setMaxRecipients(Number(e.target.value))}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowStart(null)}
                className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={() => handleStart(showStart)}
                disabled={startMutation.isPending}
                className="px-4 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-50"
              >
                {startMutation.isPending ? 'Starting...' : 'Start'}
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

      {/* Campaign List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <Mail className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No email campaigns yet</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
          >
            Create First Campaign
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {campaigns.map((campaign: EmailBlastCampaign) => (
            <div
              key={campaign.id}
              className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-4 hover:border-blue-300 dark:hover:border-blue-700 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
                    <Mail className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div>
                    <h3 className="font-semibold">{campaign.name}</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {campaign.subject || 'No subject'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-6">
                  <div className="w-48">
                    <StatusBadge status={campaign.status} />
                    <div className="mt-2">
                      <ProgressBar
                        sent={campaign.sent_count}
                        failed={campaign.failed_count}
                        total={campaign.total_recipients}
                      />
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {campaign.status === 'draft' && (
                      <>
                        <button
                          onClick={() => handleSelectUniversities(campaign.id)}
                          className="px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-blue-600 flex items-center gap-1"
                          title="Pilih Universitas"
                        >
                          <Filter className="w-4 h-4" />
                          Pilih
                        </button>
                        <button
                          onClick={() => {
                            if (confirm('Tambah semua universitas ke campaign ini?')) {
                              addRecipientsMutation.mutate(campaign.id)
                            }
                          }}
                          className="px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg flex items-center gap-1"
                          title="Add All Recipients"
                        >
                          <RefreshCw className={cn("w-4 h-4", addRecipientsMutation.isPending && "animate-spin")} />
                          Add All
                        </button>
                        <button
                          onClick={() => setShowStart(campaign.id)}
                          className="px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-green-600 flex items-center gap-1"
                          title="Start"
                        >
                          <Play className="w-4 h-4" />
                          Start
                        </button>
                      </>
                    )}
                    {campaign.status === 'running' && (
                      <button
                        onClick={() => pauseMutation.mutate(campaign.id)}
                        className="px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-amber-600 flex items-center gap-1"
                        title="Pause"
                      >
                        <Pause className="w-4 h-4" />
                        Pause
                      </button>
                    )}
                    {campaign.status === 'paused' && (
                      <>
                        <button
                          onClick={() => startMutation.mutate({ campaign_id: campaign.id, max_recipients: 100 })}
                          className="px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-green-600 flex items-center gap-1"
                          title="Resume"
                        >
                          <Play className="w-4 h-4" />
                          Resume
                        </button>
                        <button
                          onClick={() => handleSelectUniversities(campaign.id)}
                          className="px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-blue-600 flex items-center gap-1"
                          title="Tambah Recipient"
                        >
                          <Filter className="w-4 h-4" />
                          Tambah
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
                        className="px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-red-600 flex items-center gap-1"
                        title="Cancel"
                      >
                        <XCircle className="w-4 h-4" />
                        Cancel
                      </button>
                    )}
                    <Link
                      to={`/email-blast/${campaign.id}`}
                      className="px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg flex items-center gap-1"
                    >
                      Detail
                      <ChevronRight className="w-4 h-4" />
                    </Link>
                  </div>
                </div>
              </div>

              <div className="mt-3 text-xs text-gray-400">
                {campaign.sent_count} sent, {campaign.failed_count} failed, {campaign.total_recipients} total
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
