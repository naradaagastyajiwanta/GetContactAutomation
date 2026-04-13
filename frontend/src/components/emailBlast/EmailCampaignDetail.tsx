/**
 * EmailCampaignDetail — Campaign compose + management with tabs.
 * Features: Preview, Attachment Variables, Retry Failed
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ArrowLeft,
  Save,
  Rocket,
  Pause,
  XCircle,
  Users,
  Send,
  Paperclip,
  Upload,
  RefreshCw,
  Inbox,
  Search,
  CheckCircle2,
  Check,
  Clock,
  AlertTriangle,
  AlertCircle,
  Plus,
  FileText,
  Eye,
  RotateCcw,
  ChevronDown,
  Mail,
  Play,
} from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import * as XLSX from 'xlsx'
import { cn, formatRelative } from '../../lib/utils'
import {
  useEmailBlastCampaign,
  useEmailBlastRecipients,
  useStartEmailCampaign,
  usePauseEmailCampaign,
  useCancelEmailCampaign,
  useUpdateEmailCampaign,
  useAddAllRecipients,
  useDeleteEmailRecipient,
  useSentEmails,
  useInboxEmails,
  useCampaignAttachment,
  useAddSelectedRecipients,
  useCreateEmailCampaign,
  useUploadAttachment,
  useUploadExternalRecipients,
  useSendTestEmail,
} from '../../hooks/useEmailBlast'
import { useUniversitiesWithEmails, useProvinces } from '../../hooks/useUniversities'
import { useUniversityGroups } from '../../hooks/useUniversityGroups'
import { Spinner } from '../ui/Spinner'
import { Button } from '../ui/Button'
import { EmptyState } from '../ui/EmptyState'
import { Modal } from '../ui/Modal'
import type { EmailBlastCampaign } from '../../api/emailBlast'
import type { AttachmentInfo } from '../../api/emailBlast'

interface Props {
  campaignId?: number
  canManage: boolean
  onClose: () => void
  onCompose?: () => void
}

// ─── Status Badge Config ─────────────────────────────────────────────────────

const statusConfig: Record<string, { label: string; icon: React.ElementType; color: string; bg: string }> = {
  draft: { label: 'Draft', icon: FileText, color: 'text-gray-500', bg: 'bg-gray-100 text-gray-600' },
  running: { label: 'Active', icon: Rocket, color: 'text-blue-600', bg: 'bg-blue-100 text-blue-700' },
  paused: { label: 'Paused', icon: Pause, color: 'text-amber-600', bg: 'bg-amber-100 text-amber-700' },
  completed: { label: 'Done', icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-100 text-green-700' },
  cancelled: { label: 'Cancelled', icon: XCircle, color: 'text-red-600', bg: 'bg-red-100 text-red-700' },
}

const AUTO_PLACEHOLDERS = ['university_name', 'email', 'tanggal', 'nomor_surat']

const EMAIL_COLUMN_KEYWORDS = ['email', 'e-mail', 'email address', 'alamat email', 'mail']
const NAME_COLUMN_KEYWORDS = ['name', 'nama', 'university', 'instansi', 'company', 'lembaga', 'organization']

function normalizeSpreadsheetCell(value: unknown): string {
  return String(value ?? '').trim()
}

function normalizeSpreadsheetHeader(value: unknown): string {
  return normalizeSpreadsheetCell(value).toLowerCase()
}

function detectHeaderRow(rows: unknown[][]): number {
  for (let i = 0; i < Math.min(rows.length, 10); i += 1) {
    const normalized = rows[i].map(normalizeSpreadsheetHeader)
    if (normalized.some((cell) => EMAIL_COLUMN_KEYWORDS.some((keyword) => cell.includes(keyword)))) {
      return i
    }
  }
  return 0
}

function detectColumnIndex(headers: unknown[], keywords: string[]): number {
  const normalizedHeaders = headers.map(normalizeSpreadsheetHeader)
  return normalizedHeaders.findIndex((header) => keywords.some((keyword) => header.includes(keyword)))
}

function parseRecipientSpreadsheet(file: File): Promise<unknown[][]> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const workbook = XLSX.read(event.target?.result, { type: 'binary' })
        const worksheet = workbook.Sheets[workbook.SheetNames[0]]
        const rows = XLSX.utils.sheet_to_json(worksheet, { header: 1, raw: false }) as unknown[][]
        resolve(rows)
      } catch (error) {
        reject(error)
      }
    }
    reader.onerror = () => reject(new Error('Gagal membaca file'))
    reader.readAsBinaryString(file)
  })
}

// ─── Template Rendering (client-side preview) ─────────────────────────────────

function renderPreview(text: string | null | undefined, vars: Record<string, string>): string {
  if (!text) return ''
  let result = text
  for (const [key, val] of Object.entries(vars)) {
    result = result.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), val || `{{${key}}}`)
  }
  return result
}

// ─── Preview Modal ─────────────────────────────────────────────────────────────

function PreviewModal({
  isOpen,
  onClose,
  subject,
  body,
  fromEmail,
  fromName,
  attachmentFilename,
  vars,
  sampleUniversity,
}: {
  isOpen: boolean
  onClose: () => void
  subject: string | undefined
  body: string | undefined
  fromEmail: string
  fromName: string
  attachmentFilename?: string
  vars: Record<string, string>
  sampleUniversity: string
}) {
  const renderedSubject = renderPreview(subject, {
    university_name: sampleUniversity,
    email: 'contoh@universitas.ac.id',
    tanggal: new Date().toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' }),
    nomor_surat: '001/ASOSIASI/2026',
    ...vars,
  })
  const renderedBody = renderPreview(body, {
    university_name: sampleUniversity,
    email: 'contoh@universitas.ac.id',
    tanggal: new Date().toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' }),
    nomor_surat: '001/ASOSIASI/2026',
    ...vars,
  })

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Preview Email" size="lg">
      <div className="space-y-4">
        {/* Email meta */}
        <div className="space-y-1 rounded-lg border border-gray-100 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900">
              <Send className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-gray-900 dark:text-white">
                {fromName} <span className="font-normal text-gray-400">&lt;{fromEmail}&gt;</span>
              </p>
              <p className="text-xs text-gray-400">To: contoh@universitas.ac.id</p>
              <p className="mt-1 text-sm font-medium text-gray-900 dark:text-white">
                Subject: {renderedSubject}
              </p>
            </div>
          </div>
        </div>

        {/* Email body */}
        <div className="min-h-[200px] max-h-[400px] overflow-y-auto rounded-lg border border-gray-100 px-5 py-4 dark:border-gray-700">
          <div className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
            {renderedBody}
          </div>
        </div>

        {/* Attachment indicator */}
        {attachmentFilename && (
          <div className="flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800">
            <Paperclip className="h-4 w-4 text-gray-400" />
            <span className="text-sm text-gray-600 dark:text-gray-300">
              {attachmentFilename}
            </span>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end pt-2">
          <Button variant="secondary" onClick={onClose}>Close</Button>
        </div>
      </div>
    </Modal>
  )
}

// ─── Test Email Modal ───────────────────────────────────────────────────────

