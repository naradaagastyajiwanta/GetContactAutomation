import { useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  getUniversities,
  getProvinces,
  getUniversity,
  getUniversityContacts,
  getUniversityPosts,
  getUniversityRelatedIgs,
  importUniversities,
  createUniversities,
  toggleUniversityEnabled,
  bulkToggleUniversities,
  toggleContactContacted,
} from '../api/universities'
import type { PaginatedUniversities } from '../api/universities'
import { queryKeys } from '../lib/queryKeys'

export function useUniversities(params: Record<string, unknown> = {}, autoRefresh = true) {
  const query = useQuery<PaginatedUniversities>({
    queryKey: queryKeys.universities.list(params),
    queryFn: () =>
      getUniversities(params as {
        status?: string
        search?: string
        province?: string
        has_ig?: boolean
        enabled?: boolean
        limit?: number
        offset?: number
      }),
    placeholderData: (prev) => prev, // keep previous data while loading next page
    refetchInterval: autoRefresh ? 30000 : false, // Auto-refresh every 30 seconds
  })

  // Refetch when tab/window gains focus
  useEffect(() => {
    if (!autoRefresh) return

    const handleFocus = () => {
      query.refetch()
    }

    window.addEventListener('focus', handleFocus)
    return () => window.removeEventListener('focus', handleFocus)
  }, [query, autoRefresh])

  return query
}

export function useProvinces() {
  return useQuery<string[]>({
    queryKey: ['universities', 'provinces'],
    queryFn: getProvinces,
    staleTime: 5 * 60 * 1000, // cache for 5 min
  })
}

export function useUniversity(id: number) {
  return useQuery({
    queryKey: queryKeys.universities.detail(id),
    queryFn: () => getUniversity(id),
    enabled: id > 0,
  })
}

export function useUniversityContacts(id: number) {
  return useQuery({
    queryKey: queryKeys.universities.contacts(id),
    queryFn: () => getUniversityContacts(id),
    enabled: id > 0,
  })
}

export function useUniversityPosts(id: number) {
  return useQuery({
    queryKey: queryKeys.universities.posts(id),
    queryFn: () => getUniversityPosts(id),
    enabled: id > 0,
  })
}

export function useUniversityRelatedIgs(id: number) {
  return useQuery({
    queryKey: queryKeys.universities.relatedIgs(id),
    queryFn: () => getUniversityRelatedIgs(id),
    enabled: id > 0,
  })
}

export function useToggleContactContacted(universityId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ contactId, contacted }: { contactId: number; contacted: boolean }) =>
      toggleContactContacted(contactId, contacted),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.contacts(universityId) })
      toast.success(variables.contacted ? 'Ditandai sudah dihubungi' : 'Ditandai belum dihubungi')
    },
    onError: () => {
      toast.error('Gagal mengubah status kontak')
    },
  })
}

export function useImportUniversities() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: importUniversities,
    onSuccess: (data) => {
      toast.success(`Imported ${data.imported} universities`)
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard })
    },
    onError: () => {
      toast.error('Failed to import universities')
    },
  })
}

export function useCreateUniversities() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createUniversities,
    onSuccess: (data) => {
      toast.success(`Added ${data.added} universities${data.skipped > 0 ? `, ${data.skipped} skipped (duplicates)` : ''}`)
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard })
    },
    onError: () => {
      toast.error('Failed to add universities')
    },
  })
}

export function useToggleEnabled() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      toggleUniversityEnabled(id, enabled),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
      toast.success(variables.enabled ? 'University enabled' : 'University disabled')
    },
    onError: () => {
      toast.error('Failed to toggle university')
    },
  })
}

export function useBulkToggle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ids, enabled }: { ids: number[]; enabled: boolean }) =>
      bulkToggleUniversities(ids, enabled),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
      toast.success(
        `${data.updated} universities ${variables.enabled ? 'enabled' : 'disabled'}`
      )
    },
    onError: () => {
      toast.error('Failed to update universities')
    },
  })
}
