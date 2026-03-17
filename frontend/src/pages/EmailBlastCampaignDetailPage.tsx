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
} from '../hooks/useEmailBlast'
import type { EmailBlastCampaign, EmailBlastRecipient } from '../api/emailBlast'
import { useUniversitiesWithEmails, useProvinces } from '../hooks/useUniversities'
import { useAddSelectedRecipients } from '../hooks/useEmailBlast'

const statusConfig: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  draft: { label: 'Draft', color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-100 dark:bg-gray-800', icon: RefreshCw },
  running: { label: 'Sending', color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/30', icon: Play },
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

  const { data: campaignData, isLoading: campaignLoading } = useEmailBlastCampaign(campaignId)
  const { data: recipientsData, isLoading: recipientsLoading, refetch } = useEmailBlastRecipients(campaignId, statusFilter)

  const startMutation = useStartEmailCampaign()
  const pauseMutation = usePauseEmailCampaign()
  const cancelMutation = useCancelEmailCampaign()
  const addRecipientsMutation = useAddAllRecipients()
  const addSelectedRecipientsMutation = useAddSelectedRecipients()
  const updateMutation = useUpdateEmailCampaign()
  const uploadAttachmentMutation = useUploadAttachment()
  const { data: attachmentData } = useCampaignAttachment(campaignId)

  // University selector queries
  const { data: provinces } = useProvinces()
  const { data: uniData, isLoading: uniLoading } = useUniversitiesWithEmails(uniProvince || undefined, uniSearch, 500, 0)
  const universities = uniData?.data || []

  const campaign = campaignData?.campaign
  const recipients = recipientsData?.recipients || []

  // Initialize edit fields when campaign loads
  useEffect(() => {
    if (campaign) {
      setEditSubject(campaign.subject || '')
      setEditTemplate(campaign.template_message || '')
      setEditDelay(campaign.delay_between_ms || 8000)
    }
  }, [campaign])

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
          <p className="text-gray-500">Campaign not found</p>
          <Link to="/email-blast" className="mt-4 text-blue-600 hover:underline">
            Back to campaigns
          </Link>
        </div>
      </div>
    )
  }

  const handleStart = () => {
    startMutation.mutate({ campaign_id: campaignId, max_recipients: maxRecipients })
  }

  const handlePause = () => {
    pauseMutation.mutate(campaignId)
  }

  const handleCancel = () => {
    if (confirm('Are you sure you want to cancel this campaign?')) {
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
    } else {
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
                Add All
              </button>
              <button
                onClick={handleStart}
                className="px-3 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-2"
                disabled={startMutation.isPending}
              >
                <Play className="w-4 h-4" />
                Start
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
              Pause
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
                Resume
              </button>
              <button
                onClick={handleCancel}
                className="px-3 py-2 text-sm bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center gap-2"
                disabled={cancelMutation.isPending}
              >
                <XCircle className="w-4 h-4" />
                Cancel
              </button>
            </>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-4">
          <div className="text-2xl font-bold">{campaign.total_recipients}</div>
          <div className="text-sm text-gray-500">Total</div>
        </div>
        <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-4">
          <div className="text-2xl font-bold text-green-600">{campaign.sent_count}</div>
          <div className="text-sm text-gray-500">Sent</div>
        </div>
        <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-4">
          <div className="text-2xl font-bold text-red-600">{campaign.failed_count}</div>
          <div className="text-sm text-gray-500">Failed</div>
        </div>
        <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-4">
          <div className="text-2xl font-bold">
            {campaign.total_recipients > 0
              ? Math.round((campaign.sent_count / campaign.total_recipients) * 100)
              : 0}%
          </div>
          <div className="text-sm text-gray-500">Progress</div>
        </div>
      </div>

      {/* Campaign Details - with inline editing for draft/paused */}
      <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl p-4 mb-6">
        <h3 className="font-semibold mb-4">Campaign Details</h3>

        <div className="space-y-4">
          {/* Subject */}
          <div>
            <label className="block text-sm font-medium mb-1">Subject</label>
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
            <label className="block text-sm font-medium mb-1">Template Message</label>
            {campaign.status === 'draft' || campaign.status === 'paused' ? (
              <>
                <textarea
                  value={editTemplate}
                  onChange={(e) => setEditTemplate(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 h-32"
                  placeholder="Yth. Bagian Sekretariat {{university_name}}, ..."
                />
                <p className="text-xs text-gray-500 mt-1">
                  Available: {'{{university_name}}'}, {'{{email}}'}, {'{{tanggal}}'}
                </p>
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
              <label className="block text-sm font-medium mb-1">Delay (ms)</label>
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
              <label className="block text-sm font-medium mb-1">From</label>
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
                {attachmentData.variables && Object.keys(attachmentData.variables).length > 0 && (
                  <div className="mt-2 text-xs text-gray-500">
                    Variables: {Object.keys(attachmentData.variables).join(', ')}
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
                    <button
                      onClick={handleUploadAttachment}
                      disabled={uploadAttachmentMutation.isPending}
                      className="px-3 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 flex items-center gap-1"
                    >
                      <Upload className="w-4 h-4" />
                      {uploadAttachmentMutation.isPending ? 'Uploading...' : 'Upload'}
                    </button>
                  )}
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

          {/* Save Button */}
          {(campaign.status === 'draft' || campaign.status === 'paused') && (
            <div className="flex justify-end">
              <button
                onClick={handleSaveEdit}
                disabled={updateMutation.isPending}
                className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 flex items-center gap-2"
              >
                <Save className="w-4 h-4" />
                {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Recipients */}
      <div className="bg-white dark:bg-gray-900 border dark:border-gray-800 rounded-xl">
        <div className="p-4 border-b dark:border-gray-800 flex items-center justify-between">
          <h3 className="font-semibold">Recipients</h3>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <select
              value={statusFilter || ''}
              onChange={(e) => setStatusFilter(e.target.value || undefined)}
              className="text-sm border rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-700"
            >
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="sent">Sent</option>
              <option value="failed">Failed</option>
            </select>
            <button
              onClick={() => refetch()}
              className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {recipientsLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : recipients.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            No recipients found
          </div>
        ) : (
          <div className="divide-y dark:divide-gray-800">
            {recipients.slice(0, 100).map((recipient: EmailBlastRecipient) => (
              <div key={recipient.id} className="p-4 flex items-center justify-between">
                <div>
                  <div className="font-medium">{recipient.university_name || 'Unknown'}</div>
                  <div className="text-sm text-gray-500">{recipient.email}</div>
                </div>
                <div className="flex items-center gap-2">
                  {recipient.status === 'pending' && (
                    <span className="text-xs text-gray-500">Pending</span>
                  )}
                  {recipient.status === 'sent' && (
                    <span className="inline-flex items-center gap-1 text-xs text-green-600">
                      <CheckCircle2 className="w-3 h-3" /> Sent
                    </span>
                  )}
                  {recipient.status === 'failed' && (
                    <span className="inline-flex items-center gap-1 text-xs text-red-600" title={recipient.error_message || ''}>
                      <AlertCircle className="w-3 h-3" /> Failed
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {recipients.length > 100 && (
          <div className="p-4 text-center text-sm text-gray-500 border-t dark:border-gray-800">
            Showing 100 of {recipients.length} recipients
          </div>
        )}
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
                <option value="">All Provinces</option>
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
                Select All ({universities.length})
              </button>
              {selectedUniIds.size > 0 && (
                <span className="text-sm text-blue-600">{selectedUniIds.size} selected</span>
              )}
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto">
              {uniLoading ? (
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
                {selectedUniIds.size > 0 ? `${selectedUniIds.size} selected` : `${universities.length} universities`}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowSelectUni(false)}
                  className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmSelectUni}
                  disabled={selectedUniIds.size === 0 || addSelectedRecipientsMutation.isPending}
                  className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
                >
                  {addSelectedRecipientsMutation.isPending ? 'Adding...' : 'Add to Campaign'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
