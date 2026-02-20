import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getWaQr, getWaStatus, sendTestMessage, waLogout, waRestart } from '../api/whatsapp'
import { queryKeys } from '../lib/queryKeys'

export function useWaQr() {
  return useQuery({
    queryKey: queryKeys.whatsapp.qr,
    queryFn: getWaQr,
    refetchInterval: 3_000,
  })
}

export function useWaStatus() {
  return useQuery({
    queryKey: queryKeys.whatsapp.status,
    queryFn: getWaStatus,
    refetchInterval: 10_000,
  })
}

export function useSendTestMessage() {
  return useMutation({
    mutationFn: ({ to, message }: { to: string; message: string }) =>
      sendTestMessage(to, message),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Test message sent!')
      } else {
        toast.error(data.error || 'Failed to send message')
      }
    },
    onError: () => {
      toast.error('Failed to send test message')
    },
  })
}

export function useWaLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: waLogout,
    onSuccess: () => {
      toast.success('Logged out from WhatsApp')
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.all })
      queryClient.invalidateQueries({ queryKey: queryKeys.health })
    },
    onError: () => {
      toast.error('Failed to logout')
    },
  })
}

export function useWaRestart() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: waRestart,
    onSuccess: () => {
      toast.success('Restarting WhatsApp connection...')
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.all })
      queryClient.invalidateQueries({ queryKey: queryKeys.health })
    },
    onError: () => {
      toast.error('Failed to restart connection')
    },
  })
}
