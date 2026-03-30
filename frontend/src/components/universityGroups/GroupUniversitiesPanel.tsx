/**
 * GroupUniversitiesPanel — right panel for managing group membership.
 * Browse All shows a full table (like UniversitiesPage).
 * In Group shows a compact list with checkboxes.
 */

import React, { useState, useMemo, useRef, useEffect } from 'react'
import {
  Search, Users, Check, X, Plus, CheckCircle2, AlertCircle,
  ListChecks, Loader2, ClipboardList, Trash2, ArrowRight
} from 'lucide-react'
import { matchUniversityNames, type MatchedUniversity } from '../../api/universities'
import { cn, formatDate } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { EmptyState } from '../ui/EmptyState'
import { Select } from '../ui/Select'
import { Modal } from '../ui/Modal'
import { ConfirmModal } from '../ui/ConfirmModal'
import { Pagination } from '../ui/Pagination'
import { Badge } from '../ui/Badge'
import { STATUS_COLORS } from '../../lib/constants'
import { useUniversities } from '../../hooks/useUniversities'
import { useAddUniversitiesToGroup, useRemoveUniversitiesFromGroup } from '../../hooks/useUniversityGroups'
import type { UniversityGroupDetail } from '../../api/universityGroups'
import type { University } from '../../lib/types'

interface GroupUniversitiesPanelProps {
  group: UniversityGroupDetail
  onGroupUpdated: () => void
  onDelete: () => void
}

// ─── Bulk Paste Modal ──────────────────────────────────────────────────────────

interface BulkPasteModalProps {
  isOpen: boolean
  onClose: () => void
  group: UniversityGroupDetail
  onAdded: (ids: number[]) => void
}

