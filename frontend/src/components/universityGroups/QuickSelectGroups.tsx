/**
 * QuickSelectGroups — collapsible chip-based group selector for blast modals.
 * Reusable across WhatsApp blast and Email blast modals.
 */

import { useState } from 'react'
import { ChevronDown, ChevronRight, Check } from 'lucide-react'
import { cn } from '../../lib/utils'
import { Spinner } from '../ui/Spinner'
import type { UniversityGroup } from '../../api/universityGroups'

interface QuickSelectGroupsProps {
  groups: UniversityGroup[]
  selectedGroupIds: Set<number>
  onToggle: (groupId: number) => void
  isLoading?: boolean
}

export function QuickSelectGroups({ groups, selectedGroupIds, onToggle, isLoading }: QuickSelectGroupsProps) {
  const [isOpen, setIsOpen] = useState(false)

  if (groups.length === 0) return null

  return (
    <div className="mb-3">
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200"
      >
        {isOpen ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        Quick-Select by Group
        {selectedGroupIds.size > 0 && (
          <span className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-indigo-500 text-[10px] font-bold text-white">
            {selectedGroupIds.size}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="mt-2 flex flex-wrap gap-2">
          {isLoading ? (
            <Spinner size="sm" />
          ) : (
            groups.map((group) => {
              const isSelected = selectedGroupIds.has(group.id)
              return (
                <button
                  key={group.id}
                  onClick={() => onToggle(group.id)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                    isSelected
                      ? 'border-indigo-400 bg-indigo-100 text-indigo-700 dark:border-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-300'
                      : 'border-gray-200 bg-white text-gray-600 hover:border-indigo-300 hover:text-indigo-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400 dark:hover:border-indigo-600 dark:hover:text-indigo-400',
                  )}
                  title={`${group.university_count} universities`}
                >
                  {isSelected && <Check className="h-3 w-3 shrink-0" />}
                  <span className="truncate max-w-[140px]">{group.name}</span>
                  <span className="shrink-0 text-[10px] opacity-70">
                    ({group.university_count})
                  </span>
                </button>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
