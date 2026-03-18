/**
 * EmailBlastCampaignDetailPage — Detail view for email blast campaign.
 */

import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Mail,
  ArrowLeft,
  Play,
  Pause,
  XCircle,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Filter,
  Save,
  Search,
  Check,
  Square,
  Paperclip,
  Upload,
  X,
  Users,
  Clock,
  Send,
  FileText,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckSquare,
  Trash2,
  Inbox,
  Eye,
} from 'lucide-react'
import { cn } from '../lib/utils'
import {
  useEmailBlastCampaign,
  useEmailBlastRecipients,
  useStartEmailCampaign,
  usePauseEmailCampaign,
  useCancelEmailCampaign,
  useAddAllRecipients,
  useUpdateEmailCampaign,
  useUploadAttachment,
  useCampaignAttachment,
  useDeleteEmailRecipient,
  useSentEmails,
  useInboxEmails,
} from '../hooks/useEmailBlast'
import type { EmailBlastCampaign, EmailBlastRecipient } from '../api/emailBlast'
import { useUniversitiesWithEmails, useProvinces } from '../hooks/useUniversities'
import { useAddSelectedRecipients } from '../hooks/useEmailBlast'

const statusConfig: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  draft: { label: 'Draft', color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-100 dark:bg-gray-800', icon: FileText },
  running: { label: 'Sedang Berjalan', color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-100 dark:bg-blue-900/40', icon: Send },
  paused: { label: 'Dijeda', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-100 dark:bg-amber-900/40', icon: Pause },
  completed: { label: 'Selesai', color: 'text-green-600 dark:text-green-400', bg: 'bg-green-100 dark:bg-green-900/40', icon: CheckCircle2 },
  cancelled: { label: 'Dibatalkan', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-100 dark:bg-red-900/40', icon: XCircle },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = statusConfig[status] || statusConfig.draft
  const Icon = cfg.icon
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium', cfg.bg, cfg.color)}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  )
}

function CollapsibleSection({ title, icon: Icon, children, defaultOpen = true, badge }: { title: string, icon: React.ElementType, children: React.ReactNode, defaultOpen?: boolean, badge?: string }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl overflow-hidden mb-4 shadow-sm">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-3 flex items-center justify-between bg-gradient-to-r from-gray-50 to-white dark:from-gray-800 dark:to-gray-900 hover:from-gray-100 dark:hover:from-gray-750 transition-all"
      >
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
            <Icon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          </div>
          <span className="font-semibold text-gray-900 dark:text-white text-sm">{title}</span>
          {badge && (
            <span className="ml-1 px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-full">
              {badge}
            </span>
          )}
        </div>
        {isOpen ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </button>
      {isOpen && <div className="p-4 border-t dark:border-gray-800">{children}</div>}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color, subtext }: { icon: React.ElementType, label: string, value: string | number, color?: string, subtext?: string }) {
  const textColorClass = color?.replace('bg-', 'text-') || 'text-blue-600 dark:text-blue-400'
  return (
    <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-4 flex items-center gap-3 shadow-sm hover:shadow-md transition-all">
      <div className={cn('p-2.5 rounded-lg', color || 'bg-blue-100 dark:bg-blue-900/40')}>
        <Icon className={cn('w-4 h-4', textColorClass)} />
      </div>
      <div className="flex-1 min-w-0">
        <div className={cn('text-xl font-bold', textColorClass)}>
          {value}
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{label}</div>
        {subtext && <div className="text-xs text-gray-400">{subtext}</div>}
      </div>
    </div>
  )
}

export default function EmailBlastCampaignDetailPage() {
  const { id } = useParams<{ id: string }>()
  const campaignId = Number(id)

  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [activeTab, setActiveTab] = useState<'content' | 'recipients' | 'inbox'>('content')
  const [inboxType, setInboxType] = useState<'sent' | 'received'>('sent')
  const [selectedEmail, setSelectedEmail] = useState<any>(null)
  const [maxRecipients, setMaxRecipients] = useState(100)
  const [editSubject, setEditSubject] = useState('')
  const [editTemplate, setEditTemplate] = useState('')
  const [editDelay, setEditDelay] = useState(8000)
  const [showSelectUni, setShowSelectUni] = useState(false)
  const [uniSearch, setUniSearch] = useState('')
  const [uniProvince, setUniProvince] = useState('')
  const [selectedUniIds, setSelectedUniIds] = useState<Set<number>>(new Set())
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null)
  const [attachmentVars, setAttachmentVars] = useState<Record<string, string>>({})
  const [isInitialized, setIsInitialized] = useState(false)

  const { data: campaignData, isLoading: campaignLoading } = useEmailBlastCampaign(campaignId)
  const { data: recipientsData, isLoading: recipientsLoading, refetch } = useEmailBlastRecipients(campaignId, statusFilter)

  const startMutation = useStartEmailCampaign()
  const pauseMutation = usePauseEmailCampaign()
  const cancelMutation = useCancelEmailCampaign()
  const addRecipientsMutation = useAddAllRecipients()
  const addSelectedRecipientsMutation = useAddSelectedRecipients()
  const updateMutation = useUpdateEmailCampaign()
  const uploadAttachmentMutation = useUploadAttachment()
  const deleteRecipientMutation = useDeleteEmailRecipient()
  const { data: attachmentData } = useCampaignAttachment(campaignId)
  const { data: sentEmailsData, isLoading: sentEmailsLoading, refetch: refetchSentEmails } = useSentEmails(campaignId)
  const { data: inboxEmailsData, isLoading: inboxEmailsLoading, refetch: refetchInboxEmails } = useInboxEmails(campaignId)

  // University selector queries
  const { data: provinces } = useProvinces()
  const { data: uniData, isLoading: uniLoading } = useUniversitiesWithEmails(uniProvince || undefined, uniSearch, 500, 0)
  const universities = uniData?.data || []

  const campaign = campaignData?.campaign
  const recipients = recipientsData?.recipients || []

  // Initialize edit fields when campaign loads
  useEffect(() => {
    if (campaign && !isInitialized) {
      setEditSubject(campaign.subject || '')
      setEditTemplate(campaign.template_message || '')
      setEditDelay(campaign.delay_between_ms || 8000)
      setIsInitialized(true)
    }
  }, [campaign, isInitialized])

  // Auto-save for email content
  useEffect(() => {
    if (!isInitialized || !campaign) return
    if (campaign.status !== 'draft' && campaign.status !== 'paused') return

    const timer = setTimeout(() => {
      updateMutation.mutate({
        id: campaignId,
        data: {
          subject: editSubject,
          template_message: editTemplate,
          delay_between_ms: editDelay,
        },
      })
    }, 1500)

    return () => clearTimeout(timer)
  }, [editSubject, editTemplate, editDelay])

  const handleSaveEdit = () => {
    updateMutation.mutate({
      id: campaignId,
      data: {
        subject: editSubject,
        template_message: editTemplate,
        delay_between_ms: editDelay,
      },
    })
  }

  if (campaignLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    )
  }

  if (!campaign) {
    return (
      <div className="p-6">
        <div className="text-center py-12">
          <Mail className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p className="text-gray-500">Campaign tidak ditemukan</p>
          <Link to="/email-blast" className="mt-4 text-blue-600 hover:underline">
            Kembali ke daftar campaign
          </Link>
        </div>
      </div>
    )
  }

  const handleStart = () => {
    startMutation.mutate(
      { campaign_id: campaignId, max_recipients: maxRecipients },
      {
        onSuccess: () => {
          alert('Campaign dimulai! Mengirim email...')
        },
        onError: (error: any) => {
          alert('Gagal memulai campaign: ' + (error?.message || 'Error tidak diketahui'))
        }
      }
    )
  }

  const handlePause = () => {
    pauseMutation.mutate(campaignId)
  }

  const handleCancel = () => {
    if (confirm('Apakah Anda yakin ingin membatalkan campaign ini?')) {
      cancelMutation.mutate(campaignId)
    }
  }

  const handleAddRecipients = () => {
    addRecipientsMutation.mutate(campaignId)
  }

  const handleOpenSelectUni = () => {
    setSelectedUniIds(new Set())
    setUniSearch('')
    setUniProvince('')
    setShowSelectUni(true)
  }

  const handleToggleUni = (id: number) => {
    const newSet = new Set(selectedUniIds)
    if (newSet.has(id)) {
      newSet.delete(id)
    } else {
      newSet.add(id)
    }
    setSelectedUniIds(newSet)
  }

  const handleSelectAllUni = () => {
    if (selectedUniIds.size === universities.length) {
      setSelectedUniIds(new Set())
    } else {
      setSelectedUniIds(new Set(universities.map(u => u.id)))
    }
  }

  const handleConfirmSelectUni = () => {
    if (selectedUniIds.size > 0) {
      addSelectedRecipientsMutation.mutate(
        { id: campaignId, universityIds: Array.from(selectedUniIds) },
        { onSuccess: () => setShowSelectUni(false) }
      )
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && file.name.endsWith('.docx')) {
      setAttachmentFile(file)
      // Auto-upload when file is selected
      uploadAttachmentMutation.mutate(
        { campaignId, file, variables: attachmentVars },
        {
          onSuccess: (result) => {
            setAttachmentFile(null)
            setAttachmentVars(result.variables || {})
          },
          onError: () => {
            setAttachmentFile(null)
          }
        }
      )
    } else if (file) {
      alert('Hanya file .docx yang diizinkan')
    }
  }

  const handleUploadAttachment = () => {
    if (!attachmentFile) return
    uploadAttachmentMutation.mutate(
      { campaignId, file: attachmentFile, variables: attachmentVars },
      {
        onSuccess: (result) => {
          setAttachmentFile(null)
          setAttachmentVars(result.variables || {})
          alert('Template berhasil diupload!')
        },
        onError: () => {
          alert('Gagal upload template')
        }
      }
    )
  }

  const handleVarChange = (key: string, value: string) => {
    setAttachmentVars(prev => ({ ...prev, [key]: value }))
  }

  const handleDeleteRecipient = (recipientId: number) => {
    if (confirm('Hapus penerima ini dari campaign?')) {
      deleteRecipientMutation.mutate({ campaignId, recipientId })
    }
  }

  const pendingCount = recipients.filter(r => r.status === 'pending').length
  const sentCount = recipients.filter(r => r.status === 'sent').length
  const failedCount = recipients.filter(r => r.status === 'failed').length

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <Link
            to="/email-blast"
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              <Mail className="w-6 h-6" />
              {campaign.name}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {campaign.subject || 'No subject'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <StatusBadge status={campaign.status} />

          {campaign.status === 'draft' && (
            <>
              <button
                onClick={handleOpenSelectUni}
                className="px-2.5 py-1.5 text-xs bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50 text-blue-600 dark:text-blue-400 rounded-lg flex items-center gap-1.5"
              >
                <Filter className="w-3.5 h-3.5" />
                Pilih Univ
              </button>
              <button
                onClick={() => {
                  if (confirm('Tambah semua universitas ke campaign ini?')) {
                    handleAddRecipients()
                  }
                }}
                className="px-2.5 py-1.5 text-xs bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg flex items-center gap-1.5"
                disabled={addRecipientsMutation.isPending}
              >
                <RefreshCw className={cn("w-3.5 h-3.5", addRecipientsMutation.isPending && "animate-spin")} />
                Add All
              </button>
              <button
                onClick={handleStart}
                className="px-2.5 py-1.5 text-xs bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-1.5 disabled:opacity-50"
                disabled={startMutation.isPending || campaign.total_recipients === 0}
              >
                {startMutation.isPending ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Mengirim...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5" />
                    Mulai
                  </>
                )}
              </button>
            </>
          )}

          {campaign.status === 'running' && (
            <button
              onClick={handlePause}
              className="px-2.5 py-1.5 text-xs bg-amber-600 hover:bg-amber-700 text-white rounded-lg flex items-center gap-1.5"
              disabled={pauseMutation.isPending}
            >
              <Pause className="w-3.5 h-3.5" />
              Jeda
            </button>
          )}

          {campaign.status === 'paused' && (
            <>
              <button
                onClick={handleStart}
                className="px-2.5 py-1.5 text-xs bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-1.5"
                disabled={startMutation.isPending}
              >
                <Play className="w-3.5 h-3.5" />
                Lanjutkan
              </button>
              <button
                onClick={handleCancel}
                className="px-2.5 py-1.5 text-xs bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center gap-1.5"
                disabled={cancelMutation.isPending}
              >
                <XCircle className="w-3.5 h-3.5" />
                Batal
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg w-fit">
        <button
          onClick={() => setActiveTab('content')}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-md flex items-center gap-1.5 transition-all",
            activeTab === 'content'
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Mail className="w-3.5 h-3.5" />
          Konten
        </button>
        <button
          onClick={() => setActiveTab('recipients')}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-md flex items-center gap-1.5 transition-all",
            activeTab === 'recipients'
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Users className="w-3.5 h-3.5" />
          Penerima
          <span className="ml-1 px-1.5 py-0.5 bg-gray-200 dark:bg-gray-600 rounded-full text-xs">{recipients.length}</span>
        </button>
        <button
          onClick={() => { setActiveTab('inbox'); refetchSentEmails(); }}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-md flex items-center gap-1.5 transition-all",
            activeTab === 'inbox'
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Inbox className="w-3.5 h-3.5" />
          Inbox
          {sentEmailsData?.total ? (
            <span className="ml-1 px-1.5 py-0.5 bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400 rounded-full text-xs">{sentEmailsData.total}</span>
          ) : null}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'content' && (
      <>
        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-4">
          <StatCard icon={Users} label="Total" value={campaign.total_recipients} color="bg-blue-100 dark:bg-blue-900/40" subtext="Semua penerima" />
          <StatCard icon={Send} label="Terkirim" value={campaign.sent_count} color="bg-green-100 dark:bg-green-900/40" />
          <StatCard icon={AlertTriangle} label="Gagal" value={campaign.failed_count} color="bg-red-100 dark:bg-red-900/40" />
          <StatCard icon={CheckCircle2} label="Progres" value={campaign.total_recipients > 0 ? Math.round((campaign.sent_count / campaign.total_recipients) * 100) : 0} color="bg-purple-100 dark:bg-purple-900/40" subtext="persen" />
        </div>

        {/* Progress Bar - Real-time */}
        {campaign.status === 'running' && campaign.total_recipients > 0 && (
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {campaign.status === 'running' ? 'Sedang Mengirim...' : 'Progress'}
              </span>
              <span className="text-sm text-gray-500">
                {campaign.sent_count} / {campaign.total_recipients} email
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3 overflow-hidden">
              <div
                className="bg-gradient-to-r from-green-500 to-green-400 h-full rounded-full transition-all duration-500 ease-out relative"
                style={{ width: `${campaign.total_recipients > 0 ? (campaign.sent_count / campaign.total_recipients) * 100 : 0}%` }}
              >
                <div className="absolute right-0 top-0 bottom-0 w-1 bg-white/30 animate-pulse"></div>
              </div>
            </div>
            <div className="flex justify-between mt-1 text-xs text-gray-500">
              <span>{campaign.total_recipients > 0 ? Math.round((campaign.sent_count / campaign.total_recipients) * 100) : 0}% selesai</span>
              <span>{pendingCount} tersisa</span>
            </div>
          </div>
        )}

        {/* 2 Column Layout - 75/25 */}
        <div className="grid grid-cols-4 gap-6">
          {/* Left Column - Email Content (75%) */}
          <div className="col-span-3">
            <CollapsibleSection title="Konten Email" icon={Mail}>

      <div className="space-y-4">
          {/* Subject */}
          <div>
            <label className="block text-sm font-medium mb-1">Subjek Email</label>
            {campaign.status === 'draft' || campaign.status === 'paused' ? (
              <input
                type="text"
                value={editSubject}
                onChange={(e) => setEditSubject(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
                placeholder="Permintaan Kerja Sama - {{university_name}}"
              />
            ) : (
              <div className="px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm">
                {campaign.subject || '-'}
              </div>
            )}
          </div>

          {/* Template Message */}
          <div>
            <label className="block text-sm font-medium mb-1">Isi Pesan</label>
            {campaign.status === 'draft' || campaign.status === 'paused' ? (
              <>
                <textarea
                  value={editTemplate}
                  onChange={(e) => setEditTemplate(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 h-32"
                  placeholder="Yth. Bagian Sekretariat {{university_name}}, ..."
                />
                <div className="mt-2 p-3 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg border border-blue-100 dark:border-blue-800">
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                    <p className="text-xs font-semibold text-blue-700 dark:text-blue-300">Placeholder Tersedia</p>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <div className="flex items-center gap-1.5">
                      <code className="px-1.5 py-0.5 bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-300 text-xs rounded font-mono">{'{{university_name}}'}</code>
                      <span className="text-xs text-gray-500">Nama Univ</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <code className="px-1.5 py-0.5 bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-300 text-xs rounded font-mono">{'{{email}}'}</code>
                      <span className="text-xs text-gray-500">Email</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <code className="px-1.5 py-0.5 bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-300 text-xs rounded font-mono">{'{{tanggal}}'}</code>
                      <span className="text-xs text-gray-500">Tanggal</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <code className="px-1.5 py-0.5 bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-300 text-xs rounded font-mono">{'{{nomor_surat}}'}</code>
                      <span className="text-xs text-gray-500">No. Surat</span>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <pre className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-xs whitespace-pre-wrap max-h-40 overflow-y-auto">
                {campaign.template_message || '-'}
              </pre>
            )}
          </div>

          {/* Delay and From */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Jeda antar email</label>
              {campaign.status === 'draft' || campaign.status === 'paused' ? (
                <input
                  type="number"
                  value={editDelay}
                  onChange={(e) => setEditDelay(Number(e.target.value))}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
                  min="1000"
                  step="1000"
                />
              ) : (
                <div className="px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm">
                  {campaign.delay_between_ms}ms
                </div>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Pengirim</label>
              <div className="px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm">
                {campaign.from_name} &lt;{campaign.from_email}&gt;
              </div>
            </div>
          </div>

          {/* Attachment (DOCX Template) */}
          <div className="mt-4 pt-4 border-t dark:border-gray-700">
            <div className="flex items-center gap-2 mb-3">
              <Paperclip className="w-4 h-4" />
              <label className="text-sm font-medium">Lampiran (DOCX Template)</label>
            </div>

            {/* Current attachment info */}
            {attachmentData?.filename && (
              <div className="mb-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-blue-600" />
                    <span className="text-sm">{attachmentData.filename}</span>
                  </div>
                </div>
                {attachmentData.detected_variables && attachmentData.detected_variables.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {attachmentData.detected_variables.map(v => (
                      <span key={v} className="px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded-full font-mono">
                        {`{{${v}}}`}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Upload new file */}
            {(campaign.status === 'draft' || campaign.status === 'paused') && (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <input
                    type="file"
                    accept=".docx"
                    onChange={handleFileChange}
                    className="flex-1 text-sm file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 dark:file:bg-blue-900/30 dark:file:text-blue-300"
                  />
                  {attachmentFile && (
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Mengupload...</span>
                    </div>
                  )}
                </div>

                {/* Placeholder info for DOCX */}
                <div className="p-3 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 rounded-lg border border-amber-100 dark:border-amber-800">
                  <div className="flex items-center gap-2 mb-2">
                    <Paperclip className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                    <p className="text-xs font-semibold text-amber-700 dark:text-amber-300">Placeholder untuk DOCX</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <code className="px-1.5 py-0.5 bg-white dark:bg-gray-800 text-amber-600 dark:text-amber-300 text-xs rounded font-mono">{'{{university_name}}'}</code>
                    <code className="px-1.5 py-0.5 bg-white dark:bg-gray-800 text-amber-600 dark:text-amber-300 text-xs rounded font-mono">{'{{email}}'}</code>
                    <code className="px-1.5 py-0.5 bg-white dark:bg-gray-800 text-amber-600 dark:text-amber-300 text-xs rounded font-mono">{'{{tanggal}}'}</code>
                    <code className="px-1.5 py-0.5 bg-white dark:bg-gray-800 text-amber-600 dark:text-amber-300 text-xs rounded font-mono">{'{{nomor_surat}}'}</code>
                  </div>
                </div>

                {/* Variable inputs if template has variables */}
                {attachmentData?.variables && Object.keys(attachmentData.variables).length > 0 && (
                  <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                    <p className="text-xs text-gray-500 mb-2">Isi variabel untuk template:</p>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.keys(attachmentData.variables).map(key => (
                        <div key={key}>
                          <label className="block text-xs text-gray-500 mb-1">{key}</label>
                          <input
                            type="text"
                            value={attachmentVars[key] || ''}
                            onChange={(e) => handleVarChange(key, e.target.value)}
                            placeholder={key}
                            className="w-full px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
                          />
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={handleUploadAttachment}
                      disabled={uploadAttachmentMutation.isPending}
                      className="mt-2 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
                    >
                      Simpan Variabel
                    </button>
                  </div>
                )}

                <p className="text-xs text-gray-500">
                  Gunakan placeholder di dalam DOCX: {'{{university_name}}'}, {'{{email}}'}, {'{{tanggal}}'}, dll
                </p>
              </div>
            )}
          </div>

          {/* Auto-save indicator */}
          {(campaign.status === 'draft' || campaign.status === 'paused') && (
            <div className="flex items-center gap-2 text-sm text-gray-500 pt-2">
              {updateMutation.isPending ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Menyimpan...</span>
                </>
              ) : (
                <>
                  <Check className="w-4 h-4 text-green-500" />
                  <span>Tersimpan otomatis</span>
                </>
              )}
            </div>
          )}
        </div>
      </CollapsibleSection>
        </div>

        {/* Right Column - Recipients (20%) */}
        <div className="col-span-1">
          <CollapsibleSection title="Penerima" icon={Users} badge={`${recipients.length}`}>
          <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl">
            {/* Compact filter row */}
            <div className="p-2 border-b dark:border-gray-800 flex items-center gap-2">
              <select
                value={statusFilter || ''}
                onChange={(e) => setStatusFilter(e.target.value || undefined)}
                className="text-xs border rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-700 flex-1"
              >
                <option value="">Semua</option>
                <option value="pending">Menunggu</option>
                <option value="sent">Terkirim</option>
                <option value="failed">Gagal</option>
              </select>
              <button
                onClick={() => refetch()}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
              >
                <RefreshCw className="w-3 h-3" />
              </button>
            </div>

        {/* Compact recipient list */}
        <div className="max-h-80 overflow-y-auto">
          {recipientsLoading ? (
            <div className="flex items-center justify-center py-6">
              <RefreshCw className="w-4 h-4 animate-spin text-gray-400" />
            </div>
          ) : recipients.length === 0 ? (
            <div className="text-center py-6 text-xs text-gray-500">
              Tidak ada penerima
            </div>
          ) : (
            <div className="divide-y dark:divide-gray-800">
              {recipients.slice(0, 30).map((recipient: EmailBlastRecipient) => (
                <div key={recipient.id} className="p-2 flex items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium truncate">{recipient.university_name || '-'}</div>
                    <div className="text-xs text-gray-500 truncate">{recipient.email}</div>
                  </div>
                  <div className="flex-shrink-0 flex items-center gap-2">
                    {recipient.status === 'pending' && campaign.status === 'draft' && (
                      <button
                        onClick={() => handleDeleteRecipient(recipient.id)}
                        className="p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
                        title="Hapus"
                      >
                        <Trash2 className="w-3 h-3 text-red-500" />
                      </button>
                    )}
                    {recipient.status === 'pending' && (
                      <span className="text-xs text-gray-400">⏳</span>
                    )}
                    {recipient.status === 'sent' && (
                      <span className="text-xs text-green-600">✓</span>
                    )}
                    {recipient.status === 'failed' && (
                      <span className="text-xs text-red-500" title={recipient.error_message || ''}>✕</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {recipients.length > 30 && (
          <div className="p-2 text-center text-xs text-gray-500 border-t dark:border-gray-800">
            +{recipients.length - 30} lagi
          </div>
        )}
      </div>
      </CollapsibleSection>
        </div>
      </div>
      </>
      )}

      {/* Recipients Tab */}
      {activeTab === 'recipients' && (
        <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-6">
          <div className="text-center text-gray-500">
            <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>Daftar penerima</p>
            <p className="text-sm mt-1">{recipients.length} total penerima</p>
          </div>
        </div>
      )}

      {/* Inbox Tab */}
      {activeTab === 'inbox' && (
        <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl overflow-hidden">
          {/* Toggle Sent/Received */}
          <div className="p-4 border-b dark:border-gray-800">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold flex items-center gap-2">
                <Inbox className="w-4 h-4" />
                Inbox
              </h3>
              <div className="flex items-center gap-2">
                <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
                  <button
                    onClick={() => setInboxType('sent')}
                    className={cn(
                      "px-3 py-1 text-xs font-medium rounded-md transition-all",
                      inboxType === 'sent'
                        ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                        : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                    )}
                  >
                    Terkirim ({sentEmailsData?.total || 0})
                  </button>
                  <button
                    onClick={() => { setInboxType('received'); refetchInboxEmails(); }}
                    className={cn(
                      "px-3 py-1 text-xs font-medium rounded-md transition-all",
                      inboxType === 'received'
                        ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                        : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                    )}
                  >
                    Masuk ({inboxEmailsData?.total || 0})
                  </button>
                </div>
                <button
                  onClick={() => inboxType === 'sent' ? refetchSentEmails() : refetchInboxEmails()}
                  className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                  title="Refresh"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Sent Emails */}
          {inboxType === 'sent' && (
            <>
              {sentEmailsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
                </div>
              ) : sentEmailsData?.emails.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <Send className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p>Belum ada email terkirim</p>
                </div>
              ) : (
                <div className="divide-y dark:divide-gray-800 max-h-[600px] overflow-y-auto">
                  {sentEmailsData?.emails.map((email: any) => (
                    <div
                      key={email.id}
                      onClick={() => setSelectedEmail({ ...email, type: 'sent' })}
                      className="p-4 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            {email.status === 'sent' ? (
                              <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
                            ) : (
                              <AlertCircle className="w-3.5 h-3.5 text-red-500" />
                            )}
                            <span className="font-medium text-sm truncate">{email.subject || '(Tanpa Subjek)'}</span>
                          </div>
                          <div className="text-xs text-gray-500 truncate mb-1">
                            Kepada: {email.university_name || email.email}
                          </div>
                          <div className="text-xs text-gray-400 line-clamp-2">
                            {email.body?.substring(0, 100)}...
                          </div>
                        </div>
                        <div className="text-xs text-gray-400 whitespace-nowrap flex-shrink-0">
                          {email.sent_at ? new Date(email.sent_at).toLocaleString('id-ID', {
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
            </>
          )}

          {/* Received Emails (Replies) */}
          {inboxType === 'received' && (
            <>
              {inboxEmailsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
                </div>
              ) : inboxEmailsData?.emails.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <Mail className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p>Belum ada email masuk/balasan</p>
                  <p className="text-xs mt-1">Email balasan akan muncul di sini</p>
                </div>
              ) : (
                <div className="divide-y dark:divide-gray-800 max-h-[600px] overflow-y-auto">
                  {inboxEmailsData?.emails.map((email: any) => (
                    <div
                      key={email.id}
                      onClick={() => setSelectedEmail({ ...email, type: 'received' })}
                      className="p-4 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <Mail className="w-3.5 h-3.5 text-blue-500" />
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
            </>
          )}
        </div>
      )}

      {/* Select University Modal */}
      {showSelectUni && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-3xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Pilih Universitas</h2>
              <button onClick={() => setShowSelectUni(false)} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {/* Filters */}
            <div className="flex gap-2 mb-4">
              <div className="flex-1 relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={uniSearch}
                  onChange={(e) => setUniSearch(e.target.value)}
                  placeholder="Cari universitas..."
                  className="w-full pl-9 pr-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
              <select
                value={uniProvince}
                onChange={(e) => setUniProvince(e.target.value)}
                className="px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
              >
                <option value="">Semua Provinsi</option>
                {provinces?.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>

            {/* Select All */}
            <div className="flex items-center gap-2 mb-2 pb-2 border-b dark:border-gray-800">
              <button
                onClick={handleSelectAllUni}
                className="flex items-center gap-2 text-sm"
              >
                {selectedUniIds.size === universities.length && universities.length > 0 ? (
                  <Check className="w-4 h-4" />
                ) : (
                  <Square className="w-4 h-4" />
                )}
                Pilih Semua ({universities.length})
              </button>
              {selectedUniIds.size > 0 && (
                <span className="text-sm text-blue-600">{selectedUniIds.size} dipilih</span>
              )}
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto">
              {uniLoading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
                </div>
              ) : universities.length === 0 ? (
                <div className="text-center py-8 text-gray-500">Tidak ada universitas ditemukan</div>
              ) : (
                <div className="divide-y dark:divide-gray-800">
                  {universities.map((uni) => (
                    <div
                      key={uni.id}
                      onClick={() => handleToggleUni(uni.id)}
                      className={cn(
                        "flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800",
                        selectedUniIds.has(uni.id) && "bg-blue-50 dark:bg-blue-900/20"
                      )}
                    >
                      {selectedUniIds.has(uni.id) ? (
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
                {selectedUniIds.size > 0 ? `${selectedUniIds.size} dipilih` : `${universities.length} universitas`}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowSelectUni(false)}
                  className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg"
                >
                  Batal
                </button>
                <button
                  onClick={handleConfirmSelectUni}
                  disabled={selectedUniIds.size === 0 || addSelectedRecipientsMutation.isPending}
                  className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
                >
                  {addSelectedRecipientsMutation.isPending ? 'Menambahkan...' : 'Tambah ke Campaign'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Email Detail Modal */}
      {selectedEmail && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between mb-4 pb-4 border-b dark:border-gray-800">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                {selectedEmail.type === 'received' ? (
                  <Mail className="w-5 h-5 text-blue-500" />
                ) : (
                  <Eye className="w-5 h-5 text-blue-500" />
                )}
                {selectedEmail.type === 'received' ? 'Email Masuk' : 'Detail Email'}
              </h2>
              <button onClick={() => setSelectedEmail(null)} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4">
              {/* Type indicator */}
              <div className="flex items-center gap-2">
                {selectedEmail.type === 'received' ? (
                  <>
                    <Mail className="w-4 h-4 text-blue-500" />
                    <span className="text-blue-600 dark:text-blue-400">Email Masuk / Balasan</span>
                  </>
                ) : (
                  <>
                    {selectedEmail.status === 'sent' ? (
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-red-500" />
                    )}
                    <span className={selectedEmail.status === 'sent' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                      {selectedEmail.status === 'sent' ? 'Terkirim' : 'Gagal'}
                    </span>
                  </>
                )}
              </div>

              {/* Subject */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">Subjek</label>
                <div className="font-medium">{selectedEmail.subject || '(Tanpa Subjek)'}</div>
              </div>

              {selectedEmail.type === 'received' ? (
                <>
                  {/* From - for received emails */}
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Dari</label>
                    <div className="font-medium">{selectedEmail.from_name || '-'}</div>
                    <div className="text-sm text-gray-500">{selectedEmail.from_email}</div>
                  </div>

                  {/* To - for received emails */}
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Kepada</label>
                    <div className="text-sm text-gray-500">{selectedEmail.to_email}</div>
                  </div>
                </>
              ) : (
                <>
                  {/* Recipient - for sent emails */}
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Penerima</label>
                    <div className="font-medium">{selectedEmail.university_name || '-'}</div>
                    <div className="text-sm text-gray-500">{selectedEmail.email}</div>
                  </div>
                </>
              )}

              {/* Body */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  {selectedEmail.type === 'received' ? 'Isi Email' : 'Isi Pesan'}
                </label>
                <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm whitespace-pre-wrap max-h-60 overflow-y-auto">
                  {selectedEmail.body || '(Tidak ada isi email)'}
                </div>
              </div>

              {/* Timestamp */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  {selectedEmail.type === 'received' ? 'Waktu Diterima' : 'Waktu Kirim'}
                </label>
                <div className="text-sm text-gray-500">
                  {selectedEmail.type === 'received' && selectedEmail.date
                    ? new Date(selectedEmail.date).toLocaleString('id-ID', {
                        day: 'numeric',
                        month: 'long',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })
                    : selectedEmail.sent_at
                    ? new Date(selectedEmail.sent_at).toLocaleString('id-ID', {
                        day: 'numeric',
                        month: 'long',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })
                    : '-'}
                </div>
              </div>

              {/* Error message if failed */}
              {selectedEmail.type === 'sent' && selectedEmail.status === 'failed' && selectedEmail.error_message && (
                <div>
                  <label className="block text-xs text-red-500 mb-1">Pesan Error</label>
                  <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg text-sm text-red-600 dark:text-red-400">
                    {selectedEmail.error_message}
                  </div>
                </div>
              )}
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