function BulkPasteModal({ isOpen, onClose, group, onAdded }: BulkPasteModalProps) {
  const [bulkText, setBulkText] = useState('')
  const [matches, setMatches] = useState<MatchedUniversity[]>([])
  const [notMatched, setNotMatched] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState<'input' | 'results'>('input')

  const addMutation = useAddUniversitiesToGroup()
  const existingIds = useMemo(() => new Set(group.universities.map((u) => u.id)), [group])

  const lines = bulkText.split('\n').map((l) => l.trim()).filter(Boolean)
  const lineCount = lines.length

  function handleClose() {
    setBulkText('')
    setMatches([])
    setNotMatched([])
    setStep('input')
    onClose()
  }

  async function handleMatch() {
    if (!bulkText.trim()) return
    setLoading(true)
    try {
      const result = await matchUniversityNames(lines)
      setMatches(result.matches)
      setNotMatched(lines.filter(
        (l) => !result.matches.some((m) => m.matched_query.toLowerCase() === l.toLowerCase())
      ))
      setStep('results')
    } finally {
      setLoading(false)
    }
  }

  async function handleAddAll() {
    const ids = matches.map((m) => m.id)
    await addMutation.mutateAsync({ groupId: group.id, universityIds: ids })
    onAdded(ids)
    handleClose()
  }

  async function handleAddNew() {
    const newIds = matches.filter((m) => !existingIds.has(m.id)).map((m) => m.id)
    if (newIds.length === 0) return
    await addMutation.mutateAsync({ groupId: group.id, universityIds: newIds })
    onAdded(newIds)
    handleClose()
  }

  const alreadyInGroup = matches.filter((m) => existingIds.has(m.id))
  const newToAdd = matches.filter((m) => !existingIds.has(m.id))

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Bulk Add Universities" size="md">
      {step === 'input' ? (
        <div className="space-y-4">
          <div className="rounded-lg bg-indigo-50 p-3 dark:bg-indigo-950/20">
            <p className="text-xs text-indigo-700 dark:text-indigo-300">
              <span className="font-semibold">How it works:</span> Paste a list of university names — one per line — and we'll match them against the database. Fuzzy matching handles slight name variations.
            </p>
          </div>

          <div>
            <textarea
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
              placeholder={
                "Paste university names here, one per line.\n\nExamples:\nUniversitas Indonesia\nUniversitas Gadjah Mada\nITB\nPoliteknik Negeri Bandung\nUniversitas Brawijaya"
              }
              rows={8}
              autoFocus
              className="w-full resize-none rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm text-gray-800 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
            {lineCount > 0 && (
              <p className="mt-1 text-right text-xs text-gray-400">
                {lineCount} name{lineCount !== 1 ? 's' : ''} ready
              </p>
            )}
          </div>

          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">
              Also works with pasted spreadsheet columns
            </p>
            <div className="flex gap-2">
              {bulkText && (
                <button
                  onClick={() => setBulkText('')}
                  className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-400 hover:border-gray-300 hover:text-gray-600 dark:border-gray-700 dark:text-gray-500 dark:hover:border-gray-600 dark:hover:text-gray-300"
                >
                  <X className="h-3 w-3" /> Clear
                </button>
              )}
              <button
                onClick={handleMatch}
                disabled={!bulkText.trim() || loading}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Matching...
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" />
                    Match Names
                    {lineCount > 0 && <span className="ml-1">({lineCount})</span>}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {matches.length} found
            </span>
            {notMatched.length > 0 && (
              <span className="flex items-center gap-1.5 rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-600 dark:bg-red-900/40 dark:text-red-400">
                <AlertCircle className="h-3.5 w-3.5" />
                {notMatched.length} not found
              </span>
            )}
            {alreadyInGroup.length > 0 && (
              <span className="flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                {alreadyInGroup.length} already in group
              </span>
            )}
          </div>

          {matches.length > 0 && (
            <div className="max-h-52 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-800">
              {matches.map((m) => (
                <div key={m.id} className="flex items-center gap-2.5 rounded px-2 py-1.5 text-sm">
                  <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-emerald-100 dark:bg-emerald-900/40">
                    <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                  </div>
                  <span className="flex-1 truncate font-medium text-gray-800 dark:text-gray-200">{m.name}</span>
                  {m.province && (
                    <span className="shrink-0 rounded bg-gray-200 px-1.5 py-0.5 text-[11px] text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                      {m.province}
                    </span>
                  )}
                  {m.match_type === 'partial' && (
                    <span className="shrink-0 text-[11px] text-amber-500">≈ {m.matched_query}</span>
                  )}
                  {existingIds.has(m.id) && (
                    <span className="shrink-0 rounded bg-gray-300 px-1.5 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-600 dark:text-gray-400">
                      already added
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {notMatched.length > 0 && (
            <div className="max-h-28 overflow-y-auto rounded-lg border border-red-200 bg-red-50 p-2 dark:border-red-900 dark:bg-red-950/10">
              {notMatched.map((n, i) => (
                <div key={i} className="flex items-center gap-2 rounded px-2 py-1.5 text-sm text-red-500">
                  <X className="h-4 w-4 shrink-0" />
                  <span className="truncate">{n}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between pt-2">
            <button
              onClick={() => setStep('input')}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <ArrowRight className="h-4 w-4 rotate-180" />
              Back
            </button>
            <div className="flex gap-2">
              {newToAdd.length > 0 && (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleAddAll}
                    loading={addMutation.isPending}
                  >
                    Add All ({matches.length})
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleAddNew}
                    loading={addMutation.isPending}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add New ({newToAdd.length})
                  </Button>
                </>
              )}
              {newToAdd.length === 0 && alreadyInGroup.length > 0 && notMatched.length === 0 && (
                <Button size="sm" variant="outline" onClick={handleClose}>
                  Close
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ─── Main Panel ────────────────────────────────────────────────────────────────

export function GroupUniversitiesPanel({ group, onGroupUpdated, onDelete }: GroupUniversitiesPanelProps) {
  const [search, setSearch] = useState('')
  const [province, setProvince] = useState('')
  const [showOnlyMembers, setShowOnlyMembers] = useState(true)
  const [browsePage, setBrowsePage] = useState(1)
  const PAGE_SIZE = 100
  const [pendingChecked, setPendingChecked] = useState<Set<number>>(
    () => new Set(group.universities.map((u) => u.id))
  )
  const [bulkOpen, setBulkOpen] = useState(false)
  const selectAllRef = useRef<HTMLInputElement>(null)

  const [confirmModal, setConfirmModal] = useState<{
    open: boolean
    title: string
    message: string
    variant: 'danger' | 'default'
    onConfirm: () => void
  }>({ open: false, title: '', message: '', variant: 'default', onConfirm: () => {} })

  const { data: univData, isLoading } = useUniversities(
    { limit: PAGE_SIZE, offset: showOnlyMembers ? 0 : (browsePage - 1) * PAGE_SIZE, province: province || undefined },
    false
  )
  const addMutation = useAddUniversitiesToGroup()
  const removeMutation = useRemoveUniversitiesFromGroup()

  const allUniversities: University[] = univData?.data ?? []

  const displayedUniversities = useMemo(() => {
    const searchLower = search.toLowerCase().trim()
    if (showOnlyMembers) {
      return group.universities.filter((u) => {
        if (searchLower && !u.name.toLowerCase().includes(searchLower)) return false
        if (province && u.province !== province) return false
        return true
      })
    }
    return allUniversities.filter((u) => {
      if (searchLower && !u.name.toLowerCase().includes(searchLower)) return false
      if (province && u.province !== province) return false
      return true
    })
  }, [showOnlyMembers, search, province, allUniversities, group.universities])

  const provinces = useMemo(() => {
    const source = showOnlyMembers ? group.universities : (univData?.data ?? [])
    const set = new Set<string>()
    source.forEach((u) => { if (u.province) set.add(u.province) })
    return Array.from(set).sort()
  }, [showOnlyMembers, univData?.data, group.universities])

  // Indeterminate checkbox
  const allOnPageSelected = displayedUniversities.length > 0 &&
    displayedUniversities.every((u) => pendingChecked.has(u.id))
  const someOnPageSelected = displayedUniversities.length > 0 &&
    !allOnPageSelected && displayedUniversities.some((u) => pendingChecked.has(u.id))

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someOnPageSelected
    }
  }, [someOnPageSelected])

  async function handleToggle(univId: number) {
    const isCurrentlyChecked = pendingChecked.has(univId)
    const newSet = new Set(pendingChecked)
    isCurrentlyChecked ? newSet.delete(univId) : newSet.add(univId)
    setPendingChecked(newSet)

    if (isCurrentlyChecked) {
      await removeMutation.mutateAsync({ groupId: group.id, universityIds: [univId] })
    } else {
      await addMutation.mutateAsync({ groupId: group.id, universityIds: [univId] })
    }
    onGroupUpdated()
  }

  function handleMatchedAdded(ids: number[]) {
    setPendingChecked((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => next.add(id))
      return next
    })
  }

  function handleSelectAllToggle() {
    const ids = displayedUniversities.map((u) => u.id)

    if (allOnPageSelected) {
      // Deselect all on this page
      if (showOnlyMembers) {
        setConfirmModal({
          open: true,
          title: `Remove ${ids.length} universities?`,
          message: `Are you sure you want to remove ${ids.length} universities from "${group.name}"?`,
          variant: 'danger',
          onConfirm: () => {
            removeMutation.mutate({ groupId: group.id, universityIds: ids })
            onGroupUpdated()
            setPendingChecked((prev) => {
              const next = new Set(prev)
              ids.forEach((id) => next.delete(id))
              return next
            })
            setConfirmModal((m) => ({ ...m, open: false }))
          },
        })
      } else {
        // Browse All — remove from group
        setPendingChecked((prev) => {
          const idsToRemove = ids.filter((id) => prev.has(id))
          if (idsToRemove.length > 0) {
            removeMutation.mutate({ groupId: group.id, universityIds: idsToRemove })
            onGroupUpdated()
          }
          const next = new Set(prev)
          ids.forEach((id) => next.delete(id))
          return next
        })
      }
    } else {
      // Select all on this page
      setPendingChecked((prev) => {
        const next = new Set(prev)
        ids.forEach((id) => next.add(id))
        return next
      })
      if (showOnlyMembers) {
        const newIds = ids.filter((id) => !pendingChecked.has(id))
        if (newIds.length > 0) {
          setConfirmModal({
            open: true,
            title: `Add ${newIds.length} universities?`,
            message: `Add ${newIds.length} universities to "${group.name}"?`,
            variant: 'default',
            onConfirm: () => {
              addMutation.mutate({ groupId: group.id, universityIds: newIds })
              onGroupUpdated()
              setConfirmModal((m) => ({ ...m, open: false }))
            },
          })
        }
      } else {
        // Browse All — add to group
        const newIds = ids.filter((id) => !pendingChecked.has(id))
        if (newIds.length > 0) {
          addMutation.mutate({ groupId: group.id, universityIds: newIds })
          onGroupUpdated()
        }
      }
    }
  }

  return (
    <>
      <BulkPasteModal
        isOpen={bulkOpen}
        onClose={() => setBulkOpen(false)}
        group={group}
        onAdded={handleMatchedAdded}
      />

      <ConfirmModal
        isOpen={confirmModal.open}
        onClose={() => setConfirmModal((m) => ({ ...m, open: false }))}
        onConfirm={confirmModal.onConfirm}
        title={confirmModal.title}
        message={confirmModal.message}
        variant={confirmModal.variant}
        confirmLabel={confirmModal.variant === 'danger' ? 'Remove' : 'Add'}
        cancelLabel="Cancel"
        loading={removeMutation.isPending || addMutation.isPending}
      />

      <div className="flex h-full flex-col overflow-hidden">
        {/* Header */}
        <div className="border-b border-gray-100 px-4 pt-4 pb-3 dark:border-gray-800 shrink-0">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">{group.name}</h2>
              {group.description && (
                <p className="truncate text-xs text-gray-500 dark:text-gray-400">{group.description}</p>
              )}
              <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
                {pendingChecked.size} university{pendingChecked.size !== 1 ? 'ies' : 'y'} in this group
              </p>
            </div>
            <div className="flex items-center gap-1.5 ml-3 shrink-0">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setBulkOpen(true)}
                className="border-indigo-200 text-indigo-600 hover:bg-indigo-50 dark:border-indigo-800 dark:text-indigo-400 dark:hover:bg-indigo-950/20"
              >
                <ClipboardList className="h-3.5 w-3.5" />
                Bulk
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={onDelete}
                loading={removeMutation.isPending}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {/* Tabs */}
          <div className="mt-3 flex items-center gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800/50">
            <button
              onClick={() => { setShowOnlyMembers(true); setSearch(''); setProvince(''); setBrowsePage(1) }}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition-all',
                showOnlyMembers
                  ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              )}
            >
              <ListChecks className="h-3.5 w-3.5" />
              In Group
              <span className={cn(
                'ml-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold',
                showOnlyMembers
                  ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300'
                  : 'bg-gray-200 text-gray-500 dark:bg-gray-600 dark:text-gray-400'
              )}>
                {group.universities.length}
              </span>
            </button>
            <button
              onClick={() => { setShowOnlyMembers(false); setSearch(''); setProvince(''); setBrowsePage(1) }}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition-all',
                !showOnlyMembers
                  ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              )}
            >
              <Users className="h-3.5 w-3.5" />
              Browse All
            </button>
          </div>
        </div>

        {/* Search + filter */}
        <div className="flex items-center gap-2 px-4 py-2.5 shrink-0">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); if (!showOnlyMembers) setBrowsePage(1) }}
              placeholder={showOnlyMembers ? 'Search in group...' : 'Search universities...'}
              className="h-7 w-full rounded-md border border-gray-200 bg-gray-50 pl-7 pr-2 text-xs text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
            />
          </div>
          <Select
            value={province}
            onChange={(v) => { setProvince(v); if (!showOnlyMembers) setBrowsePage(1) }}
            options={provinces.map((p) => ({ value: p, label: p }))}
            placeholder="All"
            className="h-7 min-w-[100px] text-xs"
          />
        </div>

        {/* Scrollable content */}
        <div className="flex-1 min-h-0 overflow-auto">
          {isLoading && !showOnlyMembers ? (
            <div className="flex items-center justify-center py-16">
              <Spinner />
            </div>
          ) : displayedUniversities.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                icon={Users}
                title={showOnlyMembers ? 'No universities in this group' : 'No universities found'}
                description={showOnlyMembers
                  ? search ? 'Try a different search.' : 'Click "Bulk Paste" to add quickly.'
                  : search ? 'Try a different search.' : 'No universities available.'}
              />
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {/* Bulk actions bar */}
              {displayedUniversities.length > 1 && (
                <div className="sticky top-0 z-10 flex items-center gap-3 bg-indigo-50/90 px-5 py-2.5 backdrop-blur-sm dark:bg-indigo-950/20">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <div className="relative">
                      <input
                        ref={selectAllRef}
                        type="checkbox"
                        checked={allOnPageSelected}
                        onChange={handleSelectAllToggle}
                        className="peer h-4 w-4 cursor-pointer appearance-none rounded border-2 border-indigo-300 transition-all checked:border-indigo-600 checked:bg-indigo-600"
                      />
                      <svg className="pointer-events-none absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 opacity-0 peer-checked:opacity-100" viewBox="0 0 12 12" fill="none">
                        <path d="M2.5 6L5 8.5L9.5 3.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </div>
                    <span className="text-xs font-medium text-indigo-700 dark:text-indigo-300">
                      {allOnPageSelected ? 'Deselect all' : 'Select all'}
                    </span>
                  </label>
                  <span className="ml-auto rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300">
                    {displayedUniversities.filter((u) => pendingChecked.has(u.id)).length} / {displayedUniversities.length}
                  </span>
                </div>
              )}

              {/* University rows */}
              {displayedUniversities.map((univ) => {
                const isChecked = pendingChecked.has(univ.id)
                const colors = STATUS_COLORS[univ.status] || STATUS_COLORS.pending

                return (
                  <div
                    key={univ.id}
                    className={cn(
                      'group flex items-start gap-4 px-5 py-4 transition-colors',
                      isChecked
                        ? 'bg-indigo-50/50 dark:bg-indigo-950/10'
                        : 'hover:bg-gray-50/80 dark:hover:bg-gray-800/30'
                    )}
                  >
                    {/* Custom checkbox */}
                    <label className="mt-0.5 shrink-0 cursor-pointer">
                      <div className="relative">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleToggle(univ.id)}
                          className="peer h-4 w-4 cursor-pointer appearance-none rounded border-2 border-gray-300 transition-all checked:border-indigo-600 checked:bg-indigo-600 dark:border-gray-600"
                        />
                        <svg className="pointer-events-none absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 opacity-0 peer-checked:opacity-100" viewBox="0 0 12 12" fill="none">
                          <path d="M2.5 6L5 8.5L9.5 3.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </div>
                    </label>

                    {/* Info */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                            {univ.name}
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            {univ.province && (
                              <span className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                                <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                                {univ.province}
                              </span>
                            )}
                            {univ.ig_handle && (
                              <span className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                                <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z"/></svg>
                                @{univ.ig_handle}
                              </span>
                            )}
                            <Badge className={cn('text-[10px] px-1.5 py-0 font-medium', colors.bg, colors.text)}>
                              {univ.status}
                            </Badge>
                          </div>
                        </div>

                        {/* Stats on the right */}
                        <div className="shrink-0 text-right">
                          {(univ.total_contacts ?? 0) > 0 && (
                            <div className="flex items-center gap-1.5">
                              {(univ.contacted_contacts ?? 0) > 0 ? (
                                <>
                                  <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                                    {univ.contacted_contacts}
                                  </span>
                                  <span className="text-xs text-gray-400">/ {univ.total_contacts}</span>
                                </>
                              ) : (
                                <span className="text-xs text-gray-400">{univ.total_contacts} contacts</span>
                              )}
                            </div>
                          )}
                          {univ.student_count && (
                            <div className="mt-0.5 text-[11px] text-gray-400">
                              {(univ.student_count / 1000).toFixed(0)}k students
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}

              {/* Pagination */}
              {!showOnlyMembers && univData && (
                <div className="sticky bottom-0 z-10 flex items-center justify-between bg-white/95 px-5 py-3 shadow-[0_-1px_4px_rgba(0,0,0,0.06)] dark:bg-[#111827]/95 dark:shadow-none">
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    Showing {((browsePage - 1) * PAGE_SIZE) + 1}–{Math.min(browsePage * PAGE_SIZE, univData.total)} of{' '}
                    <span className="font-semibold text-gray-700 dark:text-gray-300">{univData.total.toLocaleString()}</span>{' '}
                    universities
                  </span>
                  <Pagination
                    currentPage={browsePage}
                    totalPages={Math.ceil(univData.total / PAGE_SIZE)}
                    onPageChange={(p) => {
                      setBrowsePage(p)
                      setPendingChecked((prev) => {
                        const next = new Set<number>()
                        prev.forEach((id) => next.add(id))
                        return next
                      })
                    }}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
