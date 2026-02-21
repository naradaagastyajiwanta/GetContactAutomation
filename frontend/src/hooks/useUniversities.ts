import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  getUniversities,
  getUniversity,
  getUniversityContacts,
  getUniversityPosts,
  importUniversities,
  createUniversities,
} from '../api/universities'
import { queryKeys } from '../lib/queryKeys'

export function useUniversities(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: queryKeys.universities.list(params),
    queryFn: () =>
      getUniversities(params as { status?: string; search?: string; limit?: number; offset?: number }),
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
