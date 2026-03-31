import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '../lib/queryKeys'
import toast from 'react-hot-toast'
import { useNotifications } from './useNotifications'
export type { Notification } from './useNotifications'

type WSEvent =
  | { type: 'agent_completed'; agent: string; stats: Record<string, unknown> }
  | { type: 'conversation_changed'; conv_id: number; state: string; phone: string }
  | { type: 'message_sent'; phone: string; timestamp: string }
  | { type: 'university_updated'; uni_id: number; status: string }
  | { type: 'got_number'; uni_id: number; phone: string }
  | { type: 'quota_reached'; remaining: number }
  | { type: 'blast_progress'; campaign_id: number; sent_count: number; failed_count: number; invalid_count: number; total: number; percent: number; status: string }
  | { type: 'blast_completed'; campaign_id: number; failed: Array<{ phone: string; name: string; university: string; error: string }> }
  | { type: 'blast_paused'; campaign_id: number; reason?: string; retry_after_ms?: number; auto_resume_at?: string | null; phone?: string }
  | { type: 'blast_resumed'; campaign_id: number; source?: string }
  | { type: 'email_quota_updated'; sent_today: number; daily_limit: number; remaining: number; is_exhausted: boolean; campaign_id: number }
  | { type: 'quota_exhausted'; campaign_id: number; remaining: number; daily_limit: number; pending_count: number }
  | { type: 'log_line'; ts: string; level: string; text: string }

// Singleton WebSocket across all hook instances
let wsInstance: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let shutdownTimer: ReturnType<typeof setTimeout> | null = null
let queryClientInstance: ReturnType<typeof useQueryClient> | null = null
let notificationsInstance: ReturnType<typeof useNotifications> | null = null
let connectedState = false
let wsSubscriberCount = 0
const _connectionSubscribers = new Set<(connected: boolean) => void>()

// ── Log-line subscriber registry ─────────────────────────────────────────────
export interface LogLineEntry { ts: string; level: string; text: string }
type LogLineCallback = (entry: LogLineEntry) => void
const _logLineSubscribers = new Set<LogLineCallback>()

export function subscribeToLogLines(cb: LogLineCallback): () => void {
  _logLineSubscribers.add(cb)
  return () => _logLineSubscribers.delete(cb)
}

function getWsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

function publishConnectionState(connected: boolean) {
  connectedState = connected
  _connectionSubscribers.forEach((callback) => callback(connected))
}

function handleEventNotifications(data: WSEvent, add: ReturnType<typeof useNotifications>['add']) {
  switch (data.type) {
    case 'agent_completed': {
      const agentName = data.agent.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
      const isError = 'error' in data.stats
      add({
        type: 'agent_completed',
        title: isError ? `${agentName} failed` : `${agentName} completed`,
        body: isError
          ? `Error: ${data.stats.error}`
          : `Processed ${data.stats.processed || 0} items — ${data.stats.success || 0} success, ${data.stats.failed || 0} failed`,
      })
      break
    }
    case 'got_number':
      add({ type: 'got_number', title: 'Secretariat number found!', body: `Got contact for university #${data.uni_id}` })
      break
    case 'blast_completed': {
      const failed = data.failed || []
      const failedCount = failed.length
      add({
        type: 'blast_completed',
        title: failedCount === 0 ? 'Blast campaign done!' : `Blast done — ${failedCount} failures`,
        body: failedCount === 0 ? 'All messages sent successfully.' : `${failedCount} recipients failed.`,
      })
      break
    }
    case 'blast_paused':
      add({
        type: 'blast_completed',
        title: 'Blast paused by anti-ban',
        body: data.reason || 'Outbound sending paused temporarily.',
      })
      break
    case 'blast_resumed':
      add({
        type: 'blast_completed',
        title: 'Blast resumed',
        body: data.source === 'auto_resume' ? 'Campaign resumed automatically.' : 'Campaign resumed.',
      })
      break
    case 'quota_reached':
      add({ type: 'quota_reached', title: 'Daily quota reached', body: `Only ${data.remaining} conversations remaining.` })
      break
    case 'quota_exhausted': {
      const d = data as Extract<WSEvent, { type: 'quota_exhausted' }>
      add({
        type: 'quota_exhausted' as const,
        title: '📧 Quota harian habis — Campaign di-pause',
        body: d.pending_count > 0
          ? `${d.pending_count} email belum terkirim. Campaign akan otomatis lanjut besok.`
          : `Quota harian (${d.daily_limit} email) sudah tercapai.`,
      })
      break
    }
    case 'conversation_changed':
      add({ type: 'conversation_changed', title: 'Conversation updated', body: `#${data.conv_id} → ${data.state}` })
      break
    case 'university_updated':
      add({ type: 'university_updated', title: 'University updated', body: `University #${data.uni_id} → ${data.status}` })
      break
  }
}

