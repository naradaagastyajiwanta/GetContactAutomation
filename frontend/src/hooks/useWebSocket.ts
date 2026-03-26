import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '../lib/queryKeys'
import toast from 'react-hot-toast'

type WSEvent =
  | { type: 'agent_completed'; agent: string; stats: Record<string, unknown> }
  | { type: 'conversation_changed'; conv_id: number; state: string; phone: string }
  | { type: 'message_sent'; phone: string; timestamp: string }
  | { type: 'university_updated'; uni_id: number; status: string }
  | { type: 'got_number'; uni_id: number; phone: string }
  | { type: 'quota_reached'; remaining: number }
  | { type: 'blast_progress'; campaign_id: number; recipient_id: number; phone: string; status: string }
  | { type: 'blast_completed'; campaign_id: number; failed: Array<{ phone: string; name: string; university: string; error: string }> }

const WS_URL = import.meta.env.VITE_WS_URL
  || '/ws'

let wsConnectionCount = 0

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const queryClient = useQueryClient()
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>()
  const connectionIdRef = useRef<number>(++wsConnectionCount)
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    // Clean up any existing connection before creating a new one
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.close()
      wsRef.current = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws`

    wsRef.current = new WebSocket(url)

    wsRef.current.onopen = () => {
      setConnected(true)
      // Invalidate queries on connection to refresh data
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
    }

    wsRef.current.onmessage = (event) => {
      try {
        const data: WSEvent = JSON.parse(event.data)
        handleEvent(data)
      } catch {
        // Silently ignore unparseable messages
      }
    }

    wsRef.current.onclose = (event) => {
      setConnected(false)
      // Don't reconnect on intentional close (code 1000)
      if (event.code !== 1000) {
        reconnectTimeoutRef.current = setTimeout(() => {
          connect()
        }, 3000)
      }
    }

    wsRef.current.onerror = () => {
      // Errors are handled in onclose, no need to log
      setConnected(false)
    }
  }, [queryClient])

  const handleEvent = useCallback((event: WSEvent) => {
    switch (event.type) {
      case 'agent_completed': {
        const agentName = event.agent.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
        toast.success(`${agentName} completed`, { duration: 3000, icon: '✅' })
        setTimeout(() => {
          queryClient.refetchQueries({ queryKey: queryKeys.pipeline.status })
          queryClient.refetchQueries({ queryKey: queryKeys.pipeline.logs({}) })
          queryClient.refetchQueries({ queryKey: queryKeys.dashboard })
          queryClient.refetchQueries({ queryKey: queryKeys.universities.all })
        }, 500)
        break
      }

      case 'conversation_changed':
        queryClient.invalidateQueries({ queryKey: queryKeys.conversations.detail(event.conv_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.conversations.list({}) })
        break

      case 'got_number':
        toast.success('Got secretariat number!', { duration: 5000 })
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.detail(event.uni_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard })
        break

      case 'message_sent':
        queryClient.invalidateQueries({ queryKey: queryKeys.conversations.list({}) })
        break

      case 'university_updated':
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.detail(event.uni_id) })
        break

      case 'quota_reached':
        toast.error('Daily quota reached!', { duration: 5000, icon: '⚠️' })
        break

      case 'blast_progress':
        queryClient.invalidateQueries({ queryKey: queryKeys.blast })
        break

      case 'blast_completed': {
        const failedCount = event.failed?.length || 0
        if (failedCount === 0) {
          toast.success('Blast campaign completed! All messages sent.', { duration: 5000, icon: '🎉' })
        } else {
          const failedNames = event.failed
            .slice(0, 5)
            .map((f) => f.name || f.phone)
            .join(', ')
          const extra = failedCount > 5 ? ` +${failedCount - 5} more` : ''
          toast.error(`Blast completed with ${failedCount} failures: ${failedNames}${extra}`, { duration: 8000 })
        }
        queryClient.invalidateQueries({ queryKey: queryKeys.blast })
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
        break
      }

      default:
        break
    }
  }, [queryClient])

  useEffect(() => {
    // Small delay to avoid race with Vite HMR
    const timer = setTimeout(connect, 500)
    return () => {
      clearTimeout(timer)
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      if (wsRef.current) {
        wsRef.current.close(1000)
        wsRef.current = null
      }
    }
  }, [connect])

  return { connected }
}
