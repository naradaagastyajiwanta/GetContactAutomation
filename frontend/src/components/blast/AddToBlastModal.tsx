/**
 * AddToBlastModal — Shared modal that lets users pick an existing blast campaign
 * (or create a new one) and add contacts/universities to it.
 *
 * Usage:
 *   <AddToBlastModal
 *     isOpen={true}
 *     onClose={() => {}}
 *     contactIds={[1,2,3]}           // from ig_contacts
 *     universityIds={[10,20]}        // adds ALL contacts from these universities
 *     label="3 contacts"             // descriptive text shown in modal
 *   />
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Megaphone,
  Plus,
  Loader2,
  X,
  CheckCircle2,
  ChevronRight,
  AlertCircle,
  Phone,
  GraduationCap,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import {
  useBlastCampaigns,
  useCreateCampaign,
  useAddRecipients,
} from '../../hooks/useBlast'
import { useUniversityGroups } from '../../hooks/useUniversityGroups'
import { QuickSelectGroups } from '../universityGroups/QuickSelectGroups'
import type { BlastCampaign, PreviouslyBlastedContact } from '../../api/blast'
import { checkPreviouslyBlasted } from '../../api/blast'

interface AddToBlastModalProps {
  isOpen: boolean
  onClose: () => void
  contactIds?: number[]
  universityIds?: number[]
  label?: string
}

export function AddToBlastModal({
  isOpen,
  onClose,
  contactIds,
  universityIds,
  label,
}: AddToBlastModalProps) {
  const navigate = useNavigate()
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null)
  const [newCampaignName, setNewCampaignName] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [addedResult, setAddedResult] = useState<{ added: number; skipped: number } | null>(null)
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<number>>(new Set())

  // Previously-blasted confirmation state
  const [checking, setChecking] = useState(false)
  const [duplicates, setDuplicates] = useState<PreviouslyBlastedContact[] | null>(null)
  const [excludedIds, setExcludedIds] = useState<Set<number>>(new Set())
  const [pendingCampaignId, setPendingCampaignId] = useState<number | null>(null)
  const [allResolvedContactIds, setAllResolvedContactIds] = useState<number[]>([])

  const { data: campaignsData, isLoading: loadingCampaigns } = useBlastCampaigns(
    { status: 'draft', limit: 50 },
  )
  const { data: groupsData, isLoading: loadingGroups } = useUniversityGroups()
  const createMutation = useCreateCampaign()
  const addMutation = useAddRecipients()

  const draftCampaigns = campaignsData?.data || []

  if (!isOpen) return null

  const doAdd = (campaignId: number) => {
    // Determine payload: if we have exclusions from university_ids, use resolved contact_ids instead
    const hasExclusions = excludedIds.size > 0
    const payload: { campaignId: number; contact_ids?: number[]; university_ids?: number[]; group_ids?: number[] } = {
      campaignId,
    }

    if (hasExclusions && universityIds?.length) {
      // Switch from university_ids to explicit resolved contact_ids minus excluded
      payload.contact_ids = allResolvedContactIds.filter((id) => !excludedIds.has(id))
    } else if (contactIds?.length) {
      payload.contact_ids = contactIds.filter((id) => !excludedIds.has(id))
    } else if (universityIds?.length) {
      payload.university_ids = universityIds
    }

    if (selectedGroupIds.size > 0) {
      payload.group_ids = Array.from(selectedGroupIds)
    }

    addMutation.mutate(payload, {
      onSuccess: (result) => {
        setAddedResult({ added: result.added, skipped: result.skipped })
        setDuplicates(null)
        setExcludedIds(new Set())
        setPendingCampaignId(null)
      },
    })
  }

  const handleAddToCampaign = async (campaignId: number) => {
    setSelectedCampaignId(campaignId)
    setChecking(true)

    try {
      const params: { contact_ids?: number[]; university_ids?: number[] } = {}
      if (contactIds?.length) params.contact_ids = contactIds
      if (universityIds?.length) params.university_ids = universityIds

      // If only group_ids selected (no explicit university/contact ids), skip duplicate check
      if (Object.keys(params).length === 0 && selectedGroupIds.size === 0) {
        setChecking(false)
        doAdd(campaignId)
        return
      }

      const result = await checkPreviouslyBlasted(params)
      setAllResolvedContactIds(result.all_contact_ids)

      if (result.previously_blasted.length > 0) {
        setDuplicates(result.previously_blasted)
        setExcludedIds(new Set())
        setPendingCampaignId(campaignId)
        setChecking(false)
        return
      }
    } catch {
      // If check fails, proceed anyway
    }

    setChecking(false)
    doAdd(campaignId)
  }

  const handleConfirmAdd = () => {
    if (!pendingCampaignId) return
    doAdd(pendingCampaignId)
  }

  const handleCancelDuplicates = () => {
    setDuplicates(null)
    setExcludedIds(new Set())
    setPendingCampaignId(null)
    setSelectedCampaignId(null)
    setChecking(false)
  }

  const toggleExcluded = (id: number) => {
    setExcludedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleCreateAndAdd = () => {
    if (!newCampaignName.trim()) return
    createMutation.mutate(
      { name: newCampaignName.trim() },
      {
        onSuccess: (result) => {
          if (result.success && result.campaign) {
            handleAddToCampaign(result.campaign.id)
          }
        },
      }
    )
  }

  const handleGoToCampaign = () => {
    if (selectedCampaignId) {
      navigate(`/blast/${selectedCampaignId}`)
    }
    handleClose()
  }

  const handleClose = () => {
    setSelectedCampaignId(null)
    setNewCampaignName('')
    setShowCreate(false)
    setAddedResult(null)
    setDuplicates(null)
    setExcludedIds(new Set())
    setPendingCampaignId(null)
    setChecking(false)
    setAllResolvedContactIds([])
    setSelectedGroupIds(new Set())
    onClose()
  }

  // Success state
  if (addedResult) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-sm p-6 text-center">
          <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-900/30 mx-auto mb-3 flex items-center justify-center">
            <CheckCircle2 className="w-6 h-6 text-green-600 dark:text-green-400" />
          </div>
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-1">
            Added to Campaign
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
            {addedResult.added} added, {addedResult.skipped} skipped (duplicates)
          </p>
          <div className="flex gap-2 justify-center">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
            >
              Close
            </button>
            <button
              onClick={handleGoToCampaign}
              className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Go to Campaign
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Megaphone className="w-5 h-5 text-indigo-500" />
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                Add to Blast Campaign
              </h2>
              {label && (
                <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
              )}
            </div>
          </div>
          <button
            onClick={handleClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Quick-select by group */}
        <div className="px-4 pt-3">
          <QuickSelectGroups
            groups={groupsData?.groups ?? []}
            selectedGroupIds={selectedGroupIds}
            onToggle={(id) => {
              setSelectedGroupIds((prev) => {
                const next = new Set(prev)
                if (next.has(id)) next.delete(id)
                else next.add(id)
                return next
              })
            }}
            isLoading={loadingGroups}
          />
        </div>

        {/* Campaign list */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loadingCampaigns ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          ) : draftCampaigns.length === 0 && !showCreate ? (
            <div className="text-center py-6">
              <p className="text-sm text-gray-400 dark:text-gray-500 mb-3">
                No draft campaigns. Create one first.
              </p>
              <button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-1.5 mx-auto px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <Plus className="w-4 h-4" />
                New Campaign
              </button>
            </div>
          ) : (
            <>
              {draftCampaigns.map((c) => (
                <button
                  key={c.id}
                  onClick={() => handleAddToCampaign(c.id)}
                  disabled={addMutation.isPending || checking}
                  className={cn(
                    'w-full flex items-center justify-between p-3 rounded-lg border text-left transition-all',
                    selectedCampaignId === c.id && (addMutation.isPending || checking)
                      ? 'border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-600 hover:bg-gray-50 dark:hover:bg-gray-800',
                    'disabled:opacity-50'
                  )}
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {c.name}
                    </p>
                    <p className="text-[11px] text-gray-400 dark:text-gray-500">
                      {c.total_recipients} recipients · {c.device_id}
                    </p>
                  </div>
                  {selectedCampaignId === c.id && (addMutation.isPending || checking) ? (
                    <Loader2 className="w-4 h-4 animate-spin text-indigo-500 shrink-0" />
                  ) : (
                    <Plus className="w-4 h-4 text-gray-400 shrink-0" />
                  )}
                </button>
              ))}

              {/* Create new inline */}
              {!showCreate ? (
                <button
                  onClick={() => setShowCreate(true)}
                  className="w-full flex items-center justify-center gap-1.5 p-2.5 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 text-sm text-gray-500 dark:text-gray-400 hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  Create New Campaign
                </button>
              ) : (
                <div className="p-3 rounded-lg border border-indigo-200 dark:border-indigo-800 bg-indigo-50/50 dark:bg-indigo-900/10">
                  <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                    New Campaign Name
                  </p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newCampaignName}
                      onChange={(e) => setNewCampaignName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleCreateAndAdd()}
                      placeholder="e.g. Blast Jawa Barat"
                      autoFocus
                      className="flex-1 px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm dark:bg-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                    />
                    <button
                      onClick={handleCreateAndAdd}
                      disabled={!newCampaignName.trim() || createMutation.isPending || addMutation.isPending}
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
                    >
                      {createMutation.isPending || addMutation.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        'Create & Add'
                      )}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Previously-blasted confirmation overlay */}
        {duplicates && duplicates.length > 0 && (
          <div className="absolute inset-0 z-10 bg-white dark:bg-gray-800 rounded-2xl flex flex-col">
            {/* Overlay header */}
            <div className="p-4 border-b border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 rounded-t-2xl">
              <div className="flex items-center gap-2 mb-1">
                <AlertCircle className="w-5 h-5 text-amber-500" />
                <h3 className="text-sm font-semibold text-amber-800 dark:text-amber-300">
                  Previously Contacted
                </h3>
              </div>
              <p className="text-xs text-amber-600 dark:text-amber-400">
                {duplicates.length} of {allResolvedContactIds.length} contacts were already blasted.
                Uncheck to exclude them.
              </p>
            </div>

            {/* Duplicates list */}
            <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
              {duplicates.map((d) => {
                const excluded = excludedIds.has(d.contact_id)
                return (
                  <label
                    key={d.contact_id}
                    className={cn(
                      'flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-all',
                      excluded
                        ? 'border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/10 opacity-60'
                        : 'border-amber-200 dark:border-amber-800 bg-amber-50/30 dark:bg-amber-900/10'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={!excluded}
                      onChange={() => toggleExcluded(d.contact_id)}
                      className="mt-0.5 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <Phone className="w-3 h-3 text-gray-400 shrink-0" />
                        <span className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">
                          {d.contact_name || d.phone_number}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <GraduationCap className="w-3 h-3 text-gray-400 shrink-0" />
                        <span className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                          {d.university_name || '—'}
                        </span>
                      </div>
                      <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-0.5">
                        Blasted in "{d.campaign_name}"
                        {d.sent_at && ` · ${new Date(d.sent_at).toLocaleDateString()}`}
                      </p>
                    </div>
                  </label>
                )
              })}
            </div>

            {/* Overlay footer */}
            <div className="p-3 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between gap-2">
              <button
                onClick={handleCancelDuplicates}
                className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmAdd}
                disabled={addMutation.isPending}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
              >
                {addMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    Add {allResolvedContactIds.length - excludedIds.size} contacts
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