function handleEventQuery(data: WSEvent, qc: ReturnType<typeof useQueryClient>) {
  switch (data.type) {
    case 'agent_completed': {
      const agentName = data.agent.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
      toast.success(`${agentName} completed`, { duration: 3000, icon: '✅' })
      setTimeout(() => {
        qc.refetchQueries({ queryKey: queryKeys.pipeline.status })
        qc.refetchQueries({ queryKey: queryKeys.pipeline.logs({}) })
        qc.refetchQueries({ queryKey: queryKeys.dashboard })
        qc.refetchQueries({ queryKey: queryKeys.universities.all })
      }, 500)
      break
    }
    case 'conversation_changed':
      qc.invalidateQueries({ queryKey: queryKeys.conversations.detail(data.conv_id) })
      qc.invalidateQueries({ queryKey: queryKeys.conversations.list({}) })
      break
    case 'got_number':
      toast.success('Got secretariat number!', { duration: 5000 })
      qc.invalidateQueries({ queryKey: queryKeys.universities.detail(data.uni_id) })
      qc.invalidateQueries({ queryKey: queryKeys.dashboard })
      break
    case 'message_sent':
      qc.invalidateQueries({ queryKey: queryKeys.conversations.list({}) })
      break
    case 'university_updated':
      qc.invalidateQueries({ queryKey: queryKeys.universities.all })
      qc.invalidateQueries({ queryKey: queryKeys.universities.detail(data.uni_id) })
      break
    case 'quota_reached':
      toast.error('Daily quota reached!', { duration: 5000, icon: '⚠️' })
      break
    case 'blast_progress':
      // Instantly update campaign cache — no delay, progress bar moves in real-time
      qc.setQueryData(
        ['email-blast-campaign', data.campaign_id],
        (old: unknown) => {
          if (!old) return old
          const o = old as { campaign?: { sent_count?: number; failed_count?: number; invalid_count?: number; status?: string } }
          return {
            ...o,
            campaign: {
              ...o.campaign,
              sent_count: data.sent_count,
              failed_count: data.failed_count,
              invalid_count: data.invalid_count,
              status: data.status,
            },
          }
        }
      )
      // Also refresh the campaigns list and quota
      qc.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
      qc.invalidateQueries({ queryKey: ['email-blast-quota'] })
      break
    case 'blast_completed': {
      const failedCount = data.failed?.length || 0
      if (failedCount === 0) {
        toast.success('Blast campaign completed! All messages sent.', { duration: 5000, icon: '🎉' })
      } else {
        const failedNames = data.failed.slice(0, 5).map((f) => f.name || f.phone).join(', ')
        const extra = failedCount > 5 ? ` +${failedCount - 5} more` : ''
        toast.error(`Blast completed with ${failedCount} failures: ${failedNames}${extra}`, { duration: 8000 })
      }
      qc.invalidateQueries({ queryKey: queryKeys.blast })
      qc.invalidateQueries({ queryKey: queryKeys.universities.all })
      qc.invalidateQueries({ queryKey: ['email-blast-campaigns'] })
      break
    }
    case 'blast_paused':
      toast('Blast paused by anti-ban', { duration: 5000, icon: '⏸️' })
      qc.invalidateQueries({ queryKey: queryKeys.blast })
      break
    case 'blast_resumed':
      toast.success('Blast resumed', { duration: 4000, icon: '▶️' })
      qc.invalidateQueries({ queryKey: queryKeys.blast })
      break
    case 'email_quota_updated':
      // Immediately update the quota query cache with fresh data from WebSocket
      qc.setQueryData(['email-blast-quota'], (old: unknown) => ({
        ...(old as object || {}),
        sent_today: data.sent_today,
        daily_limit: data.daily_limit,
        remaining: data.remaining,
        is_exhausted: data.is_exhausted,
      }))
      break
  }
}

function onMessage(event: MessageEvent) {
  try {
    const data: WSEvent = JSON.parse(event.data)
    if (data.type === 'log_line') {
      _logLineSubscribers.forEach(cb => cb({ ts: data.ts, level: data.level, text: data.text }))
      return
    }
    if (queryClientInstance) handleEventQuery(data, queryClientInstance)
    if (notificationsInstance) handleEventNotifications(data, notificationsInstance.add)
  } catch {
    // ignore parse errors
  }
}

function connectWs() {
  if (shutdownTimer) {
    clearTimeout(shutdownTimer)
    shutdownTimer = null
  }
  if (wsInstance && (wsInstance.readyState === WebSocket.OPEN || wsInstance.readyState === WebSocket.CONNECTING)) {
    return
  }
  wsInstance = new WebSocket(getWsUrl())
  wsInstance.onopen = () => {
    publishConnectionState(true)
    if (queryClientInstance) queryClientInstance.invalidateQueries({ queryKey: queryKeys.pipeline.status })
  }
  wsInstance.onmessage = onMessage
  wsInstance.onclose = (e) => {
    wsInstance = null
    publishConnectionState(false)
    if (e.code !== 1000 && wsSubscriberCount > 0) reconnectTimer = setTimeout(connectWs, 3000)
  }
  wsInstance.onerror = () => wsInstance?.close()
}

export function useWebSocket() {
  const [connected, setConnected] = useState(connectedState)
  const queryClient = useQueryClient()
  const notifications = useNotifications()

  // Register singleton refs once
  if (!queryClientInstance) queryClientInstance = queryClient
  if (!notificationsInstance) notificationsInstance = notifications

  useEffect(() => {
    queryClientInstance = queryClient
    notificationsInstance = notifications
  }, [queryClient, notifications])

  useEffect(() => {
    wsSubscriberCount += 1
    _connectionSubscribers.add(setConnected)
    connectWs()

    return () => {
      _connectionSubscribers.delete(setConnected)
      wsSubscriberCount = Math.max(0, wsSubscriberCount - 1)
      if (wsSubscriberCount === 0) {
        if (reconnectTimer) {
          clearTimeout(reconnectTimer)
          reconnectTimer = null
        }
        shutdownTimer = setTimeout(() => {
          if (wsSubscriberCount === 0 && wsInstance && wsInstance.readyState !== WebSocket.CLOSED) {
            wsInstance.close(1000)
          }
          shutdownTimer = null
        }, 1000)
      }
    }
  }, [])

  return { connected, ...notifications }
}
