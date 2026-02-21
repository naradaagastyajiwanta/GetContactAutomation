import { apiClient } from './client'
import type { ApiCallLog } from '../lib/types'

function parseJsonFields(log: Record<string, unknown>): ApiCallLog {
  const parse = (val: unknown) => {
    if (typeof val === 'string') {
      try { return JSON.parse(val) } catch { return val }
    }
    return val
  }
  return {
    ...log,
    situation_tags: parse(log.situation_tags) as string[] ?? [],
    knowledge_items_injected: parse(log.knowledge_items_injected) as ApiCallLog['knowledge_items_injected'] ?? [],
    tool_calls_made: parse(log.tool_calls_made) as string[] ?? [],
    messages_sent: log.messages_sent ? parse(log.messages_sent) as ApiCallLog['messages_sent'] : null,
  } as ApiCallLog
}

export interface ApiLogsParams {
  chatbot_type?: string
  conversation_id?: number
  call_type?: string
  limit?: number
  offset?: number
}

export async function getApiLogs(params: ApiLogsParams = {}): Promise<{ logs: ApiCallLog[] }> {
  const { data } = await apiClient.get('/api-logs', { params })
  return { logs: (data.logs || []).map(parseJsonFields) }
}

export async function getApiLog(id: number): Promise<ApiCallLog> {
  const { data } = await apiClient.get(`/api-logs/${id}`)
  return parseJsonFields(data)
}
