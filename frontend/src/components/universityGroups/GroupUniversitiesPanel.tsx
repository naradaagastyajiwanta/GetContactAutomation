/**
 * GroupUniversitiesPanel — right panel for managing group membership.
 * Shows a search + province filter + checkbox list of all universities.
 * Checking/unchecking adds/removes universities from the group in real-time.
 */

import { useState, useMemo } from 'react'
import { Search, MapPin, ExternalLink, Trash2, Users, Check } from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { EmptyState } from '../ui/EmptyState'
import { Select } from '../ui/Select'
import { useUniversities } from '../../hooks/useUniversities'
import { useAddUniversitiesToGroup, useRemoveUniversitiesFromGroup } from '../../hooks/useUniversityGroups'
import type { UniversityGroupDetail } from '../../api/universityGroups'
import type { University } from '../../lib/types'

interface GroupUniversitiesPanelProps {
  group: UniversityGroupDetail
  onGroupUpdated: () => void
  onDelete: () => void
}

export function GroupUniversitiesPanel({ group, onGroupUpdated, onDelete }: GroupUniversitiesPanelProps) {
  const [search, setSearch] = useState('')
  const [province, setProvince] = useState('')
  const [showOnlyMembers, setShowOnlyMembers] = useState(true)
  const [pendingChecked, setPendingChecked] = useState<Set<number>>(
    () => new Set(group.universities.map((u) => u.id))
  )

  const { data: univData, isLoading } = useUniversities(
    { limit: 1000, province: province || undefined },
    false
  )
  const addMutation = useAddUniversitiesToGroup()
  const removeMutation = useRemoveUniversitiesFromGroup()

  const memberIds = useMemo(() => new Set(group.universities.map((u) => u.id)), [group])

  // All universities from DB (for "add" mode)
  const allUniversities: University[] = univData?.data ?? []

  // Universities to display: either members-only or all, filtered by search/province
  const displayedUniversities: (University | { id: number; name: string; province: string | null; website: string | null; ig_handle: string | null; email_kampus: string | null; student_count: number | null })[] = useMemo(() => {
    if (showOnlyMembers) {
      // Show only members (use group.universities which has the full data)
      const searchLower = search.toLowerCase().trim()
      return group.universities.filter((u) => {
        if (searchLower && !u.name.toLowerCase().includes(searchLower)) return false
        if (province && u.province !== province) return false
        return true
      })
    } else {
      // Show all universities
      const searchLower = search.toLowerCase().trim()
      return allUniversities.filter((u: University) => {
        if (searchLower && !u.name.toLowerCase().includes(searchLower)) return false
        if (province && u.province !== province) return false
        return true
      })
    }
  }, [showOnlyMembers, search, province, allUniversities, group.universities])

  const provinces = useMemo(() => {
    const source = showOnlyMembers ? group.universities : (univData?.data ?? [])
    const set = new Set<string>()
    source.forEach((u: University | { province: string | null }) => { if (u.province) set.add(u.province) })
    return Array.from(set).sort()
  }, [showOnlyMembers, univData?.data, group.universities])

  const pendingCheckedSorted = Array.from(pendingChecked)

  async function handleToggle(univId: number) {
    const isCurrentlyChecked = pendingChecked.has(univId)
    const newSet = new Set(pendingChecked)
    if (isCurrentlyChecked) {
      newSet.delete(univId)
    } else {
      newSet.add(univId)
    }
    setPendingChecked(newSet)

    // Sync to backend
    if (isCurrentlyChecked) {
      // Was checked → now unchecked: remove
      await removeMutation.mutateAsync({ groupId: group.id, universityIds: [univId] })
    } else {
      // Was unchecked → now checked: add
      await addMutation.mutateAsync({ groupId: group.id, universityIds: [univId] })
    }
    onGroupUpdated()
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4 dark:border-gray-800">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{group.name}</h2>
          {group.description && (
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{group.description}</p>
          )}
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            {pendingCheckedSorted.length} university{pendingCheckedSorted.length !== 1 ? 'ies' : 'y'} in this group
          </p>
        </div>
        <Button
          variant="danger"
          size="sm"
          onClick={onDelete}
          loading={removeMutation.isPending}
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete Group
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 border-b border-gray-100 px-5 py-3 dark:border-gray-800">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={showOnlyMembers ? 'Cari di grup...' : 'Cari universities...'}
            className="h-8 w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-3 text-xs text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
          />
        </div>
        <Select
          value={province}
          onChange={setProvince}
          options={provinces.map((p) => ({ value: p, label: p }))}
          placeholder="All Provinces"
          className="h-8 min-w-[140px] text-xs"
        />
      </div>

      {/* Members-only toggle */}
      <div className="flex gap-2 border-b border-gray-100 px-5 py-2 dark:border-gray-800">
        <span className="flex items-center text-xs font-medium text-gray-500 dark:text-gray-400">
          {showOnlyMembers ? (
            <>
              <Check className="mr-1.5 h-3 w-3 text-indigo-500" />
              {group.universities.length} member{group.universities.length !== 1 ? 's' : ''}
            </>
          ) : (
            <>
              <Users className="mr-1.5 h-3 w-3 text-gray-400" />
              Semua universities
            </>
          )}
        </span>

        {showOnlyMembers ? (
          <button
            onClick={() => setShowOnlyMembers(false)}
            className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-dashed border-indigo-300 bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-600 transition-colors hover:border-indigo-400 hover:bg-indigo-100 dark:border-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-400"
          >
            + Tambah Universities
          </button>
        ) : (
          <button
            onClick={() => setShowOnlyMembers(true)}
            className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-dashed border-gray-300 bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-500 transition-colors hover:border-gray-400 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400"
          >
            ← Kembali ke Anggota
          </button>
        )}
      </div>

      {/* University list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && !showOnlyMembers ? (
          <div className="flex items-center justify-center py-12">
            <Spinner />
          </div>
        ) : displayedUniversities.length === 0 ? (
          <div className="py-8">
            <EmptyState
              icon={Users}
              title={showOnlyMembers ? 'No members in this group' : 'No universities found'}
              description={showOnlyMembers
                ? search ? 'Try a different search term.' : 'Add universities from the "All" view.'
                : search ? 'Try a different search term.' : 'No universities available.'}
            />
          </div>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-800/80">
            {displayedUniversities.map((univ) => {
              const isChecked = pendingChecked.has(univ.id)
              return (
                <label
                  key={univ.id}
                  className={cn(
                    'flex cursor-pointer items-center gap-3 px-5 py-3 transition-colors',
                    isChecked
                      ? 'bg-indigo-50/50 dark:bg-indigo-950/20'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800/50',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => handleToggle(univ.id)}
                    className="h-4 w-4 shrink-0 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
                      {univ.name}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      {univ.province && (
                        <span className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
                          <MapPin className="h-3 w-3" />
                          {univ.province}
                        </span>
                      )}
                      {univ.website && (
                        <a
                          href={univ.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="flex items-center gap-0.5 text-xs text-indigo-500 hover:text-indigo-600"
                        >
                          <ExternalLink className="h-3 w-3" />
                          Website
                        </a>
                      )}
                    </div>
                  </div>
                </label>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
