import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  listUniversityGroups,
  createUniversityGroup,
  getUniversityGroup,
  updateUniversityGroup,
  deleteUniversityGroup,
  addUniversitiesToGroup,
  removeUniversitiesFromGroup,
  type UniversityGroup,
  type UniversityGroupDetail,
} from '../api/universityGroups'

// ---------------------------------------------------------------------------
// Query Hooks
// ---------------------------------------------------------------------------

export function useUniversityGroups() {
  return useQuery<{ success: boolean; groups: UniversityGroup[] }>({
    queryKey: ['university-groups'],
    queryFn: () => listUniversityGroups(),
    staleTime: 30_000,
  })
}

export function useUniversityGroup(groupId: number) {
  return useQuery<{ success: boolean; group: UniversityGroupDetail }>({
    queryKey: ['university-groups', groupId],
    queryFn: () => getUniversityGroup(groupId),
    enabled: !!groupId,
    staleTime: 30_000,
  })
}

// ---------------------------------------------------------------------------
// Mutation Hooks
// ---------------------------------------------------------------------------

export function useCreateUniversityGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description?: string }) =>
      createUniversityGroup(name, description ?? ''),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['university-groups'] })
      toast.success('Group created')
    },
    onError: () => {
      toast.error('Failed to create group')
    },
  })
}

export function useUpdateUniversityGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      groupId,
      data,
    }: {
      groupId: number
      data: { name?: string; description?: string }
    }) => updateUniversityGroup(groupId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['university-groups'] })
      queryClient.invalidateQueries({ queryKey: ['university-groups', variables.groupId] })
      toast.success('Group updated')
    },
    onError: () => {
      toast.error('Failed to update group')
    },
  })
}

export function useDeleteUniversityGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (groupId: number) => deleteUniversityGroup(groupId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['university-groups'] })
      toast.success('Group deleted')
    },
    onError: () => {
      toast.error('Failed to delete group')
    },
  })
}

export function useAddUniversitiesToGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      groupId,
      universityIds,
    }: {
      groupId: number
      universityIds: number[]
    }) => addUniversitiesToGroup(groupId, universityIds),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['university-groups'] })
      queryClient.invalidateQueries({ queryKey: ['university-groups', variables.groupId] })
    },
    onError: () => {
      toast.error('Failed to add universities to group')
    },
  })
}

export function useRemoveUniversitiesFromGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      groupId,
      universityIds,
    }: {
      groupId: number
      universityIds: number[]
    }) => removeUniversitiesFromGroup(groupId, universityIds),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['university-groups'] })
      queryClient.invalidateQueries({ queryKey: ['university-groups', variables.groupId] })
    },
    onError: () => {
      toast.error('Failed to remove universities from group')
    },
  })
}
