/**
 * BlastCampaignDetailPage — Edit campaign template, manage recipients, configure
 * sending settings, preview messages, and start/pause/cancel the blast.
 */

import { useState, useRef, useCallback, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Megaphone,
  Save,
  Play,
  Pause,
  XCircle,
  Trash2,
  Plus,
  Search,
  Users,
  Eye,
  Settings2,
  MessageSquareText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Send,
  Clock,
  Phone,
  User,
  GraduationCap,
  X,
  ChevronDown,
  ChevronUp,
  Smartphone,
  Timer,
  Zap,
} from 'lucide-react'
import { cn } from '../lib/utils'
import {
  useBlastCampaign,
  useUpdateCampaign,
  useBlastRecipients,
  useAddRecipients,
  useRemoveRecipient,
  useClearRecipients,
  useBlastPreview,
  useBlastContacts,
  useStartCampaign,
  usePauseCampaign,
  useCancelCampaign,
  useDeleteCampaign,
} from '../hooks/useBlast'
import { useWhatsAppDevices } from '../hooks/useWhatsApp'
import type { BlastContact, BlastContactsParams, PreviouslyBlastedContact } from '../api/blast'
import { checkPreviouslyBlasted } from '../api/blast'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const recipientStatusStyle: Record<string, { color: string; bg: string; icon: React.ElementType }> = {
  pending: { color: 'text-gray-500', bg: 'bg-gray-100 dark:bg-gray-700', icon: Clock },
  sent: { color: 'text-green-600', bg: 'bg-green-50 dark:bg-green-900/30', icon: CheckCircle2 },
  failed: { color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-900/30', icon: AlertCircle },
  skipped: { color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-900/30', icon: XCircle },
}

function RecipientStatusBadge({ status }: { status: string }) {
  const cfg = recipientStatusStyle[status] || recipientStatusStyle.pending
  const Icon = cfg.icon
  return (
    <span className={cn('inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-medium', cfg.bg, cfg.color)}>
      <Icon className="w-3 h-3" />
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Contact Selector Modal
// ---------------------------------------------------------------------------

const PAGE_SIZE = 100

function ContactSelectorModal({
  campaignId,
  onClose,
}: {
  campaignId: number
  onClose: () => void
}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [filters, setFilters] = useState<BlastContactsParams>({ limit: PAGE_SIZE })
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [page, setPage] = useState(0)
  const [checking, setChecking] = useState(false)
  const [duplicates, setDuplicates] = useState<PreviouslyBlastedContact[] | null>(null)
  const [excludedIds, setExcludedIds] = useState<Set<number>>(new Set())

  const debouncedSearch = useMemo(() => {
    return searchQuery.trim() || undefined
  }, [searchQuery])

  const queryParams = useMemo<BlastContactsParams>(
    () => ({ ...filters, search: debouncedSearch, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [filters, debouncedSearch, page]
  )

  const { data, isLoading } = useBlastContacts(queryParams, true)
  const addMutation = useAddRecipients()
  const contacts = data?.data || []
  const totalContacts = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(totalContacts / PAGE_SIZE))

  const toggleContact = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    const pageIds = contacts.map((c) => c.contact_id)
    const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id))
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (allPageSelected) {
        pageIds.forEach((id) => next.delete(id))
      } else {
        pageIds.forEach((id) => next.add(id))
      }
      return next
    })
  }

  const handleAdd = async () => {
    if (selectedIds.size === 0) return
    setChecking(true)
    try {
      const result = await checkPreviouslyBlasted({ contact_ids: Array.from(selectedIds) })
      if (result.previously_blasted.length > 0) {
        setDuplicates(result.previously_blasted)
        setExcludedIds(new Set())  // default: include all, user can exclude
      } else {
        // No duplicates — add directly
        addMutation.mutate(
          { campaignId, contact_ids: Array.from(selectedIds) },
          { onSuccess: () => onClose() }
        )
      }
    } catch {
      // If check fails, proceed anyway
      addMutation.mutate(
        { campaignId, contact_ids: Array.from(selectedIds) },
        { onSuccess: () => onClose() }
      )
    } finally {
      setChecking(false)
    }
  }

  const handleConfirmAdd = () => {
    const finalIds = Array.from(selectedIds).filter((id) => !excludedIds.has(id))
    if (finalIds.length === 0) {
      setDuplicates(null)
      return
    }
    addMutation.mutate(
      { campaignId, contact_ids: finalIds },
      { onSuccess: () => { setDuplicates(null); onClose() } }
    )
  }

  const toggleExclude = (id: number) => {
    setExcludedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-indigo-500" />
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Select Contacts</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Filters */}
        <div className="p-4 border-b border-gray-100 dark:border-gray-700 space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setPage(0) }}
              placeholder="Search university or contact name..."
              className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm dark:bg-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <FilterChip
              label="Has Name"
              active={filters.has_name === true}
              onClick={() => { setFilters((f) => ({ ...f, has_name: f.has_name ? undefined : true })); setPage(0) }}
            />
            <FilterChip
              label="Not Contacted"
              active={filters.contacted === false}
              onClick={() => { setFilters((f) => ({ ...f, contacted: f.contacted === false ? undefined : false })); setPage(0) }}
            />
            <FilterChip
              label="Contacted"
              active={filters.contacted === true}
              onClick={() => { setFilters((f) => ({ ...f, contacted: f.contacted ? undefined : true })); setPage(0) }}
            />
            <FilterChip
              label="Has Conversation"
              active={filters.has_conversation === true}
              onClick={() => {
                setFilters((f) => ({
                  ...f,
                  has_conversation: f.has_conversation ? undefined : true,
                }))
                setPage(0)
              }}
            />
          </div>
        </div>

        {/* Contact List */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          ) : contacts.length === 0 ? (
            <div className="text-center py-12 text-gray-400 text-sm">No contacts found</div>
          ) : (
            <div>
              {/* Select all row */}
              <div
                className="sticky top-0 z-10 flex items-center gap-3 px-4 py-2 bg-gray-50 dark:bg-gray-750 border-b border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-500 dark:text-gray-400 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700"
                onClick={toggleAll}
              >
                <input
                  type="checkbox"
                  checked={contacts.length > 0 && contacts.every(c => selectedIds.has(c.contact_id))}
                  readOnly
                  className="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span>
                  {contacts.length > 0 && contacts.every(c => selectedIds.has(c.contact_id))
                    ? `Deselect page (${contacts.length})`
                    : `Select page (${contacts.length})`}
                  {selectedIds.size > 0 && ` · ${selectedIds.size} total selected`}
                </span>
              </div>
              {contacts.map((c) => (
                <div
                  key={c.contact_id}
                  onClick={() => toggleContact(c.contact_id)}
                  className={cn(
                    'flex items-center gap-3 px-4 py-2.5 border-b border-gray-100 dark:border-gray-700/50 cursor-pointer transition-colors',
                    selectedIds.has(c.contact_id)
                      ? 'bg-indigo-50 dark:bg-indigo-900/20'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(c.contact_id)}
                    readOnly
                    className="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                        {c.contact_name || c.phone_number}
                      </span>
                      {c.has_person_name ? (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400">
                          Named
                        </span>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
                      <span className="flex items-center gap-1">
                        <Phone className="w-3 h-3" />
                        {c.phone_number}
                      </span>
                      <span className="flex items-center gap-1 truncate">
                        <GraduationCap className="w-3 h-3" />
                        {c.university_name || 'Unknown'}
                      </span>
                      {c.province && <span>{c.province}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalContacts > PAGE_SIZE && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 text-xs">
            <span className="text-gray-500 dark:text-gray-400">
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalContacts)} of {totalContacts}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-2.5 py-1 rounded-md text-xs font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Prev
              </button>
              {/* Page number buttons */}
              {(() => {
                const pages: number[] = []
                const maxVisible = 5
                let start = Math.max(0, page - Math.floor(maxVisible / 2))
                const end = Math.min(totalPages, start + maxVisible)
                if (end - start < maxVisible) start = Math.max(0, end - maxVisible)
                for (let i = start; i < end; i++) pages.push(i)
                return pages.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={cn(
                      'w-7 h-7 rounded-md text-xs font-medium transition-colors',
                      p === page
                        ? 'bg-indigo-600 text-white'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                    )}
                  >
                    {p + 1}
                  </button>
                ))
              })()}
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-2.5 py-1 rounded-md text-xs font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {selectedIds.size} selected{data?.total ? ` of ${data.total}` : ''}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={selectedIds.size === 0 || addMutation.isPending || checking}
              className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg disabled:opacity-50 transition-colors"
            >
              {(addMutation.isPending || checking) ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              {checking ? 'Checking...' : `Add ${selectedIds.size} Contacts`}
            </button>
          </div>
        </div>

        {/* Duplicate Confirmation Overlay */}
        {duplicates && duplicates.length > 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/30 backdrop-blur-[2px] rounded-2xl">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[70vh] flex flex-col border border-amber-200 dark:border-amber-700">
              {/* Confirmation Header */}
              <div className="flex items-center gap-3 p-4 border-b border-amber-100 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 rounded-t-xl">
                <div className="p-2 rounded-full bg-amber-100 dark:bg-amber-900/40">
                  <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {duplicates.length} contact{duplicates.length > 1 ? 's' : ''} previously blasted
                  </h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    These contacts have been sent messages in previous campaigns. Uncheck to exclude them.
                  </p>
                </div>
              </div>

              {/* Duplicate List */}
              <div className="flex-1 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700">
                {duplicates.map((d) => (
                  <label
                    key={d.contact_id}
                    className={cn(
                      'flex items-start gap-3 px-4 py-3 cursor-pointer transition-colors',
                      excludedIds.has(d.contact_id)
                        ? 'bg-gray-50 dark:bg-gray-800/50 opacity-60'
                        : 'hover:bg-amber-50/50 dark:hover:bg-amber-900/10'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={!excludedIds.has(d.contact_id)}
                      onChange={() => toggleExclude(d.contact_id)}
                      className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                        {d.contact_name || d.phone_number}
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                        <span className="flex items-center gap-1">
                          <Phone className="w-3 h-3" /> {d.phone_number}
                        </span>
                        {d.university_name && (
                          <span className="flex items-center gap-1">
                            <GraduationCap className="w-3 h-3" /> {d.university_name}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-[10px] text-amber-600 dark:text-amber-400">
                        Blasted in "{d.campaign_name}"{d.sent_at ? ` on ${new Date(d.sent_at).toLocaleDateString()}` : ''}
                      </div>
                    </div>
                  </label>
                ))}
              </div>

              {/* Confirmation Footer */}
              <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 rounded-b-xl">
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {excludedIds.size > 0 && (
                    <span className="text-amber-600 dark:text-amber-400 font-medium">
                      {excludedIds.size} excluded ·{' '}
                    </span>
                  )}
                  {selectedIds.size - excludedIds.size} will be added
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setDuplicates(null)}
                    className="px-3 py-1.5 text-xs text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleConfirmAdd}
                    disabled={selectedIds.size - excludedIds.size === 0 || addMutation.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg disabled:opacity-50 transition-colors"
                  >
                    {addMutation.isPending ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    )}
                    Confirm Add {selectedIds.size - excludedIds.size} Contacts
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-2.5 py-1 rounded-full text-xs font-medium transition-colors border',
        active
          ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 border-indigo-300 dark:border-indigo-700'
          : 'bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
      )}
    >
      {label}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Template Placeholder Buttons
// ---------------------------------------------------------------------------

const PLACEHOLDERS = [
  { key: '{nama_universitas}', label: 'University', icon: GraduationCap },
  { key: '{nama_kontak}', label: 'Contact', icon: User },
  { key: '{nomor_telepon}', label: 'Phone', icon: Phone },
]

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function BlastCampaignDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const campaignId = Number(id)

  // Campaign data
  const { data: campaign, isLoading: loadingCampaign } = useBlastCampaign(campaignId, !!id)
  const isDraft = campaign?.status === 'draft'
  const isSending = campaign?.status === 'sending'
  const isPaused = campaign?.status === 'paused'
  const isFinished = campaign?.status === 'completed' || campaign?.status === 'cancelled'

  // Recipients
  const [recipientPage, setRecipientPage] = useState(0)
  const RECIPIENTS_PER_PAGE = 50
  const { data: recipientsData, isLoading: loadingRecipients } = useBlastRecipients(
    campaignId,
    { limit: RECIPIENTS_PER_PAGE, offset: recipientPage * RECIPIENTS_PER_PAGE },
    !!id
  )
  const recipients = recipientsData?.data || []
  const totalRecipients = recipientsData?.total || 0

  // Preview
  const { data: previewData } = useBlastPreview(campaignId, !!id && !!campaign?.template_message)

  // Devices
  const { data: devicesData } = useWhatsAppDevices()
  const connectedDevices = (devicesData?.devices || []).filter(
    (d) => d.connectionState === 'connected'
  )

  // Mutations
  const updateMutation = useUpdateCampaign()
  const addMutation = useAddRecipients()
  const removeMutation = useRemoveRecipient()
  const clearMutation = useClearRecipients()
  const startMutation = useStartCampaign()
  const pauseMutation = usePauseCampaign()
  const cancelMutation = useCancelCampaign()
  const deleteMutation = useDeleteCampaign()

  // Local form state
  const [templateDraft, setTemplateDraft] = useState<string | null>(null)
  const [deviceDraft, setDeviceDraft] = useState<string | null>(null)
  const [delayDraft, setDelayDraft] = useState<number | null>(null)
  const [humanMinDraft, setHumanMinDraft] = useState<number | null>(null)
  const [humanMaxDraft, setHumanMaxDraft] = useState<number | null>(null)
  const templateRef = useRef<HTMLTextAreaElement>(null)

  // Derived values (draft state overrides server value)
  const currentTemplate = templateDraft ?? campaign?.template_message ?? ''
  const currentDevice = deviceDraft ?? campaign?.device_id ?? 'device_1'
  const currentDelay = delayDraft ?? campaign?.delay_between_ms ?? 5000
  const currentHumanMin = humanMinDraft ?? campaign?.human_delay_min_ms ?? 2000
  const currentHumanMax = humanMaxDraft ?? campaign?.human_delay_max_ms ?? 8000

  // Contact selector modal
  const [showContactModal, setShowContactModal] = useState(false)

  // Sections toggle
  const [showSettings, setShowSettings] = useState(false)
  const [showPreview, setShowPreview] = useState(false)

  // Check if there are unsaved changes
  const hasUnsavedChanges =
    (templateDraft !== null && templateDraft !== campaign?.template_message) ||
    (deviceDraft !== null && deviceDraft !== campaign?.device_id) ||
    (delayDraft !== null && delayDraft !== campaign?.delay_between_ms) ||
    (humanMinDraft !== null && humanMinDraft !== campaign?.human_delay_min_ms) ||
    (humanMaxDraft !== null && humanMaxDraft !== campaign?.human_delay_max_ms)

  // Insert placeholder at cursor
  const insertPlaceholder = useCallback(
    (placeholder: string) => {
      const ta = templateRef.current
      if (!ta) {
        setTemplateDraft((prev) => (prev ?? campaign?.template_message ?? '') + placeholder)
        return
      }
      const start = ta.selectionStart
      const end = ta.selectionEnd
      const text = currentTemplate
      const newText = text.substring(0, start) + placeholder + text.substring(end)
      setTemplateDraft(newText)
      // restore cursor after state update
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + placeholder.length
        ta.focus()
      })
    },
    [currentTemplate, campaign?.template_message]
  )

  // Save handler
  const handleSave = () => {
    const payload: Record<string, unknown> = { id: campaignId }
    if (templateDraft !== null) payload.template_message = templateDraft
    if (deviceDraft !== null) payload.device_id = deviceDraft
    if (delayDraft !== null) payload.delay_between_ms = delayDraft
    if (humanMinDraft !== null) payload.human_delay_min_ms = humanMinDraft
    if (humanMaxDraft !== null) payload.human_delay_max_ms = humanMaxDraft
    updateMutation.mutate(payload as any, {
      onSuccess: () => {
        setTemplateDraft(null)
        setDeviceDraft(null)
        setDelayDraft(null)
        setHumanMinDraft(null)
        setHumanMaxDraft(null)
      },
    })
  }

  // Delete handler
  const handleDelete = () => {
    if (!confirm('Delete this campaign and all its recipients?')) return
    deleteMutation.mutate(campaignId, {
      onSuccess: () => navigate('/blast'),
    })
  }

  // Loading
  if (loadingCampaign) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    )
  }

  if (!campaign) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="w-8 h-8 text-gray-300" />
        <p className="text-gray-500 text-sm">Campaign not found</p>
        <Link to="/blast" className="text-indigo-600 text-sm hover:underline">Back to campaigns</Link>
      </div>
    )
  }

  const progress = campaign.total_recipients > 0
    ? Math.round(((campaign.sent_count + campaign.failed_count) / campaign.total_recipients) * 100)
    : 0

  return (
    <div className="max-w-4xl mx-auto py-6 px-4 space-y-5">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            to="/blast"
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow">
            <Megaphone className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100">{campaign.name}</h1>
            <div className="flex items-center gap-2 mt-0.5">
              <CampaignStatusBadge status={campaign.status} />
              {campaign.total_recipients > 0 && (
                <span className="text-[11px] text-gray-400">
                  {campaign.sent_count}/{campaign.total_recipients} sent
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {hasUnsavedChanges && isDraft && (
            <button
              onClick={handleSave}
              disabled={updateMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
            >
              {updateMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              Save
            </button>
          )}
          {isDraft && campaign.total_recipients > 0 && currentTemplate.trim() && (
            <button
              onClick={() => {
                // Save first if needed, then start
                if (hasUnsavedChanges) {
                  const payload: Record<string, unknown> = { id: campaignId }
                  if (templateDraft !== null) payload.template_message = templateDraft
                  if (deviceDraft !== null) payload.device_id = deviceDraft
                  if (delayDraft !== null) payload.delay_between_ms = delayDraft
                  if (humanMinDraft !== null) payload.human_delay_min_ms = humanMinDraft
                  if (humanMaxDraft !== null) payload.human_delay_max_ms = humanMaxDraft
                  updateMutation.mutate(payload as any, {
                    onSuccess: () => startMutation.mutate(campaignId),
                  })
                } else {
                  startMutation.mutate(campaignId)
                }
              }}
              disabled={startMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
            >
              {startMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              Start Blast
            </button>
          )}
          {isPaused && (
            <button
              onClick={() => startMutation.mutate(campaignId)}
              disabled={startMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
            >
              {startMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              Resume
            </button>
          )}
          {isSending && (
            <button
              onClick={() => pauseMutation.mutate(campaignId)}
              disabled={pauseMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
            >
              {pauseMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Pause className="w-3.5 h-3.5" />}
              Pause
            </button>
          )}
          {(isSending || isPaused) && (
            <button
              onClick={() => cancelMutation.mutate(campaignId)}
              disabled={cancelMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
            >
              <XCircle className="w-3.5 h-3.5" />
              Cancel
            </button>
          )}
          {(isDraft || isFinished) && (
            <button
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
              title="Delete campaign"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Progress bar for active campaigns */}
      {(isSending || isPaused) && campaign.total_recipients > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {isSending ? (
                <span className="flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                  Sending in progress...
                </span>
              ) : (
                'Paused'
              )}
            </span>
            <span className="text-gray-500 dark:text-gray-400 text-xs">
              {campaign.sent_count} sent · {campaign.failed_count} failed · {campaign.total_recipients - campaign.sent_count - campaign.failed_count} remaining
            </span>
          </div>
          <div className="h-2.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
            {campaign.sent_count > 0 && (
              <div
                className="bg-green-500 h-full transition-all duration-500"
                style={{ width: `${(campaign.sent_count / campaign.total_recipients) * 100}%` }}
              />
            )}
            {campaign.failed_count > 0 && (
              <div
                className="bg-red-400 h-full transition-all duration-500"
                style={{ width: `${(campaign.failed_count / campaign.total_recipients) * 100}%` }}
              />
            )}
          </div>
          <div className="text-right text-xs text-gray-400 mt-1">{progress}%</div>
        </div>
      )}

      {/* Completed/Cancelled summary */}
      {isFinished && campaign.total_recipients > 0 && (
        <div className={cn(
          'flex items-center gap-3 p-4 rounded-xl border shadow-sm',
          campaign.status === 'completed'
            ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
            : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
        )}>
          {campaign.status === 'completed' ? (
            <CheckCircle2 className="w-5 h-5 text-green-500" />
          ) : (
            <XCircle className="w-5 h-5 text-gray-400" />
          )}
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
              {campaign.status === 'completed' ? 'Campaign completed' : 'Campaign cancelled'}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {campaign.sent_count} sent · {campaign.failed_count} failed · {campaign.total_recipients - campaign.sent_count - campaign.failed_count} skipped
            </p>
          </div>
        </div>
      )}

      {/* Failed recipients detail — shown after campaign completes with failures */}
      {isFinished && campaign.failed_count > 0 && (
        <details className="rounded-xl border border-red-200 dark:border-red-800/50 shadow-sm bg-red-50/50 dark:bg-red-900/10 overflow-hidden">
          <summary className="flex items-center gap-2 px-4 py-3 cursor-pointer select-none hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
            <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
            <span className="text-sm font-medium text-red-700 dark:text-red-400">
              {campaign.failed_count} failed deliveries
            </span>
            <span className="text-[11px] text-red-400 dark:text-red-500 ml-auto">click to expand</span>
          </summary>
          <div className="border-t border-red-200 dark:border-red-800/50 divide-y divide-red-100 dark:divide-red-900/30 max-h-[300px] overflow-y-auto">
            {recipients
              .filter((r) => r.status === 'failed')
              .map((r) => (
                <div key={r.id} className="flex items-start gap-3 px-4 py-2.5 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-900 dark:text-gray-100 truncate">
                      {r.contact_name || r.phone_number}
                    </p>
                    {r.university_name && (
                      <p className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{r.university_name}</p>
                    )}
                  </div>
                  <p className="text-xs text-red-600 dark:text-red-400 max-w-[50%] text-right shrink-0">
                    {r.error_message || 'Unknown error'}
                  </p>
                </div>
              ))}
          </div>
        </details>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Template Editor */}
      {/* ------------------------------------------------------------------ */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 dark:border-gray-700">
          <MessageSquareText className="w-4 h-4 text-indigo-500" />
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Message Template</h2>
        </div>
        <div className="p-4">
          {/* Placeholder buttons */}
          <div className="flex flex-wrap gap-2 mb-3">
            {PLACEHOLDERS.map((p) => {
              const Icon = p.icon
              return (
                <button
                  key={p.key}
                  onClick={() => insertPlaceholder(p.key)}
                  disabled={!isDraft}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-lg hover:bg-indigo-100 dark:hover:bg-indigo-900/50 disabled:opacity-40 transition-colors border border-indigo-200 dark:border-indigo-800"
                >
                  <Icon className="w-3 h-3" />
                  {p.label}
                </button>
              )
            })}
          </div>
          <textarea
            ref={templateRef}
            value={currentTemplate}
            onChange={(e) => setTemplateDraft(e.target.value)}
            disabled={!isDraft}
            rows={6}
            placeholder="Halo {nama_kontak}, kami dari LSP ingin menghubungi {nama_universitas}..."
            className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm dark:bg-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed resize-none"
          />
          <p className="mt-1.5 text-[11px] text-gray-400 dark:text-gray-500">
            Use placeholders above to personalize each message. They will be replaced with actual contact data.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Recipients */}
      {/* ------------------------------------------------------------------ */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-indigo-500" />
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
              Recipients
              {totalRecipients > 0 && (
                <span className="ml-1.5 text-xs font-normal text-gray-400">({totalRecipients})</span>
              )}
            </h2>
          </div>
          {isDraft && (
            <div className="flex items-center gap-2">
              {totalRecipients > 0 && (
                <button
                  onClick={() => {
                    if (confirm('Remove all pending recipients?')) clearMutation.mutate(campaignId)
                  }}
                  disabled={clearMutation.isPending}
                  className="px-2.5 py-1 text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                >
                  Clear All
                </button>
              )}
              <button
                onClick={() => setShowContactModal(true)}
                className="flex items-center gap-1 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded-lg transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Contacts
              </button>
            </div>
          )}
        </div>

        {loadingRecipients ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
          </div>
        ) : recipients.length === 0 ? (
          <div className="text-center py-10">
            <Users className="w-8 h-8 mx-auto text-gray-300 dark:text-gray-600 mb-2" />
            <p className="text-sm text-gray-400 dark:text-gray-500">No recipients yet</p>
            {isDraft && (
              <button
                onClick={() => setShowContactModal(true)}
                className="mt-2 text-sm text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 font-medium"
              >
                + Add contacts from database
              </button>
            )}
          </div>
        ) : (
          <div>
            {/* Table header */}
            <div className="grid grid-cols-[1fr_1fr_1fr_80px_40px] gap-2 px-4 py-2 bg-gray-50 dark:bg-gray-750 text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
              <span>Contact</span>
              <span>University</span>
              <span>Phone</span>
              <span>Status</span>
              <span></span>
            </div>
            {/* Rows */}
            {recipients.map((r) => (
              <div
                key={r.id}
                className="grid grid-cols-[1fr_1fr_1fr_80px_40px] gap-2 items-center px-4 py-2 border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm"
              >
                <span className="truncate text-gray-900 dark:text-gray-100">
                  {r.contact_name || '-'}
                </span>
                <span className="truncate text-gray-500 dark:text-gray-400 text-xs">
                  {r.university_name || '-'}
                </span>
                <span className="text-gray-600 dark:text-gray-400 text-xs font-mono">{r.phone_number}</span>
                <RecipientStatusBadge status={r.status} />
                <div>
                  {isDraft && r.status === 'pending' && (
                    <button
                      onClick={() => removeMutation.mutate({ campaignId, recipientId: r.id })}
                      className="p-1 rounded text-gray-300 hover:text-red-500 transition-colors"
                      title="Remove"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {r.status === 'failed' && r.error_message && (
                    <span title={r.error_message}>
                      <AlertCircle className="w-3.5 h-3.5 text-red-400 cursor-help" />
                    </span>
                  )}
                </div>
              </div>
            ))}

            {/* Pagination */}
            {totalRecipients > RECIPIENTS_PER_PAGE && (
              <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50 dark:bg-gray-800/50">
                <span className="text-xs text-gray-400">
                  Page {recipientPage + 1} of {Math.ceil(totalRecipients / RECIPIENTS_PER_PAGE)}
                </span>
                <div className="flex gap-1">
                  <button
                    onClick={() => setRecipientPage((p) => Math.max(0, p - 1))}
                    disabled={recipientPage === 0}
                    className="px-2.5 py-1 text-xs rounded border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                  >
                    Prev
                  </button>
                  <button
                    onClick={() => setRecipientPage((p) => p + 1)}
                    disabled={(recipientPage + 1) * RECIPIENTS_PER_PAGE >= totalRecipients}
                    className="px-2.5 py-1 text-xs rounded border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Settings (collapsible) */}
      {/* ------------------------------------------------------------------ */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-indigo-500" />
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Sending Settings</h2>
          </div>
          {showSettings ? (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          )}
        </button>
        {showSettings && (
          <div className="px-4 pb-4 pt-1 border-t border-gray-100 dark:border-gray-700 space-y-4">
            {/* Device selector */}
            <div>
              <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                <Smartphone className="w-3.5 h-3.5" />
                WhatsApp Device
              </label>
              <select
                value={currentDevice}
                onChange={(e) => setDeviceDraft(e.target.value)}
                disabled={!isDraft}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm dark:bg-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-60"
              >
                {['device_1', 'device_2', 'device_3', 'device_4', 'device_5'].map((did) => {
                  const dev = devicesData?.devices?.find((d) => d.id === did)
                  const isConnected = dev?.connectionState === 'connected'
                  return (
                    <option key={did} value={did}>
                      {did} {dev?.phoneNumber ? `(${dev.phoneNumber})` : ''} {isConnected ? '✓ Connected' : '✗ Offline'}
                    </option>
                  )
                })}
              </select>
              {connectedDevices.length === 0 && (
                <p className="mt-1 text-[11px] text-amber-500">
                  No devices connected. Connect a device on the WhatsApp page first.
                </p>
              )}
            </div>

            {/* Delay between messages */}
            <div>
              <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                <Timer className="w-3.5 h-3.5" />
                Delay Between Messages (ms)
              </label>
              <input
                type="number"
                value={currentDelay}
                onChange={(e) => setDelayDraft(Math.max(1000, Number(e.target.value)))}
                disabled={!isDraft}
                min={1000}
                step={1000}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm dark:bg-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-60"
              />
              <p className="mt-1 text-[11px] text-gray-400">
                Fixed delay between each message. Recommended: 5000–15000ms for safety.
              </p>
            </div>

            {/* Human-like delay range */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                  <Zap className="w-3.5 h-3.5" />
                  Human Delay Min (ms)
                </label>
                <input
                  type="number"
                  value={currentHumanMin}
                  onChange={(e) => setHumanMinDraft(Math.max(500, Number(e.target.value)))}
                  disabled={!isDraft}
                  min={500}
                  step={500}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm dark:bg-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-60"
                />
              </div>
              <div>
                <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                  <Zap className="w-3.5 h-3.5" />
                  Human Delay Max (ms)
                </label>
                <input
                  type="number"
                  value={currentHumanMax}
                  onChange={(e) => setHumanMaxDraft(Math.max(currentHumanMin + 500, Number(e.target.value)))}
                  disabled={!isDraft}
                  min={1000}
                  step={500}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm dark:bg-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-60"
                />
              </div>
            </div>
            <p className="text-[11px] text-gray-400">
              Random extra delay added per message to mimic human behavior. Total delay = fixed + random(min, max).
            </p>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Message Preview */}
      {/* ------------------------------------------------------------------ */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        <button
          onClick={() => setShowPreview(!showPreview)}
          className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Eye className="w-4 h-4 text-indigo-500" />
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Message Preview</h2>
          </div>
          {showPreview ? (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          )}
        </button>
        {showPreview && (
          <div className="px-4 pb-4 pt-1 border-t border-gray-100 dark:border-gray-700">
            {!previewData?.previews?.length ? (
              <p className="text-sm text-gray-400 py-4 text-center">
                {!currentTemplate.trim()
                  ? 'Write a template first to see previews'
                  : totalRecipients === 0
                    ? 'Add recipients first'
                    : 'Save changes to generate preview'}
              </p>
            ) : (
              <div className="space-y-3 mt-2">
                {previewData.previews.map((p, i) => (
                  <div key={i} className="flex gap-3">
                    {/* Chat bubble */}
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
                          → {p.phone_number}
                        </span>
                        {p.contact_name && (
                          <span className="text-[11px] text-gray-400">({p.contact_name})</span>
                        )}
                      </div>
                      <div className="bg-green-100 dark:bg-green-900/30 text-gray-800 dark:text-gray-200 text-sm px-3 py-2 rounded-lg rounded-tl-sm max-w-md whitespace-pre-wrap">
                        {p.rendered_message}
                      </div>
                    </div>
                  </div>
                ))}
                <p className="text-[11px] text-gray-400 text-center mt-2">
                  Showing up to 5 sample messages
                </p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Contact Selector Modal */}
      {showContactModal && (
        <ContactSelectorModal
          campaignId={campaignId}
          onClose={() => setShowContactModal(false)}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Status badge (reused from list page)
// ---------------------------------------------------------------------------

const campaignStatusConfig: Record<
  string,
  { label: string; color: string; bg: string; icon: React.ElementType }
> = {
  draft: { label: 'Draft', color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-100 dark:bg-gray-800', icon: Clock },
  sending: { label: 'Sending', color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/30', icon: Send },
  paused: { label: 'Paused', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/30', icon: Pause },
  completed: { label: 'Completed', color: 'text-green-600 dark:text-green-400', bg: 'bg-green-50 dark:bg-green-900/30', icon: CheckCircle2 },
  cancelled: { label: 'Cancelled', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/30', icon: XCircle },
}

function CampaignStatusBadge({ status }: { status: string }) {
  const cfg = campaignStatusConfig[status] || campaignStatusConfig.draft
  const Icon = cfg.icon
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold', cfg.bg, cfg.color)}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  )
}
