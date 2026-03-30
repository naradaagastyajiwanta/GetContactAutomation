import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  getIGAccounts,
  createIGAccount,
  updateIGAccount,
  deleteIGAccount,
  testIGAccountLogin,
} from '../api/igAccounts'
import { queryKeys } from '../lib/queryKeys'

export function useIGAccounts() {
  return useQuery({
    queryKey: queryKeys.igAccounts,
    queryFn: getIGAccounts,
    refetchInterval: 30_000, // refresh pool status every 30s
  })
}

export function useCreateIGAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createIGAccount,
    onSuccess: (data) => {
      toast.success(`Account @${data.account.username} added`)
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccounts })
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.detail || 'Failed to add account'
      toast.error(msg)
    },
  })
}

export function useUpdateIGAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number } & Parameters<typeof updateIGAccount>[1]) =>
      updateIGAccount(id, payload),
    onSuccess: () => {
      toast.success('Account updated')
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccounts })
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.detail || 'Failed to update account'
      toast.error(msg)
    },
  })
}

export function useDeleteIGAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteIGAccount,
    onSuccess: () => {
      toast.success('Account removed')
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccounts })
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.detail || 'Failed to delete account'
      toast.error(msg)
    },
  })
}

export function useTestIGAccountLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: testIGAccountLogin,
    onSuccess: (data) => {
      if (data.result.success) {
        toast.success(data.result.message)
      } else {
        toast.error(data.result.message)
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccounts })
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.detail || 'Login test failed unexpectedly'
      toast.error(msg)
    },
  })
}
