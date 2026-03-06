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
} from 'lucide-react'
import { cn } from '../../lib/utils'
import {
  useBlastCampaigns,
  useCreateCampaign,
  useAddRecipients,
} from '../../hooks/useBlast'
import type { BlastCampaign } from '../../api/blast'

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

  const { data: campaignsData, isLoading: loadingCampaigns } = useBlastCampaigns(
    { status: 'draft', limit: 50 },
  )
  const createMutation = useCreateCampaign()
  const addMutation = useAddRecipients()

  const draftCampaigns = campaignsData?.data || []

  if (!isOpen) return null

  const handleAddToCampaign = (campaignId: number) => {
    setSelectedCampaignId(campaignId)

    const payload: { campaignId: number; contact_ids?: number[]; university_ids?: number[] } = {
      campaignId,
    }
    if (contactIds?.length) payload.contact_ids = contactIds
    if (universityIds?.length) payload.university_ids = universityIds

    addMutation.mutate(payload, {
      onSuccess: (result) => {
        setAddedResult({ added: result.added, skipped: result.skipped })
      },
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
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md max-h-[80vh] flex flex-col">
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
                  disabled={addMutation.isPending}
                  className={cn(
                    'w-full flex items-center justify-between p-3 rounded-lg border text-left transition-all',
                    selectedCampaignId === c.id && addMutation.isPending
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
                  {selectedCampaignId === c.id && addMutation.isPending ? (
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
      </div>
    </div>
  )
}
