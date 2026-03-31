import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import { subscribeToLogLines, type LogLineEntry } from './useWebSocket'

const MAX_LINES = 2000

export function useSystemLogs() {
  const [lines, setLines] = useState<LogLineEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const initialized = useRef(false)

  // Load initial buffer from REST endpoint
  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    axios.get<LogLineEntry[]>('/api/logs/recent?limit=200')
      .then(res => {
        setLines(res.data)
        setError(null)
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : 'Failed to load logs')
      })
      .finally(() => setLoading(false))
  }, [])

  // Subscribe to live log lines via WebSocket
  useEffect(() => {
    const unsub = subscribeToLogLines((entry) => {
      setLines(prev => {
        const next = [...prev, entry]
        return next.length > MAX_LINES ? next.slice(next.length - MAX_LINES) : next
      })
    })
    return unsub
  }, [])

  const clear = useCallback(() => setLines([]), [])

  return { lines, loading, error, clear }
}
