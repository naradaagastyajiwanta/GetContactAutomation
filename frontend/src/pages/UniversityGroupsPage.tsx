/**
 * UniversityGroupsPage — manage university groups for quick blast selection.
 * Two-column layout: group list on left, group detail/members on right.
 */

import { useState } from 'react'
import { FolderPlus, GraduationCap } from 'lucide-react'
import {
  useUniversityGroups,
  useUniversityGroup,
  useDeleteUniversityGroup,
  useUpdateUniversityGroup,
  useCreateUniversityGroup,
} from '../hooks/useUniversityGroups'
import { GroupCard } from '../components/universityGroups/GroupCard'
import { GroupUniversitiesPanel } from '../components/universityGroups/GroupUniversitiesPanel'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import type { UniversityGroup } from '../api/universityGroups'

export default function UniversityGroupsPage() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  const { data, isLoading, refetch } = useUniversityGroups()
  const createMutation = useCreateUniversityGroup()
  const updateMutation = useUpdateUniversityGroup()
  const deleteMutation = useDeleteUniversityGroup()

  const groups: UniversityGroup[] = data?.groups ?? []
  const selectedGroup = groups.find((g) => g.id === selectedId) ?? null

  async function handleCreate() {
    if (!newName.trim()) return
    try {
      const result = await createMutation.mutateAsync({ name: newName.trim(), description: newDesc.trim() })
      setNewName('')
      setNewDesc('')
      setShowCreateForm(false)
      setSelectedId(result.group.id)
    } catch {
      // toast handled in hook
    }
  }

  async function handleDelete(id: number) {
    if (!confirm('Delete this group? This cannot be undone.')) return
    await deleteMutation.mutateAsync(id)
    if (selectedId === id) setSelectedId(null)
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left column: group list */}
      <div className="flex w-80 shrink-0 flex-col border-r border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900">
        {/* Header */}
        <div className="border-b border-gray-200 px-4 py-4 dark:border-gray-800">
          <div className="mb-3 flex items-center justify-between">
            <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              University Groups
            </h1>
            <span className="text-xs text-gray-400">{groups.length}</span>
          </div>

          {/* Create new group */}
          {showCreateForm ? (
            <div className="space-y-2 rounded-lg border border-indigo-200 bg-white p-3 dark:border-indigo-800 dark:bg-gray-800">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Group name"
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreate()
                  if (e.key === 'Escape') setShowCreateForm(false)
                }}
              />
              <input
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Description (optional)"
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreate()
                  if (e.key === 'Escape') setShowCreateForm(false)
                }}
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleCreate}
                  loading={createMutation.isPending}
                  className="flex-1"
                >
                  Create
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setShowCreateForm(false)
                    setNewName('')
                    setNewDesc('')
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowCreateForm(true)}
              className="w-full"
            >
              <FolderPlus className="h-4 w-4" />
              New Group
            </Button>
          )}
        </div>

        {/* Group list */}
        <div className="flex-1 overflow-y-auto p-3">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Spinner />
            </div>
          ) : groups.length === 0 ? (
            <EmptyState
              icon={GraduationCap}
              title="No groups yet"
              description="Create a group to bundle universities together for quick blast selection."
              className="py-8"
            />
          ) : (
            <div className="space-y-2">
              {groups.map((group) => (
                <GroupCard
                  key={group.id}
                  group={group}
                  isSelected={selectedId === group.id}
                  onSelect={() => setSelectedId(group.id === selectedId ? null : group.id)}
                  onDelete={() => handleDelete(group.id)}
                  onRename={(name, desc) =>
                    updateMutation.mutate({ groupId: group.id, data: { name, description: desc } })
                  }
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right column: group detail */}
      <div className="flex-1 overflow-hidden bg-white dark:bg-[#111827]">
        {selectedGroup ? (
          <GroupDetailWrapper
            groupId={selectedGroup.id}
            groupName={selectedGroup.name}
            onDeleted={() => setSelectedId(null)}
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={GraduationCap}
              title="Select a group"
              description="Choose a group from the left to manage its universities, or create a new one."
            />
          </div>
        )}
      </div>
    </div>
  )
}

// Separate wrapper so it re-fetches when groupId changes
function GroupDetailWrapper({
  groupId,
  groupName,
  onDeleted,
}: {
  groupId: number
  groupName: string
  onDeleted: () => void
}) {
  const { data, refetch } = useUniversityGroup(groupId)

  if (!data?.group) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner />
      </div>
    )
  }

  return (
    <GroupUniversitiesPanel
      group={data.group}
      onGroupUpdated={refetch}
      onDelete={onDeleted}
    />
  )
}
