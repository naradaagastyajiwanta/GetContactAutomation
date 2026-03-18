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
    <span className={cn('inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium', cfg.bg, cfg.color)}>
      <Icon className="w-4 h-4" />
      {cfg.label}
    </span>
  )
}

function CollapsibleSection({ title, icon: Icon, children, defaultOpen = true }: { title: string, icon: React.ElementType, children: React.ReactNode, defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl overflow-hidden mb-4">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-5 py-4 flex items-center justify-between bg-gradient-to-r from-gray-50 to-white dark:from-gray-800 dark:to-gray-900 hover:from-gray-100 dark:hover:from-gray-750 transition-all"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
            <Icon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <span className="font-semibold text-gray-900 dark:text-white">{title}</span>
        </div>
        {isOpen ? (
          <ChevronUp className="w-5 h-5 text-gray-400" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-400" />
        )}
      </button>
      {isOpen && <div className="p-5 border-t dark:border-gray-800">{children}</div>}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color, subtext }: { icon: React.ElementType, label: string, value: string | number, color?: string, subtext?: string }) {
  return (
    <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-4 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
      <div className={cn('p-3 rounded-xl', color || 'bg-blue-100 dark:bg-blue-900/40')}>
        <Icon className={cn('w-5 h-5', color?.replace('bg-', 'text-') || 'text-blue-600 dark:text-blue-400')} />
      </div>
      <div>
        <div className={cn('text-2xl font-bold', color?.replace('bg-', 'text-') || 'text-gray-900 dark:text-white')}>
          {value}
        </div>
        <div className="text-sm text-gray-500 dark:text-gray-400">{label}</div>
        {subtext && <div className="text-xs text-gray-400 mt-0.5">{subtext}</div>}
      </div>
    </div>
  )
}

export default function EmailBlastCampaignDetailPage() {
  const { id } = useParams<{ id: string }>()
  const campaignId = Number(id)

  const [statusFilter, setStatusFilter] = useState<string | undefined>()
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
    <div className="p-6 max-w-6xl mx-auto">
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
            <h1 className="text-2xl font-bold flex items-center gap-2">
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
                className="px-3 py-2 text-sm bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50 text-blue-600 rounded-lg flex items-center gap-2"
              >
                <Filter className="w-4 h-4" />
                Pilih Universitas
              </button>
              <button
                onClick={() => {
                  if (confirm('Tambah semua universitas ke campaign ini?')) {
                    handleAddRecipients()
                  }
                }}
                className="px-3 py-2 text-sm bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg flex items-center gap-2"
                disabled={addRecipientsMutation.isPending}
              >
                <RefreshCw className={cn("w-4 h-4", addRecipientsMutation.isPending && "animate-spin")} />
                Tambah Semua
              </button>
              <button
                onClick={handleStart}
                className="px-3 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-2 disabled:opacity-50"
                disabled={startMutation.isPending || campaign.total_recipients === 0}
              >
                {startMutation.isPending ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Mengirim...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    Mulai Kirim
                  </>
                )}
              </button>
            </>
          )}

          {campaign.status === 'running' && (
            <button
              onClick={handlePause}
              className="px-3 py-2 text-sm bg-amber-600 hover:bg-amber-700 text-white rounded-lg flex items-center gap-2"
              disabled={pauseMutation.isPending}
            >
              <Pause className="w-4 h-4" />
              Jeda
            </button>
          )}

          {campaign.status === 'paused' && (
            <>
              <button
                onClick={handleStart}
                className="px-3 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-2"
                disabled={startMutation.isPending}
              >
                <Play className="w-4 h-4" />
                Lanjutkan
              </button>
              <button
                onClick={handleCancel}
                className="px-3 py-2 text-sm bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center gap-2"
                disabled={cancelMutation.isPending}
              >
                <XCircle className="w-4 h-4" />
                Batalkan
              </button>
            </>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard icon={Users} label="Total" value={campaign.total_recipients} color="bg-blue-100 dark:bg-blue-900/40" subtext="Semua penerima" />
        <StatCard icon={Send} label="Terkirim" value={campaign.sent_count} color="bg-green-100 dark:bg-green-900/40" />
        <StatCard icon={AlertTriangle} label="Gagal" value={campaign.failed_count} color="bg-red-100 dark:bg-red-900/40" />
        <StatCard icon={CheckCircle2} label="Progres" value={campaign.total_recipients > 0 ? Math.round((campaign.sent_count / campaign.total_recipients) * 100) : 0} color="bg-purple-100 dark:bg-purple-900/40" subtext="persen" />
      </div>

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
                <div className="mt-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                  <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mb-1">Placeholder yang tersedia:</p>
                  <p className="text-xs text-blue-500 dark:text-blue-300">
                    {'{{university_name}}'} = Nama Universitas<br/>
                    {'{{email}}'} = Email Universitas<br/>
                    {'{{tanggal}}'} = Tanggal Hari Ini<br/>
                    {'{{nomor_surat}}'} = Nomor Surat Otomatis
                  </p>
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
                  <div className="mt-2 text-xs text-blue-600 dark:text-blue-400">
                    Placeholder terdeteksi: {attachmentData.detected_variables.map(v => `{{${v}}}`).join(', ')}
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
                <div className="p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                  <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-1">Placeholder untuk DOCX:</p>
                  <p className="text-xs text-amber-500 dark:text-amber-300">
                    {'{{university_name}}'} • {'{{email}}'} • {'{{tanggal}}'} • {'{{nomor_surat}}'}
                  </p>
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
          <CollapsibleSection title={`Penerima (${recipients.length})`} icon={Users}>
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

    </div>
  )
}
