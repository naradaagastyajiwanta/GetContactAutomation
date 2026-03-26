/**
 * GroupCard — displays a university group as a card with name, description, count, and actions.
 */

import { useState } from 'react'
import { GraduationCap, Pencil, Trash2, Check, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { UniversityGroup } from '../../api/universityGroups'
import { Button } from '../ui/Button'

interface GroupCardProps {
  group: UniversityGroup
  isSelected: boolean
  onSelect: () => void
  onDelete: () => void
  onRename: (name: string, description: string) => void
}

export function GroupCard({ group, isSelected, onSelect, onDelete, onRename }: GroupCardProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editName, setEditName] = useState(group.name)
  const [editDesc, setEditDesc] = useState(group.description)

  function handleSave() {
    if (editName.trim()) {
      onRename(editName.trim(), editDesc.trim())
    }
    setIsEditing(false)
  }

  function handleCancel() {
    setEditName(group.name)
    setEditDesc(group.description)
    setIsEditing(false)
  }

  return (
    <div
      onClick={onSelect}
      className={cn(
        'group relative cursor-pointer rounded-lg border p-4 transition-all',
        isSelected
          ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-400 dark:bg-indigo-950/30 dark:border-indigo-600'
          : 'border-gray-200 bg-white hover:border-indigo-300 hover:shadow-sm dark:border-gray-700 dark:bg-gray-800 dark:hover:border-indigo-600',
      )}
    >
      {/* Action buttons — only show when selected */}
      {isSelected && (
        <div className="absolute right-3 top-3 flex gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation()
              setIsEditing(true)
            }}
            className="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
            title="Edit"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            className="rounded p-1 text-gray-400 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
            title="Delete"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {isEditing ? (
        /* Inline edit form */
        <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
          <input
            autoFocus
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            placeholder="Group name"
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          />
          <input
            value={editDesc}
            onChange={(e) => setEditDesc(e.target.value)}
            placeholder="Description (optional)"
            className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={handleSave} className="flex-1">
              <Check className="h-3 w-3" /> Save
            </Button>
            <Button size="sm" variant="secondary" onClick={handleCancel}>
              <X className="h-3 w-3" />
            </Button>
          </div>
        </div>
      ) : (
        /* Normal card view */
        <>
          <div className="mb-2 flex items-center gap-2">
            <GraduationCap className="h-4 w-4 text-indigo-500" />
            <span className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
              {group.name}
            </span>
          </div>
          {group.description && (
            <p className="mb-3 truncate text-xs text-gray-500 dark:text-gray-400">
              {group.description}
            </p>
          )}
          <div className="mt-auto flex items-center justify-between">
            <span className="inline-flex items-center rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300">
              {group.university_count} university{group.university_count !== 1 ? 'ies' : 'y'}
            </span>
            {isSelected && (
              <div className="h-2 w-2 rounded-full bg-indigo-500" />
            )}
          </div>
        </>
      )}
    </div>
  )
}
