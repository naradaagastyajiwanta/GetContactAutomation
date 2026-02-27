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

const WS_URL = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/ws`

let wsConnectionCount = 0

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const queryClient = useQueryClient()
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()
  const connectionIdRef = useRef<number>(++wsConnectionCount)
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    const url = WS_URL.replace(/^http/, 'ws')
    console.log(`[WS ${connectionIdRef.current}] Connecting to ${url}`)
    console.log(`[WS ${connectionIdRef.current}] API URL from env:`, import.meta.env.VITE_API_URL)

    wsRef.current = new WebSocket(url)

    wsRef.current.onopen = () => {
      console.log(`[WS ${connectionIdRef.current}] Connected`)
      setConnected(true)
      // Invalidate queries on connection to refresh data
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.status })
    }

    wsRef.current.onmessage = (event) => {
      try {
        const data: WSEvent = JSON.parse(event.data)
        console.log(`[WS ${connectionIdRef.current}] Received:`, data.type, data)
        handleEvent(data)
      } catch (e) {
        console.error(`[WS ${connectionIdRef.current}] Failed to parse message:`, e)
      }
    }

    wsRef.current.onclose = (event) => {
      console.log(`[WS ${connectionIdRef.current}] Disconnected (code: ${event.code})`)
      setConnected(false)
      // Reconnect after 5s
      reconnectTimeoutRef.current = setTimeout(() => {
        connect()
      }, 5000)
    }

    wsRef.current.onerror = (error) => {
      console.error(`[WS ${connectionIdRef.current}] Error:`, error)
      console.error(`[WS ${connectionIdRef.current}] ReadyState:`, wsRef.current?.readyState)
    }
  }, [queryClient])

  const handleEvent = useCallback((event: WSEvent) => {
    console.log(`[WS ${connectionIdRef.current}] Handling event:`, event.type)
    switch (event.type) {
      case 'agent_completed':
        const agentName = event.agent.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
        toast.success(`${agentName} completed`, {
          duration: 3000,
          icon: '✅',
        })
        console.log(`[WS ${connectionIdRef.current}] Agent completed, refetching in 500ms`)
        // Small delay to ensure DB transaction is committed
        setTimeout(() => {
          queryClient.refetchQueries({ queryKey: queryKeys.pipeline.status })
          queryClient.refetchQueries({ queryKey: queryKeys.pipeline.logs({}) })
          queryClient.refetchQueries({ queryKey: queryKeys.dashboard })
          queryClient.refetchQueries({ queryKey: queryKeys.universities.all })
          console.log(`[WS ${connectionIdRef.current}] Refetch triggered`)
        }, 500)
        break

      case 'conversation_changed':
        queryClient.invalidateQueries({ queryKey: queryKeys.conversations.detail(event.conv_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.conversations.list({}) })
        break

      case 'got_number':
        toast.success('🎉 Got secretariat number!', { duration: 5000 })
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.detail(event.uni_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard })
        break

      case 'message_sent':
        // Silent update, no toast
        queryClient.invalidateQueries({ queryKey: queryKeys.conversations.list({}) })
        break

      case 'university_updated':
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.detail(event.uni_id) })
        break

      case 'quota_reached':
        toast.error('Daily quota reached!', { duration: 5000, icon: '⚠️' })
        break

      default:
        console.log('[WS] Unknown event type:', event)
    }
  }, [queryClient])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [connect])

  return { connected }
}