function TestEmailModal({
  isOpen,
  onClose,
  campaignId,
  subject,
  body,
  fromEmail,
  fromName,
  attachment,
  varValues,
}: {
  isOpen: boolean
  onClose: () => void
  campaignId: number
  subject: string
  body: string
  fromEmail: string
  fromName: string
  attachment?: AttachmentInfo
  varValues: Record<string, string>
}) {
  const [toEmail, setToEmail] = useState('')

  const sendMutation = useSendTestEmail()

  // Filter out auto placeholders for custom vars
  const customVars = attachment?.variables
    ? Object.keys(attachment.variables).filter((k) => !AUTO_PLACEHOLDERS.includes(k))
    : []

  async function handleSend() {
    if (!toEmail.trim() || !toEmail.includes('@')) {
      toast.error('Enter a valid email address')
      return
    }
    try {
      const res = await sendMutation.mutateAsync({
        campaignId,
        toEmail: toEmail.trim(),
        options: {
          subject,
          body,
          fromEmail,
          fromName,
          attachmentFilename: attachment?.filename,
          customVars: varValues,
        },
      })
      if (res.success) {
        toast.success(res.message)
        onClose()
      } else {
        toast.error(res.message)
      }
    } catch {
      toast.error('Failed to send test email')
    }
  }

  // Extract preview values for display
  const previewVars = {
    university_name: 'Universitas Gadjah Mada',
    email: toEmail || 'contoh@universitas.ac.id',
    tanggal: new Date().toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' }),
    nomor_surat: '001/ASOSIASI/2026',
    ...varValues,
  }

  const previewSubject = renderPreview(subject, previewVars)
  const previewBody = renderPreview(body, previewVars)

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Send Test Email" size="md">
      <div className="space-y-4">
        {/* To email input */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
            Send to
          </label>
          <div className="flex gap-2">
            <input
              type="email"
              value={toEmail}
              onChange={(e) => setToEmail(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="your@email.com"
              className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
            <Button onClick={handleSend} loading={sendMutation.isPending}>
              <Mail className="h-4 w-4" />
              Send
            </Button>
          </div>
        </div>

        {/* From info */}
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Send className="h-3.5 w-3.5" />
          <span>From: {fromName} &lt;{fromEmail}&gt;</span>
        </div>

        {/* Preview */}
        <div className="space-y-2 rounded-lg border border-gray-100 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800">
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400">
            Preview (with sample values)
          </p>
          <div className="space-y-1">
            <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
              Subject: {previewSubject || '(no subject)'}
            </p>
            <div className="max-h-32 overflow-y-auto text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
              {previewBody || '(no body)'}
            </div>
          </div>
        </div>

        {/* Attachment notice */}
        {attachment?.filename && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Paperclip className="h-3.5 w-3.5" />
            <span>Attachment: {attachment.filename}</span>
            {customVars.length > 0 && (
              <span className="text-indigo-500">(with custom variables)</span>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}

// ─── Attachment Variable Form ────────────────────────────────────────────────

function AttachmentVarForm({
  attachment,
  campaignId,
  onSaved,
}: {
  attachment: AttachmentInfo | undefined
  campaignId: number
  onSaved: () => void
}) {
  // Show ALL detected variables from the DOCX file, not just ones in variables
  const allDetectedVars = attachment?.detected_variables ?? []
  const customVars = allDetectedVars.filter((k) => !AUTO_PLACEHOLDERS.includes(k))

  const [values, setValues] = useState<Record<string, string>>({})
  const [isSaving, setIsSaving] = useState(false)
  const [expanded, setExpanded] = useState(customVars.length > 0)

  // Initialize form values from attachment.variables (saved values)
  useEffect(() => {
    if (attachment?.variables) {
      setValues(attachment.variables)
    }
  }, [attachment])

  // NOTE: useUploadAttachment hook MUST be called before any early returns.
  // React hooks require consistent order across renders.
  const uploadMutation = useUploadAttachment()

  // Early return AFTER hooks — required for hooks consistency
  if (customVars.length === 0) return null

  function setValue(key: string, val: string) {
    setValues((prev) => ({ ...prev, [key]: val }))
  }

  async function handleSave() {
    setIsSaving(true)
    try {
      const fileInput = document.getElementById('attachment-reupload') as HTMLInputElement
      if (fileInput?.files?.[0]) {
        await uploadMutation.mutateAsync({ campaignId, file: fileInput.files[0], variables: values })
      }
      // If no file, just save values
      toast.success('Variable values saved')
      onSaved()
    } catch {
      toast.error('Failed to save variables')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
      >
        <div className="flex items-center gap-2">
          <Paperclip className="h-4 w-4 text-purple-500" />
          <span className="text-sm font-semibold text-gray-900 dark:text-white">
            Attachment Variables
          </span>
          <span className="rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-semibold text-purple-600 dark:bg-purple-900 dark:text-purple-300">
            {customVars.length}
          </span>
        </div>
        <ChevronDown
          className={cn('h-4 w-4 text-gray-400 transition-transform', expanded && 'rotate-180')}
        />
      </button>

      {/* Form */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 py-4 space-y-3 dark:border-gray-700">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Isi nilai untuk setiap variable yang terdeteksi di lampiran DOCX.
            Nilai ini akan digunakan saat email dikirim.
          </p>

          {customVars.map((key) => {
            const hasValue = !!(values[key] ?? '').trim()
            return (
              <div key={key}>
                <label className={cn(
                  'mb-1 block text-xs font-medium',
                  hasValue ? 'text-gray-600 dark:text-gray-400' : 'text-amber-600 dark:text-amber-400'
                )}>
                  {`{{${key}}}`}
                  {!hasValue && <span className="ml-1 text-[10px]">(belum diisi)</span>}
                </label>
                <input
                  type="text"
                  value={values[key] ?? ''}
                  onChange={(e) => setValue(key, e.target.value)}
                  placeholder={`Masukkan nilai untuk ${key}...`}
                  className={cn(
                    'w-full rounded-lg border bg-gray-50 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500',
                    !hasValue ? 'border-amber-300 dark:border-amber-700' : 'border-gray-200'
                  )}
                />
              </div>
            )
          })}

          {/* Hidden file input for re-upload with new variables */}
          <input
            id="attachment-reupload"
            type="file"
            accept=".docx"
            className="hidden"
          />

          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={handleSave}
              loading={isSaving || uploadMutation.isPending}
            >
              <Save className="h-3.5 w-3.5" />
              Save Variables
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Content Tab ──────────────────────────────────────────────────────────────

function ContentTab({
  campaign,
  attachment,
  campaignId,
  canManage,
  onSave,
  isSaving,
  onPendingSavesChange,
}: {
  campaign: EmailBlastCampaign
  attachment: AttachmentInfo | undefined
  campaignId: number
  canManage: boolean
  onSave: (data: { name: string; subject: string; template_message: string; delay_between_ms: number }) => void
  isSaving: boolean
  onPendingSavesChange?: (pending: boolean) => void
}) {
  const [name, setName] = useState(campaign.name ?? '')
  const [subject, setSubject] = useState(campaign.subject ?? '')
  const [body, setBody] = useState(campaign.template_message ?? '')
  const [delayMs, setDelayMs] = useState(campaign.delay_between_ms / 1000)
  const [showPreview, setShowPreview] = useState(false)
  const [showTestEmail, setShowTestEmail] = useState(false)
  const [varValues, setVarValues] = useState<Record<string, string>>({})
  const [autoSaveTimer, setAutoSaveTimer] = useState<ReturnType<typeof setTimeout> | null>(null)
  // Use a boolean flag — don't track count, only whether a save is in-flight
  const [isDirty, setIsDirty] = useState(false)

  const uploadMutation = useUploadAttachment()
  const updateMutation = useUpdateEmailCampaign()

  useEffect(() => {
    setName(campaign.name ?? '')
    setSubject(campaign.subject ?? '')
    setBody(campaign.template_message ?? '')
    setDelayMs(campaign.delay_between_ms / 1000)
    setIsDirty(false)
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    setAutoSaveTimer(null)
  }, [campaign])

  // Auto-save: debounced save on any field change
  const triggerAutoSave = () => {
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    setIsDirty(true)
    onPendingSavesChange?.(true)
    const timer = setTimeout(() => {
      updateMutation.mutate(
        { id: campaignId, data: { subject, template_message: body, delay_between_ms: delayMs * 1000 } },
        {
          onSuccess: () => {
            setIsDirty(false)
            onPendingSavesChange?.(false)
          },
          onError: () => {
            setIsDirty(false)
            onPendingSavesChange?.(false)
            toast.error('Auto-save failed')
          },
        },
      )
    }, 1000)
    setAutoSaveTimer(timer)
  }

  const handleNameChange = (val: string) => { setName(val); triggerAutoSave() }
  const handleSubjectChange = (val: string) => { setSubject(val); triggerAutoSave() }
  const handleBodyChange = (val: string) => { setBody(val); triggerAutoSave() }

  useEffect(() => {
    if (attachment?.variables) {
      setVarValues(attachment.variables)
    }
  }, [attachment])

  const isReadOnly = !canManage || campaign.status === 'running' || campaign.status === 'completed' || campaign.status === 'cancelled'
  const customVars = attachment?.variables
    ? Object.keys(attachment.variables).filter((k) => !AUTO_PLACEHOLDERS.includes(k))
    : []

  function insertPlaceholder(p: string) {
    if (isReadOnly) return
    const next = body + p
    setBody(next)
    triggerAutoSave()
  }

  function handleSave() {
    if (isReadOnly) return
    // Cancel pending auto-save and save immediately
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
      setAutoSaveTimer(null)
    }
    onPendingSavesChange?.(true)
    updateMutation.mutate(
      { id: campaignId, data: { subject, template_message: body, delay_between_ms: delayMs * 1000 } },
      {
        onSuccess: () => {
          setIsDirty(false)
          onPendingSavesChange?.(false)
          toast.success('Saved')
        },
        onError: () => {
          setIsDirty(false)
          onPendingSavesChange?.(false)
          toast.error('Failed to save')
        },
      },
    )
  }

  async function handleAttachmentUpload(file: File) {
    if (!campaignId || isReadOnly) return
    try {
      await uploadMutation.mutateAsync({ campaignId, file, variables: varValues })
      toast.success('Attachment uploaded')
    } catch {
      toast.error('Failed to upload attachment')
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Campaign Name */}
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Campaign Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            disabled={isReadOnly}
            placeholder="e.g., Undangan Audiensi Q2 2025"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:disabled:bg-gray-900"
          />
        </div>

        {/* Subject */}
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Subject
          </label>
          <div className="relative">
            <input
              type="text"
              value={subject}
              onChange={(e) => handleSubjectChange(e.target.value)}
              disabled={isReadOnly}
              placeholder="Email subject..."
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 pr-20 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:disabled:bg-gray-900"
            />
            <button
              onClick={() => setShowPreview(true)}
              className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 rounded-md px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-950"
            >
              <Eye className="h-3.5 w-3.5" />
              Preview
            </button>
          </div>
        </div>

        {/* Placeholders */}
        <div className="flex flex-wrap gap-1.5">
          {AUTO_PLACEHOLDERS.map((p) => (
            <button
              key={p}
              onClick={() => insertPlaceholder(`{{${p}}}`)}
              disabled={isReadOnly}
              className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[11px] font-mono text-gray-500 transition-colors hover:border-indigo-300 hover:text-indigo-600 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400"
            >
              {`{{${p}}}`}
            </button>
          ))}
          {customVars.map((v) => (
            <button
              key={v}
              onClick={() => insertPlaceholder(`{{${v}}}`)}
              disabled={isReadOnly}
              className="rounded-md border border-purple-200 bg-purple-50 px-2 py-1 text-[11px] font-mono text-purple-600 transition-colors hover:border-purple-400 hover:text-purple-700 disabled:opacity-50 dark:border-purple-900 dark:bg-purple-950 dark:text-purple-400"
            >
              {`{{${v}}}`}
            </button>
          ))}
        </div>

        {/* Body */}
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Body
            </label>
            <button
              onClick={() => setShowPreview(true)}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-950"
            >
              <Eye className="h-3.5 w-3.5" />
              Preview
            </button>
          </div>
          <textarea
            value={body}
            onChange={(e) => handleBodyChange(e.target.value)}
            disabled={isReadOnly}
            rows={12}
            placeholder="Email body... Gunakan {{university_name}}, {{tanggal}}, dll untuk placeholder."
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:disabled:bg-gray-900 resize-none font-mono leading-relaxed"
          />
        </div>

        {/* Attachment */}
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Attachment
          </label>
          {attachment?.filename ? (
            <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800">
              <Paperclip className="h-4 w-4 text-gray-400" />
              <span className="flex-1 text-sm font-medium text-gray-700 dark:text-gray-200">
                {attachment.filename}
              </span>
              {attachment.detected_variables && attachment.detected_variables.length > 0 && (
                <span className="text-xs text-purple-600 dark:text-purple-400" title={`${attachment.detected_variables.length} placeholder detected in DOCX`}>
                  {attachment.detected_variables.length} placeholders
                </span>
              )}
              {!isReadOnly && (
                <button
                  onClick={() => {
                    const input = document.createElement('input')
                    input.type = 'file'
                    input.accept = '.docx'
                    input.onchange = (e) => {
                      const file = (e.target as HTMLInputElement).files?.[0]
                      if (file) handleAttachmentUpload(file)
                    }
                    input.click()
                  }}
                  className="text-xs text-indigo-600 hover:text-indigo-700"
                >
                  Replace
                </button>
              )}
            </div>
          ) : (
            <div>
              <input
                id="email-attachment"
                type="file"
                accept=".docx"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file && campaignId) handleAttachmentUpload(file)
                }}
                disabled={isReadOnly || uploadMutation.isPending}
                className="hidden"
              />
              <label
                htmlFor="email-attachment"
                className={cn(
                  'flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed border-gray-200 px-4 py-6 text-sm text-gray-500 transition-colors hover:border-indigo-300 hover:text-indigo-600 dark:border-gray-700 dark:text-gray-400 dark:hover:border-indigo-500 dark:hover:text-indigo-400',
                  (isReadOnly || uploadMutation.isPending) && 'opacity-50 cursor-not-allowed',
                )}
              >
                {uploadMutation.isPending ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4" />
                    Upload DOCX (optional)
                  </>
                )}
              </label>
            </div>
          )}
        </div>

        {/* Attachment Variable Form */}
        {canManage && attachment?.filename && campaignId && (
          <AttachmentVarForm
            attachment={attachment}
            campaignId={campaignId}
            onSaved={() => {}}
          />
        )}

        {/* Delay */}
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Delay Between Emails (seconds)
          </label>
          <input
            type="number"
            value={delayMs}
            onChange={(e) => { setDelayMs(parseInt(e.target.value) || 1); triggerAutoSave() }}
            disabled={isReadOnly}
            min={1}
            max={300}
            className="w-32 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:disabled:bg-gray-900"
          />
        </div>
      </div>

      {/* Actions */}
      {canManage && !isReadOnly && (
        <div className="flex items-center justify-between border-t border-gray-100 px-5 py-3 dark:border-gray-800">
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={handleSave} loading={updateMutation.isPending}>
              <Save className="h-4 w-4" />
              Save Draft
            </Button>
            <Button variant={isDirty ? 'secondary' : 'success'} disabled={isDirty} onClick={() => setShowTestEmail(true)}>
              <Mail className="h-4 w-4" />
              Send Test Email
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">
              {updateMutation.isPending || isDirty ? 'Saving...' : 'Auto-saves'}
            </span>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      <PreviewModal
        isOpen={showPreview}
        onClose={() => setShowPreview(false)}
        subject={subject}
        body={body}
        fromEmail={campaign.from_email || 'noreply@email.com'}
        fromName={campaign.from_name || 'Asosiasi AI'}
        attachmentFilename={attachment?.filename ?? undefined}
        vars={varValues}
        sampleUniversity="Universitas Gadjah Mada"
      />

      {/* Test Email Modal */}
      <TestEmailModal
        isOpen={showTestEmail}
        onClose={() => setShowTestEmail(false)}
        campaignId={campaignId}
        subject={subject}
        body={body}
        fromEmail={campaign.from_email || 'sekretariat@asosiasi.ai'}
        fromName={campaign.from_name || 'Sekretariat Asosiasi AI'}
        attachment={attachment}
        varValues={varValues}
      />
    </div>
  )
}

// ─── Recipients Tab ───────────────────────────────────────────────────────────

function RecipientsTab({
  campaignId,
  campaign,
  canManage,
}: {
  campaignId: number
  campaign: EmailBlastCampaign
  canManage: boolean
}) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [showAddModal, setShowAddModal] = useState(false)

  const { data, refetch } = useEmailBlastRecipients(campaignId, statusFilter || undefined)
  const deleteMutation = useDeleteEmailRecipient()

  const recipients = data?.recipients ?? []
  const isReadOnly = !canManage || campaign.status === 'running' || campaign.status === 'completed' || campaign.status === 'cancelled'

  const filtered = search.trim()
    ? recipients.filter(
        (r) =>
          (r.university_name ?? '').toLowerCase().includes(search.toLowerCase()) ||
          (r.email ?? '').toLowerCase().includes(search.toLowerCase()),
      )
    : recipients

  function handleDelete(recipientId: number) {
    if (isReadOnly) return
    deleteMutation.mutate({ campaignId, recipientId })
  }

  const pendingCount = recipients.filter((r) => r.status === 'pending').length
  const sentCount = recipients.filter((r) => r.status === 'sent').length
  const failedCount = recipients.filter((r) => r.status === 'failed').length
  const invalidCount = recipients.filter((r) => r.status === 'invalid').length

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Stats bar */}
      <div className="flex items-center gap-4 border-b border-gray-200 bg-white px-4 py-2 dark:border-gray-800 dark:bg-[#111827]">
        <span className="flex items-center gap-1 text-xs text-gray-500">
          <span className="font-semibold text-gray-700 dark:text-gray-200">{recipients.length}</span> total
        </span>
        {sentCount > 0 && (
          <span className="flex items-center gap-1 text-xs text-green-600">
            <CheckCircle2 className="h-3 w-3" /> {sentCount} sent
          </span>
        )}
        {pendingCount > 0 && (
          <span className="flex items-center gap-1 text-xs text-amber-500">
            <Clock className="h-3 w-3" /> {pendingCount} pending
          </span>
        )}
        {failedCount > 0 && (
          <span className="flex items-center gap-1 text-xs text-red-500">
            <XCircle className="h-3 w-3" /> {failedCount} failed
          </span>
        )}
        {invalidCount > 0 && (
          <span className="flex items-center gap-1 text-xs text-yellow-600">
            <AlertCircle className="h-3 w-3" /> {invalidCount} invalid
          </span>
        )}
      </div>

      {/* Header */}
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search..."
            className="h-8 w-40 rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-3 text-xs text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
          />
        </div>

        <div className="flex rounded-lg border border-gray-200 dark:border-gray-700">
          {['', 'pending', 'sent', 'failed', 'invalid'].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={cn(
                'px-2.5 py-1 text-[11px] font-medium transition-colors first:rounded-l-lg last:rounded-r-lg',
                statusFilter === s
                  ? 'bg-gray-900 text-white dark:bg-indigo-600 dark:text-white'
                  : 'text-gray-500 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800',
              )}
            >
              {s === '' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>

        {!isReadOnly && (
          <Button size="sm" variant="secondary" onClick={() => setShowAddModal(true)} className="ml-auto">
            <Plus className="h-3.5 w-3.5" />
            Add
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {recipients.length === 0 ? (
          <EmptyState
            icon={Users}
            title="No recipients yet"
            description="Add universities to send this campaign to."
            action={!isReadOnly ? (
              <Button size="sm" onClick={() => setShowAddModal(true)}>
                <Plus className="h-4 w-4" />
                Add Recipients
              </Button>
            ) : undefined}
          />
        ) : filtered.length === 0 ? (
          <EmptyState icon={Search} title="No recipients match" description="Try a different search term." />
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-800/80">
            {filtered.map((recipient) => (
              <div key={recipient.id} className="flex items-center gap-3 px-4 py-3">
                {recipient.status === 'sent' && <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />}
                {recipient.status === 'failed' && <XCircle className="h-4 w-4 shrink-0 text-red-500" />}
                {recipient.status === 'pending' && <Clock className="h-4 w-4 shrink-0 text-gray-400" />}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-gray-900 dark:text-gray-100">
                    {recipient.university_name || '(Unknown)'}
                  </p>
                  <p className="truncate text-[11px] text-gray-400">{recipient.email}</p>
                </div>
                {recipient.status === 'failed' && recipient.error_message && (
                  <span className="max-w-[150px] truncate text-[10px] text-red-500">{recipient.error_message}</span>
                )}
                {!isReadOnly && (
                  <button onClick={() => handleDelete(recipient.id)} className="shrink-0 text-gray-300 hover:text-red-500 transition-colors">
                    <XCircle className="h-4 w-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <AddRecipientsModal isOpen={showAddModal} onClose={() => setShowAddModal(false)} campaignId={campaignId} />
    </div>
  )
}

// ─── Add Recipients Modal ─────────────────────────────────────────────────────

function AddRecipientsModal({ isOpen, onClose, campaignId }: { isOpen: boolean; onClose: () => void; campaignId: number }) {
  const [sourceMode, setSourceMode] = useState<'system' | 'upload'>('system')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [province, setProvince] = useState('')
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<number>>(new Set())
  const [page, setPage] = useState(0)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [sheetRows, setSheetRows] = useState<unknown[][]>([])
  const [headerRowIndex, setHeaderRowIndex] = useState(0)
  const [emailColumnIndex, setEmailColumnIndex] = useState(-1)
  const [nameColumnIndex, setNameColumnIndex] = useState(-1)
  const PAGE_SIZE = 50
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounce search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setSearch(searchInput)
      setPage(0)
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [searchInput])

  useEffect(() => {
    let cancelled = false

    async function parseFile() {
      if (!uploadFile) {
        setSheetRows([])
        setHeaderRowIndex(0)
        setEmailColumnIndex(-1)
        setNameColumnIndex(-1)
        return
      }

      const ext = uploadFile.name.split('.').pop()?.toLowerCase()
      if (!ext || !['xlsx', 'xls', 'csv'].includes(ext)) {
        toast.error('Format file harus .xlsx, .xls, atau .csv')
        setUploadFile(null)
        return
      }

      try {
        const rows = await parseRecipientSpreadsheet(uploadFile)
        if (cancelled) return
        setSheetRows(rows)
        const detectedHeaderRow = detectHeaderRow(rows)
        setHeaderRowIndex(detectedHeaderRow)
        const headers = rows[detectedHeaderRow] ?? []
        setEmailColumnIndex(detectColumnIndex(headers, EMAIL_COLUMN_KEYWORDS))
        setNameColumnIndex(detectColumnIndex(headers, NAME_COLUMN_KEYWORDS))
      } catch {
        if (!cancelled) {
          toast.error('File tidak bisa dibaca. Coba simpan ulang sebagai .xlsx atau .csv')
          setUploadFile(null)
          setSheetRows([])
        }
      }
    }

    void parseFile()

    return () => {
      cancelled = true
    }
  }, [uploadFile])

  useEffect(() => {
    if (sheetRows.length === 0) return
    const headers = sheetRows[headerRowIndex] ?? []
    setEmailColumnIndex(detectColumnIndex(headers, EMAIL_COLUMN_KEYWORDS))
    setNameColumnIndex(detectColumnIndex(headers, NAME_COLUMN_KEYWORDS))
  }, [headerRowIndex, sheetRows])

  const { data: univData, isLoading } = useUniversitiesWithEmails(province || undefined, search, PAGE_SIZE, page * PAGE_SIZE)
  const { data: provinces } = useProvinces()
  const { data: groupsData } = useUniversityGroups()
  const addSelectedMutation = useAddSelectedRecipients()
  const addAllMutation = useAddAllRecipients()
  const uploadExternalMutation = useUploadExternalRecipients()

  const universities = univData?.data ?? []
  const total = univData?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleAddSelected() {
    // If groups are selected, pass group_ids instead (backend processes groups first, universities ignored)
    if (selectedGroupIds.size > 0 && selectedIds.size > 0) {
      toast.error('Please add groups and universities separately')
      return
    }
    if (selectedGroupIds.size > 0) {
      await addSelectedMutation.mutateAsync({
        id: campaignId,
        universityIds: Array.from(selectedIds),
        groupIds: Array.from(selectedGroupIds),
      })
    } else if (selectedIds.size === 0) {
      return
    } else {
      await addSelectedMutation.mutateAsync({ id: campaignId, universityIds: Array.from(selectedIds) })
    }
    setSelectedIds(new Set())
    setSelectedGroupIds(new Set())
    onClose()
    toast.success(`${selectedGroupIds.size > 0 ? selectedGroupIds.size + ' group(s)' : selectedIds.size} recipients added`)
  }

  async function handleAddAll() {
    await addAllMutation.mutateAsync(campaignId)
    onClose()
    toast.success('All universities added')
  }

  async function handleUploadExternalRecipients() {
    if (!uploadFile || sheetRows.length === 0) return

    if (emailColumnIndex < 0) {
      toast.error('Pilih kolom email terlebih dahulu')
      return
    }

    const dataRows = sheetRows.slice(headerRowIndex + 1)
    const rows = dataRows
      .map((row) => {
        const cells = Array.isArray(row) ? row : []
        const email = normalizeSpreadsheetCell(cells[emailColumnIndex])
        const name = nameColumnIndex >= 0 ? normalizeSpreadsheetCell(cells[nameColumnIndex]) : ''
        return {
          email,
          ...(name ? { name } : {}),
        }
      })
      .filter((row) => row.email || row.name)

    if (rows.length === 0) {
      toast.error('Tidak ada row data yang bisa diimport dari file ini')
      return
    }

    try {
      const result = await uploadExternalMutation.mutateAsync({
        campaignId,
        rows,
      })

      const summaryParts = [
        `${result.recipients_added} ditambahkan`,
      ]
      if (result.duplicate_or_existing > 0) {
        summaryParts.push(`${result.duplicate_or_existing} duplikat/existing`)
      }
      if (result.skipped_missing_email > 0) {
        summaryParts.push(`${result.skipped_missing_email} tanpa email`)
      }
      if (result.skipped_invalid_format > 0) {
        summaryParts.push(`${result.skipped_invalid_format} format tidak valid`)
      }

      toast.success(summaryParts.join(' • '))
      handleClose()
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Gagal upload recipient eksternal')
    }
  }

  function handleClose() {
    setSourceMode('system')
    setSelectedIds(new Set())
    setSelectedGroupIds(new Set())
    setPage(0)
    setSearchInput('')
    setSearch('')
    setUploadFile(null)
    setSheetRows([])
    setHeaderRowIndex(0)
    setEmailColumnIndex(-1)
    setNameColumnIndex(-1)
    onClose()
  }

  const uploadPreviewHeaders = Array.isArray(sheetRows[headerRowIndex]) ? sheetRows[headerRowIndex] : []
  const uploadPreviewRows = sheetRows
    .slice(headerRowIndex + 1)
    .filter((row) => Array.isArray(row) && row.some((cell) => normalizeSpreadsheetCell(cell)))
    .slice(0, 5)
  const headerRowOptions = sheetRows.slice(0, Math.min(sheetRows.length, 10))

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Add Recipients" size="lg">
      <div className="flex flex-col" style={{ height: '70vh' }}>
        <div className="mb-3 flex gap-2 rounded-xl bg-gray-100 p-1 dark:bg-gray-800">
          <button
            onClick={() => setSourceMode('system')}
            className={cn(
              'flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              sourceMode === 'system'
                ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100'
                : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100'
            )}
          >
            Dari System
          </button>
          <button
            onClick={() => setSourceMode('upload')}
            className={cn(
              'flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              sourceMode === 'upload'
                ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100'
                : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100'
            )}
          >
            Upload Excel
          </button>
        </div>

        {sourceMode === 'system' ? (
          <>
            {/* Search + Filter */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Search..."
                  className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 focus:border-indigo-500 focus:outline-none dark:text-gray-100"
                />
              </div>
              <select
                value={province}
                onChange={(e) => { setProvince(e.target.value); setPage(0); setSearchInput(''); setSearch('') }}
                className="text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 bg-white dark:bg-gray-800 dark:text-gray-100"
              >
                <option value="">All</option>
                {(provinces ?? []).map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            {/* Group chips */}
            {groupsData && groupsData.groups.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1">
                {groupsData.groups.map((g) => (
                  <button
                    key={g.id}
                    onClick={() => {
                      setSelectedGroupIds((prev) => {
                        const next = new Set(prev)
                        if (next.has(g.id)) next.delete(g.id)
                        else next.add(g.id)
                        return next
                      })
                    }}
                    className={cn(
                      'px-2.5 py-1 text-xs rounded-full border transition-colors',
                      selectedGroupIds.has(g.id)
                        ? 'bg-indigo-600 text-white border-indigo-600'
                        : 'bg-white text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700'
                    )}
                  >
                    {g.name}
                  </button>
                ))}
              </div>
            )}

            {/* List */}
            <div className="flex-1 overflow-y-auto min-h-0 mt-3 -mx-6 px-6">
              {isLoading ? (
                <div className="flex items-center justify-center py-16">
                  <Spinner />
                </div>
              ) : universities.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                  <Search className="w-8 h-8 mb-2 opacity-50" />
                  <p className="text-sm">No results</p>
                </div>
              ) : (
                universities.map((uni) => (
                  <div
                    key={uni.id}
                    onClick={() => toggleSelect(uni.id)}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors mb-0.5',
                      selectedIds.has(uni.id)
                        ? 'bg-indigo-50 dark:bg-indigo-950/30'
                        : 'hover:bg-gray-50 dark:hover:bg-gray-800/60'
                    )}
                  >
                    <div className={cn(
                      'w-4 h-4 rounded flex items-center justify-center shrink-0',
                      selectedIds.has(uni.id)
                        ? 'bg-indigo-600'
                        : 'border border-gray-300 dark:border-gray-600'
                    )}>
                      {selectedIds.has(uni.id) && <Check className="w-2.5 h-2.5 text-white" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{uni.name}</p>
                      <p className="text-xs text-gray-400 truncate">{uni.email || '—'}</p>
                    </div>
                    {uni.province && (
                      <span className="shrink-0 text-[11px] px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">{uni.province}</span>
                    )}
                  </div>
                ))
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => {
                    if (universities.every((u) => selectedIds.has(u.id))) {
                      setSelectedIds(new Set())
                    } else {
                      setSelectedIds((prev) => {
                        const next = new Set(prev)
                        universities.forEach((u) => next.add(u.id))
                        return next
                      })
                    }
                  }}
                  className="text-xs text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100"
                >
                  {universities.every((u) => selectedIds.has(u.id)) ? 'Uncheck all' : 'Check all'}
                </button>
                {selectedIds.size > 0 && (
                  <span className="text-xs text-indigo-600 font-medium">{selectedIds.size} selected</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {total > PAGE_SIZE && (
                  <div className="flex items-center gap-1 mr-2">
                    <button
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      disabled={page === 0}
                      className="w-6 h-6 flex items-center justify-center text-xs border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
                    >
                      ←
                    </button>
                    <span className="text-[11px] text-gray-400 px-1">{page + 1}/{totalPages}</span>
                    <button
                      onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                      disabled={page >= totalPages - 1}
                      className="w-6 h-6 flex items-center justify-center text-xs border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
                    >
                      →
                    </button>
                  </div>
                )}
                <button
                  onClick={handleClose}
                  className="px-4 py-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddAll}
                  disabled={addAllMutation.isPending}
                  className="px-3 py-1.5 text-xs border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  All ({total})
                </button>
                <button
                  onClick={handleAddSelected}
                  disabled={selectedIds.size === 0 && selectedGroupIds.size === 0}
                  className={cn(
                    'px-4 py-1.5 text-sm rounded-lg font-medium transition-colors',
                    selectedIds.size === 0 && selectedGroupIds.size === 0
                      ? 'bg-gray-100 text-gray-400 dark:bg-gray-700 cursor-not-allowed'
                      : 'bg-indigo-600 text-white hover:bg-indigo-700'
                  )}
                >
                  Add {selectedIds.size > 0 ? `(${selectedIds.size})` : selectedGroupIds.size > 0 ? `(${selectedGroupIds.size})` : ''}
                </button>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/30 dark:text-indigo-300">
              Upload file recipient eksternal untuk campaign ini. Data akan masuk langsung ke recipient campaign dan tidak akan ditambahkan ke tabel universitas. Kalau sistem salah deteksi, Anda bisa pilih sendiri baris header dan kolom email.
            </div>

            <div className="mt-4 rounded-xl border border-dashed border-gray-300 p-5 dark:border-gray-700">
              <div className="flex items-start gap-3">
                <div className="rounded-lg bg-gray-100 p-2 dark:bg-gray-800">
                  <Upload className="h-4 w-4 text-gray-500 dark:text-gray-300" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Upload Excel atau CSV</p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Setelah file dibaca, Anda bisa pilih sendiri baris header, kolom email, dan kolom nama.
                  </p>
                  <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                    Format yang didukung: .xlsx, .xls, .csv
                  </p>
                  <input
                    id="email-blast-external-upload"
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    className="hidden"
                    onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                  />
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <label
                      htmlFor="email-blast-external-upload"
                      className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                      <Upload className="h-4 w-4" />
                      Pilih File
                    </label>
                    {uploadFile ? (
                      <span className="min-w-0 truncate text-sm text-gray-600 dark:text-gray-300">
                        {uploadFile.name}
                      </span>
                    ) : (
                      <span className="text-sm text-gray-400">Belum ada file dipilih</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {sheetRows.length > 0 && (
              <div className="mt-4 space-y-4">
                <div className="grid gap-3 md:grid-cols-3">
                  <div>
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                      Header Row
                    </label>
                    <select
                      value={headerRowIndex}
                      onChange={(e) => setHeaderRowIndex(Number(e.target.value))}
                      className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                    >
                      {headerRowOptions.map((row, idx) => (
                        <option key={idx} value={idx}>
                          Row {idx + 1}: {row.map((cell) => normalizeSpreadsheetCell(cell)).filter(Boolean).slice(0, 3).join(' | ') || '(empty)'}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                      Kolom Email
                    </label>
                    <select
                      value={emailColumnIndex}
                      onChange={(e) => setEmailColumnIndex(Number(e.target.value))}
                      className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                    >
                      <option value={-1}>Pilih kolom email</option>
                      {uploadPreviewHeaders.map((header, idx) => (
                        <option key={idx} value={idx}>
                          {normalizeSpreadsheetCell(header) || `Column ${idx + 1}`}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                      Kolom Nama
                    </label>
                    <select
                      value={nameColumnIndex}
                      onChange={(e) => setNameColumnIndex(Number(e.target.value))}
                      className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                    >
                      <option value={-1}>Tanpa kolom nama</option>
                      {uploadPreviewHeaders.map((header, idx) => (
                        <option key={idx} value={idx}>
                          {normalizeSpreadsheetCell(header) || `Column ${idx + 1}`}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                  {emailColumnIndex >= 0 ? (
                    <span>
                      Sistem akan import mulai dari row {headerRowIndex + 2}. Jika nama kosong, sistem pakai email sebagai label recipient.
                    </span>
                  ) : (
                    <span className="text-amber-600 dark:text-amber-400">
                      Sistem belum bisa menentukan kolom email. Pilih manual di dropdown Kolom Email.
                    </span>
                  )}
                </div>

                <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-gray-700">
                  <div className="border-b border-gray-200 bg-gray-50 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
                    Preview Data
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-white dark:bg-gray-900">
                        <tr>
                          {uploadPreviewHeaders.map((header, idx) => (
                            <th key={idx} className="border-b border-gray-200 px-3 py-2 text-left text-xs font-semibold text-gray-500 dark:border-gray-700 dark:text-gray-400">
                              {normalizeSpreadsheetCell(header) || `Column ${idx + 1}`}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="bg-white dark:bg-gray-900">
                        {uploadPreviewRows.length === 0 ? (
                          <tr>
                            <td colSpan={Math.max(uploadPreviewHeaders.length, 1)} className="px-3 py-4 text-sm text-gray-400">
                              Tidak ada data setelah header row yang dipilih.
                            </td>
                          </tr>
                        ) : (
                          uploadPreviewRows.map((row, rowIndex) => (
                            <tr key={rowIndex}>
                              {uploadPreviewHeaders.map((_, colIndex) => (
                                <td key={colIndex} className="border-t border-gray-100 px-3 py-2 text-sm text-gray-700 dark:border-gray-800 dark:text-gray-200">
                                  {normalizeSpreadsheetCell((row as unknown[])[colIndex]) || '—'}
                                </td>
                              ))}
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            <div className="mt-auto flex items-center justify-end gap-2 pt-4 border-t border-gray-100 dark:border-gray-800">
              <button
                onClick={handleClose}
                className="px-4 py-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
              >
                Cancel
              </button>
              <button
                onClick={handleUploadExternalRecipients}
                disabled={!uploadFile || uploadExternalMutation.isPending || emailColumnIndex < 0}
                className={cn(
                  'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                  !uploadFile || uploadExternalMutation.isPending || emailColumnIndex < 0
                    ? 'bg-gray-100 text-gray-400 dark:bg-gray-700 cursor-not-allowed'
                    : 'bg-indigo-600 text-white hover:bg-indigo-700'
                )}
              >
                {uploadExternalMutation.isPending ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4" />
                    Import Recipient
                  </>
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}

// ─── Sent Tab ─────────────────────────────────────────────────────────────────

function SentTab({ campaignId, campaign }: { campaignId: number; campaign: EmailBlastCampaign }) {
  const [statusFilter, setStatusFilter] = useState<string>('')
  const { data, isLoading, refetch } = useSentEmails(campaignId, statusFilter || undefined)

  const emails = data?.emails ?? []
  const sentCount = emails.filter((e) => e.status === 'sent').length
  const failedCount = emails.filter((e) => e.status === 'failed').length
  const pendingCount = emails.filter((e) => e.status === 'pending').length
  const creatorName = campaign.created_by_name || campaign.created_by_email || 'Unknown'
  const operatorName = campaign.started_by_name || campaign.started_by_email

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {campaign.status === 'running' && (
        <div className="flex items-center gap-3 border-b border-gray-200 bg-blue-50 px-4 py-2 dark:bg-blue-950/30">
          {sentCount > 0 && <span className="flex items-center gap-1 text-xs text-blue-700 dark:text-blue-300"><CheckCircle2 className="h-3 w-3" /> {sentCount} sent</span>}
          {pendingCount > 0 && <span className="flex items-center gap-1 text-xs text-amber-600"><Clock className="h-3 w-3" /> {pendingCount} pending</span>}
          {failedCount > 0 && <span className="flex items-center gap-1 text-xs text-red-600"><XCircle className="h-3 w-3" /> {failedCount} failed</span>}
        </div>
      )}

      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
        <div className="relative">
          <div className="flex rounded-lg border border-gray-200 dark:border-gray-700">
            {['', 'sent', 'failed', 'pending'].map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={cn(
                  'px-2.5 py-1 text-[11px] font-medium transition-colors first:rounded-l-lg last:rounded-r-lg',
                  statusFilter === s
                    ? 'bg-gray-900 text-white dark:bg-indigo-600 dark:text-white'
                    : 'text-gray-500 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800',
                )}
              >
                {s === '' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <span className="ml-auto text-xs text-gray-400">{emails.length} emails</span>
      </div>

      <div className="border-b border-gray-100 bg-gray-50/80 px-4 py-2.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900/40 dark:text-gray-400">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span>Dibuat oleh {creatorName}</span>
          {operatorName ? <span>Terakhir dijalankan oleh {operatorName}</span> : null}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex h-48 items-center justify-center"><Spinner /></div>
        ) : emails.length === 0 ? (
          <EmptyState icon={Send} title="No sent emails yet" description="Sent emails will appear here." />
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-800/80">
            {emails.map((email) => (
              <div key={email.id} className="flex items-center gap-3 px-4 py-3">
                {email.status === 'sent' && <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />}
                {email.status === 'failed' && <XCircle className="h-4 w-4 shrink-0 text-red-500" />}
                {email.status === 'pending' && <Clock className="h-4 w-4 shrink-0 text-gray-400" />}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-gray-900 dark:text-gray-100">{email.university_name || email.email}</p>
                  <p className="truncate text-[11px] text-gray-400">{email.subject}</p>
                  {email.from_email ? <p className="mt-0.5 truncate text-[11px] text-gray-400">Dari {email.from_name || email.from_email}</p> : null}
                  {operatorName && (
                    <p className="mt-0.5 truncate text-[11px] text-gray-400">Dijalankan oleh {operatorName}</p>
                  )}
                </div>
                {email.error_message && <span className="max-w-[150px] truncate text-[10px] text-red-500">{email.error_message}</span>}
                <span className="shrink-0 text-[11px] text-gray-400">{email.sent_at ? formatRelative(email.sent_at) : '—'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Inbox Tab ────────────────────────────────────────────────────────────────

function CampaignInboxTab({ campaignId }: { campaignId: number }) {
  const { data, isLoading, refetch, isFetching } = useInboxEmails(campaignId, 100)
  const emails = data?.emails ?? []

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
        <span className="text-sm text-gray-500">{emails.length} replies</span>
        <button onClick={() => refetch()} className="ml-auto flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800">
          <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex h-48 items-center justify-center"><Spinner /></div>
        ) : emails.length === 0 ? (
          <EmptyState icon={Inbox} title="No replies yet" description="Inbound replies will appear here." />
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-800/80">
            {emails.map((email) => (
              <div key={email.id} className="flex items-start gap-3 px-4 py-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900">
                  <Inbox className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-gray-900 dark:text-gray-100">{email.from_name || email.from_email}</p>
                  <p className="text-[11px] text-gray-500 dark:text-gray-400">{email.from_email}</p>
                  {email.mailbox_email ? <p className="text-[11px] text-gray-400 dark:text-gray-500">Mailbox: {email.mailbox_email}</p> : null}
                  <p className="mt-1 truncate text-[12px] text-gray-600 dark:text-gray-300">{email.subject || '(no subject)'}</p>
                  <p className="mt-0.5 line-clamp-2 text-[12px] text-gray-400 dark:text-gray-500">{email.body?.replace(/<[^>]+>/g, '').slice(0, 120)}</p>
                </div>
                <span className="shrink-0 text-[10px] text-gray-400">{formatRelative(email.date)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main CampaignDetail ──────────────────────────────────────────────────────

export function EmailCampaignDetail({ campaignId, canManage, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<'content' | 'recipients' | 'sent' | 'inbox'>('content')
  const [showStartModal, setShowStartModal] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [hasPendingSaves, setHasPendingSaves] = useState(false)

  const { data, isLoading, refetch } = useEmailBlastCampaign(campaignId ?? 0)
  const { data: attachment, refetch: refetchAttachment } = useCampaignAttachment(campaignId ?? 0)
  const updateMutation = useUpdateEmailCampaign()
  const startMutation = useStartEmailCampaign()
  const pauseMutation = usePauseEmailCampaign()
  const cancelMutation = useCancelEmailCampaign()

  const campaign = data?.campaign

  const handleSave = useCallback(
    async (saveData: { name: string; subject: string; template_message: string; delay_between_ms: number }) => {
      if (!campaignId) return
      setIsSaving(true)
      try {
        await updateMutation.mutateAsync({ id: campaignId, data: saveData })
        toast.success('Campaign saved')
      } catch {
        toast.error('Failed to save')
      } finally {
        setIsSaving(false)
      }
    },
    [campaignId, updateMutation],
  )

  const handleStart = async () => {
    if (!campaignId) return
    try {
      await startMutation.mutateAsync({ campaign_id: campaignId })
      toast.success('Campaign started')
      setShowStartModal(false)
      refetch()
    } catch {
      toast.error('Failed to start campaign')
    }
  }

  const handlePause = async () => {
    if (!campaignId) return
    await pauseMutation.mutateAsync(campaignId)
    toast.success('Campaign paused')
    refetch()
  }

  const handleCancel = async () => {
    if (!campaignId) return
    if (!confirm('Are you sure? This cannot be undone.')) return
    await cancelMutation.mutateAsync(campaignId)
    toast.success('Campaign cancelled')
    refetch()
  }

  const handleRetryFailed = async () => {
    if (!campaignId) return
    try {
      const res = await fetch(`/api/email-blast/campaigns/${campaignId}/retry-failed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const data = await res.json()
      if (data.success) {
        toast.success(data.message)
        refetch()
      } else {
        toast.error(data.message || 'Failed to retry')
      }
    } catch {
      toast.error('Failed to retry failed emails')
    }
  }

  if (!campaignId) {
    return <CreateCampaignView canManage={canManage} onClose={onClose} />
  }

  if (isLoading) {
    return <div className="flex h-full items-center justify-center"><Spinner /></div>
  }

  if (!campaign) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState icon={FileText} title="Campaign not found" description="This campaign may have been deleted." action={<Button onClick={onClose}>Go Back</Button>} />
      </div>
    )
  }

  const cfg = statusConfig[campaign.status] ?? statusConfig.draft
  const isReadOnly = campaign.status === 'running' || campaign.status === 'completed' || campaign.status === 'cancelled'
  const failedCount = campaign.failed_count

  const tabs = [
    { key: 'content', label: 'Content', icon: FileText },
    { key: 'recipients', label: `Recipients (${campaign.total_recipients})`, icon: Users },
    { key: 'sent', label: 'Sent', icon: Send },
    { key: 'inbox', label: 'Replies', icon: Inbox },
  ]

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
        <button onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800">
          <ArrowLeft className="h-4 w-4" />
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-gray-900 dark:text-white">{campaign.name || 'Untitled'}</span>
            <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium', cfg.bg)}>{cfg.label}</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-gray-400">
            <span>Dibuat oleh {campaign.created_by_name || campaign.created_by_email || 'Unknown'}</span>
            {campaign.started_by_name || campaign.started_by_email ? (
              <span>Terakhir dijalankan oleh {campaign.started_by_name || campaign.started_by_email}</span>
            ) : null}
          </div>
          {campaign.status === 'running' && (
            <div className="mt-1 flex items-center gap-2">
              <div className="h-1.5 w-48 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
                <div className="h-full bg-green-400 transition-all duration-500" style={{ width: `${campaign.total_recipients > 0 ? ((campaign.sent_count + campaign.failed_count + (campaign.invalid_count ?? 0)) / campaign.total_recipients) * 100 : 0}%` }} />
              </div>
              <span className="text-[10px] text-gray-400">{campaign.sent_count}/{campaign.total_recipients}</span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-2">
          {/* Retry Failed — show when completed/running with failures */}
          {canManage && (campaign.status === 'completed' || campaign.status === 'running') && failedCount > 0 && (
            <Button size="sm" variant="secondary" onClick={handleRetryFailed} className="text-amber-600 hover:text-amber-700">
              <RotateCcw className="h-3.5 w-3.5" />
              Retry Failed ({failedCount})
            </Button>
          )}

          {canManage && campaign.status === 'draft' && (
            <>
              <Button size="sm" variant={hasPendingSaves || isSaving ? 'secondary' : 'success'} disabled={hasPendingSaves || isSaving} onClick={() => setShowStartModal(true)}>
                <Rocket className="h-3.5 w-3.5" />
                Start
              </Button>
              <Button size="sm" variant="danger" onClick={handleCancel}>
                <XCircle className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
          {canManage && campaign.status === 'running' && (
            <>
              <Button size="sm" variant="secondary" onClick={handlePause} loading={pauseMutation.isPending}>
                <Pause className="h-3.5 w-3.5" />
                Pause
              </Button>
              <Button size="sm" variant="secondary" onClick={handleCancel} loading={cancelMutation.isPending}>
                <XCircle className="h-3.5 w-3.5" />
                Stop
              </Button>
            </>
          )}
          {canManage && campaign.status === 'paused' && (
            <>
              <Button
                size="sm"
                variant="primary"
                onClick={handleStart}
                loading={startMutation.isPending}
              >
                <Play className="h-3.5 w-3.5" />
                Continue
              </Button>
              <Button size="sm" variant="secondary" onClick={handleCancel} loading={cancelMutation.isPending}>
                <XCircle className="h-3.5 w-3.5" />
                Cancel
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 border-b border-gray-200 bg-white px-4 pt-2 dark:border-gray-800 dark:bg-[#111827]">
        {tabs.map((tab) => {
          const TabIcon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as typeof activeTab)}
              className={cn(
                'flex items-center gap-1.5 rounded-t-lg border-b-2 px-4 py-2 text-[13px] font-medium transition-colors',
                activeTab === tab.key
                  ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200',
              )}
            >
              <TabIcon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'content' && (
          <ContentTab
            campaign={campaign}
            attachment={attachment}
            campaignId={campaignId}
            canManage={canManage}
            onSave={handleSave}
            isSaving={isSaving}
            onPendingSavesChange={setHasPendingSaves}
          />
        )}
        {activeTab === 'recipients' && <RecipientsTab campaignId={campaignId} campaign={campaign} canManage={canManage} />}
        {activeTab === 'sent' && <SentTab campaignId={campaignId} campaign={campaign} />}
        {activeTab === 'inbox' && <CampaignInboxTab campaignId={campaignId} />}
      </div>

      {/* Start Modal */}
      <Modal isOpen={showStartModal} onClose={() => setShowStartModal(false)} title="Start Campaign" size="sm">
        <div className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            Start sending <strong>{campaign.name}</strong> to <strong>{campaign.total_recipients}</strong> recipients?
          </p>
          {campaign.total_recipients === 0 && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900 dark:bg-amber-950">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              <p className="text-xs text-amber-700 dark:text-amber-300">Add recipients first before starting.</p>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowStartModal(false)}>Cancel</Button>
            <Button variant={campaign.total_recipients === 0 ? 'secondary' : 'success'} onClick={handleStart} loading={startMutation.isPending} disabled={campaign.total_recipients === 0}>
              <Rocket className="h-4 w-4" />
              Start Sending
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ─── Create Campaign View ────────────────────────────────────────────────────

function CreateCampaignView({ canManage, onClose }: { canManage: boolean; onClose: () => void }) {
  const [name, setName] = useState('')
  const createMutation = useCreateEmailCampaign()

  async function handleCreate() {
    if (!canManage) return
    if (!name.trim()) return
    try {
      await createMutation.mutateAsync({ name: name.trim(), subject: '', template_message: '', delay_between_ms: 20_000 })
      toast.success('Campaign created')
      onClose()
    } catch {
      toast.error('Failed to create')
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
        <button onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="text-sm font-semibold text-gray-900 dark:text-white">New Campaign</span>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        <div className="max-w-lg space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-gray-500 uppercase tracking-wider">Campaign Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Undangan Audiensi Q2 2025"
              autoFocus
              disabled={!canManage}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
          </div>
          <p className="text-xs text-gray-400">
            Subject dan body bisa di-set setelah upload DOCX template di tab Content.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-5 py-3 dark:border-gray-800">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button onClick={handleCreate} loading={createMutation.isPending} disabled={!canManage || !name.trim()}>
          <Rocket className="h-4 w-4" />
          Create
        </Button>
      </div>
    </div>
  )
}
